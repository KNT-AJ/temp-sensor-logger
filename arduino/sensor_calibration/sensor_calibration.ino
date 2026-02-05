#include <DallasTemperature.h>
#include <OneWire.h>

// ============================================================================
// DS18B20 CALIBRATION SCRIPT
// ============================================================================
// This script guides you through two-point calibration (ice bath + boiling)
// and outputs the calibration values for your production code.
//
// Commands:
//   S = Show live readings (to check stabilization)
//   G = Go / Record the calibration reading
//   N = Next sensor
//   R = Retry current sensor
//   C = Output code (after calibration complete)
// ============================================================================

// Bus configuration (same as production code)
#define BUS_A_PIN 2
#define BUS_B_PIN 3

// Expected reference temperatures (sea level)
#define ICE_POINT 0.0
#define BOIL_POINT 100.0

// Number of readings to average per sensor
#define READINGS_TO_AVERAGE 10

// Live preview settings
#define PREVIEW_INTERVAL_MS 1000
#define PREVIEW_DURATION_READINGS 30

// OneWire and DallasTemperature instances
OneWire oneWireA(BUS_A_PIN);
OneWire oneWireB(BUS_B_PIN);
DallasTemperature sensorsA(&oneWireA);
DallasTemperature sensorsB(&oneWireB);

// Calibration data storage
struct CalibrationData {
  char name[4];
  float iceReading;
  float boilReading;
  float slope;
  float offset;
  bool calibrated;
};

CalibrationData calData[10]; // Max 10 sensors
int totalSensors = 0;
int countA = 0;
int countB = 0;

// Current state
enum CalibrationState {
  STATE_INIT,
  STATE_ICE_READY,
  STATE_ICE_PREVIEW,
  STATE_ICE_MEASURE,
  STATE_BOIL_READY,
  STATE_BOIL_PREVIEW,
  STATE_BOIL_MEASURE,
  STATE_COMPLETE
};

CalibrationState currentState = STATE_INIT;
int currentSensor = 0;
unsigned long lastPreviewTime = 0;

void setup() {
  Serial.begin(9600);
  while (!Serial && millis() < 5000)
    ;

  printHeader();

  // Initialize sensors
  sensorsA.begin();
  sensorsB.begin();

  countA = sensorsA.getDeviceCount();
  countB = sensorsB.getDeviceCount();
  totalSensors = countA + countB;

  // Initialize calibration data
  for (int i = 0; i < countA && i < 10; i++) {
    snprintf(calData[i].name, 4, "A%d", i + 1);
    calData[i].calibrated = false;
  }
  for (int i = 0; i < countB && (countA + i) < 10; i++) {
    snprintf(calData[countA + i].name, 4, "B%d", i + 1);
    calData[countA + i].calibrated = false;
  }

  Serial.println("SENSOR DETECTION");
  Serial.println("================");
  Serial.print("Bus A (Pin 2): ");
  Serial.print(countA);
  Serial.println(" sensor(s)");
  Serial.print("Bus B (Pin 3): ");
  Serial.print(countB);
  Serial.println(" sensor(s)");
  Serial.print("Total: ");
  Serial.println(totalSensors);
  Serial.println();

  if (totalSensors == 0) {
    Serial.println("ERROR: No sensors found! Check wiring.");
    while (1)
      ;
  }

  currentState = STATE_ICE_READY;
  printIceInstructions();
}

void loop() {
  // Handle live preview updates
  if ((currentState == STATE_ICE_PREVIEW ||
       currentState == STATE_BOIL_PREVIEW) &&
      millis() - lastPreviewTime >= PREVIEW_INTERVAL_MS) {
    showLiveReading();
    lastPreviewTime = millis();
  }

  if (Serial.available()) {
    char cmd = Serial.read();
    // Clear any extra characters
    while (Serial.available())
      Serial.read();

    handleCommand(cmd);
  }
}

