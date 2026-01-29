# share2nightscout-bridge PR & Issue Analysis

> **Repository**: `nightscout/share2nightscout-bridge`  
> **Analyzed**: 2026-01-29  
> **Status**: 1 open PR, 13 open issues (some from 2015)

---

## Summary

| Category | Count | Critical |
|----------|-------|----------|
| Open PRs | 1 | ⚠️ Yes - error handling security fix |
| Open Issues | 13 | ⚠️ Node.js compatibility blocker |
| WIP Branches | 6 | axios migration nearly complete |
| Stale Issues | 8 | From 2015-2018, likely documentation requests |

### Key Finding

**Node.js 16+ EOL Blocker (#61)**: The `request` npm package is deprecated and the project requires Node 8-16. This blocks cgm-remote-monitor upgrade to Node 22+ (see PR #8357).

---

## Open Pull Requests

### PR #59: Fix error handling in fetch ⚠️ SECURITY

| Attribute | Value |
|-----------|-------|
| **Author** | @aredridel |
| **Created** | 2023-03-06 |
| **Status** | Mergeable, clean |
| **Changed Files** | 1 (index.js: +5/-1) |

**Problem**: Authorization failure response bodies were being passed as tokens to future requests.

**Fix** (index.js:211-217):
```javascript
// BEFORE
return request(req, then);

// AFTER  
return request(req, function (err, response, body) {
  if (err) return then(err);
  if (response.statusCode >= 300) 
    return then(new Error("request failed with status " + response.responseStatus + " " + body));
  return then(null, response, body);
});
```

**Recommendation**: **MERGE IMMEDIATELY** - This is a security-adjacent fix preventing auth token leakage on error.

---

## Critical Issues

### Issue #61: Node 16+ EOL ⚠️ BLOCKER

| Attribute | Value |
|-----------|-------|
| **Reporter** | @PieterGit (Nightscout collaborator) |
| **Created** | 2025-09-14 |
| **Blocking** | cgm-remote-monitor Node 22 upgrade (PR #8357) |

**Problem**: `package.json` engines field restricts to Node 8-16, all EOL:
```json
"engines": {
  "node": "16.x || 14.x || 12.x || 10.x || 8.x"
}
```

**Context**: The `request` npm package (sole dependency) is deprecated and has known vulnerabilities. The `connect` module in cgm-remote-monitor may supersede this bridge entirely.

**Options**:
1. Complete axios migration (WIP branch exists)
2. Deprecate in favor of cgm-remote-monitor `connect` module
3. Update engines field only (risky - request package behavior on Node 22 untested)

---

### Issue #60: Plus Sign (+) in Account Names

| Attribute | Value |
|-----------|-------|
| **Reporter** | @fsallstrom |
| **Created** | 2023-06-27 |
| **Status** | Unresolved |

**Problem**: Dexcom Share API rejects authentication for usernames containing `+` (common in phone number-based accounts like `+14087977776`).

**Analysis**: The `+` character may require URL encoding (`%2B`) in the JSON body, but since the body is sent as `application/json`, this shouldn't matter. The issue appears to be Dexcom-side validation.

**Workaround**: Users should contact Dexcom to change their account username to email format.

---

### Issue #52: Trend String Instead of Integer (EU Region)

| Attribute | Value |
|-----------|-------|
| **Reporter** | @cpitchford |
| **Created** | 2021-11-30 |
| **Status** | ✅ FIXED |

**Problem**: Dexcom EU servers changed API response from `Trend: 4` (integer) to `Trend: "Flat"` (string).

**Fix**: Already applied in v0.2.8 via `matchTrend()` function (index.js:90-106):
```javascript
function matchTrend(trend) {
  if (typeof(trend) !== "string") return trend;  // integer passthrough
  if (trend in DIRECTIONS) return DIRECTIONS[trend];  // string lookup
  // ... case-insensitive fallback
}
```

**Recommendation**: Close this issue as fixed.

---

## WIP Branches (Unmerged)

### 1. `wip/bewest/axios` - Axios Migration

| Attribute | Value |
|-----------|-------|
| **Commits Ahead** | 3 |
| **Status** | "work in progress, towards await/async" |
| **Changes** | index.js refactored, shrinkwrap reduced by 500+ lines |

**Key Changes**:
- Replaces deprecated `request` with `axios`
- Adds async/await patterns
- Updates npm shrinkwrap for modern dependencies

**Recommendation**: **Complete and merge** - This resolves #61 (Node compatibility).

---

### 2. `wip/reduce-bad-login-attempts`

| Attribute | Value |
|-----------|-------|
| **Commits** | Very old (v0.1.3 era) |
| **Changes** | Major refactor, removes tests, simplifies API |

**Analysis**: This is an old experimental branch with breaking changes. Not recommended for merge.

---

### 3. Other WIP Branches

| Branch | Purpose | Status |
|--------|---------|--------|
| `wip/battery-status` | Device battery reporting | Merged to #12 |
| `wip/bewest/multi-tenant-safety` | Tenant isolation | Unknown |
| `wip/generalize` | Plugin architecture | Unknown |
| `wip/bewest/upgrade-node` | Node 14/16 upgrade | ✅ Merged to master |

---

## Stale Issues (Pre-2020)

These issues are documentation/feature requests from 2015-2018 with no activity:

| # | Title | Created | Type |
|---|-------|---------|------|
| #31 | Missing CHO absorption rate | 2018-07-26 | Feature |
| #25 | Get more data from Share API | 2016-03-03 | Feature |
| #15 | Document the Share API | 2015-04-03 | Docs |
| #10 | Battery status | 2015-03-27 | Feature ✅ |
| #9 | Misc. Discussion (Technical) | 2015-03-27 | Meta |
| #2 | Understanding Azure billing | 2015-03-15 | Docs |
| #1 | 3 step tutorial | 2015-03-14 | Docs |

**Recommendation**: Close #10 (battery status was implemented), close #9/#2/#1 as stale meta/docs. Keep #15/#25/#31 open as future enhancement backlog.

---

## Ecosystem Impact Analysis

### Relationship to cgm-remote-monitor

The `share2nightscout-bridge` is a **standalone daemon** typically deployed:
1. As separate Heroku/Azure app
2. Integrated via cgm-remote-monitor `BRIDGE_*` environment variables

The cgm-remote-monitor `connect` module provides similar functionality but is:
- Built into the main Nightscout server
- Uses different authentication flow
- Maintained as part of core Nightscout

### Deprecation Consideration

Per Issue #61 discussion, the project may be deprecated in favor of the `connect` module. However:

| Approach | Pros | Cons |
|----------|------|------|
| Keep bridge | Simpler deployment, standalone | Separate maintenance burden |
| Use connect | Single deployment | More complex for simple use cases |
| Both | Flexibility | Maintenance overhead |

---

## Recommended Actions

### Immediate (P0)

1. **Merge PR #59** - Security fix for error handling
2. **Close Issue #52** - Already fixed in v0.2.8

### Short-term (P1)

3. **Complete axios migration** - Finish `wip/bewest/axios` branch to resolve #61
4. **Update engines field** - After axios merge, update to `"node": ">=18"`
5. **Release v0.3.0** - Major version bump for breaking dependency change

### Long-term (P2)

6. **Decide bridge vs connect** - Document official recommendation
7. **Close stale issues** - Clean up 2015-era meta issues
8. **Add CI/CD** - Currently only has wercker.yml (defunct service)

---

## Gap Implications

| Gap ID | Description | Status |
|--------|-------------|--------|
| GAP-BRIDGE-001 | Node.js 16+ EOL blocks upgrades | Open |
| GAP-BRIDGE-002 | `request` npm package deprecated | Open |
| GAP-BRIDGE-003 | No CI/CD (wercker defunct) | Open |

---

## Source References

| File | Lines | Purpose |
|------|-------|---------|
| `index.js` | 90-106 | `matchTrend()` - EU string trend fix |
| `index.js` | 211-214 | `fetch()` - PR #59 target |
| `package.json` | 18-20 | engines field - #61 target |
| `wip/bewest/axios` | - | Axios migration branch |
