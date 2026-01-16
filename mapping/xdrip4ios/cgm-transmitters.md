# xDrip4iOS CGM Transmitters

This document provides an overview of how xDrip4iOS connects to CGM transmitters via Bluetooth and transforms raw sensor data into Nightscout-compatible glucose readings.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CGM TRANSMITTER ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        BluetoothTransmitter                            │  │
│  │                     (Base class for all BLE devices)                   │  │
│  │                                                                        │  │
│  │  Responsibilities:                                                     │  │
│  │  - CBCentralManager lifecycle                                          │  │
│  │  - Device scanning and connection                                      │  │
│  │  - Service/characteristic discovery                                    │  │
│  │  - Notification subscription                                           │  │
│  │  - Read/write operations                                               │  │
│  │  - State restoration                                                   │  │
│  │  - Auto-reconnection                                                   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              ▲                                               │
│                              │ extends                                       │
│  ┌───────────────────────────┴───────────────────────────────────────────┐  │
│  │                          CGM Transmitter Classes                       │  │
│  │                                                                        │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │ CGMG5       │  │ CGMG7       │  │ CGMLibre2   │  │ CGMMiaoMiao │  │  │
│  │  │ Transmitter │  │ Transmitter │  │ Transmitter │  │ Transmitter │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │ CGMBubble   │  │ CGMBlucon   │  │ CGMAtom     │  │ CGMDroplet1 │  │  │
│  │  │ Transmitter │  │ Transmitter │  │ Transmitter │  │ Transmitter │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              │                                               │
│                              │ implements                                    │
│                              ▼                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         CGMTransmitter Protocol                        │  │
│  │                                                                        │  │
│  │  - cgmTransmitterType()                                                │  │
│  │  - setWebOOPEnabled(enabled:)                                          │  │
│  │  - isWebOOPEnabled()                                                   │  │
│  │  - startSensor(sensorCode:, startDate:)                                │  │
│  │  - stopSensor(stopDate:)                                               │  │
│  │  - calibrate(calibration:)                                             │  │
│  │  - maxSensorAgeInDays()                                                │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              │                                               │
│                              │ calls delegate                                │
│                              ▼                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     CGMTransmitterDelegate Protocol                    │  │
│  │                                                                        │  │
│  │  - cgmTransmitterInfoReceived(glucoseData:, transmitterBatteryInfo:,  │  │
│  │                                sensorAge:)                             │  │
│  │  - newSensorDetected(sensorStartDate:)                                 │  │
│  │  - sensorNotDetected()                                                 │  │
│  │  - sensorStopDetected()                                                │  │
│  │  - errorOccurred(xDripError:)                                          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Source Files

| Directory | Purpose |
|-----------|---------|
| `BluetoothTransmitter/Generic/` | Base BluetoothTransmitter class |
| `BluetoothTransmitter/CGM/Generic/` | CGMTransmitter protocol and delegate |
| `BluetoothTransmitter/CGM/Dexcom/` | Dexcom G4, G5, G6, G7 implementations |
| `BluetoothTransmitter/CGM/Libre/` | Libre, MiaoMiao, Bubble, etc. |

---

## CGMTransmitter Protocol

Defines the interface that all CGM transmitter classes must implement:

```swift
// xdrip:xdrip/BluetoothTransmitter/CGM/Generic/CGMTransmitter.swift#L5-L80
protocol CGMTransmitter: AnyObject {
    
    /// Get the transmitter type
    func cgmTransmitterType() -> CGMTransmitterType
    
    /// Enable/disable web OOP (Out of Process) calibration
    func setWebOOPEnabled(enabled: Bool)
    func isWebOOPEnabled() -> Bool
    
    /// Sensor start/stop commands (Dexcom)
    func startSensor(sensorCode: String?, startDate: Date)
    func stopSensor(stopDate: Date)
    
    /// Send calibration to transmitter (Dexcom)
    func calibrate(calibration: Calibration)
    
    /// Maximum sensor age in days
    func maxSensorAgeInDays() -> Double?
    
    /// Request new reading (Libre)
    func requestNewReading()
    
    /// BLE service/characteristic UUIDs
    func getCBUUID_Service() -> String
    func getCBUUID_Receive() -> String
}
```

---

## CGMTransmitterType Enum

```swift
// xdrip:xdrip/BluetoothTransmitter/CGM/Generic/CGMTransmitter.swift#L83-L119
enum CGMTransmitterType: String, CaseIterable {
    case dexcomG4 = "Dexcom G4"
    case dexcom = "Dexcom G5/G6/ONE"
    case dexcomG7 = "Dexcom G7/ONE+/Stelo"
    case miaomiao = "MiaoMiao"
    case GNSentry = "GNSentry"
    case Blucon = "Blucon"
    case Bubble = "Bubble"
    case Droplet1 = "Droplet-1"
    case blueReader = "BlueReader"
    case Atom = "Atom"
    case watlaa = "Watlaa"
    case Libre2 = "Libre2"
}
```

