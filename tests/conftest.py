"""Shared test setup.

Tests use a fresh SQLite file per test by default. To run the whole suite on
Postgres, point SERVE_API_DATABASE_URL at an empty scratch database; every
table in it is dropped before each test.
"""

import os

import pytest
from sqlalchemy import MetaData, create_engine

from serve_api.settings import Settings

POSTGRES_URL = os.getenv("SERVE_API_DATABASE_URL", "")


@pytest.fixture(autouse=True)
def _fresh_postgres_schema():
    if not POSTGRES_URL:
        yield
        return
    engine = create_engine(Settings().sqlalchemy_url)
    existing = MetaData()
    existing.reflect(engine)
    existing.drop_all(engine)
    engine.dispose()
    yield
