<!-- Draft body, branch bf/autoprune-promise at 8e4f7dce (one commit on dev ca6fcfaf). Local only: not pushed, no PR opened. This comment is hidden on GitHub. -->
API v3 auto-prune now handles the result of its delete (BF-156). Before this change, the code passed a callback to a storage method that returns a promise and never calls the callback. As a result the "Auto-pruned N documents" line was never logged, and a failed delete was an unhandled promise rejection, which stops the Nightscout server. One commit on `dev` `ca6fcfaf`, which changes `lib/api3/generic/collection.js` and adds one test file. Not a security issue.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nothing here is medical advice.*

**Who is affected.** Only sites that have set one of the `API3_AUTOPRUNE_` settings: `API3_AUTOPRUNE_DEVICESTATUS`, `API3_AUTOPRUNE_ENTRIES`, `API3_AUTOPRUNE_TREATMENTS`, `API3_AUTOPRUNE_PROFILE`, `API3_AUTOPRUNE_FOOD` or `API3_AUTOPRUNE_SETTINGS`. These settings are off unless someone sets them. When one is set to a number of days, Nightscout **permanently deletes** stored records in that collection that are older than that many days. `API3_AUTOPRUNE_ENTRIES` covers your glucose history. The deletion happens at most once an hour, just after an app writes to that collection through API v3 (the newer API that AAPS and some other apps use). If none of these settings is set on your site, nothing changes for you.

**What was wrong.** On sites that set one of these settings:

- If the database reported an error during that hourly clean-up, the Nightscout server stopped. Your hosting service would usually restart it. Until it did, your site was down, and uploads and followers' views were interrupted.
- The server log never showed how many records were deleted, even when the clean-up worked.

The deletion itself worked as configured: old records were removed.

**What this change does.** A database error during the clean-up is now written to the server log, and the server keeps running. It tries again at the next hourly slot, not on every write, so a database that is already having trouble is not asked over and over. When records are deleted, the log now says how many and from which collection, for example `Auto-pruned 2 documents from treatments collection`.

**Do you need to do anything?** No. If you set an `API3_AUTOPRUNE_` setting on purpose, it keeps working as before, and you can now see in your server log what it deleted. If you did not mean to set one, remove it and restart Nightscout. Nightscout cannot bring back records it has already deleted; if you need them, restore them from your own database backup.

## Technical detail

### The defect, at `ca6fcfaf`

- `lib/api3/generic/collection.js:137-169` `autoPrune`. It runs when `API3_AUTOPRUNE_<COLLECTION>` (`:32`) is a number above 0, and at most once an hour per collection (`nextAutoPrune`). It is called after a successful create (`create/insert.js:51`), update (`update/replace.js:63`), patch (`patch/operation.js:99`) and delete (`delete/operation.js:69,97`).
- `:157` called `self.storage.deleteManyOr(filter, function deleteDone (err, result) {...})`.
- `self.storage` is `CachedCollectionStorage`. Its `deleteManyOr` (`lib/api3/storage/mongoCachedCollection/index.js:117`) is `async (filter)`. It awaits `baseStorage.deleteManyOr(filter)` (`:127`), which reaches `lib/api3/storage/mongoCollection/modify.js:128` `async function deleteManyOr (col, filterDef)` and resolves to `{ deleted: result.deletedCount }`.
- So the second argument was ignored. The callback never ran, so the count was never logged, and nothing handled the returned promise. On a database error the promise rejected unhandled. Node 15 and later end the process on an unhandled rejection by default (`--unhandled-rejections=throw`), and that covers every Node version this release supports (20, 22, 24).
- The delete itself ran and completed. Only its result was lost.

### The change

```js
self.storage.deleteManyOr(filter)
  .then(function deleteDone (result) {
    if (result && result.deleted) {
      console.info('Auto-pruned ' + result.deleted + ' documents from ' + self.colName + ' collection ');
    }
  })
  .catch(function deleteFailed (err) {
    console.error('Auto-prune of ' + self.colName + ' collection failed:', err);
  });

self.nextAutoPrune = new Date(new Date().getTime() + (3600 * 1000));
```

- **The count** comes from `result.deleted`, the field `modify.js` returns. The log line is the one the old callback was written to print.
- **Failure** is logged with the collection name and the error, and the process keeps running.
- **`nextAutoPrune` still advances after a failure.** It is set synchronously when the prune starts, as before, so the next attempt is an hour later. Moving it into the success path would retry on every v3 write to that collection while the database is failing. For an uploader writing every few minutes, that would add a large `$or` delete to every request against a database that is already in trouble. The hourly retry keeps the existing load profile, and the retention period is measured in days, so a missed hour changes nothing for the data.
- **Still non-blocking.** `autoPrune` is still synchronous and returns before the delete settles. The response has already been sent (`sendJSON` comes before `autoPrune` in `insert.js`), and none of the five call sites waits.

