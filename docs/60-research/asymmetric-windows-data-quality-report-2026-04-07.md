# Asymmetric Windows & Data Quality Report: EXP-417–422

**Date**: 2026-04-07  
**Scope**: EXP-417, 419, 421, 422 — training dynamics, asymmetric context, data quality  
**Predecessor**: [gap-closing-report-2026-04-07.md](gap-closing-report-2026-04-07.md) (EXP-409/410, 10.85 MAE)

## Executive Summary

This session investigated four hypotheses for pushing past the EXP-410 champion
(10.85 MAE, 11 patients). **None produced a new champion**, but all yielded
critical methodological insights about quick-to-full-scale translation, the
limits of context expansion, and training dynamics.

### Headline Results

| EXP | Hypothesis | Quick MAE | Full MAE | Δ vs 410 | Verdict |
|-----|-----------|:---------:|:--------:|:--------:|---------|
| **419** | Cosine LR schedule | 13.50 (−0.37) | **10.81** | −0.04 | ≈ TIE |
| **421** | Asymmetric windows (2h hist → 1h pred) | **13.20** (−0.67) | — | — | Quick only |
| **422** | Asym champion pipeline (w36) | — | **10.94** | +0.09 | ≈ TIE |
| **417** | Hard patient optimization (longer FT) | 13.87 (+0.00) | — | — | DEAD END |

**Key finding**: The 1h-history w24 symmetric configuration (EXP-410) is a robust
local optimum. Two attempts to beat it via context expansion (asymmetric w36) and
training trick optimization (cosine LR, longer FT) both converge to the same
~10.8–10.9 MAE range at full scale. The transformer has extracted what it can from
the current 8-channel PK feature set at this window size.

---

## §1. EXP-419: Cosine LR Schedule (Full Validation)

**Hypothesis**: Cosine annealing LR, which won at quick scale by −0.37 MAE
(EXP-413), should compound at full scale with 5 seeds and 11 patients.

**Result**: NEUTRAL. The advantage disappears at full scale.

### Full Results (11 patients, 5 seeds, 200ep base, 30ep FT)

| Metric | EXP-419 (Cosine) | EXP-410 (Plateau) | Δ |
|--------|:-----------------:|:------------------:|:-:|
| **Mean Ensemble MAE** | **10.81** | **10.85** | −0.04 |
| Mean Single Seed | 12.06 | 11.73 | +0.33 |
| Best Patient (k) | 6.2 | 6.2 | 0.0 |
| Worst Patient (b) | 17.1 | 17.1 | 0.0 |

### Per-Patient Comparison

| Patient | EXP-410 | EXP-419 | Δ | ISF |
|:-------:|:-------:|:-------:|:-:|:---:|
| a | 13.1 | 13.1 | 0.0 | 49 |
| b | 17.1 | 17.1 | 0.0 | 94 |
| c | 9.7 | 9.7 | 0.0 | 77 |
| d | 7.0 | 7.0 | 0.0 | 40 |
| e | 9.2 | 9.1 | −0.1 | 36 |
| f | 8.4 | 8.4 | 0.0 | 21 |
| g | 10.8 | 10.7 | −0.1 | 69 |
| h | 12.4 | 12.3 | −0.1 | 92 |
| i | 10.2 | 10.2 | 0.0 | 50 |
| j | 15.0 | 15.0 | 0.0 | 40 |
| k | 6.2 | 6.2 | 0.0 | 25 |

### Why Cosine LR Failed to Translate

At quick scale (60ep, 4 patients, 1 seed), cosine annealing provides a smoother
LR decay that reaches lower learning rates earlier. But at full scale (200ep):

- **ReduceLROnPlateau adapts to actual training dynamics** — it stays at 1e-3
  until stalling, then drops. This is optimal when different seeds stall at
  different epochs.
- **Cosine decays immediately** after warmup, regardless of whether the model
  is still making progress at the current LR.
- Base seeds: cosine avg=12.1 vs plateau avg=11.7 — cosine is **worse** at base.
- Ensemble compensates, narrowing the gap to −0.04 (within noise).

