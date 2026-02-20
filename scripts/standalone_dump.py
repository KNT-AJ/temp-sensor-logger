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
# Usage: python3 standalone_dump.py [YYYYMMDD]
TARGET_DATE = sys.argv[1] if len(sys.argv) > 1 else "20260219"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"gap_{TARGET_DATE}.csv")
HEADER = "timestamp,device_id,sensor_name,bus,pin,rom,raw_temp_c,cal_temp_c,status,humidity,pressure_hpa,gas_ohms"

def find_port():
    candidates = sorted(glob.glob('/dev/ttyACM*'))
    return candidates[0] if candidates else '/dev/ttyACM0'

def find_usb_device_path():
    """Find the Arduino's sysfs USB device path by vendor:product ID."""
    # Arduino Uno R4 WiFi: 2341:1002
    import pathlib
    for dev in pathlib.Path('/sys/bus/usb/devices').iterdir():
        vid_file = dev / 'idVendor'
        pid_file = dev / 'idProduct'
        if vid_file.exists() and pid_file.exists():
            try:
                vid = vid_file.read_text().strip()
                pid = pid_file.read_text().strip()
                if vid == '2341' and pid in ('1002', '1102'):
                    return str(dev)
            except Exception:
                pass
    return None

def usb_power_cycle():
    """Power-cycle the Arduino by toggling USB authorized state.

    On Raspberry Pi 4, deauthorizing a USB device via sysfs cuts VBUS power
    to that port, causing a real hardware reset of the attached MCU.
    """
    dev_path = find_usb_device_path()
    if not dev_path:
        print("[USB] Could not find Arduino USB device (2341:1002).")
        print("[USB] Trying uhubctl as fallback...")
        # Try uhubctl - may or may not be installed
        result = subprocess.run(
            ["uhubctl", "-l", "1-1", "-p", "2", "-a", "cycle", "-d", "3"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("[USB] uhubctl power cycle succeeded.")
            return True
        else:
            print(f"[USB] uhubctl failed: {result.stderr.strip()}")
            return False

    auth_file = os.path.join(dev_path, 'authorized')
    dev_name = os.path.basename(dev_path)
    print(f"[USB] Found Arduino at {dev_name}")
    print(f"[USB] Deauthorizing USB device (cuts power)...")

    try:
        # Deauthorize - this disconnects the device and may cut VBUS
        subprocess.run(["sudo", "tee", auth_file],
                       input="0\n", text=True, capture_output=True, check=True)
        time.sleep(3)

        print(f"[USB] Re-authorizing USB device...")
        subprocess.run(["sudo", "tee", auth_file],
                       input="1\n", text=True, capture_output=True, check=True)
        time.sleep(2)
        print("[USB] USB power cycle complete.")
        return True
    except Exception as e:
        print(f"[USB] Error during power cycle: {e}")
        return False

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

    # Drain aggressively for up to 15 seconds.
    print("[DRAIN] Reading serial for up to 15s to unstick Arduino...")
    got_data = False
    drain_end = time.time() + 15
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
                time.sleep(1)
                if ser.in_waiting == 0:
                    print("[DRAIN] Output settled.")
                    break
            time.sleep(0.05)

    if not got_data:
        print("[DRAIN] No data received - Arduino is unresponsive.")
        ser.close()
        return None

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
    else:
        print("[PROBE] No status response but got drain data -- proceeding anyway.")

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

    # 2. Try to connect and unstick Arduino
    print("\n[2/4] Connecting to Arduino...")
    ser = unstick_and_connect(port)

    if ser is None:
        # Arduino is hard-stuck. Try USB power cycle to force hardware reset.
        print("\n[2/4] Arduino unresponsive. Attempting USB power cycle...")
        if usb_power_cycle():
            # Wait for port to reappear after power cycle
            print("[USB] Waiting for Arduino to reboot...")
            time.sleep(5)
            for i in range(30):
                candidates = sorted(glob.glob('/dev/ttyACM*'))
                if candidates:
                    port = candidates[0]
                    print(f"[USB] Port {port} is back!")
                    break
                time.sleep(1)
                if i % 5 == 4:
                    print(f"[USB] Waiting for port... ({i+1}s)")
            else:
                print("FATAL: Port did not reappear after USB power cycle.")
                subprocess.run(["sudo", "systemctl", "start", "temp-logger-serial"], check=False)
                sys.exit(1)

            # Wait for Arduino to finish booting (sensor discovery, etc.)
            time.sleep(5)

            # Try connecting again - this time it should be a fresh boot
            print("[USB] Connecting after power cycle...")
            ser = unstick_and_connect(port)

        if ser is None:
            print("FATAL: Could not communicate with Arduino.")
            print("You need to physically unplug and replug the USB cable.")
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
