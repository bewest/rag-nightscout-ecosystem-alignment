# Cross-Project Terminology Matrix

This matrix maps equivalent concepts across AID systems. Use this as a rosetta stone when translating between projects.

---

## Data Concepts

### Persistent State (Configuration)

| Alignment Term | Nightscout | Loop | AAPS | Trio | xDrip+ |
|----------------|------------|------|------|------|--------|
| Profile (config) | `profile` collection, `store` object | `TherapySettings` | `ProfileSwitch` entity (with `duration=0`) | Local settings + `FetchedNightscoutProfile` | N/A (CGM-focused) |
| Basal Schedule | `basal` array in profile | `BasalRateSchedule` | `ProfileSwitch.basalBlocks` | `basal` array (from NS) | N/A |
| ISF Schedule | `sens` array in profile | `InsulinSensitivitySchedule` | `ProfileSwitch.isfBlocks` | `sens` array (from NS) | N/A |
| CR Schedule | `carbratio` array in profile | `CarbRatioSchedule` | `ProfileSwitch.icBlocks` | `carbratio` array (from NS) | N/A |
| Target Range | `target_low`/`target_high` arrays | `GlucoseRangeSchedule` | `ProfileSwitch.targetBlocks` | `target_low`/`target_high` (from NS) | `Pref.highValue`/`lowValue` (display only) |

**Note**: AAPS stores profile data in `ProfileSwitch` entities; a switch with `duration=0` is permanent. Trio fetches profiles from Nightscout (`FetchedNightscoutProfile`) and stores local algorithm settings separately.

**Note**: xDrip+ is a CGM data management app, not a closed-loop system. It does not manage therapy profiles but does track glucose thresholds for display/alerts.
- Core data models: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/`
- See `mapping/xdrip-android/README.md` for full architecture documentation.

### Events (Actions/Observations)

| Alignment Term | Nightscout | Loop | AAPS | Trio | xDrip+ |
|----------------|------------|------|------|------|--------|
| Glucose Entry | `entries` collection, `sgv` field | `StoredGlucoseSample` | `GlucoseValue` entity | `BloodGlucose` | `BgReading` entity |
| Bolus Event | eventType: `Meal Bolus`, `Correction Bolus` | `DoseEntry` (type: bolus) | `Bolus` entity | `PumpHistoryEvent` | `Treatments.insulin` |
| Carb Entry Event | eventType: `Carb Correction` | `StoredCarbEntry` | `Carbs` entity | `CarbsEntry` | `Treatments.carbs` |
| Temp Basal Event | eventType: `Temp Basal` | `DoseEntry` (type: tempBasal) | `TemporaryBasal` entity | `TempBasal` | N/A (via AAPS) |
| Profile Switch | eventType: `Profile Switch` | N/A (implicit) | `ProfileSwitch` entity | N/A (implicit) | N/A |
| Override (active) | eventType: `Temporary Override` | `TemporaryScheduleOverride` | N/A (via ProfileSwitch) | `Override` | N/A |
| Temporary Target | eventType: `Temporary Target` | via `TemporaryScheduleOverride` | `TempTarget` entity | `TempTarget` | N/A |
| Note/Annotation | eventType: `Note`, `Announcement` | `NoteEntry` | `UserEntry` | `NoteEntry` | `Treatments.notes` |
| Sensor Start | eventType: `Sensor Start` | `CGMSensorEvent` | `TherapyEvent.SENSOR_CHANGE` | `SensorChange` | `Treatments` (eventType: `Sensor Start`) |
| Sensor Stop | N/A | N/A | N/A | N/A | `Treatments` (eventType: `Sensor Stop`) |

### Treatment Data Models (Deep Dive)

> **See Also**: [Treatments Collection Deep Dive](../../docs/10-domain/treatments-deep-dive.md) for comprehensive field-by-field mappings.

#### Bolus Fields

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| Insulin Amount | `insulin` | `deliveredUnits` / `programmedUnits` | `amount` | via `DoseEntry` | `insulin` |
| Bolus Type | `eventType` | `.bolus` (single) | `Type` enum | `.bolus` | N/A |
| Automatic Flag | `automatic` | `automatic` | via `Type.SMB` | `automatic` | N/A |
| Sync Identity | `identifier` / `syncIdentifier` | `syncIdentifier` | `interfaceIDs.nightscoutId` | `syncIdentifier` | `uuid` |
| Insulin Type | `insulinType` | `insulinType?.brandName` | `insulinConfiguration` | N/A | `insulinJSON` |
| Duration (extended) | `duration` | via `endDate - startDate` | N/A | via `endDate - startDate` | N/A |

**Bolus Type Enums**:
- **Loop**: Single `.bolus` type (no SMB)
- **AAPS**: `NORMAL`, `SMB`, `PRIMING` (internal); SMB uploads as `eventType: Correction Bolus` with `type: SMB` field
- **Nightscout eventType**: `Meal Bolus`, `Correction Bolus`, `Snack Bolus` (no explicit SMB eventType - see GAP-TREAT-003)

#### Carb Entry Fields

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| Carbs Amount | `carbs` | `quantity` (HKQuantity) | `amount` | via `CarbsEntry` | `carbs` |
| Absorption Time | `absorptionTime` (min) | `absorptionTime` (sec) | N/A | `absorptionTime` (sec) | N/A |
| Duration (eCarbs) | `duration` (min) | N/A | `duration` (ms) | N/A | N/A |
| Food Type | `foodType` | `foodType` | N/A | `foodType` | N/A |
| Sync Identity | `identifier` | `syncIdentifier` | `interfaceIDs.nightscoutId` | `syncIdentifier` | `uuid` |

**Unit Differences (GAP-TREAT-001, GAP-TREAT-002)**:
- Absorption time: Loop/Trio use seconds, Nightscout uses minutes
- Duration: AAPS uses milliseconds, Nightscout uses minutes

#### Temp Basal Fields

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| Rate | `rate` / `absolute` | `unitsPerHour` | `rate` | via `DoseEntry` | N/A |
| Is Absolute | `temp: "absolute"` | Always true | `isAbsolute` | Always true | N/A |
| Percent | `percent` | N/A | `rate - 100` (if relative) | N/A | N/A |
| Duration | `duration` (min) | `endDate - startDate` (sec) | `duration` (ms) | `endDate - startDate` (sec) | N/A |
| Type | `eventType` | `DoseType` enum | `Type` enum | `DoseType` | N/A |
| Automatic | `automatic` | `automatic ?? true` | N/A | `automatic` | N/A |

**Temp Basal Types (AAPS)**:
- `NORMAL`: Standard temp basal
- `EMULATED_PUMP_SUSPEND`: Suspend via 0% basal
- `PUMP_SUSPEND`: Actual pump suspend
- `SUPERBOLUS`: Superbolus temp basal
- `FAKE_EXTENDED`: Extended bolus emulation

#### Treatment Sync Identity

| System | Primary ID | Secondary ID | Upload Method |
|--------|-----------|--------------|---------------|
| Loop | `syncIdentifier` (UUID) | N/A | POST (v1 API) |
| AAPS | `interfaceIDs.nightscoutId` | `pumpId` + `pumpType` + `pumpSerial` | PUT (v3 API) |
| Trio | `syncIdentifier` (UUID) | N/A | POST (v1 API) |
| xDrip+ | `uuid` | N/A | PUT upsert (v1 API) |

**Gap Reference**: GAP-003 (no unified sync identity), GAP-TREAT-005 (Loop POST duplicates)

### Glucose Data Models (Deep Dive)

> **See Also**: [Entries Collection Deep Dive](../../docs/10-domain/entries-deep-dive.md) for comprehensive field-by-field mappings.

#### Core SGV Fields

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| Glucose Value | `sgv` | `quantity` (HKQuantity) | `value` | `sgv` | `calculated_value` |
| Timestamp | `date` (epoch ms) | `startDate` | `timestamp` | `date` | `timestamp` |
| Trend Arrow | `direction` | `trendType` (GlucoseTrend) | `trendArrow` | `direction` | `dg_slope` → direction |
| Noise Level | `noise` (1-4) | N/A | `noise` | `noise` | `noise` |
| Device/Source | `device` | `provenanceIdentifier` | `sourceSensor` | N/A | `sensor_uuid` |
| Sync Identity | `_id` | N/A | `interfaceIDs.nightscoutId` | `_id` | `uuid` |

#### Direction (Trend Arrow) Mapping

| Nightscout | Loop (GlucoseTrend) | AAPS (TrendArrow) | Trio | xDrip+ |
|------------|---------------------|-------------------|------|--------|
| `DoubleUp` | `.upUpUp` | `DOUBLE_UP` | `DoubleUp` | `DOUBLE_UP (1)` |
| `SingleUp` | `.upUp` | `SINGLE_UP` | `SingleUp` | `SINGLE_UP (2)` |
| `FortyFiveUp` | `.up` | `FORTY_FIVE_UP` | `FortyFiveUp` | `FORTY_FIVE_UP (3)` |
| `Flat` | `.flat` | `FLAT` | `Flat` | `FLAT (4)` |
| `FortyFiveDown` | `.down` | `FORTY_FIVE_DOWN` | `FortyFiveDown` | `FORTY_FIVE_DOWN (5)` |
| `SingleDown` | `.downDown` | `SINGLE_DOWN` | `SingleDown` | `SINGLE_DOWN (6)` |
| `DoubleDown` | `.downDownDown` | `DOUBLE_DOWN` | `DoubleDown` | `DOUBLE_DOWN (7)` |
| `NOT COMPUTABLE` | N/A | `NONE` | `notComputable` | `NOT_COMPUTABLE (8)` |
| N/A | N/A | `TRIPLE_UP` | `TripleUp` | N/A |
| N/A | N/A | `TRIPLE_DOWN` | `TripleDown` | N/A |

**Gap Reference**: GAP-ENTRY-001 (triple arrows have no NS equivalent)

#### Raw/Filtered Values

| Field | Nightscout | AAPS | xDrip+ | Notes |
|-------|------------|------|--------|-------|
| Unfiltered Raw | `unfiltered` | N/A | `raw_data` | Unprocessed sensor signal |
| Filtered Raw | `filtered` | N/A | `filtered_data` | Noise-reduced signal |
| Raw Calibrated | N/A | `raw` | `raw_calculated` | Intermediate value |

**Note**: iOS systems (Loop, Trio) do not expose raw sensor values—they rely on transmitter-calibrated readings.

#### CGM vs Meter Reading Distinction

| Reading Type | Nightscout | AAPS | xDrip+ |
|--------------|------------|------|--------|
| CGM (continuous) | `entries` (type: `sgv`) | `GlucoseValue` entity | `BgReading` entity |
| Meter (fingerstick) | `treatments` (eventType: `BG Check`) | `TherapyEvent` (FINGER_STICK_BG_VALUE) | `BloodTest` entity |
| Calibration | `entries` (type: `cal`) | N/A | `Calibration` entity |

**Key Distinction**: Meter readings are **treatments**, not entries. CGM readings are entries.

#### Glucose Entry Sync Identity

| System | Primary ID | Upload Role | Dedup Strategy |
|--------|-----------|-------------|----------------|
| xDrip+ | `uuid` | Primary producer | Upsert by uuid |
| AAPS | `interfaceIDs.nightscoutId` | Consumer/rebroadcast | Check before insert |
| Loop | N/A | Typically doesn't upload CGM | N/A |
| Trio | `_id` | Passthrough | Direct from NS |

**Gap Reference**: GAP-ENTRY-003 (no standardized source taxonomy), GAP-ENTRY-004 (no universal dedup)

### State Snapshots (Point-in-Time)

| Alignment Term | Nightscout | Loop | AAPS | Trio | xDrip+ |
|----------------|------------|------|------|------|--------|
| Device Status | `devicestatus` collection | `LoopDataManager` snapshot | `DeviceStatus` entity | `DeviceStatus` | `uploaderBattery` in POST |
| Loop/Algorithm State | `loop` in devicestatus | `LoopDataManager.lastLoopCompleted` | `LoopStatus` | `LoopStatus` | N/A (no loop) |
| Pump State | `pump` in devicestatus | `PumpManagerStatus` | `PumpStatus` | `PumpStatus` | Reads from AAPS broadcast |
| Uploader State | `uploader` in devicestatus | N/A | `UploaderStatus` | `UploaderStatus` | `NightscoutUploader.last_success_time` |

**Note**: xDrip+ uploads device status but does not run a loop algorithm. It can display AAPS pump status received via broadcast.
- Device status upload: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java#L134-L138`
- AAPS status handler: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/insulin/aaps/AAPSStatusHandler.java`

### Derived Values (Computed)

| Alignment Term | Nightscout | Loop | AAPS | Trio | xDrip+ |
|----------------|------------|------|------|------|--------|
| Insulin on Board | `iob` in devicestatus | `InsulinOnBoard` | `IobTotal` | `IOB` | `Iob.getIobAtTime()` (multi-insulin) |
| Carbs on Board | `cob` in devicestatus | `CarbsOnBoard` | `COB` | `COB` | N/A (no absorption model) |
| Active Basal Rate | `basal` in loop prediction | `basalDelivery` | `currentBasal` | `basal` | N/A (no basal control) |
| Predicted Glucose | `predBgs` in loop | `predictedGlucose` | `predictedBg` | `predictedBg` | N/A (no prediction) |
| Glucose Delta | `delta` in entries | `glucoseMomentum` | `delta` | `delta` | `BgReading.currentSlope()` |

**Note**: The distinction between persistent configuration, events, state snapshots, and derived values is critical for accurate cross-project translation.

**xDrip+ IOB**: Uses `Iob.java` with multi-insulin support via `InsulinInjection` profiles.
- Source: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/Iob.java`
- Multi-insulin: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/InsulinInjection.java`
- IOB calculation: `Iob.getIobAtTime()` method

---

## Profile Settings

| Setting | Nightscout | Loop | AAPS | Trio | xDrip+ |
|---------|------------|------|------|------|--------|
| Basal Rates | `basal` array | `BasalRateSchedule` | `ProfileSwitch.basalBlocks` | `basal` array | N/A |
| ISF (Correction Factor) | `sens` array | `InsulinSensitivitySchedule` | `ProfileSwitch.isfBlocks` | `sens` array | N/A |
| Carb Ratio | `carbratio` array | `CarbRatioSchedule` | `ProfileSwitch.icBlocks` | `carbratio` array | N/A |
| Target Range Low | `target_low` array | `GlucoseRangeSchedule` | `ProfileSwitch.targetBlocks.lowTarget` | `target_low` array | `Pref.lowValue` (alerts) |
| Target Range High | `target_high` array | `GlucoseRangeSchedule` | `ProfileSwitch.targetBlocks.highTarget` | `target_high` array | `Pref.highValue` (alerts) |
| Insulin Duration | `dia` | `InsulinModel.effectDuration` | `dia` | `dia` | `Insulin.maxEffect` (per profile) |
| Units | `units` (`mg/dL` or `mmol/L`) | `HKUnit` | `GlucoseUnit` | `GlucoseUnit` | `Pref.units_mmol` (boolean) |

**Note**: xDrip+ stores target ranges for alert thresholds only, not for dosing calculations.
- Insulin profiles: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/insulin/Insulin.java`
- Alert thresholds: `Pref.getStringToInt("highValue", 170)` and `Pref.getStringToInt("lowValue", 70)`

