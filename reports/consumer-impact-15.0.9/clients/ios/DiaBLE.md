# DiaBLE: consumer-impact map against the cgm-remote-monitor 15.0.9 candidate

All claims are **read-derived**: the source was read with `git show`/`git grep`, and nothing was run.

| | |
|---|---|
| repo | externals/DiaBLE (DiaBLE: Libre/Dexcom reader app, with optional Nightscout upload and view) |
| ref analysed | `origin/main` **e6a909c**, 2026-07-30 |
| local checkout | HEAD a7db070, **7 behind**, 11 dirty files. The working tree was ignored. |
| other branches | `origin/dev` = e6a909c, **identical to main** (0 commits apart). |
| Nightscout code | `DiaBLE/Nightscout.swift` (227 lines, the whole client). Callers are in `DiaBLE/MainDelegate.swift`, `DiaBLE/Views/OnlineView.swift` and `DiaBLE/Views/DataView.swift`. A byte-identical copy is at `DiaBLE Playground.swiftpm/Nightscout.swift` (same line numbers). |
| shape | A small v1 uploader and reader. It POSTs `sgv` entries and GETs the last 100. It also shows the Nightscout **web page** in an embedded WebView (`OnlineView`), which means the page's own socket.io client runs inside DiaBLE. |

**Positive controls** (`git grep -n <pattern> origin/main -- 'DiaBLE/*.swift'`):
- `api/v1/entries` → DiaBLE@e6a909c DiaBLE/Nightscout.swift:102, :165, :170, :204
- `count=` → DiaBLE/Nightscout.swift:102

The settings default the site field to a third-party host, and the token default is an empty string (DiaBLE/Settings.swift:35-36). No credential is hard-coded.

## S1–S15

| S-id | what the client does | anchor (DiaBLE@e6a909c) | patterns searched |
|---|---|---|---|
| S1 count | One GET, `count=100`, a literal. It cannot be 0, fractional or huge. The `delete()` helper takes free-form `query` text, but **no caller of it exists** on this ref. | Nightscout.swift:102, :170-199 | `count=`, `"count"`, `\.delete\(` |
| S2 find operators | None found. | — | `find\[`, `\$exists`, `\$gte`, `\$in`, `\$regex`, `\$expr`, `pipeline` |
| S3 numeric compares | None found (no filters). | — | `\$gt`, `\$lt`, `find\[` |
| S4 shared read endpoints | None found. The embedded web page loads whatever the Nightscout site serves. | — | `api/v1/status`, `api/v2`, `count/`, `times`, `slice`, `echo`, `verifyauth` |
| S5 auth | **One setting, `nightscoutToken`, is used two ways.** Reads (`request`) append it raw as `&token=`. The code appends `&token=` without checking whether a `?` exists, but `read()` always passes a query, so the URL is well formed. Writes (`post`, `delete`, `test`) send `api-secret: SHA1(nightscoutToken)`. That works with the API_SECRET. With an access token it works because the server's `findSubject` also matches `accessTokenDigest` (SHA-1 of the token) by prefix. That path is unchanged on #8754 head ef3404fd. A 401 is only logged. The web view loads `https://<site>?token=<token>`. The client does not use JWT or subjects/roles and does not set X-Forwarded-For. | Nightscout.swift:45, :75, :118-124, :181, :204-207; Views/OnlineView.swift:197-198; DiaBLE/Extensions.swift:10, :94; server cgm-remote-monitor@ef3404fd lib/authorization/storage.js:336-366 | `token`, `api-secret`, `SHA1`, `Bearer`, `authorization`, `X-Forwarded` |
| S6 websocket | No native socket.io client: `Package.swift` depends only on CryptoSwift and LibreCRKit, `DiaBLE.xcodeproj` has no remote package references, and no Swift code mentions a socket. **Indirect:** the WebView runs the Nightscout page's own socket.io client, authenticated by the `?token=` in the page URL. Under `AUTH_DEFAULT_ROLES=denied`, the candidate's socket authorize change decides whether that embedded page receives live data. The page's behaviour is the web client's, not DiaBLE's. | Views/OnlineView.swift:188-198; `DiaBLE Playground.swiftpm/Package.swift` | `socket`, `SocketIO`, `websocket`, `repositoryURL`, `.package(url:` |
| S7 `_id` | POST entries carry **no `_id`**: `type`, `dateString`, `date` (Int64 ms), `sgv` and `device`. The client does not read `_id` back and does no PUT or DELETE by id. It dedups itself: it only POSTs readings newer than the newest `date` from the last GET. | Nightscout.swift:155-167; MainDelegate.swift:432-439 | `"_id"`, `identifier`, `PUT`, `DELETE` |
| S8 treatments | None found. | — | `treatments`, `eventType` |
| S9 food | None found. | — | `food`, `quickpick` |
| S10 profile | None found. | — | `profile` (Nightscout context), `api/v1/profile` |
| S11 COB/IOB | None found: no devicestatus writes, and no COB/IOB reads. | — | `devicestatus`, `cob`, `iob`, `properties` |
| S12 query shape | A single `count=100` plus `token=`. There are no arrays. | Nightscout.swift:44-45, :102 | `\[\]`, `\$in` |
| S13 API v3 | None found. | — | `api/v3` |
| S14 other | None found. | — | `notifications`, `ack` |
| S15 errors | **An error is silently turned into "no data".** `request()` and `post()` return a placeholder `(["":""], URLResponse())` whenever the body is valid JSON but not an array. A 400 error body is exactly that case, so no error is thrown. `post()` logs "POST error (status: N)" and carries on. The upload loop keeps no "uploaded" marker: each cycle re-reads the last 100 entries and re-POSTs anything newer. A rejected POST is therefore **retried every cycle, not stalled or dropped**. An empty array from the GET makes it re-POST **all** local entries, which the server upserts on sysTime+type. | Nightscout.swift:83-96, :130-151; MainDelegate.swift:432-439 | `statusCode`, `status == 401`, `jsonDecoding`, `values.count > 0` |

## Join questions (ranked by user visibility)

1. **S6 (data stops, only on locked-down sites).** On `AUTH_DEFAULT_ROLES=denied`, the embedded Nightscout page's socket connection is now authorized like the rest of the site. Confirm that a page opened with `?token=<access token>` still receives `dataUpdate` on the candidate. This follows from the web client's behaviour, which the web-client analysis should confirm, not DiaBLE-specific code.
2. **S15 (masking).** A 400 on `GET /api/v1/entries.json?count=100` would be indistinguishable from "no data" and would make DiaBLE re-POST all local readings each cycle. Read-derived: `count=100` is valid on the candidate, so this is not expected.
3. No other surface is touched. DiaBLE is low-risk for 15.0.9.
