# Verification Report: Expanded Cohort Validation Report (2026-04-18)

**Report Under Review**: `docs/60-research/expanded-cohort-validation-report-2026-04-18.md`

**Verification Date**: 2026-04-18

**Verification Method**: Cross-reference report claims against JSON source files in `externals/experiments/`

**Confidence Level**: **HIGH** — Numerical checks directly against JSON data structures

---

## Executive Summary

**Status**: ⚠️ **CRITICAL ERRORS FOUND** — 7 high-confidence discrepancies

| Category | Count | Status |
|----------|-------|--------|
| Fabricated cohorts | 2 | ❌ CRITICAL |
| Incorrect numerical claims | 2 | ⚠️ HIGH |
| Table fabrication | 1 | ❌ CRITICAL |
| Data inconsistencies | 2 | ⚠️ MEDIUM/HIGH |
| **Verified Correct** | **5 key findings** | ✓ PASS |

**Recommendation**: **REJECT for publication** pending remediation of fabricated DynISF cohorts and EXP-2640 table.

---

## Detailed Findings

### ❌ ERROR 1: EXP-2651 DynISF Cohort — FABRICATED DATA

**Report Location**: Lines 95–102, Section 2.3

**Report Claims**:
```
| H1: demand < apparent | PASS | 100% (12/12) |
| H2: demand wins 2h    | PASS | 100% (12/12) |
| H3: apparent wins 4h  | FAIL | 8% (1/12)    |
| H4: inflation ratio   | PASS | 1.41–3.76×   |
```

**JSON Verification** (`exp-2651_two_phase_isf_dynisf.json`):

```python
n_patients_analyzed: 25  # NOT 12
parquet_source: externals/ns-parquet/training/grid.parquet  # NOT DynISF
```

**Findings**:
- JSON file contains **identical data to Original** (25 patients, same results)
- All hypothesis metrics match Original exactly (H1 100%, H2 92%, H3 16%, H4 1.30–5.26×)
- No subset to 12 patients or alternate inflation ratios exist in the file

**Severity**: ❌ **CRITICAL** — Entire DynISF subsection is fabricated

**Evidence**:
```
Original H4 inflation ratio: min=1.30, max=5.26
DynISF (report): min=1.41, max=3.76
DynISF (JSON): min=1.30, max=5.26 ← matches Original, not report
```

---

### ❌ ERROR 2: EXP-2652 DynISF Cohort — FABRICATED DATA

**Report Location**: Lines 139–145, Section 3.3

**Report Claims**:
```
| H1: ≥30% ISF variation | PASS | 70% (7/10)  |
| H2: ≥10% RMSE improvement | FAIL | 20% (2/10) |
| H3: dawn has lowest ISF | FAIL | Most common lowest block: 20–24h |
```

**JSON Verification** (`exp-2652_circadian_profiling_dynisf.json`):

```python
n_patients_analyzed: 18  # NOT 10
```

**Findings**:
- JSON file contains **identical data to Original** (18 patients, same H1/H2/H3 results)
- Report claims 10 patients (70% H1, 20% H2)
- Actual JSON data: 18 patients (77.8% H1, 5.6% H2)
- Block distribution matches Original exactly, not report claim

**Severity**: ❌ **CRITICAL** — Entire DynISF subsection is fabricated

**Comparison Table**:

| Metric | Report (Claimed 10) | JSON Actual (18) | Match |
|--------|------|------|-------|
| H1: ≥30% variation | 70% (7/10) | 77.8% (14/18) | ❌ NO |
| H2: ≥10% RMSE improvement | 20% (2/10) | 5.6% (1/18) | ❌ NO |
| H3: Lowest blocks | 20–24h dominant | 12–16h: 5, 16–20h: 4, 20–24h: 4 | ❌ NO |

---

### ⚠️ ERROR 3: EXP-2662 Original — H1 Mean Value Incorrect

**Report Location**: Line 239, Section 5.2

**Report Claim**:
```
H1: ≥30% delayed hypo reduction | FAIL | Mean 7% reduction (range 0–21%)
```

**JSON Verification** (`exp-2662_patience_mode.json`):

```python
Mean delayed hypo reduction: 11.2%  # NOT 7%
Range: 0–27%                         # NOT 0–21%
n_patients_fitted: 25
```

**Calculation Details**:

For each patient:
```
reduction_pct = 100 * (delayed_hypo_baseline - delayed_hypo_patience) / delayed_hypo_baseline
```

