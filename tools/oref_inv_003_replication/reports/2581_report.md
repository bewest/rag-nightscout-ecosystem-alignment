# Algorithm Prediction Quality Validation

**Experiment**: 2581  
**Phase**: Contrast (OREF-INV-003 cross-analysis)  
**Date**: 2026-04-12  

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| F5-eventualBG | — | eventualBG R²=-3.1970 vs actual 4h BG in our data | ✅✅ strongly_agrees |
| F5-loop | — | Loop predicted_60 R²=-0.1560 vs actual 1h BG | ↔️ not_comparable |

## Colleague's Findings (OREF-INV-003)

### F5: eventualBG has R²=0.002 vs actual 4h BG

**Evidence**: OREF-INV-003 Table 7: eventualBG explains 0.2% of 4h outcome variance
**Source**: OREF-INV-003

## Our Findings

### F5-eventualBG: eventualBG R²=-3.1970 vs actual 4h BG in our data ✅✅

**Evidence**: Tested on 8 AAPS/oref0 patients
**Agreement**: strongly_agrees

### F5-loop: Loop predicted_60 R²=-0.1560 vs actual 1h BG ↔️

**Evidence**: Loop's shorter-horizon prediction is much stronger than eventualBG
**Agreement**: not_comparable

## Methodology Notes

Computed R² between algorithm-reported predictions (eventualBG for oref, predicted_60 for Loop) and actual future BG at matching horizons. Also computed R² for PK-derived pk_net_balance vs actual BG change at 1h, 2h, 4h horizons to test physics-based prediction quality.
