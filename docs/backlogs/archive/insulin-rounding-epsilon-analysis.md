# Insulin Rounding Epsilon Analysis

**Status**: ✅ Analysis Complete - No Action Needed

**Related Files**:
- `lib/sandbox.js` - `roundInsulinForDisplayFormat()` function
- `tests/boluswizardpreview.test.js` - Flaky test `set a pill to the BWP with infos`
- `docs/test-specs/flaky-tests.md` - Historical documentation

**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`

---

## Summary

Commit `64e3463f` added `+1e-9` epsilon to `roundInsulinForDisplayFormat()`. **This change is CORRECT** and fixes genuine floating-point representation artifacts (e.g., `0.29` displaying as `0.28`).

**Important**: The BWP flaky test (`'0.50U'` vs `'0.51U'`) is a **separate issue** caused by test timing drift, NOT by floating-point artifacts. The epsilon fix does not address that flakiness. See [bwp-test-timing-determinism.md](./bwp-test-timing-determinism.md) for the actual fix.

---

## Background

### The Applied Fix (Commit 64e3463f)

```javascript
// Before
return (Math.floor(insulin / 0.01) * 0.01).toFixed(2);

// After  
return (Math.floor(insulin * 100 + 1e-9) / 100).toFixed(2);
```

---

## Analysis

### Two Separate Issues (Previously Conflated)

| Issue | Root Cause | Fix | Status |
|-------|------------|-----|--------|
| FP representation artifacts | `0.29*100 = 28.999...` | `+epsilon` ✅ | **Already fixed** |
| BWP flaky test (`0.50U` vs `0.51U`) | `Date.now()` timing drift | Freeze time in test | **Needs implementation** |

### Why +epsilon is CORRECT

JavaScript floating-point representation causes certain decimal values to round incorrectly:

```javascript
0.29 * 100 = 28.999999999999996  // Should be 29
0.57 * 100 = 56.999999999999993  // Should be 57
0.58 * 100 = 57.999999999999993  // Should be 58
```

Without epsilon: `floor(28.999...) = 28` → displays `0.28U` ❌
With +epsilon: `floor(28.999... + 1e-9) = 29` → displays `0.29U` ✅

### Why -epsilon is WRONG

```javascript
floor(0.50 * 100 - 1e-9) = floor(49.999999999) = 49  // WRONG!
```

**`-epsilon` would break exact values**, displaying `0.49U` when the calculation is exactly `0.50U`.

### Why +epsilon Does NOT Fix BWP Flakiness

The BWP test fails when:
1. Test uses `Date.now()` at line 300
2. IOB decays during slow test execution (7+ minutes)
3. Calculation produces **mathematically exact** `0.51`
4. `floor(51 + 1e-9) = 51` → still displays `0.51U`

**Epsilon cannot fix timing drift** — the value IS 0.51, not a FP artifact.

---

## Conclusion

| Question | Answer |
|----------|--------|
| Was +epsilon the right fix? | ✅ **YES** — fixes genuine FP artifacts |
| Does +epsilon fix BWP flakiness? | ❌ **NO** — that's a timing issue |
| Should we change to -epsilon? | ❌ **NO** — would break exact values |
| What fixes BWP flakiness? | Freeze `Date.now()` in test |

**No changes needed to `lib/sandbox.js`.** The epsilon implementation is correct.

---

## Verification

```bash
# Confirm +epsilon fixes FP artifacts
node -e "
var problematic = [0.29, 0.57, 0.58];
problematic.forEach(function(v) {
  var scaled = v * 100;
  console.log(v + ': floor=' + Math.floor(scaled) + 
    ' +eps=' + Math.floor(scaled + 1e-9) + 
    ' expected=' + Math.round(v * 100));
});
"

# Confirm -epsilon breaks exact values
node -e "
console.log('floor(0.50 * 100 - 1e-9) =', Math.floor(0.50 * 100 - 1e-9), '← WRONG!');
"
```

---

## Related

- [bwp-test-timing-determinism.md](./bwp-test-timing-determinism.md) - **The actual fix for BWP flakiness**
- Commit `64e3463f` - Original epsilon fix (correct)

---

## Last Updated

2026-03-17
