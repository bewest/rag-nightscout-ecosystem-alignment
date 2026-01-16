# Loop Nightscout Sync

This document details Loop's Nightscout integration as implemented in `NightscoutService/`.

## Overview

Loop syncs the following to Nightscout:
1. **Treatments** - Doses, carbs, overrides
2. **Device Status** - Loop state, predictions, IOB/COB
3. **Profile** - Therapy settings (optional)

Loop also receives:
1. **Remote Commands** - Overrides, carbs, boluses

---

## Dose Upload

### Source: `DoseEntry.swift` extension
**File**: `loop:NightscoutService/NightscoutServiceKit/Extensions/DoseEntry.swift`

```swift
func treatment(enteredBy source: String, withObjectId objectId: String?) -> NightscoutTreatment?
```

### Bolus Mapping

```swift
case .bolus:
    return BolusNightscoutTreatment(
        timestamp: startDate,
        enteredBy: source,
        bolusType: duration >= TimeInterval(minutes: 30) ? .Square : .Normal,
        amount: deliveredUnits ?? programmedUnits,
        programmed: programmedUnits,
        unabsorbed: 0,
        duration: duration,
        automatic: automatic ?? false,
        syncIdentifier: syncIdentifier,
        insulinType: insulinType?.brandName
    )
```

| Loop Field | Nightscout Field |
|------------|------------------|
| `startDate` | `timestamp` |
| `deliveredUnits` / `programmedUnits` | `amount` |
| `programmedUnits` | `programmed` |
| `automatic` | `automatic` |
| `syncIdentifier` | `syncIdentifier` |
| `insulinType?.brandName` | `insulinType` |
| `duration >= 30 min` | `bolusType: Square` |

### Temp Basal Mapping

```swift
case .tempBasal:
    return TempBasalNightscoutTreatment(
        timestamp: startDate,
        enteredBy: source,
        temp: .Absolute,
        rate: unitsPerHour,
        absolute: unitsPerHour,
        duration: endDate.timeIntervalSince(startDate),
        amount: deliveredUnits,
        automatic: automatic ?? true,
        syncIdentifier: syncIdentifier,
        insulinType: insulinType?.brandName
    )
```

| Loop Field | Nightscout Field |
|------------|------------------|
| `startDate` | `timestamp` |
| `unitsPerHour` | `rate`, `absolute` |
| `endDate - startDate` | `duration` |
| `deliveredUnits` | `amount` |
| `automatic` | `automatic` (defaults true) |
| `syncIdentifier` | `syncIdentifier` |

### Suspend Mapping

```swift
case .suspend:
    return TempBasalNightscoutTreatment(
        timestamp: startDate,
        enteredBy: source,
        temp: .Absolute,
        rate: 0,
        absolute: unitsPerHour,
        duration: endDate.timeIntervalSince(startDate),
        amount: deliveredUnits,
        automatic: automatic ?? true,
        syncIdentifier: syncIdentifier,
        insulinType: nil,
        reason: "suspend"
    )
```

**Key**: Suspends are uploaded as temp basals with `rate: 0` and `reason: "suspend"`.

### Not Uploaded

- `.basal` (scheduled basal - implicit in profile)
- `.resume` (paired with suspend - duration already captured)

---

## Device Status Upload

### Source: `StoredDosingDecision.swift` extension
**File**: `loop:NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift`

```swift
func deviceStatus(automaticDoseDecision: StoredDosingDecision?) -> DeviceStatus {
    return DeviceStatus(
        device: "loop://\(UIDevice.current.name)",
        timestamp: date,
        pumpStatus: pumpStatus,
        uploaderStatus: uploaderStatus,
        loopStatus: LoopStatus(...),
        overrideStatus: overrideStatus
    )
}
```

### Loop Status

```swift
LoopStatus(
    name: Bundle.main.bundleDisplayName,
    version: Bundle.main.fullVersionString,
    timestamp: date,
    iob: loopStatusIOB,
    cob: loopStatusCOB,
    predicted: loopStatusPredicted,
    automaticDoseRecommendation: loopStatusAutomaticDoseRecommendation,
    recommendedBolus: loopStatusRecommendedBolus,
    enacted: automaticDoseDecision?.loopStatusEnacted,
    failureReason: automaticDoseDecision?.loopStatusFailureReason
)
```

### IOB Status

```swift
var loopStatusIOB: IOBStatus? {
    guard let insulinOnBoard = insulinOnBoard else { return nil }
    return IOBStatus(timestamp: insulinOnBoard.startDate, iob: insulinOnBoard.value)
}
```

**Nightscout format**:
```json
{
  "loop": {
    "iob": {
      "timestamp": "2026-01-16T12:00:00Z",
      "iob": 2.35
    }
  }
}
```

### COB Status

```swift
var loopStatusCOB: COBStatus? {
    guard let carbsOnBoard = carbsOnBoard else { return nil }
    return COBStatus(cob: carbsOnBoard.quantity.doubleValue(for: HKUnit.gram()), timestamp: carbsOnBoard.startDate)
}
```

