# Sync & Identity Backlog

> **Domain**: Data synchronization, deduplication, identity fields  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-30

Covers: syncIdentifier, interfaceIDs, uuid, timestamps, batch ordering, ProfileSwitch

---

## OQ-010 Focus: ProfileSwitch → Override Mapping

Per [OQ-010](../../OPEN-QUESTIONS.md#oq-010-profileswitch--override-mapping), this requires systematic analysis of how ProfileSwitch semantics relate to Override behavior, with Nocturne as a key reference.

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | ~~Cross-controller conflict detection~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE 2026-01-29 |
| 2 | **Verify sync-identity mapping** | P2 | Medium | [Accuracy backlog #7](documentation-accuracy.md) |
| 3 | **Verify GAP-SYNC-* freshness** | P2 | Medium | [Accuracy backlog #21](documentation-accuracy.md) |
| 4 | **Audit REQ-SYNC-* scenario coverage** | P2 | Medium | [Accuracy backlog #24](documentation-accuracy.md) |

---

## OQ-010 Research Queue: ProfileSwitch × Nocturne

Items queued for systematic analysis of ProfileSwitch/Override alignment with Nocturne as reference implementation.

### 5. [P2] Nocturne ProfileSwitch treatment model
**Type:** Analysis | **Effort:** Medium  
**Repos:** nocturne  
**Focus:** How Nocturne handles `Profile Switch` eventType in treatment ingestion  
**Status:** ✅ COMPLETE 2026-01-30
**Deliverable:** `docs/10-domain/nocturne-profileswitch-analysis.md`
**Key Finding:** Nocturne **actively applies** percentage/timeshift (cgm-remote-monitor does not)
**Gaps Added:** GAP-NOCTURNE-004
**Requirements Added:** REQ-SYNC-054, REQ-SYNC-055, REQ-SYNC-056

**Source:** [OQ-010](../../OPEN-QUESTIONS.md#oq-010-profileswitch--override-mapping)

### 6. [P2] Nocturne percentage/timeshift handling
**Type:** Analysis | **Effort:** Medium  
**Repos:** nocturne  
**Focus:** How Nocturne handles AAPS-specific `percentage` and `timeshift` fields  
**Questions:**
- Does Nocturne apply percentage scaling when serving profiles?
- Is timeshift rotation applied or stored as metadata?
- What happens when Loop/Trio fetch AAPS ProfileSwitch with percentage!=100?

**Related Gap:** GAP-SYNC-037

### 7. [P2] Nocturne vs cgm-remote-monitor Profile collection sync
**Type:** Comparison | **Effort:** Medium  
**Repos:** nocturne, cgm-remote-monitor  
**Focus:** Compare profile sync behavior between implementations  
**Questions:**
- Same deduplication logic for `profile` collection?
- Same handling of `defaultProfile` field?
- V3 `srvModified` behavior for profile changes?

**Related Gap:** GAP-SYNC-036

### 8. [P2] Nocturne Override/Temporary Target representation
**Type:** Analysis | **Effort:** Medium  
**Repos:** nocturne  
**Focus:** How Nocturne stores and serves override vs temporary target events  
**Questions:**
- Does Nocturne distinguish Loop Override from AAPS Temporary Target?
- Are these stored in treatments with different eventTypes?
- What supersession tracking exists (if any)?

**Related Gaps:** GAP-OVRD-001, GAP-OVRD-002

### 9. [P2] Nocturne V4 ProfileSwitch extensions
**Type:** Discovery | **Effort:** Low  
**Repos:** nocturne  
**Focus:** Identify any V4-specific profile/override endpoints  
**Questions:**
- Does V4 API have profile-specific endpoints beyond V3?
- Any state-span tracking for profile activations?
- Any proposal for standardized profile change history?

**Related Gap:** GAP-NOCTURNE-001

### 10. [P3] Nocturne Rust oref profile handling
**Type:** Analysis | **Effort:** High  
**Repos:** nocturne  
**Focus:** How Rust oref implementation uses profile data  
**Questions:**
- Does Rust oref consume percentage-scaled profiles?
- Same basal/ISF/CR block parsing as JS oref?
- Any divergence in profile time interpretation?

**Related Gap:** GAP-NOCTURNE-002

### 11. [P2] ADR-004 draft: ProfileSwitch → Override mapping rules
**Type:** Decision | **Effort:** Medium  
**Repos:** (workspace internal)  
**Focus:** Draft architectural decision record for OQ-010 resolution  
**Prerequisites:** Items 5-10 above  
**Deliverable:** `docs/90-decisions/adr-004-profile-override-mapping.md`

**Blocks:** OQ-010 resolution

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Nocturne ProfileSwitch treatment model | 2026-01-30 | Item #5; GAP-NOCTURNE-004, 3 REQs |
| Orphaned assertion linkage | 2026-01-29 | 23→0 orphans, +20 REQs created |
| Override-supersede requirements | 2026-01-29 | REQ-OVERRIDE-001 to 005 created |
| Duration/utcOffset unit impact analysis | 2026-01-29 | OQ-030/031 combined, 4 alternatives, 4 REQs |
| Trace REQ-031 through REQ-035 | 2026-01-29 | 6 requirements with scenarios and source refs |
| Extract Loop sync identity fields | 2026-01-29 | 318 lines, ObjectIdCache pattern |
| Full audit: nightscout-connect | 2026-01-29 | 527 lines, XState machines, 5 sources |
| Deep dive: Batch operation ordering | 2026-01-29 | 334 lines, order preservation |
| Extract AAPS NSClient upload schema | 2026-01-28 | 70+ fields, 25 eventTypes |
| Timezone/DST handling terminology | 2026-01-28 | +150 lines, GAP-TZ-004..007 |
| Cross-controller conflict detection | 2026-01-29 | deep dive, 3 gaps |

---

## References

- [mapping/loop/sync-identity-fields.md](../../../mapping/loop/sync-identity-fields.md)
- [docs/10-domain/nightscout-connect-deep-dive.md](../../10-domain/nightscout-connect-deep-dive.md)
- [mapping/cross-project/terminology-matrix.md](../../../mapping/cross-project/terminology-matrix.md)
