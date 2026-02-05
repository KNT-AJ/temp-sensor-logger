#!/usr/bin/env python3
"""
SD Card Data Retriever for Arduino Temperature Logger
Works on Windows, Mac, and Linux.

WINDOWS SETUP:
1. Install Python from python.org (check "Add to PATH")
2. Open Command Prompt and run: pip install pyserial
3. Close Arduino Serial Monitor
4. Run: python retrieve_sd_data.py COM3 output.csv
   (Replace COM3 with your Arduino's port - check Device Manager)

MAC SETUP:
1. pip3 install pyserial
2. python3 retrieve_sd_data.py /dev/cu.usbmodem14201 output.csv
"""

import serial
import serial.tools.list_ports
import sys
import time
from datetime import datetime

def list_ports():
    """List all available serial ports."""
    ports = serial.tools.list_ports.comports()
    print("\nAvailable ports:")
    for p in ports:
        print(f"  {p.device} - {p.description}")
    print()
    return [p.device for p in ports]

def find_arduino_port():
    """Try to find Arduino port automatically."""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = p.description.lower()
        if 'arduino' in desc or 'usbmodem' in desc or 'usbserial' in desc or 'ch340' in desc:
            return p.device
    # If no Arduino found, return first port if available
    if ports:
        return ports[0].device
    return None

def retrieve_data(port, output_file, baud=9600):
    """Connect to Arduino, dump SD card, save to file."""
    
    print(f"Connecting to {port} at {baud} baud...")
    
    try:
        ser = serial.Serial(port, baud, timeout=2)
        time.sleep(3)  # Wait for Arduino to reset after connection
        
        # Clear any startup messages
        ser.reset_input_buffer()
        
        print("Pausing logging...")
        ser.write(b'P')
        time.sleep(1)
        ser.reset_input_buffer()
        
        print("Requesting file dump (this may take a moment)...")
        ser.write(b'D')
        
        # Collect output
        output_lines = []
        in_data_section = False
        empty_count = 0
        
        print("Receiving data...")
        
        while True:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
            except:
                continue
            
            if not line:
                empty_count += 1
                if empty_count > 15:  # 15 empty reads = done
                    break
                continue
            
            empty_count = 0
            
            # Track file dump markers
            if "FILE DUMP START" in line:
                in_data_section = True
                print("  [Dump started]")
                continue
            elif "FILE DUMP END" in line:
                in_data_section = False
                print("  [Dump complete]")
                break
            elif line.startswith("---"):
                continue  # Skip separator lines
            elif line.startswith("File:"):
                print(f"  {line}")
                continue
            
            # Capture CSV data
            if in_data_section:
                output_lines.append(line)
                if len(output_lines) % 100 == 0:
                    print(f"  Received {len(output_lines)} lines...")
        
        # Resume logging
        print("Resuming logging...")
        ser.write(b'P')
        time.sleep(0.5)
        
        ser.close()
        
        # Write to file
        if output_lines:
            with open(output_file, 'w') as f:
                for line in output_lines:
                    f.write(line + '\n')
            
            print(f"\n{'='*50}")
            print(f"SUCCESS! Saved {len(output_lines)} lines to: {output_file}")
            print(f"{'='*50}")
        else:
            print("\nWarning: No data received. Is the SD card empty?")
        
    except serial.SerialException as e:
        print(f"\nERROR: {e}")
        print("\nTroubleshooting:")
        print("  1. Close Arduino Serial Monitor")
        print("  2. Check the COM port in Device Manager")
        print("  3. Make sure Arduino is connected")
        list_ports()
        sys.exit(1)

def main():
    print("=" * 50)
    print("Arduino SD Card Data Retriever")
    print("=" * 50)
    
    # Parse arguments
    if len(sys.argv) >= 3:
        port = sys.argv[1]
        output_file = sys.argv[2]
    elif len(sys.argv) == 2:
        port = sys.argv[1]
        output_file = f"templog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    else:
        # Try to auto-detect port
        print("\nNo port specified. Scanning for Arduino...")
        port = find_arduino_port()
        if not port:
            print("ERROR: Could not find Arduino.")
            list_ports()
            print("Usage: python retrieve_sd_data.py <COM_PORT> [output_file.csv]")
            print("Example (Windows): python retrieve_sd_data.py COM3 data.csv")
            print("Example (Mac): python3 retrieve_sd_data.py /dev/cu.usbmodem14201 data.csv")
            sys.exit(1)
        output_file = f"templog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        print(f"Found: {port}")
    
    retrieve_data(port, output_file)

if __name__ == "__main__":
    main()
