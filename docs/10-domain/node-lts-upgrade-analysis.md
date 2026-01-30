# Node.js LTS Upgrade Analysis

> **Created**: 2026-01-30  
> **Purpose**: Map Nightscout ecosystem projects against Node.js LTS support windows  
> **Status**: Analysis complete

---

## Executive Summary

All Nightscout JavaScript projects are running on **end-of-life Node.js versions**. The ecosystem requires immediate attention:

| Risk Level | Finding |
|------------|---------|
| 🔴 Critical | cgm-remote-monitor on Node 16/14 (EOL 2023) |
| 🔴 Critical | share2nightscout-bridge supports Node 8-16 (oldest EOL 2019) |
| 🟡 Medium | nightscout-connect has no engines field (implicit compatibility unknown) |
| ⏰ Urgent | Node 20 EOL: **2026-04-30** (3 months away) |

**Recommendation**: Target **Node 22 LTS** (EOL 2027-04-30) for all projects.

---

## Current State

### Project Node.js Versions

| Project | engines.node | Latest Supported | EOL Date | Status |
|---------|--------------|------------------|----------|--------|
| cgm-remote-monitor | `^16.x \|\| ^14.x` | Node 16 | 2023-09-11 | 🔴 EOL 2+ years |
| share2nightscout-bridge | `16.x \|\| 14.x \|\| 12.x \|\| 10.x \|\| 8.x` | Node 16 | 2023-09-11 | 🔴 EOL 2+ years |
| nightscout-connect | (not specified) | Unknown | Unknown | 🟡 Needs testing |
| nightscout-librelink-up | (not specified) | Unknown | Unknown | 🟡 Needs testing |
| minimed-connect-to-nightscout | (not specified) | Unknown | Unknown | 🟡 Needs testing |
| tconnectsync | Python | N/A | N/A | ✅ Not affected |
| nocturne | .NET 9 | N/A | N/A | ✅ Not affected |

### Node.js LTS Schedule (2026-01-30)

| Version | Release | LTS Start | Maintenance End | Extended Support |
|---------|---------|-----------|-----------------|------------------|
| **Node 24** | 2025-10-15 | 2025-10-28 | 2028-04-30 | No |
| **Node 22** | 2024-04-24 | 2024-10-29 | 2027-04-30 | Yes |
| Node 20 | 2023-04-18 | 2023-10-24 | **2026-04-30** | Yes |
| Node 18 | 2022-04-19 | 2022-10-25 | 2025-04-30 | Yes |
| Node 16 | 2021-04-20 | 2021-10-26 | **2023-09-11** | Yes (expired) |
| Node 14 | 2020-04-21 | 2020-10-27 | **2023-04-30** | Yes (expired) |

**Target**: Node 22 LTS provides 15 months of remaining support.

---

## Breaking Changes Analysis

### Node 16 → Node 18

| Change | Impact | Affected Projects |
|--------|--------|-------------------|
| `--experimental-fetch` enabled by default | Low - native fetch available | All |
| OpenSSL 3.0 | Medium - some crypto changes | cgm-remote-monitor (JWT) |
| V8 10.1 | Low - performance improvements | All |
| `dns.lookup` behavior change | Low | All |

### Node 18 → Node 20

| Change | Impact | Affected Projects |
|--------|--------|-------------------|
| `url.parse()` deprecated | Medium - migrate to `URL()` | share2nightscout-bridge |
| Permission model (experimental) | None - opt-in | None |
| Test runner stable | None - feature addition | None |
| V8 11.3 | Low | All |

### Node 20 → Node 22

| Change | Impact | Affected Projects |
|--------|--------|-------------------|
| `require(esm)` support | Low - feature addition | All |
| WebSocket client | Low - feature addition | cgm-remote-monitor |
| `glob` and `fs.glob` | Low - feature addition | All |
| V8 12.4 | Low | All |

### Node 22 → Node 24

| Change | Impact | Affected Projects |
|--------|--------|-------------------|
| URLPattern API | Low - feature addition | All |
| AbortSignal improvements | Low | All |
| V8 13.x | Low | All |

**Summary**: No major breaking changes blocking upgrade. Primary risk is OpenSSL 3.0 crypto changes in Node 18.

---

## Dependency Blockers

### cgm-remote-monitor

| Dependency | Version | Node Compatibility | Blocker? |
|------------|---------|-------------------|----------|
| express | 4.17.1 | ✅ Node 22 compatible | No |
| socket.io | ~4.5.4 | ✅ Node 22 compatible | No |
| jsonwebtoken | ^9.0.0 | ✅ Node 22 compatible | No |
| request | ^2.88.2 | ⚠️ Deprecated 2020 | **Yes - replace** |
| webpack | ^5.74.0 | ✅ Node 22 compatible | No |
| axios | ^0.21.1 | ⚠️ Outdated (1.x current) | Upgrade recommended |

**Key Blocker**: `request` package deprecated in 2020. Must migrate to `axios` or `node-fetch`.

### share2nightscout-bridge

| Dependency | Version | Node Compatibility | Blocker? |
|------------|---------|-------------------|----------|
| request | ^2.88.0 | ⚠️ Deprecated 2020 | **Yes - replace** |
| mocha | ^9.2.0 | ✅ Node 22 compatible | No |

**Key Blocker**: `request` package. This is the **only runtime dependency**.

### nightscout-connect

