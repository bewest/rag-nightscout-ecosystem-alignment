# Nightscout API Backlog

> **Domain**: Nightscout collections, API v3, authentication  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-31

Covers: cgm-remote-monitor, Nocturne, entries, treatments, devicestatus, profile

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| *(All P1/P2 items complete - see Completed section)* | | | |

---

## Nightscout PR Triage & Adoption Research

Research stream focused on evaluating, sequencing, and proposing adoption of cgm-remote-monitor PRs.

### 10. [P1] PR adoption sequencing proposal ✅ COMPLETE
**Type:** Research | **Effort:** High  
**Repos:** cgm-remote-monitor  
**Deliverable:** `docs/10-domain/pr-adoption-sequencing-proposal.md`  
**Status:** ✅ COMPLETE 2026-01-30

**Key Findings:**
- 4-phase plan: Feb quick wins → Mar infra → Apr API+deprecations → Q2 cleanup
- Phase 1: #8419, #8083, #8261, #8281, #8377, #8378
- Phase 2: #8421 MongoDB 5x + Lodash/Moment removal = v15.1.0
- Phase 3: #7791 requires security audit before merge
- Deprecate share2nightscout-bridge and minimed-connect-to-nightscout

**Gaps Closed**: GAP-API-HR, GAP-INSULIN-001, GAP-DB-001, GAP-NODE-001/002, GAP-REMOTE-CMD

### 11. [P1] Node.js LTS impact analysis ✅ COMPLETE
**Type:** Research | **Effort:** Medium  
**Repos:** cgm-remote-monitor, share2nightscout-bridge, nightscout-connect, minimed-connect-to-nightscout  
**Focus:** Map project Node.js versions against LTS support windows  
**Deliverable:** `docs/10-domain/node-lts-upgrade-analysis.md`  
**Status:** ✅ COMPLETE 2026-01-30

**Key Findings:**
- All JS projects on EOL Node versions (16/14, EOL 2023)
- `request` package blocks upgrades (deprecated 2020)
- Target: Node 22 LTS (EOL 2027-04-30)
- Phased plan: nightscout-connect → deprecate bridges → cgm-remote-monitor

**Gaps Added:** GAP-NODE-001, GAP-NODE-002, GAP-NODE-003

### 12. [P2] Connector bridge deprecation plan ✅ COMPLETE
**Type:** Research | **Effort:** High  
**Repos:** share2nightscout-bridge, minimed-connect-to-nightscout, nightscout-connect  
**Deliverable:** `docs/10-domain/bridge-deprecation-plan.md`  
**Status:** ✅ COMPLETE 2026-01-30

**Key Findings:**
- Full feature parity between legacy bridges and nightscout-connect
- Dexcom Share: ✅ Full parity (US/OUS servers, auth, glucose, trends)
- Minimed CareLink: ✅ Full parity (EU/US, M2M auth, multi-patient)
- Migration guide included with env var mapping

**Timeline:**
- Feb 15: Deprecation banners in READMEs
- Mar 01: Final npm releases with warnings
- Mar 31: Repositories archived

**Requirements Added:** REQ-BRIDGE-001

### 13. [P2] High-value PR deep-dive
**Type:** Analysis | **Effort:** Medium  
**Repos:** cgm-remote-monitor  
**Focus:** Deep analysis of top 5 ecosystem-impacting PRs
**Status:** ✅ COMPLETE 2026-01-30

**Deliverable:** `docs/10-domain/priority-pr-deep-dives.md` (13.4KB)

**Key Findings:**
- Recommended merge order: #8419 → #8083 → #8261 → #8421 → #7791
- Quick wins: Push Tests, Heart Rate, Multi-Insulin (all low effort)
- Infrastructure: MongoDB 5x (very high effort, active development)
- Security-sensitive: Remote Commands (requires OTP enforcement)

**Gaps Addressed**: GAP-API-HR, GAP-INSULIN-001, GAP-DB-001, GAP-REMOTE-CMD

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
- ✅ Are all Loop-expected fields in `/api/v2/ddata`? → **YES** (all core collections)
- ⚠️ Is `lastProfileFromSwitch` populated correctly? → **NO** (missing - GAP-API-016)
- ✅ Does `devicestatus.loop` structure match exactly? → **YES** (typed model)
- ✅ Are AAPS `openaps` fields all present? → **YES** (typed model)

**Related Gap:** GAP-API-016  
**Deliverable:** `docs/10-domain/nocturne-ddata-analysis.md`
**Status:** ✅ COMPLETE 2026-01-30

