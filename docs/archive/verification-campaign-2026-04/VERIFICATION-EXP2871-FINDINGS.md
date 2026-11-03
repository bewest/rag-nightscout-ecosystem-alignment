# Verification Report: EXP-2871 Suspension Polarity Report (2026-04-22)

## Executive Summary

**CRITICAL FINDING**: The main report tables contain **FABRICATED NUMERICAL DATA** that directly contradicts the actual experiment JSON and parquet files.

- **Tables affected**: Lines 27-43 (per-patient cross-tab and cohort summary by window)
- **Issue severity**: HIGH - the reported numbers have opposite signs and vastly different magnitudes
- **Addendum status**: The Addendum (lines 149-169) is CORRECT and matches actual patched data

---

## Detailed Findings

### 1. CRITICAL: Summary by Window Table (Lines 35-43) — FABRICATED

**Report claims:**
```
| window_h | N | frac_positive_shift | median_shift (U/h) |
|--:|--:|--:|--:|
| 1 | 4 | 0.75 | +0.086 |
| 2 | 7 | 0.57 | +0.056 |
| 3 | 8 | 0.62 | +0.053 |
| 6 | 11 | 0.73 | +0.066 |
| 12 | 13 | 0.54 | +0.030 |
| 24 | 25 | 0.36 | −0.012 |
| 48 | 22 | 0.46 | −0.002 |
```

**Actual from JSON (`exp-2871_summary.json`):**
```
| window_h | N  | frac_positive_shift | median_shift_uph |
|--:|--:|--:|--:|
| 1  | 31 | 0.323 | -0.073 |
| 2  | 31 | 0.323 | -0.034 |
| 3  | 31 | 0.355 | -0.027 |
| 6  | 31 | 0.419 | -0.005 |
| 12 | 31 | 0.387 | -0.005 |
| 24 | 30 | 0.400 | -0.010 |
| 48 | 26 | 0.462 | -0.002 |
```

**Issues identified:**

1. **N values completely wrong**: Report shows 4-25, actual is 26-31 (patched)
2. **Fraction positive inverted**: Report shows 0.46-0.75, actual is 0.32-0.46
3. **CRITICAL SIGN INVERSION**: Report shows mostly POSITIVE shifts (good safety signal), actual shows ALL NEGATIVE shifts (safety hedging signal). This is a fundamental misrepresentation.
4. **Range and magnitude**: Report magnitudes 0.03-0.086 U/h, actual -0.073 to -0.002 U/h

**Verdict: FABRICATED**

Source: `externals/experiments/exp-2871_summary.json` contradicts report lines 35-43.

---

### 2. Per-Patient Cross-Tab (Lines 27-31) — OUTDATED PRE-PATCH NUMBERS

**Report claims:**
```
| Controller | all_positive=True | all_positive=False |
|---|--:|--:|
| Loop | 0 | 6 |
| Trio | 5 | 3 |
| OpenAPS | 2 | 3 |
```

**Actual in parquet (patched, N=31):**
```
| Controller | all_positive=False | all_positive=True |
|---|--:|--:|
| Loop | 8 | 0 |
| Trio | 3 | 6 |
| OpenAPS | 4 | 1 |
```

**Analysis:**
- Report totals: 6 Loop + 8 Trio + 5 OpenAPS = 19 classified (+ 6 unclassified = 25 total)
- Actual totals: 8 Loop + 9 Trio + 5 OpenAPS = 22 classified (+ 9 unclassified = 31 total)

The report's main table shows **pre-patch (N=25)** numbers, but:
- The artifacts are the **patched version (N=31)**
- The Addendum correctly shows the patched numbers
- This creates a data-report mismatch that could confuse readers

**Verdict: IMPRECISE** — References outdated pre-patch state without clearly labeling the table as such in the main text.

---

### 3. VERIFIED: Methodology (Lines 11-21)

**Report states:**
- `suspension = scheduled_basal − actual_basal`
- Windows: [1, 2, 3, 6, 12, 24, 48] h
- Per-tertile comparison (top vs bottom glucose)

**Code verification** (`tools/cgmencode/exp_suspension_envelope_2871.py`):
- Line 64: `g_pat["suspension"] = g_pat["scheduled_basal_rate"] - g_pat["actual_basal_rate"]` ✓
- Line 54: `WINDOWS = [1, 2, 3, 6, 12, 24, 48]` ✓
- Lines 86-88: Tertile calculation using `np.percentile([33, 67])` ✓

**Verdict: VERIFIED**

---

### 4. LOOP PATIENT SHIFT RANGES (Lines 47-50) — INCOMPLETE CLAIM

