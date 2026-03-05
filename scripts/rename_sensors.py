#!/usr/bin/env python3
"""
rename_sensors.py
-----------------
Retroactively renames TD01-TD05 sensor labels in the Heroku PostgreSQL
temperature_readings table.

Rename map:
  TD04 -> TD01
  TD01 -> TD02
  TD03 -> TD03  (unchanged)
  TD05 -> TD04
  TD02 -> TD05

Because the renames are circular, temporary placeholder names are used
inside a single transaction to avoid collisions.

Usage:
  # Dry run (shows row counts, no changes committed):
  python scripts/rename_sensors.py --dry-run

  # Live run (reads DATABASE_URL from env / .env file):
  python scripts/rename_sensors.py

  # Override database URL:
  python scripts/rename_sensors.py --database-url "postgres://..."
"""

import argparse
import os
import sys

try:
    import psycopg2
except ImportError:
    sys.exit("psycopg2 not found. Install with: pip install psycopg2-binary")

# Load .env if present (optional convenience — not required on Heroku)
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), "..", "backend", ".env")
    load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv not installed — rely on env vars being set externally


# ---------------------------------------------------------------------------
# Rename steps (executed in order inside one transaction).
# We use two temp names to break the circular chain:
#   TD01 -> TD_TMP1   (save old TD01 rows)
#   TD02 -> TD_TMP2   (save old TD02 rows)
#   TD04 -> TD01      (direct — TD01 slot is now free)
#   TD05 -> TD04      (direct — TD04 slot is now free)
#   TD_TMP1 -> TD02   (resolve saved TD01 rows)
#   TD_TMP2 -> TD05   (resolve saved TD02 rows)
# TD03 is skipped (correct already).
# ---------------------------------------------------------------------------
RENAME_STEPS = [
    ("TD01", "TD_TMP1"),
    ("TD02", "TD_TMP2"),
    ("TD04", "TD01"),
    ("TD05", "TD04"),
    ("TD_TMP1", "TD02"),
    ("TD_TMP2", "TD05"),
]

TABLE = "temperature_readings"
COLUMN = "sensor_name"


def count_rows(cur, name: str) -> int:
    cur.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE {COLUMN} = %s",
        (name,),
    )
    return cur.fetchone()[0]


def main():
    parser = argparse.ArgumentParser(description="Rename TD01-TD05 sensor labels in the database.")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without committing")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL connection string")
    args = parser.parse_args()

    if not args.database_url:
        sys.exit(
            "ERROR: No DATABASE_URL provided.\n"
            "Set the DATABASE_URL environment variable or pass --database-url."
        )

    print("Connecting to database…")
    try:
        conn = psycopg2.connect(args.database_url, sslmode="require")
    except Exception:
        conn = psycopg2.connect(args.database_url)

    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            # --- Preview counts ---
            print("\nRow counts BEFORE rename:")
            for old_name in ("TD01", "TD02", "TD03", "TD04", "TD05"):
                n = count_rows(cur, old_name)
                print(f"  {old_name}: {n:,} rows")

            if args.dry_run:
                print("\n[DRY RUN] No changes committed.")
                return

            # --- Execute renames ---
            print("\nApplying renames…")
            for old_name, new_name in RENAME_STEPS:
                cur.execute(
                    f"UPDATE {TABLE} SET {COLUMN} = %s WHERE {COLUMN} = %s",
                    (new_name, old_name),
                )
                print(f"  {old_name} -> {new_name}: {cur.rowcount:,} rows updated")

            # --- Post-rename counts ---
            print("\nRow counts AFTER rename:")
            for new_name in ("TD01", "TD02", "TD03", "TD04", "TD05"):
                n = count_rows(cur, new_name)
                print(f"  {new_name}: {n:,} rows")

            # --- Sanity check: no temp rows should remain ---
            for tmp in ("TD_TMP1", "TD_TMP2"):
                n = count_rows(cur, tmp)
                if n > 0:
                    raise RuntimeError(f"Unexpected rows still labeled {tmp}: {n}")

        conn.commit()
        print("\nDone. Changes committed successfully.")

    except Exception as exc:
        conn.rollback()
        sys.exit(f"\nERROR: {exc}\nTransaction rolled back — no changes were made.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
