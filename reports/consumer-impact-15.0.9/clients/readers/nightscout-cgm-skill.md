# nightscout-cgm-skill — consumer impact against cgm-remote-monitor 15.0.9 candidate

- Repo: externals/nightscout-cgm-skill (an AI-assistant "skill": one Python script that pulls
  Nightscout data into a local SQLite cache and computes statistics/charts).
- Ref analysed: `origin/master` **91a53ea (2026-06-07)**; local HEAD = 91a53ea, behind 0, dirty 0.
  Many `origin/copilot/*` feature branches exist; not analysed (default branch only).
- All code is in `scripts/cgm.py` (the only non-test source file besides `show-all-charts.ps1`).
- All claims **read-derived**.

## Positive control

`git grep -n -E "requests\.(get|post|put|delete)" origin/master -- scripts/cgm.py` → 13 call
sites, all GETs to Nightscout, e.g. `scripts/cgm.py:495` (entries paging), `:6322-6326`
(treatments). URL root is derived from `NIGHTSCOUT_URL` (`:38-55`). `requests` with a `params`
dict is the only URL-building method, so parameter names appear as string literals.

## Surface table

| S-id | what the client does | anchor (nightscout-cgm-skill@91a53ea) | patterns searched |
|---|---|---|---|
| S1 count | GET only. Literals `1` (`:324,333,924,6197`), `10000` (`:490`), `5000` (`:6324,6448`); `limit` for change-age queries (`:6627`) is validated `>= 1` (`:6601-6602`) and comes from `--count` with `type=_positive_int` (`:7066`, `_positive_int` `:6777`). Never 0, negative, fractional or huge. | as listed | `"count"`, `count=`, `_positive_int` |
| S2 operators | `find[date][$lte]` (`:492`), `find[created_at][$gte]` (`:6324,6448`), plain `find[eventType]=<Site/Sensor/Insulin Change>` (`:6627`). All allowed. | as listed | `find\[`, `\$(gte\|lte\|gt\|lt\|in\|exists\|regex\|ne\|eq\|expr)` |
| S3 numeric | Only entries `date` in epoch ms (`:492`, integer `oldest - 1`, `:522`); coerced as a number on both releases. `created_at` bounds are ISO `…Z` strings (`:6320,6443`). Insulin/carb totals are summed client-side (`:6339-6340`), so the candidate's numeric-filter fix does not move them. | as listed | `find\[(insulin\|carbs\|duration\|sgv\|mills)\]` |
| S4 shared | `status.json` for settings/units (`:67-75`), failure → empty settings. `profile.json` with no count (`:360,6654`). No `/count/`, `/times/`, `/slice/`, v2. | as listed | `status.json`, `profile.json`, `/count/`, `properties`, `verifyauth` |
| S5 auth | **No authentication of any kind**: no `api-secret` header, no `token` param, no Bearer. Works only against a site readable anonymously (`AUTH_DEFAULT_ROLES=readable`). Unchanged by the candidate. A `?token=` pasted into `NIGHTSCOUT_URL` would be mangled by `_normalize_nightscout_url` (`:38-50`, suffix matching). | `:38-55` and every `requests.get` | `api-secret`, `API_SECRET`, `token`, `Authorization`, `headers=` |
| S6 websocket | none found. | — | `socket`, `websocket` |
| S7–S11 | none (read-only). Stores entry `_id` as its SQLite key (`:506-515`). | `:506-515` | `requests\.(post\|put\|delete)` |
| S12 shape | flat `params` dicts; no arrays. | as listed | — |
| S13 v3 | none found. | — | `api/v3` |
| S14 | none found. | — | `notifications` |
| S15 errors | `raise_for_status()` on data fetches → returns an `{"error": …}` dict to the assistant (`:496-499,6327,6451-6454,6630`); capability probes treat any non-200 as "not available" (`:324-370`). Entry paging stops on an empty page (`:501-502`). A 400 would surface as an error message, not as silently wrong statistics. No request here is expected to get one. | as listed | `raise_for_status`, `status_code` |

**Impact: none expected.**