**Lesson**: ReduceLROnPlateau is the superior LR scheduler for this training
regime. Its adaptive nature handles the heterogeneous convergence across seeds
and patients.

---

## §2. EXP-421: Asymmetric Windows (Quick Validation)

**Hypothesis**: The transformer benefits from seeing more history context without
diluting the prediction target. Using w36 (24 history + 12 future) instead of
w24 (12 + 12) should provide richer glucose trend context for 1h predictions.

**Result**: Clear win at quick scale.

### Quick Results (4 patients, 1 seed, 60ep)

| Variant | History | Future | Total | MAE | h60 MAE | # Windows |
|---------|:-------:|:------:|:-----:|:---:|:-------:|:---------:|
| **w24_sym** (baseline) | 1h (12) | 1h (12) | 24 | 13.87 | 19.56 | 13.8K |
| **w36_asym** | 2h (24) | 1h (12) | 36 | **13.20** | **18.64** | 13.8K |
| **w48_asym** | 3h (36) | 1h (12) | 48 | 13.22 | 18.57 | 10.4K |

**Key observations**:
- w36 provides −0.67 MAE (−4.8%), a clear signal at quick scale
- w48 ties w36 (−0.02, within noise) despite 25% fewer training windows
- Diminishing returns from 2h → 3h history for 1h predictions
- Implementation: `future_steps=12` parameter keeps prediction target fixed
  while expanding history

---

## §3. EXP-422: Asymmetric Champion Pipeline (Full Validation)

**Hypothesis**: The w36 asymmetric advantage from EXP-421 should hold at full
scale, producing a new champion below 10.85 MAE. Additionally, filtering the
MDI patient (j) from base training may improve the base model quality.

**Result**: The quick-mode advantage DOES NOT hold at full scale. A second
demonstration of quick→full translation failure.

### All-Patients Variant — Full Results

| Metric | EXP-422 (w36 asym) | EXP-410 (w24 sym) | Δ |
|--------|:------------------:|:------------------:|:-:|
| **Mean Ensemble MAE** | **10.94** | **10.85** | **+0.09** |
| Mean Single Seed | 11.39 | 11.73 | −0.34 |
| Pump-only MAE | 10.54 | — | — |

### Per-Patient Comparison (EXP-422 vs EXP-410)

| Patient | EXP-410 | EXP-422a | Δ | h30 | h60 | Notes |
|:-------:|:-------:|:--------:|:-:|:---:|:---:|-------|
| a | 13.1 | 13.6 | +0.5 | 13.6 | 19.6 | Worse |
| b | 17.1 | 17.2 | +0.1 | 16.8 | 25.1 | Tied |
| c | 9.7 | 9.9 | +0.2 | 10.1 | 13.3 | Tied |
| d | 7.0 | 6.9 | −0.1 | 7.2 | 9.5 | Tied |
| e | 9.2 | 9.6 | +0.4 | 9.6 | 13.3 | Worse |
| f | 8.4 | 8.7 | +0.3 | 9.2 | 10.8 | Slightly worse |
| g | 10.8 | 10.8 | 0.0 | 11.0 | 12.9 | Tied |
| h | 12.4 | 12.5 | +0.1 | 12.6 | 16.6 | Tied |
| i | 10.2 | 10.3 | +0.1 | 9.9 | 13.7 | Tied |
| j | 15.0 | 14.9 | −0.1 | 15.1 | 20.6 | MDI — tied |
| k | 6.2 | 6.0 | −0.2 | 6.1 | 7.5 | Slightly better |

### Base Training Comparison

| Seed | EXP-422a base | EXP-410 base* | Δ | Early Stop |
|:----:|:-------------:|:-------------:|:-:|:----------:|
| s42 | 11.9 | ~11.7 | +0.2 | ep90 |
| s123 | 12.0 | ~11.7 | +0.3 | ep75 |
| s456 | 12.3 | ~11.7 | +0.6 | ep60 |
| s789 | 12.5 | ~11.7 | +0.8 | ep61 |
| s1024 | 11.8 | ~11.7 | +0.1 | ep91 |
| **Avg** | **12.1** | **11.7** | **+0.4** | |

