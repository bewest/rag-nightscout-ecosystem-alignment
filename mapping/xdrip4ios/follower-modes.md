# xDrip4iOS Follower Modes

This document details how xDrip4iOS implements follower functionality to consume glucose data from remote sources.

---

## Overview

xDrip4iOS supports multiple follower data sources for remote CGM monitoring:

```swift
// xdrip:xdrip/Managers/Followers/FollowerDataSourceType.swift#L33-L43
public enum FollowerDataSourceType: Int, CaseIterable {
    case nightscout = 0
    case libreLinkUp = 1
    case libreLinkUpRussia = 2
    case dexcomShare = 3
}
```

---

## Nightscout Follower

### Source Files

- `xdrip/Managers/Nightscout/NightscoutFollowManager.swift` (~471 lines)
- `xdrip/Managers/Nightscout/NightscoutFollowType.swift` (~65 lines)

### API Endpoint

```swift
// xdrip:xdrip/Managers/Nightscout/Endpoint+Nightscout.swift#L37
"/api/v1/entries/sgv.json"
```

### Query Parameters

```swift
// xdrip:xdrip/Managers/Nightscout/Endpoint+Nightscout.swift#L27-L32
var queryItems = [URLQueryItem(name: "count", value: count.description)]

if let token = token {
    queryItems.append(URLQueryItem(name: "token", value: token))
}
```

### Download Logic

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutFollowManager.swift#L123-L175
@objc public func download() {
    // Guard checks
    guard UserDefaults.standard.nightscoutEnabled else { return }
    guard !UserDefaults.standard.isMaster else { return }
    guard UserDefaults.standard.followerDataSourceType == .nightscout else { return }
    guard let nightscoutUrl = UserDefaults.standard.nightscoutUrl else { return }
    
    // Calculate time range
    var timeStampOfFirstBgReadingToDowload = Date(timeIntervalSinceNow: 
        TimeInterval(-Double(ConstantsFollower.maxiumDaysOfReadingsToDownload) * 24.0 * 3600.0))
    
    // Check latest local reading
    let latestBgReadings = bgReadingsAccessor.getLatestBgReadings(limit: nil, howOld: 1, ...)
    if latestBgReadings.count > 0 {
        timeStampOfFirstBgReadingToDowload = max(
            latestBgReadings[0].timeStamp, 
            timeStampOfFirstBgReadingToDowload
        )
    }
    
    // Skip if recent reading exists (< 30 seconds old)
    guard abs(timeStampOfFirstBgReadingToDowload.timeIntervalSinceNow) > 30.0 else {
        return
    }
    
    // Calculate count (assuming 5-minute intervals)
    let count = Int(-timeStampOfFirstBgReadingToDowload.timeIntervalSinceNow / 300 + 1)
    
    // Create endpoint and fetch
    let endpoint = Endpoint.getEndpointForLatestNSEntries(
        hostAndScheme: nightscoutUrl,
        count: count,
        token: UserDefaults.standard.nightscoutToken
    )
    
    // Parse response and create BgReading objects
}
```

### BgReading Creation (Follower)

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutFollowManager.swift#L103-L118
public func createBgReading(followGlucoseData: FollowerBgReading) -> BgReading {
    let bgReading = BgReading(
        timeStamp: followGlucoseData.timeStamp,
        sensor: nil,               // No sensor in follower mode
        calibration: nil,          // No calibration in follower mode
        rawData: followGlucoseData.sgv,  // SGV used as rawData
        deviceName: nil,
        nsManagedObjectContext: coreDataManager.mainManagedObjectContext
    )

    bgReading.calculatedValue = followGlucoseData.sgv
    
    // Calculate slope from previous readings
    let (calculatedValueSlope, hideSlope) = findSlope()
    bgReading.calculatedValueSlope = calculatedValueSlope
    bgReading.hideSlope = hideSlope
    
    return bgReading
}
```

### Nightscout Follow Types (AID Integration)

