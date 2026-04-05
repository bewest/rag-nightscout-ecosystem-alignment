# Structural Redesign Assessment: Incremental Progress vs Architectural Change

**Date**: 2026-04-05  
**Based on**: 335 experiments in research logs (EXP-001–327), 33 independently
verified (EXP-286–327 — see `accuracy-validation-2026-04-05.md`),
EXP-328–335 FDA phase code implemented, 20+ research reports  
**Question**: Does the CGM/AID intelligence program need structural redesign, or
should it continue incremental progress on the current architecture?

---

## 1. Executive Verdict

**The 3-pipeline architecture is sound. No structural redesign is needed.**

Three of five objectives are production-ready. The remaining two (hypo detection,
pattern retrieval) are bottlenecked by **data quantity** and **evaluation metrics**,
not architecture. The newly proposed FDA (Functional Data Analysis) encoding layer
is a well-scoped incremental addition — not a redesign — that targets the right
weaknesses.

However, the program faces a **credibility gap**: all classification results rest
on single training seeds with no held-out test sets. Before any further architecture
work, **validation rigor** must be established.

### Decision Matrix

| Objective | Verdict | Action |
|-----------|---------|--------|
| Glucose Forecasting | ✅ Lock — saturated at MAE=11.25 | Expand cohort, not architecture |
| UAM Detection | ✅ Lock — F1=0.939 production-ready | Multi-seed validation only |
| Override (WHEN) | ✅ Lock — F1=0.852 production-ready | Multi-seed validation only |
| Hypo Detection | ⚠️ Continue — data-limited at F1=0.676 | Augmentation, not architecture |
| ISF Drift | ⚠️ Continue — method proven, signal weak | Add physiological dimensions |
| Pattern Retrieval | 🔄 Explore — early, high uncertainty | Contrastive learning or FDA-FPCA |
| Override (WHICH/HOW) | 🆕 New work needed | Physics-based parameter search |

---

## 2. Saturation Evidence by Objective

### 2.1 Glucose Forecasting — SATURATED

```
Metric trajectory (MAE mg/dL):
  Gen-1 (synthetic):     8.5 (single-patient, leaked)
  Gen-2 (real, leaked):  17.3 → discovered 60% was data leakage
  Gen-3 (real, honest):  29.5 → architecture changes yield 0.0 improvement
  Gen-4 (regularized):   11.25 (ensemble) / 11.14 (ch_drop+FT)
  
  Model size sweep: 55K → 993K params → 0% improvement
  Architecture sweep: 8 architectures → all converge at 12.5 mg/dL single-model
```

**52 experiments** across 8 architectures. Every axis has been explored: model
capacity, feature count (8→21→39 features all overfit), loss function (MSE,
zone-weighted, clinical), training strategy (pre-train, fine-tune, ensemble).
The remaining lever is per-patient fine-tuning on more data.

**Structural redesign would not help.** The bottleneck is 11 patients × ~6 months
of data each. Doubling the cohort to N=50 is the only path to meaningful improvement.

### 2.2 UAM Detection — SATURATED (at high quality)

```
Metric trajectory (F1, positive-class):
  EXP-291: Embedding baseline      → 0.399
  EXP-313: Class-weighted embedding → 0.854  (+114%)
  EXP-313: 1D-CNN                   → 0.939  (+10%)
  EXP-313: CNN + embedding          → 0.891  (-5%, HURTS)
```

**Single breakthrough (EXP-313)** from embedding → CNN. The architecture is clear:
1D-CNN on 8 channels × 24 steps (2h). Adding anything (embeddings, ISF features,
longer windows) makes it worse. F1=0.939 with precision=0.944, recall=0.934 —
balanced and production-ready.

**No redesign needed.** Needs multi-seed replication (confidence interval likely
±0.015) and time-split validation.

### 2.3 Override Prediction (WHEN) — SATURATED (at high quality)

```
Metric trajectory (F1, macro):
  EXP-305: Embedding+state    → 0.392
  EXP-311: StateMLP            → 0.700  (+79%)
  EXP-311: 1D-CNN              → 0.726  (+3.7%)
  EXP-314: CNN 15min lead      → 0.821  (+13%)
  EXP-327: Attention 15min     → 0.852  (+3.8%)
```

Steady progression from embedding → MLP → CNN → shorter lead → attention. Each
step yielded diminishing returns: +79% → +3.7% → +13% (lead time change) → +3.8%.
The attention advantage (+2% over CNN) may not survive multi-seed replication.

