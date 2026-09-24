# oref0 — Nightscout API use

All findings are **read-derived** from source. Nothing was run.

- Repo: `externals/oref0`, remote `origin` (openaps/oref0)
- Ref analysed: `origin/master` **88cf032a** (2022-06-18). Also checked `origin/dev` **d219baf9**
  (2026-03-09), which is what the local checkout's HEAD is. `git diff origin/master origin/dev`
  touches 11 files under `bin/`+`lib/`; **none of the hit files below** (`bin/nightscout.sh`,
  `bin/ns-get.sh`, `bin/get_profile.py`, `bin/ns-dedupe-treatments.sh`,
  `bin/ns-delete-old-devicestatus.sh`, `bin/oref0-ns-loop.sh`, `bin/oref0-autotune*.{sh,py}`,
  `bin/oref0-backtest.sh`, `bin/oref0-upload-profile.js`) differs. On dev,
  `bin/ns-upload.sh`/`ns-upload-entries.sh` gain `--compressed`, `oref0-get-ns-entries.js` gains a
  `User-Agent: openaps` header and gzip, and `oref0_nightscout_check.py` reads
  `permissionGroups` defensively. Those do not change any row.
- Local checkout staleness: HEAD d219baf9 (= origin/dev), master has 2 commits not in HEAD, dirty=0.

## Positive controls

- `oref0@88cf032a bin/ns-get.sh:34` — builds `$NIGHTSCOUT_HOST/api/v1/${REPORT}?${QUERY}` (every
  shell read goes through here).
- `oref0@88cf032a bin/oref0-get-ns-entries.js:183` — `'/api/v1/entries/sgv.json?count=' + records`.
- `oref0@88cf032a bin/ns-upload.sh:13` — `REST_ENDPOINT="${NIGHTSCOUT_HOST}/api/v1/${TYPE}"` (every POST).

Patterns searched (`git grep -n -E <pat> origin/master -- bin lib`): `api/v1`, `api/v2`, `api/v3`,
`count=`, `find\[`, `find%5B`, `\$exists`, `%24`, `\$regex`, `\$in`, `verifyauth`, `api-secret`,
`API-SECRET`, `token=`, `authorization`, `_id`, `NSCLIENT_ID`, `uuid`, `socket`, `/count/`,
`/times/`, `/slice/`, `echo`, `properties`, `ddata`, `status.json`, `food`, `notifications`,
`api/v3`, `DELETE`, `-X PUT`, `profile`. `lib/` holds no HTTP code of its own; its openaps report
definitions (`lib/oref0-setup/report.json`, `cgm-loop.json`, `mdt-cgm.json`, `xdrip-cgm.json`)
invoke the `ns` device, i.e. `bin/nightscout.sh` subcommands, which are mapped below.
`bin/monitor-xdrip.sh:12` and `lib/oref0-setup/device.json:127` call `localhost:5000/api/v1/entries?count=288`, which is
xDrip's local web service, not Nightscout.

## Surface table

