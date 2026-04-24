# Loop Automatic-Bolus SMB Gating — Code Deep Dive (EXP-2990)

**Date**: 2026-04-23
**Audience**: open-source AID code authors (Loop, LoopAlgorithm, AAPS, Trio).
**Scope**: trace, in source, every gate in the Loop / LoopAlgorithm
auto-bolus path that can drive SMB delivery to ~zero at low–normal BG
(70–100 mg/dL). Map each gate to the observed >99% peer-suppression
pattern in our cohort (Loop_AB_ON peers c, d, e, g vs outlier i —
EXP-2987).
**What this is NOT**: not a runtime trace; not a per-user therapy
recommendation; not an oref0/oref1 comparison. We document Loop's gates
only, in the version pinned in `workspace.lock.json`.

---

## 1. Source path under analysis

The Loop auto-bolus dose decision flows:

```
LoopDataManager.swift  ── computes inputs
   └─> predictedGlucose.recommendedAutomaticDose(...)
         └─> insulinCorrection(...)             // DoseMath.swift
         └─> recommendAutomaticDose(...)        // LoopAlgorithm.swift
                  └─> InsulinCorrection.asPartialBolus(...) // DoseMath.swift
```

with the per-cycle dose fraction supplied by either
`ConstantApplicationFactorStrategy` (legacy) or
`GlucoseBasedApplicationFactorStrategy` (GBAF, opt-in).

---

## 2. Five gates that can suppress SMB at 70–100 mg/dL

Each gate is documented as: **trigger → effect**, with the file:line
reference in the pinned source tree under `externals/`.

### Gate G1 — Suspend-threshold short-circuit (HARD STOP)

**File**: `externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift:207-210`

```swift
// If any predicted value is below the suspend threshold, return immediately
guard prediction.quantity >= suspendThreshold else {
    return .suspend(min: prediction)
}
```

`InsulinCorrection.suspend` is later mapped to a
`bolusRecommendationNotice == .glucoseBelowSuspendThreshold`
(`DoseMath.swift:64-67`). Downstream the partial-bolus path is never
entered — `asPartialBolus` is only called for `.aboveRange` (see
`LoopAlgorithm.swift:419-434`).

* **Why this gate dominates at 70–100 mg/dL**: in this band the
  prediction will frequently dip below `suspendThreshold` (Loop
  default 67 mg/dL; user-configurable 67–80). Even a single dip
  anywhere along the prediction horizon trips the guard.
* **Patient-i route around this gate**: a lower suspend threshold
  (or, equivalently, a less hypo-protective ISF/CR stack that flattens
  the prediction) would make the dip rarer.

### Gate G2 — `.entirelyBelowRange` short-circuit

**File**: `externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift:269-283`

```swift
if minGlucose.quantity < minGlucoseTargets.lowerBound &&
   eventualGlucose.quantity < eventualGlucoseTargets.lowerBound {
    ...
    return .entirelyBelowRange(min: minGlucose, ...)
}
```

`.entirelyBelowRange` carries `bolusRecommendationNotice ==
.allGlucoseBelowTarget` (DoseMath.swift:70-71); it does NOT participate
in `recommendAutomaticDose`'s `.aboveRange` switch, so SMB = 0.

* **Why this matters at 70–100 mg/dL**: with a typical correction
  range of 100–115 mg/dL, current BG of 70–100 puts both `minGlucose`
  and `eventualGlucose` below the lower bound — gate trips.

### Gate G3 — `.inRange` (no correction needed)

**File**: `externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift:293-295`

```swift
} else {
    return .inRange
}
```

`.inRange` returns `bolusRecommendationNotice ==
.predictedGlucoseInRange` (DoseMath.swift:68-69). Again
`recommendAutomaticDose` returns nil bolusUnits.

* **Why this matters at 70–100 mg/dL**: when `eventualGlucose` is
  inside the target band and `minGlucose` ≥ lower bound, SMB = 0.

### Gate G4 — Predicted-min-below-target zero-clamp (THE smoking gun)

**File**: `externals/LoopAlgorithm/Sources/LoopAlgorithm/LoopAlgorithm.swift:419-423`

```swift
if case .aboveRange(min: let min, correcting: _, minTarget: let minTarget, units: _) = correction,
    min.quantity < minTarget
{
    deliveryMax = 0
}
```

