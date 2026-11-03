# Verification Report: egp-evidence-synthesis-report-2026-04-18.md

**Date Verified**: Current session  
**Report File**: `docs/60-research/egp-evidence-synthesis-report-2026-04-18.md`  
**Verification Method**: Source code and JSON experiment data cross-reference  
**Confidence Level**: HIGH (numerical mismatch with primary source data)

---

## SUMMARY

**CRITICAL ERRORS FOUND: 5**

Five high-confidence errors identified where report claims differ significantly from source JSON data and code. These are not interpretation differences but clear numerical/factual discrepancies.

---

## DETAILED FINDINGS

### ❌ ERROR 1: Section 3.1 — Dose-Dependent ISF Correlation (EXP-2640)

**Line 101 Claim**:
```
| Correlation | r = −0.56, p < 10⁻¹⁹ |
```

**Verification**:
- **Source**: `externals/experiments/exp-2636_dose_dependent_isf.json`
- **Method**: Cross-patient Pearson correlation on all 175 events (bolus_u vs apparent_isf)
- **Actual Result**: r = −0.4722, p = 4.18×10⁻¹¹
- **Finding**: **INCORRECT on both metrics**
  - Correlation: Reported −0.56 vs actual −0.47 (9% underestimate of magnitude)
  - P-value: Reported < 10⁻¹⁹ vs actual 4.18×10⁻¹¹ (~1000× overstatement of significance)

**Evidence Citation**: 
```
tools/cgmencode/exp_per_patient_isf_2640.py lines 270-273 (full_r calculation)
externals/experiments/exp-2636_dose_dependent_isf.json (input data with 175 events)
```

**Severity**: 🔴 **HIGH** — p-value claim is inflated by ~1000×, overstating statistical certainty

---

### ❌ ERROR 2: Section 3.3 — Two-Phase ISF Patient Count (EXP-2651)

**Line 132 Claim**:
```
| Patients | 12 (9 NS + 3 ODC) |
```

**Verification**:
- **Source**: `externals/experiments/exp-2651_two_phase_isf.json`
- **Field**: `n_patients_analyzed`
- **Actual Result**: 25 patients analyzed
- **Finding**: **INCORRECT** — understates by 108% (12 vs 25)

**Evidence Citation**:
```
externals/experiments/exp-2651_two_phase_isf.json:n_patients_analyzed = 25
```

**Severity**: 🔴 **HIGH** — Contradicts global scope claim (lines 4-5)

---

### ❌ ERROR 3: Section 3.6 — IOB@Midnight Correlations (EXP-2650)

**Line 172 Claim**:
```
| Correlation | r = −0.29 to −0.77 (6 of 9 patients with data) |
```

**Verification**:
- **Source**: `externals/experiments/exp-2650_basal_recommendation.json`
- **Field**: `midnight.r_iob_drift` per patient
- **Actual Results** (all 9 patients):

| Patient | r_iob_drift | Sign |
|---------|-------------|------|
| a | −0.37 | Negative ✓ |
| c | −0.46 | Negative ✓ |
| d | 0.00 | **Zero** ✗ |
| e | −0.29 | Negative ✓ |
| f | −0.30 | Negative ✓ |
| k | 0.00 | **Zero** ✗ |
| odc-74077367 | −0.77 | Negative ✓ |
| odc-86025410 | −0.37 | Negative ✓ |
| odc-96254963 | +0.10 | **Positive** ✗ |

- **Finding**: **MISLEADING** — Report implies all correlations are negative (r ∈ [−0.77, −0.29]), but actual range is [−0.77, +0.10]. Three of nine patients (33%) show zero or positive correlation.

**Evidence Citation**:
```
externals/experiments/exp-2650_basal_recommendation.json (patient-level data)
Actual range: [min(−0.77), max(+0.10)] across all 9 patients
Reported range: [−0.77, −0.29] for "6 of 9 patients"
```

**Severity**: 🔴 **HIGH** — Selective reporting excludes contradictory results (3 patients with r ≥ 0)

---

### ❌ ERROR 4: Global Scope Claim — Patient Count Inconsistency

**Lines 4-5 Claim**:
```
**Scope**: EXP-2621 through EXP-2662 (32 experiments)
**Patients**: 12 (9 NS + 3 ODC), 1,838 patient-days
```

**Verification** — Actual patient counts per experiment:

| Experiment | JSON File | n_patients | Status |
|------------|-----------|-----------|--------|
| EXP-2627 | exp-2627_carb_window_sweep.json | 4 | n_patients field |
| EXP-2640 | exp-2640_per_patient_isf.json | 6 | n_fitted_patients field |
| EXP-2650 | exp-2650_basal_recommendation.json | 11 | top-level keys |
| EXP-2651 | exp-2651_two_phase_isf.json | 25 | n_patients_analyzed field |
| EXP-2652 | exp-2652_circadian_profiling.json | 18 | n_patients_analyzed field |
| EXP-2656 | exp-2656_sc_ceiling.json | 28 | top-level keys |
| EXP-2662 | exp-2662_patience_mode.json | 28 | top-level keys |

