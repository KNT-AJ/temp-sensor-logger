/*
 * DS18B20 Multi-Bus Temperature Logger
 * =====================================
 * Production-ready Arduino solution for reading 10 DS18B20 temperature sensors
 * across two OneWire buses with SD card logging and Heroku cloud uploads.
 *
 * Hardware:
 *   - Bus A: 5x DS18B20 sensors on digital pin 2
 *   - Bus B: 5x DS18B20 sensors on digital pin 3
 *   - SD card (SPI or onboard)
 *   - WiFi-capable board (ESP32, ESP8266, MKR WiFi 1010, Uno R4 WiFi)
 *
 * Libraries required:
 *   - OneWire
 *   - DallasTemperature
 *   - SD
 *   - WiFi (board-specific)
 *   - ArduinoJson
 *   - TimeLib (for manual time management)
 *   - Adafruit_Sensor
 *   - Adafruit_BME680
 */

#include <TimeLib.h> // Manually added for time management logic without WiFi

// ============================================================================
// CONFIGURATION - Modify these values for your setup
// ============================================================================

// WiFi credentials
#define WIFI_SSID "myHotSpot"
#define WIFI_PASS "ki11erWing$"

// Heroku endpoint configuration
// Heroku endpoint configuration
// URL is set to local Pi proxy to avoid Arduino SSL issues
// Pi forwards to:
// https://temp-logger-1770077582-8b1b2ec536f6.herokuapp.com/api/temps
#define HEROKU_URL "http://10.0.4.58:8080/api/temps"
#define API_KEY "36e6e1669f7302366f067627383705a0"

// HTTP fallback is no longer needed since main URL is HTTP
#define USE_HTTP_FALLBACK 0
#define HTTPS_FAIL_COUNT_BEFORE_FALLBACK 3

// Amazon Root CA 1 certificate (for Heroku HTTPS)
// Valid until 2038-01-17
const char AMAZON_ROOT_CA1[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDQTCCAimgAwIBAgITBmyfz5m/jAo54vB4ikPmljZbyjANBgkqhkiG9w0BAQsF
ADA5MQswCQYDVQQGEwJVUzEPMA0GA1UEChMGQW1hem9uMRkwFwYDVQQDExBBbWF6
b24gUm9vdCBDQSAxMB4XDTE1MDUyNjAwMDAwMFoXDTM4MDExNzAwMDAwMFowOTEL
MAkGA1UEBhMCVVMxDzANBgNVBAoTBkFtYXpvbjEZMBcGA1UEAxMQQW1hem9uIFJv
b3QgQ0EgMTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBALJ4gHHKeNXj
ca9HgFB0fW7Y14h29Jlo91ghYPl0hAEvrAIthtOgQ3pOsqTQNroBvo3bSMgHFzZM
9O6II8c+6zf1tRn4SWiw3te5djgdYZ6k/oI2peVKVuRF4fn9tBb6dNqcmzU5L/qw
IFAGbHrQgLKm+a/sRxmPUDgH3KKHOVj4utWp+UhnMJbulHheb4mjUcAwhmahRWa6
VOujw5H5SNz/0egwLX0tdHA114gk957EWW67c4cX8jJGKLhD+rcdqsq08p8kDi1L
93FcXmn/6pUCyziKrlA4b9v7LWIbxcceVOF34GfID5yHI9Y/QCB/IIDEgEw+OyQm
jgSubJrIqg0CAwEAAaNCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMC
AYYwHQYDVR0OBBYEFIQYzIU07LwMlJQuCFmcx7IQTgoIMA0GCSqGSIb3DQEBCwUA
A4IBAQCY8jdaQZChGsV2USggNiMOruYou6r4lK5IpDB/G/wkjUu0yKGX9rbxenDI
U5PMCCjjmCXPI6T53iHTfIUJrU6adTrCC2qJeHZERxhlbI1Bjjt/msv0tadQ1wUs
N+gDS63pYaACbvXy8MWy7Vu33PqUXHeeE6V/Uq2V8viTO96LXFvKWlJbYK8U90vv
o/ufQJVtMVT8QtPHRh8jrdkPSHCa2XV4cdFyQzR1bldZwgJcJmApzyMZFo6IQ6XU
5MsI+yMRQ+hDKXJioaldXgjUkK642M4UwtBV8ob2xJNDd2ZhwLnoQdeXeGADbkpy
rqXRfboQnoZsG4q5WTP468SQvvG5
-----END CERTIFICATE-----
)EOF";

// Device identification
#define SITE_ID "industrial_site_01"
#define DEVICE_ID "arduino_node_01"

// Timing configuration
#define SAMPLE_INTERVAL_MS 15000  // Sample every 15 seconds
#define WIFI_TIMEOUT_MS 10000     // WiFi connection timeout
#define UPLOAD_RETRY_MAX 5        // Max upload retries
#define UPLOAD_RETRY_BASE_MS 1000 // Base retry delay (exponential backoff)
#define UPLOAD_RETRY_MAX_MS 30000 // Max retry delay

// Pin configuration
#define BUS_A_PIN 2        // OneWire bus A
#define BUS_B_PIN 3        // OneWire bus B
#define SD_CS_PIN 4        // SD card chip select (adjust per board)
#define LEVEL_SENSOR_PIN 5 // Liquid level sensor (XKC-Y25-T12V)

// Sensor configuration
#define SENSORS_PER_BUS 5
#define MAX_SENSORS (SENSORS_PER_BUS * 2)

// Upload queue configuration (ring buffer)
#define UPLOAD_QUEUE_SIZE 10

// Timezone offset in seconds (0 = UTC, -21600 = CST, -18000 = EST, -28800 =
// PST)
#define TIMEZONE_OFFSET -21600

// ============================================================================
// CALIBRATION VALUES (from stirred two-point calibration)
// ============================================================================
// Ice bath: 3.5°C actual, Boiling: 100°C actual
// Index order: A1, A2, A3, A4, A5, B1, B2, B3, B4, B5

const int CAL_SENSOR_COUNT = 10;

float calSlope[CAL_SENSOR_COUNT] = {
    1.0439, 1.0476, 1.0483, 1.0489, 1.0300, // Bus A: A1-A5 (stirred cal)
    1.0418, 1.0474, 1.0467, 1.0489, 1.0489  // Bus B: B1-B5 (stirred cal)
};

