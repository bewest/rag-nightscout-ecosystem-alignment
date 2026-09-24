# nightscout-reporter — consumer impact against cgm-remote-monitor 15.0.9 candidate

- Repo: externals/nightscout-reporter, remote `zreptil/nightscout-reporter`
- Ref analysed: `origin/master` **518d61f (2025-10-23)**; local HEAD = 518d61f, behind 0, dirty 0.
  Only other remote branch: `origin/legacy-pillman` 364980c (2022-08-26), older; not analysed.
- All claims are **read-derived** (source read with `git grep`/`git show`; nothing run).

## MISMATCH — this is not the Nightscout Reporter people use (stop-and-report)

The brief calls this client "Dart/Angular". The code at 518d61f is the **AngularDart** app, and it
is **retired**:

- `README.md:1-5` (518d61f): "this project is no longer maintained and is outdated ... use the
  repository at `zreptil/nightscout-reporter-angular` for the current version" (translated from German).
- The last commit touching code is b664fba (2022-12-22) "final changes before moving to angular";
  the two newer commits (8fad167 2025-02-05, 518d61f 2025-10-23) edit README.md only.

The current, deployed Nightscout Reporter (TypeScript Angular, `zreptil/nightscout-reporter-angular`)
is **not in the corpus** (`ls externals | grep -i -E "report|zreptil|angular"` finds only this repo).
Nothing below speaks for it. The rows below describe the frozen 2022 Dart code, which is a
reasonable *lead* for the successor (the successor was ported from it), not evidence about it.
The join step should treat Reporter as **not analysed** until the Angular repo is added.

## Positive controls (same method as the absence searches)

`git grep -n -E "api/v1|api/v2|api/v3|count=|find\[" origin/master -- lib web`
- `lib/src/start_component.dart:1213-1215` — per-day `entries.json` read (`find[date][$gte]`/`[$lte]`, `count=100000`)
- `lib/src/start_component.dart:1257-1259` — per-day `treatments.json` read
- `lib/src/globals.dart:1965-1989` `UrlData.fullUrl` — builds every URL: `<base>/api/v1/<cmd>?token=<t>&<params>`
  (called via `UserData.apiUrl`, `globals.dart:2136-2141`)

## How it talks to Nightscout

Browser-side `http.BrowserClient` GETs (`globals.dart:1324-1349`). All query strings are
hand-concatenated string literals; there is no Uri/queryParameters builder, so every parameter
name appears as a literal and the grep above is exhaustive for v1 query shape. The only POST
(`globals.dart:1329`) is used by `lib/src/controls/signin/signin_component.dart:95` for a Google
sign-in (settings sync to Google Drive), not Nightscout. The app is read-only against Nightscout.

## Surface table

