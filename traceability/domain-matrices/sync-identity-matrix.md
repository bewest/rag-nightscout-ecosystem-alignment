# Sync-Identity Domain Traceability Matrix

> **Generated**: 2026-02-01  
> **Updated**: 2026-02-01 (cycle 94 - sync-identity-reqs.yaml added)  
> **Domain**: Sync & Identity  
> **Purpose**: REQ↔GAP↔Assertion cross-reference matrix

---

## Summary

| Metric | Count |
|--------|-------|
| Requirements (REQ-SYNC-*) | 32 |
| Gaps (GAP-SYNC-*) | 25 |
| Assertions with coverage | 30 REQs (94%), 9 GAPs |
| Uncovered REQs | 2 |
| Uncovered GAPs | 16 |

**Status**: Sync-identity domain at 94% REQ coverage. 2 remaining REQs are documentation-only.

## Requirements Coverage Matrix

### Covered by Assertions (15)

| Requirement | Description | Assertion File | Assertion IDs |
|-------------|-------------|----------------|---------------|
| REQ-SYNC-036 | syncIdentifier Field Preservation | sync-deduplication.yaml | syncidentifier-preserved |
| REQ-SYNC-037 | identifier Field Preservation | sync-deduplication.yaml | identifier-preserved |
| REQ-SYNC-038 | enteredBy Field Preservation | sync-deduplication.yaml | enteredby-preserved |
| REQ-SYNC-039 | utcOffset Field Preservation | sync-deduplication.yaml | utcoffset-preserved |
| REQ-SYNC-040 | Soft Delete Sets isValid=false | sync-deduplication.yaml | softdelete-isvalid-false |
| REQ-SYNC-041 | Pump Composite Key Immutability | sync-deduplication.yaml | pump-composite-key-immutable |
| REQ-SYNC-042 | Core Treatment Fields Immutability | sync-deduplication.yaml | core-treatment-fields-immutable |
| REQ-SYNC-043 | Server Timestamps Immutability | sync-deduplication.yaml | server-timestamps-immutable |
| REQ-SYNC-044 | enteredBy Self-Exclusion Filter | sync-deduplication.yaml | enteredby-filter-excludes-self |
| REQ-SYNC-045 | History Endpoint Modified-After Filter | sync-deduplication.yaml | history-returns-modified-after |
| REQ-SYNC-046 | History Endpoint Includes Deleted | sync-deduplication.yaml | history-includes-soft-deleted |
| REQ-SYNC-047 | Query by Client Identifier | sync-deduplication.yaml | query-by-identifier |
| REQ-SYNC-048 | Cross-Controller Coexistence | sync-deduplication.yaml | cross-controller-coexistence |
| REQ-SYNC-049 | srvModified Updated on Change | sync-deduplication.yaml | srvmodified-updated-on-change |
| REQ-SYNC-050 | srvCreated Set on Creation | sync-deduplication.yaml | srvcreated-set-on-create |

### Newly Covered Requirements (15) - sync-identity-reqs.yaml

| Requirement | Description | Assertions |
|-------------|-------------|------------|
| REQ-SYNC-001 | Document WebSocket API | ✅ 2 assertions |
| REQ-SYNC-002 | Consistent Sync Identity Across API Versions | ✅ 2 assertions |
| REQ-SYNC-003 | Sync Status Response | ✅ 2 assertions |
| REQ-SYNC-010 | Sync Identity Mapping | ✅ 2 assertions |
| REQ-SYNC-051 | Profile Change Visibility | ✅ 1 assertion |
| REQ-SYNC-052 | Percentage Handling | ✅ 1 assertion |
| REQ-SYNC-053 | Profile Deduplication | ✅ 1 assertion |
| REQ-SYNC-054 | ProfileSwitch Percentage Application | ✅ 1 assertion |
| REQ-SYNC-055 | ProfileSwitch Timeshift Application | ✅ 1 assertion |
| REQ-SYNC-056 | ProfileJson Embedding Storage | ✅ 1 assertion |
| REQ-SYNC-057 | Profile Effective Values API | ✅ 1 assertion |
| REQ-SYNC-058 | ProfileSwitch Metadata in Profile Response | ✅ 1 assertion |
| REQ-SYNC-059 | Profile Deduplication Consistency | ✅ 1 assertion |
| REQ-SYNC-060 | Profile srvModified Support | ✅ 1 assertion |
| REQ-SYNC-061 | Profile Soft Delete | ✅ 1 assertion |

### Remaining Uncovered (2)

| Requirement | Description | Priority | Notes |
|-------------|-------------|----------|-------|
| REQ-SYNC-004 | WebSocket Event Payload Schemas | Low | Documentation deliverable |
| REQ-SYNC-005 | WebSocket Error Handling | Low | Documentation deliverable |

