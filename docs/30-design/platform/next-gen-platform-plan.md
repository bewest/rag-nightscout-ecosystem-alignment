# Next-gen platform: one write path, four tracks

*Contributor-facing. Living plan, current at cgm-remote-monitor dev `ca1652d6` (2026-10-27 evening). Milestone M1 is on dev: #8854 (2026-10-26, `c08cbe03`), then on 2026-10-27 #8859 (`94899828`), #8861 (`84fac457`), #8863 (`9668b179`) and #8870 (`7abe1cf6`), so every REST and socket record read, write and count goes through the storage interface in 16.0.0. Still open as drafts: #8862, #8865 and #8857. Status: proposed; the decisions in §6 are open. Which release each item goes in is proposed in [release allocation](release-allocation-2026-10-27.md) (2026-10-27, §0 re-anchored at `ca1652d6`).*

The interactive version, with the dependency map, is the site page [nightscout-next-gen-platform.html](../../../site/pages/nightscout-next-gen-platform.html).

This plan covers the work that follows the 16.0.0 modernization:

- storage behind one write path;
- the client and server identifiers Loop asked to separate;
- controller registration, from a read-only catalogue to typed writes;
- hosted multitenancy.

It names each piece of work, what it needs first, where it goes in the code, and the check that pins it.

## 1. Where things stand

