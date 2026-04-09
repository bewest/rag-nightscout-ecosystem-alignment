# Comprehensive Meal Data Science Synthesis

**Date**: 2026-04-09  
**Experiments**: EXP-1291–1301, EXP-1309, EXP-1341, EXP-1551–1571, EXP-1591–1598  
**Dataset**: 11 patients, 1,838 patient-days, 529,288 CGM steps, 50,810 natural experiments  
**Scope**: Detection → Characterization → Normalization → Periodicity → Sensitivity → Archetypes

---

## Executive Summary

Across 8 research phases and 30+ experiments, we have built a complete data-science picture of meals in AID (Automated Insulin Delivery) patients. This report synthesizes all findings into seven major takeaways — the big conclusions that emerge only when the full body of evidence is considered together.

**The core insight**: Meals in AID patients are simultaneously simpler and more complex than assumed. Simpler because 45% of patients have robust, clock-like meal patterns that survive any reasonable detection method. More complex because the AID loop itself fundamentally alters what "a meal" looks like in the data — masking true metabolic cost, dampening corrections, and creating a measurement problem where entered carbs, algorithm estimates, and glucose responses all tell different stories.

---

## 1. The Meal Counting Problem: 2,619 or 12,060?

The single most important methodological finding is that **meal count depends enormously on how you look**.

| Detection Method | Meals | Per Patient/Day | What It Captures |
|------------------|-------|-----------------|------------------|
| Census (≥5g, 30-min merge) | 4,072 | 2.2 | All carb events including snacks |
| Medium (≥5g, 90-min merge) | 3,272 | 1.8 | Merged close events |
| Therapy (≥18g, 90-min merge) | 2,619 | 1.4 | Major meals only |
| UAM-inclusive detection | 12,060 | 6.6 | All glucose excursions (76.5% unannounced) |

The 72-configuration benchmark (EXP-1569) showed this isn't just academic: **the choice of min_carb_g and hysteresis_min changes every downstream metric** — regularity, size distribution, announced fraction, and metabolic quality scores. The optimal "knee" at **5g/150min** (1.51 meals/day, efficiency ratio 26.0) represents the best universal trade-off between sensitivity and signal quality.

**Takeaway**: There is no single "true" meal count. The appropriate definition depends on the clinical question. For meal timing analysis, therapy config (≥18g) is best. For carb estimation, UAM-inclusive detection captures the full metabolic picture. For AID tuning, the knee config balances both.

---

## 2. ISF Normalization Fundamentally Re-Ranks Patients

Raw glucose excursion (mg/dL) is the standard way to assess meal impact, but it ignores a 4.5× variation in insulin sensitivity across patients. ISF-normalized excursion (correction-equivalents) reveals who is actually metabolically struggling.

| Patient | Profile ISF | Raw Excursion | ISF-Normalized | Rank Change |
|---------|-------------|---------------|----------------|-------------|
| f | 21 mg/dL/U | 104.9 mg/dL | **4.99** | 3rd → **1st** |
| i | 50 mg/dL/U | 131.0 mg/dL | **2.62** | 1st → 2nd |
| b | 95 mg/dL/U | 73.1 mg/dL | **0.77** | Mid → **Best** |
| c | 75 mg/dL/U | 109.8 mg/dL | 1.46 | 2nd → Mid |

Patient f's 105 mg/dL excursion looks moderate, but at ISF=21 mg/dL/U, each excursion costs **5 units of correction insulin** — the most metabolically expensive meals in the cohort. Patient b's 73 mg/dL excursion at ISF=95 is trivially corrected with <1 unit.

The ISF-normalized framework creates clinically meaningful thresholds:
- **< 1.0 correction-equivalent**: Well-managed (typical for high-ISF patients)
- **1.0–2.0**: Normal range
- **> 2.0**: Metabolically expensive (settings review recommended)

**Takeaway**: Raw mg/dL excursion is misleading for cross-patient comparison. ISF normalization reveals the true metabolic burden of meals and identifies patients whose AID settings may be masking poor control.

---

## 3. Supply × Demand Spectral Power Is Orthogonal to Excursion

The supply×demand spectral power (FFT-based energy of insulin-glucose interaction) captures something entirely different from excursion: **how hard the AID loop is working during a meal**.

| Metric Pair | Correlation | Interpretation |
|-------------|-------------|----------------|
| Raw excursion vs ISF-norm | r = 0.732 | Strong (related but not identical) |
| **ISF-norm vs Spectral Power** | **r = −0.039** | **Orthogonal (completely independent)** |
| Carbs vs Spectral Power | r = 0.433 | Moderate (larger meals → more AID activity) |

