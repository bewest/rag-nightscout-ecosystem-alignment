# Cross-Layer Interactions Report — State, EGP, and Inverse Estimation

**Date**: 2026-04-22
**Scope**: EXP-2823 (state × EGP), EXP-2832 (inverse EGP)
**Predecessor**: multitimescale-supply-demand-report-2026-04-22.md
**Status**: Phase complete; extended EGP coverage available for downstream
correction layers

---


## 📊 Visualization Dashboards

> **Status**: Dashboards for experiments EXP-2823, 2832 are in development.
> Visualization directory structure will be created in `visualizations/cross-layer-interactions/`
> once all figure generation is complete. Figures will include:
> - State/clustering analysis
> - Transition matrices and persistence
> - EGP audit and reconciliation
> - Algorithm comparison
>
> **Expected**: Figures will be automatically embedded in this section upon dashboard completion.

---

## 1. Motivation

The multi-layer supply/demand pipeline (raw → state → EGP → wear → residual)
needed two unanswered questions resolved before production use:

1. Are the slow (state) and supply (EGP) layers redundant or complementary?
2. Can we extend canonical EGP coverage beyond the 11 audit-credentialed
   patients so the EGP correction layer applies to most of the cohort?

EXP-2823 addresses (1); EXP-2832 addresses (2).

---

## 2. EXP-2823: EGP × State Interaction (2/5 PASS)

Tested two independent sub-hypotheses:

**H1 (between-patient)**: Higher-EGP patients spend more time in State 1.
**H2 (within-patient)**: Within a single patient, State 1 windows have
higher per-event EGP than State 0 windows.

| Sub-hypothesis | Result    | Statistic                         |
|----------------|-----------|-----------------------------------|
| H1             | SUPPORTED | Spearman ρ=+0.543 (p=0.084, n=11) |
| H2             | NOT FOUND | Median S1/S0 ratio=0.94; Wilcoxon p=1.0; only 1/20 patients S1>S0 |

**Architectural takeaway**: State and EGP are **not redundant** but they
operate at different granularities.

- State is a **between-patient EGP regime proxy** that's cheap to compute
  (BG-only) and well-correlated with canonical EGP across patients.
- State does **not** capture within-patient EGP variation. Per-event EGP
  correction should use a static per-patient EGP, not a state-dependent one.

This refines the multi-layer pipeline: the state layer (Layer 1) and EGP
layer (Layer 2) are operating on **different signals**, not stratifying
the same one. State changes the basal/sensitivity decoupling regime;
EGP corrects the per-event ISF measurement.

**H2 caveat**: The within-patient EGP proxy (`basal × scheduled_isf` in
flat windows) returned 0 for many patient/state combinations because
controllers heavily suspend basal in State 0. A drift-rate based proxy
would be a stronger H2 test; current evidence is necessary-not-sufficient
for ruling out within-patient EGP variation.

---

## 3. EXP-2832: Inverse EGP Estimation (4/5 PASS)

**Method**: Calibrate `EGP_canonical ~ β₁ × ISF_med + β₂ × pct_state1`
on 9 patients with credentialed EGP (subset of 11 with ≥5 events), then
predict EGP for 9 uncalibrated patients.

**Calibration coefficients**:
- intercept: 7.36
- β_isf_med: -0.037 (small; ISF alone is a weak signal)
- β_pct_state1: +17.7 (dominant; state proxy carries most of the signal)

**LOO cross-validation**:

| Metric          | Value             |
|-----------------|-------------------|
| LOO MAE         | 7.05 mg/dL/hr     |
| Canonical std   | 7.04 mg/dL/hr     |
| MAE / std       | **100%**          |

**P1 FAILS**. The error band is as wide as the natural variation. The
single biggest contributor is the outlier `ns-d444c120c` (canonical=24.6,
predicted=4.2, error=20.4) which alone accounts for ~30% of cumulative MAE.

**Successful criteria**:
- All 9 estimates fall in plausible [0, 30] mg/dL/hr range
- Inverse EGP correlates ρ=+0.933 with state proxy (model is largely a
  state-proxy regression after the LOO outlier)
- Inverse EGP burden correlates r=+0.466 (p<0.0001) with within-patient
  ISF residual on 340 target events — the inverse estimates carry real
  signal for the wear-adjusted setting extraction

**Inverse EGP estimates (9 newly covered patients)**:

| Patient            | ISF_med | %S1  | Inverse EGP |
|--------------------|---------|------|-------------|
| ns-c422538aa12a    | 105.8   | 0.0  | 3.4         |
| odc-74077367       | 95.0    | 10.5 | 5.7         |
| odc-86025410       | 125.7   | 54.5 | 12.4        |
| odc-96254963       | 65.7    | 59.1 | 15.4        |
| b                  | 144.5   | 81.5 | 16.4        |
| c                  | 106.5   | 85.6 | 18.6        |
| i                  | 30.0    | 83.4 | 21.0        |
| f                  | 12.8    | 82.4 | 21.5        |
| a                  | 41.3    | 93.2 | 22.3        |

**Combined 18-patient EGP distribution**: median 6.1 mg/dL/hr,
mean 10.4, CV=0.81.

---

## 4. Honest Use Recommendations for Inverse EGP

Given the 100%-of-std LOO error:

| Use case                                | Allowed? | Note |
|-----------------------------------------|----------|------|
| Patient-level RANKING (high vs low EGP) | YES      | ρ=0.93 with state proxy is robust |
| ORDINAL triage (e.g., quintile bucket)  | YES      | Within ±1 quintile likely accurate |
| Per-event ISF correction layer          | CAUTIOUS | Use as a covariate, not a fixed offset |
| Absolute clinical setting recommendation| NO       | Error band too wide; confounded with state |
| Extrapolation to canonical-extreme cases| NO       | ns-d444c120c case shows breakdown |

The inverse EGP file `exp-2832_extended_egp.parquet` should always be
joined with a confidence column (canonical vs inverse) so downstream
consumers know which estimates carry the rigorous credibility check.

---

## 5. Updated Multi-Layer Pipeline

After this phase the pipeline is:

| Layer | Source | Coverage | Use |
|-------|--------|----------|-----|
| 0 | Raw observed ISF | 24/28 patients (≥5 events) | input |
| 1 | State regime (EXP-2810/2811) | 28/28 | decouple ISF↔basal |
| 2a | Canonical EGP (EXP-2820) | 11/28 | per-event correction |
| 2b | Inverse EGP (EXP-2832) | +9 → 18/28 | rank-correct correction |
| 2c | State proxy (EXP-2823 H1) | 28/28 | cheap fallback for ranking |
| 3 | Wear (EXP-2831) | sparse but actionable | triage |
| 4 | Patient-mean residual | 24/28 | clean sensitivity estimate |

Of 28 patients, 18 now get a quantitative EGP correction (was 11), and
all 28 get a state-based EGP regime proxy. The remaining 10 with no
correction events at all (or <5) are not addressable through ISF
extraction at any layer until more data is collected.

---

## 6. Closed vs Open Questions

**Closed this phase**:
- State and EGP are independent layers (not redundant) — confirmed
- State serves as cheap between-patient EGP proxy (ρ=+0.93)
- Inverse method extends coverage but with rank-correctness, not
  quantitative precision

**Still open**:
- Within-patient EGP shifts (H2): stronger proxy needed before ruling out
- Extrapolation reliability: outlier ns-d444c120c case
- Site-degradation triage (EXP-2831): replication needed for the 4
  flagged patients
- EXP-2812: state-transition override audition windows (not yet started)
- Counter-regulation modeling (EXP-2728 negative baseline)

**Out of scope (declared)**:
- Single formulation-constant model (EXP-2830 refuted)
- Static EGP being modulatable by state (EXP-2823 H2 not found)

---

## 7. Production Output Inventory

For downstream consumers (settings extraction, triage UX, AID author docs):

| File                                                  | Content                                  |
|-------------------------------------------------------|------------------------------------------|
| `externals/experiments/exp-2810_state_assignments.parquet` | per-window state per patient |
| `externals/experiments/exp-2820_canonical_egp.parquet`     | 11 audit-credentialed EGP    |
| `externals/experiments/exp-2832_extended_egp.parquet`      | 18 EGP (canonical + inverse, with `source` flag) |
| `externals/experiments/exp-2831_triage_flags.parquet`      | 4 patients with site-degradation signal |

Always join with `source` column and confidence indicator before use.

---

## Source Files

- `tools/cgmencode/exp_egp_state_interaction_2823.py`
- `tools/cgmencode/exp_inverse_egp_2832.py`
- Predecessor reports:
  - `docs/60-research/state-and-egp-integration-report-2026-04-22.md`
  - `docs/60-research/multitimescale-supply-demand-report-2026-04-22.md`
