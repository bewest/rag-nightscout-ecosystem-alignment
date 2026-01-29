# Tooling Backlog

> **Domain**: sdqctl enhancements, workflow improvements, automation  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-29

Covers: sdqctl directives, plugins, LSP integration, agentic automation

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Algorithm conformance runners | P2 | High | oref0-runner.js ✅, aaps-runner.kt pending |
| 2 | LSP-based claim verification (Phase 2+) | P3 | Medium | JS/TS LSP integration deferred |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Integration test runner | 2026-01-29 | `tools/conformance_suite.py` - orchestrator + reports |
| LSP claim verification Phase 1 | 2026-01-29 | Line anchor validation, 99.3% valid |
| Transformation pipeline tester | 2026-01-29 | `tools/test_transforms.py` + 28 test cases |
| Hygiene tooling suite | 2026-01-29 | queue_stats.py, backlog_hygiene.py, doc_chunker.py verified |
| Conformance schema + vector extraction | 2026-01-29 | `conformance-vector-v1.json` + 85 vectors from AAPS |
| Algorithm conformance suite proposal | 2026-01-29 | `docs/sdqctl-proposals/algorithm-conformance-suite.md` - 510 lines, 5-phase plan |
| Unit conversion test suite | 2026-01-28 | `tools/test_conversions.py` + 20 test cases |
| Mock Nightscout server | 2026-01-28 | `tools/mock_nightscout.py` v1/v3 API |
| Plugin system validation | 2026-01-28 | All 5 plugins work |
| backlog-cycle.conv workflow | 2026-01-28 | Orchestration pattern |

---

## Cross-Project Test Harness (In Progress)

| Component | Status | File | Description |
|-----------|--------|------|-------------|
| Unit conversions | ✅ Done | `tools/test_conversions.py` | Time/glucose/insulin precision |
| Mock server | ✅ Done | `tools/mock_nightscout.py` | HTTP mock for API v1/v3 |
| Conformance schema | ✅ Done | `conformance/schemas/conformance-vector-v1.json` | Test vector format |
| Vector extractor | ✅ Done | `tools/extract_vectors.py` | Pull from AAPS replay tests |
| Test vectors | ✅ Done | `conformance/vectors/` | 85 vectors (77 basal, 8 LGS) |
| Conformance runners | 📋 Proposed | `conformance/runners/` | oref0, AAPS, Loop runners |
| Transform tester | ✅ Done | `tools/test_transforms.py` | Field mapping validation (28 tests) |

---

## sdqctl Enhancement Requests

| Priority | Enhancement | Proposal | Notes |
|----------|-------------|----------|-------|
| P2 | HELP-INLINE directive | [sdqctl/HELP-INLINE.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/HELP-INLINE.md) | Allow HELP anywhere in workflow |
| P2 | REFCAT glob support | [sdqctl/REFCAT-DESIGN.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/REFCAT-DESIGN.md) | `@externals/**/*Treatment*.swift` |
| P2 | Plugin System | [sdqctl/PLUGIN-SYSTEM.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/PLUGIN-SYSTEM.md) | Custom directives for ecosystem |
| P2 | LSP Integration | [lsp-integration-proposal.md](../lsp-integration-proposal.md) | Semantic code queries (4-phase plan) |
| P3 | Ecosystem help topics | New | gap-ids, 5-facet, stpa, conformance |
| P3 | VERIFY stpa-hazards | New | Check STPA hazard traceability |
| P3 | RUN-CONFORMANCE | New | Execute conformance test scenarios |
| P3 | STPA Deep Integration | [sdqctl/STPA-DEEP-INTEGRATION.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/STPA-DEEP-INTEGRATION.md) | Usage guide + predictions |

---

## Agentic Automation (R&D)

| Priority | Enhancement | Proposal | Notes |
|----------|-------------|----------|-------|
| P3 | `sdqctl agent analyze` | [AGENTIC-ANALYSIS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/AGENTIC-ANALYSIS.md) | Autonomous multi-cycle |
| P3 | `sdqctl watch` | [CONTINUOUS-MONITORING.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/CONTINUOUS-MONITORING.md) | Monitor for changes |
| P3 | `sdqctl drift` | [CONTINUOUS-MONITORING.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/CONTINUOUS-MONITORING.md) | Drift detection |
| P3 | `sdqctl delegate` | [UPSTREAM-CONTRIBUTIONS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/UPSTREAM-CONTRIBUTIONS.md) | Draft upstream fixes |
| P3 | `sdqctl upstream status` | [UPSTREAM-CONTRIBUTIONS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/UPSTREAM-CONTRIBUTIONS.md) | Track contributions |

---

## References

- [.sdqctl/directives.yaml](../../../.sdqctl/directives.yaml) - Plugin manifest
- [workflows/orchestration/](../../../workflows/orchestration/) - Backlog workflows
