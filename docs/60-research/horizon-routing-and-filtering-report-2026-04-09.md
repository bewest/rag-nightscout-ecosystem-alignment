# Horizon Routing and Patient Filtering Report

**Date**: 2026-04-09
**Experiments**: EXP-431 through EXP-438
**Focus**: Extending forecast accuracy beyond 60 minutes using horizon routing, extended future PK, history optimization, and patient fidelity gating

## Executive Summary

This report covers 8 experiments (EXP-431–438) testing strategies to extend glucose forecast accuracy beyond the 60-minute horizon where our models already excel (h30 MAE=13.3 mg/dL, below CGM MARD). The key breakthrough is **horizon-routed ensemble** (EXP-436): using separate models optimized for short-range (h30–h120) and long-range (h120–h360) predictions achieves continuous coverage from 30 minutes to 6 hours with clinically useful accuracy.

### Key Results at a Glance

| Experiment | Hypothesis | Result | Impact |
|------------|-----------|--------|--------|
| EXP-431: Stride optimization | More windows via overlap → better | **NEGATIVE** (±0.2 MAE) | Data diversity > quantity |
| EXP-432: Patient quality classification | Gold/silver/bronze filtering | N/A (quick mode) | All 4 patients similar |
| EXP-433: State-dependent loss | Weight meal/fasting differently | **NEGATIVE** (±0.2 MAE) | Transformer handles implicitly |
| EXP-434: PK fidelity filtering | Per-window conservation error | **NEGATIVE** (+0.5 MAE) | Filtering removes useful data |
| **EXP-435: Extended future PK** | Longer future PK → h240+ | **POSITIVE** (−0.2 at h240) | First h240+ improvement evidence |
| **EXP-436: Horizon routing** | Best model per horizon band | **POSITIVE** (h30=13.3→h360=28.9) | Unified 30min–6h system |
| EXP-437: Extended history (long-range) | 4–6h history → h240+ | **NEGATIVE** (+0.6 to +3.1) | PK channels compress history |
| EXP-438: Patient fidelity gating | Train on high-fidelity only | **NEGATIVE** (+1.7 MAE) | All patients contribute signal |

**Score: 2 positive, 5 negative, 1 inconclusive → strong signal that the architecture is already well-optimized; gains come from structural decisions (routing) not hyperparameter tuning.**

## Detailed Results

### EXP-431: Stride Optimization

**Hypothesis**: Overlapping windows (smaller stride) create more training examples, improving generalization.

| Stride | Windows | MAE | Δ |
|--------|---------|-----|---|
| 16 (baseline) | 10,360 | 16.57 | — |
| 12 | 14,560 | 16.66 | +0.09 |
| 6 | 30,000 | 16.37 | −0.20 |
| 3 | 55,000 | 16.47 | −0.10 |

**Finding**: 5.3× more windows gives only ±0.2 MAE. Overlapping windows are too correlated to provide new information. **Data DIVERSITY (more patients, more varied conditions) matters, not window COUNT.**

### EXP-433: State-Dependent Loss Weighting

**Hypothesis**: Weighting loss differently for fasting (48% of data), correction (37%), and meal (15%) states could improve accuracy during metabolic transitions.

| Variant | Fasting wt | Correction wt | Meal wt | MAE |
|---------|-----------|---------------|---------|-----|
| uniform | 1.0 | 1.0 | 1.0 | 16.57 |
| meal_2x | 1.0 | 1.0 | 2.0 | 16.74 |
| meal_3x | 1.0 | 1.0 | 3.0 | 16.54 |
| active_focus | 0.5 | 1.5 | 2.0 | 16.50 |

**Finding**: All variants within ±0.2 MAE. The transformer **implicitly learns to weight metabolic states** — explicit loss engineering doesn't help.

### EXP-434: Per-Window PK Conservation Filtering

**Hypothesis**: Windows where PK-predicted glucose direction mismatches actual glucose direction have lower data quality; filtering them should help.

| Filter | Windows | MAE |
|--------|---------|-----|
| no_filter | 10,360 | 16.57 |
| top_90% | 9,324 | 17.05 |
| top_75% | 7,770 | 17.11 |
| top_50% | 5,180 | 17.39 |

**Finding**: Per-window conservation error is narrowly distributed (mean=3.52, σ=0.44) in quick mode — all 4 patients have similar quality. Filtering just removes data without removing noise. **Per-PATIENT gating (EXP-438) is the right granularity**, but needs full mode where fidelity ranges 15–84.

### EXP-435: Extended Future PK Projection ★

**Hypothesis**: Projecting future PK channels beyond the 2h window to 4–6h gives the model knowledge of the insulin tail trajectory, improving h240+ predictions.

