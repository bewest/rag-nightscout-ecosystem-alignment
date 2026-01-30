# Aid Algorithms Gaps

Domain-specific gaps extracted from gaps.md.
See [gaps.md](gaps.md) for the index.

---

### GAP-ALG-001: No cross-project algorithm test vectors

**Scenario**: Algorithm validation across implementations

**Description**: Each AID project (oref0, AAPS, Loop, Trio) maintains isolated test fixtures with incompatible formats. No mechanism exists to validate behavioral consistency across implementations.

**Evidence**:
- oref0: `tests/determine-basal.test.js` with inline fixtures
- AAPS: `app/src/androidTest/assets/results/*.json` (~85 files)
- Loop: `LoopKitTests/Fixtures/` scattered JSON files

**Impact**:
- Algorithm differences may cause dosing inconsistencies for users switching between apps
- No automated regression detection for cross-project behavioral drift
- Safety-critical algorithm changes may go unvalidated

**Possible Solutions**:
1. ✅ Implement conformance vector format (DONE: `conformance-vector-v1.json`)
2. ✅ Extract vectors from AAPS (DONE: 85 vectors extracted)
3. ✅ oref0 runner complete (DONE: 26/85 pass, reveals AAPS drift)
4. 🔄 AAPS Kotlin runner (IN PROGRESS)
5. Loop Swift runner (TODO)
6. CI integration to detect behavioral drift

**Status**: Substantially addressed - oref0 runner reveals 69% divergence from AAPS

**Related**:
- [Algorithm Conformance Suite Proposal](../docs/sdqctl-proposals/algorithm-conformance-suite.md)
- `conformance/schemas/conformance-vector-v1.json`
- `conformance/runners/oref0-runner.js`
- `conformance/results/oref0-results.json`

---

---

### GAP-ALG-002: oref0 vs AAPS behavioral drift

**Scenario**: AAPS Kotlin vs upstream oref0 JavaScript

**Description**: AAPS Kotlin implementation has diverged from upstream oref0 JavaScript. The ReplayApsResultsTest compares JS vs KT within AAPS but not against upstream oref0.

**Evidence**:
- oref0-runner.js: 26/85 AAPS vectors pass against upstream oref0 (31%)
- Key differences:
  - eventualBG calculation differs significantly (e.g., 146 vs 80 in TV-017)
  - AAPS iob_data includes iobWithZeroTemp projections; oref0 logs "Problem with iobArray"
  - AAPS modifies IOB array handling for SMB prediction

**Impact**:
- AAPS users experience different dosing than OpenAPS rig users with identical settings
- 69% of test scenarios produce different outputs
- No clear compatibility guarantees between implementations

**Possible Solutions**:
1. ✅ Create shared test vectors (DONE: 85 vectors)
2. ✅ Run AAPS vectors against upstream oref0 (DONE: 26/85 pass)
3. 🔄 Document specific behavioral differences
4. Propose harmonization where clinically appropriate

**Status**: Quantified - 69% divergence measured

**Related**:
- [Algorithm Conformance Suite Proposal](../docs/sdqctl-proposals/algorithm-conformance-suite.md)
- `conformance/results/oref0-results.json` - detailed failure analysis

---

---

### GAP-ALG-003: Loop algorithm incomparable to oref

**Scenario**: Loop vs oref dosing comparison

**Description**: Loop uses fundamentally different prediction model (single combined curve vs 4 separate curves). Direct output comparison is not meaningful without semantic mapping.

**Evidence**:
- oref0: 4 curves (IOB, COB, UAM, ZT) with min() logic
- Loop: Combined prediction curve with retrospective correction
- Different insulin models (exponential vs Walsh options)

**Impact**:
- Users cannot expect identical dosing behavior when switching between Loop and oref-based systems
- No mechanism to validate "equivalent safety" across models

**Possible Solutions**:
1. Define semantic equivalence criteria ("both recommend increased basal")
2. Create scenario-based assertions rather than exact value matching
3. Document expected behavioral differences for users

**Status**: Proposal created

**Related**:
- [Algorithm Conformance Suite Proposal](../docs/sdqctl-proposals/algorithm-conformance-suite.md)
- [Prediction Arrays Comparison](../docs/10-domain/prediction-arrays-comparison.md)

---

## API Layer Gaps (2026-01-29 Audit)

---

### GAP-CARB-001: Incompatible COB Semantics

**Description**: Loop's predictive curve-based COB differs fundamentally from oref0's deviation-inferred COB, making cross-system comparisons invalid.

**Affected Systems**: Loop, AAPS, Trio, oref0, Nightscout

**Impact**:
- Nightscout displays COB without model context
- Users switching systems see different COB values for same meal
- Reports aggregate incompatible metrics
- Cannot compare algorithm performance across systems

**Example**:
- Same meal: Loop COB = 45g (curve projection), oref0 COB = 38g (deviation-inferred)

**Remediation**: Nightscout should store and display COB with model type annotation in devicestatus schema.

---

---

### GAP-CARB-002: No Standard Carb Absorption Data Format

