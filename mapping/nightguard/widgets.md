# Nightguard iOS Widgets

This document describes Nightguard's iOS widget implementation, including the timeline provider, widget types, and data entry format.

## Overview

Nightguard provides three widget configurations for iOS 14+ home screen and lock screen:

| Widget | Display | Supported Families |
|--------|---------|-------------------|
| Default (Text) | BG value as text | systemSmall, accessoryInline, accessoryCircular, accessoryRectangular |
| Timestamp | BG with absolute time | accessoryRectangular |
| Gauge | BG as circular gauge | accessoryCircular |

## Widget Bundle

**Source**: `nightguard:nightguard Widget Extension/nightguard_Widget_Extension.swift`

```swift
@main
struct NightguardWidgetsBundle: WidgetBundle {
    var body: some Widget {
        NightguardDefaultWidgets()
        NightguardTimestampWidgets()
        NightguardGaugeWidgets()
    }
}
```

---

## Widget Configurations

### Default Text Widgets

```swift
struct NightguardDefaultWidgets: Widget {
    var provider = NightguardTimelineProvider(displayName: "BG Text")

    var body: some WidgetConfiguration {
        StaticConfiguration(
            kind: "org.duckdns.dhe.nightguard.NightguardDefaultWidgets",
            provider: provider
        ) { entry in
            NightguardEntryView(entry: entry)
        }
        .configurationDisplayName("BG Values as Text")
        .description(provider.displayName)
        .supportedFamilies([
            .systemSmall,
            .accessoryInline,
            .accessoryCircular,
            .accessoryRectangular,
        ])
    }
}
```

### Timestamp Widgets

```swift
struct NightguardTimestampWidgets: Widget {
    var provider = NightguardTimelineProvider(displayName: "BG Text")

    var body: some WidgetConfiguration {
        StaticConfiguration(
            kind: "org.duckdns.dhe.nightguard.NightguardTimestampWidgets",
            provider: provider
        ) { entry in
            NightguardTimestampEntryView(entry: entry)
        }
        .configurationDisplayName("BG with absolute Time")
        .supportedFamilies([.accessoryRectangular])
    }
}
```

### Gauge Widgets

```swift
struct NightguardGaugeWidgets: Widget {
    var provider = NightguardTimelineProvider(displayName: "BG Gauge")

    var body: some WidgetConfiguration {
        StaticConfiguration(
            kind: "org.duckdns.dhe.nightguard.NightguardGaugeWidgets",
            provider: provider
        ) { entry in
            NightguardGaugeEntryView(entry: entry)
        }
        .configurationDisplayName("BG Values as Gauge")
        .supportedFamilies([.accessoryCircular])
    }
}
```

---

## Timeline Provider

**Source**: `nightguard:nightguard Widget Extension/NightguardTimelineProvider.swift`

### TimelineProvider Protocol

```swift
struct NightguardTimelineProvider: TimelineProvider {
    
    typealias Entry = NightscoutDataEntry
    
    var displayName: String = ""
    
    func placeholder(in context: Context) -> NightscoutDataEntry {
        NightscoutDataEntry(configuration: ConfigurationIntent())
    }
    
    func getSnapshot(in context: Context, completion: @escaping (NightscoutDataEntry) -> Void) {
        if context.isPreview {
            completion(NightscoutDataEntry.previewValues)
            return
        }
        Task {
            getTimelineData { completion($0) }
        }
    }
    
    func getTimeline(in context: Context, completion: @escaping (Timeline<NightscoutDataEntry>) -> Void) {
        Task {
            getTimelineData { nightscoutDataEntry in
                var entries: [NightscoutDataEntry] = []
                entries.append(nightscoutDataEntry)
                // Refresh after 10 minutes
                completion(Timeline(entries: entries, policy:
                    .after(Calendar.current.date(byAdding: .minute, value: 10, to: Date()) ?? Date())))
            }
        }
    }
}
```

### Data Fetching

