# WidgetKit Standardization Survey

> **Date**: 2026-01-31  
> **Status**: Complete  
> **Source**: ios-mobile-platform.md #6  
> **Related**: Apple Watch Complications Survey (cycle 64)

---

## Executive Summary

This survey documents WidgetKit implementations across the Nightscout iOS ecosystem, identifying widget families supported, data models used, and opportunities for shared components.

### Widget Support Matrix

| App | Home Screen | Lock Screen | Live Activity | Dynamic Island |
|-----|-------------|-------------|---------------|----------------|
| **xDrip4iOS** | ✅ S/M/L | ✅ Circular/Rect | ✅ | ✅ |
| **Nightguard** | ✅ Small | ✅ Circular/Rect | ❌ | ❌ |
| **LoopCaregiver** | ✅ S/M/L | ✅ Circular/Rect/Inline | ❌ | ❌ |
| **Trio** | ❌ | ❌ | ✅ | ✅ |
| **DiaBLE** | ✅ (placeholder) | ❌ | ✅ | ❌ |
| **Loop** | ❌ | ❌ | ❌ | ❌ |

### Key Finding

**Three distinct widget patterns exist:**
1. **Full Widget Suite** (xDrip4iOS, LoopCaregiver) - All families, rich data
2. **Lock Screen Focus** (Nightguard) - Accessory families, API-driven
3. **Live Activity Only** (Trio) - Dynamic Island, no home screen widgets

---

## 1. Widget Family Support

### 1.1 Family Coverage by App

| Family | xDrip4iOS | Nightguard | LoopCaregiver | Trio | DiaBLE |
|--------|-----------|------------|---------------|------|--------|
| `.systemSmall` | ✅ | ✅ | ✅ | ❌ | ✅ |
| `.systemMedium` | ✅ | ❌ | ✅ | ❌ | ❌ |
| `.systemLarge` | ✅ | ❌ | ✅ | ❌ | ❌ |
| `.accessoryCircular` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `.accessoryRectangular` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `.accessoryInline` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `ActivityConfiguration` | ✅ | ❌ | ❌ | ✅ | ✅ |
| `DynamicIsland` | ✅ | ❌ | ❌ | ✅ | ❌ |

### 1.2 Code References

#### xDrip4iOS
```swift
// xDrip Widget/XDripWidget.swift:22-28
.supportedFamilies([
    .systemSmall,
    .systemMedium,
    .systemLarge,
    .accessoryCircular,
    .accessoryRectangular
])
```

#### Nightguard
```swift
// nightguard Widget Extension/nightguard_Widget_Extension.swift:51-54
.supportedFamilies([
    .systemSmall,
    .accessoryCircular,
    .accessoryRectangular,
])
```

#### LoopCaregiver
```swift
// LoopCaregiverWidgetExtension/LoopCaregiverWidget.swift:29-36
.supportedFamilies([
    .accessoryCircular,
    .accessoryInline,
    .accessoryRectangular,
    .systemLarge,
    .systemMedium,
    .systemSmall
])
```

---

## 2. Data Models

### 2.1 Timeline Entry Comparison

| App | Entry Type | Key Fields |
|-----|------------|------------|
| **xDrip4iOS** | `XDripWidget.Entry` | `widgetState: WidgetState` |
| **Nightguard** | `NightscoutDataEntry` | `sgv`, `bgdelta`, `time`, `iob`, `cob` |
| **LoopCaregiver** | `GlucoseTimeLineEntry` | `looper`, `glucoseSample`, `treatmentData` |
| **Trio** | `LiveActivityAttributes.ContentState` | `bg`, `direction`, `change`, `iob`, `cob` |

### 2.2 xDrip4iOS WidgetState

```swift
// XDripWidget+Entry.swift:26-48
struct WidgetState {
    var bgReadingValues: [Double]?
    var bgReadingDates: [Date]?
    var isMgDl: Bool
    var slopeOrdinal: Int
    var deltaValueInUserUnit: Double?
    var urgentLowLimitInMgDl: Double
    var lowLimitInMgDl: Double
    var highLimitInMgDl: Double
    var urgentHighLimitInMgDl: Double
    var dataSourceDescription: String
    var deviceStatusCreatedAt: Date?
    var deviceStatusLastLoopDate: Date?
    var bgUnitString: String
    var bgValueInMgDl: Double?
    var bgReadingDate: Date?
}
```

