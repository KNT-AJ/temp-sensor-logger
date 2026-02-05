#include <DallasTemperature.h>
#include <OneWire.h>
#include <SD.h>
#include <SPI.h>

// Bus A: 5 temp sensors on Pin 2
#define BUS_A_PIN 2

// Bus B: 5 temp sensors on Pin 3 (includes 35ft extension)
#define BUS_B_PIN 3

// Liquid Level Sensor (XKC-Y25-T12V) on Pin 5
#define LEVEL_SENSOR_PIN 5

// SD Card chip select pin
#define SD_CS_PIN 4

// Log file name
#define LOG_FILE "TEMPLOG.CSV"

// Logging interval (milliseconds)
#define LOG_INTERVAL_MS 2000

// ============================================================================
// CALIBRATION VALUES (from sensor_calibration.ino - stirred data)
// ============================================================================
const int CAL_SENSOR_COUNT = 10;

float calSlope[CAL_SENSOR_COUNT] = {
    1.0439, 1.0476, 1.0483, 1.0489, 1.0300, // Bus A: A1-A5 (stirred cal)
    1.0418, 1.0474, 1.0467, 1.0489, 1.0489  // Bus B: B1-B5 (stirred cal)
};

float calOffset[CAL_SENSOR_COUNT] = {
    -1.521, -2.199, -2.067, -2.070, -0.744, // Bus A: A1-A5 (stirred cal)
    -1.771, -1.863, -1.472, -1.745, -1.745  // Bus B: B1-B5 (stirred cal)
};

float calibrate(int sensorIndex, float rawTemp) {
  if (sensorIndex >= 0 && sensorIndex < CAL_SENSOR_COUNT) {
    return (rawTemp * calSlope[sensorIndex]) + calOffset[sensorIndex];
  }
  return rawTemp;
}

// Setup OneWire instances for each bus
OneWire oneWireA(BUS_A_PIN);
OneWire oneWireB(BUS_B_PIN);

// Setup DallasTemperature instances for each bus
DallasTemperature sensorsA(&oneWireA);
DallasTemperature sensorsB(&oneWireB);

// SD card status
bool sdReady = false;
bool loggingPaused = false;
unsigned long readingCount = 0;
unsigned long lastLogTime = 0;

void setup(void) {
  Serial.begin(9600);

  // Wait for Serial Monitor to open (up to 5 seconds)
  while (!Serial && millis() < 5000) {
    ;
  }

  Serial.println("==========================================");
  Serial.println("TEMP LOGGER - 10 Temp + 1 Level + SD Card");
  Serial.println("==========================================");
  Serial.println("Commands: D=Dump file, C=Clear file, P=Pause/Resume");
  Serial.println("==========================================");

  // Initialize temp sensors
  sensorsA.begin();
  sensorsB.begin();

  // Initialize liquid level sensor pin
  pinMode(LEVEL_SENSOR_PIN, INPUT);

  // Count temp sensors
  int countA = sensorsA.getDeviceCount();
  int countB = sensorsB.getDeviceCount();

  Serial.print("\nBus A found: ");
  Serial.print(countA);
  Serial.println(" sensor(s)");

  Serial.print("Bus B found: ");
  Serial.print(countB);
  Serial.println(" sensor(s)");

  Serial.print("Total temp sensors: ");
  Serial.println(countA + countB);

  Serial.println("Level sensor: Ready (Pin 5)");

  // Initialize SD card
  Serial.print("\nInitializing SD card... ");
  if (SD.begin(SD_CS_PIN)) {
    sdReady = true;
    Serial.println("OK!");

    // Check if file exists and show size
    if (SD.exists(LOG_FILE)) {
      File logFile = SD.open(LOG_FILE, FILE_READ);
      if (logFile) {
        Serial.print("Log file size: ");
        Serial.print(logFile.size());
        Serial.println(" bytes");
        logFile.close();
      }
    } else {
      // Create new file with header
      File logFile = SD.open(LOG_FILE, FILE_WRITE);
      if (logFile) {
        logFile.println(
            "Reading,Millis,A1_Raw,A1_Cal,A2_Raw,A2_Cal,A3_Raw,A3_Cal,A4_Raw,"
            "A4_Cal,A5_Raw,A5_Cal,B1_Raw,B1_Cal,B2_Raw,B2_Cal,B3_Raw,B3_Cal,B4_"
            "Raw,B4_Cal,B5_Raw,B5_Cal,Level");
        logFile.close();
        Serial.println("Created new log file: " LOG_FILE);
      }
    }
  } else {
    Serial.println("FAILED!");
    Serial.println("Continuing without SD logging...");
  }

  Serial.println("==========================================\n");
}

// ============================================================================
// DUMP FILE TO SERIAL
// ============================================================================
void dumpFileToSerial() {
  if (!sdReady) {
    Serial.println("ERROR: SD card not available");
    return;
  }

  File logFile = SD.open(LOG_FILE, FILE_READ);
  if (!logFile) {
    Serial.println("ERROR: Could not open " LOG_FILE);
    return;
  }

  Serial.println();
  Serial.println("========== FILE DUMP START ==========");
  Serial.print("File: ");
  Serial.print(LOG_FILE);
  Serial.print(" (");
  Serial.print(logFile.size());
  Serial.println(" bytes)");
  Serial.println("--------------------------------------");

  // Read and print file contents
  while (logFile.available()) {
    Serial.write(logFile.read());
  }

  Serial.println("--------------------------------------");
  Serial.println("=========== FILE DUMP END ============");
  Serial.println();

  logFile.close();
}

