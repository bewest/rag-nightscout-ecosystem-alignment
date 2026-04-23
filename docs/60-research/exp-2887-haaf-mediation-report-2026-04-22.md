# EXP-2887 — HAAF Mediation of oref1 Counter-Reg Gap: REJECTED

**Date:** 2026-04-22
**Stream:** A (causal / confounding)
**Status:** Complete — HAAF mediation hypothesis REJECTED; oref1
lineage effect itself not robustly significant at n=19

## Question

EXP-2886 observed lineage-level mean counter_reg_intercept:

- Loop:           0.975
- oref1 (Trio):   0.767 (lowest)
- oref0 (OpenAPS): 0.966

And hypothesized a HAAF feedback loop: tighter oref1 defense →
more hypo exposure → attenuated counter-regulation. Test formally
via Baron-Kenny mediation with hypo_fraction as mediator.

## Method

n=19 patients (Loop=7, oref1=9, oref0=3) with complete
counter_reg_intercept, hypo_fraction, and lineage. Dummy-coded
lineage with Loop baseline; OLS regressions.

- Path A: lineage → hypo_fraction
- Path C: lineage → CR (total)
- Path C': lineage → CR | hypo_fraction (direct, controlling
  for mediator)
- Indirect = a·b; Sobel test

## Result

**VERDICT: HAAF MEDIATION REJECTED; oref1 lineage effect itself
not statistically distinguishable from zero at this sample size.**

### Path A: lineage → hypo_fraction

| Term      | β       | p    |
|-----------|--------:|-----:|
| intercept | +0.0388 | 0.001 |
| oref1     | **−0.0023** | **0.85** |
| oref0     | +0.0139 | 0.42 |

oref1 lineage is associated with **slightly LESS** hypo_fraction
than Loop (not more), and the effect is near-zero. The HAAF
feedback hypothesis requires Path A > 0; observed ≈ 0 with
reversed sign.

### Path B (hypo → CR | lineage)

| Term           | β       | p    |
|----------------|--------:|-----:|
| hypo_fraction  | −1.56   | **0.83** |

Hypo exposure does NOT predict counter-regulation within this
cohort once lineage is controlled. No statistical evidence that
more hypo → weaker CR.

### Path C: lineage → CR (total)

| Term  | β       | p    |
|-------|--------:|-----:|
| oref1 | −0.208  | **0.54** |
| oref0 | −0.010  | 0.98 |

The EXP-2886 lineage-level mean difference of 0.21 is directionally
present but **not statistically significant** (p=0.54). With n=7
Loop vs n=9 oref1, the uncertainty band spans [−0.91, +0.50].

### Mediation decomposition

| Quantity | Value |
|----------|------:|
| Path A (oref1 → hypo) | −0.0023 |
| Path B (hypo → CR) | −1.56 |
| Indirect a·b | **+0.004** |
| Direct C' | −0.212 |
| **Mediation proportion** | **−2%** |
| Sobel z = 0.14, p = 0.89 | null |

**Essentially 0% of the oref1 CR gap goes through HAAF exposure.**

## Interpretation

### 1. HAAF feedback hypothesis REJECTED

The proposed mechanism (oref1 → more hypo → attenuated CR) is
inconsistent with the data:
- oref1 has slightly LESS hypo_fraction than Loop
- Hypo_fraction does not predict CR within-sample
- Indirect effect is ≈ 0

### 2. Walkback of EXP-2886 framing

EXP-2886 described the oref1 low-CR pattern as a "candidate HAAF
feedback loop". EXP-2887 shows:

1. The lineage effect itself (Path C) is not statistically robust
   at n=19 — it could be a sample artifact.
2. Even if real, the HAAF pathway is not the mediator.

**Correction needed in EXP-2886:** reframe from "HAAF feedback" to
"observed cohort mean difference, direction of effect only,
mechanism unclear, not statistically significant at current n".

### 3. Candidate alternative explanations for the observed mean difference

Given that the direction is real but the mechanism isn't HAAF,
possibilities include:

- **Sample composition**: oref1 users may differ demographically
  (age, duration of T1D, BMI, geography, open-source comfort
  level). Without covariates, we cannot separate population from
  algorithm.
- **Event detection sensitivity**: the `detect_hypo_recovery_events`
  function (EXP-2875) detects events differently by controller —
  e.g., oref1 may produce more truncated-recovery events where CR
  measurement is biased low. Worth auditing.
- **Insulin-type / pump differences**: insulin brand, pump model,
  cannula type may co-vary with platform choice.
- **Bolus-timing differences**: oref1's SMB frequency produces
  different IOB profiles at event time, potentially shifting the
  CR-regression intercept without any physiological difference.
- **Small-sample noise**: with n=9 and residual SE of 0.33, the
  observed −0.21 is within sampling noise.

### 4. What would it take to resolve?

- **Add AAPS data** — another oref1 platform with likely different
  user demographics would separate "lineage" from "platform".
- **Match on demographics** — age, duration, TDD, BMI-stratified
  comparison.
- **Increase n to ≥30 per lineage** for adequate power.
- **Event-definition sensitivity audit** — rerun counter-reg
  extraction with alternative event detectors to check
  detection-bias hypothesis.

## Implications

### For the three-dimensional phenotype framework (EXP-2886)

- **Keep**: orthogonality of axes (ρ<0.32), archetype
  classifications, hidden-leverage patients, the `ns-8b3c1b50793c`
  critical finding (CR < 0). These do not depend on the lineage
  mechanism.
- **Downgrade**: the "HAAF feedback in oref1" narrative. State it
  as an observation with mechanism-unknown. Remove the speculative
  "oref1 authors investigate" action item until n and mechanism
  support it.

### For AID authors

No action for Trio/AAPS authors based on the HAAF hypothesis; it's
not supported. The **EXP-2885 nocturnal-braking gap for oref0
remains supported** (large effect, clean mechanism).

### For clinicians

When using the phenotype chart, interpret the CR axis as a
per-patient physiological signal. **Do not attribute low CR to
controller choice** — individual factors dominate.

### For autoresearch process

This is a valuable negative result. It confirms that:
- Small lineage n is a fundamental limit for cross-platform claims
- Observed cohort means must be corroborated with mediation or
  significance before framing mechanistic stories
- The autoresearch loop should include mediation / confounding
  audits as a routine guard, not only when suspicious

Consider adding a template `check_lineage_effect.py` that runs
Baron-Kenny-style mediation by default on any new cross-controller
claim.

## Limitations

- n=19, oref0 n=3 — severely under-powered.
- `hypo_fraction` is a population-level measure; transient
  exposure patterns (acute vs chronic) may matter more than
  fraction.
- Mediation assumes no reverse causation — but weak CR → more
  hypo is equally plausible causally.
- Sobel test known-conservative for small samples; bootstrap
  would be more appropriate if n allowed.

## Next experiments

- **EXP-2888** (deferred HAAF work) — rerun with AAPS patients
  when available; until then, pause the HAAF narrative.
- **EXP-2889** Hidden-leverage AID-failure simulation — what
  happens if Loop disengages from patient `g` at BG 100 descending?
- **EXP-2890** Audition wiring — add phenotype fields, with
  mediation-audit guard on lineage claims.
- **Retrospective edit**: add a "note" block to EXP-2886 pointing
  to EXP-2887's rejection of the HAAF framing.

## Files

- `tools/cgmencode/exp_haaf_mediation_2887.py`
- `externals/experiments/exp-2887_mediation.parquet`
- `externals/experiments/exp-2887_mediation_summary.json`
- `docs/60-research/figures/exp-2887_mediation.png`