**Nightscout format**:
```json
{
  "loop": {
    "cob": {
      "timestamp": "2026-01-16T12:00:00Z",
      "cob": 45.5
    }
  }
}
```

### Prediction

```swift
var loopStatusPredicted: PredictedBG? {
    guard let predictedGlucose = predictedGlucose, let startDate = predictedGlucose.first?.startDate else {
        return nil
    }
    return PredictedBG(startDate: startDate, values: predictedGlucose.map { $0.quantity })
}
```

**Nightscout format**:
```json
{
  "loop": {
    "predicted": {
      "startDate": "2026-01-16T12:00:00Z",
      "values": [120, 125, 130, 128, 122, 115, 108, ...]
    }
  }
}
```

**Note**: Loop uploads a single `predicted.values` array. oref0-based systems upload separate `predBGs.IOB[]`, `predBGs.COB[]`, `predBGs.UAM[]`, `predBGs.ZT[]`.

### Automatic Dose Recommendation

```swift
var loopStatusAutomaticDoseRecommendation: NightscoutKit.AutomaticDoseRecommendation? {
    guard let automaticDoseRecommendation = automaticDoseRecommendation else { return nil }
    
    return NightscoutKit.AutomaticDoseRecommendation(
        timestamp: date,
        tempBasalAdjustment: TempBasalAdjustment(rate: basalAdjustment.unitsPerHour, duration: basalAdjustment.duration),
        bolusVolume: automaticDoseRecommendation.bolusUnits ?? 0
    )
}
```

### Enacted

```swift
var loopStatusEnacted: LoopEnacted? {
    guard let automaticDoseRecommendation = automaticDoseRecommendation, errors.isEmpty else {
        return nil
    }
    let tempBasal = automaticDoseRecommendation.basalAdjustment
    return LoopEnacted(
        rate: tempBasal?.unitsPerHour ?? 0,
        duration: tempBasal?.duration ?? 0,
        timestamp: date,
        received: true,
        bolusVolume: automaticDoseRecommendation.bolusUnits ?? 0
    )
}
```

### Pump Status

```swift
var pumpStatus: PumpStatus? {
    return PumpStatus(
        clock: date,
        pumpID: pumpManagerStatus.device.localIdentifier ?? "Unknown",
        manufacturer: pumpManagerStatus.device.manufacturer,
        model: pumpManagerStatus.device.model,
        iob: nil,
        battery: pumpStatusBattery,
        suspended: pumpManagerStatus.basalDeliveryState?.isSuspended,
        bolusing: pumpStatusBolusing,
        reservoir: pumpStatusReservoir,
        secondsFromGMT: pumpManagerStatus.timeZone.secondsFromGMT()
    )
}
```

### Override Status

```swift
var overrideStatus: NightscoutKit.OverrideStatus {
    guard let scheduleOverride = scheduleOverride, scheduleOverride.isActive() else {
        return NightscoutKit.OverrideStatus(timestamp: date, active: false)
    }
    
    return NightscoutKit.OverrideStatus(
        name: scheduleOverride.context.name,
        timestamp: date,
        active: true,
        currentCorrectionRange: currentCorrectionRange,
        duration: remainingDuration,
        multiplier: scheduleOverride.settings.insulinNeedsScaleFactor
    )
}
```

---

## Override Upload

### As Treatment

**Source**: `OverrideTreatment.swift`

```swift
OverrideTreatment(
    startDate: override.startDate,
    enteredBy: enteredBy,
    reason: reason,
    duration: duration,
    correctionRange: nsTargetRange,
    insulinNeedsScaleFactor: override.settings.insulinNeedsScaleFactor,
    remoteAddress: remoteAddress,
    id: override.syncIdentifier.uuidString
)
```

**Nightscout eventType**: `"Temporary Override"`

### Duration Encoding

```swift
let duration: OverrideTreatment.Duration
switch override.duration {
case .finite(let time):
    duration = .finite(time)
case .indefinite:
    duration = .indefinite  // Encoded as 0 in Nightscout
}
```

---

## Remote Commands

### Command Sources

Loop receives remote commands via:
1. **Push notifications** (APNS)
2. **Nightscout polling** (checking for new commands)

### Override Action

**File**: `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Actions/OverrideAction.swift`

```swift
public struct OverrideAction: Codable {
    public let name: String            // Preset name to activate
    public let durationTime: TimeInterval?  // Optional duration override
    public let remoteAddress: String   // Who sent the command
}
```

### Override Cancel Action

**File**: `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Actions/OverrideCancelAction.swift`

```swift
public struct OverrideCancelAction: Codable {
    public let remoteAddress: String
}
```

### Carb Action

**File**: `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Actions/CarbAction.swift`

```swift
public struct CarbAction: Codable {
    public let amountInGrams: Double
    public let absorptionTime: TimeInterval?
    public let foodType: String?
    public let startDate: Date?
    public let remoteAddress: String
}
```

### Bolus Action

**File**: `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Actions/BolusAction.swift`

```swift
public struct BolusAction: Codable {
    public let amountInUnits: Double
    public let remoteAddress: String
}
```

---

## Carb Upload

**Source**: `SyncCarbObject.swift`

