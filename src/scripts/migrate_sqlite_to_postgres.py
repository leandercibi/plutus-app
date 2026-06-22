#!/usr/bin/env python3
"""
Migrate all data from a local SQLite DB to a remote PostgreSQL DB.

Usage (with SSH tunnel already open on port 5433):
    python scripts/migrate_sqlite_to_postgres.py \
        --src  sqlite:///./plutus.db \
        --dst  "postgresql+psycopg://plutus:plutus@127.0.0.1:5433/plutus_db"

Open the SSH tunnel first:
    ssh -L 5433:127.0.0.1:5432 ubuntu@<OCI_IP> -N &
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import Boolean, create_engine, inspect, text
from sqlalchemy.sql.sqltypes import JSON


def _bool_cols(table) -> set[str]:
    """Return column names that are Boolean in the ORM table definition."""
    return {c.name for c in table.columns if isinstance(c.type, Boolean)}


def _coerce_row(row: dict, bool_cols: set[str]) -> dict:
    """Cast SQLite 0/1 integers to Python bool for PostgreSQL boolean columns."""
    out = dict(row)
    for col in bool_cols:
        if col in out and out[col] is not None:
            out[col] = bool(out[col])
    return out


def migrate(src_url: str, dst_url: str, dry_run: bool = False) -> None:
    src_engine = create_engine(src_url)
    dst_engine = create_engine(dst_url)

    # Import after engines are created so models are registered
    from plutus.db.models import Base

    print("→ Initialising schema on destination…")
    if not dry_run:
        Base.metadata.create_all(dst_engine)

    tables = [t for t in Base.metadata.sorted_tables]
    print(f"→ Tables to migrate ({len(tables)}): {', '.join(t.name for t in tables)}\n")

    with src_engine.connect() as src_conn, dst_engine.connect() as dst_conn:
        inspector = inspect(src_engine)

        if not dry_run:
            # Truncate all tables in reverse dependency order so cascades don't interfere
            dst_conn.execute(text("SET session_replication_role = replica"))
            all_names = ", ".join(t.name for t in reversed(tables))
            dst_conn.execute(text(f"TRUNCATE TABLE {all_names}"))
            dst_conn.commit()
            dst_conn.execute(text("SET session_replication_role = DEFAULT"))

        for table in tables:
            table_name = table.name
            if table_name not in inspector.get_table_names():
                print(f"  skip {table_name} (not in source)")
                continue

            rows = src_conn.execute(text(f"SELECT * FROM {table_name}")).mappings().fetchall()
            if not rows:
                print(f"  {table_name}: 0 rows — skip")
                continue

            print(f"  {table_name}: {len(rows)} rows…", end=" ", flush=True)
            if dry_run:
                print("(dry-run)")
                continue

            bool_cols = _bool_cols(table)
            cols = list(rows[0].keys())
            # Quote column names to preserve mixed-case (PostgreSQL folds unquoted to lowercase)
            col_list = ", ".join(f'"{c}"' for c in cols)
            placeholders = ", ".join(f":{c}" for c in cols)
            stmt = text(f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})")
            # Disable FK checks per-table insert to avoid ordering issues
            dst_conn.execute(text("SET session_replication_role = replica"))
            dst_conn.execute(stmt, [_coerce_row(dict(r), bool_cols) for r in rows])
            dst_conn.execute(text("SET session_replication_role = DEFAULT"))
            dst_conn.commit()
            print("done")

        # Reset all sequences (PostgreSQL auto-increment)
        if not dry_run:
            print("\n→ Resetting PostgreSQL sequences…")
            seq_sql = text("""
                SELECT table_name, column_name,
                       pg_get_serial_sequence(table_name, column_name) AS seq
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND column_default LIKE 'nextval%%'
            """)
            for table_name, col_name, seq_name in dst_conn.execute(seq_sql).fetchall():
                if seq_name:
                    dst_conn.execute(text(
                        f"SELECT setval('{seq_name}', "
                        f"COALESCE((SELECT MAX({col_name}) FROM {table_name}), 1))"
                    ))
            dst_conn.commit()
            print("  sequences reset")

    print("\n✓ Migration complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL")
    parser.add_argument("--src", required=True, help="Source SQLAlchemy URL (sqlite:///...)")
    parser.add_argument("--dst", required=True, help="Destination SQLAlchemy URL (postgresql+psycopg://...)")
    parser.add_argument("--dry-run", action="store_true", help="Print row counts without writing")
    args = parser.parse_args()

    if not args.src.startswith("sqlite"):
        print("ERROR: --src must be a sqlite:// URL", file=sys.stderr)
        sys.exit(1)
    if not args.dst.startswith("postgresql"):
        print("ERROR: --dst must be a postgresql:// URL", file=sys.stderr)
        sys.exit(1)

    migrate(args.src, args.dst, dry_run=args.dry_run)
