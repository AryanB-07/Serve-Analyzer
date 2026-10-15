"""Posts (a snapshot of a serve, public or friends-only), likes and comments; reports of them.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_id", sa.String(32)),
        sa.Column("caption", sa.Text),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("hand", sa.String(8), nullable=False),
        sa.Column("overall_score", sa.Integer),
        sa.Column("key_scores", sa.JSON().with_variant(JSONB(), "postgresql")),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("posts_user", "posts", ["user_id", "created_at"])
    op.create_index("posts_visibility", "posts", ["visibility", "created_at"])
    op.create_table(
        "post_likes",
        sa.Column("post_id", sa.String(32), sa.ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("post_likes_user", "post_likes", ["user_id"])
    op.create_table(
        "post_comments",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("post_id", sa.String(32), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("post_comments_post", "post_comments", ["post_id", "created_at"])
    op.create_index("post_comments_user", "post_comments", ["user_id"])
    with op.batch_alter_table("user_reports") as batch:
        batch.add_column(sa.Column("post_id", sa.String(32)))
        batch.add_column(sa.Column("comment_id", sa.String(32)))


def downgrade() -> None:
    with op.batch_alter_table("user_reports") as batch:
        batch.drop_column("comment_id")
        batch.drop_column("post_id")
    op.drop_table("post_comments")
    op.drop_table("post_likes")
    op.drop_table("posts")
