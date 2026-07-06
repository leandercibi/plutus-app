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

from sqlalchemy import create_engine, inspect, text


def migrate(src_url: str, dst_url: str, dry_run: bool = False) -> None:
    src_engine = create_engine(src_url)
    dst_engine = create_engine(dst_url)

    # Import after engines are created so models are registered
    from plutus.db.init_db import create_all
    from plutus.db.models import Base

    print("→ Initialising schema on destination (create_all)…")
    if not dry_run:
        create_all(dst_engine)

    tables = [t.name for t in Base.metadata.sorted_tables]
    print(f"→ Tables to migrate ({len(tables)}): {', '.join(tables)}\n")

    with src_engine.connect() as src_conn, dst_engine.connect() as dst_conn:
        inspector = inspect(src_engine)
        for table_name in tables:
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

            # Truncate destination table first to avoid PK conflicts on re-run
            dst_conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))

            cols = rows[0].keys()
            placeholders = ", ".join(f":{c}" for c in cols)
            col_list = ", ".join(cols)
            stmt = text(f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})")
            dst_conn.execute(stmt, [dict(r) for r in rows])
            dst_conn.commit()
            print("done")

        # Reset all sequences (PostgreSQL auto-increment)
        if not dry_run:
            print("\n→ Resetting PostgreSQL sequences…")
            seq_sql = """
                SELECT 'SELECT setval(' || quote_literal(sequence_name) ||
                       ', (SELECT MAX(' || quote_ident(column_name) ||
                       ') FROM ' || quote_ident(table_name) || ') + 1)'
                FROM information_schema.columns
                WHERE column_default LIKE 'nextval%'
                  AND table_schema = 'public';
            """
            reset_stmts = dst_conn.execute(text(seq_sql)).fetchall()
            for (stmt_text,) in reset_stmts:
                if stmt_text:
                    dst_conn.execute(text(stmt_text))
            dst_conn.commit()
            print("  sequences reset")

    print("\n✓ Migration complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL")
    parser.add_argument("--src", required=True, help="Source SQLAlchemy URL (sqlite:///...)")
    parser.add_argument(
        "--dst", required=True, help="Destination SQLAlchemy URL (postgresql+psycopg://...)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print row counts without writing")
    args = parser.parse_args()

    if not args.src.startswith("sqlite"):
        print("ERROR: --src must be a sqlite:// URL", file=sys.stderr)
        sys.exit(1)
    if not args.dst.startswith("postgresql"):
        print("ERROR: --dst must be a postgresql:// URL", file=sys.stderr)
        sys.exit(1)

    migrate(args.src, args.dst, dry_run=args.dry_run)
