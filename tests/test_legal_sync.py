"""The Privacy Policy and Terms (frontend) must state what the backend actually does."""

import re
from pathlib import Path

from serve_api.auth import TERMS_VERSION
from serve_api.settings import Settings

CONFIG = (Path(__file__).resolve().parents[1] / "frontend/src/features/legal/config.ts").read_text()


def _ts(name: str) -> str:
    match = re.search(rf"\b{name}\b\s*[:=]\s*\"?([\w-]+)\"?", CONFIG)
    assert match, f"{name} not found in config.ts"
    return match.group(1)


def test_signups_record_the_version_the_pages_show():
    assert _ts("TERMS_VERSION") == TERMS_VERSION


def test_the_privacy_policy_states_the_default_upload_retention():
    assert int(_ts("uploadRetentionDays")) == Settings().upload_retention_days
