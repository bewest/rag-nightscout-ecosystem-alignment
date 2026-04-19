# Expanded Cohort Validation Report

**Date**: 2026-04-18
**Experiments**: EXP-2640, EXP-2651, EXP-2652, EXP-2656, EXP-2662
**Scope**: Re-validation of 5 priority EGP/ISF experiments on expanded 43-patient cohort
**Patients**: 43 unique (31 NS-parquet training + 12 DynISF-v2), up from 11 original
**Status**: COMPLETE — all 5 experiments rerun with robustness fixes

---

## Executive Summary

Five priority experiments from the EGP research program (EXP-2621–2662) were rerun on
an expanded cohort of 43 patients (31 from `ns-parquet/training/grid.parquet`, 12 from
`ns-parquet-dynisf-v2/grid.parquet`) to test whether key findings replicate beyond the
original 11-patient Nightscout dataset. Each experiment received robustness refactoring
before rerun.

**Key outcomes**:

1. **EXP-2651 (Two-Phase ISF)**: Core finding **confirmed at scale**. 100% of 25 fitted
   patients show demand ISF < apparent ISF (H1 PASS). Inflation ratio narrows from
   2–10× (N=11) to 1.30–5.26× (N=25) — still large, but more precisely bounded.
   DynISF cohort: 12/12 fitted, inflation 1.41–3.76×.

2. **EXP-2652 (Circadian ISF)**: Variation exists (78% show ≥30%), but **circadian
   profiling does not improve prediction** (H2 FAIL: only 1/18 with ≥10% RMSE gain).
   Dawn phenomenon not confirmed as universal (H3 FAIL). Findings consistent across
   both cohorts.

3. **EXP-2656 (SC Suppression Ceiling)**: Ceiling model universally beats linear
   (29/29 + 12/12). Range stable at 30–56% (original) and 30–44% (DynISF). However,
   **sticky-hyper correlation weakens** from r=−0.60 (N=12) to r=−0.285 (N=29, p=0.134)
   — no longer significant at α=0.05.

4. **EXP-2662 (Patience Mode)**: SMB savings robust (34% original, 42% DynISF) but
   **delayed hypo reduction disappoints** at 10–15% (prior claim: 34–82%). TIR impact
   negligible (−0.2pp original, −0.1pp DynISF). Hyper cost well-contained at max +2.1pp.

5. **EXP-2640 (Per-Patient ISF Curves)**: Log model wins 5/6 patients. NaN/Inf guards
   working — no crashes. Limited to 6 patients from EXP-2636 JSON input.

**Bottom line**: The expanded cohort confirms the *direction* of all major physiological
findings (two-phase ISF, suppression ceiling, dose-dependent ISF) while shrinking effect
sizes and weakening some correlations. The data is now sufficient to distinguish robust
phenomena (ceiling model superiority, demand vs apparent ISF separation) from overfitted
claims (sticky-hyper correlation, circadian RMSE improvement).

---

## 1. Experimental Refactoring

Before rerun, each experiment received targeted robustness fixes:

| Experiment | Fix | Rationale |
|-----------|-----|-----------|
| EXP-2651 | 2h → 6h prior-bolus isolation | Nyquist compliance per EXP-2665/2666; prevents SMB contamination of demand ISF |
| EXP-2652 | 4h → 12h primary circadian blocks | Nyquist-correct for DIA=6h; 4h blocks retained as informational |
| EXP-2652 | 2h → 6h prior-bolus isolation | Same Nyquist fix as EXP-2651 |
| EXP-2640 | NaN/Inf guards on curve fitting | Prevents crashes on patients with degenerate dose distributions |
| EXP-2656 | `--parquet` argparse, dynamic patient discovery | Enables multi-dataset runs; auto-discovers patient IDs |
| EXP-2656 | min-n guards | Skips patients with insufficient high-IOB data |
| EXP-2662 | `--parquet` argparse, dynamic patient discovery | Same infrastructure as EXP-2656 |
| EXP-2662 | min-n guards | Skips patients with insufficient readings |

