# Window Optimization, Augmentation, and Ensemble Report

**Date**: 2026-04-10  
**Experiments**: EXP-471 through EXP-479  
**Prior Report**: `transfer-learning-and-window-asymmetry-report-2026-04-10.md`

## Executive Summary

Nine experiments systematically explored the remaining optimization levers for PK-enhanced glucose forecasting after establishing transfer learning and asymmetric windows as the dominant techniques. **The key finding is a data volume vs. history length trade-off**: w48 (symmetric, 10360 training windows) outperforms w144 (asymmetric 112h+32f, 3448 windows) even at h60, suggesting that data volume is currently the binding constraint, not model architecture or history length.

## Results Summary

| EXP | Description | Overall MAE | h60 | Key Finding |
|-----|-------------|-------------|-----|-------------|
| 471 | h60-focused loss (w96) | 19.25 | 18.58 | h120 −0.46 but h30 +0.15. Marginal |
| 472 | Autoregressive rollout | — | 91.33 | **Catastrophic failure**. Error compounds without PK |
| 473 | ISF-based routing | 19.45 | 18.27 | ISF threshold doesn't help; w144 universally better |
| 474 | w144 + horizon focus | 18.99 | 17.73 | **Uniform MSE already optimal** on w144 |
| 475 | Extended history w192/w240 | 20.64/20.78 | 20.37/20.35 | **WORSE** — data scarcity dominates |
| 476 | Future window sweep (w192) | 20.44–27.17 | 20.14–22.02 | Max history always wins at any future length |
| 477 | Data augmentation (4×) | 19.26 | 18.17 | **Hurts** — model overfits to noise patterns |
| 478 | Multi-window ensemble | 16.73 (w48) | 17.36 (w48) | **w48 beats w144** due to 3× more data |
| 479 | Hard patient extended FT | 19.14 | 17.99 | Hard patients unchanged; fundamental limit |

## Deep Dives

### 1. Horizon-Focused Loss Is a Dead End (EXP-471, 474)

Tested 3× weighting at h60, h90, and h120 positions on both w96 and w144 asymmetric windows with transfer. In all cases, the weighted loss sacrificed h30 accuracy (+0.15 to +0.48) without meaningfully improving the targeted horizon. The transformer already allocates attention optimally across horizons under uniform MSE — explicit weighting disrupts this balance.

**Conclusion**: Uniform MSE is the correct loss function for multi-horizon forecasting.

### 2. Autoregressive Rollout Fails Catastrophically (EXP-472)

Rolling the asym_64_32 model forward (using its h160 predictions as new history for a second pass) produced h55=91.33 vs direct h60=18.49. The naive approach fails because:
- Predicted glucose replaces masked PK channels, losing causal information
- Prediction errors compound without PK absorption curves to anchor the trajectory
- The model was trained with ground-truth history, not its own predictions

**Conclusion**: AR rollout requires PK-aware context maintenance. Simple window shifting is not viable.

### 3. w144 Is the Sweet Spot — NOT the Optimum (EXP-475, 476)

History length sweep revealed a clear pattern:

| Window | History | Train Windows | Overall MAE | h60 |
|--------|---------|---------------|-------------|-----|
| w48 | 2h | 10,360 | 16.73 | 17.36 |
| w96 | 5h20m | 5,176 | 19.36 | 18.49 |
| w144 | 9h20m | 3,448 | 19.14 | 17.84 |
| w192 | 13h20m | 2,584 | 20.64 | 20.37 |
| w240 | 17h20m | 2,064 | 20.78 | 20.35 |

**The pattern**: Data volume decreases as window size increases (longer windows have fewer non-overlapping samples). Beyond w144, the data scarcity penalty outweighs the history benefit. Critically, w48 with 3× more data actually produces better h60 (17.36) than w144 (17.84).

Future window sweep (EXP-476) confirmed: at any fixed total window size, maximizing history steps and minimizing future steps always wins. The f32 (32 future steps) variant dominated f48, f64, and f96 at every horizon.

### 4. Data Augmentation Doesn't Help (EXP-477)

4× augmentation (Gaussian noise, scale ±5%, time shift ±1) produced 17,240 training windows from 3,448 originals. The augmented model had much lower training loss (0.095 vs 0.201) but higher validation loss — classic overfitting to synthetic patterns. The augmentations preserve PK physics but don't add the real-world diversity the model needs.

### 5. Hard Patients Are Data-Limited, Not Training-Limited (EXP-479)

Extended FT (15/30/50 epochs, lr 1e-4/5e-5) showed:
- Patient a: MAE=23.1, h60=20.97 — **identical** across all 4 FT configs
- Patient b: MAE=29.02, h60=26.38 — **identical** across all 4 FT configs
- Easy patients (c, d) show marginal improvement with longer FT