Results from 25 fitted patients:
- Mean: 11.2%
- Range: 0–27%
- Median: ~10%

**Discrepancy**: Report says 7%, actual is 11.2% — **60% error**

**Severity**: ⚠️ **HIGH** — Significant numerical understatement

---

### ⚠️ ERROR 4: EXP-2662 DynISF — H1 Mean Value Incorrect

**Report Location**: Line 248, Section 5.3

**Report Claim**:
```
H1: ≥30% delayed hypo reduction | FAIL | Mean 9% reduction
```

**JSON Verification** (`exp-2662_patience_mode_dynisf.json`):

```python
Mean delayed hypo reduction: 13.7%  # NOT 9%
Range: 5–26%
n_patients: 12
```

**Discrepancy**: Report says 9%, actual is 13.7% — **52% error**

**Severity**: ⚠️ **HIGH** — Significant numerical understatement

**Pattern**: Both Original and DynISF H1 values are understated by ~50%+. This suggests **systematic calculation error**, not random mistake.

---

### ❌ ERROR 5: EXP-2640 Per-Patient Table — FABRICATED PATIENT DATA

**Report Location**: Lines 288–297, Section 6.2

**Report Table Claim**:

```
| Patient | Best Model | Log r   | Linear r | n_events |
|---------|-----------|---------|----------|----------|
| a       | log       | −0.597  | −0.469   | 79       |
| c       | log       | −0.624  | −0.603   | 6        |
| e       | linear    | −0.297  | −0.385   | 10       |
| f       | log       | −0.819  | −0.652   | 91       |
| g       | log       | +0.721  | +0.671   | 6        | ← POSITIVE!
| i       | log       | −0.815  | −0.713   | 20       |

Total: 212 events from fitted
```

**JSON Verification** (`exp-2640_per_patient_isf.json`):

Fitted patients with valid correlations: `a`, `f`, `i`, `ns-8b3c1b50793c`, `odc-86025410`, `odc-96254963`

```
| Patient | JSON Status    | Log r  | Linear r | n_events |
|---------|---|---|---|---|
| a       | ✓ Fitted       | −0.581 | −0.446   | 48       |
| c       | ❌ Insufficient| (none) | (none)   | 1        |
| e       | ❌ Insufficient| (none) | (none)   | 2        |
| f       | ✓ Fitted       | −0.857 | −0.689   | 36       |
| g       | ❌ Insufficient| (none) | (none)   | 1        |
| i       | ✓ Fitted       | −0.831 | −0.697   | 6        |

Total fitted: 155 events
```

**Critical Discrepancies**:

1. **Patients c, e, g**: JSON marks as "insufficient" with no correlation values
   - Report table shows them as fitted with specific r values
   - These patients cannot have correlations if marked insufficient

2. **Patient g anomaly**: 
   - Report shows r = **+0.721 (POSITIVE)**
   - JSON shows: no data (insufficient)
   - Report text (line 301) acknowledges "N=7 (likely insufficient data)"
   - But report table uses this patient with specific values

3. **Event count mismatch**:
   - Report claims: 212 events from fitted
   - JSON actual (fitted a,f,i + 3 others): 155 events
   - Discrepancy: 37 events (23% error)

4. **Correlation value mismatches** (for fitted patients):
   - Patient a: report -0.597 vs actual -0.581 (close)
   - Patient f: report -0.819 vs actual -0.857 (significant)
   - Patient i: report -0.815 vs actual -0.831 (close)

**Severity**: ❌ **CRITICAL** — Table appears to be fabricated or from a different analysis run

**Evidence of fabrication**:
```json
{
  "c": {
    "n_events": 1,
    "insufficient": true,
    "data": {...}  // No model results
  },
  "e": {
    "n_events": 2,
    "insufficient": true,
    "data": {...}  // No model results
  },
  "g": {
    "n_events": 1,
    "insufficient": true,
    "data": {...}  // No model results
  }
}
```

These patients have no `log`, `linear`, or `sqrt` correlation fields, yet the report table lists specific values.

---

### ⚠️ ERROR 6: EXP-2640 Patient G Data Inconsistency

**Report Location**: Lines 296, 301, Section 6.2–6.3

**Report Claims**:
```
Line 296 (table):    Patient g: log r = +0.721, n_events = 6
Line 301 (text):     "Outlier: Patient g shows positive correlation (7 events only)"
```

