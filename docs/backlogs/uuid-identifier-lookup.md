# UUID Identifier Lookup Feature

**Status**: 📋 Ready for Implementation  
**Priority**: 🟠 P1  
**Feature Flag**: `TREATMENTS_ALLOW_UUID_LOOKUP`  
**Default**: `false` (maximum compatibility)

**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`

---

## Summary

Enable GET/DELETE operations to find treatments by `identifier` field when the `_id` parameter contains a UUID instead of an ObjectId. This complements the existing POST/PUT identifier extraction (REQ-SYNC-072) to provide complete CRUD support for UUID-based client sync patterns.

---

## Problem Statement

### Current State

POST/PUT operations (commit `e78a5bc6`) correctly:
1. Extract UUID from `_id` field → store in `identifier`
2. Generate proper ObjectId for `_id`
3. Deduplicate by `identifier`

But GET/DELETE operations fail:
```javascript
// lib/server/query.js:92-95
function updateIdQuery (query) {
  if (query._id && query._id.length) {
    query._id = ObjectID(query._id);  // ← Throws on UUID!
  }
}
```

### Impact

**Loop ObjectIdCache workflow breaks on cache loss:**
1. POST treatment with `syncIdentifier` → server returns `_id`
2. Cache `_id` ↔ `syncIdentifier` mapping (24hr TTL)
3. App restart or cache expiry → mapping lost
4. Loop only knows `syncIdentifier`, cannot DELETE/PUT its own treatments

---

## Implementation Design

### Detection Logic

```javascript
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const OBJECTID_RE = /^[0-9a-f]{24}$/i;
```

| Input | ObjectId Match | UUID Match | Action |
|-------|----------------|------------|--------|
| `507f1f77bcf86cd799439011` | ✅ | ❌ | Cast to ObjectId |
| `A3B4C5D6-E7F8-9012-3456-789ABCDEF012` | ❌ | ✅ | Rewrite to identifier query |
| `a3b4c5d6-e7f8-9012-3456-789abcdef012` | ❌ | ✅ | Rewrite to identifier query |
| `not-valid-id` | ❌ | ❌ | Leave unchanged (0 results) |
| `507f1f77bcf86cd79943901` (23 chars) | ❌ | ❌ | Leave unchanged (0 results) |

### Modified Function

```javascript
// lib/server/query.js

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const OBJECTID_RE = /^[0-9a-f]{24}$/i;

/**
 * Helper to set ObjectID type for `_id` queries.
 * When TREATMENTS_ALLOW_UUID_LOOKUP is enabled, UUID _id values
 * are converted to identifier queries for client sync compatibility.
 */
function updateIdQuery (query, opts) {
  if (!query._id || !query._id.length) {
    return;
  }

  if (OBJECTID_RE.test(query._id)) {
    // Standard 24-char hex ObjectId
    query._id = ObjectID(query._id);
  } else if (UUID_RE.test(query._id)) {
    if (opts && opts.allowUuidLookup) {
      // UUID detected + feature enabled: search by identifier instead
      query.identifier = query._id;
      delete query._id;
    }
    // If flag disabled: leave invalid _id, query returns 0 results (safe)
  }
  // Invalid formats: leave unchanged, MongoDB returns empty results
}
```

### Files to Modify

| File | Change |
|------|--------|
| `lib/server/env.js` | Parse `TREATMENTS_ALLOW_UUID_LOOKUP` env var |
| `lib/server/query.js` | Add UUID detection to `updateIdQuery()` |
| `lib/server/treatments.js` | Pass `allowUuidLookup` to queryOpts |
| `lib/server/entries.js` | Pass `allowUuidLookup` to queryOpts (same pattern) |
| `docs/example-template.env` | Document new env var |

---

## Feature Flag Design

### Environment Variable

```bash
# Enable UUID-based GET/DELETE lookup for treatments and entries
# When enabled, requests like DELETE /api/v1/treatments/{uuid} will
# search by 'identifier' field instead of failing on invalid ObjectId
TREATMENTS_ALLOW_UUID_LOOKUP=true
```

### Default Value: `false`

**Rationale for `false` default:**
1. **Maximum compatibility** — Existing deployments unchanged
2. **Opt-in for new behavior** — Operators consciously enable
3. **Safe failure mode** — UUID queries return empty results (not errors)
4. **No surprise data access** — Can't accidentally query by identifier

**When to set `true`:**
- Using Loop, Trio, or other AID apps with UUID sync patterns
- Want resilience against ObjectIdCache loss
- New deployments with modern AID ecosystem

---

## Test Matrix

### Flag OFF (`TREATMENTS_ALLOW_UUID_LOOKUP=false`)

| ID | Test Case | Input | Expected |
|----|-----------|-------|----------|
| UUID-OFF-001 | GET by valid ObjectId | `GET /treatments/507f1f77bcf86cd799439011` | Returns treatment |
| UUID-OFF-002 | DELETE by valid ObjectId | `DELETE /treatments/507f1f77bcf86cd799439011` | Deletes treatment |
| UUID-OFF-003 | GET by UUID | `GET /treatments/A3B4C5D6-E7F8-...` | Returns empty (no crash) |
| UUID-OFF-004 | DELETE by UUID | `DELETE /treatments/A3B4C5D6-E7F8-...` | Deletes nothing (no crash) |
| UUID-OFF-005 | GET by invalid ID | `GET /treatments/not-valid` | Returns empty (no crash) |
| UUID-OFF-006 | POST with UUID _id (existing) | POST creates with identifier | Still works (write path unchanged) |

### Flag ON (`TREATMENTS_ALLOW_UUID_LOOKUP=true`)

| ID | Test Case | Input | Expected |
|----|-----------|-------|----------|
| UUID-ON-001 | GET by valid ObjectId | `GET /treatments/507f1f77bcf86cd799439011` | Returns treatment |
| UUID-ON-002 | DELETE by valid ObjectId | `DELETE /treatments/507f1f77bcf86cd799439011` | Deletes treatment |
| UUID-ON-003 | GET by UUID (exists) | `GET /treatments/A3B4C5D6-E7F8-...` | Returns treatment by identifier |
| UUID-ON-004 | DELETE by UUID (exists) | `DELETE /treatments/A3B4C5D6-E7F8-...` | Deletes treatment by identifier |
| UUID-ON-005 | GET by UUID (not exists) | `GET /treatments/{new-uuid}` | Returns empty |
| UUID-ON-006 | DELETE by UUID (not exists) | `DELETE /treatments/{new-uuid}` | Deletes nothing |
| UUID-ON-007 | GET by invalid ID | `GET /treatments/not-valid` | Returns empty |
| UUID-ON-008 | PUT by UUID | `PUT /treatments` with UUID _id | Updates by identifier |
| UUID-ON-009 | Case insensitivity | `GET /treatments/a3b4c5d6-...` | Matches `A3B4C5D6-...` |
| UUID-ON-010 | Full CRUD cycle | POST→GET→PUT→DELETE by UUID | All succeed |

### Edge Cases (Both Flag States)

| ID | Test Case | Flag | Expected |
|----|-----------|------|----------|
| UUID-EDGE-001 | 23-char hex (invalid ObjectId) | OFF | Returns empty |
| UUID-EDGE-002 | 23-char hex (invalid ObjectId) | ON | Returns empty |
| UUID-EDGE-003 | UUID without hyphens | OFF | Returns empty |
| UUID-EDGE-004 | UUID without hyphens | ON | Returns empty (not valid UUID) |
| UUID-EDGE-005 | Empty _id | Both | No crash, enforces date filter |
| UUID-EDGE-006 | Wildcard `*` _id | Both | Existing wildcard behavior |
| UUID-EDGE-007 | Multiple treatments same identifier | ON | Returns all matches |

---

## Verification Commands

```bash
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447

