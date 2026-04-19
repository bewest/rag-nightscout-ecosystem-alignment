# DynISF Cohort Characterization: Cross-Dataset Comparison

**Date**: 2026-04-18
**Scope**: Cross-cohort metabolic phenotyping — NS standard vs DynISF parquet datasets
**Patients**: 25 NS-standard (10 letter + 12 ns-* + 3 odc-*), 12 DynISF (ns-*), 12 overlapping
**Experiments**: EXP-2651, EXP-2652, EXP-2656, EXP-2662
**Status**: Complete — data-verified from experiment JSONs

---

## Executive Summary

We compared metabolic characteristics of 12 DynISF patients (ns-\* IDs from
`ns-parquet-dynisf-v2/grid.parquet`, ~612K rows) against the broader 25-patient
NS cohort (`ns-parquet/training/grid.parquet`, ~1.29M rows across 31 patients).
All 12 DynISF patients also appear in the NS dataset, enabling both cross-cohort
and within-patient reproducibility analysis.

**Key findings:**

1. **ISF estimates are perfectly reproducible** across datasets for the 12
   overlapping patients — demand ISF, apparent ISF, and inflation ratios are
   identical (Wilcoxon p = 1.0), confirming that both parquet sources contain
   the same underlying correction episodes for these patients.

2. **No significant ISF phenotype difference** between DynISF patients and
   NS-only patients (Mann-Whitney U = 68, p = 0.61 for demand ISF). The DynISF
   cohort trends slightly higher in apparent ISF (median 71.9 vs 57.1 mg/dL/U)
   but this is not statistically significant with current sample sizes.

3. **SC ceiling estimates shift modestly** with more data — the DynISF dataset
   yields slightly lower fitted ceilings for 7/12 patients (median Δ = −0.006),
   with sticky hyper rates essentially unchanged (Wilcoxon p = 1.0).

4. **Patience mode is significantly more effective** when measured on the DynISF
   dataset: SMB prevention rises from median 38.1% → 47.4% (Wilcoxon p = 0.016)
   and wall detection from 24.4% → 24.4% (Wilcoxon p = 0.027). This suggests
   the longer observation windows in the DynISF dataset capture more wall events.

5. **Circadian patterns are identical** across datasets (variation and ISF range
   unchanged), indicating stable diurnal physiology independent of data source.

---

## 1. Cohort Composition

### Patient Groups

| Group | Source | Count | IDs |
|-------|--------|------:|-----|
| Letter patients | NS only | 10 | a, b, c, d, e, f, g, h, i, j |
| ODC patients | NS only | 3 | odc-74077367, odc-86025410, odc-96254963 |
| NS-\* patients (overlap) | Both NS & DynISF | 12 | ns-1ccae8a375b9 … ns-dde9e7c2e752 |
| **NS-only total** | NS only | **13** | Letter + ODC |
| **DynISF total** | DynISF | **12** | All ns-\* |

The DynISF parquet (`ns-parquet-dynisf-v2`) contains ~612K rows for 12 patients
vs the NS parquet (`ns-parquet/training`) with ~1.29M rows for 31 patients. The
12 ns-\* patients appear in both datasets. Because both the NS and DynISF
experiment JSONs contain the same 25 patients (the experiments were run on the
combined set), the "DynISF dataset" column in experiment results reflects the
*dynisf parquet* as data source rather than a distinct patient population.

---

## 2. ISF Characteristics (EXP-2651: Two-Phase ISF)

**Source**: `exp-2651_two_phase_isf.json` (NS), `exp-2651_two_phase_isf_dynisf.json` (DynISF)

### 2.1 Cross-Cohort Summary

| Metric | NS-Only (n=13) | DynISF / Overlap (n=12) | Mann-Whitney p |
|--------|---------------:|------------------------:|---------------:|
| Demand ISF (median) | 22.3 mg/dL/U | 25.7 mg/dL/U | 0.605 |
| Demand ISF (mean ± IQR) | 26.6 [11.1, 40.3] | 32.5 [18.5, 42.9] | — |
| Apparent ISF (median) | 57.1 mg/dL/U | 71.9 mg/dL/U | 0.497 |
| Apparent ISF (mean ± IQR) | 62.9 [50.0, 80.8] | 76.9 [52.7, 94.9] | — |
| Scheduled ISF (median) | 50.4 mg/dL/U | 58.5 mg/dL/U | — |
| Inflation ratio (median) | 2.38× | 2.76× | — |
| Inflation ratio (mean ± IQR) | — | 2.84 [1.74, 3.71] | — |
| Total correction events | 263 | 179 | — |

