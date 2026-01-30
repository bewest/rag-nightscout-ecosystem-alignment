# StateSpan Gap Remediation Mapping

> **Date**: 2026-01-30  
> **Status**: Analysis Complete  
> **Related Items**: sync-identity #20, StateSpan standardization proposal  
> **Prerequisites**: StateSpan standardization proposal ✅

---

## Executive Summary

This document maps existing gaps to StateSpan remediation potential. Of **47 analyzed gaps**, StateSpan V3 extension could:
- **Fully address**: 12 gaps
- **Partially address**: 8 gaps  
- **Unaffected**: 27 gaps

### Key Finding

StateSpan provides the **highest impact** for:
1. Override/TempTarget semantic gaps (GAP-OVRD-*)
2. Profile history and switching gaps (GAP-PROF-*, GAP-SYNC-035)
3. Time-range query gaps (GAP-V4-002)

---

## Gap Remediation Analysis

### Category 1: Fully Addressed by StateSpan (12 gaps)

These gaps would be **completely resolved** by adopting StateSpan V3 extension.

| Gap ID | Title | How StateSpan Addresses |
|--------|-------|-------------------------|
| **GAP-V4-001** | StateSpan API Not Standardized | Directly addressed - V3 standardization |
| **GAP-V4-002** | Profile Activation History Not in V3 | `category=Profile` provides query-able history |
| **GAP-SYNC-004** | Override supersession not tracked in sync | StateSpan `endMills` field explicitly tracks when overrides end |
| **GAP-SYNC-035** | No Profile Switch Events from Loop/Trio | StateSpan Profile category provides explicit switch tracking |
| **GAP-OVRD-005** | No Unified Override Representation | StateSpan Override category unifies Loop/AAPS/Trio |
| **GAP-OVRD-006** | Override Supersession Not Tracked | StateSpan `endMills` + `canonicalId` enable supersession tracking |
| **GAP-PROF-003** | No Override Presets in Nightscout | StateSpan metadata field supports preset names |
| **GAP-PROF-004** | Profile Switching Features (AAPS-only) | StateSpan Profile category normalizes switching semantics |
| **GAP-NOCTURNE-001** | V4 endpoints are Nocturne-specific | V3 standardization provides ecosystem-wide access |
| **GAP-TREAT-010** | eventType Immutability Not Enforced in Nocturne | StateSpan category enum enforces type stability |
| **GAP-TREAT-011** | Temporary Target Type Missing from Nocturne Enum | StateSpan Override category absorbs TempTarget semantics |
| **GAP-SYNC-041** | Missing V3 History Endpoint in Nocturne | StateSpan API provides time-range query capability |

---

### Category 2: Partially Addressed by StateSpan (8 gaps)

These gaps would be **improved but not eliminated** by StateSpan adoption.

| Gap ID | Title | How StateSpan Helps | Remaining Issue |
|--------|-------|---------------------|-----------------|
| **GAP-OVRD-001** | Different eventTypes for Target Overrides | StateSpan unifies under `Override` category | Still need eventType for treatments |
| **GAP-OVRD-002** | insulinNeedsScaleFactor Not in AAPS | StateSpan metadata can include both representations | AAPS uses `profilePercentage` instead |
| **GAP-OVRD-003** | Reason Enum vs Free Text | StateSpan metadata supports both | No standardized reason vocabulary |
| **GAP-OVRD-004** | Duration Units Differ | StateSpan uses `endMills` (explicit end time) | Historical data still has unit issues |
| **GAP-OVRD-007** | Duration Unit Mismatch in Loop Presets | StateSpan doesn't need duration | Preset definitions still differ |
| **GAP-SYNC-037** | Percentage/Timeshift Not Portable | StateSpan Profile metadata includes both | Semantics differ (applied vs raw) |
| **GAP-NOCTURNE-005** | Profile API Returns Raw Values | StateSpan could expose computed values | Requires additional computation layer |
| **GAP-PROF-001** | Time Format Incompatibility | StateSpan uses epoch milliseconds | Profile schedule formats still differ |

---

### Category 3: Unaffected by StateSpan (27 gaps)

These gaps require different solutions - StateSpan doesn't address them.

#### Sync Identity Issues (not StateSpan's domain)

