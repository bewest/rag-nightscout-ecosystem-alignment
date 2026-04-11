# PK-Enriched Hypo Prediction

**Experiment**: EXP-2471  
**Phase**: Contrast (OREF-INV-003 cross-analysis)  
**Date**: 2026-04-11  

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| F-features | 32-feature schema achieves hypo AUC=0.83 in-sample | PK-enriched features improve hypo AUC: 0.870→0.903 (Δ=+0.034) | 🟡 partially_agrees |

## Colleague's Findings (OREF-INV-003)

### F-features: 32-feature schema achieves hypo AUC=0.83 in-sample

**Evidence**: LightGBM on 2.9M records, 32 features.
**Source**: OREF-INV-003

## Our Findings

### F-features: PK-enriched features improve hypo AUC: 0.870→0.903 (Δ=+0.034) 🟡

**Evidence**: Adding 10 PK features from our insulin pharmacokinetics analysis (circadian ISF, IOB trajectory, supply-demand, meal timing). PK features capture individual variability not in their schema.
**Agreement**: partially_agrees
**Prior work**: EXP-2351, EXP-2475

## Synthesis

PK-enriched features improve hypo prediction (Δ AUC = +0.034). The most valuable additions are circadian ISF ratio, IOB trajectory, and supply-demand imbalance. These features capture pharmacokinetic individual variability that the colleague's 32-feature schema misses.
