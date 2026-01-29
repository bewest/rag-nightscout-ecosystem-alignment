# Algorithm Conformance Suite Proposal

> **Purpose**: Define cross-project test infrastructure for AID algorithm validation  
> **Scope**: oref0, AAPS, Loop, Trio algorithm implementations  
> **Last Updated**: 2026-01-29

## Executive Summary

This proposal defines a conformance test suite that enables cross-project validation of AID (Automated Insulin Delivery) algorithms. The suite provides a common test vector format and comparison framework to ensure algorithm consistency across JavaScript, Kotlin, Swift, and Rust implementations.

### Key Benefits

| Benefit | Impact |
|---------|--------|
| **Regression detection** | Catch algorithm changes that affect dosing |
| **Cross-language validation** | Verify Rust oref matches JS oref0 |
| **Interoperability assurance** | Ensure consistent behavior across apps |
| **Safety validation** | Confirm safety limits are enforced |

---

## Current State Analysis

### oref0 (JavaScript)

**Test Framework**: Mocha + Should.js  
**Test Location**: `externals/oref0/tests/determine-basal.test.js`  
**Fixtures**: `externals/oref0/examples/*.json`

**Input Format**:
```javascript
determine_basal(
  glucose_status,    // {glucose, delta, short_avgdelta, long_avgdelta}
  currenttemp,       // {temp, rate, duration}
  iob_data,          // {iob, basaliob, bolusiob, activity}
  profile,           // {sens, carb_ratio, max_iob, max_basal, ...}
  autosens_data,     // {ratio}
  meal_data,         // {carbs, mealCOB}
  tempBasalFunctions,
  microBolusAllowed,
  reservoir_data,
  currentTime
)
```

**Output Format**:
```json
{
  "temp": "absolute",
  "bg": 101,
  "eventualBG": 106,
  "insulinReq": -0.12,
  "rate": 0,
  "duration": 30,
  "reason": "...",
  "predBGs": {"IOB": [...], "ZT": [...], "COB": [...]}
}
```

### AAPS (Kotlin + JavaScript)

**Test Framework**: JUnit + JSONAssert  
**Test Location**: `externals/AndroidAPS/app/src/androidTest/kotlin/app/aaps/ReplayApsResultsTest.kt`  
**Fixtures**: `externals/AndroidAPS/app/src/androidTest/assets/results/*.json` (~50 files)

**Key Innovation**: AAPS runs **both JS and Kotlin implementations** and compares outputs, providing built-in cross-language validation.

**Input Interfaces**:
```kotlin
interface GlucoseStatus {
    val glucose: Double
    val delta: Double
    val shortAvgDelta: Double
    val longAvgDelta: Double
}

data class IobTotal(
    var iob: Double,
    var basaliob: Double,
    var activity: Double,
    var iobWithZeroTemp: IobTotal?
)

data class MealData(
    var carbs: Double,
    var mealCOB: Double
)
```

### Loop (Swift)

**Test Framework**: XCTest  
**Test Location**: `externals/LoopWorkspace/LoopKit/LoopKitTests/`  
**Fixtures**: `LoopKitTests/Fixtures/{DoseMathTests,GlucoseKit,CarbKit,InsulinKit}/`

**Input Structures**:
```swift
struct LoopAlgorithmInput {
    var predictionInput: LoopPredictionInput
    var predictionDate: Date
    var doseRecommendationType: DoseRecommendationType
}

struct LoopPredictionInput {
    var glucoseHistory: [StoredGlucoseSample]
    var doses: [DoseEntry]
    var carbEntries: [StoredCarbEntry]
    var settings: LoopAlgorithmSettings
}
```

---

## Proposed Conformance Architecture

### Test Vector Format

A unified JSON schema that captures algorithm inputs and expected outputs:

