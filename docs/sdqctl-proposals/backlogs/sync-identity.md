# Sync & Identity Backlog

> **Domain**: Data synchronization, deduplication, identity fields  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-29

Covers: syncIdentifier, interfaceIDs, uuid, timestamps, batch ordering

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Cross-controller conflict detection | P2 | Medium | Document actual behavior when Loop+Trio sync |
| 2 | **Verify sync-identity mapping** | P2 | Medium | [Accuracy backlog #7](documentation-accuracy.md) |
| 3 | **Verify GAP-SYNC-* freshness** | P2 | Medium | [Accuracy backlog #21](documentation-accuracy.md) |
| 4 | **Audit REQ-SYNC-* scenario coverage** | P2 | Medium | [Accuracy backlog #24](documentation-accuracy.md) |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Orphaned assertion linkage | 2026-01-29 | 23→0 orphans, +20 REQs created |
| Override-supersede requirements | 2026-01-29 | REQ-OVERRIDE-001 to 005 created |
| Duration/utcOffset unit impact analysis | 2026-01-29 | OQ-030/031 combined, 4 alternatives, 4 REQs |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Duration/utcOffset unit impact analysis | 2026-01-29 | OQ-030/031 combined, 4 alternatives, 4 REQs |
| Trace REQ-031 through REQ-035 | 2026-01-29 | 6 requirements with scenarios and source refs |
| Extract Loop sync identity fields | 2026-01-29 | 318 lines, ObjectIdCache pattern |
| Full audit: nightscout-connect | 2026-01-29 | 527 lines, XState machines, 5 sources |
| Deep dive: Batch operation ordering | 2026-01-29 | 334 lines, order preservation |
| Extract AAPS NSClient upload schema | 2026-01-28 | 70+ fields, 25 eventTypes |
| Timezone/DST handling terminology | 2026-01-28 | +150 lines, GAP-TZ-004..007 |

---

## References

- [mapping/loop/sync-identity-fields.md](../../../mapping/loop/sync-identity-fields.md)
- [docs/10-domain/nightscout-connect-deep-dive.md](../../10-domain/nightscout-connect-deep-dive.md)
- [mapping/cross-project/terminology-matrix.md](../../../mapping/cross-project/terminology-matrix.md)
