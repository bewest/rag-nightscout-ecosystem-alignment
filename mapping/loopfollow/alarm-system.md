# LoopFollow Alarm System Deep Dive

This document provides comprehensive documentation of LoopFollow's alarm system, covering all 20 alarm types, condition evaluation logic, day/night scheduling, and snooze behavior.

---

## Executive Summary

LoopFollow implements a sophisticated alarm system designed for caregivers monitoring T1D patients using AID systems. The system supports 20 distinct alarm types with configurable conditions, predictive triggering, persistence requirements, and day/night scheduling.

| Aspect | Value |
|--------|-------|
| **Alarm Types** | 20 distinct types |
| **Evaluation Interval** | Every 60 seconds (default) |
| **Priority System** | Ordered by type priority |
| **Snooze Support** | Per-alarm and global snooze |
| **Day/Night Modes** | Configurable sound and activation schedules |

---

## Source Files

| File | Purpose |
|------|---------|
| `LoopFollow/Alarm/Alarm.swift` | Core alarm model and trigger logic |
| `LoopFollow/Alarm/AlarmType/AlarmType.swift` | Alarm type enumeration |
| `LoopFollow/Alarm/AlarmManager.swift` | Singleton manager for alarm evaluation |
| `LoopFollow/Alarm/AlarmCondition/AlarmCondition.swift` | Base protocol for conditions |
| `LoopFollow/Alarm/AlarmCondition/*.swift` | Individual condition implementations |
| `LoopFollow/Alarm/AlarmConfiguration.swift` | Global alarm settings |
| `LoopFollow/Alarm/AlarmData.swift` | Data structure for evaluation |
| `LoopFollow/Task/AlarmTask.swift` | Scheduled alarm check task |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LoopFollow Alarm Architecture                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         TaskScheduler                                    ││
│  │  • Runs AlarmTask every 60 seconds                                      ││
│  │  • Builds AlarmData from current state                                  ││
│  │  • Calls AlarmManager.checkAlarms(data:)                                ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    ↓                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        AlarmManager (Singleton)                          ││
│  │                                                                          ││
│  │  • Maintains evaluators: [AlarmType: AlarmCondition]                    ││
│  │  • Sorts alarms by priority                                             ││
│  │  • Applies global snooze                                                ││
│  │  • Evaluates each alarm via shouldFire()                                ││
│  │  • Triggers first matching alarm (one per tick)                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    ↓                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        AlarmCondition Protocol                           ││
│  │                                                                          ││
│  │  shouldFire(alarm, data, now, config) → Bool                            ││
│  │    1. Check alarm.isEnabled                                             ││
│  │    2. Check per-alarm snooze                                            ││
│  │    3. Check BG limits via passesBGLimits()                              ││
│  │    4. Check day/night activeOption                                      ││
│  │    5. Call type-specific evaluate() method                              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    ↓                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        Alarm.trigger()                                   ││
│  │                                                                          ││
│  │  1. Check global mute                                                   ││
│  │  2. Check mute during calls                                             ││
│  │  3. Apply day/night sound rules                                         ││
│  │  4. Send notification via UNUserNotificationCenter                      ││
│  │  5. Play sound with optional repeat and delay                           ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Alarm Types

### Complete Enumeration

```swift
// loopfollow:LoopFollow/Alarm/AlarmType/AlarmType.swift#L8-L30
enum AlarmType: String, CaseIterable, Codable {
    case temporary = "Temporary Alert"
    case iob = "IOB Alert"
    case cob = "COB Alert"
    case low = "Low BG Alert"
    case high = "High BG Alert"
    case fastDrop = "Fast Drop Alert"
    case fastRise = "Fast Rise Alert"
    case missedReading = "Missed Reading Alert"
    case notLooping = "Not Looping Alert"
    case missedBolus = "Missed Bolus Alert"
    case sensorChange = "Sensor Change Alert"
    case pumpChange = "Pump Change Alert"
    case pump = "Pump Insulin Alert"
    case battery = "Low Battery"
    case batteryDrop = "Battery Drop"
    case recBolus = "Rec. Bolus"
    case overrideStart = "Override Started"
    case overrideEnd = "Override Ended"
    case tempTargetStart = "Temp Target Started"
    case tempTargetEnd = "Temp Target Ended"
    case buildExpire = "Looping app expiration"
}
```

