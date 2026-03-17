# UUID Identifier Handling Feature

**Status**: ✅ Core Complete (tests added `885f9133`)  
**Priority**: 🟠 P1  
**Feature Flag**: `UUID_HANDLING`  
**Default**: `false` (maximum compatibility)  
**Affects**: Treatments AND Entries (both collections)

**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`

---

## Summary

Provide unified UUID handling for **both treatments and entries** with a single feature flag controlling write (POST/PUT) and read (GET/DELETE) paths. When enabled, UUID `_id` values are normalized to the `identifier` field, and lookups by UUID search by `identifier`.

---

## Problem Statement

### Current State (Asymmetric, Both Collections)

**Treatments** (commit `e78a5bc6`) and **Entries** (commit `b8815505`) both added UUID handling for POST/PUT **without a feature flag**:

| Collection | Write Path (POST/PUT) | Read Path (GET/DELETE) |
|------------|----------------------|------------------------|
| Treatments | ✅ UUID→identifier (always on) | ❌ Fails on UUID |
| Entries | ✅ UUID→identifier (always on) | ❌ Fails on UUID |

Both use the same pattern:
1. Extract UUID from `_id` field → store in `identifier`
2. Generate proper ObjectId for `_id`
3. Deduplicate by `identifier` (treatments) or `sysTime+type` (entries)

But GET/DELETE operations still fail for BOTH:
```javascript
// lib/server/query.js:92-95 - shared by treatments AND entries
function updateIdQuery (query) {
  if (query._id && query._id.length) {
    query._id = ObjectID(query._id);  // ← Throws on UUID!
  }
}
```

### Issues with Asymmetric Design

1. **Inconsistent behavior** — Write works, read fails (both collections)
2. **No rollback option** — Write normalization always active
3. **Silent behavior change** — No operator control over new feature
4. **Affects all AID clients** — Loop, Trio, xDrip+ all use UUIDs

### Impact

**Loop ObjectIdCache workflow breaks on cache loss:**
1. POST treatment with `syncIdentifier` → server returns `_id`
2. Cache `_id` ↔ `syncIdentifier` mapping (24hr TTL)
3. App restart or cache expiry → mapping lost
4. Loop only knows `syncIdentifier`, cannot DELETE/PUT its own treatments

---

## Design Principles

### 1. ObjectID Users Unaffected

Clients posting valid 24-character hex ObjectIDs to `_id` see **no change in behavior**:

| Client sends | Detection | Result |
|--------------|-----------|--------|
| `{"_id": "507f1f77bcf86cd799439011"}` | Valid ObjectID | Works as before |
| `{"_id": "507f1f77bcf86cd799439011"}` GET/DELETE | Valid ObjectID | Works as before |
| No `_id` field | Server generates | Works as before |

The feature flag ONLY affects UUID-format `_id` values (36-char with hyphens).

### 2. Never Crash

All invalid inputs result in proper HTTP error responses or empty results — **never an uncaught exception**:

| Input Type | Write (POST/PUT) | Read (GET/DELETE) |
|------------|------------------|-------------------|
| Valid ObjectID | ✅ Works | ✅ Works |
| Valid UUID, flag ON | ✅ Normalizes | ✅ Searches identifier |
| Valid UUID, flag OFF | ⚠️ 400 with message | ⚠️ Returns empty |
| Invalid format | ⚠️ 400 or ignored | ⚠️ Returns empty |
| Empty/null | ✅ Server generates | ⚠️ Returns empty |

### 3. Clear Error Messages

When rejecting UUID `_id` (flag OFF), return actionable JSON:

```json
{
  "status": 400,
  "message": "UUID _id values require UUID_HANDLING=true. Either enable the flag or omit _id to let server generate ObjectId.",
  "received": "A3B4C5D6-E7F8-9012-3456-789ABCDEF012"
}
```

---

## Implementation Design

### Unified Feature Flag

**One flag controls all UUID behavior for BOTH collections:**

```bash
# Enable UUID handling for treatments AND entries
# When enabled:
#   - POST/PUT: UUID _id normalized to identifier, ObjectId generated
#   - GET/DELETE: UUID _id searches by identifier field
# When disabled:
#   - POST/PUT with UUID _id: Rejected with clear error
#   - GET/DELETE by UUID: Returns empty results (no crash)
UUID_HANDLING=true
```

### Behavior Matrix (Both Collections)

| `UUID_HANDLING` | POST with UUID _id | GET/DELETE by UUID |
|-----------------|--------------------|--------------------|
| `false` (default) | **Reject with error** | Returns empty (safe) |
| `true` | Normalize → identifier | Search by identifier |

**Note**: Same behavior applies to `/api/v1/treatments` AND `/api/v1/entries`.

### Detection Logic

```javascript
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const OBJECTID_RE = /^[0-9a-f]{24}$/i;
```

| Input | ObjectId Match | UUID Match | Action |
|-------|----------------|------------|--------|
| `507f1f77bcf86cd799439011` | ✅ | ❌ | Cast to ObjectId |
| `A3B4C5D6-E7F8-9012-3456-789ABCDEF012` | ❌ | ✅ | Handle per flag |
| `a3b4c5d6-e7f8-9012-3456-789abcdef012` | ❌ | ✅ | Handle per flag |
| `not-valid-id` | ❌ | ❌ | Leave unchanged (0 results) |

### Write Path (POST/PUT) Changes

```javascript
// lib/server/treatments.js - normalizeTreatmentId()

