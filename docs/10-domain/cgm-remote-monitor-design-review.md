# cgm-remote-monitor Design Review

> **Source**: 6-layer audit (3,139 lines across 7 documents)  
> **Purpose**: Synthesized refactoring recommendations for cgm-remote-monitor  
> **Last Updated**: 2026-01-29

## Executive Summary

This design review consolidates findings from the comprehensive 6-layer audit of cgm-remote-monitor (Nightscout server) and provides prioritized refactoring recommendations. The audit identified **18 gaps** across database, API, authentication, sync, plugin, and frontend layers.

### Audit Coverage

| Layer | Document | Lines | Gaps |
|-------|----------|-------|------|
| Database | `cgm-remote-monitor-database-deep-dive.md` | 455 | 3 |
| API | `cgm-remote-monitor-api-deep-dive.md` | 397 | 3 |
| Authentication | `cgm-remote-monitor-auth-deep-dive.md` | 475 | 3 |
| Sync/Upload | `cgm-remote-monitor-sync-deep-dive.md` | 520 | 3 |
| Plugins | `cgm-remote-monitor-plugin-deep-dive.md` | 436 | 3 |
| Frontend | `cgm-remote-monitor-frontend-deep-dive.md` | 468 | 3 |
| **Total** | | **2,751** | **18** |

---

## Gap Summary

### Critical (Security/Data Integrity)

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-AUTH-003 | API_SECRET grants full admin access | Security bypass |
| GAP-AUTH-004 | No token revocation mechanism | Compromised tokens remain valid |
| GAP-SYNC-008 | No cross-client sync conflict resolution | Data loss risk |
| GAP-DB-001 | Entries batch ordering not guaranteed | Loop upload corruption |

### High (Interoperability)

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-API-001 | No OpenAPI specification | Blocks SDK generation |
| GAP-API-003 | Inconsistent timestamp fields | Client confusion |
| GAP-PLUGIN-002 | Prediction curve format mismatch | Loop vs AAPS divergence |
| GAP-SYNC-009 | V1 API lacks identifier field | Deduplication failures |

### Medium (Technical Debt)

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-DB-002 | MongoDB driver deprecated patterns | Warning spam |
| GAP-DB-003 | No bulk write optimization | Performance |
| GAP-API-002 | v1/v3 response format divergence | Documentation gap |
| GAP-PLUGIN-001 | No AAPS-specific plugin | Missing fields |
| GAP-PLUGIN-003 | Enacted confirmation inconsistency | Typo tolerance |
| GAP-SYNC-010 | No sync status feedback | Client blind |

### Low (UX/Accessibility)

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-UI-001 | No component framework | Maintenance burden |
| GAP-UI-002 | Chart accessibility | Accessibility compliance |
| GAP-UI-003 | No offline support | Disconnected users |
| GAP-AUTH-005 | JWT secret in node_modules | Lost on reinstall |

---

## Refactoring Recommendations

### Phase 1: Quick Wins (Low Effort, High Value)

| # | Recommendation | Gap | Effort | Files |
|---|----------------|-----|--------|-------|
| 1 | **Upgrade MongoDB driver patterns** | GAP-DB-002 | Low | `lib/storage/mongo-storage.js` |
| 2 | **Move JWT secret to persistent path** | GAP-AUTH-005 | Low | `lib/api3/security.js` |
| 3 | **Fix enacted typo handling** | GAP-PLUGIN-003 | Low | `lib/plugins/openaps.js` |
| 4 | **Add sync status response** | GAP-SYNC-010 | Low | `lib/api3/generic/create.js` |

#### Implementation: MongoDB Driver Patterns

```javascript
// Before (deprecated)
const ObjectID = require('mongodb').ObjectID;
new ObjectID(id);

// After (modern)
const { ObjectId } = require('mongodb');
ObjectId.createFromHexString(id);
```

#### Implementation: JWT Secret Location

```javascript
// Before: lib/api3/security.js:47
const jwtPath = path.join(__dirname, '../../node_modules/.cache/nightscout-jwt');

// After: Use environment or data directory
const jwtPath = process.env.JWT_SECRET_PATH || 
  path.join(process.env.MONGO_DATA_DIR || '/var/lib/nightscout', '.jwt-secret');
```