This orthogonality creates a powerful 2D meal quality framework:

```
                    High Spectral Power
                         │
    "AID Working Hard    │    "Well-Managed"
     but Still High"     │     ✓ Best outcome
                         │
    ─────────────────────┼─────────────────────
                         │
    "Undertreated"       │    "Low Excursion,
     ✗ Worst outcome     │     Low AID Activity"
                         │
                    Low Spectral Power
       High Excursion ←──────→ Low Excursion
```

**Spectral power scales super-linearly with carb size** (~21× from small to large meals), meaning the AID loop's response is disproportionately stronger for large meals. This matches the clinical expectation that AID algorithms use SMB/temp-basal more aggressively for larger glucose rises.

**Per-patient spectral extremes**:
- Patient h: 25.6M (highest) — very active AID despite moderate excursion → well-tuned
- Patients d, k: near-zero — minimal supply×demand dynamics → possible AID disengagement

**Takeaway**: Excursion alone misses half the story. The 2D excursion × spectral-power framework identifies undertreated meals (high glucose, low AID response) that single-metric approaches miss.

---

## 4. Carb Estimation: Four Algorithms, Four Different Realities

Comparing four carb estimation algorithms on 12,060 meals (EXP-1341) reveals fundamental disagreements about meal size:

| Algorithm | Median Estimate | Correlation with Entered | What It Actually Measures |
|-----------|----------------|--------------------------|---------------------------|
| Physics residual | 22.6g | r = 0.093 (worst) | Total unexplained glucose rise (incl. dawn, stress) |
| oref0 deviation | 21.8g | **r = 0.368 (best)** | COB-predicted vs actual deviation |
| Glucose excursion | 7.8g | r = 0.263 | Simple peak-to-trough amplitude |
| Loop IRC | 5.6g | r = 0.334 | Insulin-attributed carb absorption |

The **4× gap between oref0 (22g) and Loop IRC (6g)** for unannounced meals has direct clinical consequences: oref0/AAPS treats UAM as a substantial meal requiring ~22g of coverage, while Loop's conservative IRC estimates ~6g. This explains why AAPS users report more aggressive UAM correction and why Loop is perceived as "slower to respond" to unannounced meals.

**The entered-carbs problem**: User-entered carbs (median 30g) correlate only modestly with any algorithm (max r=0.368). Entered carbs suffer from rounding artifacts (clusters at 10g, 15g, 20g, 30g), selection bias (patients announce larger meals), and AID blunting (the loop reduces the glucose response, making the entry appear "too high"). Entered carbs are **not reliable ground truth** for carb estimation validation.

**Takeaway**: No single algorithm captures "true" carbs. oref0 deviation is closest to entered carbs; physics captures the broadest set of metabolic events; Loop IRC is most conservative. An ensemble approach (physics for detection, oref0 for magnitude) would combine strengths.

---

## 5. 76.5% of Meals Are Unannounced — And They Look Different

Across 12,060 detected meals, only 23.5% have matching carb entries. The unannounced majority (76.5%) has distinct characteristics:

| Dimension | Announced (n=2,837) | Unannounced/UAM (n=9,223) | Δ |
|-----------|---------------------|---------------------------|---|
| Raw excursion | 80.5 mg/dL | 105.0 mg/dL | +30% |
| ISF-normalized | 1.70 | 1.44 | −15% |
| Spectral power | Higher | Lower | AID less active |
| Mean carbs (oref0) | 27.9g | 19.9g | −29% |

The paradox: announced meals have **higher raw excursion** but **lower ISF-normalized excursion**. This is selection bias — patients tend to announce larger meals (median 30g entered), and those patients tend to have lower ISF (more insulin-sensitive). When corrected for ISF, unannounced meals are actually more metabolically expensive per-gram.

From meal clustering (EXP-1591–1598), all meals partition into exactly **2 response phenotypes**:
- **Controlled rise** (53%): excursion = 35 mg/dL, peak at 28 min — AID catches it early
- **High excursion** (47%): excursion = 102 mg/dL, peak at 102 min — AID response lags

**Bolus timing explains 11× more excursion variance than dose** (R² = 8.9% vs 0.8%). Pre-bolusing is the single highest-leverage behavior change for meal management. This holds regardless of carb amount — even "wrong" carb estimates with good timing produce better outcomes than accurate estimates with late boluses.

**Takeaway**: The majority of metabolic events are invisible to carb-based analysis. UAM detection is not optional — it's the primary meal signal. And for the meals that are announced, **timing beats accuracy** for bolus optimization.

