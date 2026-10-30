# DRAFT backfix-register entry: a remove without ids flushes every cache

Status: draft for the plan owner. No id allocated; not in the register.
Lab: tools/lab/cache-value (Part 1). Marks: [M] measured, [R] read from code.

## Mechanism

- [R] `lib/server/cache.js` `dataChanged`: for `op == 'remove'` with no
  `changes`, the handler empties `data.treatments`, `data.devicestatus` and
  `data.entries` and bumps all three removal generations, whatever
  `operation.type` is. The per-collection branch (`changes` present) touches
  only `data[operation.type]`.
- [R] `lib/server/object-id-forms.js` `cacheRemoval(asked, deletedCount)`
  returns `undefined` for a delete by query (no `find[_id]`) whenever
  `deletedCount !== 1`, and returns `asked` (also `undefined`) when
  `deletedCount === 0`. So the v1 treatments, entries and devicestatus delete
  by query emit a remove with no `changes` both when they delete several records
  and when they delete none.
- [R] The dataloader (`lib/data/dataloader.js`) takes its long load for any
  datatype whose cache holds fewer than 20 records (`cache.isEmpty`): 48 h of
  entries, 60 h of treatments, 24 h (or 48 h) of devicestatus, instead of the
  15-minute incremental window.
- [R] Dev already has a per-collection flush, `cache.invalidate(datatype)`, and
  the comments in `lib/server/websocket.js` (reconcilePartialWrite) and
  `lib/api3/storage/mongoCachedCollection/index.js` describe the no-changes
  remove as dropping "this collection" / as "the existing global invalidation".
  The behaviour matches the second description, not the first.

## Trigger

- [M] `DELETE /api/v1/treatments/?find[eventType]=Note` with the API secret
  (3 matching records) and the same request matching 0 records.
- [R] Other emitters of a remove with no `changes`: v1 entries and devicestatus
  delete by query (`lib/server/entries.js`, `lib/server/devicestatus.js`, same
  `cacheRemoval`); the socket's fallback in `lib/server/websocket.js`
  (`changes: null`, only when `cache.invalidate` is unavailable); api3
  `deleteManyOr` when it removes more than one document, which is the hourly
  auto-prune when `API3_AUTOPRUNE_<COLLECTION>` is set; on dev only, the api3
  cached wrapper's filter-AST writes (`insertMany`, `deleteMany`, `bulkUpsert`,
  `updateMany`, `replaceFiltered`), for which grep found no caller under
  `lib/api3`.

## Consequence measured

Synthetic site, MongoDB 8.0.34, Node v22.23.4, dev e1f7ac41; caches before the
delete: 31 treatments / 287 devicestatus / 575 entries. Profiler level 2 over
the delete and the reload it triggers (results/p1-unpatched.json,
results/p1-unpatched-run2.json, results/p1-patched.json).

| | caches right after the delete (tx/ds/entries) | reload windows | MongoDB ops | documents returned | bytes returned |
|---|---|---|---|---|---|
| warm reload, nothing changed [M] | 32/287/575 | 15 min each | 14 | 4 | 6,226 |
| delete by id [M] | 31/287/575 | 15 min each | 15 | 4 | 6,226 |
| delete by query, dev [M] | 0/0/0 | tx 60 h, ds 24 h, entries 48 h | 15 | 890 | 716,202 |
| delete by query matching 0 records, dev [M] | 0/0/0 | tx 60 h, ds 24 h, entries 48 h | 15 | 890 | 716,202 |
| delete by query, patched [M] | 0/287/575 | tx 60 h, ds and entries 15 min | 15 | 32 | 10,247 |

- [M] The number of MongoDB operations does not change; what changes is the
  amount returned: devicestatus 613,602 bytes and entries 97,166 bytes of the
  716,202, against 4,378 and 435 bytes on the 15-minute reload.
- [M] The caches refill on that one reload (afterwards 28/287/575 in both
  arms). The cost is one long load per trigger, plus, for the moment between
  the flush and the end of the reload, empty entries and devicestatus caches
  (a v1 follower GET in that moment falls through to MongoDB [R]).
- [M] Reproduced twice on unpatched dev with identical figures.

## Versions affected

- [R] dev e1f7ac41 (official/dev, 2026-10-29): present.
- [R] v15.0.9 (c6a0d8ed): the same three-cache flush in `lib/server/cache.js`
  (lines 124-137) and the same `cacheRemoval`. Not run on 15.0.9.
- [R] Introduced in f878ce11 (2020-09-20); the first tag containing it is
  14.0.4. Before it the line was `data[operation.op.type] = []`, which cleared
  nothing useful.

## Proposed fix

Flush only the datatype named by the operation (patches/overflush-fix.patch):

```diff
       if (!operation.changes) {
-        data.treatments = [];
-        data.devicestatus = [];
-        data.entries = [];
-        removalGenerations.treatments += 1;
-        removalGenerations.devicestatus += 1;
-        removalGenerations.entries += 1;
+        data[operation.type] = [];
+        removalGenerations[operation.type] += 1;
       } else {
```

`data.invalidate(operation.type)` does the same thing and could be called
instead. The early `if (!data[operation.type]) return;` already limits the
handler to the three cached types.

Control (overflush.js --control): FAIL on unpatched dev with "entries cache
emptied by a treatments delete-by-query: before 575, after 0" (and the matching
devicestatus, generation and long-load messages); PASS with the patch.

Not covered here: whether a delete matching 0 records should flush the
treatments cache at all (it still does with the patch), and a test in the crm
suite.
