# Nightscout API Backlog

> **Domain**: Nightscout collections, API v3, authentication  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-29

Covers: cgm-remote-monitor, entries, treatments, devicestatus, profile

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | API v3 pagination compliance | P2 | Medium | Document srvModified-based pagination across clients |
| 2 | ~~WebSocket event coverage~~ | ~~P3~~ | ~~Medium~~ | ✅ COMPLETE 2026-01-30 |
| 3 | **Verify devicestatus/entries claims** | P2 | Medium | [Accuracy backlog #12-14](documentation-accuracy.md) |
| 4 | **Verify GAP-API-* freshness** | P2 | Medium | [Accuracy backlog #20](documentation-accuracy.md) - check if closed in PRs |
| 5 | **Audit REQ-API-* → OpenAPI alignment** | P2 | Medium | [Accuracy backlog #27](documentation-accuracy.md) |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Playwright E2E PR submission | 2026-01-29 | PR-SUBMISSION.md created, 18 tests ready |
| Playwright adoption: Implementation | 2026-01-29 | 591 lines, 4 files, ready for PR |
| cgm-remote-monitor design review | 2026-01-29 | 319 lines, 18 gaps synthesized, 5-phase refactoring plan, 4 new REQs |
| Profile collection deep dive | 2026-01-29 | Pre-existing 557 lines, migrated 4 gaps |
| Device Status collection deep dive | 2026-01-29 | Pre-existing 863 lines, migrated 4 gaps |
| Nightscout APIv3 Collection deep dive | 2026-01-29 | 290 lines, 3 gaps, 3 requirements |
| cgm-remote-monitor 6-layer audit | 2026-01-29 | 2,751 lines, 18 gaps (DB, API, Plugin, Sync, Auth, Frontend) |
| Interoperability Spec v1 | 2026-01-29 | 316 lines, RFC-style MUST/SHOULD/MAY |
| Authentication flows deep dive | 2026-01-29 | 362 lines, 4 gaps |
| Playwright adoption proposal | 2026-01-29 | 316 lines, 4-phase plan |
| Extract Nightscout v3 treatments schema | 2026-01-28 | 248 lines, 21+ eventTypes |
| Compare remote bolus handling | 2026-01-28 | 348 lines, 4 systems |
| DeviceStatus deep dive | 2026-01-21 | Loop vs oref0 structure |

---

## References

- [docs/10-domain/cgm-remote-monitor-*-deep-dive.md](../../10-domain/) (6 audit files)
- [specs/interoperability-spec-v1.md](../../../specs/interoperability-spec-v1.md)
- [specs/openapi/aid-*.yaml](../../../specs/openapi/) (entries, treatments, devicestatus, profile)
