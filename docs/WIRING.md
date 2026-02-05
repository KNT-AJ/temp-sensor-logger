# Wiring Guide

This document provides detailed wiring instructions for the DS18B20 multi-bus temperature logger.

## DS18B20 Pinout

The DS18B20 has 3 pins (flat side facing you, pins down):

```
     ___________
    |           |
    |  DS18B20  |
    |___________|
    |   |   |   |
   GND DQ  VDD
    1   2   3
```

| Pin | Name | Description |
|-----|------|-------------|
| 1 | GND | Ground |
| 2 | DQ | Data (OneWire) |
| 3 | VDD | Power (3.3V or 5V) |

## Dual Bus Wiring Diagram

```
                                    +3.3V/5V
                                       │
                                       │
             ┌─────────────────────────┼─────────────────────────┐
             │                         │                         │
             │                   ┌─────┴─────┐                   │
             │                   │           │                   │
            ┌┴┐                 ┌┴┐         ┌┴┐                  ┌┴┐
            │ │ 4.7kΩ           │ │         │ │ 4.7kΩ            │ │
            │ │                 │ │         │ │                  │ │
            └┬┘                 └┬┘         └┬┘                  └┬┘
             │                   │           │                    │
             │    ┌──────────────┘           └──────────────┐     │
             │    │                                         │     │
   ┌─────────┼────┼────────────────────────────────────────┼─────┼──────────┐
   │         │    │           Arduino WiFi Board           │     │          │
   │         │    │                                        │     │          │
   │      ┌──┴────┴────┐                             ┌─────┴─────┴──┐       │
   │      │    Pin 2   │                             │    Pin 3     │       │
   │      │  (Bus A)   │                             │   (Bus B)    │       │
   │      └────────────┘                             └──────────────┘       │
   │                                                                        │
   │   ┌──────────┐   ┌──────────┐                                          │
   │   │ SD Card  │   │   GND    │                                          │
   │   │  (SPI)   │   │  (Common)│                                          │
   │   └──────────┘   └────┬─────┘                                          │
   │                       │                                                │
   └───────────────────────┼────────────────────────────────────────────────┘
                           │
                           │
   ┌───────────────────────┴────────────────────────────────────────────────┐
   │                                                                        │
   │   ╔═══════════╗   ╔═══════════╗   ╔═══════════╗   ╔═══════════╗       │
   │   ║ DS18B20   ║   ║ DS18B20   ║   ║ DS18B20   ║   ║ DS18B20   ║  ...  │
   │   ║  Sensor 1 ║   ║  Sensor 2 ║   ║  Sensor 3 ║   ║  Sensor 4 ║       │
   │   ╚═══════════╝   ╚═══════════╝   ╚═══════════╝   ╚═══════════╝       │
   │        │               │               │               │               │
   │       GND             GND             GND             GND              │
   │                                                                        │
   └────────────────────────────────────────────────────────────────────────┘
```

## Detailed Connections

### Bus A (5 Sensors on Pin 2)

| Sensor | VDD (Pin 3) | DQ (Pin 2) | GND (Pin 1) |
|--------|-------------|------------|-------------|
| A1 | → 3.3V/5V | → Arduino Pin 2 | → GND |
| A2 | → 3.3V/5V | → Arduino Pin 2 | → GND |
| A3 | → 3.3V/5V | → Arduino Pin 2 | → GND |
| A4 | → 3.3V/5V | → Arduino Pin 2 | → GND |
| A5 | → 3.3V/5V | → Arduino Pin 2 | → GND |
| **Pullup** | 4.7kΩ between 3.3V/5V and Pin 2 |

### Bus B (5 Sensors on Pin 3)

| Sensor | VDD (Pin 3) | DQ (Pin 2) | GND (Pin 1) |
|--------|-------------|------------|-------------|
| B1 | → 3.3V/5V | → Arduino Pin 3 | → GND |
| B2 | → 3.3V/5V | → Arduino Pin 3 | → GND |
| B3 | → 3.3V/5V | → Arduino Pin 3 | → GND |
| B4 | → 3.3V/5V | → Arduino Pin 3 | → GND |
| B5 | → 3.3V/5V | → Arduino Pin 3 | → GND |
| **Pullup** | 4.7kΩ between 3.3V/5V and Pin 3 |

## SD Card Wiring (SPI Module)

For external SPI SD card modules:

