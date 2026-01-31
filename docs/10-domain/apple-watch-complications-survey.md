# Apple Watch Complications Survey

> **Date**: 2026-01-31  
> **Status**: Complete  
> **Source**: ios-mobile-platform.md #7  
> **Related**: GAP-FOLLOW-001 (No Watch in LoopFollow)

---

## Executive Summary

This survey documents Apple Watch app and complication implementations across the Nightscout iOS ecosystem.

### Watch App Inventory

| App | Watch App | Complication | Framework | Data Refresh |
|-----|-----------|--------------|-----------|--------------|
| **Loop** | ✅ Full | ✅ ClockKit | WCSession + ClockKit | Phone push |
| **Trio** | ✅ Full | ✅ WidgetKit | WCSession + WidgetKit | Phone push |
| **LoopCaregiver** | ✅ Full | ❌ None | WCSession | Phone push |
| **Nightguard** | ✅ Full | ✅ WidgetKit | Direct Nightscout | API poll (10 min) |
| **xDrip4iOS** | ✅ Full | ✅ WidgetKit | App Groups | Shared UserDefaults |
| **DiaBLE** | ✅ Watch App | ❌ None | Standalone | NFC direct |
| **LoopFollow** | ❌ None | ❌ None | N/A | N/A |

### Key Finding

**Two data refresh patterns dominate:**
1. **Phone-Push (AID controllers)**: Loop, Trio, LoopCaregiver use `WCSession` to push data from phone
2. **Independent (Followers)**: Nightguard, xDrip4iOS fetch data independently via API or shared storage

---

## 1. Watch App Details

### 1.1 Loop Watch App

**Location**: `externals/LoopWorkspace/Loop/WatchApp Extension/`

**Architecture**:
```
Loop (iPhone)
  └── WatchDataManager.swift (WCSession delegate)
        ↓ NotificationCenter.default: .LoopDataUpdated
Loop Watch
  └── ExtensionDelegate.swift (WCSession receiver)
  └── ComplicationController.swift (ClockKit)
```

**Data Flow**:
1. `LoopDataUpdated` notification fires on phone
2. `WatchDataManager` packages `WatchContext` 
3. `WCSession.updateApplicationContext()` sends to watch
4. Watch `ExtensionDelegate` receives and updates UI

**Complication Families**:
- `graphicRectangular` - Glucose chart
- Other families via `ComplicationController`

**Privacy**: `.hideOnLockScreen`

**Source Files**:
- `Loop/Managers/WatchDataManager.swift` - Phone-side coordinator
- `WatchApp Extension/ComplicationController.swift` - ClockKit provider
- `Common/Models/WatchContext.swift` - Shared data model

### 1.2 Trio Watch App

**Location**: `externals/Trio/Trio Watch App/`, `Trio Watch Complication/`

**Architecture**:
```
Trio (iPhone)
  └── WatchManager/ (Sources/Services/)
Trio Watch
  └── TrioWatchApp.swift
  └── TrioWatchComplication.swift (WidgetKit)
```

**Complication Implementation**:
```swift
// TrioWatchComplication.swift
struct TrioWatchComplicationProvider: TimelineProvider {
    func getTimeline(in _: Context, completion: @escaping (Timeline<Entry>) -> Void) {
        let entry = TrioWatchComplicationEntry(date: Date())
        let timeline = Timeline(entries: [entry], policy: .never)
        completion(timeline)
    }
}
```

**Complication Families**:
- `.accessoryCircular` - App icon
- `.accessoryCorner` - "Trio" label

**Note**: Trio's complication is icon-only, not glucose data. Uses `policy: .never` (no automatic refresh).

### 1.3 LoopCaregiver Watch App

**Location**: `externals/LoopCaregiver/LoopCaregiver/LoopCaregiverWatchApp/`

**Architecture**:
```
LoopCaregiver (iPhone)
  └── WatchConnectivityService.swift (WCSession)
LoopCaregiver Watch
  └── HomeView.swift (Glucose display)
  └── SettingsView/ (Configuration)
```

**Data Flow**:
```swift
// WatchConnectivityService.swift
public func send(_ message: String) {
    try watchSession.updateApplicationContext([kMessageKey: message])
}
```

**Complication**: None - Watch app only, no complications.

**Features**:
- Multi-looper support via Core Data
- Settings sync via `UserDefaults+Watch.swift`
- SwiftUI views

### 1.4 Nightguard Watch App

**Location**: `externals/nightguard/nightguard WatchKit App/`

**Architecture**:
```
Nightguard Watch (Independent)
  └── NightguardTimelineProvider.swift (WidgetKit)
  └── MainController.swift (UI)
  └── WatchMessageService.swift (optional phone sync)
```

**Unique**: Nightguard watch fetches data **directly from Nightscout** - no phone required.

