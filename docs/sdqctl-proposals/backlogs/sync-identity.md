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
**Status:** ✅ COMPLETE 2026-01-30
**Deliverable:** `docs/10-domain/nocturne-percentage-timeshift-handling.md`
**Key Finding:** Profile API returns raw values; scaling only applied internally for IOB/COB/bolus
**Gaps Added:** GAP-NOCTURNE-005
**Requirements Added:** REQ-SYNC-057, REQ-SYNC-058

**Questions Answered:**
- ✅ Nocturne applies percentage scaling internally only (not via API)
- ✅ Timeshift rotation applied internally only
- ✅ Loop/Trio receive raw profiles, unaware of AAPS percentage!=100

**Related Gap:** GAP-SYNC-037

### 7. [P2] Nocturne vs cgm-remote-monitor Profile collection sync
**Type:** Comparison | **Effort:** Medium  
**Repos:** nocturne, cgm-remote-monitor  
**Focus:** Compare profile sync behavior between implementations  
**Status:** ✅ COMPLETE 2026-01-30
**Deliverable:** `docs/10-domain/nocturne-cgm-remote-monitor-profile-sync.md`
**Key Findings:**
- Deduplication: cgm-remote-monitor uses `created_at` fallback; Nocturne does not
- srvModified: Missing from Nocturne Profile model
- Delete: cgm-remote-monitor soft deletes; Nocturne hard deletes
**Gaps Added:** GAP-SYNC-038, GAP-SYNC-039, GAP-SYNC-040
**Requirements Added:** REQ-SYNC-059, REQ-SYNC-060, REQ-SYNC-061

**Questions Answered:**
- ✅ Different deduplication: cgm-remote-monitor uses `identifier` OR `created_at`; Nocturne only `Id`/`OriginalId`
- ✅ Same `defaultProfile` handling: both use "Default" as convention
- ✅ srvModified differs: cgm-remote-monitor has explicit field; Nocturne uses Mills

**Related Gap:** GAP-SYNC-036

### 8. [P2] Nocturne Override/Temporary Target representation
**Type:** Analysis | **Effort:** Medium  
**Repos:** nocturne  
**Focus:** How Nocturne stores and serves override vs temporary target events  
**Status:** ✅ COMPLETE 2026-01-30
**Deliverable:** `docs/10-domain/nocturne-override-temptarget-analysis.md`
**Key Findings:**
- Loop uses `Temporary Override`; AAPS uses `Temporary Target` - no unification
- No supersession tracking in either system
- V4 StateSpan provides unified query but no override linking
- Duration unit mismatch: presets in seconds, treatments in minutes
**Gaps Added:** GAP-OVRD-005, GAP-OVRD-006, GAP-OVRD-007
**Requirements Added:** REQ-OVRD-004, REQ-OVRD-005

**Questions Answered:**
- ✅ Yes, Nocturne distinguishes Loop Override from AAPS Temporary Target (different eventTypes)
- ✅ Both stored in treatments with different eventTypes
- ✅ No supersession tracking exists

**Related Gaps:** GAP-OVRD-001, GAP-OVRD-002

### 9. [P2] Nocturne V4 ProfileSwitch extensions
**Type:** Discovery | **Effort:** Low  
**Repos:** nocturne  
**Focus:** Identify any V4-specific profile/override endpoints  
**Status:** ✅ COMPLETE 2026-01-30
**Deliverable:** `docs/10-domain/nocturne-v4-profile-extensions.md`
**Key Findings:**
- V4 StateSpan API (`/api/v4/state-spans/profiles`) provides profile activation history
- V3 API only has profile document CRUD, not activation tracking
- ChartDataController returns ProfileSpans in chart data response
- StateSpan model includes CanonicalId for deduplication, Sources array for merge
- 9 categories: Profile, Override, TempBasal, PumpMode, PumpConnectivity, Sleep, Exercise, Illness, Travel
**Gaps Added:** GAP-V4-001, GAP-V4-002
**Requirements Added:** REQ-V4-001, REQ-V4-002

**Questions Answered:**
- ✅ Yes, V4 has profile-specific endpoints (`/api/v4/state-spans/profiles`)
- ✅ Yes, state-span tracking for profile activations exists
- ✅ StateSpan model provides foundation but is Nocturne-specific (not standardized)

**Related Gap:** GAP-NOCTURNE-001

