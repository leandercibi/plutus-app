"""add daily_delivery table

Revision ID: e1b4f7d92c3a
Revises: d3a9b1c48e77
Create Date: 2026-07-14

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e1b4f7d92c3a"
down_revision = "d3a9b1c48e77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_delivery",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("delivery_qty", sa.Integer(), nullable=False),
        sa.Column("traded_qty", sa.Integer(), nullable=False),
        sa.Column("delivery_pct", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "as_of_date", name="uq_daily_delivery_symbol_date"),
    )
    op.create_index(op.f("ix_daily_delivery_symbol"), "daily_delivery", ["symbol"])
    op.create_index(op.f("ix_daily_delivery_as_of_date"), "daily_delivery", ["as_of_date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_daily_delivery_as_of_date"), table_name="daily_delivery")
    op.drop_index(op.f("ix_daily_delivery_symbol"), table_name="daily_delivery")
    op.drop_table("daily_delivery")
