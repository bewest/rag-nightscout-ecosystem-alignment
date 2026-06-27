# Autosens and Dynamic ISF Comparison

**Date:** 2026-01-29  
**Status:** Complete  
**Type:** Cross-controller analysis

## Overview

This document compares how AID systems dynamically adjust insulin sensitivity based on observed glucose behavior. Each system uses different approaches to detect and compensate for changes in insulin sensitivity.

## Terminology Mapping

| Concept | oref0/AAPS | Loop | Description |
|---------|------------|------|-------------|
| Sensitivity adjustment | Autosens | Retrospective Correction | Adjusts for sensitivity changes |
| Detection window | 8h / 24h | 30min (standard) / 180min (integral) | Time horizon |
| Output | sensitivityRatio (0.7-1.2) | Glucose correction effect | How result is applied |
| Dynamic ISF | Dynamic ISF option | Glucose-based application factor | BG-dependent ISF |

---

## oref0/oref1 Autosens

**Source:** `externals/oref0/lib/determine-basal/autosens.js:11-200`

### Algorithm

Autosens detects sensitivity changes by analyzing **deviations** between expected and actual glucose over 24 hours.

```javascript
function detectSensitivity(inputs) {
    // Use last 24h of data
    var lastSiteChange = new Date(Date.now() - (24 * 60 * 60 * 1000));
    
    // Bucket glucose data into 5-min intervals
    // Calculate deviation = actual_delta - expected_delta
    // expected_delta = BGI (from insulin) + carb_effect
    
    // Compute median of deviations
    var pSensitive = percentile(deviations, 0.50);
    var pResistant = percentile(deviations, 0.50);
    
    // Calculate ratio
    var ratio = 1 + basalOff / profile.max_daily_basal;
}
```

### Key Characteristics

| Aspect | Value |
|--------|-------|
| Detection window | 24 hours (can reset on site change) |
| Method | Median of deviations |
| Output | `sensitivityRatio` (typically 0.7-1.3) |
| Application | Multiplies ISF and basal rate |
| Limits | `autosens_min` (0.7) to `autosens_max` (1.2) |

### Deviation Calculation

```javascript
// For each 5-min interval:
deviation = actual_glucose_change - expected_glucose_change
expected = BGI (insulin effect) + carb_absorption_effect
```

---

## AAPS Sensitivity Plugins

**Source:** `externals/AndroidAPS/plugins/sensitivity/src/main/kotlin/app/aaps/plugins/sensitivity/`

AAPS offers multiple sensitivity algorithms as plugins:

### SensitivityOref1Plugin

**Source:** `SensitivityOref1Plugin.kt:57-207`

Uses 8h and 24h windows, selects whichever shows more sensitivity:

```kotlin
// Two detection windows
val hoursDetection = listOf(8.0, 24.0)
val deviationCategory = listOf(96.0, 288.0)  // 96 = 8h/5min, 288 = 24h/5min

// Collect deviations, reset on site change or profile switch
if (siteChanges.isTherapyEventEvent5minBack(autosensData.time)) {
    deviationsArray.clear()
}

// Use median (50th percentile)
val pSensitive = Percentile.percentile(deviations, 0.50)
val pResistant = Percentile.percentile(deviations, 0.50)

// Calculate ratio
val ratio = 1 + basalOff / profile.getMaxDailyBasal()

// Use 8h if more sensitive than 24h
if (ratioArray[0] < ratioArray[1]) key = 0
```

### SensitivityAAPSPlugin

Uses weighted average approach rather than percentiles.

### SensitivityWeightedAveragePlugin

Weights recent deviations more heavily than older ones.

### Key Characteristics

| Plugin | Window | Method | Use Case |
|--------|--------|--------|----------|
| Oref1 | 8h or 24h | Median | Default for oref1 |
| AAPS | 24h | Weighted | Alternative |
| Weighted Average | Configurable | Time-weighted | Custom needs |

---

## Loop Retrospective Correction

**Source:** `externals/LoopWorkspace/LoopKit/LoopKit/RetrospectiveCorrection/`

Loop uses **Retrospective Correction (RC)** rather than adjusting sensitivity directly.

### Standard Retrospective Correction

**Source:** `StandardRetrospectiveCorrection.swift:17-71`

```swift
public class StandardRetrospectiveCorrection: RetrospectiveCorrection {
    public static let retrospectionInterval = TimeInterval(minutes: 30)
    
    public func computeEffect(...) -> [GlucoseEffect] {
        // Get most recent discrepancy
        let currentDiscrepancyValue = currentDiscrepancy.quantity.doubleValue(for: unit)
        
        // Calculate velocity (mg/dL per second)
        let velocity = currentDiscrepancyValue / discrepancyTime
        
        // Apply decay effect over effectDuration
        return startingGlucose.decayEffect(atRate: velocity, for: effectDuration)
    }
}
```