| Gap ID | Title | Why Not Addressed |
|--------|-------|-------------------|
| GAP-SYNC-001 | Loop Uses POST-only, No Idempotent Upsert | API verb choice, not data model |
| GAP-SYNC-005 | Loop ObjectIdCache not persistent | Client-side cache issue |
| GAP-SYNC-006 | Loop uses Nightscout v1 API only | API version adoption |
| GAP-SYNC-007 | syncIdentifier format not standardized | Identity field format |
| GAP-SYNC-008 | No Cross-Client Sync Conflict Resolution | Conflict resolution logic |
| GAP-SYNC-009 | V1 API Lacks Identifier Field | V1 API design |
| GAP-SYNC-010 | No Sync Status Feedback | Sync protocol issue |
| GAP-SYNC-029 | No Cross-Controller Deduplication | Deduplication logic |
| GAP-SYNC-030 | No Controller Conflict Warning | Multi-controller detection |
| GAP-SYNC-031 | Profile Sync Ambiguity | Sync semantics |
| GAP-SYNC-032 | Loop/Trio Missing identifier Field | Client implementation |
| GAP-SYNC-033 | xDrip+ UUID Not Sent as identifier | Client implementation |
| GAP-SYNC-034 | No Cross-Controller Identity Standard | Identity standard |
| GAP-SYNC-038 | Profile Deduplication Fallback Missing | Nocturne-specific |
| GAP-SYNC-039 | Profile srvModified Field Missing | Nocturne-specific |
| GAP-SYNC-040 | Delete Semantics Differ | Delete semantics |
| GAP-BATCH-001 | Batch Deduplication Not Enforced | Database constraint |

#### Profile Schema Issues (not StateSpan's domain)

| Gap ID | Title | Why Not Addressed |
|--------|-------|-------------------|
| GAP-PROF-002 | Missing Safety Limits in Nightscout | Schema design |
| GAP-PROF-005 | DIA vs Insulin Model Mismatch | Insulin model semantics |
| GAP-PROF-006 | Basal Schedule Time Format Inconsistency | Profile schema |
| GAP-PROF-007 | 30-Minute Basal Rate Granularity | Pump limitations |
| GAP-PROF-008 | Basal Rate Precision Varies | Pump limitations |

#### Treatment Issues (not StateSpan's domain)

| Gap ID | Title | Why Not Addressed |
|--------|-------|-------------------|
| GAP-TREAT-001 | Absorption Time Unit Mismatch | Carb model semantics |
| GAP-TREAT-002 | Duration Unit Inconsistency | Point-in-time events |
| GAP-TREAT-003 | No Explicit SMB Event Type | Bolus classification |
| GAP-TREAT-004 | Split/Extended Bolus Representation | Bolus model |
| GAP-TREAT-005 | Loop POST-Only Creates Duplicates | API verb choice |
| GAP-TREAT-006 | Retroactive Edit Handling | Edit semantics |
| GAP-TREAT-007 | eCarbs Not Universally Supported | Carb model semantics |

---

## Remediation Priority Matrix

### High Priority (Implement First)

| Gap ID | Impact | Effort to Remediate via StateSpan |
|--------|--------|-----------------------------------|
| **GAP-V4-001** | Critical | Low - already in proposal |
| **GAP-V4-002** | High | Low - category=Profile query |
| **GAP-OVRD-005** | High | Medium - unified schema needed |
| **GAP-SYNC-004** | High | Low - endMills field |
| **GAP-NOCTURNE-001** | Medium | Low - V3 standardization |

### Medium Priority (Phase 2)

| Gap ID | Impact | Effort to Remediate via StateSpan |
|--------|--------|-----------------------------------|
| **GAP-OVRD-006** | Medium | Medium - canonicalId linking |
| **GAP-SYNC-035** | Medium | Low - Profile category |
| **GAP-PROF-004** | Medium | Medium - semantics alignment |
| **GAP-TREAT-010** | Medium | Low - category enum |
| **GAP-TREAT-011** | Medium | Low - Override category |

### Lower Priority (Phase 3)

| Gap ID | Impact | Effort to Remediate via StateSpan |
|--------|--------|-----------------------------------|
| **GAP-PROF-003** | Low | Medium - metadata design |
| **GAP-SYNC-041** | Low | Low - time-range query |

---

## Implementation Mapping