### 2.3 Nightguard NightscoutDataEntry

```swift
// nightguard Widget Extension/NightscoutDataEntry.swift:14-60
struct NightscoutDataEntry: TimelineEntry {
    var date: Date
    var sgv: String
    var sgvColor: UIColor
    var bgdeltaString: String
    var bgdeltaColor: UIColor
    var bgdeltaArrow: String
    var bgdelta: Float
    var time: NSNumber
    var battery: String
    var iob: String
    var cob: String
}
```

### 2.4 LoopCaregiver GlucoseTimelineValue

```swift
// GlucoseTimeLineEntry.swift:14-60
enum GlucoseTimeLineEntry: TimelineEntry {
    case success(GlucoseTimelineValue)
    case failure(GlucoseTimeLineEntryError)
}
// Uses LoopKit's NewGlucoseSample for glucose data
```

---

## 3. Data Refresh Strategies

### 3.1 Pattern Comparison

| App | Provider | Refresh Mechanism | Data Source |
|-----|----------|-------------------|-------------|
| **xDrip4iOS** | `StaticConfiguration` | App Groups UserDefaults | Local CGM |
| **Nightguard** | `IntentConfiguration` | Direct Nightscout API | Remote API |
| **LoopCaregiver** | `IntentConfiguration` | Nightscout via LoopKit | Remote API |
| **Trio** | `ActivityConfiguration` | Push from app | Local algorithm |

### 3.2 xDrip4iOS (App Groups)

```swift
// XDripWidget+Provider.swift
func getTimeline(in context: Context, completion: @escaping (Timeline<Entry>) -> ()) {
    let entry = Entry(date: .now, widgetState: getWidgetStateFromSharedUserDefaults())
    completion(.init(entries: [entry], policy: .never))
}
```
- **Refresh**: Phone app writes to App Groups, widget reads
- **Policy**: `.never` - relies on phone push

### 3.3 Nightguard (Direct API)

```swift
// NightguardTimelineProvider.swift
func getTimeline(in context: Context, completion: @escaping (Timeline<Entry>) -> Void) {
    getTimelineData { nightscoutDataEntry in
        completion(Timeline(entries: entries, policy:
            .after(Calendar.current.date(byAdding: .minute, value: 10, to: Date()))))
    }
}
```
- **Refresh**: Widget fetches from Nightscout directly
- **Policy**: `.after(10 minutes)` - periodic refresh

### 3.4 Trio (Live Activity)

```swift
// LiveActivity.swift
ActivityConfiguration(for: LiveActivityAttributes.self) { context in
    LiveActivityView(context: context)
} dynamicIsland: { context in
    // Dynamic Island content
}
```
- **Refresh**: App pushes updates via ActivityKit
- **Policy**: Push-based, always current

---

## 4. Live Activity Comparison

### 4.1 Live Activity Support

| App | Lock Screen Banner | Dynamic Island Compact | Dynamic Island Expanded |
|-----|--------------------|-----------------------|------------------------|
| **Trio** | ✅ Full glucose + chart | ✅ BG + trend | ✅ IOB/COB/Chart |
| **xDrip4iOS** | ✅ Glucose + delta | ✅ BG + trend | ✅ Delta + trend |
| **DiaBLE** | ✅ Basic | ❌ | ❌ |

### 4.2 Trio Live Activity Features

- BG value with dynamic color
- Trend arrow
- IOB/COB display
- Glucose chart
- Target indicator
- Updated timestamp

### 4.3 xDrip4iOS Live Activity Features

- BG value with trend
- Delta change
- Device status icon
- Unit display
- Color-coded values

---

## 5. Shared Component Opportunities

### 5.1 Proposed: GlucoseWidgetKit

**Purpose**: Unified WidgetKit package for glucose display widgets.

```swift
// Shared Timeline Entry
public struct GlucoseWidgetEntry: TimelineEntry {
    public let date: Date
    public let glucose: GlucoseValue
    public let trend: GlucoseTrend
    public let delta: GlucoseDelta?
    public let iob: Double?
    public let cob: Double?
    public let isStale: Bool
    public let colorScheme: GlucoseColorScheme
}

public struct GlucoseValue {
    let value: Double
    let unit: GlucoseUnit
    let date: Date
}

public enum GlucoseTrend: Int {
    case doubleUp = 1
    case singleUp = 2
    case fortyFiveUp = 3
    case flat = 4
    case fortyFiveDown = 5
    case singleDown = 6
    case doubleDown = 7
}
```