### Alarm Type Groups

| Group | Alarm Types |
|-------|-------------|
| **Glucose** | low, high, fastDrop, fastRise, missedReading, temporary |
| **Insulin / Food** | iob, cob, missedBolus, recBolus |
| **Device / System** | battery, batteryDrop, pump, pumpChange, sensorChange, notLooping, buildExpire |
| **Override / Target** | overrideStart, overrideEnd, tempTargetStart, tempTargetEnd |

---

## Alarm Model

### Core Structure

```swift
// loopfollow:LoopFollow/Alarm/Alarm.swift#L50-L97
struct Alarm: Identifiable, Codable, Equatable {
    var id: UUID = .init()
    var type: AlarmType
    var name: String
    var isEnabled: Bool = true
    var snoozedUntil: Date?
    
    // BG thresholds
    var aboveBG: Double?
    var belowBG: Double?
    
    // Generic threshold (days, units, percentage)
    var threshold: Double?
    
    // Predictive look-ahead (minutes)
    var predictiveMinutes: Int?
    
    // Delta value (mg/dL change or units)
    var delta: Double?
    
    // Persistence requirement (minutes)
    var persistentMinutes: Int?
    
    // Monitoring window (readings or minutes)
    var monitoringWindow: Int?
    
    // Sound settings
    var soundFile: SoundFile
    var snoozeDuration: Int = 5
    var playSoundOption: PlaySoundOption = .always
    var repeatSoundOption: RepeatSoundOption = .always
    var soundDelay: Int = 0
    
    // Time-of-day activation
    var activeOption: ActiveOption = .always
    
    // Missed bolus specific
    var missedBolusPrebolusWindow: Int?
    var missedBolusIgnoreSmallBolusUnits: Double?
    var missedBolusIgnoreUnderGrams: Double?
    var missedBolusIgnoreUnderBG: Double?
    
    // Bolus count tracking
    var bolusCountThreshold: Int?
    var bolusWindowMinutes: Int?
}
```

### Day/Night Options

```swift
enum PlaySoundOption: String, CaseIterable, Codable {
    case always, day, night, never
}

enum RepeatSoundOption: String, CaseIterable, Codable {
    case always, day, night, never
}

enum ActiveOption: String, CaseIterable, Codable {
    case always, day, night
}
```

---

## Alarm Condition Details

### 1. Low BG Condition

**File**: `LoopFollow/Alarm/AlarmCondition/LowBGCondition.swift`

**Trigger Logic**:
- Latest BG ≤ `belowBG` threshold
- OR any predicted BG within `predictiveMinutes` is ≤ threshold
- AND all BG readings in `persistentMinutes` window are ≤ threshold (if configured)

| Parameter | Field | Description |
|-----------|-------|-------------|
| Threshold | `belowBG` | BG value in mg/dL |
| Predictive | `predictiveMinutes` | Look-ahead minutes for predictions |
| Persistent | `persistentMinutes` | Duration BG must stay low |

```swift
// Predictive check example
let lookAhead = min(predictionData.count, ceil(predictiveMinutes / 5.0))
for i in 0..<lookAhead where isLow(predictionData[i]) {
    predictiveTrigger = true
    break
}
```

### 2. High BG Condition

**File**: `LoopFollow/Alarm/AlarmCondition/HighBGCondition.swift`

**Trigger Logic**:
- Latest BG ≥ `aboveBG` threshold
- AND all BG readings in `persistentMinutes` window are ≥ threshold (if configured)

