# EXP-2878 — HAAF Detection via Hypo Exposure vs Counter-Regulation

**Date:** 2026-04-22
**Stream:** B (operational)
**Status:** Complete — WEAK HAAF SIGNAL (directionally consistent, β_nadir sensitive)
**Predecessors:** EXP-2875 (counter-reg detection), EXP-2877 (dose-response confirmed)

## Question

Hypoglycemia-associated autonomic failure (HAAF) is a clinically
established phenomenon: repeated hypoglycemia exposure blunts the
counter-regulatory response to subsequent hypos, creating a
dangerous positive-feedback loop. Can we detect HAAF observationally
from CGM+pump data using the counter-reg signals validated in
EXP-2875/2877?

**HAAF prediction:** patients with higher chronic hypo exposure
should show WEAKER counter-regulation — either lower intercept
(baseline response) or lower β_nadir (dose-response slope).

## Method

Per-patient exposure metrics from `grid.parquet` (1.29M 5-min cells,
31 patients):

- `hypo_fraction` — fraction of cells with glucose < 70
- `severe_fraction` — fraction < 55
- `n_hypo` — total hypo cells (surrogate for cumulative exposure)

Per-patient counter-reg signals from EXP-2877 (27 patients with
≥10 rescue-free events):

- `intercept` — baseline rescue-free rise rate (EXP-2875)
- `beta_nadir` — dose-response slope (EXP-2877)

Spearman correlations across all 6 (exposure × signal) pairings.

## Result

**VERDICT: WEAK HAAF SIGNAL — β_nadir is the sensitive channel**

| Exposure metric  | vs intercept (ρ, p) | vs β_nadir (ρ, p) |
|------------------|--------------------:|-------------------:|
| hypo_fraction    | −0.15, p=0.46       | **−0.40, p=0.041** |
| severe_fraction  | −0.11, p=0.60       | **−0.36, p=0.066** |
| n_hypo           | −0.08, p=0.71       | −0.19, p=0.33      |

**All 6 pairings trend negative** (consistent with HAAF direction).
β_nadir correlations are uniformly stronger than intercept
correlations. One pairing is significant at α=0.05; one is
borderline.

## Interpretation

### 1. β_nadir is the HAAF-sensitive signal, not intercept

This is biologically sensible and an important refinement of the
counter-reg framework:

- **Intercept** captures baseline glucagon/catecholamine availability.
  HAAF does not abolish baseline response entirely; patients still
  have hormonal reserve for mild hypos.
- **β_nadir** captures the *gradient* of response — how much
  stronger the cascade is for deep vs shallow hypos. HAAF impairs
  this scaling: patients lose the ability to *amplify* response
  to severe hypos, which is the dangerous clinical feature.

The observational correlations match: exposure degrades the
gradient (β_nadir), not the floor (intercept).

### 2. Directionally strong but underpowered

All 6 correlations are negative — sign-test p = (1/2)^6 = 0.016.
With only 27 patients, individual correlations are underpowered,
but the uniform directional agreement is itself evidence.

### 3. Why is the signal weak?

Three non-exclusive explanations:

1. **AID suppresses hypo exposure below HAAF threshold.**
   Clinical HAAF develops after sustained/repeated hypos, typically
   hours-to-days of cumulative exposure. AID users in this cohort
   have median hypo fraction ~3-5%, well below the severe-exposure
   threshold associated with HAAF onset in pre-AID literature.

2. **Selection bias / survivor cohort.**
   Patients who develop severe HAAF are less likely to be running
   open-source AID data-upload workflows. The cohort may be
   biased toward patients with preserved awareness.

3. **Observational ceiling.**
   Without induced-hypo clamp studies, we cannot measure the full
   counter-reg cascade. Our observable proxy (rescue-free rise
   rate) is downstream of multiple layers and may be noisy at
   individual-patient scale.

## Implications

### For audition framework (EXP-2876)

The current counter-reg audition uses `intercept` thresholds
(impaired < 0.5, preserved ≥ 2.0). EXP-2878 suggests a **β_nadir-
based audition flag** may be more HAAF-predictive:

- **haaf_candidate**: β_nadir < 0.02 AND hypo_fraction > 0.05
- **preserved_gradient**: β_nadir > 0.06 AND n_hypo > 30 (patient
  has exposure but maintains gradient → genuinely preserved)

This is a higher-specificity clinical flag than intercept alone.

### For clinical practice

Patients identified as `haaf_candidate` warrant:
- Hypo-avoidance tightening (raise low alerts, reduce SMB aggression)
- Longer-term goal: hypo-holiday period to allow
  counter-regulation restoration (well-documented in T1D literature)
- Follow-up β_nadir measurement after holiday to verify recovery

### For open-source AID authors

**Actionable personalization signal:** compute per-patient β_nadir
from the last N days of rescue-free hypo events; if low AND hypo
fraction > 5%, tighten hypo-avoidance automatically or surface a
warning. This is a clinically grounded adaptive parameter that
requires only CGM + pump data.

## Limitations

- n=27 patients → individual correlations underpowered
- Cross-sectional, not longitudinal. Cannot prove *exposure causes
  degradation* vs *phenotypes with weak β_nadir experience more
  hypos* (reverse causation).
- Requires ≥10 rescue-free hypo events per patient (excludes well-
  managed patients with minimal hypo exposure).

## Next experiments

- **EXP-2879 counter-reg × circadian:** stratify events by TOD;
  dawn/pre-dawn response should exceed night.
- **Longitudinal HAAF:** split each patient's timeseries into
  halves; does β_nadir decline over time in patients with
  sustained hypo exposure?
- **EXP-2880 HAAF + phenotype:** does stream_B_early envelope-
  coupled cohort (EXP-2872) show different HAAF susceptibility?

## Files

- `tools/cgmencode/exp_haaf_2878.py`
- `externals/experiments/exp-2878_haaf.parquet`
- `externals/experiments/exp-2878_haaf_summary.json`
- `docs/60-research/figures/exp-2878_haaf.png`
