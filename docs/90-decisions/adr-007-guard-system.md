# ADR-007: Guard System Architecture for oref0 Predictions

## Status

Accepted

## Date

2025-03-30

## Context

oref0's determine-basal uses a multi-stage "guard system" where the final
temp basal rate depends on comparing multiple prediction curves against
safety thresholds. The guard system determines `minPredBG`, `minGuardBG`,
and `avgPredBG`, which together drive the dosing decision through a 7-branch
cascade.

During Phase 2 convergence, we discovered that the guard system is the
**primary source of rate divergence** between implementations. Specifically:

1. `avgPredBG` must be computed from curve eventual values (last point of
   each prediction curve), NOT from a separate guard computation
2. `minPredBG` must be capped at `avgPredBG`, not at `ztGuard` — using
   ztGuard pulls minPredBG too low, causing false "in range" decisions
3. The 7-branch dosing cascade (lines 777-955 in determine-basal.js)
   must be replicated exactly, including edge cases around threshold
   boundaries

## Decision

We will implement the guard system as a **faithful port** of the JS logic,
preserving the exact same variable names, computation order, and branching
structure. The Swift implementation lives in `DetermineBasal.swift` and
mirrors the JS line-by-line.

Key implementation choices:
- `minPredBG = min(minIOBPredBG, minCOBPredBG, minUAMPredBG, minZTPredBG)`
- `avgPredBG = round(avg(IOBpredBG_last, COBpredBG_last, UAMpredBG_last, ZTpredBG_last))`
- `minGuardBG = max(minPredBG, avgPredBG)` (the avgPredBG cap)
- The 7-branch cascade uses `minGuardBG` for threshold comparisons

## Consequences

### Positive

- **90/100 eventualBG exact match** (up from ~5% before guard fix)
- **100% rate ±0.5 agreement** on all 72 rate-producing vectors
- Readable Swift code that maps 1:1 to JS for auditing

### Negative

- Tightly coupled to JS implementation details (e.g., rounding order)
- 10 remaining eventualBG mismatches from synthetic vectors with
  stale/undefined fields (irreducible)

### Neutral

- The guard system is the same across oref0-JS, AAPS-JS, and AAPS-Kotlin
- Future oref1 work will extend but not replace this guard system

## Related

- `DetermineBasal.swift` in t1pal-mobile-apex — Swift guard implementation
- `externals/oref0/lib/determine-basal/determine-basal.js:777-955` — JS source
- Phase 2 convergence assessments A2-A7 in cross-validation-assessment.md
