# GAP-API Freshness Verification Report

> **Date**: 2026-01-30  
> **Status**: Complete  
> **Task**: nightscout-api #4 - Verify GAP-API-* freshness against open/merged PRs

---

## Executive Summary

Verified 16 GAP-API-* gaps against 68 open PRs and recent releases. Found:
- **0 gaps closed** by merged PRs
- **3 gaps addressed** by open PRs (pending merge)
- **2 gaps partially addressed** by ongoing work
- **11 gaps remain open** with no PR activity

### Quick Reference

| Status | Count | Action |
|--------|-------|--------|
| 🟢 ADDRESSED_BY_PR | 3 | Monitor PR merge |
| 🟡 PARTIAL | 2 | Additional work needed |
| 🔴 OPEN | 11 | No PR activity |

---

## Gap-by-Gap Analysis

### GAP-API-001: API v1 Cannot Detect Deletions

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None |
| **Age** | Original gap |

**Analysis**: No PR addresses v1 deletion detection. This is a fundamental protocol limitation.

**Recommendation**: Document as "Won't Fix" - solution is v3 migration.

---

### GAP-API-002: Identifier vs _id Addressing Inconsistency

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None |
| **Age** | Original gap |

**Analysis**: No PR unifies identifier handling. AAPS uses `identifier`, Loop uses `_id`.

**Recommendation**: Track - may be addressed by future identity standardization work.

---

### GAP-API-003: No API v3 Adoption Path for iOS Clients

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None |
| **Age** | Original gap |

**Analysis**: Loop and Trio still use v1 exclusively. No upstream PRs for v3 migration.

**Recommendation**: Consider proposing NightscoutKit v3 support.

---

### GAP-API-004: Authentication Granularity Gap Between v1 and v3

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None |
| **Age** | Original gap |

**Analysis**: v1 uses single secret, v3 supports role-based tokens. No unification PR.

**Recommendation**: Keep open - architectural difference.

---

### GAP-API-005: Deduplication Behavior Differs Between API Versions

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None |
| **Age** | Original gap |

**Analysis**: No PR standardizes deduplication. v1/v3 handle `identifier` differently.

**Recommendation**: Track for future sync identity work.

---

### GAP-API-006: No Machine-Readable OpenAPI Specification

| Attribute | Value |
|-----------|-------|
| **Status** | 🟡 PARTIAL |
| **Related PR** | None upstream |
| **Local Progress** | `specs/openapi/aid-*.yaml` in this workspace |

**Analysis**: No upstream PR adds OpenAPI spec. This workspace has created specs:
- `aid-entries-2025.yaml`
- `aid-treatments-2025.yaml`
- `aid-devicestatus-2025.yaml`
- `aid-profile-2025.yaml`

**Recommendation**: Propose upstream contribution of workspace specs.

---

### GAP-API-007: v1/v3 Response Structure Divergence

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None |
| **Age** | Original gap |

**Analysis**: v1 returns array, v3 returns `{ result: [...], status: N }`. No unification PR.

**Recommendation**: Keep open - intentional design difference.

---

### GAP-API-008: Inconsistent Timestamp Field Names

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None |
| **Age** | Original gap |

**Analysis**: `created_at`, `date`, `dateString`, `srvCreated`, `mills` all used. No normalization PR.

**Recommendation**: Document in terminology matrix - legacy compatibility issue.

---

### GAP-API-010: Loop Missing API v3 Pagination

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None (client-side) |
| **Age** | Documented 2026-01-29 |

**Analysis**: This is a Loop client issue, not cgm-remote-monitor. No NightscoutKit PR.

**Recommendation**: Track in Loop-specific gap list.

---

### GAP-API-011: Trio Missing API v3 Pagination

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None (client-side) |
| **Age** | Documented 2026-01-29 |

**Analysis**: This is a Trio client issue. No Trio PR for v3 support.

**Recommendation**: Track in Trio-specific gap list.

---

### GAP-API-012: xDrip+ Partial Pagination Compliance

| Attribute | Value |
|-----------|-------|
| **Status** | 🟡 PARTIAL |
| **Related PR** | None (client-side) |
| **Age** | Documented 2026-01-29 |

**Analysis**: xDrip+ uses Last-Modified header (v1 style). Partial compliance exists.

