# ADR-006: Continuance Bypass in Cross-Validation

## Status

Accepted

## Date

2025-03-30

## Context

AID algorithms include "continuance rules" — logic that returns null/no-op
when the algorithm determines the current temp basal should continue unchanged.
This saves battery, RF transmissions, and pump wear. Examples:

- **oref0-JS**: 7 inline continuance checks (lines 944, 1016, 1030 in
  determine-basal.js) that check remaining duration, rate equality, etc.
- **oref0-Swift**: `ContinuancePolicy` protocol with `shouldContinue()`
  returning `.continueUnchanged` or `.setNew(rate, duration)`
- **Loop**: Implicit via dose rounding and minimum adjustment thresholds

The problem: continuance rules are **implementation-specific** and depend on
pump state, timing, and policy decisions that aren't part of the algorithm's
mathematical core. When cross-validating, continuance causes 28 out of 100
vectors to produce null rates in JS (continuance) but explicit rates in Swift,
making comparison impossible.

## Decision

We will **bypass continuance rules** in cross-validation adapters to expose
the raw algorithm decision:

1. **Swift adapter**: Calls `calculate()` (raw) instead of
   `calculateWithContinuance()` to get the un-filtered decision
2. **JS adapter**: Cannot bypass inline continuance (it's woven into the
   control flow), so we classify null-rate JS vectors as "continuance" and
   exclude them from rate comparison
3. **AAPS adapter**: Same as JS (inline continuance in determine-basal.js)

Continuance rules are documented separately as a cross-cutting concern
(see B3: generalize-continuance in the backlog).

## Consequences

### Positive

- **72 of 100 vectors** become rate-comparable (up from ~52 before bypass)
- **100% rate ±0.5 agreement** on all comparable vectors
- Clean separation: algorithm math vs. operational policy
- ContinuancePolicy protocol enables future per-system policy testing

### Negative

- 28 vectors still produce null rates from JS (inline continuance)
- We're not testing continuance equivalence (deferred to B3)
- Adapters must document which continuance path they use

### Neutral

- The 28 null-rate vectors still validate eventualBG and prediction curves
- A future "continuance equivalence" test layer can use the same vectors

## Alternatives Considered

### A: Patch oref0-JS to disable inline continuance

Modify the JS source to always go through setTempBasal.

**Rejected because**: We'd be modifying the reference implementation,
defeating the purpose of testing against canonical behavior.

### B: Inject continuance-disabling flags

Add a profile flag like `disableContinuance: true`.

**Rejected because**: No such flag exists in oref0-JS. Would require
forking the reference. The Swift protocol approach is cleaner.

## Related

- `ContinuancePolicy.swift` in t1pal-mobile-apex
- `tools/t1pal-adapter-cli/Sources/main.swift` — uses `calculate()` not
  `calculateWithContinuance()`
- ADR-005: Cross-validation adapter protocol
- B3 backlog item: generalize-continuance
