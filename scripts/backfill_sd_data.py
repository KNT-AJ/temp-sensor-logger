#!/usr/bin/env python3
"""
SD Card Data Backfill Script
=============================
Reads a CSV file previously dumped from the Arduino SD card (via retrieve_sd_data.py)
and inserts missing rows into the Heroku PostgreSQL database.

Usage:
  DATABASE_URL="postgres://..." python3 backfill_sd_data.py <csv_file>

Or with a .env file:
  pip3 install python-dotenv
  python3 backfill_sd_data.py <csv_file>

Rows that already exist (matched by timestamp + sensor_name) are skipped.
"""

import csv
import os
import sys
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

def get_central_offset(ts_str):
    """
    Returns the string offset (like '-06:00' or '-05:00') for America/Chicago
    at the given naive local time string (YYYY-MM-DDTHH:MM:SS)
    """
    dt_naive = datetime.fromisoformat(ts_str)
    dt_aware = dt_naive.replace(tzinfo=ZoneInfo("America/Chicago"))
    return dt_aware.strftime('%z')[:3] + ':' + dt_aware.strftime('%z')[3:]

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 is required. Install with:")
    print("  pip3 install psycopg2-binary")
    sys.exit(1)

# SD card CSV header (from Arduino logToSD):
# timestamp,device_id,sensor_name,bus,pin,rom,raw_temp_c,cal_temp_c,status,humidity,pressure_hpa,gas_ohms
SITE_ID = "industrial_site_01"


def parse_csv(filepath):
    """Parse the SD card CSV into categorised rows."""
    temp_rows = []
    level_rows = []
    env_rows = []

    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sensor = row.get("sensor_name", "").strip()
            if not sensor:
                continue

            if sensor.startswith("TD"):
                temp_rows.append(row)
            elif sensor.startswith("LL"):
                level_rows.append(row)
            elif sensor.startswith("ATM"):
                env_rows.append(row)

    return temp_rows, level_rows, env_rows


