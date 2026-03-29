# Cross-Validation Harness Architecture

> Verifying that different implementations of the same dosing algorithm
> produce the same outputs given the same inputs.

## Problem

The Nightscout AID ecosystem has multiple implementations of the same
algorithms across languages:

| Algorithm | JavaScript | Swift | Kotlin |
|-----------|-----------|-------|--------|
| **oref0** | `externals/oref0/` | `t1pal-mobile-apex` DetermineBasal.swift | `externals/AndroidAPS/` DetermineBasalSMB.kt |
| **oref1** | `externals/oref0/` (SMB mode) | `t1pal-mobile-apex` Oref1Algorithm.swift | `externals/AndroidAPS/` DetermineBasalAutoISF.kt |
| **Loop** | — | `externals/LoopWorkspace/` LoopAlgorithm.swift | — |
| **Loop (t1pal)** | — | `t1pal-mobile-apex` LoopAlgorithm.swift | — |

We need to verify:
1. **IOB curves** match across implementations (most common divergence source)
2. **Prediction trajectories** (predBGs) match point-by-point
3. **Dosing decisions** (rate, duration, SMB) agree within tolerance
4. **Safety guards** (low glucose suspend, max basal) trigger identically

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    Cross-Validation Harness                       │
│                                                                  │
│  ┌─────────────┐   ┌──────────────┐   ┌───────────────────────┐ │
│  │ Vector Store │   │  Harness.js  │   │   Output Comparator   │ │
│  │ conformance/ │──▶│  4 layers    │──▶│  5-level divergence   │ │
│  │ 185 vectors  │   │  orchestrate │   │  IOB/pred/dose split  │ │
│  └─────────────┘   └──────┬───────┘   └───────────────────────┘ │
│                           │                                      │
│              ┌────────────┼────────────┐                         │
│              ▼            ▼            ▼                          │
│     ┌──────────────┐ ┌────────────┐ ┌──────────────┐            │
│     │  oref0-js    │ │ t1pal-swift│ │ aaps-kotlin  │            │
│     │  Adapter     │ │ Adapter    │ │ Adapter      │            │
│     │  (working)   │ │ (built)    │ │ (planned)    │            │
│     └──────┬───────┘ └─────┬──────┘ └──────┬───────┘            │
│            │               │               │                     │
│     JSON-over-stdio  JSON-over-stdio  JSON-over-stdio            │
│            │               │               │                     │
│     ┌──────▼───────┐ ┌────▼───────┐ ┌─────▼────────┐            │
│     │ oref0 JS lib │ │T1PalAlgo   │ │ AAPS Kotlin  │            │
│     │ externals/   │ │5 algorithms│ │ DetermineB.  │            │
│     └──────────────┘ └────────────┘ └──────────────┘            │
└──────────────────────────────────────────────────────────────────┘
```

## Adapter Protocol

Every algorithm implementation is wrapped in an **adapter** — a CLI
process that speaks JSON over stdin/stdout.

### Request (stdin)

```json
{
  "mode": "execute | validate-input | describe",
  "algorithm": "oref0",
  "input": {
    "clock": "2024-01-15T10:30:00Z",
    "glucoseStatus": { "glucose": 150, "delta": 3, "shortAvgDelta": 2.5, "longAvgDelta": 1.8 },
    "iob": { "iob": 2.5, "activity": 0.05, "basalIob": 1.2, "bolusIob": 1.3 },
    "profile": {
      "basalRate": 1.0, "sensitivity": 50, "carbRatio": 10,
      "targetLow": 100, "targetHigh": 110, "maxIob": 8, "maxBasal": 4,
      "dia": 6, "maxDailyBasal": 1.5, "enableSMB": true, "enableUAM": true
    },
    "mealData": { "carbs": 0, "cob": 15 },
    "currentTemp": { "rate": 0.5, "duration": 20 },
    "autosensData": { "ratio": 1.0 }
  }
}
```

### Response (stdout)

```json
{
  "algorithm": { "name": "oref0-js", "version": "0.7.1" },
  "decision": { "rate": 1.5, "duration": 30, "smb": null, "reason": "..." },
  "predictions": {
    "eventualBG": 135, "minPredBG": 95,
    "iob": [150, 148, 145, ...],
    "zt": [150, 152, 155, ...],
    "cob": [150, 147, 143, ...],
    "uam": [150, 149, 147, ...]
  },
  "state": { "iob": 2.5, "cob": 15, "bg": 150, "tick": "+", "insulinReq": 0.8 },
  "metadata": { "executionTimeMs": 12 }
}
```

### Three Modes

| Mode | Purpose | When to Use |
|------|---------|-------------|
| `execute` | Run algorithm, return decision + predictions | Normal testing |
| `validate-input` | Show native input WITHOUT executing | Debug input assembly failures |
| `describe` | Return capabilities (no input needed) | Adapter discovery |

### Manifest (`manifest.json`)

Each adapter directory contains a manifest:

```json
{
  "name": "oref0-js",
  "algorithm": "oref0",
  "language": "javascript",
  "invoke": { "command": "node index.js" },
  "capabilities": { "predictions": true, "smb": true },
  "modes": ["execute", "validate-input", "describe"]
}
```

### Contracts

JSON Schemas at `tools/test-harness/contracts/`:
- `adapter-input.schema.json` — input validation
- `adapter-output.schema.json` — output validation
- `adapter-manifest.schema.json` — manifest validation

## Harness Layers

The test harness (`tools/test-harness/harness.js`) runs 4 progressive layers:

### Layer 0: VALIDATE
- Schema compliance for inputs and outputs
- Adapter health checks (describe mode)
- Input assembly verification (validate-input mode)
- **Purpose**: Catch contract violations before algorithm differences

### Layer 1: EQUIVALENCE
- Run **same algorithm, different implementations** on identical vectors
- e.g., oref0-js vs t1pal-oref0-swift
- Compare outputs with tolerance-based matching
- **Purpose**: Verify ports are faithful

### Layer 2: BENCHMARK
- Run **different algorithms** on identical vectors
- e.g., oref0 vs Loop vs GlucOS
- Divergence matrix showing where algorithms agree/disagree
- **Purpose**: Understand algorithm behavioral differences

### Layer 3: RESEARCH
- Inject effect modifiers (exercise, illness, dawn phenomenon)
- Parameter mutation to explore sensitivity
- Agent-based exploration
- **Purpose**: R&D, safety analysis, parameter optimization

## Available Adapters

### 1. oref0-js (Working)

**Location**: `tools/test-harness/adapters/oref0-js/`

Wraps `externals/oref0/lib/determine-basal`. Key behavior:
- Generates 48-element IOB projection array (tau = DIA/1.85)
- Maps adapter protocol fields → oref0 native format
- Returns 4 prediction curves (IOB, COB, UAM, ZT)

```bash
echo '{"mode":"describe"}' | node tools/test-harness/adapters/oref0-js/index.js
```

### 2. t1pal-swift (Built, Multi-Algorithm)

**Location**: `tools/test-harness/adapters/t1pal-oref0-swift/` (manifest)
**Implementation**: `tools/t1pal-adapter-cli/` (Swift CLI)

Wraps `t1pal-mobile-apex` AlgorithmRegistry with 5 algorithms:
- oref0, oref1, Loop-Community, Loop-Tidepool, GlucOS
- Select algorithm via `"algorithm"` field in request
- Full predictions, SMB, effect modifier support

```bash
cd tools/t1pal-adapter-cli && swift build
echo '{"mode":"describe","algorithm":"oref0"}' | .build/debug/T1PalAdapterCLI
```

### 3. aaps-kotlin (Planned)

**Location**: `tools/test-harness/adapters/aaps-kotlin/` (to be created)

Would wrap `externals/AndroidAPS` DetermineBasalSMB.kt.
Challenge: Kotlin requires JVM + gradle build.

## Test Vectors

### Format

Each vector is a JSON file with:
```json
{
  "metadata": { "id": "TV-001", "category": "basal-adjustment", "source": "captured" },
  "input": { /* adapter-input fields */ },
  "expected": { "rate": 1.5, "eventualBG": 135, "iob": 2.5 },
  "originalOutput": { /* captured raw output including predBGs */ },
  "assertions": [{ "field": "rate", "op": "within", "value": 1.5, "tolerance": 0.05 }]
}
```

### Collections

| Collection | Location | Count | Source |
|------------|----------|-------|--------|
| Conformance | `conformance/vectors/` | 85 | oref0 fixtures |
| T1Pal End-to-End | `conformance/t1pal/vectors/oref0-endtoend/` | 100 | Captured phone runs |
| T1Pal Apex Fixtures | `../t1pal-mobile-apex/Tests/Fixtures/oref0-vectors/` | 108 | Captured with predBGs |

### Tolerances

From `conformance/t1pal/tolerances.json`:

| Field | Tolerance | Unit |
|-------|-----------|------|
| rate | 0.05 | U/hr |
| duration | 1 | minutes |
| eventualBG | 10.0 | mg/dL |
| minPredBG | 10.0 | mg/dL |
| insulinReq | 0.05 | U |
| iob | 0.01 | U |
| cob | 1.0 | g |
| predictionMAE | 2.0 | mg/dL |

## Divergence Classification

The output comparator (`output-comparator.js`) classifies differences:

| Level | Meaning | Criteria |
|-------|---------|----------|
| **NONE** | Identical | All fields within tolerance |
| **MINOR** | Cosmetic | Reason text differs, values match |
| **MODERATE** | Numerical | Rate/BG differs but same direction |
| **SIGNIFICANT** | Behavioral | Different rate direction or SMB vs no-SMB |
| **OPPOSITE** | Safety-critical | One suspends, other increases; or opposite rate direction |

## Cross-Validation Workflows

### Quick Smoke Test
```bash
make harness-validate          # L0: schemas + adapter health
```

### oref0 Equivalence (JS vs Swift)
```bash
make xval-oref0                # L1: same vectors through both adapters
```

### IOB Curve Isolation
```bash
make xval-iob                  # Compare ONLY IOB curves across implementations
```

### Full Cross-Validation
```bash
make xval-full                 # All layers, all adapters, all vectors
```

### Autonomous Convergence
```bash
make xval-converge             # Run convergence loop until stable
```

## IOB Curve Isolation

The most common source of divergence is the IOB calculation. The
`iob-isolation` harness extracts and compares ONLY the IOB curve:

```
For each test vector:
  1. Extract: dose history, DIA, insulin model parameters
  2. Calculate IOB curve using each implementation
  3. Compare point-by-point (48 ticks × 5 min = 4 hours)
  4. Report: max delta, MAE, divergence onset tick
