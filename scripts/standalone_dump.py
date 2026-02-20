#!/usr/bin/env python3
"""
Standalone SD card dump for backfill recovery.
Stops the service, opens the serial port, drains any backed-up
output to unstick the Arduino, sends F20260219, and saves to CSV.
"""
import serial
import serial.tools.list_ports
import time
import os
import sys
import subprocess
import glob

BAUD_RATE = 115200
TARGET_DATE = "20260219"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"gap_{TARGET_DATE}.csv")
HEADER = "timestamp,device_id,sensor_name,bus,pin,rom,raw_temp_c,cal_temp_c,status,humidity,pressure_hpa,gas_ohms"

def find_port():
    candidates = sorted(glob.glob('/dev/ttyACM*'))
    return candidates[0] if candidates else '/dev/ttyACM0'

def unstick_and_connect(port):
    """Open serial port and drain backed-up data to unstick the Arduino.

    When the service stops and nobody reads the serial port, the Arduino's
    uploadBatch() blocks in Serial.flush() waiting for the USB host to drain
    the CDC TX buffer.  Opening the port and reading aggressively unblocks it.
    """
    print(f"[CONNECT] Opening {port} at {BAUD_RATE} baud...")
    ser = None
    for attempt in range(5):
        try:
            ser = serial.Serial(port, BAUD_RATE, timeout=2)
            break
        except (OSError, serial.SerialException) as e:
            print(f"  [RETRY] Open failed ({e}), retrying in 3s... ({attempt+1}/5)")
            time.sleep(3)
    if ser is None:
        return None

    # Toggle DTR to signal a fresh host connection
    ser.dtr = False
    time.sleep(0.1)
    ser.dtr = True
    time.sleep(0.5)

    # Drain aggressively for up to 30 seconds.
    # As soon as the host reads, the Arduino's blocked Serial.flush() completes
    # and its main loop resumes.  We look for ANY output as proof of life.
    print("[DRAIN] Reading serial for up to 30s to unstick Arduino...")
    got_data = False
    drain_end = time.time() + 30
    while time.time() < drain_end:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                if not got_data:
                    print("[DRAIN] Arduino is alive! Draining backed-up output...")
                    got_data = True
                print(f"  [DRAIN] {line[:120]}")
        else:
            if got_data:
                # Got data earlier but nothing now - Arduino has caught up
                time.sleep(1)
                if ser.in_waiting == 0:
                    print("[DRAIN] Output settled.")
                    break
            time.sleep(0.05)

    if not got_data:
        print("[DRAIN] No data received in 30s - Arduino may be unresponsive.")

    # Probe: send S (status) command to verify bidirectional communication
    print("[PROBE] Sending status command to verify communication...")
    ser.write(b"S\n")
    ser.flush()
    probe_end = time.time() + 10
    probe_ok = False
    while time.time() < probe_end:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                print(f"  [PROBE] {line[:120]}")
                if "System Status" in line or "Status" in line or "Board:" in line:
                    probe_ok = True
        else:
            if probe_ok:
                break
            time.sleep(0.05)

    if probe_ok:
        print("[PROBE] Communication confirmed!")
    elif got_data:
        print("[PROBE] No status response but got earlier data -- proceeding anyway.")
    else:
        print("[PROBE] WARNING: No communication with Arduino at all.")
        print("[PROBE] You may need to physically unplug/replug the USB cable.")

    # Drain any remaining probe output
    flush_end = time.time() + 3
    while time.time() < flush_end:
        if ser.in_waiting > 0:
            ser.readline()
        else:
            time.sleep(0.05)

    return ser

def main():
    port = find_port()
    print(f"=== Standalone SD Dump: F{TARGET_DATE} ===")
    print(f"Port: {port}")
    print(f"Output: {OUTPUT_FILE}")

    # 1. Stop the service
    print("\n[1/4] Stopping temp-logger-serial service...")
    subprocess.run(["sudo", "systemctl", "stop", "temp-logger-serial"], check=False)
    time.sleep(2)

    # 2. Connect and unstick Arduino
    print("\n[2/4] Connecting to Arduino...")
    ser = unstick_and_connect(port)
    if ser is None:
        print("FATAL: Could not open serial port after 5 attempts.")
        subprocess.run(["sudo", "systemctl", "start", "temp-logger-serial"], check=False)
        sys.exit(1)

    # 3. Send F command
    print(f"\n[3/4] Sending F{TARGET_DATE} command...")
    cmd = f"F{TARGET_DATE}\n".encode('utf-8')
    ser.write(cmd)
    ser.flush()

    # Read response
    lines = []
    dump_started = False
    timeout = time.time() + 1200  # 20 min max
    last_log = time.time()

    while time.time() < timeout:
        if ser.in_waiting > 0:
            raw = ser.readline().decode('utf-8', errors='ignore').strip()
            if not raw:
                continue

            if "FILE DUMP START" in raw:
                dump_started = True
                print(f"  [DUMP] Stream started!")
                continue
            if "FILE DUMP END" in raw:
                print(f"  [DUMP] Stream ended. {len(lines)} lines captured.")
                break
            if "ERROR: Cannot open" in raw:
                print(f"  [ERROR] {raw}")
                print(f"  The file /logs/{TARGET_DATE}.csv may not exist on the SD card.")
                break

            if dump_started and raw.startswith("2026-"):
                lines.append(raw)
                if len(lines) % 1000 == 0:
                    print(f"  [DUMP] {len(lines)} lines...")
            else:
                print(f"  [RCV] {raw[:120]}")
        else:
            if time.time() - last_log > 30:
                elapsed = int(time.time() - (timeout - 1200))
                print(f"  [WAIT] {len(lines)} lines, {elapsed}s elapsed, dump_started={dump_started}")
                last_log = time.time()
            time.sleep(0.05)

    ser.close()
    print(f"\nSerial closed. Total lines: {len(lines)}")

    # 5. Save to CSV
    if lines:
        with open(OUTPUT_FILE, 'w') as f:
            f.write(HEADER + "\n")
            f.write("\n".join(lines) + "\n")
        print(f"\n[4/4] Saved {len(lines)} lines to {OUTPUT_FILE}")
        print(f"\nNext: run backfill_sd_data.py to insert into DB:")
        print(f'  DATABASE_URL="$DATABASE_URL" python3 {os.path.join(os.path.dirname(os.path.abspath(__file__)), "backfill_sd_data.py")} "{OUTPUT_FILE}"')
    else:
        print("\n[4/4] No data captured. Nothing to save.")

    # Restart the service
    print("\nRestarting temp-logger-serial service...")
    subprocess.run(["sudo", "systemctl", "start", "temp-logger-serial"], check=False)
    print("Done.")

if __name__ == "__main__":
    main()
