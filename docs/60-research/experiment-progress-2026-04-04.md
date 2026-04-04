# Experiment Progress Report — 2026-04-04

## Executive Summary

Today saw 28 experiments (EXP-232 through EXP-275) spanning three major efforts:
**8-channel pipeline maturation** (production-ready), **39-channel enrichment exploration** (problematic — massive overfitting), and **infrastructure fixes** (masking leaks, validation tooling). Two critical masking bugs were found and fixed. The 8f pipeline is validated and stable; the 39f pipeline requires EXP-275 results before deciding next steps.

**⚠ EXP-275 is actively training (PID 384297) — DO NOT disrupt.**

---

## 1. Bug Fixes & Their Impact on Prior Results

### 1a. Masking Leak — `glucose_vs_target` and `pump_reservoir` (commit `9fbe9ba`)

Two channels were missing from `FUTURE_UNKNOWN_CHANNELS`:

| Channel | Index | Leak Severity | Ablation Evidence |
|---------|-------|---------------|-------------------|
| `glucose_vs_target` | 34 | **CRITICAL** — 35× accuracy distortion | MAE 1.1 → 39.5 when ablated |
| `pump_reservoir` | 36 | Moderate — 45% accuracy distortion | MAE 1.1 → 1.6 when ablated |

**Channel 34** is `(glucose - target_mid) / 100`, a near-direct proxy for future glucose since target is a constant from the profile schedule. Any 39-channel model trained without masking ch34 in the future window would have learned to "cheat."

**Which experiments are affected?**

| Scope | Affected? | Reasoning |
|-------|-----------|-----------|
| **All 8f experiments (EXP-232 – EXP-258)** | ✅ **NOT affected** | Channels 34, 36 don't exist in 8-channel input |
| **All 21f experiments** | ✅ **NOT affected** | Channels 34, 36 don't exist in 21-channel input |
| **39f experiments (EXP-260, 261, 263)** | ⚠ **Likely valid** — see below | File timestamps and `"masking": "selective_21ch"` label indicate they ran AFTER the fix |
| **EXP-274, EXP-275** | ✅ **Valid** | Both call `validate_masking()` and were committed after the fix |

**Assessment:** The EXP-260/261/263 JSON files were all written AFTER the 14:02 fix timestamp and report `"selective_21ch"` masking (21 channels = post-fix count). However, if there is ANY doubt, **EXP-260 should be re-run** — it's the 39f baseline that all subsequent 39f experiments reference. **No 8f results need retraining.**

### 1b. In-Place Mutation Bug (commit `d45060c`)

Fixed `_zero_channels_in_dataset()` which was mutating the original dataset tensor instead of a copy. This could have corrupted validation data for experiments that evaluated multiple configurations on the same dataset.

**Impact:** Primarily affects EXP-261 (ablation) where the same val_ds was reused across ablation configs. Results may have been slightly contaminated by cumulative zeroing. The practical effect is small since zeroing is idempotent for repeated channels, but could explain unexpected ordering in ablation results.

### 1c. Asymmetric Window Fix (commit `401f826`)