**Characteristics:**
- **Window:** 30 minutes
- **Method:** Proportional (P) controller
- **Output:** Glucose correction effect added to prediction
- **Behavior:** Decaying effect from current discrepancy

### Integral Retrospective Correction (IRC)

**Source:** `IntegralRetrospectiveCorrection.swift:18-75`

```swift
public class IntegralRetrospectiveCorrection: RetrospectiveCorrection {
    public static let retrospectionInterval = TimeInterval(minutes: 180)
    
    // PID controller gains
    static let currentDiscrepancyGain: Double = 1.0
    static let persistentDiscrepancyGain: Double = 2.0
    static let correctionTimeConstant: TimeInterval = TimeInterval(minutes: 60.0)
    static let differentialGain: Double = 2.0
    
    // Integral forgetting factor
    static let integralForget: Double = exp(-delta.minutes / correctionTimeConstant.minutes)
}
```

**Characteristics:**
- **Window:** 180 minutes (3 hours)
- **Method:** PID controller (proportional-integral-derivative)
- **Output:** Glucose correction effect with memory
- **Behavior:** Accumulates correction for persistent errors

---

## Comparison Matrix

| Aspect | oref0/AAPS Autosens | Loop Standard RC | Loop Integral RC |
|--------|---------------------|------------------|------------------|
| **Window** | 8h / 24h | 30 min | 180 min |
| **Method** | Median deviations | P controller | PID controller |
| **Output** | sensitivityRatio (0.7-1.3) | Glucose effect (mg/dL) | Glucose effect (mg/dL) |
| **Application** | Multiplies ISF, basal | Adds to prediction | Adds to prediction |
| **Memory** | Full window | None (current only) | Integral accumulates |
| **Reset trigger** | Site change, profile switch | N/A | N/A |
| **BG floor** | Ignores positive dev if BG<80 | N/A | N/A |

---

## Dynamic ISF

### oref1 Dynamic ISF

Dynamic ISF adjusts sensitivity based on current BG level (higher BG = lower sensitivity):

```
Dynamic ISF = Profile ISF × (BG / target) ^ adjustmentFactor
```

This allows more aggressive correction at high BG levels.

### Loop Glucose-Based Application Factor

Loop has experimental support for glucose-based sensitivity adjustment:

**Source:** `GlucoseBasedApplicationFactorSelectionView.swift`

Similar concept: adjust correction strength based on current glucose.

---

## Why Autosens and Autotune Do Not Work Consistently for Groups

We now have a reasonable basis for saying that inconsistency is structural, not just anecdotal.

### 1. Autosens only uses surviving non-excluded data

`oref0-detect-sensitivity.js` requires enough glucose data and explicitly compares an 8-hour and 24-hour pass over **non-excluded** intervals, then keeps the lower ratio (`externals/oref0/bin/oref0-detect-sensitivity.js:46-50,113-130`). In practice, different users and cohorts contribute very different amounts of:

- fasting or between-meal windows
- post-site-change data
- carb-free intervals
- UAM-free intervals

That means two people with similar physiology can feed autosens very different evidence sets.

### 2. Meal and UAM exclusion is a major source of selection bias

`oref0/lib/determine-basal/autosens.js` skips data when carbs, COB, or UAM-style absorption are active (`externals/oref0/lib/determine-basal/autosens.js:67-83`). This makes autosens more stable for an individual loop, but less comparable across groups because:

- some users log carbs reliably and lose many windows
- some users do not log meals and are filtered differently
- some controllers generate more residual meal-like deviation than others

The result is a cohort comparability problem, not only an estimation problem.

### 3. Autotune is bounded heuristic optimization, not causal identification

The oref0 autotune core applies a set of bounded, practical heuristics:

- DIA and peak only move if adjacent candidates beat the current setting by about 1% on both mean and RMS deviation (`externals/oref0/lib/autotune/index.js:58-98,102-138`)
- carb ratio is aggregated from meal-labeled windows using total carbs divided by total implied insulin (`externals/oref0/lib/autotune/index.js:143-168`)
- basal changes only apply **20%** of the needed correction and are then clamped by `autosens_min` / `autosens_max` (`externals/oref0/lib/autotune/index.js:234-246`; AAPS port mirrors this in `externals/AndroidAPS/plugins/aps/src/main/kotlin/app/aaps/plugins/aps/autotune/AutotuneCore.kt:193-247`)

These are sensible safety heuristics. They are not proof that the tuned parameters are portable or physiologically correct across groups.

### 4. Controller-mediated feedback remains the dominant confound

Our workspace research already shows why this matters:

- controller compensation dominates the observational signal for ISF and CR comparisons
- removing the apparent safety margin can worsen TBR materially
- the most actionable signals are often controller-operating parameters, not pure physiology

