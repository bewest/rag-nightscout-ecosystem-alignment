# minimed-connect-to-nightscout — Nightscout API use

All findings are **read-derived**. Nothing was run.

- Repo: `externals/minimed-connect-to-nightscout` (package `version` 1.5.8 — the version the
  candidate depends on, cgm-remote-monitor ddd9b600 `package.json:132` `^1.5.8`)
- Ref analysed: `origin/master` **57bb042** (2026-03-03). `origin/dev` 1fbd3ea (2023-06-07) is older.
- Local checkout: HEAD 57bb042, behind=0, dirty=0.

## How it reaches Nightscout

**Embedded** (cgm-remote-monitor `MMCONNECT_*`, being retired): cgm-remote-monitor uses only this
package's CareLink client, filter and transform, and writes through `entries.create` /
`devicestatus.create` in-process (ddd9b600 `lib/plugins/mmconnect.js:48-91`). **Standalone**
(`run.js`): HTTP POST via `nightscout.js`.

## Positive controls

- `minimed-connect-to-nightscout@57bb042 run.js:50-51` — `/api/v1/entries.json`, `/api/v1/devicestatus.json`
- `minimed-connect-to-nightscout@57bb042 nightscout.js:9-29` — POST with `api-secret`

Patterns searched (`git grep -n -E <pat> origin/master -- '*.js' ':!test'`): `api/v1`, `api/v2`,
`api/v3`, `count`, `find\[`, `\$`, `api-secret`, `token`, `_id`, `socket`, `treatments`, `profile`,
`statusCode`. (`carelink.js:84` "Request count" is CareLink, not Nightscout.)

| S-id | what the client does | anchor (repo@sha path:line) | patterns searched |
|---|---|---|---|
| S1 | None found toward Nightscout (no reads). | — | `count` |
| S2 | None found. | — | `find`, `\$` |
| S3 | None found. | — | `\$gt` |
| S4 | None found. | — | `status`, `verifyauth`, `/count/` |
| S5 | `api-secret: sha1(secret)` header. No token/JWT/subjects. | `nightscout.js:15-18` | `api-secret`, `token` |
| S6 | None found. | — | `socket` |
| S7 | No `_id` in entries or devicestatus. De-duplication is a client-side, in-memory recency filter (`date` for SGVs, `created_at` for devicestatus); the package comment in the embedded path notes devicestatus "doesn't upsert". | `filter.js:5-22`; `run.js:55-61`; `transform.js:87-130` | `_id`, `identifier` |
| S8 | None found. | — | `treatments` |
| S9 | None found. | — | `food` |
| S10 | None found. | — | `profile` |
| S11 | Writes devicestatus with `device: 'connect-<family>'`, `uploader`, `pump` (incl. `pump.iob.bolusiob` from `activeInsulin.amount`), and a `connect` block. Does not read Nightscout COB/IOB. | `transform.js:87-130` | `iob`, `devicestatus` |
| S12 | None (POST bodies only). | — | `\[\]` |
| S13 | None found. | — | `api/v3` |
| S14 | None found. | — | `notifications` |
| S15 | Non-200 → error logged, loop continues ("Continue gathering data from CareLink even if Nightscout can't be reached"). The recency filter has **already advanced** before the upload, so a refused batch is **dropped** (not retried). | `nightscout.js:20-28`; `run.js:63-76`; `filter.js:10-20` | `statusCode`, `callback(err` |

## Worth cross-checking

Nothing in the candidate's changed surface is sent. None.