Added `forecast_steps` parameter to `train_forecast()` and `forecast_mse()`. Before this fix, experiments with asymmetric history:forecast splits (like EXP-264's 90:60 min) would train at the wrong midpoint.

**Impact:** Only EXP-264 (lookback sweep) is affected. EXP-264 has no JSON results file yet, so it may not have completed a valid run. All symmetric-window experiments (the vast majority) are unaffected.

---

## 2. 8-Channel Pipeline — Mature & Production-Ready

The 8f pipeline is the clear winner today. No retraining needed.

### Progression of Best Results (8f)

| Experiment | MAE | Technique | Verification Gap |
|------------|-----|-----------|-----------------|
| EXP-232 | 12.5 | 5-seed ensemble | — |
| EXP-234 | 12.38 | Longer training (150ep) | — |
| EXP-242 | 11.25 | Per-patient FT ensemble | — |
| EXP-249 | — | Verification of EXP-242 | **+2.8%** ✅ |
| EXP-250 | 10.72 | Deep (L=4) per-patient FT | — |
| **EXP-251** | **10.59** | **Extended training (200ep) L=4 FT** | — |
| EXP-254 | — | Verification of EXP-250 | **+7.4%** ⚠ |

**Current best: EXP-251 at 10.59 MAE (59% improvement over persistence baseline 25.9).**

### What Didn't Work (8f)

| Experiment | Technique | Result | Verdict |
|------------|-----------|--------|---------|
| EXP-239 | Hypo-weighted ensemble (w=5) | 12.87 MAE | ❌ Worse than standard |
| EXP-240 | Curriculum learning | Comparable to baseline | ❌ No benefit |
| EXP-243 | Mixed hypo/standard ensemble | 12.46 MAE | ❌ No improvement |
| EXP-244 | MC-Dropout ensemble | Comparable | ❌ No improvement |
| EXP-245 | Wider model (d=128) | 12.49 MAE | ❌ No improvement |
| EXP-246 | Snapshot ensemble | 13.11 MAE | ❌ Worse |
| EXP-252 | Lower LR fine-tuning | 10.70 MAE | ❌ Neutral |
| EXP-255 | Regularized FT (wd=1e-3) | ~10.7 MAE | ❌ Neutral, gap unchanged |
| EXP-256 | Temporal augmentation | Comparable | ❌ Slightly worse verification |
| EXP-257 | Dropout sweep | Mixed | ⚠ Helps easy patients, hurts hard ones |
| EXP-258 | TTA ensemble | 30-45% worse | ❌ **Strongly negative** |

### Verification Gap Concern

| Experiment | Train MAE | Verification MAE | Gap |
|------------|-----------|-----------------|-----|
| EXP-249 (L=2) | 11.25 | 11.56 | **+2.8%** ✅ |
| EXP-254 (L=4) | 10.72 | 11.52 | **+7.4%** ⚠ |

The L=4 deeper model has a larger verification gap (+7.4%) compared to L=2 (+2.8%). This suggests the deeper model is overfitting more to the temporal structure of training data. The L=2 per-patient FT ensemble (EXP-242/249) may be more production-suitable despite lower absolute accuracy.

---

## 3. 39-Channel Enrichment Pipeline — Severe Overfitting Problem

### EXP-260: 39f Enriched Baseline

| Metric | 39f (EXP-260) | 8f (EXP-242) | Delta |
|--------|---------------|--------------|-------|
| Ensemble MAE (train) | 13.8 | 11.25 | **+2.55 worse** |
| Verification MAE | 17.06 | 11.56 | **+5.50 worse** |
| Verification Gap | **28.6%** | **2.8%** | **10× worse** |

**The 39f model is worse than 8f on every metric.** Per-patient gaps are extreme:

| Patient | 39f Ensemble MAE | 39f Verification MAE | Gap % |
|---------|-----------------|---------------------|-------|
| h | 13.07 | 22.28 | **+70.5%** |
| e | 10.67 | 16.38 | **+53.5%** |
| c | 11.96 | 18.14 | **+51.8%** |
| g | 10.96 | 15.19 | +38.6% |
| d | 10.82 | 13.97 | +29.2% |
| i | 11.19 | 14.30 | +27.8% |
| f | 11.93 | 14.15 | +18.7% |
| a | 13.59 | 14.99 | +10.3% |
| b | 23.75 | 25.25 | +6.3% |
| j | 20.09 | 15.97 | **-20.5%** (verification better) |

Patients c, e, g, h show catastrophic overfitting (38-70% gaps).

### EXP-261: Feature Group Ablation

| Group | Channels | MAE Impact | Interpretation |
|-------|----------|------------|----------------|
| **profile** | 32, 33, 34 | **+7.38** | Dominant — ISF, CR, glucose_vs_target |
| **aid_context** | 25-31 | +2.18 | Loop predictions useful |
| **pump_state** | 35, 36 | +0.49 | Minor |
| **cgm_quality** | 21-24 | +0.28 | Minor |
| **sensor_lifecycle** | 37, 38 | +0.16 | Negligible |

The profile group (especially ch34 glucose_vs_target) dominates. Even with ch34 properly masked in the future, the history-side signal is powerful. But it may also be enabling overfitting.

### EXP-263: Forward Feature Selection

| Step | Group Added | MAE | Δ from Previous |
|------|-------------|-----|-----------------|
| 0 | base 21f | 17.53 | — |
| 1 | +profile | 16.79 | -0.74 |
| 2 | +aid_context | 16.67 | -0.12 |
| 3 | +pump_state | 16.72 | +0.05 (hurt) |
| 4 | +cgm_quality | 16.71 | -0.01 |
| 5 | +sensor_lifecycle | 16.81 | +0.10 (hurt) |

Diminishing returns after profile group. The full 39f (16.81) is barely better than 21f+profile (16.79), and both are much worse than 8f per-patient FT (10.59).

### EXP-274: Channel Dropout Regularization

| Config | Train MAE | Verification MAE | Gap % |
|--------|-----------|-----------------|-------|
| baseline (no reg) | 16.81 | 18.24 | 8.5% |
| ch_drop=0.15 | 17.25 | 17.97 | **4.2%** |
| ch_drop=0.30 | 17.70 | 18.20 | **2.8%** |
| combined (0.15+high wd) | 17.42 | 18.31 | 5.1% |

Channel dropout at 0.30 reduces the gap to 2.8% (matching 8f), but the absolute MAE (17.7) is still **67% worse** than 8f (10.59). Regularization solves the generalization problem but doesn't make the model accurate.

### EXP-275: In Progress 🔄

**Status:** Active training (PID 384297). Phase 1 (5 base models) complete. Phase 2 fine-tuning in progress — patient 'a' partially done (17/25 FT checkpoints), 9 patients remaining.

**Hypothesis:** Channel dropout + per-patient FT will rescue the 39f pipeline. This is the critical experiment — if it can bring 39f below 11.25 (EXP-242's 8f baseline), the enrichment effort is justified.

**Estimated remaining:** ~8-9 more patients × 25 FT runs each + final evaluation.

---

## 4. Key Learnings

### What Works
1. **Per-patient fine-tuning** — consistently the largest improvement lever (EXP-241: 8/10 patients improve)
2. **Seed ensembling** (5 seeds) — reliable 0.5-1.0 MAE improvement
3. **Deeper models (L=4)** — lower training MAE but higher verification gap
4. **Extended training (200ep)** — small incremental gains (EXP-251 vs EXP-250)
5. **Selective masking** — 18.2 MAE vs 25.1 MAE for full masking (EXP-230)

### What Doesn't Work
1. **More features (39f) without regularization** — catastrophic overfitting
2. **TTA ensemble** — 30-45% worse across all patients
3. **Curriculum learning, MC-dropout, snapshot ensemble** — no benefit
4. **Hypo-weighted loss at high weights (w=5)** — hurts overall MAE

### Architecture Insight
The 8-channel model with 67K parameters is at a **performance ceiling** (29.5 MAE for 8f single model). The only reliable path to lower MAE is **per-patient specialization** + **ensembling**, NOT more features or bigger models. The 39f enrichment adds information the model can't productively use at this data scale (10 patients, ~3K windows each).

---

## 5. Recommendations

### Immediate (no retraining needed)
- **Wait for EXP-275 to complete** — it will definitively answer whether 39f + per-patient FT is viable
- **Do not re-run 8f experiments** — they are validated and unaffected by masking fixes

### If EXP-275 Fails (39f MAE > 11.25)
- **Abandon 39f for forecasting** — 8f per-patient FT ensemble is the production model
- **Selectively use 39f features** for auxiliary tasks (event detection, override recommendation) where they may help without the overfitting problem
- **Focus hypo safety efforts on 8f** pipeline (EXP-265/266/267 are ready to run)

### If EXP-275 Succeeds (39f MAE < 11.25)
- **Validate with verification split** — the 28.6% gap must close to < 5%
- **Run EXP-267 (hypo safety) and EXP-268 (override)** with the 39f pipeline
- **Keep 8f as fallback** until 39f generalization is confirmed

### Possible Re-Runs Required
| Experiment | Re-Run? | Reason |
|------------|---------|--------|
| EXP-260 | ⚠ **Maybe** | If masking fix timing is uncertain, re-run to confirm baseline |
| EXP-261 | ⚠ **Maybe** | Ablation may be contaminated by in-place mutation bug |
| EXP-264 | ✅ **Yes** | Needs forecast_steps fix; no valid results yet |
| All 8f (EXP-232-258) | ❌ **No** | Unaffected by all fixes |
| EXP-274, 275 | ❌ **No** | Already using fixed masking |
