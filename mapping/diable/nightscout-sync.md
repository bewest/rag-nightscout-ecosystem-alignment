# DiaBLE Nightscout Integration

This document describes how DiaBLE integrates with Nightscout for uploading glucose readings and downloading remote data.

## Table of Contents

- [Overview](#overview)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Data Upload](#data-upload)
- [Data Download](#data-download)
- [Data Mapping](#data-mapping)
- [Error Handling](#error-handling)

---

## Overview

**File**: `Nightscout.swift` (273 lines)

DiaBLE supports bidirectional synchronization with Nightscout:

| Direction | Data Type | Endpoint |
|-----------|-----------|----------|
| Upload | Glucose readings | `POST /api/v1/entries` |
| Upload | Calibrations | `POST /api/v1/entries` |
| Upload | Device status | `POST /api/v1/devicestatus` |
| Download | Remote glucose | `GET /api/v1/entries` |
| Download | Server status | `GET /api/v1/status` |

### Nightscout Class

```swift
class Nightscout: ObservableObject, Logging {
    var siteURL: String = ""
    var token: String = ""
    
    var main: MainDelegate!
    
    // Upload/download methods
    func post(_ endpoint: String, _ jsonData: Data) async throws -> Data
    func get(_ endpoint: String) async throws -> Data
    
    func postGlucose(_ values: [Glucose]) async
    func postDeviceStatus() async
    func getServerStatus() async -> ServerStatus?
    func getRemoteGlucose(sinceDate: Date?) async -> [Glucose]
}
```

---

## Configuration

### Settings

```swift
class Settings {
    var nightscoutSite: String = ""      // e.g., "https://yoursite.herokuapp.com"
    var nightscoutToken: String = ""     // API secret token
}
```

### URL Construction

```swift
extension Nightscout {
    var baseURL: URL? {
        guard !siteURL.isEmpty else { return nil }
        var url = siteURL
        if !url.hasPrefix("http") {
            url = "https://" + url
        }
        return URL(string: url)
    }
    
    func buildURL(_ endpoint: String, query: [String: String]? = nil) -> URL? {
        guard let baseURL = baseURL else { return nil }
        var components = URLComponents(url: baseURL.appendingPathComponent(endpoint), 
                                       resolvingAgainstBaseURL: false)
        
        // Add token as query parameter
        var queryItems = [URLQueryItem(name: "token", value: token)]
        if let query = query {
            queryItems += query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        components?.queryItems = queryItems
        
        return components?.url
    }
}
```

---

## API Endpoints

### Entries API

Used for glucose readings and calibrations.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/entries` | Download glucose history |
| GET | `/api/v1/entries/sgv.json` | Download SGV entries |
| POST | `/api/v1/entries` | Upload glucose readings |

### Device Status API

Used for reporting app/device information.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/devicestatus` | Get device status history |
| POST | `/api/v1/devicestatus` | Upload device status |

### Status API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/status` | Server configuration and status |

---

## Data Upload

### Uploading Glucose Readings

```swift
func postGlucose(_ values: [Glucose]) async {
    guard !values.isEmpty else { return }
    
    // Convert DiaBLE Glucose to Nightscout entry format
    let entries: [[String: Any]] = values.map { glucose in
        [
            "type": "sgv",
            "sgv": glucose.value,
            "direction": glucose.trendArrow.nightscoutDirection,
            "date": Int(glucose.date.timeIntervalSince1970 * 1000),
            "dateString": ISO8601DateFormatter().string(from: glucose.date),
            "device": "DiaBLE"
        ]
    }
    
    do {
        let jsonData = try JSONSerialization.data(withJSONObject: entries)
        _ = try await post("/api/v1/entries", jsonData)
        log("Nightscout: uploaded \(values.count) glucose entries")
    } catch {
        log("Nightscout: upload failed - \(error)")
    }
}
```

### Entry Format

```json
{
  "type": "sgv",
  "sgv": 120,
  "direction": "Flat",
  "date": 1705449600000,
  "dateString": "2024-01-17T00:00:00.000Z",
  "device": "DiaBLE"
}
```

### Uploading Device Status

```swift
func postDeviceStatus() async {
    let status: [String: Any] = [
        "device": "DiaBLE",
        "created_at": ISO8601DateFormatter().string(from: Date()),
        "uploader": [
            "battery": main.app.device?.battery ?? 0
        ],
        "pump": [:],  // Not applicable
        "sensor": main.app.sensor != nil ? [
            "sensorAge": main.app.sensor!.age,
            "sensorState": main.app.sensor!.state.description
        ] : [:]
    ]
    
    do {
        let jsonData = try JSONSerialization.data(withJSONObject: status)
        _ = try await post("/api/v1/devicestatus", jsonData)
    } catch {
        log("Nightscout: device status upload failed - \(error)")
    }
}
```

### Device Status Format

```json
{
  "device": "DiaBLE",
  "created_at": "2024-01-17T00:00:00.000Z",
  "uploader": {
    "battery": 85
  },
  "sensor": {
    "sensorAge": 4320,
    "sensorState": "Ready"
  }
}
```

---

## Data Download

### Downloading Glucose History

```swift
func getRemoteGlucose(sinceDate: Date? = nil) async -> [Glucose] {
    var query: [String: String] = [
        "count": "288"  // ~24 hours at 5-min intervals
    ]
    
    if let sinceDate = sinceDate {
        let timestamp = Int(sinceDate.timeIntervalSince1970 * 1000)
        query["find[date][$gt]"] = String(timestamp)
    }
    
    guard let url = buildURL("/api/v1/entries/sgv.json", query: query),
          let data = try? await get(url.absoluteString) else {
        return []
    }
    
    do {
        let entries = try JSONDecoder().decode([NightscoutEntry].self, from: data)
        return entries.map { entry in
            Glucose(
                id: entry.date / 1000,
                date: Date(timeIntervalSince1970: Double(entry.date) / 1000),
                rawValue: entry.sgv,
                value: entry.sgv,
                trendArrow: TrendArrow(nightscoutDirection: entry.direction)
            )
        }
    } catch {
        log("Nightscout: parsing entries failed - \(error)")
        return []
    }
}
```

### NightscoutEntry Model

```swift
struct NightscoutEntry: Codable {
    let _id: String?
    let type: String
    let sgv: Int
    let direction: String?
    let date: Int                    // Unix timestamp in milliseconds
    let dateString: String?
    let device: String?
    let filtered: Int?
    let unfiltered: Int?
    let rssi: Int?
    let noise: Int?
}
```

### Getting Server Status

```swift
struct ServerStatus: Codable {
    let status: String
    let name: String
    let version: String
    let serverTime: String
    let serverTimeEpoch: Int
    let settings: ServerSettings
}

struct ServerSettings: Codable {
    let units: String               // "mg/dl" or "mmol"
    let timeFormat: Int             // 12 or 24
    let theme: String
    let enable: [String]            // Enabled plugins
}

func getServerStatus() async -> ServerStatus? {
    guard let url = buildURL("/api/v1/status") else { return nil }
    
    do {
        let data = try await get(url.absoluteString)
        return try JSONDecoder().decode(ServerStatus.self, from: data)
    } catch {
        log("Nightscout: failed to get server status - \(error)")
        return nil
    }
}
```

---

## Data Mapping

### Trend Arrow Mapping

DiaBLE trend arrows map to Nightscout direction strings:

| DiaBLE TrendArrow | Nightscout Direction |
|-------------------|---------------------|
| `.fallingQuickly` | "DoubleDown" |
| `.falling` | "SingleDown" |
| `.stable` | "Flat" |
| `.rising` | "SingleUp" |
| `.risingQuickly` | "DoubleUp" |
| `.notDetermined` | "NOT COMPUTABLE" |
| `.unknown` | "NONE" |

```swift
extension TrendArrow {
    var nightscoutDirection: String {
        switch self {
        case .fallingQuickly: return "DoubleDown"
        case .falling:        return "SingleDown"
        case .stable:         return "Flat"
        case .rising:         return "SingleUp"
        case .risingQuickly:  return "DoubleUp"
        case .notDetermined:  return "NOT COMPUTABLE"
        default:              return "NONE"
        }
    }
    
    init(nightscoutDirection: String?) {
        switch nightscoutDirection {
        case "DoubleDown":      self = .fallingQuickly
        case "SingleDown":      self = .falling
        case "FortyFiveDown":   self = .falling
        case "Flat":            self = .stable
        case "FortyFiveUp":     self = .rising
        case "SingleUp":        self = .rising
        case "DoubleUp":        self = .risingQuickly
        case "NOT COMPUTABLE":  self = .notDetermined
        default:                self = .unknown
        }
    }
}
```

### Glucose Unit Conversion

```swift
extension Glucose {
    /// Convert mg/dL to mmol/L
    var mmolL: Double {
        return Double(value) / 18.0182
    }
    
    /// Format for display based on unit preference
    func formatted(inMmol: Bool) -> String {
        if inMmol {
            return String(format: "%.1f", mmolL)
        } else {
            return String(value)
        }
    }
}
```

### Entry Type Mapping

| DiaBLE Data | Nightscout Type | Collection |
|-------------|-----------------|------------|
| Glucose reading | `sgv` | entries |
| Calibration | `cal` | entries |
| Sensor info | - | devicestatus |
| Device battery | - | devicestatus |

---

## Error Handling

### HTTP Request Method

```swift
func request(_ method: String, _ endpoint: String, 
             _ body: Data? = nil) async throws -> Data {
    guard let url = buildURL(endpoint) else {
        throw NightscoutError.invalidURL
    }
    
    var request = URLRequest(url: url)
    request.httpMethod = method
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    
    // Add API secret hash for write operations
    if method != "GET" {
        let secretHash = token.sha1()
        request.setValue(secretHash, forHTTPHeaderField: "api-secret")
    }
    
    if let body = body {
        request.httpBody = body
    }
    
    let (data, response) = try await URLSession.shared.data(for: request)
    
    guard let httpResponse = response as? HTTPURLResponse else {
        throw NightscoutError.invalidResponse
    }
    
    switch httpResponse.statusCode {
    case 200..<300:
        return data
    case 401:
        throw NightscoutError.unauthorized
    case 404:
        throw NightscoutError.notFound
    default:
        throw NightscoutError.serverError(httpResponse.statusCode)
    }
}
```

### Error Types

```swift
enum NightscoutError: LocalizedError {
    case invalidURL
    case invalidResponse
    case unauthorized
    case notFound
    case serverError(Int)
    case parsingError
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid Nightscout URL"
        case .unauthorized:
            return "Invalid API token"
        case .notFound:
            return "Endpoint not found"
        case .serverError(let code):
            return "Server error: \(code)"
        case .parsingError:
            return "Failed to parse response"
        default:
            return "Unknown error"
        }
    }
}
```

### Retry Logic

```swift
func postWithRetry(_ endpoint: String, _ data: Data, retries: Int = 3) async throws {
    var lastError: Error?
    
    for attempt in 1...retries {
        do {
            _ = try await post(endpoint, data)
            return
        } catch {
            lastError = error
            log("Nightscout: attempt \(attempt) failed - \(error)")
            
            // Exponential backoff
            if attempt < retries {
                try await Task.sleep(nanoseconds: UInt64(pow(2.0, Double(attempt))) * 1_000_000_000)
            }
        }
    }
    
    throw lastError ?? NightscoutError.serverError(0)
}
```

---

## Integration Flow

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                      DiaBLE ←→ Nightscout Data Flow                            │
└───────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐    Parse     ┌─────────────┐    Convert    ┌─────────────────────┐
│ CGM Sensor  │ ──────────▶  │   Glucose   │ ───────────▶  │ Nightscout Entry    │
│ (NFC/BLE)   │              │   Array     │               │ JSON Array          │
└─────────────┘              └─────────────┘               └──────────┬──────────┘
                                                                      │
                                                                      ▼
                                                           POST /api/v1/entries
                                                                      │
                                                                      ▼
                                                           ┌─────────────────────┐
                                                           │ Nightscout Server   │
                                                           │                     │
                                                           │ - Store in MongoDB  │
                                                           │ - WebSocket notify  │
                                                           │ - Trigger alarms    │
                                                           └──────────┬──────────┘
                                                                      │
                                                                      ▼
                                                           GET /api/v1/entries
                                                                      │
                                                                      ▼
┌─────────────┐    Display   ┌─────────────┐    Parse     ┌─────────────────────┐
│  Follower   │ ◀──────────  │   Remote    │ ◀──────────  │ NightscoutEntry     │
│    View     │              │   Glucose   │              │ JSON Response       │
└─────────────┘              └─────────────┘              └─────────────────────┘
```

---

## Related Documentation

- [data-models.md](data-models.md) - Glucose and Sensor data structures
- [cgm-transmitters.md](cgm-transmitters.md) - How sensor data is acquired
- [xDrip4iOS Nightscout Sync](../xdrip4ios/nightscout-sync.md) - Similar implementation in xDrip4iOS