| Parameter | Field | Description |
|-----------|-------|-------------|
| Threshold | `aboveBG` | BG value in mg/dL |
| Persistent | `persistentMinutes` | Duration BG must stay high |

### 3. Fast Drop Condition

**File**: `LoopFollow/Alarm/AlarmCondition/FastDropCondition.swift`

**Trigger Logic**:
- Each of the last `monitoringWindow` readings dropped by ≥ `delta` mg/dL

| Parameter | Field | Description |
|-----------|-------|-------------|
| Drop Amount | `delta` | Required drop per reading (mg/dL) |
| Readings | `monitoringWindow` | Number of consecutive drops needed |

**Default**: 18 mg/dL drop over 2 readings

```swift
for i in 1...dropsNeeded {
    let delta = Double(readings[i - 1].sgv - readings[i].sgv)
    if delta < dropPerReading { return false }
}
return true
```

### 4. Fast Rise Condition

**File**: `LoopFollow/Alarm/AlarmCondition/FastRiseCondition.swift`

**Trigger Logic**: Mirror of Fast Drop but for increases

| Parameter | Field | Description |
|-----------|-------|-------------|
| Rise Amount | `delta` | Required rise per reading (mg/dL) |
| Readings | `monitoringWindow` | Number of consecutive rises needed |

**Default**: 10 mg/dL rise over 3 readings

### 5. Missed Reading Condition

**File**: `LoopFollow/Alarm/AlarmCondition/MissedReadingCondition.swift`

**Trigger Logic**:
- No BG reading received for ≥ `threshold` minutes

| Parameter | Field | Description |
|-----------|-------|-------------|
| Minutes | `threshold` | Minutes without a reading |

**Default**: 16 minutes

### 6. Not Looping Condition

**File**: `LoopFollow/Alarm/AlarmCondition/NotLoopingCondition.swift`

**Trigger Logic**:
- Time since last loop run ≥ `threshold` minutes
- AND last looping check was within 6 minutes (data freshness guard)

| Parameter | Field | Description |
|-----------|-------|-------------|
| Minutes | `threshold` | Minutes since last loop |

**Default**: 31 minutes

```swift
let elapsedSecs = Date().timeIntervalSince1970 - lastLoopTime
let limitSecs = thresholdMinutes * 60
return elapsedSecs >= limitSecs
```

### 7. IOB Condition

**File**: `LoopFollow/Alarm/AlarmCondition/IOBCondition.swift`

**Trigger Logic** (any of):
1. Latest IOB ≥ `threshold` units
2. Within `predictiveMinutes`, count of boluses ≥ `monitoringWindow` where each ≥ `delta` units
3. Within same window, sum of boluses ≥ `threshold`

| Parameter | Field | Description |
|-----------|-------|-------------|
| IOB Max | `threshold` | Maximum IOB in units |
| Min Bolus | `delta` | Minimum bolus size to count |
| Bolus Count | `monitoringWindow` | Number of boluses needed |
| Lookback | `predictiveMinutes` | Window for bolus counting |

**Default**: 6U threshold, 1U min bolus, 2 boluses in 30 minutes

### 8. COB Condition

**File**: `LoopFollow/Alarm/AlarmCondition/COBCondition.swift`

**Trigger Logic**:
- Current COB ≥ `threshold` grams

| Parameter | Field | Description |
|-----------|-------|-------------|
| COB Max | `threshold` | Maximum COB in grams |

**Default**: 20 grams

### 9. Missed Bolus Condition

**File**: `LoopFollow/Alarm/AlarmCondition/MissedBolusCondition.swift`

**Trigger Logic**:
- Carb entry logged > `delayMin` minutes ago (but within 60 min)
- AND carbs > `minCarbGr` grams
- AND current BG > `minBG`
- AND no bolus ≥ `minBolusU` within prebolus window
- AND not already alerted for this carb entry

