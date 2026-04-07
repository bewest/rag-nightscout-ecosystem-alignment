# Transfer Learning & Window Asymmetry Report

**Date**: 2026-04-10
**Experiments**: EXP-461 through EXP-470
**Scope**: Transfer learning, window asymmetry, curriculum learning, routing optimization

## Executive Summary

This report covers 10 experiments that establish two major findings:

1. **Window transfer learning** (w48→target) is the single most effective improvement lever for extended-horizon forecasting, giving −0.93 to −1.21 MAE depending on target window size.

2. **Asymmetric history:future ratios** dramatically improve h5-h120 predictions. Maximizing history (9h20m) with minimal future projection yields h60=18.05 — a new best.

These findings enable an optimal routing pipeline covering h30-h360. EXP-470's 3-specialist pipeline achieved composite MAE of 23.34 (quick mode, 4 patients); adding asym_112_32 as a 4th specialist is projected to improve this to ~22.95.

## Key Results Table

| EXP | Description | Key Result | Δ vs Control |
|-----|-------------|-----------|--------------|
| 461 | Combined 2nd PK + fidelity | h180 −1.47 | −0.55 overall |
| 462 | Transfer w48→w96 | h60 −1.19, h180 −1.52 | **−0.93 overall** |
| 463 | Triple stack (all levers) | h240 −1.36 | −1.03 overall |
| 464 | Curriculum w24→w48→w96 | Two-hop worse | −0.45 (vs −0.93 single) |
| 465 | Transfer w48→w144 | h360 −1.80 | **−1.21 overall** |
| 466 | Routing w96 vs w144 | w144 wins h60, w96 wins h120 | Strategy clarified |
| 467 | Extended FT (15/30/45ep) | Diminishing returns | −0.10 for 45ep vs 15ep |
| 468 | Asym w96 64h+32f | h30 −1.47, h60 −1.32 | **−2.72 overall** |
| 469 | Asym w144 112h+32f | **h60=18.05, h120=22.58** | −4.91 vs symmetric |
| 470 | 3-specialist routing | Composite MAE=23.34 | Full h30-h360 coverage |

## Finding 1: Transfer Learning

### What Works

Single-hop transfer from a well-trained w48 model to any larger window:

| Target | Transfer Δ | Best At |
|--------|-----------|---------|
| w96 | −0.93 overall | h60 −1.19, h180 −1.52 |
| w144 | −1.21 overall | h300 −1.63, h360 −1.80 |

Transfer benefit **increases with target window size** — longer windows need good initialization most.

### What Doesn't Work

- **Two-hop curriculum** (w24→w48→w96): −0.45 vs single-hop's −0.93. The intermediate w24 stage doesn't add useful representations.
- **Extended FT**: ft45 gives only −0.10 vs ft15. Early stopping dominates — transfer initialization is already strong enough.
- **Triple stacking**: Transfer + fidelity + 2nd PK (−1.03) barely beats transfer alone (−1.02). The levers partially cannibalize, except at h240+ where they're additive.

### Mechanism

Transfer works because:
1. w48 learns excellent glucose+PK attention patterns on 2× more data (10,360 vs 5,176 windows for w96)
2. These patterns (temporal convolutions, attention heads) transfer via shared transformer weights
3. Positional encoding is re-initialized (different sequence length) but learned quickly
4. 53-56 of 56 parameter tensors transfer with matching shapes

### Production Recommendation

Always train a w48 base model first, then transfer to target window. Cost: one extra training run (~2 min quick mode). Benefit: consistent −0.93 to −1.21 MAE across all horizons.

## Finding 2: Window Asymmetry

### The Discovery

Standard practice uses symmetric windows (equal history and future). But shifting the split toward more history dramatically helps short-mid horizons:

| Config | History | Future | h30 | h60 | h120 | Max Horizon |
|--------|---------|--------|-----|-----|------|-------------|
| w96 sym 48+48 | 4h | 4h | 15.88 | 19.81 | 23.76 | h240 |
| w96 asym 64+32 | 5h20m | 2h40m | **14.41** | **18.49** | **23.31** | h160 |
| w144 sym 72+72 | 6h | 6h | 15.30 | 19.21 | 24.54 | h360 |
| w144 asym 112+32 | 9h20m | 2h40m | **14.70** | **18.05** | **22.58** | h160 |
| w144 asym 96+48 | 8h | 4h | 17.73 | 21.97 | 24.68 | h240 |

### Why asym_96_48 Fails

Counter-intuitively, asym_96_48 (8h history + 4h future) is **worse** than symmetric 72+72. The model still must predict 48 future steps but now has proportionally less future PK context. The sweet spot is 32 future steps (h160) — enough PK context for near-term, with maximum history.

### Why More History Helps

With 9h20m of history (asym_112_32), the model sees:
- **Complete insulin absorption cycles** (DIA ≈ 5-6h): at least one full cycle visible
- **Circadian context**: ~40% of a day's pattern
- **Multiple meal cycles**: typically 2-3 meals visible
- **Trend establishment**: long enough to distinguish transient events from sustained trends

