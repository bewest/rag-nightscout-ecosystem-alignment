# OpenAPSSwift Parity Testing

> **Purpose**: Validate that Trio-dev's native Swift oref implementation produces equivalent outputs to the JavaScript reference  
> **Gap Reference**: [GAP-TRIO-SWIFT-001](../../../traceability/aid-algorithms-gaps.md)  
> **Created**: 2026-01-31

## Overview

Trio-dev contains two parallel oref implementations:
1. **JavaScript** (`trio-oref/lib/`) - Reference implementation via JavaScriptCore
2. **Swift** (`Trio/Sources/APS/OpenAPSSwift/`) - Native Swift port

This test suite validates parity between them.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Parity Test Framework                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐         ┌──────────────────┐             │
│  │  Test Vector │────────▶│  JS Runner       │──┐          │
│  │  (JSON)      │         │  (Node.js)       │  │          │
│  └──────────────┘         └──────────────────┘  ▼          │
│         │                                    ┌─────────┐    │
│         │                                    │ Compare │    │
│         │                                    │ Engine  │    │
│         │                                    └─────────┘    │
│         ▼                 ┌──────────────────┐  ▲          │
│  ┌──────────────┐         │  Swift Runner    │──┘          │
│  │  Test Vector │────────▶│  (swiftc/xctest) │             │
│  │  (JSON)      │         └──────────────────┘             │
│  └──────────────┘                                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Test Vector Schema

Each test vector captures a complete algorithm invocation:

```json
{
  "id": "vector-001",
  "description": "High BG with active IOB",
  "function": "determineBasal",
  "inputs": {
    "glucose_status": {...},
    "currenttemp": {...},
    "iob_data": [...],
    "profile": {...},
    "autosens_data": {...},
    "meal_data": {...},
    "microBolusAllowed": true,
    "reservoir_data": null,
    "clock": "2026-01-31T12:00:00.000Z"
  },
  "expected_outputs": {
    "rate": 2.5,
    "duration": 30,
    "reason": "...",
    "COB": 25,
    "IOB": 1.2,
    "eventualBG": 135,
    "tolerance": {
      "rate": 0.01,
      "duration": 0,
      "eventualBG": 1
    }
  }
}
```

## Functions Under Test

| Function | JS Entry | Swift Entry | Priority |
|----------|----------|-------------|----------|
| `iob` | `iob/index.js:generate()` | `IobGenerator.generate()` | P1 |
| `meal` | `meal/total.js:generate()` | `MealGenerator.generate()` | P1 |
| `autosense` | `autosens.js:generate()` | `AutosensGenerator.generate()` | P1 |
| `makeProfile` | `profile/index.js:generate()` | `ProfileGenerator.generate()` | P2 |
| `determineBasal` | `determine-basal.js:determine_basal()` | `DetermineBasalGenerator.generate()` | P1 |

## Comparison Tolerances

Floating-point differences are expected due to:
- JavaScript uses double precision, Swift uses Decimal
- Date/time parsing edge cases
- Rounding at different stages

**Default Tolerances**:
| Output Type | Tolerance | Notes |
|-------------|-----------|-------|
| Insulin rates | ±0.01 U/hr | Pump delivery precision |
| Duration | 0 minutes | Exact match required |
| BG predictions | ±1 mg/dL | Acceptable clinical variance |
| IOB/COB | ±0.01 | Algorithmic precision |
| Timestamps | ±1000ms | Parsing variance |

## Test Categories

### 1. Unit Parity Tests

Compare individual function outputs:

```yaml
# conformance/scenarios/openapsswift-parity/iob-parity.yaml
name: IOB Calculation Parity
function: iob
vectors:
  - id: iob-001
    description: Single recent bolus
    inputs:
      treatments: [{eventType: "Bolus", insulin: 5.0, timestamp: "..."}]
      profile: {dia: 6, peak: 75}
    assertions:
      - js_output.iob == swift_output.iob ± 0.01
      - js_output.activity == swift_output.activity ± 0.001
```

### 2. Integration Parity Tests

End-to-end determineBasal comparison:

```yaml
name: Full Loop Cycle Parity
function: determineBasal
vectors:
  - id: loop-001
    description: Normal operation - steady BG
    inputs: {...}  # Full input set
    assertions:
      - js.rate == swift.rate ± 0.01
      - js.reason contains swift.reason_keywords
      - js.deliverAt == swift.deliverAt ± 1s
```

### 3. Edge Case Tests

Known divergence scenarios:

| Case | Description | Risk |
|------|-------------|------|
| DynamicISF sigmoid maxLimit=1 | Division edge case | **HIGH** (GAP-TRIO-SWIFT-002) |
| Zero TDD | Division by zero handling | Medium |
| Negative IOB | Float precision | Low |
| Stale CGM | >15min without reading | Medium |

## Implementation Plan

### Phase 1: Vector Extraction (This Cycle)
- [x] Define test vector schema
- [x] Identify functions under test
- [ ] Extract 10 sample vectors from AAPS replay tests
- [ ] Adapt to Trio input format

### Phase 2: JS Runner
- [ ] Create `openapsswift-js-runner.js`
- [ ] Accept JSON input, output JSON result
- [ ] Run against trio-oref/lib/ bundles

### Phase 3: Swift Runner (macOS Only)
- [ ] Create `openapsswift-swift-runner.swift`
- [ ] Compile as standalone CLI
- [ ] Mirror JS runner interface

### Phase 4: Comparison Engine
- [ ] Create `parity_compare.py`
- [ ] Apply tolerances
- [ ] Generate diff report

## Integration with Existing Infrastructure

This extends the existing conformance framework:

```
conformance/
├── vectors/
│   └── oref0/                    # Existing AAPS-extracted vectors
├── runners/
│   └── oref0-runner.js           # Existing JS runner
└── scenarios/
    ├── algorithm-conformance/    # Existing oref0 tests
    └── openapsswift-parity/      # NEW: JS vs Swift comparison
        ├── README.md             # This file
        ├── vectors/              # Trio-specific test vectors
        ├── js-runner.js          # JS side
        └── swift-runner.swift    # Swift side
```

## Success Criteria

| Metric | Target | Current |
|--------|--------|---------|
| Functions covered | 5/5 | 0/5 |
| Test vectors | 50+ | 0 |
| Pass rate (iob) | >99% | N/A |
| Pass rate (determineBasal) | >95% | N/A |
| Known divergences documented | 100% | 1 (DynamicISF) |

## Known Divergences

### GAP-TRIO-SWIFT-002: DynamicISF Sigmoid Edge Case

**Location**: `DynamicISF.swift:88-89`

```swift
// Bug: When maxLimit == 1, autosensInterval = 0
let autosensInterval = maxLimit - minLimit  // Could be 0
let exponent = bgDev * preferences.adjustmentFactorSigmoid * tddFactor + fixOffset
newRatio = autosensInterval / (1 + Decimal.exp(-exponent)) + minLimit
// If autosensInterval = 0, result is always minLimit regardless of BG
```

**JS Behavior**: Same logic, same bug potential

**Remediation**: Add guard: `if maxLimit <= minLimit { return minLimit }`

## References

- [Trio Comprehensive Analysis](../../../docs/10-domain/trio-comprehensive-analysis.md)
- [Cross-Platform Testing Research](../../../docs/10-domain/cross-platform-testing-research.md)
- [GAP-TRIO-SWIFT-001](../../../traceability/aid-algorithms-gaps.md)