float calOffset[CAL_SENSOR_COUNT] = {
    -1.521, -2.199, -2.067, -2.070, -0.744, // Bus A: A1-A5 (stirred cal)
    -1.771, -1.863, -1.472, -1.745, -1.745  // Bus B: B1-B5 (stirred cal)
};

// Sensor name mapping: index -> TD name
// A1=TD03, A2=TD05, A3=TD04, A4=TD01, A5=TD02
// B1=TD09, B2=TD07, B3=TD10, B4=TD08, B5=TD06
const char *sensorNames[CAL_SENSOR_COUNT] = {
    "TD03", "TD05", "TD04", "TD01", "TD02", // Bus A
    "TD09", "TD07", "TD10", "TD08", "TD06"  // Bus B
};

// Display order: maps display position (0-9) to sensor index
// Position 0=TD01, 1=TD02, 2=TD03, etc.
// TD01=A4(idx 3), TD02=A5(idx 4), TD03=A1(idx 0), TD04=A3(idx 2), TD05=A2(idx
// 1) TD06=B5(idx 9), TD07=B2(idx 6), TD08=B4(idx 8), TD09=B1(idx 5),
// TD10=B3(idx 7)
const uint8_t displayOrder[CAL_SENSOR_COUNT] = {
    3, 4, 0, 2, 1, // TD01-TD05 sensor indices
    9, 6, 8, 5, 7  // TD06-TD10 sensor indices
};

// Level sensor name
#define LEVEL_SENSOR_NAME "LL01"

// Apply calibration to raw reading
float calibrate(int sensorIndex, float rawTemp) {
  if (sensorIndex >= 0 && sensorIndex < CAL_SENSOR_COUNT) {
    return (rawTemp * calSlope[sensorIndex]) + calOffset[sensorIndex];
  }
  return rawTemp; // Return uncalibrated if index out of range
}

// ============================================================================
// WATCHDOG / SELF-HEALING CONFIGURATION
// ============================================================================
const int MAX_CONSECUTIVE_FAILURES_BEFORE_RESET =
    20; // Reboot after ~5 mins (20 * 15s) of continuous failure
int consecutiveFailures = 0;

// ============================================================================
// BOARD-SPECIFIC INCLUDES AND DEFINITIONS
// ============================================================================

// Detect board and include appropriate libraries
#if defined(ESP32)
#define BOARD_NAME "ESP32"
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <time.h>
#define HTTPS_SUPPORTED 1
#define USE_BUILTIN_TIME 1

#elif defined(ESP8266)
#define BOARD_NAME "ESP8266"
#include <ESP8266HTTPClient.h>
#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <time.h>
#define HTTPS_SUPPORTED 1
#define USE_BUILTIN_TIME 1

#elif defined(ARDUINO_SAMD_MKRWIFI1010)
#define BOARD_NAME "MKR WiFi 1010"
#include <WiFiNINA.h>
#include <WiFiSSLClient.h>
#define HTTPS_SUPPORTED 1
#define USE_BUILTIN_TIME 0

#elif defined(ARDUINO_UNOR4_WIFI)
#define BOARD_NAME "Arduino Uno R4 WiFi"
#include <WiFiS3.h>
#include <WiFiSSLClient.h>
#define HTTPS_SUPPORTED 1
#define USE_BUILTIN_TIME 0

#else
#define BOARD_NAME "Generic Arduino WiFi"
#include <WiFi.h>
#define HTTPS_SUPPORTED 0
#define USE_BUILTIN_TIME 0
#endif

// Common includes
#include "Adafruit_BME680.h"
#include <Adafruit_Sensor.h>
#include <ArduinoJson.h>
#include <DallasTemperature.h>
#include <OneWire.h>
#include <SD.h>
#include <SPI.h>
#include <Wire.h>

// ============================================================================
// FORWARD DECLARATIONS (required for Arduino IDE)
// ============================================================================
struct SensorInfo;
struct SensorReading;
struct UploadBatch;

// ============================================================================
// DATA STRUCTURES
// ============================================================================

// Sensor information structure
struct SensorInfo {
  uint8_t rom[8];       // 64-bit ROM address
  char busId;           // 'A' or 'B'
  uint8_t pin;          // Physical pin number
  char logicalName[16]; // Human-readable name
  bool present;         // Whether sensor was found at startup
  float lastTemp;       // Last reading
  bool lastReadOk;      // Last read status
};

// Reading structure for upload queue
struct SensorReading {
  char busId;
  uint8_t pin;
  uint8_t rom[8];
  uint8_t sensorIndex; // Index for calibration/name lookup
  float rawTempC;      // Raw temperature before calibration
  float tempC;         // Calibrated temperature
  bool ok;
};

// Queued upload batch
struct UploadBatch {
  char timestamp[25];
  SensorReading readings[MAX_SENSORS];
  uint8_t readingCount;
  uint8_t retryCount;
  bool valid;
  bool levelSensorState; // true = liquid detected

  // Environment Sensor (BME680)
  bool bmeFound;
  float envTempC;
  float envHumidity;
  float envPressure;
  float envGasResistance;
};

// ============================================================================
// FUNCTION PROTOTYPES (required for Arduino IDE)
// ============================================================================
void logToSD(const char *timestamp, SensorReading *readings, uint8_t count,
             bool levelState, bool bmeFound, float envTemp, float envHum,
             float envPres, float envGas);
void readAllSensors(SensorReading *readings, uint8_t *readingCount,
                    uint8_t *okCount, uint8_t *errorCount);
void queueUpload(const char *timestamp, SensorReading *readings, uint8_t count,
                 bool levelState, bool bmeFound, float envTemp, float envHum,
                 float envPres, float envGas);
void buildJsonPayload(UploadBatch *batch, char *buffer, size_t bufferSize);
bool uploadBatch(UploadBatch *batch);

// Serial command handling
void processSerialCommands();
void printHelp();
void listFiles();
void listDirectory(File dir, int indent);
void dumpFile(const char *path);
void tailCurrentLog();
void dumpAllLogs();
void showStatus();

// ============================================================================
// GLOBAL OBJECTS AND VARIABLES
// ============================================================================

// OneWire buses
OneWire oneWireBusA(BUS_A_PIN);
OneWire oneWireBusB(BUS_B_PIN);

// DallasTemperature instances
DallasTemperature sensorsBusA(&oneWireBusA);
DallasTemperature sensorsBusB(&oneWireBusB);

