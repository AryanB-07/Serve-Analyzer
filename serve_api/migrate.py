"""Schema migrations. Run with: python -m serve_api.migrate

The API applies pending migrations at startup unless SERVE_API_AUTO_MIGRATE=0;
the worker never migrates, it waits until the schema is current.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine

from .settings import Settings

log = logging.getLogger("serve_api.migrate")

# Any constant works; it only has to be the same in every process that migrates.
ADVISORY_LOCK_ID = 7_319_004_211


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(engine: Engine) -> None:
    """Bring the schema to the latest revision.

    On Postgres a transaction-scoped advisory lock serialises concurrent
    upgrades, so several API replicas can start at once.
    """
    cfg = alembic_config(engine.url.render_as_string(hide_password=False))
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.exec_driver_sql(f"SELECT pg_advisory_xact_lock({ADVISORY_LOCK_ID})")
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def is_current(engine: Engine) -> bool:
    head = ScriptDirectory.from_config(alembic_config(str(engine.url))).get_current_head()
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision() == head


def wait_until_current(engine: Engine, timeout_s: float = 120.0, poll_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    warned = False
    while not is_current(engine):
        if time.monotonic() > deadline:
            raise RuntimeError(
                "The database schema is out of date. Start the API or run "
                "`python -m serve_api.migrate`."
            )
        if not warned:
            log.warning("waiting for database migrations (start the API or run serve_api.migrate)")
            warned = True
        time.sleep(poll_s)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    engine = create_engine(settings.sqlalchemy_url)
    upgrade(engine)
    log.info("database is at the latest revision")
    engine.dispose()


if __name__ == "__main__":
    main()
