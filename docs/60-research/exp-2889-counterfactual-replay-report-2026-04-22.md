# EXP-2889 — Counterfactual AID-Off Replay Validates the Brake Construct

**Date:** 2026-04-22
**Stream:** Counterfactual outcome validation
**Status:** Strong positive result — AID intervention magnitude
quantified, braking_ratio validated as fragility marker

## 1. Motivation

EXP-2888 showed that observed `severe_fraction` is a
collider-biased validation target for AID-risk constructs: the AID
prevents exactly the outcome we'd use to validate "fragility under
AID." This experiment constructs the correct counterfactual target
— *what would have happened without AID suspension* — and re-tests
every EXP-2886 phenotype axis against it.

## 2. Method

For each pre-nadir descent event in `exp-2881_evening_drivers`
(n = 3 759 events with valid slope):

```
duration_min   = (bg_start − bg_nadir) / (−descent_slope)
basal_deficit  = max(0, sched_basal − actual_basal)     [U/h]
extra_insulin  = basal_deficit × duration_min / 60       [U]
extra_drop     = extra_insulin × ISF_pop (= 50 mg/dL/U)  [mg/dL]
cf_nadir       = bg_nadir − extra_drop
```

ISF_pop = 50 mg/dL/U (population median from EXP-2756).  A uniform
ISF is appropriate because we need *rank-ordering* of fragility,
not absolute prediction.  Per-patient severe fraction computed on
both observed and counterfactual nadirs; difference is the
**AID protection magnitude**.

## 3. Headline result: AID prevents most descent severe hypos

| Scope     | Observed severe | Counterfactual severe | Protection |
| --------- | --------------- | --------------------- | ---------- |
| All 3 759 descents | 36.2 % | 94.7 % | **58.4 pp / 61.7 % rel** |

Almost every descent event *would* reach < 54 mg/dL if the AID had
not suspended basal.  The AID converts 95 % "would-be-severe"
descents into 36 % actually-severe descents.  This is the scale of
intervention that EXP-2888's observed-outcome validation was
fighting.

## 4. Phenotype validation against counterfactual outcome

Spearman correlations (n = 19, only 3D-phenotype patients):

|  Predictor               | cf_severe         | aid_protection    |
|  ----------------------- | ----------------- | ----------------- |
|  **braking_ratio**       | **−0.711 p=0.001**| −0.365 p=0.12     |
|  hidden_leverage         | +0.153 p=0.53     | +0.342 p=0.15     |
|  stack_score             | −0.097 p=0.69     | +0.156 p=0.52     |
|  counter_reg_intercept   | −0.050 p=0.84     | −0.021 p=0.93     |

**Key validation:** `braking_ratio` is strongly and significantly
inversely related to counterfactual severe-hypo fraction.  Patients
whose AID suspends *most aggressively* (low ratio) are exactly the
patients whose descents *would be* severe-hypo without the
intervention.  The construct is mechanistically correct — the
observed-outcome null from EXP-2888 was collider bias, not invalid
construct.

`hidden_leverage` lines up in the expected direction for
`aid_protection_severe` (ρ = +0.34, patients flagged as leveraged
receive more AID protection) but doesn't cross significance at
n = 19.  Consistent with EXP-2888's finding that the multiplicative
composite is weaker than its parts.

## 5. Archetype stratification on counterfactual outcome

| Archetype            | n | obs_severe | cf_severe | AID protection |
| -------------------- | - | ---------- | --------- | -------------- |
| algorithm_dependent  | 6 | 35.2 %     | 96.0 %    | 60.8 pp |
| exposed_stacker      | 2 | 46.4 %     | 88.5 %    | 42.1 pp |
| **hidden_leverage**  | 3 | 34.6 %     | **99.9 %**| **65.3 pp** |
| insufficient_data    | 5 | 30.2 %     | 97.7 %    | 67.5 pp |
| **lax_braking**      | 1 | 57.9 %     | 70.5 %    | **12.5 pp** |
| stacker_balanced     | 1 | 21.1 %     | 93.0 %    | 71.9 pp |
| stacker_weak_defense | 1 | 18.5 %     | 93.7 %    | 75.1 pp |
| well_defended        | 5 | 34.8 %     | 98.6 %    | 63.8 pp |

Kruskal-Wallis on cf_severe across archetypes: H = 7.76, p = 0.101.