```

### Why IOB Diverges

| Source | Description | Impact |
|--------|-------------|--------|
| **Tau calculation** | `tau = peak*(1-peak/end)/(1-2*peak/end)` — floating point | Cascading prediction error |
| **IOB array generation** | JS adapter synthesizes 48-tick array from snapshot; Swift computes from dose history | Fundamentally different approaches |
| **Zero-temp projection** | Each tick needs `iobWithZeroTemp.activity` separately | Missing → minPredBG stuck at 999 |
| **Bilinear vs exponential** | Older oref0 configs use triangle model | Different curve shapes |

## Prediction Trajectory Alignment

Beyond IOB, prediction arrays should match across implementations of
the same algorithm:

```
For each of 4 curves (IOB, COB, UAM, ZT):
  1. Run both adapters on same vector
  2. Extract prediction arrays
  3. Align by time (both should be 5-min intervals)
  4. Compare point-by-point
  5. Report: MAE, max delta, correlation, divergence onset
```

### Key Metrics

| Metric | Formula | Good | Concerning |
|--------|---------|------|------------|
| **MAE** | mean(\|a[i] - b[i]\|) | < 2 mg/dL | > 5 mg/dL |
| **Max Delta** | max(\|a[i] - b[i]\|) | < 5 mg/dL | > 15 mg/dL |
| **Correlation** | pearson(a, b) | > 0.99 | < 0.95 |
| **Divergence Onset** | first tick where \|delta\| > tolerance | > 20 ticks | < 5 ticks |

## Autonomous Convergence Loop

The convergence loop connects existing tools into a continuous
improvement cycle:

```
┌─────────────────────────────────────────────────────────┐
│              Convergence Loop Orchestrator               │
│                                                         │
│  ┌──────────┐                                           │
│  │ 1. LOAD  │  Load vectors from conformance/           │
│  │  vectors │  + t1pal/vectors/ + apex fixtures          │
│  └────┬─────┘                                           │
│       ▼                                                 │
│  ┌──────────┐                                           │
│  │ 2. EXEC  │  Run each vector through ALL adapters     │
│  │  adapters│  oref0-js, t1pal-swift(oref0), etc.       │
│  └────┬─────┘                                           │
│       ▼                                                 │
│  ┌──────────┐                                           │
│  │3. COMPARE│  Output comparator → divergence level     │
│  │  results │  Per-field: IOB, predictions, decision     │
│  └────┬─────┘                                           │
│       ▼                                                 │
│  ┌──────────┐                                           │
│  │4. ISOLATE│  Which component diverges?                │
│  │  source  │  IOB? Carb absorption? Safety guard?       │
│  └────┬─────┘                                           │
│       ▼                                                 │
│  ┌──────────┐                                           │
│  │5. REPORT │  Generate:                                │
│  │  & feed  │  - Gap entries (GAP-ALG-NNN)              │
│  │  back    │  - Regression vectors for divergent cases  │
│  │          │  - Score trend (improving/regressing?)     │
│  └────┬─────┘                                           │
│       │                                                 │
│       └──────────────────────────▶ (1) next iteration   │
└─────────────────────────────────────────────────────────┘
```

### Convergence Score

Each run produces a convergence score:

```
convergence = 1 - (divergent_vectors / total_vectors)

