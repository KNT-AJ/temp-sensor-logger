#!/bin/bash
set -e

# Setup script for Temperature Logger HTTP Proxy Service
# usage: ./scripts/setup_proxy_service.sh

# Determine paths
REPO_DIR=$(pwd)
PROXY_SCRIPT="$REPO_DIR/scripts/http_proxy.js"
NODE_PATH=$(which node || echo "/usr/bin/node")
USER_NAME=$(whoami)
SERVICE_NAME="temp-logger-proxy"

echo "Setting up $SERVICE_NAME..."
echo "  Repo Dir: $REPO_DIR"
echo "  Script:   $PROXY_SCRIPT"
echo "  Node:     $NODE_PATH"
echo "  User:     $USER_NAME"

# Check if script exists
if [ ! -f "$PROXY_SCRIPT" ]; then
    echo "Error: Could not find scripts/http_proxy.js. Are you running this from the repo root?"
    exit 1
fi

# Create systemd service file content
SERVICE_CONTENT="[Unit]
Description=Arduino Temperature Logger HTTP Proxy
After=network.target

[Service]
ExecStart=$NODE_PATH $PROXY_SCRIPT
Restart=always
User=$USER_NAME
WorkingDirectory=$REPO_DIR
Environment=PATH=/usr/bin:/usr/local/bin
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
"

# Install service
echo "Installing service file to /etc/systemd/system/$SERVICE_NAME.service..."
echo "$SERVICE_CONTENT" | sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null

# Reload and Enable
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling $SERVICE_NAME to start on boot..."
sudo systemctl enable $SERVICE_NAME

echo "Starting $SERVICE_NAME..."
sudo systemctl restart $SERVICE_NAME

echo "Checking status..."
sleep 2
sudo systemctl status $SERVICE_NAME --no-pager

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "To view logs: journalctl -u $SERVICE_NAME -f"
echo "=========================================="
