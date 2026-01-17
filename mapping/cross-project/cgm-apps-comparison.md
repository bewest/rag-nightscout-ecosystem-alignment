# CGM Apps Cross-Project Comparison

This matrix compares CGM data management applications: xDrip+ (Android), xDrip4iOS, DiaBLE, Nightguard, xdrip-js, and related ecosystem apps.

---

## Platform Overview

| Aspect | xDrip+ (Android) | xDrip4iOS | DiaBLE | Nightguard | xdrip-js |
|--------|-----------------|-----------|--------|------------|----------|
| **Platform** | Android | iOS | iOS/watchOS | iOS/watchOS | Node.js (OpenAPS rigs) |
| **Language** | Java/Kotlin | Swift | Swift | Swift | JavaScript |
| **Primary Role** | CGM hub + producer | CGM producer | CGM producer | Consumer/follower only | BLE library |
| **License** | GPL-3.0 | GPL-3.0 | GPL-3.0 | AGPL-3.0 | MIT |
| **Codebase Size** | ~16,000 lines (models only) | ~5,000 lines | ~20,000 lines | ~16,600 lines | ~2,500 lines |
| **Repository** | eveningoutpost/dexdrip | JohanDegraeve/xdripswift | gui-dos/DiaBLE | nightscout/nightguard | xdrip-js/xdrip-js |
| **Primary API** | `/api/v1/entries` | `/api/v1/entries` | `/api/v1/entries` | `/api/v2/properties` | N/A (local BLE) |

---

## CGM Data Sources

*Note: Nightguard and xdrip-js are consumer/library apps without direct CGM connections. xdrip-js provides BLE communication for Lookout/Logger apps.*

| Source Type | xDrip+ (Android) | xDrip4iOS | DiaBLE | Nightguard | xdrip-js |
|-------------|-----------------|-----------|--------|------------|----------|
| **Dexcom G5** | Direct BT | Direct BT | Direct BT | N/A | Direct BT |
| **Dexcom G6** | Direct BT | Direct BT | Direct BT | N/A | Direct BT |
| **Dexcom G7** | Direct BT | Direct BT | Direct BT | N/A | No |
| **Dexcom ONE+/Stelo** | No | No | Direct BT | N/A | No |
| **Libre 1** | Via bridge | Via bridge | NFC | N/A | No |
| **Libre 2** | Via bridge | Direct BT | NFC + BLE | N/A | No |
| **Libre 2 Gen2** | No | No | NFC + BLE | N/A | No |
| **Libre 3** | Via companion | No | NFC + BLE (partial) | N/A | No |
| **Libre Pro/Pro H** | No | No | NFC | N/A | No |
| **Lingo** | No | No | NFC | N/A | No |
| **Medtrum A6** | Direct BT | No | No | N/A | No |
| **GluPro** | Direct BT | No | No | N/A | No |
| **MiaoMiao** | Bridge device | Bridge device | Bridge device | N/A | No |
| **Bubble** | Bridge device | Bridge device | Bridge device | N/A | No |
| **BluCon** | Bridge device | No | Bridge device | N/A | No |
| **Wixel/xBridge** | Bridge device | No | No | N/A | No |
| **Carelink (630G/640G/670G)** | Cloud follower | No | No | N/A | No |
| **Nightscout Follower** | Yes | Yes | No | Yes (primary) | No |
| **Dexcom Share Follower** | Yes | Yes | No | No | No |
| **LibreLinkUp Follower** | No | Yes | Yes | No | No |
| **Web/Custom Follower** | Yes | No | No | No | No |
| **Companion Apps** | 5+ (LibreAlarm, NSEmulator, etc.) | No | No | N/A | Lookout, Logger |
| **Total Source Types** | 20+ | ~6 | 12+ | 1 (NS) | 2 (G5/G6) |

---

## Nightscout Integration

*Note: xdrip-js is a BLE library without direct Nightscout integration—client apps (Lookout/Logger) handle uploads.*

### API Paths Used

| Path | xDrip+ | xDrip4iOS | DiaBLE | Nightguard | Direction |
|------|--------|-----------|--------|------------|-----------|
| `POST /api/v1/entries` | Yes | Yes | Yes | No | Upload |
| `GET /api/v1/entries.json` | Yes | Yes | Yes | Yes | Download |
| `GET /api/v2/properties` | No | No | No | Yes (primary) | Download |
| `GET /api/v1/status.json` | No | No | Yes | Yes | Download |
| `POST /api/v1/treatments` | Yes | Yes | No | Yes (care only) | Upload |
| `PUT /api/v1/treatments` | Yes | Yes | No | No | Update |
| `DELETE /api/v1/treatments/{id}` | Yes | Yes | No | No | Delete |
| `GET /api/v1/treatments` | Yes | Yes | No | Yes | Download |
| `POST /api/v1/devicestatus` | Yes | Yes | Yes | No | Upload |
| `GET /api/v1/devicestatus.json` | No | Yes | No | Yes | Download |
| `GET /api/v1/profile` | No | Yes | No | No | Download |