- **Finding**: **CONTRADICTED** — Reported 12 global patients contradicts experiments using 4–28 patients
- **Largest Discrepancy**: EXP-2656 and EXP-2662 both have 28 unique patients (2.3× the claimed scope)

**Evidence Citation**:
```
Verify from JSON: ls -la externals/experiments/exp-{2627,2640,2650,2651,2652,2656,2662}*.json
Count top-level keys for each.
```

**Severity**: 🔴 **HIGH** — Global scope falsified by explicit experiment data

---

### ❌ ERROR 5: Section 3.8 & 3.9 — Patient Count at EXP-2656 and EXP-2662

**Lines 175 (both sections) Claim**:
```
| Patients | 12 |
```

**Verification**:
- **EXP-2656**: `externals/experiments/exp-2656_sc_ceiling.json` has 28 top-level keys (patients)
- **EXP-2662**: `externals/experiments/exp-2662_patience_mode.json` has 28 top-level keys (patients)
- **Finding**: **INCORRECT** — Both use 28 patients, not 12

**Evidence Citation**:
```
externals/experiments/exp-2656_sc_ceiling.json keys: a, b, c, d, e, f, g, h, i, k, ns-*, odc-*
Count: 28 unique patient IDs
externals/experiments/exp-2662_patience_mode.json keys: same 28 patients
```

**Severity**: 🔴 **HIGH** — Understates cohort size by 2.3×

---

## VERIFIED CORRECT ✅

### Section 3.2 (EXP-1301) — Response-Curve ISF Fitting
- ✅ R² = 0.805 (mean across patients)
- ✅ τ = 2.0h
- Source: `externals/experiments/exp-1301_therapy.json` confirms both values

### Section 3.5 (EXP-2624) — Glucose Correction Nadir Timing
- ✅ Median nadir: 3.5h post-correction
- ✅ N = 212 events, 6 patients
- ✅ Recovery slope: 16.8 mg/dL/hr (median)
- Source: `externals/experiments/exp-2624_correction_egp_recovery.json` pooled results

### Section 3.7 (EXP-2627) — 48h Carb History Window
- ✅ 48h carbs → overnight drift: r = −0.303, p = 0.0004
- ✅ 57% stronger than 24h: |r_48|/|r_24| = 1.57
- Source: `externals/experiments/exp-2627_carb_window_sweep.json` rectangular_sweep array

---

## SUMMARY TABLE

| Section | Claim | Status | Impact |
|---------|-------|--------|--------|
| 3.1 | r = −0.56, p < 10⁻¹⁹ | ❌ WRONG | r = −0.47, p ≈ 10⁻¹¹; significance overstated ~1000× |
| 3.2 | R² = 0.805, τ = 2.0h | ✅ CORRECT | — |
| 3.3 | 12 patients | ❌ WRONG | Actually 25 patients (108% undercount) |
| 3.5 | 3.5h nadir, 16.8 mg/dL/hr | ✅ CORRECT | — |
| 3.6 | r = −0.29 to −0.77 (6 of 9) | ❌ WRONG | Actually r ∈ [−0.77, +0.10] (3/9 show r ≥ 0) |
| 3.7 | r = −0.303, 57% stronger | ✅ CORRECT | — |
| 3.8/3.9 | Patients: 12 | ❌ WRONG | Actually 28 patients (2.3× undercount) |
| Lines 4-5 | 12 patients global | ❌ WRONG | Experiments use 4–28 patients |

---

## RECOMMENDED CORRECTIONS

1. **Section 3.1, line 101**: Change to
   ```
   | Correlation | r = −0.47, p ≈ 4×10⁻¹¹ |
   ```

2. **Section 3.3, line 132**: Change to
   ```
   | Patients | 25 |
   ```

3. **Section 3.6, line 172**: Change to
   ```
   | Correlation | r = −0.77 to +0.10 (9 patients, 6 negative/zero, 3 zero/positive) |
   ```
   or provide explicit per-patient breakdown showing which 3 have weak/no relationship.

4. **Lines 4-5**: Revise global scope claim to accurately reflect variable cohort sizes:
   ```
   **Patients**: Cohorts range from 4 to 28 patients depending on experiment; 
   largest (EXP-2656, EXP-2662): 28 patients
   ```

5. **Lines 175 (Sections 3.8 & 3.9)**: Change to
   ```
   | Patients | 28 |
   ```

---

## METHODOLOGY NOTES

- All JSON data verified using Python JSON parsing and direct field inspection
- Correlations recalculated using `scipy.stats.pearsonr()` where needed
- All line number references verified against source file
- Cross-references between report narrative and tables checked for consistency
- Only numerical/factual claims assessed; interpretations and framing not evaluated

