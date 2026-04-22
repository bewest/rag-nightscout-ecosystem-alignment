# Quick Reference: April 18 Verification Findings

## Status Summary

| # | Report | Status | Errors | Action |
|---|--------|--------|--------|--------|
| 1 | egp-evidence-synthesis-report-2026-04-18.md | ❌ REJECT | 5 | **Retract & rebuild** |
| 2 | expanded-cohort-validation-report-2026-04-18.md | ❌ REJECT | 5 | **Discard DynISF sections** |
| 3 | sc-ceiling-demand-isf-report-2026-04-18.md | ⚠️ FIX | 2 | **Replace ceiling column** |
| 4 | wall-resolution-mechanism-report-2026-04-18.md | ✅ PASS | 0 | **Publish as-is** |
| 5 | controller-isf-signatures-report-2026-04-18.md | ❌ REJECT | 5 | **Rebuild with actual IDs** |

---

## Critical Errors by Report

### Report 1: EGP Evidence Synthesis

1. **P-value inflation** (Section 3.1): Claims p<10⁻¹⁹; actual ≈4×10⁻¹¹ (1000× overstatement)
2. **Patient count** (Line 4): Claims 12; EXP-2656/2662 use 28 (2.3× error)
3. **Selective reporting** (Section 3.6): Hides 3 of 9 patients with r≥0
4. **Wrong counts** (3.3, 3.8, 3.9): Claims 12; actual 25, 28, 28 respectively

---

### Report 2: Expanded Cohort Validation

1. **Fabricated DynISF cohort** (EXP-2651): Claims 12 patients; JSON shows 25 identical to Original
2. **Fabricated DynISF cohort** (EXP-2652): Claims 10 patients; JSON shows 18
3. **Fabricated EXP-2640 table**: Rows c, e, g marked insufficient but data invented
4. **H1 understatement**: EXP-2662 Original 7% vs actual 11.2% (60% error)
5. **H1 understatement**: EXP-2662 DynISF 9% vs actual 13.7% (52% error)

---

### Report 3: SC Ceiling Demand ISF

1. **Fitted ceiling column**: 69% of values wrong; median 22.5% vs actual 13.9%
2. **Range overstated**: 10-67% vs actual 10-55%

**Fix**: Replace fitted ceiling column with correct JSON values

---

### Report 4: Wall Resolution Mechanism

✅ **No errors found** — All tables verified, all arithmetic correct

---

### Report 5: Controller ISF Signatures

1. **Fabricated patient IDs**: All 12 ns-* IDs don't exist (actual: a-k + odc-*)
2. **Patient i contradiction**: Motivation mentions; table excludes without explanation
3. **Hidden exclusions**: 5 of 17 patients excluded undisclosed (29% sample loss)
4. **Artificial homogeneity**: Motivation promises multicontroller; results show 100% Trio/AB
5. **Hypothesis inversions**: H1, H2, H3 all reported FAIL but actual PASS

---

## Key Statistics

- **Total reports**: 5
- **Reports with errors**: 4 (80%)
- **Total high-confidence errors**: 17
- **Fabricated sections**: 3 (Reports 2, 5)
- **Per-patient tables affected**: 2 (Reports 2, 5)
- **Wrong patient counts**: 4 (Reports 1, 2, 3, 5)
- **Hidden exclusions**: 2 (Reports 1, 5)
- **P-value issues**: 1 (Report 1)

---

## Recommended Actions

**TODAY (do not publish)**:
- Flag Reports 1, 2, 5 as requiring retraction/rebuild
- Hold Report 3 pending ceiling column replacement

**TOMORROW (rebuild)**:
- Report 1: Verify actual patient scope; remove inflated p-value claims
- Report 2: Discard DynISF sections; rebuild EXP-2640 table from JSON
- Report 5: Rebuild using actual patient IDs from JSON; include all 17 or document exclusion

**READY (approve)**:
- Report 4: Publish as-is

---

## Where to Find Details

**Full verification report**: `VERIFICATION-REPORT-2026-04-18-BATCH.md`
- Complete evidence for each error
- JSON references and line numbers
- Actual vs claimed values for every discrepancy

**This quick reference**: Error summary and remediation roadmap