### Sync Architecture

| Aspect | xDrip+ (Android) | xDrip4iOS |
|--------|-----------------|-----------|
| **Queue System** | UploaderQueue with bitfield circuits | Direct upload |
| **Multi-destination** | 5 circuits (NS, Mongo, InfluxDB, Wear, Test) | Nightscout only |
| **Treatment Sync** | Bi-directional with delete | Bi-directional |
| **Gzip Compression** | Yes (configurable) | No |
| **Rate Limiting** | Built-in (JoH.ratelimit) | Timer-based |
| **Backfill** | MissedReadingsEstimator | Time-based |

### Upload Identifiers

| Field | xDrip+ | xDrip4iOS | DiaBLE | Nightguard |
|-------|--------|-----------|--------|------------|
| `enteredBy` | `"xdrip"` | `"xDrip4iOS"` | `"DiaBLE"` | `"nightguard"` |
| `device` | `"xDrip-" + manufacturer + model` | Device name | `"DiaBLE"` | N/A |
| `uuid` | Client-generated UUID | Client-generated UUID | N/A | N/A |

---

## Data Models

### BgReading Comparison

| Field | xDrip+ | xDrip4iOS | Notes |
|-------|--------|-----------|-------|
| `timestamp` | Yes | Yes | Epoch milliseconds |
| `calculated_value` | Yes | Yes | mg/dL |
| `raw_data` | Yes | Yes | Raw sensor value |
| `filtered_data` | Yes | Yes | Filtered sensor value |
| `noise` | Yes | Yes | Signal quality |
| `uuid` | Yes | Yes | Unique identifier |
| `source_info` | Yes | No | Provenance tracking |
| `dg_mgdl` | Yes | No | Dexcom native glucose |
| `dg_slope` | Yes | No | Dexcom native trend |
| `age_adjusted_raw_value` | Yes | No | Sensor age compensation |
| `calibration_flag` | Yes | No | Needs calibration |
| `a`, `b`, `c`, `ra`, `rb`, `rc` | Yes | No | Calibration polynomials |

### Treatments Comparison

| Field | xDrip+ | xDrip4iOS | Notes |
|-------|--------|-----------|-------|
| `timestamp` | Yes | Yes | Event time |
| `eventType` | Yes | Yes | Treatment type |
| `enteredBy` | Yes | Yes | Creator |
| `notes` | Yes | Yes | Free text |
| `uuid` | Yes | Yes | Unique ID |
| `carbs` | Yes | Yes | Grams |
| `insulin` | Yes | Yes | Total units |
| `insulinJSON` | Yes | No | Multi-insulin support |
| `duration` | Via notes | Yes | For exercise/temp targets |

---

## Unique Features

### xDrip+ Only

| Feature | Description |
|---------|-------------|
| **Local Web Server** | Nightscout API emulation on port 17580 |
| **Multi-Insulin Tracking** | Track multiple insulin types per treatment |
| **Pluggable Calibration** | 5+ calibration algorithms |
| **Smart Pen Integration** | InPen, Pendiq, NovoPen support |
| **Tidepool Upload** | Direct Tidepool platform integration |
| **InfluxDB Upload** | Time-series database export |
| **MongoDB Direct** | Bypass Nightscout REST API |
| **Broadcast Service API** | Intent-based inter-app communication |
| **AAPS Integration** | Deep device status exchange |
| **Tasker Support** | Automation via local endpoints |
| **Android Wear Direct** | G6/G7 direct to watch |

### xDrip4iOS Only

| Feature | Description |
|---------|-------------|
| **Apple HealthKit** | Native iOS health data integration |
| **Apple Watch App** | Native watchOS complications |
| **iOS Widgets** | Home/lock screen widgets |
| **LibreLinkUp Follower** | Abbott cloud follower |
| **Calendar Integration** | Events for watch complications |
| **Speak** | Voice announcements |

### Nightguard Only