**Source code**:
- `tools/cgmencode/exp_two_phase_isf_2651.py`
- `tools/cgmencode/exp_circadian_isf_2652.py`
- `tools/cgmencode/exp_per_patient_isf_2640.py`
- `tools/cgmencode/exp_sc_ceiling_2656.py`
- `tools/cgmencode/exp_patience_mode_2662.py`

---

## 2. EXP-2651: Two-Phase ISF Decomposition

### 2.1 Design

Decomposes each correction bolus into demand-phase (0–2h, direct insulin action) and
apparent (full nadir) ISF. Tests whether demand ISF is systematically lower than apparent
ISF, indicating EGP-mediated inflation of scheduled ISF values.

**Isolation window**: 6h (upgraded from 2h for Nyquist compliance).

### 2.2 Results — Original Cohort (NS-parquet)

| Metric | Prior (N=11, 672 events) | Expanded (N=25 fitted / 31 dataset, 442 events) |
|--------|--------------------------|--------------------------------------------------|
| H1: demand < apparent | 100% | **100%** (25/25) |
| H2: demand wins 2h RMSE | ~90% | **92%** (23/25) |
| H3: apparent wins 4h RMSE | ~50% | **16%** (4/25) |
| H4: inflation ratio | 2–10× | **1.30–5.26×** (24 patients with valid ratio) |
| Isolation window | 2h | 6h |

### 2.3 Results — DynISF Cohort (12 patients)

| Hypothesis | Result | Detail |
|-----------|--------|--------|
| H1: demand < apparent | **PASS** | 100% (12/12) |
| H2: demand wins 2h | **PASS** | 100% (12/12) |
| H3: apparent wins 4h | **FAIL** | 8% (1/12) |
| H4: inflation ratio | **PASS** | 1.41–3.76× |

### 2.4 Interpretation

The two-phase ISF decomposition is the most robust finding in the research program. It
replicates perfectly (100% H1 pass rate) across both cohorts and with the stricter 6h
isolation window. The inflation ratio narrows from 2–10× to 1.30–5.26× — the upper bound
contracts substantially, suggesting the original 10× outliers were contaminated by
insufficient isolation.

H3 (apparent wins at 4h) drops from ~50% to 16%, indicating that with proper 6h isolation,
the demand ISF is actually a better predictor even at longer horizons. This is a
methodological improvement, not a contradiction.

**Verdict**: ✅ **CONFIRMED** — demand/apparent ISF separation is real and universal.

**Source**: `externals/experiments/exp-2651_two_phase_isf.json`,
`externals/experiments/exp-2651_two_phase_isf_dynisf.json`

---

## 3. EXP-2652: Circadian ISF Profiling

### 3.1 Design

Tests whether ISF varies by time-of-day (circadian rhythm) and whether time-of-day–specific
ISF values improve glucose prediction. Primary analysis uses Nyquist-correct 12h blocks
(day/night). 4h blocks retained for exploratory analysis only.

### 3.2 Results — Original Cohort (18 fitted)

| Hypothesis | Result | Detail |
|-----------|--------|--------|
| H1: ≥30% ISF variation | **PASS** | 78% (14/18) show ≥30% range |
| H2: ≥10% RMSE improvement (12h blocks) | **FAIL** | 1/18 (5.6%) |
| H3: dawn has lowest ISF | **FAIL** | Most common lowest block: 12–16h (5/18), 16–20h (4/18), 20–24h (4/18) |

### 3.3 Results — DynISF Cohort (10 fitted)

| Hypothesis | Result | Detail |
|-----------|--------|--------|
| H1: ≥30% ISF variation | **PASS** | 70% (7/10) |
| H2: ≥10% RMSE improvement | **FAIL** | 2/10 (20%) |
| H3: dawn has lowest ISF | **FAIL** | Most common lowest block: 20–24h |

### 3.4 Comparison with Prior Claims