### Profile Data Structures

| Aspect | Nightscout | Loop | AAPS | Trio |
|--------|------------|------|------|------|
| Profile Entity | `profile` collection | `TherapySettings` | `ProfileSwitch` entity | `FetchedNightscoutProfile` (from NS) |
| Time-Value Format | `{time, timeAsSeconds, value}` | `RepeatingScheduleValue<T>` | `Block` (duration-based) | `NightscoutTimevalue` |
| Multiple Profiles | `store` dictionary | Single settings | Via named `ProfileSwitch` entries | `store` dictionary |
| Profile Naming | `defaultProfile` string | None (implicit) | `profileName` field | `defaultProfile` string |
| Permanent vs Temp | N/A (always stored) | N/A (single config) | `duration=0` = permanent | N/A (uses NS profiles) |

### Timezone Handling

| Aspect | Nightscout | Loop | AAPS | Trio |
|--------|------------|------|------|------|
| Storage Format | IANA string | `TimeZone` object | `utcOffset: Long` (ms) | IANA string (from NS) |
| DST Awareness | Yes (moment-tz) | Yes (Foundation) | No (fixed offset) | Yes (via NS) |
| Per-Schedule TZ | In each profile | Per `DailyValueSchedule` | Per `ProfileSwitch` event | From profile |

**Gap**: AAPS uses fixed `utcOffset` captured at event time, which does not automatically handle DST transitions (GAP-TZ-001).

### Profile Sync Direction

| System | Upload | Download | Identity Field |
|--------|--------|----------|----------------|
| Loop | Optional | No | N/A |
| AAPS | Yes | Yes | `interfaceIDs.nightscoutId` |
| Trio | No | Yes | `_id` from NS |
| xDrip4iOS | No | Yes (read-only) | N/A |

**See Also**: [Profile/Therapy Settings Comparison](../../docs/60-research/profile-therapy-settings-comparison.md) for comprehensive cross-system analysis.

---

## Override/Adjustment Concepts

| Concept | Nightscout | Loop | AAPS | Trio | xDrip+ |
|---------|------------|------|------|------|--------|
| Override Active | `Temporary Override` active | `overrideContext != nil` | `ProfileSwitch.percentage != 100` | `Override.enabled` | N/A (no override) |
| Duration | `duration` (minutes) | `duration` (TimeInterval) | `duration` (minutes) | `duration` (minutes) | N/A |
| Reason/Name | `reason` | `preset.symbol` + `preset.name` | N/A | `reason` | N/A |
| Target Adjustment | `targetTop`/`targetBottom` | `settings.targetRange` | `targetLow`/`targetHigh` | `target` | N/A |
| Overall Insulin % | `insulinNeedsScaleFactor` | `settings.insulinNeedsScaleFactor` | `ProfileSwitch.percentage` | `insulinNeedsScaleFactor` | N/A |
| Supersession | N/A (gap) | Built-in (new cancels old) | N/A (last switch wins) | Built-in | N/A |

