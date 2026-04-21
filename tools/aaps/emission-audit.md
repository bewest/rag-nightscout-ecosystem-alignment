# AAPS Profile-Edit Emission Audit

**Goal**: enumerate exactly what AAPS uploads to Nightscout when a user edits the Local Profile and presses **Save**, separately for NSClient (V1) and NSClientV3.

References use commit-stable paths under `externals/AndroidAPS/`.

---

## Triggering action

ProfileFragment "Save" button:

> `plugins/main/src/main/kotlin/app/aaps/plugins/main/profile/ProfileFragment.kt:338-348`
>
> ```kotlin
> binding.save.setOnClickListener {
>   ...
>   profilePlugin.storeSettings(activity, dateUtil.now())
> }
> ```

`ProfilePlugin.storeSettings` (`plugins/main/.../ProfilePlugin.kt:184-209`):

1. Persists profile fields to local preferences.
2. Sets `LongNonKey.LocalProfileLastChange = timestamp` (i.e. `now()`).
3. Calls `createAndStoreConvertedProfile()`.
4. `rxBus.send(EventProfileStoreChanged())`.

Crucially, **no `ProfileSwitch` treatment is created here**. `createProfileSwitch` (`implementation/.../ProfileFunctionImpl.kt:167-197`) is invoked only from:

- `ProfileSwitchDialog` (user-initiated switch)
- `loadFromStore` flow (when receiving from NS) — indirectly via callers
- The keep-alive worker re-sending an existing switch

So a Local Profile edit by itself emits **only the profile-store update**, not a profile-switch.

---

## NSClient V1 path

Subscriber: `plugins/sync/.../nsclient/services/NSClientService.kt:215-217`

```kotlin
.toObservable(EventProfileStoreChanged::class.java)
...
.subscribe({ resend("EventProfileStoreChanged") }, ...)
```

`resend()` triggers `DataSyncSelectorV1.processChangedProfileStore()` (`plugins/sync/.../nsclient/DataSyncSelectorV1.kt:786-805`):

```kotlin
val lastSync = preferences.get(NsclientLongKey.ProfileStoreLastSyncedId)
val lastChange = preferences.get(LongNonKey.LocalProfileLastChange)
if (lastChange == 0L) return                         // ← guard #1
if (lastChange > lastSync) {
  if (activePlugin.activeProfileSource.profile?.allProfilesValid != true) return  // ← guard #2
  val profileJson = profileStore?.getData() ?: return
  if (JsonHelper.safeGetLongAllowNull(profileJson, "date") == null)
    profileJson.put("date", profileStore.getStartDate())
  val dataPair = DataSyncSelector.PairProfileStore(profileJson, dateUtil.now())
  activePlugin.activeNsClient?.nsAdd("profile", dataPair, "")
  synchronized(dataPair) { dataPair.waitMillis(60000) }                          // ← 60s ack window
  val now = dateUtil.now()
  if (dataPair.confirmed) confirmLastProfileStore(now)                            // ← bug-prone: uses now(), not lastChange
}
```

Wire format: Socket.IO `dbAdd` event with collection `"profile"` and the profile-store JSON as payload. Reaches c-r-m at `lib/server/websocket.js` profile branch.

### Potential V1 failure modes for "edit didn't propagate"