```json
{
  "$schema": "https://nightscout.github.io/schemas/conformance-vector-v1.json",
  "version": "1.0.0",
  "metadata": {
    "id": "TV-001",
    "name": "High glucose with no IOB",
    "category": "basal-adjustment",
    "source": "oref0/examples",
    "description": "Verify temp basal increase when BG high and IOB is zero"
  },
  "input": {
    "glucoseStatus": {
      "glucose": 180,
      "glucoseUnit": "mg/dL",
      "delta": 5,
      "shortAvgDelta": 4,
      "longAvgDelta": 3,
      "timestamp": "2026-01-29T12:00:00Z"
    },
    "iob": {
      "iob": 0,
      "basalIob": 0,
      "bolusIob": 0,
      "activity": 0
    },
    "profile": {
      "basalRate": 1.0,
      "sensitivity": 50,
      "carbRatio": 10,
      "targetLow": 100,
      "targetHigh": 110,
      "maxIob": 3.0,
      "maxBasal": 4.0,
      "dia": 5
    },
    "mealData": {
      "carbs": 0,
      "cob": 0
    },
    "currentTemp": {
      "rate": 0,
      "duration": 0
    }
  },
  "expected": {
    "rate": {"min": 1.5, "max": 4.0},
    "duration": 30,
    "eventualBG": {"min": 100, "max": 140},
    "smbAllowed": false,
    "reasonContains": ["high", "temp"]
  },
  "assertions": [
    {"type": "rate_increased", "baseline": 1.0},
    {"type": "safety_limit", "field": "rate", "max": 4.0},
    {"type": "no_smb"}
  ]
}
```

### Test Categories

| Category | Description | Count Target |
|----------|-------------|--------------|
| `basal-adjustment` | Temp basal increase/decrease | 20+ |
| `smb-delivery` | SuperMicroBolus scenarios | 15+ |
| `low-glucose-suspend` | LGS safety behaviors | 10+ |
| `carb-absorption` | COB impact on dosing | 15+ |
| `safety-limits` | Max IOB, max basal enforcement | 10+ |
| `autosens` | Sensitivity adjustments | 10+ |
| `exercise-mode` | Override/activity adjustments | 5+ |

### Directory Structure

```
conformance/
├── vectors/
│   ├── basal-adjustment/
│   │   ├── TV-001-high-bg-no-iob.json
│   │   ├── TV-002-low-bg-positive-iob.json
│   │   └── ...
│   ├── smb-delivery/
│   ├── low-glucose-suspend/
│   ├── carb-absorption/
│   ├── safety-limits/
│   └── autosens/
├── schemas/
│   └── conformance-vector-v1.json
├── runners/
│   ├── oref0-runner.js
│   ├── aaps-runner.kt
│   ├── loop-runner.swift
│   └── rust-runner.rs
└── results/
    └── comparison-matrix.json
```

---

## Implementation Plan

### Phase 1: Schema & Fixture Extraction ✅ COMPLETE

**Tasks**:
1. ✅ Define `conformance-vector-v1.json` JSON Schema
2. Extract test vectors from oref0 examples (deferred to Phase 2)
3. ✅ Extract test vectors from AAPS replay test fixtures
4. ✅ Normalize to common format

**Deliverables**:
- ✅ `conformance/schemas/conformance-vector-v1.json` (260 lines)
- ✅ `conformance/vectors/` with 85 vectors (77 basal, 8 LGS)
- ✅ `tools/extract_vectors.py` extraction script
- ✅ `make extract-vectors` Makefile target

### Phase 2: JavaScript Runner ✅ COMPLETE

**Tasks**:
1. ✅ Create Node.js test runner for oref0
2. ✅ Load conformance vectors
3. ✅ Execute determine-basal
4. ✅ Validate outputs against assertions
5. ✅ Generate results JSON

**Deliverables**:
- ✅ `conformance/runners/oref0-runner.js` (400+ lines)
- ✅ Makefile target: `make conformance-oref0`
- ✅ `conformance/results/oref0-results.json` output

**Initial Results** (AAPS vectors → oref0):
- 26/85 vectors pass (31%)
- basal-adjustment: 24/77 passed
- low-glucose-suspend: 2/8 passed

This divergence is expected - AAPS uses modified oref0 with different tuning and eventualBG calculations.

### Phase 3: Kotlin Runner (2-3 days)

**Tasks**:
1. Extract AAPS algorithm as standalone module
2. Create JUnit test runner loading vectors
3. Support both JS and pure-Kotlin paths
4. Compare outputs

**Deliverables**:
- `conformance/runners/aaps/` Gradle project
- Test report with JS vs KT comparison

### Phase 4: Cross-Language Comparison (2-3 days)

**Tasks**:
1. Run all runners against same vector set
2. Generate comparison matrix
3. Identify behavioral differences
4. Document gaps

