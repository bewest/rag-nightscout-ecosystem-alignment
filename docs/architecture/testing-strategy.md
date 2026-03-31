# Cross-Validation Testing Strategy

## Overview

This document describes the testing strategy for verifying algorithm equivalence
across implementations. The system uses a **4-layer validation pyramid** with
increasing scope and cost.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Conformance Vectors                        │
│  conformance/t1pal/vectors/oref0-endtoend/TV-*.json          │
│  100 vectors: 78 natural (real phone runs) + 22 synthetic    │
└────────────────┬────────────────────────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │   Adapter Protocol      │
    │   JSON-over-stdio       │
    │   (ADR-005)             │
    └────────────┬────────────┘
                 │
    ┌────────────┼────────────┬────────────────┐
    ▼            ▼            ▼                ▼
┌─────────┐ ┌─────────┐ ┌──────────┐  ┌───────────┐
│ oref0-js│ │ aaps-js │ │t1pal-    │  │ (future)  │
│ Node.js │ │ Node.js │ │swift     │  │ trio-js   │
│         │ │         │ │ SPM      │  │ loop-swift│
└─────────┘ └─────────┘ └──────────┘  └───────────┘
    │            │            │
    └────────────┼────────────┘
                 ▼
    ┌────────────────────────┐
    │   Comparison Engine    │
    │   output-comparator.js │
    │   prediction-alignment │
    └────────────────────────┘
```

## Validation Layers

### Layer 0: Infrastructure Validation (`make harness-validate`)

Verifies the test infrastructure itself:
- Vector schema conformance (all TV-*.json match schema)
- Adapter health checks (each adapter responds to `describe` mode)
- Input assembly correctness (`validate-input` mode)

**When to run**: After changing adapters, schemas, or vector format.

### Layer 1: Equivalence Testing (`make harness-equivalence`)

Same-algorithm cross-implementation comparison:
- oref0-JS vs oref0-Swift on 100 vectors
- EventualBG match, rate agreement, prediction curve MAE

**When to run**: After any algorithm code change in t1pal-mobile-apex.

### Layer 2: Cross-Algorithm Benchmarking (`make harness-benchmark`)

Different algorithms on same inputs:
- oref0 vs Loop vs GlucOS on shared vectors
- Documents expected behavioral differences

**When to run**: When adding new algorithms or comparing approaches.

### Layer 3: Research (`make harness-research`)

Exploratory testing with input mutation:
- Parameter sweeps (vary ISF, CR, target)
- Agent effect injection (effectModifiers)
- Edge case generation

**When to run**: During algorithm development and research.

## Quick Reference: Make Targets

| Target | Time | Scope |
|--------|------|-------|
| `make xval-smoke` | ~30s | 10 vectors, JS↔Swift |
| `make aaps-smoke` | ~5s | 10 vectors, JS↔AAPS |
| `make three-way-smoke` | ~30s | 10 vectors, JS↔AAPS↔Swift |
| `make xval-validate` | ~3min | 100 vectors, JS↔Swift |
| `make aaps-xval` | ~10s | 100 vectors, JS↔AAPS |
| `make three-way-xval` | ~3min | 100 vectors, JS↔AAPS↔Swift |
| `make loop-xval` | ~5min | 100 vectors, Loop-C↔Loop-T↔oref0 |
| `make loop-smoke` | ~30s | 10 vectors, Loop-C↔Loop-T↔oref0 |
| `make harness-quick` | ~1min | L0 + L1 (10 vectors) |
| `make harness-ci` | ~10min | Full pipeline |

## Metrics and Tolerances

### Default Tolerances (from `lib/output-comparator.js`)

| Metric | Tolerance | Rationale |
|--------|-----------|-----------|
| Rate | ±0.05 U/hr | Pump precision (round_basal step) |
| EventualBG | ±10 mg/dL | Floating-point accumulation over 48 ticks |
| IOB | ±0.01 U | Exponential model precision |
| Prediction MAE | <2.0 mg/dL | Acceptable curve drift |

### Current Achievement (Phase 3 Complete — 2026-03-31)

**3-Way Cross-Implementation Validation** (300 vectors: 100 oref0-native + 200 Loop-derived):

| Vector Suite | EventualBG | Rate ±0.5 | IOB MAE |
|-------------|------------|-----------|---------|
| oref0-native (100) | **100/100 (100%)** | **72/72 (100%)** | **0.005** |
| Loop-derived (200) | **194/195 (99.5%)** | **131/133 (98.5%)** | **0.028** |
| **Combined (300)** | **294/295 (99.7%)** | **201/203 (99.0%)** | — |

All 3 adapters (oref0-JS, t1pal-Swift, AAPS-JS) agree on decisions.

**All 4 Prediction Curves Aligned** (JS ↔ Swift, avg MAE in mg/dL):

| Curve | Avg MAE | Max MAE | Status |
|-------|---------|---------|--------|
| IOB | 0.005 | 0.08 | ✅ |
| ZT | 0.013 | 0.12 | ✅ |
| COB | 0.000 | 0.00 | ✅ |
| UAM | 0.002 | 0.085 | ✅ |

## Adding a New Adapter

1. Create directory: `tools/test-harness/adapters/<name>/`
2. Create `manifest.json` following `contracts/adapter-manifest.schema.json`
3. Implement the adapter (read stdin JSON, write stdout JSON)
4. Test with `echo '{"mode":"describe"}' | <command>`
5. Add to cross-validation scripts

### Adapter Output Contract

```json
{
  "algorithm": { "name": "oref0-js", "version": "0.2.1" },
  "decision": {
    "rate": 1.5,
    "duration": 30,
    "reason": "..."
  },
  "predictions": {
    "eventualBG": 120,
    "iob": [120, 119, 118, ...],
    "zt": [120, 119.5, ...],
    "cob": [120, 121, ...],
    "uam": [120, 118, ...]
  },
  "state": {
    "insulinReq": 0.5,
    "minPredBG": 90,
    "minGuardBG": 95
  }
}
```

## Convergence Loop

The autonomous convergence loop (`tools/test-harness/convergence-loop.js`)
drives accuracy improvement:

1. **Run** all adapters on all vectors
2. **Compare** outputs, classify divergence
3. **Isolate** which component diverges (IOB? predictions? guard?)
4. **Diagnose** via parameter mutation
5. **Report** gap entries and regression vectors
6. **Iterate** until convergence targets met

This drove Phase 2 from 5% to 90% (7 cycles), then Phase 3 to 99.7% (9 cycles)
with full prediction curve alignment across all 4 oref0 trajectories.

## Vector Format

Vectors in `conformance/t1pal/vectors/oref0-endtoend/TV-*.json`:

```json
{
  "metadata": { "id": "TV-001", "category": "basal-adjustment" },
  "input": {
    "glucoseStatus": { "glucose": 120, "delta": -2, ... },
    "iob": { "iob": 1.5, "activity": 0.01, ... },
    "profile": { "basalRate": 1.0, "sensitivity": 50, ... },
    "mealData": { "carbs": 0, ... },
    "currentTemp": { "rate": 0, "duration": 0 }
  },
  "originalOutput": {
    "rate": 1.5,
    "reason": "...",
    "predBGs": { "IOB": [...], "ZT": [...] }
  }
}
```

The `originalOutput.predBGs` arrays are ground-truth prediction trajectories
captured from real phone algorithm runs.