| Parameter | Field | Description |
|-----------|-------|-------------|
| Delay | `monitoringWindow` | Minutes after carbs to check |
| Prebolus | `predictiveMinutes` | Window before carbs for prebolus |
| Min Bolus | `delta` | Ignore boluses smaller than this |
| Min Carbs | `threshold` | Ignore carb entries smaller |
| Min BG | `aboveBG` | Ignore when BG is below this |

**Default**: 15 min delay, 15 min prebolus, 0.1U min bolus, 4g min carbs

### 10. Recommended Bolus Condition

**File**: `LoopFollow/Alarm/AlarmCondition/RecBolusCondition.swift`

**Trigger Logic**:
- Recommended bolus ≥ `threshold` units
- AND either first time above threshold OR increased by >5%

| Parameter | Field | Description |
|-----------|-------|-------------|
| Min Rec | `threshold` | Minimum recommended bolus |

**Default**: 1 unit

### 11. Battery Condition

**File**: `LoopFollow/Alarm/AlarmCondition/BatteryCondition.swift`

**Trigger Logic**:
- Phone battery level ≤ `threshold` percent

| Parameter | Field | Description |
|-----------|-------|-------------|
| Min Level | `threshold` | Battery percentage |

**Default**: 20%

### 12. Battery Drop Condition

**File**: `LoopFollow/Alarm/AlarmCondition/BatteryDropCondition.swift`

**Trigger Logic**:
- Battery dropped by ≥ `delta` percent within `monitoringWindow` minutes
- Ignores drop from 100% (charger unplugged)

| Parameter | Field | Description |
|-----------|-------|-------------|
| Drop | `delta` | Percentage drop |
| Window | `monitoringWindow` | Minutes to observe |

**Default**: 10% drop in 15 minutes

### 13. Pump Volume Condition

**File**: `LoopFollow/Alarm/AlarmCondition/PumpVolumeCondition.swift`

**Trigger Logic**:
- Reservoir level ≤ `threshold` units

| Parameter | Field | Description |
|-----------|-------|-------------|
| Min Units | `threshold` | Reservoir units remaining |

**Default**: 20 units

### 14. Sensor Change Condition

**File**: `LoopFollow/Alarm/AlarmCondition/SensorAgeCondition.swift`

**Trigger Logic**:
- Days since sensor insertion ≥ `threshold`

| Parameter | Field | Description |
|-----------|-------|-------------|
| Days | `threshold` | Sensor age in days |

**Default**: 12 days

### 15. Pump Change Condition

**File**: `LoopFollow/Alarm/AlarmCondition/PumpChangeCondition.swift`

**Trigger Logic**:
- Days since pump/cannula insertion ≥ `threshold`

| Parameter | Field | Description |
|-----------|-------|-------------|
| Days | `threshold` | Pump site age in days |

**Default**: 12 days (for pod expiration)

### 16. Build Expire Condition

**File**: `LoopFollow/Alarm/AlarmCondition/BuildExpireCondition.swift`

**Trigger Logic**:
- Days until Loop app build expires ≤ `threshold`

| Parameter | Field | Description |
|-----------|-------|-------------|
| Days | `threshold` | Days before expiration |

**Default**: 7 days

### 17-20. Event Conditions

| Condition | Trigger |
|-----------|---------|
| **Override Start** | Override just activated |
| **Override End** | Override just ended |
| **Temp Target Start** | Temp target just activated |
| **Temp Target End** | Temp target just ended |

These track the latest event timestamp and fire once per event.

### 21. Temporary Condition

**File**: `LoopFollow/Alarm/AlarmCondition/TemporaryCondition.swift`

**Trigger Logic**:
- Single-fire alarm when BG passes configured limits
- Auto-disables after triggering

---

## Alarm Data Structure

