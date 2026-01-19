# Trio Overrides and Temp Targets

This document details how Trio implements profile overrides and temporary targets.

## Source Files

| File | Purpose |
|------|---------|
| `trio:Trio/Sources/APS/OpenAPS/OpenAPS.swift` | oref2() function |
| `trio:Trio/Sources/APS/Storage/OverrideStorage.swift` | Override state model |
| `trio:Trio/Sources/Models/TempTarget.swift` | Temp target model |
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl+Override.swift` | Remote override commands |
| `trio:Model/TrioCoreDataPersistentContainer.xcdatamodeld/` | Override CoreData entity |

---

## Override Architecture

Trio stores overrides in CoreData and passes them to the algorithm via `oref2_variables`:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Override Flow                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CoreData                                                        │
│  ├── Override entity (enabled, percentage, target, duration)   │
│  ├── TempTargets entity (target, duration, hbt)                │
│  └── TempTargetsSlider entity (preset percentages)             │
│                 │                                                │
│                 ▼                                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              OpenAPS.oref2()                                ││
│  │  Fetches override state from CoreData                       ││
│  │  Calculates TDD averages                                    ││
│  │  Returns Oref2_variables                                    ││
│  └─────────────────────────────────────────────────────────────┘│
│                 │                                                │
│                 ▼                                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │           determine-basal.js                                ││
│  │  Applies override percentage to ISF/CR                      ││
│  │  Applies override target                                    ││
│  │  Checks SMB schedule disable                                ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Override Parameters

### Oref2_variables Model

```swift
// trio:Oref2_variables.swift
struct Oref2_variables: JSON {
    // TDD data
    let average_total_data: Decimal    // 10-day TDD average
    let weightedAverage: Decimal       // Weighted TDD
    let past2hoursAverage: Decimal     // Recent 2h TDD
    let date: Date
    
    // Temp target state
    let isEnabled: Bool                // Temp target active
    let hbt: Decimal                   // Half-basal exercise target
    
    // Override state
    let presetActive: Bool
    let overridePercentage: Decimal    // 100 = normal
    let useOverride: Bool              // Override active flag
    let duration: Decimal              // Duration in minutes
    let unlimited: Bool                // Indefinite override
    let overrideTarget: Decimal        // Custom target (0 = use profile)
    
    // SMB control
    let smbIsOff: Bool                 // Disable SMBs
    let smbIsScheduledOff: Bool        // Time-based SMB disable
    let start: Decimal                 // Schedule start hour
    let end: Decimal                   // Schedule end hour
    let smbMinutes: Decimal            // Custom SMB max minutes
    let uamMinutes: Decimal            // Custom UAM max minutes
    
    // Advanced settings
    let advancedSettings: Bool
    let isfAndCr: Bool                 // Override affects both ISF and CR
    let isf: Bool                      // Override affects ISF only
    let cr: Bool                       // Override affects CR only
}
```

---

## Override Percentage Effects

### Algorithm Application

```javascript
// trio:trio-oref/lib/determine-basal/determine-basal.js#L191-L203
var overrideFactor = 1;
var sensitivity = profile.sens;
var carbRatio = profile.carb_ratio;

if (oref2_variables.useOverride) {
    overrideFactor = oref2_variables.overridePercentage / 100;
    
    if (isfAndCr) {
        // Both scaled together
        sensitivity /= overrideFactor;
        carbRatio /= overrideFactor;
    } else {
        // Individual scaling
        if (cr_) { carbRatio /= overrideFactor; }
        if (isf) { sensitivity /= overrideFactor; }
    }
}
```

### Percentage Interpretation

| Override % | ISF Effect | CR Effect | Insulin Delivery |
|------------|------------|-----------|------------------|
| 50% | ISF × 2 | CR × 2 | Less aggressive |
| 100% | No change | No change | Normal |
| 150% | ISF ÷ 1.5 | CR ÷ 1.5 | More aggressive |
| 200% | ISF ÷ 2 | CR ÷ 2 | Much more aggressive |

---

## Override Target

When an override sets a custom target:

```javascript
// trio:trio-oref/lib/determine-basal/determine-basal.js#L147-L151
var profileTarget = profile.min_bg;
var overrideTarget = oref2_variables.overrideTarget;