### 10. [P3] Nocturne Rust oref profile handling ✅
**Type:** Analysis | **Effort:** High  
**Repos:** nocturne  
**Focus:** How Rust oref implementation uses profile data  
**Questions:**
- ✅ Does Rust oref consume percentage-scaled profiles? → **NO** (PredictionService bypasses ProfileService)
- ✅ Same basal/ISF/CR block parsing as JS oref? → **YES** (minutes-from-midnight, i-index sorting)
- ✅ Any divergence in profile time interpretation? → **NO** (algorithm equivalent)

**Deliverable:** [Rust oref Profile Analysis](../../docs/10-domain/nocturne-rust-oref-profile-analysis.md)

**Gaps Added:** GAP-OREF-001, GAP-OREF-002, GAP-OREF-003

**Related Gap:** GAP-NOCTURNE-002

### 11. [P2] ADR-004 draft: ProfileSwitch → Override mapping rules ✅
**Type:** Decision | **Effort:** Medium  
**Repos:** (workspace internal)  
**Focus:** Draft architectural decision record for OQ-010 resolution  
**Prerequisites:** Items 5-10 above ✅
**Deliverable:** `docs/90-decisions/adr-004-profile-override-mapping.md`

**Completed:** 2026-01-30

**Decision Summary:**
1. Accept both Override and ProfileSwitch as valid representations
2. Define semantic equivalence rules for translation
3. Require percentage application at query time
4. Recommend StateSpan model for profile history

**Gaps Addressed:** GAP-NOCTURNE-004/005, GAP-OVRD-005/006, GAP-OREF-001

**OQ-010:** ✅ RESOLVED

---

## OQ-010 Extended: Nocturne Systematic Research

Per user request (2026-01-30), additional research focused on Nocturne as it relates to issues mentioned across the docs. These items extend the resolved OQ-010 with deeper Nocturne-specific analysis.

### 12. [P2] Nocturne SignalR→Socket.IO bridge behavior ✅
**Type:** Analysis | **Effort:** Medium  
**Repos:** nocturne  
**Focus:** Document message translation, latency impact, event fidelity  
**Status:** ✅ COMPLETE 2026-01-30
**Deliverable:** `docs/10-domain/nocturne-signalr-bridge-analysis.md`

**Key Findings:**
- Bridge provides **functional parity** for core events (dataUpdate, alarm, storage)
- Latency overhead: **5-10ms** per message (acceptable for CGM data)
- Event ordering preserved within event types
- Missing features: `clients` event, compression

**Gaps Added:** GAP-BRIDGE-001, GAP-BRIDGE-002
**Gap Updated:** GAP-NOCTURNE-003 (confirmed with measurements)

### 13. [P2] Nocturne Rust oref algorithm conformance testing ✅
**Type:** Verification | **Effort:** High  
**Repos:** nocturne, oref0  
**Focus:** Create test vectors comparing JS oref0 vs Rust oref outputs  
**Status:** ✅ COMPLETE 2026-01-30
**Deliverable:** `conformance/scenarios/nocturne-oref/README.md`, `iob-tests.yaml`

**Key Findings:**
- IOB bilinear: ✅ Same formula, same polynomial coefficients
- IOB exponential: ✅ Same LoopKit #388 formula
- COB algorithm: ✅ Same deviation-based approach
- Precision: Both IEEE 754 f64, < 1e-15 difference

**Gaps Added:** GAP-OREF-CONFORMANCE-001, GAP-OREF-CONFORMANCE-002, GAP-OREF-CONFORMANCE-003
**Requirements Added:** REQ-OREF-CONFORM-001, REQ-OREF-CONFORM-002, REQ-OREF-CONFORM-003

### 14. [P2] Nocturne V4 StateSpan standardization proposal ✅
**Type:** Proposal | **Effort:** Medium  
**Repos:** nocturne, cgm-remote-monitor  
**Focus:** Evaluate V4 StateSpan model for ecosystem adoption  
**Status:** ✅ COMPLETE 2026-01-30
**Deliverable:** `docs/sdqctl-proposals/statespan-standardization-proposal.md`

**Key Findings:**
- StateSpan provides cleaner abstraction than treatment-based time ranges
- 9 categories, minimal viable subset: Profile, Override, TempBasal, PumpMode
- Recommendation: V3 extension (not V4-only) for backward compatibility
- 4-phase migration path proposed

