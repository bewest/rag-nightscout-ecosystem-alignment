# PR #8444 / 15.0.7 — Affected Issues & Bugs

**Date:** 2026-03-19  
**PR:** [nightscout/cgm-remote-monitor#8444](https://github.com/nightscout/cgm-remote-monitor/pull/8444) (dev → master, 15.0.7)  
**Worktree:** `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`  
**Branch analysed:** `wip/test-improvements`  
**Purpose:** Map 15.0.7 fixes to known GitHub issues, assess test coverage, identify gaps.

---

## 1. Issues Directly Fixed

### 1.1 [#8450](https://github.com/nightscout/cgm-remote-monitor/issues/8450) — Loop Temporary Override UUID sync breakage ⭐ CRITICAL

**Status:** ✅ Fixed for new data — `normalizeTreatmentId()` in `lib/server/treatments.js`

**Root cause:** v1 API accepted UUID strings as `_id` on POST but coerced them
to ObjectId on UPDATE/DELETE, causing Loop override sync to stall permanently
after an indefinite override.

**Fix (REQ-SYNC-072):** `normalizeTreatmentId()` promotes non-ObjectId `_id`
values (UUIDs) to the `identifier` field; server generates a valid ObjectId for
`_id`. Subsequent updates and deletes use `identifier` for lookup.

**Query-layer support:** `lib/server/query.js` `normalizeIdValue()` detects
UUID in `_id` query parameters and rewrites `{_id: UUID}` →
`{identifier: UUID}`, so `DELETE /api/v1/treatments/<uuid>` and
`PUT /api/v1/treatments/` both resolve correctly when `identifier` is present.

**Test coverage (new overrides):**

| Test | File | Verifies |
|------|------|----------|
| TEST-GAP-001 | `tests/gap-treat-012.test.js:61` | UUID `_id` POST → promoted to `identifier`, server ObjectId |
| TEST-GAP-001 (indefinite) | `tests/gap-treat-012.test.js:98` | Indefinite override UUID preserved |
| TEST-GAP-001 (remote) | `tests/gap-treat-012.test.js:120` | Remote command override UUID preserved |
| TEST-GAP-002 | `tests/gap-treat-012.test.js:143` | DELETE by server-assigned ObjectId after UUID promotion |
| TEST-GAP-002 (find) | `tests/gap-treat-012.test.js:176` | Query by `identifier` finds the override |
| TEST-GAP-003 | `tests/gap-treat-012.test.js:202` | PUT with UUID `_id` updates existing override |
| TEST-GAP-004 | `tests/gap-treat-012.test.js:244` | Re-POST same UUID upserts (no duplicate) |
| Batch | `tests/gap-treat-012.test.js:290` | Batch of UUID overrides all get `identifier` |
| Mixed batch | `tests/gap-treat-012.test.js:319` | UUID + non-UUID in same batch |
| Uppercase | `tests/gap-treat-012.test.js:348` | Uppercase UUID handled |
| Lowercase | `tests/gap-treat-012.test.js:373` | Lowercase UUID handled |
| ObjectId passthrough | `tests/gap-treat-012.test.js:398` | Valid 24-hex ObjectId NOT promoted |
| UUID_HANDLING flag | `tests/uuid-handling.test.js` | Feature flag on/off (8 tests) |

**⚠️ Gap — legacy data not tested:**
Overrides created *before* the fix have UUID directly in `_id` with **no
`identifier` field**. The query rewrite (`_id: UUID` → `identifier: UUID`) will
match zero documents for these records. DELETE and PUT on legacy overrides will
silently fail. **No test currently covers this scenario.** See §4.

### 1.2 [#8446](https://github.com/nightscout/cgm-remote-monitor/issues/8446) — MongoDB 8.x compatibility (7 fixes)

**Status:** ✅ Fixed

| Fix | Error | File | Test |
|-----|-------|------|------|
| 1. `toSafeInt()` | `MongoInvalidArgumentError: limit requires an integer` | `lib/api3/storage/mongoCollection/find.js:10` | API3 query tests |
| 2. `safeObjectID()` | `TypeError: ObjectID is not a constructor` | `lib/server/websocket.js:15` | WebSocket tests |
| 3. `$set` wrapper | `MongoInvalidArgumentError: Update document requires atomic operators` | `lib/server/treatments.js` | Treatment upsert tests |
| 4. Stale WS broadcast | Clients see pre-PATCH data | `lib/api3/generic/patch/operation.js` | `tests/api3.patch.operation.test.js:91` |
| 5. `endmills` on PATCH | Temp basal missing from chart | `lib/api3/generic/patch/operation.js` | `tests/api3.patch.test.js:239` |
| 6a. `idMergePreferNew` | WS updates invisible in cache | `lib/data/ddata.js:78` | `tests/ddata.test.js:58` |
| 6b. `endmills` data-load | Missing `endmills` on all paths | `lib/data/ddata.js:53` | `tests/ddata.test.js:44` |
| 7. `endmills` on replace | Missing `endmills` on PUT | `lib/api3/generic/update/replace.js` | `tests/api3.update.test.js:300` |

Fixes 1–3 are **MongoDB 8.x blockers**. Fixes 4–7 benefit all MongoDB versions.

### 1.3 [#6923](https://github.com/nightscout/cgm-remote-monitor/issues/6923) — Unable to edit/save Temporary Override treatment

**Status:** ❌ **Not fixed for existing data** (see §4 for analysis)

**Issue:** Clicking edit (pencil) or delete (✕) on a Temporary Override in
Reports → Treatments yields HTTP 500 because the UUID `_id` is coerced to
ObjectId.

**What the fix does:** For *new* overrides, `normalizeTreatmentId()` moves UUID
to `identifier` and assigns a valid ObjectId. The Reports UI then operates on
the ObjectId, so edit/delete succeed.

**What remains broken:** For overrides **already in the database** with a UUID
in `_id` and no `identifier` field:

- `DELETE /api/v1/treatments/69F15FD2-...` → `query_for()` rewrites to
  `{identifier: "69F15FD2-..."}` → matches 0 documents → silent no-op (no 500,
  but no delete either).
- `PUT /api/v1/treatments/` with UUID `_id` → `normalizeTreatmentId()` promotes
  UUID to `identifier`, then `upsertQueryFor()` matches by `identifier` →
  matches 0 documents → inserts a *new* document instead of updating.

**Net effect:** The 500 error is gone (the ObjectId coercion crash is fixed),
but the underlying operation silently fails on legacy data. The user sees no
error but the override persists.

**Test gap:** No test covers the legacy-data scenario. See §4.

---

## 2. Issues Partially Addressed

### 2.1 [#8129](https://github.com/nightscout/cgm-remote-monitor/issues/8129) — OpenAPS pill behavior is unpredictable

**Status:** 🟡 Partially mitigated

**What's fixed:** Fix 4 (stale WS broadcast) and Fix 6a (`idMergePreferNew`
identifier matching) eliminate two server-side causes of stale pill data.

