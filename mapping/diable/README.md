# DiaBLE Behavior Documentation

This directory contains documentation extracted from DiaBLE, a native iOS/watchOS application for continuous glucose monitoring. DiaBLE provides **direct sensor reading** capabilities via NFC and Bluetooth Low Energy (BLE), without requiring the manufacturer's official app.

## Source Repository

- **Repository**: [gui-dos/DiaBLE](https://github.com/gui-dos/DiaBLE)
- **Language**: Swift (native iOS/watchOS)
- **License**: GPL-3.0
- **Analysis Date**: 2026-01-17
- **Platform**: iOS 17+, watchOS 10+

## Purpose & Value

DiaBLE (Diabetes Bluetooth Low Energy) provides:

1. **Direct sensor communication** - Read CGM sensors directly via NFC/BLE without official apps
2. **Multi-sensor support** - Abbott Libre family, Dexcom sensors, and third-party bridges
3. **Sensor debugging** - Raw data dumps, FRAM reads, encryption analysis
4. **Nightscout integration** - Upload glucose readings and calibrations
5. **Real-time streaming** - Continuous BLE streaming from compatible sensors
6. **Cross-platform sync** - iOS and watchOS companion apps

## Documentation Index

| Document | Description |
|----------|-------------|
| [data-models.md](data-models.md) | Glucose, Sensor, Device data structures and state management |
| [cgm-transmitters.md](cgm-transmitters.md) | Abbott, Dexcom, bridge device support and protocols |
| [nightscout-sync.md](nightscout-sync.md) | Nightscout API integration and data synchronization |

## Key Source Files

| File | Purpose | Lines |
|------|---------|-------|
| `App.swift` | SwiftUI app entry point, environment setup | 301 |
| `MainDelegate.swift` | Core app delegate, BLE/NFC orchestration | 492 |
| `Glucose.swift` | Glucose reading structures, history, calibration | 512 |
| `Sensor.swift` | CGM sensor model, state, region, family | 151 |
| `Device.swift` | BLE device abstraction base class | 183 |
| `Libre.swift` | Libre 1 sensor, FRAM layout, parsing | 408 |
| `Libre2.swift` | Libre 2 encryption, BLE streaming | 433 |
| `Libre2Gen2.swift` | Libre 2 Gen2 (new security) support | 258 |
| `Libre3.swift` | Libre 3 AES-CCM encryption, activation | 1212 |
| `LibrePro.swift` | Libre Pro/ProH sensor support | 374 |
| `Lingo.swift` | Abbott Lingo sensor support | 835 |
| `Abbott.swift` | Abbott sensor base, encryption helpers | 207 |
| `Dexcom.swift` | Dexcom G5/G6/ONE support | 693 |
| `DexcomG7.swift` | Dexcom G7/ONE+ support | 827 |
| `MiaoMiao.swift` | MiaoMiao bridge device | 153 |
| `Bubble.swift` | Bubble bridge device | 142 |
| `BluCon.swift` | BluCon bridge device | 209 |
| `NFC.swift` | CoreNFC integration, sensor commands | 933 |
| `NFCTools.swift` | NFC debugging, raw FRAM access | 323 |
| `Bluetooth.swift` | BLE UUID constants, device scanning | 121 |
| `BluetoothDelegate.swift` | CoreBluetooth delegate, characteristic handling | 869 |
| `Nightscout.swift` | Nightscout API upload/download | 273 |
| `Settings.swift` | User preferences, persistent storage | 339 |
| `OOP.swift` | Online processing (LibreOOP) | 505 |

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                       DiaBLE Application Architecture                          │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │                          SwiftUI Layer                                    │ │
│  │                                                                           │ │
│  │  App.swift (@main)                                                        │ │
│  │      │                                                                    │ │
│  │      ├── ContentView.swift (main UI container)                            │ │
│  │      ├── Monitor.swift (glucose graph + current reading)                  │ │
│  │      ├── Details.swift (sensor/transmitter info)                          │ │
│  │      ├── Console.swift (debug log viewer)                                 │ │
│  │      ├── DataView.swift (history table)                                   │ │
│  │      ├── OnlineView.swift (Nightscout/OOP settings)                       │ │
│  │      └── SettingsView.swift (app preferences)                             │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                              │                                                 │
│                              ▼ @Environment                                    │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │                      Observable State Layer                               │ │
│  │                                                                           │ │
│  │  @Observable class AppState                                               │ │
│  │  ├── app: MainDelegate                                                    │ │
│  │  ├── device: Device?           (connected transmitter/bridge)             │ │
│  │  ├── sensor: Sensor?           (current CGM sensor)                       │ │
│  │  ├── transmitter: Transmitter? (attached transmitter)                     │ │
│  │  ├── currentGlucose: Int       (latest reading mg/dL)                     │ │
│  │  ├── lastReadingDate: Date                                                │ │
│  │  ├── history: History          (glucose readings array)                   │ │
│  │  ├── calibration: Calibration  (slope/intercept)                          │ │
│  │  └── status: String            (connection status)                        │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                              │                                                 │
│                              ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │                       MainDelegate Coordinator                            │ │
│  │                                                                           │ │
│  │  MainDelegate: NSObject, WKApplicationDelegate                            │ │
│  │  ├── centralManager: CBCentralManager    (BLE scanning/connection)        │ │
│  │  ├── nfc: NFC?                           (NFC session handler)            │ │
│  │  ├── healthKit: HealthKit?               (Apple Health integration)       │ │
│  │  ├── nightscout: Nightscout?             (NS sync manager)                │ │
│  │  │                                                                        │ │
│  │  Methods:                                                                 │ │
│  │  ├── scan() → Start BLE scanning for devices                              │ │
│  │  ├── connect(device:) → Establish BLE connection                          │ │
│  │  ├── read(sensor:) → NFC read sensor FRAM                                 │ │
│  │  ├── parseSensorData(Data) → Decode raw bytes to readings                 │ │
│  │  └── didParseSensor(sensor:) → Process and upload readings                │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                              │                                                 │
│          ┌───────────────────┼───────────────────┐                             │
│          ▼                   ▼                   ▼                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                      │
│  │     NFC      │    │  Bluetooth   │    │  Nightscout  │                      │
│  │   (CoreNFC)  │    │(CoreBluetooth│    │   (REST API) │                      │
│  └──────────────┘    └──────────────┘    └──────────────┘                      │
│          │                   │                   │                             │
│          ▼                   ▼                   ▼                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                      │
│  │ Libre 1/2/3  │    │ BLE Devices  │    │   Nightscout │                      │
│  │  Pro, Lingo  │    │ MiaoMiao,    │    │    Server    │                      │
│  │   (Abbott)   │    │ Bubble,      │    │              │                      │
│  │              │    │ BluCon,      │    │              │                      │
│  │              │    │ Dexcom G6/G7 │    │              │                      │
│  └──────────────┘    └──────────────┘    └──────────────┘                      │
│                                                                                │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Sensor Support Matrix

### Abbott Libre Family

| Sensor Type | NFC | BLE | Encryption | File |
|-------------|-----|-----|------------|------|
| Libre 1 | ✅ | ❌ (via bridge) | None | `Libre.swift` |
| Libre 2 | ✅ | ✅ | AES (usefulFunction) | `Libre2.swift` |
| Libre 2 Gen2 | ✅ | ✅ | Enhanced | `Libre2Gen2.swift` |
| Libre 3 | ✅ | ✅ | AES-CCM | `Libre3.swift` |
| Libre Pro/ProH | ✅ | ❌ | None | `LibrePro.swift` |
| Libre US 14-Day | ✅ | ❌ | None | `Libre.swift` |
| Libre Select/X | ✅ | ✅ | AES-CCM | `Libre3.swift` |
| Lingo | ✅ | ✅ | AES-CCM | `Lingo.swift` |

### Dexcom Family

| Sensor Type | NFC | BLE | Authentication | File |
|-------------|-----|-----|----------------|------|
| Dexcom G5 | ❌ | ✅ | Bond + Auth | `Dexcom.swift` |
| Dexcom G6 | ❌ | ✅ | Bond + Auth | `Dexcom.swift` |
| Dexcom ONE | ❌ | ✅ | Bond + Auth | `Dexcom.swift` |
| Dexcom G7 | ❌ | ✅ | Enhanced | `DexcomG7.swift` |
| Dexcom ONE+ | ❌ | ✅ | Enhanced | `DexcomG7.swift` |
| Stelo | ❌ | ✅ | Enhanced | `DexcomG7.swift` |

### Third-Party Bridge Devices

| Device | Protocol | Supported Sensors | File |
|--------|----------|-------------------|------|
| MiaoMiao 1/2/3 | BLE | Libre 1/2/Pro | `MiaoMiao.swift` |
| Bubble | BLE | Libre 1/2/Pro | `Bubble.swift` |
| BluCon | BLE | Libre 1 | `BluCon.swift` |

## Data Flow

```
┌─────────────┐    NFC/BLE     ┌─────────────┐    Parse      ┌─────────────┐
│   Sensor    │ ───────────▶   │  Raw Data   │ ───────────▶  │   Glucose   │
│ (Hardware)  │                │   (bytes)   │               │  Readings   │
└─────────────┘                └─────────────┘               └─────────────┘
                                                                    │
                                                                    ▼
                               ┌─────────────┐    Upload     ┌─────────────┐
                               │   Display   │ ◀───────────  │  Calibrate  │
                               │   (UI)      │               │  (optional) │
                               └─────────────┘               └─────────────┘
                                      │
                                      ▼
                               ┌─────────────┐
                               │  Nightscout │
                               │   Upload    │
                               └─────────────┘
```

## Related Documentation

- [xDrip4iOS Documentation](../xdrip4ios/README.md) - Alternative iOS CGM app with similar sensor support
- [Nightscout cgm-remote-monitor](../cgm-remote-monitor/) - Server-side Nightscout documentation
