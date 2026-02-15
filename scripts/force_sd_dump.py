import serial
import time
import json
import requests
import sys
import os
import glob
import re
from datetime import datetime
from serial_uploader import find_arduino_port, upload_to_heroku, parse_csv_line, fetch_latest_timestamp

# Configuration
SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200

def main():
    print("=== Force SD Card Dump & Upload ===")
    print("WARNING: This will stop the live logger service!")
    
    # 1. Stop the service first
    print("Stopping temp-logger-serial service...")
    os.system("sudo systemctl stop temp-logger-serial")
    time.sleep(2)
    
    port = find_arduino_port()
    print(f"[SERIAL] Connecting to {port} @ {BAUD_RATE}...")
    
    # Fetch latest timestamp first to avoid duplicates
    # Since serial_uploader.py has this logic, we just need to ensure the global variable is set
    # But imported module globals are tricky. Let's just rely on the fact that upload_to_heroku
    # uses the module-level 'last_processed_timestamp' variable from serial_uploader.
    # We need to set THAT variable.
    import serial_uploader
    serial_uploader.last_processed_timestamp = fetch_latest_timestamp()
    
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=2)
        ser.dtr = True 
        time.sleep(3) # Wait for Arduino to boot
        print("[OK] Connected.")
        
        # Send Dump Command
        print("[CMD] Sending 'D' (Dump All logs)...")
        ser.write(b"D\n")
        
        print("Reading dump... (Press Ctrl+C to abort)")
        
        line_count = 0
        upload_count = 0
        start_time = time.time()
        
        while True:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                except:
                    continue
                    
                if not line: continue
                
                # Check for end of dump
                if "=== FILE DUMP END ===" in line:
                    print("\n[DONE] Dump complete!")
                    break
                    
                # Parse CSV lines
                # YYYY-MM-DD format
                if re.match(r'\d{4}-\d{2}-\d{2}T', line):
                    payload = parse_csv_line(line)
                    if payload:
                        print(f"\r[READ] {payload['timestamp']}...", end="", flush=True)
                        upload_to_heroku(payload)
                        upload_count += 1
                    line_count += 1
                elif "JSON_UPLOAD:" in line:
                    # Ignore live uploads during dump
                    pass
                else:
                    # Show progress / debug
                    if "--- File:" in line:
                        print(f"\n[FILE] {line}")
                        
            else:
                # Timeout check? No, dump can take a while if files are huge.
                # Just wait.
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nAborted by user.")
    except Exception as e:
        print(f"\n[ERROR] {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            
        print(f"\nProcessed {line_count} lines, Uploaded {upload_count} batches.")
        print("Restarting service...")
        os.system("sudo systemctl start temp-logger-serial")
        print("Done.")

if __name__ == "__main__":
    main()
