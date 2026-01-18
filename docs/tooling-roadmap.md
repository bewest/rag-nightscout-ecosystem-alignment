# Tooling Roadmap

This document outlines tooling improvements for the AID Alignment Workspace, designed to support agent-based software development lifecycle workflows.

**Last Updated**: 2026-01-18

## Current State (Implemented)

The workspace has comprehensive tooling for validation, verification, and traceability:

### Core Tools

| Tool | Purpose | Output | Status |
|------|---------|--------|--------|
| `bootstrap.py` | Clone/update external repositories | Manages `externals/` | ✅ Existing |
| `checkout_submodules.py` | Handle git submodules | Updates nested repos | ✅ Existing |
| `gen_refs.py` | Generate code reference permalinks | `docs/_generated/` | ✅ Existing |
| `gen_coverage.py` | Generate scenario coverage matrix | `traceability/coverage-matrix.*` | ✅ Existing |
| `gen_inventory.py` | Generate workspace artifact inventory | `traceability/inventory.*` | ✅ Existing |
| `linkcheck.py` | Validate markdown links and code refs | Console output | ✅ Existing |
| `validate_fixtures.py` | Check JSON fixtures against schemas | Console output | ✅ Existing |
| `run_conformance.py` | Execute assertion tests | Console output | ✅ Existing |
| `verify_refs.py` | Verify code references resolve to files | `traceability/refs-validation.*` | ✅ Existing |
| `verify_coverage.py` | Analyze requirement/gap coverage | `traceability/coverage-analysis.*` | ✅ Existing |
| `verify_terminology.py` | Check terminology consistency | `traceability/terminology-consistency.*` | ✅ Existing |
| `verify_assertions.py` | Trace assertions to requirements | `traceability/assertion-trace.*` | ✅ Existing |

### Enhanced Tools (New - 2026-01-18)

| Tool | Purpose | Output | Status |
|------|---------|--------|--------|
| `query_workspace.py` | Interactive query interface | JSON/Text | ✅ **NEW** |
| `validate_json.py` | JSON/YAML schema validation | JSON/Text | ✅ **NEW** |
| `gen_traceability.py` | Comprehensive traceability matrices | Markdown/JSON | ✅ **NEW** |
| `run_workflow.py` | Automated workflow orchestration | JSON reports | ✅ **NEW** |
| `workspace_cli.py` | Unified CLI interface | Varied | ✅ **NEW** |

### CI/CD Integration

| Component | Purpose | Status |
|-----------|---------|--------|
| `.github/workflows/validation.yml` | Multi-stage validation pipeline | ✅ **NEW** |
| Makefile targets | Convenient shortcuts | ✅ **UPDATED** |
| Replit configuration | Agent-ready workspace | ✅ Existing |

## Completed Phases

### ✅ Phase 1: Cross-Reference Validation (COMPLETED)

**Status**: Implemented via `verify_refs.py` (existing) and enhanced with `query_workspace.py`

**Features Delivered**:
- ✅ Verify REQ-XXX references in mapping documents link to valid requirements
- ✅ Check scenario references in requirements.md resolve to actual scenarios
- ✅ Validate code references (`alias:path#anchor`) resolve to existing files/lines
- ✅ Report dangling references and orphaned requirements
- ✅ Interactive query interface for requirements and gaps

**Agent Use Case**: Agents can query `python3 tools/query_workspace.py --tests-for REQ-001 --json` to verify coverage before completing work.

---

### ✅ Phase 3: Gap Analysis (COMPLETED)

**Status**: Implemented via `gen_traceability.py` and `verify_coverage.py`

**Features Delivered**:
- ✅ Cross-reference inventory against expected coverage
- ✅ Identify projects with no mapping documents
- ✅ Find requirements without test coverage
- ✅ List scenarios missing fixture data
- ✅ Generate prioritized work backlog (via coverage reports)

**Agent Use Case**: Run `python3 tools/gen_traceability.py --type requirements --json | jq '.gaps.untested[]'` to get list of work items.

---

### ✅ Phase 4: Unified CLI (COMPLETED)

**Status**: Implemented via `workspace_cli.py`

**Features Delivered**:
- ✅ `workspace status` - Overall workspace health
- ✅ `workspace validate` - Run all validation checks
- ✅ `workspace verify` - Run verification tools
- ✅ `workspace query <term>` - Search documentation
- ✅ `workspace trace <id>` - Trace requirements/gaps
- ✅ `workspace coverage` - Generate coverage reports
- ✅ Interactive mode for exploration

**Agent Use Case**: Single entry point `python3 tools/workspace_cli.py <command> --json` reduces context needed.

---

### ✅ Phase 5: Machine-Readable Requirements (COMPLETED)

**Status**: Implemented via `query_workspace.py` and `gen_traceability.py`