---

### Phase 2: Security Hardening (Medium Effort, Critical)

| # | Recommendation | Gap | Effort | Files |
|---|----------------|-----|--------|-------|
| 5 | **Deprecate API_SECRET for writes** | GAP-AUTH-003 | Medium | `lib/api3/security.js`, `lib/server/bootevent.js` |
| 6 | **Add token revocation list** | GAP-AUTH-004 | Medium | New: `lib/api3/tokenBlacklist.js` |
| 7 | **Enforce ordered batch writes** | GAP-DB-001 | Medium | `lib/api3/generic/create.js` |

#### Implementation: Ordered Batch Writes

```javascript
// Before: lib/api3/generic/create.js (unordered)
const results = await Promise.all(docs.map(doc => col.insertOne(doc)));

// After: Ordered bulk write
const bulkOps = docs.map(doc => ({ insertOne: { document: doc } }));
const result = await col.bulkWrite(bulkOps, { ordered: true });
```

#### Implementation: Token Revocation

```javascript
// New: lib/api3/tokenBlacklist.js
const revokedTokens = new Set();
const REVOCATION_EXPIRY = 24 * 60 * 60 * 1000; // 24 hours

module.exports = {
  revoke(tokenHash) {
    revokedTokens.add(tokenHash);
    setTimeout(() => revokedTokens.delete(tokenHash), REVOCATION_EXPIRY);
  },
  isRevoked(tokenHash) {
    return revokedTokens.has(tokenHash);
  }
};
```

---

### Phase 3: API Standardization (Medium Effort, High Value)

| # | Recommendation | Gap | Effort | Files |
|---|----------------|-----|--------|-------|
| 8 | **Generate OpenAPI 3.0 spec** | GAP-API-001 | Medium | New: `swagger/openapi-v3.yaml` |
| 9 | **Document timestamp conventions** | GAP-API-003 | Low | `docs/api.md` |
| 10 | **Normalize prediction formats** | GAP-PLUGIN-002 | Medium | `lib/plugins/openaps.js`, `lib/plugins/loop.js` |
| 11 | **Backfill identifier field** | GAP-SYNC-009 | Medium | Migration script |

#### OpenAPI Generation Strategy

1. Use existing route definitions in `lib/api3/` to generate base spec
2. Add `x-nightscout-*` extensions for AID-specific semantics
3. Include controller support matrix (`x-aid-controllers`)
4. Generate TypeScript client from spec

#### Prediction Format Normalization

```javascript
// Unified prediction envelope in deviceStatus
{
  "predicted": {
    "values": [100, 105, 110, ...],      // Primary curve (mg/dL)
    "timestamps": [1706000000000, ...],  // Epoch ms
    "curves": {                          // Optional decomposition
      "iob": [...],
      "cob": [...],
      "uam": [...],
      "zt": [...]
    }
  }
}
```

---

### Phase 4: Sync Architecture (High Effort, Critical)

| # | Recommendation | Gap | Effort | Files |
|---|----------------|-----|--------|-------|
| 12 | **Add conflict resolution** | GAP-SYNC-008 | High | `lib/api3/generic/update.js` |
| 13 | **Implement version vectors** | GAP-SYNC-008 | High | Schema change |
| 14 | **Add AAPS plugin** | GAP-PLUGIN-001 | Medium | New: `lib/plugins/aaps.js` |

#### Conflict Resolution Strategy

```javascript
// Add version field to all documents
{
  "_id": "...",
  "srvModified": 1706000000000,
  "version": 3,                    // Incrementing version
  "sourceId": "loop-abc123",       // Originating client
  "data": { ... }
}

// On update: check version, reject if stale
if (existingDoc.version > incomingDoc.version) {
  return { status: 409, conflict: existingDoc };
}
```

---

### Phase 5: Frontend Modernization (High Effort, Long-term)

| # | Recommendation | Gap | Effort | Files |
|---|----------------|-----|--------|-------|
| 15 | **Add Playwright E2E tests** | GAP-UI-001 | Medium | `tests/e2e/` |
| 16 | **Progressive component migration** | GAP-UI-001 | High | Incremental |
| 17 | **Chart accessibility** | GAP-UI-002 | Medium | `lib/client/chart.js` |
| 18 | **IndexedDB offline cache** | GAP-UI-003 | High | `lib/client/serviceworker.js` |

