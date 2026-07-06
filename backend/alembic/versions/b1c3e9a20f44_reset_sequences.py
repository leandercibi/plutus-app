"""reset_sequences

Revision ID: b1c3e9a20f44
Revises: 0ef8a817f493
Create Date: 2026-06-29 12:00:00.000000

Idempotent sequence repair: rows seeded with explicit IDs left sequences
behind, causing UniqueViolation on the next insert.
"""

from alembic import op

revision = "b1c3e9a20f44"
down_revision = "0ef8a817f493"
branch_labels = None
depends_on = None

_TABLES = [
    "swing_signal",
    "swing_trade",
    "fill",
    "notification",
    "tranche",
    "universe",
    "accumulation_candidate",
    "accumulation_position",
    "latest_price",
    "alert_cooldown",
    "bundle_stat_per_regime",
    "calibration_row",
    "drawdown_governor_state",
    "walk_forward_run",
]


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"SELECT setval('{table}_id_seq', "
            f"GREATEST((SELECT COALESCE(MAX(id), 1) FROM {table}), 1))"
        )


def downgrade() -> None:
    pass
