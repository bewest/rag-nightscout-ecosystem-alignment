# Tooling Guide: Enhanced Traceability and Verification

This guide describes the enhanced tooling suite for querying, tracing, and verifying documentation and test coverage in the Nightscout Alignment Workspace.

## Overview

The workspace provides comprehensive tooling to help trace documentation and tests, verify accuracy, and ensure alignment between requirements, specifications, and implementations. This tooling is designed for both **interactive use** (human developers) and **automated workflows** (AI agents, CI/CD).

## Core Tools

### 1. Query Workspace (`query_workspace.py`)

**Purpose**: Interactive and automated query interface for documentation and tests.

**Interactive Mode**:
```bash
python3 tools/query_workspace.py
# or
make cli
```

**Command Line Usage**:
```bash
# Query a requirement
python3 tools/query_workspace.py --req REQ-001

# Query a gap
python3 tools/query_workspace.py --gap GAP-SYNC-001

# Search documentation
python3 tools/query_workspace.py --search "authentication"

# Find tests for a requirement
python3 tools/query_workspace.py --tests-for REQ-001

# Find documentation for a term
python3 tools/query_workspace.py --term "basal"

# JSON output for automation
python3 tools/query_workspace.py --req REQ-001 --json
```

**Use Cases**:
- AI agents checking what tests cover a requirement
- Developers searching for documentation mentioning a specific term
- Interactive exploration of requirements and gaps
- Automated verification of test coverage

### 2. JSON/YAML Validator (`validate_json.py`)

**Purpose**: Validate JSON and YAML artifacts against schemas.

**Supported Formats**:
- JSON Schema (`.schema.json` files)
- Shape specs (`.shape.json` files - lightweight, no dependencies)
- OpenAPI specifications (`.yaml` files)

**Usage**:
```bash
# Validate all fixtures
python3 tools/validate_json.py

# Validate specific file
python3 tools/validate_json.py --file data.json --schema schema.json

# Validate OpenAPI specs
python3 tools/validate_json.py --openapi

# JSON output
python3 tools/validate_json.py --json

# Via Makefile
make validate-json
```

**Use Cases**:
- Validate fixtures before committing
- Check OpenAPI spec correctness
- Automated validation in CI/CD
- Pre-commit hooks

### 3. Traceability Matrix Generator (`gen_traceability.py`)

**Purpose**: Generate comprehensive traceability reports linking requirements, specs, tests, and documentation.

**Usage**:
```bash
# Generate full traceability matrix
python3 tools/gen_traceability.py

# Generate specific matrix
python3 tools/gen_traceability.py --type requirements

# JSON output
python3 tools/gen_traceability.py --json

# Via Makefile
make traceability
```

**Outputs**:
- `traceability/traceability-requirements.md` - Requirements matrix
- `traceability/traceability-gaps.md` - Gaps analysis
- `traceability/traceability-full.json` - Complete JSON report

**Use Cases**:
- Identify untested requirements
- Find unmapped specifications
- Generate audit reports
- Track coverage over time

### 4. Workflow Runner (`run_workflow.py`)

**Purpose**: Orchestrate validation and verification workflows for CI/CD.

**Workflows**:
- `quick` - Fast validation subset (for rapid feedback)
- `validation` - Validate all JSON/YAML files
- `verification` - Run static verification tools
- `coverage` - Generate coverage reports
- `full` - Complete CI/CD pipeline

**Usage**:
```bash
# Run full workflow
python3 tools/run_workflow.py

# Run specific workflow
python3 tools/run_workflow.py --workflow validation

# Quick check
python3 tools/run_workflow.py --quick

# JSON output for CI/CD
python3 tools/run_workflow.py --json > workflow-report.json

# Fail fast on first error
python3 tools/run_workflow.py --fail-fast

# Via Makefile
make workflow TYPE=quick
make workflow TYPE=full
```

**Use Cases**:
- CI/CD integration
- Pre-commit validation
- Automated testing
- Agent-driven workflows

### 5. Workspace CLI (`workspace_cli.py`)

**Purpose**: Unified command-line interface for all workspace operations.

