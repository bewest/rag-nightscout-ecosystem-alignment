# glooko-nightscout-eu — Nightscout API use

All findings are **read-derived**. Nothing was run.

- Repo: `externals/glooko-nightscout-eu`
- Ref analysed: `origin/main` **2b7fbc4** (2026-06-25). Only branch.
- Local checkout: HEAD 2b7fbc4, behind=0, dirty=0.

## Positive control

- `glooko-nightscout-eu@2b7fbc4 glooko_uploader.py:74-77` — `POST {NS_URL}/api/v1/treatments` with `api-secret`.

Patterns searched (`git grep -n -E <pat> origin/main -- .`): `api/v1`, `api/v2`, `api/v3`,
`count`, `find`, `\$`, `api-secret`, `token`, `_id`, `socket`, `devicestatus`, `entries`,
`profile`, `urlopen`, `except`. (`/api/v2/pumps/…`, `/api/v2/foods`, `/api/v2/insulins` at
`:85`, `:98`, `:107` and `authenticity_token` at `:57-60` are Glooko's, not Nightscout's.)
`docker-compose.example.yml:14` carries a placeholder secret value (not a real credential).

| S-id | what the client does | anchor (repo@sha path:line) | patterns searched |
|---|---|---|---|
| S1 | None found (never reads Nightscout). | — | `count` |
| S2 | None found. | — | `find`, `\$` |
| S3 | None found. | — | `\$gt` |
| S4 | None found. | — | `status`, `verifyauth` |
| S5 | `api-secret: sha1(NIGHTSCOUT_SECRET)` header. No token/subjects. | `glooko_uploader.py:10`, `:19`, `:75-76` | `api-secret`, `token` |
| S6 | None found. | — | `socket` |
| S7 | No `_id`. Each treatment carries `glookoGuid`; dedup is a client-side set of guids persisted to `/data/uploaded.json`. One treatment per POST (array of one). | `glooko_uploader.py:43-51`, `:86-114` | `_id`, `guid` |
| S8 | POST only: `Meal Bolus`/`Correction Bolus`/`Carb Correction` with `insulin` (2 dp) / `carbs` (1 dp), `enteredBy: 'glooko-bridge'`, `created_at` converted to UTC `…T…:…:….000Z`. | `glooko_uploader.py:28-39`, `:92-113` | `created_at`, `eventType` |
| S9 | None found. | — | `food` (Glooko's only) |
| S10 | None found. | — | `profile` |
| S11 | None found. | — | `devicestatus`, `iob` |
| S12 | None (POST bodies only). | — | — |
| S13 | None found. | — | `api/v3` |
| S14 | None found. | — | `notifications` |
| S15 | `urlopen` raises on any 4xx/5xx; the exception propagates out of `run_once` **before** `state.add(g)` for that record and before `save_state`, so the whole run is abandoned and retried after `INTERVAL_MIN`; guids added earlier in that run are kept in memory but not saved to disk until a run completes. A persistent 400 on one record would **stall** every later record in the lookback window. | `glooko_uploader.py:74-77`, `:96`, `:118-126` | `except`, `urlopen` |

## Worth cross-checking

Nothing in the candidate's changed surface is sent. None.
