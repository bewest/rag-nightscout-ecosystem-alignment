# sdqctl Traceability Workflows

Declarative workflows for automating traceability operations using [sdqctl](https://github.com/bewest/copilot-do-proposal/tree/main/sdqctl).

## Prerequisites

```bash
# Activate venv with sdqctl
source activate-sdqctl.sh
```

## Workflow Categories

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
| `deep-dive-template.conv` | Template for 5-facet analysis |

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

CONTEXT @traceability/requirements.md
CONTEXT @traceability/gaps.md
CONTEXT @tools/verify_refs.py

PROMPT Validate all code references in requirements and gaps.

OUTPUT-FORMAT markdown
OUTPUT-FILE traceability/refs-validation.md
```

See [sdqctl documentation](https://github.com/bewest/copilot-do-proposal/tree/main/sdqctl) for full directive reference.
