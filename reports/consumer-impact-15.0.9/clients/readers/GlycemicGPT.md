# GlycemicGPT — consumer impact against cgm-remote-monitor 15.0.9 candidate

- Repo: externals/GlycemicGPT (multi-app: FastAPI backend `apps/api`, web, mobile).
- Ref analysed: `origin/main` **d1a9adb7 (2026-08-18)**. Local HEAD 249a7890 is **97 behind**.
  `origin/develop` ec902563 (2026-09-12) is newer, but
  `git diff --stat origin/main origin/develop -- apps/api/src/services/integrations/nightscout`
  is empty: the Nightscout integration is identical on both.
- Nightscout integration: `apps/api/src/services/integrations/nightscout/` (client, sync, evaluate,
  mappers). Glooko/Dexcom integrations also exist and are not Nightscout.
- All claims **read-derived**.

## Positive control

`git grep -n -E "/api/v[123]/|find\[|\"count\"" origin/main -- apps/api/src/services/integrations/nightscout/client.py`
→ `client.py:462` (`/api/v1/status.json`), `:614-650` (entries/treatments/devicestatus), `:662`
(profile), `:681-692` and `:734-737` (the only two param builders). All requests go through
`_request` (`:285-377`, httpx). Parameter names are string literals in `params` dicts.

## Surface table

| S-id | what the client does | anchor (GlycemicGPT@d1a9adb7, path `apps/api/src/services/integrations/nightscout/`) | patterns searched |
|---|---|---|---|
| S1 count | GET only. `count` is a constant: `DEFAULT_PAGE_SIZE = 5000` (`client.py:87`); onboarding probes 2500/1000/200/50 (`evaluate.py:43-46`); docstring example 500 (`client.py:161`). No computed or zero count. | as listed | `DEFAULT_PAGE_SIZE`, `_PROBE_COUNT`, `count=` |
| S2 operators | `find[dateString][$gte]` (entries fallback), `find[created_at][$gte]` (treatments, devicestatus) (`client.py:681-694`); `find[_id][$gt]=<24-hex>` (entries cursor, `:734-737`, validated as 24-hex `:724-733,766-777`). All allowed. | as listed | `find\[`, `\$(gte\|lte\|gt\|lt\|in\|exists\|regex\|ne\|eq)` |
| S3 numeric | none. Bounds are ISO strings (`since_utc.isoformat()` with `Z`, `client.py:691-694`) or an ObjectId. | as listed | `find\[(insulin\|carbs\|duration\|date\|sgv)\]` |
| S7 `_id` cursor | `find[_id][$gt]=<hex>` becomes an ObjectId bound via `updateIdQuery`, whose code is **identical** on 15.0.8 (`92d08342 lib/server/query.js:95-123`), dev (`ddd9b600 :110-138`) and #8758 (`6d120fa2 :110-138`). Entries stored with a string `_id` (15.0.6 or earlier, per #8758) never match an ObjectId `$gt` on any release; #8758 does not rewrite stored ids. No change. Note: an entries query with only an `_id` filter still gets the default date window (`enforceDateFilter`), unchanged. | as listed | `_id` |
| S4 shared | `/api/v1/status.json` (connection test, `client.py:462-500`), `/api/v3/version` + `/api/v3/status` for v3 detection (`:507-545`). `profile.json` with no count (`:662`). | as listed | `status`, `version`, `/count/`, `properties` |
| S5 auth | v1: `api-secret: sha1(secret)` (`client.py:254-263`); v3: `Authorization: Bearer <token>` (`:265-280`); no credential → anonymous (`:254-266`). Data fetches are v1-only (`_require_v1_for_fetch`). 401/403 → `NightscoutAuthError`, no retry (`:379-386`). 429 honoured with a clamped `Retry-After` (`:95,339-345`). No X-Forwarded-For. No subject/role writes. A slow (throttled) auth reply is bounded by the client timeout. | as listed | `api-secret`, `Authorization`, `Bearer`, `token`, `X-Forwarded`, `authorization/` |
| S6 websocket | none found. | — | `socket`, `websocket` |
| S7–S11 writes | none found (read-only sync into its own DB). | — | `"POST"`, `"PUT"`, `"DELETE"` in `client.py` |
| S12 shape | flat dicts; no arrays. | — | — |
| S13 v3 | version/status only; no v3 data reads. | `client.py:507-545` | `api/v3` |
| S14 | none found. | — | `notifications` |
| S15 errors | non-200 → `NightscoutServerError` (`client.py:699-703,742-746`); the sync layer catches and retries next cycle (`client.py:726-730` comment; `sync.py`). Empty list is a normal "no new data". A 400 would stall sync with an error rather than lose data silently. None expected. | as listed | `status_code`, `raise` |

**Impact: none expected.**