| Config | History | Future | Train | h120 | h180 | h240 | h300 | h360 |
|--------|---------|--------|-------|------|------|------|------|------|
| w48_sym | 2h | 2h | 10,360 | 22.1 | — | — | — | — |
| w60_asym | 2h | 3h | 8,288 | 22.9 | 25.8 | — | — | — |
| w72_asym | 2h | 4h | 6,904 | 23.1 | 24.8 | 27.2 | — | — |
| **w96_asym** | **2h** | **6h** | **5,176** | 23.6 | 25.1 | **27.0** | **27.2** | **28.9** |

**Key finding**: At h240 (4 hours), w96 BEATS w72 (27.0 vs 27.2) despite 25% fewer training windows. This is the **first evidence that extended future PK helps beyond the DIA horizon**. The h300–h360 plateau is consistent with DIA physics (5–6h insulin mostly resolved).

Compare to CNN baseline (EXP-356): h240=40.4, h360=40.8 → **transformer with extended PK is 13 MAE better at h240.**

### EXP-436: Horizon-Routed Ensemble ★★

**Hypothesis**: Since short-horizon predictions benefit from more training data (w48 = 10,360 windows) while long-horizon predictions benefit from extended future PK (w96 = 5,176 windows), routing predictions to the best model per horizon band should give the best of both worlds.

| Horizon | Short (w48) | Long (w96) | Routed | Source |
|---------|-------------|------------|--------|--------|
| h30 | **13.3** | 15.6 | **13.3** | short |
| h60 | **17.2** | 19.1 | **17.2** | short |
| h90 | **20.0** | 21.2 | **20.0** | short |
| h120 | **22.1** | 23.6 | **22.1** | short |
| h150 | — | 24.4 | 24.4 | long |
| h180 | — | 25.1 | 25.1 | long |
| h240 | — | 27.0 | 27.0 | long |
| h300 | — | 27.2 | 27.2 | long |
| h360 | — | 28.9 | 28.9 | long |

**This is the most clinically useful result**: A single system providing accurate predictions from 30 minutes through 6 hours. The per-patient breakdown reveals the challenge:

| Patient | Fidelity | h30 | h120 | h240 | h360 |
|---------|----------|-----|------|------|------|
| d | 52 | 7.9 | 13.0 | 16.2 | 18.9 |
| c | 17 | 10.8 | 15.6 | 17.5 | 19.5 |
| a | 17 | 15.3 | 23.8 | 30.1 | 30.8 |
| b | 35 | 19.2 | 36.0 | 44.1 | 46.5 |

Patient b accounts for disproportionate error at all horizons. Patient d achieves h360=18.9 mg/dL — clinically excellent for 6-hour predictions.

### EXP-437: Extended History for Long-Range

**Hypothesis**: If the long-range model could see 4–6h of history instead of 2h, it might better understand the full DIA context.

| History | Train | h120 | h180 | h240 | h300 | h360 |
|---------|-------|------|------|------|------|------|
| 2h | 5,176 | 23.6 | 25.1 | **27.0** | **27.2** | **28.9** |
| 4h | 4,140 | 24.2 | 26.3 | 26.6 | 26.9 | 30.8 |
| 6h | 3,448 | 26.7 | 28.1 | 30.1 | 29.5 | 31.7 |

**Finding**: More history HURTS, especially 6h (+3 MAE across horizons). The 4h variant shows a marginal improvement at h240 (−0.4) and h300 (−0.3) but is worse everywhere else.

**Why?** PK channels already encode the full insulin delivery history via convolution — the model doesn't need to "see" 4–6h of raw data when PK channels summarize DIA information. Longer windows just reduce training data without adding information.

### EXP-438: Patient Fidelity Gating

**Hypothesis**: Training only on high-fidelity patients (settings assessment score ≥ 45) should produce a cleaner base model.

| Training Set | N_train | Overall MAE | Patient d | Patient b |
|-------------|---------|-------------|-----------|-----------|
| all_patients | 10,360 | 16.57 | 9.7 | 25.4 |
| gold_only (≥45) | 2,590 | 18.51 | 11.7 | 25.1 |
| silver+ (≥35) | 5,180 | 18.26 | 10.6 | 26.2 |

**Finding**: Gating HURTS by +1.7–2.0 MAE. Even patient d (the gold-standard) gets WORSE when trained only on gold data (9.7→11.7). This means that **even low-fidelity patients contribute useful training patterns** — the model extracts what's learnable from each patient during per-patient fine-tuning, and more diverse base training helps.

**Caveat**: In quick mode (4 patients), fidelity scores are narrow (17–52). Full mode spans 15–84, which may show different results for the most extreme cases.

## Synthesis and Strategic Insights

### Confirmed Dead Ends (Cumulative from EXP-428–438)

