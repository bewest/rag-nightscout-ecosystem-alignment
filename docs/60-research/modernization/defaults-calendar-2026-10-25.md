# cgm-remote-monitor: operator-visible defaults, flags and behaviour changes, and a proposed calendar

> **DRAFT proposal, 2026-10-25, for the maintainers and the community.** Read-only inventory against `official/master` = `v15.0.9` `c6a0d8ed`, `official/dev` `b29f1bf7` and the tips of cuts 3, 4 and 5 (§0). The maintainer's word on the calendar (2026-10-25): it stays a draft, and the offsets are decided by maintainers and the community together; nothing in §3 is scheduled. BF-72 and BF-161 appear by mechanism only, because both are live on 15.0.9. Contributor-facing. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md); [16.0.0 release records](../../../releases/cgm-remote-monitor-16.0.0/contents.md); [versioning policy §5.7](../../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#57-compatibility-flags).

Session f4's `defaults-calendar` lane. *Who notices*: SH = self-hoster (operator), UP = uploader app
(xDrip+, Loop, Trio, AndroidAPS, oref0, nightscout-connect), FO = follower (browser, follower apps,
embeds), HP = hosted provider.

## Decided or changed since the inventory was taken (2026-10-25)

| row | now |
|---|---|
| C3-1, C3-2 | **Driver 7 ships in 16.0.0; MongoDB 4.4 or newer is required to start** (maintainer). C3-2 is BF-182; with -f8's fix on cut 3 (`7b636ce6`) servers 3.6 to 4.2 get the boot error page instead of an endless retry ([matrix note](mongodb-server-compat-matrix-2026-10-25.md)). The S0 cell "Driver 7 only if C3-2 is fixed first" is met. |
| C3-5 | **Compose default MongoDB 6.0 stands** (cut 3's `6.0.27`). The maintainer is fine with 6 or 7 and wants no automated migration or runbook for it. The S0 "status quo kept: compose MongoDB 5.0.32" cell is superseded. |
| D4 | Filed as **BF-179**; fixed on local branch `bf/179-omit-dev-install` `1cf70838`, to be cherry-picked onto cut 3. |
| C4-3 (storage socket) | Filed as **BF-183**; reproduced live and fixed on local branch `bf/183-storage-socket-log-redaction` `f6704b8a`, for cut 4. |
| B5 | BF-152 step 1 (opt-in `API3_SETTINGS_STRICT_READ_ENABLED`, default off) on local `bf/16.0.0-v3-settings-read-scope` `06ba6201`. |
| B6 | BF-164: lab done ([AndroidAPS websocket note](../remedial/aaps-websocket-delivery-lab-2026-10-25.md)); research on the AndroidAPS side before any code. |
| B7 | BF-175 **closed** as not a defect; the careportal case it surfaced is BF-180. |
| B2, B3 | BF-72 and BF-161: 16.0.0 only, no 15.0.x backport (maintainer). |
| T1-T3 | Added to the versioning policy §5.7 registry, 2026-10-25. |
| C3-6 | Read only; reproduce before filing. |

## 0. What was compared

| ref | hash | note |
|---|---|---|
| `official/master` = `v15.0.9` | `c6a0d8ed` | shipping release |
| `official/dev` | `b29f1bf7` (merge of #8840, 22:41Z) | unchanged from the brief's base; holds cut 1 (#8828 `eb72a1d3`), #8836 (`5de8505d`), #8833 (`fd3792e5`), cut 2 (#8837 `eb44a9c2`) and #8839 (`78524be4`) |
| cut 3 `official/chore/compose-mongodb6` | `ebb690cf` | 532 behind / 63 ahead of dev; merge base `b6e8c7cd` (already in dev) |
| cut 4 `official/chore/mime-exposure-review` | `b80aa147` | 532 / 142; cut 3 is its ancestor |
| cut 5 `official/chore/nightscout-modernization` (#8605) | `b1bdaca0` | 408 / 240; cut 4 is its ancestor; merge base `59430336` |
| -f8's rebased cut 3 (local, not pushed) | `wip/cut3-onto-16.0.0` `72c156fb` | used only to check whether a cut-3 finding survives the rebase |

Method: `git diff official/dev...<tip>` (each cut's own change since its merge base), then per file
whether `dev` already holds the tip's blob (28 files identical, 34 changed only by the cut, 78
changed on both sides for cut 5); `process.env`/`readENV` reads on every ref; `package.json` and
`package-lock.json` versions; boot sequence, refusal paths and exits read in source. Because the
tips are 400-530 commits behind `dev`, a plain `dev..tip` diff shows `dev`'s own newer work as
"removed"; those rows are listed separately in §4 as merge hazards, not as changes the cuts make.

**Provenance.** *reproduced* = executed and observed. *read* = read from source on the ref named.
Every row says which.

**Who notices**: SH = self-hoster (operator), UP = uploader app (xDrip+, Loop, Trio, AAPS, oref0,
nightscout-connect), FO = follower (browser, Nightscout follower apps, embeds), HP = hosted
provider (PaaS or managed Nightscout).

## 1. Inventory

### 1a. Already on `dev` (cut 1, cut 2 and other 16.0.0 merges) — for marking

| # | setting / behaviour | where (on `dev` `b29f1bf7`) | 15.0.9 | `dev` / 16.0.0 | who notices | failure mode if missed | reversibility | carried by | prov. |
|---|---|---|---|---|---|---|---|---|---|
| D1 | Node runtime floor | `lib/server/runtime-policy.js:10` (`process.exit(1)`), `package.json` engines | engines `>=20.x`, not enforced | exits at boot outside `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` (Node 20, 21, 23, 25, older 22/24/26 patches) | SH, HP | the process exits; on a PaaS this is a restart loop: no display, uploads refused, alarms do not run. Visible in the host's logs only | operator upgrades Node; no flag | cut 1 (#8828) + `6a146a4c` | read |
| D2 | Legacy Dexcom Share bridge (`share2nightscout-bridge`) removed | `lib/server/bridge-connect-compat.js:42-63`, `bootevent.js:85-94` | `BRIDGE_*` already served by nightscout-connect since 15.0.8 unless `DEXCOM_BRIDGE_USE_LEGACY=true` | `DEXCOM_BRIDGE_USE_LEGACY` ignored with a `DEPRECATION WARNING` log line; `BRIDGE_*` mapped to connect (incl. `BRIDGE_SERVER=US/EU/host`, #8823); `CONNECT_SOURCE` set to another source → boot error page | SH (Dexcom Share users) | sites that set `DEXCOM_BRIDGE_USE_LEGACY=true`: data now comes through connect; if connect cannot log in, Share data stops arriving with only a log line. Conflicting source: the whole site shows the stop page | none in 16.0.0 (bridge code removed) | cut 1 | read |
| D3 | Legacy MiniMed CareLink bridge (`mmconnect`) removed | `lib/server/mmconnect-connect-compat.js:16-36`, `bootevent.js:370-386` | `mmconnect` plugin, deprecated | `MMCONNECT_*` migrated to connect when `CONNECT_COUNTRY_CODE` is set; otherwise, or with a conflicting `CONNECT_SOURCE`, a boot error page naming the fix | SH (MiniMed users), every UP on that site | on the stop page no API route is mounted (`app.js` returns before mounting), so **every** uploader on the site is refused, not only MiniMed. Not silent: the page names the fix | operator adds `CONNECT_COUNTRY_CODE` or removes `MMCONNECT_*` | cut 1 | read |
| D4 | Build/runtime split: `webpack`, Babel and loaders are devDependencies; `postinstall` still runs `webpack` | `package.json:47`; `bin/azure-deploy.sh` and `Dockerfile` install with dev deps then prune | webpack in `dependencies` | a production-only install (`npm install --omit=dev`, `NODE_ENV=production npm install`, `NPM_CONFIG_PRODUCTION=true`) cannot run the `postinstall` build | SH (source installs), HP (third-party guides that set `NODE_ENV=production` at build) | install/deploy fails; on hosts that keep the previous release it stays on the old version; on a bare-metal `git pull && npm install --production` the site can be left without a bundle | operator changes the install command | cut 2 (#8837) | read (not run) |
| D5 | `Cache-Control: no-store` on any request carrying a credential; `Referrer-Policy: no-referrer` on every response (was only on the HSTS/CSP paths) | `lib/server/app.js:60-61`, `lib/middleware/credential-cache.js` | header set depended on `SECURE_*` settings | always | FO (browser caches), HP (CDN caching) | none expected; a CDN that relied on caching credentialed `status.json` stops caching it | code revert only | #8836 | read |
| D6 | Error and CSP-report log lines drop query strings and redact credentials | `lib/server/log-privacy.js`, `error-handler.js` | full URL and error logged | redacted | SH (debugging) | less detail in logs | code revert only | #8836 | read |
| D7 | Docker image ships without `npm`/`npx` | `Dockerfile:34` | npm present | removed from the runtime stage | SH who `docker exec … npm …` | those commands fail | rebuild image | #8836 | read |
| D8 | Status bootstrap sends credentials in headers, not the URL | `lib/client/index.js`, `lib/api/status.js` | `?secret=`/`?token=` on `status.json` | headers; query credentials still accepted from other clients | FO (shared links keep working) | none expected | code revert only | #8836 | read |
| D9 | MongoDB 4.4 and earlier documented as unsupported; CI edges 5.0 and 8.0 | `README.md:157-158`; #8833 removed the 4.4 CI check | 4.4 deprecated, tested | unsupported; **no server-side check**: driver 5.9.2 still connects to 3.6-4.4 | SH | none on `dev` (it still runs on old servers); the refusal arrives with cut 3 (C3-2) | n/a | #8838, #8833 | reproduced (driver 5.9.2 → MongoDB 4.2.24 connects) |
| D10 | `THEME=modern` opt-in theme | #8831 | n/a | new value; default unchanged | FO | none (opt-in) | unset it | #8831 | read |

Corrections merged on `dev` with no setting (BF-172/173/174 bolus wizard units, BF-157, BF-09 socket
dedup, #8816 snooze length, #8812/#8808/#8840 report figures) change what is shown but are not
defaults; they are in `releases/cgm-remote-monitor-16.0.0/contents.md` and not repeated here.

### 1b. Cut 3 — `chore/compose-mongodb6` `ebb690cf` (driver 7)

| # | setting / behaviour | where (tip) | 15.0.9 / `dev` | cut 3 | who notices | failure mode if missed | reversibility | prov. |
|---|---|---|---|---|---|---|---|---|
| C3-1 | MongoDB Node driver 5.9.2 → 7.x | `package.json:121` (`^7.6.0`; lock 7.6.0, rebased branch 7.7.0) | 5.9.2: servers 3.6+ | servers 4.4+ only (`MIN_SUPPORTED_SERVER_VERSION = '4.4'` in the driver) | SH on MongoDB 3.6/4.0/4.2 (old Docker images, old managed plans, ARM boards pinned to old builds) | see C3-2 | operator upgrades MongoDB (one major at a time; a raised feature-compatibility version is one-way), or stays on the previous Nightscout | read (driver constant) + reproduced |
| C3-2 | **On MongoDB ≤ 4.2 boot retries forever** | `lib/storage/mongo-storage.js:48` (`isRetryableConnectionError` treats every `MongoServerSelectionError` as retryable) | 5.9.2 connects | driver 7 reports the wire-version mismatch as a `MongoServerSelectionError`; the loop retries with back-off indefinitely, the HTTP server never listens, and no boot error page is shown | SH, HP, every UP and FO on the site | **glucose data silently stops arriving** after the upgrade: uploads fail to connect, followers see nothing, server alarms never start; the only signal is the repeated "Error connecting to MongoDB … retrying" log line | as C3-1 | **reproduced**: `wip/cut3-onto-16.0.0` `72c156fb` (driver 7.7.0) `lib/storage/mongo-storage.js` `init()` against `mongo:4.2` (4.2.24): no resolution after 45 s, still retrying; same code against `mongo:4.4` (4.4.24): connected in 28 ms; driver 5.9.2 against 4.2.24: connected in 32 ms |
| C3-3 | MONGODB-AWS authentication: credentials moved from the URI into a driver credential provider; `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` read as fallbacks | `lib/storage/mongo-client-configuration.js:38-57` | driver 5 read them from the URI | same inputs accepted; a URI with an access key and no secret now throws at boot | SH on AWS DocumentDB/Atlas-AWS auth | a half-configured URI that used to be tolerated stops boot | code | read |
| C3-4 | Bulk reads use `batchSize: 1000` | `lib/storage/mongo-read-options.js:6` | driver 5 default batches | same result set; bounded batches | none | — | — | read (refactor) |
| C3-5 | Docker Compose default `mongo:5.0.32` → `mongo:6.0.27` | `docker-compose.yml:12` (also on the rebased branch) | 5.0.32, with the `nofile` ulimit `dev` added | 6.0.27 (the tip also lacks `dev`'s ulimit block, a merge item) | SH using the shipped compose file | an existing data directory whose feature-compatibility version is still 4.4 (created on 4.4, upgraded to 5.0 without raising it) does not start on 6.0: the mongo container restart-loops and Nightscout retries forever, so **glucose data silently stops arriving**. MongoDB 5.0 and 6.0 are both past upstream end of life (`README.md:158` on `dev` says so) | revert the tag, if the 6.0 server has not raised the compatibility version | read (MongoDB upgrade rule not run here) |
| C3-6 | v1 `slice`/`times`/`echo` reads on a non-`entries` storage are no longer answered from the in-memory entries cache | `lib/api/entries/index.js:400` | `dev` `:407-433` can serve a `type`-only or unfiltered read for another storage from the entries cache | always queries the selected storage | UP/FO using those endpoints for treatments etc. | a correction: the response for those reads changes from cached entries to the storage's records | code | read |
| C3-7 | Authorization reload refuses a filter | `lib/authorization/storage.js:80` | `query_for(opts)` | throws `TypeError` if called with `find` | none (internal) | — | — | read (refactor) |
| C3-8 | jQuery UI bundle → `jquery-ui` 1.14; help tooltips reimplemented without the jQuery tooltip plugin; food quick-pick portions no longer shared with the food list (`cb4774ad`); authorization editor keeps drafts after a failed save | `package.json:115`, `lib/client/help-tooltips.js`, `lib/food/food.js` | jQuery UI 1.12 bundle; quick-pick add mutates the shared food record | maintained widgets; quick-pick corrections | FO, SH (admin and food pages) | presentation; the quick-pick change alters carb totals shown in the food editor's quick picks where the old shared mutation made them wrong | code | read |
| C3-9 | `engines.node` `^22.23.2 \|\| ^24.20.0` and connector `v0.0.13` tarball on the tip | `package.json:92` | `dev` is newer (`^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1`, connector `0.1.0`) | — | — | merge item (§4), already resolved on `wip/cut3-onto-16.0.0` | — | read |

### 1c. Cut 4 — `chore/mime-exposure-review` `b80aa147` (on top of cut 3)

| # | setting / behaviour | where (tip) | 15.0.9 / `dev` | cut 4 | who notices | failure mode if missed | reversibility | prov. |
|---|---|---|---|---|---|---|---|---|
| C4-1 | `TRUST_PROXY` unset = **trust nobody**; HTTPS detection only through `req.secure` | `lib/server/client-ip.js:7`, `lib/server/app.js:106` | 15.0.9 (#8754): unset = forwarded headers believed from any peer (compatibility), via `forwarded-for` | unset resolves the socket peer and ignores `X-Forwarded-Proto` | SH and HP behind a TLS-terminating edge (Heroku, Render, Railway, Fly, Azure, Northflank, reverse proxies) | every request is redirected `307` to `https://` itself, an endless loop: uploads and follower pages fail, so **glucose data stops arriving**; failed-login delay keys every visitor on the proxy's address | operator sets `TRUST_PROXY` or `INSECURE_USE_HTTP` | read |
|  | *status*: superseded. Cut 5 (`395f3207`) restored compatibility as the unset default; BF-88 (maintainer, 2026-09-23) keeps 15.0.9's resolution; the registry says no flip is planned. **Must not be taken** from cut 4's tip when cut 4 lands before cut 5 | | | | | | | |
| C4-2 | Legacy Dexcom and MiniMed bridges retired | `lib/plugins/bridge.js`, `lib/plugins/mmconnect.js` removed; `lib/server/mmconnect-connect-compat.js` (25 lines) | — | — | — | superseded by cut 1 (D2, D3); `dev`'s versions are the newer ones | — | read |
| C4-3 | Status credentials out of URLs; alarm-socket log lines without credentials | `lib/api/status.js`, `lib/api3/alarmSocket.js` | `dev` has both (#8836; alarm-socket lines already redacted on `dev`; **`storageSocket.js:63,76` on `dev` still logs the token and the message** on failure) | — | SH logs | superseded except the storage-socket log line (cut 4 changes only alarmSocket) | — | read |
| C4-4 | Moment Timezone 0.5.48 → 0.6.3 (tz data 2026c) | `package.json:118` | 0.5.48 | newer zone rules | FO and reports in zones whose rules changed in the newer data | profile time-of-day lookups (basal, ISF, carb ratio by time) and report times shift by the rule change for those zones only | code | read |
| C4-5 | Notification state owned per service and cleared on teardown | `lib/notifications.js:16` | module-level `alarms` | per `init()`; ignored after teardown | none in a single-process server | refactor on the alarm path | — | read |
| C4-6 | `mime` → `mime-types`, CSV stringify 6, semver 7, ESLint 10, webpack HMR, `expose-loader` removal | various | — | same outputs intended ("byte-level compatibility" tests for CSV) | none | refactor | — | read |

### 1d. Cut 5 — `chore/nightscout-modernization` `b1bdaca0` (#8605; on top of cut 4)

Of cut 5's 140 product files, 28 are already identical on `dev` (cut 2 carried them: page bundles,
`lib/report/statistics.js`, `lib/d3.mjs` etc.). The rows below are what remains.

| # | setting / behaviour | where (tip) | 15.0.9 / `dev` | cut 5 | who notices | failure mode if missed | reversibility | prov. |
|---|---|---|---|---|---|---|---|---|
| C5-1 | Express 4.22.2 → 5.2.1; routes rewritten as regular expressions, `'*'` → `'/{*path}'`, `/at/:at?` → `/at{/:at}`; one mutable `req.query` kept per request; query parser `qs` with `allowPrototypes`, `arrayLimit: 1000` | `package.json:110`, `lib/middleware/configure-request.js:8`, `lib/api/index.js` | Express 4.22.2, whose own extended parser already uses `allowPrototypes: true, arrayLimit: 1000` | same parse options; Express 5 semantics elsewhere | UP (every v1/v2/v3 client) | a route or parse difference would refuse or mis-read uploads; nothing identified by reading. CORS preflight: `res.send(200)` (`app.js:222`) answers JSON `200` under Express 5 instead of the text `OK` (status unchanged) | code | read (parser options compared in Express 4.22.2's `lib/utils.js:290-291`) |
| C5-2 | Helmet 4 → 8, headers composed explicitly | `lib/server/app.js:86,122` | Helmet 4 umbrella (incl. `Expect-CT`) | HSTS, Referrer-Policy, nosniff, DNS-prefetch, download-options, cross-domain-policies, hide powered-by, `X-XSS-Protection: 0`; no `Expect-CT`; CSP `useDefaults: false` | FO, HP | none expected; header diff only | code | read |
| C5-3 | Pushover: SDK replaced by a native HTTPS client; receipt cancel `GET …?token=` → `POST`; `timestamp` sent as Unix seconds; non-2xx and `status != 1` become errors; 10 s timeout | `lib/server/pushover-client.js:59`, `lib/plugins/pushover.js:77` | `pushover-notifications` 1.2.x; cancel by GET with the token in the URL | native POST | SH using Pushover; the person receiving alarms | **an alarm silently stops** if the new transport mis-sends (errors only logged). Whether the old GET cancel and Date timestamp were accepted by Pushover was not established; if not, cut 5 corrects emergency-alarm cancellation | code | read |
| C5-4 | Notification dedup and receipt caches: `node-cache` → `@cacheable/node-cache` behind a compatibility subclass | `lib/server/pushnotify.js:15-16`, `lib/utils/notification-cache.js` | node-cache 4 semantics | subclass reproduces copy-on-write and `ttl(key, 0)` | as C5-3 | a semantic gap would repeat or suppress Pushover/IFTTT alarms (**an alarm silently stops** on suppression) or lose acknowledgement receipts | code | read |
| C5-5 | APNs provider `@parse/node-apn` 5.2.3 → 8.1.0, provider created per send and shut down after | `package.json:99`, `lib/server/loop.js:135` | one provider per call, never shut down | as tip | Loop caregivers using remote overrides/carbs/bolus | remote commands fail to reach the phone; the careportal gets the completion error | code | read |
| C5-6 | EJS 3 → 6, entities 6 → 8, axios 0.34 → 1.20 (`IMPORT_CONFIG` fetch), Flot 0.8 → 4.2.6 (reports), Swagger UI 4 → 5 (`/api-docs`, `/api3-docs`), `mime-types` 3 (status `.js` pinned to `application/javascript`) | `package.json` | — | same contracts intended | FO (reports, docs page), SH (`IMPORT_CONFIG`) | report charts or docs page render differently; `IMPORT_CONFIG` failure stops boot with a boot error page (unchanged path) | code | read |
| C5-7 | API v3 `Location` header built from collection and identifier | `lib/api3/generic/create/insert.js:38` | `req.baseUrl + req.path + id` | `/api/v3/<col>/<id>`, each segment encoded | UP (v3 clients that follow `Location`) | identical for normal requests | code | read |
| C5-8 | `bin/with-env.js`, `.nvmrc`, `Dockerfile`, `azuredeploy.json` | — | `dev` newer | tip has `node:22-alpine`, `.nvmrc` `24`, `WEBSITE_NODE_DEFAULT_VERSION` hard-coded `8.11.1` | — | merge items (§4) | — | read |

### 1e. Open backfixes with default implications

| # | item | where | 15.0.9 / `dev` | proposed / decided change | who notices | failure mode if missed | reversibility | state | prov. |
|---|---|---|---|---|---|---|---|---|---|
| B1 | **BF-67/86** alarm thresholds | `lib/settings.js:309` `verifyThresholds` (`dev`) | out-of-order threshold rewritten ±1 with a server log line; `BG_LOW` entered in mmol/L on a mg/dL site stored as-is, low alarm can never fire. 15.0.9's per-threshold conversion on mmol sites is on `dev` | ladder decided 2026-10-13 (`4f083622f`): (1) announce: persistent admin notice via `env.notifies` + log line, values unchanged; (2) opt-in strict flag; (3) strict default in a major = start, disable only the invalid alarms, banner to every viewer, never refuse to start, with a restore flag for one major; (4) remove that flag a major later | SH, FO (alarm recipients) | **an alarm silently stops** (BF-86) or fires at a value nobody chose (BF-67) — today's behaviour; under stage 3, an alarm is disabled *with* a banner | per stage: flag | not started; stage 1 waits on nothing | reproduced (register gate `threshold-silent-rewrite.js`) |
| B2 | **BF-72** caller-supplied regular expressions | a branch on the advisory's private fork (on `dev`) | no bound on a caller-supplied pattern | always-on bounds on a caller-supplied pattern's size and run time, answered with an error when hit, plus an opt-in refusal of unsafe patterns (default off); exact limits and setting names are held with the advisory | UP and FO issuing pattern reads on large collections (report text search, `/times`, `/slice`) | a slow intended query gets an error instead of data | settings overrides | fix shape decided 2026-10-21; 16.0.0 only; ships with its advisory | read |
| B3 | BF-161 pattern nesting | `bf/entries-pattern-limit` `d2c4df9f` | unbounded | depth 10, 400 before expansion | as B2 | an intended pattern deeper than 10 is refused (deepest known use: 1) | code | value awaits confirmation | read |
| B4 | **BF-95** future-dated readings delay the stale-data alarm | `lib/sandbox.js`, `lib/plugins/timeago.js` | warning late by the clock skew | no design yet; option on record: a notice when readings arrive ahead of the clock by more than a tolerance | SH, FO | stale-data warning arrives late (not silent) | — | needs a design decision | reproduced (register) |
| B5 | **BF-152** v3 `settings` read by identifier | `lib/api3/generic/read/operation.js` | `api:settings:read` suffices | any gating needs AndroidAPS's answer: AAPSClient reads its settings this way | UP (AAPSClient followers) | gating by default breaks AAPSClient followers with read-only tokens | flag | open, research | reproduced (register) |
| B6 | **BF-164** non-v3 writes not broadcast on the v3 storage socket | `lib/api3/storageSocket.js` | v3 writes only | behaviour question; if adopted, broadcasting v1/socket/in-process writes | UP (AAPS NSClientV3 with `ns_use_ws`) | today: carbs/insulin entered elsewhere do not reach AAPS while its socket stays connected. A default change could make AAPS process records it did not before | flag | reclassified 2026-10-12 as a question | reproduced (register) |
| B7 | BF-175 temp-target `units: 'mmol/L'` | `lib/data/ddata.js:466` | only `'mmol'` takes the explicit branch; the `< 20` fallback converts every ordinary mmol/L target | accept both spellings | none expected: a record escapes both branches only if both targets are ≥ 20 in mmol/L | — | correction, no flag | candidate | read |
| B8 | **BF-88** `TRUST_PROXY` unset resolution | `lib/server/client-ip.js:73-75` (`dev`) | `forwarded-for` | decided: cuts keep 15.0.9's resolution; no flip planned (versioning policy §5.7 registry) | — | see C4-1 for what a flip to trust-nobody does | flag exists | decided | reproduced (register) |

### 1f. Transitional settings already shipping (candidates for the same calendar)

| # | setting | default | where (`dev`) | stated plan | who notices on a flip | failure mode on a flip |
|---|---|---|---|---|---|---|
| T1 | `API_V1_COUNT_LEADING_NUMBER` | `true` | `lib/server/env.js:111` | "switch to false in a future release" (15.0.9, #8761); `Deprecation`/`Warning` headers and a log-once line already shipped | UP: oref0 rigs (`count=N?…`) | `400 Bad count`; per 15.0.9 testing notes the rig re-uploads its last 24 h of treatments on every loop |
| T2 | `API_V1_COUNT_ZERO_WINDOW` | `true` | `env.js:112` | as T1 | UP: GluPredKit (`count=0` in a date window) | `200 []`: **glucose data silently stops arriving** for that client |
| T3 | `ALLOW_UNRESTRICTED_FRAME_EMBEDDING` | `true` | `env.js:94` | "switch to false in a future release" (15.0.8, `f7481725`) | FO: pages that embed the site from another origin | the embed shows a refused frame |
| T4 | `TRUST_PROXY` | unset (compatibility) | `env.js:43` | permanent, no flip planned | — | C4-1 |
| T5 | `UUID_HANDLING` | `true` | `env.js:102` | none stated | — | — |

When this inventory was taken, T1-T3 were not in the versioning policy §5.7 registry, which listed only `TRUST_PROXY`; they were added on 2026-10-25.

## 2. Pure refactors: ship whenever they verify

No intended operator-visible effect, read in source: C3-4, C3-7, C4-5, C4-6, C5-2, C5-7; the cut 5
lint changes (`var x = ''` → `var x;` in `ar2.js`, `basalprofile.js`, `cob.js`, `daterangedelete.js`
etc.; check each for a path that returns the unassigned value, e.g. a virtual-assistant reply);
`lib/bus.js` Stream → EventEmitter; `async` → `lib/utils/callback-tasks.js` in Alexa/Google Home;
`mongo-client-configuration.js` for non-AWS URIs (returned unchanged); Swagger `serveFiles` per mount;
ESLint, Mocha 12, webpack tooling (development only).

Refactors **on the alarm or dosing path** that need a live delivery check before they ship, even
though no default changes: C5-3 (Pushover), C5-4 (notification caches), C5-5 (APNs), C4-5
(notification state), and the maker change in §4.

## 3. Proposed calendar

### 3.1 The rule

Each change carries a **not-before date**. The announce step names that date (release notes, and an
`env.notifies` admin notice when the site is actually affected), and the change lands in the first
release of the required class cut on or after it. A strictness change becomes a default only in a
major; announce and opt-in may ship in a minor; corrections and refactors ship in any release once
verified. Nothing refuses to start (BF-67/86 decision); a refusal shows a page or a banner that
names the fix.

### 3.2 Slots

T = the 16.0.0 release date (not yet set). Offsets are proposals for maintainers and the community to decide.

| slot | release | not before | class |
|---|---|---|---|
| S0 | 16.0.0 | T | major (decided) |
| S1 | 16.1.0 | T + 8 weeks | minor |
| S2 | 16.2.0 | T + 16 weeks | minor |
| S3 | 17.0.0 | T + 6 months | major |
| S4 | 18.0.0 | T + 12 months | major |
| any | patch or minor | when verified | refactors and corrections |

### 3.3 Assignments

| slot | status quo kept | announce | opt-in strict | strict default | removal |
|---|---|---|---|---|---|
| **S0 16.0.0** | `TRUST_PROXY` unset (T4); ~~compose MongoDB 5.0.32 (C3-5)~~ superseded: 6.0 stands | BF-67/86 stage 1 (B1), if ready; release-notes dates for T1, T2, T3 and the compose change; MongoDB server-version notice (see below) | B2's opt-in refusal if its advisory publishes with 16.0.0 | already in: D1 Node floor, D2/D3 bridge removal, D4 build split. **Driver 7 (C3-1)** only if C3-2 is fixed first (decision note 1) | — |
| **S1 16.1** | | BF-67/86 stage 1 if not in S0; BF-95 notice if designed (B4); a persistent admin notice when T1/T2 tolerances are used (each already logs once) | BF-152 read gating (B5) and BF-164 broadcast (B6), each behind a flag, only once the AndroidAPS answers are in | | |
| **S2 16.2** | | | BF-67/86 stage 2 flag, naming S3; compose override for a supported MongoDB major with the upgrade guide | | |
| **S3 17.0.0** | | | | BF-67/86 stage 3 (restore flag for one major); T1/T2 → `false` if oref0 and GluPredKit releases send valid counts by then (otherwise move the date); T3 → `false`; compose default to a supported MongoDB major; driver 7 if held from S0; B2 refusal default if decided; B5/B6 defaults if decided with AndroidAPS | |
| **S4 18.0.0** | | | | | BF-67/86 restore flag; T1-T3 settings themselves |
| **any** | | | | | §2 refactors; cut 4 (no default change once C4-1 is resolved to 15.0.9's behaviour); cut 5's dependency majors (C5-1 to C5-7) after the replay lab and a live alarm-delivery check; B3 (BF-161), B7 (BF-175), C3-6, C3-8 corrections |

**Changes that can share a slot.** (a) S0: driver 7 with a MongoDB version check and the
release-notes dates for T1-T3; (b) S3: every strict default above, so operators meet one
announced breaking release rather than several; (c) cut 4 and cut 5 together in any minor, since cut
4 is an ancestor of cut 5 and cut 4 alone carries C4-1 (re-ordering is allowed; landing cut 5's
content in one step avoids shipping C4-1's interim default).

**MongoDB server-version notice** (proposal, for S0 or the release before driver 7): `dev`'s driver
5.9.2 can read `buildInfo`; a persistent `env.notifies` admin notice on servers older than 4.4 names
the release in which they stop working. This is the announce step that driver 7 otherwise skips.
