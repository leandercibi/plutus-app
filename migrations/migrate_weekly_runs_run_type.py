"""Migration: drop unique constraint on weekly_runs.run_date, add run_type column."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import text
from plutus.db.session import engine

with engine.connect() as conn:
    # Add run_type column if it doesn't exist
    conn.execute(text("""
        ALTER TABLE weekly_runs
        ADD COLUMN IF NOT EXISTS run_type VARCHAR(20) NOT NULL DEFAULT 'scheduled'
    """))

    # Drop the unique constraint on run_date
    # PostgreSQL: constraint is named weekly_runs_run_date_key by default
    conn.execute(text("""
        ALTER TABLE weekly_runs
        DROP CONSTRAINT IF EXISTS weekly_runs_run_date_key
    """))

    conn.commit()

print("Migration complete: run_type column added, unique constraint on run_date dropped.")
