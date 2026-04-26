# Review: exp-2983-trio-iob-governor-2026-04-23.md

## ERRORS FOUND

### 1. ❌ CRITICAL: Per-patient p75_IOB table contains impossible values (0.0)

**Location**: Report table line 23-33

**Issue**: Two patients show p75_IOB = 0.22 and 0.13 in the report table, but JSON source has 0.0.

| Patient | Report p75_IOB | JSON p75_IOB |
|---------|---|---|
| ns-d444c120c23a | 0.13 | 0.0000 |
| ns-1ccae8a375b9 | 0.22 | 0.0000 |

Since the 75th percentile cannot be 0 when mean_IOB is 0.10–0.21, these report values appear to be fabricated or transposed from another patient.

**Evidence**:
- `externals/experiments/exp-2983_summary.json` per_patient array confirms p75_iob_U = 0.0 for both patients
- This is mathematically inconsistent: 75th percentile ≥ median ≥ mean, so p75 cannot exceed mean

---

### 2. ⚠️  MINOR: p75_IOB rounding inconsistency

**Location**: Report table line 33, patient ns-adde5f4af7ca

**Issue**: JSON value is 2.2149999141693115, reported as 2.22 but standard rounding to 2 decimals gives 2.21.

**Evidence**:
- JSON: `"p75_iob_U": 2.2149999141693115`
- Report: `2.22`
- Expected: `2.21` (banker's rounding) or `2.21` (truncation)

**Impact**: Minor—off by 0.01 U, within measurement noise.

---

## VERIFIED CLAIMS

✅ **Spearman correlations** (lines 14-19):
- mean_IOB ↔ hypo_rate: ρ = −0.333, p = 0.38 ✓
- p75_IOB ↔ hypo_rate: ρ = −0.469, p = 0.20 ✓

✅ **Per-patient hypo rates** (line 23–33): All match JSON within 0.2 percentage points

✅ **Within-patient tertile data** (lines 47–48):
- ns-a9ce2317bead: 15.97% → 0.97% ✓
- ns-adde5f4af7ca: 4.99% → 1.10% ✓

✅ **Code references** (lines 89–94):
- `externals/Trio/trio-oref/lib/profile/index.js:40-51` - enableSMB_always config ✓
- `externals/Trio/trio-oref/lib/determine-basal/determine-basal.js:84-88` - enableSMB_always gate ✓
- `externals/Trio/trio-oref/lib/determine-basal/determine-basal.js:880,977-982` - maxIOBPredBG logic ✓

---

## CONCLUSION

**The report has 1 critical data error** (impossible p75_IOB values for two patients) and 1 minor rounding inconsistency. The statistical claims and code references are accurate.