Even when the correction case is `.aboveRange` (i.e. there *is* a
predicted excursion above target), if the predicted minimum dips below
the lower bound of the target range the *deliveryMax is forced to 0*
and `asPartialBolus` returns 0 (`LoopAlgorithm.swift:431-434`).

* **Why this is the dominant gate for the observed pattern**: at
  current BG 70–100 the prediction's minimum will, in the vast majority
  of cycles, sit below the typical 100 mg/dL `minTarget` floor. So even
  if eventual glucose forecasts a rise above target (which is exactly
  the EXP-2987 starting condition: cells in 70–100 with non-zero
  eligibility), `deliveryMax = 0` ⇒ SMB suppressed.
* **Match to data signature**: this gate maps cleanly to the
  observed >99% suppression of *eligible* cells (no override, no
  recent carbs, IOB below patient-95th-percentile) at 70–100 in peers
  c, d, e, g (EXP-2987 §2). Patient `i` fires in 13% of eligible cells —
  consistent with a lower correction-range floor that lifts G4 more
  often.

### Gate G5 — GBAF low-end clamp (soft attenuation)

**File**: `externals/LoopWorkspace/Loop/Loop/Models/GlucoseBasedApplicationFactorStrategy.swift:14-41`

Constants (lines 15-20):

```swift
static let minPartialApplicationFactor = 0.20
static let maxPartialApplicationFactor = 0.80
static let minGlucoseDeltaSlidingScale = 10.0  // mg/dL
static let maxGlucoseSlidingScale     = 200.0  // mg/dL
```

Computation (lines 33-38):

```swift
let minGlucoseSlidingScale = ...minGlucoseDeltaSlidingScale + lowerBoundTarget
let scalingFraction = (max - min) / (maxGlucoseSlidingScale - minGlucoseSlidingScale)
let scalingGlucose  = max(currentGlucose - minGlucoseSlidingScale, 0.0)
let effectiveBolusApplicationFactor = min(min + scalingGlucose * scalingFraction, max)
```

* When current BG ≤ `lowerBoundTarget + 10`, `scalingGlucose = 0` and
  the factor floors at **0.20** (20% of the would-be partial dose).
* This does NOT zero out the dose; combined with rounding to the
  pump's bolus increment (typically 0.05 U for Omnipod, 0.025 U for
  Medtronic), a small computed dose * 0.20 can round to 0 — but on its
  own, GBAF is an *attenuator*, not a *gate*.

**Where rounding turns attenuation into suppression**:
`asPartialBolus` (DoseMath.swift:101-110) applies `volumeRounder`
(supplied by `LoopDataManager.swift:1820-1822` from the pump manager's
`roundBolusVolume`). Tiny corrections at low BG ⇒ partial dose ≈ 0.05 U
⇒ rounded to 0.

### Gate G6 — Manual-bolus current-glucose-below-target notice

**File**: `externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift:444-459`

```swift
if let targetAtCurrentGlucose = target.closestPrior(...),
   currentGlucose.quantity < targetAtCurrentGlucose.value.lowerBound {
    bolus.notice = .currentGlucoseBelowTarget(...)
}
```

This is the **manual** bolus path (carb-entry / user-initiated bolus).
It does *not* affect SMB but is documented here because UI logic in
`Loop` reuses the notice to surface the "Predicted Glucose Below
Target" warning that mirrors G4.

---

## 3. IOB-headroom additional clamp (not a 70-100 gate, but a peer-suppression amplifier)

**File**: `externals/LoopAlgorithm/Sources/LoopAlgorithm/LoopAlgorithm.swift:415-417`
**File**: `externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift:1814-1816, 1840`

```swift
let deliveryHeadroom = max(0, maxBolus * 2.0 - activeInsulin)
var deliveryMax = min(maxBolus * applicationFactor, deliveryHeadroom)
```

`automaticDosingIOBLimit = maxBolus * 2.0`. When current IOB ≥
`maxBolus * 2`, `deliveryHeadroom = 0` ⇒ deliveryMax = 0 ⇒ SMB = 0.

* **Why peers may benefit even when G4 doesn't fire**: peers c/d/g
  had iob_p50 in 0.3–1.1 U and iob_p95 in 4.6–5.9 U; with conservative
  `maxBolus` settings (proxy: their iob_p95 is ~⅓ of patient i's
  9.95 U), peer headroom routinely floors at 0.