**Interactive Mode**:
```bash
python3 tools/workspace_cli.py
# or
make cli
```

**Commands**:
```bash
# Show workspace status
python3 tools/workspace_cli.py status

# Run validation
python3 tools/workspace_cli.py validate

# Search documentation
python3 tools/workspace_cli.py query "authentication"

# Trace requirement
python3 tools/workspace_cli.py trace REQ-001

# Generate coverage
python3 tools/workspace_cli.py coverage

# JSON output
python3 tools/workspace_cli.py status --json
```

**Use Cases**:
- Unified interface for all operations
- Interactive exploration
- Automated scripting
- AI agent integration

## Makefile Shortcuts

The Makefile provides convenient shortcuts for common operations:

```bash
# Search documentation
make query TERM="authentication"

# Trace requirement or gap
make trace ID=REQ-001
make trace ID=GAP-SYNC-001

# Generate traceability matrix
make traceability

# Validate JSON/YAML
make validate-json

# Run workflows
make workflow TYPE=quick
make workflow TYPE=validation
make workflow TYPE=full

# Interactive CLI
make cli
```

## GitHub Actions Integration

The `.github/workflows/validation.yml` workflow provides automated CI/CD:

**Jobs**:
1. **Quick Validation** - Fast checks (runs first)
2. **Full Validation** - Comprehensive validation
3. **Verification** - Static verification tools
4. **Coverage** - Coverage analysis and reports
5. **Summary** - Aggregate results

**Triggered On**:
- Push to `main` or `dev` branches
- Pull requests
- Manual workflow dispatch

**Artifacts**:
- Validation results (JSON)
- Verification results (JSON)
- Coverage reports
- Traceability matrices

## AI Agent Workflows

The tools are designed for AI agent integration:

### Example 1: Check Test Coverage

```bash
# What tests cover REQ-001?
python3 tools/query_workspace.py --tests-for REQ-001 --json
```

### Example 2: Validate Before Commit

```bash
# Run quick validation
python3 tools/run_workflow.py --workflow quick --json

# Check exit code
if [ $? -eq 0 ]; then
  echo "Validation passed"
else
  echo "Validation failed"
fi
```

### Example 3: Find Documentation Gaps

```bash
# Generate traceability matrix
python3 tools/gen_traceability.py --type requirements --json | \
  jq '.gaps.untested[]'
```

### Example 4: Search Documentation

```bash
# Find all docs mentioning "sync"
python3 tools/query_workspace.py --search "sync" --json | \
  jq '.[] | .file'
```

## Replit Integration

The `.replit` file configures the workspace for Replit Agent:

**Configured Workflows**:
- Workspace Status - Show repository status
- Can be extended with additional workflows

**Agent Mode**: Enabled for expert mode operation

## Best Practices

### For Developers

1. **Before Committing**:
   ```bash
   make workflow TYPE=quick
   ```

2. **After Making Changes**:
   ```bash
   make validate-json
   make verify
   ```

3. **When Documenting**:
   ```bash
   make query TERM="your-topic"
   make trace ID=REQ-XXX
   ```

### For AI Agents

1. **Always use `--json` flag** for machine-readable output
2. **Check exit codes** for success/failure
3. **Use `--fail-fast`** in CI/CD to stop on first error
4. **Query before making changes** to understand existing coverage
5. **Validate after changes** to ensure correctness

### For CI/CD

1. **Use workflow runner** for orchestration:
   ```bash
   python3 tools/run_workflow.py --workflow full --json
   ```

2. **Save artifacts** for debugging:
   ```bash
   python3 tools/run_workflow.py --json > workflow-report.json
   ```

3. **Run verification separately** to continue on issues:
   ```bash
   python3 tools/run_workflow.py --workflow verification
   ```

## Tool Comparison

