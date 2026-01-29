# LoopFollow Deep Dive

> **Source**: `externals/LoopFollow/`  
> **Last Updated**: 2026-01-29  
> **Version**: 2.x (maintained by Loop and Learn)

## Overview

LoopFollow is an iOS/watchOS caregiver monitoring app that aggregates data from multiple diabetes management sources into a single view. It consumes Nightscout API data to display CGM readings, insulin dosing, carbs, predictions, and AID system status.

| Aspect | Details |
|--------|---------|
| **Language** | Swift (iOS/watchOS) |
| **Maintainer** | Loop and Learn community |
| **Original Author** | Jon Fawcett |
| **License** | MIT |
| **Platforms** | iOS, watchOS |
| **Data Sources** | Nightscout, Dexcom Share |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         LoopFollow                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │ Controllers  │   │   Remote     │   │   Helpers    │        │
│  │  /Nightscout │   │   Commands   │   │              │        │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘        │
│         │                  │                   │                │
│         ▼                  ▼                   ▼                │
│  ┌─────────────────────────────────────────────────────┐       │
│  │                  NightscoutUtils                     │       │
│  │  • executeRequest()                                  │       │
│  │  • executeDynamicRequest()                           │       │
│  │  • constructURL()                                    │       │
│  └─────────────────────────────────────────────────────┘       │
│                            │                                    │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │       Nightscout API v1      │
              │  • /api/v1/entries.json      │
              │  • /api/v1/treatments.json   │
              │  • /api/v1/devicestatus.json │
              │  • /api/v1/profile/current   │
              │  • /api/v1/status.json       │
              └──────────────────────────────┘
