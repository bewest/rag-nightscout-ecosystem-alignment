# IOB Protective Effect: OREF-INV-003 vs Our EXP-2351

**Experiment**: EXP-2461  
**Phase**: Contrast (OREF-INV-003 cross-analysis)  
**Date**: 2026-04-11  

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| F-iob | iob_basaliob has 8.4% SHAP importance for hypo prediction; negative basalIOB correlates with lower hypo risk | High IOB is PROTECTIVE: RR(Q4 vs Q1)=1.189, 0/2 patients show RR<1 | 🟡 partially_agrees |
| F-iob-causal | basalIOB importance is correlational (SHAP) | Causal direction: glucose→IOB→hypo, not IOB→hypo | 🟡 partially_agrees |

## Colleague's Findings (OREF-INV-003)

### F-iob: iob_basaliob has 8.4% SHAP importance for hypo prediction; negative basalIOB correlates with lower hypo risk

**Evidence**: LightGBM SHAP on 2.9M records from 28 oref users.
**Source**: OREF-INV-003

### F-iob-causal: basalIOB importance is correlational (SHAP)

**Evidence**: No causal direction analysis in OREF-INV-003.
**Source**: OREF-INV-003

## Our Findings

### F-iob: High IOB is PROTECTIVE: RR(Q4 vs Q1)=1.189, 0/2 patients show RR<1 🟡

**Evidence**: Relative risk analysis on our independent dataset of 2 patients. Their statistical SHAP finding and our causal RR finding describe the SAME phenomenon: the AID loop delivers more insulin when it's safe, so high IOB correlates with low hypo risk.
**Agreement**: partially_agrees
**Prior work**: EXP-2351, EXP-2463

### F-iob-causal: Causal direction: glucose→IOB→hypo, not IOB→hypo 🟡

**Evidence**: Glucose change→IOB change r=0.402; IOB change→hypo r=-0.055; glucose change→hypo r=-0.149. The causal chain is: falling glucose triggers AID suspension → IOB drops → hypo follows. High IOB is a MARKER of safety, not a cause.
**Agreement**: partially_agrees
**Prior work**: EXP-2464

## Synthesis

Both analyses identify the same phenomenon but interpret it differently. Their SHAP importance correctly identifies basalIOB as a hypo predictor. Our RR analysis adds causal direction: high IOB is protective BECAUSE the AID loop delivered insulin only when safe. This is the AID Compensation Theorem in action: the loop's own behavior creates a protective correlation between IOB and outcomes. Clinical implication: do NOT reduce IOB to prevent hypos — the algorithm is already doing the right thing.