void handleCommand(char cmd) {
  switch (currentState) {
  case STATE_ICE_READY:
    if (cmd == 'g' || cmd == 'G') {
      currentState = STATE_ICE_MEASURE;
      currentSensor = 0;
      Serial.println("\nRecording ice bath measurements...\n");
      measureIce();
    } else if (cmd == 's' || cmd == 'S') {
      currentState = STATE_ICE_PREVIEW;
      currentSensor = 0;
      Serial.println("\n>>> LIVE PREVIEW MODE <<<");
      Serial.println("Watch readings stabilize, then press 'G' to record\n");
      lastPreviewTime = 0; // Force immediate reading
    }
    break;

  case STATE_ICE_PREVIEW:
    if (cmd == 'g' || cmd == 'G') {
      currentState = STATE_ICE_MEASURE;
      Serial.println("\n--- Recording calibration reading ---\n");
      measureIce();
    } else if (cmd == 'n' || cmd == 'N') {
      currentSensor++;
      if (currentSensor >= totalSensors) {
        currentSensor = 0;
      }
      Serial.print("\nSwitched to sensor ");
      Serial.println(calData[currentSensor].name);
    }
    break;

  case STATE_ICE_MEASURE:
    if (cmd == 'n' || cmd == 'N') {
      currentSensor++;
      if (currentSensor >= totalSensors) {
        printIceResults();
        currentState = STATE_BOIL_READY;
        printBoilInstructions();
      } else {
        Serial.println("\nPress 'S' to preview or 'G' to record directly");
        currentState = STATE_ICE_PREVIEW;
        lastPreviewTime = 0;
      }
    } else if (cmd == 'r' || cmd == 'R') {
      measureIce(); // Retry current sensor
    } else if (cmd == 's' || cmd == 'S') {
      currentState = STATE_ICE_PREVIEW;
      Serial.println("\n>>> LIVE PREVIEW MODE <<<");
      lastPreviewTime = 0;
    }
    break;

  case STATE_BOIL_READY:
    if (cmd == 'g' || cmd == 'G') {
      currentState = STATE_BOIL_MEASURE;
      currentSensor = 0;
      Serial.println("\nRecording boiling water measurements...\n");
      measureBoil();
    } else if (cmd == 's' || cmd == 'S') {
      currentState = STATE_BOIL_PREVIEW;
      currentSensor = 0;
      Serial.println("\n>>> LIVE PREVIEW MODE <<<");
      Serial.println("Watch readings stabilize, then press 'G' to record\n");
      lastPreviewTime = 0;
    }
    break;

  case STATE_BOIL_PREVIEW:
    if (cmd == 'g' || cmd == 'G') {
      currentState = STATE_BOIL_MEASURE;
      Serial.println("\n--- Recording calibration reading ---\n");
      measureBoil();
    } else if (cmd == 'n' || cmd == 'N') {
      currentSensor++;
      if (currentSensor >= totalSensors) {
        currentSensor = 0;
      }
      Serial.print("\nSwitched to sensor ");
      Serial.println(calData[currentSensor].name);
    }
    break;

  case STATE_BOIL_MEASURE:
    if (cmd == 'n' || cmd == 'N') {
      currentSensor++;
      if (currentSensor >= totalSensors) {
        printBoilResults();
        calculateCalibration();
        currentState = STATE_COMPLETE;
        printFinalResults();
      } else {
        Serial.println("\nPress 'S' to preview or 'G' to record directly");
        currentState = STATE_BOIL_PREVIEW;
        lastPreviewTime = 0;
      }
    } else if (cmd == 'r' || cmd == 'R') {
      measureBoil(); // Retry current sensor
    } else if (cmd == 's' || cmd == 'S') {
      currentState = STATE_BOIL_PREVIEW;
      Serial.println("\n>>> LIVE PREVIEW MODE <<<");
      lastPreviewTime = 0;
    }
    break;

  case STATE_COMPLETE:
    if (cmd == 'c' || cmd == 'C') {
      printCodeOutput();
    }
    break;
  }
}

void showLiveReading() {
  sensorsA.requestTemperatures();
  sensorsB.requestTemperatures();

  float temp;
  if (currentSensor < countA) {
    temp = sensorsA.getTempCByIndex(currentSensor);
  } else {
    temp = sensorsB.getTempCByIndex(currentSensor - countA);
  }

  Serial.print("[");
  Serial.print(calData[currentSensor].name);
  Serial.print("] ");

  if (temp == DEVICE_DISCONNECTED_C) {
    Serial.println("ERROR - Sensor disconnected!");
  } else {
    Serial.print(temp, 3);
    Serial.print(" C   ");

    // Show expected value based on current phase
    if (currentState == STATE_ICE_PREVIEW) {
      Serial.print("(target: 0.000 C, error: ");
      Serial.print(temp - ICE_POINT, 3);
    } else {
      Serial.print("(target: 100.000 C, error: ");
      Serial.print(temp - BOIL_POINT, 3);
    }
    Serial.println(" C)");
  }
}

