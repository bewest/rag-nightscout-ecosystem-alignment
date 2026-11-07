# AID Alignment Workspace - Progress Tracker

This document is the dated journal of the **ecosystem research** facets (mappings, specs,
conformance, deep dives). Programme state for cgm-remote-monitor (merges, decisions, test runs,
handoffs) is recorded in `releases/<product>-<version>/`, not here; see `AGENTS.md` §3.

> **Archive**: Older entries moved to:
> - [progress-archive-2026-02-to-09.md](docs/archive/progress-archive-2026-02-to-09.md) (Feb–Sep 2026: telemetry design, EXP-29xx closeouts, AAPS profile sync)
> - [progress-archive-2026-03-18-to-31.md](docs/archive/progress-archive-2026-03-18-to-31.md) (Phase 1-3 cross-validation, simulation, gap coverage)
> - [progress-archive-2026-02-01.md](docs/archive/progress-archive-2026-02-01.md) (14 entries)
> - [progress-archive-2026-01-30-batch1.md](docs/archive/progress-archive-2026-01-30-batch1.md)
> - [progress-archive-2026-01-30-batch2.md](docs/archive/progress-archive-2026-01-30-batch2.md)
> - [progress-archive-2026-01-30-batch3.md](docs/archive/progress-archive-2026-01-30-batch3.md)
> - [progress-archive-2026-01-30-batch4.md](docs/archive/progress-archive-2026-01-30-batch4.md)

---

## Tenant JWT Proof Integration and HTTP Gate (2026-11-02)

Fast-forward integrated the one-commit `workspace/tenant-jwt-proof-20261102`
branch at `dc2c5fbf`; no push or new commit was made. Its real secrets-backed
JWT HTTP tests verify tenant-alias binding, current grants, and fail-closed
behavior on authority outage. The combined tenant HTTP suite passes **19** with
**10 Docker-gated cases pending** when the Docker gate is off; explicitly
enabling the disposable PostgreSQL M3 lab passes all **10** cases. The trusted
proxy test now recognizes the actual local IPv4 and IPv6 loopback peers.
`npm run test:tiers` reports **470 test files across 8 tiers: OK**.

**Boundary:** this verifies the JWT-to-HTTP authorization seam and existing
test lab only. Source API import/backend acceptance and production tenant role
runtime wiring remain open; M1/M2 are not promoted, so M3 remains blocked as a
milestone despite its lab passing. No serving enablement or upstream push.

## Multitenant M1/M2 slices and M3 HTTP lab (2026-11-02)

On `workspace/multitenant-20261102`, four bounded commits now cover the M1
one-time importer and entries-schema candidate (`327cbb1f`, `025704cd`), the
M2 persistent policy/fencing and provider-neutral HTTP boundary (`c496d009`),
and the M3 two-tenant HTTP lab (`a19b549c`). No upstream push or serving-role
enablement occurred. The entries schema remains an explicit operator-migration
candidate; the importer does not apply schema changes or register PostgreSQL
as a serving backend.

**Compatibility decision:** the inspected client corpus uses named entry
fields, and the maintainer confirms no known client depends on JSON key order.
The API3 replacement response does not expose `modifiedCount`, so PostgreSQL
keeps JSONB logical equality: an order-only replacement may report `0` where
MongoDB reports `1`. No BSON-order sidecar or importer metadata is required.

**Acceptance:** importer, CLI and PostgreSQL writer unit tests passed **9**;
the tenant-bound PostgreSQL importer target passed **1**. Disposable-Docker
migration and tenant HTTP suites passed **23** (13 migrations, 10 lab cases).
Tenant resolver/app/JWT HTTP tests passed **19**, and the integrated
secrets/Vault/PostgreSQL policy gate passed **37**. `npm run test:tiers`
classifies **473 files across 8 tiers**. The CRM changed-code ESLint checks,
alignment `make site-check`, and `make queue-check` pass. The full broad suite
was not rerun; the earlier broad-suite AJV failure remains a separate,
unresolved gate.

**Boundary:** the lab uses real PostgreSQL/RLS, the candidate migration, actual
API3 GET handling, and a test-only POST/PATCH adapter around shared validation
and M1 intent writes. It proves tenant isolation, cross-tenant refusal,
persisted outcomes, reconnect, and refusal to bind when the migration ledger
is absent, pending, or stale. The baseline importer is offset-paginated and
not snapshot-isolated; `srvModified` history is best-effort, and hard deletes
have no tombstones. Production credential/policy adapters, full legacy
write-route/runtime wiring, and complete M1/M2 compatibility remain open.
No serving role was enabled.

