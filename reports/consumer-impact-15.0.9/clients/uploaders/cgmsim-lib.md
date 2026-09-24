# cgmsim-lib — Nightscout API use

All findings are **read-derived**. Nothing was run. This is a library (`@lsandini/cgmsim-lib`
0.10.3); the host application chooses the arguments, so computed values below are bounded only
by what the library itself checks.

- Repo: `externals/cgmsim-lib`
- Ref analysed: `origin/main` **c09f9c0** (2026-05-14). Other remote branches are feature
  branches; not analysed.
- Local checkout: HEAD c09f9c0, behind=0, dirty=0.
- Only `src/` was analysed; `dist/` is a build of it (the prior census lists `dist/` hits at the
  same logical sites).

## Positive controls

- `cgmsim-lib@c09f9c0 src/downloads.ts:48` — `/api/v1/entries/sgv.json?count=${maxCount}`
- `cgmsim-lib@c09f9c0 src/upload.ts:103` — `POST /api/v1/entries/`

Patterns searched (`git grep -n -E <pat> origin/main -- src`, excluding tests): `api/v1`, `api/v2`,
`api/v3`, `count`, `find\[`, `\$gte`, `\$lte`, `\$in`, `\$exists`, `api-secret`, `api_secret`,
`token`, `_id`, `socket`, `status`. (`src/utils.ts:17-30` `token` is a Logtail logging token read
from the environment, not Nightscout.)

| S-id | what the client does | anchor (repo@sha path:line) | patterns searched |
|---|---|---|---|
| S1 | `count=${maxCount}` on GET entries/sgv, profile, treatments, devicestatus when `maxCount` is truthy; otherwise no count. `validateMaxCount` only rejects `> 3000`. So `maxCount = 0` sends **no** count (server default); a negative or fractional `maxCount` from the host app is sent as-is and gets **400 "Bad count"** on the candidate (15.0.8: `parseInt`). No DELETE carries a count. | `src/downloads.ts:29-34`, `:43-54`, `:63-76`, `:85-98`, `:107-122`, `:132-139` | `count`, `maxCount` |
| S2 | `find[created_at][$gte]=<fromUtcString>` on `GET /api/v1/activity/`; `find[created_at][$lte]=<YYYY-MM-DD>` on **DELETE** `/api/v1/devicestatus/` (and any `apiUrl` passed to `deleteBase`). Values are not URL-encoded by the library. | `src/load-activity.ts:28-33`; `src/utils.ts:198-215`; `src/delete.ts:24-37` | `find\[`, `\$` |
| S3 | Date bounds only (`created_at` strings; the server rewrites the `dateField` bound to ISO UTC). A date-only bound (`YYYY-MM-DD`) is parsed as midnight. No numeric-field comparisons. | as S2 | numeric `\$gte` — none |
| S4 | None found. | — | `status`, `verifyauth`, `/count/`, `properties`, `ddata` |
| S5 | `api-secret: sha1(apiSecret)` on every request. TLS verification disabled for https (`rejectUnauthorized: false`). No token/JWT/subjects. | `src/setupParams.ts:4-32` | `api-secret`, `token`, `Authorization` |
| S6 | None found. | — | `socket` |
| S7 | No `_id` on any upload (notes, treatments, entries, activity, devicestatus). No PUT/DELETE by id. | `src/upload.ts:32`, `:65`, `:103`, `:144`, `:179`, `:237-270` | `_id`, `identifier` |
| S8 | Treatments POST with `mills`, `utcOffset: 0`, and explicit `carbs: null` / `insulin: null` on temp basals. (A stored `null` counts as present for `$exists`, so these temp basals match `find[carbs][$exists]=true` in other clients — unchanged by the candidate, which only fixes the `false` spelling.) | `src/upload.ts:231-270` | `carbs`, `insulin`, `created_at` |
| S9 | None found. | — | `food` |
| S10 | Reads `/api/v1/profile.json` (optionally with count). No profile writes. | `src/downloads.ts:63-76` | `profile` |
| S11 | Writes devicestatus (`uploadDeviceStatus`) and reads devicestatus back via `downloadNightscoutDeviceStatus`; does not read Nightscout-computed COB/IOB endpoints. | `src/upload.ts:155-189`; `src/downloads.ts:107-122` | `devicestatus`, `properties`, `pebble` |
| S12 | Hand-built query strings; no arrays; trailing slash before `?` (`/api/v1/activity/?find…`). | `src/load-activity.ts:32`; `src/utils.ts:205` | `\[\]`, `\$in` |
| S13 | None found. | — | `api/v3`, `limit` |
| S14 | None found. | — | `notifications` |
| S15 | Downloads throw on non-200 (the caller decides). **Uploads and deletes resolve on any HTTP status** (`fetch(...).then(() => log success)`), so a 400 on a POST or DELETE is logged as success and the data is silently not stored / not deleted. | `src/downloads.ts:13-22`; `src/utils.ts:156-178`, `:198-215` | `status`, `then`, `catch` |

## Worth cross-checking against the change list

1. **S1**: only if a host app passes a negative/fractional `maxCount`. Question: does the CGMSIM
   service ever compute `maxCount` (e.g. from hours)? Not visible in this library.
2. **S15**: any new 400 on POST would be invisible to users of this library. Nothing it POSTs
   (no `_id`, no count) is in the candidate's refused set on read.