**Features Delivered**:
- ✅ Extract structured requirement data (ID, statement, rationale, scenarios, verification)
- ✅ Enable automated requirement coverage analysis
- ✅ Support filtering by category, priority, or status
- ✅ Generate requirement traceability matrix
- ✅ JSON output for all tools

**Agent Use Case**: `python3 tools/query_workspace.py --search "sync" --json` returns programmatic results.

## Remaining Phases

### Phase 2: Change Detection / Diff Analysis

**Purpose**: Identify what changed in source repositories since last analysis.

**Proposed Tool**: `detect_changes.py`

**Features**:
- Compare current external repo state to pinned SHAs in `workspace.lock.json`
- List modified files in areas relevant to mapped functionality
- Flag when analyzed code has drifted significantly
- Generate "stale analysis" warnings

**Priority**: P2 (Medium)

**Agent Use Case**: When resuming work, an agent can check if source analysis is still current or needs updating.

---

### Phase 6: Visualization

**Purpose**: Generate visual representations of workspace relationships.

**Proposed Tool**: `gen_diagrams.py`

**Features**:
- Mermaid diagrams showing: Source → Mapping → Requirements → Tests
- Coverage heatmaps by project/feature area
- Dependency graphs between requirements
- HTML report with interactive navigation

**Priority**: P3 (Low)

**Agent Use Case**: Quickly understand workspace structure and identify blind spots.

---

## Implementation Status Summary

| Phase | Status | Priority | Tools |
|-------|--------|----------|-------|
| 1. Cross-Reference Validation | ✅ **COMPLETED** | P1 | `verify_refs.py`, `query_workspace.py` |
| 2. Change Detection | ⏳ Pending | P2 | `detect_changes.py` (proposed) |
| 3. Gap Analysis | ✅ **COMPLETED** | P1 | `gen_traceability.py`, `verify_coverage.py` |
| 4. Unified CLI | ✅ **COMPLETED** | P2 | `workspace_cli.py` |
| 5. Machine-Readable Requirements | ✅ **COMPLETED** | P3 | `query_workspace.py`, `gen_traceability.py` |
| 6. Visualization | ⏳ Pending | P3 | `gen_diagrams.py` (proposed) |

## Recent Additions (2026-01-18)

### New Capabilities

1. **Interactive Query Interface** (`query_workspace.py`)
   - Search requirements, gaps, and documentation
   - Find test coverage for requirements
   - Both interactive and command-line modes
   - JSON output for automation

2. **Enhanced JSON/YAML Validation** (`validate_json.py`)
   - Schema validation (JSON Schema)
   - Shape validation (lightweight format)
   - OpenAPI spec validation
   - Works without dependencies (fallback mode)

3. **Comprehensive Traceability** (`gen_traceability.py`)
   - Requirements → Tests → Documentation matrix
   - Gap coverage analysis
   - API endpoint tracking
   - Markdown and JSON reports

4. **Workflow Automation** (`run_workflow.py`)
   - Orchestrates validation/verification workflows
   - Multiple workflow types (quick, full, validation, verification)
   - CI/CD integration ready
   - JSON output for parsing

5. **Unified CLI** (`workspace_cli.py`)
   - Single entry point for all operations
   - Interactive mode for exploration
   - Command mode for automation
   - Consistent interface

6. **GitHub Actions Integration**
   - Multi-stage validation pipeline
   - Artifact uploads
   - Summary generation
   - Parallel job execution

### Documentation

- `docs/TOOLING-GUIDE.md` - Comprehensive tooling guide
- `docs/TOOLING-QUICKREF.md` - Quick reference for common tasks
- Updated Makefile with new targets
- This roadmap updated with completion status

---

## Implementation Priority

| Phase | Effort | Value | Priority |
|-------|--------|-------|----------|
| 1. Cross-Reference Validation | Medium | High | P1 |
| 2. Change Detection | Medium | High | P1 |
| 3. Gap Analysis | Medium | High | P2 |
| 4. Unified CLI | High | Medium | P2 |
| 5. Machine-Readable Requirements | Low | Medium | P3 |
| 6. Visualization | Medium | Medium | P3 |

## Agent-Based SDLC Considerations

When building tools for agent-based workflows:

1. **Structured Output**: Always provide both human-readable (Markdown) and machine-readable (JSON) output
2. **Exit Codes**: Return meaningful exit codes (0=success, 1=warnings, 2=errors) for workflow automation
3. **Incremental Mode**: Support `--changed-only` flags to minimize work on large workspaces
4. **Dry Run**: Support `--dry-run` to preview changes without side effects
5. **Idempotency**: Running a tool multiple times should produce consistent results
6. **Context Awareness**: Tools should work from any directory, not just workspace root

## Next Steps

1. Review and prioritize based on immediate workflow needs
2. Implement Phase 1 (cross-reference validation) as next modest improvement
3. Iterate based on agent workflow feedback