For users with automated insulin delivery systems:

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutFollowType.swift#L14-L27
@objc public enum NightscoutFollowType: Int, CaseIterable, Codable {
    case none = 0     // Basic follower (BG only)
    case loop = 1     // Loop/FreeAPS follower
    case openAPS = 2  // OpenAPS/AAPS follower
}
```

When set to `.loop` or `.openAPS`, xDrip4iOS also downloads and displays devicestatus data relevant to that AID system.

---

## LibreLinkUp Follower

### Source Files

- `xdrip/Managers/LibreLinkUp/LibreLinkUpFollowManager.swift` (~47KB)
- `xdrip/Managers/LibreLinkUp/LibreLinkUpModels.swift` (~264 lines)

### Region Support

```swift
// xdrip:xdrip/Managers/LibreLinkUp/LibreLinkUpModels.swift#L14-L31
public enum LibreLinkUpRegion: Int, CaseIterable {
    case notConfigured = 0  // Global
    case ae = 1   // United Arab Emirates
    case ap = 2   // Asia/Pacific
    case au = 3   // Australia
    case ca = 4   // Canada
    case de = 5   // Germany
    case eu = 6   // Europe
    case eu2 = 7  // Great Britain
    case fr = 8   // France
    case jp = 9   // Japan
    case la = 10  // Latin America
    case us = 11  // United States
}
```

### API Endpoints

```swift
// xdrip:xdrip/Managers/LibreLinkUp/LibreLinkUpModels.swift#L99-L138
var urlLogin: String {
    switch self {
    case .notConfigured:
        return "https://api.libreview.io/llu/auth/login"
    default:
        return "https://api-\(self).libreview.io/llu/auth/login"
    }
}

var urlConnections: String {
    // Similar pattern: https://api-{region}.libreview.io/llu/connections
}

func urlGraph(patientId: String) -> String {
    // https://api-{region}.libreview.io/llu/connections/{patientId}/graph
}
```

### Russia-Specific Endpoints

```swift
// For .libreLinkUpRussia data source type
"https://api.libreview.ru/llu/auth/login"
"https://api.libreview.ru/llu/connections"
"https://api.libreview.ru/llu/connections/{patientId}/graph"
```

### Authentication Flow

1. **Login**: POST to `/llu/auth/login` with credentials
2. **Get Auth Token**: Extract `authTicket.token` from response
3. **Get Connections**: GET `/llu/connections` to get `patientId`
4. **Get Graph Data**: GET `/llu/connections/{patientId}/graph` for readings

### Response Models

```swift
// xdrip:xdrip/Managers/LibreLinkUp/LibreLinkUpModels.swift#L176-L263

// Login Response
struct RequestLoginResponse: Codable {
    let user: RequestLoginResponseUser?
    let authTicket: RequestLoginResponseAuthTicket?
    let redirect: Bool?   // True if wrong region
    let region: String?   // Correct region if redirect
}

// Graph Response (glucose data)
struct RequestGraphResponse: Codable {
    let connection: RequestGraphResponseConnection?
    let activeSensors: [RequestGraphResponseActiveSensors]?
    let graphData: [RequestGraphResponseGlucoseMeasurement]?
}

// Glucose Measurement
struct RequestGraphResponseGlucoseMeasurement: Codable {
    let FactoryTimestamp: Date    // UTC timestamp
    let ValueInMgPerDl: Double    // Glucose in mg/dL
}

// Sensor Info
struct RequestGraphResponseSensor: Codable {
    let sn: String   // Serial number
    let a: Double    // Sensor start date (epoch)
}
```

### Region Auto-Detection

LibreLinkUp can redirect to correct region:

```swift
// If redirect == true && region != nil
// Automatically switch to correct region and retry
init?(from string: String) {
    switch string.lowercased() {
    case "ae": self = .ae
    case "ap": self = .ap
    // ... etc
    }
}
```

---

## Dexcom Share Follower

### Data Source Type

```swift
case dexcomShare = 3
```

### Configuration Requirements

| Property | Description |
|----------|-------------|
| Username | Dexcom account email |
| Password | Dexcom account password |
| Use US Servers | Toggle for US vs international |

---

## Follower Data Source Comparison

| Feature | Nightscout | LibreLinkUp | DexcomShare |
|---------|-----------|-------------|-------------|
| **Authentication** | API_SECRET or Token | Username/Password | Username/Password |
| **Data Freshness** | Real-time (depends on uploader) | ~1-3 min delay | ~5 min delay |
| **BG History** | Configurable (days) | Limited | Limited |
| **Requires Account** | NS site | Abbott account | Dexcom account |
| **Regions** | N/A | Multiple | US/International |
| **AID Integration** | Yes (Loop/OpenAPS) | No | No |

---

## Disconnect Warning Thresholds

```swift
// xdrip:xdrip/Managers/Followers/FollowerDataSourceType.swift#L102-L111
var secondsUntilFollowerDisconnectWarning: Int {
    switch self {
    case .nightscout:
        return ConstantsFollower.secondsUntilFollowerDisconnectWarningNightscout
    case .libreLinkUp, .libreLinkUpRussia:
        return ConstantsFollower.secondsUntilFollowerDisconnectWarningLibreLinkUp
    case .dexcomShare:
        return ConstantsFollower.secondsUntilFollowerDisconnectWarningDexcomShare
    }
}
```

---

## Service Status Monitoring

xDrip4iOS can check service health status:

```swift
// xdrip:xdrip/Managers/Followers/FollowerDataSourceType.swift#L137-L167
func hasServiceStatus() -> Bool {
    return true  // All sources support status check
}

