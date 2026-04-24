# SMB Emission Policy — Loop (AB-ON) vs oref1 — Code-side deep dive (2026-04-23)

## Scope
For open-source AID code authors. Ties the **data-side** finding
(EXP-2966 / EXP-2972 / EXP-2973: Loop_AB_ON vs oref1 SMB-emission
behavior in the 70-100 mg/dL no-carb sweet spot) to the **code-side**
mechanisms that produce that behavior. Reads the dosing source files
in both controllers and identifies the specific policy choices that
generate the observed differences.

## What this is NOT
Not therapy advice. Not a fork-recommendation. Not a per-patient
analysis. Not a claim that one policy is safer than the other.

## Audience
Maintainers of LoopWorkspace, AndroidAPS, Trio, oref1/oref0 forks,
and anyone designing an AID controller from scratch.

---

## 1. Data-side facts being explained

| Metric (70-100 mg/dL, no-carb, pooled cells) | Loop_AB_ON | oref1 | Source |
|---|---:|---:|---|
| Cell count | 28,845 | 66,172 | EXP-2972 |
| Emission rate `P(SMB>0 \| cell)` | 0.039 | 0.080 | EXP-2972 |
| Mean per-event SMB (U) | 0.244 | 0.169 | EXP-2972 |
| Mean SMB per cell (U) | 0.0094 | 0.0135 | EXP-2972 |
| Pooled SMB-on-velocity slope | +0.86 | +0.57 | EXP-2966 |
| Per-patient slope median | +0.77 | +0.55 | EXP-2971 |
| Per-patient unanimous direction | 5/5 | 9/9 | EXP-2971 |
| MWU between designs | p=0.30 | — | EXP-2971 |

Velocity-stratified (EXP-2973):

| Stratum | Loop em_rate | oref1 em_rate | Loop mean_em (U) | oref1 mean_em (U) |
|---|---:|---:|---:|---:|
| rising  > +0.5 mg/dL/min | 0.038 | 0.097 | 0.361 | 0.185 |
| stable  ±0.5             | 0.040 | 0.078 | 0.192 | 0.158 |
| falling < −0.5           | 0.035 | 0.048 | 0.228 | 0.239 |

**Headline observations to explain in code:**
1. oref1 fires SMB **roughly twice as often** as Loop in this band
   (pooled), and **modulates emission frequency with velocity**
   (rising 0.097 → falling 0.048).
2. Loop fires **less often** but with **larger per-event size**, and
   **modulates emission magnitude with velocity** (rising 0.361 →
   stable 0.192). Loop's per-cycle emission rate is essentially flat
   across velocity strata (~0.038).
3. Per-patient pictures diverge inside Loop_AB_ON: 4/5 patients almost
   never fire SMB at 70-100 (`em_rate` ≤ 0.0022), while patient `i`
   fires 12.4% of cells. oref1 patients are tightly clustered
   (em_rate 0.008 to 0.144).

---

## 2. Loop AB-ON: the per-cycle SMB mechanism

**Entry point:** `externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift:1818`

```swift
switch settings.automaticDosingStrategy {
case .automaticBolus:
    let applicationFactorStrategy: ApplicationFactorStrategy = UserDefaults.standard.glucoseBasedApplicationFactorEnabled
        ? GlucoseBasedApplicationFactorStrategy()
        : ConstantApplicationFactorStrategy()

    let effectiveBolusApplicationFactor = applicationFactorStrategy.calculateDosingFactor(...)

    // L1840
    let maxAutomaticBolus = min(iobHeadroom, maxBolus! * min(effectiveBolusApplicationFactor, 1.0))

    dosingRecommendation = predictedGlucose.recommendedAutomaticDose(
        ...
        maxAutomaticBolus: maxAutomaticBolus,
        partialApplicationFactor: effectiveBolusApplicationFactor * self.timeBasedDoseApplicationFactor,
        ...
    )
```

**Per-cycle SMB amount:** `externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift:101-110`

```swift
public func asPartialBolus(
    partialApplicationFactor: Double,
    maxBolusUnits: Double,
    volumeRounder: ((Double) -> Double)? = nil
) -> Double {
    let partialDose = units * partialApplicationFactor
    return Swift.min(Swift.max(0, volumeRounder?(partialDose) ?? partialDose),
                     volumeRounder?(maxBolusUnits) ?? maxBolusUnits)
}
```

Where `units` is the full insulin correction needed by the
predicted-glucose curve (essentially `(predictedBG − target) / ISF`,
with carb-effect & momentum already folded into `predictedGlucose`).

**Application factor — Constant strategy (default):** 0.4 (40% of
correction per cycle).

**Application factor — GBAF strategy:** `GlucoseBasedApplicationFactorStrategy.swift`

```swift
static let minPartialApplicationFactor = 0.20
static let maxPartialApplicationFactor = 0.80
static let minGlucoseDeltaSlidingScale = 10.0  // mg/dL above lower target
static let maxGlucoseSlidingScale = 200.0      // mg/dL
```

