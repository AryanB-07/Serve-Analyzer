"""Whether a username is free: the one rule behind signup, its availability check, and Settings."""

from __future__ import annotations

from .db import Database
from .schemas import HELD, TAKEN, UsernameCheck, normalise_username, username_problem


def username_check(db: Database, username: str, user_id: str | None) -> UsernameCheck:
    """Whether ``username`` could be ``user_id``'s (None: someone signing up)."""
    name = normalise_username(username)[:40]
    if problem := username_problem(name):
        return UsernameCheck(username=name, available=False, problem=problem)
    why = db.username_unavailable(name, user_id)
    return UsernameCheck(username=name, available=why is None, problem={"taken": TAKEN, "held": HELD}.get(why or ""))