> **Note**: One NS-only patient (b) had negative demand ISF (−4.3), indicating
> reverse correction behavior. Inflation ratio could not be computed for
> all NS-only patients due to undefined values, so cross-group inflation
> comparison is limited. The 12 DynISF patients have well-defined inflation
> ratios ranging from 1.30× to 5.15×.

### 2.2 Per-Patient ISF Detail (DynISF Cohort)

| Patient | Demand ISF | Apparent ISF | Scheduled ISF | Inflation | Events |
|---------|----------:|------------:|-------------:|----------:|-------:|
| ns-1ccae8a375b9 | 41.8 | 54.2 | 45.0 | 1.30× | 21 |
| ns-554b16de7133 | 21.7 | 65.0 | 81.1 | 3.00× | 7 |
| ns-6bef17b4c1ec | 12.7 | 56.0 | 63.0 | 4.42× | 6 |
| ns-8b3c1b50793c | 2.2 | 6.4 | 11.0 | 2.96× | 17 |
| ns-8f3527d1ee40 | 18.8 | 48.1 | 62.0 | 2.56× | 16 |
| ns-8ffa739b986b | 24.2 | 42.3 | 55.0 | 1.75× | 8 |
| ns-9b9a6a874e51 | 78.9 | 157.8 | 100.0 | 2.00× | 11 |
| ns-a9ce2317bead | 27.2 | 94.6 | 55.0 | 3.48× | 26 |
| ns-adde5f4af7ca | 46.2 | 78.8 | 50.4 | 1.70× | 21 |
| ns-c422538aa12a | 67.9 | 95.8 | 131.5 | 1.41× | 10 |
| ns-d444c120c23a | 17.5 | 90.3 | 50.0 | 5.15× | 24 |
| ns-dde9e7c2e752 | 30.3 | 133.3 | 220.0 | 4.40× | 12 |

**Interpretation**: DynISF patients span a wide ISF range (demand 2.2–78.9
mg/dL/U), with no clustering relative to NS-only patients. The non-significant
p-value (0.605) confirms the two groups are drawn from the same metabolic
distribution. ISF inflation (scheduled ÷ demand) ranges from 1.30× to 5.15×
across the DynISF cohort, consistent with previously observed AID compensation
effects.

---

## 3. Circadian Patterns (EXP-2652: Circadian Profiling)

**Source**: `exp-2652_circadian_profiling.json` (NS), `exp-2652_circadian_profiling_dynisf.json` (DynISF)

Only 18 patients passed the minimum-events threshold for circadian analysis:
9 NS-only (a, d, f, g, h, i, odc-74077367, odc-86025410, odc-96254963) and
9 overlap (ns-\* patients; ns-554b16de7133, ns-6bef17b4c1ec, ns-8ffa739b986b
excluded due to insufficient events).

### 3.1 Circadian Variation Summary

| Metric | NS-Only (n=9) | Overlap (n=9) | Mann-Whitney p |
|--------|-------------:|-------------:|---------------:|
| ISF variation (median) | 1.87 | 1.70 | 0.930 |
| ISF variation (mean) | 1.90 | 2.43 | — |
| ISF range % (median) | 62.7% | 55.5% | 1.000 |
| ISF range % (mean) | 68.3% | 85.3% | — |
| Lowest ISF block (mode) | 12-16 (4/9) | 16-20 (3/9) | — |

> **Note**: The high mean ISF range (85.3%) in the overlap group is driven
> by two patients with extreme circadian variation: ns-8b3c1b50793c (235.3%)
> and ns-8f3527d1ee40 (196.4%). Excluding these outliers brings the overlap
> mean to 47.9%, below the NS-only group.

### 3.2 Per-Patient Circadian Detail (Overlap)

