# DS18B20 Sensor Calibration Guide

Complete step-by-step guide for calibrating your temperature sensors using the interactive calibration script.

---

## Overview

This guide walks you through **two-point calibration** using:
- **Ice bath** = 0°C (32°F) reference point
- **Boiling water** = 100°C (212°F) reference point (at sea level)

The calibration script will guide you through each step and automatically calculate correction values for your production code.

---

## What You'll Need

### Hardware
- [ ] Arduino with all 10 sensors connected (5 on Pin 2, 5 on Pin 3)
- [ ] USB cable to connect Arduino to computer
- [ ] Ice cubes (crushed ice works best)
- [ ] Container for ice bath (bowl, pitcher, or bucket)
- [ ] Pot to boil water
- [ ] Heat-safe container for boiling water (or use the pot directly)
- [ ] Tongs or pliers to hold sensors in boiling water
- [ ] Towel to dry sensors between tests

### Software
- [ ] Arduino IDE installed
- [ ] Serial Monitor ready (9600 baud)

---

## PHASE 1: Setup the Arduino

### Step 1.1: Open the Calibration Sketch

1. Open Arduino IDE
2. Go to **File → Open**
3. Navigate to: `temp-sensor-logger/arduino/sensor_calibration/sensor_calibration.ino`
4. Click **Open**

### Step 1.2: Upload to Arduino

1. Connect Arduino via USB
2. Go to **Tools → Board** and select your Arduino (e.g., "Arduino Uno R4 WiFi")
3. Go to **Tools → Port** and select the correct COM port
4. Click the **Upload** button (→ arrow icon)
5. Wait for "Done uploading" message

### Step 1.3: Open Serial Monitor

1. Go to **Tools → Serial Monitor** (or press `Ctrl+Shift+M` / `Cmd+Shift+M`)
2. Set baud rate to **9600** (dropdown in bottom-right)
3. Set line ending to **"No line ending"** (dropdown next to baud rate)

### Step 1.4: Verify Sensors Detected

You should see:
```
╔════════════════════════════════════════════╗
║   DS18B20 TWO-POINT CALIBRATION SCRIPT     ║
║   Reference: 0°C (ice) + 100°C (boiling)   ║
╚════════════════════════════════════════════╝

SENSOR DETECTION
================
Bus A (Pin 2): 5 sensor(s)
Bus B (Pin 3): 5 sensor(s)
Total: 10
```

**If you see "0 sensor(s)"**: Check your wiring and pullup resistors, then press the Arduino reset button.

---

## PHASE 2: Ice Bath Calibration (0°C)

### Step 2.1: Prepare the Ice Bath

> ⚠️ **IMPORTANT**: The ice bath must be done correctly to get accurate calibration!

1. **Fill container 75% with ice** (crushed ice is best, but cubes work)
2. **Add cold water** just enough to fill the gaps between ice pieces
3. **Stir** the mixture for 30 seconds
4. **Wait 2 minutes** for temperature to stabilize

**What it should look like:**
```
┌─────────────────┐
│ ❄️❄️❄️❄️❄️❄️❄️❄️ │  ← Mostly ice
│ ❄️💧❄️💧❄️💧❄️💧 │  ← Water filling gaps
│ ❄️❄️❄️❄️❄️❄️❄️❄️ │  ← More ice than water!
└─────────────────┘
```

**Common mistakes:**
- ❌ Too much water, not enough ice → temperature will be above 0°C
- ❌ Not stirring → temperature varies in different spots
- ❌ Not waiting → temperature hasn't stabilized

### Step 2.2: Start Ice Bath Measurements

1. In Serial Monitor, you should see:
   ```
   ╔════════════════════════════════════════════╗
   ║   STEP 1: ICE BATH (0°C)                   ║
   ╠════════════════════════════════════════════╣
   ║ 1. Fill container mostly with crushed ice  ║
   ║ 2. Add small amount of cold water          ║
   ║ 3. Stir and wait 2 minutes                 ║
   ║ 4. Submerge first sensor, keep wires dry   ║
   ╚════════════════════════════════════════════╝

   When ready, press 'G' to start measuring
   ```

2. **Type `G` and press Enter** to begin

### Step 2.3: Measure Each Sensor

For each sensor (A1 through B5):

1. **Submerge the sensor probe** fully into the ice water
   - Only the metal probe tip goes in the water
   - Keep the wires and connections **above water**
   
2. **Hold steady for 10 seconds** while it takes readings
   - You'll see dots appearing: `..........`
   
3. **Read the result:**
   ```
   Sensor A1 ice reading: 0.312 C (error: 0.312 C)
   
   Press 'N' for next sensor, 'R' to retry this sensor
   ```

4. **Type `N` and press Enter** to move to next sensor
   - Or type `R` to retry if you think the reading was wrong

5. **Repeat for all 10 sensors**

### Step 2.4: Ice Bath Complete

After all sensors, you'll see a summary:
```
=== ICE BATH RESULTS ===
A1: 0.312 C
A2: 0.187 C
A3: -0.125 C
...
```

The script automatically moves to the boiling water phase.

---

## PHASE 3: Boiling Water Calibration (100°C)

### Step 3.1: Prepare Boiling Water

> ⚠️ **SAFETY WARNING**: Boiling water causes severe burns! Use caution!

1. **Boil water** in a pot on the stove
2. **Wait for a ROLLING boil** (large bubbles, not just small bubbles)
3. **Keep it boiling** during measurements - don't turn off the heat!

