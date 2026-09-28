"""Shared test setup.

Tests use a fresh SQLite file per test by default. To run the whole suite on
Postgres, point SERVE_API_DATABASE_URL at an empty scratch database; every
table in it is dropped before each test.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine

from serve_api.db import Database
from serve_api.settings import Settings

POSTGRES_URL = os.getenv("SERVE_API_DATABASE_URL", "")
PASSWORD = "correct horse battery"


def sign_in(client: TestClient, email: str | None = None) -> TestClient:
    """Sign up a new account on ``client`` (which then carries its session cookie)."""
    email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    res = client.post("/auth/signup", json={"email": email, "password": PASSWORD})
    assert res.status_code == 201, res.text
    return client


def make_user(db: Database, email: str | None = None) -> str:
    """An account created straight in the database (no usable password); returns its id."""
    return db.create_user(email or f"{uuid.uuid4().hex[:12]}@example.com", "!")["id"]


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