// BME680 Environment Sensor
Adafruit_BME680 bme; // I2C
bool bmeFound = false;

// Sensor registry
SensorInfo sensorRegistry[MAX_SENSORS];
uint8_t sensorCount = 0;

// Upload queue (ring buffer)
UploadBatch uploadQueue[UPLOAD_QUEUE_SIZE];
uint8_t queueHead = 0;
uint8_t queueTail = 0;
uint8_t queueCount = 0;

// Timing
unsigned long lastSampleTime = 0;
unsigned long lastUploadAttempt = 0;
unsigned long currentRetryDelay = UPLOAD_RETRY_BASE_MS;

// State tracking
bool sdAvailable = false;
bool wifiConnected = false;
bool ntpSynced = false;
unsigned long bootTime = 0;

// HTTPS failure tracking for HTTP fallback
uint8_t httpsFailCount = 0;
bool useHttpFallback = false;

// Current date for log file rotation
char currentLogDate[12] = "";
char currentLogPath[32] = "";

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

// Convert ROM address to hex string
void romToString(const uint8_t *rom, char *buffer) {
  for (int i = 0; i < 8; i++) {
    sprintf(buffer + (i * 2), "%02X", rom[i]);
  }
  buffer[16] = '\0';
}

// Print ROM address to Serial
void printRom(const uint8_t *rom) {
  char romStr[17];
  romToString(rom, romStr);
  Serial.print(romStr);
}

// Get current timestamp in ISO format
void getTimestamp(char *buffer, size_t bufferSize) {
  if (timeStatus() != timeNotSet) {
    snprintf(buffer, bufferSize, "%04d-%02d-%02dT%02d:%02d:%02d", year(),
             month(), day(), hour(), minute(), second());
    return;
  }

  // Fallback to uptime-based timestamp
  unsigned long uptime = (millis() - bootTime) / 1000;
  unsigned long hours = uptime / 3600;
  unsigned long mins = (uptime % 3600) / 60;
  unsigned long secs = uptime % 60;
  snprintf(buffer, bufferSize, "UPTIME+%04lu:%02lu:%02lu", hours, mins, secs);
}

// Get current date string for log file rotation
void getCurrentDate(char *buffer) {
  if (timeStatus() != timeNotSet) {
    // Use YYYYMMDD format (8 chars) to ensure filenames fit 8.3 limits (e.g.,
    // 20260206.csv)
    snprintf(buffer, 11, "%04d%02d%02d", year(), month(), day());
    return;
  }
  strcpy(buffer, "no-date");
}

// ============================================================================
// WIFI FUNCTIONS
// ============================================================================

void setupWiFi() {
  // Check if WiFi module is working
  if (WiFi.status() == WL_NO_MODULE) {
    Serial.println("Communication with WiFi module failed!");
    return;
  }

  // STATIC IP CONFIGURATION (To bypass DHCP failure)
  IPAddress local_IP(10, 0, 4, 60);
  IPAddress gateway(10, 0, 4, 1);
  IPAddress subnet(255, 255, 255, 0);
  IPAddress primaryDNS(8, 8, 8, 8);
  IPAddress secondaryDNS(8, 8, 4, 4);

  Serial.println("Configuring Static IP...");
  WiFi.config(local_IP, primaryDNS, gateway, subnet);

  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long startTime = millis();
  while (WiFi.status() != WL_CONNECTED &&
         (millis() - startTime) < WIFI_TIMEOUT_MS) {
    delay(250);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.println();
    Serial.print("WiFi connected! IP: ");
    Serial.println(WiFi.localIP());

    // Initialize NTP if supported
#if USE_BUILTIN_TIME
    Serial.println("Syncing time via NTP...");
    configTime(TIMEZONE_OFFSET, 0, "pool.ntp.org", "time.nist.gov");

    // Wait for time sync (max 5 seconds)
    unsigned long ntpStart = millis();
    while (time(nullptr) < 1000000000 && (millis() - ntpStart) < 5000) {
      delay(100);
    }

    if (time(nullptr) > 1000000000) {
      ntpSynced = true;
      Serial.println("NTP synced successfully");

      char timeStr[25];
      getTimestamp(timeStr, sizeof(timeStr));
      Serial.print("Current time: ");
      Serial.println(timeStr);
    } else {
      Serial.println("NTP sync failed, using uptime timestamps");
    }
#endif
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    wifiConnected = false;
    Serial.println();
    Serial.println(
        "WiFi connection failed - continuing with local logging only");
  }
}

// void checkWiFiConnection() {
//   bool currentlyConnected = (WiFi.status() == WL_CONNECTED);

//   if (currentlyConnected && !wifiConnected) {
//     Serial.println("WiFi reconnected!");
//     Serial.print("IP Address: ");
//     Serial.println(WiFi.localIP());
//     wifiConnected = true;
//   } else if (!currentlyConnected && wifiConnected) {
//     Serial.println("WiFi disconnected - will retry");
//     wifiConnected = false;
//     // Don't immediately reconnect - let the next check handle it
//   } else if (!currentlyConnected) {
//     // Still disconnected, check if we should retry
//     static unsigned long lastReconnectAttempt = 0;
//     if (millis() - lastReconnectAttempt > 10000) {
//       Serial.println("Retrying WiFi connection...");
//       WiFi.begin(WIFI_SSID, WIFI_PASS);
//       lastReconnectAttempt = millis();
//     }
//   }
// }

// ============================================================================
// SD CARD FUNCTIONS
// ============================================================================

void setupSD() {
  Serial.print("Initializing SD card... ");

  if (SD.begin(SD_CS_PIN)) {
    sdAvailable = true;
    Serial.println("SD card ready");

    // Create logs directory if it doesn't exist
    if (!SD.exists("/logs")) {
      SD.mkdir("/logs");
      Serial.println("Created /logs directory");
    }
  } else {
    sdAvailable = false;
    Serial.println("SD card initialization failed!");
  }
}