if (overrideTarget != 0 && overrideTarget != 6 && oref2_variables.useOverride && !profile.temptargetSet) {
    profileTarget = overrideTarget;
}
```

**Note**: Override target is only used if no temp target is active (`!profile.temptargetSet`).

---

## Override Duration

```swift
// trio:OpenAPS.swift#L194-L211
if useOverride {
    duration = (overrideArray.first?.duration ?? 0) as Decimal
    let addedMinutes = Int(duration)
    let date = overrideArray.first?.date ?? Date()
    
    // Check if override has expired
    if date.addingTimeInterval(addedMinutes.minutes.timeInterval) < Date(),
       !unlimited
    {
        useOverride = false
        // Save disabled state to CoreData
        let saveToCoreData = Override(context: self.coredataContext)
        saveToCoreData.enabled = false
        saveToCoreData.date = Date()
        saveToCoreData.duration = 0
        saveToCoreData.indefinite = false
        saveToCoreData.percentage = 100
        try? self.coredataContext.save()
    }
}
```

---

## SMB Schedule Disable

Overrides can disable SMBs for a time window:

```javascript
// trio:trio-oref/lib/determine-basal/determine-basal.js#L48-L70
if (oref_variables.smbIsScheduledOff) {
    let currentHour = new Date(time.getHours());
    let startTime = oref_variables.start;
    let endTime = oref_variables.end;
    
    // Handle window that spans midnight
    if (startTime < endTime && (currentHour >= startTime && currentHour < endTime)) {
        console.error("SMB disabled: current time is in SMB disabled scheduled");
        return false;
    } else if (startTime > endTime && (currentHour >= startTime || currentHour < endTime)) {
        console.error("SMB disabled: current time is in SMB disabled scheduled");
        return false;
    }
}
```

---

## Temp Targets

### Temp Target Model

```swift
// trio:TempTarget.swift
struct TempTarget: JSON {
    let id: String
    let createdAt: Date
    let targetTop: Decimal       // High target (mg/dL)
    let targetBottom: Decimal    // Low target (mg/dL)
    let duration: Decimal        // Duration in minutes
    let enteredBy: String?
    let reason: String?
}
```

### Temp Target Processing

```swift
// trio:OpenAPS.swift#L222-L240
if temptargetActive {
    let duration_ = Int(truncating: tempTargetsArray.first?.duration ?? 0)
    let hbt = tempTargetsArray.first?.hbt ?? Double(hbt_)
    let startDate = tempTargetsArray.first?.startDate ?? Date()
    let durationPlusStart = startDate.addingTimeInterval(duration_.minutes.timeInterval)
    let remainingDuration = durationPlusStart.timeIntervalSinceNow.minutes
    
    if remainingDuration > 0.1 {
        hbt_ = Decimal(hbt)
        temptargetActive = true
    } else {
        temptargetActive = false
    }
}
```

---

## Exercise Mode

### Half-Basal Exercise Target

```swift
// trio:Preferences.swift#L16-L17
var exerciseMode: Bool = false
var halfBasalExerciseTarget: Decimal = 160  // half_basal_exercise_target
```

When a temp target is set above `halfBasalExerciseTarget`:
- Basal is reduced by 50%
- More conservative dosing is applied

---

## Nightscout Sync

### Temp Target Upload

Temp targets are uploaded as treatments:

```swift
// trio:NightscoutManager.swift
private func uploadTempTargets() {
    uploadTreatments(tempTargetsStorage.nightscoutTretmentsNotUploaded(), 
                     fileToSave: OpenAPS.Nightscout.uploadedTempTargets)
}
```

### Treatment Format

```json
{
  "eventType": "Temporary Target",
  "created_at": "2026-01-16T12:00:00.000Z",
  "enteredBy": "Trio",
  "targetTop": 120,
  "targetBottom": 100,
  "duration": 60,
  "reason": "Exercise"
}
```

### Temp Target Download

Trio fetches temp targets from Nightscout:

```swift
// trio:NightscoutAPI.swift#L202-L244
func fetchTempTargets(sinceDate: Date? = nil) -> AnyPublisher<[TempTarget], Swift.Error> {
    components.queryItems = [
        URLQueryItem(name: "find[eventType]", value: "Temporary+Target"),
        URLQueryItem(name: "find[enteredBy][$ne]", value: TempTarget.manual),
        URLQueryItem(name: "find[enteredBy][$ne]", value: NightscoutTreatment.local),
        URLQueryItem(name: "find[duration][$exists]", value: "true")
    ]
}
```

---

## Override vs Temp Target Priority

| Scenario | Target Used |
|----------|-------------|
| Override only | Override target |
| Temp target only | Temp target |
| Both active | Temp target (takes priority) |
| Neither active | Profile target |

---

## Comparison with Other Systems

| Feature | Trio | Loop | AAPS |
|---------|------|------|------|
| Override % | Yes (ISF/CR scaling) | Yes (insulinNeedsScaleFactor) | Via ProfileSwitch |
| Custom Target | Yes | Yes | Via ProfileSwitch |
| SMB Disable | Yes (scheduled) | N/A | Via ObjectivesPlugin |
| Duration | Minutes (or indefinite) | TimeInterval | Minutes |
| Nightscout Sync | Temp Target only | Full Override sync | ProfileSwitch |

**Gap**: Trio overrides are stored locally in CoreData and only the temp target portion syncs to Nightscout. Full override state (percentage, SMB settings) is not uploaded.

---

## Remote Override Control (NEW)

Trio supports starting and canceling overrides via the TrioRemoteControl APNS system.

### Start Override by Name

```swift
// trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl+Override.swift
@MainActor internal func handleStartOverrideCommand(_ payload: CommandPayload) async {
    guard let overrideName = payload.overrideName, !overrideName.isEmpty else {
        await logError("Override name is missing")
        return
    }
    
    // Fetch available presets
    let presetIDs = try await overrideStorage.fetchForOverridePresets()
    let presets = try presetIDs.compactMap { 
        try viewContext.existingObject(with: $0) as? OverrideStored 
    }
    
    // Find matching preset by name
    if let preset = presets.first(where: { $0.name == overrideName }) {
        await enactOverridePreset(preset: preset, payload: payload)
    } else {
        await logError("Override preset '\(overrideName)' not found")
    }
}
```

### Enact Override Preset

```swift
@MainActor private func enactOverridePreset(preset: OverrideStored, payload: CommandPayload) async {
    preset.enabled = true
    preset.date = Date()
    preset.isUploadedToNS = false
    
    // Disable any other active overrides
    await disableAllActiveOverrides(except: preset.objectID)
    
    if viewContext.hasChanges {
        try viewContext.save()
        NotificationCenter.default.post(name: .willUpdateOverrideConfiguration, object: nil)
        await awaitNotification(.didUpdateOverrideConfiguration)
        await logSuccess("Override started")
    }
}
```

### Cancel All Active Overrides

```swift
@MainActor internal func handleCancelOverrideCommand(_ payload: CommandPayload) async {
    await disableAllActiveOverrides()
    await logSuccess("Override canceled")
}

