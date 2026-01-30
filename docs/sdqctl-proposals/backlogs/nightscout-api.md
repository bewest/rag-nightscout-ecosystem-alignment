# Nightscout API Backlog

> **Domain**: Nightscout collections, API v3, authentication  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-30

Covers: cgm-remote-monitor, Nocturne, entries, treatments, devicestatus, profile

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

## Nocturne API Compatibility Research

Per OQ-010 extended research request (2026-01-30), focused analysis of Nocturne API behavior.

### 6. [P2] Nocturne V3 API behavioral parity testing
**Type:** Verification | **Effort:** High  
**Repos:** nocturne, cgm-remote-monitor  
**Focus:** Verify identical behavior for V3 endpoints between implementations  
**Questions:**
- ✅ Are all V3 query parameters supported (`count`, `skip`, `date$gte`, etc.)? → **YES** (full parity)
- ⚠️ Does ETag/srvModified behavior match exactly? → **NO** (different strategies)
- ✅ Are partial failure responses identical? → **YES** (same format)
- ✅ Edge cases: empty results, invalid parameters, auth errors? → **YES** (similar handling)

**Related Gap:** GAP-NOCTURNE-001, GAP-SYNC-041, GAP-API-010, GAP-API-011  
**Deliverable:** `conformance/scenarios/nocturne-v3-parity/` test cases
**Status:** ✅ COMPLETE 2026-01-30

**Key Findings:**
- Query parameter support: Full parity (9 operators, date field auto-parsing)
- **CRITICAL**: Missing `/api/v3/{collection}/history` endpoint (GAP-SYNC-041)
- ETag: cgm-remote-monitor uses timestamp-based weak ETag, Nocturne uses content-hash
- Nocturne enhanced: X-Total-Count, Link headers for pagination
- Soft delete: Not supported in Nocturne (links to GAP-SYNC-040)

### 7. [P2] Nocturne eventType normalization behavior
**Type:** Analysis | **Effort:** Medium  
**Repos:** nocturne, cgm-remote-monitor  
**Focus:** Compare how treatment eventTypes are normalized/stored  
**Questions:**
- ✅ Are eventTypes case-sensitive? → **YES** (both systems)
- ✅ Does Nocturne normalize whitespace/aliases? → **NO** (stored as-is)
- ✅ Are unknown eventTypes accepted or rejected? → **ACCEPTED** (both systems)
- ✅ Treatment.EventType enum vs string handling? → **String storage, enum advisory**

**Related Gap:** GAP-TREAT-001, GAP-TREAT-010, GAP-TREAT-011
**Deliverable:** `docs/10-domain/nocturne-eventtype-handling.md`
**Status:** ✅ COMPLETE 2026-01-30

**Key Findings:**
- High parity - both store as string, accept any value
- Case-sensitive matching in both systems
- Nocturne has 28 enum types vs ~25 documented in cgm-remote-monitor
- Minor gap: Immutability not enforced in Nocturne (GAP-TREAT-010)

### 8. [P2] Nocturne V2 DData endpoint completeness
**Type:** Verification | **Effort:** Medium  
**Repos:** nocturne, cgm-remote-monitor  
**Focus:** Verify DData combined response matches Loop/AAPS expectations  
**Questions:**
- Are all Loop-expected fields in `/api/v2/ddata`?
- Is `lastProfileFromSwitch` populated correctly?
- Does `devicestatus.loop` structure match exactly?
- Are AAPS `openaps` fields all present?

**Related Gap:** GAP-API-001  
**Deliverable:** `docs/10-domain/nocturne-ddata-analysis.md`

### 9. [P3] Nocturne authentication mode compatibility
**Type:** Analysis | **Effort:** Low  
**Repos:** nocturne, cgm-remote-monitor  
**Focus:** Compare auth mechanisms (API_SECRET, JWT, readable token)  
**Questions:**
- Does Nocturne accept legacy `api_secret` header?
- Is JWT token format compatible with cgm-remote-monitor?
- Are readable/admin/devicestatus tokens interchangeable?
- Any auth-related behavioral differences?

**Related Gap:** GAP-AUTH-001  
**Deliverable:** `docs/10-domain/nocturne-auth-compatibility.md`

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| eventType normalization behavior | 2026-01-30 | Item #7; High parity, GAP-TREAT-010/011 (minor) |
| V3 API behavioral parity testing | 2026-01-30 | Item #6; GAP-SYNC-041 (missing history), 40+ test scenarios |
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