| Feature | Description |
|---------|-------------|
| **Consumer-Only Design** | Pure follower app, no CGM connection |
| **Advanced Alarm System** | Smart snooze, prediction, edge detection, persistent high |
| **Yesterday Overlay** | Chart shows previous day as comparison |
| **Care Data Tracking** | CAGE, SAGE, BAGE display and creation |
| **Loop Integration** | IOB, COB, temp basal, temp target from devicestatus |
| **Screen Lock Mode** | Keeps app running overnight for alarms |
| **3 Widget Types** | Text, timestamp, and gauge widgets |
| **Watch Complications** | Multiple complication families |
| **API V2 Properties** | Uses newer consolidated API endpoint |

### DiaBLE Only

| Feature | Description |
|---------|-------------|
| **NFC Direct Reading** | Read Libre sensors via NFC without bridges |
| **Libre 2/3 BLE Streaming** | Direct Bluetooth to Libre 2/3 sensors |
| **Dexcom G7 Support** | Native G7 support with backfill |
| **Sensor Encryption Research** | Publishes technical details for Libre 2/3 encryption |
| **watchOS Direct BLE** | Experimental direct-to-watch CGM connection |
| **LibreView CSV Import** | Import data from Abbott's LibreView cloud |
| **Realm File Parsing** | Read encrypted trident.realm from Libre 3 app |
| **Temperature Calibration** | Legacy LibreLink 2.3 calibration algorithm |
| **Dexcom ONE+/Stelo** | Support for newer Dexcom consumer sensors |

### xdrip-js Only

| Feature | Description |
|---------|-------------|
| **OpenAPS Integration** | Designed for DIY closed-loop rigs |
| **Headless Operation** | Runs on Raspberry Pi without display |
| **Transmitter Reset** | Reset G5/G6 transmitters for extended life |
| **Custom Calibration** | Linear least squares regression (via Logger) |
| **Backfill Gap Filling** | Retrieve missed readings from transmitter memory |
| **Battery Monitoring** | Transmitter battery voltage tracking |
| **Alternate BT Channel** | Use receiver Bluetooth channel option |

---

## Treatment Event Types

| Event Type | xDrip+ | xDrip4iOS | Nightguard | Nightscout Canonical |
|------------|--------|-----------|------------|---------------------|
| Sensor Start | `"Sensor Start"` | `"Sensor Start"` | `"Sensor Change"` (R/W) * | `"Sensor Start"` |
| Sensor Stop | `"Sensor Stop"` | N/A | N/A | N/A |
| Meal Bolus | `"Meal Bolus"` | `"Bolus"` | Read only | `"Meal Bolus"` |
| Correction Bolus | `"Correction Bolus"` | `"Bolus"` | Read only | `"Correction Bolus"` |
| Carbs | `"Carb Correction"` | `"Carbs"` | Read only | `"Carbs"` |
| BG Check | `"BG Check"` | `"BG Check"` | Read only | `"BG Check"` |
| Note | `"Note"` | `"Note"` | Read only | `"Note"` |
| Exercise | `"Exercise"` | `"Exercise"` | Read only | `"Exercise"` |
| Temp Basal | N/A (via AAPS) | `"Temp Basal"` | Read only | `"Temp Basal"` |
| Site Change | N/A | `"Site Change"` | `"Site Change"` (R/W) | `"Site Change"` |
| Pump Battery | N/A | `"Pump Battery Change"` | `"Pump Battery Change"` (R/W) | `"Pump Battery Change"` |
| Temp Target | N/A | N/A | `"Temporary Target"` (R) | `"Temporary Target"` |

\* Nightguard uses non-canonical event names for some treatments (e.g., "Sensor Change" instead of "Sensor Start")

---

## Authentication Methods

| Method | xDrip+ | xDrip4iOS | Nightguard |
|--------|--------|-----------|------------|
| API_SECRET (SHA1 header) | Yes | Yes | No (not implemented) |
| Token (query parameter) | Yes | Yes | Yes (embedded in base URI) |
| Local (no auth) | Port 17580 loopback | N/A | N/A |

---

## Data Flow Architecture

### xDrip+ (Android)

```
CGM Device → Bluetooth → DexCollectionService → BgReading
                                                    ↓
                                            UploaderQueue
                                                    ↓
                    ┌───────────────────────────────┼───────────────────────────────┐
                    ↓                               ↓                               ↓
            Nightscout REST              MongoDB Direct               InfluxDB REST
                    ↓                               ↓                               ↓
            Local Web Server             Android Wear API             Tidepool API
                    ↓
            Broadcast Service → AAPS, Watchfaces, Tasker
```

### xDrip4iOS