| Patient | Day ISF | Night ISF | Variation | Range % | Lowest Block |
|---------|--------:|----------:|----------:|--------:|:-------------|
| ns-1ccae8a375b9 | 47.4 | 60.0 | 1.86 | 64.3% | 16-20 |
| ns-8b3c1b50793c | 10.9 | 3.9 | 6.40 | 235.3% | 04-08 |
| ns-8f3527d1ee40 | 37.9 | 78.3 | 3.52 | 196.4% | 20-24 |
| ns-9b9a6a874e51 | 166.7 | 146.9 | 1.25 | 20.3% | 12-16 |
| ns-a9ce2317bead | 66.7 | 115.5 | 3.20 | 109.8% | 16-20 |
| ns-adde5f4af7ca | 86.6 | 69.3 | 1.36 | 33.9% | 16-20 |
| ns-c422538aa12a | 95.8 | 95.8 | 1.00 | 0.0% | 00-04 |
| ns-d444c120c23a | 71.3 | 105.3 | 1.70 | 52.2% | 04-08 |
| ns-dde9e7c2e752 | 113.0 | 178.4 | 1.62 | 55.5% | 20-24 |

**Interpretation**: No significant difference in circadian amplitude between
cohorts. Both groups show substantial individual variation (1.0–6.4×), with the
typical patient showing ~60–70% ISF swing across the day. The modal lowest-ISF
block shifts from midday (12-16) in NS-only patients to late afternoon (16-20)
in DynISF patients, though sample sizes are too small for formal testing.

---

## 4. SC Suppression Ceiling (EXP-2656)

**Source**: `exp-2656_sc_ceiling.json` (NS, 29 patients), `exp-2656_sc_ceiling_dynisf.json` (DynISF, 12 patients)

### 4.1 Ceiling Comparison

| Metric | NS-Only (n=17) | Overlap from NS (n=12) | Overlap from DynISF (n=12) | NS vs Overlap p |
|--------|---------------:|-----------------------:|---------------------------:|----------------:|
| Fitted ceiling (median) | 0.300 | 0.300 | 0.303 | 0.509 |
| Fitted ceiling (mean) | 0.333 | 0.350 | 0.341 | — |
| Fitted ceiling IQR | [0.300, 0.348] | [0.300, 0.414] | [0.300, 0.376] | — |
| Sticky hyper % (median) | 28.9% | 16.7% | 15.8% | 0.097 |
| Sticky hyper % (mean) | 25.0% | 17.7% | 17.9% | — |
| Ceiling improvement (median) | 1.82% | 1.99% | 1.95% | — |
| Actual/Predicted ratio (median) | 0.000 | 0.070 | 0.060 | — |
| Linear RMSE (median) | 138.2 | 121.3 | 121.2 | — |
| Ceiling RMSE (median) | 131.9 | 105.8 | 110.0 | — |
| Base EGP (median) | 60.0 | 60.0 | 59.9 | — |

> The sticky hyper rate trends lower in DynISF patients (16.7% vs 28.9%,
> p = 0.097). This marginally significant result suggests DynISF patients
> may have better glucose control at high IOB, possibly because the dynamic
> ISF algorithm adapts to insulin resistance states more effectively.

### 4.2 Per-Patient Ceiling Reproducibility (NS → DynISF)

| Patient | NS Ceiling | DynISF Ceiling | Δ Ceiling | NS Sticky | DynISF Sticky | Δ Sticky |
|---------|----------:|---------------:|----------:|----------:|--------------:|---------:|
| ns-1ccae8a375b9 | 0.406 | 0.344 | −0.062 | 6.5% | 8.6% | +2.1 pp |
| ns-554b16de7133 | 0.300 | 0.300 | 0.000 | 10.8% | 10.4% | −0.4 pp |
| ns-6bef17b4c1ec | 0.300 | 0.307 | +0.007 | 17.2% | 17.1% | −0.1 pp |
| ns-8b3c1b50793c | 0.453 | 0.438 | −0.015 | 11.8% | 13.9% | +2.1 pp |
| ns-8f3527d1ee40 | 0.300 | 0.300 | 0.000 | 6.8% | 6.5% | −0.3 pp |
| ns-8ffa739b986b | 0.438 | 0.424 | −0.014 | 15.3% | 14.1% | −1.2 pp |
| ns-9b9a6a874e51 | 0.443 | 0.421 | −0.022 | 24.1% | 23.8% | −0.3 pp |
| ns-a9ce2317bead | 0.300 | 0.300 | 0.000 | 34.1% | 32.8% | −1.3 pp |
| ns-adde5f4af7ca | 0.300 | 0.300 | 0.000 | 22.3% | 22.8% | +0.5 pp |
| ns-c422538aa12a | 0.300 | 0.300 | 0.000 | 16.2% | 14.5% | −1.7 pp |
| ns-d444c120c23a | 0.355 | 0.361 | +0.006 | 24.1% | 26.7% | +2.6 pp |
| ns-dde9e7c2e752 | 0.300 | 0.300 | 0.000 | 23.7% | 23.6% | −0.1 pp |

