# Tooling Roadmap

This document outlines proposed tooling improvements for the AID Alignment Workspace, designed to support agent-based software development lifecycle workflows.

## Current State

The workspace currently has these tools:

| Tool | Purpose | Output |
|------|---------|--------|
| `bootstrap.py` | Clone/update external repositories | Manages `externals/` |
| `checkout_submodules.py` | Handle git submodules | Updates nested repos |
| `gen_refs.py` | Generate code reference permalinks | `docs/_generated/` |
| `gen_coverage.py` | Generate scenario coverage matrix | `traceability/coverage-matrix.*` |
| `gen_inventory.py` | Generate workspace artifact inventory | `traceability/inventory.*` |
| `linkcheck.py` | Validate markdown links and code refs | Console output |
| `validate_fixtures.py` | Check JSON fixtures against schemas | Console output |
| `run_conformance.py` | Execute assertion tests | Console output |

## Proposed Improvements

### Phase 1: Cross-Reference Validation

**Purpose**: Automatically verify that references between artifacts are valid.

**Proposed Tool**: `validate_refs.py`

**Features**:
- Verify REQ-XXX references in mapping documents link to valid requirements
- Check scenario references in requirements.md resolve to actual scenarios
- Validate code references (`alias:path#anchor`) resolve to existing files/lines
- Report dangling references and orphaned requirements

**Agent Use Case**: Before completing a mapping document, an agent can run this to ensure all cross-references are valid.

---

### Phase 2: Change Detection / Diff Analysis

**Purpose**: Identify what changed in source repositories since last analysis.

**Proposed Tool**: `detect_changes.py`

**Features**:
- Compare current external repo state to pinned SHAs in `workspace.lock.json`
- List modified files in areas relevant to mapped functionality
- Flag when analyzed code has drifted significantly
- Generate "stale analysis" warnings

**Agent Use Case**: When resuming work, an agent can check if source analysis is still current or needs updating.

---

### Phase 3: Gap Analysis

**Purpose**: Identify what's missing or incomplete across the workspace.

**Proposed Tool**: `analyze_gaps.py`

**Features**:
- Cross-reference inventory against expected coverage
- Identify projects with no mapping documents
- Find requirements without test coverage
- List scenarios missing fixture data
- Generate prioritized work backlog

**Agent Use Case**: An agent can query "what should I work on next?" and get a prioritized list.

---

### Phase 4: Unified CLI

**Purpose**: Single entry point for all workspace operations.

**Proposed Tool**: `aid` (or `workspace`) CLI

**Features**:
- `aid status` - Overall workspace health
- `aid validate` - Run all validation checks
- `aid inventory` - Generate/display inventory
- `aid gaps` - Show gap analysis
- `aid refs <alias:path>` - Resolve code reference to permalink
- `aid watch` - Watch mode for continuous validation

**Agent Use Case**: Consistent, discoverable interface reduces context needed to operate the workspace.

---

### Phase 5: Machine-Readable Requirements

**Purpose**: Enable programmatic access to requirements data.

**Proposed Enhancement**: Parse `requirements.md` → `requirements.json`

**Features**:
- Extract structured requirement data (ID, statement, rationale, scenarios, verification)
- Enable automated requirement coverage analysis
- Support filtering by category, priority, or status
- Generate requirement traceability matrix

**Agent Use Case**: An agent can query "which requirements relate to sync?" programmatically.

---

### Phase 6: Visualization

**Purpose**: Generate visual representations of workspace relationships.

**Proposed Tool**: `gen_diagrams.py`

**Features**:
- Mermaid diagrams showing: Source → Mapping → Requirements → Tests
- Coverage heatmaps by project/feature area
- Dependency graphs between requirements
- HTML report with interactive navigation

**Agent Use Case**: Quickly understand workspace structure and identify blind spots.

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
