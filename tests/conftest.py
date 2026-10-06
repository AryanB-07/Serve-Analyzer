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
from serve_api.mailer import Email
from serve_api.settings import Settings

POSTGRES_URL = os.getenv("SERVE_API_DATABASE_URL", "")
PASSWORD = "correct horse battery"


def sign_in(client: TestClient, email: str | None = None) -> TestClient:
    """Sign up a new account on ``client`` (which then carries its session cookie)."""
    email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    res = client.post("/auth/signup", json={"email": email, "password": PASSWORD})
    assert res.status_code == 201, res.text
    return client


class FakeMailer:
    """Records messages instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, message: Email) -> None:
        self.sent.append(message)

    def last_link(self, to: str | None = None) -> str:
        """The link in the most recent message (to ``to``, if given)."""
        for message in reversed(self.sent):
            if to is None or message.to == to:
                return next(w for w in message.text.split() if w.startswith("http"))
        raise AssertionError(f"no email sent to {to}")


def production_settings(tmp_path, **overrides) -> Settings:
    """Settings that pass the production checks (a secret, SMTP, a public app URL)."""
    values = dict(data_dir=tmp_path, environment="production", secret="prod-secret",
                  smtp_host="smtp.example.com", smtp_username="mail@example.com",
                  app_url="https://serve.example.com")
    return Settings(**{**values, **overrides})


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
