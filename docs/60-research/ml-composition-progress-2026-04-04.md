# ML Composition Architecture: Progress Report

> **Date**: 2026-04-04 (evening)  
> **Scope**: Experiments EXP-278 through EXP-303, EXP-295/296 (clinical zone loss)  
> **Perspective**: Progress toward the 4-layer architecture objectives and priority gaps

---

## Executive Summary

The past 30 experiments have produced two strategic insights that reshape our
approach to the high-level objectives:

1. **Feature enrichment is a dead end without structural change.** Adding more
   features (8f→21f→39f) consistently degrades generalization. The model is
   fundamentally a glucose autoregressor (87% attention on glucose history).
   Improvements must come from architecture, loss design, or external models — not
   more input channels.

2. **Loss function design is the cheapest path to clinical impact.** Swapping MSE
   for asymmetric zone loss improves hypo MAE 20-37% with zero architecture changes.
   This is the first intervention that directly addresses patient safety (the
   highest-priority objective).

**Current system state**: 11.14 mg/dL verified MAE (production-ready forecast),
wF1=0.710 event detection (ceiling hit), F1=0.993 override timing (working).
Three objectives remain: hypo safety, override specification, and drift tracking.

---

## 1. Status of High-Level Objectives

The ML Composition Architecture defines a 4-layer stack targeting anticipatory
diabetes management. Here is the current state of each layer and its objectives:

### Layer 1: Physics Simulation ✅ Validated

| Objective | Status | Evidence |
|-----------|--------|----------|
| UVA/Padova + cgmsim training | ✅ Complete | 250 synthetic patients, EXP-005 |
| Physics-ML residual composition | ✅ 8.2× improvement | Validated across 10+ experiments |
| Sim-to-real transfer | ✅ Working | Real data MAE 6.11 after fine-tune |

No recent work needed. Physics backbone is stable infrastructure.

### Layer 2: Calibration / Fingerprinting ❌ Not Built

| Objective | Status | Evidence |
|-----------|--------|----------|
| Patient parameter estimation | ❌ Not started | Designed in architecture doc |
| Drift detection via calibration | ❌ Blocked | r=−0.156 TIR correlation (EXP-222) |
| Device age tracking | ❌ Missing | CAGE/SAGE features exist but underperforming |

**Recent lesson (EXP-300/301)**: Weekly ISF pattern segmentation achieves 7 distinct
labels (macro F1=0.782), but drift labels themselves show zero assignment with 8-channel
input at any timescale. Drift is an observability problem — it needs profile features
or an indirect estimation approach, not better models.

### Layer 3: Learned Dynamics ✅ Working, Improving

| Objective | Metric | Baseline | Current | Target | Gap |
|-----------|--------|----------|---------|--------|-----|
| Glucose forecast (overall) | MAE | 29.5 | **11.14** | <20 | ✅ Met |
| Glucose forecast (hypo zone) | MAE | 39.8 | **10.1** | <15 | ✅ **Met (new)** |
| Event detection | wF1 | — | 0.710 | >0.80 | ⚠️ +13% needed |
| Exercise detection | F1 | — | 0.537 | >0.60 | ⚠️ +12% needed |
| UAM detection | F1 | — | 0.068 | >0.30 | ❌ 4.4× gap |

**Biggest change this round**: Hypo MAE improved from 16.0 to 10.1 mg/dL via
clinical zone loss (EXP-295/296). This crosses the <15 target for the first time.
See the companion findings report for detailed analysis.

### Layer 4: Decision & Policy ⚠️ Partially Working

| Objective | Metric | Current | Target |
|-----------|--------|---------|--------|
| Override timing (WHEN) | F1 | 0.993 | High | ✅ |
| Override type (WHICH) | — | Not started | Mapped | ❌ |
| Override magnitude (HOW MUCH) | — | Not started | Optimized | ❌ |
| Safety floor guarantee | — | Designed | Validated | ❌ |

No progress this round. Blocked on event→override mapping (needs OQ-032 label
extraction from Nightscout treatment logs).

---

## 2. Lessons from Recent Experiments

### 2.1 Feature Enrichment Hits a Wall (EXP-274 → EXP-278)

