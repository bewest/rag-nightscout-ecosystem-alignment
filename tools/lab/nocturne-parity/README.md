# nocturne-parity — cgm-remote-monitor's 16.0.0 API next to Nocturne, per endpoint

*Contributor-facing.* Compares, operation by operation, the v1 and v3 API that cgm-remote-monitor
documents for 16.0.0 with what Nocturne documents and serves on the same paths. Two parts: a diff
of the two projects' OpenAPI documents, and one probe set run unchanged against both servers,
booted from pinned commits, with synthetic data only. Feeds the Nocturne row of the compatibility
specification (`docs/30-design/platform/spec/compatibility.md`) and the `HUB-REG-NOCTURNE` packet.

Result: [results/compare.md](results/compare.md) (generated; the machine-readable inputs sit
beside it).

| | commit | what |
|---|---|---|
| cgm-remote-monitor | [`d46ef808`](https://github.com/nightscout/cgm-remote-monitor/commit/d46ef808995cee266b034d6ca5a99da49c7a21df) | head of pull request [#8858](https://github.com/nightscout/cgm-remote-monitor/pull/8858): `dev` c08cbe03 plus accurate `lib/server/swagger.yaml` (v1) and `lib/api3/swagger.yaml` (v3); the repository's copies are `specs/openapi/upstream/cgm-remote-monitor/api-v{1,3}.yaml` |
| Nocturne | [`89dcaf1dd`](https://github.com/nightscout/nocturne/commit/89dcaf1dd0c4dc7e35104a9cb557ccba2b097d1c) | `main`, 2026-10-26 |

Both are in `PINS`; `run.sh` refuses any other commit. Nocturne `file:line` references below are
at `89dcaf1dd` under `src/API/Nocturne.API/` (or the path given) and are read, not run, unless a
result file is named; `api-v1.yaml:N` and `api-v3.yaml:N` are lines of the repository's copies of
#8858's documents.

## What it measures

1. **Documents.** cgm-remote-monitor's two documents against Nocturne's `nightscout` document
   (its v1–v3 surface; Nocturne builds it at run time and serves it at `/openapi/nightscout.json`,
   saved as `results/nocturne-nightscout-openapi.json`). The build-time NSwag document
   (`src/API/Nocturne.API/nswag.json`) is the `nocturne` (V4) document, so it is not the one used.
   Each operation is classed `same`, `differs` (with the aspects: query parameters, auth schemes,
   response codes, 2xx body kind, 2xx body keys or record fields), `only-crm` or `only-noc`.
   Nocturne operations outside the paths cgm-remote-monitor's two documents cover (`/api/v2/...`,
   `/pebble`) are listed but not compared: cgm-remote-monitor serves v2 too, but #8858 does not
   document it.
2. **Behaviour.** `probe.js` against each server (381 result lines per run on cgm-remote-monitor,
   351 on Nocturne, which issues no credential for the other 30), without a credential and with a
   full-access one, in two anonymous-access set-ups per server (below). Each response is reduced to
   status, content type, body shape (kind, top-level keys, the kind of an envelope's `result`,
   record field names, array length) and, for the semantic probes, named values computed from the
   body (`sem`). Probes cover every operation in both documents that the audit for #8858 probed,
   plus the semantics listed under "Semantics probed".

### Path normalisation

Written out in `ops.js`, applied to both documents before operations are joined:

1. the server URL (or a path-level `servers` override, as for `/api/versions`) is prefixed;
2. trailing slashes are dropped;
3. literal segments are lower-cased (both servers route case-insensitively; Nocturne's document
   spells controller names, `/api/v1/Entries`);
4. every path parameter becomes `{}` whatever its name (`{id}`, `{_id}`, `{spec}`, `{identifier}`);
5. cgm-remote-monitor's v3 `{collection}` is expanded to its six collections;
6. cgm-remote-monitor documents an express optional tail as one template whose description says
   trailing parameters may be left off (`/slice/{storage}/{field}/{type}/{prefix}/{regex}` is
   express `/slice/:storage/:field{/:type}{/:prefix}{/:regex}`); it is expanded to one key per
   depth (`/slice/{}/{}` … `/slice/{}/{}/{}/{}/{}`; `/times`, `/times/echo` and `/echo` likewise).
   Nocturne's document lists each depth as its own path;
7. keys join exactly first; a leftover Nocturne key joins the one cgm-remote-monitor template that
   covers it (`/api/v1/Count/entries/where` joins `/count/{storage}/where`), never the reverse
   (`/api/v1/Profile/{id}` does not join `/profile/current`).

Format suffixes (`/entries.json`) are not part of a key; probes with a suffix are counted under the
operation without it.

### Credentials

- cgm-remote-monitor: `API_SECRET` is a random value per run. The full-access credential is its
  SHA-1 in `api-secret`. For v3, which takes a JWT (the document's only scheme), the probe mints a
  subject with role `admin` and one with `readable` through `/api/v2/authorization/subjects` and
  exchanges their access tokens at `/api/v2/authorization/request/{token}`.
- Nocturne: there is no `API_SECRET` setting. `setup-nocturne.js` seeds one tenant with no sample
  data through the dev-only endpoint, signs in as its owner, and mints a direct grant with scope `*`
  (`POST /api/auth/direct-grants`). Nocturne stores the SHA-1 of the grant's token as a legacy
  secret hash (`Services/Auth/DirectGrantService.cs:175`, read, not run), so the token works as a site's API
  secret: the same SHA-1-in-`api-secret` request authenticates on v1 and v3 (measured). The
  `/api/v2/authorization/subjects` reply carries an empty `accessToken` (measured), so no JWT or
  read-only credential is issued, and the probes that need one are `not run` on Nocturne (30 per
  set-up).
- The probe uses, for v3, the first of {JWT, `api-secret`} that `/api/v3/status` accepts: the JWT
  on cgm-remote-monitor, `api-secret` on Nocturne (result `v3.credential`). Probe results are
  joined on probe id and credential class (`none`, `full`, `readonly`, or the spelling under
  test), so v3 `full` means each server's documented full-access credential.

### Anonymous access set-ups

| set-up | cgm-remote-monitor | Nocturne |
|---|---|---|
| 1 | `AUTH_DEFAULT_ROLES=denied` | the tenant's `Public` member as seeded: no permissions, 24-hour clamp on |
| 2 | `AUTH_DEFAULT_ROLES=readable` | `Public` given every read scope it accepts (`Scope.PublicShareScopes`), clamp off |

Nocturne has no site-wide default role for requests without a credential. Read, not run: the
`Public` member's permissions apply only to requests on a share-link host
(`Middleware/AuthenticationMiddleware.cs:225-227`, `context.IsShareAccess()`), and requests to the apex go
without them. Measured: set-up 2 answers anonymous apex requests exactly as set-up 1 (401 on every
data read). Share-link hosts are a different URL shape and are not probed.

## How each server is booted (`run.sh`)

- **cgm-remote-monitor**: two `lib/server/server.js` processes from the pinned tree (its own
  `npm ci`), `NODE_ENV=production`, `INSECURE_USE_HTTP=true`, the plugin list of the #8858 audit,
  one MongoDB 7 container (`--ulimit nofile=64000`), one database per set-up.
- **Nocturne**: `cargo build --release -p nocturne-alerts-ffi` in `crates/`, then `dotnet build
  -c Release -p:GenerateNSwagClient=false -p:NocturneAlertsFromSource=true` (the path the project's
  csproj names for image builds; see "Limits" for why not the default developer build). PostgreSQL
  17.6 in a container, initialised with the tree's own `docs/postgres/container-init/00-init.sh`
  (roles `nocturne_migrator`, `nocturne_app`, `nocturne_web`); passwords and `INSTANCE_KEY` are
  random per run. The API starts once in `Development` (migrations; the dev-only seed and sign-in
  endpoints), is stopped, and is measured in `Production`. Requests to `127.0.0.1` carry no tenant
  subdomain, so Nocturne resolves them to its only tenant (`Multitenancy/TenantResolutionMiddleware.cs:305,352`).
- Everything binds 127.0.0.1; containers are `npar-mongo-<pid>` and `npar-pg-<pid>`, removed on
  exit; servers are stopped by the PIDs `run.sh` recorded. Before every request, `probe.js` checks
  `/api/versions` answers 200, so a server that died mid-run fails the run instead of answering
  the negative probes.

## How results are compared

Two results are `same` when status, body kind (array, object, text, empty, null), the top-level
keys of an object body, the kind of an envelope's `result`, and the `sem` values are all equal.
Responses are never compared byte for byte. Array lengths and record field names (the keys inside
array items or inside `result`) are reported in the note column, not judged: both servers return
stored client fields and add their own. Error bodies are judged by their keys, so
cgm-remote-monitor's `{status,message,description}` against ASP.NET's
`{type,title,status,traceId}` counts as a difference. In the Operations table the measured cells
show the first full-credential probe of the operation in set-up 1, and the verdict counts every
probe of it in both set-ups.

## Semantics probed

| question | probes | crm 16.0.0 doc says | crm measured | Nocturne doc | Nocturne measured |
|---|---|---|---|---|---|
| v3 client `identifier` kept? | `v3.*.create`, `*.read.client-identifier`, `sem.v3.identifier.*` | assigned by the client, compared exactly as sent (`api-v3.yaml:1117`) | kept; v3 serves no `_id` | silent (`identifier` schema `{}`) | replaced by a 24-hex id equal to `_id`; a read by the sent identifier is 404 |
| v3 `_id` vs `identifier` on records written through v1 | `sem.v3.identifier.fromv1` | silent | `identifier` served, no `_id` | silent | `_id` served, 24 hex, equal to `identifier` |
| v3 envelope | every v3 probe | `{status,result}` on reads, `{status,identifier,lastModified}` on create | as documented | search: `V3CollectionResponse` `{data,limit,meta,skip,total}`; read: the bare record | search and history `{status,result}`; read and update of `entries` and `treatments`, and patch of `entries`: the bare record; patch of `treatments`: `{status,identifier,result}` |
| v3 re-send of the same document | `v3.*.create.again`, `sem.v3.resend.*` | 200 with `isDeduplication` (`api-v3.yaml:104`) | 200, `isDeduplication: true`; stored once | 200 for a duplicate (POST descriptions) | entries: 200 `isDeduplication: true`; treatments, devicestatus, profile: 201 without it; treatments stored once |
| v3 `limit` | `sem.limit.*` | default and maximum 1000; 0, above maximum or not a whole number: 400 | as documented | not documented | default 1000; `1001`, `100000`, `abc`: 200 with 1000; `0`: 200 with 1 record; `-1`: 400 |
| v3 history by modification time | `sem.history.old-records-written-now` | every insertion since `Last-Modified` (`api-v3.yaml:378`); records not written by v3 fall back to `date` (`:384`) | includes v1-written records dated 1–10 days ago, written now | silent | excludes them |
| v3 `history` without a timestamp | `v3.*.history.header`, `.noheader` | documented (header form) | 200 / 400 | not in the document | 404 |
| v3 `PATCH` | `v3.*.patch*` | all six collections | as documented | entries, treatments only | entries 200 (the bare record), treatments 200 (`{status,identifier,result}`); others 405 |
| v1 read window | `sem.window.*` | four days without a date filter (`api-v1.yaml:17`) | 1 and 3 days returned, 5 and 10 not | silent | same as crm |
| v1 `count` | `sem.count.*` | whole numbers; `abc`, `-3`, `1e2` 400; `N?…` read as N and `count=0` as the default or the whole date range, both with `Deprecation: true` (`api-v1.yaml:19`) | as documented | `^-?(?:0\|[1-9]\d*)$`, default 10 | `count=0` 0 records with or without a date range; `-3` 200 with 0; `5?npar` 400; `abc`, `5abc`, `3.5`, `1e1` 400; no `Deprecation` header |
| v1 delete with `count=0` | `sem.count.delete.0` | 400 | 400 | silent | 200 |
| v1 re-send dedup | `sem.dedup.*` | silent on v1 | entry, treatment: stored once; devicestatus: twice; two devices' readings at the same `date`: one returned | silent | same as crm, and also two devices' readings 60 s apart in one 5-minute clock slot are returned as one (two across a slot boundary; two from one device) |
| v1 credential spellings | `v1.entries.secret-*`, `token-query` | header, `?secret=`, `?token=`, bearer JWT | all four accepted; the plaintext secret in the header refused | header only | header, `?secret=`, upper-case SHA-1 accepted; the plaintext token in the header also accepted (it is a `noc_` token, `Middleware/Handlers/ApiKeyHandler.cs:73`, read); `?token=` and JWT not probed (none issued) |
| `/api/versions` | `api.versions` | array | array | object `{versions}` | object `{versions}` |
| v1 `/status` without a credential, set-up 1 | `v1.status*` | 401 under `denied` | 401 | silent | 200 |

The v1 rows of the table read v1 entries back with `.json`; without a suffix cgm-remote-monitor
answers v1 entries reads as text (`v1.entries.get`, `v1.entries.spec.id`), Nocturne as JSON.

## Questions for both projects' maintainers

Listed neutrally; each is a difference against the shared contract or a place the documents are
silent, not a finding against either server.

1. **v3 `identifier`.** cgm-remote-monitor's document makes the client's identifier the record's
   sync identity; Nocturne answers with its own id and a read by the client's identifier is 404.
   Should the shared contract require the client identifier to be kept (and readable), and should
   Nocturne's document state what it does? (Nocturne issue #1932 discusses the same field.)
2. **v3 read and write envelopes.** Nocturne's document describes v3 search as
   `{data,limit,meta,skip,total}`; it serves `{status,result}`, as cgm-remote-monitor documents.
   Its read, update and patch answer the bare record. Which shape is the contract for each
   operation, and should each document match its server?
3. **v3 `limit`.** Out-of-range and malformed values: refusal (cgm-remote-monitor's document) or
   clamping (Nocturne measured)? `limit=0` returning one record on Nocturne is outside both.
4. **v3 history.** Should records written through v1 enter `history/{lastModified}` when they are
   written, or by their `date`? cgm-remote-monitor's document says both (`:378`, `:384`); the two
   servers measure differently.
5. **v1 `count=0` and the leading-number form.** cgm-remote-monitor keeps 15.0.8's readings with a
   deprecation header; Nocturne answers an empty list and refuses `N?…`. Clients known to send
   these (oref0's `count=1?…`, GluPredKit's `count=0` with a date range) read differently on each.
6. **v1 cross-device readings in one 5-minute slot.** Nocturne returns one of two devices'
   readings 60 s apart in the same clock slot; cgm-remote-monitor returns both. Not documented on
   either side. Whether the second reading is stored and hidden or merged is not measured.
7. **Credential surface.** Nocturne accepts `api-secret` on v3 and issues no v2 access token or
   JWT; cgm-remote-monitor's v3 takes only a JWT. Which credentials should a client of the
   shared contract expect on each version?
8. **Documents.** Each document lists operations the other server lacks (Counts in compare.md):
   Nocturne serves no `/entries/preview`, `/echo`, `/googlehome`, `/notifications/pushovercallback`,
   v3 `history` without a timestamp, and v3 `PATCH` outside entries and treatments; its document
   lists v1 `PUT`/`GET` by id, `/iob`, `/debug/*` and v3 `bulk`, which cgm-remote-monitor does not.

## Files

| File | What it is |
|---|---|
| `PINS` | the two commits |
| `fetch-trees.sh` | clones both repositories at the pins; `npm ci` in the cgm-remote-monitor tree |
| `run.sh` | everything below; `--compare-only` re-renders `compare.md` from existing results |
| `boot-crm.sh`, `boot-nocturne.sh` | start one server, record its PID |
| `setup-nocturne.js` | tenant, owner sign-in, full-access grant; the `Public` member for set-up 2 |
| `probe.js` | the probe set |
| `ops.js`, `docdiff.js` | path normalisation; the document diff |
| `compare.js` | `results/compare.md`; `--selftest` checks the comparator |
| `results/probe-{crm-denied,crm-readable,noc-public-none,noc-public-read}.jsonl` | one line per request |
| `results/docdiff.json`, `results/nocturne-nightscout-openapi.json` | the document diff; Nocturne's document as served (its `servers` entry set to `/`) |
| `results/meta.json`, `results/nocturne-public-read-setup.json` | commits, file hashes, tool versions; the set-up 2 change as Nocturne reported it |

## Run

Needs docker, git, curl, openssl, the .NET 10 SDK, cargo (rustup installs the toolchain Nocturne's
`crates/rust-toolchain.toml` names) and Node.js 22 or later.

```sh
tools/lab/nocturne-parity/fetch-trees.sh /tmp/npar-trees
NODE="n exec 24 node" tools/lab/nocturne-parity/run.sh /tmp/npar-trees/crm-d46ef808 /tmp/npar-trees/nocturne-89dcaf1dd
```

About three minutes after the first build. Ports default to 17461, 17462, 17470, 27460 and 25460
(`CRM_PORT_DENIED`, `CRM_PORT_READABLE`, `NOC_PORT`, `MONGO_PORT`, `PG_PORT`); `run.sh` stops if
one is taken. Logs go to `$LOGS` (a temporary directory by default) because they carry local
paths; nothing secret or local is written to `results/`: paths are recorded with the secret, its
SHA-1, tokens and server-assigned identifiers replaced by placeholders, and bodies only as shapes.

`run.sh` refuses to run when a tree is not at its pin or has local changes, when the repository's
copies of #8858's documents differ from the tree's, or (with `--compare-only`) when the results were
made by another `probe.js`, `ops.js` or `docdiff.js` or other commits. After each run it checks the
comparator (`compare.js --selftest`) and the table: it changes one Nocturne status in a copy of the
results and requires `compare.md` to change on that probe's lines only. Two consecutive runs on
2026-10-26 gave byte-identical `compare.md`; the `.jsonl` files change on every run (times, paths).

## Limits

- Not probed: the v2 surface, `/pebble`, websockets, Nocturne's V4 API, share-link hosts, the
  operations only Nocturne documents (`/iob`, `/debug/*`, v1 by-id `GET`/`PUT`, v3 `bulk`), and
  `?token=` or JWT credentials on Nocturne (none issued).
- v3 probes send minimal documents (`date`, `app`, `device`, `identifier`, plus `eventType` or
  `sgv`), as the #8858 audit did. Nocturne refuses them for `food` and `settings` (400 "Invalid
  request data") and answers 404 on reads of the `devicestatus` and `profile` it created from them;
  a fuller document may be answered differently. Not probed.
- One configuration per server: cgm-remote-monitor with the defaults of its settings
  (`API3_DEDUP_FALLBACK_ENABLED`, `API_V1_COUNT_*` and the rest), MongoDB 7, Node 24; Nocturne in
  `Production` with one tenant at the apex, PostgreSQL 17.6. Nocturne's document was taken from the
  `Production` server; the `Development` document was not compared.
- Nocturne's default developer build did not complete on Linux with .NET SDK 10.0.113: MSBuild
  could not load the inline task source `build\NocturneAlertsResolveLibrary.cs`
  (`src/Core/Nocturne.Core.Alerts.Native/Nocturne.Core.Alerts.Native.csproj:115`, error reported
  at 121,9), a path written with a backslash.
  `run.sh` uses the csproj's image-build path instead (`NocturneAlertsFromSource=true`, library
  built by cargo). Measured once; other SDKs not tried.
- Derived from the route audit for #8858 (its `probe.js`, 325 requests, and `boot.sh`): the v1, v2
  and v3 request list is kept. Changed: the secret is per run and never written out; requests carry
  an operation key and a credential class; v3 per-record probes address the identifier the server
  answered with, and reading by the sent identifier is its own probe; the history-by-timestamp
  probe asks for `limit=1000` (all of the run's changes, a fixed set) instead of 5; bodies are
  reduced to shapes; the semantic probes are new.
