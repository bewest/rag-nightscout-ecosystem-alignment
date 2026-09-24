# oref-digital-twin — consumer impact against cgm-remote-monitor 15.0.9 candidate

- Repo: externals/oref-digital-twin (Python ingestion + a browser page running oref0 via Pyodide).
- Ref analysed: `origin/main` **a2e8610 (2026-08-08)**; local HEAD = a2e8610 (not in the corpus
  staleness file; measured here: behind 0, dirty 0).
- All claims **read-derived**.

## Positive controls

- Python: `ingestion/client.py:73-95` (`_get`, URL `{base}/api/v1/{path}`), `:107-143` (windowed pulls).
- Browser: `web/app.js:32-68` (`nsGet`, `windowed`, `fetchNightscout`).
Found with `git grep -n -E "api/v1/|find\[|count" origin/main -- ingestion web`.

## Surface table

| S-id | what the client does | anchor (oref-digital-twin@a2e8610) | patterns searched |
|---|---|---|---|
| S1 count | `count=50000` per 7-day window, GET (`ingestion/client.py:34,120`; `web/app.js:49`). Profile: no count (`client.py:146`, `app.js:64`). Accepted by the candidate. | as listed | `count` |
| S2 operators | `$gte`/`$lte` only. | `client.py:117-121`, `app.js:46-50` | `\$(gte\|lte\|gt\|lt\|in\|exists\|regex\|ne\|eq)` |
| S3 numeric | entries `date` in epoch ms (integers, `client.py:115-116,137`; `app.js:47-48,61`) — coerced on both releases. treatments/devicestatus `created_at` ISO `.000Z` (`client.py:112-114,150-153`; `app.js` `toISOString()`). Totals computed client-side. No change. | as listed | `find\[(insulin\|carbs\|duration\|sgv)\]` |
| S4 shared | `profile.json` only. | `client.py:145-147` | `status`, `/count/`, `properties` |
| S5 auth | Python: `token=` query param and/or `api-secret: <pre-hashed SHA-1>` header from env (`ingestion/config.py:34-49`). Browser: `token=` query only (`app.js:35`). 401/403 → raise, no retry (`client.py:88-89`, `app.js:37`). Retries 429/5xx with backoff (`client.py:92-94`). No X-Forwarded-For, no subjects. | as listed | `token`, `api-secret`, `Authorization`, `X-Forwarded` |
| S6 | none found. | — | `socket` |
| S7–S11 | none (read-only). Dedupes by `_id` across windows (`client.py:128-132`). | `client.py:128-132` | `POST`, `PUT`, `DELETE` |
| S12 | flat params; no arrays. | — | — |
| S13 | none found. | — | `api/v3` |
| S14 | none found. | — | `notifications` |
| S15 | 400 → `NightscoutError("unexpected status")`, raised (`client.py:95`); browser throws (`app.js:38`). Empty window → nothing appended. None expected. | as listed | `status` |

**Impact: none expected.**