# Test with flag OFF (default)
unset TREATMENTS_ALLOW_UUID_LOOKUP
npm test -- --grep "UUID"

# Test with flag ON
TREATMENTS_ALLOW_UUID_LOOKUP=true npm test -- --grep "UUID"

# Full test suite
npm test

# Manual verification
curl -X POST localhost:1337/api/v1/treatments \
  -H "Content-Type: application/json" \
  -H "api-secret: $(echo -n 'your-secret' | sha1sum | cut -d' ' -f1)" \
  -d '{"eventType":"Note","_id":"A3B4C5D6-E7F8-9012-3456-789ABCDEF012","notes":"test"}'

# With flag ON, this should find it:
TREATMENTS_ALLOW_UUID_LOOKUP=true curl \
  localhost:1337/api/v1/treatments/A3B4C5D6-E7F8-9012-3456-789ABCDEF012
```

---

## Work Items

| ID | Task | Priority | Status | Depends On |
|----|------|----------|--------|------------|
| uuid-feature-flag | Add `TREATMENTS_ALLOW_UUID_LOOKUP` to env.js | 🟠 P1 | 📋 Ready | - |
| uuid-query-impl | Modify `updateIdQuery()` in query.js | 🟠 P1 | 📋 Ready | uuid-feature-flag |
| uuid-treatments-opts | Pass flag to treatments.js queryOpts | 🟠 P1 | 📋 Ready | uuid-query-impl |
| uuid-entries-opts | Pass flag to entries.js queryOpts | 🟢 P2 | 📋 Ready | uuid-query-impl |
| uuid-test-flag-off | Tests UUID-OFF-001 through UUID-OFF-006 | 🟠 P1 | 📋 Ready | uuid-query-impl |
| uuid-test-flag-on | Tests UUID-ON-001 through UUID-ON-010 | 🟠 P1 | 📋 Ready | uuid-query-impl |
| uuid-test-edge | Tests UUID-EDGE-001 through UUID-EDGE-007 | 🟠 P1 | 📋 Ready | uuid-query-impl |
| uuid-doc-env | Document env var in example-template.env | 🟢 P2 | 📋 Ready | uuid-feature-flag |

---

## Rollout Plan

1. **Phase 1: Implementation** — Add code with flag defaulting to `false`
2. **Phase 2: Testing** — Full test matrix in CI
3. **Phase 3: Documentation** — Update README, CHANGELOG
4. **Phase 4: Opt-in** — Announce feature, users enable as needed
5. **Phase 5: Evaluate** — Consider changing default to `true` in future release

---

## Related

- [REQ-SYNC-072](../../traceability/requirements.md) — Server-controlled ID with transparent promotion
- [GAP-SYNC-045](../../traceability/sync-identity-gaps.md) — Entries UUID handling
- [Release 15.0.7 Docs](./release-15.0.7-documentation.md) — Parent release backlog
- Commit `e78a5bc6` — Original identifier extraction for POST/PUT

---

## Last Updated

2026-03-17
