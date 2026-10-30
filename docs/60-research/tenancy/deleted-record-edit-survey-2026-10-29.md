# Edits of a soft-deleted record: what clients do

> **Snapshot, 2026-10-29.** Contributor-facing. This is a read-only survey for ID-Q3 of the
> [ID-FIRST-MATCH design note](../../30-design/platform/id-first-match-design-note-2026-10-29.md#6a-question-ids-and-answers-session--a5-2026-10-29).
> **[R]** means read in code; **[M]** means measured in a lab.

**Refs.**

| project | ref |
|---|---|
| cgm-remote-monitor | `dev` `cf3d4b8f` |
| AndroidAPS | master `aa16db64`; dev `7e1d537d` (the quoted passages are confirmed at dev head `19c8e521`) |
| Loop | LoopWorkspace v3.14.9 `548b332` (NightscoutService `2cef4896`, NightscoutKit `4ec9fd1`) |
| Trio | v1.0.2 `0b29cd53` |
| xDrip+ | 2026.09.18 `1ed76004` |
| xDrip4iOS | 7.1.1 `c268542e` |
| tconnectsync | v3.0.1 `7c4b2f4` |
| nightscout-connect | dev `04102f9` |
| LoopFollow | `4a74b781` |
| LoopCaregiver | `2305718` |
| nightguard | `75404bd` |

## 1. What the server does with an edit of a deleted record

**API v3 PUT and PATCH: 410.**
- PUT: `lib/api3/generic/update/operation.js:65-66`. **[M]**: record-identity lab, 2026-10-27.
- PATCH: `lib/api3/generic/patch/operation.js:53-56`. **[R]**
- The swagger states the 410 contract for read, update and patch (`lib/api3/swagger.yaml:168,211,270`).
- API v3 POST, by contrast, revives a deleted record, except on device status. **[M]**: matrix
  `dev-e1f7ac41-idfirst`.

**API v1 PUT on treatments, profile, food and activity: replaces the record, which revives it.** **[R]**
- Treatments: `treatments.save`, `lib/server/treatments.js:404-460`. Its write is an upsert of the
  client's body, which carries no `isValid`.
- Profile, food and activity: `profile.js:180-213`, `food.js:104-135`, `activity.js:54,91`.
- No v1 path checks `isValid` on an edit.
- Entries and device status have no v1 PUT.

**Socket `dbUpdate`:** a `$set` or merge patch, with no `isValid` check. **[R]**
- The record stays deleted unless the body carries `isValid: true`.
- AndroidAPS's legacy v1 client sends the full record, `isValid` included, so its edits revive.

**Who soft-deletes.**
- API v3 DELETE without `permanent=true`, as used by AndroidAPS NSClientV3 and AAPSClient.
- AndroidAPS's legacy v1 client (`dbUpdate isValid:false`).
- Any write that carries `isValid:false`. No surveyed client sends one this way.

**Who hard-deletes.**
- The website: the chart's Remove sends `dbRemove`; the report editor and admin tools use v1 DELETE.
- Loop, Trio, xDrip+, nightscout-connect and tconnectsync. **[R]**

## 2. When it happens

It needs a soft-delete producer and a v1 editor acting on the same record.

**The likely case:** a site with AndroidAPS (or AAPSClient) and xDrip+.
1. A user deletes a treatment in AndroidAPS, which sends a v3 soft DELETE.
2. xDrip+ later PUTs that same treatment again. It PUTs every upload, creates included.

**Loop and Trio sites** rarely have a soft-delete producer.

**AndroidAPS editing a record deleted elsewhere** gets 410 on its PATCH. That is today's v3 behaviour, and
ID-Q3's v1 choice does not change it.

## 3. AndroidAPS

**Incoming deletions.**
- `SyncNs*Transaction` reads "nsId exists, allow only invalidation" (e.g. `SyncNsCarbsTransaction.kt:20-34`):
  a deletion is applied locally and never undone.
- A record revived on Nightscout therefore stays invalid in AndroidAPS.

**Its own edit getting a 410.** It is retried every round with no limit, and that record type's upload queue
stalls.
- Master: `NSClientV3Plugin.kt:648-657`; `DataSyncSelectorV3.kt:218-220`.
- Dev bounds 404s to 5 retries but not 410s. Its own comment says "a permanently failing record can't wedge its
  collection's cursor", so this is a client-side gap.

**Stated intent.**
- Deletion is final.
- Soft delete exists so a v3 history client learns of deletions (`lib/server/soft-deleted.js:5-10`).
- 410 is a v3 contract AndroidAPS codes around: `ClientControlReceiver.kt`, PR #4933, commit `1a8544a085`.
- No AndroidAPS issue asks the server to change it.

## 4. Per client

| client | how it edits | can it edit a record deleted elsewhere | reaction to a 4xx | under "refuse" | under "acknowledge, stays deleted" |
|---|---|---|---|---|---|
| AndroidAPS NSClientV3 | v3 PATCH; v3 soft DELETE | yes, low to moderate | 410: retried with no limit, blocks that type | unchanged (v3 already 410) | changes only if v3 also moved |
| AndroidAPS legacy v1 socket | `dbUpdate` with the full body | low | ack ignored | dropped | dropped |
| Loop 3.14.9 carbs | v1 PUT by `_id` cached 24 h | rare | batch fails and retries indefinitely; carb deletes in the batch not sent | endless retries | silent divergence (Loop shows it, Nightscout doesn't) |
| Trio 1.0.2 | no PUT/PATCH | n/a | retried | no effect | no effect |
| xDrip+ | v1 PUT for every upload | moderate on mixed AndroidAPS sites | blocks later treatment uploads up to 7 days | up to 7 days blocked | silent divergence |
| xDrip4iOS 7.1.1 | v1 PUT by `_id`, per item | low to moderate | retried per item, forever | retries forever | converges (it reconciles deletions when importing) |
| website report editor | v1 PUT | stale page only | `console.info` | edit lost silently | "saved", gone on reload |
| tconnectsync | v1 PUT /profile | race only | raises | exception | no change |

## 5. What the evidence shows

**On API v1, acknowledge-not-applied breaks fewer clients than a refusal.**
- Every surveyed v1 editor treats a 2xx as done and a 4xx as retry-later, and none reads the reply body.
- A refusal therefore creates retry loops. In Loop and xDrip+ those loops block other uploads.
- Acknowledging creates the same silent divergence that a website hard delete already causes.
- On v1 PUT the server cannot tell an edit from a re-send: xDrip+ uses PUT for both. Refusing "edits" would
  also refuse its retries, unless the body is compared with the stored record.

**On API v3, the 410 is the documented contract.** AndroidAPS relies on it, so keeping it breaks nothing new.

**Not measured:**
- a v1 PUT by `_id` after a soft delete;
- a v3 PATCH 410;
- a socket `dbUpdate` carrying `isValid: true` on a deleted record.