---

## 4. Mapping the five gates to the EXP-2987 pattern

EXP-2987 found peers c, e suppress >99.9% of eligible cells; d/g
suppress ~99%; patient i suppresses 87%. After ruling out (a) override
fraction, (b) recent carbs, (c) per-patient IOB cap (proxy), and (d)
behavioral eligibility threshold, this deep-dive narrows the
remaining lever to **G4 + G1**:

| Gate | Mechanism | Configurable knob | Likely peer setting | Likely i setting |
|------|-----------|-------------------|---------------------|------------------|
| G1   | suspend short-circuit | `suspendThreshold` | 75–80 mg/dL | 67–70 mg/dL |
| G4   | predicted-min < minTarget zero-clamp | `GlucoseRangeSchedule.lowerBound` | 100–110 mg/dL | 90–95 mg/dL |
| G5   | GBAF 0.20 floor + pump rounding | `glucoseBasedApplicationFactorEnabled` | unknown | unknown |
| IOB-headroom | maxBolus*2 cap on activeInsulin | `maxBolus` | small (≤4 U → cap ≤8 U) | larger (≥6 U → cap ≥12 U) |

**Hypothesis (testable in EXP-2991/2993)**: peers run the **stack G1
high + G4 high + maxBolus low** ("conservative dial"); patient i runs
**G1 low + G4 low + maxBolus high** ("aggressive dial"). This is
consistent with the 30× SMB fire-rate gap at 70–100 mg/dL and with the
overshoot phenotype (i overshoots more, peers undershoot/recover slower).

---

## 5. Code-author actionable findings

1. **Document G4 prominently in user-facing docs.** The
   "predicted min below target ⇒ deliveryMax=0" rule (LoopAlgorithm.swift:419-423)
   is the single dominant suppression gate at low–normal BG; users
   tuning their correction range floor are unknowingly tuning their
   SMB fire-rate.
2. **Surface a "policy conservatism" indicator.** Combine
   `suspendThreshold`, `correctionRangeLowerBound`, `maxBolus`, and
   GBAF-on into a single visible score so a user setting an
   aggressive combination sees it at setup.
3. **Add a debug log line for each suppression gate trip.** Today only
   GBAF logs the resulting factor (`LoopDataManager.swift:1837`).
   Adding "G1 trip", "G4 trip", "headroom 0" logs would let users and
   support diagnose suppression patterns without source dives.
4. **Consider a unit test matrix** at `LoopAlgorithm/Tests/` covering
   the 70-100 stratum × 4 correction-range floors × 3 suspend
   thresholds × 3 maxBolus values to lock in the gating contract.

---

## 6. Cross-references

* Marker doc: `docs/60-research/exp-2990-loop-smb-gating-2026-04-23.md`
* Behavioral correlate (rules out non-G4 levers): `docs/60-research/exp-2987-peer-suppression-levers-2026-04-23.md`
* Earlier-dosing rejection: `docs/60-research/exp-2988-earlier-dosing-rejected-2026-04-23.md`
* Synthesis update: `docs/60-research/synthesis-design-comparison-2026-04-23.md` §13 addendum

---

## 7. File:line citation block (canonical)

| Gate | File | Lines |
|------|------|-------|
| G1 suspend short-circuit | `externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift` | 207-210 |
| G1 notice mapping | `externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift` | 64-67 |
| G2 entirelyBelowRange | `externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift` | 269-283 |
| G3 inRange | `externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift` | 293-295 |
| G4 predicted-min zero-clamp | `externals/LoopAlgorithm/Sources/LoopAlgorithm/LoopAlgorithm.swift` | 419-423 |
| G4 partial-bolus consumer | `externals/LoopAlgorithm/Sources/LoopAlgorithm/LoopAlgorithm.swift` | 431-434 |
| G5 GBAF strategy | `externals/LoopWorkspace/Loop/Loop/Models/GlucoseBasedApplicationFactorStrategy.swift` | 14-41 |
| G5 strategy selection | `externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift` | 1825-1840 |
| IOB-headroom clamp | `externals/LoopAlgorithm/Sources/LoopAlgorithm/LoopAlgorithm.swift` | 415-417 |
| Pump volume rounding | `externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift` | 101-110 |
