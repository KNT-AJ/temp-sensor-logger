import serial
import time
import json
import requests
import sys
import os
import glob
import re
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
SITE_ID = "industrial_site_01"

# Global state
last_processed_timestamp = "1970-01-01T00:00:00"

def find_arduino_port():
    """Auto-detect Arduino serial port (ttyACM0, ttyACM1, etc.)"""
    candidates = sorted(glob.glob('/dev/ttyACM*'))
    if candidates:
        port = candidates[0]
        print(f"[DETECT] Auto-detected Arduino port: {port}")
        return port
    return SERIAL_PORT  # fallback to default

def fetch_latest_timestamp():
    """Fetches the timestamp of the last recorded reading from Heroku."""
    try:
        headers = {"X-API-Key": API_KEY}
        # Assuming an endpoint /api/temps?limit=1 exists and returns valid JSON
        # If not, we might need to rely on local state or just be careful.
        # For now, we'll try to get it, or default to epoch if failed.
        response = requests.get(f"{HEROKU_URL}?limit=1", headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if 'readings' in data and len(data['readings']) > 0:
                # Assuming descending order
                latest = data['readings'][0].get('timestamp')
                print(f"[INIT] Latest DB timestamp: {latest}")
                return latest
    except Exception as e:
        print(f"[WARN] Could not fetch latest timestamp: {e}")
    
    return "1970-01-01T00:00:00"

def upload_to_heroku(json_data):
    """Sends JSON data to Heroku backend"""
    global last_processed_timestamp
    
    # Deduplication check
    ts = json_data.get('timestamp', '')
    if ts <= last_processed_timestamp:
        print(f"[SKIP] Duplicate/Old data: {ts} (<= {last_processed_timestamp})")
        return

    try:
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY
        }
        response = requests.post(HEROKU_URL, json=json_data, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            print(f"[OK] Uploaded {ts} (Status {response.status_code})")
            # Update last processed timestamp only if successful
            if ts > last_processed_timestamp:
                last_processed_timestamp = ts
        else:
            print(f"[ERROR] Heroku returned {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"[ERROR] Upload to Heroku failed: {e}")

def parse_csv_line(line):
    """
    Parses a single log line (CSV format) from Arduino dump.
    Format: timestamp,device_id,sensor_name,bus,pin,rom,raw,cal,status...
    """
    try:
        parts = line.split(',')
        if len(parts) < 3: return None
        
        # Basic validation: timestamp is first
        timestamp = parts[0]
        if not re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', timestamp):
            return None
            
        device_id = parts[1]
        sensor_name = parts[2]
        
        # Construct payload structure (matching upload_batch in recovery script)
        payload = {
            "site_id": SITE_ID,
            "device_id": device_id,
            "timestamp": timestamp,
            "readings": []
        }
        
        # Temperature sensor
        # Format: timestamp,device,name,bus,pin,rom,raw,cal,status,hum,pres,gas
        # Note: CSV format from Arduino logToSD:
        # logFile.print(timestamp); ... sensor_name ... bus ... pin ... rom ... 
        # ... raw ... cal ... status ...
        
        if len(parts) >= 9 and parts[3] in ['A', 'B']:
             payload["readings"].append({
                "sensor_name": sensor_name,
                "bus": parts[3],
                "pin": int(parts[4]),
                "rom": parts[5],
                "raw_temp_c": float(parts[6]) if parts[6] != 'null' else None,
                "temp_c": float(parts[7]) if parts[7] != 'null' else None,
                "status": parts[8]
            })
            
        # Environment sensor (ATM01)
        # logToSD format: timestamp,device,ATM01,I2C,N/A,N/A,temp,temp,ok,hum,pres,gas
        elif sensor_name == "ATM01" and len(parts) >= 12:
             payload["environment_sensor"] = {
                "sensor_name": sensor_name,
                "type": "BME680",
                "temp_c": float(parts[6]),
                "humidity": float(parts[9]),
                "pressure_hpa": float(parts[10]),
                "gas_resistance_ohms": float(parts[11])
            }

        # Level sensor
        # logToSD format: timestamp,device,LL01,L,pin,N/A,N/A,N/A,state
        elif parts[3] == 'L':
             payload["level_sensor"] = {
                "sensor_name": sensor_name,
                "pin": int(parts[4]),
                "state": parts[8]
            }
            
        return payload

    except Exception:
        return None

def main():
    global last_processed_timestamp
    
    port = find_arduino_port()
    print(f"[SERIAL] Connecting to {port} @ {BAUD_RATE}...")
    
    # 1. Fetch latest state from DB
    last_processed_timestamp = fetch_latest_timestamp()
    
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=2)
        ser.dtr = True # Force DTR to reset/wake Uno R4
        time.sleep(3) # Wait for Arduino to boot
        print("[OK] Serial connected. Listening for data...")
    except Exception as e:
        print(f"[ERROR] Could not open serial port {port}: {e}")
        sys.exit(1)

    # Sync Time
    try:
        now_utc = datetime.now(timezone.utc)
        now_central = now_utc.astimezone(CENTRAL_TZ)
        utc_epoch = int(time.time())
        tz_name = now_central.strftime('%Z')
        utc_offset_hours = int(now_central.utcoffset().total_seconds()) // 3600
        print(f"[CLOCK] Syncing time ({tz_name}, UTC{utc_offset_hours:+d}) epoch={utc_epoch}")
        ser.write(f"C{utc_epoch}\n".encode('utf-8'))
        time.sleep(0.5)
    except Exception as e:
        print(f"[WARN] Failed to sync time: {e}")

    # BME Re-init
    try:
        print("[BME] Sending BME680 re-init command (B)...")
        ser.write(b"B\n")
        time.sleep(4)
    except Exception as e:
        print(f"[WARN] Failed to send BME re-init: {e}")

    while True:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                if not line:
                    continue

                # Case 1: JSON Upload (Standard)
                if line.startswith("JSON_UPLOAD:"):
                    raw_json = line.replace("JSON_UPLOAD:", "", 1)
                    try:
                        data = json.loads(raw_json)
                        # Debug log
                        if 'environment_sensor' in data:
                            env = data['environment_sensor']
                            print(f"  [ATM] {env.get('sensor_name')}: {env.get('temp_c')}C")
                        elif 'readings' in data:
                            print(f"  [Temp] {len(data['readings'])} readings")
                            
                        upload_to_heroku(data)
                    except json.JSONDecodeError:
                        print(f"[ERROR] Invalid JSON received")
                        
                # Case 2: CSV Data (Recovery)
                # Check for timestamp format at start of line: YYYY-MM-DDTHH:MM:SS
                elif re.match(r'\d{4}-\d{2}-\d{2}T', line):
                    payload = parse_csv_line(line)
                    if payload:
                        # Found a valid CSV line!
                        # We use upload_to_heroku which has the deduplication logic
                        upload_to_heroku(payload)
                    else:
                        print(f"[Arduino] {line}")
                        
                # Case 3: Debug messages
                else:
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
