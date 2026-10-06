"""End-to-end smoke test of a running deployment, through the same URLs a browser uses.

    python scripts/smoke_test.py https://localhost --mailpit http://localhost:8025 --insecure

Signs up, confirms the email (reading the link from a Mailpit test inbox), uploads the
sample serve, waits for the worker to analyse it, checks the results and video, then
deletes the analysis and the account. Standard library only, so it runs on any machine
with Python. Exits non-zero on the first failure.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample_serve.mp4"
PASSWORD = "smoke test password"


class Client:
    def __init__(self, base: str, insecure: bool) -> None:
        self.base = base.rstrip("/")
        self.context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPSHandler(context=self.context),
        )

    def call(self, method: str, path: str, body=None, headers=None, raw: bytes | None = None):
        """Returns (status, headers, body bytes). HTTP errors are returned, not raised."""
        url = path if path.startswith("http") else self.base + path
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        hdrs = {"Content-Type": "application/json", "Origin": self.base, **(headers or {})}
        request = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        try:
            with self.opener.open(request, timeout=60) as res:
                return res.status, res.headers, res.read()
        except urllib.error.HTTPError as err:
            return err.code, err.headers, err.read()

    def json(self, method: str, path: str, body=None, expect: int = 200):
        status, _, data = self.call(method, path, body)
        check(status == expect, f"{method} {path} -> {status}, expected {expect}: {data[:300]!r}")
        return json.loads(data) if data else None


def check(ok: bool, message: str) -> None:
    if not ok:
        print(f"FAIL: {message}", flush=True)
        sys.exit(1)


def step(name: str) -> None:
    print(f"- {name}", flush=True)


def wait_until(what: str, fn, timeout_s: float, every_s: float = 2.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            result = fn()
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            result = None
        if result:
            return result
        time.sleep(every_s)
    check(False, f"timed out after {timeout_s:.0f}s waiting for {what}")


def latest_link(mailpit: str, to: str, path: str) -> str:
    """The token from the newest email to ``to`` whose link goes to ``path``."""

    def find():
        with urllib.request.urlopen(f"{mailpit}/api/v1/search?query=to:{to}", timeout=10) as res:
            messages = json.loads(res.read())["messages"]
        for summary in messages:  # newest first
            with urllib.request.urlopen(f"{mailpit}/api/v1/message/{summary['ID']}", timeout=10) as res:
                text = json.loads(res.read())["Text"]
            if match := re.search(rf"{re.escape(path)}\?token=([A-Za-z0-9_-]+)", text):
                return match.group(1)
        return None

    return wait_until(f"an email to {to} linking to {path}", find, timeout_s=60)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", help="the app's public URL, e.g. https://localhost")
    parser.add_argument("--mailpit", help="Mailpit's web URL, to read verification emails")
    parser.add_argument("--insecure", action="store_true", help="accept a self-signed certificate")
    parser.add_argument("--timeout", type=float, default=300, help="seconds to wait for the analysis")
    args = parser.parse_args()
    c = Client(args.base, args.insecure)
    started = time.monotonic()

    step("the API is healthy")
    wait_until("/api/health", lambda: c.call("GET", "/api/health")[0] == 200, timeout_s=180)

    step("the frontend and its client-side routes are served")
    for path in ("/", "/privacy", "/reset-password"):
        status, headers, body = c.call("GET", path, headers={"Content-Type": ""})
        check(status == 200 and b'id="root"' in body, f"GET {path} -> {status}")
    if args.base.startswith("https://"):
        status, headers, _ = c.call("GET", "/")
        check("max-age=31536000" in headers.get("Strict-Transport-Security", ""), "HSTS header missing")

    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    step(f"sign up as {email}")
    me = c.json("POST", "/api/auth/signup", {"email": email, "password": PASSWORD, "accept_terms": True}, 201)
    check(me["email_verified"] is False, "a new account should start unverified")

    body = {"hand": "right", "filename": SAMPLE.name, "content_type": "video/mp4",
            "size_bytes": SAMPLE.stat().st_size}
    if args.mailpit:
        step("analysing is refused until the email is confirmed")
        status, _, _ = c.call("POST", "/api/analyses", body)
        check(status == 403, f"expected 403 before verification, got {status}")
        step("confirm the email from the link in the inbox")
        token = latest_link(args.mailpit, email, "/verify-email")
        c.json("POST", "/api/auth/verify-email", {"token": token}, 204)
        check(c.json("GET", "/api/auth/me")["email_verified"] is True, "email still unverified")

    step("upload the sample serve")
    created = c.json("POST", "/api/analyses", body, 201)
    analysis_id, upload = created["analysis"]["id"], created["upload"]
    status, _, data = c.call("PUT", upload["url"], raw=SAMPLE.read_bytes(), headers=upload["headers"])
    check(status in (200, 204), f"upload -> {status}: {data[:200]!r}")
    c.json("POST", f"/api/analyses/{analysis_id}/start", expect=202)

    step("wait for the worker")

    def finished():
        summary = c.json("GET", f"/api/analyses/{analysis_id}")
        return summary if summary["status"] in ("succeeded", "failed") else None

    summary = wait_until("the analysis to finish", finished, timeout_s=args.timeout)
    check(summary["status"] == "succeeded", f"analysis failed: {summary.get('error')}")

    step("results, frames and the playback video load")
    result = c.json("GET", f"/api/analyses/{analysis_id}/result")
    check(result["phases"]["contact"] is not None, "no contact frame in the result")
    frames = c.json("GET", f"/api/analyses/{analysis_id}/frames")
    check(frames["n_frames"] == result["n_frames"], "frames and result disagree")
    status, headers, video = c.call("GET", result["video_url"], headers={"Range": "bytes=0-1023", "Content-Type": ""})
    check(status in (200, 206) and len(video) > 0, f"playback video -> {status}")

    if args.mailpit:
        step("password reset emails a link")
        c.json("POST", "/api/auth/password-reset", {"email": email}, 202)
        latest_link(args.mailpit, email, "/reset-password")

    step("delete the analysis, then the account")
    c.json("DELETE", f"/api/analyses/{analysis_id}", expect=204)
    status, _, _ = c.call("GET", f"/api/analyses/{analysis_id}")
    check(status == 404, f"deleted analysis still there ({status})")
    c.json("DELETE", "/api/auth/me", {"password": PASSWORD}, 204)
    status, _, _ = c.call("GET", "/api/auth/me")
    check(status == 401, f"still signed in after deleting the account ({status})")

    print(f"OK: smoke test passed in {time.monotonic() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
