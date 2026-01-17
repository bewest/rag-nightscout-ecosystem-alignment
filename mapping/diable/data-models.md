# DiaBLE Data Models

This document describes the core data structures used in DiaBLE for representing glucose readings, sensors, devices, and application state.

## Table of Contents

- [Glucose Models](#glucose-models)
- [Sensor Model](#sensor-model)
- [Device Model](#device-model)
- [Application State](#application-state)
- [Data Flow Diagram](#data-flow-diagram)

---

## Glucose Models

### GlucoseReading Struct

The base structure for a single glucose measurement.

**File**: `Glucose.swift` (512 lines)

```swift
struct Glucose: Identifiable, Codable {
    let id: Int               // Unique reading ID
    let date: Date            // Timestamp of reading
    let rawValue: Int         // Raw sensor value (uncalibrated)
    let rawTemperature: Int   // Temperature ADC value
    let temperatureAdjustment: Int
    let hasError: Bool        // Data quality flag
    let dataQuality: DataQuality
    let dataQualityFlags: Int
    
    // Derived values
    var value: Int            // Calibrated glucose mg/dL
    var temperature: Double   // Converted temperature
    var trendRate: Double?    // Rate of change mg/dL/min
    var trendArrow: TrendArrow
}
```

### DataQuality Enum

Indicates the quality/reliability of a glucose reading.

```swift
enum DataQuality: Int, CustomStringConvertible {
    case OK = 0
    case SD14_FIFO_OVERFLOW = 1
    case FILTER_DELTA = 2
    case WORK_VOLTAGE = 4
    case PEAK_DELTA_EXCEEDED = 8
    case AVG_DELTA_EXCEEDED = 16
    case RF = 32
    case REF_R = 64
    case SIGNAL_SATURATED = 128
    case SENSOR_SIGNAL_LOW = 256
    case THERMISTOR_OUT_OF_RANGE = 2048
    case TEMP_HIGH = 8192
    case TEMP_LOW = 16384
    case INVALID_DATA = 32768
}
```

### TrendArrow Enum

Direction and rate of glucose change.

```swift
enum TrendArrow: Int, CustomStringConvertible, CaseIterable {
    case unknown       = -1
    case notDetermined = 0
    case fallingQuickly = 1   // ↓↓ (> -2 mg/dL/min)
    case falling       = 2    // ↓  (-1 to -2 mg/dL/min)
    case stable        = 3    // → (-1 to +1 mg/dL/min)
    case rising        = 4    // ↑  (+1 to +2 mg/dL/min)
    case risingQuickly = 5    // ↑↑ (> +2 mg/dL/min)
    
    var symbol: String {
        switch self {
        case .fallingQuickly: "↓↓"
        case .falling:        "↓"
        case .stable:         "→"
        case .rising:         "↑"
        case .risingQuickly:  "↑↑"
        default:              "?"
        }
    }
}
```

### History Structure

Container for glucose history with current and trend data.

```swift
struct History {
    var values: [Glucose]          // All historical readings
    var factoryValues: [Glucose]   // Factory-calibrated readings
    var rawValues: [Glucose]       // Raw uncalibrated readings
    var factoryTrend: [Glucose]    // Last 16 readings (1-min intervals)
    var rawTrend: [Glucose]        // Raw trend data
    var calibratedValues: [Glucose] // User-calibrated readings
    var calibratedTrend: [Glucose]
    var storedValues: [Glucose]    // Persisted readings
    var nightscoutValues: [Glucose] // Downloaded from NS
}
```

### Calibration Structure

Linear calibration parameters for converting raw to calibrated values.

```swift
struct Calibration: Codable {
    var slope: Double = 1.0
    var intercept: Double = 0.0
    
    func calibrate(_ value: Double) -> Double {
        return slope * value + intercept
    }
}
```

---

## Sensor Model

### Sensor Class

Represents a CGM sensor with its metadata and state.

**File**: `Sensor.swift` (151 lines)

```swift
class Sensor: ObservableObject, Codable {
    // Identification
    var uid: Data                    // 8-byte NFC UID
    var patchInfo: Data              // Sensor patch info bytes
    var serial: String               // Human-readable serial (e.g., "0M00000XXXX")
    
    // Type information
    var type: SensorType             // Libre 1, Libre 2, etc.
    var family: SensorFamily         // Abbott, Dexcom
    var region: SensorRegion         // US, EU, etc.
    
    // Lifecycle
    var state: SensorState           // .notYetStarted, .starting, .ready, .expired, .shutdown, .failure
    var age: Int                     // Minutes since activation
    var maxLife: Int                 // Maximum sensor life in minutes
    var lifetime: Int                // Remaining lifetime
    
    // Firmware
    var firmware: String
    var securityGeneration: Int      // 0=Gen1, 1=Gen2 (for Libre 2)
    
    // FRAM Data
    var fram: Data                   // Raw FRAM bytes (344 bytes typical)
    var encryptedFram: Data          // Encrypted FRAM (Libre 2/3)
    var trend: [Glucose]             // Last 16 minutes of readings
    var history: [Glucose]           // Last 8 hours of readings (every 15 min)
    
    // Streaming (Libre 2/3)
    var streamingUnlockCode: UInt32
    var streamingUnlockCount: UInt16
    var lastReadingDate: Date
}
```

### SensorType Enum

All supported sensor models.

```swift
enum SensorType: String, CaseIterable, Codable {
    case none          = "none"
    case libre1        = "Libre 1"
    case libreUS14day  = "Libre US 14-day"
    case libreProH     = "Libre Pro/H"
    case libre2        = "Libre 2"
    case libre2US      = "Libre 2 US"
    case libre2CA      = "Libre 2 CA"
    case libre3        = "Libre 3"
    case libreSelect   = "Libre Select"
    case libreX        = "Libre X"
    case lingo         = "Lingo"
    case dexcomG5      = "Dexcom G5"
    case dexcomG6      = "Dexcom G6"
    case dexcomONE     = "Dexcom ONE"
    case dexcomG7      = "Dexcom G7"
    case dexcomONEPlus = "Dexcom ONE+"
    case stelo         = "Stelo"
}
```

### SensorFamily Enum

```swift
enum SensorFamily: String, CaseIterable, Codable {
    case none    = "none"
    case libre   = "Libre"
    case dexcom  = "Dexcom"
}
```

### SensorState Enum

```swift
enum SensorState: UInt8, CustomStringConvertible {
    case unknown        = 0x00
    case notYetStarted  = 0x01  // Sensor not activated
    case starting       = 0x02  // Warmup period
    case ready          = 0x03  // Normal operation
    case expired        = 0x04  // Past max lifetime
    case shutdown       = 0x05  // Manually stopped
    case failure        = 0x06  // Sensor malfunction
    
    var description: String {
        switch self {
        case .notYetStarted: "Not yet started"
        case .starting:      "Starting (warmup)"
        case .ready:         "Ready"
        case .expired:       "Expired"
        case .shutdown:      "Shutdown"
        case .failure:       "Failure"
        default:             "Unknown"
        }
    }
}
```

### SensorRegion Enum

```swift
enum SensorRegion: Int, CaseIterable, Codable {
    case unknown        = 0
    case european       = 1
    case usa            = 2
    case australian     = 4
    case easternROW     = 8
    case japan          = 9
}
```

---

## Device Model

### Device Base Class

Abstract base class for all BLE devices (sensors and bridges).

**File**: `Device.swift` (183 lines)

```swift
class Device: ObservableObject, Identifiable {
    // CoreBluetooth references
    var peripheral: CBPeripheral?
    var characteristics: [CBUUID: CBCharacteristic] = [:]
    
    // Device info
    var type: DeviceType
    var name: String
    var serial: String
    var firmware: String
    var hardware: String
    var manufacturer: String
    var macAddress: Data
    var rssi: Int                    // Signal strength
    var battery: Int                 // Battery percentage
    
    // Connection state
    var state: CBPeripheralState
    var lastConnectionDate: Date?
    
    // Abstract methods (overridden by subclasses)
    func readValue(for characteristic: CBCharacteristic) { }
    func writeValue(_ data: Data, for characteristic: CBCharacteristic) { }
}
```

### DeviceType Enum

```swift
enum DeviceType: String, CaseIterable, Codable {
    case none         = "none"
    // Transmitters (attached to sensors)
    case transmitter  = "Transmitter"
    case libre3       = "Libre 3"
    case dexcom       = "Dexcom"
    case dexcomG7     = "Dexcom G7"
    // Bridge devices
    case miaomiao     = "MiaoMiao"
    case bubble       = "Bubble"
    case blucon       = "BluCon"
    
    static var allBridges: [DeviceType] {
        [.miaomiao, .bubble, .blucon]
    }
}
```

### Transmitter Class

Represents a transmitter attached to a sensor.

```swift
class Transmitter: Device {
    var sensor: Sensor?              // Associated sensor
    var streamingEnabled: Bool       // BLE streaming active
    
    // BLE service/characteristic UUIDs (device-specific)
    static var dataServiceUUID: String
    static var dataReadCharacteristicUUID: String
    static var dataWriteCharacteristicUUID: String
}
```

### Device Subclass Hierarchy

```
Device (base)
├── Transmitter (sensor transmitters)
│   ├── Libre3 (Abbott Libre 3)
│   ├── Dexcom (G5/G6/ONE)
│   └── DexcomG7 (G7/ONE+/Stelo)
└── Bridge (third-party readers)
    ├── MiaoMiao
    ├── Bubble
    └── BluCon
```

---

## Application State

### AppState Class

The central observable state container for the app.

**File**: `App.swift` (301 lines)

```swift
@Observable
class AppState {
    // Delegates
    var app: MainDelegate!
    
    // Connected hardware
    var device: Device?              // Current connected device
    var sensor: Sensor?              // Current sensor
    var transmitter: Transmitter?    // Current transmitter
    
    // Current readings
    var currentGlucose: Int = 0      // Latest glucose mg/dL
    var lastReadingDate: Date = Date.distantPast
    var trendArrow: TrendArrow = .unknown
    var trendDelta: Int = 0
    
    // History
    var history: History = History()
    var calibration: Calibration = Calibration()
    
    // Status
    var status: String = "Welcome"
    var deviceState: String = ""
    var lastConnectionDate: Date?
    
    // Settings reference
    var settings: Settings
    
    // Debug
    var log: String = ""
}
```

### MainDelegate Class

Core coordinator handling NFC, BLE, and data processing.

**File**: `MainDelegate.swift` (492 lines)

```swift
class MainDelegate: NSObject, WKApplicationDelegate, 
                    CBCentralManagerDelegate, CBPeripheralDelegate {
    // Hardware interfaces
    var centralManager: CBCentralManager!
    var nfc: NFC?
    
    // Integrations
    var healthKit: HealthKit?
    var nightscout: Nightscout?
    
    // Device management
    var knownDevices: [Device] = []
    
    // Key methods
    func scan()                              // Start BLE scanning
    func connect(_ device: Device)           // Connect to device
    func disconnect()                        // Disconnect current device
    func read(_ sensor: Sensor)              // NFC read sensor
    func parseSensorData(_ data: Data)       // Decode sensor FRAM
    func didParseSensor(_ sensor: Sensor)    // Process readings, upload
}
```

### Settings Class

User preferences and persistent configuration.

**File**: `Settings.swift` (339 lines)

```swift
class Settings: ObservableObject, Codable {
    // Units
    var displayingMillimoles: Bool = false   // mmol/L vs mg/dL
    
    // Thresholds
    var targetLow: Int = 70
    var targetHigh: Int = 180
    var alarmLow: Int = 55
    var alarmHigh: Int = 250
    
    // Nightscout
    var nightscoutSite: String = ""
    var nightscoutToken: String = ""
    
    // Calibration
    var calibrating: Bool = false
    var usingOOP: Bool = true                // Use LibreOOP
    
    // Device preferences
    var preferredDevicePattern: String = ""
    var preferredTransmitterSerial: String = ""
    
    // Reading intervals
    var readingInterval: Int = 5             // Minutes
    var mutedAudio: Bool = false
}
```

---

## Data Flow Diagram

### From Sensor to Display

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Sensor → Display Data Flow                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌───────────────┐
│  CGM Sensor   │
│  (Hardware)   │
└───────┬───────┘
        │
        │ NFC Read (Libre 1/2/3)    BLE Stream (Libre 2/3, Dexcom)
        │ or                        or
        │ Bridge Read (MiaoMiao)    Direct BLE (Dexcom G6/G7)
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                           Raw Data Reception                               │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│  │   NFC.swift     │    │ BluetoothDel.   │    │  Bridge.swift   │        │
│  │  (CoreNFC)      │    │ (CoreBluetooth) │    │ (MiaoMiao, etc) │        │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘        │
│           │                      │                      │                  │
│           └──────────────────────┴──────────────────────┘                  │
│                                  │                                         │
│                                  ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐│
│  │                    Sensor.fram (Raw bytes: 344 bytes)                  ││
│  │  ┌──────────┬──────────┬──────────┬──────────┬──────────────────────┐ ││
│  │  │ Header   │ Trend    │ History  │ Footer   │ Libre 2/3: Encrypted │ ││
│  │  │ 24 bytes │ 96 bytes │ 192 bytes│ 32 bytes │ (requires decryption)│ ││
│  │  └──────────┴──────────┴──────────┴──────────┴──────────────────────┘ ││
│  └───────────────────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                            Decryption Layer                                │
│  (For Libre 2/3 encrypted sensors)                                        │
│                                                                            │
│  Libre2.processCrypto(data:uid:patchInfo:)                                │
│  └── Uses AES encryption with usefulFunction() for key derivation         │
│                                                                            │
│  Libre3.decrypt(data:)                                                     │
│  └── Uses AES-CCM mode with sensor-specific keys                          │
└───────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                           Parsing Layer                                    │
│                                                                            │
│  Libre.parseFRAM()           Dexcom.parse()           Bridge.parse()      │
│  ├── Extract header          ├── Parse opcode         ├── Extract FRAM    │
│  ├── Parse trend buffer      ├── Extract glucose      ├── Forward to      │
│  ├── Parse history buffer    ├── Extract trend        │   Libre parser    │
│  └── Validate checksums      └── Extract status       └──────────────────  │
│                                                                            │
│  Output: [Glucose] array with raw values, temperatures, quality flags      │
└───────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                          Calibration Layer                                 │
│                                                                            │
│  Option A: Factory Calibration (from sensor FRAM)                          │
│  └── Uses i1, i2, i3, i4, i5, i6 parameters from patch info               │
│                                                                            │
│  Option B: LibreOOP (Online Processing)                                    │
│  └── Sends raw data to remote server for calibration                       │
│                                                                            │
│  Option C: User Calibration                                                │
│  └── Linear calibration: value = slope * rawValue + intercept             │
│                                                                            │
│  Output: Calibrated glucose values in mg/dL                                │
└───────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                          Storage & Display                                 │
│                                                                            │
│  AppState.history.values       AppState.currentGlucose                    │
│  └── Historical array          └── Latest reading                          │
│                                                                            │
│  HealthKit.save()              Nightscout.post()                          │
│  └── Apple Health              └── Remote sync                             │
│                                                                            │
│  Monitor.swift (UI)                                                        │
│  └── Graph + Current Value + Trend Arrow                                   │
└───────────────────────────────────────────────────────────────────────────┘
```

### FRAM Memory Layout (Libre 1/2)

```
Offset   Size   Content
──────────────────────────────────────────────────
0x00     24     Header (sensor state, age, calibration params)
0x18     96     Trend buffer (16 readings × 6 bytes each)
0x78     192    History buffer (32 readings × 6 bytes each)
0x138    32     Footer (manufacturing data)
──────────────────────────────────────────────────
Total:   344 bytes

Each 6-byte glucose reading:
  Bytes 0-1: Raw glucose value (little-endian)
  Bytes 2-3: Quality flags
  Bytes 4-5: Temperature
```

---

## Related Documentation

- [cgm-transmitters.md](cgm-transmitters.md) - Device-specific parsing and communication
- [nightscout-sync.md](nightscout-sync.md) - How glucose data is uploaded to Nightscout