| S-id | what the client does | anchor (repo@sha path:line) | patterns searched |
|---|---|---|---|
| S1 | **Malformed count on every loop run.** `nightscout latest-openaps-treatment $NIGHTSCOUT_HOST $API_SECRET` (called from `oref0-ns-loop.sh:242` on every `upload` step) runs `ns-get treatments.json'?find[enteredBy]=/openaps:\/\//&count=1' $*`. `ns-get.sh` takes `$1` as REPORT (already containing a query), `$2` as host and **`$3` (the API secret) as QUERY**, and builds `…/api/v1/${REPORT}'?'${QUERY}`, i.e. `…&count=1?<secret>`; with token auth `…&count=1?token=…&token=…`. So the server receives `count` = `1?…`. **15.0.8** reads it with `parseInt` → 1 (cgm-remote-monitor 92d08342 `lib/server/treatments.js:243-244`). **The candidate refuses it**: `validateCount` accepts only `/^\s*\d+\s*$/` → **HTTP 400 "Bad count"** (ddd9b600 `lib/api/index.js:71-94`, `lib/server/count.js:21-33`). (The same construction also puts the hashed secret in the URL; noted as mechanism only.) | `bin/nightscout.sh:164-165`; `bin/ns-get.sh:7-9`, `:27-36`, `:68-70`; `bin/oref0-ns-loop.sh:241-243` | `count=`, `latest-openaps-treatment`, `QUERY` |
| S1 | **`get_profile.py` with a token:** `…/treatments.json?find[eventType][$eq]=Profile Switch&count=1` then `p_url + "?" + token` → `count=1?token=…`. 15.0.8: count 1 and the token never reaches the server as `token` (so it only worked on a site readable without auth). Candidate: **400 "Bad count"**; the script then indexes the error object (`p_switch[0]`) and crashes. `get_profile.py` is a manual tool, not in the loop. | `bin/get_profile.py:61-70` | `count=`, `token` |
| S1 | Other counts, all plain positive integers: `10` (defaults for `oref0_glucose*` and help text), `1` (`latest-treatment-time`), `300` (`lsgaps`), `1000` (`oref0_glucose_since`, overridable by `$3`), `100` (devicestatus for pushover snooze), `1500` (autotune, backtest), `9999999` (backtest; < 2^53), `$(($count-1))` in dedupe (only run when `count > 1`, so ≥1), **`100000` on a DELETE** (`ns-delete-old-devicestatus.sh`; valid, so the candidate carries it out and still deletes everything matched). **Computed:** `oref0-get-ns-entries.js` sends `count = 12 * hours` when `hours > 0`, else 1000. The loop passes `24` and `1` → 288 and 12. A fractional `hours` given by hand (e.g. `0.1` → `1.2`) would now get 400; none is passed by any script. | `bin/nightscout.sh:52`, `:97`, `:203`, `:245`, `:276`, `:283`, `:290-291`; `bin/oref0-ns-loop.sh:43`, `:65`, `:69`; `bin/oref0-pushover.sh:83`; `bin/oref0-autotune.sh:206`; `bin/oref0-autotune.py:150`; `bin/oref0-backtest.sh:226`, `:245`; `bin/ns-dedupe-treatments.sh:21-23`; `bin/ns-delete-old-devicestatus.sh:36-37`; `bin/oref0-get-ns-entries.js:58-63`, `:183` | `count=`, `records`, `hours` |
| S2 | `find[enteredBy]=/openaps:\/\//` (a regex literal as an equality value — the server's treatments walker turns `enteredBy` into a regex; the candidate keeps that walker, per bf-coercion). `find[eventType]=Temporary+Target`; `find[eventType][$eq]=Profile Switch`; `find[type][$eq]=sgv`; `find[created_at][$gte]=<date -Iminutes -u>`; `find[created_at][$lte]`; `find[created_at]=<exact>` (dedupe); `find[date][$gte]/[$lte]=<epoch ms>`; **`find[carbs][$exists]=true`** (value `true` — unaffected by the `$exists` fix). No `$regex`, `$in`, `$expr`, `pipeline`. | `bin/nightscout.sh:165`, `:240`, `:245`, `:291`, `:297`, `:301`; `bin/get_profile.py:64`; `bin/ns-dedupe-treatments.sh:23`; `bin/ns-delete-old-devicestatus.sh:36`; `bin/oref0-autotune.sh:206`, `:214`; `bin/oref0-backtest.sh:226-245` | `find\[`, `find%5B`, `\$exists`, `%24` |
| S3 | `find[date][$gte]/[$lte]=<epoch ms>` on entries (`date` was already `parseInt`-coerced on 15.0.8 and is `number` in the candidate map, so integer bounds behave the same). `find[created_at]` bounds on treatments/devicestatus are strings (not in the coercion map). No decimal or numeric-treatment-field bounds (no `insulin`, `duration`, `carbs` comparisons). Nothing relies on the old string comparison. Note `date -Iminutes` output carries `+00:00`; in `autotune.sh`/`backtest.sh` it is put in the URL unencoded, so `+` arrives as a space — existing behaviour, not changed by the candidate as far as read. | as S2 | `\$gte`, `\$lte`, `%24gte`, `insulin`, `duration` |
| S4 | `GET /api/v1/status.json` (`preflight`, `get-status`: reads `.status == "ok"`). `GET /api/v1/profile/current` (`oref0-upload-profile.js`). No `/count`, `/times`, `/slice`, `/echo`, v2 properties/ddata, verifyauth. | `bin/nightscout.sh:184-196`; `bin/oref0-upload-profile.js:76-79` | `status.json`, `verifyauth`, `/count/`, `/times/`, `/slice/`, `echo`, `properties`, `ddata`, `profile/current` |
| S5 | `API_SECRET` is either a SHA-1 hex hash sent as `api-secret:`/`API-SECRET:` header, or the literal string `token=<t>` appended to the query. `oref0_nightscout_check.py` exchanges the token at `GET /api/v2/authorization/request/<token>` and reads `permissionGroups[0]` and `exp` (shape unchanged in candidate ef3404fd `lib/authorization/index.js:284-310`). No subject/role creation. No X-Forwarded-For. `curl -m 30` bounds a slow (delayed) auth reply to 30 s. On 401 nothing special: the body is fed to `jq`. | `bin/ns-get.sh:26-36`; `bin/ns-upload.sh:37-52`; `bin/ns-upload-entries.sh:19-25`; `bin/oref0-get-ns-entries.js:171-176`; `bin/oref0_nightscout_check.py:67-85`, `:93-109`; `bin/nightscout.sh:318-327` | `api-secret`, `API-SECRET`, `token=`, `authorization`, `X-Forwarded` |
| S6 | None found. | — | `socket`, `io.connect`, `authorize`, `dbAdd` |
| S7 | Does not send its own `_id`: `oref0-upload-profile.js` explicitly `delete upload_profile._id` before POST; devicestatus/treatments/entries are built from pump/CGM data without `_id`. Reads `_id` back only in `ns-dedupe-treatments.sh`, which then `DELETE /api/v1/treatments/<_id>` for duplicates (the candidate's either-form `_id` lookup makes these deletes find string-stored copies too). Relies on the server upserting treatments by `created_at`+`eventType` when the cull sends history again (see S15). | `bin/oref0-upload-profile.js:243-271`; `bin/ns-dedupe-treatments.sh:20-35` | `_id`, `NSCLIENT_ID`, `uuid`, `DELETE` |
| S8 | Treatments: POST only (`ns-upload treatments.json`), no PUT. Deletes only in the dedupe tool. `created_at` from pump history, zoned ISO. | `bin/oref0-ns-loop.sh:230-239`, `:246-260`; `bin/nightscout.sh:344-349` | `-X PUT`, `DELETE`, `created_at` |
| S9 | None found. | — | `food`, `quickpick` |
| S10 | `oref0-upload-profile.js`: `GET /api/v1/profile/current`, then (if changed) `POST /api/v1/profile` of a whole profile document **without `_id`**, `defaultProfile: 'OpenAPS Autosync'`, fresh `startDate`/`created_at`/`mills`; optional `Profile Switch` treatment POST (`duration: 0`, `profile: 'OpenAPS Autosync'`). `get_profile.py` reads `/api/v1/profile.json` and the latest `Profile Switch`. `oref0-autotune.py` reads `/api/v1/profile.json` unauthenticated. | `bin/oref0-upload-profile.js:76-110`, `:247-360`; `bin/get_profile.py:41-80`; `bin/oref0-autotune.py:94-98` | `profile`, `Profile Switch`, `defaultProfile`, `startDate` |
| S11 | Writes devicestatus via `ns-status.js`: `openaps.iob`, `openaps.suggested`, `openaps.enacted`, `pump.{battery,reservoir,status,clock}`, `uploader`, `mmtune`, `preferences` (with host/serial/tokens redacted). Also writes small `{date, device, snooze}` devicestatus records from pushover. Reads devicestatus back only for `snooze` (jq filters `.date > <epoch s>` client-side). Does not read Nightscout-computed COB/IOB. | `bin/ns-status.js:28-60`, `:96-135`; `bin/oref0-pushover.sh:83-110`; `bin/oref0-ns-loop.sh:42-56` | `openaps`, `iob`, `suggested`, `COB`, `properties`, `pebble` |
| S12 | Bracket notation, sometimes percent-encoded (`find%5Bdate%5D%5B%24gte%5D`). No arrays. **Two malformed shapes:** (a) the `count=1?…` above; (b) `nightscout.sh:245` `latest-treatment-time` passes a QUERY that starts with `?` (`'?find[enteredBy]=…&count=1'`), producing `treatments.json??find…` — the filter key reaches the server as `?find` and is ignored, so it returns the newest treatment of any uploader (existing behaviour; its `count=1` is valid, so no 400). (c) `oref0-autotune.py:139`/`:150` embed literal backslashes (`find\[date\]\[\$gte\]`) and unexecuted backticks in a Python string, so their filters never parse as `find` on any version — broken before and after; `count=1500` in `:150` is still intact. | `bin/nightscout.sh:165`, `:245`; `bin/ns-get.sh:29-34`; `bin/oref0-autotune.py:139`, `:150` | `find\[`, `\\\[`, `\?find`, `%5B` |
| S13 | None found. | — | `api/v3`, `limit=` |
| S14 | None found. | — | `notifications`, `ack` |
| S15 | Uploads use `curl -s` **without `--fail`**, so an HTTP 400/401/500 still exits 0: `ns-upload.sh` logs "Uploaded …" and the ns-loop **deletes the queued devicestatus file** (`rm $file_name`) — a refused devicestatus is dropped, not retried. Reads: the body is piped to `jq`; a 400 JSON object makes `jq .[0]` fail, producing empty output. **For the S1 hit specifically:** `latest_ns_treatment_time` becomes empty (`date -Is -d` with no argument errors), the "in the future" guard is false, and `cull-latest-openaps-treatments … ""` keeps every pump-history treatment with `created_at > ""`, i.e. **the whole 24 h pump history is re-POSTed on every loop** instead of only new treatments. Whether that creates duplicates or overwrites records edited in Nightscout depends on the server's treatment upsert (by `created_at`+`eventType`, `replaceOne`). The loop does not stall and does not surface the error beyond "Latest NS treatment: " printed empty. (This assumes `set -e` is not active in the ns-loop shell: the only common function that sets it, `get_pref_bool` at `bin/oref0-bash-common-functions.sh:366-368`, is not called by `oref0-ns-loop.sh`; if some deployment runs it with `set -e`, the failed substitution would instead abort the upload step — a stall of treatment uploads.) `oref0-get-ns-entries.js` on a non-200 prints "Loading CGM data from Nightscout failed" and emits nothing, so the ns-glucose files are overwritten with empty output. | `bin/ns-upload.sh:40-51`; `bin/oref0-ns-loop.sh:207-215`, `:241-260`; `bin/nightscout.sh:344-349`; `bin/oref0-get-ns-entries.js:195-211` | `curl`, `--fail`, `-f `, `die`, `statusCode` |

## Worth cross-checking against the change list

1. **S1/S15 `count=1?<secret>` — highest.** Question: does the candidate's `validateCount`
   (ddd9b600 `lib/api/index.js:71-94`) run before `/api/v1/treatments` GET and see
   `req.query.count === '1?…'`? If yes, every oref0 rig's `upload_recent_treatments` gets a 400
   from `latest-openaps-treatment`, and the rig re-uploads its whole 24 h of pump-history
   treatments every loop (~5 min). The join must answer: does the candidate's treatments upsert
   (`created_at`+`eventType`, `replaceOne`) keep that idempotent — no duplicates — and does it
   **replace** a treatment the user edited in Nightscout with the rig's version each time? Also
   the extra write volume per rig. This is "wrong or overwritten records", not "data stops".
   The fix on the oref0 side is a quoting change in `nightscout.sh:165`; the server side could
   also accept a leading-digits count (which would re-open what `validateCount` closes).
2. **S1 `get_profile.py` with a token** — manual tool, crashes with 400 on the candidate; on 15.0.8
   it silently ran unauthenticated. Low.
3. **S15 dropped devicestatus on any 400** — nothing in oref0 sends a shape the candidate newly
   refuses on POST (no `_id`, no `count`), so read-derived: no new drops.
