# Next-gen platform: one write path, four tracks

*Contributor-facing living plan. Reconciled 2026-11-08 to the published
[operation-window acceptance family](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md)
and [release record](../../../releases/cgm-remote-monitor-16.0.0/contents.md).
Draft [#8898](https://github.com/nightscout/cgm-remote-monitor/pull/8898) carries
`ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364`, based on dev `4a482627`.
Native/browser, corpus and cold-deployment campaigns retain their actual source
heads. Current milestone claims live in the
[delivery dashboard](../tenancy/multitenant-delivery-dashboard.md); release
placement lives in [release allocation](release-allocation-2026-10-27.md).
This is a map of bounded capabilities and remaining work, not production admission.*

The interactive version, with the dependency map, is the site page [nightscout-next-gen-platform.html](../../../site/pages/nightscout-next-gen-platform.html).

This plan covers the work that follows the 16.0.0 modernization:

- storage behind one write path;
- the client and server identifiers Loop asked to separate;
- controller registration, from a read-only catalogue to typed writes;
- multitenant Nightscout.

It names each piece of work, what it needs first, where it goes in the code, and the check that pins it.

## 1. Where things stand

The [tenancy reading guide](../tenancy/README.md) identifies the current plan,
decision owners and historical evidence. Start with the dashboard for sequencing;
use this map to see how the platform tracks meet.

| Scope | Current recorded acceptance | What remains |
|---|---|---|
| Foundations, data and tenant authority | [R72](../remedial/rc-16.0.0-integration-record.md#r72---admitted-entries-and-owner-configuration-completion-batch-2026-11-06) retains M0 and promotes M1–M4: admitted PG ports/import, actual typed/versioned owner settings, tenant refusal and route separation, pinned headless clients and source-pattern replay. | Wider owner catalogue/lifecycle and production resolution trust; Android emulator and resource bounds in C. No all-client claim. |
| Durable runtime | [R73](../remedial/rc-16.0.0-integration-record.md#r73-durable-runtime-operations-batch) accepts functional M5 on one host: separate roles, polling/snapshots, durable suppression and reference notification handoff. | Live provider/device delivery, multi-node ownership and capacity/freshness/egress budgets. |
| Tenant-local recovery and shared-process restart | [Operation-window acceptance](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md) accepts same-ID logical restore with forward client history, public-ID preservation, fail-closed uncertainty and B continuity while A remains suspended, including fresh service processes. Native evidence is on c23; cold Compose/UI/socket/restore and pinned-client evidence is on ed2. | Fixed trusted process cohort, private ingress and direct PG connections bound this proof. Dynamic membership, transaction pooling, multi-host coordination, arbitrary direct SQL writers and automatic orphan clearance remain outside it. |
| Deployment artifact and verification | The published ed2 draft has an exact-source Compose image and cold synthetic deployment acceptance. Final full-suite and pinned-client campaigns are on ed2; native/default-browser on c23 and entire enabled corpus on 39f4 retain their source attribution. | Whole M6 stays blocked. Draft publication, dev merge, operator release, default enablement and production admission are distinct boundaries. |
| Optional shared human identity | [Shared OIDC/session capability](../../../reports/tenancy/shared-oidc-sessions-2026-11-07/README.md) is fixed on a separate local source branch with bounded source checks and controls. | Actual signed native DB/Vault/HTTPS/browser and reference-provider acceptance are UNMEASURED. It has not joined the published Compose candidate. |
| Independent single/nonresident profile | R55 accepts private acquisition on `2ee8b493`, with caller policies and the physical subscriber retained. | The computed-single branch remains separate; full writer/alarm/clinical coverage, freshness, cost and its own entry bar remain. Default single stays resident. |

The [acceptance family](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md)
owns exact source/instrument identities and immutable failed and successful runs;
the [release record](../../../releases/cgm-remote-monitor-16.0.0/contents.md) owns
programme disposition. This reconciliation is **read-derived** from those records,
not a rerun of the application. Recorded-evidence gates replay archived captures;
they do not execute a fresh native/current-HEAD campaign.

### What is complete enough to inform a decision?

Use an accepted capability to answer the question it exercised. An implementation
can settle a bounded design question while its parent queue item remains open.
A production decision additionally needs an operating envelope, deployment trust
and failure recovery under the selected topology.

| Decision you can make from current evidence | Evidence supports | Evidence still needed to unlock broader use |
|---|---|---|
| Keep API, realtime and evaluator as explicit cooperating roles | Functional one-host M5 and later cold Compose demonstrate consumed role boundaries and restart behavior. | [Fixed-roster API scaling](../tenancy/selectable-endpoints-and-api-scaling-plan.md) needs instance-complete drain/invalidation and endpoint trust, separately from singleton evaluator ownership. Multi-host/HA adds failover and partition acceptance; platform placement/assignment does not replace application operation lifetime. |
| Keep restore tenant-local in the reference topology | Actual restore/history convergence and B continuity, including B startup while A stays suspended. | Broader membership, orphan resolution policy and production recovery objectives. The [adopted ownership contract](../tenancy/sql-and-migration-architecture.md#supported-database-ownership-contract) excludes independent direct SQL writers; stronger fencing is not a production prerequisite for the supported cooperative topology. |
| Continue the admitted PostgreSQL backend and migration path | Tenant-scoped native/HTTP/storage controls and append-only allocator migration/restore work. | Supported production workloads, pool limits, noisy-neighbor behavior, capacity and restore/upgrade budgets. |
| Scope a reusable current-property result | [Derived-output characterization](../../../reports/tenancy/derived-output-2026-11-07/README.md) finds selected evaluator/API properties agree, with time/settings/identity-sensitive controls. | A reusable result interface and expiry/invalidation checks. Raw realtime frames remain a different product; no publication service or distributed result store is selected. |
| Choose resident versus computed execution for single-tenant sites | The independent prototype demonstrates bounded functional behavior and failures worth guarding. | Quiet steady-state cost, full caller/clinical coverage and per-profile reliability before changing placement or defaults. |
| Select an identity/deployment reference for acceptance | Adopted generic OIDC, Vault progression and per-deployment trust/probe contracts define what to build and test. | Native signed/session/provider acceptance, service-login renewal and live edge/Vault probes. Source checks alone do not admit a production identity system. |

The [deployment guide](../tenancy/deployment-and-rig-testing.md) separates tenancy,
backend, execution profile, service placement and host topology. These are
independent choices: more processes improve operational separation, while a
shared host, PostgreSQL service, Vault or edge can still fail all tenants.
The [current M5/M6 decision list](../tenancy/m5-m6-decision-list.md) owns remaining
policy questions; the [release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md)
own adopted answers. A deferred decision keeps its prototypes and benches running.

| Earlier overview | Retained evidence |
|---|---|
| [R62–R72 overview at the prior revision](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/53cda175990e9bc0cd351eb6b7758f6fe3b4311e/docs/30-design/platform/next-gen-platform-plan.md#1-where-things-stand) | Earlier publication checks, prototype failures and small clock HTTP evidence; the integration record and named capsules retain their original verdicts. |
| [R49–R55 platform checkpoints at the prior revision](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/ed18a7bceb096fc52e155fc5a005106f7e91263d/docs/30-design/platform/next-gen-platform-plan.md#1-where-things-stand) | Native and cumulative campaigns, capacity HOLD and cleanup captures, original replica failure and focused clock repair. Their named reports remain authoritative for those runs. |

## 1. 16.0.0 scope (maintainer, 2026-10-30)

16.0.0 targets **every single-tenant item of this plan**, through the entry bar and in priority order. A
miss rolls to 16.1.0, or to 17.0.0 if it changes a default.
- **The identity work is the core.** It is the substance of the agreement with the Loop maintainers:
  identifier-first on every path, re-sends recognised, the format rules, and one record per identifier.
- **The unique index on `identifier` is in 16.0.0**, behind `WRITE_IDENTIFIER_INDEX=try|require|off|drop`
  (default `try`).
  - Under `try`, boot attempts a partial unique index per collection: records with an `identifier`,
    soft-deleted ones included, built online. If existing duplicates block it, the counts per collection
    (never the values) are logged and shown on the status page, and the server runs without the index.
  - The write rule (ID-Q5) still refuses to create a second record with a stored identifier.
  - `require` refuses to start until the index exists. `off` skips building it but leaves any existing index enforced; `drop` removes the index at boot, then runs as `off`.
  - An operator-run tool reports duplicate groups and resolves them by the P4 pick.
- **Multitenant items may ship dormant, labelled alpha behind explicit `multitenant` configuration, or not ship.**

Feasibility, from the 7 days to 2026-10-30: 53 PRs merged into `dev`, and 14 of this plan's 36 items went
to done. Build speed is not the limit. Time on `dev`, cohort checks and review are, so items land in
priority order and early, and the tag is gated by the bar, not by a date.

## 1a. Priority and merge order (2026-10-29)

The [release allocation](release-allocation-2026-10-27.md) owns release ordering,
the [release contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md)
own merged and tested state, and the queue owns item claims. Identity and the
write path remain the single-tenant release priority; a multitenant prototype
passing its own campaign does not bypass that release entry bar.

The detailed October merge-order and per-commit execution table is retained in
[the captured platform revision](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/8792fc7a3d62f59629ed94bac168dcad5d9aa3c7/docs/30-design/platform/next-gen-platform-plan.md#1a-priority-and-merge-order-2026-10-29).
It preserves the original source heads, matrix results, cohort requests and
release hypotheses. It is historical context, not a current dispatch queue.

## 2. Why the tracks meet at the write step

Every track changes what happens when a record is written:

| track | what it needs from the write step |
|---|---|
| Identity | a single place that matches a re-sent record on `identifier` first, then on the time key, for v1, v3 and the socket alike |
| Registration | a single place that applies a controller's declared schema to its typed writes, and leaves unregistered writers byte-identical |
| Validation | a single place for #8841's rules, so the socket and the v1 modules are not checked separately |
| Tenancy | a single place that carries the tenant binding, so no path can write without one |

#8854 built that place as a boundary at the driver call, and the storage interface sits above it. Each later slice adds one rule there. Every slice must keep the following:

| must hold | pinned by |
|---|---|
| the `_id` forms: ObjectId, upper- and lower-case hex, UUID, and `UUID_HANDLING` moving a non-hex `_id` to `identifier` | #8854's matrix rows; `tests/identity-matrix.test.js` |
| the API v3 create and deduplication reply (`status`, `identifier`, `isDeduplication`, `lastModified`), and AndroidAPS's string-matched refusal texts | `tests/write-validation.test.js`; the v3 suites |
| Loop's `syncIdentifier` and Trio's `id` stored and returned untouched | write-contract matrix |
| v1 treatment upsert on `created_at` + `eventType` | write-contract matrix |

The forward constraints are two mature backends behind one interface (D2–D4), the closed query operator set as a filter tree (D8), a source label and later a tenant binding on every write, and one commit fact the change feed can carry (D6; D-EVENT decided 2026-10-31: one in-process event per write, named from WriteResult.items[], and the per-database-call event kept as backend instrumentation; delivery between processes is decided with the serve roles; its card in §5). Under #8854's merge conditions, the commit event stays internal and unstable, and the intent layer gets its own name. The later [B7 recovery direction](../tenancy/durable-event-delivery-contract-2026-11-06.md) uses a durable feed and the adopted [bounded full current-state snapshot backstop](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m5-bounded-snapshot-reconciliation); the time-only alarm tick remains separate from that reconciliation schedule.

## 3. The map

For multitenant status and sequencing, use the
[multitenant delivery dashboard](../tenancy/multitenant-delivery-dashboard.md).
It owns M0-M6 prerequisites, parallel lanes, bounded slices and current
acceptance. The [roadmap](../tenancy/multitenant-delivery-roadmap.md)
defines milestone criteria and boundaries. The integration record and named reports
retain execution evidence. This map summarizes their bounded implications.

Read a node's reference and remaining scope before treating its color as a verdict.
**Done** means the named item/component is complete or merged to dev; it says
nothing by itself about an operator release. **In progress/blocked** can contain
accepted useful slices with broader work remaining. Arrows show prerequisites,
not runtime communication, fault domains or percentage complete. Milestone
promotion belongs to the dashboard; deployment admission belongs to the selected
deployment's trust record and measured probes.

<!-- chart: map -->

## 4. The tracks in detail

### 4.1 Storage

Done, in 16.0.0: PR-8854, QC-MATRIX-TT (360 cells), ST-FILTER, ST-READS, ST-WRITES, ST-COUNT-ONEPATH, ST-V3-DECOUPLE, WC-STEP-PATCH (release 1).

| item | builds | needs | check |
|---|---|---|---|
| WC-STEP-PATCH | release 1 merged as #8874 (`368e6c23`, no behaviour change); release 2 merged as #8886 (`51d38f9f`, 2026-11-01), resolves filter writes to ids and gives API v3 the same write shape (Q9, Q-U, Q-A); the reached ids come back in `WriteResult.removed` and `.updated`, and `items[]` stays one slot per input (maintainer, 2026-10-31): `write(intent)` -> WriteResult.items[] above the interface; matching, server dates, the null-removes rule and validation move into it; compare-and-set behind an adapter method | ST-WRITES | [write-contract spec](../tenancy/write-contract-spec-2026-10-07.md) G1 |
| ST-V3-DECOUPLE | merged with #8865 (`991b0654`): API v3 without API v1's modules, the socket and the cache, so `serve api` serves it alone (historical headless-API stage) | ST-WRITES, PLAT-SERVE | `serve api` passes the API v3 suites (634 pass, 0 fail, 108 single-only pending, as reported at `9f7f84f8`); `single` unchanged |
| ST-EVENT | merged with #8886 (`51d38f9f`, 2026-11-01): one internal event per write, `storage-intent-committed`, carrying the write's records (`_id`, identifier, outcome, refusal problems) without document contents; the per-database-call `storage-write-committed` stays as instrumentation | WC-STEP-PATCH, D-EVENT (decided 2026-10-31) | each stored and refused record named once per write |
| ST-HARNESS | **merged 2026-11-01** as #8881 (`f54941b5`, head `993275f3`): backend-selectable harness, backend selection, tenant scope | WC-STEP-PATCH | `NS_TEST_BACKEND` controls |
| ST-VIEWS | **merged 2026-11-01** as #8875 (`1fc6d8be`), not wired in; equal to the resident path on 126,092 replayed minutes per view (re-checked on `1fc6d8be`): computed views from bounded queries, without a resident `ddata`: page, socket `dataUpdate`, plugins, alarms (M4) | ST-READS | each view equal to today's on the corpus fixtures; alarms per the execution plan §7b |
| ST-VIEWS-PROFILE | R55 retains independent local acceptance on `2ee8b493`; earlier #8891 and R43 captures retain their own heads. Explicit single/nonresident launcher computes bounded alarms/properties after admitted physical writes and heartbeat, retaining the last cycle properties; default single stays resident. Logical no-op/refusal admission, full alarm/writer coverage, live stats freshness, quiet-hardware cost and placement remain open. It is not joined into #8898. | ST-VIEWS | [R43](../remedial/rc-16.0.0-integration-record.md#r43---independent-nonresident-profile-refresh-on-925c9527-2026-11-05): actual trigger/timer/freshness and teardown controls; remaining entry bar is explicit |
| ST-PG | R72 accepts admitted PostgreSQL/RLS backend/DDL/import contracts; later tenant-local allocator/restore and cold Compose evidence are source-attributed in the acceptance family. Resource bounds remain in C | ST-HARNESS | actual HTTP/Mongo differentials, migration/restore controls and bounded M1 criteria in the delivery dashboard |

The September seam chain is kept as reference for ST-HARNESS, ST-PG and TEN-RESOLVE (commits named on each item); it is not merged as it stands.

### 4.2 Identity

Done, in 16.0.0: DEV-8845, ID-SIMPLE-MATCH. Done in this repository: SPEC-ID-AMEND (2026-10-30).

| item | builds | needs | check |
|---|---|---|---|
| SPEC-ID-AMEND | a conformance case for the mandatory identifier on registered instances; identity I2 and §6 state API v3's refusal of a client `_id` (BF-170) | #8845 | `tools/nsschema` cases |
| ID-FIRST-MATCH | identifier-first on every collection and path | ID-SIMPLE-MATCH, WC-STEP-PATCH (D-LOOP-ID's rules decided 2026-10-29) | write-contract matrix; the re-send table, identity reference §2.7 |
| ID-BATCH | v1 per-item reply behavior and index-dependent duplicate-key retry for batch writes | WC-STEP-PATCH, ID-UNIQUE-INDEX | implemented across #8889 and #8894, including tests in `tests/api.id-batch-replies.test.js` and `tests/api.batch-race-item-level.test.js`; the old local branch is not a separate release-critical PR |
| ID-RESEND-SWITCH | site-level `WRITE_RESEND` and `WRITE_DELETED_RESEND` modes, defaulting to current behavior | ID-FIRST-MATCH and compatibility B | merged as #8892 (`3c773ee5`); local matrix showed 0/4,916 default-mode changes relative to its base; required hosted checks passed |
| ID-UNIQUE-INDEX | partial unique index on `identifier`, per collection (with the tenant under multi); duplicate-key races follow the selected resend mode (Q-IDX), including batch item retry | ID-FIRST-MATCH, ID-RESEND-SWITCH | merged as #8894 at `497d08c9` on `dev`; all required hosted checks passed. Full `--batch --no-idf` matrix: 3,443 cells per off/try lane, zero invalid cells, same 33 expected batch differences on MongoDB 5.0.32/8.0.34; remaining differences are cache-only. |

Rules in force (maintainer, 2026-10-26 and 2026-10-27; updated 2026-10-31):

- **Null removes.** An explicit null removes a field on a merged re-send (`WRITE_RESEND=merge-except-treatments`), API v3 PATCH and the socket's `dbUpdate` (RFC 7386; [write contract §6.1](../tenancy/write-contract-spec-2026-10-07.md#61-decided-2026-10-12)). It never does so on PUT or create, and devicestatus never merges.
- **Fallback.** A v1 entries re-send whose identifier matches nothing still matches on `sysTime`+`type`; treatments never fall back. A devicestatus re-send whose identifier is stored replaces the stored record by default (compatibility B, 2026-10-31; it merged from ID-Q2, 2026-10-29); `WRITE_RESEND=merge-except-treatments` keeps that, and `WRITE_RESEND=acknowledge` the rule before it (write nothing, answer with the stored `_id`).
- **Absent identifier.** `identifier` is SHOULD for legacy writers, and the time-key fallback stays. It is MUST for registered controller instances. Revisited as adoption grows.
- **Scope.** Uniqueness is per collection, with the tenant in the key under multi. Values stay globally unique by convention.
- **Re-send after delete.** It is acknowledged with a 2xx naming the stored, deleted record, and the record stays deleted. `WRITE_DELETED_RESEND=revive` (default `stay`, 2026-10-31) restores 15.0.9's re-send that revives a deleted record.
- **Format (2026-10-29, D-LOOP-ID rule 1 and ID-Q6).** Any string of 1 to 256 characters, with no character restriction, percent-encoded in a URL path; a UUID is recommended. A placeholder or over-length value is treated as absent with a warning; refusing it is `WRITE_IDENTIFIER=strict`, off by default. *2026-10-31 (compatibility A):* API v3 refuses a malformed identifier with 400 by default, as 15.0.9 did; API v1, the socket and in-process stay lenient. Which placeholders are named is open (ID-PLACEHOLDER-LIST, [identity specification](spec/identity.md) §5).
- **`_id` (2026-10-29).** A client may still send an ObjectId `_id` over API v1 (legacy). Going forward the server sets `_id` and the client sets `identifier`.
- **Replace on match (2026-10-31, compatibility B; supersedes merge on match of 2026-10-29).** A re-send matching a
  stored record replaces it on every collection, as slice 4 does for treatments. *Extended the same evening:* every
  re-send matched by identifier replaces on every path, including the identifier-first matches for profile, food,
  activity and device status over v1, in-process and the socket; entries over v1 and in-process keep merging, as
  on 15.0.9. Merge stays for edits: API v3 `PATCH` and the socket's `dbUpdate`. `WRITE_RESEND=replace|merge-except-treatments|acknowledge|refuse` (default `replace`) and
  `WRITE_DELETED_RESEND=stay|revive` (default `stay`) are built before the tag as opt-in ways back, parsed with the
  other `WRITE_*` settings; per-client D20 quirks may select a `WRITE_RESEND` mode. Each path that changes is
  listed cell by cell.
- **Re-send after delete, every path (2026-10-29).** "Acknowledged, stays deleted" applies on every path, and
  the spec text is corrected. Every changed cell is documented, so the change can be reverted or adjusted
  as cohort feedback arrives.
- **Records without an identifier.** Natural keys for device status and profile are a separate item,
  ID-NATURAL-KEY, with its own corpus check of what would merge. Food and activity have no natural key.
- **Socket edits and removes, and activity.** Identifier addressing is added where it changes nothing for
  writes that carry no `identifier`: socket `dbUpdate`, `dbUpdateUnset` and `dbRemove` accept an
  `identifier` when there is no `_id`, and activity creates match on `identifier`. This is conditional on
  the extended matrix showing every existing form unchanged.
- **Re-send with changed fields.** Compatibility B/C and the selected `WRITE_RESEND` mode above govern current behavior. The [client survey](../../60-research/tenancy/identity-resend-survey-2026-10-29.md) retains the reason changed Loop/Trio POSTs must be handled deliberately; it does not override the adopted mode.

The rules are in the [identity specification](spec/identity.md) and the [identifier conventions](identifier-conventions.md); the conversation with the Loop maintainers is in [upstream-asks-loop-identifier](upstream-asks-loop-identifier/README.md).

### 4.3 Registration

| slice | builds | needs | check |
|---|---|---|---|
| REG-S0 | capability document and catalogue, read-only, flag off by default | specs | schema validation; flag off is byte-identical to dev |
| REG-S1 | submit, etag, retire; MongoDB store; single mode | REG-S0 | negotiation conformance cases against a booted server (25 of 32 pass, 6 mapped, 1 not applicable) |
| REG-S2 | definitions, leased instances, channels and roles; instances on one flat root, `/api/v4/instances/{instanceId}` | REG-S1 | instance conformance cases |
| REG-S5 | owner actions on a single-tenant site with `API_SECRET` | REG-S1, REG-S2 | owner-action conformance cases |
| REG-S3 | typed writes and read selection | REG-S2, WC-STEP-PATCH, SPEC-ID-AMEND | unregistered writers byte-identical |
| REG-S4 | projected views for older readers | REG-S3 | projection cases |
| HUB-REG-CRM-SEAM | registrations under tenant scope | REG-S2, ST-PG, T30-WIRING | per-mode cases (SPEC-REG-MODES) |

S0, S1, S2 and S5 need no storage work and are one single-tenant PR, draft [#8857](https://github.com/nightscout/cgm-remote-monitor/pull/8857) (`f7a43fed`). S5 comes before S3 because only S3 waits on the write step. #8857 lets a `devicestatus-upload` token register its controller; that role choice is the maintainer's, in the PR. It keeps one holder document per (scope, channel, role), so each role has one live instance. Of the 186 conformance cases, 35 pass, 88 are mapped and 0 fail (at `3be98536`); the rest wait for later slices. The [hub implementer's guide](guides/hub-implementer.md) maps each slice to modules on dev; the [controller guide](guides/new-controller.md) is the same flow from the controller author's side.

### 4.4 Tenancy

The dependency map shows selected work items and their bounded component state.
Its blocked markers preserve unmet acceptance prerequisites even where a useful
preview already passes. The [M0–M6 dashboard](../tenancy/multitenant-delivery-dashboard.md)
is authoritative for milestone gates; accepted slices are not completion percentages.
The adopted M2 bar is tenant-local config/versioned writes, unknown-tenant refusal,
A's token failing on B by signature, no environment/root/key leakage, and separate
owner/data/operator routes. R72 accepts that bounded versioned-write and
route-separation bar; wider catalogue and human-session acceptance remain M6. M4's bar is executed headless clients
plus source-pattern replay for the rest, with **no all-client claim**; Android
emulator work moves to C and iOS is outside the automated lab. M4 still depends on M3.
The [promotion decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06)
own these scope changes. Headless owner `config.ownerPolicy` is retained writer
policy, distinct from the withdrawn authorization reader option.

The [architecture and compatibility comparison](../tenancy/single-and-multitenant-architecture.md)
contains request-flow, isolation and historical-comparison diagrams.

| item | builds | needs |
|---|---|---|
| PLAT-ENTRY | one executable, `bin/nightscout.js`: `single` (today's server, every old start path unchanged) and the operator tools; image ENTRYPOINT, and no image HEALTHCHECK so a boot-error page is not restarted away (D21) | dev |
| PLAT-SERVE | Merged `multitenant` CLI namespace (#8899); R72 accepts bounded M1–M4 preview contracts on draft #8898. R73 accepts functional M5, and later ed2 Compose/restore acceptance is bounded; M6 and production/default admission remain open | PLAT-ENTRY, ST-READS |
| T30-RESEARCH | the tenant-owner configuration surface: 264 settings on dev, 12 contested | D-T30 |
| T30-SCHEMA-CONFIG | Adopted owner-authority writer policy and transactional proposed-grant fencing are retained. Reader clamping is removed; R72 accepts M2 tenant-local config/versioned writes and route separation; wider lifecycle belongs to M6. Selected preview services do not finish this item; historical old-seam gate fails its D15 predicate | T30-RESEARCH |
| TEN-RESOLVE | Direct/canonical preview resolution accepted; full production trust, durable mapping and operator lifecycle still blocked | MT-CONFIG-MIN, MIG-RUNNER, PLAT-SERVE |
| T30-WIRING | Current persisted authority composes with actual CLI/REST. Adopted local new-format token verification keeps per-operation PG session/key/grants; writer proposed-grant fencing is retained; optional reader clamping is withdrawn. Management issuer/refresh, existing-grant lifecycle policy and production trust are M6 work | TEN-RESOLVE, MT-SECRETS-CONTRACT |
| TEN-LAB | R72 promotes M3 after M1/M2, then M4 at the adopted headless/source-pattern scope; no all-client or M6 claim | ST-PG, T30-WIRING, MIG-RUNNER |

Single-tenant on MongoDB stays first-class (D1, D4). The subcommand selects tenancy (maintainer, 2026-10-27): `nightscout single` is single-tenant and the `nightscout multitenant` namespace selects multitenancy (#8899), so the API preview requires explicit multitenant configuration and `TENANCY_MODE` retires as an operator setting. The [interface ownership proposal](interface-ownership-2026-10-27.md) retains its original questions; current separate-process composition and restore boundaries are in the [architecture comparison](../tenancy/single-and-multitenant-architecture.md). The settings census on dev is [t30-census-dev](../../60-research/tenancy/t30-census-dev-2026-10-27.md). The decisions D1–D23 are in the [execution plan](../tenancy/multitenancy-decisions.md).

Tenancy and execution are separate axes (D-EXEC-PROFILE, 2026-10-31). The subcommand selects tenancy; whether a site keeps a resident `ddata` or computes its views from bounded queries is a second choice. R72 accepts request-local loader/cache frames at its bounded M1–M4 scope; R73 accepts the functional multitenant evaluator/realtime reference; M6 retains lifecycle and wider admission work. This does not establish a universal computed execution profile. The independent single/nonresident prototype retains properties between cycles; R50 now measures acquisition races, failed-cycle retention and recovery through actual triggers. R49/R50 retain the measured differences in bounds, frame/future behavior, identity unions, statistics and failure lifecycle. Cost remains unmeasured and default single remains resident. R54/R55 accept a shared private allocation helper behind those separate caller policies. R62/R64 retain the published REST side. The whole independent profile branch remains separate; a private helper/evaluateCycle hunk is reused in the multitenant candidate. R67 bounds recovered clinical constructor evidence. R73 promotes functional M5; the independent computed-single profile retains its separate entry bar. Input acquisition and clinical result persistence are not one atomic operation.

## 5. Decisions and remaining questions

Cards labelled decided describe adopted constraints. Other cards retain their
question and owner; an option marked recommended is a proposal. Select **Show on
the map** to see affected items. The current M5/M6 decision list linked above
contains later tenancy policies; this map does not create a second decision log. Release questions (the 16.0.0 quiet period, cohort requests, when dev reopens) are Q13–Q16 in the [release allocation](release-allocation-2026-10-27.md#5-open-decisions).

<!-- chart: decisions -->

## 6. How the work moves

- **Pull requests.** Sized by milestone, not by slice: the single-tenant registration PR (S0, S1, S2, S5); storage slices grouped into few PRs. A track with many pieces in flight uses an integration branch with child PRs, the way #8605 carried 109 children. Dev is merged into a branch, not rebased, and a PR's merge records that the merged tree matches the reviewed tree.
- **What pins behaviour.** #8854's CRUD matrix and this repository's write-contract matrix (`tools/qc/write-contract-matrix.js`; v1, v3, socket and in-process). A slice that changes no behaviour changes no cell; a slice that changes behaviour lists the cells it changes and why.
- **Red controls.** Every new test is shown failing against the code it guards before the change, with the original symptom.
- **Conformance.** The registration and identity cases in `specs/sync/conformance/` run against a booted server by a harness in this repository (D12), reported case by case as passed, mapped or not applicable.
- **Agents.** Agents build slices in their own worktrees, run the checks and hand back a branch, a PR body and the push commands. They never push. Maintainers push, open, review and merge.
- **Releases.** #8865 (one executable, the image's start and stop, the boot split; `multitenant` is the current namespace after #8899; the explicitly configured separate-process Compose preview is implemented in #8898) merged into 16.0.0 on 2026-10-30. Since 2026-10-30 every single-tenant item of this plan targets 16.0.0 through the entry bar (§1); a miss merges after the tag, one theme per minor; the 16.0.0 quiet period starts when its merge list is closed, not on a date. Components shipped before they are mature are labelled alpha; the label belongs to the multitenant bindings, not to code every single-tenant site runs.
- **Records.** Each landed slice updates its queue item (`queue/work-queue.yaml`) and this plan's data file, and the page is re-rendered.

## 7. Sources

- Current tenancy scope: the operation-window acceptance family and release contents linked in §1; PR #8898 metadata read on 2026-11-08. Older storage, identity, registration and ecosystem figures below retain their named source baselines.

- Historical non-tenancy baseline: cgm-remote-monitor dev `604de1cb`; open PR heads, CI and `dev` distance read with `gh pr list`, `gh pr checks` and `gh api .../compare` on 2026-10-31 (re-read about 22:00Z). The test workflow runs only on pull requests to `dev` or `master`, so #8886 (base `feat/id-first-match`) shows only `auto-close` until it is retargeted.
- [Storage seam interface](../tenancy/nightscout-storage-seam-interface-2026-09-14.md), [write-contract spec](../tenancy/write-contract-spec-2026-10-07.md), [execution plan](../tenancy/multitenancy-decisions.md), [#8854 alignment brief](../modernization/pr-8854-alignment-2026-10-26.md).
- [Registration specification](spec/registration.md), [identity specification](spec/identity.md), [records specification](spec/records.md).
- Nocturne `970031f6`, re-checked at `36d5ef4a2`. Tenant scope is an `ITenantScoped` marker with row-level security. It keeps a sync key (tenant, data source, sync identifier) and a single record-changed seam proposed in its issue #2130. Its API v3 serves `identifier` equal to `_id` (issue #1932).
- Controllers, read at AndroidAPS dev `325e5623`, NightscoutKit `6efa02d4`, Trio dev `7ff1f777e`, xDrip+ `c42cf55c`. AndroidAPS is the only API v3 client and keeps the server's `identifier`. Loop sends `syncIdentifier`, and Trio sends `id`.
