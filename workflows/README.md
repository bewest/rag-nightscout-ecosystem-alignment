# sdqctl Traceability Workflows

Declarative workflows for automating traceability operations using [sdqctl](https://github.com/bewest/copilot-do-proposal/tree/main/sdqctl).

## Prerequisites

```bash
# Activate venv with sdqctl
source activate-sdqctl.sh
```

## Workflow Categories

### Discovery Workflows (NEW)

Located in `discovery/`:

| Workflow | Purpose |
|----------|---------|
| `discovery/component-discovery.conv` | Find and catalog components in repos |
| `discovery/terminology-extraction.conv` | Extract terms from source code |
| `discovery/gap-discovery.conv` | Identify undocumented gaps |
| `discovery/cross-project-diff.conv` | Compare implementations across repos |

### Design Workflows (NEW)

Located in `design/`:

| Workflow | Purpose |
|----------|---------|
| `design/deep-dive-template.conv` | 5-facet component analysis template |
| `design/requirement-extraction.conv` | Convert gaps to formal requirements |
| `design/spec-generation.conv` | Generate OpenAPI specs from requirements |
| `design/conformance-scenario.conv` | Create conformance test scenarios |

### Iteration Workflows (NEW)

Located in `iterate/`:

| Workflow | Purpose |
|----------|---------|
| `iterate/progress-update.conv` | Update progress.md with session log |
| `iterate/facet-refresh.conv` | Refresh all 5 facets for a component |
| `iterate/verification-loop.conv` | Continuous verification cycle |

### Integration Workflows (NEW)

Located in `integrate/`:

| Workflow | Purpose |
|----------|---------|
| `integrate/tool-validation.conv` | Run Python tools, analyze results |
| `integrate/ci-pipeline.conv` | Full CI pipeline with RUN commands |

### Verification Workflows

| Workflow | Purpose | Equivalent |
|----------|---------|------------|
| `verify-refs.conv` | Validate code references resolve | `make verify-refs` |
| `verify-coverage.conv` | Analyze REQ/GAP coverage | `make verify-coverage` |
| `verify-terminology.conv` | Check terminology consistency | `make verify-terminology` |
| `verify-assertions.conv` | Trace assertions to requirements | `make verify-assertions` |

### Generation Workflows

| Workflow | Purpose | Equivalent |
|----------|---------|------------|
| `gen-inventory.conv` | Generate workspace inventory | `make inventory` |
| `gen-traceability.conv` | Build traceability matrix | `make traceability` |
| `gen-coverage-report.conv` | Coverage matrix with gaps | `make coverage` |

### Analysis Workflows

| Workflow | Purpose |
|----------|---------|
| `gap-detection.conv` | Identify missing requirements/coverage |
| `cross-project-alignment.conv` | Compare implementations across repos |

### Composite Workflows

| Workflow | Purpose | Equivalent |
|----------|---------|------------|
| `full-verification.conv` | All verification steps | `make verify` |
| `ci-pipeline.conv` | Full CI pipeline | `make ci` |
| `faceted-analysis.conv` | 5-facet documentation update | - |

## Usage

```bash
# Run single workflow
sdqctl run workflows/verify-refs.conv

# Run all verification workflows
sdqctl flow workflows/verify-*.conv

# Run all generation workflows
sdqctl flow workflows/gen-*.conv --parallel 3

# Multi-cycle analysis with compaction
sdqctl cycle workflows/gap-detection.conv --max-cycles 3

# Discovery with fresh session mode (sees file changes between cycles)
sdqctl cycle workflows/discovery/component-discovery.conv -n 3 --session-mode fresh

# Apply a workflow to multiple components
sdqctl apply workflows/design/deep-dive-template.conv \
  --components "mapping/*/README.md" \
  --progress progress.md
```

## Validation Modes

All workflows now support lenient validation for aspirational patterns:

```bash
# Validate with lenient mode
sdqctl validate workflows/*.conv --allow-missing

# Or workflows include VALIDATION-MODE lenient
```

## Makefile Integration

```bash
make sdqctl-verify    # Run all verification workflows
make sdqctl-gen       # Run all generation workflows
```

## ConversationFile Format

Each `.conv` file uses a Dockerfile-like syntax:

```dockerfile
# verify-refs.conv - Validate code references
MODEL claude-sonnet-4
ADAPTER copilot
MODE verification
MAX-CYCLES 1
VALIDATION-MODE lenient

CONTEXT @traceability/requirements.md
CONTEXT @traceability/gaps.md
CONTEXT-OPTIONAL @conformance/scenarios/**/*.yaml

PROMPT Validate all code references in requirements and gaps.

OUTPUT-FORMAT markdown
OUTPUT-FILE traceability/refs-validation.md
```

See [sdqctl documentation](https://github.com/bewest/copilot-do-proposal/tree/main/sdqctl) for full directive reference.

## Documentation

- [NIGHTSCOUT-SDQCTL-GUIDE.md](../docs/NIGHTSCOUT-SDQCTL-GUIDE.md) - Full guide for using sdqctl with this workspace
- [CONTINUATION-PROMPTS.md](../docs/CONTINUATION-PROMPTS.md) - Ready-to-use prompts for continuing work
