# Sync & Identity Backlog

> **Domain**: Data synchronization, deduplication, identity fields  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-28

Covers: syncIdentifier, interfaceIDs, uuid, timestamps, batch ordering

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Extract AAPS NSClient upload schema | P1 | Medium | All fields uploaded to Nightscout |
| 2 | Deep dive: Batch operation ordering | P1 | Medium | Order-preservation for sync |
| 3 | Extract Loop sync identity fields | P2 | Medium | What makes a treatment unique |
| 4 | Full audit: nightscout-connect | P2 | Medium | Cloud platform connectors |
| 5 | Trace REQ-031 through REQ-035 | P1 | Low | 5 uncovered sync requirements |
| 6 | **Code analysis: identifier vs syncIdentifier** | P1 | Low | OQ-001 - trace usage across repos |
| 7 | **Code analysis: Loop batch order dependency** | P1 | Low | OQ-002 - check if Loop requires order |
| 8 | **Impact analysis: Duration unit standardization** | P1 | Medium | OQ-030 - analyze all 4 alternatives |
| 9 | **Impact analysis: utcOffset unit** | P1 | Low | OQ-031 - combine with duration analysis |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Timezone/DST handling terminology | 2026-01-28 | +150 lines, GAP-TZ-004..007 |

---

## References

- [mapping/cross-project/terminology-matrix.md](../../../mapping/cross-project/terminology-matrix.md)
- [traceability/requirements.md](../../../traceability/requirements.md) (REQ-031-035)