| Tool | Purpose | Input | Output | Use Case |
|------|---------|-------|--------|----------|
| `query_workspace.py` | Search/query | REQ/GAP IDs, search terms | JSON/Text | Find info quickly |
| `validate_json.py` | Validate files | JSON/YAML files | Pass/Fail + errors | Pre-commit validation |
| `gen_traceability.py` | Generate matrices | All workspace files | Markdown/JSON reports | Audit & coverage |
| `run_workflow.py` | Orchestrate | Workflow name | Results summary | CI/CD automation |
| `workspace_cli.py` | Unified interface | Commands | Varied | Interactive/scripting |

## Output Formats

All tools support both **human-readable** and **machine-readable** output:

### Human-Readable (Default)
- Markdown reports
- Console output with colors/formatting
- Summary statistics

### Machine-Readable (`--json`)
- Structured JSON
- Consistent schema
- Easy to parse programmatically

## Dependencies

**Required** (included in Python standard library):
- `json`
- `re`
- `subprocess`
- `pathlib`

**Optional** (enhanced functionality):
- `pyyaml` - For YAML parsing (OpenAPI specs)
- `jsonschema` - For full JSON Schema validation

**Installation** (optional):
```bash
pip install pyyaml jsonschema
```

The tools work **without** optional dependencies using fallback methods.

## Next Steps

1. **Try the tools**:
   ```bash
   make cli
   ```

2. **Run a workflow**:
   ```bash
   make workflow TYPE=quick
   ```

3. **Generate traceability**:
   ```bash
   make traceability
   ```

4. **Integrate into your workflow**:
   - Add to pre-commit hooks
   - Configure CI/CD
   - Use in agent prompts

## Support

For issues or questions:
1. Check tool help: `python3 tools/<tool>.py --help`
2. Review generated reports in `traceability/`
3. Check workflow output for details

## Cycle-Aware Development Tools

The workspace includes advanced tooling for AI-assisted development cycles:

### 6. Phase Navigator (`phase_nav.py`)

**Purpose**: Track document phases and suggest transitions in the 5-phase engineering cycle.

**Phases**:
1. Source Analysis - Analyze code, document behavior
2. Research & Synthesis - Compare implementations, propose improvements
3. Knowledge Consolidation - Distill research into stable knowledge
4. Design Guidance - Create actionable implementation guides
5. Decision Making - Formalize via ADRs

**Usage**:
```bash
# Show phase summary
python3 tools/phase_nav.py summary

# Check phase of a specific document
python3 tools/phase_nav.py current docs/10-domain/treatments.md

# List all documents by phase
python3 tools/phase_nav.py list

# Suggest phase transitions
python3 tools/phase_nav.py suggest --json
```

### 7. Drift Detector (`detect_drift.py`)

**Purpose**: Detect when documentation drifts from source code.

**Usage**:
```bash
# Check all documents for drift
python3 tools/detect_drift.py

# Show only stale documents
python3 tools/detect_drift.py --stale-only

# Check specific document
python3 tools/detect_drift.py --file mapping/loop-sync.md

# JSON output
python3 tools/detect_drift.py --json
```

### 8. Spec Capture (`spec_capture.py`)

**Purpose**: Extract implicit requirements from documentation and verify specs against source.

**Usage**:
```bash
# Show spec coverage
python3 tools/spec_capture.py coverage

# Scan all mappings for specs
python3 tools/spec_capture.py scan

# Extract specs from a document
python3 tools/spec_capture.py extract mapping/loop-sync.md

# Verify a requirement
python3 tools/spec_capture.py verify REQ-001
```

### 9. Project Sequencer (`project_seq.py`)

**Purpose**: Manage multi-component improvement projects with sequenced work items.

**Usage**:
```bash
# Show current project status
python3 tools/project_seq.py status

# Create a new project
python3 tools/project_seq.py create "Sync Protocol Update"

# Add a component
python3 tools/project_seq.py add-component "Treatment Sync" --files mapping/treatments.md

# Advance to next phase/component
python3 tools/project_seq.py advance
```

### 10. Agent Context Provider (`agent_context.py`)

**Purpose**: Single entry point for AI agents to get workspace context.

**Usage**:
```bash
# Get brief context
python3 tools/agent_context.py brief

# Get context for a specific file
python3 tools/agent_context.py for docs/10-domain/treatments.md

# Get full context
python3 tools/agent_context.py full

# Get context for a topic
python3 tools/agent_context.py topic "sync protocol" --json
```

