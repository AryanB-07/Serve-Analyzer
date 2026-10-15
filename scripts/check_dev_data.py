"""Load every account and analysis in a database through the real API, and report anything that fails.

    uv run python scripts/check_dev_data.py

Uses the API's settings (SERVE_API_DATABASE_URL, SERVE_API_DATA_DIR, storage), applies pending
migrations as the API would at startup, and gives analyses from before History's scores their
scores (the worker's housekeeping step). Then, signed in as each account (a short-lived session
made directly, so no passwords are needed, and removed afterwards):

- /auth/me, the profile (and its picture), friends, followers and following (counts matching
  the lists), blocks, each of their pages,
  conversations and their messages, and the leaderboard;
- the data download;
- that suspended accounts appear nowhere anyone else looks (and are skipped, since they
  can't sign in);
- History, every page, with each kind of filter;
- each analysis's summary, report, and for finished ones the result, the frames, and the
  thumbnail and video files the result links to;
- a note saved and put back, on one analysis per account.

Exits non-zero if anything failed, listing what.
"""

from __future__ import annotations

import secrets
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serve_api import migrate  # noqa: E402
from serve_api.app import create_app  # noqa: E402
from serve_api.auth import SESSION_COOKIE, hash_token  # noqa: E402
from serve_api.db import Database, now  # noqa: E402
from serve_api.settings import Settings  # noqa: E402
from serve_api.storage import make_storage  # noqa: E402
from serve_api.tables import analyses, sessions, users  # noqa: E402
from serve_api.worker import backfill_scores  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

FILTERS = [
    {"uploaded_from": (now() - timedelta(days=30)).isoformat()},
    {"uploaded_to": (now() - timedelta(days=30)).isoformat()},
    {"min_score": "80", "max_score": "100"},
    {"min_score": "50", "max_score": "79"},
    {"min_score": "0", "max_score": "49"},
    {"stat": "front_knee_flexion", "stat_band": "off"},
    {"stat": "wrist_height", "stat_band": "good"},
    {"stat": "back_knee_flexion", "stat_band": "borderline", "min_score": "50"},
]


class Check:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.counts: Counter[str] = Counter()

    def expect(self, ok: bool, what: str) -> bool:
        self.counts["checks"] += 1
        if not ok:
            self.failures.append(what)
        return ok

    def get(self, client: TestClient, path: str, what: str, **kw):
        res = client.get(path, **kw)
        self.expect(res.status_code in (200, 206), f"{what}: GET {path} -> {res.status_code} {res.text[:200]}")
        return res


def check_hidden(c: Check, client: TestClient, who: str, hidden_names: set[str]) -> None:
    """Suspended accounts appear nowhere another account looks."""
    for path in ("/follows", "/conversations", "/notifications", "/leaderboard"):
        res = client.get(path)
        if res.status_code == 200:
            for name in hidden_names:
                c.expect(f'"{name}"' not in res.text, f"{who}: suspended @{name} shows in {path}")
    for name in hidden_names:
        c.expect(client.get(f"/people/{name}").status_code == 404, f"{who}: suspended @{name} can be looked up")