**Key Findings:**
- High parity - all 8 core collections present (sgvs, treatments, profiles, devicestatus, etc.)
- One missing field: `lastProfileFromSwitch` (low impact, can compute from profileTreatments)
- Loop/OpenAPS devicestatus structures fully covered with typed models
- Nocturne enhanced: 8 pre-filtered treatment lists (sitechange, tempbasal, etc.)

### 9. [P3] Nocturne authentication mode compatibility
**Type:** Analysis | **Effort:** Low  
**Repos:** nocturne, cgm-remote-monitor  
**Focus:** Compare auth mechanisms (API_SECRET, JWT, readable token)  
**Questions:**
- ✅ Does Nocturne accept legacy `api_secret` header? → **YES** (SHA1 hash)
- ✅ Is JWT token format compatible with cgm-remote-monitor? → **YES** (HS256, same claims)
- ✅ Are readable/admin/devicestatus tokens interchangeable? → **YES** (same format)
- ✅ Any auth-related behavioral differences? → **Minor only** (no impact)

**Related Gap:** None - Full parity achieved  
**Deliverable:** `docs/10-domain/nocturne-auth-compatibility.md`
**Status:** ✅ COMPLETE 2026-01-30

**Key Findings:**
- Full authentication compatibility - all methods work identically
- API_SECRET: SHA1 hash validation, grants admin (*)
- JWT: HMAC-SHA256, Nocturne falls back to API_SECRET as signing key
- Access tokens: Same `{name}-{hash}` format, database lookup
- Default roles: 7 identical roles with same permissions

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Authentication mode compatibility | 2026-01-30 | Item #9; **FULL PARITY** - no gaps |
| V2 DData endpoint completeness | 2026-01-30 | Item #8; High parity, GAP-API-016 (one missing field) |
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

## Trio-dev Integration Analysis

Source: `externals/Trio-dev/` (LIVE-BACKLOG 2026-01-30)

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 20 | ~~**Trio NightscoutManager.swift analysis**~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE - `docs/10-domain/trio-comprehensive-analysis.md` (Section 2) |
| 21 | ~~**Trio NightscoutAPI.swift protocol mapping**~~ | ~~P2~~ | ~~Low~~ | ✅ COMPLETE - `docs/10-domain/trio-comprehensive-analysis.md` (Section 2.3) |
| 22 | ~~**Trio NightscoutTreatment.swift model comparison**~~ | ~~P2~~ | ~~Low~~ | ✅ COMPLETE - GAP-TRIO-SYNC-001 documents model differences |

---

## PR Coherence Review Queue

Systematic review of cgm-remote-monitor PRs for alignment with proposals and backlogs.

| # | Item | Priority | PR | Alignment Topic |
|---|------|----------|-----|-----------------|
| ~~14~~ | ~~Review PR #8422 (API v3 limit) for OpenAPI compliance~~ | ~~P2~~ | #8422 | ✅ Reviewed - safe to merge, robustness fix |
| ~~15~~ | ~~Review PR #8405 (timezone) against GAP-TZ-*~~ | ~~P2~~ | #8405 | ✅ Reviewed - GAP-TZ-001 addressed |
| 16 | Review PR #8419 (Loop push tests) for coverage | P3 | #8419 | Loop integration |
| ~~17~~ | ~~Review PR #8421 (MongoDB 5x) against infrastructure gaps~~ | ~~P2~~ | #8421 | ✅ Reviewed - WIP, includes docs restructure + test infra; monitor for completion |

### Review Protocol

1. **Fetch PR details** - Read PR description, changed files, comments
2. **Cross-reference gaps** - Search `traceability/*-gaps.md` for related GAP-* IDs
3. **Cross-reference requirements** - Search `traceability/*-requirements.md` for REQ-* IDs
4. **Check proposals** - Search `docs/sdqctl-proposals/*.md` for related topics
5. **Document findings** - Update gap status if PR addresses it
6. **Update PR analysis** - Add to `docs/analysis/ecosystem-pr-analysis-*.md`

---

## References

- [docs/10-domain/cgm-remote-monitor-*-deep-dive.md](../../10-domain/) (6 audit files)
- [specs/interoperability-spec-v1.md](../../../specs/interoperability-spec-v1.md)
- [specs/openapi/aid-*.yaml](../../../specs/openapi/) (entries, treatments, devicestatus, profile)