→ At BG 70-100 mg/dL with a typical lower target of 100, GBAF clamps
to its **floor of 0.20** because `currentGlucose <
minGlucoseSlidingScale = lowerTarget + 10`. (Below
`minGlucoseSlidingScale` the sliding term is zero.)

**Cycle gate:** Loop runs the dosing decision once per CGM cycle
(~5 min). There is **no SMBInterval-style inter-event gating** in
the dosing path; if a non-zero `partialDose` survives `volumeRounder`
each cycle, it is delivered.

**The "implicit gate" that explains low Loop em_rate at 70-100:**
- At BG 90 mg/dL with target 100 mg/dL: `units = (90 − 100) / ISF`
  is negative → clamped to 0. **No SMB.**
- At BG 99 mg/dL with target 100 mg/dL: `units ≈ 0` → SMB rounded
  down to 0. **No SMB.**
- For BG to drive SMB at 70-100, the *predicted* eventual BG must
  exceed target — i.e. positive momentum or net carb-effect. That is
  why **Loop's per-event SMB at 70-100 is large when it fires (the
  model predicts a meaningful overshoot) but rare**.

---

## 3. oref1: the per-cycle SMB mechanism

**Gate:** `externals/AndroidAPS/plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/DetermineBasalSMB.kt:66-103`

```kotlin
fun enable_smb(profile: OapsProfile, microBolusAllowed: Boolean,
               meal_data: MealData, target_bg: Double): Boolean {
    if (!microBolusAllowed) return false
    if (profile.enableSMB_always) return true
    if (profile.enableSMB_with_COB && meal_data.mealCOB != 0.0) return true
    if (profile.enableSMB_after_carbs && meal_data.carbs != 0.0) return true
    if (profile.enableSMB_with_temptarget && profile.temptargetSet && target_bg < 100) return true
    return false  // disabled
}
```

In a no-carb cell, the only routes to `true` are:
- `enableSMB_always = true` (user opt-in), or
- low temp-target active (target < 100).

This is why `oref0`-pattern patients (`odc-...`) fire 0 SMB events at
70-100 no-carb in our data — their profiles do not have
`enableSMB_always`.

**Per-cycle SMB sizing (DetermineBasalSMB.kt:1052-1107):**

```kotlin
if (microBolusAllowed && enableSMB && bg > threshold) {
    val maxBolus = if (iob > mealInsulinReq && iob > 0)
        round(profile.current_basal * profile.maxUAMSMBBasalMinutes / 60, 1)
    else
        round(profile.current_basal * profile.maxSMBBasalMinutes / 60, 1)

    val roundSMBTo = 1 / profile.bolus_increment
    val microBolus = floor(min(insulinReq / 2, maxBolus) * roundSMBTo) / roundSMBTo

    ...

    val SMBInterval = min(10, max(1, profile.SMBInterval)) * 60.0  // seconds
    if (lastBolusAge > SMBInterval - 6.0) {
        if (microBolus > 0) { rT.units = microBolus }
    } else {
        // wait
    }
}
```

`SMBDefaults` (`externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/aps/SMBDefaults.kt`):

```kotlin
const val SMBInterval = 3                   // minimum 3 min between SMBs
const val maxSMBBasalMinutes = 30           // SMB ≤ 30 min of basal (with COB)
const val maxUAMSMBBasalMinutes = 30        // SMB ≤ 30 min of basal (UAM)
```

**Per-event size:** `min(insulinReq / 2, basal * 30/60)` rounded to
bolus increment.

- For a typical basal of 1.0 U/hr: per-event SMB ≤ 0.5 U.
- The `/ 2` halving makes oref1's per-event sizes **systematically
  half** of what Loop would emit for the same `insulinReq`, and the
  data confirm: oref1 mean_emission 0.169 U vs Loop 0.244 U.

**Threshold gate:** `bg > threshold` where `threshold` is a low-end
guard near suspend threshold. At 70-100 mg/dL this is satisfied
(threshold typically 60-80) so the SMB block is reachable.

---

## 4. Mapping data findings → code-side mechanisms

### Finding A — oref1 fires ~2× more often than Loop at 70-100 no-carb
**Code mechanism:** different "implicit gates":
- **Loop:** the gate is `(predictedBG − target) > 0` and
  `partialDose > volumeRounder.minimum`. With BG ≤ 100 and target
  ≈ 100, the predicted overshoot must be large to clear the rounder.
- **oref1:** once `enable_smb()` returns true, **every 3-min eligible
  cycle** that has positive `insulinReq` (driven by IOB-momentum
  prediction) and survives the 0.05U/0.1U rounder produces an SMB.
  oref1's `insulinReq` uses `naive_eventualBG` which can be > target
  even when current BG is below it (slow-rising IOB-deficit path).

### Finding B — Loop's per-event SMB is ~44% larger than oref1's
**Code mechanism:**
- **Loop:** `partialDose = units × 0.4` (constant) or up to ×0.8
  (GBAF at high BG). At 70-100 GBAF floors to 0.2 — so the multiplier
  is 0.20-0.40.
- **oref1:** `microBolus = insulinReq / 2 = 0.5`.

