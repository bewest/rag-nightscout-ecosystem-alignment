# Verification Report: EXP-2668 Controller ISF Signatures

**Report Under Review**: `docs/60-research/controller-isf-signatures-report-2026-04-18.md`  
**Date Reviewed**: 2026-04-18  
**Source Data**: `externals/experiments/exp-2668_controller_isf_signatures.json`  
**Verification Status**: ⚠️ **CRITICAL ISSUES - DO NOT PUBLISH**

---

## Executive Summary

This report contains **5 critical fabrication issues**:

1. **All 12 patient IDs in the table are fabricated** (ns-* namespace not in source data)
2. **Hidden patient exclusion**: 17 patients in JSON, only 12 (filtered) in report
3. **Patient i contradiction**: Main motivating example excluded from results table
4. **Artificial controller homogeneity**: Table shows only Trio/AB despite 5 controller types in data
5. **Hypothesis result mismatches**: 3 of 5 hypotheses show wrong PASS/FAIL status

**Verdict**: The per-patient table (lines 16-29) is completely fabricated. The source data supports a different narrative than what the report presents.

---

## Detailed Findings

### ❌ ISSUE 1: FABRICATED PATIENT IDs (CRITICAL)

**Location**: Lines 16-29 (table body)

**Claim**: 12 patients with IDs like `ns-1ccae8a375b9`, `ns-554b16de7133`, etc.

**Finding**: None of these IDs exist in `exp-2668_controller_isf_signatures.json`

```
Report table IDs:
  ns-1ccae8a375b9, ns-554b16de7133, ns-6bef17b4c1ec,
  ns-8b3c1b50793c, ns-8f3527d1ee40, ns-8ffa739b986b,
  ns-9b9a6a874e51, ns-a9ce2317bead, ns-adde5f4af7ca,
  ns-c422538aa12a, ns-d444c120c23a, ns-dde9e7c2e752

Actual JSON patients:
  a, b, c, d, e, f, g, h, i, k,
  odc-39819048, odc-49141524, odc-58680324,
  odc-61403732, odc-74077367, odc-86025410, odc-96254963
```

**Severity**: 🔴 CRITICAL - The table data cannot be verified

**Remediation**: Rebuild table using actual patient IDs from JSON and appropriate filtering rationale

---

### ❌ ISSUE 2: HIDDEN PATIENT EXCLUSION (CRITICAL)

**Location**: Line 5 header vs lines 16-29 table

**Claim**: "**Patients**: 12" + table shows 12 rows

**Finding**: 
- JSON contains **17 patients total**
- Report table shows **12 patients** (only Trio/AB)
- **Excluded patients NOT disclosed**:
  - Patient a (Loop/TBR, 180 days)
  - Patient i (Loop/AB, 180 days) ← **mentioned in motivation**
  - 5 odc-* patients (AAPS/SMB and AAPS/TBR)

**Severity**: 🔴 CRITICAL - Undisclosed sample restriction

**Remediation**: 
- Option 1: Include all 17 patients with explicit controller-based grouping
- Option 2: If restricting to Trio/AB only, state this explicitly in Section 2 header
- Option 3: If restricting to high-quality data (180+ days), document criteria

---

### ❌ ISSUE 3: PATIENT i CONTRADICTION (CRITICAL)

**Location**: Line 10 (motivation) vs Lines 16-29 (table)

**Motivation Claim (Line 10)**:
> "EXP-2666 found patient i has 1132% ISF shift between 2-12h isolation, while most patients stabilize at 6h."

**Table**: Patient i is **completely absent** from the 12-patient table

**JSON Data on Patient i**:
```
Patient i:
  Controller: Loop/AB (not Trio/AB)
  Days: 180
  SMB/day: 76.2
  Bol/day: 78.6
  Median Gap: 0.17h
  >6h gaps: N/A (no data in JSON)
```

**Severity**: 🔴 CRITICAL - Main motivating example is excluded without explanation

**Contradiction**: 
- Report motivates entire analysis with patient i's 1132% ISF shift
- Then analyzes only Trio/AB patients (excluding patient i who is Loop/AB)
- Patient i result should be in results section, not just motivation

