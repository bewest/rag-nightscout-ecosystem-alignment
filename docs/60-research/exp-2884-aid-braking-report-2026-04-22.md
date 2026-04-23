# EXP-2884 — AID Basal-Cut Efficacy: Ceiling Saturation

**Date:** 2026-04-22
**Stream:** A + B
**Status:** Complete — CEILING EFFECT CONFIRMED: AID already at full
suspension in ALL TODs during pre-nadir descent

## Question

EXP-2881 revealed a paradox: evening hypos carry +2.85 U total
insulin excess vs rest (bolus +2.25 U, basal +0.15 U/h × some hours +
IOB +0.60 U), yet the descent slope is only 0.13 mg/dL/min faster
than other TODs. Where does the excess effect go?

Candidate hypothesis: AID systems aggressively cut evening basal
during the falling-BG window, absorbing much of the stacking load
and explaining the small descent penalty.

## Method

For each pre-nadir descent event (3,912 events, 31 patients, from
EXP-2881 parquet), compute over the 60-min window ending at nadir:

- `delivery_ratio = actual_basal / sched_basal`
- `basal_attenuation_uh = sched_basal − actual_basal`

Stratify by TOD; Mann-Whitney evening vs rest; per-patient Wilcoxon.

## Result

**VERDICT: SATURATED BRAKING — AID already cuts basal to ZERO
during descent across ALL TODs. No room left for differential
response.**

### Cohort stratum medians

| TOD       | n    | sched (U/h) | actual (U/h) | ratio | cut (U/h) |
|-----------|-----:|------------:|-------------:|------:|----------:|
| night     | 922  | 0.804       | **0.000**    | 0.00  | 0.750     |
| morning   | 1114 | 0.835       | **0.000**    | 0.00  | 0.750     |
| afternoon | 972  | 0.800       | **0.000**    | 0.00  | 0.750     |
| evening   | 904  | 0.950       | **0.000**    | 0.00  | 0.829     |

The critical observation is that **median actual basal during the
60-minute pre-nadir descent is 0.000 U/h in every TOD**. AID systems
(Loop / Trio / OpenAPS / AAPS) all suspend basal completely when BG
is falling toward hypo.

Evening shows marginally higher attenuation (+0.079 U/h) with high
statistical significance (Mann-Whitney p=2.2×10⁻⁶) purely because
the scheduled basal happens to be higher evening (0.95 vs ~0.81 U/h)
— not because AID cuts evening more aggressively; it's at the floor
everywhere.

### Per-patient (n=24)

| Metric                      | Median diff (ev − rest) | Wilcoxon p | Frac evening cuts more |
|-----------------------------|------------------------:|-----------:|-----------------------:|
| delivery_ratio              | +0.000                  | 0.18       | —                      |
| basal_attenuation_uh        | +0.040                  | 0.09       | 54%                    |

Null within-patient — AID responds identically to falling BG across
TODs because it's at the suspension floor in all of them.

## Interpretation

### 1. AID basal-cut is a SATURATED brake, not a graduated control

During pre-nadir descent, AIDs hit the floor (zero basal) regardless
of TOD. The "brake pedal" has no more travel. This is the correct
safety behavior — when BG is falling, cutting basal all the way is
the only defense — but it means:

- Increasing scheduled basal cannot be offset by smarter AID braking
  during a descent event.
- Excess boluses (stacking) are *not* absorbed by additional basal
  cuts — there is no additional cut possible.
- The 0.13 mg/dL/min evening descent penalty (EXP-2881) reflects the
  ~2.85 U excess acting through **IOB**, not through net basal
  delivery.

### 2. Stacking = irrecoverable load

When stacked bolus IOB drives BG down faster than basal suspension
can defend against, hypo is essentially guaranteed. AID ***cannot***
recover: it has no positive action (only delivery cuts), and it's
already at the floor.

**This confirms the hypo-prevention hierarchy:**

