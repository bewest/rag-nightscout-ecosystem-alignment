# CGM Data Sources Deep Dive

This document provides comprehensive analysis of how CGM (Continuous Glucose Monitor) data flows from sensors to Nightscout entries, covering data sources, calibration, follower modes, and data provenance across xDrip+ (Android), xDrip4iOS, Loop, AAPS, and Trio.

---

## Executive Summary

CGM data originates from hardware transmitters and flows through a chain of software components before reaching Nightscout. Understanding this flow is critical for:

1. **Data provenance** - Knowing where glucose values came from
2. **Calibration accuracy** - Understanding which calibration was applied where
3. **Deduplication** - Preventing duplicate entries from multiple uploaders
4. **Latency** - Understanding delays introduced by each layer

### Key Findings

| Aspect | Finding |
|--------|---------|
| **Primary Producer** | xDrip+ Android is the most common CGM data producer with 20+ data source types |
| **iOS Producers** | xDrip4iOS and Loop CGMManager plugins handle Dexcom/Libre transmitters |
| **Calibration Diversity** | Only xDrip+ Android has pluggable calibration (5+ algorithms); others use native/OOP |
| **Follower Latency** | Nightscout follower: real-time; LibreLinkUp: 1-3 min; Dexcom Share: ~5 min |
| **Provenance Gap** | Calibration source and algorithm are not tracked in Nightscout entries |

---

## Data Flow Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CGM DATA FLOW ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────┐                                                          │
│  │ CGM Transmitter│  (G5, G6, G7, Libre 2, MiaoMiao, Bubble, etc.)          │
│  └───────┬───────┘                                                          │
│          │ Bluetooth LE / NFC                                                │
│          ▼                                                                   │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    DATA SOURCE LAYER                                   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │  │
│  │  │ xDrip+      │  │ xDrip4iOS   │  │ Loop CGM   │  │ Companion   │   │  │
│  │  │ (20+ types) │  │ (~6 types)  │  │ Manager    │  │ Apps        │   │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘   │  │
│  └─────────┼────────────────┼────────────────┼────────────────┼──────────┘  │
│            │                │                │                │             │
│            ▼                ▼                ▼                ▼             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    CALIBRATION LAYER                                   │  │
│  │                                                                        │  │
│  │  xDrip+: Pluggable (xDrip Original, Native, Datricsae, etc.)          │  │
│  │  xDrip4iOS: Native/WebOOP only                                        │  │
│  │  Loop/Trio: Transmitter-calibrated (no local calibration)             │  │
│  │  AAPS: Via xDrip+ broadcast (inherits xDrip+ calibration)             │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│            │                │                │                │             │
│            ▼                ▼                ▼                ▼             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    LOCAL STORAGE LAYER                                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │  │
│  │  │ BgReading   │  │ BgReading   │  │ StoredGlucose│                   │  │
│  │  │ (SQLite)    │  │ (CoreData)  │  │ Sample       │                   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│            │                │                │                              │
│            ▼                ▼                ▼                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    UPLOAD LAYER                                        │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │  │
│  │  │ Nightscout  │  │ Nightscout  │  │ No CGM     │                    │  │
│  │  │ REST POST   │  │ REST POST   │  │ Upload     │                    │  │
│  │  │ (/entries)  │  │ (/entries)  │  │ (consumer) │                    │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              │                                               │
│                              ▼                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    NIGHTSCOUT                                          │  │
│  │                    entries collection                                   │  │
│  │                    { sgv, direction, date, device, noise, ... }        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              │                                               │
│            ┌─────────────────┼─────────────────┐                            │
│            ▼                 ▼                 ▼                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│  │ Loop/Trio   │    │ AAPS        │    │ Followers   │                     │
│  │ (consumer)  │    │ (consumer)  │    │ (display)   │                     │
│  └─────────────┘    └─────────────┘    └─────────────┘                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Source Categories

### 1. Direct Bluetooth CGM Sources

These connect directly to CGM transmitters via Bluetooth Low Energy.

