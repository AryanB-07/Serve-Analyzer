"""Alembic environment. Used by `python -m serve_api.migrate` and by the `alembic` CLI."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from serve_api.settings import Settings
from serve_api.tables import metadata

config = context.config


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        # SQLite can't ALTER most things; batch mode rebuilds the table instead.
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )


def run() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    url = config.get_main_option("sqlalchemy.url") or Settings().sqlalchemy_url
    engine = create_engine(url)
    with engine.connect() as conn:
        _configure(conn)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) migrations are not supported; run against a database.")
run()
