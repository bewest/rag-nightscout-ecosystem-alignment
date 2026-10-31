# Next-gen platform: one write path, four tracks

*Contributor-facing. Living plan, current at cgm-remote-monitor dev `37b2280f` (2026-10-31, #8883 and #8882 merged), with open PR heads and CI re-read from GitHub at about 16:40Z that day. Status: proposed; the decisions in §5 are open. Which release each item goes in is proposed in [release allocation](release-allocation-2026-10-27.md).*

The interactive version, with the dependency map, is the site page [nightscout-next-gen-platform.html](../../../site/pages/nightscout-next-gen-platform.html).

This plan covers the work that follows the 16.0.0 modernization:

- storage behind one write path;
- the client and server identifiers Loop asked to separate;
- controller registration, from a read-only catalogue to typed writes;
- multitenant Nightscout.

It names each piece of work, what it needs first, where it goes in the code, and the check that pins it.

## 1. Where things stand

| | on dev `37b2280f` (ships in 16.0.0) | in review (draft PRs) | not started |
|---|---|---|---|
| Storage | `WRITE_VALIDATION` (#8841); the write boundary `lib/storage/write-step.js` (#8854); the filter tree and interface with v1 reads (#8861); v1, authorization and socket writes labelled by source (#8863); v1 count only through the interface (#8870). Every REST and socket record read, write and count goes through the storage interface (milestone M1). ST-V3-DECOUPLE (with #8865, 2026-10-30). `write(intent)` release 1, every write path through one step (#8874, `368e6c23`, 2026-10-31) | ST-HARNESS, draft #8881 (`ffa5e6b4`); ST-VIEWS, draft #8875 (`24647c0a`) | `write(intent)` release 2 (filter writes resolved to ids, one write shape for API v3), ST-EVENT (D-EVENT decided 2026-10-31: a per-write event from items[], with release 2), PostgreSQL |
| Identity | `identifier` is the client's, `_id` the server's; API v3 refuses a client `_id` (#8845); v1 entries and devicestatus match on `identifier`, and an explicit null removes a field (#8859) | merged 2026-10-30: #8877 (`cf3d4b8f`; BF-209, BF-211; BF-210 withdrawn) and #8878 (`d51c7a60`; BF-212 first part). ID-FIRST-MATCH, draft #8879 (`f5bd2642`, CI green): slices 1, 2, 5, 3 and 4. SPEC-ID-AMEND done in this repository (2026-10-30) | slices 6 and 6a (prepared), the unique index (built locally), ID-BATCH (prototype) |
| Registration | specifications only; dev also carries an older proposal schema, `docs/proposals/schemas/controller-instance-registration.schema.json` | #8857: S0, S1, S2, S5, off by default (`10fe6725`, 25 behind dev) | typed writes (S3), projected views (S4) |
| Tenancy | nothing | merged 2026-10-30: #8865 PLAT-SERVE with ST-V3-DECOUPLE and PLAT-ENTRY (`991b0654`; #8862 closed as superseded) | tenant configuration, resolution, tenant-scoped auth, multitenant lab |

## 1. 16.0.0 scope (maintainer, 2026-10-30)

16.0.0 targets **every single-tenant item of this plan**, through the entry bar and in priority order. A
miss rolls to 16.1.0, or to 17.0.0 if it changes a default.
- **The identity work is the core.** It is the substance of the agreement with the Loop maintainers:
  identifier-first on every path, re-sends recognised, the format rules, and one record per identifier.
- **The unique index on `identifier` is in 16.0.0**, behind `WRITE_IDENTIFIER_INDEX=try|require|off`
  (default `try`).
  - Under `try`, boot attempts a partial unique index per collection: records with an `identifier`,
    soft-deleted ones included, built online. If existing duplicates block it, the counts per collection
    (never the values) are logged and shown on the status page, and the server runs without the index.
  - The write rule (ID-Q5) still refuses to create a second record with a stored identifier.
  - `require` refuses to start until the index exists. `off` skips it.
  - An operator-run tool reports duplicate groups and resolves them by the P4 pick.
- **Multitenant items may ship dormant, labelled alpha behind `serve`, or not ship.**

Feasibility, from the 7 days to 2026-10-30: 53 PRs merged into `dev`, and 14 of this plan's 36 items went
to done. Build speed is not the limit. Time on `dev`, cohort checks and review are, so items land in
priority order and early, and the tag is gated by the bar, not by a date.

## 1a. Priority and merge order (2026-10-29)

Identity moved up on 2026-10-29, because most of the week's defects came from records matched by
different rules on different paths: BF-121's socket gap, BF-209, and the chart split's shared
identity (BF-212, where a re-send can overwrite another record's amount). D-LOOP-ID's three rules are now decided. On 2026-10-30 the maintainer put every single-tenant item into 16.0.0's scope (§1), so identity work goes
through the entry bar before the tag, directly after `write(intent)`; ID-FIRST-MATCH slice 1 started that day.

**Before the 16.0.0 tag**, in this order:

| # | PR | risk | what review should look at |
|---|---|---|---|
| 1 | **merged 2026-10-30 (`cf3d4b8f`)**: #8877, BF-209 + BF-211 (BF-210 withdrawn 2026-10-29) | changes which socket treatment uploads are stored as separate records. That is dosing data, for AndroidAPS 3.4.2.x v1 users and the chart-drag split | the identity rule's equivalence for the exact match (559,872 inputs); the three flipped gate fixtures; the one matrix cell that moves (`treatments × v3 × ws`). Ask an AndroidAPS 3.4.2.x v1 cohort to check carbs and boluses |
| 2 | **merged 2026-10-30 (`991b0654`)**: #8865, one executable and the boot split | every site starts through it, so it carries the release's widest operational change | the image's `nightscout single` start, `npm start`, Heroku/Docker/Azure forms, SIGTERM shutdown. Ask each hosting cohort to check it |
| 2a | **merged 2026-10-30 (`d51c7a60`)**: #8878, BF-212 first part: the chart split stops copying identity fields | low; changes only what the moved half of a chart drag carries | the unit test (red on dev) and the reproduction probe; the re-upload double count remains |
| 3 | **merged 2026-10-30 with #8877 (`cf3d4b8f`)**: BF-211, per-collection cache flush | low; changes only which caches a delete by query empties | the red/green control from `tools/lab/cache-value`; v1 deletes by query and API v3 auto-prune |
| 3a | #8855, Crowdin | low | none beyond the usual |
| 3c | **merged 2026-10-31 (`2f50d944`)**: #8883 (head `789d5d9d`): BF-219, BF-220, BF-221 (v1 treatment and entry writes) and BF-222 (API v3 autoPrune names what it deletes to the cache); #8879 takes it in its `dev` merge (four-file conflict, session -4e) | dosing-relevant reply and announcement fixes | HTTP-level tests red on `dev`; the write-step port reviewed |
| 3d | **merged 2026-10-31 (`37b2280f`)**: #8882 (head `32cd90e6`): hygiene, the development lint popup and drawer resize. The resize handler now registers at the first open (`2737756d`), so loading `browser-utils` without a window no longer throws | display only | browser test red on `dev` |
| 3b | **merged 2026-10-30 (`305a6533`, #8880)**: BF-213, BF-214, BF-217: a missed URGENT pump alarm, a pump-plugin crash that hides every pump alarm, a device-status cache gap; BF-213 alarms at Loop's severity (maintainer, 2026-10-30) | Loop users with pump alerts get new pump alarms | each fix red then green; the release-notes line |
| 4 | BF-72 and BF-161 fork branches | security fixes held outside the public PR list until release ([register](../remedial/nightscout-backfix-register.md)) | brought up to `dev` and merged before the tag |
| 5 | #8824, dev to master | blocked by master protection, which requires `Run Tests (22, 6)`, `(22, 4.4)` and `(24, 6)` plus one approving review | fix the required check, then merge and tag |

**Eligible for 16.0.0 through an entry bar** (maintainer, 2026-10-29): rows 8 and 9 below, plus the
re-send switch, in that order. Each joins the merge list when its matrix result is as stated, its red
controls and ablations pass, a revert has been rehearsed, and it has had time on `dev` with its cohort
check. Whatever has not cleared the bar at the tag rolls to 16.1.0. 16.0.0 is already a major, so identity
rules that change outcomes may land there instead of 17.0.0.

**Next, through the bar** (2026-10-30: every single-tenant row targets 16.0.0; a miss rolls to 16.1.0, or to 17.0.0 if it changes a default):

| # | work | release | risk | review |
|---|---|---|---|---|
| 6 | **done 2026-10-30** (this repository, `b982fbdd8`): SPEC-ID-AMEND, spec and conformance only | 16.0.0 through the bar | none for sites | case-by-case conformance report |
| 7 | #8857, registration S0-S2, S5 | 16.0.0 through the bar | off by default; at `10fe6725` with `dev` `305a6533` merged in, 25 commits behind `dev` | the flag stays off; D-REG-FLAG (where the catalogue lives) |
| 8 | **merged 2026-10-31 (`368e6c23`)**: #8874 plus slices 4 and 6, `write(intent)` release 1 | 16.0.0 (at `4f9fc4cd` against dev `991b0654`: 0 of 1,929 cells outside `cache`, merge revert rehearsed). Its cohort check is one window with the identity work, opening when slices 3 and 4 are on `dev` | every write moves, behaviour-neutral by the matrix | G1 at 0 cells; the slice 6 dedupe gate; per-rule ablations; review commit by commit |
| 9 | ID-FIRST-MATCH as three landings, A (slices 1, 2, 5), B (3, 4) and C (6, 6a, then ID-UNIQUE-INDEX), in hours to days with one cohort window over the set, as two PRs: one identity PR for A, B and C1, then the index (maintainer, 2026-10-30): slices 1, 2, 5, 3, 4, 6, 6a, then ID-UNIQUE-INDEX (`WRITE_IDENTIFIER_INDEX`, with the duplicate-key retry inside the write step), then ID-BATCH ([design note](id-batch-design-note-2026-10-30.md)) | 16.0.0 through the bar, in that order (index before ID-BATCH: maintainer, 2026-10-30). Draft **#8879** (base `dev`, head `f5bd2642`, 0 behind `dev` `368e6c23`, CI green): slices 1, 2, 5 (with 5b's 409 rule), 3 and 4 (merge on match, treatments `replaced` on every path) pushed; 6 and 6a prepared; the unique index built on slice 3 and held for 6a; ID-BATCH's questions decided. `WRITE_IDENTIFIER=strict` covers v3 and the socket; v1 gets it with ID-BATCH (ID-STRICT-V1) | re-send matching on every path | the re-send table in the [identity reference §2.7](../../10-domain/record-identity-reference.md); D-LOOP-ID's per-client switch |
| 10 | #8875 ST-VIEWS (maintainer, 2026-10-30): in 16.0.0 in steps. Draft at `24647c0a` (25 behind `dev`): with the newest treatment read within 60 h and the full resident windows (60 h treatments, 24 h device status), both views equal the resident path on 126,092 replayed minutes each. *Maintainer, 2026-10-31:* ships in 16.0.0 unwired, because `serve` has no role that runs alarms yet (only `api` starts). The wiring moves to the one-tenant computed profile prototype (ST-VIEWS-PROFILE, D-EXEC-PROFILE) and later to the multitenant roles; `single` keeps the resident path | 16.0.0 (unwired) | alarms are safety-relevant | the replay lab's per-dataset table at 0 differing minutes, its break-it controls and noise floor; alarm cohort checks (execution plan §7b) |
| 11 | #8810, AndroidAPS iOS push | 16.0.0 if its review items close, else 16.1.0 | device tokens are readable by read tokens | its four review items, with the author |

Research that informs the order, without being in it: the cache-value lab (BF-211), the cache
catch-up lab (rounds 1–3: release 2 resolves filter writes to ids, and API v3 takes the same write
shape; it found BF-222), and the extended write-contract matrix (QC-MATRIX-IDF), which found BF-212. The maintainer's direction on BF-212: a lossy edit of a controller-claimed record needs a
manual confirmation. Two records already sharing an identifier is a question for the ID-FIRST-MATCH design.

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

The forward constraints are two mature backends behind one interface (D2–D4), the closed query operator set as a filter tree (D8), a source label and later a tenant binding on every write, and one commit fact the change feed can carry (D6; D-EVENT decided 2026-10-31: one in-process event per write, named from WriteResult.items[], and the per-database-call event kept as backend instrumentation; delivery between processes is decided with the serve roles; its card in §5). Under #8854's merge conditions, the commit event stays internal and unstable, and the intent layer gets its own name.

## 3. The map

<!-- chart: map -->

## 4. The tracks in detail

### 4.1 Storage

Done, in 16.0.0: PR-8854, QC-MATRIX-TT (360 cells), ST-FILTER, ST-READS, ST-WRITES, ST-COUNT-ONEPATH, ST-V3-DECOUPLE, WC-STEP-PATCH (release 1).

| item | builds | needs | check |
|---|---|---|---|
| WC-STEP-PATCH | release 1 merged as #8874 (`368e6c23`, no behaviour change); release 2 resolves filter writes to ids and gives API v3 the same write shape (Q9, Q-U, Q-A): `write(intent)` -> WriteResult.items[] above the interface; matching, server dates, the null-removes rule and validation move into it; compare-and-set behind an adapter method | ST-WRITES | [write-contract spec](../tenancy/write-contract-spec-2026-10-07.md) G1 |
| ST-V3-DECOUPLE | merged with #8865 (`991b0654`): API v3 without API v1's modules, the socket and the cache, so `serve api` serves it alone (M3) | ST-WRITES, PLAT-SERVE | `serve api` passes the API v3 suites (634 pass, 0 fail, 108 single-only pending, as reported at `9f7f84f8`); `single` unchanged |
| ST-EVENT | the commit event names the records of each write, from WriteResult.items[] (the cache no longer needs it: release 2 resolves filter writes to ids in the write step, maintainer 2026-10-30) | WC-STEP-PATCH, D-EVENT (decided 2026-10-31) | each stored and refused record named once per write |
| ST-HARNESS | draft #8881 (`ffa5e6b4`): backend-selectable harness, backend selection, tenant scope | WC-STEP-PATCH | `NS_TEST_BACKEND` controls |
| ST-VIEWS | draft #8875 at `24647c0a`, not wired in; equal to the resident path on 126,092 replayed minutes per view, in review: computed views from bounded queries, without a resident `ddata`: page, socket `dataUpdate`, plugins, alarms (M4) | ST-READS | each view equal to today's on the corpus fixtures; alarms per the execution plan §7b |
| ST-VIEWS-PROFILE | prototype (2026-10-31), not in 16.0.0: a single-tenant start profile with no resident `ddata`; after each write and on a timer it computes the alarms view, and it serves the properties view on request; `single` unchanged (D-EXEC-PROFILE) | ST-VIEWS | replay lab through the profile's trigger at 0 differing minutes; execution plan §7b; resident against computed cost and its break-even |
| ST-PG | PostgreSQL with row-level security, entries first | ST-HARNESS | the backend-selectable suite on both stores |

The September seam chain is kept as reference for ST-HARNESS, ST-PG and TEN-RESOLVE (commits named on each item); it is not merged as it stands.

### 4.2 Identity

Done, in 16.0.0: DEV-8845, ID-SIMPLE-MATCH. Done in this repository: SPEC-ID-AMEND (2026-10-30).

| item | builds | needs | check |
|---|---|---|---|
| SPEC-ID-AMEND | a conformance case for the mandatory identifier on registered instances; identity I2 and §6 state API v3's refusal of a client `_id` (BF-170) | #8845 | `tools/nsschema` cases |
| ID-FIRST-MATCH | identifier-first on every collection and path | ID-SIMPLE-MATCH, WC-STEP-PATCH (D-LOOP-ID's rules decided 2026-10-29) | write-contract matrix; the re-send table, identity reference §2.7 |
| ID-BATCH | per-item results in v1 batch replies | WC-STEP-PATCH | one bad item no longer refuses the batch |
| ID-UNIQUE-INDEX | partial unique index on `identifier`, per collection (with the tenant under multi) | the two above | 0 duplicates measured across the 12-site corpus (ID-DUP-MEASURE) |

Rules in force (maintainer, 2026-10-26 and 2026-10-27):

- **Null removes.** An explicit null removes a field on merge-on-match, API v3 PATCH and the socket's `dbUpdate` (RFC 7386; [write contract §6.1](../tenancy/write-contract-spec-2026-10-07.md#61-decided-2026-10-12)). It never does so on PUT or create, and devicestatus never merges.
- **Fallback.** A v1 entries re-send whose identifier matches nothing still matches on `sysTime`+`type`; treatments never fall back. A devicestatus re-send whose identifier is stored merges by default since ID-Q2 (2026-10-29); `WRITE_RESEND=acknowledge` keeps the earlier rule (write nothing, answer with the stored `_id`).
- **Absent identifier.** `identifier` is SHOULD for legacy writers, and the time-key fallback stays. It is MUST for registered controller instances. Revisited as adoption grows.
- **Scope.** Uniqueness is per collection, with the tenant in the key under multi. Values stay globally unique by convention.
- **Re-send after delete.** It is acknowledged with a 2xx naming the stored, deleted record, and the record stays deleted.
- **Format (2026-10-29, D-LOOP-ID rule 1 and ID-Q6).** Any string of 1 to 256 characters, with no character restriction, percent-encoded in a URL path; a UUID is recommended. A placeholder or over-length value is treated as absent with a warning; refusing it is `WRITE_IDENTIFIER=strict`, off by default. Which placeholders are named is open (ID-PLACEHOLDER-LIST, [identity specification](spec/identity.md) §5).
- **`_id` (2026-10-29).** A client may still send an ObjectId `_id` over API v1 (legacy). Going forward the server sets `_id` and the client sets `identifier`.
- **Merge on match (2026-10-29).** When a re-send matching a stored record is applied, fields it leaves out are
  kept (RFC 7386), and `PUT` replaces. The census reads replace on several paths today. The extended matrix
  measures each path first, and each path that changes is listed cell by cell.
- **Re-send after delete, every path (2026-10-29).** "Acknowledged, stays deleted" applies on every path, and
  the spec text is corrected. Every changed cell is documented, so the change can be reverted or adjusted
  as cohort feedback arrives.
- **Records without an identifier.** Natural keys for device status and profile are a separate item,
  ID-NATURAL-KEY, with its own corpus check of what would merge. Food and activity have no natural key.
- **Socket edits and removes, and activity.** Identifier addressing is added where it changes nothing for
  writes that carry no `identifier`: socket `dbUpdate`, `dbUpdateUnset` and `dbRemove` accept an
  `identifier` when there is no `_id`, and activity creates match on `identifier`. This is conditional on
  the extended matrix showing every existing form unchanged.
- **Re-send with changed fields (2026-10-29).** Merge on match stays the default, because Loop and Trio re-send changed doses, overrides and temp targets by `POST` ([client survey](../../60-research/tenancy/identity-resend-survey-2026-10-29.md)). API v3 keeps refusing a changed date, device or event type, and `PUT` replaces. A site setting plus per-client quirks (D20) may opt a client into keep-first or refuse. A default changes only in a major: 16.0.0 if it clears the entry bar (§1a), otherwise 17.0.0.

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

Single-tenant on MongoDB stays first-class (D1, D4). The subcommand selects tenancy (maintainer, 2026-10-27): `nightscout single` is single-tenant and every `nightscout serve` role is multitenant, so every tenancy item ships behind `serve` and `TENANCY_MODE` retires as an operator setting. Which listener and role owns each API is mapped in [interface ownership](interface-ownership-2026-10-27.md), with its eight open questions (among them whether serving every role in one process is part of the multi target). The settings census on dev is [t30-census-dev](../../60-research/tenancy/t30-census-dev-2026-10-27.md). The decisions D1–D21 are in the [execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md).

Tenancy and execution are separate axes (D-EXEC-PROFILE, 2026-10-31). The subcommand selects tenancy; whether a site keeps a resident `ddata` or computes its views from bounded queries is a second choice. Today the two are coupled (`single` resident, `serve` computed). A third profile, one tenant computed on demand, is being prototyped as ST-VIEWS-PROFILE, and the execution mode is chosen by measured cost and equality, keeping the resident path wherever it is the cheaper one.

## 5. Open decisions

Select **Show on the map** on a card to see which items it holds up. Release questions (the 16.0.0 quiet period, cohort requests, when dev reopens) are Q13–Q16 in the [release allocation](release-allocation-2026-10-27.md#5-open-decisions).

<!-- chart: decisions -->

## 6. How the work moves

- **Pull requests.** Sized by milestone, not by slice: the single-tenant registration PR (S0, S1, S2, S5); storage slices grouped into few PRs. A track with many pieces in flight uses an integration branch with child PRs, the way #8605 carried 109 children. Dev is merged into a branch, not rebased, and a PR's merge records that the merged tree matches the reviewed tree.
- **What pins behaviour.** #8854's CRUD matrix and this repository's write-contract matrix (`tools/qc/write-contract-matrix.js`; v1, v3, socket and in-process). A slice that changes no behaviour changes no cell; a slice that changes behaviour lists the cells it changes and why.
- **Red controls.** Every new test is shown failing against the code it guards before the change, with the original symptom.
- **Conformance.** The registration and identity cases in `specs/sync/conformance/` run against a booted server by a harness in this repository (D12), reported case by case as passed, mapped or not applicable.
- **Agents.** Agents build slices in their own worktrees, run the checks and hand back a branch, a PR body and the push commands. They never push. Maintainers push, open, review and merge.
- **Releases.** #8865 (one executable, the image's start and stop, the boot split; `serve` reserved for a multitenant Nightscout, every role refused until it is multitenant) merged into 16.0.0 on 2026-10-30. Since 2026-10-30 every single-tenant item of this plan targets 16.0.0 through the entry bar (§1); a miss merges after the tag, one theme per minor; the 16.0.0 quiet period starts when its merge list is closed, not on a date. Components shipped before they are mature are labelled alpha; the label belongs to the multitenant bindings, not to code every single-tenant site runs.
- **Records.** Each landed slice updates its queue item (`queue/work-queue.yaml`) and this plan's data file, and the page is re-rendered.

## 7. Sources

- cgm-remote-monitor dev `37b2280f`; open PR heads, CI and `dev` distance read with `gh pr list`, `gh pr checks` and `gh api .../compare` on 2026-10-31 (re-read about 16:40Z).
- [Storage seam interface](../tenancy/nightscout-storage-seam-interface-2026-09-14.md), [write-contract spec](../tenancy/write-contract-spec-2026-10-07.md), [execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md), [#8854 alignment brief](../modernization/pr-8854-alignment-2026-10-26.md).
- [Registration specification](spec/registration.md), [identity specification](spec/identity.md), [records specification](spec/records.md).
- Nocturne `970031f6`, re-checked at `36d5ef4a2`. Tenant scope is an `ITenantScoped` marker with row-level security. It keeps a sync key (tenant, data source, sync identifier) and a single record-changed seam proposed in its issue #2130. Its API v3 serves `identifier` equal to `_id` (issue #1932).
- Controllers, read at AndroidAPS dev `325e5623`, NightscoutKit `6efa02d4`, Trio dev `7ff1f777e`, xDrip+ `c42cf55c`. AndroidAPS is the only API v3 client and keeps the server's `identifier`. Loop sends `syncIdentifier`, and Trio sends `id`.