The future PK projection (32 steps = h160) provides the causal insulin/carb information, while the deep history provides the context to interpret it.

### Diminishing Returns Pattern

| History Length | Δ h60 vs symmetric |
|---------------|-------------------|
| 5h20m (w96 asym) | −1.32 |
| 9h20m (w144 asym) | −1.16 |

The benefit from 5h20m→9h20m is smaller than 4h→5h20m, suggesting diminishing returns beyond ~6h of history for short horizons. However, h120 still improves (−0.45 → −1.96), indicating longer horizons benefit from longer history.

## Finding 3: Optimal Routing Architecture

### Best Specialist Per Horizon Band

| Band | Best Specialist | MAE Range | Why |
|------|----------------|-----------|-----|
| h5-h30 | short_asym (w96, 64h+32f) | 14.4 | Slightly beats asym_112_32 at h30 (14.41 vs 14.70) |
| h60-h120 | asym_112_32 (w144, 112h+32f) | 18.1-22.6 | Maximum history for mid horizons |
| h150-h180 | mid_sym (w96, 48h+48f) | 23.7-24.5 | Balanced coverage |
| h240-h360 | long_sym (w144, 72h+72f) | 26.7-30.7 | Maximum future projection |

### Optimal Composite Routing

The following table presents the best specialist per horizon across EXP-468, 469, and 470. Note: EXP-470 itself tested only 3 specialists (short_asym, mid_sym, long_sym); the asym_112_32 results come from EXP-469 and are included here as the ideal cross-experiment routing.

| Horizon | MAE | Specialist | Source |
|---------|-----|------------|--------|
| h30 | 14.41 | short_asym (w96 64+32) | EXP-468 |
| h60 | 18.05 | asym_112_32 (w144 112+32) | EXP-469 |
| h120 | 22.58 | asym_112_32 (w144 112+32) | EXP-469 |
| h150 | 23.66 | mid_sym (w96 48+48) | EXP-470 |
| h180 | 24.54 | mid_sym (w96 48+48) | EXP-470 |
| h240 | 26.67 | long_sym (w144 72+72) | EXP-470 |
| h360 | 30.72 | long_sym (w144 72+72) | EXP-470 |

Cross-experiment composite average: 22.95. The EXP-470 3-specialist composite (without asym_112_32) was 23.34.

### Production Pipeline

```
w48 base (shared) ──┬──→ asym w96 (64+32)  → h5-h30 predictions
                    ├──→ asym w144 (112+32) → h60-h120 predictions
                    ├──→ sym w96 (48+48)    → h150-h180 predictions  
                    └──→ sym w144 (72+72)   → h240-h360 predictions
```

All specialists share the same w48 transfer initialization. Total model count: 5 (1 base + 4 specialists). The 3-specialist variant (EXP-470, without asym_112_32) achieved composite MAE=23.34; the 4-specialist variant with asym_112_32 is expected to improve this to ~22.95.

## Confirmed Dead Ends (Updated)

| Finding | Experiments | Result |
|---------|------------|--------|
| Two-hop curriculum transfer | EXP-464 | −0.45 vs −0.93 single-hop |
| Extended FT with transfer | EXP-467 | −0.10 for 3× more FT epochs |
| Triple stack vs transfer alone | EXP-463 | −1.03 vs −1.02 (marginal) |
| asym_96_48 (8h+4h) | EXP-469 | Worse than symmetric |
| Feature engineering for transformer | EXP-428,443,457 | Learns derivatives internally |

## Strategic Implications

### For Production (h60 Champion)
- **Current best**: asym_112_32 with transfer, h60=18.05 (quick mode)
- Needs full validation (11pt, 5 seeds) to confirm
- If confirmed, replaces w48_sym (h60=14.21 full validated) as champion candidate
- Note: different evaluation windows (quick vs full) — not directly comparable

### For Extended Horizons (h120-h360)
- Routing pipeline is viable: coverage from h30 to h360 with 3 specialists
- All specialists benefit from shared w48 transfer
- h120 effectively solved at ~22.6 MAE (quick mode)
- h360 still challenging at ~30.7 MAE — room for improvement

### For Future Research
1. **Full validation of asym_112_32** — highest priority
2. **asym_112_32 as short specialist in routing** — replace current short_asym
3. **Larger w144 asym variants** for h120-h240 (e.g., asym_104_40)
4. **Explore w192 or w240** for h360 specialist with transfer
5. **Ensemble across specialists** — average overlapping horizon predictions

## Appendix: Per-Patient Results (EXP-469 asym_112_32)

| Patient | Overall | h30 | h60 | ISF |
|---------|---------|-----|-----|-----|
| a | 27.37 | 19.93 | 25.32 | 49 |
| b | 18.54 | 13.35 | 17.52 | 94 |
| c | 10.86 | 8.79 | 10.08 | 77 |
| d | 20.26 | 16.72 | 19.28 | 40 |

Note: Per-patient h120 breakdown was not captured in the experiment output. The aggregate h120=22.58 is reported in the main results table.

Patient c remains the easiest (low ISF variance, high fidelity), patient a the hardest (highest absolute glucose swings).