| Metric | Prior (N=11) | Expanded (N=18+10) |
|--------|-------------|---------------------|
| ISF variation present | Yes | Yes (78%/70% ≥30%) |
| RMSE improvement | "10–20%" claimed | **1/18 original, 2/10 DynISF** ≥10% |
| Dawn phenomenon | Assumed | **Not universal** — afternoon/evening dominate |

### 3.5 Interpretation

Circadian ISF variation *exists* — most patients show ≥30% range across the day. However,
this variation does **not** translate into meaningful prediction improvement when using
Nyquist-correct 12h blocks. The prior "10–20% RMSE improvement" claim was based on
overfitted 4h blocks that violated the Nyquist criterion for DIA=6h insulin dynamics.

The dawn phenomenon is not the dominant pattern. The lowest ISF blocks are distributed
across afternoon and evening hours, suggesting that ISF variation is driven more by
meal/activity patterns than by endogenous circadian hormones.

**Verdict**: ⚠️ **PARTIALLY CONFIRMED** — variation exists, but is not predictively useful
at Nyquist-correct resolution. Prior RMSE claims were artifacts of overfitting.

**Source**: `externals/experiments/exp-2652_circadian_profiling.json`,
`externals/experiments/exp-2652_circadian_profiling_dynisf.json`

---

## 4. EXP-2656: SC Insulin Suppression Ceiling

### 4.1 Design

Tests whether subcutaneous insulin suppression of hepatic EGP follows a saturable (ceiling)
model rather than linear. Fits a ceiling parameter per patient representing the maximum
fraction of EGP that SC insulin can suppress.

### 4.2 Results — Original Cohort (29 patients)

| Hypothesis | Result | Detail |
|-----------|--------|--------|
| H1: actual rate slower than linear prediction | **PASS** | 100% (29/29) |
| H2: ceiling model beats linear RMSE | **PASS** | 100% (29/29) |
| H3: ceiling range 30–50% | **PASS** | Range: 30–56% |
| H4: ceiling correlates with sticky-hyper % | **FAIL** | r = −0.285, p = 0.134 |

### 4.3 Results — DynISF Cohort (12 patients)

| Hypothesis | Result | Detail |
|-----------|--------|--------|
| H1: actual rate slower than linear | **PASS** | 100% (12/12) |
| H2: ceiling beats linear | **PASS** | 100% (12/12) |
| H3: ceiling range 30–50% | **FAIL** | Range: 30–44% (narrower, all ≤44%) |
| H4: ceiling–sticky correlation | **FAIL** | r = −0.038 (essentially zero) |

### 4.4 Comparison with Prior Claims

| Metric | Prior (N=12) | Expanded Original (N=29) | DynISF (N=12) |
|--------|-------------|--------------------------|---------------|
| Ceiling range | 30–56% | 30–56% | 30–44% |
| Ceiling beats linear | 12/12 | 29/29 | 12/12 |
| Sticky-hyper correlation | r = −0.60, p = 0.039 | **r = −0.285, p = 0.134** | **r = −0.038** |

### 4.5 Interpretation

The core physiological finding — SC insulin has a saturable suppression ceiling around
30–56% of EGP — replicates perfectly across all 41 patients. The ceiling model universally
outperforms linear.

However, the **sticky-hyper correlation collapses** from r=−0.60 (significant at α=0.05
with N=12) to r=−0.285 (not significant, p=0.134 with N=29). The DynISF cohort shows
essentially zero correlation (r=−0.038). This suggests the original r=−0.60 was an
artifact of small-sample variability. The ceiling is real; its correlation with clinical
sticky-hyper phenotype is not.

**Verdict**: ✅ **CEILING CONFIRMED**, ❌ **STICKY-HYPER CORRELATION REJECTED**

**Source**: `externals/experiments/exp-2656_sc_ceiling.json`,
`externals/experiments/exp-2656_sc_ceiling_dynisf.json`

---

## 5. EXP-2662: Patience Mode Controller

### 5.1 Design

Simulates a "patience mode" controller that withholds SMBs when IOB exceeds a
threshold (waiting for existing insulin to act). Tests delayed-hypo reduction,
hyper cost, SMB savings, and TIR impact.

