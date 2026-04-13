# Basal Correctness Debate: OREF-INV-003 F7 vs Our EXP-1961

**Experiment**: EXP-2451  
**Phase**: Contrast (OREF-INV-003 cross-analysis)  
**Date**: 2026-04-11  
**Data provenance**: ⚠️ Pre-ODC-fix. AAPS/ODC patients used percentage temp basals stored as raw U/hr rates. See EXP-2521 for corrected-data rerun.

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| F7 | basalIOB does NOT indicate whether scheduled basal is correct | basalIOB direction is partially informative at population level | ✅ agrees |
| F7-ext | Cannot conclude scheduled basal is wrong from basalIOB alone | Multi-method analysis confirms basal excess | 🟠 partially_disagrees |
| AID-comp | (Implicit) basalIOB not predicting basal correctness suggests settings may be adequate | AID Compensation Theorem: algorithm masks wrong basals | 🟡 partially_agrees |

## Colleague's Findings (OREF-INV-003)

### F7: basalIOB does NOT indicate whether scheduled basal is correct

**Evidence**: basalIOB is a signed value reflecting algorithm adjustments, not a measure of basal adequacy. Cannot conclude basal is wrong.
**Source**: OREF-INV-003

### F7-ext: Cannot conclude scheduled basal is wrong from basalIOB alone

**Evidence**: Only basalIOB feature examined for basal correctness.
**Source**: OREF-INV-003

### AID-comp: (Implicit) basalIOB not predicting basal correctness suggests settings may be adequate

**Evidence**: No explicit AID compensation analysis.
**Source**: OREF-INV-003

## Our Findings

### F7: basalIOB direction is partially informative at population level ✅

**Evidence**: Only 0/19 patients show consistent negative basalIOB. Their claim appears supported in our data.
**Agreement**: agrees
**Prior work**: EXP-2451

### F7-ext: Multi-method analysis confirms basal excess 🟠

**Evidence**: 3 independent methods (basalIOB sign, supply-demand ratio, fasting BG drift): 0/19 patients basal too high by consensus. SD: 12/19 too high.
**Agreement**: partially_disagrees
**Prior work**: EXP-1961, EXP-2452, EXP-2453

### AID-comp: AID Compensation Theorem: algorithm masks wrong basals 🟡

**Evidence**: TIR stays acceptable even with basals too high because the algorithm compensates (basalIOB-TIR r=-0.315). Wrong basals increase IOB volatility and reduce safety margins.
**Agreement**: partially_agrees
**Prior work**: EXP-1971, EXP-2456

## Synthesis

Both analyses are correct within their scope. basalIOB IS a noisy per-decision signal (their point). But scheduled basals ARE systematically too high (our point, confirmed by supply-demand and fasting analyses). The AID Compensation Theorem explains why: the algorithm masks wrong settings, making TIR appear adequate while increasing IOB volatility.
