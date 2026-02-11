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
    temp_rows, level_rows, env_rows = parse_csv(filepath)
    total = len(temp_rows) + len(level_rows) + len(env_rows)
    print(f"Parsed {total} rows from {filepath}")
    print(f"  Temperature: {len(temp_rows)}")
    print(f"  Level:       {len(level_rows)}")
    print(f"  Environment: {len(env_rows)}")

    if total == 0:
        print("Nothing to backfill.")
        return

    conn = psycopg2.connect(database_url, sslmode="require")
    cur = conn.cursor()

    inserted = {"temp": 0, "level": 0, "env": 0}
    skipped = {"temp": 0, "level": 0, "env": 0}

    # --- Temperature readings ---
    for row in temp_rows:
        ts = row["timestamp"].strip()
        if ts.startswith("UPTIME"):
            skipped["temp"] += 1
            continue

        device_id = row.get("device_id", "arduino_node_01").strip()
        sensor_name = row["sensor_name"].strip()
        bus = row.get("bus", "").strip()
        pin = row.get("pin", "0").strip()
        rom = row.get("rom", "").strip()
        raw_temp = row.get("raw_temp_c", "").strip()
        cal_temp = row.get("cal_temp_c", "").strip()
        status = row.get("status", "").strip()

        raw_val = float(raw_temp) if raw_temp and raw_temp != "null" else None
        cal_val = float(cal_temp) if cal_temp and cal_temp != "null" else None

        # Check if row already exists
        cur.execute(
            """SELECT 1 FROM temperature_readings
               WHERE timestamp = %s AND sensor_name = %s
               LIMIT 1""",
            (ts, sensor_name),
        )
        if cur.fetchone():
            skipped["temp"] += 1
            continue

        cur.execute(
            """INSERT INTO temperature_readings
               (timestamp, site_id, device_id, sensor_name, bus, pin, rom, raw_temp_c, temp_c, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (ts, SITE_ID, device_id, sensor_name, bus, int(pin), rom, raw_val, cal_val, status),
        )
        inserted["temp"] += 1

    # --- Level sensor readings ---
    for row in level_rows:
        ts = row["timestamp"].strip()
        if ts.startswith("UPTIME"):
            skipped["level"] += 1
            continue

        device_id = row.get("device_id", "arduino_node_01").strip()
        sensor_name = row["sensor_name"].strip()
        pin = row.get("pin", "5").strip()
        # Level state is stored in the "status" column of the CSV
        state = row.get("status", "NONE").strip()

        cur.execute(
            """SELECT 1 FROM level_sensor_readings
               WHERE timestamp = %s AND sensor_name = %s
               LIMIT 1""",
            (ts, sensor_name),
        )
        if cur.fetchone():
            skipped["level"] += 1
            continue

        cur.execute(
            """INSERT INTO level_sensor_readings
               (timestamp, site_id, device_id, sensor_name, pin, state)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (ts, SITE_ID, device_id, sensor_name, int(pin), state),
        )
        inserted["level"] += 1

    # --- Environment readings ---
    for row in env_rows:
        ts = row["timestamp"].strip()
        if ts.startswith("UPTIME"):
            skipped["env"] += 1
            continue

        device_id = row.get("device_id", "arduino_node_01").strip()
        sensor_name = row["sensor_name"].strip()
        raw_temp = row.get("raw_temp_c", "").strip()
        humidity = row.get("humidity", "").strip()
        pressure = row.get("pressure_hpa", "").strip()
        gas = row.get("gas_ohms", "").strip()

        temp_val = float(raw_temp) if raw_temp and raw_temp != "null" else None
        hum_val = float(humidity) if humidity and humidity != "null" else None
        pres_val = float(pressure) if pressure and pressure != "null" else None
        gas_val = float(gas) if gas and gas != "null" else None

        cur.execute(
            """SELECT 1 FROM environment_readings
               WHERE timestamp = %s AND sensor_name = %s
               LIMIT 1""",
            (ts, sensor_name),
        )
        if cur.fetchone():
            skipped["env"] += 1
            continue

        cur.execute(
            """INSERT INTO environment_readings
               (timestamp, site_id, device_id, sensor_name, temp_c, humidity, pressure_hpa, gas_resistance_ohms)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (ts, SITE_ID, device_id, sensor_name, temp_val, hum_val, pres_val, gas_val),
        )
        inserted["env"] += 1

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
