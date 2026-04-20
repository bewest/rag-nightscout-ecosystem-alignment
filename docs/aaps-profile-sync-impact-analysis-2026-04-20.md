# AAPS Profile Sync to Nightscout: Impact Analysis

**Date**: 2026-04-20
**Audience**: cgm-remote-monitor maintainers, AndroidAPS maintainers
**Reporter**: Nightscout ecosystem alignment workspace
**c-r-m PR**: [nightscout/cgm-remote-monitor#8475](https://github.com/nightscout/cgm-remote-monitor/pull/8475)
**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447` (branch `wip/test-improvements`)
**Fix commit (c-r-m)**: `85f7e6ac` — fix(websocket): dedup AAPS profile dbAdd by startDate; warn on insert errors
**AAPS reference**: tag `3.4.2.2` (commit `5b1a2fec02`)

---

## TL;DR

AAPS users report that **editing a profile in AAPS does not appear to update the profile shown in Nightscout**, while a full initial profile sync works.

The root cause is a two-side mismatch:

1. **AAPS V1 NSClient never issues a profile UPDATE** — every change is sent as `dbAdd`. There is no `nsUpdate("profile", …)` path.
2. **c-r-m's websocket `dbAdd` handler has no dedup branch for the `profile` collection** — it falls through to a generic `insertOne` and silently swallows any error.

Result: each AAPS profile edit creates a *new* MongoDB document. Which document the UI shows is then determined by `ctx.profile.last()` ordering, which is non-deterministic on `startDate` ties.

A secondary (narrower) issue exists in AAPS: `confirmLastProfileStore(now)` uses wallclock-now instead of the `lastChange` value that was just synced, which causes a lost-edit race when the user re-edits within the 60s socket ack window.

**The c-r-m fix in this report makes profile updates work for all AAPS users without an AAPS update.** The AAPS-side fix is a recommended defense-in-depth improvement that addresses the rapid-re-edit race.

---

## Symptom

| Action in AAPS | Expected on NS | Actual |
|---|---|---|
| Initial full profile push | Profile appears | ✅ Works |
| Edit existing profile (e.g. change a CR) | Profile updates | ❌ Update not visible / inconsistent |
| Re-edit same profile multiple times | Latest version visible | ❌ Older version may be displayed |

---

## Code Path Traced

### AAPS side (V1 NSClient)

`plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/DataSyncSelectorV1.kt:786-805`

```kotlin
private suspend fun processChangedProfileStore() {
    if (isPaused) return
    val lastSync = preferences.get(NsclientLongKey.ProfileStoreLastSyncedId)
    val lastChange = preferences.get(LongNonKey.LocalProfileLastChange)
    if (lastChange == 0L) return
    if (lastChange > lastSync) {
        if (activePlugin.activeProfileSource.profile?.allProfilesValid != true) return
        val profileStore = activePlugin.activeProfileSource.profile
        val profileJson = profileStore?.getData() ?: return
        if (JsonHelper.safeGetLongAllowNull(profileJson, "date") == null)
            profileJson.put("date", profileStore.getStartDate())
        val dataPair = DataSyncSelector.PairProfileStore(profileJson, dateUtil.now())
        activePlugin.activeNsClient?.nsAdd("profile", dataPair, "")
        synchronized(dataPair) { dataPair.waitMillis(60000) }
        val now = dateUtil.now()
        val cont = dataPair.confirmed
        if (cont) confirmLastProfileStore(now)
    }
}
```

Observations:

- `nsAdd` is the **only** sync method called for profiles — there is no `nsUpdate` branch anywhere in V1 (or V3 — see `DataSyncSelectorV3.kt:725`).
- `PairProfileStore` is the only `Pair*` ack type that does not record an NS-assigned id. See `NSClientAddAckWorker.kt:164-168`:
  ```kotlin
  is PairProfileStore -> {
      dataPair.confirmed = true
  }
  ```
  Compare to every other Pair (treatments, food, devicestatus, etc.) which calls `storeDataForDb.addToNsId…` to track the server-assigned `_id`.
- `confirmLastProfileStore(now)` uses `dateUtil.now()` after the ack instead of the `lastChange` value captured at send time.

### c-r-m side (websocket)

`lib/server/websocket.js:370-534` (pre-fix)

`processSingleDbAdd` has explicit dedup branches for `treatments` (lines 380-472) and `devicestatus` (lines 474-513), but **no branch for `profile`** — profile falls through to the generic `else`:

```js
} else {
  try {
    var genericInsertResult = await mongoCollection.insertOne(data.data);
    var genericDoc = data.data;
    genericDoc._id = genericInsertResult.insertedId;
    ctx.bus.emit('data-update', { type: data.collection, op: 'update', changes: ... });
    ctx.bus.emit('data-received');
    return [genericDoc];
  } catch (err) {
    if (err != null && err.message) {
      console.log(data.collection + ' insertion error: ', err.message);  // <-- silent
      return [];
    }
    throw err;
  }
}
```

Each AAPS profile edit therefore inserts a new document. If the source `JSONObject` retains an `_id` from a previously-imported profile, the resulting `E11000 duplicate key` error is logged at `console.log` level (often invisible in production) and the call returns `[]`.

`lib/server/profile.js:120` (pre-fix):

```js
function last (fn) {
  return runWithCallback(function () {
    return api().find().sort({startDate: -1}).limit(1).toArray();
  }, fn);
}
```

When multiple profile documents share the same `startDate`, MongoDB's tiebreaker is undefined, so which profile the UI displays becomes effectively random.

---

## Demonstration

### Bug demonstration (pre-fix)

We added regression tests in `tests/websocket.shape-handling.test.js` and ran them against the pre-fix `lib/server/websocket.js` (via `git checkout HEAD~1 -- lib/server/websocket.js`):

```
1) repeated AAPS profile dbAdd with same startDate REPLACES instead of duplicating:
   Uncaught AssertionError: expected '69e676370c32c9251e86ff9c' to be '69e676370c32c9251e86ff9b'