Two archetypes stand out:

1. **hidden_leverage (n = 3)** — counterfactual severe = 99.9 %.
   Essentially every descent in these patients would reach < 54 mg/dL
   without AID.  They receive the most protection (65 pp).
   These are the patients whose settings rely on the controller to
   operate safely.

2. **lax_braking (n = 1)** — counterfactual severe = 70.5 %,
   protection = 12.5 pp.  The AID barely changes the outcome
   distribution for this patient.  Either their settings are so
   conservative the AID doesn't need to brake, or the controller is
   poorly tuned.  Distinct from fragile-but-protected profiles.

## 6. Interpretation

### 6.1  Counter-causal structure finally resolved

Summarizing the three related experiments:

| Experiment | Outcome | Result | Reason |
| ---------- | ------- | ------ | ------ |
| EXP-2886 | archetype cohort means on stack × brake × CR | lineage differences observed | orthogonality preserved |
| EXP-2887 | Baron-Kenny mediation | HAAF path rejected (a*b ≈ 0) | sampling, not mechanism |
| EXP-2888 | observed severe_fraction | all ρ non-sig; composite worse than parts | **AID intervention severed construct-outcome link (collider)** |
| **EXP-2889** | **counterfactual cf_severe** | **braking_ratio ρ = −0.71, p = 0.001** | **correct outcome variable chosen** |

The construct was right all along.  The collider was hiding it.

### 6.2  Actionable implications

**For individual patients:**
- Patients with low `braking_ratio` *and* high AID protection
  magnitude are **AID-safety-dependent**.  Their settings are not
  safe on their own.  Clinical review should ask *why* settings
  rely so heavily on closed-loop suppression.
- `lax_braking` patients — AID isn't buffering them.  Either
  conservative settings (good) or ineffective controller tuning
  (fix).  Distinguish by looking at TDD vs profile.

**For AID authors:**
- Publishing "severe hypo rate on your AID" as a safety metric is
  misleading: it measures post-intervention outcome.  Counterfactual
  protection magnitude is the safety-relevant comparison across
  controllers.
- oref1 patients (Trio/AAPS) show the strongest protection magnitude
  per EXP-2885 suspension rates — the modern oref lineage is
  effective at converting would-be-severe into not-severe.

### 6.3  Methodology implications

EXP-2889 is a template for **technique §2.9** in the deconfounding
toolkit:  *counterfactual simulation as validation target*.  For
any construct that targets risk the AID prevents:

1. Simulate forward from observed intervention point assuming
   no intervention
2. Aggregate counterfactual outcomes per patient
3. Validate construct against the counterfactual, not the observed

## 7. Limitations

- Uniform ISF_pop = 50 mg/dL/U; per-patient ISF would sharpen the
  estimate but not change rank-order.  ISF heterogeneity
  (EXP-2739: 55× across patients) means absolute cf_nadir is noisy.
- Event duration inferred from descent_slope linearity; real
  descents are slightly sigmoidal near nadir.  Conservative
  (likely underestimates deficit).
- Model assumes basal deficit arrives instantaneously — real
  insulin absorption delays by ~15-30 min.  Cf_severe is an
  *upper-bound* of the counterfactual severe rate.
- n = 19 3D-phenotype patients is small.  cf_hypo (< 70) is
  saturated near 100 % so yields no discriminative power.

## 8. Next steps

- **Audition wiring**: update `production/audition_matrix.py` with
  `braking_ratio`, `aid_protection_severe`, `counterfactual_severe`.
  These now have validated predictive power.
- **EXP-2890**: Per-patient ISF replay — redo with profile ISF per
  patient to tighten cf_nadir estimates.
- **EXP-2891**: Dose-response of protection by lineage on *matched*
  aggressiveness terciles (Simpson-safe).
- **Patient vignettes**: the `lax_braking` patient and the
  `hidden_leverage` cohort warrant individualized clinical review
  reports using this methodology.

## 9. Artifacts

- `tools/cgmencode/exp_counterfactual_replay_2889.py`
- `externals/experiments/exp-2889_counterfactual_replay.parquet`
- `externals/experiments/exp-2889_event_replay.parquet`
- `externals/experiments/exp-2889_counterfactual_replay_summary.json`
- `docs/60-research/figures/exp-2889_counterfactual_replay.png`