```swift
private func getTimelineData(completion: @escaping (NightscoutDataEntry) -> Void) {
    
    BackgroundRefreshLogger.info("TimelineProvider is getting Timeline...")
    let oldData = NightscoutDataRepository.singleton.loadCurrentNightscoutData()
    let oldEntries = NightscoutDataRepository.singleton.loadTodaysBgData()
    
    NightscoutService.singleton.readTodaysChartData(oldValues: []) { result in
        
        var bgEntries: [BgEntry]
        var errorMessage = ""
        
        if case .data(let bloodSugarValues) = result {
            NightscoutDataRepository.singleton.storeTodaysBgData(bloodSugarValues)
            bgEntries = bloodSugarValues.map { bgValue in
                BgEntry(
                    value: UnitsConverter.mgdlToDisplayUnits(String(bgValue.value)),
                    valueColor: UIColorChanger.getBgColor(String(bgValue.value)),
                    delta: "0",
                    timestamp: bgValue.timestamp,
                    arrow: bgValue.arrow
                )
            }
        } else if case .error(let error) = result {
            // Use cached values on error
            bgEntries = oldEntries.map { ... }
            errorMessage = error.localizedDescription
        } else {
            // Use cached values
            bgEntries = oldEntries.map { ... }
        }
        
        // Reduce to last 4 entries for widget display
        var reducedEntries = bgEntries
        if bgEntries.count > 3 {
            reducedEntries = Array(bgEntries.suffix(4))
        }
        
        let reducedEntriesWithDelta = calculateDeltaValues(reducedEntries)
        let entry = convertToTimelineEntry(updatedData, reducedEntriesWithDelta, errorMessage)
        
        // Trigger alarm notifications (iOS only)
        #if os(iOS)
        AlarmNotificationService.singleton.notifyIfAlarmActivated(updatedData)
        #endif
        
        completion(entry)
    }
}
```

---

## NightscoutDataEntry

**Source**: `nightguard:nightguard Widget Extension/NightscoutDataEntry.swift`

### Fields

```swift
struct NightscoutDataEntry: TimelineEntry {
    let date: Date                    // Entry date for timeline
    let sgv: String                   // BG value (display units)
    let sgvColor: UIColor             // BG color coding
    let bgdeltaString: String         // Delta string
    let bgdeltaColor: UIColor         // Delta color
    let bgdeltaArrow: String          // Trend arrow
    let bgdelta: Float                // Delta numeric
    let time: NSNumber                // Timestamp
    let battery: String               // Uploader battery
    let iob: String                   // Insulin on board
    let cob: String                   // Carbs on board
    let snoozedUntilTimestamp: TimeInterval  // Snooze state
    let lastBGValues: [BgEntry]       // Recent readings for mini-chart
    let errorMessage: String          // Error to display
    let configuration: ConfigurationIntent
}
```

### Preview Values

```swift
static var previewValues: NightscoutDataEntry {
    NightscoutDataEntry(
        date: Date(),
        sgv: "120",
        sgvColor: UIColor.green,
        bgdeltaString: "+5",
        bgdeltaColor: UIColor.white,
        bgdeltaArrow: "→",
        // ...
    )
}
```

---

## Widget Views

### Entry View Router

```swift
struct NightguardEntryView: View {
    @Environment(\.widgetFamily) var widgetFamily
    var entry: NightscoutDataEntry

    var body: some View {
        switch widgetFamily {
        case .systemSmall:
            SystemSmallView(entry: entry)
                .widgetBackground(backgroundView: Color.black)
        case .accessoryCircular:
            AccessoryCircularView(entry: entry)
                .widgetBackground(backgroundView: background())
        case .accessoryInline:
            AccessoryInlineView(entry: entry)
        case .accessoryRectangular:
            AccessoryRectangularView(entry: entry)
                .widgetBackground(backgroundView: EmptyView())
        default:
            Text("Not an implemented widget yet")
        }
    }
}
```

### View Files

| View | File | Purpose |
|------|------|---------|
| `SystemSmallView` | `SystemSmallView.swift` | Home screen small widget |
| `AccessoryCircularView` | `AccessoryCircularView.swift` | Lock screen circular |
| `AccessoryCircularGaugeView` | `AccessoryCircularGaugeView.swift` | Lock screen gauge |
| `AccessoryInlineView` | `AccessoryInlineView.swift` | Lock screen inline text |
| `AccessoryRectangularView` | `AccessoryRectangularView.swift` | Lock screen rectangular |
| `AccessoryRectangularTimestampView` | `AccessoryRectangularTimestampView.swift` | Rectangular with time |

---

## SystemSmallView

**Source**: `nightguard:nightguard Widget Extension/SystemSmallView.swift`

```swift
struct SystemSmallView: View {
    var entry: NightscoutDataEntry
    
    var body: some View {
        VStack {
            // BG Value + Arrow
            HStack {
                Text(entry.sgv)
                    .font(.largeTitle)
                    .foregroundColor(Color(entry.sgvColor))
                Text(entry.bgdeltaArrow)
                    .font(.title)
            }
            
            // Delta
            Text(entry.bgdeltaString)
                .foregroundColor(Color(entry.bgdeltaColor))
            
            // Time ago
            Text(entry.timeAgoString)
                .font(.caption)
            
            // Mini chart (last 4 readings)
            // ...
        }
    }
}
```

