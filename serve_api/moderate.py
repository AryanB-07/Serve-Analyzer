"""Look into a reported account, and suspend or unsuspend it.

    python -m serve_api.moderate show <username or email>        # the account and reports about it
    python -m serve_api.moderate suspend <username or email> --reason "Harassment (reports 12, 15)"
    python -m serve_api.moderate unsuspend <username or email>

On the server: docker compose -f deploy/docker-compose.yml exec api python -m serve_api.moderate ...

A suspended account can't sign in (its sessions end at once), and to everyone else it's hidden
as if it had blocked them: it can't be found, its conversations and requests disappear, and
serves it shared stop opening. Nothing is deleted, so unsuspending puts everything back.
The reason is kept for your records; the person is told only that the account is suspended.
"""

from __future__ import annotations

import argparse
import sys

from .auth import normalise_email
from .db import Database
from .schemas import normalise_username
from .settings import Settings


def find(db: Database, who: str) -> dict | None:
    if "@" in who.lstrip("@"):  # an email; a leading @ is a username
        return db.get_user_by_email(normalise_email(who))
    person = db.person_by_username(normalise_username(who))
    return db.get_user(person["user_id"]) if person else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("show", "suspend", "unsuspend"):
        p = sub.add_parser(name)
        p.add_argument("who", help="username (with or without @) or email")
        if name == "suspend":
            p.add_argument("--reason", required=True, help="why, for your records")
    args = parser.parse_args(argv)

    db = Database(Settings().sqlalchemy_url)
    user = find(db, args.who)
    if user is None:
        print(f"No account matches {args.who!r}.", file=sys.stderr)
        return 1
    profile = db.get_profile(user["id"]) or {}
    label = f"@{profile['username']}" if profile.get("username") else user["email"]

    if args.action == "suspend":
        db.suspend(user["id"], args.reason)
        print(f"Suspended {label}. Every session has ended.")
    elif args.action == "unsuspend":
        db.unsuspend(user["id"])
        print(f"Unsuspended {label}.")
    user = db.get_user(user["id"])
    print(f"account   {user['id']}  {user['email']}  joined {user['created_at']:%Y-%m-%d}")
    print(f"username  {profile.get('username') or '(none)'}  name: {profile.get('display_name') or '(none)'}")
    if user["suspended_at"]:
        print(f"status    SUSPENDED since {user['suspended_at']:%Y-%m-%d}: {user['suspended_reason'] or ''}")
    else:
        print("status    active")
    about = [r for r in db.people_reports() if r["reported_id"] == user["id"]]
    print(f"reports   {len(about)} about this account")
    for r in about:
        message = f'  message: "{(r["message_body"] or "")[:80]}"' if r["message_body"] else ""
        print(f"  {r['created_at']:%Y-%m-%d}  {r['reason']:<14} {(r['note'] or '')[:80]}{message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
