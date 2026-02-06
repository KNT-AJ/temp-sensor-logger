#!/bin/bash
set -e

# Configuration
SKETCH_PATH="arduino/temp_sensor_logger/temp_sensor_logger.ino"
BOARD_FQBN="arduino:renesas_uno:unor4wifi"
PORT="/dev/ttyACM0"

# 1. Install Arduino CLI if not present
if ! command -v arduino-cli &> /dev/null; then
    echo "Installing Arduino CLI..."
    curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
    export PATH=$PATH:$PWD/bin
    sudo mv bin/arduino-cli /usr/local/bin/
else
    echo "Arduino CLI is already installed"
fi

# 2. Update Cores
echo "Updating core index..."
arduino-cli core update-index

# 3. Install Uno R4 WiFi Core
echo "Installing/Updating Uno R4 WiFi core..."
arduino-cli core install arduino:renesas_uno

# 4. Install Libraries
echo "Installing/Updating libraries..."
arduino-cli lib install "OneWire"
arduino-cli lib install "DallasTemperature"
arduino-cli lib install "ArduinoJson"

# 5. Compile
echo "Compiling sketch..."
arduino-cli compile --fqbn $BOARD_FQBN $SKETCH_PATH

# 6. Upload
echo "Uploading sketch to $PORT..."
# Wait a moment for port to settle if it was just plugged in
sleep 2
arduino-cli upload -p $PORT --fqbn $BOARD_FQBN $SKETCH_PATH

echo "Done! Monitor with: arduino-cli monitor -p $PORT -c 115200"