**Gaps Added:** GAP-STATESPAN-001, GAP-STATESPAN-002, GAP-STATESPAN-003
**Requirements Added:** REQ-STATESPAN-001 through REQ-STATESPAN-005

### 15. [P2] Nocturne PostgreSQL migration field fidelity ✅
**Type:** Verification | **Effort:** Medium  
**Repos:** nocturne  
**Focus:** Verify all cgm-remote-monitor fields are preserved in migration  
**Status:** ✅ COMPLETE 2026-01-30
**Deliverable:** `mapping/nocturne/migration-field-fidelity.md`

**Key Findings:**
- **Full field fidelity** through hybrid approach: typed columns + JSONB
- 60+ typed treatment columns, including AAPS/Loop-specific fields
- Nested objects stored as JSONB (loop, openaps, pump, etc.)
- `additional_properties` JSONB captures arbitrary unknown fields
- `original_id` preserves MongoDB ObjectId for migration tracking
- **srvModified gap**: Computed from mills, not stored independently

**Questions Answered:**
- ✅ No MongoDB fields lost - all captured in typed columns or JSONB
- ✅ `OriginalId` sufficient for migration identity
- ✅ Nested objects fully preserved via JSONB columns
- ✅ Plugin fields captured in `additional_properties` JSONB

**Gaps Added:** GAP-MIGRATION-001, GAP-MIGRATION-002, GAP-MIGRATION-003
**Requirements Added:** REQ-MIGRATION-001 through REQ-MIGRATION-004

**Related Gaps:** GAP-SYNC-039, GAP-NOCTURNE-001  
**Deliverable:** `mapping/nocturne/migration-field-fidelity.md`

### 16. [P3] Nocturne connector polling interval coordination
**Type:** Analysis | **Effort:** Low  
**Repos:** nocturne  
**Focus:** Document how multiple connectors coordinate polling  
**Questions:**
- Are connector polls staggered or concurrent?
- What prevents rate-limit exhaustion with multiple CGM sources?
- How does Nightscout→Nocturne connector handle data that came from Nocturne?
- Any deduplication for multi-source same-data?

**Related Gaps:** GAP-CONNECT-001, GAP-NOCTURNE-001  
**Deliverable:** `docs/10-domain/nocturne-connector-coordination.md`

### 17. [P2] Nocturne srvModified field implementation
**Type:** Gap Remediation | **Effort:** Medium  
**Repos:** nocturne, cgm-remote-monitor  
**Focus:** Analyze impact of missing srvModified in Nocturne Profile model  
**Questions:**
- Does missing srvModified break Loop/AAPS sync polling?
- Can Nocturne add srvModified to maintain V3 parity?
- What is current Profile modification tracking mechanism?
- Impact on profile history queries?

**Related Gap:** GAP-SYNC-039  
**Deliverable:** `docs/10-domain/nocturne-srvmodified-gap-analysis.md`

### 18. [P2] Nocturne soft-delete vs hard-delete interop
**Type:** Analysis | **Effort:** Medium  
**Repos:** nocturne, cgm-remote-monitor  
**Focus:** Document deletion behavior differences and sync impact  
**Questions:**
- Does hard-delete break isValid=false sync pattern?
- How do Loop/AAPS handle deleted treatments from Nocturne?
- Is there audit trail for deletions?
- Impact on undo/recovery scenarios?

**Related Gap:** GAP-SYNC-040  
**Deliverable:** `docs/10-domain/nocturne-deletion-semantics.md`

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Nocturne SignalR bridge analysis | 2026-01-30 | Item #12; GAP-BRIDGE-001/002, REQ-BRIDGE-001/002/003 |
| ADR-004 ProfileSwitch mapping | 2026-01-30 | Item #11; OQ-010 resolved |
| Nocturne Rust oref profile handling | 2026-01-30 | Item #10; GAP-OREF-001/002/003, 3 REQs |
| Nocturne V4 ProfileSwitch extensions | 2026-01-30 | Item #9; GAP-V4-001/002, 2 REQs |
| Nocturne Override/TempTarget representation | 2026-01-30 | Item #8; GAP-OVRD-005/006/007, 2 REQs |
| Nocturne vs cgm-remote-monitor Profile sync | 2026-01-30 | Item #7; GAP-SYNC-038/039/040, 3 REQs |
| Nocturne percentage/timeshift handling | 2026-01-30 | Item #6; GAP-NOCTURNE-005, 2 REQs |
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
