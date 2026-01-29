# Sync & Identity Backlog

> **Domain**: Data synchronization, deduplication, identity fields  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-29

Covers: syncIdentifier, interfaceIDs, uuid, timestamps, batch ordering

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | **Extract Loop sync identity fields** | P1 | Medium | → Ready Queue #3 |
| 2 | Deep dive: Batch operation ordering | P1 | Medium | Order-preservation for sync |
| 3 | Trace REQ-031 through REQ-035 | P1 | Low | 5 uncovered sync requirements |
| 4 | **OQ-001 Resolution: Sync identity terminology** | P1 | Low | Document-only approach - see below |
| 5 | Full audit: nightscout-connect | P2 | Medium | Cloud platform connectors |
| 6 | Impact analysis: Duration unit standardization | P1 | Medium | OQ-030 - all 4 alternatives |
| 7 | Impact analysis: utcOffset unit | P1 | Low | OQ-031 - combine with duration |

### OQ-001 Resolution Work Items (P1)

**Decision**: Document-only approach - no new `syncId` field.

| # | Task | Effort |
|---|------|--------|
| 4a | Update `docs/OPEN-QUESTIONS.md` - mark OQ-001 resolved | Low |
| 4b | Update `mapping/cross-project/terminology-matrix.md` - add sync identity definitions | Low |
| 4c | Update `docs/90-decisions/adr-002-sync-identity-strategy.md` - clarify document-only | Low |
| 4d | Add progress entry for OQ-001 resolution | Low |

**Key Findings from Analysis (2026-01-29)**:
- NS v3 `identifier`: Deterministic UUID v5 (device+date+eventType), server-side, for API deduplication
- Loop/Trio `syncIdentifier`: Random UUID, client-side, for sync state tracking
- AAPS `interfaceIDs.nightscoutId`: Stores NS identifier, multi-level dedup (nightscoutId → pumpId → timestamp)
- **Conclusion**: These serve complementary purposes, not replaceable - document relationship only

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Extract AAPS NSClient upload schema | 2026-01-28 | `mapping/aaps/nsclient-schema.md` - 70+ fields |
| Timezone/DST handling terminology | 2026-01-28 | +150 lines, GAP-TZ-004..007 |
| Loop batch order dependency analysis | 2026-01-28 | Completed as part of batch ordering deep dive |

---

## References

- [mapping/cross-project/terminology-matrix.md](../../../mapping/cross-project/terminology-matrix.md)
- [traceability/requirements.md](../../../traceability/requirements.md) (REQ-031-035)
