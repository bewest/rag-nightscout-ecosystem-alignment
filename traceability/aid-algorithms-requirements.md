# Aid Algorithms Requirements

Domain-specific requirements extracted from requirements.md.
See [requirements.md](requirements.md) for the index.

---

### REQ-ALG-001: Cross-Project Test Vector Format

**Statement**: The ecosystem MUST define a unified JSON schema for algorithm test vectors that can be executed by any AID implementation.

**Rationale**: Enables automated detection of behavioral differences across oref0, AAPS, Loop, and Trio algorithm implementations.

**Scenarios**:
- Algorithm Conformance Testing
- Cross-Project Regression Detection
- New Implementation Validation

**Verification**:
- ✅ Schema validates all extracted test vectors
- ✅ At least 50 vectors covering all categories (85 extracted)
- 🔄 Runners exist for oref0, AAPS, and Loop (oref0 complete, others pending)

**Status**: oref0 runner complete
- `conformance/schemas/conformance-vector-v1.json` - Schema complete
- `conformance/vectors/` - 85 vectors extracted from AAPS
- `tools/extract_vectors.py` - Extraction tooling complete
- `conformance/runners/oref0-runner.js` - oref0 runner complete (26/85 pass)

**Gap Reference**: GAP-ALG-001

---

---

### REQ-ALG-002: Semantic Equivalence Assertions

**Statement**: The conformance suite MUST support semantic assertions (e.g., "rate increased", "no SMB") rather than only exact value matching.

**Rationale**: Different algorithm architectures (Loop combined curve vs oref 4-curve) produce different numerical values for equivalent clinical decisions.

**Scenarios**:
- Loop vs oref Comparison
- Algorithm Migration Validation

**Verification**:
- ✅ Assertion types include: rate_increased, rate_decreased, no_smb, eventual_in_range
- ✅ Baseline field allows relative assertions
- ✅ oref0-runner validates assertions (runner complete)

**Status**: Implementation complete for oref0

**Gap Reference**: GAP-ALG-003

---

---

### REQ-ALG-003: Safety Limit Validation

**Statement**: The conformance suite MUST include test vectors that verify safety limits (max IOB, max basal) are enforced.

**Rationale**: Safety-critical limits must be validated across all implementations to prevent overdosing.

**Scenarios**:
- Max IOB Enforcement
- Max Basal Rate Enforcement
- Low Glucose Suspend

**Verification**:
- Test vectors exist for each safety category
- All implementations pass safety limit tests
- Failures are treated as critical

**Gap Reference**: GAP-ALG-001

---

---

### REQ-ALG-004: Baseline Regression Detection

**Statement**: The conformance suite SHOULD detect when an implementation's behavior drifts from a known baseline.

**Rationale**: Algorithm updates should be intentional; accidental behavioral changes could affect patient safety.

**Scenarios**:
- oref0 Upstream Update
- AAPS Kotlin Migration
- Version Upgrade Validation

**Verification**:
- Baseline results stored per implementation
- CI detects changes from baseline
- Drift report generated with affected vectors

**Gap Reference**: GAP-ALG-002

---

## API Layer Requirements

---

### REQ-CARB-001: COB Model Type Annotation

**Statement**: Nightscout devicestatus uploads SHOULD include carb absorption model type annotation with COB values.

**Rationale**: COB values from different models (predictive vs reactive) are not comparable and should be labeled.

**Scenarios**:
- Multi-controller households
- User switching between systems
- Historical data analysis

**Verification**:
- devicestatus.cob includes model field
- UI displays model type when available
- Reports group by model type

**Gap Reference**: GAP-CARB-001

---

---

### REQ-CARB-002: Minimum Carb Impact Documentation

**Statement**: AID systems MUST document their minimum carb impact floor and its effect on COB decay.

**Rationale**: The min_5m_carbimpact parameter significantly affects how quickly COB decays and should be understood by users.

**Scenarios**:
- Configuring absorption settings
- Troubleshooting "stuck" COB
- Comparing system behavior

**Verification**:
- min_5m_carbimpact documented in user guide
- Effect on COB decay explained
- Comparison with other systems provided

**Gap Reference**: GAP-CARB-003

---

---

### REQ-CARB-003: Absorption Model Selection

**Statement**: AID systems supporting multiple absorption models SHOULD allow user selection with clear documentation of differences.