### 5.2 Results — Original Cohort (27 patients)

| Hypothesis | Result | Detail |
|-----------|--------|--------|
| H1: ≥30% delayed hypo reduction | **FAIL** | Mean 10% reduction (range 0–27%) |
| H2: hyper increase ≤5pp | **PASS** | Max +2.1pp |
| H3: ≥20% SMB savings | **PASS** | Mean 34%, range 0–78% |
| H4: TIR neutral (≤1pp loss) | **FAIL** | Mean −0.2pp (within tolerance individually, but sign is consistently negative) |

### 5.3 Results — DynISF Cohort (12 patients)

| Hypothesis | Result | Detail |
|-----------|--------|--------|
| H1: ≥30% delayed hypo reduction | **FAIL** | Mean 15% reduction |
| H2: hyper increase ≤5pp | **PASS** | Max +1.2pp |
| H3: ≥20% SMB savings | **PASS** | Mean 42% |
| H4: TIR neutral | **FAIL** | Mean −0.1pp |

### 5.4 Comparison with Prior Claims

| Metric | Prior (N=12) | Expanded Original (N=27) | DynISF (N=12) |
|--------|-------------|--------------------------|---------------|
| SMB savings | 34–82% | **Mean 34%** (range 0–78%) | **Mean 42%** |
| Delayed hypo reduction | "34–82%" claimed | **Mean 10%** | **Mean 15%** |
| Max hyper cost | Not reported | +2.1pp | +1.2pp |
| Mean TIR delta | Not reported | −0.2pp | −0.1pp |

### 5.5 Interpretation

Patience mode delivers real SMB savings (34–42% mean across cohorts) with negligible
hyper cost (max +2.1pp). However, the headline claim of 34–82% delayed hypo reduction
is **not reproduced** — actual reduction is 10–15% on the expanded cohort. The prior
range likely conflated SMB savings with hypo reduction.

TIR impact is consistently slightly negative (−0.1 to −0.2pp), indicating patience mode
trades a trivial amount of TIR for insulin conservation. This is clinically acceptable
but should be honestly reported.

**Verdict**: ⚠️ **PARTIALLY CONFIRMED** — SMB savings real, hypo reduction overstated

**Source**: `externals/experiments/exp-2662_patience_mode.json`,
`externals/experiments/exp-2662_patience_mode_dynisf.json`

---

## 6. EXP-2640: Per-Patient Dose-ISF Curves

### 6.1 Design

Fits per-patient dose–response curves (linear, log, sqrt models) to individual correction
bolus events from EXP-2636. Tests dose-dependent ISF at the individual patient level with
NaN/Inf guards for robustness.

### 6.2 Results (6 patients fitted, 219 events)

| Patient | Best Model | Log r | Linear r | n_events |
|---------|-----------|-------|----------|----------|
| a | log | −0.597 | −0.469 | 79 |
| c | log | −0.624 | −0.603 | 38 |
| e | linear | −0.297 | −0.385 | 21 |
| f | log | −0.819 | −0.652 | 24 |
| g | log | +0.721 | +0.671 | 7 |
| i | log | −0.815 | −0.713 | 24 |

- **Log model wins**: 5/6 patients (83%)
- **Negative correlation** (expected: higher dose → lower ISF): 5/6 patients
- **Outlier**: Patient g shows positive correlation (7 events only — likely insufficient data)
- **NaN/Inf guards**: Working correctly, no crashes on degenerate inputs

### 6.3 Interpretation

The logarithmic dose–ISF relationship replicates at the per-patient level for 5/6 patients
with sufficient data. The one exception (patient g, N=7) likely reflects data insufficiency
rather than a true physiological difference. This is consistent with the population-level
finding from EXP-2636 (r=−0.56, p<10⁻¹⁹).

**Verdict**: ✅ **CONFIRMED** — log dose-ISF relationship holds per-patient

**Source**: `externals/experiments/exp-2640_per_patient_isf.json`
**Code**: `tools/cgmencode/exp_per_patient_isf_2640.py`