---

## 6. The Meal Clock: 45% of Patients Are Robust, 36% Need Personalization

The most surprising finding of the entire research program is how **binary** patients are in their meal-clock behavior. There is no smooth continuum — patients cluster sharply into archetypes.

### Robustness Tiers (EXP-1571)

| Tier | n (%) | σσ Range | Peaks | Defining Feature |
|------|-------|----------|-------|------------------|
| **Robust** | 5 (45%) | 0.28–0.59 | 2–4 | Any detection config works |
| **Moderate** | 2 (18%) | 0.82–0.99 | 2 | Config matters somewhat |
| **Sensitive** | 4 (36%) | 1.12–2.24 | 0–1 | Config choice is critical |

### The Key Predictor: Number of Meal Peaks

The single strongest predictor of robustness is **n_peaks** (ρ = −0.851, p = 0.0009). This is the meal-clock equivalent of a structural engineering principle: redundancy creates resilience.

| Peaks | Patients | σσ | Why Robust? |
|-------|----------|-----|-------------|
| 3–4 | c, f, g, j | 0.28–0.59 | Each peak independently anchors the clock |
| 2 | b, h, i | 0.56–0.99 | Marginal — losing one peak destabilizes |
| 0–1 | a, d, e, k | 1.12–2.24 | All structure in one feature; easily disrupted |

### Per-Patient Meal Clock Signatures

| Patient | Weighted Std | Peaks | Archetype | Clinical Implication |
|---------|-------------|-------|-----------|---------------------|
| g | 1.00h | 3 | Clock-like | Time-of-day profiles viable |
| j | 1.58h | 4 | Clock-like | Four-meal structure |
| b | 3.32h | 2 | Moderate | Two-meal anchor |
| c | 4.43h | 3 | "Consistently irregular" | Diffuse but stable biology |
| a | 7.29h | 1 | Random | No exploitable pattern |
| k | 4.17h | 0 | Insufficient (22 meals) | Logging compliance issue? |

Patient c is the most informative outlier: **high entropy (0.96) but low σσ (0.39)**. This is the "consistently irregular" archetype — the patient genuinely eats diffusely across the day, and this diffusion is biologically real, not detection noise. The regularity of their irregularity makes them robust.

### Periodicity Findings

- **Population**: No systematic weekday vs weekend shift (meals/week: 15.7 uniform)
- **Lunch is most synchronized** across patients (inter-patient std = 0.26h)
- **Dinner is most variable** within patients (within-patient std = 1.01h)
- **Weekend effects**: 50/50 split — some patients shift, others don't. No universal pattern.

**Takeaway**: For robust patients (45%), any reasonable detection config works — invest in metabolic analysis, not detection tuning. For sensitive patients (36%), per-patient parameter optimization is essential. The n_peaks metric is a cheap, reliable triage tool: count someone's meal peaks, and you immediately know how much detection tuning they need.

---

## 7. The AID Loop Is the Dominant Confound — And the Dominant Signal

Every meal analysis confronts the same fundamental challenge: **the AID loop is always active, and it changes everything**.

### How AID Distorts Meal Signals

| What We Measure | What AID Does | Impact |
|-----------------|---------------|--------|
| Glucose excursion | Delivers correction insulin → reduces peak | Excursion 20–40% lower than uncontrolled |
| Effective ISF | Suspends basal during corrections → total insulin → 0 | ISF ratio degenerates (3.62× deconfounded vs 2.72× raw) |
| Carb estimates | Bolus covers part of meal → algorithm sees smaller residual | Loop IRC underestimates by 4× vs oref0 |
| Basal adequacy | Modulates basal continuously → scheduled rate irrelevant | Loop runs at scheduled basal only 3–77% of the time |
| Meal timing | Pre-bolus creates early glucose dip → shifts apparent meal start | Peak detection shifted 5–15 min vs true intake |

### Key AID Confounding Results

- **Effective ISF is 1.36× profile ISF** (population mean, range 1.0–2.2×). AID masks inadequate settings by adjusting temp basals.
- **Physics ML UAM detection (F1=0.513) outperforms oref0 UAM (F1=0.344)** by 49% — but oref0 has 31% longer lead time (38 vs 29 min).
- **Response-curve ISF** (exponential fit, R²=0.805) is the correct method for AID patients. The traditional total-insulin denominator degenerates because the loop suspends basal during corrections.
- **Population effective DIA = 6.0h** (vs 5h profile). 4/7 patients have DIA longer than profile, meaning the insulin tail extends further than their settings assume.