**Rationale**: Different absorption patterns (fast vs slow carbs) benefit from different models.

**Scenarios**:
- High-fat meals (slower absorption)
- Simple carbs (faster absorption)
- Mixed meals

**Verification**:
- Model selection available in settings
- Each model's characteristics documented
- Guidance on when to use each model

**Implementation Reference**: Loop CarbMath.swift supports Linear, Parabolic, PiecewiseLinear

---

## Vendor Interop Requirements

---

### REQ-CARB-004: Carb Sensitivity Factor Calculation

**Statement**: CSF (Carb Sensitivity Factor) calculation MUST use the formula: `CSF = ISF / CR` (mg/dL per gram of carbs).

**Rationale**: Consistent CSF calculation ensures glucose effects from carbs are comparable across systems.

**Scenarios**:
- Glucose Prediction
- Bolus Calculation

**Verification**:
- Calculate CSF in multiple systems with same ISF/CR
- Verify results match
- Test with varying ISF and CR schedules

---

---

### REQ-CARB-005: Per-Entry Absorption Time (Where Supported)

**Statement**: Systems that support per-entry absorption time (Loop, Trio) SHOULD preserve this field during sync. Systems using profile-based absorption (oref0, AAPS) MAY ignore this field.

**Rationale**: Different foods absorb at different rates. Loop/Trio support per-entry `absorptionTime`; oref0/AAPS use profile-based defaults and do not accept per-entry overrides.

**Scenarios**:
- Mixed Meal Entry (Loop/Trio)
- Cross-Platform Sync

**Verification**:
- Create carb entry with custom absorption time in Loop/Trio
- Verify COB decay follows specified time
- Sync to Nightscout and verify `absorptionTime` field preserved
- Note that oref0/AAPS will use profile-based absorption regardless

---

---

### REQ-CARB-006: COB Maximum Limits

**Statement**: COB hard limits SHOULD be configurable and MUST be clearly documented per system.

**Rationale**: Different limits (e.g., oref0's 120g cap vs Loop's no cap) can cause confusion and unexpected behavior.

**Scenarios**:
- Large Meal Entry
- COB Display

**Verification**:
- Enter carbs exceeding maxCOB limit
- Verify COB is capped at documented maximum
- Confirm limit is surfaced in UI or logs

---

## Libre CGM Protocol Requirements

---

### REQ-DEGRADE-001: Automation Disable on CGM Loss

**Statement**: AID controllers MUST automatically disable closed-loop automation when CGM data becomes stale or unreliable, falling back to scheduled basal delivery.

**Rationale**: Automation decisions require current glucose evidence. Without reliable CGM, the system should degrade to a known-safe state (scheduled basal) rather than continue making decisions on stale data.

**Scenarios**:
- CGM Signal Loss
- Sensor Warmup Period
- Compression Low Detection

**Verification**:
- Simulate CGM data gap exceeding staleness threshold
- Verify automation suspends and basal schedule resumes
- Verify clear notification to user about fallback state

---

---

### REQ-DEGRADE-002: Pump Communication Timeout Handling

**Statement**: AID controllers MUST enter a safe fallback state when pump communication fails, with clear indication to the user about current therapy status.

**Rationale**: Pump command failures create uncertainty about actual delivery. The system should inform the user and await confirmation rather than silently failing or retrying indefinitely.

**Scenarios**:
- Pump Out of Range
- Bluetooth Disconnection
- Pod/Pump Occlusion

**Verification**:
- Simulate pump communication timeout
- Verify system enters fallback state
- Verify user notification includes actionable guidance

---

---

### REQ-DEGRADE-003: Remote Control Fallback

**Statement**: When remote control channels are unavailable, caregiver apps SHOULD continue to provide remote visibility (following) and SHOULD offer out-of-band communication guidance.

**Rationale**: Network failures should not leave caregivers without any visibility. Read-only monitoring should remain available longer than write commands.

**Scenarios**:
- Nightscout Connectivity Loss
- Push Notification Failure
- API Token Expiration

**Verification**:
- Simulate command channel failure
- Verify following/monitoring continues
- Verify UI guidance for alternative communication

---

---

### REQ-DEGRADE-004: Layer Transition Logging

**Statement**: AID systems MUST log layer transitions (e.g., closed-loop to open-loop, automation to manual) with reason codes and timestamps.

