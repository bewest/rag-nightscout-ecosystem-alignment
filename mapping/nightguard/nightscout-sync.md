# Nightguard Nightscout Synchronization

This document describes how Nightguard communicates with Nightscout servers, including API paths, data fetching patterns, caching strategies, and authentication.

## Overview

Nightguard is primarily a **data consumer** - it reads data from Nightscout for display and alerting. The only write operations are for creating care events (sensor/cannula/battery changes).

## API Endpoints

### Read Operations

| Path | Purpose | Query Parameters |
|------|---------|------------------|
| `GET /api/v2/properties` | Current BG, IOB, COB, battery | (none) |
| `GET /api/v1/status.json` | Units configuration | (none) |
| `GET /api/v1/entries.json` | Historical BG readings | `count`, `find[date][$gt]`, `find[date][$lte]` |
| `GET /api/v1/devicestatus.json` | Pump/Loop status | `count=5` |
| `GET /api/v1/treatments` | Care events, temp targets | `find[eventType]`, `find[created_at][$gte]`, `count` |
| `GET /api/v1/treatments.json` | Latest treatments (simplified) | (none) |

### Write Operations

| Path | Purpose | Body |
|------|---------|------|
| `POST /api/v1/treatments` | Create care events | JSON treatment object |

---

## Primary Data Source: /api/v2/properties

Nightguard uses the V2 properties endpoint as its primary source for current BG data. This endpoint provides a consolidated view of the current state.

**Source**: `nightguard:nightguard/external/NightscoutService.swift#L407-L465`

```swift
func readCurrentData(_ resultHandler: @escaping (NightscoutRequestResult<NightscoutData>) -> Void) -> URLSessionTask? {
    let url = UserDefaultsRepository.getUrlWithPathAndQueryParameters(
        path: "api/v2/properties", 
        queryParams: [:]
    )
    // ...
}
```

### Response Parsing

The response is parsed in `extractApiV2PropertiesData()`:

```swift
// Extract current BG
let sgv = bgnow.object(forKey: "last") as? NSNumber ?? 0
let time = bgnow.object(forKey: "mills") as? NSNumber ?? 0

// Extract battery
let upbat = jsonDict.object(forKey: "upbat") as? NSDictionary
nightscoutData.battery = upbat.object(forKey: "display") as? String ?? "?"

// Extract IOB (append "U" suffix)
let iobDict = jsonDict.object(forKey: "iob") as? NSDictionary
if let iob = iobDict.object(forKey: "display") as? String {
    nightscoutData.iob = String(iob) + "U"
}

// Extract COB (append "g" suffix)
let cobDict = jsonDict.object(forKey: "cob") as? NSDictionary
if let cob = cobDict.object(forKey: "display") as? Double {
    nightscoutData.cob = cob.string(fractionDigits: 0) + "g"
}
```

---

## Historical Data: /api/v1/entries.json

For chart display, Nightguard fetches historical BG readings.

**Source**: `nightguard:nightguard/external/NightscoutService.swift#L167-L281`

### Today's Data

```swift
func readTodaysChartData(oldValues: [BloodSugar], 
                         _ resultHandler: @escaping (NightscoutRequestResult<[BloodSugar]>) -> Void)
```

- Fetches from start of day (minus 1 hour buffer)
- Incremental loading: uses last received timestamp to fetch only new values
- Maximum 1440 entries per request

### Yesterday's Data (Overlay)

```swift
func readYesterdaysChartData(_ resultHandler: @escaping (NightscoutRequestResult<[BloodSugar]>) -> Void)
```

- Fetches full previous day (00:00 to 00:00)
- Timestamps shifted forward 24 hours for overlay display

### Query Parameters

```swift
let chartDataWithinPeriodOfTimeQueryParams = [
    "find[date][$gt]"  : "\(unixTimestamp1)",
    "find[date][$lte]" : "\(unixTimestamp2)",
    "count"            : "1440",
]
```

---

## Device Status: /api/v1/devicestatus.json

For Loop/AAPS integration, Nightguard reads pump status.

**Source**: `nightguard:nightguard/external/NightscoutService.swift#L1147-L1268`

