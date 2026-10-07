"""Background worker: claims queued analyses and runs the pipeline.

Run with: python -m serve_api.worker   (any number of them, against the same database)

Each claim is time-limited: while processing, the worker refreshes the job's
heartbeat every HEARTBEAT; a job whose heartbeat is older than LEASE is put
back on the queue by whichever worker notices first (or failed, after
MAX_ATTEMPTS claims). A worker that loses its claim can no longer write the
job's status.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import threading
import time
import uuid
from datetime import timedelta

from serve_analyzer.errors import PipelineError
from serve_analyzer.pipeline import analyze
from serve_analyzer.pose import extract_pose_in_subprocess

from . import keys, migrate
from .convert import counts_from_labels, public_message
from .db import Database, now
from .purge import analysis_prefixes, run_purges
from .settings import Settings
from .storage import Storage, make_storage

log = logging.getLogger("serve_api.worker")

LEASE = timedelta(minutes=2)
HEARTBEAT = timedelta(seconds=20)
MAX_ATTEMPTS = 3
SWEEP_EVERY_S = 30.0
HOUSEKEEPING_EVERY_S = 3600.0
ABANDONED_AFTER = timedelta(days=1)   # an upload that never arrived
ATTEMPTS_KEPT = timedelta(days=1)     # longer than any rate-limit window


class Heartbeat:
    """Refreshes a claim from a background thread while the pipeline runs."""

    def __init__(self, db: Database, analysis_id: str, token: str, every: timedelta) -> None:
        self.db, self.analysis_id, self.token = db, analysis_id, token
        self.every = every.total_seconds()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"heartbeat-{analysis_id}")

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            try:
                if not self.db.heartbeat(self.analysis_id, self.token):
                    log.warning("analysis %s: claim lapsed; another worker may take it",
                                self.analysis_id)
                    return
            except Exception:
                log.exception("analysis %s: heartbeat failed", self.analysis_id)

    def __enter__(self) -> Heartbeat:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()


def process(job: dict, db: Database, storage: Storage, token: str,
            heartbeat_every: timedelta = HEARTBEAT) -> None:
    """Run the pipeline for one claimed job.

    Outputs are written to a private scratch folder and published only if the
    claim is still ours, so a worker that stalled past its lease can't
    overwrite the files of the worker that took the job over.
    """
    analysis_id = job["id"]

    def write(status: str, **fields) -> bool:
        if db.update_claimed(analysis_id, token, status, **fields):
            return True
        log.warning("analysis %s: claim lost, %s not recorded", analysis_id, status)
        return False

    input_key = keys.input_key(analysis_id, job["content_type"])
    with Heartbeat(db, analysis_id, token, heartbeat_every), storage.scratch_dir() as work:
        try:
            with storage.local_copy(input_key) as video:
                result = analyze(video, job["hand"], work, on_stage=write,
                                 pose_extractor=extract_pose_in_subprocess)
            counts = counts_from_labels(json.loads((work / keys.RESULTS).read_text())["labels"])
        except PipelineError as exc:
            log.info("analysis %s failed: %s (%s)", analysis_id, exc.code, exc)
            write("failed", error_code=exc.code, error_message=public_message(exc.code, str(exc)))
            return
        except Exception:
            log.exception("analysis %s crashed", analysis_id)
            write("failed", error_code="INTERNAL", error_message=public_message("INTERNAL", ""))
            return
        if not db.heartbeat(analysis_id, token):
            log.warning("analysis %s: claim lost before publishing; outputs discarded", analysis_id)
            return
        storage.publish(work, keys.output_prefix(analysis_id))
    if write("succeeded", counts=counts):
        log.info("analysis %s succeeded (contact frame %s)", analysis_id, result.phases.contact)
    elif db.get(analysis_id) is None:
        # Deleted while we were publishing: don't leave its files behind.
        for prefix in analysis_prefixes(analysis_id):
            storage.delete_prefix(prefix)
        log.info("analysis %s was deleted while processing; outputs removed", analysis_id)


def release_memory() -> None:
    """Hand memory freed by the last job back to the operating system.

    glibc keeps freed memory for reuse; after a 1080p job this returns about 115 MB
    (374 -> 258 MB measured). A no-op where libc isn't glibc (macOS, Alpine).
    """
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def sweep(db: Database, lease: timedelta = LEASE, max_attempts: int = MAX_ATTEMPTS) -> None:
    requeued, failed = db.release_stale(lease, max_attempts, public_message("INTERNAL", ""))
    if requeued:
        log.warning("requeued %d analyses whose worker stopped responding", requeued)
    if failed:
        log.warning("failed %d analyses after %d attempts", failed, max_attempts)


def housekeeping(db: Database, storage: Storage, upload_retention_days: int = 0) -> None:
    """Delete what nobody will use again: abandoned uploads, dead sessions and links, old
    attempts, and (with ``upload_retention_days``) original videos past their retention
    period. Also retries storage deletions that failed when an analysis or account was deleted."""
    if left := run_purges(db, storage):
        log.warning("%d storage deletions still pending", left)
    if upload_retention_days > 0:
        expired = db.expire_inputs(now() - timedelta(days=upload_retention_days))
        for analysis_id in expired:
            storage.delete_prefix(keys.upload_prefix(analysis_id))
            db.mark_input_deleted(analysis_id)
        if expired:
            log.info("deleted %d original uploads older than %d days", len(expired), upload_retention_days)
    for analysis_id in db.delete_abandoned_uploads(now() - ABANDONED_AFTER):
        storage.delete_prefix(keys.upload_prefix(analysis_id))
        log.info("deleted abandoned upload %s", analysis_id)
    sessions, attempts = db.delete_expired(attempts_before=now() - ATTEMPTS_KEPT)
    if sessions or attempts:
        log.info("deleted %d expired sessions and %d old sign-in attempts", sessions, attempts)


def run(settings: Settings, poll_s: float = 1.0, once: bool = False) -> None:
    settings.check()
    db = Database(settings.sqlalchemy_url)
    migrate.wait_until_current(db.engine)
    storage = make_storage(settings)
    last_sweep = last_housekeeping = float("-inf")
    while True:
        if time.monotonic() - last_sweep >= SWEEP_EVERY_S:
            sweep(db)
            last_sweep = time.monotonic()
        if time.monotonic() - last_housekeeping >= HOUSEKEEPING_EVERY_S:
            housekeeping(db, storage, settings.upload_retention_days)
            last_housekeeping = time.monotonic()
        job = db.claim_next(uuid.uuid4().hex)
        if job is not None:
            process(job, db, storage, job["claim_token"])
            release_memory()
        elif once:
            return
        else:
            time.sleep(poll_s)


def main() -> None:
    parser = argparse.ArgumentParser(prog="serve_api.worker")
    parser.add_argument("--once", action="store_true", help="exit when the queue is empty")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("alembic").setLevel(logging.WARNING)
    run(Settings(), once=args.once)


if __name__ == "__main__":
    main()