**Rationale**: Understanding why the system changed modes is critical for retrospective analysis, debugging, and user trust.

**Scenarios**:
- Automation Pause
- Safety Limit Breach
- Component Failure

**Verification**:
- Trigger layer transition (e.g., pause automation)
- Verify log entry includes reason code
- Verify log entry includes precise timestamp

---

---

### REQ-DEGRADE-005: Safe State Documentation

**Statement**: Each AID system SHOULD document its safe states and the conditions that trigger transitions to those states.

**Rationale**: Users, caregivers, and developers need to understand what happens when components fail. This enables appropriate planning and reduces panic during degraded operation.

**Scenarios**:
- System Documentation
- User Onboarding
- Incident Response

**Verification**:
- Review system documentation for safe state definitions
- Verify safe states are discoverable in UI/settings
- Verify safe state behavior matches documentation

---

---

### REQ-DEGRADE-006: Delegate Agent Fallback

**Statement**: Delegate agents (L9) MUST fall back to human confirmation when confidence is low, context signals are unavailable, or out-of-band data is stale.

**Rationale**: Agents operating with incomplete information should not make autonomous decisions. Graceful degradation means reverting to "propose only" mode.

**Scenarios**:
- Context Signal Loss
- Low Confidence Decision
- Stale Wearable Data

**Verification**:
- Simulate loss of out-of-band signal
- Verify agent reverts to propose-only mode
- Verify agent requests human confirmation

---

## Batch Operation Requirements

---

### REQ-INS-001: Consistent Exponential Model Across Systems

**Statement**: AID systems using the exponential insulin model MUST use the same mathematical formula to ensure IOB calculations are comparable.

**Rationale**: Different formulas produce different IOB decay curves, leading to inconsistent dosing decisions when comparing systems or switching between them.

**Scenarios**:
- IOB Comparison (to be created)

**Verification**:
- Given identical bolus history and DIA settings
- Calculate IOB using Loop, oref0, AAPS, and Trio
- Verify IOB values match within 0.01U precision

**Cross-System Status**:
- Loop: ✅ Original exponential formula
- oref0: ✅ Copied from Loop (explicitly credited)
- AAPS: ✅ Port of oref0
- Trio: ✅ Uses oref0 JavaScript

**Source Reference**: `oref0:lib/iob/calculate.js#L125` cites Loop as formula source.

---

---

### REQ-INS-002: DIA Minimum Enforcement

**Statement**: AID systems MUST enforce a minimum DIA of 5 hours for exponential insulin models to prevent dangerously fast IOB decay.

**Rationale**: DIA values below 5 hours cause insulin to "disappear" from IOB calculations before it finishes acting, leading to insulin stacking and hypoglycemia.

**Scenarios**:
- DIA Validation (to be created)

**Verification**:
- Attempt to set DIA = 3 hours with exponential model → Verify rejection or auto-correction to 5 hours
- Verify user notification when DIA is adjusted

**Cross-System Status**:
- Loop: ✅ Fixed DIA per model preset (5-6 hours)
- oref0: ✅ `requireLongDia` flag enforces 5h minimum
- AAPS: ✅ `hardLimits.minDia()` returns 5.0
- Trio: ✅ Via oref0 enforcement

---

---

### REQ-INS-003: Peak Time Configuration Bounds

**Statement**: When custom peak time is enabled, AID systems MUST clamp the value to valid ranges to prevent unrealistic insulin curves.

**Rationale**: Peak times outside physiological ranges produce unrealistic insulin activity curves that lead to dangerous predictions.

**Scenarios**:
- Peak Time Validation (to be created)

**Verification**:
- Rapid-acting: Verify peak clamped to 50-120 min range
- Ultra-rapid: Verify peak clamped to 35-100 min range
- Verify user notification when peak is adjusted

**Cross-System Status**:
- oref0: ✅ Explicit min/max checks in `iobCalcExponential()`
- AAPS: ✅ Free Peak plugin with hard limits
- Trio: ✅ Via oref0 enforcement
- Loop: ✅ Fixed peaks per preset (no custom)

---

---

### REQ-INS-004: Activity Calculation for BGI

**Statement**: AID systems MUST calculate insulin activity (rate of action) alongside IOB to enable Blood Glucose Impact (BGI) predictions.