| Mode | Symptom |
|---|---|
| `lastChange == 0L` (guard #1) — happens if user imported NS profile with `startDate=0`/missing, then never touched local profile after | First edit may not fire because `storeSettings(timestamp = store.getStartDate())` set lastChange=0; next edit with `dateUtil.now()` should clear this |
| `allProfilesValid != true` (guard #2) | Silent no-op |
| Server replies but `dataPair.confirmed=false` after 60s | No advance of `lastSync` → next edit will retry; but original row may still have been written on server |
| `confirmLastProfileStore(now)` saves `now` instead of `lastChange` | Race: another edit arrives during 60s window, gets timestamp `lastChange2 < now`, considered already-synced → **lost edit**. This is the V1 race we patched in c-r-m via dedup + `_id` sort tiebreaker. |

---

## NSClient V3 path

Subscriber: `plugins/sync/.../nsclientV3/NSClientV3Plugin.kt:295-297`

```kotlin
.toObservable(EventProfileStoreChanged::class.java)
...
.subscribe({ executeUpload("EventProfileStoreChanged", forceNew = false) }, ...)
```

`executeUpload` eventually calls `DataSyncSelectorV3.processChangedProfileStore()` (`plugins/sync/.../nsclientV3/DataSyncSelectorV3.kt:712-728`):

```kotlin
val lastSync = preferences.get(NsclientLongKey.ProfileStoreLastSyncedId)
val lastChange = preferences.get(LongNonKey.LocalProfileLastChange)
if (lastChange == 0L) return
if (lastChange > lastSync) {
  if (activePlugin.activeProfileSource.profile?.allProfilesValid != true) return
  val profileJson = profileStore?.getData() ?: return
  if (JsonHelper.safeGetLongAllowNull(profileJson, "date") == null)
    profileJson.put("date", profileStore.getStartDate())
  val now = dateUtil.now()
  if (activePlugin.activeNsClient?.nsAdd("profile", PairProfileStore(profileJson, now), "") == true)
    confirmLastProfileStore(now)                                                  // ← same bug shape
}
```

Wire format: REST `POST /api/v3/profile` via `NSAndroidClientImpl.createProfileStore` (`core/nssdk/.../NSAndroidClientImpl.kt:436`), which adds `"app": "AAPS"` to the body. Reaches c-r-m at `lib/api3/generic/create/operation.js`.

V3 dedup behavior in c-r-m (verified in `tests/api3.aaps-patterns.test.js`):

- Identifier = `uuid.v5(device + '_' + date)` because profile docs lack `device`/`eventType`. So `device=undefined`, identifier depends only on `date`.
- Same-`date` retry within or after 60s → c-r-m treats as duplicate; existing doc updated (no new row).
- Different-`date` edit → new row. **Each profile edit produces a new "Database records" entry.**

### Potential V3 failure modes for "edit didn't propagate"

| Mode | Symptom |
|---|---|
| `lastChange == 0L` (initial-import edge case) | Same as V1 |
| `allProfilesValid != true` | Silent no-op |
| `nsAdd` returns `false` (HTTP error / parse error) | `lastSync` not advanced → retried on next event; no diagnostic in NS unless logging is enabled |
| `confirmLastProfileStore(now)` race | Same shape as V1; in V3 a "lost" edit means no row on server (because dedup-by-identifier requires same `date`, which won't happen for distinct edits) |

---

## What about the "Test@@@@@\<ts\>" columns the user reports?

These are NOT profile-store records. They are **profile-switch treatments** rendered by NS's Reporting page via `lib/profilefunctions.js:272-287`, which injects each switch's embedded `profileJson` into the in-memory profile store using the disambiguator `<name>@@@@@<mills>`.

Profile-switch treatments are produced by AAPS only when the user explicitly:

- Activates a profile in the Profile Switch dialog (`createProfileSwitch`)
- Imports a profile from NS that triggers `loadFromStore` followed by an automatic switch
- Pump-driver paths (Dana, Omnipod) that send `EventProfileSwitchChanged`

A user who **only edits Local Profile** should see new "Database records" entries (V3 path) or potentially merged ones (V1 path with same `defaultProfile`), **not** new profile-switch columns.

If the user is seeing many `Test@@@@@…` columns, they have been creating profile switches as well (likely through the dialog or pump-driver flow). That part is **working as designed**.

---

## Decision tree for diagnosing a real-world report

```
"My edit doesn't show up in NS Profile Editor"
│
├── Database records dropdown shows only one entry (1969 or otherwise old)?
│   ├── YES → AAPS is not (or no longer) sending profile-store updates.
│   │        Probable causes (in order of likelihood):
│   │          1. NSClient(V1/V3) plugin not enabled
│   │          2. lastChange == 0L guard hit (initial-import edge case) — fix: edit & save once more
│   │          3. allProfilesValid == false (invalid profile state)
│   │          4. nsAdd persistently failing (network/auth) — check NS server logs for /api/vN/profile
│   │          5. (V1 only) Race losing every edit → unlikely to lose ALL of them
│   │
│   └── NO (multiple entries appear) → AAPS is sending; user just hasn't selected the right one.
│         Open the dropdown, pick newest entry.
│
└── Profile Editor shows wrong profile name even on newest record?
    ├── Newest record's `defaultProfile` field is wrong → AAPS-side bug or user editing different profile
    └── Newest record's `defaultProfile` is right but `store[name]` content is stale → NS client cache; force refresh
```

The Discord user's screenshots show **scenario YES** (only one Database records entry, 1969). Our V1 dedup fix would only matter in the rare "race losing every edit" case — and even then, retries would normally land *some* edits.

Most likely root cause: **#2 (`lastChange == 0L`) or #4 (nsAdd failing silently)**, neither of which is fixed by c-r-m changes alone.