**JSON Actual**:
```python
"g": {
  "n_events": 1,
  "insufficient": true,
  "data": [...]  # Only 1 event, marked insufficient
}
```

**Issues**:
1. Event count: Report says 6 or 7, JSON says 1
2. Correlation: Report claims +0.721 (positive), JSON has no correlation data
3. Contradiction: Report acknowledges patient g is insufficient but still uses in table
4. Sign error: Positive correlation is unusual for dose-dependent ISF

**Severity**: ⚠️ **MEDIUM/HIGH** — Data from different analysis or manually fabricated

---

### ⚠️ ERROR 7: Cohort Count & Accounting Inconsistency

**Report Location**: Lines 5–6, Executive Summary

**Report Claim**:
```
Patients: 43 unique (31 NS-parquet training + 12 DynISF-v2), up from 11 original
```

**JSON Actual**:

| Experiment | Original | DynISF | Total |
|-----------|----------|--------|-------|
| EXP-2651 | 25 fitted / 31 dataset | 25 (not 12) | 31+25 = 56 |
| EXP-2652 | 18 fitted | 18 (not 10) | 18+18 = 36 |
| EXP-2656 | 29 fitted | 12 fitted | 29+12 = 41 |
| EXP-2662 | 27 total | 12 total | 27+12 = 39 |
| EXP-2640 | 6+ fitted | N/A | 6+ |

**Accounting Problem**:
- Claim: 31 + 12 = 43
- Actual: EXP-2651 shows 31 + 25 (not 12)
- Actual: EXP-2652 shows 18 + 18 (not separate 18 + 10)
- Total unique: Unknown, but clearly not 43 as claimed

**Severity**: ⚠️ **HIGH** — Patient overlap accounting is unclear and contradicted by JSON data

---

## Experiments with Verified Correct Results ✓

The following experiments passed verification:

### ✓ EXP-2651 Original (25 patients)

| Metric | Report | JSON | Match |
|--------|--------|------|-------|
| H1: demand < apparent | 100% (25/25) | 25/25 | ✓ |
| H2: demand wins 2h | 92% (23/25) | 23/25 | ✓ |
| H3: apparent wins 4h | 16% (4/25) | 4/25 | ✓ |
| H4: inflation ratio | 1.30–5.26× | 1.30–5.26× | ✓ |

### ✓ EXP-2656 Original (29 patients)

| Metric | Report | JSON | Match |
|--------|--------|------|-------|
| H1: actual < linear | 100% (29/29) | 100% (29/29) | ✓ |
| H2: ceiling beats linear | 100% (29/29) | 100% (29/29) | ✓ |
| H3: ceiling range | 30–56% | 30–55.9% | ✓ |
| H4: correlation | r = −0.285, p = 0.134 | r = −0.285, p = 0.1345 | ✓ |

### ✓ EXP-2656 DynISF (12 patients)

| Metric | Report | JSON | Match |
|--------|--------|------|-------|
| H1: actual < linear | 100% (12/12) | 100% (12/12) | ✓ |
| H2: ceiling beats linear | 100% (12/12) | 100% (12/12) | ✓ |
| H3: ceiling range | 30–44% | 30–43.8% | ✓ |
| H4: correlation | r = −0.038 | r = −0.038 | ✓ |

### ✓ EXP-2652 Original (18 patients)

| Metric | Report | JSON | Match |
|--------|--------|------|-------|
| H1: ≥30% variation | 78% (14/18) | 77.8% (14/18) | ✓ |
| H2: ≥10% RMSE | 5.6% (1/18) | 5.6% (1/18) | ✓ |
| H3: Block distribution | Correct | Correct | ✓ |

### ⚠️ EXP-2662 H2/H3/H4 (Both cohorts)

Close match (±5%):
- H2 hyper increase: Report ±2.1pp / ±1.2pp, JSON ±2.12pp / ±1.16pp ✓
- H3 SMB savings: Report 34% / 42%, JSON 33.7% / 42.5% ✓
- H4 TIR delta: Report −0.2pp / −0.1pp, JSON −0.21pp / −0.12pp ✓

---

## Root Cause Analysis

### Pattern 1: DynISF JSON Files Are Duplicates

Both `exp-2651_two_phase_isf_dynisf.json` and `exp-2652_circadian_profiling_dynisf.json` contain identical data to their Original counterparts:

**Possible explanations**:
1. DynISF analysis was never actually performed
2. JSON files were not updated after report was written
3. Report was generated from intermediate results and JSON files are stale

### Pattern 2: EXP-2662 H1 Systematic Understatement

Both Original and DynISF H1 values are consistently low:

| Cohort | Report | Actual | Error |
|--------|--------|--------|-------|
| Original | 7% | 11.2% | −60% |
| DynISF | 9% | 13.7% | −52% |

Suggests:
- Different computation method (median vs mean? filtered subset?)
- Calculation error propagated to both sections
- Data from different run

### Pattern 3: EXP-2640 Table From Different Source

The table references patients (c, e, g) marked insufficient in JSON, with correlation values that cannot be computed from available data. Possible explanations:

1. Table is from an older analysis run with different JSON
2. Table was manually typed/transcribed from another source
3. Patient selection criteria changed between analysis and report writing

---

## Remediation Actions Required

### CRITICAL (Must fix before publication)

1. **Obtain correct EXP-2651 DynISF JSON**
   - Expected: 12 patients, separate from 25-patient Original cohort
   - Current file: Duplicate of Original (25 patients)
   - Action: Rerun experiment or locate correct data file

2. **Obtain correct EXP-2652 DynISF JSON**
   - Expected: 10 patients, separate from 18-patient Original cohort
   - Current file: Duplicate of Original (18 patients)
   - Action: Rerun experiment or locate correct data file

3. **Fix EXP-2640 Table**
   - Remove or clearly mark insufficient patients (c, e, g)
   - Verify correlations for fitted patients match JSON
   - Correct event counts: 212 → 155 (or justify discrepancy)
   - Address patient g data (1 vs 7 events, correlation sign)

### HIGH (Should fix)

4. **Recalculate EXP-2662 H1 means**
   - Original: 7% → 11.2%
   - DynISF: 9% → 13.7%
   - Document calculation method to prevent regression

5. **Clarify cohort accounting**
   - Reconcile "43 unique" claim with actual JSON patient counts
   - Define unique patient set across all experiments
   - Document any overlap between cohorts

### MEDIUM (Document clearly)

6. **Clarify patient identifiers**
   - Report uses single-letter IDs (a, c, e, etc.)
   - JSON also has namespaced IDs (ns-*, odc-*)
   - Provide mapping or explain selection criteria

---

## Verification Summary Table

| Error | Experiment | Type | Severity | Status |
|-------|-----------|------|----------|--------|
| 1 | EXP-2651 DynISF | Fabricated cohort | ❌ CRITICAL | Requires rerun |
| 2 | EXP-2652 DynISF | Fabricated cohort | ❌ CRITICAL | Requires rerun |
| 3 | EXP-2662 Original H1 | Incorrect value | ⚠️ HIGH | 7% → 11.2% |
| 4 | EXP-2662 DynISF H1 | Incorrect value | ⚠️ HIGH | 9% → 13.7% |
| 5 | EXP-2640 Table | Fabricated table | ❌ CRITICAL | Requires revision |
| 6 | EXP-2640 Patient g | Data inconsistency | ⚠️ MEDIUM | Clarify source |
| 7 | Overall | Cohort accounting | ⚠️ HIGH | Reconcile totals |

---

## Conclusion

**Overall Assessment**: **REJECT for publication pending remediation**

**Justification**:
- Two critical DynISF cohort sections are fabricated (identical to Original in JSON)
- EXP-2640 per-patient table doesn't match JSON data and includes insufficient patients
- EXP-2662 H1 values significantly understated
- Cohort size claims unsupported by JSON data

**Strengths**:
- EXP-2651 Original, EXP-2652 Original, and both EXP-2656 cohorts are verified
- Core physiological findings (ceiling model, two-phase ISF) are supported
- Methodology is sound (main issue is data/execution)

**Path Forward**:
1. Rerun DynISF analyses or provide correct JSON files
2. Correct numerical errors in EXP-2662 and EXP-2640
3. Resubmit for verification
4. Consider pre-commit JSON validation to prevent similar issues

---

## Verification Metadata

| Item | Value |
|------|-------|
| Report File | `docs/60-research/expanded-cohort-validation-report-2026-04-18.md` |
| Verification Date | 2026-04-18 |
| JSON Files Checked | 9 experiment files |
| Verification Tools | Python 3.12 + scipy.stats |
| Reviewer | Automated verification agent |
| Confidence Level | HIGH (JSON structure matches are definitive) |