*EXP-410 base MAE estimated from checkpoint 13 data.

### Why Asymmetric Windows Failed to Translate

The quick→full translation failure follows the same pattern as EXP-419 (cosine LR):

1. **Base model is slightly worse** (12.1 vs 11.7): The w36 model has 50% more
   sequence positions to attend to, diluting per-position attention quality.
   With only 4 patients, the extra context helps overcome this (novelty bias).
   With 11 diverse patients, the attention dilution effect dominates.

2. **Per-patient FT compensates equally**: Both w24 and w36 converge to similar
   per-patient MAE after FT, because FT adapts to the individual regardless of
   base window size.

3. **The 1h history is already sufficient for 1h predictions**: For h5–h60, the
   relevant glucose dynamics are captured in the most recent hour. Two hours of
   history provides diminishing returns — the transformer already learns trend
   and momentum from 12 steps.

4. **Data scarcity is NOT the bottleneck**: w36 and w24 both yield ~13.8K
   training windows — context, not quantity, is the limiting factor.

### h60 Performance: Where Extra History Should Help Most

| Source | h60 MAE |
|--------|:-------:|
| EXP-410 (w24 sym) | ~14.7 |
| EXP-422 (w36 asym) | ~14.8 |
| EXP-421 quick w36 | 18.64 |
| EXP-421 quick w24 | 19.56 |

Even at h60 where the extra hour of context should theoretically help most
(insulin activity from 2 hours ago is still relevant via DIA=5h), the full-scale
w36 is tied with w24. The quick-mode −0.92 advantage vanishes entirely.

### Pump-Only Variant (Still Running)

