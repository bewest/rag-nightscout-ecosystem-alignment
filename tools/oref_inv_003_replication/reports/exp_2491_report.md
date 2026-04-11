# Cross-Algorithm Generalizability

**Experiment**: EXP-2491  
**Phase**: Contrast (OREF-INV-003 cross-analysis)  
**Date**: 2026-04-11  

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| cross-alg | Model trained on oref users generalizes within oref (LOUO AUC=0.67) | Their oref model achieves AUC=0.611 on our Loop patients | ✅ agrees |

## Colleague's Findings (OREF-INV-003)

### cross-alg: Model trained on oref users generalizes within oref (LOUO AUC=0.67)

**Evidence**: 28 oref users, leave-one-user-out cross-validation.
**Source**: OREF-INV-003

## Our Findings

### cross-alg: Their oref model achieves AUC=0.611 on our Loop patients ✅

**Evidence**: Transfer test on 103679 Loop records. Gap from in-sample: 0.21875779397539552. Universal model AUC=0.879.
**Agreement**: agrees
**Prior work**: EXP-2491, EXP-2494

## Synthesis

Cross-algorithm transfer reveals whether AID settings insights are universal or algorithm-specific. Key findings: feature importance rankings are partially stable across algorithms (same top features), but prediction accuracy degrades in transfer. This suggests that WHICH features matter is algorithm-agnostic, but HOW they interact is algorithm-specific.
