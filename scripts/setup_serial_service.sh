#!/bin/bash

# Configuration
SERVICE_NAME="temp-logger-serial"
SCRIPT_PATH="/home/emi01/Desktop/GitHub/temp-sensor-logger/scripts/serial_uploader.py"
USER="emi01"
NODE_SERVICE="temp-logger-proxy"

echo "=== Setting up Serial Uploader Service ==="

# 1. Install Python dependencies
echo "Installing Python dependencies..."
sudo apt update
sudo apt install -y python3-pip python3-serial python3-requests

# 2. Stop old Node.js proxy service if it exists
if systemctl list-units --full -all | grep -Fq "$NODE_SERVICE.service"; then
    echo "Stopping and disabling old proxy service ($NODE_SERVICE)..."
    sudo systemctl stop $NODE_SERVICE
    sudo systemctl disable $NODE_SERVICE
    echo "Old service disabled."
fi

# 3. Create Systemd Service File
echo "Creating systemd service file..."
sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null <<EOF
[Unit]
Description=Arduino Temperature Logger Serial Uploader
After=network.target

[Service]
ExecStart=/usr/bin/python3 $SCRIPT_PATH
WorkingDirectory=$(dirname $SCRIPT_PATH)
Restart=always
User=$USER
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 4. Reload and Start
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling and starting $SERVICE_NAME..."
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

# 5. Check Status
echo "Service status:"
sudo systemctl status $SERVICE_NAME --no-pager

echo "=== Setup Complete ==="
echo "Monitor logs with: journalctl -u $SERVICE_NAME -f"
