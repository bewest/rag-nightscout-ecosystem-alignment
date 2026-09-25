# Modernization-only security commits: which fix a defect on dev

*Contributor-facing. Snapshot, 2026-09-22. Historical: the two backports this triage selected are
merged into `dev` as #8751 (BF-104, BF-105), not released. Queue item `BF2-BACKPORT`; the release decision is in the
[15.0.9 decisions](../../../releases/cgm-remote-monitor-15.0.9/decisions.md).
Measured 2026-09-22 against `origin/dev` `74fc6619` (15.0.9), the modernization branch
`origin/chore/nightscout-modernization` `b1bdaca0`, and the shipping release
`origin/master` `92d08342` (= v15.0.8). Storage: `mongo:7` in Docker. Node `22.23.2` via
`n exec`. Every DEFECT-ON-DEV row was reproduced by booting the tree and issuing the request,
with a control in the same run; nothing here is graded from reading alone.*

**Details withheld.** Four defects below are live on the shipping release (15.0.8). This repository
is public, so they are described by mechanism only: no request shapes, route/grant combinations or
log excerpts. The probes and raw outputs are kept outside version control. The fixes for `31c354d8` and
`d3ac8026` are already public on the modernization branch (PR #8605), so the mechanism is not new
information; the reproduction would be.

## Method

Each candidate was read (diff + message + its tests), then its defective code path was checked
on `origin/dev`. For a DEFECT-ON-DEV verdict a probe was run against a booted `origin/dev`
server showing the defect, plus a control — the same probe against the modernization tree (the
fixed arm), and, where authorization is involved, both `AUTH_DEFAULT_ROLES=readable` (shipped
default) and `AUTH_DEFAULT_ROLES=denied` arms. Anonymous access is only a defect where it
survives `denied`; see the standing control
[advisory-auth-configuration-matrix-2026-09-21](advisory-auth-configuration-matrix-2026-09-21.md).
Liveness was asserted in the same run (a `GET /api/v1/status.json` before and after each probe).
Servers were launched detached (`setsid nohup … < /dev/null &`) against one dedicated Mongo
container (`ns-w4-mongo`, port 27084). Probes, launch scripts and raw outputs are held under
`externals/work/crm-w4-dev/tmp/` (gitignored; `.gitignore` line 32 ignores `tmp/`).

The sweep for further security-shaped commits used
`git log --no-merges origin/dev..origin/chore/nightscout-modernization` (498 commits) filtered
by path (`lib/authorization`, `lib/server/websocket.js`, `lib/api3/security*`,
`lib/api3/alarmSocket.js`, `lib/api/status.js`, `lib/server/app.js`, `lib/server/env.js`,
`lib/admin_plugins`, `lib/api/entries`, `lib/api3/generic`, `lib/api3/shared`) and by content
(`-G` over `console.*(token|secret|password|api_secret|credential|jwt|href)`). Additions found
this way are the last four rows below.

## Verdicts

| commit | subject | verdict | live on 15.0.8 | backport |
|---|---|---|---|---|
| `31c354d8` | Stop logging alarm subscription credentials | **DEFECT-ON-DEV** (low–med) | yes | on `bf2/backports` (code verbatim; test adapted to dev socket) |
| `d3ac8026` | enforce read permissions for selected count and slice storage | **DEFECT-ON-DEV** (medium) | yes | on `bf2/backports` (code verbatim; dropped mod-only doc hunk) |
| `973a2849` | Keep status bootstrap credentials out of URLs | **DEFECT-ON-DEV** (low; CWE-598) | yes | not built — client/browser evidence; recommend follow-up |
| `71c42c9a` | restrict authorization reloads to complete snapshots | **NOT-A-DEFECT** (hardening; no reachable filter path) | n/a | none |
| `d48be5e5` | preserve authorization editor drafts after failed saves | **DEFECT-ON-DEV** (non-security; UX/data-entry) | yes | not built — browser-only test; recommend follow-up |
| `ad4a8cd5` | Compose explicit Helmet headers | **NOT-ON-DEV** (defect introduced by the Helmet 8 upgrade) | no | none |
| `0367aee5` | Upgrade Helmet 4→8 | **NOT-ON-DEV** (modernization-only; not a fix) | no | none |
| `479a6a4d` | reject custom pipelines in the count API | **NOT-ON-DEV** (already on dev via BF-70/#8743) | fixed on dev | none |
| `924aa8d7` | reject JavaScript operators in MongoDB queries | **NOT-ON-DEV** (already on dev via BF-70/#8743) | fixed on dev | none |
| `f2ebd7d4` | restrict slice cache reads to entries storage | **UNSETTLED** (correctness; not reproduced this run) | likely | none yet — see notes |
| `8458f39e` | retain import client without leaking configuration | **DEFECT-ON-DEV** (low; conditional on IMPORT_CONFIG) | yes | not built — recommend follow-up |

Branch `bf2/backports` (worktree `externals/work/crm-bf2-backports`, off `origin/dev`
`74fc6619`) carries the two DEFECT-ON-DEV candidates whose break-it test runs in the backend
suite. The other DEFECT-ON-DEV candidates (`973a2849`, `d48be5e5`, `8458f39e`) are real but
their break-it evidence is client-side / browser-only / boot-error-page, out of this backend
run; each is a recommended register entry and follow-up below.

## Per-candidate notes (mechanism only)

### 31c354d8 — alarm socket logs the submitted credential — DEFECT-ON-DEV, live on 15.0.8
`lib/api3/alarmSocket.js` prints the caller-submitted `accessToken` / `jwtToken` / whole
`message` to stdout on an authorization failure. Reproduced on `dev` and on `v15.0.8`: an
`/alarm` subscribe with a credential that fails resolution writes that credential to the server
log verbatim; a JWT recovered from the log decoded to the real access token and authenticated a
REST read (200). The modernization tree (control) writes a fixed message with no credential.
Not previously in the register (the register's socket entries #8745/#8746 are scope/ack, not
logging; BF-05 is `aggregate.js` logging). Severity is bounded by requiring read access to the
log, so low–medium. Backported: the three-line `alarmSocket.js` change applies verbatim; its
bundled test targeted the modernization branch's `alarmSocket.js`, which predates dev's
#8745/#8746 socket-scope fixes, so the success-path fixture was adapted to dev's socket
(`socket.join`, an `auth` object carrying `shiros`) and the pre-#8746 ack-count assertions were
dropped (dev covers those in `api3.alarm-socket.ack.test.js`). The credential-privacy
assertions are unchanged and fail on unpatched dev.

### d3ac8026 — a per-collection read grant is not checked on two shared routes — DEFECT-ON-DEV, live on 15.0.8
Two v1 routes mounted under the entries router choose which collection to read from a path
parameter (`prep_storage` in `lib/api/entries/index.js`). The router is gated only on the entries read
permission, so a credential scoped to entries can read other collections through them. Reproduced on
`dev` and on `v15.0.8` under `AUTH_DEFAULT_ROLES=denied`, so the credential's own grant is the only
entitlement. The modernization tree (control) refuses the same request, and allows it only with the
matching per-collection grant; the entries-only case is allowed on every tree (positive control). On
the shipped `readable` default there is no marginal exposure, because anonymous access already reads
every collection. The defect bites a hardened install that issues scoped tokens, where it is a
cross-collection authorization bypass (CWE-863). Not in the register (BF-01/#8738 is count
correctness, a different mechanism). Backported: the `prep_storage` hunk applies verbatim; only the
modernization-only `docs/runtime-upgrade.md` hunk was dropped (absent on dev). Test and test-spec apply
unchanged.

### 973a2849 — status bootstrap credential travels in the URL — DEFECT-ON-DEV (low; CWE-598)
`lib/client/index.js` builds the boot `status.json` request as
a status request whose query string carries the API-secret hash or the subject JWT, and `lib/api/status.js` reads the
credential from `req.query`. The credential (the API-secret SHA-1 hash, or the subject JWT)
therefore lands in browser history, reverse-proxy and CDN access logs, and `Referer` headers —
sensitive information in a URL query string. Present on dev source and the shipped client;
confirmed at runtime that dev honours query credentials on `status` (so what is placed in the
URL is a working credential). This is credential hygiene, not an access bypass, so the
`denied`-survival control does not apply. Not built onto the branch: the defect is client
behaviour and the modernization break-it evidence is the browser page-startup suite
(`tests/browser/page-startup.test.js`) plus the header-vs-query status backend test (which
passes on both trees because both honour headers, so it is a compatibility test, not a
break-it). Recommend a register entry and a follow-up port of the client+server change together
with the browser assertion. The commit's delete-query-guard half is tests only (no code
change) and overlaps BF-70's operator work already on dev.

### 71c42c9a — authorization reload filter surface — NOT-A-DEFECT (hardening)
Removes the shared query-builder from `listRoles`/`listSubjects` so a reload can only issue an
empty filter. On dev the only callers are the internal `reloadAuthorizationData` at
`lib/authorization/storage.js:163,180`, both passing `{sort:{name:1}}`; the HTTP subject/role
endpoints (`lib/authorization/endpoints.js`) serve the cached `storage.subjects`/`storage.roles`
arrays and never forward a request query to these helpers. No request-controlled filter reaches
the surface, so there is no reachable defect — this is defense-in-depth against a CodeQL taint
alert (the commit says as much). No backport.

### d48be5e5 — admin editor drafts lost on a failed save — DEFECT-ON-DEV (non-security)
On dev, `lib/admin_plugins/roles.js` and `subjects.js` close the jQuery-UI dialog in the save
callback regardless of whether the POST/PUT failed, and `subjects.js` drops the error before
invoking its callback — so a failed save silently discards the operator's unsaved draft. Real
defect on dev, but it is a UX / data-entry loss with no exposure or authorization consequence,
so out of the security scope of this branch. Its break-it test is browser-only
(`tests/browser/admin-dialogs.test.js`, Playwright/jQuery-UI). Recommend a low-priority
non-security register entry and a follow-up port run under the browser harness.

### ad4a8cd5 / 0367aee5 — Helmet — NOT-ON-DEV
`0367aee5` upgrades Helmet 4→8 (modernization-only); `ad4a8cd5` then remediates a CodeQL
`js/insecure-helmet-configuration` alert created by passing `false` cross-origin options to the
Helmet-8 umbrella call. Dev runs Helmet `^4.0.0` and passes no such options. Measured headers
on the HSTS path (`INSECURE_USE_HTTP=false SECURE_HSTS_HEADER=true`) are **identical** between
dev and the modernization tree for every security header (`strict-transport-security`,
`x-content-type-options`, `x-dns-prefetch-control`, `x-download-options`,
`x-permitted-cross-domain-policies`, `x-xss-protection`, `referrer-policy`,
`content-security-policy` byte-identical when `SECURE_CSP=true`), the only difference being that
dev additionally emits the deprecated `Expect-CT: max-age=0` (an "off" value, harmless), which
Helmet 7+ removed. Dev is missing no security header and weakens none. The remediated defect
does not exist on dev; it would be introduced by the Helmet upgrade. No backport.

### 479a6a4d / 924aa8d7 — already on dev — NOT-ON-DEV
Both are the modernization ancestors of the query-operator work that landed on dev as BF-70
(PR #8743). Dev already carries `lib/storage/assert-no-query-javascript.js`,
`lib/server/query-operator-allowlist.js`, `aggregate.js`'s `refusePipeline`, and the `query.js`
`assertNoQueryJavascript(params.find)` guard. The `$where`/`$function` rejection and the count
`pipeline` refusal are present on dev by inspection of the shipped modules. No backport (and see
the live BF-72 `$regex` DoS, which none of these close).

### f2ebd7d4 — slice cache returns the wrong collection — UNSETTLED (correctness)
On dev, `query_models` (`lib/api/entries/index.js`) serves a type-filtered slice from
`ctx.cache.entries` whenever a `type` query is present, without checking `req.storage`, so
`/slice/treatments/.../sgv` (and devicestatus) can be answered from the entries cache instead of
the requested collection. The fix adds `inMemoryPossible = storage === ctx.entries`. The
mechanism is visible in the dev source, but the reproduction attempt this run did not exercise
the cache path (the positive control — an entries slice served from cache — also returned
empty, because the date-prefix filter excluded the seeded records and the cache was not warmed
as intended), so per read-or-run this is left UNSETTLED rather than asserted. It is a
data-correctness defect, not security. Recommend a dedicated cache-primed reproduction before
filing/backporting.

### 8458f39e — IMPORT_CONFIG diagnostics leak the config URL and settings — DEFECT-ON-DEV (low)
On dev, `lib/server/bootevent.js` logs `Getting settings from <href>`, `extending settings with
<settings>`, and on failure `Attempt to fetch config <href> failed. <err.response>`, and pushes
the full `err` (with response) into `ctx.bootErrors`, which `lib/server/booterror.js`
`JSON.stringify`s onto the 500 boot-error page served to any visitor. Where `IMPORT_CONFIG`
carries credentials in the URL or the response echoes secret settings, those reach the log and
the public error page. Real on dev and shipping, but gated on `IMPORT_CONFIG` being configured,
so low. The modernization fix redacts to a fixed message plus numeric status. Not built onto the
branch (the fix is entangled with the Axios dependency move in the same commit family, and the
break-it is a boot-error-page assertion). Recommend a register entry and a targeted port of the
`bootevent.js`/diagnostics half only.

## Proposed register entries (coordinator allocates BF- ids)

1. **Alarm socket logs the submitted credential** (`31c354d8`). `lib/api3/alarmSocket.js`
   prints `accessToken`/`jwtToken`/`message` on auth failure. Reproduced on dev + v15.0.8; a
   JWT recovered from the log authenticated a REST read. Low–med (needs log access). Fixed on
   `bf2/backports`.
2. **A credential scoped to entries reads other collections through two shared routes** (`d3ac8026`).
   CWE-863. Reproduced under `denied` on dev + v15.0.8; the control (modernization) refuses. Medium on a
   hardened/scoped-token install; zero marginal on the `readable` default. Fixed on
   `bf2/backports`.
3. **Status bootstrap credential travels in the status.json URL** (`973a2849`). CWE-598.
   Client puts the API-secret hash / JWT in the query string; server reads it from the URL.
   Low. Follow-up (client + browser test).
4. **Admin authorization editor loses drafts on a failed save** (`d48be5e5`). Non-security
   UX/data-entry loss; dev closes the dialog and discards the draft on a failed POST/PUT.
   Follow-up (browser test).
5. **IMPORT_CONFIG diagnostics leak the config URL and settings to logs and the boot-error
   page** (`8458f39e`). Low, conditional on `IMPORT_CONFIG`. Follow-up.
6. **(candidate) Slice cache can answer a non-entries slice from the entries cache**
   (`f2ebd7d4`). Correctness; UNSETTLED pending a cache-primed reproduction.

## Suite

Full backend suite (`npm test`, Node 22.23.2, `mongo:7`) on `origin/dev` `74fc6619` and on
`bf2/backports`, back to back against the same Mongo container (separate databases):

| tree | passing | pending | failing |
|---|---|---|---|
| `origin/dev` `74fc6619` | 2386 | 3 | 0 |
| `bf2/backports` | 2398 | 3 | 0 |

The +12 is exactly the two new test files (10 alarm-logging cases + 2 storage-read-permission
cases); no existing test changed result. Break-it, verified against unpatched dev: the 6
credential-privacy alarm cases fail with *"credentials must stay out of logs"* and the
entries-only storage case fails, on `origin/dev`; all pass on `bf2/backports`.

## Backport commits (branch `bf2/backports`, worktree `externals/work/crm-bf2-backports`, off `origin/dev` `74fc6619`)

| commit | defect | files |
|---|---|---|
| `9c50788e` | 31c354d8 — alarm socket credential logging | `lib/api3/alarmSocket.js`, `tests/api3.alarm-logging.test.js` |
| `b5038500` | d3ac8026 — count/slice storage read permissions | `lib/api/entries/index.js`, `tests/storage-read-permissions.test.js`, `docs/test-specs/storage-read-permissions.md` |

(Commit SHAs are from this run; the branch has not been pushed.)