```swift
func readDeviceStatus(resultHandler: @escaping (DeviceStatusData) -> Void) {
    let lastTwoDeviceStatusQuery = ["count": "5"]
    let url = getUrlWithPathAndQueryParameters(
        path: "api/v1/devicestatus.json", 
        queryParams: lastTwoDeviceStatusQuery
    )
    // ...
}
```

### AAPS Device Status Parsing

Nightguard specifically looks for AAPS-format `pump.extended` data:

```swift
if deviceStatus.contains(where: {$0.key == "pump"}) {
    let pumpEntries = deviceStatus["pump"] as? [String:Any]
    let reservoirUnits = pumpEntries["reservoir"] as? Double
    
    if let extendedEntries = pumpEntries["extended"] as? [String:Any] {
        let profile = extendedEntries["ActiveProfile"]
        let baseRate = extendedEntries["BaseBasalRate"]
        let tempRate = extendedEntries["TempBasalAbsoluteRate"]
        let tempRemaining = extendedEntries["TempBasalRemaining"]
    }
}
```

---

## Treatments: /api/v1/treatments

### Reading Care Events

For CAGE/SAGE/BAGE display, Nightguard queries treatments by event type:

**Source**: `nightguard:nightguard/external/NightscoutService.swift#L544-L640`

```swift
func readLastTreatementEventTimestamp(eventType: EventType, 
                                       daysToGoBackInTime: Int,
                                       resultHandler: @escaping (Date) -> Void)
```

### Event Types

```swift
enum EventType: String {
    case sensorStart = "Sensor Change"
    case pumpBatteryChange = "Pump Battery Change"
    case cannulaChange = "Site Change"
    case temporaryTarget = "Temporary Target"
}
```

### Query Parameters

```swift
let lastTreatmentByEventtype = [
    "find[eventType]": eventType.rawValue,
    "find[created_at][$gte]": startDate.convertToIsoDate(),
    "count": "1"
]
```

### Reading Temporary Targets

**Source**: `nightguard:nightguard/external/NightscoutService.swift#L642-L750`

```swift
func readLastTemporaryTarget(daysToGoBackInTime: Int,
                             resultHandler: @escaping (TemporaryTargetData?) -> Void)
```

Parses `targetTop`, `targetBottom`, `duration`, and `created_at` to determine if a temp target is currently active.

---

## Writing Care Events

Nightguard can create three types of care treatments:

### Cannula Change (Site Change)

```swift
func createCannulaChangeTreatment(changeDate: Date, 
                                   resultHandler: @escaping (_ errorMessage: String?) -> Void)
```

### Sensor Change (Sensor Start)

```swift
func createSensorChangeTreatment(changeDate: Date,
                                  resultHandler: @escaping (_ errorMessage: String?) -> Void)
```

### Battery Change (Pump Battery Change)

```swift
func createBatteryChangeTreatment(changeDate: Date,
                                   resultHandler: @escaping (_ errorMessage: String?) -> Void)
```

### Treatment JSON Format

```json
{
  "eventType": "Site Change",
  "enteredBy": "nightguard",
  "created_at": "2026-01-16T10:30:00.000Z",
  "mills": 1705403400000,
  "notes": "",
  "carbs": null,
  "insulin": null
}
```

---

## Caching Strategy

Nightguard implements a multi-layer caching strategy via `NightscoutCacheService`.

**Source**: `nightguard:nightguard/external/NightscoutCacheService.swift`

### Cache Layers

```
┌─────────────────────────────────────────────────────┐
│                 NightscoutCacheService               │
├─────────────────────────────────────────────────────┤
│  In-Memory Cache:                                    │
│  ├── todaysBgData: [BloodSugar]                     │
│  ├── yesterdaysBgData: [BloodSugar]                 │
│  ├── currentNightscoutData: NightscoutData          │
│  └── temporaryTargetData: TemporaryTargetData       │
├─────────────────────────────────────────────────────┤
│  Persistent Cache (UserDefaults):                    │
│  ├── NightscoutDataRepository.storeTodaysBgData()   │
│  ├── NightscoutDataRepository.storeYesterdaysBgData()│
│  └── NightscoutDataRepository.storeCurrentData()     │
└─────────────────────────────────────────────────────┘
```