### 11. AI Advisor (`ai_advisor.py`)

**Purpose**: AI-powered suggestions for development cycle progression.

**Usage**:
```bash
# Get overall suggestions
python3 tools/ai_advisor.py suggest

# Analyze a specific file
python3 tools/ai_advisor.py analyze docs/10-domain/treatments.md

# Analyze a topic
python3 tools/ai_advisor.py topic "authentication"
```

## Extended Workspace CLI Commands

The workspace CLI now includes these additional commands:

```bash
# Phase navigation
workspace_cli.py phase              # Show phase summary
workspace_cli.py phase suggest      # Suggest transitions
workspace_cli.py phase <file>       # Check file phase

# Drift detection
workspace_cli.py drift              # Check all documents
workspace_cli.py drift --stale-only # Show only stale

# Spec management
workspace_cli.py specs              # Show coverage
workspace_cli.py specs scan         # Scan for specs
workspace_cli.py specs extract <file>

# Project management
workspace_cli.py project            # Show status
workspace_cli.py project create "Name"
workspace_cli.py project advance

# AI context
workspace_cli.py context            # Brief context
workspace_cli.py context full       # Full context
workspace_cli.py context for <file>

# AI advice
workspace_cli.py advise             # Get suggestions
workspace_cli.py advise analyze <file>
```

## Roadmap & Status

### Implementation Status

| Phase | Status | Priority | Tools |
|-------|--------|----------|-------|
| 1. Cross-Reference Validation | ✅ Completed | P1 | `sdqctl verify refs`, `query_workspace.py` |
| 2. Change Detection | ⏳ Pending | P2 | `detect_drift.py` |
| 3. Gap Analysis | ✅ Completed | P1 | `gen_traceability.py`, `verify_coverage.py` |
| 4. Unified CLI | ✅ Completed | P2 | `sdqctl verify all` |
| 5. Machine-Readable Requirements | ✅ Completed | P3 | `query_workspace.py`, `gen_traceability.py` |
| 6. Visualization | ⏳ Pending | P3 | `gen_diagrams.py` (proposed) |

### sdqctl Integration (2026-01-30)

Several custom tools now have sdqctl equivalents. Prefer sdqctl for consistency:

| Task | Preferred | Legacy (deprecated) |
|------|-----------|---------------------|
| Validate refs | `sdqctl verify refs` | `python tools/verify_refs.py` |
| Check terminology | `sdqctl verify terminology` | `python tools/verify_terminology.py` |
| Check links | `sdqctl verify links` | `python tools/linkcheck.py` |
| Run all checks | `sdqctl verify all` | `make check` |

See [tools-comparison-proposal.md](sdqctl-proposals/tools-comparison-proposal.md) for full migration details.

### Pending: Change Detection (Phase 2)

**Purpose**: Identify what changed in source repositories since last analysis.

**Features**:
- Compare current external repo state to pinned SHAs in `workspace.lock.json`
- List modified files in areas relevant to mapped functionality
- Flag when analyzed code has drifted significantly
- Generate "stale analysis" warnings

### Pending: Visualization (Phase 6)

**Purpose**: Generate visual representations of workspace relationships.

**Features**:
- Mermaid diagrams showing: Source → Mapping → Requirements → Tests
- Coverage heatmaps by project/feature area
- Dependency graphs between requirements
- HTML report with interactive navigation

### Agent-Based SDLC Considerations

When building tools for agent-based workflows:

1. **Structured Output**: Always provide both human-readable (Markdown) and machine-readable (JSON) output
2. **Exit Codes**: Return meaningful exit codes (0=success, 1=warnings, 2=errors) for workflow automation
3. **Incremental Mode**: Support `--changed-only` flags to minimize work on large workspaces
4. **Dry Run**: Support `--dry-run` to preview changes without side effects
5. **Idempotency**: Running a tool multiple times should produce consistent results
6. **Context Awareness**: Tools should work from any directory, not just workspace root
