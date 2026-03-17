# BWP Test Timing Determinism

**Status**: 📋 Ready for Implementation  
**Priority**: 🟠 P1  
**Type**: Test fix (no production code change)

**Related Files**:
- `tests/boluswizardpreview.test.js:300` - Uses `Date.now()` causing timing drift
- `lib/plugins/iob.js` - IOB decay calculation (time-sensitive)
- `lib/plugins/boluswizardpreview.js` - Bolus wizard calculation

**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`

---

## Summary

Test `set a pill to the BWP with infos` uses `Date.now()` for time calculations, making the bolus estimate sensitive to test execution duration. This causes flaky failures when test infrastructure is slow.

**This is the actual fix for the BWP flakiness** — NOT the epsilon change (which addresses a separate FP artifact issue). See [insulin-rounding-epsilon-analysis.md](./insulin-rounding-epsilon-analysis.md) for why epsilon is correct but doesn't fix this.

---

## Problem

### Current Test Code

```javascript
var now = Date.now();
var before = now - (5 * 60 * 1000);  // 5 minutes ago

var data = {
  sgvs: [{mills: before, mgdl: 295}, {mills: now, mgdl: 300}]
  , treatments: [{mills: before, insulin: '1.5'}]
  // ...
};

var sbx = require('../lib/sandbox')().clientInit(ctx, Date.now(), data);
```

### Why It's Flaky

1. **IOB decays over time**: The `iob.calcTreatment()` function calculates remaining insulin based on `minAgo = (currentTime - bolusTime) / 60000`

2. **Test uses live time**: Both `before` and the sandbox initialization use `Date.now()`

3. **Slow CI = more decay**: If test execution takes 2+ minutes between setting `before` and calling `clientInit()`:
   - `minAgo` increases from 5 to 7+ minutes
   - IOB drops from ~1.494 to ~1.49 (due to 3-decimal rounding)
   - Bolus estimate changes from 0.506 to exactly 0.51
   - Display changes from `'0.50U'` to `'0.51U'`

### IOB Calculation Trace

For treatment at `minAgo = 5`:
```
x1 = 5/5 + 1 = 2
iobContrib = 1.5 * (1 - 0.001852 * 4 + 0.001852 * 2) = 1.494444
rounded = 1.494
bolus = (300 - 1.494*90 - 120) / 90 = 0.506 → floor → 0.50U ✓
```

For treatment at `minAgo = 7`:
```
x1 = 7/5 + 1 = 2.4
iobContrib = 1.5 * (1 - 0.001852 * 5.76 + 0.001852 * 2.4) = 1.4906...
rounded = 1.49
bolus = (300 - 1.49*90 - 120) / 90 = 0.51 exactly → 0.51U ✗
```

---

## Solution

### Option 1: Freeze Time in Test (Recommended)

Use a fixed timestamp instead of `Date.now()`:

```javascript
it('set a pill to the BWP with infos', function (done) {
  // Use fixed timestamp for deterministic calculation
  var fixedNow = 1600000000000;  // Arbitrary fixed timestamp
  var before = fixedNow - (5 * 60 * 1000);

  var ctx = {
    settings: {}
    , pluginBase: {
      updatePillText: function mockedUpdatePillText(plugin, options) {
        options.label.should.equal('BWP');
        options.value.should.equal('0.50U');
        done();
      }
    }
    , moment: helper.ctx.moment
  };
  
  // ... profile setup ...

  var data = {
    sgvs: [{mills: before, mgdl: 295}, {mills: fixedNow, mgdl: 300}]
    , treatments: [{mills: before, insulin: '1.5'}]
    , devicestatus: []
    , profile: loadedProfile
  };

  // Pass fixedNow instead of Date.now()
  var sbx = require('../lib/sandbox')().clientInit(ctx, fixedNow, data);

  iob.setProperties(sbx);
  boluswizardpreview.setProperties(sbx);
  boluswizardpreview.updateVisualisation(sbx);
});
```

### Option 2: Calculate Expected Value Dynamically

Instead of hardcoding `'0.50U'`, calculate what the expected value should be:

```javascript
var sbx = require('../lib/sandbox')().clientInit(ctx, Date.now(), data);
iob.setProperties(sbx);
boluswizardpreview.setProperties(sbx);

// Calculate expected based on actual IOB
var actualIob = sbx.properties.iob.iob;
var expectedBolus = (300 - actualIob * 90 - 120) / 90;
var expectedDisplay = (Math.floor(expectedBolus * 100) / 100).toFixed(2) + 'U';

// Use calculated expectation
options.value.should.equal(expectedDisplay);
```

**Note**: This approach tests less (doesn't verify the specific calculation) but is more resilient.

### Option 3: Use Time Mocking Library

Use a library like `sinon` or `lolex` to freeze `Date.now()`:

```javascript
var sinon = require('sinon');

describe('boluswizardpreview', function () {
  var clock;
  
  beforeEach(function() {
    clock = sinon.useFakeTimers(1600000000000);
  });
  
  afterEach(function() {
    clock.restore();
  });
  
  // Tests now have deterministic time
});
```

---

## Work Items

| ID | Task | Priority | Status |
|----|------|----------|--------|
| BWP-TIME-001 | Implement fixed timestamp in test | 🟠 P1 | 📋 Ready |
| BWP-TIME-002 | Verify test passes with stress testing | 🟠 P1 | 📋 Ready |
| BWP-TIME-003 | Document pattern for other timing-sensitive tests | 🟢 P2 | 📋 Ready |

---

## Verification

After implementing the fix:

```bash
# Stress test - should pass 100%
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447
for i in {1..20}; do 
  npm test -- --grep "BWP with infos" 2>&1 | grep -E "(passing|failing)"
done

# Run with artificial delay to simulate slow CI
node -e "
setTimeout(function() {
  require('child_process').execSync('npm test -- --grep \"BWP with infos\"', {stdio: 'inherit'});
}, 120000);  // 2 minute delay
"
```

---

## Impact

- **Flaky test eliminated**: No more random CI failures
- **No production code change**: Fix is test-only
- **Pattern established**: Can apply to other timing-sensitive tests

---

## Related

- [insulin-rounding-epsilon-analysis.md](./insulin-rounding-epsilon-analysis.md) - Confirms epsilon is correct (separate issue)
- `docs/test-specs/flaky-tests.md` - Flaky test documentation

---

## Last Updated

2026-03-17