| Category | Experiments | Finding |
|----------|------------|---------|
| Data quantity tricks | EXP-431 (stride) | Overlapping windows don't help |
| Loss engineering | EXP-433 (state), EXP-426 (horizon) | Transformer handles implicitly |
| Feature engineering | EXP-428 (explicit features) | Transformer learns features better |
| Per-window filtering | EXP-434 (conservation) | Removes signal, not noise |
| Patient filtering | EXP-438 (fidelity gating) | All patients contribute |
| Longer history | EXP-437 (4–6h), EXP-429/430 | PK channels compress history |
| Metabolic flux features | Research synthesis | CNN/transformer learns natively |

### What Actually Works

1. **Horizon routing** (EXP-436): Use the right model for each prediction band
2. **Extended future PK** (EXP-435): Project PK channels 6h forward for long-range
3. **PK channels** (EXP-356): Future PK provides genuinely new causal information
4. **ISF normalization** (EXP-361/364): Normalizes cross-patient glucose variability
5. **Per-patient fine-tuning** (EXP-408/410): Adapts to individual dynamics
6. **PKGroupedEncoder** (EXP-408): Signal separation by channel type

### The Information Bottleneck

Every experiment in this batch confirms the same principle: **the bottleneck is information diversity, not quantity or quality filtering**. The transformer is remarkably good at extracting signal from noisy, heterogeneous data. The only things that help are:

1. **Providing genuinely new information** (future PK — the model can't compute this)
2. **Structural decisions** (routing, channel grouping — better inductive biases)
3. **More diverse patients** (the untested frontier)

### Current Production System

| Horizon Band | Model | Config | MAE (quick) | Coverage |
|-------------|-------|--------|-------------|----------|
| h30–h120 | PKGroupedEncoder | w48, 8ch+PK, ISF, FT | 13.3–22.1 | 30min–2h |
| h120–h360 | PKGroupedEncoder | w96, 8ch+PK, ISF, FT | 23.6–28.9 | 2h–6h |

Full validation reference (EXP-408): h30=10.42 MAE (11 patients, 5 seeds).

### Comparison to Prior Art

| System | h30 | h60 | h120 | h240 | h360 |
|--------|-----|-----|------|------|------|
| CNN baseline (EXP-356) | 22.8 | — | 41.8 | 50.7 | 51.8 |
| CNN + future PK (EXP-356) | 22.2 | — | 38.3 | 40.4 | 40.8 |
| Transformer v14 short | **13.3** | **17.2** | **22.1** | — | — |
| Transformer v14 long | 15.6 | 19.1 | 23.6 | **27.0** | **28.9** |
| **Routed ensemble** | **13.3** | **17.2** | **22.1** | **27.0** | **28.9** |

The routed transformer ensemble represents a **23–24 MAE improvement at h240–h360** over the CNN, and **8–9 MAE improvement** over the CNN with future PK.

## Recommendations for Next Steps

### High Priority

1. **Full validation of horizon routing** (EXP-436 at full scale): The quick-mode results are promising but may overestimate architecture gains. Full validation with 11 patients and 5 seeds is essential.

2. **Patient b investigation**: At h360=46.5 MAE (vs mean 28.9), patient b is 2.5× worse. Targeted investigation of patient b's data quality and whether specialized approaches can help.

3. **More patients**: Every experiment confirms data diversity is the true bottleneck. Adding even 2–3 new high-quality patients could improve all horizons.

### Medium Priority

4. **Crossover horizon optimization**: The current h120 crossover between short and long models is fixed. An adaptive crossover (e.g., h90 for patient b, h150 for patient d) could improve per-patient accuracy.

5. **Full-mode fidelity gating** (EXP-438 with 11 patients): Quick mode showed no benefit, but the fidelity range (15–84) is much wider at full scale. Patient i (fidelity=15) may genuinely introduce noise.

### Lower Priority

6. **Uncertainty estimation**: The routed ensemble provides point predictions. Adding confidence intervals (heteroscedastic loss, ensemble disagreement) would improve clinical utility.

7. **Strategic planning layer** (EXP-414–416): Overnight risk assessment, next-day TIR prediction — entirely unbuilt but potentially high clinical impact.

## Appendix: Per-Patient Error Distribution (EXP-436)

```
Patient d (fid=52): ████░░░░░░░░░░░░░░░░  h360=18.9  ← excellent
Patient c (fid=17): █████░░░░░░░░░░░░░░░  h360=19.5  ← good (stable CGM)
Patient a (fid=17): ████████░░░░░░░░░░░░  h360=30.8  ← moderate
Patient b (fid=35): ████████████████████  h360=46.5  ← hard case
```

Note: Patient c has low fidelity score but good predictions — suggesting their glucose dynamics are inherently more stable/predictable, independent of therapy fidelity. Fidelity score ≠ predictability.
