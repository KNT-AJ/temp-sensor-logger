import serial
import time
import json
import requests
import sys
import os

# Configuration
SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200
HEROKU_URL = "https://temp-logger-1770077582-8b1b2ec536f6.herokuapp.com/api/temps"
API_KEY = "36e6e1669f7302366f067627383705a0"

def upload_to_heroku(json_data):
    """Sends JSON data to Heroku backend"""
    try:
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY
        }
        response = requests.post(HEROKU_URL, json=json_data, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            print(f"✅ Success: Uploaded to Heroku (Status {response.status_code})")
        else:
            print(f"❌ Error: Heroku returned {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"❌ Error uploading to Heroku: {e}")

def main():
    print(f"🔌 Connecting to {SERIAL_PORT} @ {BAUD_RATE}...")
    
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        ser.dtr = True # Force DTR to reset/wake Uno R4
        time.sleep(1) # Wait for reset
        print("✅ Serial connected. Listening for data...")
    except Exception as e:
        print(f"❌ Could not open serial port {SERIAL_PORT}: {e}")
        sys.exit(1)

    # Clear buffer
    ser.reset_input_buffer()

    while True:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                
                if not line:
                    continue

                # Check for magic prefix
                if line.startswith("JSON_UPLOAD:"):
                    raw_json = line.replace("JSON_UPLOAD:", "", 1)
                    print(f"📦 Received JSON payload ({len(raw_json)} bytes)")
                    
                    try:
                        data = json.loads(raw_json)
                        upload_to_heroku(data)
                    except json.JSONDecodeError as e:
                        print(f"❌ Invalid JSON received: {e}")
                else:
                    # Just a regular debug log from Arduino
                    print(f"[Arduino] {line}")
            else:
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"⚠️ Serial Loop Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
