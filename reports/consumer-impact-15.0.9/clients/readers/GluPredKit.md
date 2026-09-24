# GluPredKit — consumer impact against cgm-remote-monitor 15.0.9 candidate

- Repo: externals/GluPredKit (SINTEF blood-glucose prediction toolkit, Python).
- Ref analysed: `origin/main` **e5bd635 (2026-01-13)**; local HEAD = e5bd635, behind 0, dirty 0.
  The Nightscout parser was last changed in 79630d3 (2025-02-06, "nightscout parser (#75)").
- All claims **read-derived**.

## HIGHEST-RISK HIT: it asks for `count=0` meaning "no limit", on every read

`glupredkit/parsers/nightscout.py:66-91` builds three requests, each with `'count': 0` and a date window:

| line | request | params |
|---|---|---|
| `:67-75` | `GET {url}/api/v1/profile?…` via `requests.get` with the library's headers | `count=0`, `find[created_at][$gte]`, `find[created_at][$lte]` (ISO, `…T…:…:….000Z`) |
| `:78-83` | `api.get_treatments(params)` (python-nightscout) | `count=0`, `find[created_at][$gte]`, `find[created_at][$lte]` |
| `:86-91` | `api.get_sgvs(params)` (python-nightscout) | `count=0`, `find[dateString][$gte]`, `find[dateString][$lte]` |

**On 15.0.8** the string `"0"` is truthy in JavaScript, so every one of these reached
`.limit(0)`, which in MongoDB means *no limit*: the tool received every record in the window.
- treatments/entries: `if (opts && opts.count) return this.limit(parseInt(opts.count))`
  (`cgm-remote-monitor@92d08342 lib/server/treatments.js:244`, `entries.js:36`); a `find` forces the
  database path (bf/reads measured `?count=0&find[…]` returning every row on dev a8888f0d).
- profile: `req.query.count ? Number(req.query.count) : default` → `Number("0")` = 0 → `.limit(0)`
  (`92d08342 lib/api/profile/index.js:49`, `lib/server/profile.js:87-90`).

**On the candidate** `count=0` on a GET is answered with an **empty list**:
`validateCount` lets zero through (`ddd9b600 lib/api/index.js:89`), `applyCount` returns an
object whose `toArray()` resolves `[]` (`ddd9b600 lib/server/count.js` `applyCount`/`NO_DOCUMENTS`),
and `profile.list` returns `[]` for a zero count (`ddd9b600 lib/server/profile.js` `isZeroCount`).
(`/api/v1/profile` ignores the `find` it is sent on both releases.)

**What the user sees:** the entries list is empty, so `create_dataframe` returns an empty DataFrame
with no DatetimeIndex (`nightscout.py:389-461`), and `df_glucose.resample('5min')` (`:143`) fails;
the `except` at `:193-196` prints "Error in data processing" and re-raises. A GluPredKit
`parse --parser nightscout` run that worked against 15.0.8 **stops with an error** against 15.0.9,
and no data is downloaded. (If the entries call alone returned data, empty treatments and profiles
would instead yield a dataset with zero insulin and carbs — `merge_and_process` and
`get_basal_rates_from_profile` tolerate empty input, `:318-319,464-465` — which is the more
dangerous failure; it does not arise here because all three calls send `count=0`.)

This contradicts the candidate's own PR text: `reports/phase0-pr-bodies/count-zero-empty.md`
says "Apps that already work keep working. If you use an app that asks for zero records, it now
gets an empty answer instead of an error." GluPredKit is an app that *works today because of* the
15.0.8 defect, and the release notes' count section (`releases/cgm-remote-monitor-15.0.9/release-notes.md`
"Asking for a number of records") does not tell its users. The operator census
(`docs/60-research/tenancy/v1-operator-census-2026-09-14.md`) counts operators, not `count` values,
so it could not have caught this.

**Caveat (not analysed):** `get_treatments`/`get_sgvs` come from the `python-nightscout` package
(`requirements.txt:13`, `setup.py:36`), which is not in the corpus. The read assumes the library
passes the params dict through as query parameters to `treatments.json` and an entries path — that
is how the call sites use it, but the library's URL construction was not read. The profile call
(`:73-74`) does not depend on the library's URL building (only on `api.request_headers()`), so at
least that request is certain to carry `count=0`.

## Positive control

`git grep -n -i -E "api/v1|count|find\[" origin/main -- glupredkit/parsers/nightscout.py`
→ `:68-90` (the three param dicts) and `:73` (`/api/v1/profile`). No other GluPredKit file calls
Nightscout (`git grep -n -i "nightscout" origin/main -- 'glupredkit/*.py'` hits only `cli.py:50,104`,
the parser registration).

## Surface table

| S-id | what the client does | anchor (GluPredKit@e5bd635) | patterns searched |
|---|---|---|---|
| S1 count | `count=0` on profile, treatments, entries (GET) — see above. No other count. | `glupredkit/parsers/nightscout.py:68,79,87` | `count`, `'count'` |
| S2 operators | `$gte`/`$lte` only. Allowed by the candidate. | `:69-70,80-81,88-89` | `\$(gte\|lte\|gt\|lt\|in\|exists\|regex\|ne\|eq)`, `pipeline` |
| S3 numeric | none: time bounds are ISO strings on `created_at` (treatments; its `dateField`, normalised by `enforceDateFilter` on both releases) and `dateString` (entries; a string field, not coerced on either release). All insulin/carb/temp-basal figures are computed client-side (`:109-130`, `:506-512`). | as listed | `find\[(insulin\|carbs\|duration\|absolute\|rate\|sgv\|date)\]` |
| S4 shared | none found. | — | `status`, `/count/`, `properties`, `verifyauth` |
| S5 auth | `nightscout.Api(url, api_secret=password)`; the profile call reuses `api.request_headers()` (`:62,74`). The header format is the library's (not read). No token query, no JWT, no subjects, no X-Forwarded-For. | `:62,74` | `api_secret`, `token`, `Authorization`, `X-Forwarded` |
| S6 websocket | none found. | — | `socket`, `websocket` |
| S7–S11 | none (read-only). Treatment model is monkey-patched to accept Loop/Trio fields (`:12-50`). | `:12-50` | `post`, `put`, `delete`, `_id` |
| S12 shape | `urllib.parse.urlencode` of a flat dict (`:73`) → bracket keys percent-encoded; no arrays. | `:73` | `urlencode` |
| S13 v3 | none found. | — | `api/v3` |
| S14 | none found. | — | `notifications` |
| S15 errors | Profile: `profiles_response.json()` with no status check (`:74-75`). Library calls: exceptions propagate. Empty lists: see above — entries empty → exception; treatments/profiles empty → silently zero. | `:74-75,98-100,193-196` | `status_code`, `raise_for_status`, `except` |
