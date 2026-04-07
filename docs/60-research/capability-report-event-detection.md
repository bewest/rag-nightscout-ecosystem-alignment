# Capability Report: Event Detection & Classification

**Date**: 2026-04-07 | **Overnight batch**: EXP-685, EXP-688, EXP-748 | **Patients**: 11

---

## Capability Definition

Classify treatment events and glycemic risk states — meals, corrections, hypo/hyper risk, pattern phenotypes — from CGM traces and treatment logs, with actionable lead time for proactive intervention.

---

## Current State of the Art

| Task | Best Metric | Method | Status |
|------|-------------|--------|--------|
| 2h HIGH prediction | AUC **0.907** | XGBoost combined_43 | ✅ Deployable |
| 2h HYPO prediction | AUC **0.860** | XGBoost combined_43 | ✅ Deployable |
| HIGH recurrence 3d | AUC **0.919** | XGBoost | ✅ Deployable |
| HIGH recurrence 24h | AUC **0.882** | XGBoost | ✅ Deployable |
| Overnight HIGH risk | AUC **0.805** | CNN, 6h evening context | ✅ Deployable |
| Event detection (weighted) | wF1 **0.710** | Per-patient XGBoost | ✅ Production |
| Meal detection | F1 0.547–0.822 | XGBoost tabular features | ⚠️ Hardest event |
| Correction bolus | F1 **0.768** | XGBoost | ✅ Reliable |
| Mean lead time | **36.9 min** (73.8% >30 min) | XGBoost | ✅ |

**Champion**: Regularized XGBoost (n_est=300, depth=6, lr=0.03) on combined_43 features (22 baseline tabular + 12 throughput + 9 multi-day). Three independent architectures (XGBoost, CNN, Transformer) converge at wF1 ≈ 0.710 — a feature ceiling, not a model ceiling.

### Why XGBoost Dominates Neural (6.6×)

Transformer attention analysis (EXP-114) revealed the neural model allocates **86.8% of attention to glucose history** and only 13.2% to treatment features — it becomes a glucose autoregressor. XGBoost succeeds because its top features are treatment-derived: `carbs_total` (0.124), `bolus_total` (0.085), `cob_now` (0.071), `net_basal_now` (0.070). Neural event head: F1 = 0.107. XGBoost: F1 = 0.705.

---

## Overnight Contribution

The overnight batch did not retrain event classifiers. Instead, it deployed them into an integrated clinical pipeline and quantified the detection ceiling.

### AID-aware clinical rules (EXP-685)

Event detection feeds a rule engine distinguishing **AID compensation** from **genuine physiological problems** using supply-demand flux decomposition:

| Recommendation | Count (of 11) |
|---------------|---------------|
| Decrease basal rate | 9 |
| Increase CR ratio | 5 |
| Adjust CR/ISF settings | 4 |
| Maintain current settings | 3 |

A patient with high TAR + negative net flux looks under-insulinized but is actually over-compensated — the AID is masking bad settings.

### Multi-patient dashboard (EXP-688)

Composite risk grading: Grade A (3 patients), B (4), C (4), D (0). Mean risk: 48.0/100, mean TIR: 70.9%.

### Unannounced meal quantification (EXP-748)

**46.5% of glucose rise events** (2,302 of 4,809) had no carb entry. This is the irreducible blind spot: reactive detection (glucose already rising) achieves F1 = 0.939, but predictive detection (before glucose moves) is limited to F1 = 0.565 without meal announcement. This validates oref0/AAPS's UAM design: accept late detection, compensate with aggressive dosing.

---

## What Was Tried and Ruled Out

| Approach | Result | Verdict |
|----------|--------|---------|
| EMA strategic features | +0.011 AUC for HYPO at 12h | ⚠️ Small gain |
| PK channel features | +0.014 AUC for HIGH | ⚠️ Task-specific |
| Focal loss for hypo | +0.002 AUC | ❌ Marginal |
| Neural event head | 6.6× worse than XGBoost | ❌ Wrong architecture |
| Class rebalancing | Net negative | ❌ Hurts majority class |
| PK channels overnight HYPO | −0.013 AUC | ❌ Harmful |

---

## Validation Vignette

**True Positive — Post-meal spike** (Patient e): Glucose 324 mg/dL, rising, 24h TIR = 47.9%, IOB = 0.751. P(HIGH 2h) = 0.999. Actual: 100% above 180 for 2 hours.

**True Negative — Stable morning** (Patient k): Glucose 94 mg/dL, flat, TIR = 100%, zero IOB/COB. P(HIGH 2h) = 0.001. Stayed 91–103. Zero alarm fatigue.

**False Negative — Unannounced meal** (Patient f): Glucose 90 mg/dL, mild trend, zero IOB/COB. P(HIGH 2h) = 0.055. Rocketed to 277. The blind spot — no carb entry means no prediction.

---

## Key Insight

Event detection splits into two regimes: **reactive** (glucose already moving, F1 = 0.939) and **predictive** (before glucose moves, F1 = 0.565). The overnight batch advanced the downstream use of detection — feeding it into AID-aware rules that decompose controller compensation from patient needs — rather than improving the detection itself. The wF1 = 0.710 ceiling is real and structural.
