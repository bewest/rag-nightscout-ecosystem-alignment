# Verification Report: EXP-2916 Design-Gap Analysis

**Report:** `docs/60-research/exp-2916-design-gap-2026-04-23.md`
**Data Source:** `externals/experiments/exp-2916_summary.json`
**Verification Date:** 2026-04-24
**Status:** ✗ ISSUES FOUND

## Executive Summary

The headline table (lines 42-46) is **CORRECT**. However, **two numerical errors** appear in the text:
1. Line 106 and Table lines 54-58: Loop-conservative gap overstated as **0.18** (actual: **0.149**)
2. Line 94: Claim that oref1 forms "design ceiling at every tercile" is **contradicted by data** (Loop > oref1 at moderate tercile)

---

## Verified Claims

### ✓ Headline Table (Lines 42-46)

| Design | Claim n | Actual n | Match | Claim cells below | Actual | Match | Claim mean gap | Actual | Match |
|--------|---------|----------|-------|-------------------|--------|-------|-----------------|--------|-------|
| oref0  | 3       | 3        | ✓     | 2                 | 2      | ✓     | +0.194          | +0.194 | ✓     |
| Loop   | 7       | 7        | ✓     | 5                 | 5      | ✓     | +0.091          | +0.091 | ✓     |
| oref1  | 9       | 9        | ✓     | 1                 | 1      | ✓     | -0.041          | -0.041 | ✓     |

**All headline values match JSON exactly.**

### ✓ N-value Summation
- oref0: 3 + Loop: 7 + oref1: 9 = 19 ✓
- Matches `n_patients: 19` in JSON

### ✓ Largest Gap #1 (oref0 conservative vs oref1 conservative)
- Claimed: +0.51 ✓
- Actual: 0.5092 ✓
- Within rounding tolerance

---

## ERROR #1: Loop-Conservative Gap Overstated

**Location:** Line 106 & Table lines 54-58

**Claim:**
```
"Loop-conservative sits ~0.18 below oref1-conservative" (line 106)
"Loop conservative | oref1 conservative | +0.18" (table, line 58)
```

**Actual values from JSON:**
```
oref1 conservative protection: 0.6347
Loop conservative protection:  0.4856
Difference:                    0.1491
```

**Issue:** 
- Reported: **0.18**
- Actual: **0.1491**
- Discrepancy: **+0.0309** (21% overestimate)

**Rounding check:** Even generous rounding (0.15 → 0.2) does not justify 0.18.

**JSON verification:**
```json
"tercile": "conservative",
"design_a": "Loop (iOS)",
"design_b": "oref1 (modern)",
"protection_a": 0.48561061061061067,
"protection_b": 0.6346688034188034,
"abs_gap": 0.1490581928081927
```

---

## ERROR #2: Ceiling Claim Contradicted by Data

**Location:** Lines 94 & 110

**Claim:**
```
"After excluding the artifact cell, the design-comparison surface 
collapses to: oref1 forms the design ceiling at every tercile." (line 94)

"oref1 sets the ceiling at all three terciles in this cohort." (line 110)
```

**Actual cell means by tercile (from JSON `cell_means`):**

| Tercile      | Loop    | oref0   | oref1   | Ceiling? |
|--------------|---------|---------|---------|----------|
| conservative | 0.4856  | 0.1255  | **0.6347** | ✓ oref1  |
| **moderate** | **0.6370** | 0.3895  | 0.6151  | **✗ Loop** |
| aggressive   | 0.5825  | 0.7193  | 0.7185  | ✓ (oref0 minimal, report flags as outlier) |

**Issue:**
- Report states oref1 is ceiling "at every tercile"
- **Moderate tercile has Loop = 0.6370 > oref1 = 0.6151**
- Report only acknowledges oref0-aggressive as problematic
- **Does not acknowledge Loop > oref1 at moderate tercile**

**JSON verification:**
```json
{"lineage": "Loop (iOS)", "tercile": "moderate", "cell_mean_protection": 0.6370091896407686},
{"lineage": "oref1 (modern)", "tercile": "moderate", "cell_mean_protection": 0.6150937081659973}
```

---

## Verification of Cross-References

### ✓ EXP-2904 Cell Means
- Report correctly states it uses "Guard-#6-verified EXP-2904 cell means"
- JSON contains identical cell means: confirmed present in `cell_means` array
- All three designs (oref0, Loop, oref1) at all three terciles (conservative, moderate, aggressive) present

### ✓ Associated Experiments
- EXP-2892, EXP-2893, EXP-2894, EXP-2905: referenced appropriately
- File links exist at lines 145-157

---

## Assessment of Fabrication Patterns

**No evidence of systematic fabrication detected:**

✓ Headline table is exact match to JSON (high precision indicates direct data pull)  
✓ Large gaps (0.51) correctly reported  
✓ Pattern matches documented (headline ranking oref1>Loop>oref0)  
✓ N values and summation correct  
✓ Caveats appropriately flagged (n=1 oref0 cells, SMB outlier)  

**Nature of errors:**
- ERROR #1 is a **rounding mistake**: 0.1491 → claimed 0.18 (upward bias)
- ERROR #2 is an **incomplete analysis**: Report correctly excludes oref0-aggressive outlier but fails to mention Loop outperforms oref1 at moderate tercile

Both errors suggest **careless claim generalization** rather than data fabrication.

---

## Summary

| Item | Status | Notes |
|------|--------|-------|
| Headline table (n, cells below, mean gaps) | ✓ VERIFIED | All values match JSON exactly |
| N summation | ✓ VERIFIED | 3+7+9=19 |
| Largest gap #1 (oref0 cons vs oref1 cons) | ✓ VERIFIED | 0.51 |
| Largest gap #2 (oref0 mod vs Loop) | ✓ VERIFIED | 0.25 |
| Largest gap #3 (Loop cons vs oref1 cons) | ✗ ERROR | Claimed 0.18, actual 0.1491 |
| "oref1 ceiling at every tercile" claim | ✗ ERROR | Loop > oref1 at moderate tercile |
| EXP-2904 cross-reference | ✓ VERIFIED | Cell means present and correct |
| Caveat flags (n=1 oref0, SMB outlier) | ✓ VERIFIED | Appropriately documented |

---

**VERDICT:** PARTIALLY VERIFIED WITH CORRECTIONS REQUIRED

- **Rounding error:** Line 106 & table line 58: change 0.18 → 0.15 (actual: 0.149)
- **Logical error:** Line 94 & 110: soften "ceiling at every tercile" to acknowledge Loop > oref1 at moderate tier

**Confidence:** HIGH — all discrepancies traced to specific JSON fields with clear numerical evidence.
