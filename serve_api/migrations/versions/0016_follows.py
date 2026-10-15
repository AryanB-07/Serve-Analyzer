"""Follows replace friend requests: friends are people who follow each other.

Existing data is converted: a friendship becomes a follow each way, and a pending request
becomes a follow from the person who asked. "Accepts friend requests" becomes "allows
follows", and notifications are renamed to match.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

STAMP = sa.DateTime(timezone=True)
follows = sa.table("follows", sa.column("follower_id", sa.String), sa.column("followee_id", sa.String),
                   sa.column("created_at", STAMP))
connections = sa.table("connections", sa.column("id", sa.String), sa.column("requester_id", sa.String),
                       sa.column("addressee_id", sa.String), sa.column("pair", sa.String), sa.column("status", sa.String),
                       sa.column("created_at", STAMP), sa.column("accepted_at", STAMP))
notifications = sa.table("notifications", sa.column("kind", sa.String))
KINDS = {"request_received": "new_follower", "request_accepted": "followed_back"}


def upgrade() -> None:
    op.create_table(
        "follows",
        sa.Column("follower_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("followee_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("follower_id <> followee_id", name="follows_not_self"),
    )
    op.create_index("follows_followee", "follows", ["followee_id"])
    bind = op.get_bind()
    rows = bind.execute(sa.select(connections)).mappings().all()
    new = []
    for r in rows:
        new.append({"follower_id": r["requester_id"], "followee_id": r["addressee_id"], "created_at": r["created_at"]})
        if r["status"] == "accepted":
            new.append({"follower_id": r["addressee_id"], "followee_id": r["requester_id"],
                        "created_at": r["accepted_at"] or r["created_at"]})
    if new:
        bind.execute(sa.insert(follows), new)
    op.drop_table("connections")
    with op.batch_alter_table("profiles") as batch:
        batch.alter_column("accept_requests", new_column_name="allow_follows")
    for old, renamed in KINDS.items():
        bind.execute(sa.update(notifications).where(notifications.c.kind == old).values(kind=renamed))


def downgrade() -> None:
    op.create_table(
        "connections",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("requester_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("addressee_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pair", sa.String(65), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("connections_addressee", "connections", ["addressee_id", "status"])
    op.create_index("connections_requester", "connections", ["requester_id", "status"])
    import uuid

    bind = op.get_bind()
    rows = {(r["follower_id"], r["followee_id"]): r["created_at"] for r in bind.execute(sa.select(follows)).mappings()}
    seen = set()
    for (a, b), at in rows.items():
        pair = ":".join(sorted((a, b)))
        if pair in seen:
            continue
        seen.add(pair)
        back = rows.get((b, a))
        first, second = ((a, b, at), back) if back is None or at <= back else ((b, a, back), at)
        bind.execute(sa.insert(connections).values(
            id=uuid.uuid4().hex, requester_id=first[0], addressee_id=first[1], pair=pair,
            status="accepted" if back is not None else "pending", created_at=first[2],
            accepted_at=second if back is not None else None))
    op.drop_table("follows")
    with op.batch_alter_table("profiles") as batch:
        batch.alter_column("allow_follows", new_column_name="accept_requests")
    for old, renamed in KINDS.items():
        bind.execute(sa.update(notifications).where(notifications.c.kind == renamed).values(kind=old))
