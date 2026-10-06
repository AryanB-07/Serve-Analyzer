"""Deleting stored videos and results after their analysis or account is deleted.

The database deletion and the queued storage prefixes commit together (see
Database.delete_analysis / delete_user). Files are then removed right away, and
anything that fails is retried by the worker's housekeeping, so a deletion is
never forgotten.
"""

from __future__ import annotations

import logging

from . import keys
from .db import Database
from .storage import Storage

log = logging.getLogger("serve_api.purge")


def analysis_prefixes(analysis_id: str) -> list[str]:
    return [keys.upload_prefix(analysis_id), keys.output_prefix(analysis_id)]


def run_purges(db: Database, storage: Storage, ids: list[int] | None = None) -> int:
    """Delete queued prefixes (``ids``, or all pending). Returns how many are still pending."""
    left = 0
    for purge_id, prefix in db.pending_purges(ids):
        try:
            storage.delete_prefix(prefix)
        except Exception:
            log.exception("could not delete %s; will retry", prefix)
            left += 1
            continue
        db.finish_purge(purge_id)
    return left