```
CGM Device → Bluetooth → CGMTransmitter → BgReading (CoreData)
                                               ↓
                                    NightscoutSyncManager
                                               ↓
                                    ┌──────────┴──────────┐
                                    ↓                     ↓
                            Nightscout REST         HealthKit
```

### Nightguard

```
                                Nightscout Server
                                       ↓
                           NightscoutService (REST Client)
                                       ↓
                           NightscoutCacheService
                                       ↓
               ┌───────────────────────┼───────────────────────┐
               ↓                       ↓                       ↓
        iOS App (SwiftUI)        Apple Watch         iOS Widgets
               ↓                       ↓                       ↓
        ┌──────┴──────┐         WatchConnectivity    TimelineProvider
        ↓             ↓                ↓                       ↓
    ChartScene   AlarmRule     Complications         Widget Views
```

---

## Alarm System Comparison

| Feature | xDrip+ | xDrip4iOS | Nightguard |
|---------|--------|-----------|------------|
| **High/Low Alerts** | Yes | Yes | Yes |
| **Missed Readings** | Yes | Yes | Yes (configurable) |
| **Edge Detection (Fast Rise/Drop)** | Yes | Basic | Yes (advanced) |
| **Low Prediction** | Yes | Basic | Yes (15 min lookahead) |
| **Smart Snooze** | No | No | Yes (trend-aware) |
| **Persistent High** | No | No | Yes (time-based) |
| **Snooze Sync (Phone↔Watch)** | N/A | No | Yes |
| **Background Alarms** | Yes | Yes | Yes (simplified) |

---

## Gap Analysis

### xDrip+ Gaps

| Gap | Description | Impact |
|-----|-------------|--------|
| No iOS version | Platform-locked | iOS users cannot use |
| No LibreLinkUp | Missing follower source | Libre users limited |
| No HealthKit | No Apple Health integration | No unified health view |

### xDrip4iOS Gaps

| Gap | Description | Impact |
|-----|-------------|--------|
| No local server | No inter-app API | Limited automation |
| No multi-insulin | Single insulin per treatment | Less accurate tracking |
| No Tidepool | No direct upload | Extra step required |
| No pluggable cal | Native only | Less flexibility |
| Limited sources | Fewer CGM types | Device limitations |

### Nightguard Gaps

| Gap | Description | Impact |
|-----|-------------|--------|
| No CGM connection | Consumer-only, no direct sensor | Depends on Nightscout |
| No profile download | Cannot display profile data | Limited Loop context |
| No treatment editing | Can only create care events | Limited management |
| No HealthKit | No Apple Health integration | Data silo |
| Limited treatments | Only CAGE/SAGE/BAGE writes | Not a treatment manager |

### DiaBLE Gaps

| Gap | Description | Impact |
|-----|-------------|--------|
| No treatment support | Cannot create/sync treatments | CGM data only |
| No follower mode | Cannot consume Nightscout data | Primary mode only |
| No HealthKit | No Apple Health integration | Data silo |
| Prototype status | Not production-ready | Stability concerns |
| No profile download | Cannot display profile data | Limited closed-loop context |
| Libre 3 partial | AES-CCM encryption not fully cracked | Depends on external decryption |

### xdrip-js Gaps

| Gap | Description | Impact |
|-----|-------------|--------|
| G5/G6 only | No G7, no Libre sensors | Limited sensor support |
| No mobile app | Library only, requires host app | Not standalone |
| No Nightscout direct | Relies on client apps (Lookout/Logger) | Indirect integration |
| No calibration UI | Raw calibration API only | Developer-focused |
| Linux/Raspberry Pi focused | Not cross-platform mobile | Niche use case |

---

## Recommendations for Alignment

1. **Standardize `enteredBy`**: Both apps should use a consistent format
2. **Sync identity field**: Adopt common UUID format across apps
3. **Multi-insulin schema**: Propose `insulinJSON` extension to Nightscout
4. **Local API spec**: Document xDrip+ web server for potential xDrip4iOS adoption
5. **Event type mapping**: Harmonize `Sensor Stop` and other xDrip+-specific types

---

## Auditable Source Citations

All claims in this document are traceable to the xDrip+ source code in `externals/xDrip/`.

### Key Source Files (with line references)