| Dependency | Version | Node Compatibility | Blocker? |
|------------|---------|-------------------|----------|
| axios | ^1.3.4 | ✅ Node 22 compatible | No |
| xstate | ^4.37.1 | ✅ Node 22 compatible | No |
| yargs | ^17.7.1 | ✅ Node 22 compatible | No |
| tough-cookie | ^4.1.3 | ✅ Node 22 compatible | No |

**No blockers** - modern dependency stack.

---

## Upgrade Recommendations

### Strategy: Phased Upgrade to Node 22 LTS

#### Phase 1: nightscout-connect (Low Risk)

**Effort**: Low  
**Blocking**: Nothing

1. Add `engines` field: `"node": ">=18"`
2. Test on Node 22
3. Update CI matrix
4. Release

**Rationale**: Modern dependencies, no blockers.

#### Phase 2: share2nightscout-bridge → Deprecate

**Effort**: Low  
**Alternative**: nightscout-connect

1. Mark repository as **deprecated**
2. Add README banner pointing to nightscout-connect
3. Archive repository
4. **Do not upgrade** - redirect users instead

**Rationale**: 
- Single dependency (`request`) is deprecated
- nightscout-connect already supports Dexcom Share
- Maintaining two bridges is redundant

#### Phase 3: cgm-remote-monitor (High Value)

**Effort**: High  
**Blocking**: MongoDB 5.x PR (#8421), `request` migration

1. Merge PR#8421 (MongoDB 5.x support)
2. Replace `request` with `axios` (already in deps)
3. Update `axios` from 0.21.1 to 1.x
4. Update `engines` field to `"node": ">=20"`
5. Test full CI suite on Node 22
6. Phased rollout via Heroku/Docker tags

**Bundled Changes** (recommended to merge together):
- PR#8421 MongoDB 5.x
- Node 22 upgrade
- `request` → `axios` migration

#### Phase 4: minimed-connect-to-nightscout → Deprecate

**Effort**: Low  
**Alternative**: nightscout-connect

1. Mark repository as **deprecated**
2. nightscout-connect supports Minimed CareLink
3. Archive repository

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| OpenSSL 3.0 JWT breakage | Low | High | Test JWT flows specifically |
| `request` replacement regressions | Medium | High | Comprehensive API testing |
| MongoDB driver incompatibility | Low | High | Already addressed in PR#8421 |
| Socket.IO WebSocket changes | Low | Medium | Test real-time updates |
| Hosting provider Node version | Medium | High | Document minimum requirements |

---

## Timeline Recommendation

| Phase | Target | Deadline |
|-------|--------|----------|
| 1. nightscout-connect engines field | Node 22 | 2026-02-15 |
| 2. share2nightscout-bridge deprecation | Archive | 2026-02-28 |
| 3. cgm-remote-monitor upgrade | Node 22 | 2026-03-31 (before Node 20 EOL) |
| 4. minimed-connect deprecation | Archive | 2026-03-31 |

**Critical Deadline**: Node 20 EOL is **2026-04-30**. All upgrades should target Node 22 before this date.

---

## Gaps Identified

### GAP-NODE-001: EOL Node.js Versions

**Description**: All JavaScript Nightscout projects specify EOL Node.js versions in `engines` field.

**Affected Systems**: cgm-remote-monitor, share2nightscout-bridge

**Impact**: Security vulnerabilities, no upstream fixes, hosting provider deprecation warnings.

**Remediation**: Upgrade to Node 22 LTS per phased plan above.

### GAP-NODE-002: Deprecated `request` Package

**Description**: Both cgm-remote-monitor and share2nightscout-bridge depend on the deprecated `request` package.

**Affected Systems**: cgm-remote-monitor, share2nightscout-bridge

**Impact**: No security updates since 2020, blocks Node.js upgrades.

**Remediation**: 
- cgm-remote-monitor: Migrate to axios (already in dependencies)
- share2nightscout-bridge: Deprecate in favor of nightscout-connect

### GAP-NODE-003: Missing engines Field

**Description**: nightscout-connect lacks `engines` field, making Node.js compatibility unclear.

**Affected Systems**: nightscout-connect

**Impact**: Users may run on incompatible Node versions.

**Remediation**: Add `"engines": { "node": ">=18" }` to package.json.

---

## Requirements Generated

### REQ-NODE-001: Minimum Node.js LTS

**Statement**: All Nightscout JavaScript projects MUST specify a currently-supported Node.js LTS version in `engines.node`.

**Rationale**: EOL Node.js versions receive no security updates.

**Verification**: CI matrix includes minimum and latest LTS.

### REQ-NODE-002: No Deprecated Dependencies

**Statement**: Projects SHOULD NOT depend on packages deprecated more than 2 years.

**Rationale**: Deprecated packages receive no security updates and may break on newer Node.js.

**Verification**: `npm audit` in CI pipeline.

### REQ-NODE-003: Engines Field Required

**Statement**: All npm packages MUST include `engines.node` field.

**Rationale**: Enables npm to warn users of incompatible Node.js versions.

**Verification**: package.json lint check.

---

## Cross-References

- [cgm-remote-monitor PR Analysis](cgm-remote-monitor-pr-analysis.md) - PR#8421 MongoDB 5.x
- [Connector Bridge Deprecation Plan](../sdqctl-proposals/backlogs/nightscout-api.md#12) - Backlog item
- [nightscout-connect Design Review](nightscout-connect-design-review.md) - Architecture

---

## Appendix: Node.js Release Data Source

Data from https://endoflife.date/api/nodejs.json (fetched 2026-01-30).
