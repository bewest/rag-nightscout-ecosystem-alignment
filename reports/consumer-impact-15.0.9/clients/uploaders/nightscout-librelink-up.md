# nightscout-librelink-up — Nightscout API use

All findings are **read-derived**. Nothing was run.

- Repo: `externals/nightscout-librelink-up` (package `version` 3.3.0)
- Ref analysed: `origin/main` **bff2317** (2026-03-04). Only branch on the remote.
- Local checkout: HEAD bff2317, behind=0, dirty=0.

## Positive controls

- `nightscout-librelink-up@bff2317 src/nightscout/apiv1.ts:24` — `GET /api/v1/entries?count=1`
- `nightscout-librelink-up@bff2317 src/nightscout/apiv3.ts:61` — `GET /api/v3/entries?limit=1&sort$desc=date`

Patterns searched (`git grep -n -E <pat> origin/main -- src`): `api/v1`, `api/v2`, `api/v3`, `count`,
`limit`, `find`, `\$`, `api-secret`, `Authorization`, `Bearer`, `authorization/request`, `_id`,
`identifier`, `socket`, `status`, `treatments`, `devicestatus`, `profile`, `food`, `catch`.
The Nightscout client is selected by `NIGHTSCOUT_API_V3` (`src/config.ts:66`, `src/index.ts:291-293`).

| S-id | what the client does | anchor (repo@sha path:line) | patterns searched |
|---|---|---|---|
| S1 | v1: literal `count=1` on `GET /api/v1/entries` (newest entry, used as a watermark). No computed count, no DELETE. | `src/nightscout/apiv1.ts:24` | `count` |
| S2 | None found (no `find`). | — | `find`, `\$` |
| S3 | None on the server side. Client side it compares each LibreLinkUp reading's `Date` with the newest Nightscout entry's numeric `date` (`measurementDate > lastEntry.date`). | `src/index.ts:300-320` | `\$gt`, `\$gte`, `lastEntry.date` |
| S4 | None found. | — | `/count/`, `/times/`, `/slice/`, `echo`, `properties`, `ddata`, `status`, `verifyauth` |
| S5 | v1: `api-secret: <NIGHTSCOUT_API_TOKEN>` sent **verbatim** (not hashed by the client — the operator must supply the SHA-1 or it fails with 401). v3: exchanges `NIGHTSCOUT_API_TOKEN` at `GET /api/v2/authorization/request/<token>` **before every request** (no JWT caching) and sends `Authorization: Bearer <jwt>`; a failed exchange is logged and an empty bearer is sent (`addBearerJwtToken` then throws "No jwtToken found"). No subjects/roles. No X-Forwarded-For. No timeout configured on axios, so a delayed auth reply delays the cron run. | `src/nightscout/apiv1.ts:15-19`; `src/nightscout/apiv3.ts:28-56`, `:59-68`, `:82-106`; `src/config.ts:58` | `api-secret`, `Authorization`, `Bearer`, `authorization/request`, `timeout` |
| S6 | None found. | — | `socket`, `io(` |
| S7 | Does not send `_id`. Entries carry `type:'sgv', sgv, direction, device, date, dateString` (v1) or `type, sgv, direction, device, date, app` (v3). Deduplication is client-side (only readings newer than the newest stored entry are sent) plus the server's entries upsert. No PUT/DELETE by id. | `src/nightscout/apiv1.ts:39-46`; `src/nightscout/apiv3.ts:89-96`; `src/index.ts:296-322` | `_id`, `identifier`, `uuid` |
| S8 | None found (no treatments). | — | `treatments` |
| S9 | None found. | — | `food` |
| S10 | None found. | — | `profile` |
| S11 | None found (no devicestatus). | — | `devicestatus`, `iob`, `cob` |
| S12 | Literal query strings; no arrays; `sort$desc` (v3). | as S1/S13 | `\[\]`, `\$in` |
| S13 | v3 `GET /api/v3/entries?limit=1&sort$desc=date` (limit 1 — valid under the v3 rule); v3 `POST /api/v3/entries`, one request per reading, **requires status 201** — any other status (including a 200 deduplication answer) throws. v3 read with an empty `result` throws "Last entry not found" (so on a site with no entries the v3 client never uploads). | `src/nightscout/apiv3.ts:58-79`, `:81-117` | `api/v3`, `limit`, `sort`, `201` |
| S14 | None found. | — | `notifications`, `ack` |
| S15 | A global axios response interceptor **returns** (does not reject) errors, so a 4xx/5xx arrives as a non-200 object and the client's own status check throws. Upload failure is caught and logged ("Upload to NightScout failed"); nothing is persisted locally, and the next cron run re-reads the newest Nightscout entry, so missed readings are retried as long as LibreLinkUp still has them in its graph window (~12 h). An error from the watermark read (v1 `lastEntry`) propagates out of `createFormattedMeasurements` — the run is skipped. An empty array from v1 `lastEntry` means "no watermark": all graph readings are sent. | `src/index.ts:64-77`, `:296-345`; `src/nightscout/apiv1.ts:27-34`, `:50-52` | `interceptors`, `catch`, `status` |

## Worth cross-checking against the change list

Nothing this client sends is in the candidate's changed surface on read (count=1, no find, no
`_id`, v3 limit=1). Question for the join, low priority: does anything in the candidate change
the v3 `POST /api/v3/entries` status code for a re-sent reading (201 vs 200)? This client treats
anything but 201 as a failure, but the next run recovers.
