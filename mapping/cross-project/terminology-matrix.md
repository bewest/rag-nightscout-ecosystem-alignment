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

## Notes for Implementers

1. **AAPS has no explicit "Override" concept** - Use ProfileSwitch with percentage/target modifications
2. **Loop conflates overrides and temp targets** - Both are handled via TemporaryScheduleOverride
3. **Nightscout separates Override and Temp Target** - Different eventTypes for different use cases
4. **Trio follows OpenAPS patterns** - Similar to Nightscout with some extensions

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial cross-project terminology matrix |