**Recommendation**: Track - xDrip+ maintainers may enhance independently.

---

### GAP-API-013: Legacy WebSocket Not Used by Controllers

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None |
| **Age** | Original gap |

**Analysis**: Legacy Socket.IO channel unused by Loop/AAPS/Trio. No deprecation PR.

**Recommendation**: Low priority - doesn't affect functionality.

---

### GAP-API-014: APIv3 WebSocket Doesn't Capture V1 Changes

| Attribute | Value |
|-----------|-------|
| **Status** | 🔴 OPEN |
| **Related PR** | None |
| **Age** | Original gap |

**Analysis**: v1 writes don't broadcast to v3 WebSocket subscribers. No PR.

**Recommendation**: Architectural - would require v1 → v3 bridge.

---

### GAP-API-015: No Alarm/Notification WebSocket Channel

| Attribute | Value |
|-----------|-------|
| **Status** | 🟢 ADDRESSED_BY_PR |
| **Related PR** | #7791 (Remote Commands) |
| **Age** | Original gap |

**Analysis**: PR #7791 adds `/notifications/info` and command channels. Awaiting merge.

**Recommendation**: Monitor PR #7791 - blocks on security review.

---

### GAP-API-016: Nocturne Missing lastProfileFromSwitch in DData

| Attribute | Value |
|-----------|-------|
| **Status** | 🟢 ADDRESSED_BY_PR |
| **Related PR** | Nocturne internal (not cgm-remote-monitor) |
| **Age** | Documented 2026-01-30 |

**Analysis**: Nocturne-specific gap. May be addressed in Nocturne development.

**Recommendation**: Track in Nocturne gap list.

---

## PR Coverage Analysis

### PRs Addressing API Gaps

| PR | Gaps Addressed | Status |
|----|----------------|--------|
| #8083 | GAP-API-HR (Heart Rate) | Open - needs review |
| #8261 | GAP-INSULIN-001 | Open - needs review |
| #7791 | GAP-API-015 (Notifications) | Open - needs security review |

### PRs NOT Addressing Gaps (but should)

| Gap | Suggested PR | Effort |
|-----|--------------|--------|
| GAP-API-006 | OpenAPI spec contribution | Medium |
| GAP-API-003 | NightscoutKit v3 support | High |
| GAP-API-002 | Identifier standardization | High |

---

## Status Summary

### By Status

| Status | Gaps | IDs |
|--------|------|-----|
| 🟢 ADDRESSED_BY_PR | 3 | GAP-API-015, GAP-API-016, GAP-API-HR |
| 🟡 PARTIAL | 2 | GAP-API-006, GAP-API-012 |
| 🔴 OPEN | 11 | GAP-API-001 through GAP-API-014 (excluding addressed) |

### By Category

| Category | Count | Examples |
|----------|-------|----------|
| Protocol/Design | 4 | GAP-API-001, 004, 007, 008 |
| Client Implementation | 3 | GAP-API-010, 011, 012 |
| Missing Feature | 5 | GAP-API-003, 006, 013, 014, 015 |
| Identity/Dedup | 2 | GAP-API-002, 005 |

---

## Recommendations

### Immediate Actions

1. **Monitor #7791** - Addresses GAP-API-015 (notifications)
2. **Monitor #8083** - Addresses heart rate gaps
3. **Monitor #8261** - Addresses insulin model gaps

### Medium-Term Actions

1. **Propose OpenAPI spec PR** - Close GAP-API-006
2. **Document v1 limitations** - GAP-API-001, 007 are "by design"
3. **Track client-side gaps separately** - GAP-API-010/011/012 need client PRs

### Long-Term Roadmap

1. **API v3 adoption campaign** - Close GAP-API-003, 010, 011
2. **Identity standardization** - Close GAP-API-002, 005
3. **WebSocket unification** - Close GAP-API-014

---

## References

- [Priority PR Deep-Dives](./priority-pr-deep-dives.md)
- [PR Adoption Sequencing Proposal](./pr-adoption-sequencing-proposal.md)
- [Nightscout API Gaps](../../traceability/nightscout-api-gaps.md)
- [API v3 Pagination Compliance](./api-v3-pagination-compliance.md)
