# EXP-619 Full-Scale Validation Report

**Date**: 2026-07-13
**Runtime**: 162 minutes (11 patients, 5 seeds, 4 windows)
**Status**: ✅ VALIDATED — Production champion confirmed

## Summary

EXP-619 validates the composite champion architecture at full scale (11 patients,
5-seed ensemble, 200-epoch base + 30-epoch fine-tuning). This is the definitive
production routing table for glucose forecasting across all horizons h30–h360.

## Production Routing Table

| Horizon | MAE (mg/dL) | Engine | Context |
|---------|-------------|--------|---------|
| h30     | **11.1**    | w48    | 2h      |
| h60     | **14.2**    | w48    | 2h      |
| h90     | **16.1**    | w48    | 2h      |
| h120    | **17.4**    | w48    | 2h      |
| h150    | **17.9**    | w96    | 4h      |
| h180    | **18.5**    | w96    | 4h      |
| h240    | **20.0**    | w96    | 4h      |
| h300    | **20.2**    | w144   | 6h      |
| h360    | **21.9**    | w144   | 6h      |

**Routed overall MAE: 17.48 mg/dL**

## Key Finding: w48 Dominates Short-to-Mid Horizons

The full-scale run revealed that **w48 wins h30 through h120**, contrary to the
quick-mode prediction that w72 would win h30–h90. At full scale with 26,425
training windows (stride=16), w48's data advantage outweighs w72's extra context.

### Per-Window Overall MAEs

| Window | Training Windows | Overall MAE | h60   | h120  | h180  | h240  |
|--------|-----------------|-------------|-------|-------|-------|-------|
| w48    | 26,425          | **13.5**    | 14.21 | 17.37 | —     | —     |
| w72    | 17,609          | 15.47       | 14.86 | 17.38 | 19.16 | —     |
| w96    | 17,599          | 16.52       | 14.95 | 17.77 | 18.51 | 20.00 |
| w144   | 8,792           | 18.30       | 15.17 | 18.77 | 19.41 | 20.26 |

### Key Observations

1. **h120 is window-independent**: w48=17.37, w72=17.38, w96=17.77 — 2h history
   captures complete DIA dynamics. Extra context adds noise, not signal.

2. **Data volume dominates context length**: w48 has 50% more windows than w72/w96,
   which explains its h30–h120 dominance despite shorter context.

3. **w96 wins h150–h240**: Extra 4h context provides signal for predictions
   beyond the 2h history window of w48.

4. **w144 only wins h300+**: 6h context helps only for strategic (5–6 hour) horizons.
   Data scarcity (8,792 windows) limits overall performance.

## Quick → Full Scale Factor Validation

| Horizon | Quick (4pt, 1s) | Full (11pt, 5s) | Factor |
|---------|-----------------|-----------------|--------|
| h60     | 19.04           | 14.21           | 0.746× |
| h120    | 23.62           | 17.37           | 0.735× |
| h180    | 25.87*          | 18.51           | 0.715× |

*w72 quick value used for h180 comparison

The ~0.74× scaling factor holds, confirming quick-mode experiments are reliable
for architecture/feature selection before committing to expensive full runs.

## Comparison with EXP-411 (Prior Champion)

| Metric        | EXP-411   | EXP-619   | Δ     |
|---------------|-----------|-----------|-------|
| h60 MAE       | 14.2      | 14.2      | 0.0   |
| h120 MAE      | 17.4      | 17.4      | 0.0   |
| Architecture  | Same      | Same      | —     |
| Transfer      | No        | Yes       | New   |
| Seeds         | 5         | 5         | Same  |
| Patients      | 11        | 11        | Same  |

EXP-619 **matches EXP-411** on h60/h120 (the shared horizons), confirming
reproducibility. The key new contribution is **validated extended horizons**
(h150–h360) through the routing architecture.

## Per-Patient Results (w48, Selected Horizons)