void updateLogFilePath() {
  char dateStr[12];
  getCurrentDate(dateStr);

  // Check if date changed (for log rotation)
  if (strcmp(dateStr, currentLogDate) != 0) {
    strcpy(currentLogDate, dateStr);
    snprintf(currentLogPath, sizeof(currentLogPath), "/logs/%s.csv", dateStr);

    // Create header if file doesn't exist
    if (sdAvailable && !SD.exists(currentLogPath)) {
      File logFile = SD.open(currentLogPath, FILE_WRITE);
      if (logFile) {
        logFile.println("timestamp,device_id,sensor_name,bus,pin,rom,raw_temp_"
                        "c,cal_temp_c,status,humidity,pressure_hpa,gas_ohms");
        logFile.close();
        Serial.print("Created new log file: ");
        Serial.println(currentLogPath);
      }
    }
  }
}

void logToSD(const char *timestamp, SensorReading *readings, uint8_t count,
             bool levelState, bool bmeFound, float envTemp, float envHum,
             float envPres, float envGas) {
  if (!sdAvailable) {
    Serial.println("SD card not available - skipping local log");
    return;
  }

  updateLogFilePath();

  File logFile = SD.open(currentLogPath, FILE_WRITE);
  if (!logFile) {
    Serial.print("Failed to open log file: ");
    Serial.println(currentLogPath);
    return;
  }

  char romStr[17];

  // Log temperature sensors (in TD01-TD10 order)
  for (uint8_t displayPos = 0;
       displayPos < CAL_SENSOR_COUNT && displayPos < count; displayPos++) {
    uint8_t sensorIdx = displayOrder[displayPos];
    // Find the reading for this sensor index
    for (uint8_t i = 0; i < count; i++) {
      if (readings[i].sensorIndex == sensorIdx) {
        romToString(readings[i].rom, romStr);
        const char *sensorName = sensorNames[sensorIdx];

        // Format:
        // timestamp,device_id,sensor_name,bus,pin,rom,raw_temp_c,cal_temp_c,status
        logFile.print(timestamp);
        logFile.print(",");
        logFile.print(DEVICE_ID);
        logFile.print(",");
        logFile.print(sensorName);
        logFile.print(",");
        logFile.print(readings[i].busId);
        logFile.print(",");
        logFile.print(readings[i].pin);
        logFile.print(",");
        logFile.print(romStr);
        logFile.print(",");

        if (readings[i].ok) {
          logFile.print(readings[i].rawTempC, 2);
          logFile.print(",");
          logFile.print(readings[i].tempC, 2);
          logFile.println(",ok,,,");
        } else {
          logFile.println("null,null,error,,,");
        }
        break;
      }
    }
  }

  // Log level sensor
  logFile.print(timestamp);
  logFile.print(",");
  logFile.print(DEVICE_ID);
  logFile.print(",");
  logFile.print(LEVEL_SENSOR_NAME);
  logFile.print(",L,");
  logFile.print(LEVEL_SENSOR_PIN);
  logFile.print(",N/A,N/A,N/A,");
  logFile.print(levelState ? "LIQUID" : "NONE");
  logFile.println(",,,");

  if (bmeFound) {
    logFile.print(timestamp);
    logFile.print(",");
    logFile.print(DEVICE_ID);
    logFile.print(",ATM01,I2C,N/A,N/A,"); // sensor_name=ATM01
    logFile.print(envTemp, 2);            // reuse raw temp slot for temp
    logFile.print(",");
    logFile.print(envTemp, 2); // reuse cal temp slot
    logFile.print(",ok,");
    logFile.print(envHum, 2);
    logFile.print(",");
    logFile.print(envPres, 2);
    logFile.print(",");
    logFile.println(envGas, 2);
  }

  logFile.flush();
  logFile.close();

  Serial.print("Logged ");
  Serial.print(count);
  Serial.print(" temps + level (");
  Serial.print(levelState ? "LIQUID" : "NONE");
  Serial.println(") to SD");
}

// ============================================================================
// SENSOR DISCOVERY AND MANAGEMENT
// ============================================================================

void discoverSensors() {
  Serial.println("\n=== Sensor Discovery ===");
  sensorCount = 0;

  // Initialize temperature libraries
  sensorsBusA.begin();
  sensorsBusB.begin();

  // Discover sensors on Bus A
  Serial.println("\nBus A (Pin 2):");
  uint8_t countA = sensorsBusA.getDeviceCount();
  Serial.print("  Found ");
  Serial.print(countA);
  Serial.println(" sensor(s)");

  if (countA < SENSORS_PER_BUS) {
    Serial.print("  WARNING: Expected ");
    Serial.print(SENSORS_PER_BUS);
    Serial.println(" sensors!");
  }

  DeviceAddress tempAddress;
  for (uint8_t i = 0; i < countA && sensorCount < MAX_SENSORS; i++) {
    if (sensorsBusA.getAddress(tempAddress, i)) {
      SensorInfo *sensor = &sensorRegistry[sensorCount];
      memcpy(sensor->rom, tempAddress, 8);
      sensor->busId = 'A';
      sensor->pin = BUS_A_PIN;
      snprintf(sensor->logicalName, 16, "A%d", i + 1);
      sensor->present = true;
      sensor->lastTemp = 0;
      sensor->lastReadOk = false;

      Serial.print("  [");
      Serial.print(sensor->logicalName);
      Serial.print("] ROM: ");
      printRom(sensor->rom);
      Serial.println();

      // Set resolution to 12-bit for accuracy
      sensorsBusA.setResolution(tempAddress, 12);

      sensorCount++;
    }
  }

  // Discover sensors on Bus B
  Serial.println("\nBus B (Pin 3):");
  uint8_t countB = sensorsBusB.getDeviceCount();
  Serial.print("  Found ");
  Serial.print(countB);
  Serial.println(" sensor(s)");

  if (countB < SENSORS_PER_BUS) {
    Serial.print("  WARNING: Expected ");
    Serial.print(SENSORS_PER_BUS);
    Serial.println(" sensors!");
  }

  for (uint8_t i = 0; i < countB && sensorCount < MAX_SENSORS; i++) {
    if (sensorsBusB.getAddress(tempAddress, i)) {
      SensorInfo *sensor = &sensorRegistry[sensorCount];
      memcpy(sensor->rom, tempAddress, 8);
      sensor->busId = 'B';
      sensor->pin = BUS_B_PIN;
      snprintf(sensor->logicalName, 16, "B%d", i + 1);
      sensor->present = true;
      sensor->lastTemp = 0;
      sensor->lastReadOk = false;

      Serial.print("  [");
      Serial.print(sensor->logicalName);
      Serial.print("] ROM: ");
      printRom(sensor->rom);
      Serial.println();

      // Set resolution to 12-bit for accuracy
      sensorsBusB.setResolution(tempAddress, 12);

      sensorCount++;
    }
  }

  Serial.println("\n=== Discovery Complete ===");
  Serial.print("Total sensors found: ");
  Serial.println(sensorCount);

  if (sensorCount == 0) {
    Serial.println("ERROR: No sensors found! Check wiring.");
  }
}