def backfill(filepath, database_url):
    """Insert missing rows from the CSV into the database."""
    import psycopg2.extras
    temp_rows, level_rows, env_rows = parse_csv(filepath)
    total = len(temp_rows) + len(level_rows) + len(env_rows)
    print(f"Parsed {total} rows from {filepath}")
    print(f"  Temperature: {len(temp_rows)}")
    print(f"  Level:       {len(level_rows)}")
    print(f"  Environment: {len(env_rows)}")

    if total == 0:
        print("Nothing to backfill.")
        return

    # Find min and max timestamps to narrow down our query
    all_ts = []
    for r in temp_rows + level_rows + env_rows:
        ts = r["timestamp"].strip()
        if not ts.startswith("UPTIME"):
            all_ts.append(ts)
    
    if not all_ts:
        print("No valid timestamps found.")
        return

    min_ts = min(all_ts)
    max_ts = max(all_ts)

    conn = psycopg2.connect(database_url, sslmode="require")
    cur = conn.cursor()

    def get_existing(table_name):
        cur.execute(f"""
            SELECT to_char(timestamp at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), sensor_name 
            FROM {table_name} 
            WHERE timestamp >= %s AND timestamp <= %s
        """, (min_ts, max_ts))
        return set((row[0], row[1]) for row in cur.fetchall())

    print(f"Fetching existing records between {min_ts} and {max_ts}...")
    existing_temp = get_existing("temperature_readings")
    existing_level = get_existing("level_sensor_readings")
    existing_env = get_existing("environment_readings")

    inserted = {"temp": 0, "level": 0, "env": 0}
    skipped = {"temp": 0, "level": 0, "env": 0}

    # --- Temperature readings ---
    temp_to_insert = []
    for row in temp_rows:
        ts = row["timestamp"].strip()
        if ts.startswith("UPTIME"):
            skipped["temp"] += 1
            continue

        sensor_name = row["sensor_name"].strip()
        
        if (ts, sensor_name) in existing_temp:
            skipped["temp"] += 1
            continue

        device_id = row.get("device_id", "arduino_node_01").strip()
        bus = row.get("bus", "").strip()
        pin = row.get("pin", "0").strip()
        rom = row.get("rom", "").strip()
        raw_temp = row.get("raw_temp_c", "").strip()
        cal_temp = row.get("cal_temp_c", "").strip()
        status = row.get("status", "").strip()

        raw_val = float(raw_temp) if raw_temp and raw_temp != "null" else None
        cal_val = float(cal_temp) if cal_temp and cal_temp != "null" else None

        db_ts = ts + get_central_offset(ts)
        temp_to_insert.append((db_ts, SITE_ID, device_id, sensor_name, bus, int(pin), rom, raw_val, cal_val, status))

    if temp_to_insert:
        print(f"Inserting {len(temp_to_insert)} temperature readings...")
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO temperature_readings
               (timestamp, site_id, device_id, sensor_name, bus, pin, rom, raw_temp_c, temp_c, status)
               VALUES %s""",
            temp_to_insert,
            page_size=1000
        )
        inserted["temp"] += len(temp_to_insert)
        conn.commit()

    # --- Level sensor readings ---
    level_to_insert = []
    for row in level_rows:
        ts = row["timestamp"].strip()
        if ts.startswith("UPTIME"):
            skipped["level"] += 1
            continue

        sensor_name = row["sensor_name"].strip()
        
        if (ts, sensor_name) in existing_level:
            skipped["level"] += 1
            continue

        device_id = row.get("device_id", "arduino_node_01").strip()
        pin = row.get("pin", "5").strip()
        state = row.get("status", "NONE").strip()

        db_ts = ts + get_central_offset(ts)
        level_to_insert.append((db_ts, SITE_ID, device_id, sensor_name, int(pin), state))

    if level_to_insert:
        print(f"Inserting {len(level_to_insert)} level readings...")
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO level_sensor_readings
               (timestamp, site_id, device_id, sensor_name, pin, state)
               VALUES %s""",
            level_to_insert,
            page_size=1000
        )
        inserted["level"] += len(level_to_insert)
        conn.commit()

    # --- Environment readings ---
    env_to_insert = []
    for row in env_rows:
        ts = row["timestamp"].strip()
        if ts.startswith("UPTIME"):
            skipped["env"] += 1
            continue

        sensor_name = row["sensor_name"].strip()
        
        if (ts, sensor_name) in existing_env:
            skipped["env"] += 1
            continue

        device_id = row.get("device_id", "arduino_node_01").strip()
        raw_temp = row.get("raw_temp_c", "").strip()
        humidity = row.get("humidity", "").strip()
        pressure = row.get("pressure_hpa", "").strip()
        gas = row.get("gas_ohms", "").strip()

        temp_val = float(raw_temp) if raw_temp and raw_temp != "null" else None
        hum_val = float(humidity) if humidity and humidity != "null" else None
        pres_val = float(pressure) if pressure and pressure != "null" else None
        gas_val = float(gas) if gas and gas != "null" else None

        db_ts = ts + get_central_offset(ts)
        env_to_insert.append((db_ts, SITE_ID, device_id, sensor_name, temp_val, hum_val, pres_val, gas_val))

    if env_to_insert:
        print(f"Inserting {len(env_to_insert)} environment readings...")
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO environment_readings
               (timestamp, site_id, device_id, sensor_name, temp_c, humidity, pressure_hpa, gas_resistance_ohms)
               VALUES %s""",
            env_to_insert,
            page_size=1000
        )
        inserted["env"] += len(env_to_insert)
        conn.commit()

    cur.close()
    conn.close()

    total_inserted = sum(inserted.values())
    total_skipped = sum(skipped.values())

    print(f"\n{'=' * 50}")
    print(f"Backfill complete!")
    print(f"  Inserted: {total_inserted}  (temp={inserted['temp']}, level={inserted['level']}, env={inserted['env']})")
    print(f"  Skipped:  {total_skipped}  (temp={skipped['temp']}, level={skipped['level']}, env={skipped['env']})")
    print(f"{'=' * 50}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 backfill_sd_data.py <csv_file>")
        print("\nSet DATABASE_URL environment variable or use a .env file.")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.isfile(filepath):
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        print("Set it to your Heroku PostgreSQL connection string.")
        sys.exit(1)

    backfill(filepath, database_url)


if __name__ == "__main__":
    main()
