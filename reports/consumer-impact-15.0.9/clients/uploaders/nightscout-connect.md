# nightscout-connect — Nightscout API use (both directions)

All findings are **read-derived** from source at the ref below. Nothing was run.

- Repo: `externals/nightscout-connect`, remote `official` (= github nightscout/nightscout-connect)
- Ref analysed: `official/dev` **977da8a** (2026-09-23, "Merge pull request #79 … profile-sync-bounded-update").
  Tag `v0.1.0-dev.3` resolves to exactly 977da8a, so this is the version the candidate pins
  (cgm-remote-monitor `origin/dev` ddd9b600 `package.json:140` `"nightscout-connect": "0.1.0-dev.3"`).
  `package.json:3` on the branch says `0.1.0`; `scripts/release-version.js` sets the prerelease
  version at publish time, so the difference is expected, not a mismatch.
- **Corpus-file mismatch (reported, not worked around):** `client-corpus.txt` lists this repo as
  `origin/main b394411 2026-07-07 behind=0`. `official/main` is b394411; `official/dev` is 72
  commits past it. The brief's instruction (analyse `official/dev`) was followed.
- Local checkout: HEAD 649a7de, dirty=0 (working tree not read).

## How it reaches Nightscout (positive controls)

The connector has two Nightscout-facing roles and two sink implementations:

| role | code | how it talks | positive control |
|---|---|---|---|
| **reader of a remote Nightscout** ("nightscout" source) | `lib/sources/nightscout.js` | axios HTTP, v1 + v2 authorization | `official/dev lib/sources/nightscout.js:248` (`/api/v1/entries.json`) |
| **writer into the host Nightscout, in-process** (what cgm-remote-monitor runs: `index.js:71-72` selects output `internal`) | `lib/outputs/internal.js` | direct calls to `ctx.entries/treatments/devicestatus/profile.create/list/remove/save` — **no HTTP, no query-string parsing, no `count` middleware** | `official/dev lib/outputs/internal.js:159-162` |
| writer into a Nightscout over HTTP (standalone `forever` command only) | `lib/outputs/nightscout.js` | axios HTTP v1, `API-SECRET` header; nested params via `qs.stringify` where a `paramsSerializer` is given | `official/dev lib/outputs/nightscout.js:63` (`POST /api/v1/entries.json`), selected at `commands/forever.js:50` |

Consequence for the join: for sites running the candidate with `CONNECT_SOURCE=…`, the **sink
side never passes through `lib/api/index.js` `validateCount` or the v1 query-string operator
allowlist**; it goes through the storage modules (`lib/server/{entries,treatments,devicestatus,profile}.js`)
directly. The **source side** does pass through the remote site's HTTP API, and that remote site
may be 15.0.8 or 15.0.9.

Patterns searched (all with `git grep -n <pat> official/dev -- lib index.js commands`):
`api/v1`, `api/v2`, `api/v3`, `count`, `find`, `\$exists`, `\$in`, `\$gt`, `\$gte`, `\$lt`,
`\$regex`, `\$expr`, `pipeline`, `_id`, `identifier`, `uuid`, `socket`, `/count/`, `/times/`,
`/slice/`, `echo`, `properties`, `ddata`, `verifyauth`, `authorization`, `API-SECRET`,
`Authorization`, `token`, `food`, `quickpick`, `notifications`, `paramsSerializer`,
`sourceMaxCount|SOURCE_MAX|maxCount`.

## Surface table

