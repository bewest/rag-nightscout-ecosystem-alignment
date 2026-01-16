# Cross-Project Terminology Matrix

This matrix maps equivalent concepts across AID systems. Use this as a rosetta stone when translating between projects.

---

## Data Concepts

### Persistent State (Configuration)

| Alignment Term | Nightscout | Loop | AAPS | Trio |
|----------------|------------|------|------|------|
| Profile (config) | `profile` collection, `store` object | `TherapySettings` | `Profile` entity | `FreeAPSSettings` |
| Basal Schedule | `basal` array in profile | `BasalRateSchedule` | `Profile.basalBlocks` | `basalProfile` |
| ISF Schedule | `sens` array in profile | `InsulinSensitivitySchedule` | `Profile.isfBlocks` | `sens` array |
| CR Schedule | `carbratio` array in profile | `CarbRatioSchedule` | `Profile.icBlocks` | `carb_ratio` array |
| Target Range | `target_low`/`target_high` arrays | `GlucoseRangeSchedule` | `Profile.targetBlocks` | `target_low`/`target_high` |

### Events (Actions/Observations)

| Alignment Term | Nightscout | Loop | AAPS | Trio |
|----------------|------------|------|------|------|
| Glucose Entry | `entries` collection, `sgv` field | `StoredGlucoseSample` | `GlucoseValue` entity | `BloodGlucose` |
| Bolus Event | eventType: `Meal Bolus`, `Correction Bolus` | `DoseEntry` (type: bolus) | `Bolus` entity | `PumpHistoryEvent` |
| Carb Entry Event | eventType: `Carb Correction` | `StoredCarbEntry` | `Carbs` entity | `CarbsEntry` |
| Temp Basal Event | eventType: `Temp Basal` | `DoseEntry` (type: tempBasal) | `TemporaryBasal` entity | `TempBasal` |
| Profile Switch | eventType: `Profile Switch` | N/A (implicit) | `ProfileSwitch` entity | N/A (implicit) |
| Override (active) | eventType: `Temporary Override` | `TemporaryScheduleOverride` | N/A (via ProfileSwitch) | `Override` |
| Temporary Target | eventType: `Temporary Target` | via `TemporaryScheduleOverride` | `TempTarget` entity | `TempTarget` |
| Note/Annotation | eventType: `Note`, `Announcement` | `NoteEntry` | `UserEntry` | `NoteEntry` |

### State Snapshots (Point-in-Time)

| Alignment Term | Nightscout | Loop | AAPS | Trio |
|----------------|------------|------|------|------|
| Device Status | `devicestatus` collection | `LoopDataManager` snapshot | `DeviceStatus` entity | `DeviceStatus` |
| Loop/Algorithm State | `loop` in devicestatus | `LoopDataManager.lastLoopCompleted` | `LoopStatus` | `LoopStatus` |
| Pump State | `pump` in devicestatus | `PumpManagerStatus` | `PumpStatus` | `PumpStatus` |
| Uploader State | `uploader` in devicestatus | N/A | `UploaderStatus` | `UploaderStatus` |

### Derived Values (Computed)

| Alignment Term | Nightscout | Loop | AAPS | Trio |
|----------------|------------|------|------|------|
| Insulin on Board | `iob` in devicestatus | `InsulinOnBoard` | `IobTotal` | `IOB` |
| Carbs on Board | `cob` in devicestatus | `CarbsOnBoard` | `COB` | `COB` |
| Active Basal Rate | `basal` in loop prediction | `basalDelivery` | `currentBasal` | `basal` |
| Predicted Glucose | `predBgs` in loop | `predictedGlucose` | `predictedBg` | `predictedBg` |

**Note**: The distinction between persistent configuration, events, state snapshots, and derived values is critical for accurate cross-project translation.

---

## Profile Settings

| Setting | Nightscout | Loop | AAPS | Trio |
|---------|------------|------|------|------|
| Basal Rates | `basal` array | `BasalRateSchedule` | `defaultBasal` | `basalProfile` |
| ISF (Correction Factor) | `sens` array | `InsulinSensitivitySchedule` | `isf` | `sens` |
| Carb Ratio | `carbratio` array | `CarbRatioSchedule` | `ic` | `carb_ratio` |
| Target Range Low | `target_low` array | `GlucoseRangeSchedule` | `targetLow` | `target_low` |
| Target Range High | `target_high` array | `GlucoseRangeSchedule` | `targetHigh` | `target_high` |
| Insulin Duration | `dia` | `InsulinModel.effectDuration` | `dia` | `dia` |
| Units | `units` (`mg/dL` or `mmol/L`) | `HKUnit` | `GlucoseUnit` | `GlucoseUnit` |