**No redesign needed.** The next tier is predicting override TYPE and MAGNITUDE
(WHICH/HOW MUCH), which requires physics-model integration, not ML architecture
changes.

### 2.4 Hypo Detection — DATA-LIMITED, NOT ARCHITECTURE-LIMITED

```
Metric trajectory (F1, positive-class):
  EXP-311: Override low class   → 0.515
  EXP-315: Dedicated CNN        → 0.520  (+1%)
  EXP-317: Threshold optimized  → 0.630  (+21%)  ← threshold, not architecture
  EXP-321: Focal loss γ=2       → 0.662  (+5%)
  EXP-322: Multi-task            → 0.672  (+2%)
  EXP-324: + Platt calibration  → 0.676  (+1%)
  EXP-327: Attention             → 0.663  (-2%)  ← architecture change: no help
  EXP-327: Ensemble              → 0.667  (-1%)
```

**The plateau is stark**: last 4 experiments (4 different architectures) all land
at F1 = 0.663–0.676, a spread of 0.013. Meanwhile AUC = 0.958 — the model
*discriminates* well, but F1 is capped by the 6.4% class prevalence (~1,850
positive windows out of 29,000).

**Critical evidence**: Threshold optimization (+21%) delivered 7× the improvement
of focal loss (+3%). The bottleneck is calibration and data, not model capacity.

**Structural change needed**: Not architecture — **data augmentation**. Strategies:
- Synthetic hypo event generation (time-warp real events)
- GAN-based minority class generation
- Longer patient timelines (more rare events)
- Multi-site data pooling (more patients with hypo history)

### 2.5 ISF Drift — METHOD PROVEN, MISSING DIMENSIONS

```
Metric trajectory (significance at p<0.05):
  EXP-300: Episode segmentation    → 0/11 drift labels
  EXP-306: Cross-patient pooling   → ρ = -0.001 (null)
  EXP-307: Per-patient embedding   → 8/11 sig. (encoder collapse)
  EXP-308: Insulin-controlled      → 4/11 clean drift
  EXP-309: Per-cycle ISF ratio     → 0/11 sig. (too noisy)
  EXP-312: Rolling biweekly mean   → 9/11 sig. ← breakthrough
  EXP-325: CUSUM on daily ISF      → 85-100% false alarm rate
```

**The statistical method won.** Rolling biweekly aggregation of ISF_effective detects
drift in 9/11 patients where neural approaches failed (encoder collapse, noise).
But the detected drift has weak predictive value (correlation with TIR: r = -0.156,
explaining only 2.4% of outcome variance).

**Structural change needed**: Not in detection method — in the **feature space**.
Current approach tracks a single number (ISF_effective mean) when drift is likely
multi-dimensional: circadian ISF variation (dawn phenomenon), device age effects,
illness episodes, activity level changes. FDA's functional decomposition (FPCA on
ISF curves over time-of-day) could address this directly.

### 2.6 Pattern Retrieval — EARLY, HIGHEST UNCERTAINTY

```
Metric trajectory (Silhouette score):
  EXP-287: 2h embedding      → -0.349
  EXP-289: 12h embedding     → -0.339
  EXP-301: 7d embedding      → -0.301
  EXP-304: 7d aligned stride → +0.326  ← only positive silhouette ever
  EXP-304: cross-scale concat → -0.200  (devastating: ΔSil = -0.525)
```

**Only one approach has ever produced positive silhouette.** The 7-day Transformer
encoder with 24h alignment stride. All other timescales, all cross-scale combinations,
and all LOO evaluations produce negative silhouette.

Additionally, R@K is completely saturated at 1.000 — the retrieval metric cannot
discriminate between approaches, leaving silhouette as the only signal.

**This is the objective most likely to benefit from structural change.** Candidates:
- **Contrastive learning** (SimCLR/BYOL): learns discriminative embeddings without
  label dependency — could break the R@K saturation
- **FDA-FPCA embeddings** (EXP-332): mathematically-derived embeddings that don't
  require training — avoids GRU optimization pitfalls
- **Hierarchical labels**: replace single majority-vote labels with multi-level
  annotations (glucose state × insulin state × meal context)

---

## 3. The FDA Proposal: Enhancement, Not Redesign

The Functional Data Analysis proposal (EXP-328–341) introduces B-spline smoothing,
FPCA decomposition, glucodensity profiles, and functional derivatives as a
preprocessing layer. Key assessment:

### What FDA Is

