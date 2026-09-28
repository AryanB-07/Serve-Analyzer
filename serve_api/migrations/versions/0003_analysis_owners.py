"""Every analysis belongs to a user.

Analyses created before accounts existed are given to the oldest account. If
there are none, a placeholder owner is created instead (it has no usable
password, so nobody can sign in as it); nothing is deleted.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

PLACEHOLDER_EMAIL = "legacy-owner@serve-analyzer.invalid"

users = sa.table(
    "users",
    sa.column("id", sa.String), sa.column("email", sa.String),
    sa.column("password_hash", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
)


def _owner_for_existing_rows(bind) -> str:
    owner = bind.execute(sa.text("SELECT id FROM users ORDER BY created_at, id LIMIT 1")).scalar()
    if owner is None:
        owner = uuid.uuid4().hex
        # "!" is not a valid argon2 hash, so no password ever matches it.
        op.bulk_insert(users, [{"id": owner, "email": PLACEHOLDER_EMAIL, "password_hash": "!",
                                "created_at": datetime.now(UTC)}])
    return owner


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("user_id", sa.String(32), nullable=True))
    if bind.execute(sa.text("SELECT 1 FROM analyses LIMIT 1")).first():
        bind.execute(sa.text("UPDATE analyses SET user_id = :owner WHERE user_id IS NULL"),
                     {"owner": _owner_for_existing_rows(bind)})
    with op.batch_alter_table("analyses") as batch:
        batch.alter_column("user_id", existing_type=sa.String(32), nullable=False)
        batch.create_foreign_key("fk_analyses_user_id_users", "users", ["user_id"], ["id"],
                                 ondelete="CASCADE")
        batch.drop_index("analyses_created")
        batch.create_index("analyses_user_created", ["user_id", "created_at", "id"])


def downgrade() -> None:
    with op.batch_alter_table("analyses") as batch:
        batch.drop_index("analyses_user_created")
        batch.create_index("analyses_created", ["created_at", "id"])
        batch.drop_constraint("fk_analyses_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")