```

Two `dbAdd` calls with identical `startDate` produced two distinct `_id` values, proving a duplicate document was created instead of an update.

### Fix verification (post-fix)

After the fix is applied, the same tests pass: the second `dbAdd` returns the same `_id` as the first, and the document content is updated in place. Full test suite: 878 passing, 1 pending, 3 pre-existing unrelated failures (security tests on `release/dev`).

### AAPS race demonstration

`tools/aaps/profile_sync_race_simulation.js` (this workspace) simulates `processChangedProfileStore` with the buggy `confirmLastProfileStore(now)` and the proposed `confirmLastProfileStore(lastChangeAtSend)`:

```
=== BUGGY: confirmLastProfileStore(dateUtil.now()) ===
  edits made:  [ 1000, 1500 ]
  edits sent:  [ 1000 ]
  LOST edits:  [ 1500 ]

=== FIXED: confirmLastProfileStore(lastChangeAtSend) ===
  edits made:  [ 1000, 1500 ]
  edits sent:  [ 1000, 1500 ]
  LOST edits:  none
```

Scenario: user edits at T=1000, sync poll at T=1100 sends the profile, user re-edits at T=1500 (during the 60s ack window), ack returns at T=2000. The buggy code sets `lastSync=2000`, so the T=1500 edit is permanently unsyncable until a future edit timestamp exceeds 2000.

---

## Fix #1 (c-r-m) — REQUIRED, lands the user-visible repair

**Worktree commit `85f7e6ac` on branch `wip/test-improvements`.**

### `lib/server/websocket.js` — add a `profile` dedup branch

Inserted between the `devicestatus` branch and the generic `else`:

```js
} else if (data.collection === 'profile') {
  var profileQuery = null;
  if (data.data.NSCLIENT_ID) {
    profileQuery = { NSCLIENT_ID: data.data.NSCLIENT_ID };
  } else if (data.data.startDate) {
    profileQuery = { startDate: data.data.startDate };
  }

  if (profileQuery) {
    try {
      var existingProfile = await mongoCollection.findOne(profileQuery);
      if (existingProfile) {
        console.log(LOG_DEDUP + 'Profile match on ' + Object.keys(profileQuery).join(',')
                    + '; replacing existing _id=' + existingProfile._id);
        var replacementDoc = Object.assign({}, data.data);
        replacementDoc._id = existingProfile._id;
        await mongoCollection.replaceOne({ _id: existingProfile._id }, replacementDoc);
        ctx.bus.emit('data-update', { type: 'profile', op: 'update',
                                      changes: ctx.ddata.processRawDataForRuntime([replacementDoc]) });
        ctx.bus.emit('data-received');
        return [replacementDoc];
      }
    } catch (err) {
      console.warn('profile dedup lookup error: ', err && err.message ? err.message : err);
      return [];
    }
  }

  try {
    var profileInsertResult = await mongoCollection.insertOne(data.data);
    /* … emit + return … */
  } catch (err) {
    if (err != null && err.message) {
      console.warn('profile insertion error: ', err.message);
      return [];
    }
    throw err;
  }
}
```

Also upgraded the generic `else` `console.log` → `console.warn` so MongoDB write failures are visible in production logs.

### `lib/server/profile.js` — deterministic tie-breaker in `last()`

```js
function last (fn) {
  return runWithCallback(function () {
    return api().find().sort({startDate: -1, _id: -1}).limit(1).toArray();
  }, fn);
}
```

This makes the choice between any pre-existing duplicate profiles deterministic (newest insert wins) without requiring a data migration.

### `tests/websocket.shape-handling.test.js` — regression coverage

Three new tests under `dbAdd profile collection (AAPS V1 sync)`:

1. First AAPS-shaped profile dbAdd inserts a new document.
2. Repeated dbAdd with same `startDate` returns the **same** `_id` and replaces in place (proven to fail without the fix).
3. dbAdd with a distinct `startDate` inserts and `ctx.profile.last()` returns the newest by content.

---

## Fix #2 (AndroidAPS) — RECOMMENDED, addresses rapid-re-edit race

`plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/DataSyncSelectorV1.kt:786-805`

```diff
 private suspend fun processChangedProfileStore() {
     if (isPaused) return
     val lastSync = preferences.get(NsclientLongKey.ProfileStoreLastSyncedId)
     val lastChange = preferences.get(LongNonKey.LocalProfileLastChange)
     if (lastChange == 0L) return
     if (lastChange > lastSync) {
         if (activePlugin.activeProfileSource.profile?.allProfilesValid != true) return
         val profileStore = activePlugin.activeProfileSource.profile
         val profileJson = profileStore?.getData() ?: return
         if (JsonHelper.safeGetLongAllowNull(profileJson, "date") == null)
             profileJson.put("date", profileStore.getStartDate())
-        val dataPair = DataSyncSelector.PairProfileStore(profileJson, dateUtil.now())
+        val syncedChange = lastChange
+        val dataPair = DataSyncSelector.PairProfileStore(profileJson, syncedChange)
         activePlugin.activeNsClient?.nsAdd("profile", dataPair, "")
         synchronized(dataPair) { dataPair.waitMillis(60000) }
-        val now = dateUtil.now()
         val cont = dataPair.confirmed
-        if (cont) confirmLastProfileStore(now)
+        if (cont) confirmLastProfileStore(syncedChange)
     }
 }
