"""Background worker: claims queued analyses and runs the pipeline.

Run with: python -m serve_api.worker
"""

from __future__ import annotations

import argparse
import json
import logging
import time

from serve_analyzer.errors import PipelineError
from serve_analyzer.pipeline import analyze

from . import keys
from .convert import counts_from_labels, public_message
from .db import Database
from .settings import Settings
from .storage import LocalStorage

log = logging.getLogger("serve_api.worker")


def process(job: dict, db: Database, storage: LocalStorage) -> None:
    analysis_id = job["id"]
    video = storage.path(keys.input_key(analysis_id, job["content_type"]))
    out_dir = storage.path(keys.output_prefix(analysis_id))
    try:
        result = analyze(
            video, job["hand"], out_dir,
            on_stage=lambda stage: db.set_status(analysis_id, stage),
        )
    except PipelineError as exc:
        log.info("analysis %s failed: %s (%s)", analysis_id, exc.code, exc)
        db.set_status(analysis_id, "failed", error_code=exc.code,
                      error_message=public_message(exc.code, str(exc)))
        return
    except Exception:
        log.exception("analysis %s crashed", analysis_id)
        db.set_status(analysis_id, "failed", error_code="INTERNAL",
                      error_message=public_message("INTERNAL", ""))
        return
    counts = counts_from_labels(json.loads((out_dir / keys.RESULTS).read_text())["labels"])
    db.set_status(analysis_id, "succeeded", counts=counts)
    log.info("analysis %s succeeded (contact frame %s)", analysis_id, result.phases.contact)


def run(settings: Settings, poll_s: float = 1.0, once: bool = False) -> None:
    db = Database(settings.db_path)
    storage = LocalStorage(settings)
    if requeued := db.requeue_interrupted():
        log.warning("requeued %d interrupted analyses", requeued)
    while True:
        job = db.claim_next()
        if job is not None:
            process(job, db, storage)
        elif once:
            return
        else:
            time.sleep(poll_s)


def main() -> None:
    parser = argparse.ArgumentParser(prog="serve_api.worker")
    parser.add_argument("--once", action="store_true", help="exit when the queue is empty")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(Settings(), once=args.once)


if __name__ == "__main__":
    main()