```swift
// loopfollow:LoopFollow/Alarm/AlarmData.swift#L6-L25
struct AlarmData: Codable {
    let bgReadings: [GlucoseValue]         // Last 24 readings (oldest → newest)
    let predictionData: [GlucoseValue]     // Next 12 predictions
    let expireDate: Date?                  // App build expiration
    let lastLoopTime: TimeInterval?        // Last loop run timestamp
    let latestOverrideStart: TimeInterval?
    let latestOverrideEnd: TimeInterval?
    let latestTempTargetStart: TimeInterval?
    let latestTempTargetEnd: TimeInterval?
    let recBolus: Double?                  // Recommended bolus
    let COB: Double?                       // Carbs on board
    let sageInsertTime: TimeInterval?      // Sensor insertion time
    let pumpInsertTime: TimeInterval?      // Pump site insertion time
    let latestPumpVolume: Double?          // Reservoir level
    let IOB: Double?                       // Insulin on board
    let recentBoluses: [BolusEntry]        // Recent bolus entries
    let latestBattery: Double?             // Phone battery level
    let batteryHistory: [batteryStruct]    // Battery readings over time
    let recentCarbs: [CarbSample]          // Recent carb entries
}
```

---

## Global Configuration

```swift
// loopfollow:LoopFollow/Alarm/AlarmConfiguration.swift#L6-L33
struct AlarmConfiguration: Codable, Equatable {
    var snoozeUntil: Date?              // Global snooze all alarms
    var muteUntil: Date?                // Global mute sounds
    var dayStart: TimeOfDay             // Default: 6:00 AM
    var nightStart: TimeOfDay           // Default: 10:00 PM
    
    var overrideSystemOutputVolume: Bool // Override device volume
    var forcedOutputVolume: Float        // 0.0 to 1.0
    var audioDuringCalls: Bool           // Play during phone calls
    var ignoreZeroBG: Bool               // Ignore zero BG readings
    var autoSnoozeCGMStart: Bool         // Snooze during CGM warmup
    var enableVolumeButtonSnooze: Bool   // Use volume buttons to snooze
}
```

---

## Evaluation Flow

### AlarmManager.checkAlarms()

```swift
// loopfollow:LoopFollow/Alarm/AlarmManager.swift#L42-L153
func checkAlarms(data: AlarmData) {
    // 1. Check global snooze
    if let snoozeUntil = config.snoozeUntil, snoozeUntil > now {
        stopAlarm()
        return
    }
    
    // 2. Sort alarms by priority
    let sorted = alarms.sorted(by: Alarm.byPriorityThenSpec)
    
    // 3. Iterate through alarms
    for alarm in sorted {
        // Skip if same type as snoozed alarm
        if alarm.type == skipType { continue }
        
        // Skip BG-based alarms without recent data (except missedReading)
        if alarm.type.isBGBased && !isLatestReadingRecent { continue }
        
        // Skip if already handled this BG reading
        if alarm.type.isBGBased && latestDate <= lastHandled { continue }
        
        // Skip if per-alarm snoozed
        if let until = alarm.snoozedUntil, until > now {
            skipType = alarm.type
            continue
        }
        
        // Evaluate condition
        guard checker.shouldFire(alarm, data, now, config) else {
            // Stop if currently active but no longer meets requirements
            if currentAlarm == alarm.id { stopAlarm() }
            continue
        }
        
        // If already active, keep it
        if currentAlarm == alarm.id { break }
        
        // Fire the alarm
        currentAlarm = alarm.id
        alarm.trigger(config, now)
        
        // Track handled BG time
        if alarm.type.isBGBased { lastBGAlarmTime = latestDate }
        
        // Auto-disable temporary alarms
        if alarm.type == .temporary { alarm.isEnabled = false }
        
        break  // Only one alarm per tick
    }
}
```

### AlarmCondition.shouldFire()