**Remediation**:
- Add patient i to table (as separate Loop/AB group, or with explicit "excluded" note)
- Explain why patient i is excluded from the hypothesis testing
- If testing different hypotheses for different controller groups, restructure accordingly

---

### ❌ ISSUE 4: ARTIFICIAL CONTROLLER HOMOGENEITY (HIGH)

**Location**: Lines 10-29 (entire results section)

**Report Narrative (Line 10)**:
> "Different AID controllers dose differently: SMB-AID fires 50-75 micro-boluses/day (short inter-bolus gaps), Loop/TBR modulates basal rates (longer clean windows)."

**Report Table**: 100% Trio/AB (12/12 patients)

**JSON Distribution**:
```
AAPS/SMB:  3 patients
AAPS/TBR:  4 patients
Loop/AB:   7 patients
Loop/TBR:  2 patients
Trio/AB:   1 patient  ← Report shows 12 (fabricated)
```

**Severity**: 🟠 HIGH - Motivation contradicts presentation

**Issue**: 
- Report motivates analysis with controller type diversity ("different controllers dose differently")
- Actual table shows ZERO diversity (all same controller)
- JSON has 5 different controller types
- No explanation for why diversity disappeared

**Remediation**:
- Include multiple controller types in analysis (as motivation promises)
- Show Loop/TBR, Loop/AB, AAPS/SMB, AAPS/TBR alongside Trio/AB
- If hypothesis requires homogeneity, reframe motivation accordingly

---

### ❌ ISSUE 5: HYPOTHESIS RESULTS MISMATCH (HIGH)

**Location**: Lines 49-57 (hypothesis table)

**Report Hypothesis Results**:
```
H1: FAIL (p ≥ 0.05)
H2: FAIL (p ≥ 0.05)
H3: FAIL
H4: FAIL
H5: FAIL
```

**JSON Hypothesis Results**:
```python
exp2668['hypotheses'] = {
    'H1': 'False',      # Matches: FAIL ✓
    'H2': 'False',      # Matches: FAIL ✓
    'H3': True,         # MISMATCH: Report says FAIL, JSON says True ✗
    'H4': True,         # MISMATCH: Report says FAIL, JSON says True ✗
    'H5': True,         # MISMATCH: Report says FAIL, JSON says True ✗
}
```

**Severity**: 🟠 HIGH - 3 of 5 hypothesis results incorrect

**Specific Issues**:
- **H1 (FAIL)** ✓ Correct - "Demand ISF differs by controller type" did NOT reach significance
- **H2 (FAIL)** ✓ Correct - "Optimal isolation differs by controller" did NOT reach significance
- **H3 (FAIL)** ✗ **WRONG** - Should be **PASS** - "Patient i shift explained by SMB-AID spacing" **did** reach significance
- **H4 (FAIL)** ✗ **WRONG** - Should be **PASS** - "Loop/TBR has more isolated corrections" **did** reach significance
- **H5 (FAIL)** ✗ **WRONG** - Should be **PASS** - "Within-controller ISF CV < overall CV" **did** hold true

**Remediation**: Update lines 55-57 to reflect actual results:
```
| H3 | PASS | Patient i shift explained by SMB-AID bolus spacing |
| H4 | PASS | Loop/TBR has more isolated corrections/day than SMB-AID |
| H5 | PASS | Within-controller ISF CV < overall CV |
```

---

## Arithmetic Verification

### Per-Patient Table Check (Lines 18-29)

**Validation rule**: SMB/day ≤ Bol/day (micro-boluses are subset of total boluses)

**JSON patients (cannot verify report table - IDs are fabricated)**:

| Patient | Controller | SMB/day | Bol/day | SMB ≤ Bol |
|---------|-----------|---------|---------|-----------|
| a | Loop/TBR | 0.0 | 4.9 | ✓ |
| b | Trio/AB | 50.4 | 59.7 | ✓ |
| c | Loop/AB | 56.5 | 57.9 | ✓ |
| d | Loop/AB | 63.1 | 65.8 | ✓ |
| e | Loop/AB | 72.2 | 75.2 | ✓ |
| f | Loop/TBR | 0.0 | 3.0 | ✓ |
| g | Loop/AB | 54.0 | 60.3 | ✓ |
| h | Loop/AB | 43.5 | 46.8 | ✓ |
| i | Loop/AB | 76.2 | 78.6 | ✓ |
| k | Loop/AB | 58.9 | 66.9 | ✓ |
| odc-39819048 | AAPS/SMB | 40.2 | 42.2 | ✓ |
| odc-49141524 | AAPS/SMB | 27.2 | 28.6 | ✓ |
| odc-58680324 | AAPS/TBR | 0.0 | 4.3 | ✓ |
| odc-61403732 | AAPS/SMB | 31.1 | 32.8 | ✓ |
| odc-74077367 | AAPS/TBR | 0.0 | 65.4 | ✓ |
| odc-86025410 | AAPS/TBR | 0.0 | 9.4 | ✓ |
| odc-96254963 | AAPS/TBR | 0.0 | 9.0 | ✓ |

**Finding**: All JSON values are arithmetically consistent (SMB ≤ Bol), but table in report cannot be verified.

---

## Missing Data Elements

### Patient i ISF Shift Claim (Line 10)

**Claim**: "1132% ISF shift between 2-12h isolation"

**Status**: 
- ✓ Patient i exists in JSON
- ✓ Patient i has 'sweep' data with ISF values
- ? Unable to verify exact 1132% value (requires running calculation on sweep window data)
- ⚠️ **Concern**: If this value comes from EXP-2666, verify that cross-reference is correct

**Verification needed**: Check `exp-2666_isolation_sweep.json` for patient i ISF shift value

---

## Cross-Reference Issues

**Line 4**: "**Predecessor**: EXP-2663, EXP-2666"
- ✓ EXP-2666 file exists (`exp-2666_isolation_sweep.json`)
- Cannot verify that patient i 1132% value without examining EXP-2666 data

**Line 10**: "EXP-2666 found patient i has 1132% ISF shift"
- Requires verification against EXP-2666 report or data

---

## Summary Table

| Issue | Type | Severity | Instances | Fixable |
|-------|------|----------|-----------|---------|
| Fabricated patient IDs | Fabrication | Critical | 12 rows | Yes (rebuild from JSON) |
| Hidden patient exclusion | Disclosure | Critical | 5 patients | Yes (document or include) |
| Patient i exclusion contradiction | Logic | Critical | 1 patient | Yes (include or explain) |
| Artificial controller homogeneity | Sampling bias | High | Entire table | Yes (include diversity) |
| Hypothesis result errors | Transcription | High | 3/5 hypotheses | Yes (correct) |

---

## Recommendations

### IMMEDIATE ACTIONS (Must fix before publication)

1. **Rebuild Table 2.1** using actual patient IDs from JSON (a, b, c, etc.)
   - Organize by controller type (not hidden)
   - Include all 17 patients or document exclusion criteria

2. **Correct Hypothesis Results** (Lines 55-57)
   - H3: FAIL → PASS
   - H4: FAIL → PASS
   - H5: FAIL → PASS

3. **Resolve Patient i Contradiction**
   - Either include patient i in table with explanation
   - Or explain why main motivating example is excluded

### SECONDARY ACTIONS

4. **Verify ISF shift claim** against EXP-2666
5. **Add exclusion criteria** to Section 2 header if filtering is intentional
6. **Restructure results** to match narrative (show controller diversity if that's the story)

---

## Verification Confidence

| Element | Confidence | Evidence |
|---------|-----------|----------|
| Patient IDs fabricated | 100% | JSON search confirms no ns-* IDs |
| Hypothesis results wrong | 100% | JSON shows True/False values |
| Patient count discrepancy | 100% | JSON has 17 patients |
| Controller diversity missing | 100% | JSON shows 5 types, table shows 1 |
| Patient i excluded | 100% | Not in table rows 18-29 |

---

## Conclusion

**This report cannot be published in its current form.** The per-patient table is fabricated (wrong patient IDs), the hypothesis results are incorrect (3/5 wrong), and the main motivating example (patient i) is excluded from the analysis without explanation.

**Recommendation**: **RETRACT** and rebuild with:
1. Actual patient identifiers from source data
2. Correct hypothesis results  
3. Explanation of sample inclusion/exclusion
4. Restored controller diversity in analysis

---

**Verification performed**: 2026-04-18  
**Reviewer**: Copilot (via autoreview-correct skill)  
**Status**: Ready for author response
