#!/usr/bin/env python3
"""
fix_timestamp_drift.py
======================
Identifies and corrects timestamps in the Heroku PostgreSQL database that were
stored with the wrong UTC offset due to clock drift or a DST mismatch on the
Arduino (TIMEZONE_OFFSET hard-coded as CST/-6h when CDT/-5h was in effect).

Usage:
    # Dry run — shows how many rows are affected, no changes made
    python fix_timestamp_drift.py --dry-run --shift-hours -7

    # Apply the fix for a specific time window
    python fix_timestamp_drift.py --apply --shift-hours -7 \\
        --start "2026-02-26 18:00:00" --end "2026-02-27 08:00:00"

    # Use a specific DATABASE_URL instead of the environment variable
    python fix_timestamp_drift.py --dry-run --db-url "postgres://..." --shift-hours -7

Arguments:
    --shift-hours   Number of hours to ADD to affected timestamps.
                    Use a positive value to shift forward (e.g. +1 to correct
                    a 1-hour-behind CST error during CDT), negative to shift back.
    --start         Start of window to examine (CT naive ISO, e.g. "2026-02-26 20:00:00")
    --end           End of window to examine (CT naive ISO)
    --dry-run       Print counts only, make no changes (default)
    --apply         Actually UPDATE the database rows
    --db-url        PostgreSQL connection string (overrides DATABASE_URL env var)
    --tables        Comma-separated list of tables to fix.
                    Default: temperature_readings,level_sensor_readings,environment_readings
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 is required. Install with: pip install psycopg2-binary")
    sys.exit(1)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        print("ERROR: zoneinfo (or backports.zoneinfo) is required.")
        sys.exit(1)

CENTRAL_TZ = ZoneInfo("America/Chicago")
UTC_TZ = ZoneInfo("UTC")

ALL_TABLES = ["temperature_readings", "level_sensor_readings", "environment_readings"]


def parse_ct_naive(value: str) -> datetime:
    """Parse a naive ISO datetime string as Central Time and return UTC-aware datetime."""
    dt = datetime.fromisoformat(value.strip())
    if dt.tzinfo is not None:
        return dt.astimezone(UTC_TZ)
    return dt.replace(tzinfo=CENTRAL_TZ).astimezone(UTC_TZ)


def connect(db_url: str):
    try:
        return psycopg2.connect(db_url, sslmode="require")
    except Exception:
        return psycopg2.connect(db_url)


def count_rows(conn, table: str, start_utc: datetime, end_utc: datetime) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM {table} WHERE timestamp BETWEEN %s AND %s",
            (start_utc, end_utc),
        )
        return cur.fetchone()[0]


def sample_rows(conn, table: str, start_utc: datetime, end_utc: datetime, limit: int = 5):
    """Return a few sample rows so the user can sanity-check before applying."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""SELECT id, timestamp AT TIME ZONE 'America/Chicago' AS ts_ct
                FROM {table}
                WHERE timestamp BETWEEN %s AND %s
                ORDER BY timestamp ASC
                LIMIT %s""",
            (start_utc, end_utc, limit),
        )
        return cur.fetchall()


def apply_shift(conn, table: str, start_utc: datetime, end_utc: datetime, shift: timedelta) -> int:
    """UPDATE timestamps in the given window by the shift amount. Returns rows updated."""
    with conn.cursor() as cur:
        cur.execute(
            f"""UPDATE {table}
                SET timestamp = timestamp + %s::interval
                WHERE timestamp BETWEEN %s AND %s""",
            (str(shift), start_utc, end_utc),
        )
        return cur.rowcount


def main():
    parser = argparse.ArgumentParser(description="Fix drifted timestamps in the sensor DB.")
    parser.add_argument("--shift-hours", type=float, required=True,
                        help="Hours to ADD to affected timestamps (e.g. 7 to shift forward 7 h, -1 to shift back 1 h)")
    parser.add_argument("--start", type=str, default=None,
                        help="Start of window (CT naive ISO). Default: 7 days ago.")
    parser.add_argument("--end", type=str, default=None,
                        help="End of window (CT naive ISO). Default: now.")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Print counts only, make no changes (default mode)")
    parser.add_argument("--apply", action="store_true", default=False,
                        help="Actually apply the UPDATE statements")
    parser.add_argument("--db-url", type=str, default=None,
                        help="PostgreSQL connection string. Defaults to DATABASE_URL env var.")
    parser.add_argument("--tables", type=str,
                        default=",".join(ALL_TABLES),
                        help=f"Comma-separated table list. Default: {','.join(ALL_TABLES)}")
    args = parser.parse_args()

    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: Set DATABASE_URL or pass --db-url")
        sys.exit(1)

    now_utc = datetime.now(UTC_TZ)
    if args.end:
        end_utc = parse_ct_naive(args.end)
    else:
        end_utc = now_utc

    if args.start:
        start_utc = parse_ct_naive(args.start)
    else:
        start_utc = end_utc - timedelta(days=7)

    tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    shift = timedelta(hours=args.shift_hours)
    do_apply = args.apply and not args.dry_run

    # Show what we will do
    mode_label = "APPLY" if do_apply else "DRY RUN"
    shift_label = f"{args.shift_hours:+.1f} hours"

    print(f"\n{'='*60}")
    print(f"  Timestamp Drift Correction Tool  [{mode_label}]")
    print(f"{'='*60}")
    print(f"  Window (UTC): {start_utc.isoformat()} -> {end_utc.isoformat()}")
    print(f"  Window (CT):  {start_utc.astimezone(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')} "
          f"-> {end_utc.astimezone(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  Shift:        {shift_label}")
    print(f"  Tables:       {', '.join(tables)}")
    print(f"{'='*60}\n")

    conn = connect(db_url)
    conn.autocommit = False

    total_rows = 0
    try:
        for table in tables:
            count = count_rows(conn, table, start_utc, end_utc)
            total_rows += count
            print(f"  {table}: {count} rows in window")

            if count > 0:
                samples = sample_rows(conn, table, start_utc, end_utc)
                print(f"    Sample timestamps (CT, before shift):")
                for row in samples:
                    print(f"      id={row['id']}  ts_ct={row['ts_ct']}")

        print(f"\n  Total rows affected: {total_rows}")

        if not do_apply:
            print("\n  [DRY RUN] No changes made. Re-run with --apply to commit changes.")
            print("  Example:")
            print(f"    python fix_timestamp_drift.py --apply --shift-hours {args.shift_hours} "
                  f"--start \"{start_utc.astimezone(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S')}\" "
                  f"--end \"{end_utc.astimezone(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S')}\"")
        else:
            print(f"\n  Applying shift of {shift_label} to {total_rows} rows...")
            updated_total = 0
            for table in tables:
                updated = apply_shift(conn, table, start_utc, end_utc, shift)
                updated_total += updated
                print(f"  {table}: updated {updated} rows")
            conn.commit()
            print(f"\n  ✓ Committed. Total rows updated: {updated_total}")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