**What remains:** Client-side timing of devicestatus uploads relative to BG
arrival (reported as "disappears when new BG arrives") is not addressed.

### 2.2 [#8144](https://github.com/nightscout/cgm-remote-monitor/issues/8144) — Admin tool to clean Mongo profile database

**Status:** 🟡 Indirectly helped — `toSafeInt()` prevents pagination crashes on
large profile collections. Core feature request (prune tool) not addressed.

### 2.3 [#8223](https://github.com/nightscout/cgm-remote-monitor/issues/8223) — Duration events not displayed past midnight

**Status:** 🟡 Partially mitigated — `endmills` normalisation (Fixes 5/6b/7)
ensures documents carry computed `endmills`. Renderer midnight-clipping may
remain as a separate issue.

---

## 3. Related Issues (Not Directly Fixed)

| Issue | Title | Relationship | Status |
|-------|-------|--------------|--------|
| [#8183](https://github.com/nightscout/cgm-remote-monitor/issues/8183) | IFTTT Overrides show as Notes | IFTTT uses careportal path, not v1 treatments API. UUID handling not invoked. | ⬜ Not addressed |
| [#8156](https://github.com/nightscout/cgm-remote-monitor/issues/8156) | Loopalyzer rendering cache | `idMergePreferNew` improves data cache but Loopalyzer internal cache is separate. | ⬜ Not addressed |
| [#5230](https://github.com/nightscout/cgm-remote-monitor/issues/5230) | Overrides spanning 2 days invisible | `endmills` fixes help; renderer clipping likely remains. | 🟡 Partially |
| [#5992](https://github.com/nightscout/cgm-remote-monitor/issues/5992) | Terminated remote override rendering | May benefit from consistent UUID/identifier handling. | 🟡 Partially |

### Historical (closed)

| Issue | Title | Notes |
|-------|-------|-------|
| [#4761](https://github.com/nightscout/cgm-remote-monitor/issues/4761) | Override not visible in NS from Loop | Early UUID sync problem |
| [#7141](https://github.com/nightscout/cgm-remote-monitor/issues/7141) | Temporary Override fails | Override creation path |
| [#6841](https://github.com/nightscout/cgm-remote-monitor/issues/6841) | Overrides don't work from NS Careportal | Careportal override path |
| [#8323](https://github.com/nightscout/cgm-remote-monitor/issues/8323) | Event types disappear from dropdown | Treatment type registration |

---

## 4. Test Gap: Legacy UUID Data (#6923)

### The problem

Overrides created before the `normalizeTreatmentId()` fix have this shape in
MongoDB:

```json
{
  "_id": "69F15FD2-8075-4DEB-AEA3-4352F455840D",
  "eventType": "Temporary Override",
  "created_at": "2026-02-17T02:00:16.000Z",
  "durationType": "indefinite",
  "correctionRange": [90, 110],
  "reason": "Override Name"
}
```

Note: **no `identifier` field**. The UUID lives directly in `_id`.

### Code path analysis

**DELETE /api/v1/treatments/:uuid**

```
api/treatments/index.js:174  →  req.query.find._id = req.params.id  ("69F15FD2-...")
  → delete_records → ctx.treatments.remove(query)
    → treatments.js:237  remove() → query_for(opts)
      → query.js:95  updateIdQuery()
        → query.js:100  typeof query._id === 'string'
          → query.js:136  UUID_RE.test("69F15FD2-...") → true, uuidHandling → true
            → returns { searchByIdentifier: true }
              → query.js:103-105  query.identifier = UUID; delete query._id
                → deleteMany({ identifier: "69F15FD2-..." })
                  → matches 0 documents (legacy doc has no identifier field)
```

**Result:** No crash (the old ObjectId coercion is gone), but no delete either.
Silent failure.

**PUT /api/v1/treatments/ with UUID `_id`**

```
api/treatments/index.js:194  →  ctx.treatments.save(data)
  → treatments.js:253  save() → normalizeTreatmentId(obj)
    → obj.identifier = UUID, delete obj._id
      → upsertQueryFor(obj) → { identifier: UUID }
        → updateOne({ identifier: UUID }, ..., { upsert: true })
          → matches 0 documents → inserts NEW document
```

**Result:** No crash, but creates a duplicate instead of updating the original.

### Regression test: `tests/issue-6923-legacy-uuid.test.js`

A regression test was written to prove the legacy path is broken. It inserts a
document directly into MongoDB with UUID as `_id` (no `identifier` field) and
exercises each CRUD path. **All 3 tests fail as expected:**

```
  Issue #6923: Legacy UUID override edit/delete
    1) DELETE /api/v1/treatments/:uuid should actually remove the legacy document
    2) PUT /api/v1/treatments/ with UUID _id should update in place, not create a duplicate
    3) GET /api/v1/treatments/?find[_id]=UUID should find the legacy document

  0 passing (6s)
  3 failing
```

| Test | Expected | Actual | Root Cause |
|------|----------|--------|------------|
| DELETE | `deletedCount: 1` | `deletedCount: 0` — silent no-op | `updateIdQuery` rewrites `{_id: UUID}` → `{identifier: UUID}`, matches nothing |
| PUT | 1 document (updated) | **2 documents** (duplicate created) | `upsertQueryFor` matches by `identifier`, misses legacy doc, inserts new |
| GET | 1 result | 0 results | `normalizeIdValue` rewrites query to `{identifier: UUID}`, matches nothing |

**Run command:**
```bash
MONGO_CONNECTION="mongodb://localhost:27017/test_issue_6923" \
  npx mocha tests/issue-6923-legacy-uuid.test.js --exit --timeout 30000
```

These tests will continue to fail until the `$or` fallback (below) is
implemented. They serve as a regression safety net.

### Proposed fix direction

The `updateIdQuery()` function in `query.js` should, when `uuidHandling` is
enabled and the value is a UUID, produce an **$or** query:

```js
// Instead of only: { identifier: UUID }
// Use: { $or: [ { identifier: UUID }, { _id: UUID } ] }
```

This would find both new-format documents (UUID in `identifier`) and legacy
documents (UUID in `_id`), allowing DELETE and PUT to work on both.

---

## 5. Fix-to-Issue Traceability Matrix

| Fix | Code Location | Issues Fixed | Issues Mitigated |
|-----|---------------|-------------|-----------------|
| `normalizeTreatmentId()` | `lib/server/treatments.js:348` | #8450 (new data) | #5992 |
| `normalizeIdValue()` UUID rewrite | `lib/server/query.js:130` | #8450 (query path) | #6923 (partial) |
| `safeObjectID()` | `lib/server/websocket.js:15` | #8446 Fix 2 | #8129 |
| `toSafeInt()` | `lib/api3/storage/mongoCollection/find.js:10` | #8446 Fix 1 | #8144 |
| `$set` wrapper | `lib/server/treatments.js` (create) | #8446 Fix 3 | — |
| Stale broadcast elimination | `lib/api3/generic/patch/operation.js` | #8446 Fix 4 | #8129 |
| `endmills` (PATCH) | `lib/api3/generic/patch/operation.js` | #8446 Fix 5 | #8223, #5230 |
| `idMergePreferNew` | `lib/data/ddata.js:78` | #8446 Fix 6a | #8129, #8156 |
| `endmills` (data load) | `lib/data/ddata.js:53` | #8446 Fix 6b | #8223, #5230 |
| `endmills` (replace) | `lib/api3/generic/update/replace.js` | #8446 Fix 7 | #8223 |

## 6. Test Coverage Summary

| Test File | # Tests | Coverage |
|-----------|---------|----------|
| `tests/gap-treat-012.test.js` | 12 | Loop override UUID CRUD (new data only) |
| `tests/uuid-handling.test.js` | 8 | UUID_HANDLING flag on/off |
| `tests/api3.patch.test.js` | 1 | `endmills` on PATCH |
| `tests/api3.patch.operation.test.js` | 1 | WS broadcast post-PATCH |
| `tests/api3.update.test.js` | 1 | `endmills` on replace |
| `tests/ddata.test.js` | 2 | `idMergePreferNew` + `endmills` derivation |
| `tests/api.partial-failures.test.js` | 8 | Batch ordering, duplicate handling |
| `tests/api.deduplication.test.js` | ~8 | Cross-client dedup |
| **Total** | **~41** | All 7 fixes + UUID handling (new data) |

| `tests/issue-6923-legacy-uuid.test.js` | 3 | Legacy UUID data: DELETE/PUT/GET all fail (expected) |

**Known gap:** Legacy UUID documents (§4) — the 3 regression tests confirm all
operations silently fail. These tests document the bug and will pass once the
`$or` fallback query is implemented.