func serviceStatusBaseUrlString(nightscoutUrl: String? = "") -> String {
    switch self {
    case .nightscout:
        return nightscoutUrl ?? ""
    case .dexcomShare:
        return ConstantsFollower.followerStatusDexcomBaseUrl
    case .libreLinkUp, .libreLinkUpRussia:
        return ConstantsFollower.followerStatusAbbottBaseUrl
    }
}

func serviceStatusApiPathString() -> String {
    switch self {
    case .nightscout:
        return ConstantsFollower.followerStatusNightscoutApiPath  // /api/v1/status.json
    case .dexcomShare, .libreLinkUp, .libreLinkUpRussia:
        return ConstantsFollower.followerStatusAtlassianApiPath   // Atlassian Statuspage
    }
}
```

---

## Background Keep-Alive

```swift
// xdrip:xdrip/Managers/Followers/FollowerBackgroundKeepAliveType.swift
enum FollowerBackgroundKeepAliveType {
    // Options for keeping app alive in background for follower mode
    // Uses silent audio playback or other iOS background modes
}
```

---

## Follower Mode Upload Control

Follower mode can optionally upload data to Nightscout (e.g., from LibreLinkUp to NS):

```swift
// UserDefaults.standard.followerUploadDataToNightscout

// Upload is blocked if:
// 1. Follower source IS Nightscout (would create loop)
// 2. followerUploadDataToNightscout is false
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    FOLLOWER MODE DATA FLOW                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐        │
│  │  Nightscout  │     │ LibreLinkUp  │     │ DexcomShare  │        │
│  │   Server     │     │   API        │     │   API        │        │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘        │
│         │                    │                    │                 │
│         │ GET /entries       │ GET /graph         │ GET readings    │
│         │                    │                    │                 │
│         ▼                    ▼                    ▼                 │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐        │
│  │ Nightscout   │     │ LibreLinkUp  │     │ DexcomShare  │        │
│  │FollowManager │     │FollowManager │     │FollowManager │        │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘        │
│         │                    │                    │                 │
│         └────────────────────┼────────────────────┘                 │
│                              │                                      │
│                              ▼                                      │
│                   ┌─────────────────────┐                           │
│                   │ FollowerBgReading   │                           │
│                   │  - timeStamp        │                           │
│                   │  - sgv              │                           │
│                   └──────────┬──────────┘                           │
│                              │                                      │
│                              ▼ createBgReading()                    │
│                   ┌─────────────────────┐                           │
│                   │ BgReading (CoreData)│                           │
│                   │  - calculatedValue  │                           │
│                   │  - calculatedSlope  │                           │
│                   └──────────┬──────────┘                           │
│                              │                                      │
│           ┌──────────────────┼──────────────────┐                   │
│           ▼                  ▼                  ▼                   │
│     ┌──────────┐      ┌──────────┐       ┌──────────┐              │
│     │   UI     │      │ HealthKit│       │ Optional │              │
│     │ Display  │      │  Storage │       │ NS Upload│              │
│     └──────────┘      └──────────┘       └──────────┘              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Code References

| Component | File | Purpose |
|-----------|------|---------|
| FollowerDataSourceType | `Managers/Followers/FollowerDataSourceType.swift` | Follower source enum |
| NightscoutFollowManager | `Managers/Nightscout/NightscoutFollowManager.swift` | NS follower logic |
| NightscoutFollowType | `Managers/Nightscout/NightscoutFollowType.swift` | AID follow types |
| LibreLinkUpFollowManager | `Managers/LibreLinkUp/LibreLinkUpFollowManager.swift` | LLU follower logic |
| LibreLinkUpModels | `Managers/LibreLinkUp/LibreLinkUpModels.swift` | LLU data models |
| FollowerBgReading | `Managers/Followers/FollowerBgReading.swift` | Intermediate BG model |