**Rationale**: BGI = -activity × ISF × 5 is used to predict how much glucose will drop in the next 5 minutes. Without activity, predictions are incomplete.

**Scenarios**:
- BGI Calculation (to be created)

**Verification**:
- Calculate activity from insulin curve formula
- Compute BGI = -activity × ISF × 5
- Verify BGI matches observed glucose change (within noise)

**Cross-System Status**:
- Loop: ✅ Via `percentEffectRemaining` derivative
- oref0: ✅ `activityContrib` calculated alongside `iobContrib`
- AAPS: ✅ `result.activityContrib` in `iobCalcForTreatment()`
- Trio: ✅ Via oref0

---

---

### REQ-INS-005: Insulin Model Metadata in Treatments (Proposed)

**Statement**: Treatments uploaded to Nightscout SHOULD include insulin model metadata (curve type, peak time, DIA) to enable historical IOB reconstruction.

**Rationale**: Without model metadata, historical IOB values cannot be reproduced, limiting retrospective analysis and debugging.

**Scenarios**:
- Treatment Upload Validation (to be created)

**Verification**:
- Upload bolus treatment
- Verify presence of `insulinModel`, `insulinPeak`, `insulinDIA` fields
- Download treatment and verify metadata preserved

**Cross-System Status**:
- Loop: ❌ Not implemented (gap)
- oref0: ❌ Not implemented (gap)
- AAPS: ⚠️ Partial via `insulinConfiguration` in database
- Trio: ❌ Not implemented (gap)

**Gap Reference**: GAP-INS-001

---

## BLE Protocol Requirements

---

### REQ-PR-001: Heart Rate Collection Support

**Statement**: Nightscout SHOULD provide a standardized HeartRate collection in APIv3 for biometric data storage.

**Rationale**: AAPS and other systems collect heart rate data that should be stored alongside CGM data for holistic analysis.

**Scenarios**:
- AAPS uploads HR from connected devices
- Correlation analysis between HR and glucose
- Exercise detection and dosing adjustment

**Verification**:
- POST to /api/v3/heartrate succeeds
- GET returns stored HR data with timestamps
- AAPS uploader successfully syncs HR

**Specification**: [`specs/openapi/aid-heartrate-2025.yaml`](../specs/openapi/aid-heartrate-2025.yaml)

**Gap Reference**: GAP-API-HR

---

---

### REQ-PR-002: Multi-Insulin API Standardization

**Statement**: Nightscout SHOULD provide an insulin entity collection for storing multiple insulin profiles with curves and display properties.

**Rationale**: Users often use multiple insulins (rapid, long-acting) and need consistent profiles across xDrip+, nightscout-reporter, and Nightscout.

**Scenarios**:
- Define insulin curves for IOB calculations
- Share insulin definitions across devices
- Color-code treatments by insulin type

**Verification**:
- POST to /api/v3/insulin succeeds
- GET returns insulin profiles with curves
- xDrip+ and nightscout-reporter compatible

**Gap Reference**: GAP-INSULIN-001

---

---

### REQ-PR-003: Remote Command Queue

**Statement**: Nightscout SHOULD provide a command queue for remote AID control with delivery status tracking.

**Rationale**: Loop caregivers need reliable remote bolus/carb delivery with confirmation.

**Scenarios**:
- Caregiver sends remote bolus
- Command delivery confirmed or failed
- Expired commands cleaned up

**Verification**:
- POST command to queue
- Query command status
- Receive push confirmation

**Gap Reference**: GAP-REMOTE-CMD

---

---

### REQ-PR-004: Consistent Timezone Display

**Statement**: Nightscout SHOULD display device timezone from profile rather than browser local time, with dual display when timezones differ.

**Rationale**: Cross-timezone caregivers need to see times in the looper's timezone.

**Scenarios**:
- Caregiver in different timezone
- Historical data review
- Careportal entry creation

**Verification**:
- Clock shows device timezone
- Both times shown when offsets differ
- Profile timezone used as source

**Gap Reference**: GAP-TZ-001

---

## Statistics API Requirements

---

## Profile Schema Requirements

### REQ-PROF-001: Standard Time Format

**Statement**: Profile schedules SHOULD use seconds from midnight for time representation.

**Rationale**: Nightscout uses "HH:MM" strings while Loop/AAPS use integers. Standardization prevents conversion errors.

