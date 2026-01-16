# Nightguard Alarm Logic

This document describes Nightguard's alarm system, including threshold detection, snoozing, edge detection, low prediction, and smart snooze features.

## Overview

Nightguard implements a sophisticated alarm system with multiple alert types:

| Alarm Type | Description | Default |
|------------|-------------|---------|
| High BG | Blood glucose above upper bound | > 180 mg/dL |
| Low BG | Blood glucose below lower bound | < 80 mg/dL |
| Missed Readings | No data for configured time | > 15 minutes |
| Fast Rise | BG rising too quickly | Edge detection enabled |
| Fast Drop | BG dropping too quickly | Edge detection enabled |
| Low Predicted | Prediction shows low coming | 15 min lookahead |
| Persistent High | High BG for extended period | 30 min at > 250 |

## AlarmRule Class

**Source**: `nightguard:nightguard/domain/AlarmRule.swift`

The `AlarmRule` class is the central controller for all alarm logic, implemented as a collection of static methods and properties.

### User-Configurable Settings

```swift
// Threshold settings
static let alertIfAboveValue = UserDefaultsRepository.upperBound  // Default: 180
static let alertIfBelowValue = UserDefaultsRepository.lowerBound  // Default: 80

// General alarm toggle
static let areAlertsGenerallyDisabled = UserDefaultsValue<Bool>(
    key: "areAlertsGenerallyDisabled", default: false)

// Missed readings alarm
static let noDataAlarmEnabled = UserDefaultsValue<Bool>(
    key: "noDataAlarmEnabled", default: true)
static let minutesWithoutValues = UserDefaultsValue<Int>(
    key: "noDataAlarmAfterMinutes", default: 15)

// Edge detection (fast rise/drop)
static let isEdgeDetectionAlarmEnabled = UserDefaultsValue<Bool>(
    key: "edgeDetectionAlarmEnabled", default: false)
static let deltaAmount = UserDefaultsValue<Float>(
    key: "deltaAmount", default: 8)  // mg/dL per 5 minutes
static let numberOfConsecutiveValues = UserDefaultsValue<Int>(
    key: "numberOfConsecutiveValues", default: 3)

// Low prediction
static let isLowPredictionEnabled = UserDefaultsValue<Bool>(
    key: "lowPredictionEnabled", default: true)
static let minutesToPredictLow = UserDefaultsValue<Int>(
    key: "lowPredictionMinutes", default: 15)

// Smart snooze
static let isSmartSnoozeEnabled = UserDefaultsValue<Bool>(
    key: "smartSnoozeEnabled", default: true)

// Persistent high
static let isPersistentHighEnabled = UserDefaultsValue<Bool>(
    key: "persistentHighEnabled", default: false)
static let persistentHighMinutes = UserDefaultsValue<Int>(
    key: "persistentHighMinutes", default: 30)
static let persistentHighUpperBound = UserDefaultsValue<Float>(
    key: "persistentHighUpperBound", default: 250)
```

---

## Alarm Activation Logic

### Main Entry Point

```swift
static func isAlarmActivated() -> Bool {
    return (getAlarmActivationReason() != nil)
}
```

### Activation Reason Algorithm

```swift
static func getAlarmActivationReason(ignoreSnooze: Bool = false) -> String? {
    
    // 1. Check if alarms are globally disabled
    if areAlertsGenerallyDisabled.value { return nil }
    
    // 2. Check if currently snoozed
    if isSnoozed() && !ignoreSnooze { return nil }
    
    // 3. Get most recent readings
    let bloodValues = [BloodSugar].latestFromRepositories()
    guard let currentReading = bloodValues.last else { return nil }
    
    // 4. Check for missed readings
    if currentReading.isOlderThanXMinutes(minutesWithoutValues.value) {
        if noDataAlarmEnabled.value {
            return "Missed Readings"
        }
        return nil  // Old data can't trigger other alarms
    }
    
    // 5. Check thresholds with smart snooze
    let isTooHigh = currentReading.value > alertIfAboveValue.value
    let isTooLow = currentReading.value < alertIfBelowValue.value
    
    if isSmartSnoozeEnabled.value && (isTooHigh || isTooLow) {
        // Apply smart snooze logic (see below)
    }
    
    // 6. Check high/low thresholds
    if isTooHigh {
        // Check persistent high first
        if isPersistentHighEnabled.value { ... }
        return "High BG"
    }
    if isTooLow {
        return "Low BG"
    }
    
    // 7. Check edge detection
    if isEdgeDetectionAlarmEnabled.value {
        if bloodValuesAreIncreasingTooFast(bloodValues) {
            return "Fast Rise"
        }
        if bloodValuesAreDecreasingTooFast(bloodValues) {
            return "Fast Drop"
        }
    }
    
    // 8. Check low prediction
    if isLowPredictionEnabled.value {
        if let minutesToLow = PredictionService.singleton.minutesTo(low: alertIfBelowValue.value) {
            if minutesToLow <= minutesToPredictLow.value {
                return "Low Predicted in \(minutesToLow)min"
            }
        }
    }
    
    return nil
}
```

