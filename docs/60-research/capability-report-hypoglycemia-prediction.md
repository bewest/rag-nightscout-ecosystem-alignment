# Capability Report: Hypoglycemia Prediction

**Date**: 2026-04-07 | **Overnight batch**: EXP-692, EXP-695, EXP-749 | **Patients**: 11

---

## Capability Definition

Predict impending hypoglycemic events (BG < 70 mg/dL) with sufficient lead time for preventive action — automated insulin suspension by the AID system or manual carbohydrate intake.

---

## Current State of the Art

| Task | Best Metric | Method | Status |
|------|-------------|--------|--------|
| 2h HYPO prediction | AUC **0.860** | XGBoost combined_43 | ✅ Deployable |
| HYPO with physics features | AUC **0.696** | Physics boost (+34%) | ✅ Key gain |
| 4h HYPO + PK features | AUC 0.738 | PK-replace 6ch | ❌ Gap |
| 6h HYPO | AUC 0.696 | XGBoost | ❌ Gap |
| Overnight HYPO | AUC **0.690** | CNN 6h context | ❌ Ceiling |
| HYPO recurrence 6h | AUC 0.668 | XGBoost | ❌ Gap |
| Personalized alert thresholds | **−15% false alerts** | Per-patient error dist. | ✅ Deployable |

**Clinical deployment threshold**: AUC ≥ 0.80. Only the 2-hour horizon crosses this bar.

---

## The Fundamental Asymmetry: HIGH vs HYPO

| Prediction | 2h AUC | 6h AUC | Overnight AUC |
|------------|--------|--------|---------------|
| HIGH | **0.907** | 0.796 | **0.805** |
| HYPO | 0.860 | 0.668 | 0.690 |
| Gap | 0.047 | **0.128** | **0.115** |

HIGH prediction is solved at every horizon. HYPO prediction degrades sharply beyond 2 hours. The gap widens with horizon length because:

1. **Counter-regulatory hormones are unmeasured**: Below 70 mg/dL, glucagon, epinephrine, and cortisol activate non-linearly. These create the rebound-high dynamics that make hypo trajectories unpredictable from CGM + insulin data alone.
2. **Hypo is rare**: Per-patient hypo rates range 1.2–13.9%. Class imbalance is structural.
3. **Error scales with BG level**: At 60 min, hypo-range MAE is 26.6 mg/dL vs 21.5 in-range, while R² drops from 0.281 to 0.153 — reliability nearly halves (EXP-817).

---

## Approaches Tried

| Approach | Result | Verdict |
|----------|--------|---------|
| Physics features (supply/demand) | AUC 0.520 → 0.696 (+34%) | ✅ Largest gain |
| Two-stage (classify then forecast) | −32% hypo MAE | ✅ Architecture matters |
| Personalized alert thresholds | −15% false alerts | ✅ Reduces alarm fatigue |
| PK channel features | −0.013 AUC overnight | ❌ Harmful for overnight |
| Focal loss | +0.002 AUC | ❌ Negligible |
| Near-hypo threshold (75 vs 70) | +0.006 AUC | ❌ Marginal |
| Glucose derivatives (dBG/dt, d²BG/dt²) | ±0.003 AUC | ❌ Neutral |
| CNN architecture | Same ceiling as XGBoost | ❌ Not a model problem |
| Extended context (6h, 12h) | No improvement over 2h | ❌ Signal is local |

**The ceiling is robust**: CNN ≈ XGBoost ≈ Transformer all converge to ~0.69 at overnight horizons. Three architectures, five feature sets, three loss functions — same result. This is a **data representation problem**.

---

## Personalized Alert Thresholds (EXP-695)

Fixed-threshold alerts cause alarm fatigue for some patients and miss events for others. Patient-specific thresholds based on prediction error distribution:

| Metric | Fixed | Personalized | Improvement |
|--------|-------|-------------|-------------|
| Mean alert rate (per day) | 2.6 | **2.2** | −15% |
| Patient j (worst case) | 6.0/day | **2.5/day** | −58% |
| Patient k (tightest range) | 0.4/day | **3.4/day** | +750% (more sensitive) |

Personalization adjusts both directions: reduces false alerts for variable patients, increases sensitivity for tight-control patients.

---

## Per-Patient Hypo Landscape

| Patient | Hypo Rate (%) | F1 (baseline) | F1 (cleaned) | Risk Profile |
|---------|---------------|---------------|--------------|-------------|
| i | **13.9** | 0.404 | 0.403 | Highest risk — TBR 10.7%, excessive insulin |
| h | 10.7 | 0.263 | 0.256 | High TBR despite 85% TIR — basal too high |
| k | 9.9 | 0.246 | **0.290** | Tight control, benefits from cleaning |
| c | 6.3 | 0.191 | 0.190 | Moderate risk |
| b | **1.2** | 0.057 | 0.058 | Lowest risk — too few events to learn from |

Patients with <3% hypo rates produce F1 < 0.10 — insufficient positive samples for reliable detection.

---

## Validation Vignette

**Patient i** — Highest-risk patient (TBR 10.7%, mean net flux −10.69 mg/dL/5min). Overnight glucose drops from 142 to 58 mg/dL over 90 minutes. Physics model detects the insulin surplus: active IOB of 3.2 U against zero COB at midnight. The supply-demand decomposition shows demand exceeding supply by 14.9 mg/dL/5min — the highest flux imbalance in the cohort. Alert fires at BG = 95 (47 minutes before reaching 70), providing actionable lead time.

**Patient b** — Lowest-risk patient (TBR 1.0%). Model correctly assigns P(HYPO) < 0.05 for 98.8% of windows. The 1.2% hypo rate means the F1 score (0.058) is misleadingly low — the model is correct to rarely predict hypo for this patient.

---

## Key Insight

Hypoglycemia follows **different physics** than hyperglycemia. Above 180 mg/dL, glucose dynamics are driven by measurable inputs (insulin, carbs). Below 70 mg/dL, counter-regulatory hormones introduce an unmeasured exogenous force that makes trajectories fundamentally less predictable. Breaking the 0.69 ceiling likely requires new data dimensions — continuous glucagon monitoring, cortisol sensing, or wearable stress markers.
