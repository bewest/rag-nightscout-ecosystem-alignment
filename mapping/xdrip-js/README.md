# xdrip-js Behavior Documentation

This directory contains documentation extracted from xdrip-js, a Node.js library for interfacing with Dexcom G5/G6 CGM transmitters via Bluetooth Low Energy (BLE). This library serves as a foundation for DIY closed-loop systems and CGM data logging applications.

## Source Repository

- **Repository**: [xdrip-js/xdrip-js](https://github.com/xdrip-js/xdrip-js)
- **Language**: Node.js / JavaScript
- **License**: MIT
- **Analysis Date**: 2026-01-17
- **BLE Library**: noble

## Purpose & Value

xdrip-js provides direct BLE communication with Dexcom G5 and G6 transmitters, enabling:

1. **Direct transmitter access** - Bypasses Dexcom receiver/app for raw CGM data
2. **OpenAPS integration** - Foundation for DIY closed-loop insulin delivery systems
3. **Nightscout connectivity** - Data can be uploaded via client applications
4. **Protocol documentation** - Reverse-engineered Dexcom BLE protocol
5. **Calibration support** - Direct sensor calibration without Dexcom app
6. **Session management** - Start/stop sensor sessions programmatically

## Documentation Index

| Document | Description |
|----------|-------------|
| [ble-protocol.md](ble-protocol.md) | Complete BLE protocol: authentication, message types, opcodes |
| [data-models.md](data-models.md) | Glucose, Calibration, Battery, Version data structures |

## Client Applications

Applications built on xdrip-js:

| Application | Purpose | Repository |
|-------------|---------|------------|
| **Lookout** | OpenAPS integration, glucose monitoring | [xdrip-js/Lookout](https://github.com/xdrip-js/Lookout) |
| **Logger** | Data logging and archival | [xdrip-js/Logger](https://github.com/xdrip-js/Logger) |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        xdrip-js Architecture                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                     CLIENT APPLICATION                                   ││
│  │  (Lookout, Logger, or custom Node.js application)                       ││
│  │                                                                          ││
│  │  const Transmitter = require('xdrip-js');                               ││
│  │  const tx = new Transmitter(transmitterId, getMessagesCallback);         ││
│  │                                                                          ││
│  │  tx.on('glucose', (glucose) => { ... });                                ││
│  │  tx.on('batteryStatus', (battery) => { ... });                          ││
│  │  tx.on('version', (firmware) => { ... });                               ││
│  │  tx.on('calibrationData', (cal) => { ... });                            ││
│  │  tx.on('backfillData', (backfill) => { ... });                          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                     TRANSMITTER CLASS                                    ││
│  │  lib/transmitter.js - Main entry point (EventEmitter)                   ││
│  │                                                                          ││
│  │  ┌─────────────┐  ┌─────────────────────┐  ┌────────────────────────┐   ││
│  │  │ Authenticate│  │ Message Handling    │  │ Session Management     │   ││
│  │  │             │  │                     │  │                        │   ││
│  │  │ - AES-128   │  │ - ReadGlucose       │  │ - StartSensor          │   ││
│  │  │ - ECB mode  │  │ - ReadSensorMessage │  │ - StopSensor           │   ││
│  │  │ - Challenge │  │ - ReadCalibration   │  │ - CalibrateSensor      │   ││
│  │  │ - Bond      │  │ - ProcessBackfill   │  │ - ResetTx              │   ││
│  │  └─────────────┘  └─────────────────────┘  └────────────────────────┘   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                   BLUETOOTH MANAGER                                      ││
│  │  lib/bluetooth-manager.js - BLE abstraction layer                       ││
│  │                                                                          ││
│  │  - Noble library wrapper                                                 ││
│  │  - Service/characteristic discovery                                      ││
│  │  - Read/write operations                                                 ││
│  │  - Notification subscriptions                                            ││
│  │  - Exclusive operation handling (JealousPromise)                        ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                     MESSAGE PROTOCOL                                     ││
│  │  lib/messages/*.js - Protocol message implementations                   ││
│  │                                                                          ││
│  │  Authentication      Control              Session                        ││
│  │  ├── 0x01 AuthReq    ├── 0x22 BatteryTx   ├── 0x26 SessionStartTx       ││
│  │  ├── 0x03 AuthChRx   ├── 0x23 BatteryRx   ├── 0x27 SessionStartRx       ││
│  │  ├── 0x04 AuthChTx   ├── 0x24 TimeTx      ├── 0x28 SessionStopTx        ││
│  │  ├── 0x05 AuthStatus ├── 0x25 TimeRx      └── 0x29 SessionStopRx        ││
│  │  ├── 0x06 KeepAlive  ├── 0x2e SensorTx                                  ││
│  │  ├── 0x07 BondReq    ├── 0x2f SensorRx    Calibration                   ││
│  │  └── 0x09 Disconnect ├── 0x30 GlucoseTx   ├── 0x32 CalDataTx            ││
│  │                      ├── 0x31 GlucoseRx   ├── 0x33 CalDataRx            ││
│  │  Version             ├── 0x42 ResetTx     ├── 0x34 CalGlucoseTx         ││
│  │  ├── 0x20/4A/52 Tx   ├── 0x43 ResetRx     └── 0x35 CalGlucoseRx         ││
│  │  ├── 0x21 Rx0        ├── 0x50 BackfillTx                                ││
│  │  ├── 0x4B Rx1        └── 0x51 BackfillRx                                ││
│  │  └── 0x53 Rx2                                                           ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                     DEXCOM G5/G6 TRANSMITTER                            ││
│  │  BLE GATT Services                                                       ││
│  │                                                                          ││
│  │  CGM Service: F8083532-849E-531C-C594-30F1F86A4EA5                      ││
│  │  ├── Communication: F8083533-...                                        ││
│  │  ├── Control: F8083534-...                                              ││
│  │  ├── Authentication: F8083535-...                                       ││
│  │  └── Backfill: F8083536-...                                             ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Source Files

| File | Purpose | Key Exports |
|------|---------|-------------|
| `index.js` | Entry point | Transmitter class |
| `lib/transmitter.js` | Main class, event emitter, message orchestration | Transmitter |
| `lib/bluetooth-manager.js` | BLE operations via noble | BluetoothManager |
| `lib/bluetooth-services.js` | GATT UUIDs | TransmitterService, CGMServiceCharacteristic |
| `lib/glucose.js` | Glucose data model | Glucose |
| `lib/calibration-state.js` | Calibration state machine | CalibrationState |
| `lib/backfill-parser.js` | Gap-fill data parsing | BackfillParser |
| `lib/crc.js` | CRC-16 XMODEM calculation | crc16, crcValid |

## Message Files

| Directory | Purpose |
|-----------|---------|
| `lib/messages/` | Base message implementations (G5/G6 common) |
| `lib/messages/g5/` | G5-specific messages |
| `lib/messages/g6/` | G6-specific messages, Anubis transmitter support |

## Transmitter Detection

The library auto-detects transmitter type based on serial number prefix:

```javascript
// From lib/transmitter.js
this.g6Transmitter = (id.substr(0, 1) === '8');
const g6Type = id.substr(0, 2);
this.g6PlusTransmitter = (g6Type === '8G' || g6Type === '8H' || 
                          g6Type === '8J' || g6Type === '8L' || g6Type === '8R');
```

| Serial Prefix | Transmitter Type |
|---------------|------------------|
| `4xxxxx` | G5 transmitter |
| `8xxxxx` | G6 transmitter |
| `8G`, `8H`, `8J`, `8L`, `8R` | G6+ transmitter |

## OpenAPS/Nightscout Integration

xdrip-js fits into the DIY diabetes technology ecosystem:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Dexcom G5/G6   │────▶│    xdrip-js     │────▶│    Lookout      │
│   Transmitter   │ BLE │  (this library) │     │  (client app)   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┼────────────────────────┐
                        ▼                                ▼                        ▼
                ┌───────────────┐              ┌─────────────────┐      ┌─────────────────┐
                │   Nightscout  │              │     OpenAPS     │      │      Loop       │
                │   (MongoDB)   │              │   (oref0/oref1) │      │  (alternative)  │
                └───────────────┘              └────────┬────────┘      └─────────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │  Insulin Pump   │
                                               │  (via RileyLink)│
                                               └─────────────────┘
```

## Usage Example

```javascript
const Transmitter = require('xdrip-js');

// 6-character transmitter serial number
const transmitterId = '8G1234';

// Callback to return commands to send to transmitter
function getMessages() {
  return [
    { type: 'CalibrateSensor', date: Date.now(), glucose: 100 }
  ];
}

const transmitter = new Transmitter(transmitterId, getMessages);

// Glucose reading event
transmitter.on('glucose', (glucose) => {
  console.log(`Glucose: ${glucose.glucose} mg/dL`);
  console.log(`Trend: ${glucose.trend} mg/dL per 10min`);
  console.log(`Status: ${glucose.status}`);
});

// Battery status event
transmitter.on('batteryStatus', (battery) => {
  console.log(`VoltageA: ${battery.voltagea}`);
  console.log(`Runtime: ${battery.runtime} days`);
});

// Firmware version event
transmitter.on('version', (firmware) => {
  console.log(`Firmware: ${firmware.firmwareVersion}`);
});

// Disconnect event
transmitter.on('disconnect', () => {
  console.log('Transmitter disconnected');
});
```

## Supported Commands

Commands returned from `getMessagesCallback`:

| Command Type | Fields | Description |
|--------------|--------|-------------|
| `StartSensor` | `date`, `sensorSerialCode` | Start a new sensor session |
| `StopSensor` | `date` | Stop current sensor session |
| `CalibrateSensor` | `date`, `glucose` | Submit calibration BG value |
| `ResetTx` | - | Reset transmitter |
| `BatteryStatus` | - | Request battery information |
| `VersionRequest` | - | Request firmware version |
| `Backfill` | `date`, `endDate` | Request historical glucose data |

## Related Projects

| Project | Relationship |
|---------|-------------|
| [xDrip+](https://github.com/NightscoutFoundation/xDrip) | Android app with similar functionality |
| [xDrip4iOS](https://github.com/JohanDegraeve/xdripswift) | iOS app with similar functionality |
| [cgm-remote-monitor](https://github.com/nightscout/cgm-remote-monitor) | Nightscout - data visualization |
| [oref0](https://github.com/openaps/oref0) | OpenAPS algorithm implementation |