### Sensor Type Mapping

```swift
// xdrip:xdrip/BluetoothTransmitter/CGM/Generic/CGMTransmitter.swift#L122-L133
func sensorType() -> CGMSensorType {
    switch self {
    case .dexcomG4, .dexcom, .dexcomG7:
        return .Dexcom
        
    case .miaomiao, .Bubble, .GNSentry, .Droplet1, 
         .blueReader, .watlaa, .Blucon, .Libre2, .Atom:
        return .Libre
    }
}
```

---

## CGMTransmitterDelegate Protocol

Callback interface for receiving glucose data:

```swift
// xdrip:xdrip/BluetoothTransmitter/CGM/Generic/CGMTransmitterDelegate.swift
protocol CGMTransmitterDelegate: AnyObject {
    
    /// New sensor detected (for transmitters that can detect this)
    func newSensorDetected(sensorStartDate: Date?)
    
    /// Sensor stopped (expired, removed)
    func sensorStopDetected()
    
    /// Sensor not detected
    func sensorNotDetected()
    
    /// Glucose data received from transmitter
    /// - Parameters:
    ///   - glucoseData: Array of GlucoseData (newest first)
    ///   - transmitterBatteryInfo: Battery level info
    ///   - sensorAge: Sensor age in seconds (if available)
    func cgmTransmitterInfoReceived(
        glucoseData: inout [GlucoseData], 
        transmitterBatteryInfo: TransmitterBatteryInfo?, 
        sensorAge: TimeInterval?
    )
    
    /// Error occurred during communication
    func errorOccurred(xDripError: XdripError)
}
```

---

## Transmitter Capabilities

| Transmitter | Sensor Detection | Manual Start | WebOOP | Battery Type |
|-------------|-----------------|--------------|--------|--------------|
| Dexcom G4 | No | Yes | No | - |
| Dexcom G5/G6 | Yes | Yes | Yes* | Voltage |
| Dexcom G7 | Yes | No | Yes | - |
| MiaoMiao | Yes | Yes | Yes | % |
| Bubble | Yes | Yes | Yes | % |
| Blucon | Yes | Yes | Yes | % |
| Libre 2 | Yes | Yes | Yes | % |
| Atom | Yes | Yes | Yes | % |
| GNSentry | No | Yes | No | - |
| Droplet-1 | No | Yes | No | % |
| BlueReader | No | Yes | No | % |
| Watlaa | No | Yes | No | % |

*WebOOP = Calibrated data from transmitter algorithm

---

## Dexcom Transmitter Identification

xDrip4iOS identifies Dexcom transmitter type by ID prefix:

```swift
// xdrip:xdrip/BluetoothTransmitter/CGM/Generic/CGMTransmitter.swift#L291-L327
func detailedDescription() -> String {
    switch self {
    case .dexcom:
        if let transmitterId = UserDefaults.standard.activeSensorTransmitterId {
            if transmitterId.startsWith("4") {
                return "Dexcom G5"
            } else if transmitterId.startsWith("8") {
                return "Dexcom G6"
            } else if transmitterId.startsWith("5") || transmitterId.startsWith("C") {
                return "Dexcom ONE"
            }
        }
        return "Dexcom"
        
    case .dexcomG7:
        if let transmitterId = UserDefaults.standard.activeSensorTransmitterId {
            if transmitterId.startsWith("DX01") {
                return "Dexcom Stelo"
            } else if transmitterId.startsWith("DX02") {
                return "Dexcom ONE+"
            }
        }
        return "Dexcom G7"
        
    case .Libre2:
        if let maxAge = UserDefaults.standard.activeSensorMaxSensorAgeInDays, 
           maxAge >= 15 {
            return "Libre 2 Plus EU"
        }
        return "Libre 2 EU"
    
    default:
        return self.rawValue
    }
}
```

### Dexcom ID Prefixes

| Prefix | Model |
|--------|-------|
| `4XXXXX` | Dexcom G5 |
| `8XXXXX` | Dexcom G6 |
| `5XXXXX` | Dexcom ONE |
| `CXXXXX` | Dexcom ONE |
| `DX01XX` | Dexcom Stelo |
| `DX02XX` | Dexcom ONE+ |
| (other) | Dexcom G7 |

---

## GlucoseData Structure

Raw glucose data from transmitters:

```swift
// xdrip:xdrip/BluetoothTransmitter/CGM/Generic/GlucoseData.swift
class GlucoseData {
    var timeStamp: Date
    var glucoseLevelRaw: Double      // Raw sensor value
    var glucoseLevelFiltered: Double // Filtered value (if available)
}
```