**Data Flow**:
```swift
// NightguardTimelineProvider.swift
func getTimeline(in context: Context, completion: @escaping (Timeline<Entry>) -> Void) {
    getTimelineData { nightscoutDataEntry in
        completion(Timeline(entries: entries, policy:
            .after(Calendar.current.date(byAdding: .minute, value: 10, to: Date()) ?? Date())))
    }
}
```

**Refresh Policy**: Every 10 minutes via `.after()` timeline policy.

**Complication Families** (via Widget Extension):
- `accessoryRectangular` - Full glucose + delta + timestamp
- `accessoryCircular` - Gauge or value
- `accessoryRectangularTimestamp` - With time

### 1.5 xDrip4iOS Watch App

**Location**: `externals/xdripswift/xDrip Watch App/`, `xDrip Watch Complication/`

**Architecture**:
```
xDrip4iOS (iPhone)
  └── Writes to App Group UserDefaults
xDrip Watch
  └── XDripWatchComplication.swift (WidgetKit)
  └── Reads from shared UserDefaults
```

**Data Flow** (Shared UserDefaults):
```swift
// XDripWatchComplication+Provider.swift
func getWidgetStateFromSharedUserDefaults() -> WidgetState? {
    guard let sharedUserDefaults = UserDefaults(suiteName: Bundle.main.appGroupSuiteName) else {return nil}
    guard let encodedLatestReadings = sharedUserDefaults.data(forKey: "complicationSharedUserDefaults...") else {
        return nil
    }
    // Decode and return
}
```

**Refresh Policy**: `policy: .never` - Updated when phone writes to shared storage.

**Widget State Model**:
```swift
WidgetState(
    bgReadingValues: [Double],
    bgReadingDates: [Date],
    isMgDl: Bool,
    slopeOrdinal: Int,
    deltaValueInUserUnit: Double,
    urgentLowLimitInMgDl: Double,
    lowLimitInMgDl: Double,
    highLimitInMgDl: Double,
    urgentHighLimitInMgDl: Double,
    keepAliveIsDisabled: Bool,
    liveDataIsEnabled: Bool
)
```

### 1.6 DiaBLE Watch App

**Location**: `externals/DiaBLE/DiaBLE Watch/`

**Architecture**: Standalone watch app with NFC capability.

**Unique**: DiaBLE watch can read Libre sensors directly via NFC (no phone).

**Complication**: None - standalone app only.

---

## 2. Data Refresh Patterns

### 2.1 Pattern Comparison

| Pattern | Apps | Mechanism | Latency | Battery |
|---------|------|-----------|---------|---------|
| **WCSession Push** | Loop, Trio, LoopCaregiver | Phone pushes on data change | <1 sec | Low |
| **Shared UserDefaults** | xDrip4iOS | Phone writes, watch polls | ~5 sec | Low |
| **Direct API Poll** | Nightguard | Watch fetches from Nightscout | Variable | Higher |
| **NFC Direct** | DiaBLE | Watch reads sensor | On-demand | Medium |

### 2.2 WCSession (Phone-Push) Pattern

**Pros**:
- Immediate updates when phone has new data
- Low battery impact on watch
- Rich data transfer capability

**Cons**:
- Requires phone in range
- Phone app must be running

**Implementation**:
```swift
// Phone side
watchSession.updateApplicationContext([data])

// Watch side
func session(_ session: WCSession, didReceiveApplicationContext context: [String: Any]) {
    // Update UI
}
```

### 2.3 Shared UserDefaults Pattern

**Pros**:
- Simple implementation
- Works with WidgetKit
- Phone/watch independent timing

**Cons**:
- Requires App Groups entitlement
- Data may be stale until next poll

**Implementation**:
```swift
// Phone side
UserDefaults(suiteName: appGroup)?.set(encoded, forKey: key)

// Watch side
UserDefaults(suiteName: appGroup)?.data(forKey: key)
```

### 2.4 Direct API Pattern

**Pros**:
- Watch fully independent
- Works without phone

**Cons**:
- Higher battery usage
- Requires cellular/WiFi
- API rate limits

**Implementation**:
```swift
// Nightguard pattern
func getTimeline(completion: @escaping (Timeline<Entry>) -> Void) {
    NightscoutService.fetchData { data in
        completion(Timeline(entries: [entry], policy: .after(10.minutes)))
    }
}
```

---

## 3. Complication Framework Comparison

### 3.1 ClockKit vs WidgetKit

| Aspect | ClockKit (Legacy) | WidgetKit (Modern) |
|--------|-------------------|-------------------|
| **Introduced** | watchOS 2 | watchOS 9 |
| **Status** | Deprecated watchOS 9+ | Current |
| **Families** | `CLKComplicationFamily` | `.accessory*` |
| **Refresh** | `CLKComplicationServer` | `TimelineProvider` |
| **Used By** | Loop | Trio, Nightguard, xDrip4iOS |