### Refresh Strategy

| Data Type | Refresh Trigger | Staleness Threshold |
|-----------|-----------------|---------------------|
| Current BG | `isOlderThanYMinutes()` | 5 min (or 1 min if configured) |
| Today's chart | Current data is stale | Same as current BG |
| Yesterday's chart | Day changed | Once per calendar day |
| Device status | App becomes active | Each activation |
| Care data | On demand | 5/14/40 day lookback |
| Temp targets | `isUpToDate()` | 5 minutes |

### Request Deduplication

Nightguard tracks pending requests to avoid duplicate fetches:

```swift
fileprivate var todaysBgDataTasks: [URLSessionTask] = []
fileprivate var yesterdaysBgDataTasks: [URLSessionTask] = []
fileprivate var currentNightscoutDataTasks: [URLSessionTask] = []

var hasTodaysBgDataPendingRequests: Bool {
    serialQueue.sync {
        return todaysBgDataTasks.contains(where: { $0.state == .running })
    }
}
```

### Thread Safety

All cache operations use a serial dispatch queue:

```swift
let serialQueue = DispatchQueue(label: "de.my-wan.dhe.nightscoutCacheServiceSerialQueue")
```

---

## Authentication

Nightguard supports token-based authentication embedded in the base URI.

**URL Construction**: `nightguard:nightguard/repository/UserDefaultsRepository.swift`

### Token Extraction

The token is stored as part of the base URI and extracted for each request:

```
https://your-site.herokuapp.com?token=mytoken-abcd1234
```

### HTTP 401 Handling

Write operations check for 401 responses and display a user-friendly error:

```swift
if let httpResponse = response as? HTTPURLResponse {
    if httpResponse.statusCode == 401 {
        resultHandler(.error(createUnauthorizedError(description:
            NSLocalizedString("You don't have write access to your nightscout site.\n" +
                            "Did you enter a security token in your nightscout base URI?", ...))))
    }
}
```

---

## Error Handling

Nightguard uses a `NightscoutRequestResult<T>` enum for consistent error handling:

```swift
enum NightscoutRequestResult<T> {
    case data(T)
    case error(Error)
}
```

### Error Types

| Error | Cause | User Message |
|-------|-------|--------------|
| Empty URI | No base URI configured | "The base URI is empty or invalid!" |
| 401 Unauthorized | Missing/invalid token | "You don't have write access..." |
| No data | Empty response | "No data received from Nightscout..." |
| Parse error | Invalid JSON | "Invalid JSON received from..." |

---

## Widget/Watch Data Refresh

Widgets and Watch app use the same caching infrastructure but with different refresh patterns.

### Widget Timeline Provider

**Source**: `nightguard:nightguard Widget Extension/NightguardTimelineProvider.swift`

```swift
func getTimeline(in context: Context, completion: @escaping (Timeline<NightscoutDataEntry>) -> Void) {
    getTimelineData { nightscoutDataEntry in
        var entries: [NightscoutDataEntry] = []
        entries.append(nightscoutDataEntry)
        // Refresh after 10 minutes
        completion(Timeline(entries: entries, policy:
            .after(Calendar.current.date(byAdding: .minute, value: 10, to: Date()) ?? Date())))
    }
}
```

### Watch App Refresh

The Watch app uses WatchConnectivity to sync data from the phone, reducing direct network requests:

```swift
WatchMessageService.singleton.onMessage { (message: NightscoutDataMessage) in
    // Process synced data from phone
}
```

---

## Code References

| Purpose | Location |
|---------|----------|
| Main service class | `nightguard:nightguard/external/NightscoutService.swift` |
| Cache service | `nightguard:nightguard/external/NightscoutCacheService.swift` |
| Data repository | `nightguard:nightguard/repository/NightscoutDataRepository.swift` |
| URL construction | `nightguard:nightguard/repository/UserDefaultsRepository.swift` |
| Widget timeline | `nightguard:nightguard Widget Extension/NightguardTimelineProvider.swift` |
