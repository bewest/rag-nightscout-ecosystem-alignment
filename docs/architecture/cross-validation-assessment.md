# Cross-Implementation Algorithm Validation

**Scope**: oref0 implementations (JS, Swift, AAPS-JS, AAPS-Kotlin) + Loop  
**Vectors**: 100 oref0-native + 200 Loop-generated (300 total)

## Current State

4-way cross-implementation validation of oref0 across JS, Swift, AAPS-JS, and
AAPS-Kotlin shows full parity on eventualBG and all 4 prediction curves aligned.

### Decision Parity

| Vector Suite | Adapters | EventualBG | Rate ±0.5 |
|-------------|----------|------------|-----------|
| oref0-native (100) | JS/Swift/AAPS-JS | **100/100 (100%)** | **72/72 (100%)** |
| Loop (200) | JS/Swift/AAPS-JS | **194/195 (99.5%)** | **129/131 (98.5%)** |
| **Combined (300)** | **AAPS-JS ↔ AAPS-Kotlin** | **300/300 (100%)** | **300/300 (100%)** |

### Prediction Curve Alignment (JS ↔ Swift)

| Curve | Avg MAE (mg/dL) | Max MAE | Status |
|-------|-----------------|---------|--------|
| IOB | 0.005 | 0.154 | ✅ |
| ZT | 0.013 | 0.106 | ✅ |
| COB | 0.000 | 0.000 | ✅ |
| UAM | 0.002 | 0.085 | ✅ |

### Cross-Algorithm Pairs

| Pair | EventualBG | Rate ±0.5 | IOB MAE |
|------|------------|-----------|---------|
| oref0-JS ↔ t1pal-Swift | **100/100** | **72/72 (100%)** | **0.005** |
| oref0-JS ↔ AAPS-JS | **100/100** | **72/72 (100%)** | 0.012 |
| AAPS-JS ↔ AAPS-Kotlin | **300/300** | **300/300 (100%)** | — |
| oref0-JS ↔ t1pal-Swift (Loop) | **194/195** | **131/133 (98.5%)** | 0.028 |

Clinical dosing decisions are equivalent across all four implementations.

---

## Adapter Inventory

| Adapter | Language | Algorithm | Location | Status |
|---------|----------|-----------|----------|--------|
| oref0-js | JavaScript | Upstream oref0 | `tools/test-harness/adapters/oref0-js/` | ✅ Reference |
| t1pal-swift | Swift | T1Pal oref0 port | `tools/t1pal-adapter-cli/` | ✅ 5 algorithms |
| aaps-js | JavaScript | AAPS-modified oref0 | `tools/test-harness/adapters/aaps-js/` | ✅ |
| aaps-kotlin | Kotlin/JVM | AAPS DetermineBasalSMB.kt | `tools/test-harness/adapters/aaps-kotlin/` | ✅ |

### Supporting Infrastructure

| Component | Location |
|-----------|----------|
| IOB isolation harness | `tools/test-harness/iob-isolation.js` |
| Prediction alignment | `tools/test-harness/prediction-alignment.js` |
| Convergence loop | `tools/test-harness/convergence-loop.js` |
| AAPS cross-validation | `tools/test-harness/aaps-xval.js` |
| oref0-native vectors (100) | `conformance/t1pal/vectors/oref0-endtoend/` |
| Loop vectors (200) | `conformance/loop/vectors/` |

### Not Yet Available

| Component | Notes |
|-----------|-------|
| LoopWorkspace (native Swift) adapter | Different algorithm family |
| Trio-specific adapter | Trio's oref0 extensions (autoISF, DynISF) |
| oref1 in Swift | Not registered in AlgorithmRegistry |

---

## Methodology

### Adapter Protocol

All adapters implement JSON-over-stdio with three modes:
- **execute**: Run algorithm, return decision + predictions
- **validate-input**: Show native input translation (debugging)
- **describe**: Report capabilities and supported features

Contracts: `tools/test-harness/contracts/adapter-{input,output}.schema.json`

### Comparison Metrics

| Metric | Threshold | Description |
|--------|-----------|-------------|
| EventualBG exact | ±1 mg/dL | Primary decision input agreement |
| Rate ±0.5 | ±0.5 U/hr | Clinical dosing equivalence |
| IOB MAE | <0.05 | Insulin-on-board curve alignment |
| Prediction MAE | <0.1 mg/dL | Per-curve trajectory alignment |

### Known Differences: Upstream oref0 vs AAPS-modified oref0

| Aspect | Upstream (oref0-js) | AAPS (aaps-js, aaps-kotlin) |
|--------|---------------------|------------------------------|
| `round_basal` | Rounds to pump precision | Identity (no-op) |
| `flatBGsDetected` | Computed inline | Passed as parameter |
| aCOB curve | Not present | Added prediction curve |
| High BG SMB | Enabled | Removed |
| DynISF mode | Not present | Supported (disabled in adapter) |

These differences mean oref0-js ↔ AAPS adapters diverge on ~97% of oref0-native
vectors (expected). The meaningful comparison is AAPS-JS ↔ AAPS-Kotlin (same
algorithm, different language): **100% match on all 300 vectors**.

---

## Assessment History

17 assessments (A1–A17) document the iterative convergence from 5% to 100%
eventualBG match. See [`traceability/cross-validation-log.md`](../../traceability/cross-validation-log.md)
for the complete chronological log.

Key milestones:
- **A1–A3**: Initial assessment, 5% match → eventualBG formula fix
- **A4–A7**: Guard system, COB/activity ports → 90% eventualBG
- **A10–A12**: IOB array architecture → prediction MAE 0.005
- **A14–A15**: 3-way parity (JS/Swift/AAPS-JS) on 300 vectors
- **A16**: UAM formula alignment → all 4 curves <0.02 MAE
- **A17**: AAPS Kotlin adapter → 300/300 (100%) vs AAPS-JS

*Last updated: 2026-03-31*
