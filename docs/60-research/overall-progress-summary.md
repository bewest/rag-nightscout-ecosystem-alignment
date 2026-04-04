# cgmencode ML Pipeline — Overall Progress Summary

> **258 experiments · 18 phases · 10 patients · 134K parameters**
>
> Master summary tying together all research threads for the cgmencode ML pipeline.

---

## Executive Summary

The **cgmencode pipeline** — a 134K-parameter `CGMGroupedEncoder` transformer trained on 10 real Nightscout patients (~32K windows, ~600K CGM readings) — has been systematically evaluated across **258 experiments spanning 18 phases**.

The system addresses four high-level objectives from the ML Composition Architecture:

1. **Glucose Forecasting**: 10.59 mg/dL MAE (59% better than persistence)
2. **Event Detection**: 0.705 weighted F1 (XGBoost on tabular features)
3. **Pattern / Drift Recognition**: Circadian amplitude 71.3 mg/dL, drift r = −0.156
4. **Override Recommendations**: 0.993 F1 on TIR-impact metric

After a critical masking-correctness fix in Phase 4, the per-patient fine-tuning ensemble became the dominant strategy, reaching a practical performance floor for this architecture on this data.

---

## Scorecard

| Objective | Metric | Baseline | Current Best | Method | Δ | Status |
|-----------|--------|----------|-------------|--------|---|--------|
| Forecast MAE | mg/dL | 25.9 (persistence) | **10.59** | Per-patient L=4 FT ensemble | −59% | ✅ Production-ready |
| Forecast (verification) | mg/dL | — | **11.49** | Same, held-out data | — | ✅ Validated |
| Hypo Detection F1 | F1 | — | **0.700** | Production v7 conformal | New | ✅ Production-ready |
| Hypo MAE | mg/dL | 15.2 | **10.4** | 2-stage detection | −32% | ⚠️ Needs dedicated module |
| Event Detection | wF1 | 0.107 (neural) | **0.705** | Per-patient XGBoost | +559% | ✅ Production-ready |
| Event Lead Time | % >30 min | — | **73.8%** | Combined winners | New | ✅ Actionable |
| Override WHEN | F1 | 0.130 (broken metric) | **0.993** | TIR-impact scoring | +664% | ✅ Metric fixed |
| Override WHICH/HOW | — | — | Not started | — | — | ❌ Next priority |
| Drift Tracking | Pearson r | +0.70 (wrong sign) | **−0.328** | Wavelet 96 h | Fixed | ⚠️ Weak signal |
| Circadian Patterns | mg/dL | — | **71.3 ± 18.7** | Per-patient extraction | New | ✅ Ready |
| Clarke Zone A+B | % | 97.0% | **97.1%** | Already saturated | — | ✅ Excellent |
| Conformal 90% | coverage | — | **90.0%** | Per-horizon calibrated | New | ✅ Calibrated |
| LOO Generalization | mg/dL | — | **17.4 ± 2.5** | Leave-one-out (10) | New | ✅ Measured |
| vs Persistence | % improvement | 0% | **59%** | Best ensemble | +59 pp | ✅ Large margin |

---

## What Worked (Ranked by Impact)

| Rank | Approach | Impact | Key Experiment | Notes |
|------|----------|--------|----------------|-------|
| 1 | Per-patient fine-tuning | −8% to −15% MAE | EXP-241, 242, 250, 251 | **THE** breakthrough strategy |
| 2 | 5-seed ensemble averaging | −5% MAE | EXP-232, 242 | Consistent, low-effort |
| 3 | Selective future masking | +28% vs full masking | EXP-230 | Critical correctness fix |
| 4 | XGBoost for events | 5.1× over neural | EXP-155 | Right tool for the job |
| 5 | Physics-residual composition | 8.2× on synthetic | EXP-005 | Foundation of approach |
| 6 | TIR-impact override metric | 0.13 → 0.993 F1 | EXP-227 | Metric redesign, not model fix |
| 7 | Hypo 2-stage approach | −32% hypo MAE | EXP-136 | Classify risk, then forecast |
| 8 | Deeper architecture (L=4) | −4.7% MAE | EXP-247, 250 | Diminishing returns |
| 9 | Temporal event features | +11.2% event F1 | EXP-180 | Feature engineering > architecture |
| 10 | Autosens drift fix | +0.70 → −0.156 | EXP-154, 183 | Kalman → sliding median |

---

## What Failed (Ranked by Surprise)

| Rank | Approach | Result | Key Experiment | Lesson |
|------|----------|--------|----------------|--------|
| 1 | Curriculum learning | −146% worse | EXP-240, 177 | Calm → volatile doesn't transfer |
| 2 | Test-time augmentation | −35% worse | EXP-258 | Model too sensitive to perturbations |
| 3 | Neural event detection | 5.1× worse than XGBoost | EXP-155 | Transformers ignore treatment features |
| 4 | Temporal data augmentation | −2% worse + wider gap | EXP-256 | Perturbations teach wrong patterns |
| 5 | UVA/Padova pretraining | 0% gain | EXP-141 | Sufficient real data obsoletes synthetic |
| 6 | Wider model (d=128) | +0.11 worse | EXP-245 | Already at optimal width |
| 7 | Weight decay regularization | Zero effect | EXP-255 | Gap isn't overfitting |
| 8 | MC-Dropout ensemble | +0.8 worse | EXP-244 | Seed diversity > dropout diversity |
| 9 | Treatment-context drift | 0% gain | EXP-188 | Glucose-only sufficient for drift |
| 10 | Class rebalancing for events | Net negative | EXP-176 | Hurts majority class accuracy |

