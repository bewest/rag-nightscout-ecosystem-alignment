# Test Harness — Layered Algorithm Testing

Cross-language, layered testing harness for the Nightscout AID ecosystem.
Tests algorithm **equivalence**, **benchmarking**, and **R&D** across
JS, Swift, and Kotlin implementations.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: R&D / Research                                    │
│  Agent effect injection, mutation proposals, sandbox         │
│  node harness.js --layer research --agents exercise          │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Algorithm Benchmarking                            │
│  Cross-algorithm comparison, divergence measurement          │
│  node harness.js --layer benchmark --adapters a,b            │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Algorithm Equivalence                             │
│  Same-algorithm cross-implementation testing                 │
│  node harness.js --layer equivalence --adapters a,b          │
├─────────────────────────────────────────────────────────────┤
│  Layer 0: Validation                                        │
│  Schema compliance, adapter health, input assembly           │
│  node harness.js --layer validate                            │
└─────────────────────────────────────────────────────────────┘
```

## The Adapter Protocol

Each algorithm implementation is wrapped as an **adapter** — a CLI process
that speaks JSON over stdio:

```
stdin → { mode, input } → [Adapter Process] → { output } → stdout
```

### Adapter Modes

| Mode | Description |
|------|-------------|
| `execute` | Run algorithm, return normalized output |
| `validate-input` | Show native input translation (for debugging) |
| `describe` | Return adapter capabilities |

### Adapter Contract

**Input** (`contracts/adapter-input.schema.json`):
- Superset of TV-\* conformance vector `input` format
- Base fields: `glucoseStatus`, `iob`, `profile`, `mealData`, `currentTemp`
- Extension fields: `glucoseHistory`, `doseHistory`, `effectModifiers`

**Output** (`contracts/adapter-output.schema.json`):
- Normalized across all algorithms
- `decision`: rate, duration, smb, reason
- `predictions`: eventualBG, minPredBG, iob[], zt[], cob[], uam[]
- `state`: iob, cob, bg, insulinReq

### Solving the Conflation Problem

When tests fail, the **validate-input** mode reveals whether the failure
is from input assembly or algorithm logic:

```
# See what the adapter actually passes to the algorithm
echo '{"mode":"validate-input","input":{...}}' | node adapters/oref0-js/index.js
→ { "nativeInput": {...}, "fieldMapping": {...}, "warnings": [...] }
```

## Quick Start

```bash
cd tools/test-harness
npm install

# Layer 0: validate everything works
node harness.js --layer validate

# Layer 1: test oref0-js against expected outputs
node harness.js --layer equivalence --limit 10

# Layer 1: cross-implementation equivalence (when 2+ adapters exist)
node harness.js --layer equivalence \
  --adapters adapters/oref0-js,adapters/t1pal-oref0-swift

# Layer 2: benchmark different algorithms
node harness.js --layer benchmark \
  --adapters adapters/oref0-js,adapters/loop-swift

# Layer 3: test with agent effects
node harness.js --layer research --agents exercise --limit 5
node harness.js --layer research --agents breakfast-boost,illness
```

## Directory Structure

```
tools/test-harness/
├── harness.js                  # CLI orchestrator
├── package.json
├── contracts/
│   ├── adapter-input.schema.json    # Input contract (JSON Schema)
│   ├── adapter-output.schema.json   # Output contract (JSON Schema)
│   └── adapter-manifest.schema.json # Adapter metadata schema
├── lib/
│   ├── adapter-protocol.js     # Load, invoke, validate adapters
│   ├── vector-loader.js        # Load TV-* conformance vectors
│   ├── output-comparator.js    # Tolerance-based comparison
│   └── report.js               # Human/JSON report formatting
├── adapters/
│   ├── oref0-js/               # ✅ Working JS oref0 adapter
│   │   ├── manifest.json
│   │   └── index.js
│   └── t1pal-oref0-swift/      # 🔧 Swift adapter scaffold
│       ├── manifest.json
│       └── bridge.sh
├── layers/
│   ├── validate.js             # L0: Schema + adapter health
│   ├── equivalence.js          # L1: Cross-implementation testing
│   ├── benchmark.js            # L2: Cross-algorithm comparison
│   └── research.js             # L3: R&D with agent effects
└── scoring/                    # Python scoring (future)
```

## Writing a New Adapter

1. Create a directory under `adapters/` with a `manifest.json`:

```json
{
  "name": "my-algorithm",
  "algorithm": "oref0",
  "language": "swift",
  "invoke": { "command": "swift run MyAdapterCLI" },
  "capabilities": { "predictions": true, "smb": false },
  "modes": ["execute", "validate-input", "describe"]
}
```

2. Implement a CLI tool that:
   - Reads `{"mode":"execute","input":{...}}` from stdin
   - Translates adapter input → native algorithm input
   - Runs the algorithm
   - Translates native output → adapter output format
   - Writes JSON to stdout

3. Test it:

```bash
node harness.js --layer validate --adapters adapters/my-algorithm
node harness.js --layer equivalence --adapters adapters/oref0-js,adapters/my-algorithm
```

## Agent Presets (Layer 3)

| Preset | Effect | Use Case |
|--------|--------|----------|
| `exercise` | ISF×1.2, Basal×0.5 | During exercise |
| `post-exercise` | ISF×0.7, Basal×0.8 | Post-exercise sensitivity |
| `breakfast-boost` | ISF×1.3, CR×0.85, Basal×1.2 | Dawn phenomenon |
| `illness` | ISF×1.5, Basal×1.3 | Sick day management |

Custom modifiers can be passed as JSON objects.

## Integration with Makefile

```bash
make harness-validate     # Layer 0
make harness-equivalence  # Layer 1
make harness-benchmark    # Layer 2
make harness-research     # Layer 3
```
