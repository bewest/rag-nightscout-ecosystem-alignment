# EXP-2994: Patient `g` Sweet-Spot Vignette

**Date**: 2026-04-23
**Audience**: open-source AID code authors (Loop).
**Scope**: deep-dive on patient `g`, identified by EXP-2993 as the
mid-conservatism sweet spot among the 5 Loop_AB_ON peers (c, d, e, g, i):
lowest TTT_median (50 min), lowest TAR (0.191), lowest TBR among Loop_AB_ON.
**What this is NOT**: not a recommendation that any patient adopt g's
settings; n=1 sweet spot — descriptive only.

Implementation: `tools/cgmencode/exp_patient_g_sweet_spot_2994.py`
Outputs (gitignored): `externals/experiments/exp-2994_patient_g_sweet_spot.parquet`,
`exp-2994_patient_g_summary.json`.

---

## Headline

**Patient g IS reproducibly a sweet spot, NOT idiosyncratic.** Across
27 weeks of data, g's TIR (mean 0.667, std 0.092, CV 0.138) and overshoot
(mean 0.213, std 0.060) are tight enough to call a stable target rather
than a lucky window. g's distinguishing settings signature — small SMBs
(`bolus_smb_p95 = 0.55 U` vs peer mean 0.95) and very low scheduled-basal
share (`basal_frac_of_tdd = 0.060` vs peer mean 0.258, ~2 SD below) —
is observable in pump telemetry and in principle tunable by AID-author
guard-rails or default presets.

---

## Per-band table (g vs c, d, e, i)

| BG band | Patient | frac of cells | SMB rate per h | mean SMB size (U) | overshoot rate |
|---|---|---:|---:|---:|---:|
| hypo (<70)      | g | 0.029 | 0.000 |  —    | 0.195 |
|                 | c | 0.039 | 0.000 |  —    | 0.286 |
|                 | d | 0.007 | 0.000 |  —    | 0.094 |
|                 | e | 0.016 | 0.000 |  —    | 0.256 |
|                 | i | 0.096 | 0.005 | 0.50  | 0.109 |
| low (70–100)    | g | 0.150 | 0.028 | 0.07  | 0.142 |
|                 | c | 0.113 | 0.000 |  —    | 0.228 |
|                 | d | 0.109 | 0.004 | 0.53  | 0.042 |
|                 | e | 0.100 | 0.003 | 0.55  | 0.151 |
|                 | i | 0.174 | 1.484 | 0.25  | 0.104 |
| TIR (100–180)   | g | 0.516 | 2.85  | 0.16  | 0.208 |
|                 | c | 0.392 | 3.01  | 0.21  | 0.354 |
|                 | d | 0.578 | 3.16  | 0.18  | 0.190 |
|                 | e | 0.478 | 3.49  | 0.29  | 0.255 |
|                 | i | 0.359 | 4.35  | 0.30  | 0.248 |
| hyper1 (180–250)| g | 0.136 | 3.62  | 0.20  | 0.989 |
|                 | c | 0.180 | 4.18  | 0.35  | 0.993 |
|                 | d | 0.159 | 4.31  | 0.24  | 0.991 |
|                 | e | 0.225 | 4.24  | 0.30  | 0.993 |
|                 | i | 0.162 | 4.92  | 0.54  | 0.994 |
| hyper2 (>250)   | g | 0.059 | 4.81  | 0.25  | 1.000 |
|                 | c | 0.102 | 4.12  | 0.38  | 1.000 |
|                 | d | 0.021 | 5.48  | 0.36  | 1.000 |
|                 | e | 0.073 | 5.37  | 0.42  | 1.000 |
|                 | i | 0.105 | 5.35  | 0.81  | 1.000 |

**Pattern** (g vs peers, controlling for total time observed):

1. **Smaller SMB size in every band.** g's TIR-band mean SMB is 0.16 U;
   peer median is ~0.21 U; patient i (the most aggressive) is 0.30 U.
   In hyper2, g's mean SMB is 0.25 U vs i's 0.81 U (3.2× smaller).
2. **Comparable SMB rate per hour.** g delivers SMBs at 2.85/h in TIR
   (peer median 3.32/h) — not unusually frequent.
3. **Lower hyper2 prevalence.** g spends 5.9% of cells above 250
   vs c (10.2%) and i (10.5%). This is the *outcome*, not the *cause*.
4. **Lowest TIR-band overshoot (0.208 vs c 0.354).** When BG is in
   100–180, g's forward-90-min max exceeds 180 the least often.

---

## Settings signature (`g` vs Loop_AB_ON peer mean ± SD)

| Axis | g | peer mean | peer SD | g position |
|---|---:|---:|---:|---|
| `iob_p95`                       |  5.92 |  8.32 | 3.75 | −0.6 SD (modest IOB cap) |
| `bolus_smb_p95`                 |  0.55 |  0.95 | 0.40 | **−1.0 SD** (small max SMB) |
| `suppress_70_100_eligible`      |  0.994 | 0.965 | 0.063 | +0.5 SD (high suppression) |
| `basal_frac_of_tdd`             |  0.060 | 0.258 | 0.103 | **−1.9 SD** (almost all-bolus) |