// ============================================================================
// TEMPERATURE READING
// ============================================================================

void readAllSensors(SensorReading *readings, uint8_t *readingCount,
                    uint8_t *okCount, uint8_t *errorCount) {
  *readingCount = 0;
  *okCount = 0;
  *errorCount = 0;

  // Request temperatures from all sensors
  sensorsBusA.requestTemperatures();
  sensorsBusB.requestTemperatures();

  // Wait for conversion (750ms for 12-bit resolution)
  delay(750);

  // Read each registered sensor
  for (uint8_t i = 0; i < sensorCount; i++) {
    SensorInfo *sensor = &sensorRegistry[i];
    SensorReading *reading = &readings[*readingCount];

    // Copy sensor info to reading
    reading->busId = sensor->busId;
    reading->pin = sensor->pin;
    reading->sensorIndex = i;
    memcpy(reading->rom, sensor->rom, 8);

    // Read temperature from appropriate bus
    float rawTemp;
    if (sensor->busId == 'A') {
      rawTemp = sensorsBusA.getTempC(sensor->rom);
    } else {
      rawTemp = sensorsBusB.getTempC(sensor->rom);
    }

    // Check for valid reading
    // DEVICE_DISCONNECTED_C is -127, also check for unreasonable values
    if (rawTemp == DEVICE_DISCONNECTED_C || rawTemp < -50 || rawTemp > 125) {
      reading->rawTempC = 0;
      reading->tempC = 0;
      reading->ok = false;
      sensor->lastReadOk = false;
      (*errorCount)++;
    } else {
      // Store both raw and calibrated
      reading->rawTempC = rawTemp;
      float calibratedTemp = calibrate(i, rawTemp);
      reading->tempC = calibratedTemp;
      reading->ok = true;
      sensor->lastTemp = calibratedTemp;
      sensor->lastReadOk = true;
      (*okCount)++;
    }

    (*readingCount)++;
  }
}

// ============================================================================
// CLOUD UPLOAD FUNCTIONS
// ============================================================================

// Add batch to upload queue
void queueUpload(const char *timestamp, SensorReading *readings, uint8_t count,
                 bool levelState, bool bmeFound, float envTemp, float envHum,
                 float envPres, float envGas) {
  if (queueCount >= UPLOAD_QUEUE_SIZE) {
    // Queue full - drop oldest entry
    Serial.println("Upload queue full - dropping oldest batch");
    queueTail = (queueTail + 1) % UPLOAD_QUEUE_SIZE;
    queueCount--;
  }

  UploadBatch *batch = &uploadQueue[queueHead];
  strncpy(batch->timestamp, timestamp, sizeof(batch->timestamp) - 1);
  batch->timestamp[sizeof(batch->timestamp) - 1] = '\0';
  memcpy(batch->readings, readings, sizeof(SensorReading) * count);
  batch->readingCount = count;
  batch->retryCount = 0;
  batch->valid = true;
  batch->levelSensorState = levelState;

  batch->bmeFound = bmeFound;
  batch->envTempC = envTemp;
  batch->envHumidity = envHum;
  batch->envPressure = envPres;
  batch->envGasResistance = envGas;

  queueHead = (queueHead + 1) % UPLOAD_QUEUE_SIZE;
  queueCount++;

  Serial.print("Queued upload batch (queue size: ");
  Serial.print(queueCount);
  Serial.println(")");
}

// Build JSON payload for upload
void buildJsonPayload(UploadBatch *batch, char *buffer, size_t bufferSize) {
  // Use ArduinoJson for efficient JSON building
  static StaticJsonDocument<2560> doc; // Static to save stack space
  doc.clear();

  doc["site_id"] = SITE_ID;
  doc["device_id"] = DEVICE_ID;
  doc["timestamp"] = batch->timestamp;

  JsonArray readings = doc.createNestedArray("readings");

  char romStr[17];

  // Add readings in TD01-TD10 order
  for (uint8_t displayPos = 0;
       displayPos < CAL_SENSOR_COUNT && displayPos < batch->readingCount;
       displayPos++) {
    uint8_t sensorIdx = displayOrder[displayPos];
    // Find the reading for this sensor index
    for (uint8_t i = 0; i < batch->readingCount; i++) {
      if (batch->readings[i].sensorIndex == sensorIdx) {
        JsonObject reading = readings.createNestedObject();
        const char *sensorName = sensorNames[sensorIdx];
        reading["sensor_name"] = sensorName;
        reading["bus"] = String(batch->readings[i].busId);
        reading["pin"] = batch->readings[i].pin;

        romToString(batch->readings[i].rom, romStr);
        reading["rom"] = romStr;

        if (batch->readings[i].ok) {
          reading["raw_temp_c"] =
              serialized(String(batch->readings[i].rawTempC, 2));
          reading["temp_c"] = serialized(String(batch->readings[i].tempC, 2));
          reading["status"] = "ok";
        } else {
          reading["raw_temp_c"] = (char *)nullptr;
          reading["temp_c"] = (char *)nullptr;
          reading["status"] = "error";
        }
        break;
      }
    }
  }

  // Add level sensor data
  JsonObject levelSensor = doc.createNestedObject("level_sensor");
  levelSensor["sensor_name"] = LEVEL_SENSOR_NAME;
  levelSensor["pin"] = LEVEL_SENSOR_PIN;
  levelSensor["state"] = batch->levelSensorState ? "LIQUID" : "NONE";

  // Add environment sensor data
  if (batch->bmeFound) {
    JsonObject envSensor = doc.createNestedObject("environment_sensor");
    envSensor["sensor_name"] = "ATM01";
    envSensor["type"] = "BME680";
    envSensor["temp_c"] = serialized(String(batch->envTempC, 2));
    envSensor["humidity"] = serialized(String(batch->envHumidity, 2));
    envSensor["pressure_hpa"] = serialized(String(batch->envPressure, 2));
    envSensor["gas_resistance_ohms"] =
        serialized(String(batch->envGasResistance, 0));
  }

  serializeJson(doc, buffer, bufferSize);
}

