# ALG-XVAL Cross-Validation Results

> **Track**: ALG-XVAL Phase 3
> **Date**: 2026-02-16
> **Status**: Complete

## Summary

| Metric | Count |
|--------|-------|
| Total Test Cases | 44 |
| **Passed** | 37 (84%) |
| **Failed** | 7 (16%) |
| Errors | 0 |

## Test Categories

### oref0-extracted-vectors (8 cases)
- Passed: 3
- Failed: 5
- **Issue**: Test cases expected explicit temp basal responses, but oref0 returned "doing nothing" when glucose was unchanged (delta=0)

### boundary-vectors (12 cases)
- Passed: 12
- Failed: 0
- **Result**: All boundary safety conditions validated ✅

### temp-basal-vectors (12 cases)
- Passed: 10
- Failed: 2
- **Issue**: TEMP-009 and TEMP-010 show rate discrepancy (expected ~1.15, got 2.7)

### smb-decision-vectors (12 cases)
- Passed: 12
- Failed: 0
- **Result**: All SMB decision logic validated ✅

## Failure Analysis

### Category 1: "Doing Nothing" Cases (5 failures)

**Test Cases**: OREF0-001, OREF0-003, OREF0-004, OREF0-006, OREF0-008

**Root Cause**: When glucose delta is 0 and currenttemp is <= basal, oref0 returns no action:
```
"Temp 0 <= current basal 1U/hr; doing nothing."
```

**Explanation**: Our test vectors specified `delta: 0` which triggers oref0's "unchanged CGM" logic. The expected values assumed a temp basal would be set, but oref0 correctly determines no action is needed when:
1. CGM is not changing
2. Current temp is already appropriate

**Resolution**: Mark as **expected behavior difference** - not a bug. Update vectors to include non-zero delta for scenarios requiring action.

### Category 2: Rate Calculation Difference (2 failures)

**Test Cases**: TEMP-009, TEMP-010

| Vector | Expected | oref0 Actual |
|--------|----------|--------------|
| TEMP-009 | 1.15 U/hr | 2.7 U/hr |
| TEMP-010 | 1.125 U/hr | 2.7 U/hr |

**Root Cause**: These test cases have:
- High glucose (130-140 mg/dL)
- Low delta (+1-2 mg/dL/5m)
- No IOB

oref0's calculation with `maxSafeBasal` and insulin response curves produces higher rates than our hand-calculated expected values.

**Resolution**: Mark for **investigation** - need to verify if expected values were calculated correctly or if oref0's higher rate is appropriate.

## T1Pal Algorithm Conformance

The XValConformanceTests.swift validates T1Pal algorithm against the same vectors:

| Test | Result |
|------|--------|
| Insulin Model Conformance | ✅ 7/7 passed |
| IOB Curve Conformance | ✅ 3/3 passed |
| Boundary Safety | ✅ 4/4 passed |
| All Vectors Loadable | ✅ 62 test cases |

## Key Findings

1. **Safety boundaries match**: Both T1Pal and oref0 correctly handle low glucose suspend scenarios
2. **Insulin models align**: DIA and peak time values match between implementations when customDIA is properly passed
3. **IOB curves match within tolerance**: All IOB decay tests pass with ±0.01 tolerance
4. **"No action" scenarios differ**: oref0's "doing nothing" behavior differs from expected temp basal in some cases

## Files

- **Swift Tests**: `packages/T1PalAlgorithm/Tests/T1PalAlgorithmTests/XValConformanceTests.swift`
- **Node.js Runner**: `scripts/run-oref0-vectors.js`
- **Results JSON**: `conformance/algorithm/xval/results/oref0-results.json`

## Next Steps (ALG-XVAL-024)

1. Review TEMP-009/TEMP-010 rate calculations against oref0 determine-basal.js source
2. Update oref0-extracted-vectors with non-zero delta values
3. Add iobArray to test inputs for Advanced Meal Assist scenarios
4. Consider adding Loop algorithm runner for three-way comparison

---

*Trace: ALG-XVAL-020, ALG-XVAL-021, ALG-XVAL-022, ALG-XVAL-023*