| | on dev `ca1652d6` | in review (draft PRs) | not started |
|---|---|---|---|
| Storage | `WRITE_VALIDATION` (#8841); the write boundary `lib/storage/write-step.js` (#8854); the filter tree and interface, v1 reads (#8861), v1, authorization and socket writes labelled by source (#8863), v1 count only through the interface (#8870): milestone M1 | — | ST-EVENT (decision, bench running), ST-V3-DECOUPLE, write(intent), computed views, backend-selectable harness, PostgreSQL |
| Identity | `identifier` is the client's, `_id` the server's; API v3 refuses a client `_id` (#8845: BF-169, BF-170); v1 entries and devicestatus match on `identifier`, null removes a field (#8859) | — | identifier-first on every path, unique index |
| Registration | nothing in code; dev carries an older proposal schema, `docs/proposals/schemas/controller-instance-registration.schema.json` | #8857 S0, S1, S2, S5, off by default (`f7a43fed`, 64 behind dev, conflicts) | typed writes (S3), projected views (S4) |
| Tenancy | nothing | #8862 PLAT-ENTRY (`b63d9b7f`, 64 behind dev); #8865 PLAT-SERVE (`1dafe2a5`; its base `feat/storage-writes` is merged, so it needs retargeting to dev) | tenant configuration, resolution, tenant-scoped auth, hosted lab |

## 2. Why the tracks meet at the write step

Every track changes what happens when a record is written:

| track | what it needs from the write step |
|---|---|
| Identity | a single place that matches a re-sent record on `identifier` first, then on the time key, for v1, v3 and the socket alike |
| Registration | a single place that applies a controller's declared schema to its typed writes, and leaves unregistered writers byte-identical |
| Validation | a single place for #8841's rules, so the socket and the v1 modules are not checked separately |
| Tenancy | a single place that carries the tenant binding, so no path can write without one |

Draft #8854 builds that place as a boundary at the driver call, and its own follow-up list asks for the rest "in measured slices". The plan below adds those slices one at a time. Each one is pinned by #8854's matrix and by this repository's write-contract matrix (`tools/qc/write-contract-matrix.js`, four paths: v1, v3, socket, in-process). Reviewers read one boundary, and each track adds its rule to it.

## 3. The map

<!-- chart: map -->

## 4. The storage seam: three ways to reach dev

<!-- chart: options -->

What a #8854-first path keeps compatible:

| | must hold | pinned by |
|---|---|---|
| Backward | the `_id` forms: ObjectId, upper- and lower-case hex, UUID, and `UUID_HANDLING` moving a non-hex `_id` to `identifier` | #8854's matrix rows; `tests/identity-matrix.test.js` |
| Backward | the API v3 create and deduplication reply (`status`, `identifier`, `isDeduplication`, `lastModified`), and AndroidAPS's string-matched refusal texts | `tests/write-validation.test.js`; the v3 suites |
| Backward | Loop's `syncIdentifier` and Trio's `id` stored and returned untouched | write-contract matrix |
| Backward | v1 treatment upsert on `created_at` + `eventType` | write-contract matrix |
| Forward | two mature backends (D2–D4): a backend-neutral interface above #8854's boundary, which stays as the MongoDB-edge observer; `write(intent)` above the interface | ST-FILTER to WC-STEP-PATCH |
| Forward | the closed query operator set (D8) as a filter tree | ST-FILTER, the mingo differential |
| Forward | source and origin labels, then a tenant binding, on every write | ST-WRITES, ST-HARNESS, TEN-RESOLVE |
| Forward | one commit fact the change feed (D6) can carry | ST-EVENT (decision D-EVENT) |

The September chain stays useful as reference. Its filter AST (`4f753ab9`), `fromMongo` bridge (`68ffbd66`), `bulkUpsert` mode split, PostgreSQL backend (`983ff64f`, `7cc03cda`) and tenant scope binding are the starting points for ST-FILTER, ST-PG and TEN-RESOLVE. They are not merged as they stand.

The replay trial measured both paths on dev `47723cda`. Branches: `seam/replay-2610` `f41cb244`, `seam/compose-8854-2610` `873c0cbb` and, re-measured at #8854 `fa22d573`, `seam/compose-fa22-2610` `089bbfc5`; all local.

- **The replay works.** The September S1 and S2 commits apply to dev with no test lost: 4,610 passing on dev, 4,698 on the replay (the 88 are the seam's own files). Three write-contract cells change: the v1 hard-delete reply's key order.
- **The seam's interface composes above #8854's boundary.** The two conflict in 2 paths. On the composed branch #8854's 367 tests pass. The one failure is its boundary check flagging the socket, because that file now acquires its collection through the interface; the check needs one rule for this.
- **Which old commits carry over.** The filter-tree and interface commits replay cleanly and keep their measured reasons. The call-site conversions describe code dev has since rewritten, so slices 2 and 3 are re-derived on dev.

## 5. The tracks in detail

### 5.1 Storage

| item | builds | needs | check |
|---|---|---|---|
| PR-8854 | the boundary, read contract, data diagnostics, `--fail-zero`; merged to dev 2026-10-26 (`c08cbe03`) for 16.0.0 | dev | 336-cell matrix equal to dev; AST gate with bypass controls |
| QC-MATRIX-TT | Temporary Target records in reject mode added to the write-contract matrix | PR-8854 | off and reject differ only in the new cells |
| ST-FILTER | slice 1: filter tree and interface methods under the API v3 adapter, composed with the boundary | PR-8854 | both matrices unchanged; the mingo differential |
| ST-READS | slice 2: v1 reads through the interface | ST-FILTER | api.* suites; a new end-to-end `$type`/`$exists` test |
| ST-WRITES | slice 3: v1 and socket writes through the interface, labelled by source | ST-READS | our matrix at 0 cells changed; #8854's per-cell boundary assertions |
| ST-EVENT | the commit event's granularity and contents | PR-8854, D-EVENT | each stored record named once per write |
| ST-COUNT-ONEPATH | API v1 count only through the interface: `lib/server/aggregate.js` loses its constructor pipeline hook and no-store path (decided 2026-10-27, before the 16.0.0 tag) | ST-WRITES | no client-visible change; the BF-70 refusal and the find guard keep their tests |
| ST-V3-DECOUPLE | API v3 without API v1's modules, the socket and the cache, so `serve api` serves it alone (adopted 2026-10-27, M3) | ST-WRITES, PLAT-SERVE | `serve api` passes the API v3 suites (485 pass, 81 fail at #8865 `1dafe2a5`); `single` unchanged |
| WC-STEP-PATCH | slice 4: `write(intent)` -> WriteResult.items[] above the interface; matching, server dates, the null-removes rule and validation move into it; compare-and-set behind an adapter method | ST-WRITES, ST-EVENT | [write-contract spec](../tenancy/write-contract-spec-2026-10-07.md) G1 |
| ST-HARNESS | slice 5: backend-selectable harness, backend selection, tenant scope | WC-STEP-PATCH | `NS_TEST_BACKEND` controls |
| ST-VIEWS | computed views from bounded queries, without a resident `ddata`: page, socket `dataUpdate`, plugins, alarms (adopted 2026-10-27, M4) | ST-READS | each view equal to today's on the corpus fixtures; alarms per the execution plan §7b |
| ST-PG | PostgreSQL with row-level security, entries first | ST-HARNESS | the backend-selectable suite on both stores |

### 5.2 Identity

| item | builds | needs | check |
|---|---|---|---|
| ID-SIMPLE-MATCH | v1 entries and devicestatus match on `identifier`, as treatments do | #8845 | one record after two sends; red control on dev |
| SPEC-ID-AMEND | a conformance case for the mandatory identifier on registered instances; identity I2 and §6 state API v3's refusal of a client `_id` (BF-170) | #8845 | `tools/nsschema` cases |
| ID-FIRST-MATCH | identifier-first on every collection and path | ID-SIMPLE-MATCH, WC-STEP-PATCH, D-LOOP-ID | write-contract matrix |
| ID-BATCH | per-item results in v1 batch replies | WC-STEP-PATCH | one bad item no longer refuses the batch |
| ID-UNIQUE-INDEX | partial unique index on `identifier` | the two above | 0 duplicates measured across the 12-site corpus (ID-DUP-MEASURE) |

The rules are in the [identity specification](spec/identity.md) and the [identifier conventions](identifier-conventions.md). The conversation with the Loop maintainers is recorded in [upstream-asks-loop-identifier](upstream-asks-loop-identifier/README.md).

### 5.3 Registration

| slice | builds | needs | check |
|---|---|---|---|
| REG-S0 | capability document and catalogue, read-only, flag off by default (built) | specs | schema validation; flag off is byte-identical to dev |
| REG-S1 | submit, etag, retire; MongoDB store; single mode (built: 25 of 32 cases pass, 6 mapped, 1 not applicable) | REG-S0 | negotiation conformance cases against a booted server |
| REG-S2 | definitions, leased instances, channels and roles; instances on one flat root, `/api/v4/instances/{instanceId}` (decided 2026-10-26) | REG-S1 | instance conformance cases |
| REG-S5 | owner actions on a single-tenant site with `API_SECRET` | REG-S1, REG-S2 | owner-action conformance cases |
| REG-S3 | typed writes and read selection | REG-S2, WC-STEP-PATCH, SPEC-ID-AMEND | unregistered writers byte-identical |
| REG-S4 | projected views for older readers | REG-S3 | projection cases |
| HUB-REG-CRM-SEAM | registrations under tenant scope | REG-S2, ST-PG, T30-WIRING | per-mode cases (SPEC-REG-MODES) |

Slices S0, S1, S2 and S5 need no storage work and go to dev together as one single-tenant registration PR; S5 comes before S3 because only S3 waits on the write step. S0, S1, S2 and S5 are in draft [#8857](https://github.com/nightscout/cgm-remote-monitor/pull/8857) at `f7a43fed`, which has dev `8dbb60c2` merged in and lets a `devicestatus-upload` token register its controller (v4 decisions round 2; the role choice is put to the maintainer in the PR). Instances sit on one flat root, `/api/v4/instances/{instanceId}`, with the product named in the body (decided 2026-10-26). Of the 186 cases, 35 pass, 88 are mapped and 0 fail (measured at `3be98536`); the rest wait for later slices. Decided 2026-10-26: one holder document per (scope, channel, role) keeps each role to one live instance. The [hub implementer's guide](guides/hub-implementer.md) maps each slice to modules on dev. The [controller guide](guides/new-controller.md) is the same flow from the controller author's side.

### 5.4 Tenancy

| item | builds | needs |
|---|---|---|
| PLAT-ENTRY | one executable, `bin/nightscout.js`: `single` (today's server, every old start path unchanged) and the operator tools; image ENTRYPOINT, and no image HEALTHCHECK so a boot-error page is not restarted away (D21) | dev |
| PLAT-SERVE | `nightscout serve <roles>`: hosted roles carved from `bootevent`, `api` first, each listener bound separately (D5, D7, D16) | PLAT-ENTRY, ST-READS |
| T30-RESEARCH | the tenant-owner configuration surface (277 settings classified) | D-T30 |
| T30-SCHEMA-CONFIG | the per-tenant settings table (D15) | T30-RESEARCH |
| TEN-RESOLVE | tenant resolution and the platform admin interface (D7, D10, D16) | ST-HARNESS, T30-SCHEMA-CONFIG, PLAT-SERVE, ST-V3-DECOUPLE |
| T30-WIRING | tenant-scoped API keys and per-tenant signing keys (D13, D14) | TEN-RESOLVE |
| TEN-LAB | two tenants on PostgreSQL in a Docker Compose lab, isolation checked with a control | ST-PG, T30-WIRING, ST-VIEWS |

Which listener and role owns each API, single-tenant and multitenant, is mapped in [interface ownership](interface-ownership-2026-10-27.md) (2026-10-27, with eight open questions); the tenant settings census re-measured on dev is [t30-census-dev](../../60-research/tenancy/t30-census-dev-2026-10-27.md). The decisions D1–D21 are in the [execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md). Single-tenant on MongoDB stays first-class (D1, D4). Every tenancy item ships behind `TENANCY_MODE=multi`.

## 6. Open decisions

Select **Show on the map** on a card to see which items it holds up.

Decided 2026-10-26: an explicit null removes a field on merge-on-match, API v3 PATCH and the socket's `dbUpdate` (RFC 7386; [write contract §6.1](../tenancy/write-contract-spec-2026-10-07.md#61-decided-2026-10-12)), never on PUT or create, and devicestatus never merges; in 16.0.0, in one shared merge helper.

Decided 2026-10-26 (D-ID-FALLBACK): for 16.0.0 a v1 entries re-send whose identifier matches nothing still matches on `sysTime`+`type`, as today (TEST-ENTRY-UUID-003); treatments never fall back; revisited once identifiers are common. A devicestatus re-send whose identifier is stored writes nothing and is answered with the stored `_id`, on v1 and v3.

Decided 2026-10-26 (D21): Nightscout starts through one executable. `nightscout single` is today's server, hosted roles are `nightscout serve <roles>`, and operator tools are subcommands of the same dispatcher, as Consul, node-multienv and Ory do it. Still open: whether serving every role in one process is part of the multi target.

Decided 2026-10-26: #8854 lands in 16.0.0 after four alignment conditions (outcome B in its [brief](../modernization/pr-8854-alignment-2026-10-26.md)): a per-item socket reply or no socket validation yet, the data-warnings header off or held, the commit event marked internal and unstable, and a separate name for the intent layer.

<!-- chart: decisions -->

## 7. How the work moves

- **Pull requests.** Sized by milestone, not by slice: one single-tenant registration PR (S0, S1, S2, S5); one 16.0.0 re-send and merge contract PR (identifier matching, the null-removes rule, BF-195, the devicestatus answer); the storage slices grouped into few PRs after #8854, the first being ST-FILTER with ST-READS (decided 2026-10-26). A track with many pieces in flight uses an integration branch with child PRs, the way #8605 carried 109 children. Dev is merged into the branch, not rebased. A PR's merge records that the merged tree matches the reviewed tree.
- **What pins behaviour.** #8854's CRUD matrix and this repository's write-contract matrix. A slice that changes no behaviour changes no cell. A slice that changes behaviour lists the cells it changes and why.
- **Red controls.** Every new test is shown failing against the code it guards before the change, with the original symptom.
- **Conformance.** The registration and identity cases in `specs/sync/conformance/` run against a booted server by a harness in this repository (D12), reported case by case as passed, mapped or not applicable.
- **Agents.** Agents build slices in their own worktrees, run the checks and hand back a branch, a PR body and the push commands. They never push. Maintainers push, open, review and merge.
- **Releases.** Decided 2026-10-27 (maintainer, Q12): the seam slices go into 16.0.0 if they meet the entry bar of [release allocation B6](release-allocation-2026-10-27.md#b6-prototypes-in-1600-labelled-alpha-asked-2026-10-27); they met it and merged the same afternoon. Proposed that evening ([§0](release-allocation-2026-10-27.md#0-the-questions-again-after-m1-landed-evening-2026-10-27), Q13–Q16): nothing more from this plan enters 16.0.0; `dev` takes release fixes during the short quiet period the pre-tag definition of done asks for, decisions (D-EVENT, D-T30, identity) are settled meanwhile, and 16.1.0 work merges when `dev` reopens. Components shipped before they are mature are labelled alpha; that label belongs to the multitenant bindings (Q12a).
- **Records.** Each landed slice updates its queue item (`queue/work-queue.yaml`) and this plan's data file, and the page is re-rendered.

## 8. Sources

- cgm-remote-monitor dev `ca1652d6` (2026-10-27 evening); earlier dev `47723cda` and draft #8854 `880b7369` with its data-contracts document.
- [Storage seam interface](../tenancy/nightscout-storage-seam-interface-2026-09-14.md), [write-contract spec](../tenancy/write-contract-spec-2026-10-07.md), [execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md).
- [Registration specification](spec/registration.md), [identity specification](spec/identity.md), [records specification](spec/records.md).
- Nocturne `970031f6`, re-checked at `36d5ef4a2`. Tenant scope is an `ITenantScoped` marker with row-level security. It keeps a sync key (tenant, data source, sync identifier) and a single record-changed seam proposed in its issue #2130. Its API v3 serves `identifier` equal to `_id` (issue #1932).
- Controllers, read at AndroidAPS dev `325e5623`, NightscoutKit `6efa02d4`, Trio dev `7ff1f777e`, xDrip+ `c42cf55c`. AndroidAPS is the only API v3 client and keeps the server's `identifier`. Loop sends `syncIdentifier`, and Trio sends `id`.