---

## Refresh Strategy

### Timeline Refresh

Widgets request refresh after 10 minutes:

```swift
completion(Timeline(entries: entries, policy:
    .after(Calendar.current.date(byAdding: .minute, value: 10, to: Date()) ?? Date())))
```

### Manual Refresh

Widgets are reloaded programmatically when:
1. App receives new data
2. Snooze state changes
3. Settings change

```swift
#if os(iOS)
WidgetCenter.shared.reloadAllTimelines()
#endif
```

---

## iOS 17+ Compatibility

Widget background handling for iOS 17+:

```swift
extension View {
    func widgetBackground(backgroundView: some View) -> some View {
        if #available(iOS 17.0, *) {
            return containerBackground(for: .widget) {
                backgroundView
            }
        } else {
            return background(backgroundView)
        }
    }
}
```

---

## BgEntry Helper Model

For widget display, Nightguard uses a simplified `BgEntry` structure:

```swift
struct BgEntry {
    let value: String        // Display value (with units)
    let valueColor: UIColor  // Color based on range
    let delta: String        // Delta from previous
    let timestamp: Double    // Epoch milliseconds
    let arrow: String        // Trend arrow
}
```

### Delta Calculation

```swift
private func calculateDeltaValues(_ reducedEntries: [BgEntry]) -> [BgEntry] {
    var preceedingEntry: BgEntry?
    var newEntries: [BgEntry] = []
    
    for bgEntry in reducedEntries {
        if let prev = preceedingEntry {
            let v1 = Float(bgEntry.value) ?? 0
            let v2 = Float(prev.value) ?? v1
            let delta = (v1 - v2).cleanSignedValue
            
            newEntries.append(BgEntry(
                value: bgEntry.value,
                valueColor: bgEntry.valueColor,
                delta: delta,
                timestamp: bgEntry.timestamp,
                arrow: bgEntry.arrow
            ))
        }
        preceedingEntry = bgEntry
    }
    
    return newEntries
}
```

---

## Color Coding

Widgets use `UIColorChanger` for consistent color coding:

| Condition | Color |
|-----------|-------|
| High (> upper bound) | Yellow/Orange |
| Low (< lower bound) | Red |
| In range | Green |
| Very old data | Gray |

```swift
valueColor: UIColorChanger.getBgColor(String(bgValue.value))
bgdeltaColor: UIColorChanger.getDeltaLabelColor(data.bgdelta)
```

---

## Widget Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    iOS Widget Architecture                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  NightguardWidgetsBundle                     ││
│  │  ┌─────────────────────────────────────────────────────────┐││
│  │  │ NightguardDefaultWidgets  (Text)                        │││
│  │  │ NightguardTimestampWidgets (Text + Time)                │││
│  │  │ NightguardGaugeWidgets    (Gauge)                       │││
│  │  └─────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────┘│
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              NightguardTimelineProvider                      ││
│  │  ├── getSnapshot()  → Preview or live data                  ││
│  │  ├── getTimeline()  → Schedule refresh                      ││
│  │  └── getTimelineData() → Fetch from Nightscout              ││
│  └─────────────────────────────────────────────────────────────┘│
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │               NightscoutDataEntry                            ││
│  │  ├── sgv, bgdelta, arrow, time                              ││
│  │  ├── iob, cob, battery                                      ││
│  │  ├── lastBGValues: [BgEntry]                                ││
│  │  └── errorMessage                                           ││
│  └─────────────────────────────────────────────────────────────┘│
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  Widget Views                                ││
│  │  ├── SystemSmallView         (Home screen)                  ││
│  │  ├── AccessoryInlineView     (Lock screen inline)           ││
│  │  ├── AccessoryCircularView   (Lock screen circle)           ││
│  │  ├── AccessoryCircularGaugeView (Lock screen gauge)         ││
│  │  └── AccessoryRectangularView (Lock screen rect)            ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Code References

| Purpose | Location |
|---------|----------|
| Widget bundle | `nightguard:nightguard Widget Extension/nightguard_Widget_Extension.swift` |
| Timeline provider | `nightguard:nightguard Widget Extension/NightguardTimelineProvider.swift` |
| Data entry | `nightguard:nightguard Widget Extension/NightscoutDataEntry.swift` |
| System small view | `nightguard:nightguard Widget Extension/SystemSmallView.swift` |
| Accessory views | `nightguard:nightguard Widget Extension/Accessory*.swift` |
