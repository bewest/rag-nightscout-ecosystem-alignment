# EXP-2983 — Trio IOB-stacking governor: hypo vs IOB at SMB emission

**Date**: 2026-04-23
**Audience**: Open-source AID code authors
**Scope**: Per-patient (n=8 Trio with ≥20 no-carb SMB events) and
within-patient relationship between IOB-at-emission and
60-min hypo (<70 mg/dL) rate post-emission. Tests whether an
IOB ceiling exists above which hypo risk jumps materially.
**What this is NOT**: a per-patient `maxIOB` recommendation; not
a clinical safety study. Observational, ~30k pooled events.

## Result — NULL on the stacking-ceiling hypothesis (with reverse-direction signal)

Cross-patient Spearman:

| relationship | ρ | p (two-sided) | n_patients |
|---|---:|---:|---:|
| mean_IOB ↔ hypo_rate  | **−0.333** | 0.38 | 8 |
| p75_IOB  ↔ hypo_rate  | −0.469 | 0.20 | 8 |

Per-patient table (sorted by mean IOB):

| patient | n_events | mean IOB (U) | p75 IOB (U) | hypo rate |
|---|---:|---:|---:|---:|
| ns-1ccae8a375b9 |  4115 | 0.21 | 0.22 | 4.5% |
| ns-d444c120c23a |  6561 | 0.10 | 0.13 | 3.6% |
| ns-dde9e7c2e752 |  2750 | 0.53 | 0.77 | 1.2% |
| ns-a9ce2317bead |  4986 | 0.80 | 1.16 | 7.0% |
| ns-6bef17b4c1ec |  6385 | 0.88 | 1.31 | 1.9% |
| ns-9b9a6a874e51 |  3626 | 0.96 | 1.36 | 2.8% |
| ns-8f3527d1ee40 |  5006 | 0.98 | 1.25 | 3.9% |
| ns-8b3c1b50793c |  2171 | 1.17 | 1.79 | 0.6% |
| ns-adde5f4af7ca |  5767 | 1.36 | 2.22 | 3.1% |

Pooled across-Trio bands of IOB-at-emission:

| IOB band (U) | n events | hypo rate |
|---|---:|---:|
| 0.0 – 0.5 | 20,496 | **4.0%** |
| 0.5 – 1.0 |  6,193 | 2.2% |
| 1.0 – 1.5 |  3,717 | 2.2% |
| 1.5 – 2.0 |  2,183 | 2.3% |
| 2.0 – 3.0 |  2,393 | 2.5% |
| 3.0 – 5.0 |  1,811 | **1.3%** |
| 5.0 – 10.0|    745 | 2.1% |

Within-patient IOB-tertile (e.g., ns-a9ce2317bead 15.97% → 0.97%
T0→T2; ns-adde5f4af7ca 4.99% → 1.10% T0→T2): **hypo rate
decreases or is flat** as IOB rises within-patient.

## Interpretation

The naive "more stacked IOB ⇒ more hypo" model **does not hold**
in this Trio cohort. The relationship is **flat or mildly
inverse**. Three plausible explanations:

1. **Selection / context confounding**. SMB at low IOB tends to
   occur when BG is already low or falling (algorithm fires
   small corrections to stop a fall). Those events live near
   the hypo threshold by construction. SMB at high IOB occurs
   in mid-meal or post-meal when BG is high — far from 70.
2. **Algorithm caps work**. Trio's `maxIOB`, `maxSMB_Basal`
   minutes, and `enableSMB` policy gates already prevent
   genuinely dangerous stacking states from emitting more SMB.
   The dataset only contains *allowed* emissions; the censoring
   itself proves the cap is doing work.
3. **DIA/ISF correctness**. When IOB is high, BG was high
   recently → carb absorption + counter-regulation are still
   active → insulin "lands softer" than the linear ISF model
   predicts.

## Implication for AID authors

There is **no empirical IOB ceiling visible in this Trio cohort**
above which hypo risk discontinuously jumps. Existing Trio
defaults (`maxIOB`, `enableSMB_always: false` per
`externals/Trio/trio-oref/lib/profile/index.js:47`) already
prevent the dangerous regime in this sample. The
**hypo-prevention lever is not "lower maxIOB"**; the relevant
levers appear to be:

- Suppression *at low BG* (not at high IOB) — see the 4% hypo
  rate at IOB <0.5 U.
- Post-event reduction of subsequent SMB (which Trio already
  does via `IOBpredBG` in `determine-basal.js:880,977`).

## Cite

- `externals/Trio/trio-oref/lib/profile/index.js:40-51` —
  `enableSMB_always` warnings and default = false.
- `externals/Trio/trio-oref/lib/determine-basal/determine-basal.js:84-88`
  — `enableSMB_always` gate.
- `externals/Trio/trio-oref/lib/determine-basal/determine-basal.js:880,977-982`
  — `maxIOBPredBG` clamp on prediction-based dosing decisions.

## Verdict

**NULL on the stacking-ceiling hypothesis** (and a directional
reverse signal that should not be over-interpreted as
"more IOB is safe" — it reflects context selection).

## Source / data
- `tools/cgmencode/exp_trio_iob_governor_2983.py`
- `externals/experiments/exp-2983_summary.json`
