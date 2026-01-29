# Nightscout API Backlog

> **Domain**: Nightscout collections, API v3, authentication  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-29

Covers: cgm-remote-monitor, entries, treatments, devicestatus, profile

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Playwright adoption: Implementation | P2 | Medium | Proposal complete, needs PR |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
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