**Note**: xDrip+ is a CGM app without override/adjustment concepts. It receives and displays AAPS overrides but does not create them.
- Broadcast receiver for AAPS: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/services/broadcastservice/BroadcastService.java`

---

## Sync Identity Fields

| Controller | Nightscout Field | Purpose | Source Code |
|------------|------------------|---------|-------------|
| AAPS | `identifier` | Client-side unique ID | `database/entities/*.kt` |
| Loop | `pumpId` + `pumpType` + `pumpSerial` | Composite pump event ID | `LoopKit/*.swift` |
| xDrip+ (Android) | `uuid` | Client-generated UUID | `models/Treatments.java#L85` |
| xDrip4iOS | `uuid` | Client-generated UUID | `Managers/Nightscout/*.swift` |
| Generic | `_id` | MongoDB ObjectId (server-generated) | N/A |

**Gap**: No unified sync identity field exists across controllers (GAP-003).

---

## Authority/Actor Identity

| Concept | Nightscout | Loop | AAPS | Trio | xDrip+ |
|---------|------------|------|------|------|--------|
| Actor Identity | `enteredBy` (unverified) | `origin` | `pumpType` | `enteredBy` | `enteredBy: "xdrip"` |
| Authority Level | N/A (gap) | N/A | N/A | N/A | N/A |
| Verified Identity | Proposed (OIDC) | N/A | N/A | N/A | N/A |

**Gap**: No system tracks verified actor identity with authority levels (GAP-AUTH-001, GAP-AUTH-002).

### xDrip+ Unique Identifiers

| Identifier | Value | Source |
|------------|-------|--------|
| `enteredBy` | `"xdrip"` | `Treatments.XDRIP_TAG` constant |
| `device` | `"xDrip-" + manufacturer + model` | `NightscoutUploader.getDeviceName()` |
| User-Agent | `"xDrip+ " + BuildConfig.VERSION_NAME` | HTTP headers |

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

| Event | Nightscout eventType | Loop | AAPS | Trio | xDrip+ |
|-------|---------------------|------|------|------|--------|
| Sensor Start | `Sensor Start` | `CGMSensorEvent` | `TherapyEvent.SENSOR_CHANGE` | `SensorChange` | `Sensor Start` |
| Sensor Stop | N/A | N/A | N/A | N/A | `Sensor Stop` (unique) |
| Site Change | `Site Change` | `PumpEvent` | `TherapyEvent.CANNULA_CHANGE` | `SiteChange` | N/A |
| Pump Battery | `Pump Battery Change` | `PumpEvent` | `TherapyEvent` | `PumpBattery` | N/A |
| BG Check | `BG Check` | `BGCheck` | `TherapyEvent.FINGER_STICK_BG_VALUE` | `BGCheck` | `BG Check` |

---

## Code References

| Project | Override/Adjustment Model Location |
|---------|-----------------------------------|
| Nightscout | `crm:lib/plugins/careportal.js` |
| Loop | `loop:Loop/Models/TemporaryScheduleOverride.swift` |
| AAPS | `aaps:database/entities/ProfileSwitch.kt` |
| Trio | `trio:FreeAPS/Sources/Models/Override.swift` |
| xDrip+ (Android) | N/A (CGM-focused, no override) |

### xDrip+ Key Source Files

| Component | Location | Lines | Purpose |
|-----------|----------|-------|---------|
| BgReading | `models/BgReading.java` | ~2,394 | Core glucose entity |
| Treatments | `models/Treatments.java` | ~1,436 | Treatment/bolus/carb entity |
| Calibration | `models/Calibration.java` | ~1,123 | Calibration data |
| UploaderQueue | `utilitymodels/UploaderQueue.java` | ~557 | Multi-destination upload queue |
| NightscoutUploader | `utilitymodels/NightscoutUploader.java` | ~1,470 | Nightscout REST API client |
| NightscoutFollow | `cgm/nsfollow/NightscoutFollow.java` | ~135 | Follower mode |
| DexCollectionType | `utils/DexCollectionType.java` | ~392 | CGM source enum (20+ types) |

**Full documentation**: See `mapping/xdrip-android/` for comprehensive xDrip+ analysis.

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

## Pump Protocol Models (Deep Dive)

> **See Also**: [Pump Protocols Specification](../../specs/pump-protocols-spec.md) for comprehensive low-level protocol documentation.

### Transport Layer Comparison

| Aspect | Omnipod DASH | Dana RS | Medtronic |
|--------|--------------|---------|-----------|
| **Transport** | BLE Direct | BLE Direct | RF (916.5/868 MHz) |
| **Bridge Device** | No | No | RileyLink required |
| **MTU** | 20 bytes | 20 bytes | 64 bytes |
| **Encryption** | AES-128-CCM | Matrix + XOR | None |
| **Session Auth** | EAP-AKA (Milenage) | Time + Password | Serial check |

### Omnipod DASH Message Structure

| Component | Offset | Size | Description |
|-----------|--------|------|-------------|
| Magic | 0 | 2 | "TW" pattern |
| Flags | 2 | 2 | Version, SAS, TFS, EQOS, ack, priority |
| Sequence | 4 | 1 | Message sequence number |
| Ack Num | 5 | 1 | Acknowledgment number |
| Payload Size | 6 | 2 | 11-bit size (shifted) |
| Source ID | 8 | 4 | Controller address |
| Dest ID | 12 | 4 | Pod address |
| Payload | 16 | N | Data + 8-byte MAC for encrypted |

**Source**: `OmniBLE/Bluetooth/MessagePacket.swift`

### Omnipod DASH Command Opcodes

| Opcode | Command | Direction | Description |
|--------|---------|-----------|-------------|
| `0x01` | VersionResponse | Pod→Ctrl | Pod version info |
| `0x07` | AssignAddress | Ctrl→Pod | Assign pod address |
| `0x0e` | GetStatus | Ctrl→Pod | Request status |
| `0x17` | BolusExtra | Ctrl→Pod | Extended bolus params |
| `0x1a` | SetInsulinSchedule | Ctrl→Pod | Main delivery command |
| `0x1d` | StatusResponse | Pod→Ctrl | Current status |
| `0x1f` | CancelDelivery | Ctrl→Pod | Stop delivery |

**Source**: `OmniBLE/OmnipodCommon/MessageBlocks/MessageBlock.swift`

### Omnipod Delivery Constants

| Constant | Value | Unit |
|----------|-------|------|
| Pulse Size | 0.05 | U |
| Pulses per Unit | 20 | pulses/U |
| Bolus Delivery Rate | 0.025 | U/s |
| Max Reservoir Reading | 50 | U |
| Service Duration | 80 | hours |

**Source**: `OmniBLE/OmnipodCommon/Pod.swift`

### Dana RS Packet Structure

| Component | Offset | Size | Description |
|-----------|--------|------|-------------|
| Start Bytes | 0 | 2 | `0xA5 0xA5` |
| Length | 2 | 1 | Packet size - 7 |
| Type | 3 | 1 | Command type |
| OpCode | 4 | 1 | Command code |
| Data | 5 | N | Payload |
| CRC | -4 | 2 | CRC-16 (big-endian) |
| End Bytes | -2 | 2 | `0x5A 0x5A` |

**Source**: `pump/danars/comm/DanaRSPacket.kt`

### Dana RS Encryption Modes

| Mode | Description | CRC Variant |
|------|-------------|-------------|
| DEFAULT | Legacy (time + password + SN) | Standard polynomial |
| RSv3 | Pairing key + random key + matrix | Modified polynomial |
| BLE5 | 6-digit PIN + matrix (Dana-i) | BLE5-specific polynomial |

**Source**: `pump/danars/encryption/BleEncryption.kt`

### Medtronic History Entry Types

| Code | Entry | Head | Date | Body |
|------|-------|------|------|------|
| `0x01` | Bolus | 4 (8 on 523+) | 5 | 0 |
| `0x16` | TempBasalDuration | 2 | 5 | 0 |
| `0x33` | TempBasalRate | 2 | 5 | 1 |
| `0x1e` | SuspendPump | 2 | 5 | 0 |
| `0x6e` | DailyTotals523 | 1 | 2 | 49 |

**Source**: `pump/medtronic/comm/history/pump/PumpHistoryEntryType.kt`

### Pump Protocol Gap Summary

| Gap ID | Description | Impact |
|--------|-------------|--------|
| **GAP-PUMP-006** | Medtronic RF lacks encryption | Replay attacks possible |
| **GAP-PUMP-007** | Omnipod uses non-standard Milenage | Requires Insulet-specific constants |
| **GAP-PUMP-008** | Dana RS encryption mode detection | Must handle 3 modes |
| **GAP-PUMP-009** | Medtronic history size varies by model | Parsing must be model-aware |

**Full details**: See [Pump Protocols Specification](../../specs/pump-protocols-spec.md)

---

## Insulin Curve Models (Deep Dive)

> **See Also**: [Insulin Curves Deep Dive](../../docs/10-domain/insulin-curves-deep-dive.md) for comprehensive cross-system analysis of insulin activity curves, mathematical formulas, and IOB calculations.

### Mathematical Model Comparison

| System | Primary Model | Formula Source | Legacy Model |
|--------|---------------|----------------|--------------|
| **Loop** | Exponential | Original | N/A |
| **oref0** | Exponential | Loop (copied) | Bilinear |
| **AAPS** | Exponential | oref0 (port) | N/A |
| **Trio** | Exponential | oref0 (via JS) | Bilinear |
| **xDrip+** | Linear Trapezoid | Independent | N/A |

**Key Finding**: All major AID systems share the **same exponential insulin model**. oref0 explicitly credits Loop as the source: `// Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473`

### Insulin Type Presets

| Preset | Loop Peak | oref0 Peak | AAPS Peak | Trio Peak | Delay |
|--------|-----------|------------|-----------|-----------|-------|
| Rapid-Acting Adult | 75 min | 75 min | 75 min | 75 min | Loop: 10 min, others: 0 |
| Rapid-Acting Child | 65 min | N/A | N/A | N/A | 10 min |
| Ultra-Rapid / Fiasp | 55 min | 55 min | 55 min | 55 min | Loop: 10 min, others: 0 |
| Lyumjev | **55 min** | 55 min | **45 min** | 55 min | Loop: 10 min, others: 0 |
| Afrezza (Inhaled) | 29 min | N/A | N/A | N/A | 10 min |
| Free Peak | N/A | 50-120 min | Configurable | Configurable | 0 |

**Important**: Peak times are NOT equivalent across systems. AAPS Lyumjev uses **45 min** while Loop uses **55 min**. Loop also includes a 10-minute delay before activity starts that oref0/AAPS/Trio do not have.

### DIA (Duration of Insulin Action) Constraints

| System | Minimum DIA | Default DIA | Enforcement |
|--------|-------------|-------------|-------------|
| **Loop** | Fixed per preset | 5-6 hr | Hardcoded in model |
| **oref0 (bilinear)** | 3 hr | 3 hr | Soft clamp |
| **oref0 (exponential)** | 5 hr | 5 hr | `requireLongDia` flag |
| **AAPS** | 5 hr | 5 hr | `hardLimits.minDia()` |
| **Trio** | 5 hr | Profile-defined | Via oref0 |
| **xDrip+** | None | Per profile | User configurable |

### Insulin Model Implementation

| Aspect | oref0 | Loop | AAPS | Trio | xDrip+ |
|--------|-------|------|------|------|--------|
| **Source File** | `lib/iob/calculate.js` | `ExponentialInsulinModel.swift` | `InsulinOrefBasePlugin.kt` | `lib/iob/index.js` | `LinearTrapezoidInsulin.java` |
| **Model Class** | N/A (function) | `InsulinModel` protocol | `Insulin` interface | N/A (function) | `Insulin` abstract class |
| **Peak Config** | `profile.insulinPeakTime` | Per preset | Plugin-specific | `preferences.insulinPeakTime` | Per profile JSON |
| **DIA Config** | `profile.dia` | Per preset | `profile.dia` | `pumpSettings.insulinActionCurve` | `Insulin.maxEffect` |
| **Custom Peak** | Yes (ranges) | No | Yes (Free Peak) | Yes (via oref0) | Yes (JSON config) |

### IOB Calculation Components

| Component | oref0 | Loop | AAPS | Trio | xDrip+ |
|-----------|-------|------|------|------|--------|
| **Total IOB** | `iob.iob` | `insulinOnBoard` | `iobTotal.iob` | `iob.iob` | `Iob.getIobAtTime()` |
| **Basal IOB** | `iob.basaliob` | N/A (combined) | `iobTotal.basaliob` | `iob.basaliob` | Not applicable (no basal tracking) |
| **Bolus IOB** | `iob.bolusiob` | N/A (combined) | N/A | `iob.bolusiob` | Not applicable (no basal/bolus split) |
| **Activity** | `iob.activity` | N/A | `iobTotal.activity` | `iob.activity` | `calculateActivity()` |
| **Bolus Snooze** | `iob.bolussnooze` | N/A | `iobTotal.bolussnooze` | `iob.bolussnooze` | Not applicable |
| **Zero Temp IOB** | `iob.iobWithZeroTemp` | N/A | `iobWithZeroTemp` | `iobWithZeroTemp` | Not applicable |

**xDrip+ Note**: xDrip+ tracks total IOB from all insulin injections but does not distinguish basal vs bolus IOB (it tracks injections, not pump-controlled basals). The `Iob.getIobBreakdown()` method provides IOB per insulin type (e.g., NovoRapid vs Lantus), not basal/bolus split.

### xDrip+ Multi-Insulin Support

xDrip+ uniquely supports multiple insulin types per treatment:

| Feature | xDrip+ | AID Systems |
|---------|--------|-------------|
| **Multi-Insulin Per Treatment** | ✅ `insulinJSON` array | No |
| **Long-Acting Insulin Tracking** | ✅ (13+ types) | No |
| **Concentration Support** | U100-U500 | U100-U200 (AAPS only) |
| **IOB Per Insulin Type** | ✅ `Iob.getIobBreakdown()` | No |
| **Smart Pen Integration** | InPen, Pendiq, NovoPen | No |

**xDrip+ Insulin Profiles**: `externals/xDrip/app/src/main/res/raw/insulin_profiles.json`

### Insulin Curve Gap Summary

| Gap ID | Description | Impact |
|--------|-------------|--------|
| **GAP-INS-001** | Insulin model metadata not synced to Nightscout | Cannot determine which curve produced IOB |
| **GAP-INS-002** | No standardized multi-insulin representation | xDrip+ `insulinJSON` is non-portable |
| **GAP-INS-003** | Peak time customization not captured in treatments | Cannot reproduce historical IOB calculations |
| **GAP-INS-004** | xDrip+ linear trapezoid model incompatible | IOB values differ from AID exponential models |

**Full gap details**: See [Insulin Curves Deep Dive - Related Gaps](../../docs/10-domain/insulin-curves-deep-dive.md#related-gaps)

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

## CGM Source Models (Deep Dive)

> **See Also**: [CGM Data Sources Deep Dive](../../docs/10-domain/cgm-data-sources-deep-dive.md) for comprehensive analysis of how CGM data flows from sensors to Nightscout.

### Data Source Types

| Source Category | xDrip+ Android | xDrip4iOS | Loop | AAPS |
|-----------------|----------------|-----------|------|------|
| **Direct Bluetooth** | G5, G6, G7, Medtrum, GluPro | G5, G6, G7, Libre 2 | CGMBLEKit, G7SensorKit | Via xDrip+ |
| **Bridge Devices** | 6+ (MiaoMiao, Bubble, Wixel, etc.) | 4 (MiaoMiao, Bubble, Blucon, Atom) | No | Via xDrip+ |
| **Cloud Followers** | NS, Share, CareLink, WebFollow | NS, Share, LibreLinkUp | Share only | NS only |
| **Companion Apps** | 5+ (LibreAlarm, NSEmulator, etc.) | No | No | No |
| **Local Web Server** | Yes (port 17580) | No | No | No |
| **Total Source Types** | 20+ | ~6 | 3-4 | Via xDrip+ |

### Calibration Models

| System | Calibration Options | Description |
|--------|---------------------|-------------|
| **xDrip+ Android** | xDrip Original, Native, Datricsae, Last7Unweighted, FixedSlope | Pluggable algorithms |
| **xDrip4iOS** | Native, WebOOP | Transmitter calibration or OOP server |
| **Loop** | Native only | Transmitter-calibrated readings |
| **AAPS** | Via xDrip+ | Inherits xDrip+ calibration |
| **Trio** | Native only | Transmitter-calibrated readings |

### BgReading Entity Mapping

| Field | xDrip+ Android | xDrip4iOS | Loop | AAPS | Nightscout |
|-------|----------------|-----------|------|------|------------|
| **Glucose Value** | `calculated_value` | `calculatedValue` | `quantity` | `value` | `sgv` |
| **Timestamp** | `timestamp` | `timeStamp` | `startDate` | `timestamp` | `date` |
| **Raw Value** | `raw_data` | `rawData` | N/A | N/A | `unfiltered` |
| **Filtered Value** | `filtered_data` | `filteredData` | N/A | N/A | `filtered` |
| **Trend Slope** | `dg_slope` | `calculatedValueSlope` | `trendType` | `trendArrow` | `direction` |
| **Noise** | `noise` | N/A | N/A | `noise` | `noise` |
| **Sync Identity** | `uuid` | `uuid` | N/A | `interfaceIDs` | `_id` |
| **Source Info** | `source_info` | `deviceName` | `provenanceIdentifier` | `sourceSensor` | `device` |

### Follower Data Sources

| Follower Type | xDrip+ Android | xDrip4iOS | Loop | Trio |
|---------------|----------------|-----------|------|------|
| **Nightscout** | `NSFollow` | `NightscoutFollowManager` | N/A | Via CGMManager |
| **Dexcom Share** | `SHFollow` | `DexcomShareFollowManager` | `ShareClient` | `ShareClient` |
| **LibreLinkUp** | No | `LibreLinkUpFollowManager` | No | No |
| **CareLink** | `CLFollow` | No | No | No |
| **Generic Web** | `WebFollow` | No | No | No |

### Collection Type Enum (xDrip+ Android)

```java
// DexCollectionType categories
usesBluetooth:  BluetoothWixel, DexcomShare, DexbridgeWixel, LimiTTer, ...
usesWifi:       WifiWixel, WifiBlueToothWixel, Mock, LimiTTerWifi, ...
usesLibre:      LimiTTer, LibreAlarm, LimiTTerWifi, LibreWifi, LibreReceiver
isPassive:      NSEmulator, NSFollow, SHFollow, WebFollow, LibreReceiver, ...
usesDexcomRaw:  BluetoothWixel, DexbridgeWixel, WifiWixel, DexcomG5, ...
```

### CGM Data Provenance Gap Summary

| Gap ID | Description | Impact |
|--------|-------------|--------|
| **GAP-CGM-001** | Calibration algorithm not tracked | Cannot determine calibration quality |
| **GAP-CGM-002** | Bridge device info lost in upload | Cannot identify hardware issues |
| **GAP-CGM-003** | Sensor age not standardized | Cannot assess reading reliability |
| **GAP-CGM-004** | No universal source taxonomy | Free-form `device` field unreliable |
| **GAP-CGM-005** | Raw values not uploaded by iOS | Cannot recalibrate or validate |
| **GAP-CGM-006** | Follower source not distinguished | Cannot tell direct vs cloud data |

**Full gap details**: See [CGM Data Sources Deep Dive - Gap Summary](../../docs/10-domain/cgm-data-sources-deep-dive.md#gap-summary)

---

## Algorithm Comparison (Deep Dive)

> **See Also**: [Algorithm Comparison Deep Dive](../../docs/10-domain/algorithm-comparison-deep-dive.md) for comprehensive cross-system analysis explaining why the same CGM data produces different dosing recommendations.

### Prediction Methodology

| Aspect | Loop | oref0/AAPS/Trio |
|--------|------|-----------------|
| **Prediction Style** | Single combined curve | 4 separate curves (IOB, COB, UAM, ZT) |
| **Effect Combination** | All effects summed + momentum blend | Each curve independent |
| **Decision Basis** | Minimize combined prediction excursions | Use minPredBG across all curves |
| **UAM Handling** | Implicitly via Retrospective Correction | Explicit UAM curve |
| **Safety Floor** | Combined prediction minimum | ZT curve provides floor |

### Carb Absorption Models

| Aspect | Loop | oref0/AAPS/Trio |
|--------|------|-----------------|
| **Model Type** | Dynamic piecewise linear | Linear decay with assumed rate |
| **Adaptation** | Real-time based on ICE (Insulin Counteraction Effects) | Limited deviation-based |
| **Absorption Time** | Per-entry (user or default) | Global `carbs_hr` rate |
| **Fast Carbs** | Handles via dynamic adaptation | Handled via UAM curve |

### Sensitivity Adjustment Mechanisms

| Mechanism | Loop | oref0 | AAPS | Trio |
|-----------|------|-------|------|------|
| **Real-time** | Retrospective Correction | Via deviation | Via deviation | Via deviation |
| **Historical Pattern** | No | Autosens (8-24h) | Autosens or DynISF | Autosens |
| **TDD-Based** | No | No | Dynamic ISF option | No |
| **Override/Preset** | Override presets | Temp target | Profile switch % | Override profiles |

### Algorithm Interoperability Gaps

| Gap ID | Description | Systems Affected |
|--------|-------------|------------------|
| **GAP-ALG-001** | Insulin model configuration differs (preset vs DIA field) | Loop vs oref0/AAPS/Trio |
| **GAP-ALG-002** | Carb absorption model differs (dynamic vs linear) | Loop vs oref0/AAPS/Trio |
| **GAP-ALG-003** | Sensitivity mechanism differs (RC vs Autosens) | Loop vs oref0/AAPS/Trio |
| **GAP-ALG-004** | Loop has no explicit UAM curve (relies on RC instead) | Loop |
| **GAP-ALG-005** | Loop has no SMB algorithm (Loop 3 auto-bolus is distinct from SMB) | Loop |
| **GAP-ALG-006** | AAPS DynISF is TDD-based while others are deviation-based | AAPS vs others |
| **GAP-ALG-007** | Trio supports SMB time-window scheduling (`smbIsScheduledOff`) | Trio |
| **GAP-ALG-008** | Prediction transparency differs (1 combined curve vs 4 separate curves) | Loop vs oref0/AAPS/Trio |

**Full gap details with source citations**: See [Algorithm Comparison Deep Dive - Section 7](../../docs/10-domain/algorithm-comparison-deep-dive.md#7-identified-gaps)

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

## oref0-Specific Concepts

### Core Algorithm Components

oref0 is the reference algorithm that powers AAPS (via Kotlin port) and Trio (via embedded JS). Understanding oref0 is essential for understanding these systems.

| Component | File | Purpose |
|-----------|------|---------|
| `determine-basal` | `lib/determine-basal/determine-basal.js` | Main algorithm decision engine |
| `autosens` | `lib/determine-basal/autosens.js` | 24h sensitivity detection |
| `cob` | `lib/determine-basal/cob.js` | Carb absorption detection |
| `iob/calculate` | `lib/iob/calculate.js` | IOB calculation with bilinear/exponential curves |
| `iob/total` | `lib/iob/total.js` | IOB aggregation across treatments |

### Prediction Curves (predBGs)

oref0 outputs four separate prediction curves, each representing a different scenario:

| Curve | Field | Description | Loop Equivalent |
|-------|-------|-------------|-----------------|
| IOB | `predBGs.IOB[]` | Insulin-only prediction (baseline) | Combined `predictedGlucose` |
| COB | `predBGs.COB[]` | With carb absorption (linear decay) | Carb effect component |
| UAM | `predBGs.UAM[]` | Unannounced meal (deviation-based) | N/A (no UAM) |
| ZT | `predBGs.ZT[]` | Zero temp "what-if" for safety | N/A |

**Cross-Project Significance**: Loop only uploads combined predictions, not component effects (GAP-SYNC-002). oref0's separate arrays enable algorithm comparison.

### Carb Absorption Model

| Parameter | oref0 | AAPS | Loop | Notes |
|-----------|-------|------|------|-------|
| Model Type | Linear decay | Same | PiecewiseLinear (dynamic) | oref0 is simpler |
| Min Absorption Rate | `min_5m_carbimpact` (8 mg/dL/5m) | Same | `absorptionTimeOverrun` | Prevents stalled COB |
| Max COB | `maxCOB` (120g) | Same | Per-entry limit | Global cap |
| Absorption Duration | Calculated from CI | Same | Observed dynamically | Different approaches |

### SMB (Super Micro Bolus) Parameters

| Parameter | oref0 | AAPS | Trio | Description |
|-----------|-------|------|------|-------------|
| `maxSMBBasalMinutes` | 75 | Same | Same | Max SMB as minutes of basal |
| `maxUAMSMBBasalMinutes` | 30 | Same | Same | Max SMB in UAM mode |
| `SMBInterval` | 3 | Same | Same | Minimum minutes between SMBs |
| `enableSMB_always` | false | Same | Same | SMB at all times |
| `enableSMB_with_COB` | true | Same | Same | SMB when COB > 0 |
| `enableSMB_after_carbs` | true | Same | Same | SMB for 6h after carbs |

### Shared IOB Formula Origin

The exponential insulin activity curve in oref0 was sourced directly from Loop:

```
oref0:lib/iob/calculate.js#L125
// Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473
```

This means **oref0, AAPS, Trio, and Loop all use the same exponential insulin model**, enabling direct cross-project IOB comparison for rapid-acting and ultra-rapid insulin types.

### Deviation-Based Algorithm

oref0's core innovation is deviation analysis:

| Term | Calculation | Purpose |
|------|-------------|---------|
| BGI | `-activity × sens × 5` | Expected 5-min BG change from insulin |
| Deviation | `delta - BGI` | Unexplained BG change (carbs, sensitivity) |
| eventualBG | `BG - (IOB × sens) + deviation` | Where BG is heading |

### Safety Parameters

| Parameter | oref0 Default | Description |
|-----------|---------------|-------------|
| `max_iob` | 6 U | Maximum insulin on board |
| `max_basal` | 4 U/hr | Maximum temp basal rate |
| `autosens_min` | 0.5 | Minimum sensitivity ratio |
| `autosens_max` | 2.0 | Maximum sensitivity ratio |
| `max_daily_safety_multiplier` | 4 | Multiplier on max daily basal |
| `current_basal_safety_multiplier` | 5 | Multiplier on current basal |

---

## Remote Command Security Models

> **See Also**: [Remote Commands Cross-System Comparison](../../docs/10-domain/remote-commands-comparison.md) for comprehensive source code analysis.

### Transport and Authentication

| Aspect | Trio | Loop | AAPS |
|--------|------|------|------|
| Transport | APNS Push | APNS Push | SMS |
| Payload Encryption | AES-256-GCM | None | None |
| Authentication | Shared secret | TOTP OTP | Phone whitelist + TOTP + PIN |
| Key Derivation | SHA256 | Base32 secret | HMAC key |

### Security Parameters

| Parameter | Trio | Loop | AAPS |
|-----------|------|------|------|
| Encryption Algorithm | AES-256-GCM | N/A | N/A |
| Key Size | 256 bits | 160+ bits (SHA1) | 160 bits |
| OTP Algorithm | N/A | HMAC-SHA1 | HMAC |
| OTP Digits | N/A | 6 | 6 + PIN (3+) |
| OTP Period | N/A | 30 sec | 30 sec |
| Nonce Size | 12 bytes | N/A | N/A |

### Replay Protection

| Mechanism | Trio | Loop | AAPS |
|-----------|------|------|------|
| Timestamp Window | ±10 minutes | Expiration date | Command timeout |
| Duplicate Detection | Implicit (timestamp) | In-memory tracking | `processed` flag |
| OTP Reuse Prevention | N/A | Track recent OTPs | Timeout-based |
| Bolus Distance | Recent bolus check (20%) | N/A | Configurable minimum |

### Command Type Support

| Command | Trio | Loop | AAPS |
|---------|------|------|------|
| Remote Bolus | `bolus` | `bolusEntry` | `BOLUS` SMS |
| Remote Carbs | `meal` | `carbsEntry` | `CARBS` SMS |
| Override Start | `startOverride` | `temporaryScheduleOverride` | N/A |
| Override Cancel | `cancelOverride` | `cancelTemporaryOverride` | N/A |
| Temp Target | `tempTarget` | N/A (via override) | `TARGET` SMS |
| Cancel TT | `cancelTempTarget` | N/A | `TARGET STOP` SMS |
| Basal Change | N/A | N/A | `BASAL` SMS |
| Loop Control | N/A | N/A | `LOOP` SMS |
| Pump Control | N/A | N/A | `PUMP` SMS |
| Profile Switch | N/A | N/A | `PROFILE` SMS |

### OTP Requirement per Command

| Command Type | Trio | Loop | AAPS |
|--------------|------|------|------|
| Bolus | N/A (encrypted) | **Required** | Required |
| Carbs | N/A (encrypted) | **Required** | Required |
| Override | N/A (encrypted) | **Not Required** ⚠️ | N/A |
| Cancel Override | N/A (encrypted) | **Not Required** ⚠️ | N/A |

**Security Gap**: Loop does not require OTP for override commands. See [GAP-REMOTE-001](../../traceability/gaps.md#gap-remote-001-remote-command-authorization-unverified).

### Safety Enforcement

| Check | Trio | Loop | AAPS |
|-------|------|------|------|
| Max Bolus | Remote handler | Downstream | ConstraintChecker |
| Max IOB | Remote handler | Downstream | ConstraintChecker |
| Recent Bolus | 20% rule | N/A | Min distance |
| Queue Empty | N/A | N/A | 3-min wait |
| Pump Suspended | N/A | N/A | Checked |

### Source File References

| System | Primary Source |
|--------|---------------|
| Trio | `trio:Trio/Sources/Services/RemoteControl/` |
| Loop | `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/` |
| AAPS | `aaps:plugins/main/src/main/kotlin/.../smsCommunicator/` |

---

## API Version Models

> **See Also**: [Nightscout API v1 vs v3 Comparison](../../docs/10-domain/nightscout-api-comparison.md)

### API Version by Client

| Client | API Version | Authentication | Sync Method |
|--------|-------------|----------------|-------------|
| **AAPS** | v3 | Bearer token (opaque) | History endpoint |
| **Loop** | v1 | SHA1 secret | Polling with date filter |
| **Trio** | v1 | SHA1 secret | Polling with date filter |
| **xDrip+** | v1 | SHA1 secret | Polling with date filter |
| **OpenAPS** | v1 | SHA1 secret | Polling with date filter |
| **Nightguard** | v1 | SHA1 secret (read-only) | Polling |
| **xDrip4iOS** | v1 | SHA1 secret | Polling with date filter |

### Document Identity Fields

| System | API Version | Primary ID | Secondary ID | Update Method |
|--------|-------------|-----------|--------------|---------------|
| **Nightscout v1** | v1 | `_id` (MongoDB ObjectId) | N/A | PUT to `/{collection}/{_id}` |
| **Nightscout v3** | v3 | `identifier` (server-assigned) | `_id` (internal) | PUT/PATCH to `/{collection}/{identifier}` |
| **AAPS** | v3 | `identifier` | `interfaceIDs.nightscoutId` | PATCH via SDK |
| **Loop** | v1 | `_id` | `syncIdentifier` | POST (no upsert) |
| **Trio** | v1 | `_id` | `syncIdentifier` | POST (no upsert) |
| **xDrip+** | v1 | `_id` | `uuid` | PUT upsert |

### API v3 Exclusive Features

| Feature | Description | Used By |
|---------|-------------|---------|
| `identifier` | Server-assigned immutable document ID | AAPS |
| `history/{timestamp}` | Incremental sync since timestamp | AAPS |
| `isValid` | Soft-delete flag (false = deleted) | AAPS |
| `isDeduplication` | Response flag indicating duplicate | AAPS |
| `srvModified` | Server modification timestamp | AAPS |
| Bearer Access Tokens | Opaque tokens with Shiro permissions | AAPS |
| Shiro Permissions | Granular `api:collection:operation` | AAPS |

### Sync Pattern Comparison

| Aspect | v1 Polling | v3 History |
|--------|------------|------------|
| Detects Insertions | Yes | Yes |
| Detects Updates | Partial | Yes |
| Detects Deletions | No | Yes (`isValid: false`) |
| Bandwidth Efficiency | Lower | Higher |
| Time Precision | Seconds | Milliseconds |

### Query Syntax Comparison

| Operation | v1 Syntax | v3 Syntax |
|-----------|-----------|-----------|
| Equality | `find[type]=sgv` | `type$eq=sgv` |
| Greater Than | `find[date][$gte]=1705000000000` | `date$gte=1705000000000` |
| Less Than | `find[date][$lte]=1705000000000` | `date$lte=1705000000000` |
| Count/Limit | `count=100` | `limit=100` |
| Sorting | N/A (server default) | `sort=field` or `sort$desc=field` |

**Gap Reference**: GAP-API-001 (v1 cannot detect deletions), GAP-API-003 (no v3 adoption path for iOS)

---

## Pump Communication Models

> **See Also**: [Pump Communication Deep Dive](../../docs/10-domain/pump-communication-deep-dive.md) for comprehensive protocol analysis.

### Pump Interface Abstraction

| Concept | Loop/Trio | AAPS |
|---------|-----------|------|
| **Pump Interface** | `PumpManager` protocol | `Pump` interface |
| **Status Object** | `PumpManagerStatus` | `PumpDescription` + state getters |
| **Command Result** | `PumpManagerResult<T>` | `PumpEnactResult` |
| **History Sync** | `PumpManagerDelegate.hasNewPumpEvents()` | `PumpSync` interface |
| **Connection State** | Implicit (delegate callbacks) | `isConnected()`, `isConnecting()`, `isHandshakeInProgress()` |

### Core Pump Commands

| Command | Loop PumpManager | AAPS Pump |
|---------|------------------|-----------|
| **Bolus** | `enactBolus(units:activationType:completion:)` | `deliverTreatment(DetailedBolusInfo)` |
| **Cancel Bolus** | `cancelBolus(completion:)` | `stopBolusDelivering()` |
| **Temp Basal** | `enactTempBasal(unitsPerHour:for:completion:)` | `setTempBasalAbsolute(rate, minutes, profile, enforceNew, tbrType)` |
| **Cancel TBR** | `enactTempBasal(0, 0, completion:)` | `cancelTempBasal(enforceNew)` |
| **Suspend** | `suspendDelivery(completion:)` | `suspendDelivery()`* or `setTempBasalPercent(0, ...)` |
| **Resume** | `resumeDelivery(completion:)` | `resumeDelivery()`* or `cancelTempBasal()` |
| **Set Profile** | `syncBasalRateSchedule(items:completion:)` | `setNewBasalProfile(Profile)` |

*Note: AAPS supports native suspend/resume on some pumps; others emulate via 0% temp basal (`PUMP_SUSPEND` or `EMULATED_PUMP_SUSPEND` types).

### Pump Transport Protocols

| Pump Type | Loop/Trio | AAPS | Protocol |
|-----------|-----------|------|----------|
| **Omnipod DASH** | OmniBLE | omnipod-dash | BLE + AES-CCM |
| **Omnipod Eros** | OmniKit | omnipod-eros | RF 433MHz + RileyLink |
| **Medtronic** | MinimedKit | medtronic | RF 916MHz + RileyLink |
| **Dana RS** | N/A | danars | BLE + Custom encryption |
| **Dana i** | N/A | danars | BLE + Custom encryption |
| **Accu-Chek Insight** | N/A | insight | BLE + SightParser |
| **Accu-Chek Combo** | N/A | combov2 | RF + ruffy |
| **Diaconn G8** | N/A | diaconn | BLE |
| **Medtrum** | N/A | medtrum | BLE |

### Precision Constraints Comparison

| Pump | Bolus Step | Basal Step | TBR Duration Step |
|------|------------|------------|-------------------|
| **Omnipod DASH/Eros** | 0.05 U | 0.05 U/hr | 30 min |
| **Dana RS** | 0.05 U | 0.01 U/hr | 15/30/60 min |
| **Medtronic 523/723** | 0.05 U | 0.025 U/hr | 30 min |
| **Accu-Chek Insight** | 0.01-0.05 U | 0.01 U/hr | 15 min |
| **Diaconn G8** | 0.01 U | 0.01 U/hr | 30 min |

### Bolus State Machine

| State | Loop `BolusState` | AAPS |
|-------|-------------------|------|
| **No Bolus** | `.noBolus` | N/A (no explicit state) |
| **Initiating** | `.initiating` | Pre-`deliverTreatment()` |
| **In Progress** | `.inProgress(dose)` | `BolusProgressData.delivering` |
| **Canceling** | `.canceling` | `stopBolusDelivering()` called |
| **Uncertain** | `deliveryIsUncertain: true` | `PumpEnactResult.success == false` |

### Basal Delivery State Machine

| State | Loop `BasalDeliveryState` | AAPS |
|-------|---------------------------|------|
| **Active (scheduled)** | `.active(at)` | `isSuspended() == false` |
| **Temp Basal** | `.tempBasal(dose)` | `PumpSync.expectedPumpState().temporaryBasal != null` |
| **Suspended** | `.suspended(at)` | `isSuspended() == true` |
| **Initiating TBR** | `.initiatingTempBasal` | N/A |
| **Canceling TBR** | `.cancelingTempBasal` | N/A |

### Temp Basal Type Enums

| AAPS TBR Type | Description | Nightscout |
|---------------|-------------|------------|
| `NORMAL` | Standard temp basal | `Temp Basal` |
| `EMULATED_PUMP_SUSPEND` | Suspend via 0% basal | `Temp Basal` |
| `PUMP_SUSPEND` | Actual pump suspend | `Temp Basal` |
| `SUPERBOLUS` | Superbolus temp basal | `Temp Basal` |
| `FAKE_EXTENDED` | Extended bolus emulation | `Temp Basal` |

**Gap Reference**: GAP-PUMP-002 (extended bolus not in Loop), GAP-PUMP-003 (TBR duration units)

---

## Dexcom BLE Protocol Models

> **See Also**: [Dexcom BLE Protocol Deep Dive](../../docs/10-domain/dexcom-ble-protocol-deep-dive.md) for comprehensive protocol specification.

### BLE Service and Characteristic UUIDs

| Purpose | UUID | Description |
|---------|------|-------------|
| **Advertisement** | `FEBC` | Dexcom advertisement service |
| **CGM Data Service** | `F8083532-849E-531C-C594-30F1F86A4EA5` | Main data service |
| **Communication** | `F8083533-849E-531C-C594-30F1F86A4EA5` | Status updates (Read/Notify) |
| **Control** | `F8083534-849E-531C-C594-30F1F86A4EA5` | Command exchange (Write/Indicate) |
| **Authentication** | `F8083535-849E-531C-C594-30F1F86A4EA5` | Auth handshake (Write/Indicate) |
| **Backfill** | `F8083536-849E-531C-C594-30F1F86A4EA5` | Historical data (Read/Write/Notify) |
| **J-PAKE (G7)** | `F8083538-849E-531C-C594-30F1F86A4EA5` | G7 J-PAKE exchange |

### G6 vs G7 Protocol Differences

| Aspect | G6 | G7 |
|--------|----|----|
| **Authentication** | AES-128-ECB challenge-response | J-PAKE (Password Authenticated Key Exchange) |
| **Connection Slots** | 2 (xDrip + Dexcom app) | 1 (exclusive) |
| **Glucose Opcode** | 0x30/0x31 or 0x4E/0x4F | 0x4E/0x4F only |
| **Calibration** | Factory + user calibration | Factory only |
| **Warmup** | 2 hours | 27 minutes |
| **Backfill Opcode** | 0x50/0x51 | 0x59 |

### Core Message Opcodes

| Category | Opcode (Tx/Rx) | Purpose |
|----------|----------------|---------|
| **Auth Request** | 0x01/0x03 | Initiate authentication |
| **Auth Challenge** | 0x04/0x05 | Complete authentication |
| **Keep Alive** | 0x06 | Maintain connection |
| **Bond Request** | 0x07/0x08 | Request Bluetooth bonding |
| **Disconnect** | 0x09 | Graceful disconnect |
| **Battery Status** | 0x22/0x23 | Battery voltage and runtime |
| **Transmitter Time** | 0x24/0x25 | Current time and session start |
| **Session Start** | 0x26/0x27 | Start sensor session |
| **Session Stop** | 0x28/0x29 | Stop sensor session |
| **Glucose (G5)** | 0x30/0x31 | Request glucose reading |
| **Calibration Data** | 0x32/0x33 | Get/set calibration |
| **Calibrate Glucose** | 0x34/0x35 | Submit calibration value |
| **Reset** | 0x42/0x43 | Reset transmitter |
| **Version (extended)** | 0x4A/0x4B | Get transmitter version |
| **Glucose (G6/G7)** | 0x4E/0x4F | Request glucose reading |
| **Backfill (G6)** | 0x50/0x51 | Request historical data |
| **Version Extended (G7)** | 0x52/0x53 | Get extended version |
| **Backfill Finished (G7)** | 0x59 | Backfill complete |

### Glucose Message Structure Comparison

| Field | G6 (0x31/0x4F) | G7 (0x4E) |
|-------|----------------|-----------|
| **Opcode** | Byte 0 | Byte 0 |
| **Status** | Byte 1 | Byte 1 |
| **Timestamp** | Bytes 6-9 (submessage) | Bytes 2-5 |
| **Sequence** | Bytes 2-5 | Bytes 6-7 |
| **Age** | N/A | Bytes 10-11 |
| **Glucose** | Bytes 10-11 (12-bit) | Bytes 12-13 (12-bit) |
| **Algorithm State** | Byte 12 | Byte 14 |
| **Trend** | Byte 13 (signed) | Byte 15 (signed, /10) |
| **Predicted** | N/A | Bytes 16-17 |

### Authentication Hash Function

| System | Implementation | Key Derivation |
|--------|----------------|----------------|
| **CGMBLEKit** | `aes128ecb_encrypt(challenge+challenge, key)` | `key = "00" + transmitterID + "00" + transmitterID` |
| **xdrip-js** | `crypto.createCipheriv('aes-128-ecb', key, '')` | Same as above |
| **DiaBLE** | `doubleChallenge.aes128Encrypt(keyData: cryptKey)` | Same as above |

### CRC-16 Implementation

All systems use **CRC-16 CCITT (XModem)**:
- Polynomial: `0x1021`
- Initial value: `0x0000`
- Position: Last 2 bytes of message (little-endian)

### Transmitter ID Formats

| Transmitter | ID Format | Example | Detection |
|-------------|-----------|---------|-----------|
| **G5** | 5 alphanumeric | `40XXX` | Length == 5 |
| **G6** | 6 alphanumeric, starts with 8 | `80XXXX` | `id[0] == '8'` |
| **G6+** | 6 alphanumeric, 8G/8H/8J/8L/8R | `8GXXXX` | Prefix check |
| **G7** | DXCM + suffix | `DXCMXX` | Advertisement name |

### Calibration/Algorithm State Mapping

| State Value | G6 Name | G7 Name | Reliable Glucose |
|-------------|---------|---------|------------------|
| 0x01 | Stopped | Stopped | No |
| 0x02 | Warmup | Warmup | No |
| 0x06 | OK | OK | Yes |
| 0x07 | NeedCalibration7 | NeedsCalibration | G6: Yes, G7: No |
| 0x0F | SessionFailure15 | SessionExpired | No |
| 0x12 | QuestionMarks | TemporarySensorIssue | No |

**Gap Reference**: GAP-BLE-001 (J-PAKE spec), GAP-BLE-002 (certificate chain)

---

## Carb Absorption Models

> **See Also**: [Carb Absorption Deep Dive](../../docs/10-domain/carb-absorption-deep-dive.md) for comprehensive mathematical formulas and source code citations.

### Absorption Curve Types

| Model Type | Loop | oref0 | AAPS | Trio |
|------------|------|-------|------|------|
| **Parabolic (Scheiner)** | `ParabolicAbsorption` | N/A | N/A | `ParabolicAbsorption` |
| **Linear** | `LinearAbsorption` | Default (implicit) | Default (implicit) | `LinearAbsorption` |
| **PiecewiseLinear (Trapezoid)** | `PiecewiseLinearAbsorption` (default) | N/A | N/A | `PiecewiseLinearAbsorption` (default) |
| **Extended Carbs (eCarbs)** | N/A | N/A | `duration` field on `Carbs` entity | N/A |

### COB Calculation Approach

| Aspect | Loop/Trio | oref0/AAPS |
|--------|-----------|------------|
| **Philosophy** | Model-first with dynamic adaptation | Observation-first with min floor |
| **Absorption Tracking** | Per-entry with `AbsorbedCarbValue` | Global deviation-based inference |
| **Dynamic Adaptation** | Yes (`observedTimeline`) | No (linear decay) |
| **Minimum Rate** | Clamping logic | `min_5m_carbimpact` (3 mg/dL/5m) |

### Key Parameters

| Parameter | Loop | oref0 | AAPS | Source (Line) |
|-----------|------|-------|------|---------------|
| **Default Absorption Time** | 3 hours | Profile-based | Profile-based | `CarbMath.swift#L14` |
| **Max Absorption Time** | 10 hours | 6 hours (carb window) | 6 hours | `CarbMath.swift#L13`, `total.js#L49` |
| **Effect Delay** | 10 minutes | None | None | `CarbMath.swift#L16` |
| **Initial Overrun Factor** | 1.5x | N/A | N/A | `CarbMath.swift#L15` |
| **Max COB Cap** | None | 120g (configurable) | 120g | `total.js#L108` |
| **Min Carb Impact** | N/A | 3 mg/dL/5m (8 for low-carb) | 3 mg/dL/5m | `cob.js#L190` |
| **Max Absorption Rate** | N/A | 30 g/h | 30 g/h | `determine-basal.js#L480` |

**Source Files**:
- Loop: `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/CarbMath.swift`
- oref0: `externals/oref0/lib/meal/total.js`, `externals/oref0/lib/determine-basal/cob.js`, `externals/oref0/lib/determine-basal/determine-basal.js`

### Carb Entry Field Comparison

| Field | Loop | oref0 | AAPS | Nightscout |
|-------|------|-------|------|------------|
| **Amount** | `quantity` (HKQuantity) | `carbs` | `amount` | `carbs` |
| **Absorption Time** | `absorptionTime` (seconds) | N/A | N/A | `absorptionTime` (minutes) |
| **Duration (eCarbs)** | N/A | N/A | `duration` (milliseconds) | `duration` (minutes) |
| **Start Date** | `startDate` | `timestamp` | `timestamp` | `created_at` |

**Unit Conversion Notes**:
- Loop/Trio absorption time: **seconds**
- Nightscout absorption time: **minutes** (GAP-CARB-001)
- AAPS duration: **milliseconds**
- Nightscout duration: **minutes** (GAP-CARB-002)

### UAM (Unannounced Meals) Handling

| Mechanism | Loop | oref0 | AAPS | Trio |
|-----------|------|-------|------|------|
| **Detection** | Retrospective Correction (implicit) | Explicit UAM curve | Explicit UAM | Both (RC + UAM) |
| **Prediction Curve** | Single combined | Separate `UAMpredBGs` | Separate | Separate |
| **Decay Model** | Via RC adjustment | Linear decay (3h max) | Linear decay | Linear decay |
| **Enable Setting** | Always via RC | `enableUAM` profile flag | `enableUAM` | `enableUAM` |

### Glucose Effect Calculation

| System | Formula | Source |
|--------|---------|--------|
| **Loop** | `glucoseEffect = ISF / CR * absorbedCarbs` | `CarbMath.swift#L279-L288` |
| **oref0** | `csf = sens / carb_ratio; effect = csf * carbs` | `determine-basal.js#L477` |
| **AAPS** | Same as oref0 (JS port) | oref0 JS execution |

### Source Files Reference

| System | Key Carb Absorption Files |
|--------|---------------------------|
| **Loop** | `LoopKit/CarbKit/CarbMath.swift`, `CarbStatus.swift`, `AbsorbedCarbValue.swift` |
| **oref0** | `lib/determine-basal/cob.js`, `lib/meal/total.js`, `lib/determine-basal/determine-basal.js` |
| **AAPS** | `database/entities/Carbs.kt`, `core/data/iob/CobInfo.kt` |
| **Trio** | Same as Loop (`LoopKit/CarbKit/*`) + oref0 JS |

**Gap Reference**: GAP-CARB-001 through GAP-CARB-005

---

## Libre CGM Protocol Models

> **See Also**: [Libre Protocol Deep Dive](../../docs/10-domain/libre-protocol-deep-dive.md) for comprehensive protocol specification.

### Sensor Type Detection (from PatchInfo)

| PatchInfo[0] | Sensor Type | Family | Security Generation |
|--------------|-------------|--------|---------------------|
| 0xDF, 0xA2 | Libre 1 | 0 | 0 |
| 0xE5, 0xE6 | Libre US 14-day | 0 | 1 |
| 0x70 | Libre Pro/H | 1 | 0 |
| 0x9D, 0xC5 | Libre 2 EU | 3 | 1 |
| 0xC6, 0x7F | Libre 2+ EU | 3 | 1 |
| 0x76, 0x2B, 0x2C | Libre 2 Gen2 (US) | 3 | 2 |
| 24-byte patchInfo | Libre 3 | 4 | 3 |

### Sensor Families

| Family | Raw Value | Sensors | IC Manufacturer |
|--------|-----------|---------|-----------------|
| libre1 | 0 | Libre 1 | TI (0x07) |
| librePro | 1 | Libre Pro/H | TI (0x07) |
| libre2 | 3 | Libre 2, 2+, Gen2 | TI (0x07) |
| libre3 | 4 | Libre 3, 3+ | Abbott (0x7a) |
| libreSense | 7 | Libre Sense (wellness) | TI (0x07) |
| lingo | 9 | Lingo (wellness) | Abbott (0x7a) |

### FRAM Memory Layout (344 bytes) - Libre 1/2/2+/Gen2 Only

> **Note**: FRAM applies only to NFC-based sensors. Libre 3 is BLE-only and does not use FRAM.

| Region | Offset | Size | Key Fields |
|--------|--------|------|------------|
| Header | 0-23 | 24 bytes | CRC (0-1), State (4), Error Code (6), Failure Age (7-8) |
| Body | 24-319 | 296 bytes | CRC (24-25), Trend Index (26), History Index (27), Trend (28-123), History (124-315), Age (316-317) |
| Footer | 320-343 | 24 bytes | CRC (320-321), Region (323), Max Life (326-327), Calibration (328+) |

### Glucose Reading Structure (6 bytes)

| Bit Offset | Bit Count | Field | Notes |
|------------|-----------|-------|-------|
| 0 | 14 | rawValue | Raw glucose value |
| 14 | 9 | quality | Data quality (error bits) |
| 23 | 2 | qualityFlags | Additional flags |
| 25 | 1 | hasError | Error indicator |
| 26 | 12 | rawTemperature | Temperature reading (<<2) |
| 38 | 9 | tempAdjustment | Temperature adjustment (<<2) |
| 47 | 1 | negativeAdj | Sign bit for adjustment |

### NFC Commands

| Code | Name | Description |
|------|------|-------------|
| 0xA1 | Universal Prefix | Execute subcommand |
| 0xB0 | Read Block | Read single memory block |
| 0xB3 | Read Blocks | Read multiple blocks |

### NFC Subcommands (via 0xA1)

| Subcode | Name | Description |
|---------|------|-------------|
| 0x1A | Unlock | Read FRAM in clear |
| 0x1B | Activate | Activate sensor |
| 0x1E | Enable Streaming | Enable BLE (Libre 2) |
| 0x1F | Get Session Info | Gen2 session info |
| 0x20 | Read Challenge | Gen2 challenge |
| 0x21 | Read Blocks | Gen2 FRAM read |
| 0x22 | Read Attribute | Gen2 sensor state |

### Libre 2 Key Derivation Constants

> **Note**: These are derivation constants, NOT direct encryption keys. Actual keys are derived per-sensor using the 8-byte sensor UID and 6-byte patchInfo as inputs. See [Libre Protocol Deep Dive](../../docs/10-domain/libre-protocol-deep-dive.md#libre-2-encryption) for full algorithm.

| Constant | Value | Purpose |
|----------|-------|---------|
| key[0] | 0xA0C5 | XOR derivation constant |
| key[1] | 0x6860 | XOR derivation constant |
| key[3] | 0x14C6 | Initial XOR derivation |
| secret | 0x1b6a | Default secret for key derivation |

### BLE UUIDs

| System | Service UUID | Key Characteristic UUIDs |
|--------|--------------|--------------------------|
| Libre 2 | FDE3 | F001 (login), F002 (data) |
| Libre 3 | Base: 0898xxxx-EF89-11E9-81B4-2A2AE2DBCCE4 | 10CC (data), 1338 (control), 1482 (status), 177A (glucose), 2198 (security), 22CE (challenge), 23FA (cert) |

> **Note**: Libre 3 uses 13+ characteristics. See [Libre Protocol Deep Dive - BLE Service and Characteristic UUIDs](../../docs/10-domain/libre-protocol-deep-dive.md#ble-service-and-characteristic-uuids) for complete list with full UUIDs.

### Libre 3 BLE Characteristics

| UUID Suffix | Name | Purpose |
|-------------|------|---------|
| 10CC | data | Data service |
| 1338 | patchControl | Send commands |
| 1482 | patchStatus | Sensor status |
| 177A | oneMinuteReading | Current glucose |
| 195A | historicalData | Backfill history |
| 1AB8 | clinicalData | Clinical backfill |
| 1BEE | eventLog | Event logging |
| 1D24 | factoryData | Factory data |
| 2198 | securityCommands | Security protocol |
| 22CE | challengeData | Auth challenge |
| 23FA | certificateData | Certificates |

### Transmitter Bridge Protocols

| Device | Service UUID | Start Command | Data Format |
|--------|--------------|---------------|-------------|
| MiaoMiao | 6E400001-... (Nordic UART) | 0xF0 | 363+ bytes (18 header + 344 FRAM + patchInfo) |
| Bubble | 6E400001-... (Nordic UART) | [0x00, 0xA0, interval] | 8 header + 344 FRAM |
| Blucon | Proprietary | Device-specific | Wrapped FRAM |
| Atom | 6E400001-... (Nordic UART) | Similar to Bubble | Wrapped FRAM |

### Cross-Implementation Comparison

| Feature | DiaBLE | LibreTransmitter | xDrip4iOS | xDrip+ Android |
|---------|--------|------------------|-----------|----------------|
| Libre 1 NFC | ✅ | ✅ | ✅ | ✅ |
| Libre 2 NFC | ✅ | ✅ | ✅ | ✅ |
| Libre 2 BLE | ✅ | ✅ | ✅ | ✅ |
| Libre 2 Gen2 | ⚠️ | ❌ | ⚠️ | ✅ |
| Libre 3 | ⚠️ | ❌ | ❌ | ⚠️ |
| Bridge Transmitters | Limited | MiaoMiao, Bubble | MiaoMiao, Bubble, etc. | All |

**Source Files**:
- DiaBLE: `externals/DiaBLE/DiaBLE/Libre.swift`, `Libre2.swift`, `Libre3.swift`
- LibreTransmitter: `externals/LoopWorkspace/LibreTransmitter/LibreSensor/`
- xDrip4iOS: `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/Libre/`

**Gap Reference**: GAP-LIBRE-001 through GAP-LIBRE-006

---

## LoopCaregiver Remote 2.0 Models

> **See Also**: [LoopCaregiver Remote Commands](../loopcaregiver/remote-commands.md), [LoopCaregiver Authentication](../loopcaregiver/authentication.md)

### Remote Command Types

| Action Type | LoopCaregiver | Loop (Receiver) | Description |
|-------------|---------------|-----------------|-------------|
| `bolusEntry` | `BolusAction(amountInUnits)` | `BolusRemoteNotification` | Remote insulin delivery |
| `carbsEntry` | `CarbAction(amountInGrams, absorptionTime?, startDate?)` | `CarbEntryRemoteNotification` | Remote carb entry |
| `temporaryScheduleOverride` | `OverrideAction(name, durationTime?, remoteAddress)` | `OverrideRemoteNotification` | Activate override by name |
| `cancelTemporaryOverride` | `OverrideCancelAction(remoteAddress)` | `OverrideCancelRemoteNotification` | Cancel active override |
| `autobolus` | `AutobolusAction(active)` | Remote 2.0 only | Toggle autobolus on/off |
| `closedLoop` | `ClosedLoopAction(active)` | Remote 2.0 only | Toggle closed loop on/off |

### Remote Command Status States

| LoopCaregiver State | Nightscout State | Description |
|---------------------|------------------|-------------|
| `.pending` | `Pending` | Command uploaded, awaiting Loop pickup |
| `.inProgress` | `InProgress` | Loop received, executing |
| `.success` | `Success` | Command completed successfully |
| `.error(message)` | `Error` | Execution failed with error message |

### Authentication Components

| Component | LoopCaregiver | Loop | Description |
|-----------|---------------|------|-------------|
| OTP Secret | `NightscoutCredentials.otpURL` | `OTPSecretStore` (Keychain) | Shared TOTP secret |
| OTP Manager | `OTPManager` | `OTPManager` | Generates/validates TOTP codes |
| OTP Parameters | SHA1, 6 digits, 30s | SHA1, 6 digits, 30s | Standard TOTP (RFC 6238) |
| Credential Service | `NightscoutCredentialService` | N/A | Wraps OTP with auto-refresh |

### QR Code Deep Link Format

| Field | Query Parameter | Required | Description |
|-------|-----------------|----------|-------------|
| Looper Name | `name` | Yes | Display name for the looper |
| Nightscout URL | `nsURL` | Yes | URL-encoded Nightscout server URL |
| API Secret | `secretKey` | Yes | Nightscout API_SECRET |
| OTP URL | `otpURL` | Yes | URL-encoded otpauth:// URI |
| Creation Date | `createdDate` | No | For watch configuration uniqueness |

**Deep Link URL Format**:
```
caregiver://createLooper?name={name}&secretKey={api_secret}&nsURL={ns_url_encoded}&otpURL={otp_url_encoded}
```

**OTP URL Format** (Standard TOTP):
```
otpauth://totp/{label}?algorithm=SHA1&digits=6&issuer=Loop&period=30&secret={base32_secret}
```

### Remote 2.0 vs 1.0 Comparison (LoopCaregiver)

| Aspect | Remote 1.0 | Remote 2.0 |
|--------|------------|------------|
| **Protocol** | Direct OTP in request | Command payload with status |
| **OTP Inclusion** | Query parameter | `otp` field in payload |
| **Status Tracking** | None | Pending → InProgress → Success/Error |
| **Command Types** | 4 (bolus, carbs, override, cancel) | 6 (adds autobolus, closedLoop) |
| **Version Field** | None | `version: "2.0"` |
| **Enable Flag** | N/A | `settings.remoteCommands2Enabled` |

### Caregiver Safety Features

| Feature | Implementation | Value |
|---------|----------------|-------|
| Recommended Bolus Expiry | `calculateValidRecommendedBolus()` | 7 minutes |
| Post-Bolus Rejection | Compare bolus timestamp vs deviceStatus | Reject if bolus after recommendation |
| Credential Validation | `checkAuth()` before storing | API call to Nightscout |
| OTP Refresh | Timer-based (1 second) | Always fresh code |

### Cross-App Command Comparison

| Feature | LoopCaregiver | LoopFollow | Nightguard | Trio Caregiver* |
|---------|---------------|------------|------------|-----------------|
| Remote Bolus | ✅ | ❌ | ❌ | ✅ |
| Remote Carbs | ✅ | ❌ | ❌ | ✅ |
| Remote Override | ✅ | ✅ | ❌ | ✅ |
| Cancel Override | ✅ | ✅ | ❌ | ✅ |
| Autobolus Toggle | ✅ | ❌ | ❌ | N/A |
| Closed Loop Toggle | ✅ | ❌ | ❌ | N/A |
| OTP Handling | Automatic | Manual | N/A | N/A (encrypted) |
| Status Tracking | ✅ | ❌ | N/A | ✅ |

*Trio uses encryption rather than OTP

**Source Files**:
- `loopcaregiver:LoopCaregiverKit/Sources/.../Nightscout/OTPManager.swift` - TOTP generation
- `loopcaregiver:LoopCaregiverKit/Sources/.../Nightscout/NightscoutDataSource.swift` - Command upload
- `loopcaregiver:LoopCaregiverKit/Sources/.../Models/DeepLinkParser.swift` - QR code parsing
- `loopcaregiver:LoopCaregiverKit/Sources/.../Models/RemoteCommands/Action.swift` - Action types

**Gap Reference**: GAP-REMOTE-005, GAP-REMOTE-006

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Added LoopCaregiver Remote 2.0 Models section with command types, status states, auth components, deep links |
| 2026-01-17 | Agent | Added Libre CGM Protocol Models section with sensor types, FRAM layout, encryption, BLE, transmitter bridges |
| 2026-01-17 | Agent | Added Carb Absorption Models section with curve types, COB calculation, parameters, UAM handling |
| 2026-01-17 | Agent | Added Dexcom BLE Protocol Models section with UUIDs, opcodes, message structures, authentication |
| 2026-01-17 | Agent | Added Pump Communication Models section with interface, commands, protocols, and state machines |
| 2026-01-17 | Agent | Added API Version Models section with v1/v3 comparison |
| 2026-01-17 | Agent | Added Remote Command Security Models section with cross-system comparison |
| 2026-01-16 | Agent | Integrated xDrip+ (Android) into terminology matrix - events, sync identity, actor identity, device events, code references |
| 2026-01-16 | Agent | Added oref0-specific concepts (algorithm components, prediction curves, carb model, SMB params, shared IOB formula) |
| 2026-01-16 | Agent | Added Trio-specific concepts (oref2 variables, remote commands, overrides, insulin curves, dynamic ISF) |
| 2026-01-16 | Agent | Added algorithm/controller concepts, safety constraints, pump commands, insulin models, loop states |
| 2026-01-16 | Agent | Initial cross-project terminology matrix |
