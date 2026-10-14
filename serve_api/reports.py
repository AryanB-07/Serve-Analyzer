"""List what people reported with "This result looks wrong", as CSV.

    python -m serve_api.reports                 # every report
    python -m serve_api.reports --days 7        # the last week's

On the server: docker compose -f deploy/docker-compose.yml exec api python -m serve_api.reports

Each row is a labelled clip for judging the pipeline: "not_a_serve" on a finished analysis
is a non-serve the serve check let through, and "was_a_serve" on a NOT_A_SERVE failure is a
serve it rejected. The original video is kept only until it expires under the retention
policy (``original_until``), and never once the analysis or account is deleted.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import timedelta

from .db import Database, now
from .settings import Settings

COLUMNS = ["created_at", "analysis_id", "reason", "status", "error_code", "hand", "camera_view",
           "note", "original_until"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=float, help="only reports from the last N days")
    args = parser.parse_args(argv)
    settings = Settings()
    db = Database(settings.sqlalchemy_url)
    since = now() - timedelta(days=args.days) if args.days else None
    retention = timedelta(days=settings.upload_retention_days)
    writer = csv.DictWriter(sys.stdout, COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in db.reports(since):
        if row["input_deleted_at"] is not None:
            until = "deleted"
        elif settings.upload_retention_days:
            until = (row["uploaded_at"] + retention).date().isoformat()
        else:
            until = "kept"
        writer.writerow({**row, "created_at": row["created_at"].isoformat(timespec="seconds"),
                         "note": (row["note"] or "").replace("\n", " "), "original_until": until})


if __name__ == "__main__":
    main()