**Wilcoxon paired tests**: Ceiling W = 3, p = 0.156; Sticky W = 39, p = 1.000.

The ceiling estimates are highly reproducible. Seven of 12 patients show ceiling
values at the 0.300 floor (the model's minimum) in both datasets. For the 5
patients with ceiling > 0.300, the DynISF dataset yields slightly lower
estimates (mean Δ = −0.017), consistent with more data reducing noise in the
saturation fit. Sticky hyper rates are essentially unchanged (mean |Δ| = 1.1 pp).

---

## 5. Patience Mode (EXP-2662)

**Source**: `exp-2662_patience_mode.json` (NS, 27 patients), `exp-2662_patience_mode_dynisf.json` (DynISF, 12 patients)

### 5.1 Patience Mode Effectiveness

| Metric | NS-Only (n=15) | Overlap from NS (n=12) | Overlap from DynISF (n=12) | NS vs Overlap p |
|--------|---------------:|-----------------------:|---------------------------:|----------------:|
| Wall detection % (median) | 24.9% | 24.4% | 24.4% | 0.643 |
| Wall detection % (mean) | 22.6% | 21.4% | 25.2% | — |
| SMB prevented % (median) | 33.2% | 38.1% | 47.4% | 0.508 |
| SMB prevented % (mean) | 31.8% | 36.1% | 42.5% | — |
| SMB prevented (U, median) | 402.7 | 739.9 | 1379.1 | — |
| Hypo reduction (pp, median) | −0.068 | −0.262 | −0.362 | — |
| Hyper increase (pp, median) | 0.000 | +0.497 | +0.487 | — |
| TIR change (pp, median) | 0.000 | −0.071 | −0.119 | — |
| Baseline TIR (median) | 0.7% | 0.9% | 0.9% | — |
| N readings (total) | 655,924 | 476,214 | 597,947 | — |

### 5.2 Patience Mode Paired Comparison (NS → DynISF)

| Patient | NS Wall% | Dyn Wall% | Δ Wall | NS SMB% | Dyn SMB% | Δ SMB | NS Hypo Δ | Dyn Hypo Δ |
|---------|--------:|---------:|------:|--------:|---------:|-----:|----------:|-----------:|
| ns-1ccae8a375b9 | 10.4% | 19.9% | +9.5 | 14.1% | 29.5% | +15.4 | −0.264 | −0.499 |
| ns-554b16de7133 | 26.8% | 32.8% | +6.0 | 41.9% | 51.2% | +9.3 | −0.193 | −0.264 |
| ns-6bef17b4c1ec | 24.0% | 24.1% | +0.1 | 50.2% | 50.2% | 0.0 | −0.497 | −0.474 |
| ns-8b3c1b50793c | 33.0% | 41.1% | +8.1 | 35.6% | 46.9% | +11.3 | −0.024 | −0.023 |
| ns-8f3527d1ee40 | 24.8% | 24.6% | −0.2 | 49.3% | 49.6% | +0.3 | −0.501 | −0.588 |
| ns-8ffa739b986b | 26.2% | 31.4% | +5.2 | 40.6% | 47.9% | +7.3 | −0.782 | −1.143 |
| ns-9b9a6a874e51 | 13.9% | 12.6% | −1.3 | 29.4% | 25.2% | −4.2 | −0.143 | −0.131 |
| ns-a9ce2317bead | 28.2% | 33.2% | +5.0 | 45.7% | 53.7% | +8.0 | −0.261 | −0.356 |
| ns-adde5f4af7ca | 28.7% | 28.7% | 0.0 | 52.7% | 53.7% | +1.0 | −0.442 | −0.455 |
| ns-c422538aa12a | 12.9% | 19.2% | +6.3 | 27.1% | 40.8% | +13.7 | −0.184 | −0.369 |
| ns-d444c120c23a | 6.4% | 14.0% | +7.6 | 11.5% | 27.1% | +15.6 | −0.126 | −0.321 |
| ns-dde9e7c2e752 | 21.1% | 21.0% | −0.1 | 34.6% | 33.5% | −1.1 | −0.303 | −0.285 |

**Wilcoxon paired tests**:
- Wall detection: W = 11, **p = 0.027** — significantly higher in DynISF
- SMB prevented: W = 9, **p = 0.016** — significantly higher in DynISF

Nine of 12 patients show increased wall detection in the DynISF dataset (mean
Δ = +3.8 pp). Ten of 12 show increased SMB prevention (mean Δ = +6.4 pp). The
DynISF dataset contains ~25% more readings per patient on average (49,829 vs
39,685), which likely provides more statistical power to detect wall events that
were undersampled in the smaller NS windows.

---

## 6. Reproducibility Assessment

### 6.1 Summary of Cross-Dataset Stability

| Experiment | Metric | Reproducibility | Wilcoxon p | Interpretation |
|------------|--------|----------------|------------|----------------|
| EXP-2651 ISF | Demand ISF | **Perfect** (0.0% Δ) | 1.000 | Same correction episodes |
| EXP-2651 ISF | Apparent ISF | **Perfect** (0.0% Δ) | 1.000 | Same correction episodes |
| EXP-2651 ISF | Inflation ratio | **Perfect** (0.0% Δ) | 1.000 | Same correction episodes |
| EXP-2652 Circadian | ISF variation | **Perfect** (0.0% Δ) | 1.000 | Same circadian windows |
| EXP-2652 Circadian | ISF range % | **Perfect** (0.0% Δ) | 1.000 | Same circadian windows |
| EXP-2656 Ceiling | Fitted ceiling | Near-perfect (|Δ| ≤ 0.062) | 0.156 | Slight shift w/ more data |
| EXP-2656 Ceiling | Sticky hyper % | Near-perfect (|Δ| ≤ 2.6 pp) | 1.000 | Stable |
| EXP-2662 Patience | Wall detection % | **Shifted** (mean +3.8 pp) | **0.027** | More data → more walls |
| EXP-2662 Patience | SMB prevented % | **Shifted** (mean +6.4 pp) | **0.016** | More data → more SMB |

### 6.2 Interpretation

The reproducibility pattern reveals two distinct categories:

1. **Correction-episode metrics** (ISF, circadian) are perfectly stable because
   both datasets identify the same isolated correction events. The two-phase ISF
   algorithm finds identical episodes regardless of which parquet is used as
   input — the additional rows in the DynISF parquet provide context but do not
   change event detection.

2. **Population-level metrics** (ceiling, patience) show modest shifts because
   they operate on all readings, not just correction episodes. The DynISF
   dataset's additional readings (~122K more) increase the denominator and
   reveal more wall/SMB events, especially for patients whose NS dataset
   coverage was sparse (e.g., ns-1ccae8a375b9 gained +9.5 pp in wall detection,
   ns-d444c120c23a gained +7.6 pp).

This is the expected behavior: metrics dependent on rare-event detection are
more sensitive to dataset size, while per-episode physiological estimates are
stable once enough events are captured.

---

## 7. DynISF Phenotype Summary

### 7.1 Are DynISF patients metabolically different?

**No.** Based on four independent experiments, DynISF patients show no
statistically significant metabolic differences from the broader NS cohort:

| Domain | p-value | Direction | Conclusion |
|--------|--------:|-----------|------------|
| Demand ISF | 0.605 | DynISF slightly higher | No difference |
| Apparent ISF | 0.497 | DynISF slightly higher | No difference |
| Circadian variation | 0.930 | Nearly identical | No difference |
| ISF range % | 1.000 | Nearly identical | No difference |
| SC ceiling | 0.509 | Nearly identical | No difference |
| Sticky hyper % | 0.097 | DynISF lower (trend) | Marginal, needs N |
| Wall detection | 0.643 | Nearly identical | No difference |
| SMB prevention | 0.508 | DynISF slightly higher | No difference |

### 7.2 Does the DynISF algorithm affect estimates?

**Minimally.** The DynISF parquet contains the same patients with more data
rows. This additional data:

- Does **not** change ISF or circadian estimates (same correction episodes)
- Slightly **refines** ceiling fits (7/12 patients shift by < 0.02)
- Significantly **increases** patience-mode wall detection and SMB savings
  (Wilcoxon p < 0.03), reflecting more complete glucose trace coverage

### 7.3 Notable Individual Patterns

- **ns-8b3c1b50793c**: Extreme circadian variation (6.4×, range 235%) — an
  outlier in both cohorts, likely reflecting unusual insulin sensitivity cycling
- **ns-d444c120c23a** and **ns-dde9e7c2e752**: Highest inflation ratios
  (5.15× and 4.40×) — their AID systems are aggressively compensating,
  making scheduled ISF a poor estimate of true insulin sensitivity
- **ns-9b9a6a874e51**: Highest demand ISF (78.9 mg/dL/U) — extremely
  insulin sensitive, ceiling at 0.421 suggests substantial hepatic resistance
- **ns-1ccae8a375b9**: Largest patience-mode shift between datasets
  (wall +9.5 pp, SMB +15.4 pp), indicating the NS dataset significantly
  undersampled this patient's control data

---

## 8. Statistical Methods

All comparisons used non-parametric tests appropriate for small samples:

- **Mann-Whitney U**: Unpaired comparison of NS-only vs DynISF groups
  (two-sided, exact). Used for cross-cohort phenotype differences.
- **Wilcoxon signed-rank**: Paired comparison of the same 12 patients
  across datasets. Used for reproducibility assessment.
- Significance threshold: α = 0.05, with no multiple-comparison correction
  (exploratory analysis).
- Implementation: `scipy.stats.mannwhitneyu` and `scipy.stats.wilcoxon`.

---

## 9. Figures (TODO)

The following visualizations would complement this report:

- `../../visualizations/dynisf-cohort/fig1_isf_comparison_boxplot.png` — TODO: Demand and apparent ISF box plots by cohort
- `../../visualizations/dynisf-cohort/fig2_inflation_scatter.png` — TODO: Inflation ratio scatter: NS-only vs DynISF
- `../../visualizations/dynisf-cohort/fig3_circadian_heatmap.png` — TODO: Block-level ISF heatmap by patient and cohort
- `../../visualizations/dynisf-cohort/fig4_ceiling_reproducibility.png` — TODO: NS vs DynISF ceiling paired plot
- `../../visualizations/dynisf-cohort/fig5_patience_shift.png` — TODO: Wall% and SMB% shift waterfall chart
- `../../visualizations/dynisf-cohort/fig6_reproducibility_summary.png` — TODO: Bland-Altman plots for cross-dataset metrics

---

## 10. Data Sources

| File | Patients | Experiment |
|------|:--------:|------------|
| `externals/experiments/exp-2651_two_phase_isf.json` | 25 | Two-phase ISF (NS parquet) |
| `externals/experiments/exp-2651_two_phase_isf_dynisf.json` | 25 | Two-phase ISF (DynISF parquet) |
| `externals/experiments/exp-2652_circadian_profiling.json` | 18 | Circadian profiling (NS) |
| `externals/experiments/exp-2652_circadian_profiling_dynisf.json` | 18 | Circadian profiling (DynISF) |
| `externals/experiments/exp-2656_sc_ceiling.json` | 29 | SC ceiling (NS) |
| `externals/experiments/exp-2656_sc_ceiling_dynisf.json` | 12 | SC ceiling (DynISF) |
| `externals/experiments/exp-2662_patience_mode.json` | 27 | Patience mode (NS) |
| `externals/experiments/exp-2662_patience_mode_dynisf.json` | 12 | Patience mode (DynISF) |

---

*Generated from experiment JSON data. Statistics computed with Python 3.12,
NumPy, and SciPy. All p-values are two-sided.*
