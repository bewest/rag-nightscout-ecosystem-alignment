# Carb Absorption Model Comparison

> **Systems Analyzed**: Loop, AAPS, Trio, oref0  
> **Purpose**: Compare carb absorption algorithms across AID systems  
> **Related**: [Algorithm Conformance Suite](../sdqctl-proposals/algorithm-conformance-suite.md)

---

## Executive Summary

The four major open-source AID systems use fundamentally different approaches to carb absorption modeling. Loop uses **predictive curve-based models** that project expected absorption, while oref0/AAPS/Trio use **reactive deviation-based models** that infer absorption from glucose changes.

### Key Findings

| Finding | Impact |
|---------|--------|
| Two paradigms | Predictive (Loop) vs Reactive (oref0/AAPS/Trio) |
| Different COB semantics | Not directly comparable between systems |
| UAM handling differs | Loop uses retrospective correction; oref0 uses explicit detection |
| No standard format | Carb absorption data not interoperable |

---

## Model Paradigms

### Predictive (Loop)

**Approach**: Model expected absorption curve based on carb type/timing, then adjust based on observed glucose effects.

```
Expected Absorption → Glucose Effect Prediction → Comparison with Observed → Adjustment
```

**Advantages**:
- Anticipates absorption before glucose rises
- Multiple curve models available
- Per-entry absorption tracking

**Disadvantages**:
- Sensitive to carb estimation accuracy
- Complex curve fitting

### Reactive (oref0/AAPS/Trio)

**Approach**: Observe glucose deviation from insulin-only prediction, infer carb absorption from the difference.

```
Observed BG - Predicted IOB Effect = Deviation → Infer Carb Absorption
```

**Advantages**:
- Adapts to actual absorption patterns
- Simpler model
- UAM detection built-in

**Disadvantages**:
- Lags actual absorption
- Relies on minimum absorption floor

---

## Loop Carb Absorption

> **Source**: `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/CarbMath.swift`

### Absorption Models

Loop supports three pluggable absorption curves:

#### 1. Linear Absorption

> **Source**: `CarbMath.swift:152-187`

```
Absorption Rate = constant
COB(t) = Carbs × (1 - t/absorptionTime)
```

Simple linear decay over absorption time.

#### 2. Parabolic Absorption (Scheiner GI Curve)

> **Source**: `CarbMath.swift:111-149`

```
0-50% time: Parabolic rise
50-100% time: Reverse parabolic fall
```

Models slower initial absorption, peak in middle, slower tail.

#### 3. Piecewise Linear (Default)

> **Source**: `CarbMath.swift:190-243`

Three phases:
| Phase | Time Range | Behavior |
|-------|------------|----------|
| Rise | 0-15% | Quadratic rise |
| Plateau | 15-50% | Constant rate |
| Fall | 50-100% | Linear decay |

### Dynamic Adaptation

> **Source**: `CarbMath.swift:656-667`

After a standby interval (20% of absorption time), Loop dynamically adjusts absorption rate based on observed glucose effects:

```swift
// CarbMath.swift:657-662
if hasStandbyEnded {
    timeToAbsorbObservedCarbs = observedAbsorption / observedRate
    estimatedTimeRemaining = timeToAbsorbObservedCarbs * (1 - percentAbsorbed)
}
```

### Key Parameters

| Parameter | Default | Source |
|-----------|---------|--------|
| `maximumAbsorptionTimeInterval` | 10 hours | `CarbMath.swift:13` |
| `defaultAbsorptionTime` | 3 hours | `CarbMath.swift:14` |
| `defaultAbsorptionTimeOverrun` | 1.5x | `CarbMath.swift:15` |
| `defaultEffectDelay` | 10 minutes | `CarbMath.swift:16` |

### COB Calculation

> **Source**: `CarbStore.swift:1058-1109`

```swift
// Blend observed timeline with modeled predictions
func dynamicCarbsOnBoard() -> Double {
    // modeled → observed → post-observation projection
}
```

---

## oref0 Carb Absorption

> **Source**: `externals/oref0/lib/determine-basal/`

### Core Algorithm

oref0 infers carb absorption from glucose deviation:

> **Source**: `determine-basal.js:470-486`

```javascript
// Carb Impact from deviation
ci = round((minDelta - bgi), 1);  // line 470

// Carb Sensitivity Factor
csf = sens / profile.carb_ratio;  // line 477

// Cap at max absorption rate (30 g/h)
maxCI = round(maxCarbAbsorptionRate * csf * 5/60, 1);  // line 482
ci = Math.min(ci, maxCI);  // line 485
```

