# sdqctl vs Custom Python Tools: Comparison and Recommendations

> **Created**: 2026-01-29  
> **Purpose**: Evaluate overlap between sdqctl capabilities and 32 custom Python tools  
> **Status**: Analysis

---

## Executive Summary

The workspace has 32 custom Python tools in `tools/` alongside sdqctl, a vendor-agnostic CLI for AI-assisted workflows. This analysis identifies overlaps, integration opportunities, and deprecation candidates.

**Recommendation**: Keep domain-specific tools, integrate workflow tools with sdqctl, deprecate redundant utilities.

---

## Tool Categories

### Category 1: Workflow Orchestration (sdqctl overlap)

| Tool | Purpose | sdqctl Equivalent | Recommendation |
|------|---------|-------------------|----------------|
| `run_workflow.py` | Orchestrate validation workflows | `sdqctl iterate/flow` | **Deprecate** - use sdqctl |
| `phase_nav.py` | Track document phases | `sdqctl iterate` | **Deprecate** - use sdqctl |
| `project_seq.py` | Multi-component projects | `sdqctl apply` | **Deprecate** - use sdqctl |

### Category 2: Hygiene/Status (keep - sdqctl plugins)

| Tool | Purpose | Integration Path | Recommendation |
|------|---------|------------------|----------------|
| `queue_stats.py` | Quick status line | sdqctl status plugin | **Keep** - integrate as plugin |
| `backlog_hygiene.py` | Queue validation | sdqctl directive | **Keep** - integrate as directive |
| `doc_chunker.py` | Split large files | sdqctl directive | **Keep** - integrate as directive |

### Category 3: Verification (keep - specialized)

| Tool | Purpose | Why Keep |
|------|---------|----------|
| `verify_refs.py` | Validate code references | Domain-specific logic |
| `verify_terminology.py` | Terminology consistency | Domain-specific logic |
| `verify_assertions.py` | Map assertions to requirements | Domain-specific logic |
| `verify_coverage.py` | Cross-reference coverage | Domain-specific logic |
| `linkcheck.py` | Check broken links | Standard utility |
| `validate_json.py` | JSON schema validation | Standard utility |
| `validate_fixtures.py` | Fixture shape validation | Domain-specific |

### Category 4: Generation (keep - specialized)

| Tool | Purpose | Why Keep |
|------|---------|----------|
| `gen_coverage.py` | Coverage matrix | Domain-specific output |
| `gen_inventory.py` | Workspace inventory | Domain-specific output |
| `gen_refs.py` | Reference generation | Domain-specific output |
| `gen_traceability.py` | Traceability reports | Domain-specific output |

### Category 5: Conformance Testing (keep - core functionality)

| Tool | Purpose | Why Keep |
|------|---------|----------|
| `run_conformance.py` | Execute assertions | Core testing infrastructure |
| `extract_vectors.py` | Extract test vectors | Core testing infrastructure |
| `test_conversions.py` | Unit conversion tests | Core testing infrastructure |
| `mock_nightscout.py` | Mock server | Testing infrastructure |

### Category 6: Bootstrap/Setup (keep - essential)

| Tool | Purpose | Why Keep |
|------|---------|----------|
| `bootstrap.py` | Workspace setup | Essential for onboarding |
| `checkout_submodules.py` | Clone externals | Essential for setup |

### Category 7: AI Integration (evaluate)

| Tool | Purpose | Recommendation |
|------|---------|----------------|
| `agent_context.py` | AI context provider | **Keep** - core for AI workflows |
| `ai_advisor.py` | Intelligent suggestions | **Evaluate** - may overlap with sdqctl |
| `query_workspace.py` | Documentation queries | **Keep** - useful for RAG |

### Category 8: Utilities (keep/deprecate mixed)

| Tool | Purpose | Recommendation |
|------|---------|----------------|
| `detect_drift.py` | Doc-code drift | **Keep** - unique functionality |
| `spec_capture.py` | Extract specifications | **Keep** - unique functionality |
| `workspace_cli.py` | Unified CLI | **Evaluate** - may overlap with sdqctl |
| `verify_hello.py` | Plugin test | **Deprecate** - test artifact only |

### Category 9: Test Files (keep - test infrastructure)

| Tool | Purpose | Recommendation |
|------|---------|----------------|
| `test_hygiene_tools.py` | Integration tests | **Keep** - test infrastructure |
| `test_hygiene_tools_unit.py` | Unit tests | **Keep** - test infrastructure |

---

## Summary

| Action | Count | Tools |
|--------|-------|-------|
| **Deprecate** | 4 | run_workflow, phase_nav, project_seq, verify_hello |
| **Integrate** | 3 | queue_stats, backlog_hygiene, doc_chunker → sdqctl plugins |
| **Evaluate** | 2 | ai_advisor, workspace_cli |
| **Keep** | 23 | Domain-specific, verification, generation, testing |

---

## Implementation Plan

### Phase 1: Deprecate Redundant (Low effort)

1. Mark deprecated in docstrings
2. Add deprecation warnings
3. Update documentation to use sdqctl equivalents
4. Remove in future release

### Phase 2: Plugin Integration (Medium effort)

1. Create sdqctl HYGIENE directive
2. Integrate queue_stats as `sdqctl status --queue`
3. Integrate doc_chunker as `sdqctl chunk`
4. Integrate backlog_hygiene as `sdqctl hygiene`

### Phase 3: Evaluate Overlaps (Low effort)

1. Compare ai_advisor with sdqctl advisory features
2. Compare workspace_cli with sdqctl command set
3. Decide: merge, deprecate, or keep separate

---

## Conclusion

The custom tools serve distinct purposes:
- **Domain-specific** tools (verification, generation) should remain
- **Workflow orchestration** tools should migrate to sdqctl
- **Hygiene tools** should integrate as sdqctl plugins

Net reduction: 4 tools deprecated, 3 integrated, 25 retained.
