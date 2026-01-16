# Loop (LoopWorkspace) Documentation Inventory

**Repository**: [LoopKit/LoopWorkspace](https://github.com/LoopKit/LoopWorkspace)  
**Alias**: `loop`  
**Language**: Swift (iOS)  
**Last Updated**: 2026-01-16

---

Loop is an iOS closed-loop insulin delivery system that automates basal insulin delivery based on CGM readings, IOB, and COB calculations.

**Total Submodules**: 15+ component repositories

---

## Repository Structure

### Core Application

| Component | Path | Description | Integration Priority |
|-----------|------|-------------|---------------------|
| Loop App | `Loop/` | Main iOS application | **Critical** |
| LoopCore | `Loop/LoopCore/` | Core business logic | **Critical** |
| LoopKit | `LoopKit/` | Shared framework for pump/CGM integration | **Critical** |
| DoseMath | `Loop/DoseMathTests/` | Dosing algorithm tests | High |

### CGM Integrations

| Component | Path | Description | Integration Priority |
|-----------|------|-------------|---------------------|
| CGMBLEKit | `CGMBLEKit/` | Dexcom G5/G6 BLE communication | High |
| G7SensorKit | `G7SensorKit/` | Dexcom G7 integration | High |
| LibreTransmitter | `LibreTransmitter/` | Libre CGM integration | Medium |
| ShareClient | `dexcom-share-client-swift/` | Dexcom Share cloud API | Medium |

### Pump Integrations

| Component | Path | Description | Integration Priority |
|-----------|------|-------------|---------------------|
| OmniKit | `OmniKit/` | Omnipod Eros driver | **Critical** |
| OmniBLE | `OmniBLE/` | Omnipod DASH BLE driver | **Critical** |
| RileyLinkKit | `RileyLinkKit/` | RileyLink BLE bridge for Medtronic/Eros | **Critical** |

### Cloud Services

| Component | Path | Description | Integration Priority |
|-----------|------|-------------|---------------------|
| NightscoutService | `NightscoutService/` | Nightscout upload/download | High |
| TidepoolService | `TidepoolService/` | Tidepool data sync | Medium |
| LogglyService | `LogglyService/` | Loggly logging integration | Low |
| AmplitudeService | `AmplitudeService/` | Analytics | Low |

---

## Key Data Models

### Therapy Settings

| Model | Location | Description |
|-------|----------|-------------|
| `TherapySettings` | LoopKit | Complete therapy configuration |
| `BasalRateSchedule` | LoopKit | Scheduled basal rates |
| `InsulinSensitivitySchedule` | LoopKit | ISF schedule |
| `CarbRatioSchedule` | LoopKit | Carb ratio schedule |
| `GlucoseRangeSchedule` | LoopKit | Target glucose ranges |

### Dosing Models

| Model | Location | Description |
|-------|----------|-------------|
| `DoseEntry` | LoopKit | Individual dose event |
| `InsulinOnBoard` | LoopCore | IOB calculation result |
| `CarbsOnBoard` | LoopCore | COB calculation result |
| `TemporaryBasalRecommendation` | LoopCore | Algorithm output |
| `BolusRecommendation` | LoopCore | Bolus suggestion |

### Override Models

| Model | Location | Description |
|-------|----------|-------------|
| `TemporaryScheduleOverride` | LoopKit | Override preset definition |
| `TemporaryScheduleOverrideSettings` | LoopKit | Override parameter values |
| `OverridePreset` | LoopKit | Saved override configurations |

---

## Algorithm Architecture

Loop uses a prediction-based control loop:

1. **Glucose Prediction** - Projects future glucose using:
   - Current glucose + momentum
   - Insulin effect (IOB decay)
   - Carb effect (COB absorption)

2. **Dose Recommendation** - Calculates temp basal or bolus to:
   - Keep predicted glucose in target range
   - Respect safety limits (max IOB, max basal)

3. **Dose Enactment** - Sends command to pump driver

### Key Algorithm Files

| File | Purpose |
|------|---------|
| `LoopCore/LoopMath.swift` | Core prediction calculations |
| `LoopCore/DoseRecommendation.swift` | Dosing logic |
| `LoopKit/InsulinMath.swift` | IOB calculations |
| `LoopKit/CarbMath.swift` | COB calculations |

---

## Safety Constraints

| Parameter | Description | Typical Range |
|-----------|-------------|---------------|
| `maximumBasalRatePerHour` | Max temp basal rate | 0-30 U/hr |
| `maximumBolus` | Max single bolus | 0-30 U |
| `suspendThreshold` | Low glucose suspend threshold | 67-80 mg/dL |
| `overrideRanges` | Allowed override target ranges | 87-180 mg/dL |

---

## Nightscout Integration Points

| Loop Concept | Nightscout Mapping |
|--------------|-------------------|
| `DoseEntry` (temp basal) | `treatments.eventType = 'Temp Basal'` |
| `DoseEntry` (bolus) | `treatments.eventType = 'Bolus'` |
| `CarbEntry` | `treatments.eventType = 'Carb Correction'` |
| `TemporaryScheduleOverride` | `treatments.eventType = 'Temporary Override'` |
| Loop Status | `devicestatus.loop` object |

---

## Alignment Gaps

1. **Override Supersession**: Loop tracks override changes locally but export to Nightscout doesn't include supersession relationship
2. **Prediction Data**: Loop predictions not synced to Nightscout in standard format
3. **Profile Sync**: Loop uses `TherapySettings` which differs structurally from Nightscout profiles
