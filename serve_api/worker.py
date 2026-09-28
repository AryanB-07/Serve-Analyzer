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
import json
import logging
import threading
import time
import uuid
from datetime import timedelta

from serve_analyzer.errors import PipelineError
from serve_analyzer.pipeline import analyze

from . import keys, migrate
from .convert import counts_from_labels, public_message
from .db import Database
from .settings import Settings
from .storage import LocalStorage

log = logging.getLogger("serve_api.worker")

LEASE = timedelta(minutes=2)
HEARTBEAT = timedelta(seconds=20)
MAX_ATTEMPTS = 3
SWEEP_EVERY_S = 30.0


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


def process(job: dict, db: Database, storage: LocalStorage, token: str,
            heartbeat_every: timedelta = HEARTBEAT) -> None:
    analysis_id = job["id"]
    video = storage.path(keys.input_key(analysis_id, job["content_type"]))
    out_dir = storage.path(keys.output_prefix(analysis_id))

    def write(status: str, **fields) -> None:
        if not db.update_claimed(analysis_id, token, status, **fields):
            log.warning("analysis %s: claim lost, %s not recorded", analysis_id, status)

    with Heartbeat(db, analysis_id, token, heartbeat_every):
        try:
            result = analyze(video, job["hand"], out_dir, on_stage=write)
        except PipelineError as exc:
            log.info("analysis %s failed: %s (%s)", analysis_id, exc.code, exc)
            write("failed", error_code=exc.code, error_message=public_message(exc.code, str(exc)))
            return
        except Exception:
            log.exception("analysis %s crashed", analysis_id)
            write("failed", error_code="INTERNAL", error_message=public_message("INTERNAL", ""))
            return
    counts = counts_from_labels(json.loads((out_dir / keys.RESULTS).read_text())["labels"])
    write("succeeded", counts=counts)
    log.info("analysis %s succeeded (contact frame %s)", analysis_id, result.phases.contact)


def sweep(db: Database, lease: timedelta = LEASE, max_attempts: int = MAX_ATTEMPTS) -> None:
    requeued, failed = db.release_stale(lease, max_attempts, public_message("INTERNAL", ""))
    if requeued:
        log.warning("requeued %d analyses whose worker stopped responding", requeued)
    if failed:
        log.warning("failed %d analyses after %d attempts", failed, max_attempts)


def run(settings: Settings, poll_s: float = 1.0, once: bool = False) -> None:
    settings.check()
    db = Database(settings.sqlalchemy_url)
    migrate.wait_until_current(db.engine)
    storage = LocalStorage(settings)
    last_sweep = float("-inf")
    while True:
        if time.monotonic() - last_sweep >= SWEEP_EVERY_S:
            sweep(db)
            last_sweep = time.monotonic()
        job = db.claim_next(uuid.uuid4().hex)
        if job is not None:
            process(job, db, storage, job["claim_token"])
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