| S-id | what the client does | anchor (repo@sha path:line) | patterns searched |
|---|---|---|---|
| S1 count | All GET. Literals only: `count=2` (`globals.dart:865`, `settings_component.dart:239,267`, `print-user-data.dart:191`), `count=10` (`globals.dart:878`), `count=100` (`start_component.dart:1245`), `count=10000` (`start_component.dart:1054`), `count=100000` on entries, treatments, devicestatus, activity per day (`start_component.dart:1215,1259,1308,1321`). profile: `count=${maxCount}` (`start_component.dart:1006`) where maxCount comes from the fixed list `[100000, 2000, 1000, 500, 250, 100]` (`globals.dart:956`) indexed by a user setting (`start_component.dart:1002`). No computed count; cannot be 0, negative, fractional or > 2^53. All accepted by the candidate's `validateCount` (digits, safe integer, > 0) — `cgm-remote-monitor@ddd9b600 lib/api/index.js:71-94`, `lib/server/count.js`. No DELETE. | nightscout-reporter@518d61f as listed | `count=`, `count\b`, `profileMaxCounts` |
| S2 operators | `$gte $lte $gt $lt $eq $ne` only; plain equality `find[eventType]=Profile Switch` (`start_component.dart:1051`); `find[eventType][$eq]=Temp%20Basal` (`:1245`); `find[profilePlugin][$ne]=<AAPS plugin class>` (`:1054`, only when the user enables the AAPS 3.0 fix `g.ppFixAAPS30`). A commented-out `profiles.json?find[startDate]...` block (`:1007-1011`) is dead code. No `$exists`, `$regex`, `$in`, `$expr`, `pipeline`. All inside the candidate allowlist. | as listed | `\$(gte\|lte\|gt\|lt\|eq\|ne\|in\|nin\|exists\|regex\|where\|expr)`, `pipeline` |
| S3 numeric comparison | The only numeric-field filter is `entries` `date` in epoch ms (`start_component.dart:1214-1215`, `settings_component.dart:239,267`, `print-user-data.dart:190-191`). 15.0.8 already `parseInt`ed entries `date` (`cgm-remote-monitor@92d08342 lib/server/entries.js:186-187`); the candidate `parseFloat`s it from the schema (`query-coercion.json` entries.date = number). Same result for integer ms. Treatments, devicestatus and activity are filtered on `created_at` with ISO-8601 UTC strings from `toIso8601String()` of UTC DateTimes (`start_component.dart:1205-1210,1243-1244,1258,1307,1320`); `created_at` is each of those collections' `dateField`, normalised by `enforceDateFilter` identically in both releases (the candidate's only change there is the unescaped-`+` repair regex, and these strings end in `Z`). **No duration/insulin/carbs/absolute/percent filter exists**, so the release-note warning "reports ... may show different numbers" does not apply to this code's queries: all totals are computed client-side from full per-day downloads. | as listed | `find\[(duration\|insulin\|carbs\|absolute\|percent\|rate\|sgv\|mbg\|glucose\|mills)\]`, `find\[date\]`, `find\[created_at\]` |
| S4 shared/aggregate | `status.json` on start-up, per report and for the current-glucose widget (`start_component.dart:935,956,983`, `globals.dart:855`, `printparams_component.dart:82`); `status` (HTML/text) in `checkSetup`, which looks for the substring `status ok` (`globals.dart:1355-1357`). A `status` field of `'401'` in the JSON marks the site unreachable (`start_component.dart:988-990`). No `/count/`, `/times/`, `/slice/`, `/echo/`, v2 `properties`/`ddata`, `verifyauth`. Candidate change to `lib/api/status.js` is only the client-address source (`TRUST_PROXY`), no contract change (`cgm-remote-monitor@ef3404fd lib/api/status.js`). | as listed | `status\.json`, `'status'`, `verifyauth`, `/count/`, `/times/`, `/slice/`, `/echo/`, `properties`, `ddata` |
| S5 auth | Token in the query string only: `?token=<t>&` (`globals.dart:1978-1979`). Token read from user settings (`globals.dart:1916,1942`). No `api-secret` header, no JWT/Bearer, no subject/role creation, no X-Forwarded-For. Two demo configurations carry a **hard-coded credential** at `globals.dart:608` and `globals.dart:741` (a public demo site's read token; not reproduced). Reaction to 401: only via the status JSON's `status=='401'` (`start_component.dart:988`); data requests ignore HTTP status entirely (see S15). A delayed auth reply just delays the request (no timeout set on `BrowserClient`). | as listed | `token`, `api-secret`, `API-SECRET`, `apisecret`, `Authorization`, `Bearer`, `X-Forwarded`, `authorization/` |
| S6 websocket | none found. No socket.io dependency or code. | — | `socket`, `WebSocket`, `io(` in `pubspec.yaml` and `lib/*.dart` |
| S7 `_id` | Read-only. Reads treatment `_id` into synthetic profile JSON (`start_component.dart:1125`) and `entry.id = t.id` (`:1278`); treats it as an opaque string. No POST/PUT/DELETE to Nightscout. | as listed | `_id`, `method: *'(post\|put\|delete)'`, `\.post\(`, `\.put\(`, `\.delete\(` |
| S8 treatment edits | none found (read-only). Relevant read side: de-duplicates adjacent equal treatments and skips `enteredBy == 'sync'` (`start_component.dart:1268-1271`). #8758's "edited records no longer leave an old copy" can *reduce* duplicate treatments it sums, on sites that had them; client-side dedupe only catches adjacent exact duplicates. | as listed | as S7 |
| S9 food | none found. | — | `food`, `quickpick` |
| S10 profile | Reads `profile.json?count=N` (`start_component.dart:1006`) and Profile Switch treatments since Jan 1 of the previous year (`:1051-1057`); builds synthetic profiles from `profileJson` (`:1120-1145`). Warns when N profiles came back (`:1033-1034`). No profile writes. | as listed | `profile.json`, `profiles.json`, `Profile Switch`, `defaultProfile`, `startDate` |
| S11 COB/IOB | Downloads devicestatus per day (`start_component.dart:1306-1317`) and parses it client-side; does not read Nightscout-computed COB/IOB (no v2 properties, no pebble). | as listed | `pebble`, `properties`, `devicestatus` |
| S12 query shape | Bracket notation only, max 3 `find` clauses per request, no arrays, no nesting beyond `find[field][$op]`. Values carry an unencoded space (`find[eventType]=Profile Switch`, `start_component.dart:1051`) left to the browser's URL encoder, and dots (`info.nightscout.androidaps...`, `:1054`). No valueless parameters: when `params` is empty the trailing `?`/`&` is trimmed (`globals.dart:1983-1985`). No underscores in values that the candidate's `_`-to-space change (bf/parms, client page URL only) could affect. | as listed | `find\[`, `&count`, `\?token=` |
| S13 v3 | none found. | — | `api/v3`, `lastModified`, `identifier`, `sort\$desc` |
| S14 other | none found. | — | `notifications`, `/ack`, `alexa`, `googlehome`, `loop` (in URL context) |
| S15 errors / empty | `request()` returns `response.body` regardless of HTTP status (`globals.dart:1339-1346`); `requestJson()` JSON-decodes anything that starts with `[` or `{` (`:1299-1316`). A 400 `{status, message}` object would be assigned to `List<dynamic> src` (`start_component.dart:1216,1246,1260,1309,1322`) and throw a runtime type error, caught only by per-block try/catch where present (profile block `:1016-1049`; the per-day entries loop has none around the assignment). An empty array is handled as "no data that day" (`hasData` stays false, `:1203,1341`). **No request in this code is expected to get a 400 from the candidate** (S1/S2 above), so this path is dormant. | as listed | `statusCode`, `\.status\b`, `catchError`, `requestJson` |

## Candidate-side observation surfaced while checking S3 (for the join step, not a client fact)

The candidate stopped coercing `activity` filters. On 15.0.8 `lib/server/activity.js` set no
`walker`, so `default_options` supplied `{ date: parseInt, sgv: parseInt }`
(`cgm-remote-monitor@92d08342 lib/server/query.js:40-41`, `activity.js:144-147`). On the candidate,
`activity.js` passes `collection: 'activity'` (`ddd9b600 lib/server/activity.js:145`), which makes
`default_options` choose an empty walker (`ddd9b600 lib/server/query.js` `opts.collection ? { } : ...`),
and the schema entry for `activity` is `{}` (`lib/server/query-coercion.json`, identical on
ef3404fd and 6d120fa2). So `find[date][$gte]=<epoch ms>` on `/api/v1/activity` becomes a string
bound and matches nothing on the candidate, where 15.0.8 matched numeric `date`s. The register's
BF-03 detail notes the default walker but concludes activity "has no numeric field to fix"; it does
not record this regression. **Reporter is not affected** (it filters activity by `created_at`,
`start_component.dart:1319-1321`), but any client filtering activity by `date` would get `[]`.