```

---

## Directory Structure

```
LoopFollow/
├── LoopFollow/
│   ├── Controllers/
│   │   └── Nightscout/           # Nightscout data fetchers
│   │       ├── BGData.swift          # SGV entries
│   │       ├── DeviceStatus.swift    # devicestatus parsing
│   │       ├── DeviceStatusLoop.swift    # Loop-specific parsing
│   │       ├── DeviceStatusOpenAPS.swift # OpenAPS/Trio parsing
│   │       ├── Treatments.swift      # Treatment fetcher
│   │       ├── Profile.swift         # Profile fetcher
│   │       ├── ProfileManager.swift  # Profile caching
│   │       └── Treatments/           # Per-type processors
│   │           ├── Bolus.swift
│   │           ├── Carbs.swift
│   │           ├── Basals.swift
│   │           ├── Overrides.swift
│   │           ├── TemporaryTarget.swift
│   │           └── ...
│   ├── Remote/                   # Remote command support
│   │   ├── LoopAPNS/             # Loop APNS commands
│   │   ├── Nightscout/           # NS-based commands (Trio)
│   │   └── TRC/                  # Trio Remote Control
│   ├── Helpers/
│   │   └── NightscoutUtils.swift # API request utilities
│   └── Nightscout/               # NS settings UI
└── Tests/
```

---

## Nightscout API Usage

### Endpoints Used

| Endpoint | Purpose | Parameters |
|----------|---------|------------|
| `GET /api/v1/entries.json` | CGM readings | `count`, `find[dateString][$gte]`, `find[type][$ne]` |
| `GET /api/v1/treatments.json` | Treatments | `find[created_at][$gte]`, `find[created_at][$lte]` |
| `GET /api/v1/devicestatus.json` | AID status | `count=1` |
| `GET /api/v1/profile/current.json` | Active profile | (none) |
| `GET /api/v1/status.json` | Site status | (none) |
| `POST /api/v2/notifications/loop` | Remote commands | Override payloads |

**Source**: `LoopFollow/Helpers/NightscoutUtils.swift`

### Authentication

- Uses `token` query parameter for authentication
- Stored in `Storage.shared.token.value`

```swift
static func constructURL(baseURL: String, token: String, endpoint: String, parameters: [String: String]) -> URL? {
    var urlComponents = URLComponents(string: baseURL + endpoint)
    var queryItems = parameters.map { URLQueryItem(name: $0.key, value: $0.value) }
    if !token.isEmpty {
        queryItems.append(URLQueryItem(name: "token", value: token))
    }
    urlComponents?.queryItems = queryItems
    return urlComponents?.url
}
```

---

## Data Consumption

### CGM Data (Entries)

**Source**: `LoopFollow/Controllers/Nightscout/BGData.swift`

Fetches SGV entries from Nightscout with fallback to Dexcom Share:

```swift
// Query parameters
parameters["count"] = "\(downloadDays * 2 * 24 * 60 / 5)"
parameters["find[dateString][$gte]"] = utcISODateFormatter.string(from: date)
parameters["find[type][$ne]"] = "cal"  // Exclude calibrations
```

**Data Flow**:
1. Try Dexcom Share first (if configured)
2. If Share data is stale (>5.5 min) or incomplete, fetch from Nightscout
3. Merge Dex + NS data if both sources used

**Timestamp Handling**:
- NS returns `date` in milliseconds
- Converts to seconds: `nsData[i].date /= 1000`

### Treatments

**Source**: `LoopFollow/Controllers/Nightscout/Treatments.swift`

Fetches and categorizes treatments by eventType:

| eventType | Processor |
|-----------|-----------|
| `Temp Basal` | `processNSBasals()` |
| `Correction Bolus`, `Bolus`, `External Insulin` | `processNSBolus()` |
| `SMB` | `processNSSmb()` |
| `Meal Bolus`, `Carb Correction` | `processNSCarbs()` |
| `Temporary Override`, `Exercise` | `Overrides.swift` |
| `Temporary Target` | `TemporaryTarget.swift` |
| `Note` | `Notes.swift` |
| `BG Check` | `BGCheck.swift` |
| `Suspend Pump`, `Resume Pump` | `SuspendPump.swift`, `ResumePump.swift` |
| `Pump Site Change`, `Site Change` | `SiteChange.swift` |
| `Sensor Start` | `SensorStart.swift` |
| `Insulin Change` | `InsulinCartridgeChange.swift` |

### DeviceStatus

**Source**: `LoopFollow/Controllers/Nightscout/DeviceStatus.swift`

Fetches latest devicestatus and routes to appropriate parser:

```swift
// Fetch most recent devicestatus
let parameters = ["count": "1"]
NightscoutUtils.executeDynamicRequest(eventType: .deviceStatus, parameters: parameters)
```

**System Detection**:
- **Loop**: Contains `loop` key in devicestatus
- **OpenAPS/Trio**: Contains `openaps` key in devicestatus

### DeviceStatus: Loop Format

**Source**: `LoopFollow/Controllers/Nightscout/DeviceStatusLoop.swift`

Extracts from Loop devicestatus:

| Field Path | Display |
|------------|---------|
| `loop.iob.iob` | IOB |
| `loop.cob.cob` | COB |
| `loop.predicted.values` | Prediction curve |
| `loop.enacted` | Loop enacted decision |
| `loop.failureReason` | Loop failure indicator |
| `override.active` | Override status |

### DeviceStatus: OpenAPS/Trio Format

**Source**: `LoopFollow/Controllers/Nightscout/DeviceStatusOpenAPS.swift`

Extracts from OpenAPS/Trio devicestatus:

| Field Path | Display |
|------------|---------|
| `openaps.iob.iob` | IOB |
| `openaps.suggested.COB` or `enacted.COB` | COB |
| `openaps.suggested.predBGs` | Multiple prediction curves |
| `openaps.enacted` | Enacted decision |
| `device` | Device identifier |

**Prediction Curves** (OpenAPS-specific):
- `IOB` - Insulin-only prediction
- `COB` - Carb absorption prediction
- `UAM` - Unannounced meal prediction
- `ZT` - Zero temp prediction

---

## Remote Command Support

### Remote Types

**Source**: `LoopFollow/Remote/RemoteType.swift`

```swift
enum RemoteType: String, Codable {
    case none = "None"
    case nightscout = "Nightscout"
    case trc = "Trio Remote Control"
    case loopAPNS = "Loop APNS"
}
```

### Loop APNS Commands

**Source**: `LoopFollow/Remote/LoopAPNS/`

Uses Apple Push Notification Service for remote commands:
- Requires Apple Developer account
- Push notifications to Loop app

### Trio Remote Control (TRC)

**Source**: `LoopFollow/Remote/TRC/`

Uses Nightscout notifications endpoint for Trio:
- `POST /api/v2/notifications/loop`
- Sends override commands

### Nightscout Commands (Trio)

**Source**: `LoopFollow/Remote/Nightscout/`

Direct Nightscout treatment posting for Trio:
- Override enable/cancel
- Temporary targets

---

## Profile Consumption

**Source**: `LoopFollow/Controllers/Nightscout/Profile.swift`, `ProfileManager.swift`

Fetches active profile for display:

| Profile Field | Usage |
|--------------|-------|
| `basal` | Basal rate display |
| `carbratio` | CR display |
| `sens` | ISF display |
| `target_low`, `target_high` | Target range display |
| `units` | mg/dL or mmol/L |

---

## Multi-Source Data

### Dexcom Share Integration

**Source**: `LoopFollow/Controllers/Nightscout/BGData.swift`

LoopFollow can fetch CGM directly from Dexcom Share:
- Used as primary source if configured
- Falls back to Nightscout if Share data is stale

```swift
if (latestDate + 330) < now, IsNightscoutEnabled() {
    // Dexcom data is old, loading from NS instead
    self.webLoadNSBGData()
}
```

### Data Priority

1. **Dexcom Share** (if configured and data is fresh)
2. **Nightscout** (fallback or for extended history)
3. **Merge** both for historical views

---

## Gaps Identified

### GAP-LOOPFOLLOW-001: API v1 Only

**Description**: LoopFollow uses Nightscout API v1 exclusively. No v3 API support.

**Impact**:
- Cannot leverage v3 features (identifiers, server-side filtering)
- No sync identity awareness
- May miss real-time updates available in v3

**Source**: `LoopFollow/Helpers/NightscoutUtils.swift:49-61`

### GAP-LOOPFOLLOW-002: No WebSocket/Server-Sent Events

**Description**: LoopFollow uses polling for data updates. No real-time push support.

**Impact**:
- Delays between data availability and display
- Higher battery/network usage from polling
- Configurable interval helps but not real-time

**Source**: Multiple polling schedulers in Controllers

### GAP-LOOPFOLLOW-003: Treatment eventType Hardcoding

**Description**: Treatment categorization relies on exact string matching of eventTypes.

**Impact**:
- New eventTypes from Loop/Trio/AAPS may be missed
- `default` case logs but doesn't display
- Requires code update for new treatment types

**Source**: `LoopFollow/Controllers/Nightscout/Treatments.swift:55-100`

---

## Comparison with Other Caregiving Apps

| Feature | LoopFollow | LoopCaregiver | Nightscout Web |
|---------|------------|---------------|----------------|
| **Platform** | iOS/watchOS | iOS | Web |
| **CGM Display** | ✅ | ✅ | ✅ |
| **Loop Status** | ✅ | ✅ | ✅ |
| **Predictions** | ✅ (single/multi) | ✅ | ✅ |
| **Remote Bolus** | Via APNS | ✅ | ❌ |
| **Remote Carbs** | Via NS | ✅ | ✅ |
| **Remote Override** | ✅ | ✅ | Limited |
| **Dexcom Share** | ✅ | ❌ | Via bridge |
| **Multi-Looper** | ✅ (3 instances) | ❌ | ✅ |

---

## Configuration

### Environment/Settings

| Setting | Purpose |
|---------|---------|
| `url` | Nightscout URL |
| `token` | API token |
| `downloadDays` | History depth (days) |
| `downloadTreatments` | Enable treatment fetch |
| `downloadPrediction` | Enable prediction display |
| `remoteType` | Remote command method |

### Multi-Instance Support

LoopFollow supports up to 3 instances for monitoring multiple users:
- LoopFollow
- LoopFollow_Second
- LoopFollow_Third

Each instance is configured independently with its own Nightscout URL.

---

## Source File Reference

### Core Nightscout Files
- `LoopFollow/Helpers/NightscoutUtils.swift` - API utilities
- `LoopFollow/Controllers/Nightscout/BGData.swift` - CGM data
- `LoopFollow/Controllers/Nightscout/Treatments.swift` - Treatments
- `LoopFollow/Controllers/Nightscout/DeviceStatus.swift` - AID status
- `LoopFollow/Controllers/Nightscout/DeviceStatusLoop.swift` - Loop parsing
- `LoopFollow/Controllers/Nightscout/DeviceStatusOpenAPS.swift` - OpenAPS parsing
- `LoopFollow/Controllers/Nightscout/Profile.swift` - Profile fetch

### Remote Command Files
- `LoopFollow/Remote/RemoteType.swift` - Remote type enum
- `LoopFollow/Remote/LoopAPNS/` - Loop APNS support
- `LoopFollow/Remote/TRC/` - Trio Remote Control
- `LoopFollow/Remote/Nightscout/` - NS-based commands

---

## Summary

| Aspect | Details |
|--------|---------|
| **Purpose** | Caregiver monitoring of Loop/Trio/OpenAPS users |
| **Data Source** | Nightscout API v1, Dexcom Share |
| **Collections** | entries, treatments, devicestatus, profile |
| **AID Support** | Loop, OpenAPS, Trio |
| **Remote** | APNS (Loop), TRC (Trio), Nightscout |
| **Multi-User** | 3 instances supported |

LoopFollow is a comprehensive caregiver app that successfully consumes data from multiple AID systems through Nightscout's unified API, demonstrating the value of Nightscout as a data aggregation layer.