```

**Why:** sets `ProfileStoreLastSyncedId` to the watermark that was actually synced. If the user re-edits during the 60s ack window, that newer `lastChange` exceeds `lastSync` and the next poll re-sends. With the current code, `lastSync` jumps past the unsynced `lastChange` and the edit is silently dropped.

The same pattern appears in V3 (`DataSyncSelectorV3.kt:712-728`) and should be considered there as well.

### Suggested test
A `DataSyncSelectorV1Test` does not currently exist (only V3 has a test). The simulation in `tools/aaps/profile_sync_race_simulation.js` of the workspace can be ported to a JUnit test using mocked `dateUtil` and `preferences`.

---

## Why fix #1 (c-r-m) is sufficient for users

| Symptom | Fixed by c-r-m alone? |
|---|---|
| Profile edit creates duplicate document | ✅ Yes — dedup branch replaces in place |
| User sees stale profile due to non-deterministic `last()` | ✅ Yes — secondary `_id` sort + dedup eliminates duplicates going forward |
| Mongo errors on profile insert silently swallowed | ✅ Yes — `console.warn` |
| Rapid re-edit within 60s loses an edit | ❌ No — requires AAPS-side fix |

**No AAPS update is required for users to see the primary symptom resolved.** As soon as their Nightscout server runs the patched c-r-m, AAPS profile edits will update the existing profile document instead of creating duplicates.

---

## Recommended PRs

1. **c-r-m PR** — base `release/dev` ← branch `wip/test-improvements`
   - Either the full branch (which also restores the `/test` endpoint env support and includes the cgm-pr-8447 fixes) or just `85f7e6ac` cherry-picked.
   - Title suggestion: `fix(websocket): dedup AAPS profile dbAdd by startDate; warn on insert errors`
2. **AndroidAPS PR** — change `confirmLastProfileStore(now)` → `confirmLastProfileStore(syncedChange)` in V1, mirror in V3 if appropriate, add `DataSyncSelectorV1Test` covering the rapid-re-edit race.

---

## Open questions worth flagging upstream

- **Should `PairProfileStore` track `nightscoutId`?** Every other `Pair*` does. Tracking would let AAPS use stable `_id` references and allow the c-r-m server to do `_id`-based dedup rather than `startDate`-based. It would also unblock a future `nsUpdate` path for profiles.
- **The `createdAt % 1000 == 0L` heuristic in `NsIncomingDataProcessor.processProfile:283-295`** ("whole second means edited in NS") is fragile — any AAPS-originated profile whose epoch happens to land on a whole second will be re-imported as if NS-edited. Worth replacing with explicit provenance.
- **V3 path** uses REST POST and `lib/server/profile.js:save()` (which now does `replaceOne` upsert by `_id`), but `createProfileStore` does not include `_id`, so V3 may exhibit the same insert-on-edit behavior via REST. Worth verifying separately.

---

## References

- c-r-m fix: commit `85f7e6ac` on `wip/test-improvements`
- c-r-m files: `lib/server/websocket.js`, `lib/server/profile.js`, `tests/websocket.shape-handling.test.js`
- AAPS files: `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/DataSyncSelectorV1.kt`, `…/workers/NSClientAddAckWorker.kt`, `…/nsShared/NsIncomingDataProcessor.kt`, `plugins/main/src/main/kotlin/app/aaps/plugins/main/profile/ProfilePlugin.kt`
- Workspace simulation: `tools/aaps/profile_sync_race_simulation.js`