Breakdown by component:
  iob_convergence:        % vectors where IOB within 0.01 U
  prediction_convergence: % vectors where predMAE < 2.0 mg/dL
  decision_convergence:   % vectors where rate within 0.05 U/hr
```

## Related Tools (Other Repos)

### t1pal-mobile-apex

| Tool | Purpose | Integration Point |
|------|---------|-------------------|
| `ShadowAlgorithmRunner` | Parallel algorithm execution | Powers t1pal-swift adapter |
| `Replay/Comparator` | IOB + prediction comparison | Reference for comparison logic |
| `LoopIOBParityTests` | Loop IOB verification | Test methodology to replicate |
| `AlgorithmReplayRunner` | Batch replay with divergence | Session-based validation |

### t1pal-mobile-workspace

| Tool | Purpose | Integration Point |
|------|---------|-------------------|
| `t1pal-predict-divergence` | Multi-algo divergence CLI | Can feed live Nightscout data into harness |
| `proto_common/` | Fixture schema, validation, diff | Reusable for vector management |
| `run-oref0-vectors.js` | oref0 vector runner | Simpler alternative to full harness |

## Adding a New Adapter

1. Create directory: `tools/test-harness/adapters/{name}/`
2. Add `manifest.json` (see schema above)
3. Implement the 3-mode stdin/stdout protocol
4. Build and verify: `echo '{"mode":"describe"}' | your-command`
5. Register in Makefile: add to `ADAPTERS` list
6. Run equivalence: `make harness-equivalence`

### Adapter Checklist

- [ ] `manifest.json` validates against schema
- [ ] `describe` mode returns capabilities
- [ ] `validate-input` mode shows native translation
- [ ] `execute` mode returns decision + predictions
- [ ] Output validates against `adapter-output.schema.json`
- [ ] IOB curves match reference within tolerance
- [ ] Prediction arrays present (if capabilities.predictions = true)

## Running Commands

```bash
# Prerequisite: install harness dependencies
make harness-deps

