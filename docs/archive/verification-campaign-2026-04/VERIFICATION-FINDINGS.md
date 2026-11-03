# Research Report Verification — Expanded Cohort Validation (2026-04-18)

## Quick Summary

**Report**: `docs/60-research/expanded-cohort-validation-report-2026-04-18.md`

**Verification Status**: ⚠️ **REJECT FOR PUBLICATION** — 7 critical/high-priority errors found

**Error Categories**:
- ❌ 2 fabricated DynISF cohorts (EXP-2651, EXP-2652)
- ❌ 1 fabricated per-patient table (EXP-2640)
- ⚠️ 2 incorrect numerical values (EXP-2662 H1)
- ⚠️ 2 data inconsistencies (patient g, cohort accounting)

---

## Critical Errors

### 1. **EXP-2651 DynISF JSON is Identical to Original**
- **Report claims**: 12 separate DynISF patients
- **JSON contains**: 25 patients (same as Original)
- **Evidence**: File `exp-2651_two_phase_isf_dynisf.json` has `n_patients_analyzed: 25`

### 2. **EXP-2652 DynISF JSON is Identical to Original**
- **Report claims**: 10 separate DynISF patients
- **JSON contains**: 18 patients (same as Original)
- **Evidence**: File `exp-2652_circadian_profiling_dynisf.json` has `n_patients_analyzed: 18`

### 3. **EXP-2640 Per-Patient Table Doesn't Match JSON**
- **Report table lists**: a, c, e, f, g, i as fitted patients
- **JSON shows**: c, e, g marked "insufficient" (no correlation data)
- **Patient g anomaly**: Report shows r=+0.721, JSON has no data

### 4. **EXP-2662 H1 Values Significantly Understated**
- **Original**: Report 7%, JSON actual 11.2% (60% error)
- **DynISF**: Report 9%, JSON actual 13.7% (52% error)

---

## Verification Output Files

1. **Full Report** (14.8 KB): 
   - `docs/60-research/VERIFICATION-expanded-cohort-2026-04-18.md`
   - Detailed findings, evidence, root causes, remediation steps

2. **Summary** (3.8 KB):
   - `VERIFICATION-SUMMARY-2026-04-18.txt`
   - Quick reference with error categories and fix checklist

3. **This Document**:
   - `VERIFICATION-FINDINGS.md`
   - One-page overview for rapid review

---

## What Was Verified ✓

| Experiment | Status | Details |
|-----------|--------|---------|
| EXP-2651 Original | ✓ PASS | 25 patients, all H1-H4 match |
| EXP-2656 Original | ✓ PASS | 29 patients, all H1-H4 match |
| EXP-2656 DynISF | ✓ PASS | 12 patients (separate), all H1-H4 match |
| EXP-2652 Original | ✓ PASS | 18 patients, all H1-H3 match |
| EXP-2662 H2/H3/H4 | ✓ PASS | Both cohorts ±5% match |
| **EXP-2651 DynISF** | ❌ FAIL | JSON identical to Original (25 not 12) |
| **EXP-2652 DynISF** | ❌ FAIL | JSON identical to Original (18 not 10) |
| **EXP-2662 H1** | ❌ FAIL | Original 7%→11.2%, DynISF 9%→13.7% |
| **EXP-2640 Table** | ❌ FAIL | Patients c,e,g insufficient; correlations fabricated |

---

## Remediation Checklist

### CRITICAL (Must fix):
- [ ] Rerun or obtain EXP-2651 DynISF with 12 patients
- [ ] Rerun or obtain EXP-2652 DynISF with 10 patients
- [ ] Fix EXP-2640 table (remove insufficient patients or refit)
- [ ] Verify DynISF JSON files are not duplicates of Original

### HIGH PRIORITY:
- [ ] Update EXP-2662 Original H1: 7% → 11.2%
- [ ] Update EXP-2662 DynISF H1: 9% → 13.7%
- [ ] Document H1 calculation method
- [ ] Resolve patient g contradiction (1 vs 7 events)

### MEDIUM PRIORITY:
- [ ] Clarify cohort accounting (31+12≠actual)
- [ ] Map single-letter IDs to JSON patient identifiers
- [ ] Add validation step to prevent similar issues

---

## Impact Assessment

### Core Findings (Unaffected):
✓ Two-phase ISF (EXP-2651 Original) — **SOUND**
✓ SC suppression ceiling (EXP-2656 both cohorts) — **SOUND**
✓ Circadian ISF variation exists (EXP-2652 Original) — **SOUND**

### Questionable Findings (Must Verify):
❌ DynISF cohort superiority — **NO DATA**
❌ Patience mode H1 benefit — **WRONG VALUES**
❌ Per-patient dose-ISF curves — **FABRICATED TABLE**

---

## Next Steps

1. **Author review**: Examine why DynISF JSON files are duplicates
2. **Data audit**: Confirm whether DynISF analysis was actually performed
3. **Recalculation**: Rerun EXP-2651/2652 with correct DynISF cohorts
4. **Correction**: Fix numerical errors and resubmit for verification
5. **Prevention**: Add pre-publication JSON validation

---

## Verification Metadata

- **Verification Date**: 2026-04-18
- **JSON Files Checked**: 9 experiment files
- **Tool**: Python 3.12 + scipy.stats
- **Confidence Level**: HIGH (numerical checks against primary data)
- **Review Time**: ~1 hour (automated + human analysis)

---

## Contact

For detailed findings, see full verification report:
`docs/60-research/VERIFICATION-expanded-cohort-2026-04-18.md`