---

## Research Trajectory Analysis

### Phase 1 — Foundation (EXP-001 → 100)

Established the core architecture, data pipeline, causal masking strategy, and physics-residual approach. Validated on synthetic (UVA/Padova) and real (Nightscout) data.

**Best result**: 12.4 mg/dL MAE.

### Phase 2 — Specialization (EXP-100 → 150)

Explored ensemble diversity, hypo-specific models, and built the production inference pipeline. Introduced conformal prediction and clinical safety metrics.

**Best result**: 12.1 mg/dL MAE (ensemble), Hypo F1 = 0.700.

### Phase 3 — Multi-Objective (EXP-150 → 228)

Pushed event detection to its ceiling (0.705 wF1), fixed the override metric (0.993 F1), corrected drift-tracking sign error, and began per-patient exploration.

**Key insight**: Different objectives need different tools — XGBoost for events, metric redesign for overrides, feature engineering for drift.

### Phase 4 — Honest Masking + Per-Patient Revolution (EXP-229 → 258)

Discovered that **60% of prior improvement was from data leakage** through future-masking. Rebuilt all results with selective masking. Per-patient fine-tuning ensemble became the dominant approach.

**Best result**: 10.59 mg/dL MAE — a 59% improvement over persistence.

---

## Saturation Evidence

The improvement trajectory shows clear diminishing returns:

| Transition | Change | Improvement |
|-----------|--------|-------------|
| EXP-139 → EXP-232 | Rebuilt after masking fix | 12.1 → 12.46 (honest baseline) |
| EXP-232 → EXP-242 | Per-patient FT | 12.46 → 11.25 | −9.7% |
| EXP-242 → EXP-250 | Deeper L=4 | 11.25 → 10.71 | −4.8% |
| EXP-250 → EXP-251 | Extended training | 10.71 → 10.59 | −1.1% |
| EXP-251 → EXP-256/257/258 | Augmentation / dropout / TTA | All neutral or negative |

**Improvement rate**: 9.7% → 4.8% → 1.1% → 0%.

We are at the **practical floor** for this architecture on this data. Further gains require either new data dimensions or a new architecture (Gen-3).

---

## Infrastructure Scale

| Resource | Count |
|----------|-------|
| Experiment JSON files | 262 |
| Checkpoint files (.pth) | 699 |
| Total experiment data | 1.4 GB |
| `experiments_agentic.py` | ~1,900 lines, 19 registered experiments |
| Patient train/verification splits | 10 patients × 2 |

---

## Open Questions & Next Steps

1. **Override WHICH / HOW_MUCH** — The system knows *when* to override (0.993 F1) but not *what* override to recommend or *how strong* it should be. This is the highest-priority open problem.

2. **Patient j** — Needs special handling: 0% IOB data, only 138 verification windows, worst performance across all metrics. May require a dedicated cold-start strategy.

3. **Hypoglycemia** — Needs a dedicated detection module. The current 39.8 mg/dL MAE in the hypo range is clinically dangerous and unacceptable for safety-critical applications.

4. **Missing data dimensions** — Wearables (heart rate, activity), menstrual cycle labels, illness severity, and meal composition are all absent. Each could unlock a new tier of accuracy.

5. **Gen-3 architecture** — Being developed by a colleague; addresses semantic feature grouping and may break through the current saturation ceiling.

6. **Temporal non-stationarity** — The 7.4% verification gap likely reflects changing patient behavior over time, not overfitting. Adaptive or online-learning approaches are unexplored.

7. **Event detection for new patients** — The 0.71 F1 requires per-patient training. Cold-start event detection for previously unseen patients is untested.

---

## Data Sufficiency Assessment

| Data Source | Status | Sufficient For |
|------------|--------|---------------|
| 10 Nightscout patients (32K windows) | ✅ Adequate | Forecasting, events, drift |
| UVA/Padova synthetic (42 patients, 1,008 scenarios) | ✅ Available | Cold-start, pre-training (marginal value) |
| Verification splits (temporal holdout) | ✅ Robust | Honest evaluation |
| Menstrual cycle labels | ❌ Missing | Cannot train hormonal drift |
| Wearable data (HR, activity) | ❌ Missing | Cannot improve exercise detection |
| Meal composition / photos | ❌ Missing | Cannot improve meal detection |

---

## Companion Reports

For detailed analysis of individual objectives, see:

- [`objective-glucose-forecasting.md`](objective-glucose-forecasting.md) — Forecasting trajectory and verification
- [`objective-event-detection.md`](objective-event-detection.md) — Event detection and XGBoost vs neural
- [`objective-pattern-drift-override.md`](objective-pattern-drift-override.md) — Drift, circadian, and override assessment
- [`diabetes-insights-from-ml.md`](diabetes-insights-from-ml.md) — Clinical insights from ML experiments
- [`overnight-experiment-report-phase18.md`](overnight-experiment-report-phase18.md) — Phase 18 detailed experiment log

---

*Report generated from 258 experiments across 18 phases of the cgmencode ML pipeline.*