function normalizeTreatmentId (obj, env) {
  var isUuidId = typeof obj._id === 'string' && UUID_RE.test(obj._id);
  
  if (isUuidId) {
    if (!env.settings.uuidHandling) {
      // Flag OFF: Return error object (caller handles HTTP 400 response)
      return {
        error: true,
        status: 400,
        message: 'UUID _id values require UUID_HANDLING=true. ' +
                 'Either enable the flag or omit _id to let server generate ObjectId.',
        received: obj._id
      };
    }
    // Flag ON: Extract to identifier, let server generate ObjectId
    obj.identifier = obj._id;
    delete obj._id;
  }
  
  // ObjectId _id values pass through unchanged
  return null;  // No error
}
```

**Key principle**: Never crash. Invalid requests get proper HTTP 400 JSON responses.
```

### Read Path (GET/DELETE) Changes

```javascript
// lib/server/query.js - updateIdQuery()

function updateIdQuery (query, opts) {
  if (!query._id || !query._id.length) {
    return;
  }

  if (OBJECTID_RE.test(query._id)) {
    // Standard 24-char hex ObjectId
    query._id = ObjectID(query._id);
  } else if (UUID_RE.test(query._id)) {
    if (opts && opts.uuidHandling) {
      // Flag ON: Search by identifier instead
      query.identifier = query._id;
      delete query._id;
    }
    // Flag OFF: Leave invalid _id, query returns 0 results (safe)
  }
  // Invalid formats: leave unchanged, MongoDB returns empty results
}
```

### Files to Modify

| File | Change |
|------|--------|
| `lib/server/env.js` | Parse `UUID_HANDLING` env var |
| `lib/server/query.js` | Add UUID detection to `updateIdQuery()` |
| `lib/server/treatments.js` | Guard `normalizeTreatmentId()` with flag check |
| `lib/server/entries.js` | Same pattern for entries (GAP-SYNC-045) |
| `docs/example-template.env` | Document new env var |

---

## Feature Flag Design

### Environment Variable

```bash
# Enable UUID handling for treatments and entries
# Controls BOTH write (POST/PUT) and read (GET/DELETE) paths
#
# When TRUE:
#   - POST/PUT: UUID _id extracted to 'identifier', server generates ObjectId
#   - GET/DELETE: UUID _id searches by 'identifier' field
#   - Enables Loop, Trio, AAPS UUID sync patterns
#
# When FALSE (default):
#   - POST/PUT with UUID _id: Returns 400 error with instructions
#   - GET/DELETE by UUID: Returns empty results (no error)
#   - Original Nightscout behavior preserved
#
UUID_HANDLING=true
```

### Default Value: `false`

**Rationale for `false` default:**
1. **Maximum compatibility** — Existing deployments unchanged
2. **Explicit opt-in** — Operators consciously enable new behavior
3. **Clear error on misconfiguration** — POST with UUID _id tells you what to do
4. **Safe failure mode** — GET/DELETE returns empty, doesn't crash

**When to set `true`:**
- Using Loop, Trio, or other AID apps with UUID sync patterns
- Want resilience against ObjectIdCache loss
- New deployments with modern AID ecosystem
- Migrating from systems that used UUID _id values

---

## Test Matrix

### Flag OFF (`UUID_HANDLING=false`)