| Source | xDrip+ Android | xDrip4iOS | Loop | AAPS |
|--------|----------------|-----------|------|------|
| **Dexcom G5** | Yes (Ob1 collector) | Yes | Yes (CGMBLEKit) | Via xDrip+ |
| **Dexcom G6** | Yes (Ob1 collector) | Yes | Yes (CGMBLEKit) | Via xDrip+ |
| **Dexcom G7** | Yes (Ob1 collector) | Yes | Yes (G7SensorKit) | Via xDrip+ |
| **Dexcom ONE** | Yes | Yes | Yes | Via xDrip+ |
| **Libre 2** | Via bridge | Yes (direct BLE) | Via LibreTransmitter | Via xDrip+ |
| **Libre 3** | Via companion app | No | No | Via xDrip+ |
| **Medtrum A6** | Yes | No | No | Via xDrip+ |
| **GluPro** | Yes | No | No | Via xDrip+ |

#### Transmitter ID Patterns (Dexcom)

| Prefix | Model | Source |
|--------|-------|--------|
| `4XXXXX` | Dexcom G5 | xDrip4iOS |
| `8XXXXX` | Dexcom G6 | xDrip4iOS |
| `5XXXXX`, `CXXXXX` | Dexcom ONE | xDrip4iOS |
| `DX01XX` | Dexcom Stelo | xDrip4iOS |
| `DX02XX` | Dexcom ONE+ | xDrip4iOS |
| (6-char other) | Dexcom G7 | xDrip4iOS |

### 2. Bridge Device Sources

Bridge devices read from CGM sensors and relay via Bluetooth.

| Device | xDrip+ Android | xDrip4iOS |
|--------|----------------|-----------|
| **MiaoMiao** | Yes | Yes |
| **Bubble** | Yes | Yes |
| **Wixel/xBridge** | Yes | No |
| **LimiTTer** | Yes | No |
| **Blucon** | Yes | Yes |
| **Atom** | Yes | Yes |
| **Droplet-1** | Yes | Yes |

### 3. Follower/Cloud Sources

These download glucose data from cloud services.

| Source | xDrip+ Android | xDrip4iOS | Latency |
|--------|----------------|-----------|---------|
| **Nightscout** | Yes (NSFollow) | Yes | Real-time* |
| **Dexcom Share** | Yes (SHFollow) | Yes | ~5 minutes |
| **LibreLinkUp** | No | Yes | 1-3 minutes |
| **CareLink (Medtronic)** | Yes (CLFollow) | No | Variable |
| **Generic Web** | Yes (WebFollow) | No | Variable |

*Depends on uploader frequency

#### Follower Download Endpoints

| Source | Endpoint | Authentication |
|--------|----------|----------------|
| **Nightscout** | `GET /api/v1/entries/sgv.json?count=N` | API_SECRET or token |
| **Dexcom Share** | Proprietary API | Username/password |
| **LibreLinkUp** | `GET /llu/connections/{patientId}/graph` | OAuth token |

### 4. Companion App Sources (xDrip+ Android Only)

These receive glucose data via Android intents from other apps.

| Source Type | Apps | Mechanism |
|-------------|------|-----------|
| **NSEmulator** | Spike, Diabox | Broadcast intent with NS format |
| **LibreAlarm** | LibreAlarm app | Libre scan results |
| **LibreReceiver** | OOP companion | Out-of-process calibration |
| **AidexReceiver** | Aidex CGM app | Native broadcast |
| **UiBased** | Various | Screen scraping |

---

## Calibration Systems

### xDrip+ Pluggable Calibration (Android Only)

xDrip+ is unique in offering multiple calibration algorithms:

