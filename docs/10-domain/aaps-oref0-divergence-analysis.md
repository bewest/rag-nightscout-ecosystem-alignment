# AAPS vs oref0 Algorithm Divergence Analysis

This document analyzes the 69% divergence found in conformance testing between AAPS algorithm outputs and vanilla oref0, based on 85 test vectors extracted from AAPS `ReplayApsResultsTest` fixtures.

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total test vectors | 85 |
| Passed | 26 (31%) |
| Failed | 59 (69%) |
| Errors | 0 |

**Root Cause**: The divergence is NOT caused by differences between vanilla AAPS and oref0. It is caused by AAPS's **Dynamic ISF** and **AutoISF** extensions that are not present in oref0.

| AAPS Algorithm Variant | Tests | Pass Rate | Divergence |
|------------------------|-------|-----------|------------|
| OpenAPSSMBPlugin | 16 | 94% | Minimal (1 failure) |
| OpenAPSAMAPlugin | 3 | 67% | Low (1 failure) |
| OpenAPSSMBDynamicISFPlugin | 44 | 18% | High (36 failures) |
| OpenAPSSMBAutoISFPlugin | 22 | 5% | Very High (21 failures) |

**Conclusion**: The core oref0 algorithm (OpenAPSSMBPlugin) is effectively identical in AAPS and oref0. The divergence comes from AAPS-specific ISF calculation extensions.

---

## Test Methodology

### Test Runner

- **Source**: `conformance/runners/oref0-runner.js`
- **Algorithm**: oref0 `lib/determine-basal/determine-basal.js`
- **Transform**: Converts AAPS vector format to oref0 input format

### Test Vectors

- **Source**: AAPS `ReplayApsResultsTest` fixtures
- **Location**: `conformance/vectors/basal-adjustment/`, `conformance/vectors/low-glucose-suspend/`
- **Format**: JSON with input state, expected output, and assertions

### Validation Criteria

- `rate`: Temp basal rate (exact match ±0.01)
- `duration`: Temp basal duration (exact match)
- `eventualBG`: Predicted eventual BG (exact match ±1)
- Semantic assertions: `rate_zero`, `rate_increased`, `safety_limit`

---

## Failure Analysis by Category

### Category: basal-adjustment (77 tests)

| Result | Count | Rate |
|--------|-------|------|
| Passed | 24 | 31% |
| Failed | 53 | 69% |

**Primary failure types**:
- `eventualBG` mismatch: 52 failures
- `rate` mismatch: 13 failures
- `duration` undefined: 21 failures

### Category: low-glucose-suspend (8 tests)

| Result | Count | Rate |
|--------|-------|------|
| Passed | 2 | 25% |
| Failed | 6 | 75% |

**Primary failure types**:
- `duration` mismatch: 6 failures (30 vs 120 expected)
- `rate_zero` assertion: 4 failures

---

## Algorithm-Specific Analysis

### OpenAPSSMBPlugin (15/16 = 94% pass)

This is the **vanilla oref0 SMB algorithm** ported to Kotlin. The single failure (`TV-003`) is a duration mismatch:

```
duration 30 != expected 120
```

**Analysis**: oref0 returns 30-minute temp basals by default; AAPS may have extended duration logic.

**Source**: `externals/AndroidAPS/plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/`

### OpenAPSAMAPlugin (2/3 = 67% pass)

The AMA (Advanced Meal Assist) variant without SMB. One failure (`TV-017`):

```
eventualBG 146 != expected 80
```

**Analysis**: The test vector includes negative IOB (-0.275) and a DIA of 3 hours. oref0 enforces minimum 5-hour DIA, which may cause different IOB decay calculations.

**Source**: `externals/AndroidAPS/plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSAMA/`

### OpenAPSSMBDynamicISFPlugin (8/44 = 18% pass)

Dynamic ISF calculates variable insulin sensitivity based on **Total Daily Dose (TDD)**:

```kotlin
// AAPS DetermineBasalAdapterSMBDynamicISFJS.kt
val variableSensitivity = 1800 / (tdd * ln((glucose / insulinDivisor) + 1))
```

**Key differences from oref0**:
- oref0 uses **static ISF** from profile
- AAPS calculates ISF dynamically based on TDD and current BG
- Higher BG → lower ISF → more aggressive insulin

**Expected divergence**: Every calculation involving ISF (eventualBG, insulinReq, rate) will differ.

### OpenAPSSMBAutoISFPlugin (1/22 = 5% pass)

AutoISF is an AAPS-specific enhancement that further modifies ISF based on:
- BG level (via sigmoid function)
- Time since last bolus
- Exercise activity
- Acce/dece (accelerating/decelerating BG)

This is **not present in oref0** and represents the highest divergence.

---

## Root Causes of Divergence

### 1. Dynamic ISF vs Static ISF

| Aspect | oref0 | AAPS DynamicISF |
|--------|-------|-----------------|
| ISF Source | `profile.sens` (static) | `1800 / (TDD × ln(BG/divisor + 1))` |
| TDD Weighting | Not used | 7-day, 1-day, 4-hour blend |
| BG Dependence | None | Logarithmic scaling |
| Result | Consistent predictions | Variable ISF by BG level |

**Impact**: eventualBG calculations diverge because ISF affects the insulin-to-glucose conversion.

### 2. DIA Enforcement

| Aspect | oref0 | AAPS |
|--------|-------|------|
| Minimum DIA | 5 hours (enforced) | User configurable (can be 3h) |
| Effect | Standard IOB decay | Faster IOB decay if DIA < 5 |