Loop uploads carb entries to Nightscout `treatments`:

```swift
// Carb entry fields mapped to Nightscout
- quantity → carbs (grams)
- startDate → timestamp
- absorptionTime → absorptionTime
- foodType → foodType
- syncIdentifier → identifier
```

**Nightscout eventType**: `"Carb Correction"`

---

## Profile Sync

**Source**: `ProfileSet.swift`, `StoredSettings.swift`

Loop can optionally upload therapy settings as a Nightscout profile:

```swift
// Profile structure
- basal[] - Basal rate schedule
- sens[] - ISF schedule  
- carbratio[] - CR schedule
- target_low[] - Target low schedule
- target_high[] - Target high schedule
- dia - Insulin duration
- timezone - User's timezone
```

**Note**: Loop's `TherapySettings` structure differs from Nightscout's profile format and requires transformation.

---

## Sync Identifiers

Loop uses `syncIdentifier` (UUID string) for deduplication:

| Loop Type | Sync ID Format | Nightscout Field |
|-----------|----------------|------------------|
| Dose | UUID from pump or generated | `syncIdentifier` |
| Carb | UUID generated on entry | `identifier` |
| Override | UUID from `TemporaryScheduleOverride.syncIdentifier` | `_id` |

---

## Missing from Upload

### Individual Effect Timelines

Loop computes but does not upload:
- `effects.insulin[]`
- `effects.carbs[]`
- `effects.momentum[]`
- `effects.retrospectiveCorrection[]`
- `effects.insulinCounteraction[]`

### Algorithm Parameters

Not synced:
- Insulin model parameters
- Retrospective correction type (Standard vs Integral)
- Dynamic carb absorption details
- Effect composition weights

### Override History Details

Not synced:
- `actualEnd` type (natural/early/deleted)
- Modification counter
- Supersession relationships

---

## Identified Alignment Gaps

### GAP-001: Override Supersession Tracking (Critical)

**Issue**: When Override B supersedes Override A, Nightscout has no mechanism to track:
- Which override was superseded
- Whether the end was `natural`, `early`, or `deleted`
- The relationship between override events

**Current behavior**: Loop uploads `OverrideTreatment` at start but does not update it when:
- Override ends early (cancelled)
- Override is superseded by another
- Override is deleted before execution

**Source**: `loop:NightscoutService/NightscoutServiceKit/Extensions/OverrideTreament.swift`

**Proposed fix**: Add fields to Nightscout override treatments:
```json
{
  "eventType": "Temporary Override",
  "supersededBy": "new-override-id",
  "actualEndType": "early|natural|deleted",
  "actualEndDate": "2026-01-16T10:30:00Z"
}
```

### GAP-SYNC-001: Sync Identifier Idempotency

**Issue**: Loop uses `syncIdentifier` for deduplication, but:
- Currently uses POST (not PUT), which may create duplicates in some Nightscout versions
- No explicit update mechanism when dose/entry is modified

**Source**: `loop:NightscoutService/NightscoutServiceKit/Extensions/DoseEntry.swift#L30-L31`
```swift
/* id: objectId, */ /// Specifying _id only works when doing a put (modify); all dose uploads are currently posting
```

### GAP-SYNC-002: Effect Timelines Not Uploaded

**Issue**: Loop computes but does not upload individual effect timelines:
- `effects.insulin[]` - Expected glucose change from insulin
- `effects.carbs[]` - Expected glucose change from carbs
- `effects.momentum[]` - Short-term trajectory
- `effects.retrospectiveCorrection[]` - Unexplained discrepancy correction
- `effects.insulinCounteraction[]` - Observed vs expected glucose change

These are critical for debugging and cross-project comparison.

### GAP-SYNC-003: Profile Upload Incomplete

**Issue**: Loop can optionally upload therapy settings as a Nightscout profile, but:
- No automatic sync when settings change
- Format transformation may lose precision
- Override effects on profile not reflected

### GAP-REMOTE-001: Remote Command Authorization

**Issue**: Remote commands (override, carb, bolus) track `remoteAddress` but:
- No verification of sender authority
- No permission model for who can issue commands
- Related to GAP-AUTH-001 (unverified enteredBy)

---

## Alignment Recommendations

### 1. Add Effect Timelines to Device Status

```json
{
  "loop": {
    "effects": {
      "insulin": [...],
      "carbs": [...],
      "momentum": [...],
      "retrospectiveCorrection": [...]
    }
  }
}
```

### 2. Add Supersession to Override Treatments

```json
{
  "eventType": "Temporary Override",
  "supersedes": "previous-override-id",
  "actualEndType": "early"
}
```

### 3. Add Algorithm Metadata

```json
{
  "loop": {
    "algorithm": {
      "version": "3.4.0",
      "insulinModel": "rapidActingAdult",
      "retrospectiveCorrection": "integral",
      "carbAbsorptionModel": "piecewiseLinear"
    }
  }
}
```

### 4. Separate Prediction Arrays

Match oref0 format for interoperability:
```json
{
  "loop": {
    "predBGs": {
      "IOB": [...],
      "COB": [...],
      "combined": [...]
    }
  }
}
```
