# Aid Algorithms Gaps

Domain-specific gaps extracted from gaps.md.
See [gaps.md](gaps.md) for the index.

---

### GAP-ALG-001: No cross-project algorithm test vectors

**Scenario**: Algorithm validation across implementations

**Description**: Each AID project (oref0, AAPS, Loop, Trio) maintains isolated test fixtures with incompatible formats. No mechanism exists to validate behavioral consistency across implementations.

**Evidence**:
- oref0: `tests/determine-basal.test.js` with inline fixtures
- AAPS: `app/src/androidTest/assets/results/*.json` (~50 files)
- Loop: `LoopKitTests/Fixtures/` scattered JSON files

**Impact**:
- Algorithm differences may cause dosing inconsistencies for users switching between apps
- No automated regression detection for cross-project behavioral drift
- Safety-critical algorithm changes may go unvalidated

**Possible Solutions**:
1. Implement conformance vector format (see proposal)
2. Create cross-project runners for each implementation
3. CI integration to detect behavioral drift

**Status**: Proposal created

**Related**:
- [Algorithm Conformance Suite Proposal](../docs/sdqctl-proposals/algorithm-conformance-suite.md)

---

---

### GAP-ALG-002: oref0 vs AAPS behavioral drift

**Scenario**: AAPS Kotlin vs upstream oref0 JavaScript

**Description**: AAPS Kotlin implementation may have diverged from upstream oref0 JavaScript. The ReplayApsResultsTest compares JS vs KT within AAPS but not against upstream oref0.

**Evidence**:
```kotlin
// AAPS: ReplayApsResultsTest.kt compares internal JS vs KT
// but does NOT compare against externals/oref0
```

**Impact**:
- AAPS users may experience different dosing than OpenAPS rig users with identical settings
- No clear compatibility guarantees between implementations

**Possible Solutions**:
1. Include upstream oref0 in AAPS conformance testing
2. Create shared test vectors that both projects run
3. Document known behavioral differences

**Status**: Proposal created

**Related**:
- [Algorithm Conformance Suite Proposal](../docs/sdqctl-proposals/algorithm-conformance-suite.md)

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

---