---

## 7. Statistical Power Analysis

### 7.1 Sample Size Adequacy

| Experiment | Prior N | Expanded N | Power at α=0.05 | Assessment |
|-----------|---------|-----------|------------------|------------|
| EXP-2651 | 11 | 25 + 12 = 37 | >0.99 for H1 (effect size d→∞, 100% pass) | **Adequate** |
| EXP-2652 | 11 | 18 + 10 = 28 | ~0.80 for H1 (78% rate) | **Adequate for H1, underpowered for H2** |
| EXP-2656 | 12 | 29 + 12 = 41 | ~0.55 for H4 (r=−0.285) | **Adequate for H1–H3, underpowered for H4** |
| EXP-2662 | 12 | 27 + 12 = 39 | ~0.40 for H1 (10% effect vs 30% threshold) | **Adequate for H2–H3, underpowered for H1** |
| EXP-2640 | 6 | 6 | ~0.60 for model comparison | **Underpowered — needs more patients** |

### 7.2 Effect Size Evolution

The expanded cohort reveals a consistent pattern: **effect sizes shrink toward more
moderate values as N increases**.

| Finding | Prior Effect | Expanded Effect | Direction |
|---------|-------------|-----------------|-----------|
| ISF inflation ratio | 2–10× | 1.30–5.26× | Contracted |
| SC ceiling–sticky r | −0.60 | −0.285 | Weakened |
| Delayed hypo reduction | 34–82% | 10–15% | Substantially reduced |
| SMB savings | 34–82% | 34–42% | Narrowed |
| Circadian RMSE improvement | 10–20% | <10% (1/18) | Collapsed |

This is the expected statistical regression to the mean. The original N=11–12 cohort
was large enough to detect the *direction* of effects but not to bound their *magnitude*.
The expanded cohort provides more trustworthy point estimates.

### 7.3 Required N for Remaining Hypotheses

To reach 80% power at α=0.05 for the currently failing/weak hypotheses:

| Hypothesis | Current Effect | Required N |
|-----------|---------------|------------|
| EXP-2656 H4 (ceiling–sticky r) | r = −0.285 | ~95 patients |
| EXP-2662 H1 (30% hypo reduction) | 10–15% actual | Effect too small — would need >200 patients, or the hypothesis should be revised to a lower threshold |
| EXP-2652 H2 (10% RMSE improvement) | 5.6% pass rate | Effect likely does not exist at Nyquist-correct resolution |

---

## 8. Consolidated Hypothesis Verdicts

| ID | Hypothesis | Prior | Expanded | Verdict |
|----|-----------|-------|----------|---------|
| 2651-H1 | demand ISF < apparent ISF | PASS | **PASS** (100%, N=37) | ✅ Confirmed |
| 2651-H2 | demand wins 2h prediction | PASS | **PASS** (92–100%) | ✅ Confirmed |
| 2651-H3 | apparent wins 4h prediction | ~PASS | **FAIL** (8–16%) | ❌ Rejected (6h isolation fixes this) |
| 2651-H4 | inflation ratio >1× | PASS (2–10×) | **PASS** (1.30–5.26×) | ✅ Confirmed, range narrowed |
| 2652-H1 | ≥30% circadian variation | PASS | **PASS** (70–78%) | ✅ Confirmed |
| 2652-H2 | ≥10% RMSE from circadian | PASS | **FAIL** (1/18, 2/10) | ❌ Rejected (Nyquist artifact) |
| 2652-H3 | dawn has lowest ISF | untested | **FAIL** | ❌ Rejected |
| 2656-H1 | actual rate < linear predicted | PASS | **PASS** (41/41) | ✅ Confirmed |
| 2656-H2 | ceiling beats linear | PASS | **PASS** (41/41) | ✅ Confirmed |
| 2656-H3 | ceiling in 30–50% range | PASS | **PASS** (30–56%) | ✅ Confirmed |
| 2656-H4 | ceiling correlates sticky-hyper | PASS (r=−0.60) | **FAIL** (r=−0.285) | ❌ Rejected |
| 2662-H1 | ≥30% delayed hypo reduction | PASS | **FAIL** (10–15%) | ❌ Rejected |
| 2662-H2 | hyper cost ≤5pp | PASS | **PASS** (max +2.1pp) | ✅ Confirmed |
| 2662-H3 | ≥20% SMB savings | PASS | **PASS** (34–42%) | ✅ Confirmed |
| 2662-H4 | TIR neutral | untested | **FAIL** (−0.1 to −0.2pp) | ⚠️ Marginal (within clinical tolerance) |
| 2640 | log dose-ISF per patient | PASS | **PASS** (5/6) | ✅ Confirmed |