So a tuned parameter can be **useful** without being a universal truth. That distinction matters when discussing groups.

---

## Why Our Decision Support and Settings Extraction Tools May Be Authentically Useful

Yes, we have a reasonable basis, but it is narrower and more defensible than claiming universal autotune correctness.

### What the workspace supports today

1. **Controller-aware usefulness** rather than raw physiological truth  
   The best outputs are recommendations that remain safe and interpretable after controller action is accounted for.

2. **Actionable basal guidance**  
   Personalized-EGP and per-period decomposition work improved basal calibration materially in our research line and now maps cleanly into staged titration plans.

3. **Bounded ISF guidance**  
   Correction-denominator and controller-aware framing appear useful for recommendation ranking, even though direct physiological ISF recovery remains accuracy-limited.

4. **Traceable caution on carb ratio**  
   The current workflow explicitly marks meal-announcement-dependent CR support as provisional.

### What is still needed

| Topic | What is needed |
|------|-----------------|
| **Autosens / Autotune discussion** | controller-aware, cohort-level validation instead of only internal fit or single-user success stories |
| **Decision support usefulness** | evaluation against held-out safety endpoints plus stratified controller-state audits |
| **Settings extraction usefulness** | explicit separation between controller operating parameters and physiological parameters |
| **CR usefulness** | a meal-independent proxy before CR can be considered promotion-ready |

In short: we have a credible basis for discussing **why** autosens/autotune can be inconsistent across groups, and a credible basis for saying our tools may be useful. But the strongest claim we can defend today is:

> our tools are most promising when they are framed as **controller-aware decision support** with explicit safety validation, not as universal physiological autotuning.

---

## Gaps Identified

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

**Description:** Loop doesn't have direct ISF/basal multiplier like Autosens.

**Source:** Loop architecture uses prediction adjustments, not parameter modification.

**Impact:** Users switching from AAPS to Loop may miss Autosens-like behavior.

**Remediation:** Explain that IRC provides similar long-term adaptation.

### GAP-SENS-004: Dynamic ISF Not Standardized

**Description:** Dynamic ISF implementations vary between oref1 and Loop experimental features.

**Source:** 
- oref1: `adjustmentFactor` config
- Loop: `GlucoseBasedApplicationFactorSelectionView.swift`

**Impact:** Different aggression at high BG levels.

**Remediation:** Document formula differences.

### GAP-SENS-005: No controller-aware cohort validation for autosens/autotune

**Description:** Autosens and autotune tune operating parameters from observational data, but the ecosystem lacks a shared controller-aware validation method showing that those tuned outputs remain useful across heterogeneous cohorts.

**Impact:** Group-level inconsistency can be mistaken for algorithm failure or, conversely, single-user success can be over-generalized.

**Remediation:** Validate tuned outputs against held-out safety outcomes and controller-state-stratified audits.

---

## Nightscout Visibility

### AAPS → Nightscout

Autosens ratio reported in devicestatus:
```json
{
  "openaps": {
    "suggested": {
      "sensitivityRatio": 0.95
    }
  }
}
```

### Loop → Nightscout

Retrospective correction not directly visible in devicestatus.
Total effect may be in `loop.predicted` but not itemized.

---

## Source File References

| Project | File | Key Lines |
|---------|------|-----------|
| oref0 | `lib/determine-basal/autosens.js` | 11-200 |
| AAPS | `plugins/sensitivity/SensitivityOref1Plugin.kt` | 57-207 |
| AAPS | `plugins/sensitivity/SensitivityAAPSPlugin.kt` | - |
| Loop | `RetrospectiveCorrection/StandardRetrospectiveCorrection.swift` | 17-71 |
| Loop | `RetrospectiveCorrection/IntegralRetrospectiveCorrection.swift` | 18-75 |

---

## Related Documents

- `docs/10-domain/algorithm-comparison-deep-dive.md` - Algorithm overview
- `docs/10-domain/bolus-wizard-formula-comparison.md` - ISF usage in bolus
- `docs/10-domain/profile-schema-alignment.md` - ISF schedule storage

---

## Conformance Assertions

The following conformance assertions cover sensitivity adjustment documentation requirements:

| Assertion File | Requirements | Assertions |
|----------------|--------------|------------|
| `conformance/assertions/algorithm-docs.yaml` | REQ-SENS-001, REQ-SENS-002, REQ-SENS-003 | 7 |

**Key Assertions**:
- `doc-sens-001`: AAPS autosens ratio multiplier documentation
- `doc-sens-002`: Loop RC prediction effect documentation
- `doc-sens-004`: AAPS devicestatus sensitivityRatio field
- `doc-sens-006`: AAPS 8-24 hour detection window documentation

See `traceability/domain-matrices/aid-algorithms-matrix.md` for full coverage matrix.