float getAverageReading(int sensorIndex) {
  float sum = 0;
  int validReadings = 0;

  for (int r = 0; r < READINGS_TO_AVERAGE; r++) {
    sensorsA.requestTemperatures();
    sensorsB.requestTemperatures();
    delay(100);

    float temp;
    if (sensorIndex < countA) {
      temp = sensorsA.getTempCByIndex(sensorIndex);
    } else {
      temp = sensorsB.getTempCByIndex(sensorIndex - countA);
    }

    if (temp != DEVICE_DISCONNECTED_C) {
      sum += temp;
      validReadings++;
    }

    Serial.print(".");
  }
  Serial.println();

  if (validReadings == 0)
    return DEVICE_DISCONNECTED_C;
  return sum / validReadings;
}

void measureIce() {
  Serial.print("Recording sensor ");
  Serial.print(calData[currentSensor].name);
  Serial.println(" in ICE BATH...");
  Serial.print("Averaging ");
  Serial.print(READINGS_TO_AVERAGE);
  Serial.print(" readings");

  float avg = getAverageReading(currentSensor);

  if (avg == DEVICE_DISCONNECTED_C) {
    Serial.println("ERROR: Sensor disconnected!");
    Serial.println("Press 'R' to retry, 'S' to preview, or 'N' to skip");
  } else {
    calData[currentSensor].iceReading = avg;

    Serial.print("\n>>> RECORDED: Sensor ");
    Serial.print(calData[currentSensor].name);
    Serial.print(" = ");
    Serial.print(avg, 3);
    Serial.print(" C (error: ");
    Serial.print(avg - ICE_POINT, 3);
    Serial.println(" C)");
    Serial.println();
    Serial.println("Press 'N' for next sensor, 'R' to redo, 'S' to preview");
  }
}

void measureBoil() {
  Serial.print("Recording sensor ");
  Serial.print(calData[currentSensor].name);
  Serial.println(" in BOILING WATER...");
  Serial.print("Averaging ");
  Serial.print(READINGS_TO_AVERAGE);
  Serial.print(" readings");

  float avg = getAverageReading(currentSensor);

  if (avg == DEVICE_DISCONNECTED_C) {
    Serial.println("ERROR: Sensor disconnected!");
    Serial.println("Press 'R' to retry, 'S' to preview, or 'N' to skip");
  } else {
    calData[currentSensor].boilReading = avg;
    calData[currentSensor].calibrated = true;

    Serial.print("\n>>> RECORDED: Sensor ");
    Serial.print(calData[currentSensor].name);
    Serial.print(" = ");
    Serial.print(avg, 3);
    Serial.print(" C (error: ");
    Serial.print(avg - BOIL_POINT, 3);
    Serial.println(" C)");
    Serial.println();
    Serial.println("Press 'N' for next sensor, 'R' to redo, 'S' to preview");
  }
}

void calculateCalibration() {
  for (int i = 0; i < totalSensors; i++) {
    if (calData[i].calibrated) {
      float rawRange = calData[i].boilReading - calData[i].iceReading;
      float refRange = BOIL_POINT - ICE_POINT;

      calData[i].slope = refRange / rawRange;
      calData[i].offset =
          ICE_POINT - (calData[i].slope * calData[i].iceReading);
    }
  }
}

void printHeader() {
  Serial.println();
  Serial.println("╔════════════════════════════════════════════╗");
  Serial.println("║   DS18B20 TWO-POINT CALIBRATION SCRIPT     ║");
  Serial.println("║   Reference: 0°C (ice) + 100°C (boiling)   ║");
  Serial.println("╚════════════════════════════════════════════╝");
  Serial.println();
  Serial.println("Commands: S=preview, G=record, N=next, R=retry, C=code");
  Serial.println();
}

void printIceInstructions() {
  Serial.println("╔════════════════════════════════════════════╗");
  Serial.println("║   STEP 1: ICE BATH (0°C)                   ║");
  Serial.println("╠════════════════════════════════════════════╣");
  Serial.println("║ 1. Fill container mostly with crushed ice  ║");
  Serial.println("║ 2. Add small amount of cold water          ║");
  Serial.println("║ 3. Stir and wait 2 minutes                 ║");
  Serial.println("║ 4. Submerge first sensor, keep wires dry   ║");
  Serial.println("╚════════════════════════════════════════════╝");
  Serial.println();
  Serial.println("Press 'S' to see LIVE readings (watch stabilize)");
  Serial.println("Press 'G' to record calibration reading directly");
}