### The Supply × Demand Conservation Law

The physics model's supply×demand framework reveals a conservation principle: at steady state, insulin supply must match glucose demand. Meals break this equilibrium, and the AID loop's response creates a characteristic spectral signature.

- **Spectral power correlates with carb size** (r=0.433) but **not with excursion** (r=−0.039)
- This means spectral power measures **AID effort**, not outcome — a loop working hard with low excursion is succeeding
- **Hysteresis conserves total carbs/day** (CV ≤ 0.2%) while **min_carb filtering destroys** 50%+ of carb signal — confirming hysteresis is temporal reorganization, not information loss

**Takeaway**: The AID loop is not noise to be removed — it's signal to be decoded. Supply×demand spectral power, response-curve ISF, and UAM-augmented physics models all extract clinically useful information *because* they model the loop, not despite it.

---

## Cross-Cutting Themes

### Theme A: The Personalization Gradient

Every analysis reveals a spectrum from universal to personal:

| Level | Finding | Applicable Patients |
|-------|---------|---------------------|
| Universal | UAM threshold = 1.0 mg/dL/5min | 100% (110/110 cross-patient transfers) |
| Universal | Knee config: 5g/150min | ~80% reasonable performance |
| Population | 2 meal clusters (controlled/high) | 100% (ARI=0.976 cross-patient) |
| Personal | n_peaks determines robustness tier | Tier-specific recommendations |
| Personal | ISF normalization thresholds | Per-patient ISF required |
| Fully personal | Optimal detection config | Sensitive patients only (36%) |

### Theme B: What Entered Carbs Don't Tell You

| What entered carbs capture | What they miss |
|---------------------------|----------------|
| Patient's estimate of carb intake | 76.5% of glucose excursions (UAM) |
| Relative meal size within a patient | Absolute meal size (bias, rounding) |
| Timing of acknowledged meals | Dawn phenomenon, stress, exercise |
| Intent to eat | Actual absorption (gastroparesis, fat/protein) |

### Theme C: The Detection-Sensitivity-Insight Trade-Off

```
Lenient Detection ─────────────────────── Strict Detection
(≥3g, 15min)                              (≥40g, 180min)
│                                          │
├─ More meals (2.7/day)                    ├─ Fewer meals (0.6/day)
├─ Lower quality (0.92)                    ├─ Higher quality (0.98)
├─ Noisy periodicity                       ├─ Clean periodicity
├─ Small meals included                    ├─ Only major meals
├─ Lower ISF-norm excursion (1.3)          ├─ Higher ISF-norm (2.2)
└─ All carbs preserved                     └─ 50%+ carbs filtered
                    ↕
            Knee: 5g/150min
            (1.51 mpd, quality=0.96)
```

---

## Gaps Summary

| ID | Gap | Priority | Remediation |
|----|-----|----------|-------------|
| GAP-ALG-015 | Archetype classification not in production | High | Add n_peaks triage to pipeline |
| GAP-ALG-016 | Spectral power not in meal quality scoring | High | Add 2D framework |
| GAP-ENTRY-030 | No per-patient detection config | Medium | Adaptive selection for sensitive tier |
| GAP-PROF-005 | Time-varying ISF not used | Medium | Use response-curve ISF |
| GAP-CGM-025 | Patient k insufficient meals | Low | Carb logging compliance check |

---

## Experiment Inventory

| Phase | Experiments | Key Deliverable | Figures |
|-------|------------|-----------------|---------|
| 1: Census | EXP-1551–1558 | 50,810 natural experiments catalogued | fig1–7 |
| 2: Sensitivity | EXP-1559 | 3 detection configs compared | fig8 |
| 3: Metabolic | EXP-1561 | ISF-normalized excursion + spectral power | fig9–14 |
| 4: Multi-Config | EXP-1563 | Config effects on metabolic metrics | fig15–16 |
| 5: Periodicity | EXP-1565 | Weekday/weekend: no systematic shift | fig17–24 |
| 6: Meal Clocks | EXP-1567 | Personal regularity: 1.00–7.29h std | fig25–27 |
| 7: Benchmark | EXP-1569 | 72-config sweep, knee at 5g/150min | fig28–33 |
| 8: Archetypes | EXP-1571 | Robust/Moderate/Sensitive classification | fig34–36 |
| — | EXP-1341 | 4-algorithm carb estimation on 12,060 meals | (separate) |
| — | EXP-1301 | Response-curve ISF extraction | (separate) |
| — | EXP-1309 | UAM event rates and classification | (separate) |
| — | EXP-1591–1598 | Meal response clustering (2 phenotypes) | (separate) |