| S-id | what the client does | anchor (repo@sha path:line) | patterns searched |
|---|---|---|---|
| S1 source | Every source read sends `count=sourceMaxCount` (default **1000**) for entries, treatments, devicestatus and profiles; profile "newest" and "in effect before window" reads send `count=1`. `sourceMaxCount = opts.sourceMaxCount \|\| 1000`, from `CONNECT_SOURCE_MAX_COUNT`. In cgm-remote-monitor the value arrives through `env.extendedSettings`, which turns any numeric-looking value into a Number (`sourceMaxCount` is **not** in the candidate's string-settings list, cgm-remote-monitor ddd9b600 `lib/server/env.js:311-334`). So `0` → Number 0 → falls back to 1000 (never sends 0); `2.5`/`-5` → sent as `count=2.5`/`count=-5` → **400 "Bad count" from a 15.0.9 source**; a non-numeric string is sent verbatim → 400. Default and any positive integer are unaffected. All GET. | nightscout-connect@977da8a `lib/sources/nightscout.js:46`, `:60`, `:88`, `:94-95`, `:100-101`, `:120`, `:325` | `count`, `sourceMaxCount`, `SOURCE_MAX` |
| S1 sink (internal, the candidate path) | In-process `list` calls with literal counts: `1` (sensor start, devicestatus bookmark), `1000` (stored profiles, `ctx.profile.list(cb, 1000)`), `10` (profile by `_id`), `5000` (Glooko pump-state reconcile), `100` (Glooko checkpoint, legacy lookup). None is 0, negative or fractional. No `count` on removes. | `lib/outputs/internal.js:62`, `:77`, `:123`, `:148`; `lib/outputs/glooko-pump-state.js:14`; `lib/outputs/glooko-checkpoint.js:21`, `:34`; `lib/outputs/glooko-legacy.js:22`, `:28` | `count` |
| S1 sink (HTTP, standalone only) | Same literals over HTTP GET: `count=1` ×4 at gap detection, `count=500` (45-day guid seed), `count=1000` (profiles), `count=10`, `count=1`. DELETEs (`treatments.json`, `devicestatus.json`) carry **no** `count`, so the candidate's DELETE count rule does not apply. | `lib/outputs/nightscout.js:317-335`, `:214`, `:187`, `:94`, `:132`, `:145`, `:294`, `:299` | `count`, `http.delete` |
| S2 source | `find[dateString][$gt]=<ISO>` (entries), `find[created_at][$gt]=<ISO>` (treatments, devicestatus), profiles: `find[created_at][$gt]=<ISO>&find[startDate][$gte]=1970-01-01T00:00:00.000Z`, or `find[startDate][$gte]=<ISO>` / `find[startDate][$lt]=<ISO>`. All operators are on the allowlist; all values are ISO strings on string fields (none of `dateString`, `created_at`, `startDate` is in the candidate's coercion map, ddd9b600 `lib/server/query-coercion.json` — checked: only `date/mills/srvModified` and numeric treatment/entry fields are typed). Uses `/api/v1/profiles.json` (the filterable profile route) and falls back to `/api/v1/profile.json` on 404. No `$exists`, `$regex`, `$expr`, `pipeline`. | `lib/sources/nightscout.js:60`, `:94`, `:100-101`, `:116-120` | `find`, `\$` |
| S2 sink | Internal/HTTP finds: `enteredBy`+`eventType` equality; `device` equality; `created_at` `$gte`/`$lt` ISO strings; `identifier: {$in: [...]}` and `glookoGuid: {$in: [...]}`; `_id: {$in: [...]}`; **`identifier: {$exists: false}` + `glookoGuid: {$exists: true}`** (Glooko legacy-import detection); dot-notation keys `glookoPumpState.accountKey`, `glookoSyncState.owner`. In-process the `$exists` operands are JS booleans. Over HTTP (standalone) `qs.stringify` sends them as the words `false`/`true`, which **15.0.8 reads inverted for `false`** and 15.0.9 reads correctly (bf/coercion). | `lib/outputs/glooko-legacy.js:14-18`, `:28`; `lib/outputs/glooko-pump-state.js:8-13`, `:25`; `lib/outputs/glooko-checkpoint.js:7-11`, `:51`; `lib/outputs/internal.js:123`, `:137-146`; `lib/outputs/nightscout.js:93-95`, `:131-147`, `:336` | `\$exists`, `\$in`, `\$gte`, `\$lt`, `find` |
| S3 | No numeric-field comparison on either side: every range filter is on `dateString`, `created_at` or `startDate` (strings). Nothing depends on the old number-as-string behaviour. The standalone Glooko legacy path's `$exists=false` is the only operand whose meaning flips (see S2). | as S2 | `\$gt`, `\$gte`, `\$lt`, `\$lte` on `sgv|date|mills|insulin|carbs|duration` — none found |
| S4 | Source calls `GET /api/v1/verifyauth` with no credentials and treats `status==200 && message.canRead` as "already readable". The candidate's verifyauth response shape is unchanged since 15.0.8 (cgm-remote-monitor ef3404fd `lib/api/verifyauth.js:9-31`, no diff vs 92d08342). No `/count`, `/times`, `/slice`, `/echo`, `/api/v2/properties`, `/api/v2/ddata`, `/status`. | `lib/sources/nightscout.js:182-205` | `verifyauth`, `/count/`, `/times/`, `/slice/`, `echo`, `properties`, `ddata`, `status.json` |
| S5 | **Source:** with `CONNECT_SOURCE_API_SECRET` it sends `API-SECRET: sha1(secret)` to `GET /api/v2/authorization/subjects`, looks for a subject named `nightscout-connect-reader`, and uses its **`accessToken` from the list response**. If absent it `POST`s `{name, roles: ['readable'], notes}` — exactly the fields the candidate keeps (`name, roles, notes, created_at`; ef3404fd `lib/authorization/storage.js:53`) — then re-GETs the list. The candidate still serves `accessToken` in `GET /subjects` (derived, not stored; ef3404fd `lib/authorization/endpoints.js:37-45`). It then exchanges the token at `GET /api/v2/authorization/request/<token>` and sends `Authorization: Bearer <jwt>`; the response shape (`token, sub, permissionGroups, iat, exp`) is unchanged (ef3404fd `lib/authorization/index.js:284-310`). A reused role-less subject → warn once; 401 on data read with a reused subject → warn once. A `token=` in the source URL is used directly. **Sink (HTTP):** `API-SECRET: sha1(secret)` on every call. **Sink (internal):** no auth. No X-Forwarded-For. | `lib/sources/nightscout.js:29-30`, `:146-179`, `:184`, `:208-225`, `:47-53`, `:254`; `lib/outputs/nightscout.js:30`, `:62` | `API-SECRET`, `Authorization`, `Bearer`, `authorization/subjects`, `authorization/request`, `token`, `X-Forwarded` |
| S6 | None found. | — | `socket`, `io(`, `authorize`, `dbAdd`, `loadRetro`, `alarm` |
| S7 | **The source hands every record to the sink unchanged, with the source site's `_id`** (`transformGlucose` returns the arrays as read). So the host receives entries, treatments, devicestatus and profiles carrying 24-hex string `_id`s from another database — the case #8758 / bf-object-id-consistency changes. Per collection on the candidate (6d120fa2): entries → upsert on `sysTime+type` with `_id` only in `$setOnInsert` (on 15.0.8 the sent `_id` was in `$set`, so an entry that matched a stored one with a different `_id` made MongoDB refuse the **ordered** bulk write, which fails the connector's whole persist and repeats every cycle); treatments → `replaceOne` filtered by `_id` plus removal of stale string copies; devicestatus → 24-hex `_id` stored as ObjectId, and a re-send that collides with a stored string copy is refused (duplicate key); profiles → stored as ObjectId, re-send still refused. The connector itself avoids re-sending: devicestatus rows are dropped unless `created_at` is newer than the newest stored (internal `:152-156`, HTTP `:151-159`); profiles are planned by `'id:'+String(_id)` fingerprints so only new ones are created and changed ones replaced (`profile-sync.js:20-66`). Profile replace is guarded by `find[_id]=<hex>` (count 10) and only proceeds if the find returns it — on the candidate that find matches both stored forms, so string-stored copies (from 15.0.8 and earlier) become replaceable; on 15.0.8 it logs `NOT_REPLACED` once. Glooko legacy migration sets `_id` from a stored row so the upsert reuses it. No upper-case ids, no UUID `_id`s generated. | `lib/sources/nightscout.js:258-268`, `:104-112`; `lib/outputs/internal.js:37-42`, `:73-91`, `:133-157`; `lib/outputs/nightscout.js:186-201`; `lib/outputs/profile-sync.js:18-66`; `lib/outputs/glooko-legacy.js:37-42` | `_id`, `identifier`, `uuid`, `toUpperCase` |
| S8 | Treatments are only created (upsert) — no PUT; deletes only for its own Glooko pump-state `Note` treatments, filtered by `eventType`, `glookoSource`, account key, time window and `identifier $in` (≤20). `created_at` passed through from the source as stored there. | `lib/outputs/glooko-pump-state.js:6-28`; `lib/outputs/nightscout.js:290-296`; `lib/outputs/internal.js:164-166` | `put`, `delete`, `remove`, `created_at` |
| S9 | None found. | — | `food`, `quickpick`, `hideafteruse`, `position` |
| S10 | Profile sync: create via `POST /api/v1/profile.json` (HTTP) / `ctx.profile.create` (internal) **with the source `_id`**; replace via `PUT /api/v1/profile.json` / `ctx.profile.save` with the same `_id`, gated on the `find[_id]` check above. Stored-profile read bounded to 1000. Does not create profile-switch treatments. Does not touch `defaultProfile`/`startDate` beyond copying. | `lib/outputs/nightscout.js:172-234`; `lib/outputs/internal.js:43-112` | `profile`, `startDate`, `defaultProfile`, `Profile Switch` |
| S11 | Writes devicestatus as produced by each source (Glooko IOB, LibreLinkUp device, Nightscout copies). Does not read Nightscout-computed COB/IOB (no v2 properties / pebble). | `lib/outputs/internal.js:133-161` | `iob`, `cob`, `properties`, `pebble` |
| S12 | Source: axios default param serialisation of nested objects (`find[field][$op]=value`), no arrays. Sink HTTP: `qs.stringify` (indices form `find[x][$in][0]=…`); the code deliberately chunks `$in` arrays at **20** "below the v1 parser's array-length threshold" (`glooko-legacy.js:25-27`, `glooko-pump-state.js:23-26`). **Exception:** `glooko-checkpoint.js:48-51` sends `_id: {$in: obsolete}` unchunked, where `obsolete` can hold up to 99 ids (it throws at ≥100). Over HTTP (standalone) more than 21 ids exceeds qs `arrayLimit` 20 and the array becomes an object; in-process there is no qs step. Normal steady state is 0–1 ids. Maximum visible array: 99 (checkpoint), 20 (others). Dot-notation keys in `find`. | `lib/sources/nightscout.js:60-62`; `lib/outputs/nightscout.js:39-40`, `:46`, `:188`, `:288`; `lib/outputs/glooko-checkpoint.js:48-51` | `paramsSerializer`, `\$in`, `slice(` |
| S13 | None found (no Nightscout v3 use; `/api/v3/users/sign_in` in `lib/sources/glooko/index.js:49` is Glooko's own API). | — | `api/v3`, `limit`, `lastModified`, `sort\$desc` |
| S14 | None found. | — | `notifications`, `ack`, `loop` push |
| S15 | Any source-read error (incl. 400/401) fails the frame; the frame retries up to `maxRetries: 3` at 10 s, then the cycle backs off (2.5 min × 2^n, bounded, honours `Retry-After` ≤ 15 min). Any sink write error (`recordingError` / internal `safePersist`) also fails the frame. **The bookmark only moves after a successful persist**, so a persistent error **stalls** (the same window is re-read and re-sent every cycle), it does not drop or mark-as-sent. A **200 with an empty array** from the source is treated as "no new data" (no error). In the HTTP sink, a failed gap detection is caught and logged (`nightscout.js:349-351`), leaving no bookmark → the source falls back to a 2-day window. | `lib/machines/fetch.js:226-240`, `:291-310`, `:330-345`; `lib/sources/nightscout.js:297-310`; `lib/machines/request-error.js:5-20`; `lib/outputs/nightscout.js:50-56`, `:347-351`; `lib/outputs/internal.js:207-218` | `onError`, `maxRetries`, `catch`, `recordingError` |

## Worth cross-checking against the change list

1. **S7 entries (#8758) — likely a fix for a stall.** Question: on 15.0.8/dev, does a copied entry
   whose `sysTime+type` matches a stored entry with a *different* `_id` make the ordered
   `bulkWrite` fail (immutable `_id` in `$set`), so every connector persist fails until the
   conflicting reading leaves the 2-day/bookmark window? If yes, the candidate removes a
   "data stops arriving" failure for sites whose host and source both receive the same CGM feed.
2. **S7 devicestatus (#8758 guard).** Question: can the in-process sink ever send a devicestatus
   whose `_id` is already stored (the `created_at > newest stored` filter says no in steady
   state)? If it can, `insertMany({ordered:true})` refuses the batch and the connector stalls
   rather than dropping — same on dev and candidate, but confirm the guard does not widen it.
3. **S10 profile replace.** Question: with #8758, `find[_id]=<hex>` on `ctx.profile.list_query`
   matches a string-stored copy, so the connector now PUTs/saves it; confirm `ctx.profile.save`
   then leaves one profile (the PR body says yes) — otherwise the profile sync the release notes
   advertise would create duplicates on upgraded sites.
4. **S1 source count** — only a misconfigured `CONNECT_SOURCE_MAX_COUNT` (fraction, negative,
   non-numeric) reaches the 400. Low likelihood; the symptom would be "copying stops" with a
   retry loop, and the connector logs only "Polling frame failed".
5. **S2/S12 standalone HTTP sink only** (not the candidate's in-process path): `$exists=false`
   flips meaning between 15.0.8 and 15.0.9 for Glooko legacy detection; checkpoint `_id $in` is
   unchunked. Relevant to anyone running the standalone `forever` command against a Nightscout.
