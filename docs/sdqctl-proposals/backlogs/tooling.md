# Tooling Backlog

> **Domain**: sdqctl enhancements, workflow improvements, automation  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-28

Covers: sdqctl directives, plugins, LSP integration, agentic automation

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | LSP-based claim verification | P2 | Medium | Resolve `...` placeholder paths |
| 2 | Full audit: nightscout-roles-gateway | P3 | Medium | OAuth 2.0 RBAC controller |

---

## sdqctl Enhancement Requests

| Priority | Enhancement | Proposal | Notes |
|----------|-------------|----------|-------|
| P2 | HELP-INLINE directive | [sdqctl/HELP-INLINE.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/HELP-INLINE.md) | Allow HELP anywhere in workflow |
| P2 | REFCAT glob support | [sdqctl/REFCAT-DESIGN.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/REFCAT-DESIGN.md) | `@externals/**/*Treatment*.swift` |
| P2 | Plugin System | [sdqctl/PLUGIN-SYSTEM.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/PLUGIN-SYSTEM.md) | Custom directives for ecosystem |
| P2 | LSP Integration | [sdqctl/LSP-INTEGRATION.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/LSP-INTEGRATION.md) | Semantic code queries |
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

## Completed

| Item | Date | Notes |
|------|------|-------|
| Plugin system validation | 2026-01-28 | All 5 plugins work |
| backlog-cycle.conv workflow | 2026-01-28 | Orchestration pattern |

---

## References

- [.sdqctl/directives.yaml](../../../.sdqctl/directives.yaml) - Plugin manifest
- [workflows/orchestration/](../../../workflows/orchestration/) - Backlog workflows