---

## Data Flow: Transmitter to Nightscout

```
┌──────────────────┐
│ CGM Transmitter  │
│ (Hardware)       │
└────────┬─────────┘
         │ Bluetooth LE
         ▼
┌──────────────────┐
│ BluetoothTransmitter │
│ (BLE connection)     │
└────────┬─────────┘
         │ Raw data packets
         ▼
┌──────────────────┐
│ Device-Specific  │
│ Transmitter Class│
│ (e.g., CGMG6)    │
└────────┬─────────┘
         │ GlucoseData[]
         ▼
┌──────────────────┐
│ CGMTransmitter   │
│ Delegate         │
│ (RootViewController)
└────────┬─────────┘
         │ Creates BgReading
         ▼
┌──────────────────┐
│ BgReading        │
│ (CoreData)       │
└────────┬─────────┘
         │ dictionaryRepresentationForNightscoutUpload()
         ▼
┌──────────────────┐
│ NightscoutSync   │
│ Manager          │
│ POST /entries    │
└──────────────────┘
```

---

## Libre Sensor Data Parsing

Libre sensors use a 344-byte data format parsed by utilities:

```
xdrip/BluetoothTransmitter/CGM/Libre/Utilities/
├── LibreDataParser.swift     # Main parser
├── LibreNFC.swift            # NFC reading for Libre 2
└── ...
```

### Parser Flow

1. Receive raw 344-byte packet from bridge (MiaoMiao, Bubble, etc.)
2. Extract sensor information (serial, type, age)
3. Parse glucose readings from trend and history blocks
4. Apply calibration (web OOP or local)
5. Return GlucoseData array

---

## Battery Information

Different transmitters report battery differently:

```swift
// xdrip:xdrip/BluetoothTransmitter/CGM/Generic/TransmitterBatteryInfo.swift
struct TransmitterBatteryInfo {
    // Returns (key, value) tuple for NS upload
    var batteryLevel: (key: String, value: Int)
}
```

| Transmitter | Key | Value Type |
|-------------|-----|------------|
| Dexcom G5/G6 | `batteryVoltage` | Voltage (e.g., 298) |
| MiaoMiao | `battery` | Percentage (0-100) |
| Bubble | `battery` | Percentage (0-100) |
| Libre 2 | `battery` | Percentage (0-100) |

---

## Sensor Auto-Detection

Transmitters that support automatic sensor detection:

```swift
// xdrip:xdrip/BluetoothTransmitter/CGM/Generic/CGMTransmitter.swift#L141-L180
func canDetectNewSensor() -> Bool {
    switch self {
    case .dexcomG4, .GNSentry, .Droplet1, .blueReader, .watlaa:
        return false
        
    case .dexcom, .dexcomG7, .miaomiao, .Bubble, .Blucon, .Libre2, .Atom:
        return true
    }
}
```

When a new sensor is detected, `newSensorDetected(sensorStartDate:)` is called on the delegate.

---

## Calibration Support

### Dexcom Native Mode

Dexcom G6 (Firefly) transmitters use internal calibration:

```swift
func calibrate(calibration: Calibration) {
    // Send calibration command to transmitter
}
```

### Libre with Web OOP

Libre sensors can use out-of-process calibration:

```swift
func setWebOOPEnabled(enabled: Bool)
func isWebOOPEnabled() -> Bool
```

When WebOOP is enabled, glucose values come pre-calibrated from the algorithm.

---

## NS Relevance

CGM transmitter data flows to Nightscout via:

1. **BgReading creation** from GlucoseData
2. **Upload** via `BgReading.dictionaryRepresentationForNightscoutUpload()`
3. **Entries API** POST to `/api/v1/entries`

Key fields populated:
- `sgv`: Calculated glucose value
- `direction`: Trend arrow from slope
- `device`: Transmitter name
- `date`: Timestamp
- `filtered`/`unfiltered`: Raw values

---

## Code References

| Purpose | File |
|---------|------|
| CGMTransmitter protocol | `CGM/Generic/CGMTransmitter.swift` |
| CGMTransmitterDelegate | `CGM/Generic/CGMTransmitterDelegate.swift` |
| CGMTransmitterType enum | `CGM/Generic/CGMTransmitter.swift#L83-L343` |
| BluetoothTransmitter base | `Generic/BluetoothTransmitter.swift` |
| GlucoseData model | `CGM/Generic/GlucoseData.swift` |
| TransmitterBatteryInfo | `CGM/Generic/TransmitterBatteryInfo.swift` |
| Libre parsers | `CGM/Libre/Utilities/` |
| Dexcom implementations | `CGM/Dexcom/` |
