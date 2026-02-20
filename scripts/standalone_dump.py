#!/usr/bin/env python3
"""
Standalone SD card dump for backfill recovery.
Stops the service, forces an Arduino reset via 1200bps touch,
opens the port fresh, sends F20260219, and saves to CSV.
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

def arduino_reset(port):
    """Force Arduino hardware reset via 1200bps touch (open+close at 1200 baud)."""
    print(f"[RESET] Opening {port} at 1200 baud to trigger bootloader reset...")
    try:
        s = serial.Serial(port, 1200)
        s.dtr = False  # Drop DTR
        time.sleep(0.5)
        s.close()
        print("[RESET] Port closed. Waiting for Arduino to reboot...")
        time.sleep(5)  # Wait for bootloader to time out and start sketch

        # Wait for port to reappear (it may briefly vanish)
        for i in range(20):
            if os.path.exists(port):
                print(f"[RESET] Port {port} is back.")
                return True
            time.sleep(1)
            print(f"[RESET] Waiting for port... ({i+1}s)")

        print("[RESET] Port did not reappear!")
        return False
    except Exception as e:
        print(f"[RESET] Error: {e}")
        return False

def main():
    port = find_port()
    print(f"=== Standalone SD Dump: F{TARGET_DATE} ===")
    print(f"Port: {port}")
    print(f"Output: {OUTPUT_FILE}")

    # 1. Stop the service
    print("\n[1/5] Stopping temp-logger-serial service...")
    subprocess.run(["sudo", "systemctl", "stop", "temp-logger-serial"], check=False)
    time.sleep(2)

    # 2. Force Arduino reset
    print("\n[2/5] Resetting Arduino...")
    if not arduino_reset(port):
        print("FATAL: Could not reset Arduino. Try physical unplug.")
        sys.exit(1)

    # 3. Open port and wait for Arduino to boot
    print(f"\n[3/5] Connecting at {BAUD_RATE} baud...")
    ser = serial.Serial(port, BAUD_RATE, timeout=2)
    time.sleep(1)

    # Read boot messages for up to 20 seconds
    print("[BOOT] Reading Arduino boot output...")
    boot_end = time.time() + 20
    saw_init_complete = False
    while time.time() < boot_end:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                print(f"  [BOOT] {line[:120]}")
                if "Initialization complete" in line or "Starting main loop" in line:
                    saw_init_complete = True
                    break
        else:
            time.sleep(0.05)

    if not saw_init_complete:
        print("[WARN] Did not see 'Initialization complete'. Continuing anyway...")

    # Drain any remaining boot output
    print("[DRAIN] Draining remaining output for 5s...")
    drain_end = time.time() + 5
    while time.time() < drain_end:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                print(f"  [DRAIN] {line[:120]}")
        else:
            time.sleep(0.05)

    # 4. Send F command
    print(f"\n[4/5] Sending F{TARGET_DATE} command...")
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
        print(f"\n[5/5] Saved {len(lines)} lines to {OUTPUT_FILE}")
        print(f"\nNext: run backfill_sd_data.py to insert into DB:")
        print(f'  DATABASE_URL="$DATABASE_URL" python3 {os.path.join(os.path.dirname(os.path.abspath(__file__)), "backfill_sd_data.py")} "{OUTPUT_FILE}"')
    else:
        print("\n[5/5] No data captured. Nothing to save.")

    # Restart the service
    print("\nRestarting temp-logger-serial service...")
    subprocess.run(["sudo", "systemctl", "start", "temp-logger-serial"], check=False)
    print("Done.")

if __name__ == "__main__":
    main()
