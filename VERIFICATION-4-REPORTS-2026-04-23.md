# Research Report Verification Summary
**Date**: 2026-04-23  
**Reports Reviewed**: 4 (exp-2946, exp-2947, exp-2949, exp-2950)

---

## REPORT 1: exp-2946-pp-iob-timing-2026-04-23.md

**Status**: ✅ PASS

### Verified Claims
- **Result table** (2,507 quiet-pre meals): All per-design statistics match JSON exactly
- **Per-design breakdown**:
  - Loop_AB_OFF: n=170, carbs=49.0, iob_peak=12.77, TIR=39.7% ✓
  - Loop_AB_ON: n=697, carbs=37.9, iob_peak=9.01, TIR=58.9% ✓
  - oref0: n=622, carbs=41.5, iob_peak=3.45, TIR=69.1% ✓
  - oref1: n=1018, carbs=56.6, iob_peak=4.49, TIR=80.3% ✓
- **Head-to-head contrasts** (Loop_AB_ON vs oref1): All 8 metrics verified
- **Dose-per-gram calculations**: 0.24 U/g (Loop) vs 0.08 U/g (oref1) — exact 3× ratio ✓
- **IOB lead timing**: −35 min (Loop) vs −55 min (oref1) — medians verified ✓
- **Tertile analysis**: All sample sizes and TIR values correct
- **Cross-references**: EXP-2944, EXP-2929, EXP-2918 all exist ✓

### Quality Checks
✓ No fabricated numbers  
✓ 19/19 patients accounted for  
✓ Meal sums correct (170+697+622+1018=2,507)  
✓ Values physiologically plausible  
✓ Interpretations well-supported by data  

---

## REPORT 2: exp-2947-hypo-iob-decay-2026-04-23.md

**Status**: ✅ PASS

### Verified Claims
- **Event counts**: 5,205 carb-isolated descend events (606+1442+835+2322=5,205) ✓
- **Per-design table**: All values match exp-2947_summary.json exactly
  - Loop_AB_OFF: n=606, iob_at_entry=0.469, bg_min_60=65.7, tbr_54=5.3%, basal_cut=75.5% ✓
  - Loop_AB_ON: n=1442, iob_at_entry=0.373, bg_min_60=63.2, tbr_54=7.0%, basal_cut=96.1% ✓
  - oref0: n=835, iob_at_entry=0.272, bg_min_60=54.9, tbr_54=17.0%, basal_cut=52.8% ✓
  - oref1: n=2322, iob_at_entry=0.564, bg_min_60=67.3, tbr_54=3.2%, basal_cut=91.1% ✓
- **Severity ratio claims**:
  - "2× more severe" (7.0% vs 3.2%) = 2.19× ✓
  - "5× higher" (17% vs 3.2%) = 5.31× ✓
- **Counter-intuitive paradox**: All sub-claims mathematically verified
  - Loop_AB_ON lower IOB (0.373 vs 0.564) ✓
  - Loop_AB_ON more decay (−1.452 vs −0.537) ✓
  - Loop_AB_ON deeper hypo (63.2 vs 67.3) ✓
- **Cross-references**: EXP-2944, EXP-2918, EXP-2925 all exist ✓

### Quality Checks
✓ Event anchor matches code (BG=80, prior 30min >80)  
✓ Hypo thresholds correctly computed  
✓ Basal-cut percentages verified  
✓ Pareto dominance claim supported by data  

---

## REPORT 3: exp-2949-iob-age-operationalisation-2026-04-23.md

**Status**: ✅ PASS

### Verified Claims
- **insulin_activity table** (line 29-33): All means exact match
  - Loop_AB_OFF: 0.000 ✓
  - Loop_AB_ON: 0.000 ✓
  - oref0: 0.000 ✓
  - oref1: 0.007 (hypo) / 0.016 (high) ✓
- **time_since_bolus_min table** (all 12 medians verified):
  - HYPO entry: 360, 70, 180, 60 ✓
  - SUSTAINED-HIGH: 360, 0, 65, 0 ✓
  - MEAL onset: 0, 0, 0, 0 ✓
- **Event counts**: 5,205 hypo / 5,165 sustained-high / 2,029 meal ✓
- **P-value significance**: All accurately characterized (p ≪ 0.001) ✓
- **Cross-references**: EXP-2944, 2946, 2947, 2937, 2940 all exist ✓

### Quality Checks
✓ Negative result correctly presented (falsification of freshness ratio approach)  
✓ tsb interpretation correct (lower tsb = fresher bolus)  
✓ Mechanism attribution correct (iob_delta, not tsb proxy)  
✓ Event definitions match source code  

**Note**: P-value "0" represents scipy underflow (<1e-300); standard notation.

---

## REPORT 4: exp-2950-uniform-action-curve-2026-04-23.md

**Status**: ✅ PASS

### Verified Claims
- **Sample size**: 5,159 sustained-high entries (609+1626+1203+1721=5,159) ✓
- **Per-design table**: All values match exp-2950_summary.json exactly
  - Loop_AB_OFF: n=609, iob_entry=3.30, iob_delta=+0.69, bg_delta=+21.64 ✓
  - Loop_AB_ON: n=1,626, iob_entry=6.38, iob_delta=+0.40, bg_delta=+12.16 ✓
  - oref0: n=1,203, iob_entry=1.91, iob_delta=−0.05, bg_delta=+10.80 ✓
  - oref1: n=1,721, iob_entry=7.02, iob_delta=−0.78, bg_delta=−9.60 ✓
- **Contrast calculations**:
  - iob_entry gap: 7.02−6.38 = 0.64 ✓
  - act_entry % increase: 0.0454/0.0386 = 1.176 (18% claimed, 17.6% actual — acceptable rounding)
  - iob_delta gap: 0.40−(−0.78) = 1.18 ✓
  - bg_delta gap: 12.16−(−9.60) = 21.76 ≈ 22 mg/dL ✓
- **Action curve formula**: Pre-peak IOB(t) = 1−0.5(t/75)² verified ✓
- **EXP-2944 comparison**: All direction indicators correct ✓

### Quality Checks
✓ All arithmetic verified  
✓ Effect sizes and p-values reasonable  
✓ Cross-experiment consistency confirmed  
✓ Biological plausibility supported  

---

## SUMMARY

| Report | Status | Critical Errors | Issues |
|--------|--------|-----------------|--------|
| EXP-2946 (pp-iob-timing) | ✅ PASS | 0 | 0 |
| EXP-2947 (hypo-iob-decay) | ✅ PASS | 0 | 0 |
| EXP-2949 (iob-age-operationalisation) | ✅ PASS | 0 | 0 |
| EXP-2950 (uniform-action-curve) | ✅ PASS | 0 | 0 |

### Overall Result: **ALL 4 REPORTS PASS VERIFICATION** ✅

**All four reports are accurate and ready for publication.**

### Verification Coverage
✓ Per-patient/per-design tables verified against JSON  
✓ Headline statistics confirmed  
✓ Methods correctly described vs source code  
✓ Patient counts verified (19 for EXP-2946, 11+ for others)  
✓ Arithmetic validated (sums, ratios, percentages)  
✓ Cross-references verified (EXP-2918, 2929, 2937, 2940, 2944, 2946, 2947)  
✓ Effect sizes and p-values reasonable  
✓ No fabricated data  
✓ No missing patients without disclosure  
✓ No undisclosed methodological changes  

---

**Reviewed by**: Copilot CLI autoreview-correct skill  
**Date completed**: 2026-04-23  
**Time spent**: ~45 minutes (general-purpose agent verification × 4 reports)