---

## Smart Snooze

Smart snooze automatically suppresses alarms when the trend indicates the BG is heading back into range.

### Implementation

```swift
if isSmartSnoozeEnabled.value && (isTooHigh || isTooLow) {
    
    // Check immediate trend direction
    switch bloodValues.trend {
    case .ascending:
        if isTooLow { return nil }  // Going up from low - don't alarm
        
    case .descending:
        if isTooHigh { return nil }  // Going down from high - don't alarm
        
    default:
        break
    }
    
    // Check prediction-based smart snooze
    if isTooHigh {
        if (PredictionService.singleton.minutesTo(low: alertIfAboveValue.value) ?? Int.max) < 30 {
            return nil  // Will be back in range within 30 min
        }
    } else if isTooLow {
        if (PredictionService.singleton.minutesTo(high: alertIfBelowValue.value) ?? Int.max) < 30 {
            return nil  // Will be back in range within 30 min
        }
    }
}
```

---

## Edge Detection (Fast Rise/Drop)

Edge detection alerts when BG is changing rapidly, even if still in range.

### Algorithm

```swift
fileprivate static func bloodValuesAreMovingTooFast(_ bloodValues: [BloodSugar], increasing: Bool) -> Bool {
    
    // Need at least numberOfConsecutiveValues readings
    guard let readings = bloodValues.lastConsecutive(numberOfConsecutiveValues.value),
          readings.count > 1 else {
        return false
    }
    
    // Calculate total change over the period
    let totalMinutes = Float((readings.last!.timestamp - readings.first!.timestamp) / 60000)
    var totalDelta = readings.last!.value - readings.first!.value
    if !increasing { totalDelta *= -1 }
    
    // Compare against threshold (deltaAmount per 5 minutes)
    let alarmDeltaPerMinute = deltaAmount.value / 5
    if totalDelta < (totalMinutes * alarmDeltaPerMinute) {
        return false
    }
    
    // Check recent readings specifically
    let recentMinutes = Float((readings.last!.timestamp - readings[readings.count-2].timestamp) / 60000)
    var recentDelta = readings.last!.value - readings[readings.count-2].value
    if !increasing { recentDelta *= -1 }
    
    // If lost reading (gap > 7 min), trigger alarm
    if recentMinutes > 7 { return true }
    
    // If recent rate halved, don't trigger
    if recentDelta < ((recentMinutes * alarmDeltaPerMinute) / 2) {
        return false
    }
    
    return true
}
```

### Default Threshold

- **deltaAmount**: 8 mg/dL per 5 minutes (1.6 mg/dL per minute)
- **numberOfConsecutiveValues**: 3 readings

---

## Low Prediction

Low prediction uses trend analysis to warn of impending hypoglycemia.

**Source**: `nightguard:nightguard/external/PredictionService.swift`

### Integration with AlarmRule

```swift
if isLowPredictionEnabled.value {
    if let minutesToLow = PredictionService.singleton.minutesTo(low: alertIfBelowValue.value) {
        if minutesToLow <= minutesToPredictLow.value {
            return String(format: "Low Predicted in %dmin", minutesToLow)
        }
    }
}
```

### Default Settings

- **minutesToPredictLow**: 15 minutes
- Prediction uses linear extrapolation from recent readings

---

## Persistent High

Persistent high triggers when BG stays elevated for an extended period.

### Implementation

```swift
if isPersistentHighEnabled.value {
    if currentReading.value < persistentHighUpperBound.value {
        
        let lastReadings = bloodValues.lastXMinutes(persistentHighMinutes.value)
        
        // Need at least one reading per 10 minutes
        if !lastReadings.isEmpty && (lastReadings.count >= (persistentHighMinutes.value / 10)) {
            if lastReadings.allSatisfy({ AlarmRule.isTooHigh($0.value) }) {
                return "Persistent High BG"
            }
        }
    }
}
```

### Default Settings

- **persistentHighMinutes**: 30 minutes
- **persistentHighUpperBound**: 250 mg/dL (only triggers below this to avoid duplicate high alerts)

---

## Snooze System

### Manual Snooze

```swift
static func snooze(_ minutes: Int) {
    snoozedUntilTimestamp.value = Date().timeIntervalSince1970 + Double(60 * minutes)
    SnoozeMessage(timestamp: snoozedUntilTimestamp.value).send()
}

static func disableSnooze() {
    snoozedUntilTimestamp.value = TimeInterval()
    SnoozeMessage(timestamp: snoozedUntilTimestamp.value).send()
}
```

### Snooze State Check