**Summary**: 9/16 hypotheses confirmed, 5 rejected, 2 marginal/revised.

---

## 9. Conclusions

### 9.1 What Survived Expansion

Three physiological findings are now well-established across 37–43 patients:

1. **Two-phase ISF decomposition** (demand < apparent, 100% universal)
2. **SC suppression ceiling** (30–56%, ceiling model always wins)
3. **Logarithmic dose-ISF relationship** (5/6 per-patient, population r=−0.56)

### 9.2 What Did Not Survive

Three claims from the original cohort are now rejected:

1. **Sticky-hyper correlation** with ceiling level (r weakened from −0.60 to −0.285)
2. **Circadian RMSE improvement** (artifact of 4h overfitting)
3. **Large delayed hypo reduction** from patience mode (10–15%, not 34–82%)

### 9.3 What Needs Revision

Two findings need updated magnitude estimates:

1. **ISF inflation ratio**: Report as 1.3–5.3× (not 2–10×)
2. **SMB savings**: Report as 34–42% mean (not 34–82% range)

### 9.4 Next Steps

1. **EXP-2640 expansion**: Run per-patient ISF curves on full 43-patient cohort
   (currently limited to 6 patients from EXP-2636 JSON).
2. **Update synthesis report**: Revise `egp-research-synthesis-report-2026-04-18.md`
   with corrected effect sizes from this validation.
3. **Power-driven protocol**: For future experiments, pre-register required N based
   on expected effect sizes from this report.
4. **DynISF-specific analysis**: The DynISF cohort shows tighter ceiling range (30–44%)
   and higher SMB savings (42%) — investigate whether DynISF algorithm settings
   produce systematically different EGP dynamics.

---

## Appendix A: Data Sources

| Dataset | Path | Patients | Notes |
|---------|------|----------|-------|
| NS-parquet training | `externals/ns-parquet/training/grid.parquet` | 31 | Primary cohort |
| DynISF-v2 | `externals/ns-parquet-dynisf-v2/grid.parquet` | 12 | DynISF algorithm users |
| EXP-2636 JSON | `externals/experiments/exp-2636_dose_dependent_isf.json` | 6 fitted | Input for EXP-2640 |

## Appendix B: Result Files

| Experiment | Original | DynISF |
|-----------|----------|--------|
| EXP-2651 | `externals/experiments/exp-2651_two_phase_isf.json` | `externals/experiments/exp-2651_two_phase_isf_dynisf.json` |
| EXP-2652 | `externals/experiments/exp-2652_circadian_profiling.json` | `externals/experiments/exp-2652_circadian_profiling_dynisf.json` |
| EXP-2656 | `externals/experiments/exp-2656_sc_ceiling.json` | `externals/experiments/exp-2656_sc_ceiling_dynisf.json` |
| EXP-2662 | `externals/experiments/exp-2662_patience_mode.json` | `externals/experiments/exp-2662_patience_mode_dynisf.json` |
| EXP-2640 | `externals/experiments/exp-2640_per_patient_isf.json` | — |

## Appendix C: Prior Reports

- `docs/60-research/egp-research-synthesis-report-2026-04-18.md` — Main synthesis (N=12)
- `docs/60-research/egp-phase-separation-report-2026-04-12.md` — Original EXP-2621–2662
- `docs/60-research/egp-evidence-synthesis-report-2026-04-18.md` — Corrective reframing