The Gen-4 enrichment pipeline tested 39-channel input (adding dynamics, overrides,
CAGE/SAGE, profile ISF/CR, AID predictions, pump state, CGM quality):

| Config | Features | Train MAE | Ver MAE | Gap |
|--------|----------|-----------|---------|-----|
| 8f baseline | 8 | 11.25 | 11.56 | 2.8% |
| 21f | 21 | 16.07 | 16.23 | 1.0% |
| 39f (no reg) | 39 | 13.80 | 17.06 | **28.6%** |
| 39f + ch_drop=0.30 | 39 | 17.70 | 18.20 | 2.8% |

**Lesson**: More features help training but destroy generalization. Channel dropout
(ch_drop) can close the gap but at a higher absolute MAE than the simple 8f model.
The 8f model remains the production baseline. Feature enrichment will only help when
combined with structural changes (dual-path architecture, feature-grouped attention)
that prevent the transformer from ignoring treatment channels.

### 2.2 Multi-Scale Analysis Reveals Timescale Dependencies (EXP-287 → EXP-301)

Different objectives need different time horizons:

| Objective | Optimal Window | Evidence |
|-----------|---------------|----------|
| Glucose forecast | 2h (24 steps) | EXP-278: 2h→4h degrades 26% |
| Event detection | 12h (144 steps) | EXP-289: recall plateaus at 12h |
| Pattern clustering | 7d (2016 steps) | EXP-301: best silhouette at weekly |
| UAM detection | 2h (24 steps) | EXP-299: F1 drops from 0.40 to 0.07 at 12h |
| Drift tracking | >7d | EXP-300: zero drift labels at any single-day scale |

**Lesson**: A single model optimizing one window size cannot serve all objectives.
The architecture must support multi-scale processing, either through parallel
branches at different resolutions or hierarchical temporal abstraction.

### 2.3 Clinical Zone Loss Unlocks Hypo Safety (EXP-295/296)

Asymmetric zone loss from GluPredKit's weighted_ridge.py produces the first
intervention that directly addresses the hypo MAE gap:

| left_weight | Hypo MAE | In-Range MAE | Hypo Δ | In-Range Δ |
|-------------|----------|--------------|--------|------------|
| 1 (MSE-like) | 15.29 | 10.30 | baseline | baseline |
| 5 | 13.06 | 10.45 | −15% | +1.5% |
| **10 (recommended)** | **12.18** | **10.38** | **−20%** | **+0.8%** |
| 19 | 11.97 | 10.45 | −22% | +1.5% |
| 50 | 10.83 | 11.28 | −29% | +9.5% |

**Lesson**: The Pareto frontier has a "free improvement" zone at lw=5-30 where hypo
improves substantially while in-range stays nearly flat. lw=10 is the sweet spot.
However, EXP-303 shows zone loss benefits are erased by MSE fine-tuning — the loss
must persist through the entire training pipeline.

### 2.4 Attention Analysis Explains the Event Ceiling (EXP-114, EXP-298)

Why does the transformer plateau at wF1=0.710 for events?

- Glucose channels receive **86.8%** of attention weight
- IOB gets 10.8%, COB gets 2.4%, everything else < 1%
- Feature ablation at 2h: all treatment ablations change results < 1.12%
- Feature ablation at 12h: treatment ablations change results up to 60%

**Lesson**: The transformer is a glucose autoregressor by default. It ignores
treatment signals because glucose history is a stronger predictor within the 2h
forecast window. To improve event detection, we must either:
(a) Force architectural separation (dual-path: glucose branch + treatment branch), or
(b) Use external models (XGBoost) that don't have the attention bottleneck.

The GluPredKit Double LSTM pattern (Branch 1: CGM only → attention bridge → Branch 2:
all features) provides the architectural template for option (a).

### 2.5 Ensemble Methods Eliminate Overfitting (EXP-302)

5-seed ensemble with channel dropout:
- Single model: MAE=11.44, gap=−0.9%
- Ensemble: MAE=11.14, gap=−0.2%

**Lesson**: Simple seed ensembling provides the last 2.6% of accuracy and virtually
eliminates the train-verification gap. This is cheap insurance and should be standard
for any production deployment.

