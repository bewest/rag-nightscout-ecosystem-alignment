# xDrip+ (Android) Behavior Documentation

This directory contains documentation extracted from xDrip+ (Android), the most feature-rich open-source CGM data management application for Android. xDrip+ serves as a **universal data hub** between CGM devices, cloud services, and other apps in the diabetes ecosystem.

## Source Repository

- **Repository**: [NightscoutFoundation/xDrip](https://github.com/NightscoutFoundation/xDrip)
- **Language**: Java + Kotlin (Android)
- **License**: GPL-3.0
- **Analysis Date**: 2026-01-16
- **Original Authors**: Stephen Black, jamorham (Nightscout Foundation)

## Purpose & Value

xDrip+ is the most comprehensive CGM data application, providing:

1. **Universal CGM connectivity** - Direct Bluetooth to 20+ CGM device types
2. **Multi-destination upload** - Nightscout, Tidepool, InfluxDB, MongoDB
3. **Local Nightscout API emulation** - Web server for inter-app communication
4. **Bi-directional Nightscout sync** - Upload and download treatments
5. **AAPS/Loop integration** - CGM data source for closed-loop systems
6. **Pluggable calibration** - Multiple algorithm options
7. **Smart pen integration** - InPen, Pendiq, NovoPen data import
8. **Multi-insulin tracking** - Separate bolus, basal, and pen insulin curves
9. **Android Wear support** - Direct G6/G7 connection on watch

## Documentation Index

| Document | Description |
|----------|-------------|
| [data-models.md](data-models.md) | BgReading, Treatments, Calibration, Sensor entity mappings |
| [nightscout-sync.md](nightscout-sync.md) | Upload queue, API interactions, treatment sync |
| [local-web-server.md](local-web-server.md) | Nightscout API emulation on port 17580 |
| [data-sources.md](data-sources.md) | All 20+ DexCollectionType variants |
| [insulin-management.md](insulin-management.md) | Multi-insulin tracking, pen integrations |
| [broadcast-service.md](broadcast-service.md) | Third-party app communication API |
| [external-integrations.md](external-integrations.md) | Tidepool, InfluxDB, AAPS, MongoDB |
| [calibrations.md](calibrations.md) | Pluggable calibration algorithms |

## Key Source Files

| File | Location | Lines | Purpose |
|------|----------|-------|---------|
| `BgReading.java` | `models/` | ~2,394 | Core glucose reading entity |
| `Treatments.java` | `models/` | ~1,436 | Treatment data with multi-insulin |
| `Calibration.java` | `models/` | ~1,123 | Calibration data and algorithms |
| `Sensor.java` | `models/` | ~360 | CGM sensor session tracking |
| `NightscoutUploader.java` | `utilitymodels/` | ~1,470 | REST API upload logic |
| `UploaderQueue.java` | `utilitymodels/` | ~557 | Unified upload queue |
| `NightscoutFollow.java` | `cgm/nsfollow/` | ~135 | Follower mode download |
| `DexCollectionType.java` | `utils/` | ~392 | CGM source enum |
| `XdripWebService.java` | `webservices/` | ~200 | Local web server |
| `BroadcastService.java` | `services/broadcastservice/` | ~569 | Inter-app API |
| `TidepoolUploader.java` | `tidepool/` | ~350 | Tidepool integration |
| `InfluxDBUploader.java` | `influxdb/` | ~200 | InfluxDB integration |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        xDrip+ (Android) Architecture                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                         DATA SOURCES (20+)                                 │  │
│  │                                                                            │  │
│  │  Direct Bluetooth          Companion Apps         Cloud Followers          │  │
│  │  ├── Dexcom G5/G6/G7       ├── LibreReceiver      ├── NSFollow             │  │
│  │  ├── Medtrum A6            ├── AidexReceiver      ├── SHFollow (Share)     │  │
│  │  ├── GluPro                ├── LibreAlarm         ├── CLFollow (Carelink)  │  │
│  │  ├── Libre via MiaoMiao    └── NSEmulator         ├── WebFollow            │  │
│  │  ├── Libre via Bubble                             └── Follower             │  │
│  │  └── Bluetooth Meters                                                      │  │
│  │       (Contour, AccuChek,                                                  │  │
│  │        Verio, CareSens)                                                    │  │
│  │                                                                            │  │
│  │  WiFi/Network              Manual/UI                                       │  │
│  │  ├── WifiWixel             ├── Manual              DexCollectionType       │  │
│  │  ├── WifiBlueToothWixel    ├── UiBased             enum handles all        │  │
│  │  ├── LimiTTerWifi          └── Mock (testing)      source switching        │  │
│  │  └── LibreWifi                                                             │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                       │                                          │
│                                       ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                         CORE DATA MODELS                                   │  │
│  │                                                                            │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │  │
│  │  │   BgReading     │  │   Treatments    │  │   Calibration   │            │  │
│  │  │   (2,394 lines) │  │   (1,436 lines) │  │   (1,123 lines) │            │  │
│  │  │                 │  │                 │  │                 │            │  │
│  │  │ • raw_data      │  │ • insulin       │  │ • bg            │            │  │
│  │  │ • filtered_data │  │ • insulinJSON   │  │ • sensor        │            │  │
│  │  │ • calculated_val│  │ • carbs         │  │ • slope         │            │  │
│  │  │ • noise         │  │ • eventType     │  │ • intercept     │            │  │
│  │  │ • dg_mgdl       │  │ • enteredBy     │  │ • raw_timestamp │            │  │
│  │  │ • source_info   │  │ • notes         │  │ • check_in      │            │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘            │  │
│  │                                                                            │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │  │
│  │  │     Sensor      │  │   BloodTest     │  │   HeartRate     │            │  │
│  │  │   (360 lines)   │  │  (finger BG)    │  │   StepCounter   │            │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘            │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                       │                                          │
│                    ┌──────────────────┼──────────────────┐                      │
│                    ▼                  ▼                  ▼                      │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                         UPLOAD CIRCUITS (UploaderQueue)                     ││
│  │                                                                             ││
│  │  Bitfield-based routing to multiple destinations:                          ││
│  │                                                                             ││
│  │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐            ││
│  │  │ NIGHTSCOUT_REST  │ │   MONGO_DIRECT   │ │  INFLUXDB_REST   │            ││
│  │  │   (bit 1<<1)     │ │    (bit 1)       │ │    (bit 1<<3)    │            ││
│  │  │                  │ │                  │ │                  │            ││
│  │  │ POST /entries    │ │ Direct MongoDB   │ │ InfluxDB line    │            ││
│  │  │ POST /treatments │ │ connection       │ │ protocol         │            ││
│  │  │ POST /devicestat │ │                  │ │                  │            ││
│  │  └──────────────────┘ └──────────────────┘ └──────────────────┘            ││
│  │                                                                             ││
│  │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐            ││
│  │  │   WATCH_WEARAPI  │ │ TEST_OUTPUT_PLUG │ │  TIDEPOOL        │            ││
│  │  │   (bit 1<<4)     │ │   (bit 1<<2)     │ │  (separate)      │            ││
│  │  │                  │ │                  │ │                  │            ││
│  │  │ Android Wear     │ │ Debug/Testing    │ │ Tidepool API     │            ││
│  │  │ sync             │ │                  │ │                  │            ││
│  │  └──────────────────┘ └──────────────────┘ └──────────────────┘            ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                       │                                          │
│                                       ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                      LOCAL WEB SERVER (Port 17580)                        │  │
│  │                                                                            │  │
│  │  Emulates Nightscout API for inter-app communication:                     │  │
│  │                                                                            │  │
│  │  /sgv.json           → GET BG readings (emulates /api/v1/entries/sgv.json)│  │
│  │  /treatments.json    → GET treatments (emulates /api/v1/treatments.json)  │  │
│  │  /pebble             → Pebble watchface endpoint                          │  │
│  │  /status.json        → Status with thresholds                             │  │
│  │  /tasker/*           → Tasker automation endpoints                        │  │
│  │  /steps/set/*        → Step counter input                                 │  │
│  │  /heart/set/*        → Heart rate input                                   │  │
│  │                                                                            │  │
│  │  Also listens on port 17581 (HTTPS with self-signed cert)                 │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                      BROADCAST SERVICE API                                 │  │
│  │                                                                            │  │
│  │  Intent-based inter-app communication:                                    │  │
│  │                                                                            │  │
│  │  Action: com.eveningoutpost.dexdrip.watch.wearintegration.BROADCAST_*     │  │
│  │                                                                            │  │
│  │  Commands:                                                                 │  │
│  │  • CMD_SET_SETTINGS     - Register app with graph settings                │  │
│  │  • CMD_UPDATE_BG_FORCE  - Request immediate BG update                     │  │
│  │  • CMD_SNOOZE_ALERT     - Snooze active alerts                            │  │
│  │  • CMD_ADD_TREATMENT    - Add treatment entry                             │  │
│  │  • CMD_CANCEL_ALARM     - Cancel alarms                                   │  │
│  │                                                                            │  │
│  │  Used by: AAPS, watchfaces, automation apps, custom integrations          │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Nightscout API Paths Used

### Upload (Producer)

| Path | Method | Purpose |
|------|--------|---------|
| `/api/v1/entries` | POST | Upload BG readings, calibrations |
| `/api/v1/treatments` | POST, PUT | Upload/update treatments |
| `/api/v1/devicestatus` | POST | Upload device status |
| `/api/v1/activity` | POST | Upload activity data |
| `/api/v1/status.json` | GET | Verify API connectivity |

### Download (Consumer/Follower)

| Path | Method | Purpose |
|------|--------|---------|
| `/api/v1/entries.json` | GET | Download BG readings (follower mode) |
| `/api/v1/treatments` | GET | Download treatments |
| `/api/v1/treatments.json` | GET | Find treatment by UUID |

### Local Emulation

| Path | Port | Purpose |
|------|------|---------|
| `/sgv.json` | 17580 | Emulates `/api/v1/entries/sgv.json` |
| `/treatments.json` | 17580 | Emulates `/api/v1/treatments.json` |
| `/pebble` | 17580 | Pebble watchface endpoint |
| `/status.json` | 17580 | High/low thresholds |
| `/tasker/*` | 17580 | Automation endpoints |

## Uploader Identification

xDrip+ identifies itself in Nightscout via:

```java
"enteredBy": "xdrip"  // Treatments.XDRIP_TAG
```

Device status includes:

```java
"uploaderBattery": batteryLevel
"device": "xDrip-" + Build.MANUFACTURER + Build.MODEL
```

## Treatment Event Types

| eventType | Purpose | Fields |
|-----------|---------|--------|
| `"<none>"` | Default/unspecified | varies |
| `"Sensor Start"` | CGM sensor started | timestamp |
| `"Sensor Stop"` | CGM sensor stopped | timestamp |
| `"Carb Correction"` | Carb entry | carbs |
| `"Correction Bolus"` | Insulin bolus | insulin, insulinJSON |
| `"Snack Bolus"` | Carbs + Insulin | carbs, insulin |
| `"Meal Bolus"` | Carbs + Insulin | carbs, insulin |
| `"Combo Bolus"` | Extended bolus | insulin, duration |
| `"BG Check"` | Finger stick | glucose, glucoseType |
| `"Note"` | Text annotation | notes |
| `"Question"` | Question marker | notes |
| `"Exercise"` | Exercise entry | duration, notes |
| `"Announcement"` | System announcement | notes |

## Multi-Insulin Support

xDrip+ uniquely supports tracking **multiple insulin types** per treatment:

```java
@Column(name = "insulinJSON")
public String insulinJSON;  // JSON array of InsulinInjection objects

// Example insulinJSON:
[
  {"profile": "NovoRapid", "units": 5.0},
  {"profile": "Lantus", "units": 20.0}
]
```

Supported insulin concentrations: U100, U200, U300, U400, U500

## Authentication

Supports both API_SECRET and token authentication:

```java
// API_SECRET (SHA1 hashed in header)
request.setValue(apiKey.sha1(), forHTTPHeaderField: "api-secret")

// Token (query parameter)
URLQueryItem(name: "token", value: token)
```

Local web server authentication:
- Loopback (127.0.0.1): No authentication required
- Open network: Requires `api-secret` header with SHA1 hash

## Comparison: xDrip+ vs xDrip4iOS

| Aspect | xDrip+ (Android) | xDrip4iOS |
|--------|-----------------|-----------|
| **Platform** | Android (Java/Kotlin) | iOS (Swift) |
| **Data Sources** | 20+ collection types | ~6 transmitter types |
| **Local Web Server** | Yes (port 17580) | No |
| **Multi-Insulin** | Yes (insulinJSON) | No |
| **Tidepool Upload** | Yes (direct) | No |
| **InfluxDB** | Yes (direct) | No |
| **MongoDB Direct** | Yes | No |
| **Smart Pen Integration** | InPen, Pendiq, NovoPen | No |
| **Calibration Plugins** | 5+ algorithms | Native only |
| **AAPS Integration** | Deep (broadcast, status) | Follower only |
| **Watch Support** | Android Wear, direct G6 | Apple Watch |
| **Follower Sources** | NS, Share, Carelink, Web | NS, LibreLinkUp, Share |

## Code Citation Format

Throughout this documentation, code references use:
```
xdrip-android:com/eveningoutpost/dexdrip/path/File.java#L123-L456
```

This maps to files in `externals/xDrip/app/src/main/java/`.

## Cross-References

- [Nightscout Data Model](../../docs/10-domain/nightscout-data-model.md) - Authoritative NS schema
- [mapping/xdrip4ios/](../xdrip4ios/) - iOS counterpart
- [mapping/aaps/](../aaps/) - AAPS integration patterns
- [mapping/loop/](../loop/) - Loop comparison

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from xDrip+ source |