#### Playwright Adoption

See: `docs/sdqctl-proposals/playwright-adoption-proposal.md` (complete proposal)

Priority test scenarios:
1. Main dashboard glucose display
2. Careportal treatment entry
3. Report generation
4. Settings panel
5. Socket.IO real-time updates

---

## Implementation Priority Matrix

```
                    High Value
                        │
    ┌───────────────────┼───────────────────┐
    │ Phase 2           │ Phase 3           │
    │ Security          │ API Standardization│
    │ (Weeks 2-4)       │ (Weeks 5-8)       │
    │                   │                   │
Low ├───────────────────┼───────────────────┤ High
Effort                  │                   Effort
    │ Phase 1           │ Phase 4-5         │
    │ Quick Wins        │ Sync + Frontend   │
    │ (Week 1)          │ (Months 2-4)      │
    │                   │                   │
    └───────────────────┼───────────────────┘
                        │
                    Low Value
```

---

## Nocturne Alignment

Nocturne (the .NET rewrite) addresses many of these gaps natively:

| Gap | cgm-remote-monitor | Nocturne |
|-----|-------------------|----------|
| GAP-DB-001 | Manual ordering | PostgreSQL transactions |
| GAP-AUTH-003 | API_SECRET bypass | Subject-based auth only |
| GAP-AUTH-004 | No revocation | Redis token blacklist |
| GAP-API-001 | No OpenAPI | Generated from controllers |
| GAP-SYNC-008 | Last-write-wins | EF Core concurrency tokens |
| GAP-PLUGIN-002 | Format mismatch | Unified model layer |

### Collaboration Opportunities

1. **Shared OpenAPI spec**: cgm-remote-monitor generates spec, Nocturne validates compatibility
2. **Shared test vectors**: Conformance suite validates both implementations
3. **Migration path**: Document data export format for NS → Nocturne migration

---

## Related PRs

From `cgm-remote-monitor-pr-analysis.md`:

| PR | Gap Addressed | Status |
|----|---------------|--------|
| #8421 | GAP-DB-001 (MongoDB 5.x batch ordering) | In progress |
| #8405 | GAP-TZ-001 (Timezone handling) | Pending |
| #8261 | GAP-INSULIN-001 (Multi-insulin) | Pending |
| #7791 | GAP-REMOTE-CMD (Remote commands) | Pending |

---

## Appendix: File References

### Core Files to Modify

| Phase | File | Purpose |
|-------|------|---------|
| 1 | `lib/storage/mongo-storage.js` | MongoDB patterns |
| 1 | `lib/api3/security.js` | JWT secret path |
| 2 | `lib/api3/generic/create.js` | Ordered writes |
| 3 | `lib/plugins/openaps.js` | Prediction format |
| 3 | `lib/plugins/loop.js` | Prediction format |
| 4 | `lib/api3/generic/update.js` | Conflict resolution |

### New Files to Create

| Phase | File | Purpose |
|-------|------|---------|
| 2 | `lib/api3/tokenBlacklist.js` | Token revocation |
| 3 | `swagger/openapi-v3.yaml` | API specification |
| 4 | `lib/plugins/aaps.js` | AAPS-specific plugin |
| 5 | `tests/e2e/dashboard.spec.js` | Playwright tests |

---

## References

- Database audit: `docs/10-domain/cgm-remote-monitor-database-deep-dive.md`
- API audit: `docs/10-domain/cgm-remote-monitor-api-deep-dive.md`
- Auth audit: `docs/10-domain/cgm-remote-monitor-auth-deep-dive.md`
- Sync audit: `docs/10-domain/cgm-remote-monitor-sync-deep-dive.md`
- Plugin audit: `docs/10-domain/cgm-remote-monitor-plugin-deep-dive.md`
- Frontend audit: `docs/10-domain/cgm-remote-monitor-frontend-deep-dive.md`
- PR analysis: `docs/10-domain/cgm-remote-monitor-pr-analysis.md`
- Playwright proposal: `docs/sdqctl-proposals/playwright-adoption-proposal.md`
- Nocturne analysis: `docs/sdqctl-proposals/nocturne-modernization-analysis.md`