# Layer 0: Validate adapters
make harness-validate

# Layer 1: Equivalence (oref0-js vs t1pal-swift)
node tools/test-harness/harness.js --layer equivalence \
  --adapters adapters/oref0-js,adapters/t1pal-oref0-swift \
  --limit 10 --json

# IOB isolation (dedicated)
node tools/test-harness/iob-isolation.js \
  --adapters adapters/oref0-js,adapters/t1pal-oref0-swift \
  --vectors conformance/t1pal/vectors/oref0-endtoend/ \
  --json

# Prediction alignment
node tools/test-harness/prediction-alignment.js \
  --adapters adapters/oref0-js,adapters/t1pal-oref0-swift \
  --vectors conformance/t1pal/vectors/oref0-endtoend/ \
  --json

# Autonomous convergence
node tools/test-harness/convergence-loop.js \
  --adapters adapters/oref0-js,adapters/t1pal-oref0-swift \
  --max-iterations 10 \
  --target-convergence 0.95

# Full cross-validation
make xval-full

# Aid autoresearch tools
cd tools/aid-autoresearch
node run-oref0-endtoend.js                      # Score all vectors
node compare-predictions.js --json               # IOB reconstruction accuracy
node param-mutation-engine.js --strategy random   # Parameter search
node multi-algorithm-comparison.js --detail       # 5-algorithm comparison
```

## File Index

```
tools/
├── test-harness/
│   ├── harness.js                    # Main orchestrator
│   ├── lib/
│   │   ├── adapter-protocol.js       # Adapter loading, invocation, validation
│   │   ├── vector-loader.js          # Load & filter test vectors
│   │   ├── output-comparator.js      # Tolerance-based comparison
│   │   └── report.js                 # Human/JSON output formatting
│   ├── layers/
│   │   ├── validate.js               # L0: schema + health
│   │   ├── equivalence.js            # L1: same-algorithm cross-impl
│   │   ├── benchmark.js              # L2: cross-algorithm
│   │   └── research.js               # L3: agent effects + mutation
│   ├── contracts/
│   │   ├── adapter-input.schema.json
│   │   ├── adapter-output.schema.json
│   │   └── adapter-manifest.schema.json
│   ├── adapters/
│   │   ├── oref0-js/                 # ✅ Working JS adapter
│   │   └── t1pal-oref0-swift/        # ✅ Built multi-algorithm adapter
│   ├── iob-isolation.js              # IOB curve comparison (to build)
│   ├── prediction-alignment.js       # Prediction array comparison (to build)
│   └── convergence-loop.js           # Autonomous convergence (to build)
├── t1pal-adapter-cli/                # Swift CLI bridging T1PalAlgorithm
│   ├── Package.swift                 # Depends on t1pal-mobile-apex
│   └── Sources/main.swift            # JSON-over-stdio implementation
├── aid-autoresearch/
│   ├── run-oref0-endtoend.js         # Score vectors through oref0
│   ├── compare-predictions.js        # Prediction trajectory comparison
│   ├── param-mutation-engine.js      # Parameter optimization search
│   ├── multi-algorithm-comparison.js # 5-strategy comparison
│   ├── run-xval-vectors.js           # Train/test cross-validation
│   └── in-silico-bridge.js           # Virtual patient simulator
conformance/
├── vectors/                          # 85 categorized test vectors
├── t1pal/
│   ├── vectors/oref0-endtoend/       # 100 captured vectors with predBGs
│   └── tolerances.json               # Field-level tolerances
```