1. Prevent stacking (EXP-2881/2882 guidance)
2. Early bolus attenuation (while there's still rising BG to absorb the IOB)
3. Counter-regulation (EXP-2875/2877) — physiological defense

Basal algorithm improvements cannot help once stacking has occurred.

### 3. Re-interpretation of "evening basal elevation"

EXP-2881 reported +0.15 U/h higher scheduled evening basal during
events. EXP-2884 confirms this is purely a **scheduled-profile
observation** — no patient is actually receiving more evening basal
during descent (all are at zero). The +0.15 U/h represents an
*avoidable prescription surplus* but not a contributing factor to
the event itself (which is IOB-driven).

This aligns with EXP-2882 finding: per-patient delta_sched_basal
median = 0.00 U/h. The evening basal excess is subgroup, not
universal, and it doesn't materially worsen the event because AID
cuts anyway.

### 4. Two distinct hypo mechanisms now separable

| Mechanism                  | Evidence                  | Intervention |
|----------------------------|---------------------------|--------------|
| Stacking / excess IOB      | EXP-2881 +2.25 U bolus    | 4h-bolus guard, correction throttle |
| Elevated scheduled basal   | EXP-2881 +0.15 U/h (subgroup) | Per-patient basal trim |
| Counter-reg failure        | EXP-2875/2877 intercept   | Clinical hypo-awareness workup |

These are largely independent (EXP-2882 stack_score ⊥ counter_reg).

## Implications for AID authors

Given the saturation finding, new opportunities:

1. **Pre-emptive bolus attenuation** — add a "stack-aware" gate
   to SMB and correction bolus logic. If 4h-cumulative-bolus >
   patient_p75, increase hypo guard by +10 mg/dL and block new
   correction unless BG truly rising.
2. **Max-negative basal doesn't solve evening hypo** — AID research
   efforts to make basal-cut more responsive (faster zero-temp
   engagement) cannot prevent stacking hypos. The lever is on the
   bolus side.
3. **IOB-based rather than BG-based gates** — when IOB > X × TDD/24,
   raise correction thresholds. Loop's momentum factor moves in this
   direction but could be strengthened.

## Implications for existing-system settings

For Loop/Trio/AAPS users:

- Basal profile flattening/reduction remains valid ONLY for the
  subgroup with elevated scheduled evening basal (EXP-2882 top
  third). For most patients, evening basal is fine and cutting it
  more won't help.
- Evening bolus behavior is the lever. Dinner-correction stacking
  reviews with CDE/endo is the highest-value intervention.

## Implications for two-stream framework

- Stream A confirmation: basal insulin is *not actually delivered*
  during descent — the "insulin input" visible to the closed-loop
  system is ~100% bolus-derived. This strengthens the argument that
  Stream A EGP inferences from closed-loop data must account for
  suspension-floor effects during risk windows (already in charter).
- Stream B confirmation: the actionable signal here is operational
  — `stack_score` + cumulative bolus monitoring, not basal-profile
  adjustments.

## Limitations

- Median actual_basal = 0 could mask distributional differences
  (e.g., evening takes longer to reach 0, or has narrower
  suspension episodes). Hazard analysis (time-to-suspension) is
  follow-up work.
- Pre-nadir descent is the narrow window; full evening window may
  show differential behavior outside the descent.
- Cannot distinguish AID types (Loop's zero temp vs OMNI vs
  OpenAPS's fully zero'd microboluses) at this resolution.

## Next experiments

- **EXP-2885 Time-to-suspension latency** — how quickly does each
  AID reach zero basal after BG turns downward? Loop vs Trio vs
  OpenAPS comparison.
- **EXP-2886 Stack-aware guard simulation** — apply a naive
  stack-guard rule retrospectively to the event set; estimate
  hypos avoided.
- **Patient vignettes for non-stackers** — patient `d` (Loop, −1.75
  U evening delta) needs different guidance than the stacker
  archetypes.

## Files

- `tools/cgmencode/exp_aid_braking_2884.py`
- `externals/experiments/exp-2884_aid_braking.parquet`
- `externals/experiments/exp-2884_aid_braking_summary.json`
- `docs/60-research/figures/exp-2884_aid_braking.png`