---

## Visualization Index

All 36 figures in `visualizations/natural-experiments/`:

| Figure | Content | Key Insight |
|--------|---------|-------------|
| fig1 | Census heatmap | 50,810 experiments by type × patient |
| fig2 | Time of day | Detector activation by hour |
| fig3 | Duration distributions | Window length by type |
| fig4 | Quality distributions | Score by detector type |
| fig5 | Cross-correlations | Dawn↔ISF (r=0.41), UAM↔Exercise (r=−0.54) |
| fig6 | Response templates | Population meal glucose curves |
| fig7 | Patient profiles | Per-patient experiment signatures |
| fig8 | Meal sensitivity | Config A/B/C comparison |
| fig9 | Carb range metabolic | ISF-norm excursion by carb size |
| fig10 | ISF normalization | Raw → normalized ranking shift |
| fig11 | Metabolic correlations | Excursion × spectral power (orthogonal) |
| fig12 | Carb range distributions | Size histograms by config |
| fig13 | Patient carb heatmap | Per-patient × carb range |
| fig14 | Announced vs unannounced | Selection bias visualization |
| fig15 | Multi-config metrics | ISF-norm + spectral by config |
| fig16 | Multi-config boxplots | Distribution comparison |
| fig17 | Meal periodicity | Shannon entropy by patient |
| fig18 | Mealtime regularity | Weighted std ranking |
| fig19 | Small vs large meals | Metabolic profiles by size |
| fig20 | Periodicity summary | Population-level metrics |
| fig21 | Weekday/weekend timing | Hour distributions by day type |
| fig22 | Per-patient WD/WE | Individual day-type comparison |
| fig23 | Zone shift detail | Breakfast/lunch/dinner timing |
| fig24 | Weekday/weekend metabolic | Metabolic differences by day type |
| fig25 | Personal meal clocks | Per-patient hourly histograms |
| fig26 | Inter-patient variation | Between-patient variability map |
| fig27 | WD/WE regularity | Day-type regularity comparison |
| fig28 | Benchmark count structure | Meals/day across 72 configs |
| fig29 | Benchmark regularity | Weighted std landscape |
| fig30 | Benchmark knee | Efficiency ratio curve |
| fig31 | Benchmark per-patient | Individual robustness trajectories |
| fig32 | Benchmark size | Size distributions by config |
| fig33 | Benchmark robustness | CV ranking by patient |
| fig34 | Archetype distribution | Tier classification + σσ vs n_peaks |
| fig35 | Stability curves | Per-patient regularity vs strictness |
| fig36 | Tier profiles | Tier metric comparison + correlation waterfall |

---

## Conclusion

The seven takeaways form a coherent picture:

1. **Meal count is a definition** — there's no ground truth, only appropriate trade-offs
2. **ISF normalization reveals hidden metabolic burden** — raw mg/dL misleads
3. **Spectral power captures AID effort** — orthogonal to excursion, together they create a 2D quality framework
4. **Carb algorithms disagree by 4×** — entered carbs aren't reliable ground truth either
5. **76.5% of meals are unannounced** — UAM detection is the primary signal, not a fallback
6. **Robustness is binary** — 45% of patients need no tuning, 36% need personalization, n_peaks is the triage tool
7. **The AID loop is signal, not noise** — supply×demand physics, response-curve ISF, and spectral analysis decode it

Together, these findings define a complete framework for meal analysis in AID patients: detect with sensitivity-appropriate thresholds, normalize with ISF, characterize with spectral power, assess periodicity with personal clocks, and triage personalization needs with n_peaks robustness scoring.

---

## Source Files

- `tools/cgmencode/exp_clinical_1551.py` — Natural experiment census and characterization (EXP-1551–1571)
- `tools/cgmencode/exp_clinical_1341.py` — Carb estimation survey
- `tools/cgmencode/exp_clinical_1301.py` — ISF and therapy assessment
- `tools/cgmencode/exp_clinical_1291.py` — AID-deconfounded therapy analysis
- `tools/cgmencode/exp_clinical_1311.py` — UAM and advanced therapy
- `externals/experiments/exp-{1551..1571}_natural_experiments.json` — All result files
- `visualizations/natural-experiments/fig1–36` — All figures
- `docs/60-research/natural-experiments-*` — Phase reports 1–8
- `docs/60-research/carb-estimation-survey-report-2026-04-10.md`
- `docs/60-research/autotune-uam-characterization-report.md`
- `docs/60-research/meal-response-clustering-report.md`
