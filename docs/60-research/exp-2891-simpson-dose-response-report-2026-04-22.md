# EXP-2891 — Simpson-Stratified AID Protection Dose-Response by Lineage

**Date:** 2026-04-22
**Stream:** Simpson-audited lineage comparison
**Status:** Lineage effect is GENUINE (survives aggressiveness
adjustment); three controller families show distinct dose-response
signatures with actionable asymmetries

## 1. Question

EXP-2889 showed oref1 patients receive the most AID protection.
Is this a **lineage** effect (algorithm family) or a confound
from **user aggressiveness** (aggressive setters force any
controller to brake harder)?  Apply Simpson stratification:

- If lineage difference vanishes within aggressiveness tercile →
  confound, report as aggressiveness signal
- If lineage difference survives within tercile → genuine
  algorithm-family signature

## 2. Method

1. Per-patient aggressiveness rank = rank(mean_sched_basal) +
   rank(mean_bolus_4h); tercile-split within cohort
2. Cell-wise mean `aid_protection_severe` for lineage × tercile
3. Kruskal-Wallis within each tercile
4. **Permutation test (n=5 000)** on lineage range of means — shuffle
   lineage labels, recompute max−min
5. **ANCOVA-style residualisation**: OLS of protection on
   aggressiveness; Kruskal on residuals tests lineage effect net
   of aggressiveness

## 3. Results

### 3.1  Pooled by lineage

| Lineage          | n | protection | cf_severe | obs_severe |
| ---------------- | - | ---------- | --------- | ---------- |
| oref1 (modern)   | 9 | **0.668** | 0.965 | 0.298 |
| Loop (iOS)       | 7 | 0.570 | 0.971 | 0.401 |
| oref0 (legacy)   | 3 | 0.411 | 0.847 | 0.435 |
| unknown          | 5 | 0.675 | 0.977 | 0.302 |

### 3.2  Lineage × aggressiveness tercile

| Lineage    | conservative | moderate | aggressive | within-lineage range |
| ---------- | ------------ | -------- | ---------- | -------------------- |
| **Loop**   | 0.486 (n=2) | 0.637 (n=2) | 0.582 (n=3) | 0.15 |
| **oref1**  | 0.635 (n=3) | 0.615 (n=2) | 0.719 (n=4) | 0.10 |
| **oref0**  | **0.125** (n=1) | 0.389 (n=1) | **0.719** (n=1) | **0.59** |

### 3.3  Simpson audit

- **Permutation test** on lineage range of means (max−min):
  observed = 0.263, p_perm = **0.018**.  Lineage effect exceeds 98 %
  of reshuffled-label replicas.
- **ANCOVA residuals**: after removing aggressiveness's linear
  effect, Kruskal on lineage residuals H=8.69, **p=0.034**.

The lineage effect is **not** an aggressiveness confound.  It
survives both permutation and ANCOVA audits.

## 4. Three distinct controller-family signatures

### 4.1  oref1 (Trio / AAPS) — *reliable across the spectrum*

Protection is high regardless of user aggressiveness
(0.63 → 0.72 across terciles).  SMB + dynISF + zero-temp suspension
appear to deliver consistent buffer irrespective of profile choice.
Protection does not penalise conservative users.

### 4.2  Loop (iOS) — *moderate with modest dose-response*

Protection middling at conservative (0.49) and rises modestly
with aggressiveness (0.58).  Per EXP-2885 hidden-leverage finding,
Loop rewards aggressive setters with harder braking.  Users who
tune conservatively receive less protection from Loop than they
would from oref1.

### 4.3  oref0 (legacy OpenAPS) — *aggressive-setting-dependent*

A **huge** within-lineage dose-response (0.13 → 0.72, range 0.59).
Conservative oref0 users receive minimal protection — in our data
the conservative oref0 patient has 12.5 pp protection vs oref1's
63 pp and Loop's 49 pp at the same aggressiveness tier.  Small n
(1 per tercile) → directional signal, but consistent with the
EXP-2885 night-time `ratio=0.748` (oref0 delivers 75 % of
scheduled basal even into hypos).

## 5. Actionable advice

### 5.1  For patients / clinicians

- **Conservative-setting oref0 users**: strongly consider migration
  to AAPS (oref1) or Loop. Settings-and-algorithm interact: a
  conservative oref0 profile yields much less hypo protection than
  the same profile would on a modern engine.
- **Loop users with conservative settings**: protection is roughly
  3-4× that of conservative-oref0 but still the weakest within-Loop
  tier. Dose-response is modest, so tuning more aggressively does
  yield some improvement.
- **oref1 users**: protection is comparatively *setting-independent*.
  This suggests more latitude to tune for TIR without sacrificing
  the hypo buffer.

### 5.2  For open-source AID authors

- **oref0 maintainers**: the conservative-user failure mode is
  real. Adding a zero-temp fallback to the legacy rig, or
  back-porting oref1's enable_smb_after_carbs / safety_auto thresholds,
  would substantially change the conservative-user protection
  profile.
- **Loop contributors**: Loop's dose-response is modest; the
  bottleneck on conservative-user protection is likely the
  suspension-threshold logic rather than setting aggressiveness.
  Worth auditing `suspendThreshold` and `predictionBuffer` behaviour
  for conservative profiles.
- **oref1 (Trio/AAPS)**: protection is broadly delivered regardless
  of aggressiveness. This is the best-in-class pattern.
- **All**: publish protection magnitude as a metric alongside
  severe-hypo rate. The AID is supposed to compress the
  counterfactual distribution, and only the counterfactual
  comparison reveals this.

## 6. Caveats (per the deconfounding toolkit)

- n = 3 oref0 patients (1 per tercile).  Within-lineage
  aggressiveness trends are directional-only; permutation p for
  across-lineage range is p=0.018 but all individual terciles have
  small cell counts.
- "unknown" lineage cohort (n=5) behaves like oref1; they are
  probably AAPS or late-version Trio.  Treating them as a
  separate category is conservative.
- Aggressiveness rank mixes two axes (basal size, bolus-4h size);
  a proper instrument would use TDD or weight-indexed dose.
- Counterfactual ISF = 50 mg/dL/U uniformly.  Per EXP-2890
  robustness audit, ISF choice does not change rank order but
  magnitudes scale with ISF.

## 7. Methodology contribution

EXP-2891 is the template for **technique §2.6 + §2.9 composed**:
apply Simpson stratification to a counterfactual-outcome metric.
Two audits (permutation + ANCOVA) are the minimum evidence bar for
publishing a lineage-effect claim under the deconfounding toolkit's
default-guards.  Retrospectively applying this audit to EXP-2886's
HAAF-feedback narrative (which was rejected by EXP-2887) would
have caught the sampling-noise issue earlier — add this template
to future cross-lineage experiments.

## 8. Next

- **EXP-2892**: per-lineage-and-phenotype controller-tuning map,
  using within-tercile protection as the tuning objective
- **Patient vignette for `ns-8b3c1b50793c`** — the oref1 patient
  with counter_reg_intercept < 0; now embedded in the context of
  oref1's reliable protection (likely that's what's keeping this
  patient safe at all)
- **Dataset-gap flag**: AAPS patients needed to separate "oref1
  algorithm" from "Trio iOS platform"

## 9. Artifacts

- `tools/cgmencode/exp_simpson_dose_response_2891.py`
- `externals/experiments/exp-2891_simpson_dose_response.parquet`
- `externals/experiments/exp-2891_simpson_dose_response_summary.json`
- `docs/60-research/figures/exp-2891_simpson_dose_response.png`