- A **feature encoding layer** that sits between raw data and existing models
- **Drop-in compatible**: `raw grid → fda_encode() → CNN/Transformer` (unchanged)
- **7 of 14 experiments already coded** (fda_features.py: 552 lines, fda_experiments.py: 830 lines)
- **Gated progression**: Phase A validates features → Phase B tests per-objective → stop if no signal

### What FDA Is Not

- Not a new pipeline architecture (stays 3 pipelines)
- Not a new model family (CNN, Transformer, GRU stay the same)
- Not a claim of superiority ("complementary" per Klonoff et al. 2025)

### Where FDA Has Highest Expected Value

| Objective | FDA Feature | Why | Expected Impact |
|-----------|-----------|-----|----------------|
| **Pattern Retrieval** | FPCA scores | Unsupervised embeddings without GRU training | Sil: +0.33 → +0.50? |
| **ISF Drift** | FPCA on ISF curves | Captures circadian structure in drift | r: -0.16 → -0.25? |
| **ISF Drift** | Functional derivatives | Smoother dISF/dt than finite differences | Faster detection? |

### Where FDA Has Low Expected Value

| Objective | Why | Better Alternative |
|-----------|-----|-------------------|
| **Forecasting** | Architecture-saturated, data-limited | Expand cohort |
| **UAM Detection** | CNN already at F1=0.94 on raw data | Multi-seed validation |
| **Hypo Detection** | Data-limited (6.4% prevalence), not representation-limited | Data augmentation |
| **Override (WHEN)** | Attention at F1=0.85 on raw data | Multi-seed validation |

### Recommendation

**Proceed with FDA Phase A (EXP-328–331) as a bounded exploration.** The gating
criteria are well-defined: if ≥2/3 Phase A experiments show signal, proceed to
Phase B (objective-specific). If not, stop. Total investment: ~4-6 experiments,
results in days. The infrastructure (fda_features.py) is already built.

**Do NOT delay validation work (multi-seed, time-split) for FDA.** FDA is Phase 3
work; validation is Phase 1.

---

## 4. The Credibility Gap: Single-Seed Risk

**The most important finding from the accuracy validation is not a metric — it's a
methodology concern.**

All 20+ classification experiments (EXP-311 through EXP-327) use a single training
seed. Only forecasting (EXP-302) has multi-seed evaluation. This means:

- **UAM F1=0.939**: Could be 0.920–0.955 depending on initialization
- **Attention F1=0.852 vs CNN F1=0.835**: The 2% gap may not be statistically significant
- **Hypo F1=0.676**: Could be 0.660–0.690 (the "plateau" may be noise)
- **All architecture comparison conclusions could flip** with different seeds

Additionally, there is no held-out test set — the 80/20 split's validation set has
been implicitly used for architecture selection across 20+ experiments (selection
bias). EXP-326 (LOO) is the strongest evidence for generalization, but tests
patient-level, not temporal, transfer.

**This is not a fatal flaw, but it must be addressed before further architecture
work is meaningful.** A 3-seed replication of the top 3 experiments would take
hours to run and would either confirm the results (unlocking Phase 2) or reveal
that the margins are noise (redirecting effort to higher-impact work).

---

## 5. Exhausted Approaches (What NOT to Revisit)

These approaches have been definitively tested and failed. They should not be
re-attempted without fundamentally new data or theory:

| Approach | Evidence | Experiments |
|----------|----------|-------------|
| Feature engineering on CNN input | Hurts F1 by 2.6–3.5% | EXP-316, 320 |
| Cross-scale concatenation | Sil drops 0.525 | EXP-304, 305 |
| Combined CNN + embeddings | Worse than CNN alone | EXP-313, 311 |
| Focal loss + multi-task stacking | Not additive | EXP-323 |
| Per-patient fine-tuning for classification | -2.9% (full), +1% (selective) | EXP-318, 319 |
| CUSUM/EWMA on daily ISF data | 85-100% false alarm rate | EXP-325 |
| Per-cycle ISF measurement | 0/11 significant (variance too high) | EXP-309 |
| Cross-patient ISF pooling | Destroys temporal signal (ρ=-0.001) | EXP-306 |
| Embedding similarity for drift | Encoder collapse (sim≈1.0) | EXP-307 |
| Longer windows for UAM | F1 drops 83% (0.40→0.07) | EXP-299 |
| Model size scaling for forecasting | 0% gain from 55K→993K params | Multiple |
| Diffusion models (DDPM) | 63% worse than persistence | EXP-016, 020 |