### 5.2 Shared Views

```swift
// System widget views
public struct GlucoseSystemSmallView: View { ... }
public struct GlucoseSystemMediumView: View { ... }
public struct GlucoseSystemLargeView: View { ... }

// Lock screen views (accessory families)
public struct GlucoseAccessoryCircularView: View { ... }
public struct GlucoseAccessoryRectangularView: View { ... }
public struct GlucoseAccessoryInlineView: View { ... }

// Live Activity views
public struct GlucoseLiveActivityView: View { ... }
public struct GlucoseDynamicIslandView: View { ... }
```

### 5.3 Shared Color Logic

```swift
public struct GlucoseColorScheme {
    let urgentLow: Double  // mg/dL
    let low: Double
    let target: Double
    let high: Double
    let urgentHigh: Double
    
    func color(for glucose: Double) -> Color {
        // Shared color logic across apps
    }
}
```

### 5.4 Adoption Path

| App | Current State | Adoption Effort |
|-----|---------------|-----------------|
| xDrip4iOS | Rich implementation | Extract to package |
| Nightguard | Good foundation | Adopt shared views |
| LoopCaregiver | Uses LoopKit types | Adapter layer |
| Trio | Live Activity only | Add home screen widgets |
| Loop | No widgets | New implementation |

---

## 6. Gap Analysis

### GAP-WIDGET-001: No Shared Widget Components

**Description**: Each app implements widgets independently with different data models and views.

**Affected Systems**: xDrip4iOS, Nightguard, LoopCaregiver, Trio, DiaBLE

**Evidence**:
- xDrip4iOS: `WidgetState` with 15+ fields
- Nightguard: `NightscoutDataEntry` with different structure
- LoopCaregiver: Uses LoopKit `NewGlucoseSample`
- Trio: `LiveActivityAttributes.ContentState`

**Impact**: 
- Code duplication across apps
- Inconsistent UX (different layouts, colors)
- Higher maintenance burden

**Remediation**: Create `GlucoseWidgetKit` SPM package with shared entry model and views.

### GAP-WIDGET-002: Loop Has No Home Screen Widgets

**Description**: Loop app has no WidgetKit implementation for home screen or lock screen.

**Affected Systems**: Loop

**Evidence**:
- No Widget Extension target in Loop project
- Users must open app or use watch for glucose

**Impact**: Users cannot see glucose on iOS home screen or lock screen.

**Remediation**: Add WidgetKit extension using existing data infrastructure.

### GAP-WIDGET-003: Trio Has No Home Screen Widgets

**Description**: Trio only has Live Activity, no static home screen widgets.

**Affected Systems**: Trio

**Evidence**:
- `LiveActivity/` directory only contains ActivityConfiguration
- No `.systemSmall`, `.systemMedium` support

**Impact**: Users without iPhone 14+ (Dynamic Island) have limited widget options.

**Remediation**: Add standard WidgetKit families alongside Live Activity.

### GAP-WIDGET-004: Inconsistent Color Schemes

**Description**: Each app uses different glucose range coloring logic.

**Affected Systems**: All apps with widgets

**Evidence**:
- xDrip4iOS: 4 thresholds (urgentLow, low, high, urgentHigh)
- Trio: Dynamic color gradients
- Nightguard: UIColor-based

**Impact**: Users see different colors for same glucose in different apps.

**Remediation**: Standardize color scheme in shared package.

---

## 7. Recommendations

### Short-term

1. **Document color standards** - Agree on glucose range colors
2. **Add widgets to Loop** - High-impact feature gap
3. **Add home widgets to Trio** - Complement Live Activity

### Medium-term

1. **Create GlucoseWidgetKit package** - Shared entry model and views
2. **Standardize trend arrow mapping** - Same ordinal values
3. **Unified refresh strategy** - Document best practices

### Long-term

1. **Full ecosystem adoption** - All apps use shared package
2. **Consistent UX** - Same layout patterns across apps
3. **Shared Live Activity components** - Dynamic Island standardization

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [apple-watch-complications-survey.md](apple-watch-complications-survey.md) | Watch WidgetKit (accessory families) |
| [healthkit-integration-audit.md](healthkit-integration-audit.md) | Data source patterns |
| [swift-package-ecosystem-assessment.md](swift-package-ecosystem-assessment.md) | SPM adoption status |