// ============================================================================
// SERIAL UPLOAD (USB TETHERING) CONFIGURATION
// ============================================================================
// We are now sending data over USB Serial to the Pi, which handles the internet
// connection. No WiFi libraries needed.

// Upload a single batch via Serial
bool uploadBatch(UploadBatch *batch) {
  static char jsonBuffer[2560]; // Static to save stack space
  buildJsonPayload(batch, jsonBuffer, sizeof(jsonBuffer));

  size_t len = strlen(jsonBuffer);
  Serial.print("Generated JSON payload size: ");
  Serial.println(len);

  // Ensure previous prints are done
  Serial.flush();
  delay(10); // Small pause for stability

  // Print with a special prefix so the Pi script can detect it
  Serial.print("JSON_UPLOAD:");
  Serial.println(jsonBuffer);
  Serial.flush(); // Ensure JSON is fully sent

  // We assume success since Serial is reliable.
  // The Pi will be responsible for the actual HTTP upload.
  Serial.println("Sent batch to Pi via Serial");

  return true;
}

// Process upload queue
void processUploadQueue() {
  if (queueCount == 0) {
    return;
  }

  // Rate limit upload attempts
  if (millis() - lastUploadAttempt < currentRetryDelay) {
    return;
  }

  lastUploadAttempt = millis();

  // Try to upload oldest batch in queue
  UploadBatch *batch = &uploadQueue[queueTail];

  if (batch->valid) {
    if (uploadBatch(batch)) {
      // Success - remove from queue
      batch->valid = false;
      queueTail = (queueTail + 1) % UPLOAD_QUEUE_SIZE;
      queueCount--;
      currentRetryDelay = UPLOAD_RETRY_BASE_MS; // Reset backoff
    } else {
      // Failed - apply exponential backoff
      batch->retryCount++;

      if (batch->retryCount >= UPLOAD_RETRY_MAX) {
        Serial.println("Max retries reached - dropping batch");

        // Optionally log failed upload to SD
        if (sdAvailable) {
          File failFile = SD.open("/unsent.jsonl", FILE_WRITE);
          if (failFile) {
            char jsonBuffer[2048];
            buildJsonPayload(batch, jsonBuffer, sizeof(jsonBuffer));
            failFile.println(jsonBuffer);
            failFile.close();
            Serial.println("Saved failed upload to /unsent.jsonl");
          }
        }

        batch->valid = false;
        queueTail = (queueTail + 1) % UPLOAD_QUEUE_SIZE;
        queueCount--;
        currentRetryDelay = UPLOAD_RETRY_BASE_MS;
      } else {
        // Exponential backoff
        currentRetryDelay =
            min(currentRetryDelay * 2, (unsigned long)UPLOAD_RETRY_MAX_MS);
        Serial.print("Will retry in ");
        Serial.print(currentRetryDelay / 1000);
        Serial.println(" seconds");
      }
    }
  }
}

// ============================================================================
// SERIAL COMMAND HANDLING
// ============================================================================

bool loggingPaused = false;

void printHelp() {
  Serial.println(F("\n=== Serial Commands ==="));
  Serial.println(F("  D - Dump all log files to serial"));
  Serial.println(F("  L - List files on SD card"));
  Serial.println(F("  P - Pause/Resume logging"));
  Serial.println(F("  S - Show status"));
  Serial.println(F("  T - Tail current log file"));
  Serial.println(F("  C<unix_timestamp> - Sync Clock"));
  Serial.println(F("  I - I2C bus scan"));
  Serial.println(F("  H - Show this help"));
  Serial.println(F("========================\n"));
}

void listFiles() {
  if (!sdAvailable) {
    Serial.println(F("ERROR: SD card not available"));
    return;
  }

  Serial.println(F("\n=== SD Card Contents ==="));

  // List root directory
  File root = SD.open("/");
  if (!root) {
    Serial.println(F("ERROR: Cannot open root directory"));
    return;
  }

  listDirectory(root, 0);
  root.close();

  Serial.println(F("========================\n"));
}

void listDirectory(File dir, int indent) {
  while (true) {
    File entry = dir.openNextFile();
    if (!entry)
      break;

    // Print indent
    for (int i = 0; i < indent; i++) {
      Serial.print(F("  "));
    }

    Serial.print(entry.name());
    if (entry.isDirectory()) {
      Serial.println(F("/"));
      listDirectory(entry, indent + 1);
    } else {
      Serial.print(F("  ("));
      Serial.print(entry.size());
      Serial.println(F(" bytes)"));
    }
    entry.close();
  }
}

void dumpFile(const char *path) {
  File file = SD.open(path);
  if (!file) {
    Serial.print(F("ERROR: Cannot open "));
    Serial.println(path);
    return;
  }

  Serial.print(F("--- File: "));
  Serial.print(path);
  Serial.print(F(" ("));
  Serial.print(file.size());
  Serial.println(F(" bytes) ---"));

  while (file.available()) {
    Serial.write(file.read());
  }

  file.close();
  Serial.println(F("--- End of file ---"));
}

void tailCurrentLog() {
  if (!sdAvailable) {
    Serial.println(F("ERROR: SD card not available"));
    return;
  }

  if (strlen(currentLogPath) == 0) {
    Serial.println(F("ERROR: No active log file"));
    return;
  }

  if (!SD.exists(currentLogPath)) {
    Serial.print(F("ERROR: Log file not found: "));
    Serial.println(currentLogPath);
    return;
  }

  File file = SD.open(currentLogPath);
  if (!file) {
    Serial.print(F("ERROR: Cannot open "));
    Serial.println(currentLogPath);
    return;
  }

  unsigned long fileSize = file.size();
  unsigned long tailBytes = 4096; // Last 4KB

  Serial.print(F("--- Tailing last 4KB of: "));
  Serial.print(currentLogPath);
  Serial.print(F(" ("));
  Serial.print(fileSize);
  Serial.println(F(" bytes) ---"));

  if (fileSize > tailBytes) {
    if (file.seek(fileSize - tailBytes)) {
      // Read until next newline to align to row
      while (file.available()) {
        if (file.read() == '\n')
          break;
      }
    }
  }

  while (file.available()) {
    Serial.write(file.read());
  }

  file.close();
  Serial.println(F("\n--- End of tail ---"));
}