---

## Override/Adjustment Concepts

| Concept | Nightscout | Loop | AAPS | Trio |
|---------|------------|------|------|------|
| Override Active | `Temporary Override` active | `overrideContext != nil` | `ProfileSwitch.percentage != 100` | `Override.enabled` |
| Duration | `duration` (minutes) | `duration` (TimeInterval) | `duration` (minutes) | `duration` (minutes) |
| Reason/Name | `reason` | `preset.symbol` + `preset.name` | N/A | `reason` |
| Target Adjustment | `targetTop`/`targetBottom` | `settings.targetRange` | `targetLow`/`targetHigh` | `target` |
| Overall Insulin % | `insulinNeedsScaleFactor` | `settings.insulinNeedsScaleFactor` | `ProfileSwitch.percentage` | `insulinNeedsScaleFactor` |
| Supersession | N/A (gap) | Built-in (new cancels old) | N/A (last switch wins) | Built-in |

---

## Sync Identity Fields

| Controller | Nightscout Field | Purpose |
|------------|------------------|---------|
| AAPS | `identifier` | Client-side unique ID |
| Loop | `pumpId` + `pumpType` + `pumpSerial` | Composite pump event ID |
| xDrip | `uuid` | Client-generated UUID |
| Generic | `_id` | MongoDB ObjectId (server-generated) |

**Gap**: No unified sync identity field exists across controllers (GAP-003).

---

## Authority/Actor Identity

| Concept | Nightscout | Loop | AAPS | Trio |
|---------|------------|------|------|------|
| Actor Identity | `enteredBy` (unverified) | `origin` | `pumpType` | `enteredBy` |
| Authority Level | N/A (gap) | N/A | N/A | N/A |
| Verified Identity | Proposed (OIDC) | N/A | N/A | N/A |

**Gap**: No system tracks verified actor identity with authority levels (GAP-AUTH-001, GAP-AUTH-002).

---

## Event Types Mapping

### Insulin Events

| Event | Nightscout eventType | Loop | AAPS | Trio |
|-------|---------------------|------|------|------|
| Meal Bolus | `Meal Bolus` | `Bolus` | `Bolus` | `Bolus` |
| Correction Bolus | `Correction Bolus` | `Bolus` | `Bolus` | `Bolus` |
| Temp Basal Start | `Temp Basal Start` | `TempBasal` | `TemporaryBasal` | `TempBasal` |
| Temp Basal End | `Temp Basal End` | (implicit) | (implicit) | (implicit) |

### Device Events

| Event | Nightscout eventType | Loop | AAPS | Trio |
|-------|---------------------|------|------|------|
| Sensor Start | `Sensor Start` | `CGMSensorEvent` | `TherapyEvent.SENSOR_CHANGE` | `SensorChange` |
| Site Change | `Site Change` | `PumpEvent` | `TherapyEvent.CANNULA_CHANGE` | `SiteChange` |
| Pump Battery | `Pump Battery Change` | `PumpEvent` | `TherapyEvent` | `PumpBattery` |

---

## Code References

| Project | Override/Adjustment Model Location |
|---------|-----------------------------------|
| Nightscout | `crm:lib/plugins/careportal.js` |
| Loop | `loop:Loop/Models/TemporaryScheduleOverride.swift` |
| AAPS | `aaps:database/entities/ProfileSwitch.kt` |
| Trio | `trio:FreeAPS/Sources/Models/Override.swift` |

---

## Algorithm/Controller Concepts

### Algorithm Recommendations

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Basal Recommendation | `rate`, `duration` in output | `TemporaryBasalRecommendation` | `APSResult.rate` | `Suggestion.rate` |
| Bolus Recommendation | `units` (SMB) | `BolusRecommendation` | `APSResult.smb` | `Suggestion.units` |
| Reason/Explanation | `reason` string | `recommendation.notice` | `APSResult.reason` | `Suggestion.reason` |
| Enact Timestamp | `deliverAt` | `date` | `date` | `deliverAt` |

### Prediction Types

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| IOB Prediction | `predBGs.IOB[]` | `predictedGlucose` (IOB effect) | `predictions.iob[]` | `predictions.IOB[]` |
| COB Prediction | `predBGs.COB[]` | `predictedGlucose` (carb effect) | `predictions.cob[]` | `predictions.COB[]` |
| UAM Prediction | `predBGs.UAM[]` | N/A (no UAM) | `predictions.uam[]` | `predictions.UAM[]` |
| Zero Temp Prediction | `predBGs.ZT[]` | N/A | `predictions.zt[]` | `predictions.ZT[]` |
| Eventual BG | `eventualBG` | `predictedGlucose.last` | `eventualBG` | `eventualBG` |