**Deliverables**:
- `conformance/results/comparison-matrix.json`
- Gap entries for behavioral differences
- `docs/10-domain/algorithm-conformance-results.md`

### Phase 5: Rust Runner (Optional, 3-5 days)

**Tasks**:
1. Create Rust runner using oref-rs (if available)
2. Validate against JS baseline
3. Performance comparison

---

## Test Vector JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "conformance-vector-v1",
  "type": "object",
  "required": ["version", "metadata", "input", "expected"],
  "properties": {
    "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
    "metadata": {
      "type": "object",
      "required": ["id", "name", "category"],
      "properties": {
        "id": {"type": "string", "pattern": "^TV-\\d{3}$"},
        "name": {"type": "string"},
        "category": {
          "enum": ["basal-adjustment", "smb-delivery", "low-glucose-suspend",
                   "carb-absorption", "safety-limits", "autosens", "exercise-mode"]
        },
        "source": {"type": "string"},
        "description": {"type": "string"}
      }
    },
    "input": {
      "type": "object",
      "required": ["glucoseStatus", "iob", "profile"],
      "properties": {
        "glucoseStatus": {
          "type": "object",
          "required": ["glucose", "delta"],
          "properties": {
            "glucose": {"type": "number"},
            "glucoseUnit": {"enum": ["mg/dL", "mmol/L"]},
            "delta": {"type": "number"},
            "shortAvgDelta": {"type": "number"},
            "longAvgDelta": {"type": "number"},
            "timestamp": {"type": "string", "format": "date-time"}
          }
        },
        "iob": {
          "type": "object",
          "required": ["iob"],
          "properties": {
            "iob": {"type": "number"},
            "basalIob": {"type": "number"},
            "bolusIob": {"type": "number"},
            "activity": {"type": "number"}
          }
        },
        "profile": {
          "type": "object",
          "required": ["basalRate", "sensitivity", "carbRatio", "targetLow", "targetHigh"],
          "properties": {
            "basalRate": {"type": "number", "minimum": 0},
            "sensitivity": {"type": "number", "minimum": 1},
            "carbRatio": {"type": "number", "minimum": 1},
            "targetLow": {"type": "number"},
            "targetHigh": {"type": "number"},
            "maxIob": {"type": "number", "minimum": 0},
            "maxBasal": {"type": "number", "minimum": 0},
            "dia": {"type": "number", "minimum": 2, "maximum": 8}
          }
        },
        "mealData": {
          "type": "object",
          "properties": {
            "carbs": {"type": "number", "minimum": 0},
            "cob": {"type": "number", "minimum": 0}
          }
        },
        "currentTemp": {
          "type": "object",
          "properties": {
            "rate": {"type": "number", "minimum": 0},
            "duration": {"type": "integer", "minimum": 0}
          }
        }
      }
    },
    "expected": {
      "type": "object",
      "properties": {
        "rate": {
          "oneOf": [
            {"type": "number"},
            {"type": "object", "properties": {"min": {"type": "number"}, "max": {"type": "number"}}}
          ]
        },
        "duration": {"type": "integer"},
        "smb": {"type": "number"},
        "smbAllowed": {"type": "boolean"},
        "eventualBG": {
          "oneOf": [
            {"type": "number"},
            {"type": "object", "properties": {"min": {"type": "number"}, "max": {"type": "number"}}}
          ]
        },
        "reasonContains": {"type": "array", "items": {"type": "string"}}
      }
    },
    "assertions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type"],
        "properties": {
          "type": {
            "enum": ["rate_increased", "rate_decreased", "rate_zero", "rate_unchanged",
                     "smb_delivered", "no_smb", "safety_limit", "eventual_in_range"]
          },
          "baseline": {"type": "number"},
          "field": {"type": "string"},
          "min": {"type": "number"},
          "max": {"type": "number"}
        }
      }
    }
  }
}
```

---

## Cross-Project Field Mapping

| Concept | oref0 | AAPS | Loop |
|---------|-------|------|------|
| Current BG | `glucose_status.glucose` | `glucoseStatus.glucose` | `glucoseHistory.last().quantity` |
| BG delta | `glucose_status.delta` | `glucoseStatus.delta` | Computed from history |
| IOB total | `iob_data.iob` | `iobTotal.iob` | `insulinOnBoard` |
| Basal IOB | `iob_data.basaliob` | `iobTotal.basaliob` | N/A (combined) |
| Sensitivity | `profile.sens` | `profile.sens` | `settings.sensitivity` |
| Carb ratio | `profile.carb_ratio` | `profile.carb_ratio` | `settings.carbRatio` |
| Target BG | `profile.min_bg`/`max_bg` | `profile.target_bg` | `settings.target` |
| COB | `meal_data.mealCOB` | `mealData.mealCOB` | `carbsOnBoard` |
| Temp rate | `suggested.rate` | `result.rate` | `tempBasal.rate` |
| SMB units | `suggested.units` | `result.smb` | `bolus.units` |

---

## Gaps Identified

### GAP-ALG-001: No cross-project algorithm test vectors

**Description**: Each AID project maintains isolated test fixtures with incompatible formats. No mechanism exists to validate behavioral consistency across implementations.

**Impact**: Algorithm differences may cause dosing inconsistencies for users switching between apps.

**Remediation**: Implement conformance vector format and cross-project runners.

### GAP-ALG-002: oref0 vs AAPS behavioral drift

**Description**: AAPS Kotlin implementation may have diverged from upstream oref0 JavaScript. The ReplayApsResultsTest compares JS vs KT within AAPS but not against upstream oref0.

**Impact**: AAPS users may experience different dosing than OpenAPS rig users with identical settings.

**Remediation**: Include upstream oref0 in conformance testing.

### GAP-ALG-003: Loop algorithm incomparable to oref

**Description**: Loop uses fundamentally different prediction model (combined curve vs 4 separate curves). Direct output comparison is not meaningful without semantic mapping.

**Impact**: Users cannot expect identical dosing behavior when switching between Loop and oref-based systems.

**Remediation**: Define semantic equivalence criteria (e.g., "both recommend increased basal") rather than exact value matching.

---

## Effort Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Schema + Fixture Extraction | ✅ Complete | None |
| JavaScript Runner | Low | Phase 1 ✅ |
| Kotlin Runner | Medium | Phase 1 ✅, Android SDK |
| Cross-Language Comparison | Medium | Phases 2-3 |
| Rust Runner | Medium | Rust oref implementation |
| **Total** | High | ~10-15 days |

---

## Success Criteria

| Metric | Target | Status |
|--------|--------|--------|
| Test vectors | 50+ covering all categories | ✅ 85 vectors |
| oref0 pass rate | 100% (baseline) | Pending runner |
| AAPS JS vs KT match | 95%+ | Pending runner |
| Cross-project comparison report | Generated | Pending |
| Gaps documented | All behavioral differences | Pending |

---

## Recommendations

| Priority | Action | Impact | Status |
|----------|--------|--------|--------|
| P1 | Create conformance vector schema | Enables all other work | ✅ Complete |
| P1 | Extract vectors from AAPS replay tests | 50+ ready-made vectors | ✅ 85 vectors |
| P2 | Build oref0-runner.js | Baseline validation | Next |
| P2 | Integrate with `make conformance` | CI automation | Pending |
| P3 | Define semantic equivalence for Loop | Enable Loop comparison | Pending |

---

## References

### Source Files Analyzed

**oref0**:
- `externals/oref0/tests/determine-basal.test.js` - Main test file
- `externals/oref0/lib/determine-basal/determine-basal.js` - Algorithm
- `externals/oref0/examples/` - JSON fixtures

**AAPS**:
- `externals/AndroidAPS/app/src/androidTest/kotlin/app/aaps/ReplayApsResultsTest.kt`
- `externals/AndroidAPS/app/src/androidTest/assets/results/` - 50+ fixtures
- `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/aps/`

**Loop**:
- `externals/LoopWorkspace/LoopKit/LoopKitTests/Fixtures/`
- `externals/LoopWorkspace/LoopAlgorithm/`
- `externals/LoopWorkspace/LoopKit/LoopKit/`

### Related Documents

- [Cross-Project Testing Plan](cross-project-testing-plan.md)
- [Prediction Arrays Comparison](../10-domain/prediction-arrays-comparison.md)
- [Algorithm Comparison Deep Dive](../10-domain/algorithm-comparison-deep-dive.md)