---

## 6. Recommended Path Forward

### Phase 1: Validation Foundation (Immediate Priority)

**Goal**: Establish confidence in current results before investing in improvements.

| Action | Experiments | Investment | Expected Outcome |
|--------|-----------|------------|-----------------|
| Multi-seed replication | EXP-313 (UAM), EXP-327 (attention), EXP-322 (hypo) | 3-5 seeds each | Confidence intervals; confirm/deny architecture rankings |
| Time-split hold-out | All top models | Reserve last 20% of each patient timeline | True temporal generalization estimate |
| Standardize eval protocol | Documentation | Define split strategy, metrics, reporting format | Reproducible benchmarks |

**Gate**: If multi-seed confirms rankings → proceed to Phase 2. If attention vs CNN
gap vanishes → simplify to CNN-only (fewer deployment parameters).

### Phase 2: Targeted Improvements (High ROI)

**Goal**: Address the two weakest objectives without architectural change.

| Action | Objective | Baseline | Target | Method |
|--------|-----------|----------|--------|--------|
| Hypo data augmentation | Hypo Detection | F1=0.676 | F1>0.70 | Time-warp, jitter, synthetic minority |
| Contrastive retrieval | Pattern Retrieval | Sil=+0.326 | Sil>+0.50 | SimCLR/BYOL on 7d windows |
| Pre-smoothed CUSUM | ISF Drift | 14-day latency | <10 days | 7d rolling → CUSUM on smoothed series |

### Phase 3: Encoding Evolution (FDA + Clinical)

**Goal**: Test whether functional representations unlock the next tier.

| Action | Objective | FDA Experiment | Gate |
|--------|-----------|---------------|------|
| FDA bootstrap + FPCA | Infrastructure | EXP-328, 329 | Round-trip <0.5 mg/dL |
| FPCA retrieval | Pattern Retrieval | EXP-332 | Sil > +0.20 |
| FPCA drift | ISF Drift | EXP-334 | ≥9/11 sig., latency <14d |
| Circadian ISF | ISF Drift | EXP-339 | Dawn phenomenon in ≥6/11 |
| Per-patient calibration | Override, Hypo | New | Per-patient ECE <0.02 |
| Override WHICH/HOW | Override | New | Physics-based type prediction |

### Phase 4: Deployment Readiness

**Goal**: Move from research to production.

| Action | Scope | Prerequisite |
|--------|-------|-------------|
| ONNX model export | All production-ready objectives | Phase 1 validation |
| Online adaptation | Event detection, override | Phase 2 augmentation |
| Prospective validation | Clinical trial design | Phase 3 calibration |
| Cohort expansion (N>50) | All objectives | Phase 1-3 learnings |

---

## 7. Conclusion

### The Architecture Is Sound

The 3-pipeline system (fast 2h / weekly 7d / rolling 14d) is well-validated by
33 experiments. Each objective maps to exactly one pipeline. Cross-scale attempts
consistently fail. **No structural redesign needed.**

### The Bottlenecks Are Data and Evaluation, Not Architecture

| Bottleneck | Affects | Solution |
|------------|---------|----------|
| Single training seed | All classification results | Multi-seed replication |
| No held-out test set | Confidence in generalization | Time-split evaluation |
| 6.4% hypo prevalence | Hypo F1 ceiling | Data augmentation |
| N=11 patients | Forecasting, generalization | Cohort expansion |
| R@K metric saturation | Pattern retrieval evaluation | Contrastive learning + new metrics |
| Univariate ISF tracking | Drift explanatory power | Multivariate / circadian modeling |

### The FDA Proposal Is Well-Scoped

FDA is an encoding-layer enhancement, not a redesign. It's gated, bounded, and
targets the right weaknesses (pattern retrieval, ISF drift). Infrastructure is
already built. Proceed as Phase 3, after validation and targeted improvements.

### The Biggest Risk Is Premature Optimization

The program has produced impressive-looking numbers (F1=0.939, AUC=0.958,
MAE=11.25) from a well-executed but **statistically thin** methodology (single
seeds, no test set, N=11). The highest-ROI investment right now is not another
architecture experiment — it's **confirming what we already have**.

> **Recommendation**: Spend the next research cycle on validation (Phase 1),
> not innovation. If the results hold under multi-seed and time-split evaluation,
> the program has a deployable system. If they don't, we'll know exactly where
> the real ceiling is before committing to augmentation or FDA work.