### Insulin Calculations

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Total IOB | `iob.iob` | `insulinOnBoard` | `iobTotal.iob` | `iob.iob` |
| Basal IOB | `iob.basaliob` | `basalDeliveryState.iob` | `iobTotal.basaliob` | `iob.basaliob` |
| Bolus Snooze IOB | `iob.bolussnooze` | N/A | `iobTotal.bolussnooze` | `iob.bolussnooze` |
| Insulin Activity | `iob.activity` | `insulinActivityForecast` | `iobTotal.activity` | `iob.activity` |

### Meal/Carb Calculations

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Carbs on Board | `meal.mealCOB` | `carbsOnBoard` | `iobCobCalculator.cob` | `meal.carbs` |
| Meal Absorption | `meal.slopeFromMaxDeviation` | `carbAbsorptionRate` | `carbsFromBolus` | `meal.slopeFromMaxDeviation` |
| Last Carb Time | `meal.lastCarbTime` | `lastCarbEntry.date` | `mealData.lastCarbTime` | `meal.lastCarbTime` |
| Unannounced Meal | UAM detection in algorithm | N/A | UAM via openAPSSMB | UAM in oref algorithm |

---

## Safety Constraints

### Maximum Limits

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Max IOB | `profile.max_iob` | `settings.maximumActiveInsulin` | `preferences.maxIOB` | `preferences.maxIOB` |
| Max Basal Rate | `profile.max_basal` | `settings.maximumBasalRate` | `preferences.maxBasal` | `preferences.maxBasal` |
| Max Bolus | N/A (SMB limit) | `settings.maximumBolus` | `preferences.maxBolus` | `preferences.maxBolus` |
| Max SMB | `profile.maxSMBBasalMinutes` | N/A (no SMB) | `preferences.maxSMBBasalMinutes` | `preferences.maxSMBBasalMinutes` |
| Max Daily Basal Multiplier | `profile.max_daily_safety_multiplier` | N/A | `maxDailySafetyMultiplier` | `maxDailySafetyMultiplier` |
| Current Basal Multiplier | `profile.current_basal_safety_multiplier` | N/A | `currentBasalSafetyMultiplier` | `currentBasalSafetyMultiplier` |

### Low Glucose Safety

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Suspend Threshold | N/A (uses min_bg) | `settings.suspendThreshold` | `preferences.lgsThreshold` | `preferences.suspendThreshold` |
| Min BG Target | `profile.min_bg` | `GlucoseRangeSchedule.minValue` | `profile.targetLow` | `target_low` |

### Autosensitivity

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Sensitivity Ratio | `sensitivityRatio` | `insulinSensitivity` | `autosensData.ratio` | `sensitivityRatio` |
| Autosens Max | `profile.autosens_max` | N/A | `autosensMax` | `autosensMax` |
| Autosens Min | `profile.autosens_min` | N/A | `autosensMin` | `autosensMin` |
| Autosens Adjust Targets | `profile.autosens_adjust_targets` | N/A | `autosensAdjustTargets` | `autosensAdjustTargets` |

---

## Pump Commands

### Basal Commands

| Alignment Term | oref0/openaps | Loop | AAPS | Trio |
|----------------|---------------|------|------|------|
| Set Temp Basal | `set_temp_basal` | `enactTempBasal()` | `tempBasalAbsolute()` | `enactTempBasal()` |
| Cancel Temp Basal | `set_temp_basal(rate=0)` | `cancelTempBasal()` | `cancelTempBasal()` | `cancelTempBasal()` |
| Suspend | `suspend_pump` | `suspendDelivery()` | `suspendPump()` | `suspendDelivery()` |
| Resume | `resume_pump` | `resumeDelivery()` | `resumePump()` | `resumeDelivery()` |

### Bolus Commands

| Alignment Term | oref0/openaps | Loop | AAPS | Trio |
|----------------|---------------|------|------|------|
| Deliver Bolus | N/A (manual) | `enactBolus()` | `deliverBolus()` | `enactBolus()` |
| Deliver SMB | via rig | N/A (no SMB) | `deliverSMB()` | `enactSMB()` |
| Cancel Bolus | N/A | `cancelBolus()` | `stopBolusDelivering()` | `cancelBolus()` |

### Status Queries