| ID | Test Case | Input | Expected |
|----|-----------|-------|----------|
| UUID-OFF-001 | GET by valid ObjectId | `GET /treatments/507f1f77bcf86cd799439011` | Returns treatment |
| UUID-OFF-002 | DELETE by valid ObjectId | `DELETE /treatments/507f1f77bcf86cd799439011` | Deletes treatment |
| UUID-OFF-003 | GET by UUID | `GET /treatments/A3B4C5D6-E7F8-...` | Returns empty (no crash) |
| UUID-OFF-004 | DELETE by UUID | `DELETE /treatments/A3B4C5D6-E7F8-...` | Deletes nothing (no crash) |
| UUID-OFF-005 | GET by invalid ID | `GET /treatments/not-valid` | Returns empty (no crash) |
| UUID-OFF-006 | POST with UUID _id | POST `{"_id": "A3B4C5D6-..."}` | **400 error** with message to enable flag |

### Flag ON (`UUID_HANDLING=true`)

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

### Entries-Specific Tests

| ID | Test Case | Flag | Expected |
|----|-----------|------|----------|
| ENTRY-UUID-001 | GET entry by UUID | OFF | Returns empty (no crash) |
| ENTRY-UUID-002 | DELETE entry by UUID | OFF | Deletes nothing (no crash) |
| ENTRY-UUID-003 | GET entry by UUID (exists) | ON | Returns entry by identifier |
| ENTRY-UUID-004 | DELETE entry by UUID (exists) | ON | Deletes entry by identifier |
| ENTRY-UUID-005 | POST entry with UUID _id | ON | Normalizes to identifier |
| ENTRY-UUID-006 | POST entry with UUID _id | OFF | **Reject with error** |

**Note**: Entries use `sysTime+type` as primary dedup key, but `identifier` is still tracked for client sync purposes.

---

## Verification Commands

```bash
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447

# Test with flag OFF (default)
unset UUID_HANDLING
npm test -- --grep "UUID"

# Test with flag ON
UUID_HANDLING=true npm test -- --grep "UUID"

# Full test suite
npm test

# Manual verification
curl -X POST localhost:1337/api/v1/treatments \
  -H "Content-Type: application/json" \
  -H "api-secret: $(echo -n 'your-secret' | sha1sum | cut -d' ' -f1)" \
  -d '{"eventType":"Note","_id":"A3B4C5D6-E7F8-9012-3456-789ABCDEF012","notes":"test"}'

# With flag ON, this should find it:
UUID_HANDLING=true curl \
  localhost:1337/api/v1/treatments/A3B4C5D6-E7F8-9012-3456-789ABCDEF012
```

---

## Work Items

| ID | Task | Priority | Status | Depends On |
|----|------|----------|--------|------------|
| uuid-feature-flag | Add `UUID_HANDLING` to env.js | 🟠 P1 | ✅ Complete (`bf6cfb77`) | - |
| uuid-guard-write-treatments | Guard `normalizeTreatmentId()` with flag check | 🟠 P1 | 📋 Deferred | uuid-feature-flag |
| uuid-guard-write-entries | Guard `normalizeEntryId()` with flag check | 🟠 P1 | 📋 Deferred | uuid-feature-flag |
| uuid-query-impl | Modify `updateIdQuery()` in query.js | 🟠 P1 | ✅ Complete (`bf6cfb77`) | uuid-feature-flag |
| uuid-treatments-opts | Pass flag to treatments.js queryOpts | 🟠 P1 | ✅ Complete (`bf6cfb77`) | uuid-query-impl |
| uuid-entries-opts | Pass flag to entries.js queryOpts | 🟠 P1 | ✅ Complete (`bf6cfb77`) | uuid-query-impl |
| uuid-test-flag-off | Tests UUID-OFF-001, UUID-OFF-002 | 🟠 P1 | ✅ Complete (`885f9133`) | uuid-query-impl |
| uuid-test-flag-on | Tests UUID-ON-001 through UUID-ON-004 | 🟠 P1 | ✅ Complete (`885f9133`) | uuid-query-impl |
| uuid-test-edge | Tests UUID-EDGE-001 through UUID-EDGE-007 | 🟠 P1 | 📋 Ready | uuid-query-impl |
| uuid-test-entries | Tests ENTRY-UUID-001 through ENTRY-UUID-006 | 🟠 P1 | 📋 Ready | uuid-entries-opts |
| uuid-doc-env | Document env var in example-template.env | 🟢 P2 | ✅ Complete (`d987e55c`) | uuid-feature-flag |

**Note**: Write path guards (`uuid-guard-write-*`) deferred as current behavior (always normalize) works and adding rejection would be a breaking change.

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