Early stopping converges to the same point regardless of training budget. These patients have intrinsically harder-to-predict glucose dynamics — more training epochs won't help. Patient b (ISF=94, high insulin sensitivity) likely has faster glucose dynamics that the 5-minute CGM sampling rate can't capture well.

### 6. The Data Volume Revelation (EXP-478)

The most surprising finding: comparing w48 (symmetric) and w144 (asymmetric) on the same patients:

| Model | Training Windows | Overall MAE | h30 | h60 | h90 | h120 |
|-------|-----------------|-------------|-----|-----|-----|------|
| w48 | 10,360 | **16.73** | **13.18** | **17.36** | **20.20** | 22.68 |
| w144 | 3,448 | 19.12 | 14.62 | 17.77 | 21.19 | **22.48** |

w48 wins h5 through h90 despite having only 2h history. w144 only wins at h120 — barely. This means **data volume is currently the primary constraint**, not history length or architecture.

## Updated Dead Ends List (Cumulative)

| # | Approach | Evidence | Why It Fails |
|---|----------|----------|--------------|
| 1 | Feature engineering for transformer | EXP-428, 443, 457 | Transformer learns features from raw signals |
| 2 | Longer history alone for short horizons | EXP-429, 430, 437, 454 | Data scarcity offsets benefit |
| 3 | Metabolic flux features | EXP-457 | Redundant with PK channels |
| 4 | Multi-task overnight risk | EXP-455 | Task interference |
| 5 | Horizon-weighted loss | EXP-426, 433, 440, **471, 474** | Uniform MSE already optimal |
| 6 | Cosine LR | EXP-444 | No benefit with early stopping |
| 7 | Two-hop curriculum transfer | EXP-464 | Intermediate checkpoint hurts |
| 8 | Extended FT with transfer | EXP-467 | Diminishing returns past 15ep |
| 9 | asym_96_48 ratio | EXP-469 | Wrong history:future ratio |
| 10 | **Naive AR rollout** | **EXP-472** | Error compounds without PK context |
| 11 | **ISF-threshold routing** | **EXP-473** | w144 universally better than routing |
| 12 | **Extended windows >w144** | **EXP-475** | Data scarcity ceiling |
| 13 | **Data augmentation** | **EXP-477** | Overfits to synthetic noise |
| 14 | **Extended per-patient FT** | **EXP-479** | Hard patients at data/signal limit |

## Key Insights and Implications

### The Data Volume Constraint

The dominant finding across all 9 experiments is that **data volume is currently the binding constraint**. Every approach that reduces training data (longer windows, patient subsetting, augmentation artifacts) hurts performance. This has profound implications:

1. **More patients** is likely the single highest-impact intervention
2. **Overlapping windows** with smaller stride could increase w144 data 2-3×
3. **Pre-training on larger glucose datasets** could provide better initialization than w48 transfer

### The w48 Paradox

w48 (2h history) beats w144 (9h20m history) at h60. This seems to contradict the DIA/PK hypothesis that longer history should help. The resolution: at quick-mode scale (4 patients), w48's 3× data advantage overwhelms w144's information advantage. At full scale (11 patients, 5 seeds), w144 might win because:
- More diverse training signal from 11 patients mitigates data scarcity
- The PK history advantage becomes signal rather than noise

**This must be validated at full scale before production decisions.**

### Production Architecture Recommendation (Updated)

Given the data volume findings:

| Horizon | Model | Rationale |
|---------|-------|-----------|
| h5-h60 | w48 symmetric + FT | Most data, best h30-h60 |
| h60-h120 | w144 asym + transfer | More context, comparable h60 |
| h120-h360 | Routing pipeline (EXP-470) | Specialist coverage |

But the simpler approach may be best: **just use w48 with transfer for everything** until more patient data is available.

## Next Research Priorities

### High Priority
1. **Full validation of w48 vs w144** at 11 patients, 5 seeds — resolve the paradox
2. **Stride reduction for w144** — increase from stride=36 to stride=18, doubling training data
3. **Proper prediction-level ensemble** — average model outputs, not MAE metrics

### Medium Priority
4. **Pre-training on synthetic CGM** — generate large-scale glucose trajectories
5. **Cross-patient transfer** — train on all patients, evaluate LOO
6. **Hard patient analysis** — examine what makes a/b predictions fundamentally harder

### Low Priority (Explored, Diminishing Returns)
7. Architecture changes (confirmed: more params hurts at this scale)
8. Loss function engineering (uniform MSE is optimal)
9. Extended FT budgets (early stopping dominates)