```swift
// loopfollow:LoopFollow/Alarm/AlarmCondition/AlarmCondition.swift#L53-L81
func shouldFire(alarm: Alarm, data: AlarmData, now: Date, config: AlarmConfiguration) -> Bool {
    // 1. Check enabled
    guard alarm.isEnabled else { return false }
    
    // 2. Check per-alarm snooze
    if let snooze = alarm.snoozedUntil, snooze > now { return false }
    
    // 3. Check BG limits
    if !passesBGLimits(alarm, data) { return false }
    
    // 4. Check time-of-day
    let isNight = (nowMin < dayStart) || (nowMin >= nightStart)
    switch alarm.activeOption {
    case .always: break
    case .day: guard !isNight else { return false }
    case .night: guard isNight else { return false }
    }
    
    // 5. Run type-specific logic
    return evaluate(alarm, data, now)
}
```

---

## Snooze Behavior

### Per-Alarm Snooze

```swift
// loopfollow:LoopFollow/Alarm/AlarmManager.swift#L155-L169
func performSnooze(_ snoozeUnits: Int? = nil) {
    let units = snoozeUnits ?? alarm.snoozeDuration
    if units > 0 {
        let snoozeSeconds = Double(units) * alarm.type.snoozeTimeUnit.seconds
        alarm.snoozedUntil = Date().addingTimeInterval(snoozeSeconds)
    }
    stopAlarm()
}
```

### Snooze Time Units

| Alarm Type | Snooze Unit | Example |
|------------|-------------|---------|
| BG alarms | Minutes | 5 → 5 minutes |
| Device alarms | Hours | 1 → 1 hour |
| Build expire | Days | 1 → 1 day |

---

## Sound Configuration

### Alarm Trigger Sound Logic

```swift
// loopfollow:LoopFollow/Alarm/Alarm.swift#L196-L261
func trigger(config: AlarmConfiguration, now: Date) {
    var playSound = true
    
    // Global mute check
    if let until = config.muteUntil, until > now { playSound = false }
    
    // Mute during calls check
    if !config.audioDuringCalls && isOnPhoneCall() { playSound = false }
    
    // Day/night sound check
    let isNight = ...
    switch playSoundOption {
    case .always: break
    case .never: playSound = false
    case .day where !isDay: playSound = false
    case .night where !isNight: playSound = false
    }
    
    // Repeat setting
    let shouldRepeat = repeatSoundOption matches time-of-day
    
    // Send notification
    AlarmManager.shared.sendNotification(title: type.rawValue, actionTitle: "Snooze")
    
    // Play sound
    if playSound {
        AlarmSound.setSoundFile(str: soundFile.rawValue)
        AlarmSound.play(repeating: shouldRepeat, delay: soundDelay)
    }
}
```

---

## Comparison with LoopCaregiver

| Feature | LoopFollow | LoopCaregiver |
|---------|------------|---------------|
| **Alarm Types** | 20 | ~5 (basic) |
| **Predictive Alarms** | Yes (low BG) | No |
| **Persistent Alarms** | Yes (N minutes) | No |
| **Delta Alarms** | Yes (fast rise/drop) | No |
| **Day/Night Scheduling** | Yes (sound + active) | No |
| **Custom Sounds** | Yes (20+ sounds) | System sounds |
| **Missed Bolus** | Yes (sophisticated) | No |
| **Build Expiration** | Yes | No |
| **Snooze Options** | Per-alarm + global | Basic |

---

## Cross-References

- [LoopCaregiver Authentication](../loopcaregiver/authentication.md) - Compare alarm vs command focus
- [LoopCaregiver Remote Commands](../loopcaregiver/remote-commands.md) - Remote control comparison
- [Nightscout Data Model](../../docs/10-domain/nightscout-data-model.md) - Data sources for alarms

---

## Gaps Identified

| Gap ID | Description |
|--------|-------------|
| GAP-LF-001 | Alarm configuration not synced to Nightscout (local only) |
| GAP-LF-002 | No alarm history or audit log |
| GAP-LF-003 | Prediction data not available for Trio (only Loop) |
| GAP-LF-004 | No multi-user alarm acknowledgment (caregiver coordination) |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial deep dive documentation |