Test vector TV-017 has `dia: 3`, which oref0 ignores (uses 5), causing IOB and eventualBG differences.

### 3. Duration Defaults

| Aspect | oref0 | AAPS |
|--------|-------|------|
| Temp basal duration | 30 minutes default | May use 120 for LGS |
| LGS behavior | 0 rate, 30 min | 0 rate, 120 min |

**Impact**: Low glucose suspend tests fail on duration, not rate.

### 4. Missing slope data

Several test vectors have `null` values for:
- `slopeFromMaxDeviation`
- `slopeFromMinDeviation`

oref0 uses these for UAM calculations; missing data may cause different prediction behavior.

---

## Sample Divergences

### TV-017 (OpenAPSAMAPlugin)

| Field | AAPS Expected | oref0 Actual |
|-------|---------------|--------------|
| eventualBG | 80 | 146 |

**Cause**: DIA=3 in vector; oref0 enforces DIA≥5, different IOB decay.

### TV-020 (DynamicISF)

| Field | AAPS Expected | oref0 Actual |
|-------|---------------|--------------|
| eventualBG | 340 | 323 |
| duration | 30 | undefined |

**Cause**: Dynamic ISF calculated different eventual BG; oref0 didn't set temp (no action required).

### TV-003 (LGS)

| Field | AAPS Expected | oref0 Actual |
|-------|---------------|--------------|
| rate | 0 | 0 ✓ |
| duration | 120 | 30 |

**Cause**: oref0 uses 30-minute temp basals; AAPS extends to 120 for LGS.

---

## Gaps Identified

### GAP-ALG-009: DynamicISF Not in oref0

**Description**: AAPS's DynamicISF algorithm (TDD-based ISF calculation) is not present in vanilla oref0.

**Affected Systems**: AAPS ↔ oref0 conformance testing

**Impact**: 52% of test vectors use DynamicISF and cannot pass oref0 validation.

**Remediation**: Either:
1. Create separate conformance runner for DynamicISF
2. Add DynamicISF implementation to conformance suite
3. Filter test vectors to SMBPlugin-only for oref0 testing

### GAP-ALG-010: AutoISF Not in oref0

**Description**: AAPS's AutoISF algorithm (sigmoid-based ISF adjustment) is entirely AAPS-specific.

**Affected Systems**: AAPS ↔ oref0 conformance testing

**Impact**: 26% of test vectors use AutoISF; virtually none pass oref0.

**Remediation**: Create AAPS-specific conformance runner.

### GAP-ALG-011: LGS Duration Differences

**Description**: oref0 uses 30-minute temp basals; AAPS uses 120 minutes for LGS.

**Affected Systems**: oref0, AAPS

**Impact**: LGS tests fail on duration even when rate is correct.

**Remediation**: Update assertions to allow 30 OR 120 minute duration for LGS.

### GAP-ALG-012: DIA Minimum Enforcement

**Description**: oref0 enforces minimum 5-hour DIA; AAPS allows user-configured lower values.

**Affected Systems**: oref0 ↔ AAPS with DIA < 5

**Impact**: IOB calculations diverge when profile DIA < 5 hours.

**Remediation**: Document as expected behavior; add DIA normalization to test transform.

---

## Recommendations

### Short-term

1. **Filter test vectors**: Run oref0 conformance only against `OpenAPSSMBPlugin` vectors
2. **Update LGS assertions**: Accept 30 or 120 minute duration
3. **Normalize DIA**: Transform DIA < 5 to 5 before running oref0

### Medium-term

1. **Create AAPS Kotlin runner**: Execute vectors against actual AAPS algorithm implementations
2. **Add DynamicISF support**: Port calculation to conformance suite for comparison
3. **Separate test suites**: One for vanilla oref0, one for AAPS variants

### Long-term

1. **Cross-system conformance**: Compare Loop, Trio, AAPS, oref0 against same vectors
2. **Standardize input format**: Create algorithm-agnostic test vector schema
3. **Live replay testing**: Run real devicestatus history through multiple algorithms

---

## Test Results Summary

### By Algorithm

| Algorithm | Total | Passed | Failed | Pass Rate |
|-----------|-------|--------|--------|-----------|
| OpenAPSSMBPlugin | 16 | 15 | 1 | 94% |
| OpenAPSAMAPlugin | 3 | 2 | 1 | 67% |
| OpenAPSSMBDynamicISFPlugin | 44 | 8 | 36 | 18% |
| OpenAPSSMBAutoISFPlugin | 22 | 1 | 21 | 5% |
| **Total** | **85** | **26** | **59** | **31%** |

### By Failure Type

| Failure Type | Count | Description |
|--------------|-------|-------------|
| eventualBG mismatch | 52 | Different BG prediction |
| duration mismatch | 21 | 30 vs 120 minute duration |
| rate_zero assertion | 16 | Expected 0 rate not achieved |
| rate mismatch | 13 | Different temp basal rate |
| rate_increased assertion | 1 | Rate did not increase as expected |

---

## Cross-References

- [Algorithm Comparison Deep Dive](./algorithm-comparison-deep-dive.md) - Detailed algorithm comparison
- [Conformance Test Runner](../../conformance/runners/oref0-runner.js) - oref0 runner implementation
- [Test Results](../../conformance/results/oref0-results.json) - Full test results
- [Terminology Matrix](../../mapping/cross-project/terminology-matrix.md#algorithm-core-terminology) - Algorithm term mapping

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-29 | Agent | Initial divergence analysis from conformance testing |