def check_user(c: Check, client: TestClient, user: dict, settings: Settings) -> None:
    who = user["email"]
    me = c.get(client, "/auth/me", who)
    c.expect(me.status_code == 200 and me.json()["id"] == user["id"], f"{who}: /auth/me is someone else")
    c.get(client, "/auth/me/export", f"{who} data download")
    profile = c.get(client, "/profile", f"{who} profile")
    if profile.status_code == 200 and (url := profile.json()["avatar_url"]):
        parts = urlsplit(url)
        if parts.netloc in ("", "testserver"):
            path = parts.path.removeprefix(settings.public_base.rstrip("/"))
            c.get(client, f"{path}?{parts.query}", f"{who} profile picture")
        c.counts["profile pictures"] += 1
    links = c.get(client, "/follows", f"{who} friends, followers and following")
    notes = c.get(client, "/notifications", f"{who} notifications")
    c.get(client, "/notifications/unread", f"{who} notification count")
    if notes.status_code == 200:
        c.counts["notifications"] += len(notes.json())
    c.get(client, "/blocks", f"{who} blocked people")
    chats = c.get(client, "/conversations", f"{who} conversations")
    c.get(client, "/conversations/unread", f"{who} unread count")
    if chats.status_code == 200:
        for chat in chats.json():
            c.counts["conversations"] += 1
            c.get(client, f"/conversations/{chat['id']}", f"{who} conversation")
            page = c.get(client, f"/conversations/{chat['id']}/messages", f"{who} messages")
            if page.status_code == 200:
                c.counts["messages"] += len(page.json()["items"])
                for m in page.json()["items"]:
                    serve = m.get("serve")
                    if serve and serve["available"] and not m["from_you"]:  # a friend's serve: opens read-only
                        c.counts["serves shared with them"] += 1
                        for part in ("", "/result", "/frames"):
                            c.get(client, f"/analyses/{serve['analysis_id']}{part}", f"{who} opens a shared serve{part}")
    board = c.get(client, "/leaderboard", f"{who} leaderboard")
    if board.status_code == 200:
        c.counts["leaderboard places"] += len(board.json()["ranked"]) + len(board.json()["not_ranked"])
    if links.status_code == 200:
        lists = links.json()
        for group in ("friends", "followers", "following"):
            c.expect(lists["counts"][group] == len(lists[group]), f"{who}: {group} count doesn't match the list")
            for item in lists[group]:
                c.counts[f"follows ({group})"] += 1
                if name := item["person"]["username"]:
                    c.get(client, f"/people/{name}", f"{who} sees @{name}")

    # History, every page.
    items, cursor = [], None
    while True:
        res = c.get(client, "/analyses", f"{who} history", params={"limit": 20, **({"cursor": cursor} if cursor else {})})
        if res.status_code != 200:
            return
        body = res.json()
        items += body["items"]
        cursor = body["next_cursor"]
        if not cursor:
            break
    with_scores = [a for a in items if a["status"] == "succeeded" and a["overall_score"] is not None]
    for params in FILTERS:
        res = c.get(client, "/analyses", f"{who} history filtered by {params}", params={"limit": 100, **params})
        if res.status_code == 200 and "min_score" in params:
            lo, hi = int(params["min_score"]), int(params.get("max_score", 100))
            got = {a["id"] for a in res.json()["items"]}
            want = {a["id"] for a in with_scores if lo <= a["overall_score"] <= hi
                    and ("stat" not in params or (a["key_scores"] or {}).get(params["stat"], {}) is not None
                         and ((a["key_scores"] or {}).get(params["stat"]) or {}).get("band") == params["stat_band"])}
            if "stat" not in params and len(items) <= 100:
                c.expect(got == want, f"{who}: score filter {params} returned {len(got)}, expected {len(want)}")

    for a in items:
        aid, label = a["id"], f"{who} {a['filename']!r} ({a['status']})"
        c.counts["analyses"] += 1
        c.counts[a["status"]] += 1
        c.get(client, f"/analyses/{aid}", label)
        c.get(client, f"/analyses/{aid}/report", f"{label} report")
        if a["status"] != "succeeded":
            continue
        c.expect(a["counts"] is not None, f"{label}: finished but has no counts")
        c.expect(a["key_scores"] is not None or a["overall_score"] is None,
                 f"{label}: has an overall score but no key scores")
        result = c.get(client, f"/analyses/{aid}/result", f"{label} result")
        c.get(client, f"/analyses/{aid}/frames", f"{label} frames")
        if result.status_code != 200:
            continue
        r = result.json()
        for name in ("video_url", "annotated_video_url", "thumbnail_url"):
            url = r.get(name)
            parts = urlsplit(url) if url else None
            if parts and parts.netloc in ("", "testserver"):  # local storage, served by the API
                path = parts.path.removeprefix(settings.public_base.rstrip("/"))  # the proxy's prefix
                c.get(client, f"{path}?{parts.query}", f"{label} {name}", headers={"Range": "bytes=0-1023"})
        c.counts[f"results schema {'5' if r.get('confidence') is not None else 'older'}"] += 1

    # A note saved and put back.
    if items:
        a = items[0]
        res = client.put(f"/analyses/{a['id']}/note", json={"note": "check_dev_data ✓"})
        c.expect(res.status_code == 200 and res.json()["note"] == "check_dev_data ✓", f"{who}: saving a note -> {res.status_code}")
        res = client.put(f"/analyses/{a['id']}/note", json={"note": a["note"]})
        c.expect(res.status_code == 200 and res.json()["note"] == a["note"], f"{who}: restoring the note -> {res.status_code}")


def main() -> int:
    settings = Settings()
    db = Database(settings.sqlalchemy_url)
    print(f"database: {db.engine.url.render_as_string(hide_password=True)}")
    migrate.upgrade(db.engine)
    scored = 0
    while n := backfill_scores(db, make_storage(settings)):
        scored += n
    print(f"scored {scored} analyses from before History's scores")

    app = create_app(settings)
    c = Check()
    with db.engine.connect() as conn:
        everyone = [dict(r) for r in conn.execute(select(users)).mappings()]
        orphans = conn.execute(select(analyses.c.id).where(
            analyses.c.user_id.not_in(select(users.c.id)))).scalars().all()
    c.expect(not orphans, f"{len(orphans)} analyses belong to no account")
    suspended = {u["id"] for u in everyone if u.get("suspended_at")}
    hidden_names = {p["username"] for p in db.profiles_of(list(suspended)).values() if p["username"]}
    for user in everyone:
        if user["id"] in suspended:  # can't sign in; checked below to be hidden from the rest
            c.counts["suspended accounts"] += 1
            continue
        token = secrets.token_urlsafe(32)
        db.create_session(user["id"], hash_token(token), now() + timedelta(minutes=10))
        try:
            client = TestClient(app, base_url="http://testserver", raise_server_exceptions=False)
            client.cookies.set(SESSION_COOKIE, token)
            check_user(c, client, user, settings)
            check_hidden(c, client, user["email"], hidden_names)
        finally:
            with db.engine.begin() as conn:
                conn.execute(delete(sessions).where(sessions.c.token_hash == hash_token(token)))
        c.counts["accounts"] += 1

    print(", ".join(f"{v} {k}" for k, v in sorted(c.counts.items())))
    if c.failures:
        print(f"\n{len(c.failures)} FAILED:")
        for f in c.failures:
            print("  -", f)
        return 1
    print("everything loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