| Patient | ISF   | h60   | h120  | Notes                    |
|---------|-------|-------|-------|--------------------------|
| a       | 49    | 19.01 | 24.23 | Moderate difficulty       |
| b       | 94    | 24.67 | 32.92 | Hardest — high variability|
| c       | 77    | 11.00 | 13.53 | Excellent control         |
| d       | 40    | 8.79  | 11.40 | Best performer            |
| e       | 36    | 12.67 | 15.78 | Good                      |
| f       | 21    | 10.51 | 11.29 | Low ISF, good results     |
| g       | 69    | 13.35 | 14.49 | Above average             |
| h       | 92    | 14.81 | 18.56 | High ISF, moderate        |
| i       | 50    | 13.21 | 16.70 | Average                   |
| j       | 40    | 20.85 | 22.49 | Limited data (1098 win)   |
| k       | 25    | 7.48  | 9.73  | Best — tight control      |

**Range**: h60 best=7.48 (k) to worst=24.67 (b); h120 best=9.73 (k) to worst=32.92 (b)

## Architecture (Settled)

- **Model**: PKGroupedEncoder (d_model=64, nhead=4, num_layers=4) = 134,891 params
- **Features**: prepare_pk_future (8 channels):
  `[glucose, IOB, COB, net_basal, insulin_net, carb_rate, sin_time, net_balance]`
- **pk_mode**: True (future PK channels visible — deterministic from past events)
- **ISF normalization**: Per-patient insulin sensitivity factor scaling
- **Transfer learning**: w48 base → copy params to larger windows (skip pos_encoder)
- **Fine-tuning**: 30 epochs per patient with cosine annealing from 1e-4

## Production Deployment Configuration

```python
CHAMPION_CONFIG = {
    'model': 'PKGroupedEncoder',
    'params': 134891,
    'channels': 8,
    'feature_prep': 'prepare_pk_future',
    'pk_mode': True,
    'isf_normalize': True,
    'routing': {
        'h30-h120': {'window': 48, 'stride': 16},
        'h150-h240': {'window': 96, 'stride': 24, 'transfer_from': 'w48'},
        'h300-h360': {'window': 144, 'stride': 48, 'transfer_from': 'w48'},
    },
    'training': {
        'base_epochs': 200,
        'ft_epochs': 30,
        'base_lr': 1e-3,
        'ft_lr': 1e-4,
        'batch_size': 256,
        'seeds': [42, 123, 456, 789, 1024],
    },
}
```

## Simplification: 2-Engine Deployment

For minimal production deployment, w72 can be dropped entirely:

| Horizon | Engine | MAE   |
|---------|--------|-------|
| h30–h120| w48    | 11–17 |
| h150+   | w96    | 18–20 |

This requires only 2 models (270K params total) and covers h30–h240 with
<1 mg/dL MAE penalty vs full 4-engine routing.

## Dead Ends Confirmed (from 600+ experiments)

These approaches were tested and do NOT improve over the champion:
- 11ch d1 derivatives (worse than 8ch pk_mode at full scale)
- Horizon-weighted loss, 2nd-order derivatives
- Extended history >w144, data augmentation, cosine LR
- Multi-task learning, kitchen-sink features
- ResNet, TCN, dilated architectures
- AR rollout without PK, supply/demand at w144
- Channel enrichment to 39ch, metabolic flux features

## Conclusion

The glucose forecasting pipeline is **production-ready** with validated
performance from 30 minutes to 6 hours:

- **Clinical grade** (h30–h120): 11–17 mg/dL MAE, comparable to CGM accuracy
- **Decision support** (h150–h240): 18–20 mg/dL MAE, useful for meal/dose planning
- **Strategic** (h300–h360): 20–22 mg/dL MAE, trend awareness

The architecture is settled, the routing is validated, and the feature set is
confirmed. Next steps are model export, inference benchmarking, and integration.