void dumpAllLogs() {
  if (!sdAvailable) {
    Serial.println(F("ERROR: SD card not available"));
    return;
  }

  Serial.println(F("=== FILE DUMP START ==="));

  // Open logs directory
  File logsDir = SD.open("/logs");
  if (!logsDir) {
    Serial.println(F("No /logs directory found"));
    Serial.println(F("=== FILE DUMP END ==="));
    return;
  }

  int fileCount = 0;

  while (true) {
    File entry = logsDir.openNextFile();
    if (!entry)
      break;

    if (!entry.isDirectory()) {
      // Build full path
      char fullPath[48];
      snprintf(fullPath, sizeof(fullPath), "/logs/%s", entry.name());
      entry.close();

      dumpFile(fullPath);
      fileCount++;
    } else {
      entry.close();
    }
  }

  logsDir.close();

  // Also dump unsent.jsonl if it exists
  if (SD.exists("/unsent.jsonl")) {
    dumpFile("/unsent.jsonl");
    fileCount++;
  }

  Serial.print(F("Total files dumped: "));
  Serial.println(fileCount);
  Serial.println(F("=== FILE DUMP END ==="));
}

void showStatus() {
  Serial.println(F("\n=== System Status ==="));

  Serial.print(F("Board: "));
  Serial.println(BOARD_NAME);

  Serial.print(F("SD Card: "));
  Serial.println(sdAvailable ? "OK" : "NOT AVAILABLE");

  Serial.println(F("WiFi: DISABLED (Serial Mode)"));

  Serial.print(F("Time Synced: "));
  Serial.println((timeStatus() != timeNotSet) ? "YES" : "NO");

  Serial.print(F("Logging: "));
  Serial.println(loggingPaused ? "PAUSED" : "ACTIVE");

  Serial.print(F("BME680 Sensor: "));
  Serial.println(bmeFound ? "OK" : "NOT FOUND");

  Serial.print(F("Sensors found: "));
  Serial.println(sensorCount);

  Serial.print(F("Upload queue: "));
  Serial.print(queueCount);
  Serial.println(F(" pending"));

  // Show current log file info
  if (sdAvailable && strlen(currentLogPath) > 0) {
    Serial.print(F("Current log file: "));
    Serial.println(currentLogPath);

    if (SD.exists(currentLogPath)) {
      File logFile = SD.open(currentLogPath);
      if (logFile) {
        Serial.print(F("Log file size: "));
        Serial.print(logFile.size());
        Serial.println(F(" bytes"));
        logFile.close();
      }
    }
  }

  // Uptime
  unsigned long uptime = (millis() - bootTime) / 1000;
  unsigned long hours = uptime / 3600;
  unsigned long mins = (uptime % 3600) / 60;
  unsigned long secs = uptime % 60;
  Serial.print(F("Uptime: "));
  Serial.print(hours);
  Serial.print(F("h "));
  Serial.print(mins);
  Serial.print(F("m "));
  Serial.print(secs);
  Serial.println(F("s"));

  Serial.println(F("=====================\n"));
}

void processSerialCommands() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();

    // Ignore newlines and carriage returns
    if (cmd == '\n' || cmd == '\r')
      return;

    switch (cmd) {
    case 'D':
    case 'd':
      Serial.println(F("Dumping all log files..."));
      dumpAllLogs();
      break;

    case 'L':
    case 'l':
      listFiles();
      break;

    case 'C':
    case 'c': {
      // Expect format: C<timestamp>
      // Use a small buffer to read the rest of the line associated with the
      // number
      int timeout = 100;
      String timeStr = Serial.readStringUntil('\n');
      timeStr.trim(); // Remove whitespace/newlines
      if (timeStr.length() > 0) {
        long receivedTime = timeStr.toInt();
        if (receivedTime > 1000000000) { // Valid roughly post-2001
          setTime(receivedTime + TIMEZONE_OFFSET);
          Serial.print(F("Time synced to: "));
          Serial.println(receivedTime + TIMEZONE_OFFSET);
          // Force log file rotation check immediately
          memset(currentLogDate, 0, sizeof(currentLogDate));
        } else {
          Serial.println(F("Invalid timestamp received"));
        }
      }
    } break;

    case 'P':
    case 'p':
      loggingPaused = !loggingPaused;
      Serial.print(F("Logging "));
      Serial.println(loggingPaused ? "PAUSED" : "RESUMED");
      break;

    case 'S':
    case 's':
      showStatus();
      break;

    case 'T':
    case 't':
      tailCurrentLog();
      break;

    case 'I':
    case 'i': {
      Serial.println(F("\n=== I2C Bus Scan ==="));
      uint8_t count = 0;
      for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
          Serial.print(F("  Device found at 0x"));
          if (addr < 16) Serial.print(F("0"));
          Serial.println(addr, HEX);
          count++;
        }
      }
      if (count == 0) {
        Serial.println(F("  No I2C devices found!"));
      } else {
        Serial.print(F("  Total devices: "));
        Serial.println(count);
      }
      Serial.println(F("===================\n"));
    } break;

    case 'H':
    case 'h':
    case '?':
      printHelp();
      break;

    default:
      Serial.print(F("Unknown command: "));
      Serial.println(cmd);
      printHelp();
      break;
    }
  }
}

// ============================================================================
// MAIN SAMPLING LOOP
// ============================================================================

