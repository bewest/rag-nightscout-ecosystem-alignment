# xDrip4iOS Behavior Documentation

This directory contains documentation extracted from xDrip4iOS (xdripswift), a native iOS application for continuous glucose monitoring. This provides a **dual perspective** on the Nightscout data model—as both a data producer (uploading CGM readings) and a data consumer (follower mode).

## Source Repository

- **Repository**: [JohanDegraeve/xdripswift](https://github.com/JohanDegraeve/xdripswift)
- **Language**: Swift (native iOS)
- **License**: GPL-3.0
- **Analysis Date**: 2026-01-16
- **Version Analyzed**: 6.2.2 (December 2025)

## Purpose & Value

While cgm-remote-monitor defines the authoritative data model, xDrip4iOS reveals:

1. **Native iOS integration patterns** - How a mobile CGM app uploads data to Nightscout
2. **Bi-directional sync logic** - Upload and download treatment synchronization
3. **Follower mode implementation** - Consuming Nightscout data as a follower
4. **Treatment type mapping** - How xDrip4iOS maps local treatment types to NS eventTypes
5. **Profile consumption** - Parsing and using Nightscout profile data
6. **Multi-source follower architecture** - Nightscout, LibreLinkUp, DexcomShare follower modes
7. **CGM transmitter abstraction** - How raw sensor data becomes Nightscout entries

## Documentation Index

| Document | Description |
|----------|-------------|
| [data-models.md](data-models.md) | BgReading, TreatmentEntry, Calibration mappings to NS collections |
| [nightscout-sync.md](nightscout-sync.md) | Upload/download logic, API paths, sync timing |
| [treatment-classification.md](treatment-classification.md) | TreatmentType enum, eventType mapping, ID extensions |
| [follower-modes.md](follower-modes.md) | Nightscout, LibreLinkUp, DexcomShare follower patterns |
| [profile-handling.md](profile-handling.md) | NightscoutProfile parsing and timezone handling |
| [cgm-transmitters.md](cgm-transmitters.md) | BluetoothTransmitter architecture for CGM devices |

## Key Source Files

| File | Purpose | Lines |
|------|---------|-------|
| `xdrip/Managers/Nightscout/NightscoutSyncManager.swift` | Core NS sync logic | ~1692 |
| `xdrip/Managers/Nightscout/NightscoutFollowManager.swift` | Nightscout follower mode | ~471 |
| `xdrip/Managers/Nightscout/NightscoutProfileModels.swift` | Profile data models | ~119 |
| `xdrip/Managers/Nightscout/BgReading+Nightscout.swift` | BG upload format | ~25 |
| `xdrip/Managers/Nightscout/Calibration+Nightscout.swift` | Calibration upload format | ~47 |
| `xdrip/Treatments/TreatmentNSResponse.swift` | Treatment download parsing | ~186 |
| `xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift` | Treatment model & upload | ~215 |
| `xdrip/Managers/LibreLinkUp/LibreLinkUpFollowManager.swift` | LibreLinkUp follower | ~47KB |
| `xdrip/Managers/Followers/FollowerDataSourceType.swift` | Follower source enum | ~169 |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        xDrip4iOS Data Architecture                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         MASTER MODE                                      ││
│  │  (Direct Bluetooth connection to CGM transmitter)                        ││
│  │                                                                          ││
│  │  CGM Transmitter (Dexcom G6/G7, Libre 2, MiaoMiao, Bubble, etc.)        ││
│  │         │                                                                ││
│  │         ▼                                                                ││
│  │  ┌─────────────────────┐                                                ││
│  │  │ BluetoothTransmitter │  (Base class for BLE communication)           ││
│  │  │ ├── CGMTransmitter   │  (CGM-specific protocol)                      ││
│  │  │ │   ├── CGMG5/G6     │                                               ││
│  │  │ │   ├── CGMLibre2    │                                               ││
│  │  │ │   ├── CGMMiaoMiao  │                                               ││
│  │  │ │   └── CGMBubble    │                                               ││
│  │  └─────────────────────┘                                                ││
│  │         │                                                                ││
│  │         ▼ CGMTransmitterDelegate.cgmTransmitterInfoReceived()           ││
│  │  ┌─────────────────────┐                                                ││
│  │  │ BgReading (CoreData)│  Local storage of glucose readings             ││
│  │  └─────────────────────┘                                                ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        FOLLOWER MODE                                     ││
│  │  (Remote data download from cloud sources)                               ││
│  │                                                                          ││
│  │  FollowerDataSourceType:                                                 ││
│  │  ├── .nightscout      → NightscoutFollowManager                         ││
│  │  ├── .libreLinkUp     → LibreLinkUpFollowManager                        ││
│  │  ├── .libreLinkUpRussia → LibreLinkUpFollowManager (RU region)          ││
│  │  └── .dexcomShare     → DexcomShareFollowManager                        ││
│  │         │                                                                ││
│  │         ▼ FollowerDelegate.followerInfoReceived()                       ││
│  │  ┌─────────────────────┐                                                ││
│  │  │ BgReading (CoreData)│  Local storage of glucose readings             ││
│  │  └─────────────────────┘                                                ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                      NIGHTSCOUT INTEGRATION                              ││
│  │                                                                          ││
│  │  NightscoutSyncManager                                                   ││
│  │  ├── uploadBgReadingsToNightscout()    → POST /api/v1/entries           ││
│  │  ├── uploadCalibrationsToNightscout()  → POST /api/v1/entries           ││
│  │  ├── uploadActiveSensorToNightscout()  → POST /api/v1/treatments        ││
│  │  ├── uploadTreatmentsToNightscout()    → POST /api/v1/treatments        ││
│  │  ├── updateTreatmentToNightscout()     → PUT  /api/v1/treatments        ││
│  │  ├── deleteTreatmentAtNightscout()     → DELETE /api/v1/treatments      ││
│  │  ├── getLatestTreatmentsNSResponses()  → GET  /api/v1/treatments        ││
│  │  ├── downloadProfile()                 → GET  /api/v1/profile           ││
│  │  └── downloadDeviceStatus()            → GET  /api/v1/devicestatus      ││
│  │                                                                          ││
│  │  NightscoutFollowManager (when FollowerDataSourceType == .nightscout)   ││
│  │  └── download()                        → GET  /api/v1/entries/sgv.json  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                       LOCAL INTEGRATIONS                                 ││
│  │                                                                          ││
│  │  ├── HealthKit         → Store glucose readings in Apple Health         ││
│  │  ├── Apple Watch       → Watch app + complications                      ││
│  │  ├── Widgets           → iOS home/lock screen widgets                   ││
│  │  ├── Calendar          → Events for Watch face complications            ││
│  │  ├── Speak             → Voice announcements of readings                ││
│  │  └── Loop Integration  → CGM client for DIY closed-loop systems         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## API Paths Used

| Path | Method(s) | Purpose |
|------|-----------|---------|
| `/api/v1/entries` | POST | Upload BG readings, calibrations |
| `/api/v1/entries/sgv.json` | GET | Download BG readings (follower mode) |
| `/api/v1/treatments` | GET, POST, PUT, DELETE | Bi-directional treatment sync |
| `/api/v1/profile` | GET | Download profile data |
| `/api/v1/devicestatus` | GET, POST | Download/upload device status |
| `/api/v1/experiments/test` | GET | Test API authentication |

## Uploader Identification

xDrip4iOS identifies itself via `enteredBy` field:

```swift
"enteredBy": ConstantsHomeView.applicationName  // "xDrip4iOS"
```

When parsing downloaded treatments, xDrip4iOS preserves the original `enteredBy` value to maintain provenance.

## Nightscout Follow Types

For AID (Automated Insulin Delivery) system users, xDrip4iOS supports specialized follower modes:

| NightscoutFollowType | Description | Data Pulled |
|---------------------|-------------|-------------|
| `.none` | Basic follower | BG readings only |
| `.loop` | Loop/FreeAPS follower | BG + Loop devicestatus |
| `.openAPS` | OpenAPS/AAPS follower | BG + OpenAPS devicestatus |

## Treatment Type Mapping

| TreatmentType (Swift) | NS eventType | NS Field |
|-----------------------|--------------|----------|
| `.Insulin` | "Bolus" | `insulin` |
| `.Carbs` | "Carbs" | `carbs` |
| `.Exercise` | "Exercise" | `duration` |
| `.BgCheck` | "BG Check" | `glucose`, `glucoseType`, `units` |
| `.Basal` | "Temp Basal" | `rate`, `duration` |
| `.SiteChange` | "Site Change" | (none) |
| `.SensorStart` | "Sensor Start" | (none) |
| `.PumpBatteryChange` | "Pump Battery Change" | (none) |

## Key Implementation Patterns

### Treatment ID Extensions

xDrip4iOS appends type-specific suffixes to NS `_id` values to handle compound treatments:

```swift
id + "-insulin"  // For insulin portion
id + "-carbs"    // For carbs portion
id + "-exercise" // For exercise portion
```

This allows a single NS treatment (e.g., "Snack Bolus" with both insulin and carbs) to become multiple local TreatmentEntry objects.

### Date Format Handling

xDrip4iOS handles two date formats in `created_at`:

```swift
// Loop, FreeAPS, OpenAPS (with milliseconds)
"yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"

// AndroidAPS (without milliseconds)
"yyyy-MM-dd'T'HH:mm:ss'Z'"
```

Detection is based on presence of `.` in the date string.

### Unit Conversion

BgCheck treatments store values in mg/dL but include unit info:

```swift
dict["glucose"] = self.value  // Always mg/dL
dict["units"] = "mg/dl"       // ConstantsNightscout.mgDlNightscoutUnitString
dict["glucoseType"] = "Finger" + mmol_annotation  // Includes mmol if user preference
```

### Authentication

Supports both API_SECRET and token authentication:

```swift
// API_SECRET (hashed)
request.setValue(apiKey.sha1(), forHTTPHeaderField: "api-secret")

// Token (query parameter)
URLQueryItem(name: "token", value: token)
```

## Cross-References

- [Nightscout Data Model](../../docs/10-domain/nightscout-data-model.md) - Authoritative NS schema
- [mapping/nightscout-reporter/](../nightscout-reporter/) - Consumer perspective (Dart web app)
- [mapping/aaps/nightscout-sync.md](../aaps/nightscout-sync.md) - AAPS NS sync patterns
- [mapping/loop/nightscout-sync.md](../loop/nightscout-sync.md) - Loop NS upload patterns

## Comparison: xDrip4iOS vs Other Ecosystem Apps

| Aspect | xDrip4iOS | Nightscout Reporter | AndroidAPS |
|--------|-----------|---------------------|------------|
| **Role** | Producer + Consumer | Consumer only | Producer + Consumer |
| **Platform** | iOS (Swift) | Web (Dart) | Android (Kotlin) |
| **CGM Connection** | Direct Bluetooth | None | Direct Bluetooth |
| **Treatment Sync** | Bi-directional | Read-only | Bi-directional |
| **Profile Sync** | Download only | Download only | Bi-directional |
| **Follower Sources** | NS, LibreLinkUp, DexcomShare | NS only | NS only |

---

## Code Citation Format

Throughout this documentation, code references use the format:
```
xdrip4ios:xdripswift/Sources/File.swift#L123-L456
```

This maps to files in `externals/xdripswift/`.

---

## Limitations / Out of Scope

This documentation does not cover:

- **Devicestatus payload schema**: While xDrip4iOS uploads battery/uploader info to `/api/v1/devicestatus`, the full payload structure is not documented here
- **Loop/OpenAPS devicestatus parsing**: The detailed parsing of AID devicestatus payloads when in Loop/OpenAPS follower mode
- **Libre data packet parsing**: The low-level 344-byte Libre sensor data format parsing utilities
- **Watch app and widget integrations**: iOS-specific integrations beyond Nightscout

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from xdripswift source |