**Description**: Each AID system stores carb absorption data in incompatible formats, preventing data interchange and replay.

**Affected Systems**: Loop, AAPS, Trio, oref0

**Storage Formats**:
| System | Format |
|--------|--------|
| Loop | Per-entry absorption timeline array |
| oref0 | Aggregate mealCOB scalar |
| AAPS | autosensData.cob with 5-min deltas |
| Trio | meal_data.mealCOB scalar |

**Impact**:
- Cannot replay absorption data across systems
- No standard for test vectors
- Limits algorithm conformance testing

**Remediation**: Define standard absorption event format with timeline, model type, and per-entry tracking.

---

---

### GAP-CARB-003: UAM Detection Variance

**Description**: Unannounced Meal (UAM) detection algorithms differ significantly across systems, causing inconsistent dosing behavior.

**Affected Systems**: Loop, AAPS, Trio, oref0

**Detection Methods**:
| System | UAM Approach |
|--------|--------------|
| Loop | Retrospective correction (implicit via observed absorption) |
| oref0 | Explicit deviation slope analysis with 60m delay |
| AAPS | enableUAM constraint check |
| Trio | enableUAM setting (oref0-derived) |

**Impact**:
- Users experience different dosing behavior with same settings
- UAM sensitivity not portable across systems
- Documentation doesn't explain behavioral differences

**Remediation**: Document UAM behavior differences prominently in user guides and Nightscout UI.

---

---

### GAP-CARB-004: min_5m_carbimpact Variance

**Scenario**: COB Decay Rate Comparison

**Description**: The `min_5m_carbimpact` parameter in oref0/AAPS defaults to 3 mg/dL/5m for normal diets but 8 mg/dL/5m for low-carb diets. This significantly affects how quickly COB decays when no absorption is detected.