**Scenarios**:
- Profile sync from Loop to Nightscout
- Profile import in AAPS from Nightscout

**Verification**:
- Time values consistently parse to same minute-of-day
- No off-by-one errors at midnight boundary

**Gap**: GAP-PROF-001

**Source**: `docs/10-domain/profile-schema-alignment.md`

---

### REQ-PROF-002: Safety Limits in Profile

**Statement**: Nightscout profile collection SHOULD support optional safety limit fields.

**Rationale**: Loop has maxBasal, maxBolus, suspendThreshold that don't sync to Nightscout.

**Scenarios**:
- View all therapy settings in Nightscout
- Restore safety limits to new device

**Verification**:
- Profile includes optional safety limit fields
- Controllers can read/write these values

**Gap**: GAP-PROF-002

**Source**: `docs/10-domain/profile-schema-alignment.md`

---

### REQ-PROF-003: Override Presets Sync

**Statement**: Nightscout profile SHOULD support override preset configurations.

**Rationale**: Loop's named overrides (Exercise, Pre-Meal) don't sync to Nightscout.

**Scenarios**:
- View override presets in Nightscout
- Share override configs between devices

**Verification**:
- Profile includes override presets array
- Presets include name, target range, duration

**Gap**: GAP-PROF-003

**Source**: `docs/10-domain/profile-schema-alignment.md`

---

### REQ-PROF-004: Insulin Model Mapping

**Statement**: Controllers SHOULD document mapping between insulin model presets and equivalent DIA values.

**Rationale**: Loop uses curve-based models while Nightscout/AAPS use scalar DIA.

**Scenarios**:
- Display equivalent DIA for Loop users
- Convert between systems

**Verification**:
- Documented mapping table exists
- Round-trip conversion preserves behavior

**Gap**: GAP-PROF-005

**Source**: `docs/10-domain/profile-schema-alignment.md`

## Bolus Wizard Requirements

### REQ-BOLUS-001: Document Calculation Approach

**Statement**: Each controller SHOULD document its bolus calculation approach clearly.

**Rationale**: Loop uses prediction-based calculation while AAPS uses traditional arithmetic. Users need to understand expected differences.

**Scenarios**:
- User switches from AAPS to Loop
- Comparing recommendations between systems

**Verification**:
- Documentation describes formula used
- Examples show calculation steps

**Gap**: GAP-BOLUS-001

**Source**: `docs/10-domain/bolus-wizard-formula-comparison.md`

---

### REQ-BOLUS-002: IOB Subtraction Transparency

**Statement**: Controllers SHOULD clearly indicate what IOB components are subtracted.

**Rationale**: AAPS allows toggling basal/bolus IOB separately; Loop combines them.

**Scenarios**:
- User wants to exclude basal IOB
- Debugging unexpected recommendations

**Verification**:
- UI shows IOB breakdown
- Documentation explains IOB handling

**Gap**: GAP-BOLUS-002

**Source**: `docs/10-domain/bolus-wizard-formula-comparison.md`

---

### REQ-BOLUS-003: Nightscout Wizard Sync

**Statement**: Bolus wizard inputs SHOULD sync to Nightscout for retrospective analysis.

**Rationale**: AAPS sends full BolusCalculatorResult; Loop sends limited data.

**Scenarios**:
- Retrospective review of bolus decisions
- Endo/CDE reviewing patient data

**Verification**:
- Wizard inputs visible in Nightscout reports
- BCR data available via API

**Gap**: Related to treatment sync

**Source**: `docs/10-domain/bolus-wizard-formula-comparison.md`

## Sensitivity Adjustment Requirements

### REQ-SENS-001: Document Sensitivity Method

**Statement**: Each controller SHOULD document its sensitivity adjustment algorithm.

**Rationale**: Autosens (ratio multiplier) vs Loop RC (prediction effect) work differently.

**Scenarios**:
- User switches from AAPS to Loop
- Comparing algorithm behaviors

**Verification**:
- Documentation describes method clearly
- Expected behavior documented

**Gap**: GAP-SENS-001

**Source**: `docs/10-domain/autosens-dynamic-isf-comparison.md`

---

### REQ-SENS-002: Sensitivity Visibility in Nightscout

**Statement**: Sensitivity adjustments SHOULD be visible in Nightscout devicestatus.

