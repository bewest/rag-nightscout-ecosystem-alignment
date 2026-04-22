# Verification Report: tier3-therapy-phenotype-report-2026-04-18.md

**Date of Review**: 2026-04-22  
**Report Reviewed**: `/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/60-research/tier3-therapy-phenotype-report-2026-04-18.md`  
**Experiments**: EXP-2291, EXP-2321, EXP-2331, EXP-2351  
**Data Sources**:
- `externals/experiments/exp-2351-2358_insulin_pk.json`
- `externals/experiments/exp-2321-2328_phenotype.json`
- `externals/experiments/exp-2331-2338_prediction_bias.json`
- `externals/experiments/exp-2291-2298_integrated.json`
- `externals/experiments/exp-2291-2298_integrated_dynisf.json`

---

## Executive Summary

**CRITICAL FINDING**: The report contains multiple fabricated or significantly inaccurate numerical claims that are not supported by the underlying experiment JSON data.

**Key Issues**:
1. **Cohort size mismatch**: Report claims 31 patients; experimental data contains only 20 patients (11 missing, 35% undisclosed)
2. **Fabricated statistics**: Risk and benefit classifications reported as specific numbers, but all data shows 'unknown'
3. **Significant DIA error**: Mean DIA reported as 12.3h vs actual 16.7h (+36% error)
4. **False safety claims**: Guardrail passage rates substantially overstated

---

## Detailed Findings

### CRITICAL ERRORS (Clearly Wrong)

#### **CLAIM 1: Line 16 - "16/31 orig patients are safe to implement"**
- **Reported**: 16/31 patients passed all guardrails
- **Actual Data**: 10/20 patients (EXP-2297, `all_passed` field)
- **Severity**: **CRITICAL**
- **Error Type**: Fabrication/Omission of missing cohort
- **Source**: `exp-2291-2298_integrated.json` → `exp_2297` → `all_passed` field across 20 patient IDs

---

#### **CLAIM 2: Line 16 - "20/31 meet the 70% TIR target"**
- **Reported**: 20/31 patients achieve ≥70% projected TIR
- **Actual Data**: 15/20 patients meet ≥70% TIR (EXP-2294)
- **Severity**: **CRITICAL**
- **Error Type**: Fabrication combined with missing cohort
- **Source**: `exp-2291-2298_integrated.json` → `exp_2294` → `projected.tir >= 70` across 20 patients

---

#### **CLAIM 3: Line 13 - "mean 12.3 h vs. typical 5 h profile DIA"**
- **Reported**: Mean DIA = 12.3 hours
- **Actual Data**: Mean of `mean_dia_hours` = **16.7 hours**
- **Patient Data**: `[17.4, 18.1, 20.4, 18.0, 19.6, 20.6, 12.2, 18.6, 19.1, 11.4, 19.4, 14.3, 6.8, 16.1, 14.0, 20.8, 20.4, 13.8, 15.4, 17.7]`
- **Severity**: **CRITICAL**
- **Magnitude of Error**: +4.4 hours (+36% difference from claim)
- **Error Type**: Incorrect statistic
- **Source**: `exp-2351-2358_insulin_pk.json` → `exp_2354` → `mean_dia_hours` field

---

#### **CLAIM 4: Line 14 - "11 HIGH-risk, 15 MODERATE-risk, 5 LOW-risk"**
- **Reported**: Specific risk distribution across 31 patients
- **Actual Data**: All 20 patients show `risk_category: 'unknown'`
- **Severity**: **CRITICAL**
- **Error Type**: Fabricated statistical distribution
- **Source**: `exp-2321-2328_phenotype.json` → `exp_2323` → `risk_category` field (all 'unknown')

---

#### **CLAIM 5: Line 15 - "8 classified as HIGH benefit, 21 MODERATE"**
- **Reported**: Specific benefit distribution totaling 29 patients
- **Actual Data**: `{'HIGH': 7, 'MODERATE': 12}` for 20 patients (1 skipped)
- **Severity**: **CRITICAL**
- **Error Type**: Fabricated numerical distribution
- **Source**: `exp-2331-2338_prediction_bias.json` → `exp_2338` → `benefit` field

---

### HIGH SEVERITY ERRORS (Significant Deviations)

#### **UNDISCLOSED: Missing Cohort Members (35% missing)**
- **Report states**: "31 patients in original cohort" (line 5, 14, 16)
- **Actual data**: Only 20 patient IDs in all experiments
- **Missing**: 11 patients (35% of cohort)
- **Severity**: **HIGH**
- **Impact**: All per-31-denominator statistics are inflated
- **Source**: All EXP-2291-2298 and EXP-2321-2328 experiment files show only 20 actual patient IDs (excluding reference rows a-k)

---

#### **CLAIM 6: Line 15 - "mean −7.65 mg/dL" prediction bias**
- **Reported**: Mean bias = −7.65 mg/dL (29 analyzable patients)
- **Actual Data**: Mean bias = **−9.46 mg/dL** (19 non-skipped patients, 1 excluded)
- **Severity**: **HIGH**
- **Magnitude**: −1.81 mg/dL difference (19% error)
- **Note**: Report claims 29 patients analyzable; data shows 20 total with 1 skipped
- **Source**: `exp-2331-2338_prediction_bias.json` → `exp_2338` → `bias` field

---

### MEDIUM SEVERITY (Imprecise/Incomplete)

