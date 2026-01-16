# Nightguard Behavior Documentation

This directory contains documentation extracted from Nightguard, a native iOS/watchOS application for blood glucose monitoring via Nightscout. Nightguard provides a **pure consumer perspective** on the Nightscout data model—it reads and displays data but does not upload CGM readings.

## Source Repository

- **Repository**: [nightscout/nightguard](https://github.com/nightscout/nightguard)
- **Language**: Swift (native iOS/watchOS)
- **License**: AGPL-3.0
- **Analysis Date**: 2026-01-16
- **Codebase Size**: ~16,600 lines of Swift

## Purpose & Value

Unlike CGM producer apps (xDrip4iOS, xDrip+), Nightguard is a **display and alerting app**:

1. **Consumer-only perspective** - How a follower app consumes Nightscout data
2. **Alarm system implementation** - Sophisticated alert logic with prediction, edge detection, smart snooze
3. **Apple ecosystem integration** - WatchOS app, iOS widgets, complications
4. **Care data tracking** - CAGE, SAGE, BAGE from treatments collection
5. **Loop integration** - Displaying IOB, COB, temp basal from devicestatus
6. **Caching strategy** - Efficient data retrieval patterns for mobile apps

## Documentation Index

| Document | Description |
|----------|-------------|
| [data-models.md](data-models.md) | NightscoutData, BloodSugar, DeviceStatusData, TemporaryTargetData |
| [nightscout-sync.md](nightscout-sync.md) | API paths, data fetching, caching, authentication |
| [alarm-logic.md](alarm-logic.md) | AlarmRule implementation, snooze, prediction, edge detection |
| [apple-watch.md](apple-watch.md) | WatchKit app, complications, WatchConnectivity |
| [widgets.md](widgets.md) | iOS widget implementation, timeline provider |

## Key Source Files

| File | Purpose | Lines |
|------|---------|-------|
| `nightguard/external/NightscoutService.swift` | Core NS API client | ~1377 |
| `nightguard/external/NightscoutCacheService.swift` | Data caching layer | ~330 |
| `nightguard/domain/AlarmRule.swift` | Alarm logic | ~373 |
| `nightguard/app/NightscoutData.swift` | Current BG model | ~185 |
| `nightguard/domain/BloodSugar.swift` | Historical BG model | ~90 |
| `nightguard/app/DeviceStatusData.swift` | Pump status model | ~126 |
| `nightguard/app/TemporaryTargetData.swift` | Temp target model | ~114 |
| `nightguard Widget Extension/NightguardTimelineProvider.swift` | Widget data | ~195 |
| `nightguard WatchKit App/ExtensionDelegate.swift` | Watch app entry | ~131 |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Nightguard Data Architecture                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        DATA LAYER                                        ││
│  │                                                                          ││
│  │  NightscoutService (Singleton)                                           ││
│  │  ├── readCurrentData()         → GET /api/v2/properties                 ││
│  │  ├── readStatus()              → GET /api/v1/status.json                ││
│  │  ├── readTodaysChartData()     → GET /api/v1/entries.json               ││
│  │  ├── readYesterdaysChartData() → GET /api/v1/entries.json               ││
│  │  ├── readDeviceStatus()        → GET /api/v1/devicestatus.json          ││
│  │  ├── readLastTreatmentEvent()  → GET /api/v1/treatments                 ││
│  │  ├── readLastTemporaryTarget() → GET /api/v1/treatments                 ││
│  │  └── createXxxTreatment()      → POST /api/v1/treatments (care events)  ││
│  │         │                                                                ││
│  │         ▼                                                                ││
│  │  NightscoutCacheService (Singleton)                                      ││
│  │  ├── Caches today's & yesterday's BG data                               ││
│  │  ├── Caches current NightscoutData                                       ││
│  │  ├── Caches care data (CAGE, SAGE, BAGE)                                ││
│  │  └── Manages pending request deduplication                               ││
│  │         │                                                                ││
│  │         ▼                                                                ││
│  │  NightscoutDataRepository (Persistence)                                  ││
│  │  └── UserDefaults-based storage                                          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        DOMAIN LAYER                                      ││
│  │                                                                          ││
│  │  Data Models:                                                            ││
│  │  ├── NightscoutData     - Current BG, delta, IOB, COB, battery          ││
│  │  ├── BloodSugar         - Historical reading (value, timestamp, arrow)  ││
│  │  ├── DeviceStatusData   - Pump profile, temp basal, reservoir           ││
│  │  └── TemporaryTargetData - Temp target range and duration               ││
│  │                                                                          ││
│  │  Alarm System:                                                           ││
│  │  ├── AlarmRule          - High/low thresholds, snooze state             ││
│  │  ├── PredictionService  - Low prediction based on trend                 ││
│  │  └── AlarmNotificationService - iOS notification delivery               ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                     PRESENTATION LAYER                                   ││
│  │                                                                          ││
│  │  iOS App:                                                                ││
│  │  ├── MainView (SwiftUI)      - Primary BG display with chart            ││
│  │  ├── MainViewModel           - MVVM state management                    ││
│  │  ├── ChartScene (SpriteKit)  - BG chart with yesterday overlay          ││
│  │  └── SlideToSnooze           - Gesture-based alarm snoozing             ││
│  │                                                                          ││
│  │  watchOS App:                                                            ││
│  │  ├── ExtensionDelegate       - Watch app lifecycle                      ││
│  │  ├── MainController          - Watch UI controller                      ││
│  │  └── Complications           - Watch face complications                 ││
│  │                                                                          ││
│  │  iOS Widgets:                                                            ││
│  │  ├── NightguardDefaultWidgets    - Text-based BG display               ││
│  │  ├── NightguardTimestampWidgets  - BG with absolute time               ││
│  │  ├── NightguardGaugeWidgets      - Gauge visualization                 ││
│  │  └── NightguardTimelineProvider  - Widget data refresh                 ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                   COMMUNICATION LAYER                                    ││
│  │                                                                          ││
│  │  WatchConnectivity:                                                      ││
│  │  ├── WatchMessageService   - Bi-directional phone↔watch messaging       ││
│  │  ├── SnoozeMessage         - Sync snooze state                          ││
│  │  ├── UserDefaultSyncMessage - Sync settings                             ││
│  │  └── NightscoutDataMessage - Share BG data                              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## API Paths Used

| Path | Method | Purpose |
|------|--------|---------|
| `/api/v2/properties` | GET | Current BG, IOB, COB, battery (primary data source) |
| `/api/v1/status.json` | GET | Nightscout configuration (units) |
| `/api/v1/entries.json` | GET | Historical BG readings |
| `/api/v1/devicestatus.json` | GET | Pump profile, temp basal, reservoir |
| `/api/v1/treatments` | GET | Care events (sensor/cannula/battery changes), temp targets |
| `/api/v1/treatments` | POST | Create care events (SAGE, CAGE, BAGE) |

## Treatment Event Types Used

Nightguard reads and writes these `eventType` values:

| EventType | Purpose | Direction |
|-----------|---------|-----------|
| `"Sensor Change"` | SAGE (sensor age) | Read & Write |
| `"Site Change"` | CAGE (cannula age) | Read & Write |
| `"Pump Battery Change"` | BAGE (battery age) | Read & Write |
| `"Temporary Target"` | Temp target display | Read only |

## Authentication

Nightguard supports token-based authentication via URL query parameter:

```
https://your-ns-site.herokuapp.com?token=your-token-here
```

The token is embedded in the base URI and extracted by `UserDefaultsRepository.getUrlWithPathAndQueryParameters()`.

For write operations (creating care events), a 401 response triggers a user-facing error about missing write access.

## Uploader Identification

When creating treatments, Nightguard uses:

```swift
"enteredBy": "nightguard"
```

## Key Implementation Patterns

### Data Refresh Strategy

Nightguard uses a time-based refresh strategy:
- Current data: Refresh if older than 5 minutes (or 1 minute if configured)
- Chart data: Refresh when current data is stale
- Care data: Refresh with 5-day lookback (sensor), 40-day (battery)
- Device status: Refresh on each app activation

### Caching Layer

`NightscoutCacheService` provides:
- Request deduplication (tracks pending URLSessionTasks)
- Yesterday overlay transformation (shifts timestamps by 24 hours)
- Thread-safe access via DispatchQueue

### Yesterday Overlay

A unique Nightguard feature - yesterday's BG values are displayed as an overlay on today's chart to help predict trends:

```swift
func transformToCurrentDay(yesterdaysValues: [BloodSugar]) -> [BloodSugar] {
    yesterdaysValues.map { value in
        BloodSugar(value: value.value, 
                   timestamp: value.timestamp + ONE_DAY_IN_MICROSECONDS, ...)
    }
}
```

## Comparison: Nightguard vs Other Ecosystem Apps

| Aspect | Nightguard | xDrip4iOS | xDrip+ |
|--------|------------|-----------|--------|
| **Role** | Consumer only | Producer + Consumer | Producer + Consumer |
| **Platform** | iOS/watchOS | iOS | Android |
| **CGM Connection** | None | Direct Bluetooth | Direct Bluetooth |
| **Treatment Sync** | Read + limited write | Bi-directional | Bi-directional |
| **Alarm System** | Full (prediction, edge) | Basic | Full |
| **Apple Watch** | Native app + complications | Native app + complications | N/A |
| **iOS Widgets** | Yes (3 types) | Yes | N/A |
| **Primary API** | `/api/v2/properties` | `/api/v1/entries` | `/api/v1/entries` |

## Cross-References

- [Nightscout Data Model](../../docs/10-domain/nightscout-data-model.md) - Authoritative NS schema
- [mapping/xdrip4ios/](../xdrip4ios/) - iOS producer perspective
- [mapping/xdrip-android/](../xdrip-android/) - Android producer perspective
- [cross-project/cgm-apps-comparison.md](../cross-project/cgm-apps-comparison.md) - CGM app comparison

---

## Code Citation Format

Throughout this documentation, code references use:
```
nightguard:nightguard/path/to/file.swift#L123-L456
```

This maps to files in `externals/nightguard/`.

---

## Limitations / Out of Scope

This documentation does not cover:

- **Statistics calculation** - The BasicStats implementation for 24-hour statistics
- **Chart rendering** - The SpriteKit ChartScene implementation details
- **Localization** - German and Finnish translation files
- **UI Tests** - The Fastlane screenshot automation

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from nightguard source |