| Algorithm | Requires Fingerstick | Description |
|-----------|---------------------|-------------|
| **xDrip Original** | Yes | Weighted linear regression from recent calibrations |
| **Native** | No | Passthrough (uses sensor's native calibration) |
| **Datricsae** | Yes | Robust regression reducing outlier impact |
| **Last 7 Unweighted** | Yes | Simple average of last 7 calibrations |
| **Fixed Slope** | No | Testing/development only |

#### Calibration Data Model (xDrip+)

```java
class Calibration {
    long timestamp;           // Calibration time
    double bg;               // Fingerstick BG (mg/dL)
    double raw_value;        // Raw sensor value at calibration
    double slope;            // Calculated slope
    double intercept;        // Calculated intercept
    double sensor_confidence; // Confidence score (0-1)
}
```

#### Calibration Selection

```java
// Get calibration plugin from preferences
CalibrationAbstract plugin = PluggableCalibration.getCalibrationPluginFromPreferences();

// Calculate glucose from raw value
double glucose = plugin.getGlucoseFromSensorRaw(raw, filtered, timestamp, lastReading);
```

### iOS Calibration (xDrip4iOS, Loop, Trio)

iOS systems have simpler calibration models:

| System | Calibration Options |
|--------|---------------------|
| **xDrip4iOS** | Native only; WebOOP for Libre bridges |
| **Loop** | Transmitter-calibrated readings only |
| **Trio** | Transmitter-calibrated readings only |

#### WebOOP (Out-of-Process) Calibration

Libre bridges can use external calibration services:

```swift
func setWebOOPEnabled(enabled: Bool)
func isWebOOPEnabled() -> Bool
```

When enabled, glucose values come pre-calibrated from the algorithm server, bypassing local calibration.

### Calibration Provenance Gap

**GAP-CGM-001**: Nightscout entries do not track which calibration algorithm produced the `sgv` value. A reading from xDrip+ using "xDrip Original" calibration is indistinguishable from one using "Native" calibration.

---

## BgReading Data Models

### xDrip+ Android BgReading

```java
@Table(name = "BgReading")
public class BgReading extends Model {
    
    @Column(name = "timestamp", index = true)
    public long timestamp;              // Epoch milliseconds
    
    @Column(name = "calculated_value")
    public double calculated_value;     // Calibrated glucose (mg/dL)
    
    @Column(name = "raw_data")
    public double raw_data;             // Raw sensor signal
    
    @Column(name = "filtered_data")
    public double filtered_data;        // Noise-filtered raw
    
    @Column(name = "noise")
    public String noise;                // Signal quality
    
    @Column(name = "uuid", unique = true)
    public String uuid;                 // Sync identity
    
    // Dexcom native values (when available)
    @Column(name = "dg_mgdl")
    public Double dg_mgdl;              // Dexcom calculated glucose
    
    @Column(name = "dg_slope")
    public Double dg_slope;             // Dexcom trend slope
    
    // Calibration polynomials
    public double a, b, c;              // Forward calibration
    public double ra, rb, rc;           // Reverse calibration
    
    // Source tracking
    @Column(name = "source_info")
    public String source_info;          // Data source identifier
}
```

### xDrip4iOS BgReading (CoreData)

```swift
class BgReading: NSManagedObject {
    @NSManaged var timeStamp: Date
    @NSManaged var calculatedValue: Double    // mg/dL
    @NSManaged var rawData: Double
    @NSManaged var filteredData: Double
    @NSManaged var calculatedValueSlope: Double
    @NSManaged var hideSlope: Bool
    @NSManaged var deviceName: String?
}
```

### Nightscout Entry Format

```json
{
    "_id": "507f1f77bcf86cd799439011",
    "type": "sgv",
    "sgv": 120,
    "direction": "Flat",
    "date": 1705421234567,
    "dateString": "2026-01-16T12:00:34.567Z",
    "device": "xDrip-DexcomG6",
    "noise": 1,
    "filtered": 123456,
    "unfiltered": 125000,
    "rssi": -65
}
```

---

## Upload Patterns

### xDrip+ Android Upload

```java
// UploaderQueue manages multi-destination uploads
public class UploaderQueue extends Model {
    public static final int NIGHTSCOUT = 1;
    public static final int MONGO = 2;
    public static final int INFLUXDB = 4;
    public static final int WATCH = 8;
    public static final int TEST = 16;
    
    public int bitfield_wanted;  // Destinations pending
    public int bitfield_complete; // Destinations completed
}

// BgReading → Nightscout JSON
public JSONObject toNightscoutUpload() {
    JSONObject json = new JSONObject();
    json.put("type", "sgv");
    json.put("sgv", calculated_value);
    json.put("direction", getDirectionString());
    json.put("date", timestamp);
    json.put("dateString", toIso8601(timestamp));
    json.put("device", getDeviceName());
    json.put("noise", noise);
    json.put("filtered", filtered_data);
    json.put("unfiltered", raw_data);
    return json;
}
```

### xDrip4iOS Upload

```swift
func dictionaryRepresentationForNightscoutUpload() -> [String: Any] {
    return [
        "type": "sgv",
        "sgv": Int(calculatedValue),
        "direction": getDirectionString(),
        "date": Int(timeStamp.timeIntervalSince1970 * 1000),
        "dateString": timeStamp.ISOStringFromDate(),
        "device": deviceName ?? "xDrip4iOS"
    ]
}
```

### Upload Identity Fields

| System | Identity Field | Generation | Dedup Strategy |
|--------|---------------|------------|----------------|
| xDrip+ Android | `uuid` | UUID.randomUUID() | Upsert by uuid |
| xDrip4iOS | `uuid` | UUID().uuidString | POST with check |
| AAPS | `interfaceIDs.nightscoutId` | Received from NS | Check before insert |
| Loop | N/A | N/A | Does not upload CGM |
| Trio | `_id` | From Nightscout | Passthrough |

---

## Follower Mode Implementation

### Nightscout Follower

Both xDrip+ and xDrip4iOS support Nightscout as a data source:

```swift
// xDrip4iOS Nightscout Follower
func download() {
    guard UserDefaults.standard.nightscoutEnabled else { return }
    guard !UserDefaults.standard.isMaster else { return }  // Follower only
    
    // Calculate how far back to fetch
    let latestReading = bgReadingsAccessor.getLatestBgReadings(limit: 1)
    let startTime = latestReading?.timeStamp ?? Date(timeIntervalSinceNow: -24*3600)
    
    // Fetch from Nightscout
    let endpoint = "/api/v1/entries/sgv.json?count=\(count)"
    // ... HTTP request
}
```

### AID Integration (Nightscout Follow Types)

xDrip4iOS supports specialized follower modes for AID systems:

```swift
enum NightscoutFollowType: Int {
    case none = 0     // Basic follower (BG only)
    case loop = 1     // Loop/FreeAPS follower
    case openAPS = 2  // OpenAPS/AAPS follower
}
```

When set to `.loop` or `.openAPS`, xDrip4iOS also downloads and displays relevant devicestatus data (IOB, COB, predictions).

### LibreLinkUp Follower (xDrip4iOS Only)

xDrip4iOS can follow LibreLinkUp accounts:

```swift
struct LibreLinkUpRegion {
    case notConfigured  // Global
    case us             // United States
    case eu             // Europe
    case de             // Germany
    // ... 12 regions total
    
    var urlLogin: String {
        "https://api-\(region).libreview.io/llu/auth/login"
    }
}
```

**Authentication Flow**:
1. POST credentials to `/llu/auth/login`
2. Extract `authTicket.token`
3. GET `/llu/connections` to get `patientId`
4. GET `/llu/connections/{patientId}/graph` for readings

### Dexcom Share Follower

Both platforms support Dexcom Share as a follower source:

| Aspect | xDrip+ Android | xDrip4iOS |
|--------|----------------|-----------|
| Service | ShareFollowService | DexcomShareFollowManager |
| Auth | Username/password | Username/password |
| Servers | US/International | US/International toggle |
| Latency | ~5 minutes | ~5 minutes |

---

## xDrip+ Local Web Server

xDrip+ provides Nightscout API emulation on port 17580, enabling local data access.

### Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/sgv.json` | Recent glucose readings | Array of SGV entries |
| `/pebble` | Pebble watchface format | Specialized format |
| `/tasker/{action}` | Tasker integration | Action-specific |

### SGV Response Format

```json
[
    {
        "date": 1705421234567,
        "dateString": "2026-01-16T12:00:34.567Z",
        "sgv": 120,
        "delta": 2.5,
        "direction": "Flat",
        "noise": 1,
        "units_hint": "mgdl",
        "sensor": {
            "age": 432000000,
            "start": 1705000000000
        }
    }
]
```

### Use Cases

1. **AAPS Integration**: Local glucose source without cloud
2. **Watchfaces**: Garmin, Amazfit via HTTP
3. **Automation**: Tasker actions
4. **Debugging**: Local development

---

## Data Provenance Tracking

### Current State

| Field | Tracked In | What It Captures |
|-------|------------|------------------|
| `device` | Nightscout | Free-form source string |
| `source_info` | xDrip+ only | Internal source identifier |
| `enteredBy` | Treatments only | Actor identity (not for entries) |

### Missing Provenance Information

**GAP-CGM-002**: The following provenance information is lost when CGM data reaches Nightscout:

| Missing Field | Impact |
|---------------|--------|
| Calibration algorithm | Cannot determine calibration quality/method |
| Raw value lineage | Cannot recalibrate or validate |
| Bridge device info | MiaoMiao vs Bubble details lost |
| Sensor serial number | Cannot correlate readings to sensor |
| Sensor age at reading | Cannot assess sensor accuracy |

### Proposed Provenance Schema

```json
{
    "sgv": 120,
    "provenance": {
        "transmitter": {
            "type": "dexcom_g6",
            "id": "8GXXXXX"
        },
        "bridge": {
            "type": "miaomiao",
            "firmware": "39"
        },
        "calibration": {
            "algorithm": "xdrip_original",
            "lastCalibration": "2026-01-16T08:00:00Z",
            "slope": 0.85,
            "intercept": 15.2
        },
        "sensor": {
            "serial": "0M00000XXX",
            "ageMinutes": 7200,
            "startDate": "2026-01-11T08:00:00Z"
        },
        "uploader": {
            "app": "xDrip+",
            "version": "2026.01.15",
            "device": "Samsung Galaxy S23"
        }
    }
}
```

---

## Cross-System Comparison

### Data Source Coverage

| Source Type | xDrip+ Android | xDrip4iOS | Loop | Trio | AAPS |
|-------------|----------------|-----------|------|------|------|
| **Direct Dexcom** | Yes (5 types) | Yes (4 types) | Yes | Yes | Via xDrip+ |
| **Direct Libre** | Via bridge | Yes | Via plugin | Via plugin | Via xDrip+ |
| **Bridge devices** | Yes (6+ types) | Yes (4 types) | No | No | Via xDrip+ |
| **Cloud followers** | Yes (4 types) | Yes (3 types) | Share only | Share only | NS only |
| **Companion apps** | Yes (5+ types) | No | No | No | No |
| **Local web server** | Yes | No | No | No | No |
| **Total source types** | 20+ | ~6 | 3-4 | 3-4 | Via xDrip+ |

### Calibration Comparison

| Feature | xDrip+ Android | xDrip4iOS | Loop | AAPS |
|---------|----------------|-----------|------|------|
| **Pluggable algorithms** | Yes (5+) | No | No | No |
| **Native calibration** | Yes | Yes | Yes | Yes |
| **User fingerstick** | Yes | Limited | No | No |
| **WebOOP support** | No | Yes | No | No |
| **Calibration entity** | Full model | N/A | N/A | N/A |

### Upload Behavior

| System | Uploads CGM | Dedup Method | Identity Field |
|--------|-------------|--------------|----------------|
| xDrip+ Android | Yes (primary) | Upsert by uuid | `uuid` |
| xDrip4iOS | Yes | POST with check | `uuid` |
| Loop | No (consumer) | N/A | N/A |
| Trio | No (consumer) | N/A | N/A |
| AAPS | Rebroadcast | Check before insert | `interfaceIDs.nightscoutId` |

---

## Gap Summary

| Gap ID | Description | Impact |
|--------|-------------|--------|
| **GAP-CGM-001** | Calibration algorithm not tracked in NS entries | Cannot determine calibration quality |
| **GAP-CGM-002** | Bridge device info lost in upload | Cannot identify hardware issues |
| **GAP-CGM-003** | Sensor age not standardized | Cannot assess reading reliability |
| **GAP-CGM-004** | No universal source taxonomy | Free-form `device` field unreliable |
| **GAP-CGM-005** | Raw values not uploaded by iOS | Cannot recalibrate or validate |
| **GAP-CGM-006** | Follower source not distinguished | Cannot tell direct vs cloud data |

---

## Suggested Test Specifications

### SPEC-CGM-001: Source Device Attribution

**Protocol**: Uploaded entries should include source device identification.

```yaml
test: source_device_present
given: A CGM entry is uploaded
then:
  - device field is present
  - device is non-empty string
  - device identifies uploader app and hardware
```

### SPEC-CGM-002: Timestamp Freshness

**Protocol**: Uploaded entries should have timestamps within expected CGM interval.

```yaml
test: timestamp_freshness
given: A CGM entry is uploaded
then:
  - date <= current_time
  - date >= current_time - 15_minutes
  - Entries older than 15 minutes flagged as backfill
```

### SPEC-CGM-003: Value Range

**Protocol**: SGV values must be within CGM operational range.

```yaml
test: sgv_value_range
given: A CGM entry with type=sgv
then:
  - sgv >= 39
  - sgv <= 400
  - Values outside range are clipped or marked invalid
```

### SPEC-CGM-004: Direction Calculation

**Protocol**: Direction arrow should reflect glucose change rate.

```yaml
test: direction_consistency
given: Consecutive SGV entries
then:
  - delta > 3 mg/dL/min implies direction IN [DoubleUp, TripleUp]
  - delta < -3 mg/dL/min implies direction IN [DoubleDown, TripleDown]
  - abs(delta) < 1 mg/dL/min implies direction = Flat
```

---

## Suggested Requirements

| Req ID | Statement | Rationale |
|--------|-----------|-----------|
| **REQ-050** | CGM entries MUST include `device` field identifying the uploader | Source attribution for debugging |
| **REQ-051** | CGM timestamps MUST be epoch milliseconds in UTC | Timezone-agnostic storage |
| **REQ-052** | Follower-sourced entries SHOULD indicate follower mode in `device` | Distinguish direct vs cloud data |
| **REQ-053** | Calibration algorithm SHOULD be trackable in entry metadata | Calibration provenance |
| **REQ-054** | Duplicate entries SHOULD be prevented via client UUID | Data integrity |
| **REQ-055** | Raw sensor values SHOULD be preserved when available | Enable recalibration/validation |
| **REQ-056** | Sensor age at reading time SHOULD be tracked | Reading reliability assessment |
| **REQ-057** | Bridge device type SHOULD be distinguishable from transmitter type | Hardware troubleshooting |

---

## Related Documentation

- [Entries Collection Deep Dive](entries-deep-dive.md) - Nightscout entries schema
- [xDrip+ Data Sources](../../mapping/xdrip-android/data-sources.md) - 20+ source types
- [xDrip+ Calibrations](../../mapping/xdrip-android/calibrations.md) - Pluggable algorithms
- [xDrip4iOS CGM Transmitters](../../mapping/xdrip4ios/cgm-transmitters.md) - BLE architecture
- [xDrip4iOS Follower Modes](../../mapping/xdrip4ios/follower-modes.md) - Cloud followers
- [CGM Apps Comparison](../../mapping/cross-project/cgm-apps-comparison.md) - Cross-app matrix
- [Terminology Matrix](../../mapping/cross-project/terminology-matrix.md) - Concept alignment

---

## Changelog

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial creation synthesizing xDrip+, xDrip4iOS, Loop, AAPS CGM data source documentation |