For the **same** `insulinReq`, oref1 delivers 0.5×, Loop AB-ON
delivers 0.2-0.4×. The data shows Loop's per-event median *higher*
because Loop only fires when `units` is already large (the implicit
gate filters out small corrections). oref1 fires across a wider
range of `insulinReq` and therefore averages smaller per-event size.

### Finding C — Loop modulates SMB **magnitude** with velocity; oref1 modulates **frequency** (EXP-2973)
**Code mechanism:**
- **Loop's `units`** is computed from the entire `predictedGlucose`
  curve, which integrates carb effect, insulin effect, and **glucose
  momentum** (the recent slope). Rising velocity makes the predicted
  overshoot larger → larger `units` → larger `partialDose`. The
  emission decision (whether the rounded dose is non-zero) only flips
  near the `bolus_increment` boundary, so the rate is nearly flat
  across velocity strata.
- **oref1's `insulinReq`** also uses momentum (via
  `naive_eventualBG`) but the per-event size is capped at `insulinReq
  / 2`. The dominant velocity sensitivity comes from the **gating**
  side: `naive_eventualBG > target` is required for `insulinReq > 0`;
  on a falling curve `naive_eventualBG` is below target → `insulinReq
  ≤ 0` → no microBolus this cycle. Hence falling cells halve the
  emission rate (0.097 → 0.048) but the per-event size is roughly
  unchanged.

### Finding D — Loop_AB_ON per-patient bimodality (EXP-2972)
**Code mechanism:** sensitivity to `maxBolus` user setting and the
GBAF/Constant choice. With Constant 0.4 and a small `maxBolus` (e.g.
2 U), `maxAutomaticBolus = min(2·2 − IOB, 2·0.4) = 0.8 U` — but
the dose is also gated by `volumeRounder` (typically 0.05 U
increment), and most importantly by **`units > 0`**. Patients whose
prediction model rarely sees a meaningful overshoot at BG 70-100
(e.g. tight target, fast carb-effect decay) will see Loop emit zero
SMB nearly always. Patient `i`'s 12% emission rate suggests either
(a) higher target with more frequent overshoot prediction, or
(b) chronically positive momentum at this BG range. **The Loop
pipeline has no equivalent of `enableSMB_always` to force emission
in the absence of a positive prediction.**

---

## 5. AID-author lever priority (revised)

In priority order for tuning per-cycle SMB behavior in the
70-100 mg/dL band:

1. **Cycle-frequency ceiling** — oref1 has explicit `SMBInterval`
   (default 3 min). Loop has no inter-bolus interval; the only
   ceiling is the 5-min cycle. **Most impactful single knob.**
2. **Enable-gate policy (no-carb regime)** — oref1 requires
   `enableSMB_always` or a low temp-target to fire SMB without COB.
   Loop has no such gate; it fires whenever the prediction shows
   overshoot. **Determines whether SMB participates at all in
   no-carb periods.**
3. **Per-event multiplier** — Loop: `partialApplicationFactor`
   (0.4 constant or 0.20-0.80 GBAF). oref1: hard-coded 0.5 of
   `insulinReq`. **Determines per-event magnitude conditional on
   firing.**
4. **maxSMB cap** — Loop:
   `maxBolus × partialApplicationFactor`, with IOB headroom
   `2·maxBolus − IOB`. oref1: `current_basal × maxSMBBasalMinutes/60`.
   **Limits worst-case single-cycle dose.**
5. **Prediction integration of momentum** — both designs fold
   recent BG slope into the per-cycle dose. Loop folds it into
   `units` (magnitude); oref1 folds it into `naive_eventualBG`
   (gating).

For a controller author who wants to **emit-often-with-small-doses**
(oref1 style): set `SMBInterval = 3` and a low-`maxSMBBasalMinutes`
cap. For **emit-seldom-with-larger-doses** (Loop AB-ON style): set
no inter-event gate and apply a per-cycle factor of 0.2-0.4.

---

## 6. Open follow-ups

- The 4/5 Loop_AB_ON patients with em_rate ≈ 0 at 70-100 may have
  GBAF disabled (Constant 0.4) plus a high target. Confirming would
  require per-patient settings export, not currently in our parquet.
- Loop's per-cycle SMB conditional-on-firing distribution should be
  inspected for clipping at `maxAutomaticBolus`; if so, the
  per-event mean we measure is left-truncated.
- oref1 falling-stratum em_rate 0.048 vs stable 0.078 — is the drop
  from `insulinReq ≤ 0` (gating) or from `microBolus < bolus_increment`
  (rounding-out)? A trace of `insulinReq` distribution per stratum
  would disambiguate.

## Provenance
- Loop / LoopAlgorithm: `externals/LoopWorkspace/Loop/`,
  `externals/LoopAlgorithm/Sources/`
- AAPS / oref1: `externals/AndroidAPS/plugins/aps/src/main/kotlin/`,
  `externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/aps/SMBDefaults.kt`
- Date: 2026-04-23
- Companion data reports: EXP-2966, EXP-2971, EXP-2972, EXP-2973,
  EXP-2975