**Rolling boil looks like:**
```
┌─────────────────┐
│ 🫧  🫧  🫧  🫧 │  ← Large bubbles breaking surface
│   🫧  🫧  🫧   │
│ 🫧  🫧  🫧  🫧 │
│  ~~~~~~~~~~~~  │  ← Vigorous movement
└─────────────────┘
```

### Step 3.2: Start Boiling Water Measurements

1. You should see:
   ```
   ╔════════════════════════════════════════════╗
   ║   STEP 2: BOILING WATER (100°C)            ║
   ╠════════════════════════════════════════════╣
   ║ 1. Bring water to a ROLLING boil           ║
   ║ 2. Use tongs to submerge sensor            ║
   ║ 3. Keep wires away from steam!             ║
   ║ 4. BE CAREFUL - HOT!                       ║
   ╚════════════════════════════════════════════╝

   When ready, press 'G' to start measuring
   ```

2. **Type `G` and press Enter** to begin

### Step 3.3: Measure Each Sensor

For each sensor (A1 through B5):

1. **Use tongs/pliers** to hold the sensor by the wire (not the probe)

2. **Submerge the metal probe** into the boiling water
   - Keep the wire and connections **out of the water and steam**
   - Steam can damage the electronics!

3. **Hold steady for 10 seconds** while it takes readings

4. **Read the result:**
   ```
   Sensor A1 boil reading: 99.687 C (error: -0.313 C)
   
   Press 'N' for next sensor, 'R' to retry this sensor
   ```

5. **Type `N` and press Enter** to move to next sensor

6. **Dry the sensor** with a towel before the next measurement

7. **Repeat for all 10 sensors**

---

## PHASE 4: Get Your Calibration Code

### Step 4.1: View Calibration Results

After all boiling water measurements, you'll see:
```
╔════════════════════════════════════════════════════════════╗
║              CALIBRATION COMPLETE!                         ║
╚════════════════════════════════════════════════════════════╝

CALIBRATION SUMMARY
===================

Sensor | Ice Raw  | Boil Raw | Slope  | Offset
-------|----------|----------|--------|--------
  A1   |  0.3120  |  99.6870 | 1.0063 | -0.3135
  A2   |  0.1870  |  99.8130 | 1.0038 | -0.1877
  ...

Press 'C' to output code for production sketch
```

### Step 4.2: Generate Code

1. **Type `C` and press Enter**

2. You'll see ready-to-use code:
   ```cpp
   // ============================================
   // COPY THIS INTO YOUR PRODUCTION CODE:
   // ============================================

   // Calibration values (generated by calibration script)
   const int CAL_SENSOR_COUNT = 10;

   float calSlope[CAL_SENSOR_COUNT] = {1.006300, 1.003800, ...};

   float calOffset[CAL_SENSOR_COUNT] = {-0.313500, -0.187700, ...};

   // Apply calibration to raw reading:
   float calibrate(int sensorIndex, float rawTemp) {
     return (rawTemp * calSlope[sensorIndex]) + calOffset[sensorIndex];
   }

   // ============================================
   ```

### Step 4.3: Save the Calibration Code

1. **Select and copy** the entire code block from Serial Monitor
2. **Paste into a text file** and save it (e.g., `calibration_values.txt`)
3. This code will be added to your production sketch (`temp_sensor_logger.ino`)

---

## Command Reference

| Key | Action | When to Use |
|-----|--------|-------------|
| **G** | **G**o / Start | Begin ice or boiling measurements |
| **N** | **N**ext | Move to next sensor after a reading |
| **R** | **R**etry | Retake current sensor measurement |
| **C** | **C**ode | Output calibration code (after complete) |

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "0 sensor(s)" detected | Wiring issue | Check connections, pullup resistors |
| Ice reading > 1°C | Too much water | Add more ice, stir, wait longer |
| Ice reading < -1°C | Sensor defect | Try retry, may need replacement |
| Boiling < 95°C | Not at full boil | Increase heat, wait for rolling boil |
| "ERROR: Sensor disconnected!" | Wire came loose | Reconnect and press 'R' to retry |
| Slope far from 1.0 (e.g., 0.95 or 1.05) | Possible sensor defect | Consider replacing sensor |

---

## Altitude Adjustment

If you're NOT at sea level, boiling point is lower:

| Elevation | Boiling Point |
|-----------|---------------|
| Sea level | 100.0°C |
| 1,000 ft | 99.0°C |
| 2,000 ft | 98.0°C |
| 3,000 ft | 97.0°C |
| 5,000 ft | 95.0°C |

To adjust, edit line 17 in `sensor_calibration.ino`:
```cpp
#define BOIL_POINT 100.0  // Change to your actual boiling point
```

---

## Quick Checklist

### Before Starting
- [ ] Arduino connected and sketch uploaded
- [ ] Serial Monitor open at 9600 baud
- [ ] All 10 sensors detected
- [ ] Ice bath prepared (mostly ice + some water)
- [ ] Water boiling on stove

### During Calibration
- [ ] Submerge only the metal probe, keep wires dry
- [ ] Press 'G' to start each phase
- [ ] Press 'N' after each reading to continue
- [ ] Press 'R' if you need to retry a reading

### After Calibration
- [ ] Press 'C' to get the code
- [ ] Copy and save the calibration values
- [ ] Add to production sketch