### Minimum Carb Impact Floor

> **Source**: `cob.js:185`

```javascript
var ci = Math.max(deviation, currentDeviation/2, profile.min_5m_carbimpact);
```

The `min_5m_carbimpact` (default 8 mg/dL per 5 min) ensures COB decays even without observed absorption.

### COB Calculation

> **Source**: `lib/meal/total.js:68-69`

```javascript
myMealCOB = Math.max(0, carbs - myCarbsAbsorbed);
mealCOB += myMealCOB;
```

### UAM Detection

> **Source**: `determine-basal.js:535-612`

oref0 detects unannounced meals through deviation slope analysis:

```javascript
// line 535
slopeFromDeviations = Math.min(slopeFromMaxDeviation, -slopeFromMinDeviation/3);

// line 595-600: UAM prediction
predUCIslope = Math.max(0, uci + (UAMpredBGs.length * slopeFromDeviations));
predUCImax = Math.max(0, uci * (1 - UAMpredBGs.length / Math.max(3*60/5, 1)));
predUCI = Math.min(predUCIslope, predUCImax);
```

### carbsReq Calculation

> **Source**: `determine-basal.js:822-894`

```javascript
// line 894: Key formula
carbsReq = (bgUndershoot - zeroTempEffect) / csf - COBforCarbsReq;
```

---

## AAPS Carb Absorption

> **Source**: `externals/AndroidAPS/workflow/src/main/kotlin/app/aaps/workflow/iob/`

### Two Absorption Models

AAPS supports two models via configuration:

#### 1. Linear (Oref1 Default)

Fixed 5-minute impact via `ApsSmbMin5MinCarbsImpact` (default 8.0 mg/dL).

#### 2. Bilinear/Weighted (AAPS Mode)

> **Source**: `CarbsInPastExtension.kt:27`

```kotlin
min5minCarbImpact = t.amount / (maxAbsorptionHours * 60 / 5) * sens / ic
```

Dynamic absorption based on `AbsorptionMaxTime`.

### COB Calculation

> **Source**: `IobCobOrefWorker.kt:216-218`

```kotlin
autosensData.this5MinAbsorption = ci * profile.getIc(bgTime) / sens  // line 216
autosensData.cob = max(previous.cob - autosensData.this5MinAbsorption, 0.0)  // line 218
```

### Key Parameters

| Parameter | Purpose |
|-----------|---------|
| `AbsorptionMaxTime` | Max absorption duration (hours) |
| `ApsSmbMin5MinCarbsImpact` | Minimum 5-min impact (mg/dL) |
| `AbsorptionCutOff` | Oref1 absorption cutoff |

---

## Trio Carb Absorption

> **Source**: `externals/Trio/trio-oref/lib/`

Trio uses the oref0 algorithm with Swift UI wrapper.

### Configuration

> **Source**: `profile/index.js`

| Setting | Default | Purpose |
|---------|---------|---------|
| `min_5m_carbimpact` | 8 mg/dL/5m | Minimum absorption floor |
| `maxCOB` | 120g | Upper limit for COB |
| `maxMealAbsorptionTime` | 6 hours | Carb window lookback |
| `remainingCarbsFraction` | 1.0 | Fraction to assume absorbs |
| `remainingCarbsCap` | 90g | Max remaining carbs |
| `enableUAM` | false | Unannounced meal detection |

### Key Differences from oref0

- Swift-based UI/settings management
- FreeAPS X-derived codebase
- iOS-specific optimizations
- Same core algorithm as oref0

---

## Comparison Matrix

### Model Characteristics

| Aspect | Loop | oref0 | AAPS | Trio |
|--------|------|-------|------|------|
| **Paradigm** | Predictive | Reactive | Reactive | Reactive |
| **Curve Models** | 3 (Linear, Parabolic, Piecewise) | 1 (Linear decay) | 2 (Linear, Bilinear) | 1 (Linear decay) |
| **Dynamic Adjustment** | Per-entry observed rate | Global min floor | Global min floor | Global min floor |
| **UAM Support** | Via retrospective correction | Explicit detection | Explicit detection | Explicit detection |
| **Per-Entry Tracking** | Yes | No (aggregate) | No (aggregate) | No (aggregate) |

### Default Parameters