### Other calls of the same kind

`lib/api3` was searched for storage calls that pass a callback, and for storage calls that are neither awaited nor returned. `collection.js:157` is the only callback-style call to an async storage method. The other calls that are not awaited are `identifyingFilter` (synchronous: `utils.identifyingFilter`), in `create/operation.js:43`, `update/operation.js:37` and `patch/operation.js:33`, and `storage.version()` in `shared/storageTools.js:16`, which is chained with `.then(..., reject)`. None of them needs a change.

### 15.0.8

`autoPrune` is the same on `v15.0.8` (`92d08342`, which is `master`): the call is at `collection.js:149`. So are `CachedCollectionStorage.deleteManyOr` (`index.js:83`) and `modify.js` `deleteManyOr` (`:72`). The files differ elsewhere, but not in these functions. The defect ships in 15.0.8, and this commit applies to it unchanged.

## Tests

`tests/api3.autoprune.test.js` (new) starts the standard API v3 test instance against a real MongoDB with `API3_AUTOPRUNE_TREATMENTS=30`. It restores the variable afterwards. Before each test it resets `nextAutoPrune`, captures `console.info` and `console.error`, and adds an `unhandledRejection` listener. Mocha's own handler re-emits a rejection from user code on `process`, so the listener counts each promise once.

1. **The setting is read:** `autoPruneDays` is `'30'`.
2. **A v3 create prunes and logs.** Three treatments go directly into the collection: two dated 40 days ago and one dated 5 days ago. A `POST /api/v3/treatments` returns 201. The test waits for a log line matching `^Auto-pruned 2 documents from treatments collection`. It then checks that only the new document and the 5-day-old one remain, that `nextAutoPrune` is an hour away, and that there was no unhandled rejection.
3. **A failing prune is logged and the process keeps running.** `deleteManyOr` on the treatments collection's storage is stubbed to reject. After a v3 create (201), the test checks:
   - the error is logged;
   - the `unhandledRejection` listener saw nothing;
   - the stub was called once;
   - `nextAutoPrune` is an hour away;
   - a second create does not call the stub again;
   - a v3 search still answers 200.

### Break-its

Each break was run against the same test file and MongoDB.

| break | result | why it is the right failure |
|---|---|---|
| the fix reverted (the `ca6fcfaf` callback form) | 2 and 3 fail | 2: `expected an "Auto-pruned" log line` (the callback never runs). 3: the listener received `[ 'simulated autoprune storage failure' ]`, which is the unhandled rejection. |
| `.catch` removed, `.then` kept | 3 fails | the listener received the same unhandled rejection |
| `result.deletedCount` instead of `result.deleted` | 2 fails | `expected an "Auto-pruned" log line`: the wrong field is undefined |
| `nextAutoPrune` advanced only on success | 3 fails | `expected 0 to be above …`: a failure would be retried on the next write |

Under Mocha a rejection does not end the process, because Mocha installs its own handler. So test 3 detects the rejection with a listener rather than by watching the process exit. A separate in-process probe, outside Mocha, covers the exit. It uses the shipping `Collection` and `CachedCollectionStorage` with only the Mongo layer faked, on Node 22.23.2. With a rejecting delete, `ca6fcfaf` exits with code 1 (`Error: simulated storage failure`), and this branch logs the error, is still alive 200 ms later, and exits 0. With a delete that succeeds, `ca6fcfaf` logs no "Auto-pruned" line, and this branch logs one.

### Validation (Node 22.23.2, MongoDB 7.0.43 in a dedicated container, `--ulimit nofile=64000:64000`)

- `npm ci` clean. `eslint` is clean on both changed files.
- Full suite (`npm test` form, `./tests/*.test.js`) at `8e4f7dce`: 3537 passing, 0 failing, 4 pending. The base `ca6fcfaf` measured 3534 passing, 0 failing, 4 pending, and this branch adds three tests.

## Open points

- **`tools/queue/gates/config-surface-census.js` `api3` arm** (alignment repository). Its deletion check passes only on `await self.storage.deleteManyOr`, so it stays red on this branch even though the promise is now handled. The check should also accept a `.catch` on the returned promise. Making `autoPrune` `async` only to satisfy the regex was not done.
- **Cache invalidation is capped at 1,000 documents** (`mongoCachedCollection/index.js:119-124`). This was noticed while reading the code and is not changed here. It looks up at most 1,000 matching ids to evict from the in-memory cache, but the delete removes every match. A first prune on a large, long-unpruned collection could therefore leave deleted documents in the cache until they age out. Not measured.