**Source**: [oref0 cob.js#L189-L194](../externals/oref0/lib/determine-basal/cob.js)

**Impact**:
- Same carb entry produces different COB timelines with different min_5m_carbimpact settings
- "Zombie carbs" (COB that never depletes) behavior differs
- Cross-user comparison invalid without knowing this setting

**Possible Solutions**:
1. Include `min_5m_carbimpact` in devicestatus
2. Standardize on a single default across configurations
3. Document as critical comparison caveat

**Status**: Under discussion

---

---

### GAP-CARB-005: COB Maximum Limits Differ

**Scenario**: Large Meal Handling

**Description**: oref0/AAPS enforce a hard `maxCOB` cap (default 120g), while Loop has no such limit. This means the same large meal (e.g., 150g carbs) produces different COB values.

**Source**: 
- [oref0 total.js#L108](../externals/oref0/lib/meal/total.js)
- Loop has no equivalent cap

**Impact**:
- Large carb entries produce different COB in different systems
- Safety implications for high-carb meals
- Users unaware of capping may be confused by COB discrepancies

**Possible Solutions**:
1. Loop adds configurable maxCOB option
2. oref0 makes maxCOB configurable with no-limit option
3. Document as known difference with safety implications

**Status**: Under discussion

---

## Libre CGM Protocol Gaps

---

### GAP-INS-001: Insulin Model Metadata Not Synced to Nightscout

**Scenario**: Historical IOB reconstruction, algorithm debugging

**Description**: When treatments are uploaded to Nightscout, no metadata about the insulin model used for IOB calculation is included. Specifically missing:
- Curve type (exponential, bilinear, linear trapezoid)
- Peak time parameter
- DIA setting at time of calculation
- Insulin brand/type

**Source Evidence**:
- Loop uploads bolus with `insulinType?.brandName` but not curve parameters
- oref0/Trio upload bolus without any model metadata
- AAPS stores `insulinConfiguration` locally but doesn't upload to Nightscout

**Impact**:
- Cannot reproduce historical IOB calculations
- Cannot determine why predictions differed from outcomes
- Algorithm debugging requires access to device settings
- Research use cases blocked

**Possible Solutions**:
1. Add `insulinModel` object to treatment schema: `{curve, peak, dia}`
2. Include model metadata in devicestatus uploads
3. Create separate `algorithmSettings` collection

**Status**: Under discussion

**Related**:
- [Insulin Curves Deep Dive](../docs/10-domain/insulin-curves-deep-dive.md)
- REQ-INS-005

---

---

### GAP-INS-002: No Standardized Multi-Insulin Representation

**Scenario**: MDI users tracking multiple insulin types, smart pen integration

**Description**: xDrip+ uniquely supports tracking multiple insulin types per treatment via `insulinJSON` field containing an array of `InsulinInjection` objects. This format is xDrip+-specific and not recognized by other systems or Nightscout.

**Source Evidence**:
```java
// xDrip+ Treatments.java
@Column(name = "insulinJSON")
public String insulinJSON;  // JSON array of {profileName, units}
```

Nightscout treatments only support single `insulin` field.

**Impact**:
- MDI users cannot track rapid + basal insulin in standard format
- Smart pen data (InPen, NovoPen) loses insulin type on upload
- IOB calculations must fall back to single insulin model
- Cross-system data correlation loses insulin type breakdown

**Possible Solutions**:
1. Add Nightscout schema support for multi-insulin treatments
2. Standardize xDrip+ `insulinJSON` format for adoption
3. Use separate treatment entries per insulin type

**Status**: Under discussion

**Related**:
- [xDrip+ Insulin Management](../mapping/xdrip-android/insulin-management.md)

---

---

### GAP-INS-003: Peak Time Customization Not Captured in Treatments

**Scenario**: Custom insulin tuning, historical analysis

**Description**: oref0 and AAPS support custom peak times via `useCustomPeakTime` and `insulinPeakTime` profile settings. However, when treatments are recorded, the peak time used for IOB calculation is not captured.

**Source Evidence**:
```javascript
// oref0:lib/iob/calculate.js
if (profile.useCustomPeakTime === true && profile.insulinPeakTime !== undefined) {
    peak = profile.insulinPeakTime;  // Custom peak, but not stored in treatment
}
```

**Impact**:
- Cannot reconstruct IOB with correct curve shape
- Profile changes retroactively affect historical analysis
- Custom tuning decisions not documented

**Possible Solutions**:
1. Include `insulinPeakAtDose` in treatment metadata
2. Capture profile snapshot at treatment time
3. Store peak time in devicestatus algorithm output

**Status**: Under discussion

**Related**:
- REQ-INS-003
- [oref0 Insulin Math](../mapping/oref0/insulin-math.md)

---

---

### GAP-INS-004: xDrip+ Linear Trapezoid Model Incompatible with AID Exponential

**Scenario**: Cross-system IOB comparison, data portability

**Description**: xDrip+ uses a linear trapezoid model for insulin activity, while all AID systems (Loop, oref0, AAPS, Trio) use the exponential model. These models produce different IOB decay curves from identical dose history.

**Source Evidence**:
- xDrip+: `LinearTrapezoidInsulin.java` uses onset/peak/duration with linear segments
- AID systems: Exponential decay with `tau`, `a`, `S` parameters from shared formula

**Impact**:
- xDrip+ IOB values differ from AAPS IOB for same user
- Smart pen data imported to AID system uses different curve
- Cannot directly compare IOB across CGM app vs AID controller

**Possible Solutions**:
1. xDrip+ adds exponential model option for AID compatibility
2. Document conversion factors between models
3. Accept limitation and document for users

**Status**: Under discussion (architectural difference, likely won't converge)

**Related**:
- [Insulin Curves Deep Dive](../docs/10-domain/insulin-curves-deep-dive.md)
- [xDrip+ Insulin Management](../mapping/xdrip-android/insulin-management.md)

---

## Pump Communication Gaps

---

### GAP-INSULIN-001: Multi-Insulin API Not Standardized

**Status**: ✅ Addressed in specification

**Description**: Multiple insulin profile support (names, curves, colors) exists in PR#8261 and is already used by xDrip+ and nightscout-reporter, but not merged into Nightscout core.

**Affected Systems**: xDrip+, nightscout-reporter, Loop, Trio, AAPS

**Impact**:
- No standard API for insulin model definitions
- IOB calculations cannot reference user-defined curves
- Insulin type not synchronized across systems

**Remediation**: ✅ OpenAPI spec created: `specs/openapi/aid-insulin-2025.yaml` (576 lines)

**Specification Coverage**:
- 5 endpoints: CRUD + bolus/basal active
- Insulin schema with DIA, peak, curve, concentration
- Cross-project field mapping table
- 4 conformance scenarios
- Bug noted: PR#8261 /basal endpoint calls bolus() function

---

---

### GAP-OREF-001: No oref0 Package Published to npm

**Scenario**: Integrating oref0 algorithm into other Node.js projects

**Description**: oref0 is not published as an npm package. Users must clone the repo and run from source. There's no `npm install oref0`.

**Source**: `externals/oref0/package.json` - not published to npm registry

**Impact**:
- Makes integration with other Node.js projects difficult
- Each project (AAPS, Trio) re-implements in native language
- No versioned releases for dependency management

**Status**: Design choice - algorithm evolved into native ports

---

---

### GAP-OREF-002: openaps Python Package Unmaintained

**Scenario**: Adding new pump or CGM support to openaps toolkit

**Description**: The openaps Python package hasn't been updated significantly; focus shifted to AndroidAPS and Loop ecosystems. New device support goes to AAPS/Loop first.

**Source**: `externals/openaps/` - limited recent commits

**Impact**:
- New pump/CGM support goes to AAPS first
- openaps/oref0 rig has limited device support
- Legacy Medtronic-focused

**Status**: Expected - ecosystem evolved to mobile apps

---

---

### GAP-OREF-003: oref0 vs oref1 Distinction Unclear

**Scenario**: Understanding which features are oref0 vs oref1 when porting

**Description**: oref1 added SMB (Super Micro Bolus) support but the code is in the same repository with no clear versioning or feature flags to distinguish oref0 vs oref1 capabilities.

**Source**: `externals/oref0/lib/determine-basal/determine-basal.js` - SMB logic mixed with base algorithm

**Impact**:
- Difficult to know which features are oref0 vs oref1
- Porting to other systems requires understanding implicit feature sets
- Documentation often conflates the two

**Possible Solutions**:
1. Document oref0 vs oref1 feature matrix
2. Add feature flags in algorithm

**Status**: Documentation gap

---

## tconnectsync Gaps

---

### GAP-PRED-001: Prediction Array Truncation Behavior Undocumented

**Scenario**: OpenAPS/AAPS devicestatus uploads with large prediction arrays

**Description**: Nightscout may truncate prediction arrays based on `PREDICTIONS_MAX_SIZE` environment variable. This behavior is server-configurable and varies between installations. Clients have no way to know if their predictions were truncated.

**Source**: `cgm-remote-monitor:tests/api.partial-failures.test.js:402-550`
```javascript
// SPEC: When PREDICTIONS_MAX_SIZE env var is set, prediction arrays
// are truncated to that size
// SPEC: Setting PREDICTIONS_MAX_SIZE=0 explicitly disables truncation
```

**Impact**:
- Algorithm debugging may be impossible if predictions are truncated
- Different Nightscout installations behave differently
- No indication to clients that data was truncated
- Research and audit use cases affected

**Possible Solutions**:
1. Document `PREDICTIONS_MAX_SIZE` behavior in API spec
2. Add response header indicating truncation occurred
3. Standardize default behavior across installations
4. Add `truncated: true` flag to devicestatus when applicable

**Status**: Under discussion

**Related**:
- GAP-SYNC-002 (Effect timelines not uploaded)

---

---

### GAP-PRED-002: Loop Single Prediction Incompatible with oref Multi-Curve Display

**Scenario**: Viewing Loop predictions in Nightscout alongside AAPS/Trio users

**Description**: Loop uploads a single combined prediction curve (`loop.predicted.values`), while Nightscout's OpenAPS plugin expects separate `predBGs.IOB`, `predBGs.COB`, `predBGs.UAM`, `predBGs.ZT` arrays. Loop predictions cannot show IOB/COB/UAM/ZT toggle.

**Source**: `NightscoutServiceKit/Extensions/StoredDosingDecision.swift`, `cgm-remote-monitor/lib/plugins/openaps.js`

**Impact**:
- Loop predictions display as single line; AAPS/Trio show 4 toggleable curves
- Different visualization experience between Loop and AAPS/Trio users
- Harder to compare algorithm behavior across systems

**Status**: Design difference - document as expected behavior

---

---

### GAP-PRED-003: Prediction Interval Not Standardized

**Scenario**: Comparing prediction accuracy across systems

**Description**: AAPS/Trio use fixed 5-minute intervals for prediction arrays; Loop may use variable intervals based on algorithm timing and available glucose data.

**Source**: `LoopAlgorithm/GlucosePredictionAlgorithm.swift`, `app.aaps.core.interfaces.aps.Predictions`

**Impact**:
- Cannot directly compare prediction arrays between systems
- Interpolation needed for cross-system accuracy analysis
- Time alignment complexity for research

**Status**: Under investigation

---

---

### GAP-PRED-004: No Prediction Confidence or Uncertainty

**Scenario**: Assessing prediction reliability for algorithm tuning

**Description**: None of the AID systems upload prediction confidence intervals or uncertainty bounds. Only point estimates are available.

**Source**: All prediction implementations

**Impact**:
- Cannot assess prediction reliability
- Algorithm comparison limited to point estimates
- No way to detect high-uncertainty situations

**Possible Solutions**:
1. Add optional `confidenceBounds` field to prediction format
2. Include standard deviation or percentile ranges

**Status**: Future enhancement consideration

---

## OpenAPS/oref0 Gaps

### GAP-ALG-009: DynamicISF Not Present in oref0

**Scenario**: Running AAPS DynamicISF test vectors against vanilla oref0

**Description**: AAPS's DynamicISF algorithm calculates variable insulin sensitivity based on Total Daily Dose (TDD) using formula `1800 / (TDD × ln(BG/divisor + 1))`. This algorithm is not present in vanilla oref0, which uses static ISF from profile.

**Source**: Conformance testing (85 vectors, 44 DynamicISF, 18% pass rate)

**Impact**:
- 52% of AAPS test vectors cannot pass oref0 validation
- eventualBG calculations diverge significantly
- Cross-system conformance testing requires algorithm-specific runners

**Possible Solutions**:
1. Create separate conformance runner for DynamicISF
2. Add DynamicISF calculation to conformance suite
3. Filter test vectors to SMBPlugin-only for oref0 testing

**Status**: Documented

---

### GAP-ALG-010: AutoISF Not Present in oref0

**Scenario**: Running AAPS AutoISF test vectors against vanilla oref0

**Description**: AAPS's AutoISF algorithm uses sigmoid-based ISF adjustment considering BG level, time since last bolus, exercise activity, and accelerating/decelerating BG. This is entirely AAPS-specific and not present in oref0.

**Source**: Conformance testing (85 vectors, 22 AutoISF, 5% pass rate)

**Impact**:
- 26% of AAPS test vectors virtually all fail oref0 validation
- AutoISF produces significantly different dosing recommendations
- Cross-system algorithm comparison requires algorithm-specific testing

**Possible Solutions**:
1. Create AAPS Kotlin-based conformance runner
2. Document AutoISF as AAPS-specific extension
3. Separate conformance suites by algorithm variant

**Status**: Documented

---

### GAP-ALG-011: LGS Duration Differences

**Scenario**: Low Glucose Suspend temp basal duration comparison

**Description**: oref0 uses 30-minute temp basals by default; AAPS uses 120 minutes for Low Glucose Suspend situations. Both achieve same safety goal (zero insulin delivery) but duration differs.

**Source**: Conformance testing LGS category (6/8 failures on duration)

**Impact**:
- LGS tests fail on duration even when rate is correct (0)
- Different pump command frequency between systems
- No functional difference in safety behavior

**Possible Solutions**:
1. Update assertions to allow 30 OR 120 minute duration for LGS
2. Document as expected behavioral difference
3. Normalize duration expectations in test framework

**Status**: Documented

---

### GAP-ALG-012: DIA Minimum Enforcement Differences

**Scenario**: Profile with DIA < 5 hours configured

**Description**: oref0 enforces minimum 5-hour DIA (Duration of Insulin Action); AAPS allows user-configured lower values. When profile has DIA=3, oref0 treats it as DIA=5, causing different IOB decay calculations.

**Source**: Test vector TV-017 (DIA=3, eventualBG 80 expected vs 146 actual)

**Impact**:
- IOB calculations diverge when profile DIA < 5 hours
- eventualBG predictions differ
- Safety: oref0's enforcement is more conservative

**Possible Solutions**:
1. Document as expected behavior difference
2. Add DIA normalization to test vector transform
3. Warn when DIA < 5 in input validation

**Status**: Documented

---

## Loop Algorithm Gaps

### GAP-ALG-013: Loop Has No Autosens

**Scenario**: Cross-system sensitivity ratio comparison

**Description**: Loop does not implement Autosens sensitivity ratio. Uses RetrospectiveCorrection which adjusts predictions but not profile values (ISF, basal).

**Source**: `LoopAlgorithm.swift:120-126`, no Autosens equivalent

**Impact**:
- Cannot compare `sensitivityRatio` output across systems
- Loop users cannot get automated profile adjustments
- Different sensitivity response than oref0-based systems

**Possible Solutions**:
1. Document as architectural difference (not a bug)
2. Consider adding Autosens as optional feature in Loop

**Status**: Documented

---

### GAP-ALG-014: Loop Prediction Is Single Curve

**Scenario**: Algorithm debugging and prediction component analysis

**Description**: Loop produces one combined prediction curve; oref0 produces 4 separate curves (IOB, COB, UAM, ZT). Loop effects are available but combined into single trajectory.

**Source**: `LoopAlgorithm.swift:168` - `LoopMath.predictGlucose()`

**Impact**:
- Cannot compare individual prediction components directly
- Debugging requires examining effect arrays separately
- Cross-system prediction comparison limited to final values

**Possible Solutions**:
1. Add devicestatus output showing effect-isolated predictions
2. Use Loop's `effects` struct for component analysis

**Status**: Documented

---

### GAP-ALG-015: Loop Does Not Expose UAM Curve

**Scenario**: Unannounced meal handling comparison

**Description**: Loop has no explicit UAM (Unannounced Meal) curve. Unexpected rises are handled via RetrospectiveCorrection which detects discrepancies but doesn't project continued absorption.

**Source**: Architectural difference - Loop uses RC, oref0 uses UAM curve

**Impact**:
- Cannot validate UAM-specific behavior in Loop
- Different response to unannounced carbs
- Loop may be slower to respond to large unlogged meals

**Possible Solutions**:
1. Document as design difference
2. Evaluate if RC provides equivalent safety

**Status**: Documented

---

### GAP-ALG-016: Different IOB/COB Calculation Timing

**Scenario**: Algorithm conformance testing with pre-computed inputs

**Description**: oref0 expects pre-computed IOB/COB as input; Loop computes them from dose/carb history during prediction. Same raw data can produce different IOB values depending on calculation timing and method.

**Source**: `LoopAlgorithm.swift:95-103` vs `oref0/lib/iob/total.js`

**Impact**:
- oref0 test vectors cannot be directly used for Loop testing
- Different IOB at same timestamp possible
- Conformance testing requires raw history, not computed values

**Possible Solutions**:
1. Create Loop-specific test vectors with raw dose history
2. Use Loop's `live_capture_input.json` format for testing

**Status**: Documented

---

## Profile Schema Gaps

### GAP-PROF-001: Time Format Incompatibility

**Description:** Nightscout uses string "HH:MM" format while Loop/AAPS use integer seconds from midnight.

**Source:** 
- `externals/cgm-remote-monitor/lib/profile/profileeditor.js:32`
- `externals/AndroidAPS/core/interfaces/profile/Profile.kt:133`

**Impact:** Profile sync requires format conversion; potential off-by-one errors at midnight boundary.

**Remediation:** Standardize on seconds from midnight with conversion utilities.

### GAP-PROF-002: Missing Safety Limits in Nightscout

**Description:** Nightscout profile lacks `maximumBasalRatePerHour`, `maximumBolus`, and `suspendThreshold` found in Loop.

**Source:** `externals/LoopWorkspace/LoopKit/LoopKit/TherapySettings.swift:19-23`

**Impact:** Safety limits not portable between systems; each controller must manage locally.

**Remediation:** Add optional safety limit fields to Nightscout profile schema.

### GAP-PROF-003: No Override Presets in Nightscout

**Description:** Loop's `overridePresets` and `correctionRangeOverrides` have no Nightscout equivalent.

**Source:** `externals/LoopWorkspace/LoopKit/LoopKit/TherapySettings.swift:15-17`

**Impact:** Override configurations not synced; must be configured separately on each device.

**Remediation:** Add override preset array to Nightscout profile collection.

### GAP-PROF-004: Profile Switching Features (AAPS-only)

**Description:** AAPS supports `percentage` and `timeshift` for profile switching; not in Loop or Nightscout.

**Source:** `externals/AndroidAPS/core/interfaces/profile/Profile.kt:36-41`

**Impact:** Profile switch events sync as treatments but actual percentages not in profile.

**Remediation:** Document as AAPS-specific feature; consider adding to Nightscout profile.

### GAP-PROF-005: DIA vs Insulin Model Mismatch

**Description:** Nightscout/AAPS use scalar DIA hours while Loop uses exponential insulin model presets.

**Source:**
- `externals/cgm-remote-monitor/lib/profile/profileeditor.js:30`
- `externals/LoopWorkspace/LoopKit/LoopKit/TherapySettings.swift:31`

**Impact:** Loop's curve-based insulin action doesn't map to simple DIA value.

**Remediation:** Define mapping between Loop model presets and equivalent DIA values.

### GAP-PROF-006: Basal Schedule Time Format Inconsistency

**Description:** Nightscout uses "HH:MM" strings for basal schedule times while controllers use numeric offsets (seconds or minutes from midnight).

**Source:**
- `externals/cgm-remote-monitor/lib/profile/profileeditor.js:146` - "time" as "HH:MM"
- `externals/LoopWorkspace/LoopKit/LoopKit/DailyValueSchedule.swift:14` - startTime as TimeInterval (seconds)
- `externals/oref0/lib/profile/basal.js:24` - minutes from midnight

**Impact:** Parsing errors, timezone confusion, potential off-by-one minute issues during conversion.

**Remediation:** Standardize on seconds-from-midnight with explicit timezone in profile.

### GAP-PROF-007: 30-Minute Basal Rate Granularity

**Description:** AAPS supports 30-minute basal rate granularity (`is30minBasalRatesCapable`) but Nightscout profile schema assumes hourly boundaries.

**Source:**
- `externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/pump/defs/PumpDescription.kt:59` - `is30minBasalRatesCapable`
- `externals/cgm-remote-monitor/lib/profile/profileeditor.js` - No 30-min validation

**Impact:** Pumps with 30-minute granularity may lose precision when syncing via Nightscout.

**Remediation:** Extend Nightscout profile to support sub-hourly time boundaries (validate any HH:MM, not just :00).

### GAP-PROF-008: Basal Rate Precision Varies

**Description:** Different systems use different basal rate precision:
- Loop: Double (full precision)
- AAPS: Constrained by basalStep (e.g., 0.01 U/hr)
- oref0: 3 decimal places
- Nightscout: Arbitrary JS number

**Source:**
- `externals/oref0/lib/profile/basal.js:29` - `Math.round(basalRate*1000)/1000`
- `externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/pump/defs/PumpDescription.kt:23` - `basalStep`

**Impact:** Rounding differences when syncing basal profiles between systems.

**Remediation:** Document precision requirements; recommend 3 decimal places as minimum.

### GAP-SYNC-020: Basal Schedule Change Events

**Description:** No standardized event type for "basal schedule was changed" across systems.

**Source:** No explicit event type in Nightscout treatments collection for profile schedule modifications.

**Impact:** Schedule changes may not propagate consistently; no audit trail for profile edits.

**Remediation:** Define profile change event type with before/after snapshots.

## Bolus Wizard Gaps

### GAP-BOLUS-001: Prediction-Based vs Arithmetic Formula

**Description:** Loop uses prediction-based bolus calculation while AAPS uses traditional arithmetic formula. Same inputs produce different recommendations.

**Source:** 
- `externals/AndroidAPS/.../BolusWizard.kt:210-216`
- `externals/LoopWorkspace/.../DoseMath.swift:275-332`

**Impact:** Users switching between systems see different bolus recommendations for identical situations.

**Remediation:** Document expected differences; different approaches are intentional design choices.

### GAP-BOLUS-002: IOB Handling Mismatch

**Description:** AAPS separates bolus/basal IOB with user toggles; Loop uses combined pending insulin.

**Source:** 
- `externals/AndroidAPS/.../BolusWizard.kt:235-242`
- `externals/LoopWorkspace/.../DoseMath.swift:546`

**Impact:** Different IOB subtraction behavior; AAPS allows excluding basal IOB.

**Remediation:** Document as intentional design difference.

### GAP-BOLUS-003: SuperBolus Not Portable

**Description:** AAPS SuperBolus feature (add 2h basal to bolus) has no Loop equivalent.

**Source:** `externals/AndroidAPS/.../BolusWizard.kt:248-253`

**Impact:** Feature not available when switching to Loop.

**Remediation:** Document as AAPS-specific feature.

### GAP-BOLUS-004: Trend Correction Differences

**Description:** AAPS has explicit trend correction toggle; Loop incorporates trend via prediction model.

**Source:** `externals/AndroidAPS/.../BolusWizard.kt:222-225`

**Impact:** AAPS trend correction is linear extrapolation (15min × 3); Loop uses full prediction.

**Remediation:** Document different approaches to trend handling.

## Sensitivity Adjustment Gaps

### GAP-SENS-001: Different Output Representations

**Description:** Autosens outputs a ratio (0.7-1.3) that multiplies ISF/basal, while Loop RC outputs glucose effects added to prediction.

**Source:** 
- `externals/oref0/lib/determine-basal/autosens.js`
- `externals/LoopWorkspace/.../StandardRetrospectiveCorrection.swift`

**Impact:** Cannot directly compare sensitivity adjustments between systems.

**Remediation:** Document equivalent effects; both achieve similar outcomes via different mechanisms.

### GAP-SENS-002: Detection Window Mismatch

**Description:** Autosens uses 8-24h windows; Loop RC uses 30-180 min windows.

**Source:** 
- `externals/AndroidAPS/.../SensitivityOref1Plugin.kt:86`
- `externals/LoopWorkspace/.../StandardRetrospectiveCorrection.swift:18`

**Impact:** Different response times to sensitivity changes.

**Remediation:** Document expected behavior differences for users.

### GAP-SENS-003: No Autosens Equivalent in Loop

**Description:** Loop doesn't have direct ISF/basal multiplier like Autosens. Uses prediction adjustments instead.

**Source:** Loop architecture uses prediction adjustments, not parameter modification.

**Impact:** Users switching from AAPS to Loop may miss Autosens-like behavior.

**Remediation:** Explain that IRC provides similar long-term adaptation.

### GAP-SENS-004: Dynamic ISF Not Standardized

**Description:** Dynamic ISF implementations vary between oref1 and Loop experimental features.

**Source:** 
- oref1: `adjustmentFactor` config
- Loop: `GlucoseBasedApplicationFactorSelectionView.swift`

**Impact:** Different aggression at high BG levels between systems.

**Remediation:** Document formula differences and expected behaviors.

## Dosing Mechanism Gaps

### GAP-DOSE-001: SMB Not Available in Loop

**Description**: Loop does not have equivalent to oref0 SMB with 3-minute frequency and 50% insulinReq dosing.

**Affected Systems**: Loop vs oref0/AAPS/Trio

**Evidence**:
- oref0: `determine-basal.js:1100` - `microBolus = Math.min(insulinReq/2, maxBolus)`
- Loop: Uses `partialApplicationFactor` (40%) with 5-min cycles

**Impact**: Faster meal response possible with SMB.

**Remediation**: Loop Auto Bolus provides similar capability; document differences.

### GAP-DOSE-002: Different Safety Mechanisms

**Description**: SMB pairs with zero temp for safety; Loop uses IOB limits and partial application.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:1120` - `smbLowTempReq` calculation with zero temp
- Loop: `DoseMath.swift:425-428` - `additionalActiveInsulinClamp`

**Impact**: Different fallback behavior if pump disconnects or issues occur.

**Remediation**: Document safety models for each system.

### GAP-DOSE-003: SMB Enable Conditions Mismatch

**Description**: oref0 has 6+ SMB enable conditions; Loop auto bolus is simpler on/off.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:72-124` - `enableSMB_always`, `_with_COB`, `_after_carbs`, `_with_temptarget`, `_high_bg`
- AAPS: `BooleanKey.kt:50-54` - 5 SMB enable settings
- Loop: Single setting

**Impact**: Different automatic dosing behavior in different contexts.

**Remediation**: Document enable condition differences for users.

### GAP-DOSE-004: Dosing Frequency Difference

**Description**: SMB can run every 3 min; Loop cycles every 5 min.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:1133-1136` - `SMBInterval = 3` (configurable 1-10)
- Loop: Fixed 5-minute loop cycle

**Impact**: SMB can deliver corrections faster.

**Remediation**: Design difference - document expected response times.

---

## Insulin Model Gaps

### GAP-INS-005: Bilinear Model Not Supported in Loop

**Description**: Loop only supports exponential model; oref0 has legacy bilinear option.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `calculate.js:24-28` - conditional bilinear/exponential selection
- Loop: Only ExponentialInsulinModel.swift exists

**Impact**: Users preferring simpler bilinear model cannot use Loop. Minor - exponential is more accurate.

**Remediation**: Document as design choice; exponential is preferred.

### GAP-INS-006: Delay Parameter Handling Differs

**Description**: Loop has explicit delay parameter (default 10 min); oref0 bakes delay into peak time.

**Affected Systems**: Loop vs oref0

**Evidence**:
- Loop: `ExponentialInsulinModel.swift:14` - `public let delay: TimeInterval`
- oref0: No delay parameter in `calculate.js`

**Impact**: Slightly different curve start behavior for same peak time setting.

**Remediation**: Document for users migrating between systems.

### GAP-INS-007: Custom Peak Time UX Differs

**Description**: Loop uses fixed presets; oref0 allows custom peak with validation bounds.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `calculate.js:87-116` - peak bounds 50-120 (rapid) or 35-100 (ultra-rapid)
- Loop: Fixed preset values per insulin type

**Impact**: oref0/AAPS users have more tuning flexibility.

**Remediation**: Consider adding custom peak to Loop presets.

### GAP-INS-008: Identical Exponential Formula Verified

**Description**: Both Loop and oref0 use identical exponential formula from Loop issue #388.

**Affected Systems**: Loop, oref0, AAPS, Trio

**Evidence**:
- oref0: `calculate.js:125-136` explicitly cites Loop issue #388
- Loop: `ExponentialInsulinModel.swift:32-34` - original source

**Impact**: Positive - formula consistency ensures IOB compatibility.

**Status**: Verified as aligned - no remediation needed.

---

## Target Range Gaps

### GAP-TGT-001: Different Algorithm Targeting Behavior

**Description**: Loop uses dynamic targeting (suspend→midpoint over time); oref0 uses static midpoint.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- Loop: `DoseMath.swift:200-214` - `targetGlucoseValue()` blends over effect duration
- oref0: `determine-basal.js:243` - Static `(min_bg + max_bg) / 2`

**Impact**: Same target range settings produce different correction behavior.

**Remediation**: Document for users migrating between systems.

### GAP-TGT-002: Autosens Target Adjustment Not in Loop

**Description**: oref0 adjusts targets based on autosens ratio; Loop does not.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:296-311` - `sensitivity_raises_target`, `resistance_lowers_target`
- Loop: No equivalent in DoseMath.swift

**Impact**: oref0 is more aggressive in adjusting for insulin resistance/sensitivity.

**Remediation**: Design difference - document expected behavior.

### GAP-TGT-003: Temp Target Sensitivity Adjustment

**Description**: oref0 adjusts sensitivity ratio based on temp target magnitude; Loop overrides are simpler.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:259-277` - Formula: `c/(c+target_bg-normalTarget)`
- Loop: Override just replaces range, no sensitivity calculation

**Impact**: Exercise modes behave differently between systems.

**Remediation**: Document the formula for users expecting equivalent behavior.

### GAP-TGT-004: SMB Enable Tied to Target in oref0

**Description**: oref0 enables/disables SMB based on target value; Loop has no such coupling.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:63-64, 103-107` - `enableSMB_with_temptarget`, high target disables SMB
- Loop: Auto bolus enable is independent of target

**Impact**: Temp targets have different side effects between systems.

**Remediation**: Document for users expecting similar behavior.

---

## Trio Bridge Gaps

### GAP-TRIO-BRIDGE-001: No Type Safety Across Bridge

**Description**: JSON serialization loses Swift type information; JS returns untyped objects.

**Affected Systems**: Trio

**Evidence**:
- `OpenAPS.swift:617-625` - `worker.call()` returns `RawJSON` (String)
- Codable parsing may fail silently with missing fields

**Impact**: Runtime errors possible if JS output doesn't match expected structure.

**Remediation**: Trio uses Codable with optional fields for graceful degradation.

### GAP-TRIO-BRIDGE-002: Synchronous JS Execution

**Description**: JS calls block the context pool; long algorithm runs could exhaust pool.

**Affected Systems**: Trio

**Evidence**:
- `JavaScriptWorker.swift:35` - Pool size of 5 contexts
- Algorithm calls are synchronous within context

**Impact**: 5-context pool may bottleneck under heavy concurrent load.

**Remediation**: Pool size configurable; async/await prevents UI blocking.

### GAP-TRIO-BRIDGE-003: Middleware Security

**Description**: Custom middleware can modify algorithm behavior arbitrarily.

**Affected Systems**: Trio

**Evidence**:
- `OpenAPS.swift:798-813` - `middlewareScript()` loads user JS
- No validation or sandboxing of middleware code

**Impact**: User-installed scripts could produce dangerous dosing decisions.

**Remediation**: Trio requires explicit user action to enable middleware.