| Parameter | Loop | oref0 | AAPS | Trio |
|-----------|------|-------|------|------|
| **Default Absorption Time** | 3h | Profile-based | Profile-based | Profile-based |
| **Max Absorption Time** | 10h | 6h | Configurable | 6h |
| **Min 5m Impact** | Curve-based | 8 mg/dL | 8 mg/dL | 8 mg/dL |
| **Max COB** | None | None | None | 120g |

### COB Semantics

| System | COB Meaning |
|--------|-------------|
| **Loop** | Remaining carbs per absorption curve model |
| **oref0** | Entered carbs minus deviation-inferred absorption |
| **AAPS** | Same as oref0 (via IobCobOrefWorker) |
| **Trio** | Same as oref0 (via trio-oref) |

⚠️ **Warning**: COB values are not directly comparable between Loop and oref0-based systems.

---

## Gap Analysis

### GAP-CARB-001: Incompatible COB Semantics

**Description**: Loop's predictive COB differs from oref0's reactive COB, making cross-system comparisons invalid.

**Affected Systems**: All

**Impact**:
- Nightscout displays COB without model context
- Users switching systems see different COB values
- Reports aggregate incompatible metrics

**Example**:
```
Same meal, same time:
- Loop COB: 45g (curve-based projection)
- oref0 COB: 38g (deviation-inferred)
```

**Remediation**: Nightscout should store and display COB with model type annotation.

### GAP-CARB-002: No Standard Absorption Data Format

**Description**: Each system stores carb absorption data differently, preventing interoperability.

**Affected Systems**: All

| System | Storage Format |
|--------|----------------|
| Loop | Per-entry absorption timeline |
| oref0 | Aggregate mealCOB |
| AAPS | autosensData.cob |
| Trio | meal_data.mealCOB |

**Impact**: Cannot replay absorption data across systems.

**Remediation**: Define standard absorption event format for Nightscout.

### GAP-CARB-003: UAM Detection Variance

**Description**: UAM detection algorithms differ, causing inconsistent behavior during unannounced meals.

**Affected Systems**: All

| System | UAM Approach |
|--------|--------------|
| Loop | Retrospective correction (implicit) |
| oref0 | Deviation slope analysis (explicit) |
| AAPS | `enableUAM` constraint |
| Trio | `enableUAM` setting |

**Impact**: Users experience different dosing behavior with identical settings.

**Remediation**: Document UAM behavior differences in user guides.

---

## Formulas Reference

### Carb Sensitivity Factor (CSF)

```
CSF = ISF / CR
```

Where:
- ISF = Insulin Sensitivity Factor (mg/dL per unit)
- CR = Carb Ratio (grams per unit)

### Carb Impact (CI)

**oref0/AAPS/Trio**:
```
CI = max(deviation, deviation/2, min_5m_carbimpact)
```

**Loop**:
```
CI = f(absorption_curve, elapsed_time, total_carbs)
```

### COB Calculation

**oref0**:
```
absorbed = ci * CR / ISF
COB = entered_carbs - sum(absorbed)
```

**Loop**:
```
COB = entered_carbs * (1 - percent_absorbed(curve, time))
```

---

## Nightscout Integration

### Current State

Nightscout displays COB from devicestatus uploads:

```json
{
  "loop": {
    "cob": { "cob": 45.2 }
  },
  "openaps": {
    "suggested": { "COB": 38 }
  }
}
```

### Recommendation

Add model type annotation:

```json
{
  "cob": {
    "value": 45.2,
    "model": "piecewise_linear",
    "source": "loop"
  }
}
```

---

## Recommendations

### For Nightscout

1. **Add COB model annotation** to devicestatus schema
2. **Display model type** in COB visualizations
3. **Avoid aggregating** COB from different model types

### For Algorithm Conformance

1. **Test vectors** should include expected COB at time points
2. **Document model** used for each test vector
3. **Compare** predictive vs reactive under same scenario

### For Users

1. **Understand** your system's absorption model
2. **Don't compare** COB values between Loop and oref0
3. **Adjust** min_5m_carbimpact based on personal absorption patterns

---

## Related Documentation

- [Algorithm Conformance Suite](../sdqctl-proposals/algorithm-conformance-suite.md)
- [Prediction Arrays Comparison](./prediction-arrays-comparison.md)
- [openaps-oref0 Deep Dive](./openaps-oref0-deep-dive.md)
- [Interoperability Spec](../../specs/interoperability-spec-v1.md)

---

*Generated: 2026-01-29 | Sources: Loop LoopKit, oref0 lib/, AAPS workflow/, Trio trio-oref/*
