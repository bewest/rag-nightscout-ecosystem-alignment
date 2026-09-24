# tconnectsync — Nightscout API use

All findings are **read-derived**. Nothing was run. The local working tree is dirty (31 files)
and was **not** read; everything below is from `git show`/`git grep` on the ref.

- Repo: `externals/tconnectsync`, remote `origin` = github jwoglom/tconnectsync
- Ref analysed: `origin/master` **7c4b2f4** (2026-07-21). Only branch on the remote.
- Local checkout: HEAD 7f88d88, 10 behind, dirty=31.

## Positive controls

- `tconnectsync@7c4b2f4 tconnectsync/nightscout.py:77` — `GET api/v1/treatments?count=1&find[enteredBy]=…`
- `tconnectsync@7c4b2f4 tconnectsync/nightscout.py:48` — `POST api/v1/<entity>`

Patterns searched (`git grep -n -E <pat> origin/master -- tconnectsync`): `api/v1`, `api/v2`,
`api/v3`, `count=`, `find\[`, `\$gte`, `\$lte`, `\$exists`, `api-secret`, `api_secret`, `token`,
`_id`, `delete_entry`, `put_entry`, `upload_entry`, `socket`, `status.json`, `profile/current`,
`food`, `notifications`. All Nightscout I/O is in `tconnectsync/nightscout.py`; callers are in
`tconnectsync/sync/tandemsource/*.py`, `check.py`.

| S-id | what the client does | anchor (repo@sha path:line) | patterns searched |
|---|---|---|---|
| S1 | Literal `count=1` on `GET api/v1/treatments` (last uploaded of an eventType) and `GET api/v1/entries.json` (last uploaded BG). `api/v1/activity` and `api/v1/devicestatus` reads send **no** count (server default). No computed count, no DELETE with count. | `tconnectsync/nightscout.py:77`, `:97`, `:117`, `:137` | `count=`, `count` |
| S2 | `find[enteredBy]=Pump (tconnectsync)` (URL-quoted), `find[eventType]=<type>`, `find[device]=Pump (tconnectsync)` (entries, devicestatus), `find[activityType]=<type>`, and `find[created_at\|dateString][$gte\|$lte]=<ISO with offset>` — values URL-encoded with `quote(…, safe='')` so the `+` of an offset survives. All on the allowlist; no `$exists`, `$in`, `$regex`, `$expr`. | `tconnectsync/nightscout.py:22-35`, `:75-77`, `:95-97`, `:115-117`, `:135-137`; value `tconnectsync/parser/nightscout.py:6` | `find\[`, `\$` |
| S3 | Date-only bounds (`created_at`, `dateString` strings; `created_at` is the treatments/devicestatus/activity `dateField`, which the server rewrites to ISO UTC). No numeric-field comparisons. Nothing depends on the old number-as-string behaviour. | `tconnectsync/nightscout.py:22-35` | `\$gte`, `\$lte` on numeric fields — none |
| S4 | `GET api/v1/status.json` (the `check` command). `GET api/v1/profile/current`. | `tconnectsync/nightscout.py:157-163`, `:169-177`; `tconnectsync/check.py:154` | `status.json`, `verifyauth`, `/count/`, `properties`, `profile/current` |
| S5 | `api-secret: sha1(secret)` header on every call **and**, on POST/PUT/DELETE/profile-current, the **plaintext** secret as a `?api_secret=` query parameter (Nightscout does not read `api_secret`; the header authenticates). No token/JWT, no subjects. No X-Forwarded-For. No request timeout set. | `tconnectsync/nightscout.py:48-52`, `:57-61`, `:66-70`, `:78`, `:170-174` | `api-secret`, `api_secret`, `token`, `Authorization`, `timeout` |
| S6 | None found. | — | `socket` |
| S7 | Does not send `_id` on POST (treatments/entries/devicestatus/activity carry `pump_event_id` as their own dedup key; the client dedups against the last uploaded record's time). **Reads `_id` back** from `last_uploaded_entry` and `DELETE api/v1/treatments/<_id>` to replace an un-ended Sleep/Exercise activity treatment. **Profile replace mode** (`NIGHTSCOUT_PROFILE_UPLOAD_MODE=replace`) sends `PUT api/v1/profile` with the document from `profile/current`, **including its `_id`**; add mode deletes `_id` and POSTs. | `tconnectsync/sync/tandemsource/process_user_mode.py:223-245`; `tconnectsync/sync/tandemsource/update_profiles.py:55-83`, `:96-116`, `:209-217`; `tconnectsync/secret.py:83` | `_id`, `pump_event_id`, `uuid` |
| S8 | Treatments: POST; "update" of Sleep/Exercise is **delete by `_id` then POST** a new one with the original `created_at`. `created_at` is Arrow ISO with offset. | `tconnectsync/sync/tandemsource/process_user_mode.py:223-260` | `put_entry`, `delete_entry`, `created_at` |
| S9 | None found. | — | `food` |
| S10 | See S7: add mode POSTs a whole profile object (no `_id`, fresh `startDate`/`created_at`); replace mode PUTs with the stored `_id`. No profile-switch treatments. | `tconnectsync/sync/tandemsource/update_profiles.py:67-83`, `:209-217` | `profile`, `startDate`, `defaultProfile` |
| S11 | Writes IOB as a treatment-shaped record (`NightscoutEntry.iob`) and pump battery devicestatus (`batteryVoltage`, `batteryPercent`). Does not read Nightscout COB/IOB. | `tconnectsync/parser/nightscout.py:76-82`; `tconnectsync/sync/tandemsource/process_device_status.py:65-84` | `iob`, `devicestatus`, `properties` |
| S12 | Hand-built query strings, bracket notation, no arrays; extra `&ts=<float epoch>` cache-buster on reads (unknown parameter, ignored by Nightscout). | `tconnectsync/nightscout.py:77`, `:97`, `:117`, `:137` | `\[\]`, `ts=` |
| S13 | None found. | — | `api/v3` |
| S14 | None found. | — | `notifications` |
| S15 | Every non-200 raises `ApiException`; the uncaught exception ends the sync run (`tconnectsync/__init__.py:36` logs it); the next scheduled run re-reads the watermarks and retries, so a persistent 400 would **stall** that sync run each time rather than drop data. An empty array from a watermark read means "nothing uploaded yet" → uploads the whole time range (dedup by the server upsert only). | `tconnectsync/nightscout.py:53-54`, `:62-63`, `:71-72`, `:80-86`, `:100-106`; `tconnectsync/__init__.py:36` | `ApiException`, `except` |

## Worth cross-checking against the change list

1. **S7/S10 profile replace (#8758).** Question: `PUT /api/v1/profile` with the `_id` read from
   `profile/current` — on a site whose current profile is stored with a **string** `_id` (copied
   by the connector, restored from an export), 15.0.8 upserts the ObjectId form and leaves a second
   copy; the candidate replaces in place. Confirm, since this client would have been adding copies
   on such sites. Only for `replace` mode (default is `add`).
2. **S7 delete by `_id`** — benefits from either-form lookup; confirm no regression for ObjectId-stored treatments.