Source: `externals/work/crm-multitenant-20261102/lib/storage/postgres-entries-write.js:220-239`,
`externals/work/crm-multitenant-20261102/tests/postgres-entries-write.test.js:270-279`,
`externals/work/crm-multitenant-20261102/lib/api3/generic/update/replace.js:34-58`,
`externals/work/crm-multitenant-20261102/lib/server/tenant-app/index.js:107-155`,
`externals/work/crm-multitenant-20261102/tests/tenant-entries-http.integration.test.js:172-327`.

## Multitenant Working Dashboard and Roadmap Grooming (2026-11-02)

The [working dashboard](docs/30-design/tenancy/multitenant-delivery-dashboard.md)
now separates milestone promotion from bounded slice acceptance and shows
milestone/work dependencies, recorded parallel lanes, next gates and linked
evidence. Queue states/prerequisites are generated directly from the manifest;
a dated status overlay records acceptance stages without inventing percentages.
`make queue` regenerates it and `make queue-check` refuses a stale dashboard.

The roadmap keeps decisions and evidence anchors, collapses historical
execution details, and directs current coordination to the dashboard. The
broader next-gen programme source links to it rather than duplicating status.
Verified peer tip `436ef543` incorporates both runner commits; the broad
integrated gate remains pending, while their targeted acceptance is recorded
below.

**Validation:** three focused generator tests pass, including stale-output
refusal; both Mermaid dependency maps parse with the pinned runtime. Queue and
site checks pass with zero warnings/unresolved links. Browser verification
confirms the original dormant-entries anchor still exists and automatically
expands its collapsed evidence section. Nothing published or enabled.

## Parallel MongoDB Primary Recovery and Renewal Refusal (2026-11-02)

Local **`436ef543`** extends `562f6206` with real expired-renewal outage refusal
and primary SIGKILL/restart before/after migration commit. Independent persisted
reads and fresh-worker retries prove rollback or exact committed-ledger
survival. Two mutations fail at matched-count/persisted-value assertions;
restored code passes. No implementation/catalogue/checksum/serving change.

**Acceptance:** **56 combined checks**, zero pending; all **15 MongoDB checks**
pass on 5.0.32 and 8.3.9. Lint: zero errors/two filesystem-path warnings;
466 files classify, diff checks pass, fixtures removed. Both runner commits
are integrated at `436ef543`. Single-node process recovery is not HA,
host/disk failure or production RPO/RTO acceptance.