| Alignment Term | oref0/openaps | Loop | AAPS | Trio |
|----------------|---------------|------|------|------|
| Get Pump Status | `read_pump_status` | `getPumpStatus()` | `readPumpStatus()` | `getPumpStatus()` |
| Get Reservoir | `reservoir` | `reservoirLevel` | `remainingInsulin` | `reservoir` |
| Get Battery | `battery` | `batteryLevel` | `batteryLevel` | `battery` |

---

## Insulin Models

| Model | oref0 | Loop | AAPS | Trio |
|-------|-------|------|------|------|
| Rapid Acting | `rapidActing` | `ExponentialInsulinModel` | `Oref1` | `rapidActing` |
| Ultra Rapid | `ultraRapid` | `ExponentialInsulinModel(peak)` | `Lyumjev` | `ultraRapid` |
| Bilinear | `bilinear` | N/A | `bilinear` | `bilinear` |
| Peak Time | `peak` (minutes) | `peakActivity` | `peak` | `insulinPeak` |
| DIA | `dia` (hours) | `effectDuration` | `dia` | `dia` |

---

## Loop Cycle States

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Loop Running | rig running | `loopManager.isLoopRunning` | `loop.isEnabled` | `isLooping` |
| Loop Suspended | rig stopped | `loopManager.isSuspended` | `loop.isSuspended` | `isSuspended` |
| Open Loop Mode | N/A (always closed) | `closedLoop = false` | `isOpenLoop` | `closedLoop = false` |
| Closed Loop Mode | default | `closedLoop = true` | `isClosedLoop` | `closedLoop = true` |
| Last Loop Time | cron timestamp | `lastLoopCompleted` | `lastRun` | `lastLoopDate` |

---

## Algorithm Variants

| Variant | oref0 | Loop | AAPS | Trio |
|---------|-------|------|------|------|
| AMA (Advanced Meal Assist) | `determine-basal.js` with AMA | N/A | `OpenAPSAMAPlugin` | N/A |
| SMB (Super Micro Bolus) | oref1 SMB mode | N/A (no SMB) | `OpenAPSSMBPlugin` | oref1 SMB |
| AutoISF | N/A | N/A | `OpenAPSAutoISFPlugin` | N/A |
| Autotune | `lib/autotune/` | N/A | `AutotunePlugin` | Autotune module |

---

## Notes for Implementers

1. **AAPS has no explicit "Override" concept** - Use ProfileSwitch with percentage/target modifications
2. **Loop conflates overrides and temp targets** - Both are handled via TemporaryScheduleOverride
3. **Nightscout separates Override and Temp Target** - Different eventTypes for different use cases
4. **Trio follows OpenAPS patterns** - Similar to Nightscout with some extensions
5. **Loop does not use oref0** - Has its own prediction and dosing algorithm (LoopMath)
6. **AAPS and Trio embed oref0** - AAPS has ported oref0 to native Kotlin (not JavaScript bridge)
7. **SMB (Super Micro Bolus)** - Only available in oref1-based systems (AAPS, Trio), not Loop
8. **Autosens** - Available in oref0/AAPS/Trio, Loop uses different sensitivity approach (RC)
9. **Dynamic ISF** - AAPS supports TDD-based variable sensitivity (DynISF), Loop has IRC

---

## AAPS-Specific Concepts

### Nightscout SDK (NSSDK)

AAPS maintains a dedicated Nightscout SDK (`core/nssdk/`) with local model classes:

| AAPS NSSDK Class | Nightscout Collection | Key Fields |
|------------------|----------------------|------------|
| `NSSgvV3` | `entries` | `sgv`, `direction`, `noise` |
| `NSBolus` | `treatments` | `insulin`, `type` (NORMAL/SMB/PRIMING) |
| `NSCarbs` | `treatments` | `carbs`, `duration` (eCarbs) |
| `NSTemporaryBasal` | `treatments` | `rate`, `duration`, `type` |
| `NSProfileSwitch` | `treatments` | `profile`, `percentage`, `timeShift` |
| `NSTemporaryTarget` | `treatments` | `targetTop`, `targetBottom`, `reason` |
| `NSDeviceStatus` | `devicestatus` | `openaps`, `pump`, `configuration` |
| `NSTherapyEvent` | `treatments` | `eventType`, `notes` |

### ProfileSwitch Modifiers (GAP-002)

AAPS ProfileSwitch has semantic fields that Nightscout doesn't distinguish:

| Modifier | Field | Effect |
|----------|-------|--------|
| Complete Switch | `profileName` changes | New profile settings |
| Percentage | `percentage != 100` | All insulin delivery scaled |
| Time Shift | `timeshift != 0` | Schedule shifted |
| Duration | `duration > 0` | Temporary vs permanent |

### Bolus Types

AAPS distinguishes bolus types via enum:

| Type | Description | NS Mapping |
|------|-------------|------------|
| `NORMAL` | User-initiated bolus | `Meal Bolus` or `Correction Bolus` |
| `SMB` | Super Micro Bolus (automatic) | `SMB` eventType |
| `PRIMING` | Pump priming (not therapy) | `Prime` eventType |

### Temp Basal Types

| Type | Description |
|------|-------------|
| `NORMAL` | Standard temp basal |
| `EMULATED_PUMP_SUSPEND` | Suspend via 0% basal |
| `PUMP_SUSPEND` | Actual pump suspend |
| `SUPERBOLUS` | Superbolus temp basal |
| `FAKE_EXTENDED` | Extended bolus emulation |

### Insulin Model Peak Times

| AAPS Plugin | Peak (minutes) | Insulin Type |
|-------------|----------------|--------------|
| `InsulinOrefRapidActingPlugin` | 75 | NovoRapid, Humalog, Apidra |
| `InsulinOrefUltraRapidActingPlugin` | 55 | Fiasp |
| `InsulinLyumjevPlugin` | 45 | Lyumjev |
| `InsulinOrefFreePeakPlugin` | Configurable | Custom |

### Dynamic ISF Formula

AAPS DynISF uses TDD-based calculation:

```
TDD = (tddWeighted8h * 0.33) + (tdd7D * 0.34) + (tdd1D * 0.33)
variableSens = 1800 / (TDD * ln((glucose / insulinDivisor) + 1))
```

Where `insulinDivisor` depends on insulin type (55-75).

---

## Trio-Specific Concepts

### oref2 Variables

Trio extends oref0 with additional state tracked in CoreData and passed to the algorithm:

| Variable | Purpose | NS Equivalent |
|----------|---------|---------------|
| `average_total_data` | 10-day TDD average | N/A (local only) |
| `weightedAverage` | Weighted 2h/10d TDD for dynamic ISF | N/A |
| `past2hoursAverage` | Recent 2-hour TDD | N/A |
| `overridePercentage` | Active override insulin % | N/A (temp target only syncs) |
| `useOverride` | Override active flag | N/A |
| `smbIsOff` | Override disables SMB | N/A |
| `smbIsScheduledOff` | Time-window SMB disable | N/A |
| `hbt` | Half-basal exercise target | N/A |

### Remote Commands (Announcements)

Trio supports remote commands via Nightscout Announcements:

| Command | Format | Example |
|---------|--------|---------|
| Remote Bolus | `bolus: <units>` | `bolus: 2.5` |
| Pump Suspend | `pump: suspend` | `pump: suspend` |
| Pump Resume | `pump: resume` | `pump: resume` |
| Loop Toggle | `looping: <bool>` | `looping: false` |
| Temp Basal | `tempbasal: <rate>,<duration>` | `tempbasal: 0.5,30` |

**Security**: Only announcements with `enteredBy: "remote"` are processed.

### Override vs Temp Target

| Feature | Override | Temp Target |
|---------|----------|-------------|
| Stored In | CoreData (local) | CoreData + NS |
| Affects ISF/CR | Yes (percentage) | No |
| Affects Target | Yes | Yes |
| Disables SMB | Optional | No |
| NS Sync | No | Yes |
| Priority | Lower | Higher (if both active) |

### Insulin Curves

| Curve | JSON Value | Peak (min) | Default DIA |
|-------|------------|------------|-------------|
| Rapid Acting | `rapid-acting` | 75 | 5 hours |
| Ultra Rapid | `ultra-rapid` | 55 | 4 hours |
| Bilinear | `bilinear` | N/A | Variable |
| Custom Peak | via `insulinPeakTime` | User-set | Variable |

### Dynamic ISF (Trio)

Trio's dynamic ISF uses TDD-based adjustment:

```
weightedTDD = (weight × 2h_TDD) + ((1 - weight) × 10d_TDD)
adjustedISF = baseISF × (referenceWeight / weightedTDD)
```

Where `weight` is configurable via `weightPercentage` (default 0.65).

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Added Trio-specific concepts (oref2 variables, remote commands, overrides, insulin curves, dynamic ISF) |
| 2026-01-16 | Agent | Added algorithm/controller concepts, safety constraints, pump commands, insulin models, loop states |
| 2026-01-16 | Agent | Initial cross-project terminology matrix |