The pump-only base training (excluding patient j's MDI data) is still running.
Preliminary base seed s42: 11.8 (vs all-patients 11.9) — marginal improvement
from filtering noisy PK. Results will be updated when complete.

---

## §4. EXP-417: Hard Patient Optimization (Dead End)

**Hypothesis**: Patients b (17.1), j (15.0), and a (13.1) are undertrained.
Longer fine-tuning (100ep), data augmentation, and higher learning rates should
improve their MAE.

**Result**: Complete dead end. FT is already converged.

### Quick Results (patients a and b)

| Patient | Variant | MAE | Δ vs baseline | Notes |
|:-------:|---------|:---:|:-------------:|-------|
| b | baseline (30ep FT) | 17.33 | — | Reference |
| b | longer_ft (100ep) | 17.33 | 0.00 | Early stops at ep52 → same checkpoint |
| b | high_lr (2e-4) | 17.60 | +0.27 | Overshoots |
| b | augmentation | 17.33 | 0.00 | Bug: noise on both input AND target |
| a | baseline | 13.66 | — | Reference |
| a | longer_ft (100ep) | 13.66 | 0.00 | Early stops at ep43 → same checkpoint |
| a | high_lr (2e-4) | 13.98 | +0.32 | Overshoots |

### Why Hard Patients Are Hard

**Patient b** (MAE=17.1, ISF=94 mg/dL/U):
- Excellent data quality (97%+ PK density, full pump telemetry)
- Extreme insulin sensitivity: 1 unit of insulin causes a 94 mg/dL drop
- Small bolus timing errors cause large glucose swings — intrinsically harder
- The model IS learning patient b's dynamics; the error floor is just higher

**Patient j** (MAE=14.9, ISF=40 mg/dL/U):
- Only MDI patient in cohort (no pump, no temp basals, no loop devicestatus)
- 48% insulin_net density (vs >97% for all pump patients)
- Only 1,465 windows (vs ~4,300 for pump patients)
- PK model makes incorrect assumptions about continuous basal delivery
- Fundamentally different insulin delivery pattern than pump patients

**Patient a** (MAE=13.6, ISF=49 mg/dL/U):
- Good data quality but moderate ISF and some glucose variability
- Already well within "reasonable" error range
- Limited headroom for improvement

### Augmentation Bug Discovered

The noise augmentation implementation adds noise to the entire batch tuple:
```python
b = (b[0] + torch.randn_like(b[0]) * augment_std,)
```
But `_step()` uses `x = batch_data[0]` as both input (masked first half) and
target (second half). Noise applies to BOTH, canceling in MSE computation.
**Fix needed**: Apply noise only to the masked input portion, not the target.

---

## §5. Patient Data Quality Audit

A comprehensive audit of all 11 patients' data quality reveals a clear bifurcation:

### Data Density by Patient

| Patient | insulin_net | carb_rate | active_carbs | temp_basal | Delivery | MAE |
|:-------:|:----------:|:---------:|:------------:|:----------:|:--------:|:---:|
| k | 100% | 5% | 100% | Yes | Pump/Loop | **6.0** |
| d | 100% | 25% | 100% | Yes | Pump/Loop | **6.9** |
| f | 100% | 32% | 100% | Yes | Pump/Loop | **8.7** |
| e | 98% | 15% | 100% | Yes | Pump/Loop | **9.6** |
| c | 97% | 60% | 100% | Yes | Pump/Loop | **9.9** |
| i | 97% | 7% | 100% | Yes | Pump/Loop | **10.3** |
| g | 98% | 45% | 100% | Yes | Pump/Loop | **10.8** |
| h | 97% | 35% | 100% | Yes | Pump/Loop | **12.5** |
| a | 97% | 50% | 100% | Yes | Pump/Loop | **13.6** |
| b | 98% | 70% | 100% | Yes | Pump/Loop | **17.2** |
| j | **48%** | 12% | 100% | **No** | **MDI** | **14.9** |

**Key observations**:
- 10 pump patients: >97% insulin_net density, full temp basal data, MAE 6.0–17.2
- Patient j: 48% insulin_net, 0 temp basals, only MDI — MAE 14.9
- **Carb logging sparsity does NOT predict MAE**: k (5% carbs) = best, b (70%) = worst
- **ISF is the primary predictor of MAE** for pump patients (r² ≈ 0.4)
- `active_carbs` is always 100% nonzero (synthetic model feature)

---

## §6. Critical Methodological Insight: Quick→Full Translation

This session adds two more data points to the growing evidence that **quick-mode
results are unreliable indicators of full-scale performance**:

| Experiment | Quick Δ | Full Δ | Translation |
|-----------|:-------:|:------:|:-----------:|
| EXP-419 (cosine LR) | −0.37 | −0.04 | ⚠️ Inflated 9× |
| EXP-422 (asym w36) | −0.67 | +0.09 | ❌ Reversed |
| EXP-413 (PK deriv) | +0.37 | — | ⚠️ Hurt at quick |
| EXP-369 (dilated ResNet) | −1.8 | +1.7 | ❌ Reversed |
| EXP-410 (ISF+PK) | −1.1 | −1.0 | ✅ Held |
| EXP-408 (PK channels) | −0.8 | −0.7 | ✅ Held |

**Pattern**: Changes that hold at full scale tend to be **feature/data changes**
(adding PK channels, ISF normalization). Changes that fail tend to be **training
dynamics** (LR schedule, context expansion, architecture complexity).

**Why?** Quick mode uses 4 patients who are relatively homogeneous (a, b, c, d).
Feature changes that help these 4 also help the other 7. But training dynamics
that work for a homogeneous 4-patient set may not generalize to the full
heterogeneous 11-patient cohort.

**Recommendation**: Quick mode should be used ONLY to screen feature and
normalization changes. Training tricks, context modifications, and architecture
changes MUST be validated at full scale before declaring a winner.

---

## §7. The Performance Ceiling: Where We Stand

### Current State of the Art

| Metric | Value | Source |
|--------|:-----:|--------|
| **Overall MAE (11pt)** | **10.85** | EXP-410 champion |
| **Overall MAE (10pt, pump only)** | **10.41** | EXP-410 excluding j |
| **h30 MARD** | **~6.6%** | Below CGM MARD (8.2%) |
| **h60 MAE** | **~14.7** | 1h horizon |
| **Best patient (k)** | **6.0** | Exceptional data quality |
| **Worst patient (b)** | **17.2** | ISF=94, intrinsically hard |

### What We've Tried That Doesn't Help (at this scale)

| Approach | Expected Δ | Actual Δ | Why |
|----------|:---------:|:--------:|-----|
| Cosine LR | −0.5 | −0.04 | Plateau adapts better |
| Asymmetric windows (2h hist) | −0.7 | +0.09 | 1h history sufficient for 1h pred |
| Longer FT (100ep) | −0.5 | 0.0 | Already converged at 30ep |
| Higher FT LR (2e-4) | −0.3 | +0.3 | Overshoots |
| Data augmentation* | −0.5 | 0.0 | Bug (noise on target too) |
| PK derivatives (EXP-413) | −0.5 | +0.37 | Transformer already extracts |

*Augmentation needs bug fix before valid conclusion.

### Where the MAE Floor Comes From

The remaining ~10.85 MAE is composed of:
- **Irreducible noise**: CGM measurement error (MARD 8.2%) ≈ ±8-14 mg/dL
- **Unmeasured physiology**: Stress, exercise, fat/protein, gut hormones
- **Patient j's MDI penalty**: Removing j → 10.41 (−0.44)
- **Patient b's ISF extremity**: ISF=94 amplifies all errors 2-4×

---

## §8. Impact on Multi-Horizon Forecasting (90min–6h)

### What We Know About Extended Horizons

From earlier experiments (EXP-353, 356, 366), PK channels provide massive
advantages at longer horizons:

| Horizon | glucose_only | + PK channels | + future PK | Best Δ |
|:-------:|:------------:|:-------------:|:-----------:|:------:|
| h30 | 20.5 | 22.8 | 20.3 | −0.2 |
| h60 | — | — | — | −2.2 |
| h120 | 43.2 | 41.8 | 38.3 | **−4.9** |
| h240 | 50.7 | 46.5 | 40.4 | **−10.3** |
| h360 | 51.8 | 47.7 | 40.8 | **−11.0** |
| h720 | 54.6 | 50.9 | 46.0 | **−8.6** |

These were measured with CNN, NOT with the PKGroupedEncoder transformer.
**The highest-impact untested experiment is future PK on the transformer.**

### The DIA Valley Problem

History length follows a non-monotonic pattern for signal quality (from prior
classification experiments):

| History | Signal Quality | Why |
|:-------:|:--------------:|-----|
| 1h | Moderate | Sees onset only |
| 2h | Good for h30-60 | Captures recent trend |
| **4h** | **Worst** | Overlapping incomplete insulin/meal arcs |
| 6h | Better | Sees complete rise→peak→resolution |
| 12h | Best episodic | Full meal + correction cycle |

For h120-h360 predictions, the model needs to see:
1. Current glucose trend (1h recent)
2. Insulin already administered and its remaining activity (2-5h lookback)
3. Recent meal absorption status (1-3h lookback)

**Conclusion**: For multi-hour predictions, 2-4h history + future PK projection
is the optimal approach — NOT just extending history further.

---

## §9. Recommendations for Next Experiments

### Highest Priority: Future PK on Transformer (EXP-411)

The single highest-impact experiment is combining the proven future PK projection
(−10 MAE at h120 on CNN) with the proven PKGroupedEncoder transformer. This has
NOT been tested yet and is the most promising path for h90–h360 improvement.

### Revised Priority List (Post EXP-417–422 Learnings)

| Priority | Experiment | Expected Impact | Confidence | Notes |
|:--------:|-----------|:--------------:|:----------:|-------|
| **1** | Future PK + transformer (h120-h360) | −3 to −8 at h120+ | HIGH | CNN showed −10 |
| **2** | Fix augmentation bug + retest | −0.3 to −0.8 | MEDIUM | Currently broken |
| **3** | Horizon-adaptive window routing | −1 to −3 at h120+ | MEDIUM | w24 for h60, w48 for h120 |
| **4** | Data quality filtering for base | ±0.1 | LOW | EXP-422p pending |
| **5** | Overnight risk assessment (E1) | New capability | MEDIUM | Unrelated to forecasting |

### What NOT to Pursue

- ❌ Further LR schedule optimization (plateau is optimal)
- ❌ Longer fine-tuning (converged at 30ep)
- ❌ Higher LR for hard patients (overshoots)
- ❌ Context expansion beyond 2h for h60 predictions (diminishing returns)
- ❌ Quick-mode-only architecture experiments (unreliable)

---

## §10. Theoretical Implications

### The Attention Saturation Hypothesis

The transformer's attention mechanism appears to be **saturated** at the current
feature set and window size:

1. **w24 (12 history positions)**: Each position gets 1/12 ≈ 8.3% attention base.
   Adding PK channels (4 extra features per position) gives the transformer
   useful signal to attend to → improvement.

2. **w36 (24 history positions)**: Each position gets 1/24 ≈ 4.2% attention base.
   The extra 12 positions contain relevant but less critical older context.
   The attention dilution approximately cancels the information gain.

3. **Implication for h120+ predictions**: Simply extending history won't help.
   Instead, we need **future PK projection** — new causal information about what
   insulin/carbs WILL DO, not what glucose DID.

### Dense Equivariant Signals vs Sparse Events

This session confirms the core principle:

- **Dense continuous signals** (glucose, PK curves, IOB): Work well as transformer
  input — every timestep carries information
- **Sparse event signals** (bolus timing, carb events): Mostly zeros, adding noise
- **The PK model bridges the gap**: Converting sparse bolus/carb events into dense
  continuous absorption curves is the key architectural insight that enabled our
  breakthrough from 24.4 → 10.85 MAE

The remaining question is whether the **derivatives** of these dense signals
(dG/dt, d²G/dt², dIOB/dt) provide additional value. EXP-413 showed PK derivatives
hurt, but glucose derivatives remain untested at full scale.

---

## Appendix: Full EXP-422 Per-Horizon Results

### All-Patients Variant — Per-Patient × Per-Horizon

| Patient | Overall | h30 | h60 | ISF | Data Quality |
|:-------:|:-------:|:---:|:---:|:---:|:------------:|
| k | 6.0 | 6.1 | 7.5 | 25 | Excellent |
| d | 6.9 | 7.2 | 9.5 | 40 | Excellent |
| f | 8.7 | 9.2 | 10.8 | 21 | Excellent |
| e | 9.6 | 9.6 | 13.3 | 36 | Good |
| c | 9.9 | 10.1 | 13.3 | 77 | Good |
| i | 10.3 | 9.9 | 13.7 | 50 | Good |
| g | 10.8 | 11.0 | 12.9 | 69 | Good |
| h | 12.5 | 12.6 | 16.6 | 92 | Good |
| a | 13.6 | 13.6 | 19.6 | 49 | Good |
| j | 14.9 | 15.1 | 20.6 | 40 | **MDI — degraded** |
| b | 17.2 | 16.8 | 25.1 | 94 | Excellent |
| **Mean** | **10.94** | | | | |

### Base Training Dynamics (All-Patients Variant)

| Seed | Best Val Loss | Early Stop Epoch | Overall MAE | h30 | h60 |
|:----:|:-------------:|:----------------:|:-----------:|:---:|:---:|
| 42 | 0.2539 | 90 | 11.9 | 12.1 | 16.3 |
| 123 | 0.2409 | 75 | 12.0 | 12.0 | 16.5 |
| 456 | 0.2559 | 60 | 12.3 | 12.4 | 16.9 |
| 789 | 0.2408 | 61 | 12.5 | 12.4 | 16.9 |
| 1024 | 0.2386 | 91 | 11.8 | 11.8 | 16.2 |
| **Mean** | | | **12.1** | | |