See the [acceptance/handoff record](docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#parallel-mig-runner-primary-recovery-and-renewal-loss-2026-11-02).

## Parallel Transactional MongoDB Operator Migrations (2026-11-02)

Integrated **`562f6206`** adds the bounded MongoDB replica-set transactional lane
to the explicit Umzug operator command: renewable server-time leases, shared
transaction fence, atomic data/ledger and pending-suffix retry. Real MongoDB
5.0.32 and 8.3.9 acceptance covers contention, paused stale-worker takeover,
SIGKILL before/after commit, outages, history/failure rollback and read-only
checks. Standalone mutation and index steps explicitly refuse; existing boot,
entries, dependency manifests and migration checksums stay unchanged.

**Validation:** **53 combined PG/MongoDB/CLI checks**, zero pending; all **12**
MongoDB checks pass at the floor too. Fence-removal and split-session mutations
fail; restored affected checks pass. ESLint has zero errors/two filesystem-path
warnings, 466 test files classify and diff checks pass. Owned fixtures removed.

**Integration:** fast-forwarded into `workspace/multitenant-20261102` at
**`436ef543`** after confirming clean peer state and disjoint entries edits.
Integrated acceptance: **56 passing** on MongoDB 8.3.9 with PostgreSQL 16 and
the CLI, **15 passing** on MongoDB 5.0.32, ESLint zero errors/two filesystem-path
warnings, and **466 test files** classified. No upstream push or serving
enablement. Standalone/index fencing, catalogues and full runner acceptance
remain open.
See the [acceptance and handoff](docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#parallel-mig-runner-transactional-mongodb-slice-2026-11-02).

## Parallel Current Authority and Scalar Settings Acceptance (2026-11-02)

Control-plane commits **`1dd8990b`** and **`011802ba`** complete bounded
dormant persistent subject authority and the typed units/seconds settings
subset. Real persistence covers cross-worker revocation, outages, floors,
version conflicts, isolation, attributed history and policy-aware rollback.
Recorded local acceptance: **36 passing, zero pending**, ESLint clean and
all **465** test files classified. No entries/runtime changes or serving.

**Integrated acceptance at `436ef543`:** the combined secrets, authority and
settings suite passed **36 tests**, ESLint was clean, and all **466** test
files classified. These dormant services do not enable routes or serving.
Persistent operator policy and atomic policy/write fencing, tenant resolution,
management authentication and runtime wiring remain open; the full M2
milestone is not promoted.

See the [acceptance and handoff record](docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#parallel-control-plane-acceptance-and-next-handoff-2026-11-02).

## Multitenancy Secrets Recovery Integration (2026-11-02)

Local merge **`0de90852`** joins entries `a8dd162d` and parallel recovery
`78b915ab`. The imported change is tests/fixture/documentation only: actual
logical PG backup/restore, encrypted non-dev single-node Vault Raft snapshot
recovery, and owned-worker SIGKILL before CAS/after commit with process retries.
Stored references/audit/key-version behavior and explicit missing-key/provider
refusals are measured. No migration, entries-source or runtime changes.

**Merged acceptance:** **879 passing, zero pending across 31 files**, including
all **34** secrets checks; ESLint, 465-file tier classification and the existing
write-boundary check pass. Production auth/TLS/HA, cluster globals, online
backup coordination, consumer/current-grant recovery and RPO/RTO remain open.
No upstream push or backend promotion; the earlier broad AJV failure remains.

**Parallel handoff:** fast-forward to the integrated baseline, then reconcile
MT-CONFIG-MIN and implement a dormant tenant-local subject-policy/current-
authority slice. Prove fresh cross-worker checks, revocation/outage refusal,
version conflicts and floors using real persistence; do not enable routes or
claim socket/data enforcement. This session keeps entries schema/import/
compatibility work. See the [integration and bounded handoff](docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#integration-secrets-recovery-acceptance-and-next-control-plane-slice-2026-11-02).

## Multitenancy Entries Upserts and Post-Commit v3 Intents (2026-11-02)

Local upstream **`14ae16db`** extends merge upserts/resends, replacement/batch
and every-form persistence, with constraint-specific duplicate mapping and
actual savepoint recovery. A dormant v3 seam reuses shared rules and emits the
internal intent event after its owned transaction commits. V3 POST still
replaces; PATCH merges. Test follow-up **`a8dd162d`** covers resolved OR removal
and shared v3 pruning. No upstream push, catalogue changes or backend enablement.

**Validation:** **878 passing, no pending across 31 files**, including real
PG/MongoDB/Vault and all shared write-intent suites. The changed entries/
transaction checks separately pass **28/28** against MongoDB 5.0.32 and 8.3.9
with PostgreSQL 16.15. ESLint, 465-file classification and existing write-boundary
check pass. Three real mutations fail for broad constraint mapping, early event
publication and missing savepoint rollback; restored implementations pass.

**Remaining:** JSONB lacks BSON field order, so JSON-equal replacements that
owe exact modification counts explicitly refuse. Reviewed schema/import,
full v1/socket intent and route authorization/validation/current-grant wiring,
resource bounds and backend suites remain open. M1/M2 are not promoted; the
previous broad no-database AJV failure is not waived. Parallel secrets/
control-plane ownership is unchanged.

See the [acceptance and continuation record](docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#continuation-entries-upserts-and-post-commit-v3-intents-2026-11-02).

## Multitenancy Entries and Secrets Integration (2026-11-02)

Local upstream merge **`6943dccb`** preserves both parents: entries `7bcfc8b0`
and secrets `fec19ba5` (including `a3888080`/`cbbe9179`). Dormant provider-neutral
secrets/Vault, PG ciphertext/audit and maintenance rewrap/CAS now coexist with
entries writes. No migration/entries source or dependency manifests changed
in the merge. No upstream push, runtime wiring or backend promotion.

**Validation:** **230 passing, no pending** across 17 focused files with real
Vault/PG/MongoDB and all Docker opt-ins; ESLint, existing write-boundary check
and **465-file** tier classification pass. After building local frontend
artifacts, unit 2,108, DOM 205, core 319 and harness 92 pass. Dependency:
368 passing, 1 pending, 1 failure from unchanged `har-validator` resolving
AJV 6.12.6 in ancestor `/home/bewest/node_modules`; the broad command is not
green. Owned lab containers removed; other sessions' resources preserved.

**Parallel handoff:** fast-forward the secrets worktree to the integrated
baseline, then pursue synthetic backup/restore and actual process-crash/retry
acceptance without runtime consumer enablement. Entries upsert/batch/retry,
MongoDB MIG-RUNNER and settings/subject policy remain separate unfinished work.
See the [integration record and commands](docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#integration-entries-and-vault-facing-secrets-2026-11-02).

**Source references:**
`externals/work/crm-multitenant-20261102/lib/secrets/component.js:16-140`,
`externals/work/crm-multitenant-20261102/lib/secrets/postgres.js:34-153`,
`externals/work/crm-multitenant-20261102/tests/postgres-secrets.integration.test.js:19-443`.

## Multitenancy Dormant Entries Writes (2026-11-02)

Local upstream **`7bcfc8b0`** adds `insertOne`, `updateOne`, `deleteOne`,
`updateMany` and `deleteMany` over the existing tenant-bound PG connection.
Scalar patches preserve unrelated data and stored identity kinds; no-op counts,
rollback and both-tenant own-write/isolation behavior match the measured subset
of MongoCollection. No registered backend, migration or default behavior changes.

**Validation:** **158 passing, no pending** across 11 focused files on
PostgreSQL 16.15/MongoDB 8.0.34; includes 8 new real-database checks and 1 input
refusal check. Actual two-backend lock contention covers disjoint patches and
same-field restoration. Three implementation mutations fail; the corrected
locked-version comparison passes. ESLint, 462-file tier classification and
existing write-boundary check pass. Owned lab containers removed.

**Remaining:** complete upsert/resend/batch/every-form outcomes,
constraint-specific retry, events/source/validation integration and full M1.
The parallel session owns MIG-RUNNER, settings/subject policy and secrets.
See the [acceptance and reproduction record](docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#continuation-dormant-entries-writes-2026-11-02).

**Source references:**
`externals/work/crm-multitenant-20261102/lib/storage/postgres-entries-write.js:65-155`,
`externals/work/crm-multitenant-20261102/tests/postgres-entries-write.test.js:155-263`.

## Multitenancy Entries Reads and Operator Migrations (2026-11-02)

Two fresh-context implementation slices are persisted on the local upstream
integration branch; **no upstream push or hosted enablement**.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Explicit PG operator runner | Local upstream `68828b8d`; `lib/migrations/`, `nightscout migrate` | Umzug 3.8.3, pinned-client advisory lock, atomic SQL/ledger, read-only status/check; no production catalogue or boot hook. |
| Entries read/filter subset | Local upstream `7d4f3872`; `lib/storage/postgres-{filter,entries-read}.js` | Actual tenant-bound connection/typed identities; six real PG/MongoDB differential checks plus four refusal/parameterization checks. |
| Decisions, gates and limits | [Delivery roadmap](docs/30-design/tenancy/multitenant-delivery-roadmap.md), `queue/work-queue.yaml` | MIG-RUNNER now in progress, not complete; next-operation current authorization selected across workers, failing closed when unavailable. |

**Validation:** **145 passing, no pending** across 12 focused upstream files
with owned disposable PostgreSQL/MongoDB and project hooks. Migration-only run:
39 passing, including 12 real PG acceptance cases for concurrency, bounded
lock wait, SIGKILL/restart, rollback, drift/history and restricted checks, plus
the unsafe split-commit control. ESLint: zero errors, two filesystem-path
warnings. All 461 test files classified; generated typed DDL fixture hash
matches. Owned containers and private credentials removed.

**Remaining:** ST-PG/M1 is not complete. Unsupported query shapes refuse;
cursor caps, remaining methods, writes/events, identifier retry/current
indexes and backend registration remain. MIG-RUNNER still owes standalone
MongoDB fencing-safe leases/resumability, actual catalogues/baselines and
serving compatibility wiring. Revocation is an adopted contract, not yet
an implemented guarantee. Single-site behavior is unchanged.

**Source references:**
`externals/work/crm-multitenant-20261102/lib/migrations/postgres.js:105-164`,
`externals/work/crm-multitenant-20261102/lib/migrations/catalogue.js:19-38`,
`externals/work/crm-multitenant-20261102/lib/storage/postgres-filter.js:82-229`,
`externals/work/crm-multitenant-20261102/lib/storage/postgres-entries-read.js:49-98`.

## Multitenancy Pooler and Identity Continuation (2026-11-02)

Completed the next bounded PG proofs and settled first-slice policy boundaries.
No upstream push or hosted backend enablement.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Current-connection pooler/DDL lab | `tools/lab/postgres-foundation/{harness.js,results.json}` | 9 checks on PostgreSQL 16.15/PgBouncer 1.25.2; two clients share one backend across 24 interleaved tenant transactions; actual binding mutation leaks to an unbound client. |
| Typed identity primitive | Local upstream `6b1bf889`; `tools/lab/postgres-foundation/generated/` | Historical JSON serialization collapses ObjectId/string copies; opt-in typed key plus actual codec pass 4 PG checks, including kind-flattening control. |
| Decisions and remaining acceptance | `docs/30-design/tenancy/multitenant-delivery-roadmap.md` | Owner grants/bounded token lifetimes included under pinned floors; explicit operator-run hosted migrations; recommend Vault-facing adapter next. |

**Validation:** 65 focused upstream checks, ESLint and test-tier classification
pass; 291 schema-pipeline tests pass. A first regression invocation omitted
MongoDB configuration; the corrected run used owned disposable PG/MongoDB.
Labs remove their own containers, networks and private credential files.

**Remaining:** ST-PG/M1 is still in progress. Collection methods, filter/sort
parity, source/events, current v3/identifier indexes, migration/import acceptance
and hosted wiring are not supplied by an identity codec. The typed DDL is opt-in;
normal generated files and single-site behavior remain unchanged.

**Source references:**
`externals/work/crm-multitenant-20261102/lib/storage/postgres-identity.js:13-38`,
`externals/work/crm-multitenant-20261102/tests/postgres-identity.test.js:9-50`,
`tools/nsschema/emit/postgres_emit.py:284-318`,
`tools/lab/postgres-foundation/harness.js:148-340`.

## Multitenancy Priorities and Celld Assessment (2026-11-02)

**Subsequent maintainer decisions and execution:** Celld removed from scope.
Adopted [the multitenant delivery roadmap](docs/30-design/tenancy/multitenant-delivery-roadmap.md):
storage first, one local upstream integration branch; headless owner API,
UI deferred; operator-only provisioning; legacy per-tenant credentials; small
reviewed config catalogue; human identity separately planned; registration/
intent/delegation contracts parallel. Added current-dev queue milestones without
claiming the old full catalogue complete.

Local upstream `27f085c9`, followed by explicit-URI guard `ce14d637`, adds a dormant PG transaction foundation and isolation
tests; 43 focused checks pass (9 PG checks), plus ESLint. The actual
session-binding mutation fails and its restoration passes. Vault Transit
feasibility: 9/9 checks on 2.2.1; non-exportability, scoped crypto/HMAC,
rotation/rewrap, revocation and an overbroad-policy control. Results:
`tools/lab/vault-transit/results.json`. No upstream push, backend availability,
owner API implementation, migration runner or hosted acceptance is claimed.
Detailed limits and the maintainer's push command are in the roadmap.

Checked public Nightscout dev at `61eb3733`, read its backend/tenant-scope/role
boundaries, reconciled dated PG and configuration evidence, and read Celld's
primary documentation. This is an assessment, not an executed runtime experiment.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Priorities and bounded workstreams | `docs/10-domain/nightscout-multitenancy-priorities-deep-dive.md` | PG entries slice and tenant control plane can proceed independently of the v16 tag; Celld is a separate actor-runtime feasibility track. |
| Five facets | `mapping/cross-project/terminology-matrix.md`, `traceability/{gaps,requirements}.md`, this entry and the deep dive | Separates scope from resolution, RLS from cell routing, scheduling from delivery, and recognized from available backends. |

**Key findings:** PG remains unimplemented on dev despite merged ST-HARNESS.
Hosted roles still refuse startup; configuration/auth wiring and evaluator/
realtime integration remain. At the initial assessment platform-map cards ST-PG/TEN-RESOLVE/TEN-LAB had
no corresponding executable queue items; the adopted roadmap now adds them.
The old seam is reference, not a
required bulk merge. Celld v0.6.2 is documented as beta, with partial Node support
and no account service or multi-tenant scheduler; a hybrid needs an explicit
durable commit/delivery design. No architecture decision, owner assignment,
new release blocker or experiment pass is claimed.

**Source files analyzed:** at `61eb3733`,
`externals/cgm-remote-monitor-official/lib/server/storage-backends.js:21-27`,
`tests/support/backends.js:58-65`, `lib/storage/tenant-scope.js:34-40`,
`lib/server/serve/roles.js:14-41` and `lib/server/serve/api.js:36-42`
(the latter paths relative to that external repository). Detailed evidence,
prior lab links and vendor-documentation limits are in the deep dive.

**Validation:** `make docs-links` and diff whitespace checks pass; all five
local links/anchors in the new assessment resolve in a separate targeted check
(the programme link gate excludes `docs/10-domain`). `make verify` still reports
the existing 162 broken references and coverage/assertion gaps; terminology and
duplicate-GAP checks pass. Traceability generation was directed outside the
repository and still extracts zero requirements/gaps from the modular indices;
no generated acceptance matrix was overwritten. No runtime tests were run.

## Tenant Storage Architecture and Decision Report (2026-11-02)

Expanded the existing cell/SQLite experiment report into a decision guide;
no workload was rerun and no backend or hosted-roadmap decision was changed.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Comparative report and four Mermaid visualizations | `docs/10-domain/tenant-cell-sqlite-deep-dive.md` | Candidate architecture, local-only latency chart, transaction/durability sequence and promotion decision path. |
| Evidence ledger and decision tables | Same report | Distinguishes local cell evidence, September MongoDB/PG/pooler measurements and November PG foundation work; no unmatched speed/cost ranking. |
| Five facets and documentation entry point | Terminology, gaps, requirements, this entry and `docs/README.md` | Storage layout versus engine, correct binding versus row isolation, lifecycle and three-backend maintenance gates. |

**Findings:** cell-owned records are feasible locally, but do not yet justify
replacing hosted PG/RLS or existing single-site MongoDB. Storage-only adaptation
is a bounded next integration hypothesis; moving the entire tenant runtime is
a larger, separate experiment. A matched comparison must include durability,
historical data, recovery headroom and operations, not just VM price or empty
tenant density. Figures label proposed versus measured boundaries.

**Evidence:** original lab `018e55c34`; PG foundation NS `ce14d637` and recorded
run in alignment `ae4ad1827`; pinned historical sources and exact file:line
references in the report. No new protocol GAP/REQ IDs or release dependencies.

**Validation:** four figures parse and render with Mermaid 11.17.2; scaled text
is at least 12 px at 688 px document width. Chart/table values, source hashes,
historical MongoDB figures, local links and heading anchors pass targeted checks.
`make verify` was repeated: terminology/duplicate-GAP checks pass, but 147
corpus references and existing coverage/assertion gaps remain. `make traceability`
completes but still extracts zero requirements from the index; generated matrix
changes were not retained. No workload, paid fleet or production gate was rerun.

## Tenant Cell + SQLite Local Experiments (2026-11-02)

Ran real celld v0.6.3 in an isolated `lab/celld-sqlite-20261102` worktree using
synthetic tenant principals and records. SQLite is the sole tenant record
authority in this arm; no external NS checkout or production backend was changed.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Executable lab and measured JSON | `tools/lab/tenant-cell-sqlite/` | Twelve positive checks; shared-cell negative control exposes cross-tenant value. |
| Deep dive | `docs/10-domain/tenant-cell-sqlite-deep-dive.md` | 32 tenants / 9,216 batched CGM rows; same-disk restart persistence; cost/fleet limits. |
| Five facets | Terminology, gaps, requirements, deep dive and this entry | Separates a third-backend candidate from NS harness and hosted acceptance. |

**Key findings:** overlapping IDs, tenant-local retry receipts, transaction
rollback, JSON predicates, indexed paging, tombstones and SIGTERM/SIGKILL
persistence pass. Loopback p50/p95 writes are 12.53/24.67 ms, reads 2.02/3.34 ms.
This is local developer storage, not a qualified-bucket fleet or capacity/cost
estimate. The runtime forbids `sqlite_version()`; use supported cell metrics.

**Open gaps:** actual NS adapter/harness, fleet durability, runtime/realtime,
tenant lifecycle and a matched three-backend cost comparison. No new protocol
GAP/REQ IDs, v16 dependency or hosted-roadmap change.
Inspected NS `official/dev` source at `61eb3733`; explicit file:line references
and runtime/source hashes are in the deep dive and measured JSON.

**Validation:** lab and syntax checks pass. `make verify` ran, but reports
102 broken corpus references and existing coverage/assertion gaps; terminology
and duplicate-GAP checks pass. `make traceability` completes but extracts zero
requirements from the index; its generated outputs were not adopted.

## Nightscout v16 Corpus and Acceptance Refresh (2026-11-02)

Surveyed all 45 lockfile repository entries through GitHub metadata; recorded
44 public entries and excluded one nonpublic entry. No external checkout or
lockfile was advanced. Official dev remains `61eb3733`; v15.0.9 is still the
latest published release. This is evidence/records work, not release approval.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Ecosystem deep dive and handoff | `docs/10-domain/nightscout-v16-ecosystem-deep-dive.md` | Full public metadata census; AAPS 4.0.0 and optional NightscoutKit fields; bounded current/other-session workstreams. |
| Five facets | `mapping/cross-project/terminology-matrix.md`, `traceability/{gaps,requirements}.md`, this entry and the deep dive | Clarifies informal versus accepted cohorts, reporter versus maintainer reproduction, opt-in versus default, unset versus lenient, and index off versus drop; reuses existing gates rather than duplicate IDs. |
| Release records | `releases/cgm-remote-monitor-16.0.0/{contents,decisions,testing-notes,release-notes}.md` | Replaces stale tester/release-note status with usable drafts, records testing underway without claiming acceptance. |
| Queue | `queue/work-queue.yaml` | Rig soak in progress; bounded #8829 investigation, no invented automatic release blocker. |

**Key findings:** obsolete 4.4 protection requirement removed; retained lanes
green, staging review/policy work continues. #8855 is green; #8897 is a new,
unreviewed report candidate. #8829's reporter reports persistence on dev,
but neither the current maintainer nor Andy reproduced it; the maintainer reports
working DIY and production/service environments and decides it is **nonblocking**.
Preserve both the reporter evidence and the release disposition.
BF-72/BF-161 remain private pre-tag work; no private disclosure or upstream
mutation. Elapsed tester time does not close final-tree/live/cohort acceptance.

**Canonical source read at upstream commits:** batch reply and write settings at
`61eb3733`; NightscoutKit `LoopStatus.swift` at `6efa02d4`.
Detailed file:line references and evidence limits are in the deep dive.

**Validation:** queue schema/fidelity, register coverage, generated
queue/views/packets and programme links pass. All 44 corpus-table rows match the
queried public metadata; the soak is in progress and #8829 is not a release
dependency. `make verify` ran but its Make target ignores failing subchecks:
162 broken source references, coverage gaps and uncovered requirements remain;
terminology and duplicate-GAP checks pass. No global verification pass is claimed.
`make traceability` runs but its index-only extraction reports zero requirements
despite the modular requirement corpus; that output is not acceptance evidence
and is not committed over the older matrix. These tool/corpus limitations are
separate follow-up, not repaired in this documentation-only refresh.
Final `make site-check` passes with zero unresolved links, zero MkDocs warnings,
the privacy scan clean and noindex on 1,671/1,671 HTML pages. The next-gen rich
page is regenerated from the committed source, including the nonblocking #8829
disposition and corrected staging status.

**Post-publication clarification:** the maintainer chose compatibility
clarification first, then acceptance reconciliation here; private security,
live operational/cohort/rollback work, candidate review/placement and #8829
follow-up go to other sessions. Contributed patches were already tested and are
high-confidence (maintainer report); further live feedback will follow.
The compatibility catalogue has 15 implementations / 120 source-shape matches
(11 measured-tier, 109 read-tier), not live execution of every app. Recorded
high confidence in continued interoperability without coordinated upgrades,
not an unconditional all-client-version or new-feature/old-server guarantee.
Updated the colophon and its gate data to remove stale protection, cohort and
unwritten-notes claims; no new tests or release blockers are invented.

## cgm-remote-monitor RC Readiness Triage (2026-11-01)

**Publication follow-up:** integrated through a clean origin-main worktree,
preserving concurrent local edits. Re-rendered compatibility/platform rich pages
from their committed sources to repair the existing site freshness failure;
site checks passed with zero unresolved links and noindex on 1,668/1,668 HTML
pages. Hosted logs report 6,323 passing / 3 pending top-level tests and 7,660
passing / 3 pending across suites counted once, not distinct identities.
Scheduled storage/identity and modern-theme/dependency merges are recorded as
completed implementation; security routing and final-tree/live/cohort acceptance
are separate remaining work. No private PR exists yet; the maintainer's advisory
Compare & pull request workflow is required, not a new scope decision.

Updated the register, queue and release records after #8895/#8896 merged,
with official `dev` `61eb37335954ae42c91345a0823bd67331025165`. Final PR diffs
and canonical merged source were inspected. No shared checkout was edited.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Dated readiness record | `docs/10-domain/nightscout-rc-readiness-2026-11-01.md` | Integrated CI/CodeQL green, dev image published; historical failures labelled, obsolete required check and live/private gates remain; no named RC. |
| Traceability and terminology | `traceability/{gaps,requirements}.md`, `mapping/cross-project/terminology-matrix.md` | Distinguish final combined-tree acceptance from old PR checks, and provider callback acknowledgment from active alarm acknowledgment. |
| Register and queue | `docs/30-design/remedial/nightscout-backfix-register.md`, `queue/work-queue.yaml` | New BF-227 / BFQ-227 is merged-upstream, still exposed on 15.0.9. RT-CI-FIXTURES-8896 is test hygiene, not a duplicate defect. |
| Release records | `releases/cgm-remote-monitor-16.0.0/{contents,decisions,testing-notes}.md`, `docs/30-design/remedial/rc-16.0.0-integration-record.md` | Current head and merged rows; R19/R20 distinguish focused/local-timeout/hosted evidence. Historical counts preserved, no new decision. |
| Callback fix | #8895, merge `bb85d10f` | 54 targeted / 59 integration tests pass; known acknowledgment once-only and diagnostic unchanged. No live transport claim. |
| CI repair | #8896, merge `61eb3733` | Fixture identity and successful index-state comparison; 37 focused tests pass, local start-path timeout remains inconclusive, full hosted checks pass. |

**Key Findings**: nightscout/cgm-remote-monitor#8584 has reporter confirmation
and is a closure candidate; nightscout/cgm-remote-monitor#8829 still needs
restricted-token/reverse-proxy cohort confirmation. No issue was closed, no
branch protection changed and no security advisory published.

**Integrated evidence**: both CI runs 41333672054 / 41333677576 and both CodeQL
runs passed. Push publishing jobs/log establish the amd64/arm64 development
image at `dev_61eb37335954ae42c91345a0823bd67331025165` and `latest_dev`,
not a named RC. Both private fixes contain that dev head; 402 combined focused
tests pass, but full-suite MongoDB acceptance and private PR routing remain
blocked/inconclusive. No security merge or publication.

**Next**: hand off the clean documentation branch for integration after the
concurrent dirty main work is coordinated. Preserve staging protection, live
alerts, real-rig soak, identity cohort/rollback and final security-tree gates.

**Documentation validation**: queue schema/fidelity/check/coverage, generated
views/packets, links, exposure legend and both new read-only merge gates pass;
both authored merge-metadata controls are non-vacuous (wrong-merge negative
fails, recorded-merge positive passes).
The absent pre-existing `P0-F` working directory was linked read-only solely
for queue validation, without cloning or changing it. `make traceability`
completed; unrelated generated reports are not committed. `make verify`
ran but is not clean: this isolated worktree has no external source clones
(470 references, 0 valid), and existing coverage/assertion gaps remain.
The detail-heading check has the same 29 missing headings as the base commit;
BF-227 has both its summary row and detail. No baseline defects were repaired.

## cgm-remote-monitor 16.0.0 Identity and Release Evidence Update (2026-11-01)

Updated the roadmap and release records after #8894 and CI stabilization #8896 merged; completed the broad batch and fresh backwards-compatibility matrices.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Unique-index PR | `nightscout/cgm-remote-monitor#8894` | Merged to `dev` as `497d08c9`; required hosted checks passed. The post-merge cache-read and startup-state test failures were fixed by #8896, whose required and post-merge checks passed. |
| Release status | `releases/cgm-remote-monitor-16.0.0/{contents,decisions,testing-notes}.md` | Full `--batch --no-idf` matrix completed: 3,443 cells per off/try lane, zero invalid; the same 33 expected batch deltas on MongoDB 5.0.32 and 8.0.34, with remaining differences limited to cache fields. |
| Compatibility evidence and colophon | `releases/cgm-remote-monitor-16.0.0/compat/`, `releases/cgm-remote-monitor-16.0.0/colophon.md`, `site/pages/cgm-remote-monitor-16.0.0-{write-compatibility,colophon}.html` | Two 4,916-cell runs per endpoint; 2,803 classified changes, 0 unexplained and no defect-verdict cells. Repeat differences are limited to cache/wire. |
| Roadmap and site | `docs/30-design/platform/next-gen-platform-plan.{md,json}`, `site/pages/nightscout-next-gen-platform.html` | #8889, #8892, #8894 and #8896 are merged; #8894 includes the batch retry, so no separate ID-BATCH feature PR is needed absent a newly identified gap. Compatibility evidence is complete; #8857 rebase/retest, #8824 staging, cohort and rollback checks remain. |

**Key Findings**:
- The 33 current index-on/off matrix deltas are 24 `batch-dupkey-mid` plus 9 `batch-repeat-identifier`; the earlier 24-cell result was pinned at `982de025`.
- The batch-only matrix completed all 13 forms under default on MongoDB 5.0.32 and 8.0.29; only the two relevant forms were compared under reject and strict.
- The older `proto/id-batch-replies` branch is at `7d81e1c1`, 1 ahead/119 behind; it is not the integration branch.
- The broader matrix has 3,443 cells in each off/try lane, zero invalid cells, complete wire capture (929/929), and no differences beyond the 33 expected batch deltas except cache-field noise.

**Next**: Rebase #8857, clear the #8824 master-protection block, then complete cohort verification, operational checks and rollback review before naming an RC. Do not revive the stale `feat/id-batch` branch without a specific uncovered behavior.

## cgm-remote-monitor 16.0.0 Identity Handoff (2026-11-01)

Refreshed the release and next-gen roadmap records after ID-RESEND-SWITCH opened as #8892.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Release status and decisions | `releases/cgm-remote-monitor-16.0.0/{contents,decisions,testing-notes}.md` | #8892 is open; all required hosted checks completed successfully by 07:21Z. ID-UNIQUE-INDEX and remaining ID-BATCH work are local and not publication-ready. |
| Roadmap and dependency map | `docs/30-design/platform/next-gen-platform-plan.{md,json}` | Critical path is #8892 review/merge, then Q-IDX race handling and re-gating on the index branch, then rebase/retest remaining ID-BATCH. |

**Key Findings**:
- Local index gates predate #8892; do not treat them as sufficient evidence for publishing an index PR.
- The batch branch is stacked on the index and 91 commits behind current `dev`.
- No local changes were made to the cgm-remote-monitor feature branches, and no new PRs were opened.

**Source Files Analyzed**:
- `externals/work/HANDOFF-d1-2026-11-01.md`
- `docs/30-design/platform/next-gen-platform-plan.json`
- `releases/cgm-remote-monitor-16.0.0/contents.md`