### StateSpan V3 Phase 1: Core Categories

| Category | Gaps Addressed | Priority |
|----------|----------------|----------|
| `Profile` | GAP-V4-002, GAP-SYNC-035, GAP-PROF-004 | High |
| `Override` | GAP-OVRD-005, GAP-OVRD-006, GAP-SYNC-004, GAP-TREAT-011 | High |
| `PumpMode` | GAP-NOCTURNE-001 (pump state tracking) | Medium |
| `TempBasal` | (future - not gap-driven) | Low |

### StateSpan V3 Phase 2: Metadata Extensions

| Metadata Field | Gaps Addressed | Category |
|----------------|----------------|----------|
| `insulinNeedsScaleFactor` | GAP-OVRD-002 | Override |
| `profilePercentage` | GAP-OVRD-002, GAP-SYNC-037 | Override, Profile |
| `targetTop/targetBottom` | GAP-OVRD-001 | Override |
| `reason` | GAP-OVRD-003 | Override |
| `presetName` | GAP-PROF-003 | Override |
| `timeshift` | GAP-SYNC-037 | Profile |

### StateSpan V3 Phase 3: Time-Range API

| Feature | Gaps Addressed |
|---------|----------------|
| `from/to` query params | GAP-V4-002, GAP-SYNC-041 |
| `active=true` filter | GAP-OVRD-006 (current state) |
| `endMills` field | GAP-SYNC-004, GAP-OVRD-006 |

---

## Requirements Mapping

### Existing Requirements Enhanced by StateSpan

| Requirement | How StateSpan Enhances |
|-------------|------------------------|
| REQ-SYNC-054 | StateSpan Profile category enables percentage tracking |
| REQ-SYNC-055 | StateSpan metadata includes timeshift |
| REQ-SYNC-057 | StateSpan can expose raw or computed values |
| REQ-OVRD-001 | StateSpan unifies override representation |
| REQ-OVRD-002 | StateSpan metadata standardizes factor fields |

### New Requirements from This Analysis

See [traceability/connectors-requirements.md](../../traceability/connectors-requirements.md) for:
- REQ-STATESPAN-001: Time Range Query
- REQ-STATESPAN-002: Category Filtering
- REQ-STATESPAN-003: Active Span Query
- REQ-STATESPAN-004: Treatment Translation
- REQ-STATESPAN-005: Source Tracking

---

## Gaps NOT Remediated - Recommended Actions

For the 27 gaps **not addressed** by StateSpan, alternative solutions:

### Sync Identity (17 gaps)

**Recommended**: Separate "Sync Identity Standardization" initiative:
1. Define cross-controller identity format (GAP-SYNC-034)
2. Enforce unique constraint on identifier (GAP-BATCH-001)
3. Add conflict detection API (GAP-SYNC-030)

### Profile Schema (5 gaps)

**Recommended**: Profile schema harmonization PR:
1. Standardize time format (GAP-PROF-006)
2. Add safety limit fields (GAP-PROF-002)
3. Define DIA/insulin model relationship (GAP-PROF-005)

### Treatment Model (5 gaps)

**Recommended**: Treatment eventType consolidation:
1. Add SMB eventType (GAP-TREAT-003)
2. Standardize duration units (GAP-TREAT-002)
3. Define extended bolus model (GAP-TREAT-004)

---

## Conclusion

StateSpan V3 extension provides high-leverage gap remediation:
- **12 gaps fully addressed** (26%)
- **8 gaps partially addressed** (17%)
- **27 gaps require alternative solutions** (57%)

The highest-value StateSpan implementation targets:
1. Override unification (5 gaps)
2. Profile history (3 gaps)
3. Nocturne compatibility (2 gaps)

**Recommended next step**: Update StateSpan V3 OpenAPI spec to include gap annotations (`x-aid-gap`) for each addressed gap.

---

## References

- [StateSpan Standardization Proposal](../../docs/sdqctl-proposals/statespan-standardization-proposal.md)
- [Sync Identity Gaps](../../traceability/sync-identity-gaps.md)
- [Algorithm Gaps](../../traceability/algorithm-gaps.md)
- [Connectors Gaps](../../traceability/connectors-gaps.md)
- [ADR-004: Profile Override Mapping](../../docs/90-decisions/adr-004-profile-override-mapping.md)
