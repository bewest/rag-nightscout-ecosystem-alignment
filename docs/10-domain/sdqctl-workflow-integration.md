# sdqctl Workflow Integration Guide

## Overview

This guide documents how to use `sdqctl` idiomatically across the Nightscout ecosystem alignment workflows. The goal is standardized verification, consistent patterns, and reduced friction for contributors.

## sdqctl Capabilities

| Command | Purpose | Example |
|---------|---------|---------|
| `run` | Execute single prompt or .conv | `sdqctl run workflows/verify-refs.conv` |
| `iterate` | Multi-cycle execution | `sdqctl iterate workflows/backlog-cycle-v2.conv -n 5` |
| `flow` | Batch/parallel workflows | `sdqctl flow workflows/verify-*.conv --parallel 4` |
| `apply` | Apply to multiple components | `sdqctl apply workflow.conv --components "lib/*.js"` |
| `status` | Session and system status | `sdqctl status` |

## Verification Workflows

### Individual Checks

```bash
# Reference validation (file:line links)
sdqctl run workflows/verify-refs.conv

# Coverage analysis (requirements ↔ scenarios)
sdqctl run workflows/verify-coverage.conv

# Terminology consistency
sdqctl run workflows/verify-terminology.conv

# Assertion tracing (claims ↔ requirements)
sdqctl run workflows/verify-assertions.conv
```

### Full Verification Suite

```bash
# Run all checks (equivalent to make verify)
sdqctl run workflows/full-verification.conv

# Or parallel execution
sdqctl flow workflows/verify-*.conv --parallel 4
```

## Backlog Cycle Execution

### Single Cycle

```bash
sdqctl iterate workflows/orchestration/backlog-cycle-v2.conv
```

### Multi-Cycle (Automated)

```bash
# Run 5 cycles
sdqctl iterate workflows/orchestration/backlog-cycle-v2.conv -n 5

# With priority guidance
sdqctl iterate workflows/orchestration/backlog-cycle-v2.conv \
  --prologue "Prioritize: CGM protocol analysis"
```

### Verbosity Levels

| Flag | Level | Shows |
|------|-------|-------|
| (none) | Default | Errors only |
| `-v` | INFO | Progress with context % |
| `-vv` | DEBUG | Streaming responses |
| `-vvv` | TRACE | Tool calls, reasoning |
| `-q` | Quiet | Errors only (CI mode) |

## Analysis Workflows

### Feature Comparison

```bash
sdqctl iterate workflows/analysis/compare-feature.conv \
  --var FEATURE="CGM data handling" \
  --var REPOS="xDrip+,Nightscout"
```

### Component Deep Dive

```bash
sdqctl iterate workflows/analysis/deep-dive.conv \
  --var COMPONENT="OpenAPS.swift" \
  --var REPO="Trio"
```

## CI Integration

### JSON Error Output

```bash
# For CI pipelines
sdqctl --json-errors run workflows/full-verification.conv 2>&1 | jq .

# Parse specific error
sdqctl --json-errors iterate workflow.conv 2>&1 | jq '.error // "success"'
```

### Makefile Integration

```makefile
# Recommended targets
sdqctl-verify:
	@sdqctl flow workflows/verify-*.conv --parallel 4

sdqctl-cycle:
	@sdqctl iterate workflows/orchestration/backlog-cycle-v2.conv

sdqctl-cycle-multi:
	@sdqctl iterate workflows/orchestration/backlog-cycle-v2.conv -n $(N)
```

## Pattern Replacements

### Before (Custom Python Calls)

```bash
# Old pattern in .conv files
RUN python tools/verify_refs.py
RUN python tools/verify_coverage.py
```

### After (Idiomatic sdqctl)

```bash
# New pattern - delegate to workflow
# Instead of inline RUN, use CONTEXT and let sdqctl orchestrate

CONTEXT @tools/verify_refs.py
PROMPT Run reference validation using the verify_refs.py tool.
```

Or better, compose workflows:

```yaml
# In backlog-cycle-v2.conv Phase 3
INCLUDE workflows/verify-refs.conv
```

## Session Management

### Check Status

```bash
sdqctl status
# Shows: version, auth, sessions, checkpoints, adapters
```

### Session Artifacts

Sessions are stored at `~/.sdqctl/sessions/` with:
- Conversation history
- Checkpoints
- Context state

## Best Practices

1. **Use .conv files** - Prefer declarative workflows over ad-hoc prompts
2. **Parallel verification** - Use `sdqctl flow --parallel` for independent checks
3. **Verbosity for debugging** - Use `-vv` when troubleshooting
4. **JSON for CI** - Use `--json-errors` in automated pipelines
5. **Prologue for context** - Use `--prologue` to guide multi-cycle runs

## Workflow Inventory

### Verification (4)
- `verify-refs.conv` - File reference validation
- `verify-coverage.conv` - Requirement coverage
- `verify-terminology.conv` - Term consistency
- `verify-assertions.conv` - Claim tracing

### Analysis (2)
- `compare-feature.conv` - Cross-project comparison
- `deep-dive.conv` - Component analysis

### Orchestration (2)
- `backlog-cycle.conv` - Original cycle (v1)
- `backlog-cycle-v2.conv` - Improved with git hygiene

### Generation (5)
- `gap-to-proposal.conv` - Gap → proposal
- `gen-conformance.conv` - Generate tests
- `gen-inventory.conv` - Asset inventory
- `gen-traceability.conv` - Traceability matrix
- `gen-coverage-report.conv` - Coverage report

## Related Documentation

- [LSP Verification Setup](lsp-verification-setup-requirements.md) - IDE integration
- [PR Review Protocol](nightscout-pr-review-protocol.md) - PR coherence checks
- [Known/Unknown Dashboard](../../tools/known_unknown_dashboard.py) - Project health
