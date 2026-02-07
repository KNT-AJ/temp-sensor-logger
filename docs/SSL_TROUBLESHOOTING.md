# SSL/HTTPS Troubleshooting for Arduino Uno R4 WiFi

## Problem Description

The Arduino Uno R4 WiFi may fail to establish HTTPS connections to Heroku servers, showing errors like:

```
HTTPS connection failed after 20004 ms
  WiFi status: 3
  WiFi RSSI: -47 dBm
```

This happens because:
1. The SSL/TLS handshake times out
2. The board may not have the required root CA certificate
3. The WiFiS3 library has limited TLS capabilities

## Solutions Implemented

We've implemented three solutions that work together:

### Solution 1: Amazon Root CA 1 Certificate (Added to Sketch)

The sketch now includes the Amazon Root CA 1 certificate embedded directly:

```cpp
const char AMAZON_ROOT_CA1[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDQTCCAimgAwIBAgITBmyfz5m/jAo54vB4ikPmljZbyjANBgkqhkiG9w0BAQsF
...
-----END CERTIFICATE-----
)EOF";
```

**Note:** While the certificate is embedded in the sketch, the Arduino Uno R4 WiFi's WiFiSSLClient doesn't directly support `setCACert()` like ESP32. The certificate is included for future compatibility.

### Solution 2: HTTP Fallback Endpoint (Backend + Sketch)

**Backend Change:** Added `/api/temps-http` endpoint that mirrors `/api/temps`:
- Same validation and database storage logic
- Located in `backend/server.js`
- Deployed to Heroku

**Sketch Changes:**
- Added `HEROKU_HTTP_URL` configuration for HTTP endpoint
- Added `USE_HTTP_FALLBACK` flag (enabled by default)
- After 3 consecutive HTTPS failures, automatically switches to HTTP mode
- Tracks failures with `httpsFailCount` and `useHttpFallback` variables

**Important:** HTTP to Heroku will be redirected to HTTPS, so this alone won't fix the issue. You need to set up an HTTP proxy (see below).

### Solution 3: Upload Root Certificate via CLI (arduino-fwuploader)

For headless systems like Raspberry Pi without Arduino IDE 2 GUI, use the `arduino-fwuploader` CLI tool:

**Install on Raspberry Pi (ARM64):**
```bash
# Download
wget https://github.com/arduino/arduino-fwuploader/releases/latest/download/arduino-fwuploader_2.4.1_Linux_ARM64.tar.gz

# Extract and install
tar -xzf arduino-fwuploader_2.4.1_Linux_ARM64.tar.gz
chmod +x arduino-fwuploader
sudo mv arduino-fwuploader /usr/local/bin/
```

**Upload Heroku certificate:**
```bash
arduino-fwuploader certificates flash \
  -b arduino:renesas_uno:unor4wifi \
  -a /dev/ttyACM0 \
  -u temp-logger-1770077582-8b1b2ec536f6.herokuapp.com:443
```

> **Warning:** Flashing certificates erases all existing certs. Include all needed URLs in one command.

**Update firmware (recommended first):**
```bash
arduino-fwuploader firmware flash \
  -b arduino:renesas_uno:unor4wifi \
  -a /dev/ttyACM0
```

### Alternative: Arduino IDE 2 GUI (if available)

If you have Arduino IDE 2 with GUI access:

1. **Open Arduino IDE 2** (not the legacy 1.x version)
2. **Connect your Arduino Uno R4 WiFi** via USB
3. **Close the Serial Monitor** if it's open
4. Go to **Tools → Upload Root Certificates**
5. Click **"Add New"**
6. Enter: `temp-logger-1770077582-8b1b2ec536f6.herokuapp.com`
7. Press Enter, check the box next to the certificate
8. Select your board from the dropdown
9. Click **"Upload"**
10. Wait for "Certificates uploaded" message

After uploading, the board should be able to connect via HTTPS.

### Alternative: Update WiFi Firmware

The Arduino Uno R4 WiFi's connectivity module may need a firmware update:

1. Go to **Tools → Firmware Updater**
2. Select your board
3. Click **"Check Updates"**
4. If updates are available, install them
5. Retry the connection

The newer firmware may include updated root CA certificates.

## Setting Up an HTTP Proxy (For HTTP Fallback)

Since Heroku forces HTTPS, you need a proxy for HTTP fallback to work:

### Option 1: Cloudflare Tunnel (Recommended for production)
```bash
# Install cloudflared
brew install cloudflare/cloudflare/cloudflared

# Create tunnel (requires Cloudflare account)
cloudflared tunnel login
cloudflared tunnel create temp-logger
cloudflared tunnel route dns temp-logger temp-logger.yourdomain.com
cloudflared tunnel run temp-logger
```

### Option 2: ngrok (Quick testing)
```bash
# Install ngrok
brew install ngrok

# Create tunnel
ngrok http https://temp-logger-1770077582-8b1b2ec536f6.herokuapp.com
```

Then update `HEROKU_HTTP_URL` in the sketch to point to your proxy's HTTP URL.

### Option 3: Local Proxy Server

Run a simple HTTP-to-HTTPS proxy on a Raspberry Pi or local server:

```javascript
// simple-proxy.js
const http = require('http');
const https = require('https');

http.createServer((req, res) => {
  const options = {
    hostname: 'temp-logger-1770077582-8b1b2ec536f6.herokuapp.com',
    path: req.url.replace('/api/temps-http', '/api/temps'),
    method: req.method,
    headers: req.headers
  };
  options.headers.host = options.hostname;
  
  const proxyReq = https.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });
  
  req.pipe(proxyReq);
}).listen(8080);

console.log('HTTP proxy running on port 8080');
```

## Configuration Summary

In `temp_sensor_logger.ino`:

```cpp
// Main HTTPS endpoint
#define HEROKU_URL "https://temp-logger-1770077582-8b1b2ec536f6.herokuapp.com/api/temps"

// HTTP fallback (update with your proxy URL if using one)
#define HEROKU_HTTP_URL "http://your-proxy.local:8080/api/temps-http"

// Enable/disable HTTP fallback
#define USE_HTTP_FALLBACK 1

// Number of HTTPS failures before switching to HTTP
#define HTTPS_FAIL_COUNT_BEFORE_FALLBACK 3
```

## Monitoring

The sketch now logs detailed connection information:

```
Connecting to temp-logger... (HTTPS)... (WiFi RSSI: -42 dBm)
HTTPS connection failed after 20005 ms
  WiFi status: 3
  WiFi RSSI: -47 dBm
  HTTPS fail count: 1/3
```

After 3 failures:
```
  Switching to HTTP fallback mode!
  Note: HTTP may not work directly with Heroku (HTTPS redirect)
  Consider setting up an HTTP proxy or using ngrok/Cloudflare tunnel
```

## Verification

Test the HTTP endpoint directly:
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"site_id":"test","device_id":"test","timestamp":"2026-02-05T12:00:00Z","readings":[{"sensor_name":"TD01","bus":"A","pin":2,"rom":"28AA00000000","temp_c":21.5,"raw_temp_c":22.0,"status":"ok"}]}' \
  https://temp-logger-1770077582-8b1b2ec536f6.herokuapp.com/api/temps-http
```

Expected response:
```json
{"status":"ok","message":"Temperature data received (HTTP)","received":1,"timestamp":"..."}
```
