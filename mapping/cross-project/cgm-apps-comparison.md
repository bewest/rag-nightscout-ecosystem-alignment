# CGM Apps Cross-Project Comparison

This matrix compares CGM data management applications: xDrip+ (Android), xDrip4iOS, Nightguard, and related ecosystem apps.

---

## Platform Overview

| Aspect | xDrip+ (Android) | xDrip4iOS | Nightguard | AAPS (as CGM source) |
|--------|-----------------|-----------|------------|---------------------|
| **Platform** | Android | iOS | iOS/watchOS | Android |
| **Language** | Java/Kotlin | Swift | Swift | Kotlin |
| **Primary Role** | CGM hub + producer | CGM producer | Consumer/follower only | Consumer/producer |
| **License** | GPL-3.0 | GPL-3.0 | AGPL-3.0 | AGPL-3.0 |
| **Codebase Size** | ~16,000 lines (models only) | ~5,000 lines | ~16,600 lines | N/A (integrated) |
| **Repository** | eveningoutpost/dexdrip | JohanDegraeve/xdripswift | nightscout/nightguard | nightscout/AndroidAPS |
| **Primary API** | `/api/v1/entries` | `/api/v1/entries` | `/api/v2/properties` | `/api/v1/entries` |

---

## CGM Data Sources

| Source Type | xDrip+ (Android) | xDrip4iOS |
|-------------|-----------------|-----------|
| **Dexcom G5** | Direct BT | Direct BT |
| **Dexcom G6** | Direct BT | Direct BT |
| **Dexcom G7** | Direct BT | Direct BT |
| **Dexcom ONE** | Direct BT | Direct BT |
| **Libre 2** | Via bridge | Direct BT |
| **Libre 3** | Via companion | No |
| **Medtrum A6** | Direct BT | No |
| **GluPro** | Direct BT | No |
| **MiaoMiao** | Bridge device | Bridge device |
| **Bubble** | Bridge device | Bridge device |
| **Wixel/xBridge** | Bridge device | No |
| **Carelink (630G/640G/670G)** | Cloud follower | No |
| **Nightscout Follower** | Yes | Yes |
| **Dexcom Share Follower** | Yes | Yes |
| **LibreLinkUp Follower** | No | Yes |
| **Web/Custom Follower** | Yes | No |
| **Companion Apps** | 5+ (LibreAlarm, NSEmulator, etc.) | No |
| **Total Source Types** | 20+ | ~6 |

---

## Nightscout Integration

### API Paths Used

| Path | xDrip+ | xDrip4iOS | Nightguard | Direction |
|------|--------|-----------|------------|-----------|
| `POST /api/v1/entries` | Yes | Yes | No | Upload |
| `GET /api/v1/entries.json` | Yes | Yes | Yes | Download |
| `GET /api/v2/properties` | No | No | Yes (primary) | Download |
| `GET /api/v1/status.json` | No | No | Yes | Download |
| `POST /api/v1/treatments` | Yes | Yes | Yes (care only) | Upload |
| `PUT /api/v1/treatments` | Yes | Yes | No | Update |
| `DELETE /api/v1/treatments/{id}` | Yes | Yes | No | Delete |
| `GET /api/v1/treatments` | Yes | Yes | Yes | Download |
| `POST /api/v1/devicestatus` | Yes | Yes | No | Upload |
| `GET /api/v1/devicestatus.json` | No | Yes | Yes | Download |
| `GET /api/v1/profile` | No | Yes | No | Download |

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

| Field | xDrip+ | xDrip4iOS | Nightguard |
|-------|--------|-----------|------------|
| `enteredBy` | `"xdrip"` | `"xDrip4iOS"` | `"nightguard"` |
| `device` | `"xDrip-" + manufacturer + model` | Device name | N/A |
| `uuid` | Client-generated UUID | Client-generated UUID | N/A |

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