---

## Gaps Coverage Matrix

### Covered by Assertions (3)

| Gap | Description | Assertion File | Assertion IDs |
|-----|-------------|----------------|---------------|
| GAP-SYNC-001 | Loop Uses POST-only, No Idempotent Upsert | sync-deduplication.yaml | identifier-preserved, syncidentifier-preserved |
| GAP-SYNC-008 | No Cross-Client Sync Conflict Resolution | sync-deduplication.yaml | cross-controller-coexistence |
| GAP-SYNC-009 | V1 API Lacks Identifier Field | sync-deduplication.yaml | query-by-identifier |

### Uncovered Gaps (22)

| Gap | Description | Priority | Blocker |
|-----|-------------|----------|---------|
| GAP-SYNC-002 | Effect timelines not uploaded to Nightscout | Low | Design decision |
| GAP-SYNC-004 | Override supersession not tracked in sync | Medium | - |
| GAP-SYNC-005 | Loop ObjectIdCache not persistent | Medium | iOS app change |
| GAP-SYNC-006 | Loop uses Nightscout v1 API only | High | Major migration |
| GAP-SYNC-007 | syncIdentifier format not standardized | High | Cross-project |
| GAP-SYNC-010 | No Sync Status Feedback | Medium | API enhancement |
| GAP-SYNC-029 | No Cross-Controller Deduplication | High | Core interop |
| GAP-SYNC-030 | No Controller Conflict Warning | Medium | UX enhancement |
| GAP-SYNC-031 | Profile Sync Ambiguity | Medium | - |
| GAP-SYNC-032 | Loop/Trio Missing identifier Field | High | V3 migration |
| GAP-SYNC-033 | xDrip+ UUID Not Sent as identifier | Medium | - |
| GAP-SYNC-034 | No Cross-Controller Identity Standard | High | RFC needed |
| GAP-SYNC-035 | No Profile Switch Events from Loop/Trio | Medium | - |
| GAP-SYNC-036 | ProfileSwitch Embedded JSON Size | Low | Storage |
| GAP-SYNC-037 | Percentage/Timeshift Not Portable | Medium | - |
| GAP-SYNC-038 | Profile Deduplication Fallback Missing in Nocturne | Medium | Nocturne |
| GAP-SYNC-039 | Profile srvModified Field Missing in Nocturne | Medium | Nocturne |
| GAP-SYNC-040 | Delete Semantics Differ (Hard vs Soft Delete) | High | Ready Queue #2 |
| GAP-SYNC-041 | Missing V3 History Endpoint in Nocturne | Medium | Nocturne |
| GAP-SYNC-042 | Trio Missing objectId Cache | Medium | - |
| GAP-SYNC-043 | Trio No Update Operation Support | Medium | - |
| GAP-SYNC-044 | Trio Profile Contains APNS Push Credentials | Low | Security |

---

## Cross-Reference: Related Assertion Files

| File | REQs Covered | GAPs Addressed |
|------|--------------|----------------|
| `conformance/assertions/sync-deduplication.yaml` | 15 | 3 |
| `conformance/assertions/treatment-sync.yaml` | 7 (REQ-TREAT-*) | 7 (GAP-TREAT-*) |
| `conformance/assertions/override-supersede.yaml` | - | GAP-SYNC-004 (indirect) |

---

## Priority Action Items

### High Priority (Core Interoperability)

1. **REQ-SYNC-002 / REQ-SYNC-010**: Create sync identity assertions
   - Need: Assertion file for cross-API version identity
   - Blocks: GAP-SYNC-007, GAP-SYNC-034

2. **GAP-SYNC-006 / GAP-SYNC-032**: V3 API migration
   - Need: Loop/Trio V3 API integration testing
   - Prerequisite: Ready Queue #1 (Loop Swift runner)

3. **GAP-SYNC-029**: Cross-controller deduplication
   - Need: Multi-controller conflict scenario assertions
   - Related: GAP-SYNC-030 (conflict warning)

### Medium Priority (Nocturne Alignment)

4. **GAP-SYNC-038-041**: Nocturne parity gaps
   - Need: Nocturne-specific assertion file
   - Related: Ready Queue #2 (Nocturne soft delete)

5. **REQ-SYNC-051-061**: Profile sync requirements
   - Need: Profile-specific assertion file
   - Consider: Move to separate profile-matrix.md

---

## Related Documents

- [sync-identity-gaps.md](../sync-identity-gaps.md) - Full gap descriptions
- [sync-identity-requirements.md](../sync-identity-requirements.md) - Full requirement specs
- [orphan-artifact-priorities.md](../orphan-artifact-priorities.md) - Priority tiers
- [sync-deduplication.yaml](../../conformance/assertions/sync-deduplication.yaml) - Primary assertions