void sampleAndLog() {
  static SensorReading readings[MAX_SENSORS];
  uint8_t readingCount, okCount, errorCount;

  // BME680 Readings
  float envTemp = 0, envHum = 0, envPres = 0, envGas = 0;
  bool bmeSuccess = false;

  if (bmeFound) {
    // Tell BME680 to begin measurement.
    unsigned long endTime = bme.beginReading();
    if (endTime == 0) {
      Serial.println(F("Failed to begin reading :("));
    } else {
      // Loop or delay? since we are in sampleAndLog which is called in loop,
      // simple delay is okay as we are already "busy" sampling.
      // But readAllSensors has a 750ms delay already.
      // We can start BME reading BEFORE DS18B20 reading!
    }
  }

  // Get current timestamp
  char timestamp[25];
  getTimestamp(timestamp, sizeof(timestamp));

  // Start BME reading if available (async start)
  unsigned long bmeWaitTime = 0;
  if (bmeFound) {
    bmeWaitTime = bme.beginReading();
  }

  // Read all temperature sensors (contains 750ms delay)
  readAllSensors(readings, &readingCount, &okCount, &errorCount);

  // Check BME reading
  if (bmeFound && bmeWaitTime > 0) {
    // If the 750ms delay wasn't enough (unlikely for BME), wait more
    // But usually BME takes ~100-200ms depending on oversampling
    if (!bme.endReading()) {
      Serial.println(F("BME680 reading failed"));
    } else {
      envTemp = bme.temperature;
      envHum = bme.humidity;
      envPres = bme.pressure / 100.0;
      envGas = bme.gas_resistance;
      bmeSuccess = true;
    }
  }

  // Read level sensor
  bool levelState = (digitalRead(LEVEL_SENSOR_PIN) == HIGH);

  // Print summary
  Serial.println("\n--- Sample Cycle ---");
  Serial.print("Time: ");
  Serial.println(timestamp);
  Serial.print("Readings: ");
  Serial.print(okCount);
  Serial.print(" ok, ");
  Serial.print(errorCount);
  Serial.println(" error");

  // Print individual readings with sensor names (in TD01-TD10 order)
  for (uint8_t displayPos = 0;
       displayPos < CAL_SENSOR_COUNT && displayPos < readingCount;
       displayPos++) {
    uint8_t sensorIdx = displayOrder[displayPos];
    // Find the reading for this sensor index
    for (uint8_t i = 0; i < readingCount; i++) {
      if (readings[i].sensorIndex == sensorIdx) {
        const char *sensorName = sensorNames[sensorIdx];
        Serial.print("  ");
        Serial.print(sensorName);
        Serial.print(": ");
        if (readings[i].ok) {
          Serial.print("Raw:");
          Serial.print(readings[i].rawTempC, 2);
          Serial.print("C -> Cal:");
          Serial.print(readings[i].tempC, 2);
          Serial.println("C");
        } else {
          Serial.println("ERROR");
        }
        break;
      }
    }
  }

  // Print level sensor
  Serial.print(LEVEL_SENSOR_NAME);
  Serial.print(": ");
  Serial.println(levelState ? "LIQUID DETECTED" : "NO LIQUID");

  if (bmeSuccess) {
    Serial.print("  ATM01 (BME680): ");
    Serial.print(envTemp);
    Serial.print("C, ");
    Serial.print(envHum);
    Serial.print("%, ");
    Serial.print(envPres);
    Serial.print("hPa, ");
    Serial.print(envGas / 1000.0);
    Serial.println(" KOhms");
  } else if (bmeFound) {
    Serial.println("  ATM01 (BME680): READ ERROR");
  }

  // Log to SD card (primary storage)
  logToSD(timestamp, readings, readingCount, levelState, bmeSuccess, envTemp,
          envHum, envPres, envGas);

  // Queue for cloud upload
  queueUpload(timestamp, readings, readingCount, levelState, bmeSuccess,
              envTemp, envHum, envPres, envGas);
}

// ============================================================================
// SETUP AND MAIN LOOP
// ============================================================================

void setup() {
  // Initialize Serial
  Serial.begin(115200);
  while (!Serial && millis() < 3000) {
    ; // Wait for serial port (with timeout for boards without USB connection)
  }

  bootTime = millis();

  Serial.println("\n========================================");
  Serial.println("DS18B20 Multi-Bus Temperature Logger");
  Serial.println("========================================");
  Serial.print("Board: ");
  Serial.println(BOARD_NAME);
  Serial.print("Site ID: ");
  Serial.println(SITE_ID);
  Serial.print("Device ID: ");
  Serial.println(DEVICE_ID);
  Serial.print("Sample interval: ");
  Serial.print(SAMPLE_INTERVAL_MS / 1000);
  Serial.println(" seconds");
  Serial.print("Bus A pin: ");
  Serial.println(BUS_A_PIN);
  Serial.print("Bus B pin: ");
  Serial.println(BUS_B_PIN);
  Serial.print("Level sensor pin: ");
  Serial.println(LEVEL_SENSOR_PIN);
  Serial.println();

  // Initialize level sensor pin
  pinMode(LEVEL_SENSOR_PIN, INPUT);

  // I2C bus scan — diagnose what's connected
  Serial.println("Scanning I2C bus...");
  Wire.begin();
  uint8_t i2cCount = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("  I2C device found at 0x");
      if (addr < 16) Serial.print("0");
      Serial.println(addr, HEX);
      i2cCount++;
    }
  }
  if (i2cCount == 0) {
    Serial.println("  No I2C devices found! Check SDA/SCL wiring.");
  } else {
    Serial.print("  Total I2C devices: ");
    Serial.println(i2cCount);
  }

  // Initialize BME680
  Serial.println("Initializing BME680...");
  if (bme.begin(0x77)) {
    Serial.println("BME680 Found at 0x77!");
    bmeFound = true;
  } else if (bme.begin(0x76)) {
    Serial.println("BME680 Found at 0x76!");
    bmeFound = true;
  } else {
    Serial.println("Could not find BME680 at 0x77 or 0x76, check wiring!");
    bmeFound = false;
  }

  if (bmeFound) {
    // Set up oversampling and filter initialization
    bme.setTemperatureOversampling(BME680_OS_8X);
    bme.setHumidityOversampling(BME680_OS_2X);
    bme.setPressureOversampling(BME680_OS_4X);
    bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
    bme.setGasHeater(320, 150); // 320*C for 150 ms
  }

  // Initialize SD card
  setupSD();

  // Connect to WiFi
  setupWiFi();

  // Discover temperature sensors
  discoverSensors();

  Serial.println("\n========================================");
  Serial.println("Initialization complete. Starting main loop...");
  Serial.println("Serial commands: D=Dump, L=List, P=Pause, S=Status, H=Help");
  Serial.println("========================================\n");
}

void loop() {
  unsigned long currentTime = millis();

  // Process serial commands (D=dump, L=list, P=pause, S=status, H=help)
  processSerialCommands();

  // Check WiFi connection
  // checkWiFiConnection();

  // Non-blocking sample timing (skip if paused)
  if (!loggingPaused && (currentTime - lastSampleTime >= SAMPLE_INTERVAL_MS)) {
    lastSampleTime = currentTime;
    sampleAndLog();
  }

  // Process upload queue
  processUploadQueue();

  // Small yield for WiFi stack (important for ESP boards)
  yield();
}
