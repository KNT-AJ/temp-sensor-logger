import sys
import os
import re
import json
import time
import requests
from collections import defaultdict
from datetime import datetime

# Configuration (matches serial_uploader.py)
HEROKU_URL = "https://temp-logger-1770077582-8b1b2ec536f6.herokuapp.com/api/temps"
API_KEY = "36e6e1669f7302366f067627383705a0"
SITE_ID = "industrial_site_01"  # Hardcoded in Arduino sketch

def parse_line(line):
    """
    Parses a single log line. 
    Expected format in log: "... [Arduino] timestamp,device_id,sensor_name,bus,pin,rom,raw,cal,status..."
    Returns a tuple (timestamp, reading_dict) or None.
    """
    if "[Arduino]" not in line:
        return None
    
    # Extract the part after [Arduino]
    try:
        csv_part = line.split("[Arduino]", 1)[1].strip()
        parts = csv_part.split(',')
        
        # Basic validation: timestamp is first
        timestamp = parts[0]
        if not re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', timestamp):
            return None
            
        device_id = parts[1]
        sensor_name = parts[2]
        
        # Check if it's a temperature sensor reading (most common)
        # Format: timestamp,device,name,bus,pin,rom,raw,cal,status,empty,empty,empty
        if len(parts) >= 9 and parts[3] in ['A', 'B']:
            return (timestamp, {
                "type": "temp",
                "device_id": device_id,
                "reading": {
                    "sensor_name": sensor_name,
                    "bus": parts[3],
                    "pin": int(parts[4]),
                    "rom": parts[5],
                    "raw_temp_c": float(parts[6]) if parts[6] != 'null' else None,
                    "temp_c": float(parts[7]) if parts[7] != 'null' else None,
                    "status": parts[8]
                }
            })
            
        # Check if it's an environment sensor (ATM01)
        # Format: timestamp,device,ATM01,I2C,N/A,N/A,temp,temp,ok,hum,pres,gas
        elif sensor_name == "ATM01" and len(parts) >= 12:
             return (timestamp, {
                "type": "env",
                "device_id": device_id,
                "data": {
                    "sensor_name": sensor_name,
                    "type": "BME680",
                    "temp_c": float(parts[6]),
                    "humidity": float(parts[9]),
                    "pressure_hpa": float(parts[10]),
                    "gas_resistance_ohms": float(parts[11])
                }
            })

        # Check if it's a level sensor
        # Format: timestamp,device,LL01,L,pin,N/A,N/A,N/A,state
        elif parts[3] == 'L':
             return (timestamp, {
                "type": "level",
                "device_id": device_id,
                "data": {
                    "sensor_name": sensor_name,
                    "pin": int(parts[4]),
                    "state": parts[8]
                }
            })
            
    except Exception as e:
        # print(f"Error parsing line: {line.strip()} -> {e}")
        pass
        
    return None

def upload_batch(payload):
    """Uploads a constructed JSON payload to Heroku."""
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    try:
        response = requests.post(HEROKU_URL, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            print(f"[OK] Uploaded batch {payload['timestamp']} ({len(payload.get('readings', []))} readings)")
            return True
        else:
            print(f"[ERROR] Upload failed {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Upload exception: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 recover_from_log_dump.py <logfile>")
        sys.exit(1)
        
    logfile = sys.argv[1]
    if not os.path.exists(logfile):
        print(f"File not found: {logfile}")
        sys.exit(1)
        
    print(f"Reading {logfile}...")
    
    # Group readings by timestamp
    batches = defaultdict(lambda: {
        "site_id": SITE_ID,
        "device_id": "",
        "timestamp": "",
        "readings": [],
        # env/level sensors are optional
    })
    
    count = 0
    with open(logfile, 'r', errors='replace') as f:
        for line in f:
            result = parse_line(line)
            if result:
                ts, data = result
                
                batch = batches[ts]
                batch["timestamp"] = ts
                batch["device_id"] = data["device_id"] # Assuming one device per batch
                
                if data["type"] == "temp":
                    batch["readings"].append(data["reading"])
                elif data["type"] == "env":
                    batch["environment_sensor"] = data["data"]
                elif data["type"] == "level":
                    batch["level_sensor"] = data["data"]
                
                count += 1
                
    print(f"Found {count} readings across {len(batches)} timestamps.")
    
    # Sort batches by timestamp to upload in order
    sorted_timestamps = sorted(batches.keys())
    
    print("Starting upload...")
    success_count = 0
    
    for ts in sorted_timestamps:
        if upload_batch(batches[ts]):
            success_count += 1
        time.sleep(0.1) # Be gentle on the API
        
    print(f"Done. Successfully uploaded {success_count}/{len(batches)} batches.")

if __name__ == "__main__":
    main()
