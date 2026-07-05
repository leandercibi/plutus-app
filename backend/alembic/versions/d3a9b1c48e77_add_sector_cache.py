"""add sector_cache table

Revision ID: d3a9b1c48e77
Revises: c7f2a4d10b88
Create Date: 2026-07-05

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d3a9b1c48e77"
down_revision = "c7f2a4d10b88"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sector_cache",
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("symbol"),
    )


def downgrade() -> None:
    op.drop_table("sector_cache")
