# API Version UUID Handling Comparison

> **Purpose**: Document how v1 and v3 APIs handle client-supplied identifiers and what fixes are needed.
> **Created**: 2026-03-11
> **Related**: [GAP-SYNC-045](../../traceability/sync-identity-gaps.md#gap-sync-045-trio-entries-upload-uses-uuid-as-_id), [Client ID Deep Dive](../10-domain/client-id-handling-deep-dive.md)

---

## Executive Summary

| Aspect | API v1 | API v3 |
|--------|--------|--------|
| Identifier field | None (uses `_id`) | `identifier` (UUID v5 hash) |
| Client `_id` handling | ❌ Broken for UUID | ✅ Ignored (server computes) |
| Dedup strategy | `sysTime + type` | `identifier` > `date + type` fallback |
| Test coverage | ❌ No dedup tests | ✅ Has dedup tests |
| UUID _id issue | ❌ Affected | ✅ Not affected |

**Key Finding**: v3 API is **NOT affected** by the UUID `_id` issue because it:
1. Ignores client-supplied `_id`
2. Computes its own `identifier` from `device + date + eventType`
3. Has proper fallback dedup via `dedupFallbackFields`

---

## v1 API: `/api/v1/entries`

### Current Behavior

```javascript
// lib/server/entries.js:111
var query = (doc.sysTime && doc.type) ? { sysTime: doc.sysTime, type: doc.type } : doc;
```

| Input | Behavior | Problem |
|-------|----------|---------|
| `_id: ObjectId` | Ignored for upsert, preserved in doc | None |
| `_id: UUID string` | Ignored for upsert, causes GET/DELETE failures | ❌ Issue |
| No `_id` | Server assigns ObjectId | None |

### Files Requiring Changes

| File | Change Needed | Lines |
|------|---------------|-------|
| `lib/server/entries.js` | Add `normalizeEntryId()`, update upsert query | 99-120, 148-156 |
| `lib/api/entries/index.js` | Update `isId()` to handle UUID | 7, 388 |

### Test Coverage Status

| Behavior | Tested? | Test File |
|----------|---------|-----------|
| Basic CRUD | ✅ | `api.entries.test.js` |
| sysTime+type dedup | ❌ | None |
| UUID _id handling | ❌ | None |
| GET by UUID | ❌ | None |
| DELETE by UUID | ❌ | None |

---

## v3 API: `/api/v3/entries`

### Current Behavior

```javascript
// lib/api3/shared/operationTools.js
function calculateIdentifier (doc) {
  let key = doc.device + '_' + doc.date;
  if (doc.eventType) {
    key += '_' + doc.eventType;
  }
  return uuid.v5(key, uuidNamespace);  // Deterministic UUID v5
}

// lib/api3/generic/setup.js:45
dedupFallbackFields: ['date', 'type']  // Fallback for entries
```

| Input | Behavior | Problem |
|-------|----------|---------|
| `_id: anything` | Ignored, server computes `identifier` | None |
| `identifier: UUID` | Validated against computed, warns if mismatch | None |
| No `identifier` | Server computes from device+date+eventType | None |

### Why v3 is NOT Affected

1. **`_id` is ignored**: v3 never uses client `_id` for identity
2. **Deterministic identifier**: `uuid.v5(device + date + eventType)` 
3. **Fallback dedup**: `['date', 'type']` matches v1's `sysTime + type`
4. **Tests exist**: `api3.create.test.js` has dedup tests

### Files (No Changes Needed)

| File | Status |
|------|--------|
| `lib/api3/generic/create/operation.js` | ✅ Uses `identifyingFilter` correctly |
| `lib/api3/storage/mongoCollection/utils.js` | ✅ Has proper fallback logic |
| `lib/api3/generic/setup.js` | ✅ `dedupFallbackFields: ['date', 'type']` |

### Test Coverage Status

| Behavior | Tested? | Test File |
|----------|---------|-----------|
| Create with identifier | ✅ | `api3.create.test.js` |
| Dedup by identifier | ✅ | `api3.create.test.js:349` |
| Dedup by fallback fields | ✅ | `api3.create.test.js:382` |
| Rapid duplicate submissions | ✅ | `api3.aaps-patterns.test.js` |

---

## Which API Does Trio Use?

### Evidence from Trio Source

```swift
// Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:340-374
// POST to /api/v1/entries.json
func uploadGlucose(entries: [NightscoutGlucose]) async throws {
    let request = URLRequest(
        url: serverURL.appendingPathComponent("api/v1/entries.json"),
        ...
    )
}
```

**Finding**: Trio uses **v1 API** (`/api/v1/entries.json`), which IS affected.

### Recommendation

Trio could switch to v3 API, but this requires:
1. Client-side changes to use v3 endpoints
2. Computing `identifier` field client-side (or letting server compute)
3. No immediate need since v1 fix is simpler

---

## Work Tracks

### Track 1: v1 API Fix (REQUIRED)

**Backlog**: [trio-entries-upload-testing.md](./trio-entries-upload-testing.md)

| Work Item | Status | Iterations |
|-----------|--------|------------|
| Phase 0: Baseline dedup tests | ❌ | 1 |
| Phase 1: UUID test cases | ❌ | 3 |
| Phase 2: Implementation | ❌ | 3 |
| Phase 3: Index & validation | ❌ | 2 |
| Phase 4: Documentation | ❌ | 1 |
| **Total** | | **10** |

### Track 2: v3 API (NO CHANGES NEEDED)

**Status**: ✅ Already handles identifiers correctly

| Aspect | Evidence |
|--------|----------|
| Client `_id` ignored | `resolveIdentifier()` computes fresh |
| Dedup works | `identifyingFilter()` with fallback |
| Tests pass | `api3.create.test.js`, `api3.aaps-patterns.test.js` |

### Track 3: Future - Migrate Trio to v3 (OPTIONAL)

**Priority**: P3 (nice-to-have)

Benefits:
- Server-computed deterministic identifiers
- Better dedup guarantees
- Modern API features

Effort:
- Trio client changes required
- New test coverage for v3 entries from Trio

---

## Code References

### v1 API Critical Lines

```
lib/server/entries.js:111        # Upsert query (sysTime + type)
lib/server/entries.js:148-156    # getEntry() with ObjectId coercion
lib/api/entries/index.js:7       # ID_PATTERN (24-hex only)
lib/api/entries/index.js:388     # GET route using isId()
```

### v3 API Key Functions

```
lib/api3/shared/operationTools.js:90-105    # calculateIdentifier()
lib/api3/shared/operationTools.js:114-126   # resolveIdentifier()
lib/api3/storage/mongoCollection/utils.js   # identifyingFilter()
lib/api3/generic/setup.js:45                # entries dedupFallbackFields
```

### Test Files

```
tests/api.entries.test.js        # v1 tests (19 tests, no dedup)
tests/api3.create.test.js        # v3 create tests (has dedup)
tests/api3.aaps-patterns.test.js # v3 AAPS patterns (has dedup)
```

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-11 | v3 API requires no changes | `calculateIdentifier()` ignores client `_id` |
| 2026-03-11 | Focus on v1 API fix | Trio uses v1, v3 already works |
| 2026-03-11 | Add v1 baseline tests first | No existing dedup test coverage |
