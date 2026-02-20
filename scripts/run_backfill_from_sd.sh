#!/bin/bash
# =============================================================================
# SD Card Gap Backfill Script
# Run this ON THE RASPBERRY PI to recover data missed during a WiFi outage.
#
# Usage:
#   chmod +x run_backfill_from_sd.sh
#   ./run_backfill_from_sd.sh
#
# This script will:
#   1. Stop the live serial logger service
#   2. Dump all Arduino SD card data to a timestamped CSV
#   3. Run the direct-DB backfill (inserts missing rows, skips existing ones)
#   4. Restart the live logger service
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="${SCRIPT_DIR}/sd_dump_${TIMESTAMP}.csv"
PORT="/dev/ttyACM0"
BAUD=115200

# Pull DATABASE_URL from the backend .env if not already set
if [ -z "$DATABASE_URL" ]; then
    ENV_FILE="${SCRIPT_DIR}/../backend/.env"
    if [ -f "$ENV_FILE" ]; then
        export $(grep -v '^#' "$ENV_FILE" | grep DATABASE_URL | xargs)
    fi
fi

# Fallback: hardcode it here if needed
# DATABASE_URL="postgres://u3r3rg1mu80jkg:...@...rds.amazonaws.com:5432/..."

if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL is not set. Set it in backend/.env or export it before running."
    exit 1
fi

echo "======================================"
echo "  SD Card Gap Backfill"
echo "  $(date)"
echo "======================================"

echo ""
echo "[1/4] Stopping temp-logger-serial service..."
sudo systemctl stop temp-logger-serial || true
sleep 2

echo ""
echo "[2/4] Dumping SD card data to: $DUMP_FILE"
python3 "${SCRIPT_DIR}/retrieve_sd_data.py" "$PORT" "$DUMP_FILE"

if [ ! -f "$DUMP_FILE" ]; then
    echo "ERROR: Dump file not created. SD dump may have failed."
    echo "Restarting service..."
    sudo systemctl start temp-logger-serial || true
    exit 1
fi

echo ""
echo "[3/4] Running direct-DB backfill (inserts missing rows, skips existing)..."
DATABASE_URL="$DATABASE_URL" python3 "${SCRIPT_DIR}/backfill_sd_data.py" "$DUMP_FILE"

echo ""
echo "[4/4] Restarting temp-logger-serial service..."
sudo systemctl start temp-logger-serial || true

echo ""
echo "======================================"
echo "  Backfill complete!"
echo "  Dump saved to: $DUMP_FILE"
echo "======================================"