| Claim | Source File | Line(s) | Notes |
|-------|-------------|---------|-------|
| `enteredBy: "xdrip"` | `externals/xDrip/.../models/Treatments.java` | L76 | `XDRIP_TAG = "xdrip"` constant |
| BgReading entity | `externals/xDrip/.../models/BgReading.java` | L69-200 | Core glucose model fields |
| Treatments entity | `externals/xDrip/.../models/Treatments.java` | L68-110 | Treatment model fields |
| 20+ DexCollectionType | `externals/xDrip/.../utils/DexCollectionType.java` | L31-59 | Enum definition |
| UploaderQueue circuits | `externals/xDrip/.../utilitymodels/UploaderQueue.java` | L75-92 | Bitfield constants |
| Local web server port | `externals/xDrip/.../webservices/XdripWebService.java` | L10-20 | Port 17580/17581 |
| NightscoutService API | `externals/xDrip/.../utilitymodels/NightscoutUploader.java` | L127-162 | Retrofit interface |
| Nightscout follower | `externals/xDrip/.../cgm/nsfollow/NightscoutFollow.java` | L43-53 | Nightscout interface |
| Multi-insulin JSON | `externals/xDrip/.../models/Treatments.java` | L85 | `insulinJSON` field |
| InsulinInjection | `externals/xDrip/.../models/InsulinInjection.java` | Full file | Multi-insulin class |
| Broadcast service | `externals/xDrip/.../services/broadcastservice/BroadcastService.java` | L63-156 | Intent receiver |
| Calibration plugins | `externals/xDrip/.../calibrations/PluggableCalibration.java` | Full file | Plugin manager |

### Full Path Template

```
externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/{path}
```

### xDrip4iOS References

```
externals/xdripswift/xdrip/Managers/Nightscout/NightscoutSyncManager.swift
externals/xdripswift/xdrip/Core/Models/BgReading+CoreDataClass.swift
```

### Nightguard References

| Claim | Source File | Notes |
|-------|-------------|-------|
| `enteredBy: "nightguard"` | `externals/nightguard/nightguard/external/NightscoutService.swift#L983` | Treatment creation |
| NightscoutData model | `externals/nightguard/nightguard/app/NightscoutData.swift` | Current BG model |
| BloodSugar model | `externals/nightguard/nightguard/domain/BloodSugar.swift` | Historical BG model |
| AlarmRule | `externals/nightguard/nightguard/domain/AlarmRule.swift` | Alarm logic |
| API V2 Properties | `externals/nightguard/nightguard/external/NightscoutService.swift#L421` | Primary data source |
| Widget Timeline | `externals/nightguard/nightguard Widget Extension/NightguardTimelineProvider.swift` | Widget data |
| Watch Extension | `externals/nightguard/nightguard WatchKit App/ExtensionDelegate.swift` | Watch app entry |

See `mapping/nightguard/` for comprehensive documentation.

### DiaBLE References

| Claim | Source File | Notes |
|-------|-------------|-------|
| Glucose model | `externals/DiaBLE/DiaBLE Playground.swiftpm/Glucose.swift` | Core glucose data structure |
| Sensor model | `externals/DiaBLE/DiaBLE Playground.swiftpm/Sensor.swift` | CGM sensor abstraction |
| Nightscout sync | `externals/DiaBLE/DiaBLE Playground.swiftpm/Nightscout.swift` | NS upload/download logic |
| Libre protocols | `externals/DiaBLE/DiaBLE Playground.swiftpm/Libre*.swift` | Libre 1/2/3/Pro support |
| Dexcom protocols | `externals/DiaBLE/DiaBLE Playground.swiftpm/Dexcom*.swift` | G5/G6/G7 support |
| Bridge devices | `externals/DiaBLE/DiaBLE Playground.swiftpm/{MiaoMiao,Bubble,BluCon}.swift` | Third-party bridges |
| NFC communication | `externals/DiaBLE/DiaBLE Playground.swiftpm/NFC*.swift` | NFC sensor reading |

See `mapping/diable/` for comprehensive documentation.

### xdrip-js References

| Claim | Source File | Notes |
|-------|-------------|-------|
| Transmitter class | `externals/xdrip-js/lib/transmitter.js` | Main BLE communication |
| Glucose structure | `externals/xdrip-js/lib/glucose.js` | Glucose event model |
| BLE services | `externals/xdrip-js/lib/bluetooth-services.js` | Dexcom UUIDs |
| Auth messages | `externals/xdrip-js/lib/messages/auth-*.js` | Authentication protocol |
| Calibration state | `externals/xdrip-js/lib/calibration-state.js` | Session state codes |
| Backfill parser | `externals/xdrip-js/lib/backfill-parser.js` | Gap filling logic |

See `mapping/xdrip-js/` for comprehensive documentation.