// ============================================================================
// CLEAR LOG FILE
// ============================================================================
void clearLogFile() {
  if (!sdReady) {
    Serial.println("ERROR: SD card not available");
    return;
  }

  // Remove and recreate file
  SD.remove(LOG_FILE);

  File logFile = SD.open(LOG_FILE, FILE_WRITE);
  if (logFile) {
    logFile.println("Reading,Millis,A1_Raw,A1_Cal,A2_Raw,A2_Cal,A3_Raw,A3_Cal,"
                    "A4_Raw,A4_Cal,A5_Raw,A5_Cal,B1_Raw,B1_Cal,B2_Raw,B2_Cal,"
                    "B3_Raw,B3_Cal,B4_Raw,B4_Cal,B5_Raw,B5_Cal,Level");
    logFile.close();
    readingCount = 0;
    Serial.println("Log file cleared and reset!");
  } else {
    Serial.println("ERROR: Could not create new log file");
  }
}

// ============================================================================
// CHECK FOR SERIAL COMMANDS
// ============================================================================
void checkSerialCommands() {
  if (Serial.available()) {
    char cmd = Serial.read();
    // Clear buffer
    while (Serial.available())
      Serial.read();

    switch (cmd) {
    case 'D':
    case 'd':
      dumpFileToSerial();
      break;

    case 'C':
    case 'c':
      clearLogFile();
      break;

    case 'P':
    case 'p':
      loggingPaused = !loggingPaused;
      if (loggingPaused) {
        Serial.println(">>> LOGGING PAUSED <<<");
      } else {
        Serial.println(">>> LOGGING RESUMED <<<");
      }
      break;

    default:
      Serial.println("Commands: D=Dump, C=Clear, P=Pause/Resume");
      break;
    }
  }
}

// ============================================================================
// MAIN LOOP
// ============================================================================
void loop(void) {
  // Check for serial commands first
  checkSerialCommands();

  // Only log at intervals (non-blocking)
  if (millis() - lastLogTime < LOG_INTERVAL_MS) {
    return;
  }
  lastLogTime = millis();

  // Request temps from both buses
  sensorsA.requestTemperatures();
  sensorsB.requestTemperatures();

  int countA = sensorsA.getDeviceCount();
  int countB = sensorsB.getDeviceCount();

  // Arrays to store readings
  float rawA[5] = {0, 0, 0, 0, 0};
  float calA[5] = {0, 0, 0, 0, 0};
  float rawB[5] = {0, 0, 0, 0, 0};
  float calB[5] = {0, 0, 0, 0, 0};
  int levelState = digitalRead(LEVEL_SENSOR_PIN);

  // Read Bus A sensors
  Serial.println("--- BUS A (Pin 2) ---");
  for (int i = 0; i < countA && i < 5; i++) {
    float rawC = sensorsA.getTempCByIndex(i);
    rawA[i] = rawC;

    Serial.print("  A");
    Serial.print(i + 1);
    Serial.print(": ");

    if (rawC == DEVICE_DISCONNECTED_C) {
      Serial.println("ERROR");
      calA[i] = -999;
    } else {
      float calC = calibrate(i, rawC);
      calA[i] = calC;
      Serial.print("Raw:");
      Serial.print(rawC, 2);
      Serial.print("C -> Cal:");
      Serial.print(calC, 2);
      Serial.print("C (");
      Serial.print(DallasTemperature::toFahrenheit(calC), 1);
      Serial.println("F)");
    }
  }

  // Read Bus B sensors
  Serial.println("--- BUS B (Pin 3 - 35ft) ---");
  for (int i = 0; i < countB && i < 5; i++) {
    float rawC = sensorsB.getTempCByIndex(i);
    rawB[i] = rawC;

    Serial.print("  B");
    Serial.print(i + 1);
    Serial.print(": ");

    if (rawC == DEVICE_DISCONNECTED_C) {
      Serial.println("ERROR");
      calB[i] = -999;
    } else {
      float calC = calibrate(countA + i, rawC);
      calB[i] = calC;
      Serial.print("Raw:");
      Serial.print(rawC, 2);
      Serial.print("C -> Cal:");
      Serial.print(calC, 2);
      Serial.print("C (");
      Serial.print(DallasTemperature::toFahrenheit(calC), 1);
      Serial.println("F)");
    }
  }

  // Liquid Level Sensor
  Serial.println("--- LIQUID LEVEL (Pin 5) ---");
  Serial.print("  Status: ");
  if (levelState == HIGH) {
    Serial.println("LIQUID DETECTED");
  } else {
    Serial.println("NO LIQUID");
  }

  // Log to SD card (if not paused)
  if (sdReady && !loggingPaused) {
    readingCount++;
    File logFile = SD.open(LOG_FILE, FILE_WRITE);
    if (logFile) {
      // Reading number and timestamp
      logFile.print(readingCount);
      logFile.print(",");
      logFile.print(millis());

      // A sensors (raw and calibrated)
      for (int i = 0; i < 5; i++) {
        logFile.print(",");
        logFile.print(rawA[i], 2);
        logFile.print(",");
        logFile.print(calA[i], 2);
      }

      // B sensors (raw and calibrated)
      for (int i = 0; i < 5; i++) {
        logFile.print(",");
        logFile.print(rawB[i], 2);
        logFile.print(",");
        logFile.print(calB[i], 2);
      }

      // Level sensor
      logFile.print(",");
      logFile.println(levelState == HIGH ? "LIQUID" : "NONE");

      logFile.close();

      Serial.print("--- SD: Logged #");
      Serial.print(readingCount);
      Serial.println(" ---");
    } else {
      Serial.println("--- SD: Write failed! ---");
    }
  } else if (loggingPaused) {
    Serial.println("--- SD: Paused ---");
  }

  Serial.println("------------------------------------------\n");
}