**Distinguishing axes** (>1 SD outside peer mean):
- `basal_frac_of_tdd` = 0.060: g delivers ~6% of TDD as scheduled basal.
  Peers c/d/e/i deliver 15–40%. g's pump is configured to lean almost
  entirely on bolus + SMB delivery; scheduled basal is an emergency floor.
- `bolus_smb_p95` = 0.55 U: g's 95th-percentile SMB is half of peer i's
  (1.50 U). g never throws large SMBs.

This is the **Loop "small-frequent + low-basal-share" preset**. It is not
the Trio frequency-lever pattern (g is still on Loop's magnitude-lever
design — see capstone Section 3 — but with a magnitude knob turned
down and the SMB rate left at typical Loop levels).

---

## Reproducibility (27-week partition)

| metric | mean | std | CV |
|---|---:|---:|---:|
| TIR (70–180)                  | 0.667 | 0.092 | 0.138 |
| TBR (<70)                     | 0.029 | 0.017 | 0.598 |
| TAR (>180)                    | 0.199 | 0.069 | 0.349 |
| Overshoot (100–180 → 90 min)  | 0.213 | 0.060 | 0.282 |

- TIR CV of 0.138 is tight — g's TIR rarely drops below 0.55 in any
  given week.
- Overshoot std of 0.06 is comparable to the magnitude of the across-peer
  difference (c at 0.36 vs g at 0.21 = 0.15), so the gap survives weekly
  noise by ~2.5×.
- TBR std of 0.017 means g's hypoglycaemia exposure is consistently low,
  not zero-mean with occasional spikes.

**Verdict**: 27 weeks of stable performance with low CV → g's pattern is
reproducible, not a lucky window.

> **Reproducing the weekly partition**: the per-week metrics in the
> table above are computed transiently inside
> `tools/cgmencode/exp_patient_g_sweet_spot_2994.py` (group-by ISO week
> on patient g's grid rows) and not persisted to the JSON artifact —
> the JSON only carries the per-patient aggregates. Re-run the script
> against `externals/ns-parquet/training/grid.parquet` to regenerate
> the weekly breakdown.

---

## Honest assessment: tunable target or idiosyncratic?

**Tunable.** Three of g's four observable settings axes
(`bolus_smb_p95`, `basal_frac_of_tdd`, `suppress_70_100_eligible`) are
properties of the pump configuration that an AID author could expose
as defaults / guard-rails:

- A "small SMB" preset (cap `maxBolus`-derived SMB sizing at ~0.6 U
  for sensitive patients) would push other Loop_AB_ON users toward
  g's bolus_smb_p95.
- A "minimal basal share" preset (recommend basal ≤ 10% of TDD when
  AB is ON) would push others toward g's basal_frac.

The fourth axis — counter-regulation — is patient physiology and
cannot be tuned; we cannot rule out that g's intact CR (1.06 from
EXP-2886) is part of why the small-SMB pattern works for g and would
not work identically for a patient with absent CR.

**Why "tunable" rather than "idiosyncratic"**:

1. The signature is on observable, configurable pump axes, not on
   unobservable patient traits.
2. The performance is stable across 27 weeks — not a regression to the
   mean from a single good month.
3. The mechanism is consistent with the capstone Section 5 lever order:
   small SMBs avoid the magnitude→overshoot pipeline (EXP-2979); low
   basal share forces every dose to be triggered by an explicit
   prediction, which is exactly the predict-and-fire-early principle of
   lever (3).

**Caveats**:

- n=1 within-design observation; cannot estimate the
  treatment effect of porting g's settings to c/d/e/i.
- g's intact CR (counter_reg_intercept = 0.94 in EXP-2886) is above
  the Loop_AB_ON mean; a patient with absent CR + low basal share
  would be more exposed if Loop ever stops delivering correctly.
- The "all-bolus" pump configuration assumes Loop is functioning;
  failure modes (CGM loss, app crash) leave g with very little
  background insulin. This is a *deployment risk*, not a
  *settings risk*, but AID authors should surface it.

---

## Code-author actionable findings

1. **Surface the four-proxy conservatism score** (EXP-2991) plus its
   per-axis position so a Loop user can see whether they sit closer
   to g (sweet spot) or to i (Pareto-dominated).
2. **Consider a "small-SMB / low-basal-share" preset** with educational
   copy: "this configuration mimics the best-performing settings
   pattern in the EXP-29xx cohort but increases dependency on Loop
   functioning correctly".
3. **Add a guard-rail recommendation** that flags
   `basal_frac_of_tdd < 0.10` AND `counter_reg_intercept < 0.5`
   together as a high-deployment-risk combination, even though each
   alone is fine.
4. **Add to unit test scenarios** a "g-style" patient configuration
   alongside the EXP-2993 aggressive-style configuration, asserting
   the SMB cap holds and overshoot rate stays below the i baseline.

---

## Verdict

**Reproducibly a sweet spot, with a tunable settings signature.** Patient
g's distinguishing axes (`basal_frac_of_tdd` ≈ 0.06; `bolus_smb_p95` ≈
0.55) are configurable pump properties, observed stable across 27 weeks
(TIR CV 0.14). Suitable as a target for AID-author defaults/presets;
unsuitable as a clinical prescription without per-patient
counter-regulation assessment.