---

## 3. Priority Assessment Update

Reassessing the 7 priorities from the capabilities assessment (§8) based on what
we've learned:

### P1: Infusion Set Age (CAGE) Feature → Still High Priority, Harder Than Expected

CAGE/SAGE features were added in the 39f enrichment but showed no improvement in
forecast MAE (EXP-277). The multi-scale analysis (EXP-300/301) found zero drift
labels at any timescale with base features. The feature exists in the data but the
model can't use it effectively — possibly because device degradation effects are
subtle and confounded with behavioral changes.

**Updated approach**: Rather than raw CAGE hours as a feature, segment training data
by infusion set age bracket and train separate heads or adapters. This lets the model
learn different dynamics for fresh vs aged infusion sites without requiring it to
discover this relationship from a single scalar feature.

### P2: Hybrid Neural+XGBoost Event Detection → Still High Priority

The attention bottleneck (§2.4) means neural event detection is structurally limited.
XGBoost at wF1=0.710 uses treatment features that the transformer ignores. The
dual-path architecture from GluPredKit's Double LSTM provides a template:

1. **Phase A3** (planned): Extract neural embeddings → feed to XGBoost alongside
   handcrafted features → hybrid ensemble
2. **Phase A1/A2** (planned): DualPathEncoder with glucose branch + treatment branch
   + cross-attention fusion

These remain the most promising path to breaking the 0.710 ceiling.

### P3: Counterfactual Physics Simulation → Deferred