```swift
static func isSnoozed() -> Bool {
    let currentTimestamp = Date().timeIntervalSince1970
    return currentTimestamp < snoozedUntilTimestamp.value
}

static func getRemainingSnoozeMinutes() -> Int {
    let currentTimestamp = TimeService.getCurrentTime()
    if (snoozedUntilTimestamp.value - currentTimestamp) <= 0 {
        return 0
    }
    return Int(ceil((snoozedUntilTimestamp.value - currentTimestamp) / 60.0))
}
```

### Watch Synchronization

Snooze state is synchronized between phone and watch via WatchConnectivity:

```swift
static func snoozeFromMessage(_ message: SnoozeMessage) {
    snoozedUntilTimestamp.value = message.timestamp
}
```

---

## Simplified Alarm Check (Background)

For background processing with limited resources, a simplified check is available:

```swift
static func determineAlarmActivationReasonBy(_ nightscoutData: NightscoutData) -> String? {
    
    if areAlertsGenerallyDisabled.value { return nil }
    if isSnoozed() { return nil }
    
    // Check missed readings
    if nightscoutData.isOlderThanXMinutes(minutesWithoutValues.value) {
        if noDataAlarmEnabled.value {
            return "Missed Readings"
        }
        return nil
    }
    
    // Simple threshold check only (no edge detection, prediction, etc.)
    let sgvFloat = Float(nightscoutData.sgv) ?? 0.0
    if sgvFloat > alertIfAboveValue.value {
        return "High BG"
    }
    if sgvFloat < alertIfBelowValue.value {
        return "Low BG"
    }
    
    return nil
}
```

---

## Settings Synchronization

Alarm settings are grouped for Watch synchronization:

```swift
.group(UserDefaultsValueGroups.GroupNames.watchSync)
.group(UserDefaultsValueGroups.GroupNames.alarm)
```

This ensures phone and watch have consistent alarm behavior.

---

## Alarm Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Alarm Evaluation Flow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐                                           │
│  │ New BG Reading   │                                           │
│  └────────┬─────────┘                                           │
│           ▼                                                      │
│  ┌──────────────────┐    Yes                                    │
│  │ Alarms Disabled? ├────────────► No Alarm                     │
│  └────────┬─────────┘                                           │
│           │ No                                                   │
│           ▼                                                      │
│  ┌──────────────────┐    Yes                                    │
│  │ Currently Snoozed?├───────────► No Alarm                     │
│  └────────┬─────────┘                                           │
│           │ No                                                   │
│           ▼                                                      │
│  ┌──────────────────┐    Yes    ┌────────────────────┐          │
│  │ Data Too Old?    ├──────────►│ "Missed Readings"  │          │
│  └────────┬─────────┘           └────────────────────┘          │
│           │ No                                                   │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │ Check High/Low   │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│     ┌─────┴─────┐                                               │
│     ▼           ▼                                               │
│  ┌──────┐   ┌──────┐                                            │
│  │ High │   │ Low  │                                            │
│  └───┬──┘   └───┬──┘                                            │
│      │          │                                                │
│      ▼          ▼                                                │
│  ┌────────────────────┐    Yes                                  │
│  │ Smart Snooze Active?├───► Check Trend/Prediction             │
│  └────────┬───────────┘       │                                 │
│           │ No                │ Heading to range?               │
│           │                   │ Yes → No Alarm                  │
│           │                   │ No  ↓                           │
│           ▼                   ▼                                 │
│  ┌────────────────────┐   ┌────────────────────┐               │
│  │ "High BG" / "Low BG"│   │ "High BG" / "Low BG"│               │
│  └────────────────────┘   └────────────────────┘               │
│           │                                                      │
│           │ (If in range)                                        │
│           ▼                                                      │
│  ┌──────────────────────┐    Yes    ┌────────────────────┐      │
│  │ Edge Detection On?   ├──────────►│ Check Rise/Drop    │      │
│  └────────┬─────────────┘           └─────────┬──────────┘      │
│           │ No                                 │ Fast? → Alarm  │
│           ▼                                    ▼                │
│  ┌──────────────────────┐    Yes    ┌────────────────────┐      │
│  │ Low Prediction On?   ├──────────►│ Check Prediction   │      │
│  └────────┬─────────────┘           └─────────┬──────────┘      │
│           │ No                                 │ Low soon? Alarm│
│           ▼                                    ▼                │
│  ┌──────────────────┐                                           │
│  │ No Alarm         │                                           │
│  └──────────────────┘                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Code References

| Purpose | Location |
|---------|----------|
| AlarmRule class | `nightguard:nightguard/domain/AlarmRule.swift` |
| PredictionService | `nightguard:nightguard/external/PredictionService.swift` |
| AlarmNotificationService | `nightguard:nightguard/external/AlarmNotificationService.swift` |
| AlarmSound | `nightguard:nightguard/app/AlarmSound.swift` |
| BloodSugar array extensions | `nightguard:nightguard/domain/BloodSugarArrayExtension.swift` |
