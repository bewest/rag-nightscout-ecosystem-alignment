# Verification Report Index

## Report Under Review
- **File**: `docs/60-research/expanded-cohort-validation-report-2026-04-18.md`
- **Topic**: Expanded cohort validation of 5 priority EGP/ISF experiments
- **Scope**: 43-patient cohort (31 NS-parquet training + 12 DynISF-v2) 
- **Date**: 2026-04-18

---

## Verification Documents Created

### 1. **VERIFICATION-FINDINGS.md** (This directory)
**One-page executive summary** — Best starting point for quick review
- ✓ Quick summary of critical errors
- ✓ What was verified (✓ PASS / ❌ FAIL breakdown)
- ✓ Impact assessment
- ✓ Remediation checklist

### 2. **VERIFICATION-SUMMARY-2026-04-18.txt** (This directory)
**Structured summary** — Error categories and remediation tracking
- ✓ All 7 errors with severity levels
- ✓ Root cause analysis
- ✓ Verified results (correct sections)
- ✓ Detailed checklist for fixes

### 3. **docs/60-research/VERIFICATION-expanded-cohort-2026-04-18.md**
**Comprehensive verification report** (14.8 KB) — Detailed findings with evidence
- ✓ Executive summary with error matrix
- ✓ Line-by-line claim verification
- ✓ Detailed evidence for each error
- ✓ Root cause analysis
- ✓ Remediation actions (critical/high/medium)
- ✓ Summary table for all experiments
- ✓ Verification metadata

---

## Quick Error Reference

| Error | Type | Severity | Location | Fix |
|-------|------|----------|----------|-----|
| EXP-2651 DynISF | Fabricated cohort | ❌ CRITICAL | Lines 95-102 | Rerun or obtain correct JSON |
| EXP-2652 DynISF | Fabricated cohort | ❌ CRITICAL | Lines 139-145 | Rerun or obtain correct JSON |
| EXP-2662 H1 Original | Wrong value | ⚠️ HIGH | Line 239 | 7% → 11.2% |
| EXP-2662 H1 DynISF | Wrong value | ⚠️ HIGH | Line 248 | 9% → 13.7% |
| EXP-2640 Table | Fabricated table | ❌ CRITICAL | Lines 288-297 | Replace with correct fitted patients |
| Patient g | Data inconsistency | ⚠️ MEDIUM | Lines 296, 301 | Clarify 1 vs 7 events, +0.721 correlation |
| Cohort accounting | Accounting error | ⚠️ HIGH | Lines 5-6 | Reconcile 31+12 with JSON counts |

---

## Evidence Files

All JSON source files used for verification are located in:
`externals/experiments/`

Files verified:
1. `exp-2651_two_phase_isf.json` ✓ Verified
2. `exp-2651_two_phase_isf_dynisf.json` ❌ Duplicate (fabricated)
3. `exp-2652_circadian_profiling.json` ✓ Verified
4. `exp-2652_circadian_profiling_dynisf.json` ❌ Duplicate (fabricated)
5. `exp-2656_sc_ceiling.json` ✓ Verified
6. `exp-2656_sc_ceiling_dynisf.json` ✓ Verified
7. `exp-2662_patience_mode.json` ⚠️ Wrong H1 values
8. `exp-2662_patience_mode_dynisf.json` ⚠️ Wrong H1 values
9. `exp-2640_per_patient_isf.json` ❌ Fabricated table

---

## How to Use These Reports

### For Quick Review (5 minutes):
1. Read: `VERIFICATION-FINDINGS.md` (this document)
2. Check: "Critical Errors" section
3. Decision: Reject or remediate

### For Detailed Review (20 minutes):
1. Read: `VERIFICATION-SUMMARY-2026-04-18.txt`
2. Reference: Error categories and root causes
3. Task: Use remediation checklist

### For Complete Analysis (1 hour):
1. Read: `docs/60-research/VERIFICATION-expanded-cohort-2026-04-18.md`
2. Check: Evidence section for each error
3. Verify: Root causes and remediation steps

### For Author Response:
1. Start with "VERIFICATION-FINDINGS.md" 
2. Reference specific line numbers from the full report
3. Use remediation checklist to plan fixes
4. Resubmit with corrected JSON and text

---

## Verified Results (✓ PASS)

These sections of the report are **correct** and well-supported by JSON data:

- ✓ EXP-2651 Original (Section 2.2): All H1-H4 results verified
- ✓ EXP-2652 Original (Section 3.2): All H1-H3 results verified
- ✓ EXP-2656 Original (Section 4.2): All H1-H4 results verified
- ✓ EXP-2656 DynISF (Section 4.3): All H1-H4 results verified
- ✓ EXP-2662 H2/H3/H4 (Sections 5.2-5.3): Results within ±5%

---

## Recommendation

**Status**: ⚠️ **REJECT FOR PUBLICATION**

**Rationale**:
- 2 critical DynISF cohorts are not supported by JSON data (appear to be duplicates of Original)
- 1 per-patient table contains fabricated data (patients marked insufficient in JSON)
- 2 key numerical values are significantly wrong (EXP-2662 H1: 60% and 52% errors)
- Core physiological findings (2-phase ISF, ceiling model) are sound but DynISF claims are unsupported

**Path Forward**:
1. Verify DynISF analysis was actually performed
2. Obtain correct DynISF JSON files (if they exist)
3. Correct numerical errors in report
4. Fix per-patient table or rerun analysis
5. Resubmit for verification

---

## Verification Metadata

| Attribute | Value |
|-----------|-------|
| Report File | `docs/60-research/expanded-cohort-validation-report-2026-04-18.md` |
| Verification Date | 2026-04-18 |
| Verification Method | JSON cross-reference + numerical validation |
| Tools Used | Python 3.12, scipy.stats, pandas |
| Confidence Level | HIGH (definitive numerical mismatches) |
| Errors Found | 7 (2 critical, 2 high, 3 medium) |
| Experiments Verified | 9 (5 pass, 4 fail/partial) |

---

## Document Locations

```
Repository Root
├── VERIFICATION-FINDINGS.md ← Start here (this document)
├── VERIFICATION-SUMMARY-2026-04-18.txt
│
├── docs/
│   └── 60-research/
│       ├── expanded-cohort-validation-report-2026-04-18.md (report under review)
│       └── VERIFICATION-expanded-cohort-2026-04-18.md (full verification)
│
└── externals/
    └── experiments/ (JSON source files)
        ├── exp-2651_two_phase_isf.json
        ├── exp-2651_two_phase_isf_dynisf.json
        ├── exp-2652_circadian_profiling.json
        ├── exp-2652_circadian_profiling_dynisf.json
        ├── exp-2656_sc_ceiling.json
        ├── exp-2656_sc_ceiling_dynisf.json
        ├── exp-2662_patience_mode.json
        ├── exp-2662_patience_mode_dynisf.json
        └── exp-2640_per_patient_isf.json
```

---

**Last Updated**: 2026-04-18
**Next Review**: After author remediation