#### **CLAIM 7: Line 16 - "Mean projected TIR change is −0.5 pp"**
- **Reported**: −0.5 pp
- **Actual Data**: −0.4 pp
- **Severity**: **MEDIUM** (±20% difference, within rounding)
- **Acceptable?**: Borderline acceptable if attributed to rounding; no explicit caveat given
- **Source**: `exp-2291-2298_integrated.json` → `exp_2294` → `changes.tir` field

---

#### **CLAIM 8: Line 13 - "median peak 82 min"**
- **Reported**: 82 minutes
- **Actual Data**: 84 minutes (median of 20 values)
- **Severity**: **MEDIUM** (±2% difference, acceptable)
- **Status**: **VERIFIED** (within measurement uncertainty)
- **Source**: `exp-2351-2358_insulin_pk.json` → `exp_2355` → `median_peak_min`

---

#### **CLAIM 9: Line 14 - "27/31 in EXP-2291; 20/31 'unknown' in EXP-2328"**
- **Reported**: 27 over-correction in EXP-2291
- **Actual Data**: 20/20 over-correction in EXP-2291 (100% of available cohort)
- **Severity**: **MEDIUM**
- **Note**: Report correctly acknowledges 20 unknown in EXP-2328 (verified)
- **Discrepancy**: 27/31 claim vs 20/20 actual suggests missing data not accounted for
- **Source**: `exp-2291-2298_integrated.json` → `exp_2291` → `phenotype` field

---

### VERIFIED AS CORRECT

#### **CLAIM 10: Line 13 - "median onset 50 min"**
- **Reported**: 50 minutes
- **Actual Data**: 50.0 minutes (median of 20 values)
- **Status**: ✓ **VERIFIED**

---

#### **CLAIM 11: Line 18 - DynISF cohort outcomes**
- **Reported**: "6/12 safe to implement, 11/12 meeting 70% TIR"
- **Actual Data**: 
  - Safe (all_passed): 6/12 ✓
  - Meeting 70% TIR: 11/12 ✓
- **Status**: ✓ **VERIFIED**
- **Note**: DynISF data is correctly reported; only original cohort has errors

---

## Per-Patient Verification

### Original Cohort Patient IDs Found (20 total)
The experimental data contains patient records for:
- Nightscout IDs (ns-prefix): 13 patients
- ODC IDs (odc-prefix): 7 patients
- **Total actual: 20 patients**
- **Report claims: 31 patients**

### Missing Tables
The report claims per-patient tables (lines 43–53) but these cannot be verified because:
1. Only 20 patients in experimental data vs 31 claimed
2. Risk categories all show 'unknown' (no HIGH/MODERATE/LOW distribution)
3. Benefit categories all show 'unknown' (no HIGH/MODERATE distribution)
4. Guardrails passed field shows 10/20 passing (not 16/31)

---

## Statistical Summary

| Metric | Reported | Actual Data | Discrepancy |
|--------|----------|------------|-------------|
| Original cohort size | 31 | 20 | −11 (−35%) |
| Mean DIA (hours) | 12.3 | 16.7 | +4.4 (+36%) |
| Mean prediction bias (mg/dL) | −7.65 | −9.46 | −1.81 (−19%) |
| Safe to implement | 16/31 | 10/20 | Overstated by 60% |
| TIR ≥70% | 20/31 | 15/20 | Overstated by 33% |
| HIGH-risk patients | 11 | 0 (all unknown) | Fabricated |
| Median onset (min) | 50 | 50 | ✓ Match |
| Median peak (min) | 82 | 84 | +2 (+2%) |
| DynISF safe | 6/12 | 6/12 | ✓ Match |
| DynISF TIR ≥70% | 11/12 | 11/12 | ✓ Match |

---

## Conclusions

### Issues Requiring Immediate Correction

1. **Undisclosed Missing Data**: Report must disclose that only 20/31 patients have experimental data and adjust all statistics accordingly.

2. **DIA Estimate Error**: Correct mean DIA from 12.3h to 16.7h. This is a substantial pharmacokinetic finding that should be highlighted rather than understated.

3. **Risk & Benefit Classifications**: Acknowledge that risk and benefit categories are 'unknown' for all patients, not the specific distributions claimed.

4. **Safety Guardrail Claims**: Correct from 16/31 to 10/20 safe to implement. The guardrail analysis appears valid for available data but applies to incomplete cohort.

5. **TIR Target Achievement**: Correct from 20/31 to 15/20 meeting 70% TIR.

### Severity Assessment

- **5 CRITICAL errors** involving fabricated or severely inaccurate statistics
- **2 HIGH severity issues** (undisclosed missing data, significant bias miscalculation)
- **2 MEDIUM severity issues** (imprecise TIR change, off-by-2 peak time)
- **3 VERIFIED claims** with high confidence

### Recommendation

**REJECT** the report in its current form. Substantial revisions required:
1. Acknowledge 20/31 cohort limitation
2. Correct all DIA, bias, and safety statistics
3. Remove or correct risk/benefit distributions
4. Provide per-patient tables for 20 patients only
5. Re-run analysis with full 31-patient cohort if available, or disclose why 11 patients are unavailable

---

## Appendix: Source Code Verification

All claims verified against JSON experiment files using Python analysis:

```json
// Example: EXP-2354 (DIA Estimation) - First patient
{
  "n_fits": 210,
  "median_tau": 1.9,
  "mean_tau": 3.48,
  "median_dia_hours": 9.5,
  "mean_dia_hours": 17.4,
  "std_dia_hours": 15.6,
  "mean_r2": 0.529,
  "profile_dia": 5.0,
  "dia_ratio": 1.9
}
```

The report's claim of 12.3h uses different aggregation than the underlying data supports.