| SD Module | Arduino Pin | ESP32 | ESP8266 | MKR 1010 | Uno R4 WiFi |
|-----------|-------------|-------|---------|----------|-------------|
| VCC | 3.3V/5V | 3.3V | 3.3V | VCC | 3.3V |
| GND | GND | GND | GND | GND | GND |
| MISO | — | GPIO19 | GPIO12 | PIN 10 | PIN 12 |
| MOSI | — | GPIO23 | GPIO13 | PIN 8 | PIN 11 |
| SCK | — | GPIO18 | GPIO14 | PIN 9 | PIN 13 |
| CS | SD_CS_PIN | GPIO5 | GPIO15 | PIN 4 | PIN 4 |

> **Note**: Some boards have onboard SD slots (e.g., MKR boards). Check your board's documentation.

## Important Notes

### Pullup Resistors

- **Required**: One 4.7kΩ pullup resistor per bus (between VDD and DQ)
- **Do NOT share** a single pullup across both buses
- For long cable runs (>5m), try 2.2kΩ instead of 4.7kΩ

### Power Supply

- DS18B20 works with both 3.3V and 5V
- ESP32/ESP8266: Use 3.3V (GPIO pins are not 5V tolerant)
- Arduino Uno/MKR: Can use 5V

### Cable Length

| Cable Length | Recommended Pullup | Notes |
|--------------|-------------------|-------|
| < 1m | 4.7kΩ | Standard |
| 1-5m | 4.7kΩ | Ensure good connections |
| 5-10m | 2.2kΩ | May need active pullup |
| > 10m | Not recommended | Use powered sensor hubs |

### Parasitic Power Mode

This setup uses **normal (powered) mode**, not parasitic power mode:
- All sensors have VDD connected to 3.3V/5V
- More reliable than parasitic mode
- Required for 12-bit resolution at maximum speed

### Sensor Identification

Each DS18B20 has a unique 64-bit ROM code (e.g., `28FF123456789012`). The firmware discovers these at startup and uses them for stable identification. This means:

- Sensors can be connected in any order
- Replacing a sensor will assign it a new ID
- The mapping persists across reboots

## Board-Specific Notes

### ESP32

```
Default SPI Pins:
- MOSI: GPIO23
- MISO: GPIO19
- SCK:  GPIO18
- CS:   GPIO5 (configurable)

Recommended SD_CS_PIN: 5
```

### ESP8266

```
Default SPI Pins:
- MOSI: GPIO13
- MISO: GPIO12
- SCK:  GPIO14
- CS:   GPIO15 (configurable)

Recommended SD_CS_PIN: 15

Note: Limited GPIO pins - avoid GPIO0, GPIO2, GPIO15 for sensors
```

### Arduino MKR WiFi 1010

```
Default SPI Pins:
- MOSI: PIN 8
- MISO: PIN 10
- SCK:  PIN 9
- CS:   PIN 4 (configurable)

Has onboard SD slot on some variants
```

### Arduino Uno R4 WiFi

```
Standard SPI Pins:
- MOSI: PIN 11
- MISO: PIN 12
- SCK:  PIN 13
- CS:   PIN 4 (configurable)

Recommended SD_CS_PIN: 4
```

## Testing Wiring

Before uploading the main firmware, test with this simple sketch:

```cpp
#include <OneWire.h>
#include <DallasTemperature.h>

#define BUS_A_PIN 2
#define BUS_B_PIN 3

OneWire oneWireA(BUS_A_PIN);
OneWire oneWireB(BUS_B_PIN);
DallasTemperature sensorsA(&oneWireA);
DallasTemperature sensorsB(&oneWireB);

void setup() {
  Serial.begin(115200);
  while (!Serial);
  
  sensorsA.begin();
  sensorsB.begin();
  
  Serial.print("Bus A sensors: ");
  Serial.println(sensorsA.getDeviceCount());
  
  Serial.print("Bus B sensors: ");
  Serial.println(sensorsB.getDeviceCount());
}

void loop() {
  sensorsA.requestTemperatures();
  sensorsB.requestTemperatures();
  
  Serial.print("Bus A Temp 0: ");
  Serial.println(sensorsA.getTempCByIndex(0));
  
  Serial.print("Bus B Temp 0: ");
  Serial.println(sensorsB.getTempCByIndex(0));
  
  delay(2000);
}
```
