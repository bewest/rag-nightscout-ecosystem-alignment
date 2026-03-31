# Algorithm Convergence Backlog

> **Status: ✅ COMPLETED** — All items resolved through Phase 2-3 convergence
> (assessments A1-A16). See [`traceability/cross-validation-log.md`](../../traceability/cross-validation-log.md).

Tracked changes needed to make `t1pal-mobile-apex` oref0 match the
canonical JS reference (`externals/oref0/lib/determine-basal`).

**Baseline** (2025-03-29): eventualBG within ±10 mg/dL for only 12%
of 100 test vectors. Systematic -60.6 mg/dL bias (Swift predicts lower).

**Final** (2026-03-31): 100% eventualBG exact match, 100% rate ±0.5,
all 4 prediction curves aligned with <0.02 mg/dL avg MAE.

---

## Continuance Rules (Factor Out First)

JS oref0 has 7 places where it returns without changing the pump temp
basal — these are **operational optimizations**, not algorithm logic.
They reduce RF transmissions, battery drain, and pump beeping when the
current temp is "close enough" to what the algorithm would set.

### The 7 Rules (from `determine-basal.js`)

| # | Line | Pattern | Condition |
|---|------|---------|-----------|
| 1 | 217-219 | `doing nothing` | CGM error + current temp ≤ basal |
| 2 | 944-946 | `temp X ~ req Y` | BG low + rising + temp ≈ basal + duration > 15m |
| 3 | 979-981 | `temp X ~< req Y` | BG low + rising + rate ≥ 0.8× current + duration > 5m |
| 4 | 1016-1018 | `temp X ~ req Y` | Falling faster than expected + temp ≈ basal + duration > 15m |
| 5 | 1029-1032 | `no temp required` | BG in range + temp ≈ basal + duration > 15m |
| 6 | 1047-1049 | `temp X ~ req Y` | IOB > maxIOB + temp ≈ basal + duration > 15m |
| 7 | 1180-1182 | `temp X >~ req Y` | High BG + current temp ≥ required + duration > 5m |

All share the pattern: compare `round_basal(suggested)` vs
`round_basal(current)` and skip the pump command if close enough.

### Proposed: `ContinuancePolicy` Protocol

```swift
protocol ContinuancePolicy {
    func shouldContinue(
        suggestedRate: Double,
        currentTemp: TempBasal?,
        scheduledBasal: Double,
        profile: AlgorithmProfile
    ) -> ContinuanceDecision
}

enum ContinuanceDecision {
    case `continue`(reason: String)  // keep current temp
    case change(rate: Double, duration: Int, reason: String)
}
```

This separates the algorithm's *intent* (what rate it wants) from the
*operational decision* (whether to actually command the pump). Tests
can then validate the algorithm's calculation independently from
continuance behavior.

### Null Rate Semantics

When ContinuancePolicy returns `.continue`, `AlgorithmDecision` should
have `suggestedTempBasal: nil` — meaning "no pump command needed."
The adapter translates this to `rate: null` in JSON output.

Currently Swift always returns a rate, which causes false mismatches
with JS oref0 (accounts for ~30% of rate disagreements).

---

## EventualBG Calculation Fix

### Current (Swift DetermineBasal.swift:137)
```swift
let eventualBG = bg + (iob * sens * -1)
```

### Reference (JS determine-basal.js:442-648)
```javascript
// Builds 48-tick IOB projection, tracks BG at each tick
for (i=0; i < iob_data.length; i++) {
    predBGI = round((-iob_data[i].activity * sens * 5), 2);
    IOBpredBG = IOBpredBGs[IOBpredBGs.length-1] + predBGI + predDev;
    // ... eventualBG = IOBpredBGs[last]
}
```

The scalar formula ignores:
- **Insulin timing**: DIA curve shape (bilinear/exponential decay)
- **Per-tick activity**: `iobTick.activity` varies per 5-min interval
- **Deviation terms**: `predDev = ci * (1 - min(1, length/(60/5)))`

This is the root cause of the -60.6 mg/dL bias.

### Fix Strategy

`Predictions.swift` already has `PredictionEngine` that builds proper
48-point curves. Wire it into `Oref0Algorithm.calculate()`:

```swift
// In Oref0Algorithm.calculate():
let output = determineBasal.calculate(...)
let predictions = predictionEngine.predict(
    currentGlucose: bg, glucoseDelta: delta,
    iob: iob, cob: cob, profile: profile,
    insulinModel: insulinModel
)
// Use predictions.iob.last as eventualBG
// Use predictions.allCurves.min() as minPredBG
```

---

## Remaining Algorithm Gaps (All Resolved ✅)

| Gap | Status | Resolution |
|-----|--------|------------|
| Prediction arrays (IOB/ZT/COB/UAM) | ✅ | All 4 curves aligned (A12, A16) |
| eventualBG from IOB projection | ✅ | Tick-by-tick (A1-A3) |
| minPredBG from curve minimums | ✅ | Array min implemented |
| Continuance rules | ✅ | ContinuancePolicy protocol (A4-A5) |
| COB in predictions | ✅ | predCI + remainingCI ported (A4, A11) |
| UAM detection | ✅ | UAM curve aligned (A16) |
| Autosens ratio | ✅ | Applied to ISF/basal |
| round_basal precision | ✅ | Pump-model aware |
| IOB array input | ✅ | 48-element array with dose history (A12, A14) |

---

## Validation Targets (All Exceeded ✅)

| Milestone | EventualBG ±10 | Rate Exact | Prediction MAE |
|-----------|----------------|------------|----------------|
| **Baseline** | 12% | 33% | N/A (no arrays) |
| After continuance + null rate | 12%* | >50%* | N/A |
| After PredictionEngine wiring | >50% | >50% | < 15 mg/dL |
| After eventualBG fix | >80% | >70% | < 10 mg/dL |
| After COB/UAM/minPred | >85% | >80% | < 5 mg/dL |
| **Achieved (Phase 3)** | **100%** | **99%** | **0.005 mg/dL** |
