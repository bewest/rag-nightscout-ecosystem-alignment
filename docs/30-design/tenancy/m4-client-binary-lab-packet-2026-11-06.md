# M4 existing-client surface: client-binary lab packet

*Contributor-facing dispatch packet, 2026-11-06. Batch B6 of the
[integration batching plan](multitenant-integration-batching-plan-2026-11-06.md).
**Read-derived throughout:** every statement below comes from reading files in this
repository and the cumulative cgm-remote-monitor worktree; no test was run, no service
was started, no client was executed. Every prediction is a hypothesis for the lab to
refute. The packet promotes no milestone and claims no runtime result.*

| Anchor | Value, read from `git rev-parse` at the moment of writing |
|---|---|
| Alignment `main` when this packet was started | `c57589e9b553af0dafdcce49d96b3ad4b448a30c` |
| Alignment `main` at the final check | `18a9a5420c062aeb6cfe195d0fc0d5fd096509e2` (one commit later: the batching plan committed; its B6 row is unchanged) |
| Cumulative CRM head under test, branch `codex/serial-integration-20261106` | `35903069b46974cfbaddd8dce00c994fb2562bc3` (published as draft #8898's head on 2026-11-06, per the batching plan §1) |
| Evidence that frames this packet | [R40](../remedial/rc-16.0.0-integration-record.md#r40---derived-rest-and-pinned-pattern-cumulative-acceptance-on-ded254b9-2026-11-04), [R41](../remedial/rc-16.0.0-integration-record.md#r41---subject-administration-and-cross-compatibility-on-94c57f1f-2026-11-05), [R25](../remedial/rc-16.0.0-integration-record.md#r25---tenant-credentialcurrent-authority-get-on-7eb76c71-2026-11-03), [R26](../remedial/rc-16.0.0-integration-record.md#r26---dormant-tenant-exchange-to-get-on-81bc71e6-2026-11-03), [R48](../remedial/rc-16.0.0-integration-record.md#r48---local-public-token-verification-through-actual-api-on-3d5eac19-2026-11-05) |

CRM paths below are relative to that worktree at `35903069`; alignment paths are relative
to this repository. `file:line` cites the lines actually read.

## 1. What M4 asks for, and what today's evidence is

The [roadmap §4](multitenant-delivery-roadmap-2026-11-02.md) criterion for M4: *v1 and v3
uploader/follower shapes exercised on pinned versions; no coordinated app upgrade
requirement; tenant-local identity and correct batch/retry/refusal semantics.* The
[dashboard](multitenant-delivery-dashboard.md) adds: *actual client execution distinguished
from source-pattern replay*, with M4 `blocked` on M3.

Today's client evidence is **source-pinned synthetic replay**, not client execution:

- R40 pins NightscoutKit `4ec9fd12` and LoopFollow `4a74b781` and says *"this is extracted
  client-pattern replay, not execution of Swift binaries"*. R41 repeats *"server contracts and
  synthetic client patterns, not execution of client applications"*. The owned runner's README
  says the same (`tools/lab/multitenant-rest-preview/README.md`).
- The CRM test that does it is `tests/tenant-rest-client-replay.integration.test.js`
  (opt-in `NS_REST_CLIENT_REPLAY_TEST=1`), whose fixture
  `tests/fixtures/client-replay-patterns.js:5-8` states *"Source-derived synthetic patterns,
  not execution of either Swift application."* Its deployment fixture
  `tests/fixtures/client-replay-http.js:3` boots *the shipping multitenant CLI* as a child
  (`:98`, `bin/nightscout.js multitenant api`) with two tenants in `direct-alias` resolution
  (`:45-47`) and selects the tenant with an explicit `Host` header (`:136-142`).
- The November 2 draft PR body in this directory
  (`multitenant-draft-pr-body-2026-11-02.md`, a peer's file) carries only the M1–M3
  "remains open" statements; the client-binary wording lives in R40/R41 and in the CRM
  READMEs, and in the live #8898 body the maintainer refreshed from R54, which is not in
  this repository.

So M4's gap is exactly: **run real client programs, at their pinned versions, against the
preview executable, and classify every difference from single-site Mongo.** This packet
ranks which clients can be run at all on a Linux lab host, designs the lab for the top
three, and names what stays unmeasured afterwards.

## 2. What credential an unmodified legacy client presents, and what the preview accepts

### 2.1 Shipping single-site extraction (what every client was written against)

`lib/authorization/index.js` at `35903069` (shipping, unchanged by the preview):

| Carrier | Where the server reads it | Line |
|---|---|---|
| `Authorization: Bearer <jwt>` | `extractJWTfromRequest` | `:34` |
| `?token=<accessToken>` in the query | `req.query.token` | `:40` |
| `?secret=` in the query, else the `api-secret` header | `apiSecretFromRequest` | `:76` |
| the admin secret hash as `api-secret` | `authorizeAdminSecret` | `:178` |
| a subject access token presented in the `api-secret` header | `doesAccessTokenExist(data.api_secret)` | `:201-203` |

The journey lab catalogues the same dialects per app (`tools/review/journey-lab/clients.js:13-19`):
`secret` (api-secret header = SHA-1 of the API secret: Loop, Trio, LoopCaregiver, xDrip),
`jwt` (Bearer from the v2 exchange: AAPS v3, nightguard v3), `token-query` (LoopFollow,
Nightscout Reporter), `token-path` (the exchange request itself), `token-header` (raw access
token in `API-SECRET`: nightguard v1), `socket` (AAPS NSClient v1 `authorize`).

### 2.2 The preview's extraction and verification

The preview reads credentials through its own extractor and verifies them inside the
tenant's secrets boundary; nothing from the single-site enclave is reused.

| Rule | Source |
|---|---|
| Only the `authorization` and `api-secret` headers are read; a duplicated header makes the request invalid | `lib/authorization/credential-extraction.js:17-22` |
| `Authorization: Bearer <token>` → carrier `bearer` (v3 accepts any case of `bearer`; v1/v2 require exactly `Bearer`) | `:32-38` |
| **API3 (`/api/v3`)**: a `token` or `secret` in the query or body makes the request **invalid**, never anonymous; `api-secret` header only | `:40-43`; `lib/secrets/legacy-credentials.md:96-99` |
| **v1/v2**: `api-secret` from `req.api_secret`, `?secret=`, the header, or a body `secret`; token from Bearer, else `?token=` or a body `token` → carrier `legacy` | `:44-59` |
| A presented-but-empty credential is invalid; a supplied invalid credential never becomes anonymous | `:61-62`; `legacy-credentials.md:52-54` |
| A `legacy`-carrier token is first exchanged (`secrets.exchangeLegacyCredential`, the R26 path) and the issued JWT is then verified; an `api-secret` goes straight to `verifyLegacyCredential` (the R25 path) | `lib/server/tenant-app/data-access.js:108-116` |
| A new-format Ed25519 token (`typ: ns-access+jwt`, R48) is recognised first and verified locally against operator-provisioned public keys and current PostgreSQL state; no legacy fallback for a recognised new token | `data-access.js:98-107`; `lib/tenant-authorization/access-tokens.md:3-6, 44-50, 66-70` |
| Root verification and subject derivation reproduce the shipping `enclave.js` / `authorization/storage.js` SHA-1 forms, against the tenant's imported root reference and stable subject IDs | `legacy-credentials.md:63-69` |
| The v2 exchange `GET /api/v2/authorization/request/:accessToken` is mounted only when the trusted `exchange` callback is injected; the path credential is the sole input; root credentials do not exchange; issuance is exactly eight hours | `lib/server/tenant-app/README.md:152-168, 181-187` |
| Revocation: a request begun after a committed reference/grant removal performs new reads and refuses; no stale-success cache | `legacy-credentials.md:107-110` |
| Pre-existing single-site JWTs are not assumed portable | `legacy-credentials.md:77-81` |
| v1 and v2 data routes are composed from the shipping `lib/api` and `lib/api2` factories with tenant-local storage ports (`createV1(... { domains, apiEnabled: true })`, `createV2(... { compatibilityOnly: true })`) | `lib/server/tenant-app/legacy-domains.js:4-5, 23-25` |
| Tenant selection is by the wire `Host` against configured aliases (`direct-alias`), or by canonical internal names behind a trusted immediate peer (`canonical-internal`); no resolved-tenant header selects a tenant | `lib/tenant-resolution/index.js:58-71, 95, 128`; `lib/server/serve/preview-config.js:90-109` |

**Finding.** An unmodified legacy client that sends the SHA-1 `api-secret` header (the
Loop/Trio/xDrip/oref0/connector dialect) or a Bearer JWT obtained from the v2 exchange (the
AAPS v3/nightguard/librelink-up dialect) presents a shape the preview accepts on both v1 and
v3. A client that puts its token in the **query** (LoopFollow, oref0 token mode, Reporter)
is accepted on **v1/v2** through the legacy-exchange path and **refused on v3**. The
pinned-pattern replay already relies on this split
(`tests/tenant-rest-client-replay.integration.test.js:24-27`: *"the pinned uploader hashes its
API secret and sends api-secret; the pinned follower sends its subject token in the query"*;
`tests/fixtures/client-replay-patterns.js:66-76` builds the follower path with `token` in the
query for v1 and v2). The intentional multitenant difference is that a supplied invalid
credential refuses instead of falling back to anonymous
(`tenant-app/README.md:252-260`). No pinned client emits a new-format Ed25519 token; R48's
readers are an addition, not a requirement, and this is consistent with the roadmap's "no
coordinated app upgrade" criterion.

What the lab must establish rather than assume: that the v1 legacy domains composed by
`legacy-domains.js` carry the shipping `count` tolerance (`RT-COUNT-COMPAT`) and the
shipping treatments write validation. Both are inherited by construction and both are
`UNMEASURED` on the preview.

## 3. Pinned client inventory, ranked by executable feasibility

Pins are the `ref` values in `workspace.lock.json`. The checked-out head under `externals/`
was read with `git rev-parse HEAD` and is listed where it differs. Survey pages under
`reports/consumer-impact-15.0.9/clients/` and the compat catalogue
`tools/qc/results/write-contract-matrix/compat-16.0.0/client-shapes.json` supplied the API
surface and credential shape; their `file:line` anchors are repeated here only where load-bearing.

Feasibility classes: **A** runs headless on Linux with no vendor cloud and no device;
**B** runs headless on Linux but needs a vendor-cloud stand-in that does not exist in this
repository; **C** JVM library inside an Android project (headless possible, build cost
unmeasured); **D** Android application (emulator); **E** iOS/watchOS application (Apple
toolchain and device or simulator; out of scope for an automated Linux lab);
**F** not a Nightscout API client, or retired.

| Rank | Client (lock alias) | Class | How it would run | API surface | Credential shape | Pinned version source |
|---|---|---|---|---|---|---|
| 1 | **nightscout-connect** (`ns-connect`) | A | Node CLI `bin/nightscout-connect`; the `forever` command selects the HTTP output `nightscout` (`commands/forever.js:50`); the `nightscout` *source* reads a remote site. Already executed as a real module by the id-batch-replies lab (`tools/lab/id-batch-replies/RESULTS.md`, "nightscout-connect was run"), the journey lab's `cgm-*` sites (real Dexcom driver against `fake-share.js`) and the connector-soak lab (`tools/lab/connector-soak/lab.sh:1-16`, sinks K1 token / K2 secret) | writer: v1 POST entries/treatments/devicestatus/profile; reader: v1 entries/treatments GET with `count`/`find`, v2 exchange | writer: `API-SECRET` header = SHA-1 (`lib/outputs/nightscout.js:39`); reader: pre-issued subject token exchanged at `/api/v2/authorization/request/<token>` then `Authorization: Bearer` (`lib/sources/nightscout.js:50, 171-184`); without a token it tries to **create a subject** with the API secret (`:148-151`), a route the preview's data plane does not mount | lock `b394411a` (main, 2026-07-16). **Checkout is `04102f9d`** and `package.json` says `0.1.1`; the CRM at `35903069` depends on `nightscout-connect` `0.1.0` (`package.json:139`). The lab reads the version from the package it runs, never from the lock |
| 2 | **oref0** (OpenAPS rigs) | A | bash + curl + node scripts (`bin/ns-upload.sh`, `bin/ns-get.sh`, `bin/nightscout.sh`, `bin/oref0-upload-profile.js`); rigs are Linux. Needs `jq` and GNU `date`; the loop itself (`oref0-ns-loop.sh`) is not needed, only its Nightscout steps | v1 POST entries/treatments/devicestatus (`ns-upload.sh:12`), v1 GET treatments with `find[enteredBy]`+`count` and entries `sgv.json?count=`, profile GET/PUT, `status.json` | either `API-SECRET` header = SHA-1, or the literal `token=<t>` appended to the **query** (`bin/ns-upload.sh:38-50`); the `latest-openaps-treatment` lookup sends `count=1?<credential>` (survey §2.1, reproduced in the 15.0.9 replay lab P1), which also puts the credential in the URL | lock `d219baf9` (dev); checkout matches |
| 3 | **cgmsim-lib** | A | Node/TypeScript library (`dist/index.js`); a few lines of driver script call its upload/download functions | v1 POST `/api/v1/entries/`, GET `entries/sgv.json?count=`, `profile.json`, `activity/?find[created_at][$gte]`, and a **filter DELETE** on `devicestatus/?find[created_at][$lte]` (survey S2) | `api-secret` header = SHA-1 on every request (`src/setupParams.ts:4-13`); TLS verification off for https (lab uses http) | lock `c09f9c03`; checkout matches |
| 4 | **nightscout-librelink-up** (`librelink-up`) | B | Node/TypeScript cron process; both a v1 and a v3 Nightscout client in one binary (`src/nightscout/apiv1.ts`, `apiv3.ts`) | v1 GET `entries?count=1` then POST; v3 `GET /api/v3/entries?limit=1&sort$desc=date`, `POST /api/v3/entries` one reading per request, **requires 201** | v1: the operator-supplied value sent **verbatim** as `api-secret` (`apiv1.ts:16`); v3: exchange at `/api/v2/authorization/request/<token>` before every request, then `Authorization: Bearer` (`apiv3.ts:39, 32, 67, 104`) | lock `bff2317f`; checkout matches. Needs a fake LibreLinkUp upstream; the connector's `scripts/librelinkup-lab.js` uses **real** accounts and is therefore unusable here |
| 5 | **share2nightscout-bridge** | B | Node process polling Dexcom Share | v1 POST `entries.json` | `api-secret` header = SHA-1 (`index.js:259-268` per survey) | lock `518c85c4`; checkout matches. The journey lab's `fake-share.js` emulates the Share endpoints the **connector's** driver uses; whether the bridge's requests match it is unmeasured |
| 6 | **tconnectsync** | B | Python CLI; `--pretend` suppresses uploads (the opposite of what the lab needs); needs the Tandem cloud | v1 POST/PUT/DELETE treatments, entries, devicestatus, profile `PUT` by read `_id` | `api-secret` = SHA-1 header on every call plus the plaintext secret as a `?api_secret=` query parameter the server ignores (`tconnectsync/nightscout.py:48-70` per survey) | lock `7c4b2f4d`; checkout matches |
| 7 | **AndroidAPS NSClientV3 SDK** (`aaps`, `core/nssdk`) | C | Kotlin multiplatform module with a `jvm` target and `jvmTest` source set (`core/nssdk/build.gradle.kts:8-14`); the HTTP layer could be exercised from a JVM test, but the sync selector and retry scheduling live in the Android plugin | v3 entries/treatments/devicestatus/profile/food REST, `/storage` and `/alarm` socket namespaces | v2 exchange then Bearer; the "empty-bearer handshake" is handled by the preview's exchange (`tenant-app/README.md:163-166`) | lock `7e1d537d` (dev, 4.0.0-dev-c). The **v1 socket client is removed on this pin** (`30fe4591a7`); it exists only on master 3.4.2.6, which is not pinned |
| 8 | **minimed-connect-to-nightscout** (`minimed-connect`) | B | Node; CareLink upstream, which the programme treats as dead (BF-61 hard stop) | v1 POST entries/devicestatus | `api-secret` = SHA-1 (`nightscout.js:15-18` per survey) | lock `57bb042c` |
| 9 | **xDrip+** (`xdrip`) | D | Android app; `NightscoutUploader.java` is in the app module | v1 POST/PUT/DELETE by its own 24-hex `_id`; follower polls | `api-secret` = SHA-1 | lock `1ed76004` |
| 10 | **AndroidAPS application** (`aaps`) | D | the plugins that schedule, retry and accept | as rank 7 plus the app's accept rules | as rank 7 | lock `7e1d537d` |
| 10a | **AndroidAPS 3.4.2.3 NSClient (v1) socket upload sequence** (`aaps` at the 3.4.2.3 tag; `plugins/sync/.../nsclient/services/NSClientService.kt`) | A as a **driven sequence**, D as the plugin itself | a Node socket.io client replays the plugin's `authorize`, `dbAdd`, `dbUpdate` and `ack` message sequence as read from the pinned source, including a retried `dbAdd` after a withheld ack; this is source-pinned pattern replay, not execution of the Kotlin plugin | v1 socket writes; the whole upload path of this plugin is the socket (execution plan §2.14 corpus table) | socket `authorize` with the site's secret hash | lock `7e1d537d` is `dev`, where the v1 plugin directory is gone; the 3.4.2.3 tag must be read by `gh api` or a pinned checkout, never a stale clone |
| 11 | **Loop via NightscoutKit / NightscoutService** (`nightscoutkit`, `loop`) | E | Swift package declaring iOS/macOS/watchOS platforms; six source files `import HealthKit`, so it does not build on a Linux toolchain | v1 array POST entries/treatments/devicestatus/profile; PUT/DELETE by cached `_id`; `experiments/test` setup check | `api-secret` = SHA-1 | lock `4ec9fd12` / LoopWorkspace `548b3324` |
| 12 | **Trio** (`trio`) | E | iOS app; the `trio-test-harness` pin (`tth`) drives it on the iOS Simulator, which needs macOS | v1 object POST, GET `sgv.json?count=1600`, DELETE by `created_at`+`eventType` | `api-secret` = SHA-1 only; any `?token=` in the configured URL is dropped (survey S5) | lock `0b29cd53` |
| 13 | **LoopFollow** (`loopfollow`) | E | iOS | v1 follower GETs with `token` in the query; socket `authorize {secret: <token>}`; **creates a subject** via `POST /api/v2/authorization/subjects` at setup | token in the query | lock `4a74b781` |
| 14 | **nightguard**, **xDrip4iOS**, **LoopCaregiver**, **DiaBLE** | E | iOS | nightguard v3-first with v1 fallback; xDrip4iOS v1 only, bulk delete by timestamp list (BF-108); LoopCaregiver v2 `notifications/loop` | Bearer (nightguard), SHA-1 header (xDrip4iOS, LoopCaregiver), raw token in `API-SECRET` (nightguard v1) | lock `75404bd2`, `c268542e`, `23057183`, `e6a909c8` |
| 15 | **GluPredKit**, **GlycemicGPT**, **nightscout-cgm-skill** | A (readers) | Python / agent readers; useful only for follower-shape reads; GluPredKit sends `count=0` meaning "everything" (survey) | v1 GET entries/treatments/profile | API secret or token per their config | lock `e5bd6357`, `d1a9adb7`, `91a53ea1` |
| — | **nightscout-reporter** | F | the pinned Dart app is retired; the current Angular Reporter is not in the corpus | — | — | lock `518d61fb` |
| — | **nocturne**, **nightscout-roles-gateway**, **xdrip-js**, **glooko\***, **GlookoServiceKit** | F | a server rewrite; an authorisation-decision service; a BLE library with no HTTP client; Glooko readers with no Nightscout call | — | — | — |
| — | **Nightscout web client** (cgm-remote-monitor `lib/client`) | browser | the browser tier (684 cases) runs against single-site boot; the same pages served by the preview are `UNMEASURED` | v1/v2 reads, careportal writes, socket | the page's own session | the CRM head |

## 4. Lab design for the top three (nightscout-connect, oref0, cgmsim-lib)

The design borrows from four existing instruments by name: the **journey lab**
(`tools/review/journey-lab/`: sites per app, scripted `fire` steps, a fake vendor upstream,
secrets kept outside the tree and never printed), the **compat pipeline**
(`tools/qc/compat/`: two trees, every differing cell explained, a verdict vocabulary),
the **id-batch-replies lab** (`tools/lab/id-batch-replies/`: real connector module run cycle
by cycle, stored rows counted from the database) and the **connector-soak lab**
(`tools/lab/connector-soak/`: a source site and token/secret sinks through a counting proxy).
The CRM-side scaffolding already exists in `tests/fixtures/client-replay-http.js`.

### 4.1 Server under test

- The explicit multitenant executable: `bin/nightscout.js multitenant api`
  (`lib/cli/commands/multitenant.js:3-4`, PLAT-SERVE D21; exit codes `:6-13`), with a
  preview configuration shaped as `tests/multitenant-preview-process.integration.test.js:41-56`
  builds it: `resolution.mode = direct-alias`, two tenants A and B, each with one alias,
  per-tenant Vault encryption/signing keys, operator-applied candidate schemas in separate
  namespaces, the legacy credential catalogue, and `domains` covering entries, treatments,
  devicestatus and profile (the collections the three clients touch).
- Disposable PostgreSQL and Vault owned by the run, as the owned runner does
  (`tools/lab/multitenant-rest-preview/README.md`); never a shared database.
- Tenant A and B each get an imported root reference and one imported subject with the
  `readable` role, provisioned the way the replay fixture provisions them (the root
  credential a client presents is the SHA-1 of A's root, `client-replay-http.js:277`).
- **Name resolution is the first setup item.** The preview selects the tenant from the wire
  `Host`. Real client binaries resolve a hostname themselves, so the lab must make `A`'s and
  `B`'s aliases reach the loopback listener without editing any client: run each client in
  its own container with host entries for the two aliases, or run the lab's own resolver.
  Do not switch to `canonical-internal` for this: it changes the trust surface
  (`preview-config.js:90-101`). The setup control: a plain status read with A's credential
  and A's alias answers from A, and the same read with an unconfigured alias refuses as an
  unknown tenant (the M2 criterion) before any client is started.

### 4.2 Single-site baseline

The same head `35903069` booted single-site on a disposable MongoDB (the compat pipeline's
and the matrix harness's boot, `tools/qc/write-contract-matrix.js:15-19`), with
`AUTH_DEFAULT_ROLES=denied`, one API secret and one `readable` subject. Every client run is
executed once against the baseline and once against tenant A of the preview, from the same
container image and the same client version, in the same order.

### 4.3 Per-client runs, positive checks, controls and predictions

Each run records, per request: method, path **without query values**, status, reply shape
(array length, per-item keys), and afterwards the stored rows read through an independent
oracle (the lab's own PostgreSQL reader for the preview, as `client-replay-http.js` reads rows;
MongoDB for the baseline). Oracle rows are compared with only the normalisation the compat
pipeline already uses (cache/wire and top-level server clock stamps, R41's rule); nothing
else is normalised.

| Client | Positive run on tenant A | Predicted outcome (hypothesis) |
|---|---|---|
| nightscout-connect, `forever` with the HTTP output pointed at A's alias and A's root secret, reading from the journey lab's `fake-share.js` as the vendor | entries POSTed in arrays per poll; backfill on first poll; later polls send only new readings | 200 with one reply object per item; A's oracle shows the readings with `device: nightscout-connect`; B's oracle is empty. srvModified may advance on a resend; logical rows do not change (R40) |
| nightscout-connect, `nightscout` **source** reading tenant A with a pre-issued subject token, writing to the single-site baseline sink | exchange at `/api/v2/authorization/request/<token>` then Bearer GETs with `count` and `find` | exchange 200 with `token,sub,permissionGroups,iat,exp`; reads 200; the sink receives A's rows and nothing from B. Without a pre-issued token the connector's subject creation is refused: record the status, do not work around it |
| oref0 `ns-upload.sh` for entries, treatments and devicestatus, in **both** credential modes (header and `token=` query), then `ns-get` `latest-openaps-treatment`, then `oref0-upload-profile.js` | v1 POSTs; the treatment lookup with the malformed `count=1?...`; profile GET/PUT | header mode: 200; query-token mode: 200 through the legacy exchange path (`data-access.js:108-116`); the malformed count answers as `RT-COUNT-COMPAT` decided on single-site, or differs, and either way the cell is classified; the hashed secret in the URL is a known client defect, so lab logs must apply the same URL redaction as `lib/server/log-privacy.js` |
| cgmsim-lib driver: upload a synthetic series, read it back with `count`, read `profile.json`, read activity with `find[created_at][$gte]`, then the filter DELETE on devicestatus | v1 round trip including a filter DELETE | reads and uploads 200; the filter DELETE either succeeds as single-site does or is explicitly refused; the preview's documented "no filter DELETE" applies to v3 (`tenant-app/README.md:265-266`), v1 is `UNMEASURED` and this cell decides it |

Negative controls, run for every client:

| Control | Mechanism | Predicted symptom |
|---|---|---|
| Same client, same A credential, pointed at **B's alias** | A's root hash does not verify against B's reference; A's subject token exchanges against B's authority and finds no subject | refused (401 family); B's oracle unchanged; no row on A either. The exact status per carrier is recorded, not assumed |
| Credential **revoked mid-run** | the operator removes A's subject grant (token clients) or replaces A's root reference (secret clients) between two client cycles | the next cycle refuses; rows from the earlier cycle remain; the client's own reaction (connector backoff in `lib/backoff.js`; oref0 "Unable to upload", exit 2; cgmsim-lib throws) is recorded as a client property |
| **Malformed batch** | an array in which one item is refusable on both stacks (the id-batch-replies scenarios are the model: a Temporary Target with bottom above top under `WRITE_VALIDATION=reject`; an entry with a non-hex `_id`) | the per-item reply array has the same shape and the same refused index on the preview as on the baseline; the stored-row count is the same. A whole-batch refusal on one stack and per-item on the other is a cell to classify, not a pass |
| **Unknown alias** | a hostname not in the tenant configuration | unknown-tenant refusal, no storage effect |
| **Absent credential** | the client run with no secret and no token | anonymous `denied` refuses reads and writes on both stacks |

Break-it controls for the lab itself (a check that has never failed is not evidence):

- Remove the Host entries for the aliases: every positive check must go red with a
  resolution failure, not a 4xx.
- Point the oracle at the wrong namespace or database: every stored-outcome assertion must
  go red with zero rows.
- Plant one unapproved difference in a captured reply before classification: the
  classifier must report it as unexplained (the control the compat refresh lane used,
  roadmap §"RC backwards compatibility").
- Restore each and re-run; the restored run is the one that counts.

### 4.4 Differential against single-site Mongo through the compat pipeline

The compat pipeline classifies cells that differ between two matrix runs into named groups
with a verdict from `Defect | Decided | Bug fix | No value change`
(`releases/cgm-remote-monitor-16.0.0/compat/groups.yaml:10`), and refuses to build the page
while any cell is unexplained (`tools/qc/compat/README.md`, step 3). The lab reuses that
classification and vocabulary, with one adapter the pipeline does not have today:

- `tools/qc/write-contract-matrix.js` boots the server **in-process from `WC_WORKTREE`
  via `lib/server/server.js`** and reads stored state **from MongoDB** (`:15-19, :23-26,
  :341-356, :427`). It cannot boot `multitenant api` and cannot read PostgreSQL. So the lab
  does not run the matrix against the preview; it emits cells in the matrix's cell shape
  (collection, path, form, reply fields, stored fields) from its own client runs and
  oracles, and feeds the pair of cell sets to `tools/qc/compat/wcdiff.py` and
  `classify_compat.py` with the existing `groups.yaml`.
- A cell that lands in no group stops the run with "unexplained", exactly as the pipeline
  does for a tree comparison. Differences already documented as intentional (strict
  invalid-credential refusal; dotted PATCH members refused with 400 on PostgreSQL; JSONB
  non-representable values refused) need their own group entries with verdict `Decided`
  and a decision basis before the run is called green.
- Nothing in this comparison speaks for old releases: the pipeline's 15.0.9 → dev
  attribution stays separate, and no old-release-to-PostgreSQL transitivity is claimed.

### 4.5 Record and gate

- The run is recorded as one dated R entry in the integration record, with the client
  versions read from the packages that ran, the preview head, the Node/PostgreSQL/Vault
  versions printed by the runner, every control's exact symptom, and the classified cell
  table. Logs stay outside the tree; the record carries counts, not URLs.
- A queue item is needed for this lab (none exists at `main` for M4 client execution; the
  nearest are `ST-PG` and `TEN-LAB`, whose `no-gate` notes name client replay as remaining).
  Its gate must be able to fail, declare its control in `queue/gate-controls.yaml`, and read
  the archived head with `git show`/`git archive`, never a checkout. The id is allocated
  when the item is written, not here.

### 4.6 D23 entry condition 2: the NSClient v1 socket sequence against a forwarding `realtime`

D23, adopted and amended on 2026-11-06 (execution plan §2.14), makes `realtime` a
reader that forwards every socket write message and the alarm `ack` unchanged, with
the socket's own authorization, to an internal write endpoint on `api`, which runs the
write step with the `socket` source label and relays the result into the socket
acknowledgement. Its entry condition 2 names this packet as the home for the proof,
because AndroidAPS 3.4.2.3's NSClient (v1) plugin is the one corpus client whose whole
upload path is the socket.

**Server under test:** the explicit multitenant executable serving `api` and a
forwarding `realtime` for two tenants, as in §4.1, plus the single-site Mongo baseline
of §4.2 on the same head.

**Driver:** a Node socket.io client replaying the plugin's message sequence as read from
the pinned 3.4.2.3 source: `authorize`, a `dbAdd` for a treatment and a devicestatus,
a `dbUpdate` by the id returned in the add's acknowledgement, the alarm `ack`, and a
retried `dbAdd` after the driver withholds its own acknowledgement handling, which is
what the plugin does when no ack arrives. The driver is pattern replay (R40's caveat
applies: not execution of the plugin) and carries no payload from any real site.

| Check | Predicted green | Exact red symptom |
|---|---|---|
| each forwarded write is stored once on tenant A with source label `socket`, and the acknowledgement carries the same id or result string the single-site baseline returns | stored rows and ack bodies equal across baseline and preview, per the compat verdict vocabulary | a differing ack shape, a missing source label, or a row on tenant B |
| the retried `dbAdd` after a withheld ack stores no duplicate | one row, one ack on the retry | two rows for one logical add |
| **control: acknowledge before `api` confirms** (patch the forwarder in a scratch copy to reply before the forward resolves, then make the forward fail) | the lost-write assertion goes red: an acknowledged add with no stored row | if it stays green the assertion is vacuous; restore and rerun |
| **control: `api` unavailable** | the socket write receives no acknowledgement and the driver's retry fires; nothing is stored until `api` returns | a success reply during the outage |
| **control: tenant A's socket credential on tenant B's alias** | `authorize` refused; no write reaches `api` | any stored row on B |
| `single` unchanged | the baseline's socket writes go directly to storage as today; no forwarder in the path | a forwarded write observed in single-site mode |

Hop latency and its effect on the plugin's ack timeout are UNMEASURED and stay so
until a quiet-hardware run; the control list above proves correctness of the forward,
not its cost.

## 5. What M4 still leaves unmeasured after this lab

| Area | Why the lab does not reach it |
|---|---|
| **Socket transport** | None of the three clients speaks socket.io. AAPS v3 `/storage` and `/alarm` namespaces, LoopFollow's `authorize {secret: <token>}`, and AAPS v1 `dbAdd`/`dbUpdate` (only on the unpinned 3.4.x master) are M5's gate (socket authorization, reconnect, tenant-local rooms), not M4's The NSClient v1 forward path alone is covered by §4.6 under D23; the v3 `/storage` and `/alarm` subscribe paths and LoopFollow's socket `authorize` remain outside this lab. |
| **Mobile binaries** | Every iOS client (Loop/NightscoutKit, Trio, LoopFollow, LoopCaregiver, nightguard, xDrip4iOS, DiaBLE) needs an Apple toolchain; xDrip+ and the AndroidAPS app need an emulator. The journey lab's `REAL-APPS.md` track is manual, needs HTTPS the phone trusts and a simulated pump, and proves app-side decisions the lab only predicts. Their request shapes remain source-pattern replay |
| **Retry semantics under outage** | R48 measured the **server** answering 503 with Vault or PostgreSQL paused; the clients' schedulers (NightscoutKit's 24-hour `_id` cache and completion-handler hang on DELETE error, AAPS WorkManager, xDrip retry-forever) are not executed. The connector's backoff is observable but not under a paused backend at soak scale |
| **Subject creation by clients** | LoopFollow and the connector's source mode create a subject through `POST /api/v2/authorization/subjects`; the preview's data plane mounts no such route (subject administration is the separate management app, R42). "No coordinated app upgrade" is unproven for any client whose onboarding creates a subject |
| **v3 uploader binaries** | nightscout-librelink-up (rank 4) is the only pinned headless v3 uploader and needs a fake LibreLinkUp upstream that does not exist in the repository; AAPS v3 is Android. The v3 uploader shape stays source-pattern replay plus the CRM's own API3 tests |
| **TLS, proxies, `canonical-internal`** | The lab uses plain HTTP and `direct-alias`; clients that insist on HTTPS, `TRUST_PROXY` behaviour and the trusted-peer mode are untouched |
| **The web client under the preview** | the browser tier runs against single-site boot only |
| **nightscout-connect in-process (`CONNECT_SOURCE`) inside a multitenant serving role** | the connector's `internal` output writes through storage ports, not HTTP; a per-tenant composition does not exist at `35903069` |
| **New-format Ed25519 tokens** | no pinned client emits them; R48's acceptance stands on its own synthetic issuer |
| **Capacity and latency** | nothing here is a benchmark |

## 6. What the lab must not claim

- M4 promotion, or any milestone. Promotion is a maintainer decision recorded in the roadmap
  and dashboard after the criterion list is fully met.
- Compatibility for any client that was not executed. A green run of three Node/bash
  clients says nothing about Swift, Kotlin or Java binaries; their rows stay
  `source-pattern replay` with the R40/R41 wording.
- "No coordinated app upgrade requirement" as a general statement. The lab can say it for
  the credential shapes it exercised (SHA-1 header, query token on v1/v2, Bearer from the
  exchange) and must say it is unproven for subject-creating onboarding and sockets.
- Equality of HTTP replies as proof of equal stored outcomes, or the reverse. Both are
  recorded; the classification is per cell.
- That single-site behaviour is unchanged. That is the full nonbrowser and browser
  campaign's job on the batch head, not this lab's.
- Anything about the vendor drivers beyond "the fake upstream was reached". Real vendor
  accounts, exports, traces or identifiers never enter the lab; every record is synthetic.
- Old-release transitivity: the compat pipeline's 15.0.9/dev classification is a separate
  measurement and is not re-run here.

## 7. Traps read while preparing this packet

- The `externals/nightscout-connect` checkout is at `04102f9d`, not the lock's `b394411a`,
  and its package version is `0.1.1` while the CRM depends on `0.1.0`. Quote the version
  from the package that runs; a result labelled with the lock pin would be mislabelled.
- The write-contract matrix cannot be pointed at the preview (§4.4); a brief that says
  "run the matrix against tenant A" is not executable as written.
- The November 2 draft PR body in this directory is a peer's untracked file and does not
  contain the client-binary statement; cite R40/R41 and the CRM READMEs instead. It is never
  staged by anyone else.
- The connector's `scripts/librelinkup-lab.js` uses real accounts; it is excluded from any
  lab under this programme.
- AndroidAPS at the pinned `7e1d537d` has no v1 socket client; a v1-socket result would
  have to come from the unpinned 3.4.x master and must be labelled as such.
- The preview refuses a supplied invalid credential where single-site falls back to
  anonymous (`tenant-app/README.md:252-260`). A client that probes with a wrong secret and
  expects anonymous `readable` behaviour will see a difference that is `Decided`, not a defect.