@MainActor private func disableAllActiveOverrides(except overrideID: NSManagedObjectID? = nil) async {
    let ids = try await overrideStorage.loadLatestOverrideConfigurations(fetchLimit: 0)
    let results = try ids.compactMap { try viewContext.existingObject(with: $0) as? OverrideStored }
    
    for canceledOverride in results where canceledOverride.enabled {
        if let overrideID = overrideID, canceledOverride.objectID == overrideID { continue }
        
        // Record the override run
        let newOverrideRunStored = OverrideRunStored(context: viewContext)
        newOverrideRunStored.id = UUID()
        newOverrideRunStored.name = canceledOverride.name
        newOverrideRunStored.startDate = canceledOverride.date ?? .distantPast
        newOverrideRunStored.endDate = Date()
        newOverrideRunStored.target = NSDecimalNumber(decimal: overrideStorage.calculateTarget(override: canceledOverride))
        newOverrideRunStored.override = canceledOverride
        newOverrideRunStored.isUploadedToNS = false
        
        canceledOverride.enabled = false
        canceledOverride.isUploadedToNS = false
    }
    
    if viewContext.hasChanges {
        try viewContext.save()
        NotificationCenter.default.post(name: .willUpdateOverrideConfiguration, object: nil)
    }
}
```

### Remote Command Payload

```json
{
  "commandType": "startOverride",
  "timestamp": 1705420800,
  "overrideName": "Exercise"
}
```

```json
{
  "commandType": "cancelOverride",
  "timestamp": 1705420800
}
```

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Updated paths to Trio/, added Remote Override Control section |
| 2026-01-16 | Agent | Initial overrides documentation from source analysis |