**Rationale**: AAPS reports sensitivityRatio; Loop RC effect not itemized.

**Scenarios**:
- Retrospective analysis of sensitivity changes
- Debugging algorithm behavior

**Verification**:
- devicestatus includes sensitivity data
- Reports can chart sensitivity over time

**Gap**: GAP-SENS-001

**Source**: `docs/10-domain/autosens-dynamic-isf-comparison.md`

---

### REQ-SENS-003: Document Detection Windows

**Statement**: Controllers SHOULD document their sensitivity detection time windows.

**Rationale**: Autosens 8-24h vs Loop RC 30-180 min affects response time.

**Scenarios**:
- Understanding lag in sensitivity detection
- Debugging unexpected behavior

**Verification**:
- Documentation states window duration
- Behavior matches documented windows

**Gap**: GAP-SENS-002

**Source**: `docs/10-domain/autosens-dynamic-isf-comparison.md`

## Carb Absorption Requirements

### REQ-CARB-001: COB Display Source Attribution

**Statement**: Systems displaying COB MUST indicate which algorithm calculated it.

**Rationale**: Loop and oref0 COB values are not directly comparable due to different calculation methods.

**Verification**: Check UI for source indicator.

### REQ-CARB-002: min_5m_carbimpact Configuration

**Statement**: oref0-based systems SHOULD expose min_5m_carbimpact as a configurable setting.

**Rationale**: Critical tuning parameter affecting carb absorption rate floor (default: AMA=3, SMB=8 mg/dL/5m).

**Verification**: Settings UI audit.

### REQ-CARB-003: Absorption Model Documentation

**Statement**: AID systems MUST document their carb absorption model type and key parameters.

**Rationale**: Users need to understand how COB is calculated for accurate meal management.

**Verification**: Documentation review.

## Prediction Curve Requirements

### REQ-PRED-001: Prediction Structure Documentation

**Statement**: AID systems MUST document their prediction curve structure and interpretation.

**Rationale**: Users and developers need to understand single vs multi-curve predictions.

**Verification**: Documentation review.

### REQ-PRED-002: Prediction Curve Labeling

**Statement**: Systems displaying predictions SHOULD label the curve type (Loop, IOB, COB, UAM, ZT).

**Rationale**: Different curves represent different scenarios with different implications.

**Verification**: UI audit for prediction labels.

### REQ-PRED-003: Multi-Curve Display Option

**Statement**: Nightscout SHOULD provide option to display all oref0 prediction curves.

**Rationale**: ZT curve is important for safety; users benefit from seeing all scenarios.

**Verification**: Settings UI check.

## Dosing Mechanism Requirements

### REQ-DOSE-001: Dosing Mechanism Documentation

**Statement**: AID systems MUST document their primary automatic dosing mechanism (temp basal, SMB, or auto bolus).

**Rationale**: Users need to understand how insulin is delivered automatically.

**Verification**: Documentation review.

### REQ-DOSE-002: Safety Net Documentation

**Statement**: Systems using automatic boluses MUST document safety mechanisms (zero temp, IOB limits).

**Rationale**: Users need to understand fallback behavior if pump disconnects.

**Verification**: Safety documentation audit.

### REQ-DOSE-003: Enable Condition Transparency

**Statement**: Systems with conditional SMB/auto-bolus SHOULD clearly display which conditions are active.

**Rationale**: Users need to know when and why automatic boluses are enabled.

**Verification**: UI review for condition display.

---

## Insulin Model Requirements

### REQ-INS-001: Exponential Formula Consistency

**Statement**: Systems using exponential insulin model MUST use compatible formula (tau/a/S parameters from Loop issue #388).

**Rationale**: Loop and oref0 share the same formula source, ensuring IOB calculations match.

**Verification**: Compare IOB output for same insulin dose and time inputs.

### REQ-INS-002: DIA Range Validation

**Statement**: Systems MUST validate DIA is within safe bounds (typically 3-8 hours).

**Rationale**: Extreme DIA values can cause unsafe dosing calculations.

**Verification**: Test boundary values in profile settings.

### REQ-INS-003: Peak Time Documentation

**Statement**: Systems SHOULD document peak time values for each insulin preset (Humalog, Fiasp, etc.).

**Rationale**: Users need to understand how insulin curve timing affects dosing.

**Verification**: Documentation review for all insulin presets.