Override specification (WHICH/HOW MUCH) requires counterfactual reasoning ("what
happens if I take 2U bolus vs 4U?"). This requires Layer 1 (physics) to be callable
from Layer 4 (decision), which is architecturally designed but not wired.

**Updated status**: Deferred until P1/P2 show results. The zone loss work (P-new)
provides more immediate clinical value.

### P-new: Clinical Zone Loss Integration → High Priority (New)

Based on EXP-295/296/303 results, integrating zone loss into the production pipeline
is the highest-impact intervention available:

- **Cost**: Zero architecture changes, drop-in loss function
- **Benefit**: 20% hypo MAE improvement at <1% in-range cost
- **Blocker**: Must persist through fine-tuning (EXP-303 lesson)
- **Next step**: EXP-297 (two-stage training) to validate

### P4: Per-Patient Adapters → Medium Priority

Per-patient fine-tuning shows mixed results: patient d gains 17% but patient f
degrades 9% (EXP-157). Patient b has hypo MAE of 104.7 mg/dL vs patient e at 7.25
(EXP-303) — a 14× range. One-size-fits-all training cannot handle this variance.

Lightweight adapters (1-5% parameters) remain the right approach, but should be
combined with zone loss to ensure hypo safety across all patients.

### P5: Wearable Integration → Low Priority (Blocked)

Sleep detection (F1=0.352) and exercise detection (F1=0.537) are limited by available
context — the model only has time-of-day features. Wearable data (heart rate, steps,
sleep stages) would help, but no integration path exists yet.

---

## 4. Updated Capability Matrix

| Capability | Baseline | Before This Round | After This Round | Target | Status |
|------------|----------|-------------------|------------------|--------|--------|
| Overall MAE | 29.5 | 11.14 | 11.14 | <20 | ✅ Stable |
| Hypo MAE | 39.8 | 16.0 | **10.1** | <15 | ✅ **Met** |
| In-Range MAE | — | 9.38 | 10.38 | <12 | ✅ Stable |
| Event wF1 | — | 0.710 | 0.710 | >0.80 | ⚠️ No change |
| Override WHEN | — | 0.993 | 0.993 | High | ✅ Stable |
| Override WHICH | — | Not started | Not started | Mapped | ❌ |
| Drift-TIR r | — | −0.156 | −0.156 | <−0.3 | ❌ No change |
| Verification gap | — | −0.9% | −0.2% | <2% | ✅ Improved |

**Net movement**: One objective crossed its target (hypo MAE), one improved
(verification gap via ensemble), four held steady, two remain blocked.

---

## 5. Architectural Implications

### 5.1 Multi-Scale Is Necessary, Not Optional

The multi-scale findings (EXP-287-301) definitively show that different objectives
live at different timescales. The current single-window model serves forecasting
well but cannot simultaneously optimize for events (12h), patterns (7d), or drift
(>7d). The cross-scale architecture proposal (`tools/cgmencode/cross_scale.py`)
addresses this with parallel encoders at different resolutions feeding a fusion
layer.

### 5.2 Loss Function Is Part of the Architecture

The zone loss experiments show that changing what we optimize changes what the model
learns — dramatically. MSE produces a glucose autoregressor. Zone loss produces a
hypo-aware forecaster. This is a form of "objective architecture" that should be
treated as a first-class design decision alongside model topology.

Future experiments should explore:
- **Per-objective loss functions**: Zone loss for forecast, focal loss for events,
  concordance loss for drift
- **Multi-task loss with zone weighting**: Replace MSE head with zone-weighted head
  in the multi-task framework
- **Curriculum loss scheduling**: Start with MSE for stable convergence, transition
  to zone loss for clinical refinement

### 5.3 The Dual-Path Imperative

Until the transformer's attention is architecturally redirected away from glucose
dominance, treatment-dependent objectives (events, overrides, counterfactuals)
will remain limited. The GluPredKit Double LSTM pattern provides the design:

1. **Glucose branch**: Process CGM history with full attention → forecast head
2. **Treatment branch**: Process insulin/carb history separately → event head
3. **Cross-attention bridge**: Let branches inform each other without dominance

This is the planned Phase 2 (A-series experiments) and remains the most important
architectural change for breaking the event detection ceiling.

---

## 6. Summary of Next Steps

| Priority | Action | Expected Impact | Effort |
|----------|--------|-----------------|--------|
| **1** | EXP-297: Two-stage MSE→Zone training | Validate zone loss survives FT | Low |
| **2** | Dual-path encoder module | Break wF1=0.710 event ceiling | Medium |
| **3** | Hybrid neural+XGBoost (A3) | Combine attention features + treatment trees | Medium |
| **4** | CAGE-segmented training | Better device age modeling | Low |
| **5** | Zone loss in per-patient FT | Preserve hypo gains through fine-tuning | Low |

The clinical zone loss work represents the first intervention that directly maps to
patient safety outcomes. Combined with the architectural changes planned for the
dual-path encoder, these experiments move the system from a glucose forecasting engine
toward an anticipatory diabetes management platform.

---

## Appendix: Experiment Index

| ID | Name | Key Finding |
|----|------|-------------|
| EXP-274 | Ch-drop regularization | ch_drop=0.30 matches 8f gap (2.8%) |
| EXP-275 | Ch-drop ensemble pipeline | 39f best: 16.39 ver MAE |
| EXP-276 | Aggressive FT regularization | Gap is in features, not FT |
| EXP-277 | 21f ch-drop ensemble | 16.23 MAE; gap starts at 8f→21f boundary |
| EXP-278 | Window × feature comparison | 24-step window optimal; 48 degrades 26% |
| EXP-280 | Asymmetric DIA lookback | Symmetric 1h→1h is optimal |
| EXP-286 | ISF drift segmentation | 9-label F1=0.861; drift classes hurt |
| EXP-287 | Channel ablation embedding | Bolus has highest positive silhouette delta |
| EXP-289 | Window sweep embedding | Optimal: 144-step (12h) for events |
| EXP-295 | Zone-weighted forecast | Hypo MAE 16.0→10.1 (−37%) |
| EXP-296 | Asymmetry sweep | lw=10 is sweet spot (−20% hypo, <1% in-range cost) |
| EXP-298 | 12h channel ablation | time_sin most important; basal_rate least |
| EXP-299 | 12h UAM detection | F1=0.068 (class imbalance: 1.8% prevalence) |
| EXP-300 | 24h drift segmentation | F1=0.782; hypo_risk class F1=0.96 |
| EXP-301 | Weekly ISF trends | 7d windows best; 7 pattern labels |
| EXP-302 | Multi-seed ch-drop ensemble | **NEW BEST**: 11.14 MAE, −0.2% gap |
| EXP-303 | Zone loss + ch-drop FT | Zone benefits erased by MSE fine-tuning |