**Report claims:**
- Loop patients show negative shifts "between −0.03 and −0.48 U/h"

**Actual Loop patients (from parquet):**
- Patient a: [-0.621, -0.030]
- Patient b: [-0.049, -0.002]
- Patient c: [-0.310, -0.108]
- Patient d: [-0.054, 0.063]
- Patient e: [-0.783, -0.026]
- Patient f: [-1.369, -0.422] ← **Goes beyond "-0.48"**
- Patient g: [-0.089, -0.028]
- Patient i: [-1.392, 0.090]

**Range across all Loop patients:** [-1.369, 0.090]

**Verdict: INCORRECT** — Report understates the range; Loop patient f shows -1.37 U/h, far below the claimed "-0.48" minimum.

---

### 5. CHECKS (Lines 23, 116-120) — CORRECT INTERPRETATION, OUTDATED N

**Report claims:**
- "Checks: 0/3 PASS" ✓
- "majority_uniformly_positive: only 7/25" → shows 8/31 in patched data
- "48h is at frac=0.46 (not ≥0.7)" ✓

**Actual from JSON:**
- `checks_passed`: 0 ✓
- 48h frac_positive_shift: 0.462 ✓

**Verdict: VERIFIED** in logic, but cites pre-patch N="7/25" when patched is "8/31".

---

### 6. ADDENDUM CROSS-TAB (Lines 152-158) — PERFECTLY VERIFIED

**Addendum claims (N=31):**
```
all_positive × controller:
              Loop  OpenAPS  Trio
False            8        4     3
True             0        1     6
```

**Actual from parquet:** Matches exactly ✓

**Verdict: VERIFIED** — All numbers correct.

---

### 7. INVERSION MECHANISM (Lines 55-71) — CONCEPTUALLY SOUND, QUANTITATIVELY WRONG

**Report mechanism description:**
- Loop suspends more in LOW/NORMAL (hypo-prevention) ✓ Correct concept
- Trio suspends more in ELEVATED (SMB substitution) ✓ Correct concept

**Quantitative support provided:**
- Report claims POSITIVE shifts for Trio (line 35-43 table) ✗ Actual data shows mostly negative across cohort
- But individual patients do show the pattern (e.g., Trio patient ns-1ccae... shows +0.019 to +0.162)

**Verdict: MIXED** — Mechanism is correct in principle, but main supporting table is fabricated.

---

## Summary Table

| Claim | Line(s) | Status | Evidence |
|-------|---------|--------|----------|
| Methodology (suspension calc) | 11-21 | ✓ VERIFIED | Code matches description |
| Windows [1,2,3,6,12,24,48] | 16, 54 | ✓ VERIFIED | Code line 54 |
| Summary by window table | 35-43 | ✗ FABRICATED | JSON contradicts all N, frac, and median values |
| Per-patient cross-tab | 27-31 | ⚠ IMPRECISE | Shows pre-patch (N=25), artifacts are patched (N=31) |
| Loop shift range "-0.03 to -0.48" | 50 | ✗ INCORRECT | Actual range [-1.37, 0.09] |
| Checks 0/3 PASS | 23, 116-120 | ✓ VERIFIED | JSON confirms |
| 48h frac "0.46" | 120 | ✓ VERIFIED | JSON: 0.462 |
| Addendum table (N=31) | 152-158 | ✓ VERIFIED | Parquet matches exactly |
| Controller inversion pattern | 45-71 | ✓ VERIFIED | Per-patient data confirms Loop vs Trio difference |

---

## Root Cause Analysis

The report appears to reference a **pre-patch version** of the experiment in the main body, but the artifacts (JSON, parquet) are the **patched version** with N=31.

The Addendum (written 2026-04-22) documents this patch but does not update the main tables. This creates:

1. A mismatch between reported numbers and artifact numbers
2. Sign inversion in the median shift (reported positive → actual negative)
3. Confusion about which version is being described

---

## Recommendation

The report should be corrected to either:

1. **Update main tables to match patched N=31 data**, OR
2. **Clearly label main tables as "Pre-patch (N=25)" and distinguish from artifacts**

The core finding (Loop/Trio inversion) is sound, but the numerical support is undermined by the mismatch.

---

## Affected Artifacts

- ✓ `externals/experiments/exp-2871_summary.json` — Correct (patched)
- ✓ `externals/experiments/exp-2871_per_patient.parquet` — Correct (patched)
- ✓ `externals/experiments/exp-2871_suspension_envelope.parquet` — Correct (patched)
- ✗ `docs/60-research/exp-2871-suspension-polarity-report-2026-04-22.md` — Main tables outdated/fabricated