### 3.2 Migration Status

| App | Current Framework | Migration Needed |
|-----|-------------------|------------------|
| Loop | ClockKit | ⚠️ Yes - deprecated |
| Trio | WidgetKit | ✅ No |
| Nightguard | WidgetKit | ✅ No |
| xDrip4iOS | WidgetKit | ✅ No |
| LoopCaregiver | None | N/A |

---

## 4. Shared Component Opportunities

### 4.1 GlucoseComplicationKit

**Purpose**: Unified WidgetKit-based complication for glucose display.

**Components**:
```swift
// Shared entry model
struct GlucoseComplicationEntry: TimelineEntry {
    let date: Date
    let glucose: Double
    let trend: GlucoseTrend
    let delta: Double
    let unit: GlucoseUnit
    let isStale: Bool
}

// Shared views
struct GlucoseAccessoryCircularView: View { ... }
struct GlucoseAccessoryRectangularView: View { ... }
struct GlucoseAccessoryCornerView: View { ... }

// Shared timeline provider
protocol GlucoseDataProvider {
    func getLatestGlucose() async -> GlucoseComplicationEntry
}
```

### 4.2 WatchSyncKit

**Purpose**: Unified WCSession management for phone-watch sync.

**Components**:
```swift
// Shared context model (from Loop's WatchContext)
struct WatchGlucoseContext: Codable {
    let glucose: Double
    let glucoseDate: Date
    let trend: Int
    let delta: Double
    let iob: Double?
    let cob: Double?
    let predictions: [Double]?
}

// Shared sync service
class WatchSyncService: NSObject, WCSessionDelegate {
    func sendContext(_ context: WatchGlucoseContext)
    func onContextReceived(_ handler: (WatchGlucoseContext) -> Void)
}
```

### 4.3 Adoption Path

| App | Adopt GlucoseComplicationKit | Adopt WatchSyncKit |
|-----|------------------------------|-------------------|
| Loop | ✅ Replace ClockKit | ✅ Already has pattern |
| Trio | ✅ Enhance icon-only | ✅ Already has pattern |
| LoopCaregiver | ✅ Add complications | ✅ Already has pattern |
| Nightguard | ⚠️ Uses direct API | ❌ Independent design |
| xDrip4iOS | ✅ Standardize entry | ⚠️ Uses App Groups |
| LoopFollow | ✅ Add watch support | ✅ New implementation |

---

## 5. Gap Analysis

### GAP-WATCH-001: Loop Uses Deprecated ClockKit

**Description**: Loop's `ComplicationController.swift` uses ClockKit which is deprecated in watchOS 9+.

**Impact**: Will need migration to WidgetKit for future watchOS compatibility.

**Remediation**: Migrate to WidgetKit `TimelineProvider` pattern.

### GAP-WATCH-002: Trio Complication is Icon-Only

**Description**: Trio's watch complication only shows the app icon, not glucose data.

**Impact**: Users cannot see glucose on watch face without opening app.

**Remediation**: Add `GlucoseComplicationEntry` with real-time data.

### GAP-WATCH-003: LoopCaregiver Has No Complications

**Description**: LoopCaregiver has watch app but no complications.

**Impact**: Caregivers cannot see glucose on watch face.

**Remediation**: Add WidgetKit complications using existing `GlucoseTimelineEntry`.

### GAP-WATCH-004: No Shared Watch Components

**Description**: Each app implements watch sync and complications independently.

**Impact**: Code duplication, inconsistent UX across apps.

**Remediation**: Create GlucoseComplicationKit and WatchSyncKit packages.

---

## 6. Recommendations

### Short-term

1. **Migrate Loop to WidgetKit** - Replace deprecated ClockKit
2. **Add glucose data to Trio complication** - Use existing watch sync
3. **Add complications to LoopCaregiver** - Leverage existing TimelineProviderShared

### Medium-term

1. **Create GlucoseComplicationKit** - Shared complication views and entry models
2. **Create WatchSyncKit** - Unified phone-watch sync
3. **Add watch app to LoopFollow** - Address GAP-FOLLOW-001

### Long-term

1. **Standardize all apps on WidgetKit** - Modern framework
2. **Unified caregiver watch experience** - Same complications across apps
3. **Direct API option for all apps** - Phone-independent like Nightguard

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [follower-caregiver-feature-consolidation.md](follower-caregiver-feature-consolidation.md) | LoopFollow vs LoopCaregiver |
| [swift-package-ecosystem-assessment.md](swift-package-ecosystem-assessment.md) | SPM status |
| [app-store-pathway-analysis.md](app-store-pathway-analysis.md) | App Store viability |
