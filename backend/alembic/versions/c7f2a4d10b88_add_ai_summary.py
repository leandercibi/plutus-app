"""add ai_summary cache table

Revision ID: c7f2a4d10b88
Revises: b1c3e9a20f44
Create Date: 2026-07-05

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c7f2a4d10b88"
down_revision = "b1c3e9a20f44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_summary",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "cache_key", name="uq_ai_summary_kind_key"),
        sa.CheckConstraint(
            "kind IN ('weekly_pipeline','daily_holdings')", name="ck_ai_summary_kind"
        ),
    )
    op.create_index("ix_ai_summary_kind", "ai_summary", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_ai_summary_kind", table_name="ai_summary")
    op.drop_table("ai_summary")