void printBoilInstructions() {
  Serial.println();
  Serial.println("╔════════════════════════════════════════════╗");
  Serial.println("║   STEP 2: BOILING WATER (100°C)            ║");
  Serial.println("╠════════════════════════════════════════════╣");
  Serial.println("║ 1. Bring water to a ROLLING boil           ║");
  Serial.println("║ 2. Use tongs to submerge sensor            ║");
  Serial.println("║ 3. Keep wires away from steam!             ║");
  Serial.println("║ 4. BE CAREFUL - HOT!                       ║");
  Serial.println("╚════════════════════════════════════════════╝");
  Serial.println();
  Serial.println("Press 'S' to see LIVE readings (watch stabilize)");
  Serial.println("Press 'G' to record calibration reading directly");
}

void printIceResults() {
  Serial.println();
  Serial.println("=== ICE BATH RESULTS ===");
  for (int i = 0; i < totalSensors; i++) {
    Serial.print(calData[i].name);
    Serial.print(": ");
    Serial.print(calData[i].iceReading, 3);
    Serial.println(" C");
  }
}

void printBoilResults() {
  Serial.println();
  Serial.println("=== BOILING WATER RESULTS ===");
  for (int i = 0; i < totalSensors; i++) {
    Serial.print(calData[i].name);
    Serial.print(": ");
    Serial.print(calData[i].boilReading, 3);
    Serial.println(" C");
  }
}

void printFinalResults() {
  Serial.println();
  Serial.println(
      "╔════════════════════════════════════════════════════════════╗");
  Serial.println(
      "║              CALIBRATION COMPLETE!                         ║");
  Serial.println(
      "╚════════════════════════════════════════════════════════════╝");
  Serial.println();
  Serial.println("CALIBRATION SUMMARY");
  Serial.println("===================");
  Serial.println();
  Serial.println("Sensor | Ice Raw  | Boil Raw | Slope  | Offset");
  Serial.println("-------|----------|----------|--------|--------");

  for (int i = 0; i < totalSensors; i++) {
    if (calData[i].calibrated) {
      Serial.print("  ");
      Serial.print(calData[i].name);
      Serial.print("  |  ");
      printFloat(calData[i].iceReading, 5);
      Serial.print("  |  ");
      printFloat(calData[i].boilReading, 6);
      Serial.print(" | ");
      printFloat(calData[i].slope, 6);
      Serial.print(" | ");
      printFloat(calData[i].offset, 6);
      Serial.println();
    }
  }

  Serial.println();
  Serial.println("Press 'C' to output code for production sketch");
}

void printFloat(float val, int width) {
  if (val >= 0)
    Serial.print(" ");
  Serial.print(val, 4);
}

void printCodeOutput() {
  Serial.println();
  Serial.println("// ============================================");
  Serial.println("// COPY THIS INTO YOUR PRODUCTION CODE:");
  Serial.println("// ============================================");
  Serial.println();
  Serial.println("// Calibration values (generated by calibration script)");
  Serial.print("const int CAL_SENSOR_COUNT = ");
  Serial.print(totalSensors);
  Serial.println(";");
  Serial.println();
  Serial.print("float calSlope[CAL_SENSOR_COUNT] = {");
  for (int i = 0; i < totalSensors; i++) {
    if (i > 0)
      Serial.print(", ");
    Serial.print(calData[i].slope, 6);
  }
  Serial.println("};");
  Serial.println();
  Serial.print("float calOffset[CAL_SENSOR_COUNT] = {");
  for (int i = 0; i < totalSensors; i++) {
    if (i > 0)
      Serial.print(", ");
    Serial.print(calData[i].offset, 6);
  }
  Serial.println("};");
  Serial.println();
  Serial.println("// Apply calibration to raw reading:");
  Serial.println("float calibrate(int sensorIndex, float rawTemp) {");
  Serial.println(
      "  return (rawTemp * calSlope[sensorIndex]) + calOffset[sensorIndex];");
  Serial.println("}");
  Serial.println();
  Serial.println("// ============================================");
}
