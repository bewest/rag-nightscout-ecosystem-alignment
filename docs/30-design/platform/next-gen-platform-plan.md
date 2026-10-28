# Next-gen platform: one write path, four tracks

*Contributor-facing. Living plan, current at cgm-remote-monitor dev `db3b9e4e` (2026-10-27). Status: proposed; the decisions in §5 are open. Which release each item goes in is proposed in [release allocation](release-allocation-2026-10-27.md).*

The interactive version, with the dependency map, is the site page [nightscout-next-gen-platform.html](../../../site/pages/nightscout-next-gen-platform.html).

This plan covers the work that follows the 16.0.0 modernization:

- storage behind one write path;
- the client and server identifiers Loop asked to separate;
- controller registration, from a read-only catalogue to typed writes;
- multitenant Nightscout.

It names each piece of work, what it needs first, where it goes in the code, and the check that pins it.

## 1. Where things stand

| | on dev `db3b9e4e` (ships in 16.0.0) | in review (draft PRs) | not started |
|---|---|---|---|
| Storage | `WRITE_VALIDATION` (#8841); the write boundary `lib/storage/write-step.js` (#8854); the filter tree and interface with v1 reads (#8861); v1, authorization and socket writes labelled by source (#8863); v1 count only through the interface (#8870). Every REST and socket record read, write and count goes through the storage interface (milestone M1) | — | ST-V3-DECOUPLE, `write(intent)`, ST-EVENT (decision deferred, research continuing), computed views, backend-selectable harness, PostgreSQL |
| Identity | `identifier` is the client's, `_id` the server's; API v3 refuses a client `_id` (#8845); v1 entries and devicestatus match on `identifier`, and an explicit null removes a field (#8859) | — | identifier-first on every path, unique index |
| Registration | specifications only; dev also carries an older proposal schema, `docs/proposals/schemas/controller-instance-registration.schema.json` | #8857: S0, S1, S2, S5, off by default (`f7a43fed`, 64 behind dev, conflicts) | typed writes (S3), projected views (S4) |
| Tenancy | nothing | #8865 PLAT-SERVE (`f01d67e6`, base dev, open), which supersedes #8862 PLAT-ENTRY by carrying its commits | tenant configuration, resolution, tenant-scoped auth, multitenant lab |

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

The forward constraints are two mature backends behind one interface (D2–D4), the closed query operator set as a filter tree (D8), a source label and later a tenant binding on every write, and one commit fact the change feed can carry (D6; D-EVENT deferred until WC-STEP-PATCH and a first subscriber exist). Under #8854's merge conditions, the commit event stays internal and unstable, and the intent layer gets its own name.

## 3. The map

<!-- chart: map -->

## 4. The tracks in detail

### 4.1 Storage

Done, in 16.0.0: PR-8854, QC-MATRIX-TT (360 cells), ST-FILTER, ST-READS, ST-WRITES, ST-COUNT-ONEPATH.

| item | builds | needs | check |
|---|---|---|---|
| WC-STEP-PATCH | in progress (session -4f, milestone 1): `write(intent)` -> WriteResult.items[] above the interface; matching, server dates, the null-removes rule and validation move into it; compare-and-set behind an adapter method | ST-WRITES | [write-contract spec](../tenancy/write-contract-spec-2026-10-07.md) G1 |
| ST-V3-DECOUPLE | API v3 without API v1's modules, the socket and the cache, so `serve api` serves it alone (M3) | ST-WRITES, PLAT-SERVE | `serve api` passes the API v3 suites (485 pass, 81 fail at #8865 `1dafe2a5`); `single` unchanged |
| ST-EVENT | the commit event names the records of each write, from WriteResult.items[] | WC-STEP-PATCH, D-EVENT (deferred) | each stored record named once per write |
| ST-HARNESS | backend-selectable harness, backend selection, tenant scope | WC-STEP-PATCH | `NS_TEST_BACKEND` controls |
| ST-VIEWS | computed views from bounded queries, without a resident `ddata`: page, socket `dataUpdate`, plugins, alarms (M4) | ST-READS | each view equal to today's on the corpus fixtures; alarms per the execution plan §7b |
| ST-PG | PostgreSQL with row-level security, entries first | ST-HARNESS | the backend-selectable suite on both stores |

The September seam chain is kept as reference for ST-HARNESS, ST-PG and TEN-RESOLVE (commits named on each item); it is not merged as it stands.

### 4.2 Identity

Done, in 16.0.0: DEV-8845, ID-SIMPLE-MATCH.

| item | builds | needs | check |
|---|---|---|---|
| SPEC-ID-AMEND | a conformance case for the mandatory identifier on registered instances; identity I2 and §6 state API v3's refusal of a client `_id` (BF-170) | #8845 | `tools/nsschema` cases |
| ID-FIRST-MATCH | identifier-first on every collection and path | ID-SIMPLE-MATCH, WC-STEP-PATCH, D-LOOP-ID | write-contract matrix |
| ID-BATCH | per-item results in v1 batch replies | WC-STEP-PATCH | one bad item no longer refuses the batch |
| ID-UNIQUE-INDEX | partial unique index on `identifier`, per collection (with the tenant under multi) | the two above | 0 duplicates measured across the 12-site corpus (ID-DUP-MEASURE) |

Rules in force (maintainer, 2026-10-26 and 2026-10-27):

- **Null removes.** An explicit null removes a field on merge-on-match, API v3 PATCH and the socket's `dbUpdate` (RFC 7386; [write contract §6.1](../tenancy/write-contract-spec-2026-10-07.md#61-decided-2026-10-12)). It never does so on PUT or create, and devicestatus never merges.
- **Fallback.** A v1 entries re-send whose identifier matches nothing still matches on `sysTime`+`type`; treatments never fall back. A devicestatus re-send whose identifier is stored writes nothing and is answered with the stored `_id`.
- **Absent identifier.** `identifier` is SHOULD for legacy writers, and the time-key fallback stays. It is MUST for registered controller instances. Revisited as adoption grows.
- **Scope.** Uniqueness is per collection, with the tenant in the key under multi. Values stay globally unique by convention.
- **Re-send after delete.** It is acknowledged with a 2xx naming the stored, deleted record, and the record stays deleted.

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

| item | builds | needs |
|---|---|---|
| PLAT-ENTRY | one executable, `bin/nightscout.js`: `single` (today's server, every old start path unchanged) and the operator tools; image ENTRYPOINT, and no image HEALTHCHECK so a boot-error page is not restarted away (D21) | dev |
| PLAT-SERVE | `nightscout serve <roles>`: multitenant roles carved from `bootevent`, `api` first, each listener bound separately (D5, D7, D16) | PLAT-ENTRY, ST-READS |
| T30-RESEARCH | the tenant-owner configuration surface: 264 settings on dev, 12 contested | D-T30 |
| T30-SCHEMA-CONFIG | the per-tenant settings table (D15) | T30-RESEARCH |
| TEN-RESOLVE | tenant resolution and the platform admin interface (D7, D10, D16) | ST-HARNESS, T30-SCHEMA-CONFIG, PLAT-SERVE, ST-V3-DECOUPLE |
| T30-WIRING | tenant-scoped API keys and per-tenant signing keys (D13, D14) | TEN-RESOLVE |
| TEN-LAB | two tenants on PostgreSQL in a Docker Compose lab, isolation checked with a control | ST-PG, T30-WIRING, ST-VIEWS |

Single-tenant on MongoDB stays first-class (D1, D4), and every tenancy item ships behind `TENANCY_MODE=multi`. Which listener and role owns each API is mapped in [interface ownership](interface-ownership-2026-10-27.md), with its eight open questions (among them whether serving every role in one process is part of the multi target). The settings census on dev is [t30-census-dev](../../60-research/tenancy/t30-census-dev-2026-10-27.md). The decisions D1–D21 are in the [execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md).

## 5. Open decisions

Select **Show on the map** on a card to see which items it holds up. Release questions (the 16.0.0 quiet period, cohort requests, when dev reopens) are Q13–Q16 in the [release allocation](release-allocation-2026-10-27.md#5-open-decisions).

<!-- chart: decisions -->

## 6. How the work moves

- **Pull requests.** Sized by milestone, not by slice: the single-tenant registration PR (S0, S1, S2, S5); storage slices grouped into few PRs. A track with many pieces in flight uses an integration branch with child PRs, the way #8605 carried 109 children. Dev is merged into a branch, not rebased, and a PR's merge records that the merged tree matches the reviewed tree.
- **What pins behaviour.** #8854's CRUD matrix and this repository's write-contract matrix (`tools/qc/write-contract-matrix.js`; v1, v3, socket and in-process). A slice that changes no behaviour changes no cell; a slice that changes behaviour lists the cells it changes and why.
- **Red controls.** Every new test is shown failing against the code it guards before the change, with the original symptom.
- **Conformance.** The registration and identity cases in `specs/sync/conformance/` run against a booted server by a harness in this repository (D12), reported case by case as passed, mapped or not applicable.
- **Agents.** Agents build slices in their own worktrees, run the checks and hand back a branch, a PR body and the push commands. They never push. Maintainers push, open, review and merge.
- **Releases.** Nothing more from this plan is proposed for 16.0.0 except, if the maintainer chooses, #8865 (one executable and `serve api`). The rest merges to dev after the 16.0.0 tag, one theme per minor; the 16.0.0 quiet period starts when its merge list is closed, not on a date. Components shipped before they are mature are labelled alpha; the label belongs to the multitenant bindings, not to code every single-tenant site runs.
- **Records.** Each landed slice updates its queue item (`queue/work-queue.yaml`) and this plan's data file, and the page is re-rendered.

## 7. Sources

- cgm-remote-monitor dev `ca1652d6`; open PR heads read with `gh pr view` on 2026-10-27.
- [Storage seam interface](../tenancy/nightscout-storage-seam-interface-2026-09-14.md), [write-contract spec](../tenancy/write-contract-spec-2026-10-07.md), [execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md), [#8854 alignment brief](../modernization/pr-8854-alignment-2026-10-26.md).
- [Registration specification](spec/registration.md), [identity specification](spec/identity.md), [records specification](spec/records.md).
- Nocturne `970031f6`, re-checked at `36d5ef4a2`. Tenant scope is an `ITenantScoped` marker with row-level security. It keeps a sync key (tenant, data source, sync identifier) and a single record-changed seam proposed in its issue #2130. Its API v3 serves `identifier` equal to `_id` (issue #1932).
- Controllers, read at AndroidAPS dev `325e5623`, NightscoutKit `6efa02d4`, Trio dev `7ff1f777e`, xDrip+ `c42cf55c`. AndroidAPS is the only API v3 client and keeps the server's `identifier`. Loop sends `syncIdentifier`, and Trio sends `id`.
