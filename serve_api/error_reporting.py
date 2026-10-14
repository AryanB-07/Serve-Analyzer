"""Optional exception reporting to Sentry, or anything that speaks its protocol (GlitchTip).

Off unless SERVE_API_SENTRY_DSN is set, and then only errors are sent: unhandled exceptions in
the API, and anything the API or worker logs at ERROR (a failed analysis, a failed email).
Both work on free plans: Sentry's Developer plan (5,000 errors a month) or GlitchTip, which is
open source and can be self-hosted. Performance tracing is off, so nothing else uses the quota.

What leaves the server is limited, because the Privacy Policy promises it:
- no request bodies, cookies, headers or query strings (sign-in cookies, passwords and the
  tokens in emailed links travel there), and no local variables or source lines from the
  stack trace;
- no user or IP address;
- email addresses and long tokens are masked in messages and log lines.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from .settings import Settings

log = logging.getLogger("serve_api.error_reporting")

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# Session cookies, emailed-link tokens and signed-URL signatures are long and random.
TOKEN = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")


def scrub_text(text: str) -> str:
    return TOKEN.sub("[token]", EMAIL.sub("[email]", text))


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    return value


def scrub_event(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sentry's before_send hook: drop request details and identities, mask the rest."""
    request = event.get("request")
    if request:
        url = request.get("url", "")
        event["request"] = {"method": request.get("method"), "url": scrub_text(url.split("?", 1)[0])}
    for key in ("user", "server_name"):
        event.pop(key, None)
    for key in ("message", "logentry", "exception", "breadcrumbs", "extra", "tags"):
        if key in event:
            event[key] = _scrub(event[key])
    return event


def init_error_reporting(settings: Settings, component: str) -> bool:
    """Start reporting if a DSN is configured. Returns whether it did."""
    if not settings.sentry_dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=os.getenv("SERVE_API_RELEASE") or None,
        # Personal data (users, IPs, cookies, bodies) is off by default; these turn off the rest.
        include_local_variables=False,
        include_source_context=False,  # file and line are enough: the code is in the repository
        max_request_body_size="never",
        traces_sample_rate=0.0,
        before_send=scrub_event,
        before_breadcrumb=lambda crumb, _hint: _scrub(crumb),
        integrations=[LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)],
    )
    sentry_sdk.set_tag("component", component)
    log.info("error reporting on (%s)", component)
    return True
