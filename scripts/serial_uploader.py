import serial
import time
import json
import requests
import sys
import os
import glob
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo('America/Chicago')

# Configuration
SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200
HEROKU_URL = "https://temp-logger-1770077582-8b1b2ec536f6.herokuapp.com/api/temps"
API_KEY = "36e6e1669f7302366f067627383705a0"

def find_arduino_port():
    """Auto-detect Arduino serial port (ttyACM0, ttyACM1, etc.)"""
    candidates = sorted(glob.glob('/dev/ttyACM*'))
    if candidates:
        port = candidates[0]
        print(f"[DETECT] Auto-detected Arduino port: {port}")
        return port
    return SERIAL_PORT  # fallback to default

def upload_to_heroku(json_data):
    """Sends JSON data to Heroku backend"""
    try:
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY
        }
        response = requests.post(HEROKU_URL, json=json_data, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            print(f"[OK] Uploaded to Heroku (Status {response.status_code})")
        else:
            print(f"[ERROR] Heroku returned {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"[ERROR] Upload to Heroku failed: {e}")

def main():
    port = find_arduino_port()
    print(f"[SERIAL] Connecting to {port} @ {BAUD_RATE}...")
    
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=2)
        ser.dtr = True # Force DTR to reset/wake Uno R4
        time.sleep(3) # Wait for Arduino to boot and print init messages
        print("[OK] Serial connected. Listening for data...")
    except Exception as e:
        print(f"[ERROR] Could not open serial port {port}: {e}")
        sys.exit(1)

    # Don't clear buffer - we want to see startup messages (BME680 init, etc.)

    # Sync Time — send UTC epoch to Arduino.
    # The Arduino's setTime() adds TIMEZONE_OFFSET (-6h) to convert
    # to Central Time internally. Sending a pre-adjusted CT epoch
    # would cause a double-offset (CT - 6h = UTC-12h).
    try:
        now_utc = datetime.now(timezone.utc)
        now_central = now_utc.astimezone(CENTRAL_TZ)
        utc_epoch = int(time.time())
        tz_name = now_central.strftime('%Z')  # CST or CDT
        utc_offset_hours = int(now_central.utcoffset().total_seconds()) // 3600
        print(f"[CLOCK] Syncing time ({tz_name}, UTC{utc_offset_hours:+d}) epoch={utc_epoch} (UTC; Arduino applies TZ offset)")
        ser.write(f"C{utc_epoch}\n".encode('utf-8'))
        time.sleep(0.5) # Give it a moment to process
    except Exception as e:
        print(f"[WARN] Failed to sync time: {e}")

    # Trigger BME680 re-init (I2C bus recovery + bme.begin)
    # This is a safety net in case the boot-time init failed.
    try:
        print("[BME] Sending BME680 re-init command (B)...")
        ser.write(b"B\n")
        time.sleep(4) # Give it time to do recovery + 5 init attempts
    except Exception as e:
        print(f"[WARN] Failed to send BME re-init: {e}")

    while True:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                
                if not line:
                    continue

                if line.startswith("JSON_UPLOAD:"):
                    raw_json = line.replace("JSON_UPLOAD:", "", 1)
                    print(f"[JSON] Received payload ({len(raw_json)} bytes)")
                    
                    try:
                        data = json.loads(raw_json)
                        # Debug log for BME
                        if 'environment_sensor' in data:
                            env = data['environment_sensor']
                            print(f"  [ATM] {env.get('sensor_name')} ({env.get('type')}): "
                                  f"{env.get('temp_c')}C, {env.get('humidity')}%, "
                                  f"{env.get('pressure_hpa')}hPa, {env.get('gas_resistance_ohms')}ohms")
                        
                        upload_to_heroku(data)
                    except json.JSONDecodeError as e:
                        print(f"[ERROR] Invalid JSON received: {e}")
                else:
                    # Just a regular debug log from Arduino
                    print(f"[Arduino] {line}")
            else:
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"[WARN] Serial Loop Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
