# DS18B20 Multi-Bus Temperature Logger

A production-ready Arduino solution for reading 10 DS18B20 temperature sensors across two OneWire buses with local SD card logging and cloud uploads to Heroku.

## Features

- **Dual OneWire Bus Support**: 5 sensors on Pin 2 (Bus A) + 5 sensors on Pin 3 (Bus B)
- **Stable Sensor Identification**: ROM-based mapping prevents reordering when sensors are replaced
- **Multi-Board Compatibility**: Works with ESP32, ESP8266, Arduino MKR WiFi 1010, and Uno R4 WiFi
- **Reliable Local Logging**: CSV files on SD card with daily rotation
- **Cloud Upload with Retry**: Exponential backoff and ring buffer for failed uploads
- **NTP Time Sync**: Real timestamps when WiFi available, uptime fallback otherwise
- **Non-Blocking Design**: Uses `millis()` for timing, never blocks the main loop

## Hardware Requirements

- Arduino-compatible board with WiFi (ESP32, ESP8266, MKR WiFi 1010, or Uno R4 WiFi)
- 10× DS18B20 temperature sensors
- SD card module (SPI) or onboard SD
- 2× 4.7kΩ pullup resistors (one per bus)
- Wiring supplies

See [docs/WIRING.md](docs/WIRING.md) for detailed wiring instructions.

## Project Structure

```
temp-sensor-logger/
├── arduino/
│   └── temp_sensor_logger/
│       └── temp_sensor_logger.ino    # Main Arduino sketch
├── backend/
│   ├── server.js                     # Express.js API server
│   ├── package.json                  # Node.js dependencies
│   ├── schema.sql                    # PostgreSQL schema
│   └── .env.example                  # Environment template
├── docs/
│   └── WIRING.md                     # Wiring diagram and notes
└── README.md                         # This file
```

## Arduino Setup

### 1. Install Required Libraries

Open Arduino IDE → Sketch → Include Library → Manage Libraries, then install:

| Library | Author | Notes |
|---------|--------|-------|
| OneWire | Paul Stoffregen | OneWire communication |
| DallasTemperature | Miles Burton | DS18B20 support |
| ArduinoJson | Benoit Blanchon | JSON serialization |
| SD | Arduino | SD card access |

For board-specific libraries:
- **ESP32**: Built-in WiFi, HTTPClient
- **ESP8266**: ESP8266WiFi, ESP8266HTTPClient (via Board Manager)
- **MKR WiFi 1010**: WiFiNINA (via Library Manager)
- **Uno R4 WiFi**: WiFiS3 (built-in)

### 2. Configure the Sketch

Open `arduino/temp_sensor_logger/temp_sensor_logger.ino` and modify the configuration section:

```cpp
// WiFi credentials
#define WIFI_SSID         "your_wifi_ssid"
#define WIFI_PASS         "your_wifi_password"

// Heroku endpoint configuration
#define HEROKU_URL        "https://your-app.herokuapp.com/api/temps"
#define API_KEY           "your_api_key_here"

// Device identification
#define SITE_ID           "industrial_site_01"
#define DEVICE_ID         "arduino_node_01"

// Timing (milliseconds)
#define SAMPLE_INTERVAL_MS    5000   // Sample every 5 seconds

// Pin configuration (adjust if needed)
#define BUS_A_PIN         2          // OneWire bus A
#define BUS_B_PIN         3          // OneWire bus B
#define SD_CS_PIN         4          // SD card chip select
```

### 3. Upload to Board

1. Select your board: Tools → Board → [Your Board]
2. Select port: Tools → Port → [Your Port]
3. Upload: Sketch → Upload

### 4. Monitor Output

Open Serial Monitor at 115200 baud to see:
- Startup information
- Sensor discovery with ROM addresses
- Per-cycle temperature readings
- Upload status

## Backend Setup (Heroku)

### 1. Create Heroku App

```bash
cd backend
heroku create your-app-name

# Add PostgreSQL (optional but recommended)
heroku addons:create heroku-postgresql:essential-0
```

### 2. Configure Environment

```bash
# Generate a secure API key
API_KEY=$(openssl rand -hex 32)
echo "Your API key: $API_KEY"

# Set environment variables
heroku config:set API_KEY=$API_KEY
heroku config:set NODE_ENV=production
```

### 3. Initialize Database (if using PostgreSQL)

```bash
# Get database URL
heroku pg:psql < schema.sql
```

### 4. Deploy

```bash
git init
git add .
git commit -m "Initial deploy"
heroku git:remote -a your-app-name
git push heroku main
```

### 5. Verify Deployment

```bash
# Health check
curl https://your-app-name.herokuapp.com/health
```

## Testing

### Test Backend Locally

```bash
cd backend
cp .env.example .env
# Edit .env with your API_KEY

npm install
npm start
```

### Test with cURL

```bash
# Health check
curl http://localhost:3000/health

# Submit test data
curl -X POST http://localhost:3000/api/temps \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d '{
    "site_id": "test_site",
    "device_id": "test_device",
    "timestamp": "2026-02-02T12:00:00Z",
    "readings": [
      {"bus": "A", "pin": 2, "rom": "28FF123456789012", "temp_c": 21.5, "status": "ok"},
      {"bus": "B", "pin": 3, "rom": "28FF987654321098", "temp_c": 22.1, "status": "ok"}
    ]
  }'
```

Expected response:
```json
{
  "status": "ok",
  "message": "Temperature data received",
  "received": 2,
  "timestamp": "2026-02-02T12:00:00.000Z"
}
```

## Log File Format

SD card logs are stored as CSV in `/logs/YYYY-MM-DD.csv`:

```csv
timestamp,device_id,bus,pin,rom,temp_c,status
2026-02-02T12:00:00Z,arduino_node_01,A,2,28FF123456789012,21.50,ok
2026-02-02T12:00:00Z,arduino_node_01,B,3,28FF987654321098,22.10,ok
```

Failed cloud uploads are saved to `/unsent.jsonl` for later recovery.

## Troubleshooting

### No Sensors Found
- Check wiring: VDD to 3.3V/5V, GND to GND, DQ to data pin
- Verify 4.7kΩ pullup resistor between VDD and DQ
- Try shorter cable lengths

### SD Card Not Working
- Verify SD_CS_PIN matches your wiring
- Ensure SD card is FAT32 formatted
- Check SPI connections (MOSI, MISO, SCK, CS)

### WiFi Connection Fails
- Double-check SSID and password (case-sensitive)
- Ensure 2.4GHz network (most boards don't support 5GHz)
- Move closer to access point

### Cloud Upload Fails
- Check HEROKU_URL includes `/api/temps`
- Verify API_KEY matches on both ends
- Check Serial Monitor for HTTP error codes

## License

MIT License - See LICENSE file for details.
