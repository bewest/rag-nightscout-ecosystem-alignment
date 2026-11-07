# Milestone promotion review: M0–M3 against the recorded evidence (2026-11-06)

*What this is: a **read-derived review**, batch B4 of the
[integration batching plan](multitenant-integration-batching-plan-2026-11-06.md).
It maps every criterion in the "Acceptance before promotion" column of the
[roadmap's section 4 table](multitenant-delivery-roadmap.md#milestones-and-continuous-integration)
for M0, M1, M2 and M3 to the evidence in the
[RC 16.0.0 integration record](../remedial/rc-16.0.0-integration-record.md)
entries R24–R55 and the
[dashboard's accepted-slices table](multitenant-delivery-dashboard.md#accepted-slices-and-integration-handoff).
Anchored on alignment `main` `c57589e9b553af0dafdcce49d96b3ad4b448a30c`, read
at the start of the review. **This document promotes nothing.** No campaign was
run for it; every count and commit below is quoted from the record text, and a
status of `measured` means a record reports the measurement, not that this
review repeated it. Where a roadmap cell packs several properties into one
sentence they are split into atomic rows. Draft requiring maintainer review.*

## How to read the tables

| status | meaning here |
|---|---|
| `measured` | a record in R24–R55, a dashboard row, or a linked roadmap evidence section reports the property exercised with a stated count or a named red control |
| `partial` | measured for a bounded case or on a lane head, with a named part of the criterion not covered |
| `unmeasured` | no record reports it, or the record itself says `UNMEASURED` or "unimplemented" |

Counts across campaigns overlap and are never summed; the records say so in
each entry. Commit shorthands are the record's own. The roadmap's two cells that
use the older word for the tenancy target are rendered here with the contract's
vocabulary ("multitenant").

## M0: foundations

Roadmap cell: *"Non-bypass application role, overlapping IDs, unbound reader,
read/write isolation, rollback/error cleanup, demonstrated pool reuse and paired
breaks. No [multitenant] role enabled."*

| criterion (atomic) | evidence | status | gap |
|---|---|---|---|
| Non-bypass application role (serving role cannot own or bypass RLS) | Roadmap execution evidence (linked from dashboard rows `025704cd`, `c496d009`): "The store rejects superuser/BYPASSRLS application connections"; pooler proof "9 foundation checks pass" on PostgreSQL 16.15 / PgBouncer 1.25.2 with "Disabling RLS, granting BYPASSRLS" as red controls. Re-asserted on later trees: R24 `8b193e18` "foreign rows when RLS is disabled and unsafe-authority startup refusal"; R48 `3d5eac19` "Duplicate tenant key material, unsafe writer grants and disabled RLS refuse before binding". | measured | None named; the forced-RLS migration check is the dashboard's `025704cd` row ("13 checks, including ... forced RLS"). |
| Overlapping IDs across tenants | R25 `7eb76c71` nine HTTP cases include "tenant isolation"; R27 `c10290d2` HTTP cases "overlapping tenant IDs"; R30 `e410b163` "tenant-local overlapping IDs"; R32 `4621d5c4` "two tenants with identical identifiers"; R38 `21145d0d` "Two tenants share identifier spellings". | measured | None named for entries; R44 `bc4ee1a9` extends to imported ObjectId/hex/custom identities (archived differential "15 passing"). |
| Unbound reader refuses | Roadmap read/filter continuation: "An unbound read refuses". R30 control: removing request-local tenant binding makes the actual GET return "500 instead of expected 200, with `postgres transaction ran with no tenant bound` (0 passing/1 failing)"; R32 repeats the same control for POST ("returns500 instead of201"). | measured | Both controls are read as fail-closed binding coverage; R30 says this "establishes fail-closed binding coverage, not successful cross-tenant data exposure". |
| Read/write isolation between tenants | R27 control "binding the other tenant returns the wrong synthetic row"; R29 `6cad7a42` control "wrong entries tenant binding exposes the other synthetic row"; R38 control "cross-bound tenant B create returns200/dedup instead of201"; R39 `ae471ac7` control "cross-bound tenant B returns A's synthetic value"; R34 `c527fb7e` "An A credential on canonical B refuses401 for GET and POST without mutation". | measured | None named; R25 notes its binding control "proves binding dependence, not foreign disclosure", which the later R27/R29/R39 controls do cover. |
| Rollback and error cleanup | R29 control "removing the owned transaction returns201 instead of rollback500"; R38 control "bypassed intent transaction plus post-write failure returns500 but leaves the row changed, violating rollback"; R41 `94c57f1f` control "removing the transaction leaves partial rename/link changes after audit failure"; R46 `44331668` control "publish inside the transaction and a verified mutating rollback exposes one false logical event instead of none". | measured | None named for the data path; the connection-failure rollback is only in the separate, unjoined clock prototype (see M5 note). |
| Demonstrated pool reuse | Roadmap pooler proof: "Two independent clients execute 24 interleaved tenant transactions on a measured single server PID", binding cleanup under transaction pooling, with the session-local-binding mutation as the red control. In R24–R55: R25 "Independent pools run in one process"; R27 "current grant revocation across independently pooled workers"; R30 "clean worker/pool closure". | partial | No record from R24 to R55 names a pool-reuse check on the cumulative head; the PgBouncer proof is the 2026-11-02 lab against the connection module, and the pool-eviction behavior tested through HTTP lives in the clock prototype `3532c1a4`, which R54 says is "not joined". |
| Paired breaks (every isolation property has a red control on the tested tree) | Every lane record R25–R53 lists its own semantic controls (for example R38 "Three in-memory request-path controls each yield0passing/1failing"; R53 `17f9a457` four controls "actual HTTP200vs403 with persisted effects"). On the cumulative head R54 `35903069`: "Native controls remain separately captured in R51–R53. This cumulative regression does not relabel those mutations as fresh controls of359". R24 likewise: "No new source ablation was run on this combined tree". | partial | Controls are measured on lane heads and inherited by ancestry at `35903069`; no record reports the paired breaks re-run on the integrated head, which the roadmap's M3 packet requires ("Expected positives and paired breaks must survive integration"). |
| No multitenant serving role enabled by default | R24 "No role is enabled"; R38 "No production source, schema, dependency manifest or runtime default changed"; R54 "No ... defaultproduction enablement or push". Since R37 `93c90520` the explicit executable `nightscout multitenant api` exists: "Only the API preview role is enabled" in that child-process test. | partial | The default is unchanged in every record, but an explicit opt-in preview executable has enabled the API preview role under test since R37; the maintainer must say whether that satisfies "no role enabled" or whether the criterion means the default only. |

**Promotion readiness, M0.** Five of eight atomic criteria are reported
measured, with red controls named in the record. To promote M0 on this evidence
the maintainer would accept (a) the 2026-11-02 PgBouncer lab as the pool-reuse
measurement without a re-run on `35903069`, (b) controls inherited by ancestry
rather than re-executed on the cumulative head, and (c) the opt-in preview
executable as consistent with "no role enabled". The dashboard's own remaining
gate for M0 is "Finish deployment/schema acceptance"; no record in R24–R55
claims that.

## M1: entries adapter

Roadmap cell: *"Applicable backend tests execute against both stores; no
pending-as-pass. Explicit unsupported collections/operations. Include null,
ordering/pagination, resend/delete and batch outcomes; preserve source
labels/events."* The dashboard's remaining gate adds: *"Reviewed DDL/import
contract (JSONB logical equality; key-order parity is not required), full
backend compatibility and resource bounds."*

| criterion (atomic) | evidence | status | gap |
|---|---|---|---|
| Applicable backend tests execute against both stores | R24 explicit campaigns: `postgres-entries-read`/`postgres-connection`/importer files "18 / 0 / 0", `postgres-entries-write.test.js` "22 / 0 / 0"; R27 "Live MongoDB/PostgreSQL reader differential 8"; R29 "Actual Mongo/PG HTTP insert, replacement and configured merge"; R41 "actual Mongo/PG treatment HTTP/stored-result tests"; R44 archived imported-identity differential "15"; R51 `33870764` settings differential "12passing". | partial | These are dedicated differentials; R39 states "No generic PG backend registry switch or single/Mongo fallback", so the existing backend suite is not executed against PostgreSQL as a registered backend, which is what "applicable backend tests" reads as. |
| No pending-as-pass | R54 `35903069`: "7144passing/80pending/0failing"; "Pending totals are dependency2 plus integration78"; every record from R24 on states "Pending opt-ins are not passes". The opt-in labs are measured in separately enabled campaigns (R38 "All three relevant opt-ins ... were enabled", focused "83"; R40 `ded254b9` enabled focused "138"; R42 `d4570e58` "233"). | partial | No record counts a pending case as a pass, so the letter of the criterion holds; what is missing is one coherent run with the opt-ins enabled on the cumulative head, and one opt-in has never run in these records: "The Mongo migration opt-in was **skipped**" (R24) and "remains skipped" (R27, R29, R32), after which the records stop mentioning it. |
| Explicit unsupported collections/operations | R27 "unsupported filter/sort shapes refuse rather than approximate MongoDB or read unboundedly"; R39 "Seven selected domains ... activity has no invented v3 route"; R40 "v1 derived paths and derived mutation methods refuse"; R51 "six-key sort refusal. Regex and dotted predicates retain sanitized PG500 capability refusals"; R42 reconciles the seam interface (§11) and write-contract (§9) amendments "without rewriting historical measurements". | measured | R36 records a known asymmetry to keep explicit: "Mongo top-level dotted updates succeed with path semantics while PG mutation maps refuse ... Do not approximate that difference or silently claim parity." |
| Null outcomes | R41 strict comparisons "retain nested identity/server-named extension fields, null/false/zero and arrays"; R42 port corpus "missing/null/false/zero comparisons"; R44 "absent/null/empty/false/zero stored identifiers"; R46 four resend modes assert "nested merge/null/removal behavior". | measured | R41 notes "Migrated absent notes are SQL null, not proof of Mongo absent-property response parity." |
| Ordering/pagination | R27 "explicit sort, positive safe-integer limit and nonnegative safe-integer skip"; control "removing pagination offset breaks the MongoDB/PostgreSQL differential"; R51 "global PG sort cap4→5" with `sortcap` control "actual HTTP500 instead of200"; R46 control "reverse shared identifying order and the legacy selected-row sequence fails". | partial | R39 and R40 leave "Imported populated PG insertion-order backfill" / "populated import ordering" UNMEASURED, and the 2026-11-02 read/filter evidence states "equal-key tie order is unspecified". |
| Resend/delete outcomes | R29 create/resend with "Synchronized identifier races preserve measured Mongo outcomes: create-only `[201,500]`, create+update `[200,201]`"; R38 "POST, replace, PATCH, logical delete, incremental history and permanent delete ... History exposes logical deletion but not a permanently removed document"; R46 "Four resend modes" over a real indexed race with "duplicate errors11000/23505"; R41 "soft-delete/retry and history". | measured | R29: "no new race guarantee is claimed". |
| Batch outcomes | R42 "partial duplicate batches and actual result counts"; R40 "legacy uploader arrays/resends" against NightscoutKit `4ec9fd12` and LoopFollow `4a74b781` pinned patterns; R47 `0c98ad06` v1 "refusal409 inside a200 batch reply" (single/Mongo, test-composed only). | measured | R47's v1 batch evidence is on the independent profile branch with Mongo, "not production route/socket admission"; PG v1 batch is covered by R39/R40's legacy handlers. |
| Preserve source labels/events | R29 "rollback/no-events and postcommit visibility before notifications"; R42 "mutating PG writes publish after commit and failed commits do not publish"; R46 control exposing "one false logical event instead of none"; R48 attribution "POST keeps shipping `subject` and PATCH keeps `modifiedBy`". | measured | Subscriber policy for logical no-op events is an open decision, not a preservation defect: R43 "No-op/refusal outcome admission ... remain an open subscriber decision". |
| Reviewed DDL/import contract (dashboard gate) | R41 "Append-only `0003_subject_management_metadata` preserves earlier migration bytes"; R53 fixture "expects migration003+004 ... compares all prior3 stored checksums"; R41 "Unrepresentable JSONB text is explicitly refused"; dashboard row `327cbb1f` "one-time best-effort import, not snapshot or ongoing sync". | partial | R35: "no tenant/credential provisioning-import command joins them"; R41: "Migration downgrade/rolling-version acceptance remains unmeasured"; R39: insertion-order backfill and "physical shared-index attribution are UNMEASURED". |
| Resource bounds (dashboard gate) | R26 lists "resource bounds" as outside acceptance; R40 "populated import ordering and resource bounds" still incomplete; R51 "sort-cost performance" not measured; clock report: "Contention and ingestion latency are **UNMEASURED**". | unmeasured | No record reports a resource, cursor-cap or lock-set bound exercised; the 2026-11-02 writes evidence already stated "Matching sets are locked/materialized without a size cap". |
| Full backend/client compatibility (dashboard gate) | R40 synthetic replay "is extracted client-pattern replay, not execution of Swift binaries"; R41 compat refresh "768cells/run ... dev versus published PR has0semantic differences; release versus each has227 changed cells"; R42 compat-rest-next "0dev/candidate semantic differences; release comparisons retain227changed cells". | partial | R41/R42: "No old-release-to-PG transitivity is claimed"; client binaries not executed; identity/settings families excluded from the historical corpus. |

**Promotion readiness, M1.** Five measured, five partial, one unmeasured. The
criterion the brief predicted as failed ("no pending-as-pass" because R54 shows
80 pending) is better described from the record text as *partial*: the 80 are
"dependency2 plus integration78" opt-in cases that no record counts as passes
and that are run separately when enabled; the real gap is the absence of a
single coherent enabled run on `35903069` and the never-run Mongo migration
opt-in. To promote M1 the maintainer would have to accept dedicated
differentials in place of the backend suite running against PostgreSQL, accept
pattern replay in place of client execution, and waive resource bounds, which no
record offers evidence for.

## M2: tenant control plane

Roadmap cell: *"Tenant-local effective config and versioned writes; unknown
tenant refuses; A token works on A and fails on B by signature; no
environment/root/key leakage; separate owner/data/operator routes."* The
dashboard's T30-WIRING and T30-TENANT-ADMIN rows name as remaining: *"Human
management issuer/refresh, existing-grant clamping, full owner catalogue and
production lifecycle acceptance"*; the roadmap itself places issuer/refresh and
delegation ceilings under M6.

| criterion (atomic) | evidence | status | gap |
|---|---|---|---|
| Tenant-local effective config | Dashboard row `c496d009`: "integrated secrets/Vault/PostgreSQL gate passes 37, including persisted current grants and atomic settings/grant fencing"; R39 serves "context/settings" with "tenant-local loader/cache frames"; R51 "Synthetic actual settings preserve supported scalar filtering/sorting/projection, current authority and mutation contracts" (12 passing, three red controls, restored 12). | measured | R51 is the only R24–R55 settings measurement and is bounded: "No client binary, all-query parity, sort-cost performance, cross-process history/revision". |
| Versioned settings writes (provenance, history, rollback) | Dashboard row `011802ba` "Units/seconds, provenance, history and rollback ... Local combined 36 checks", stage "Incorporated; testing pending"; `c496d009` atomic fencing gate 37. | partial | The dashboard still lists `011802ba` as "testing pending" (integrated gate pending); no record R24–R55 re-measures settings versioning/history on the cumulative head, and R41 says concurrent authority replacements "serialize; this is not a new optimistic version protocol". |
| Unknown tenant refuses | R31 packet: unknown forwarded name "refuses `TENANT_HOST_UNKNOWN`"; R33 `468c41dc` focused "25" with four red controls, one being "public-alias/ID fallback admits an unknown canonical name"; R34 "unknown canonical Host cannot be rescued by a public alias/ID assertion (404)". | measured | R33: "These measure resolver/app coverage, not a real production ingress transport"; TEN-RESOLVE remains `blocked` on the dashboard. |
| A token works on A and fails on B by signature | Dashboard row `dc2c5fbf` "2 HTTP tests pass for cross-tenant signature refusal"; R48 "Tenant A's token on B fails with TOKEN_SIGNATURE, with successful own-key arms" and controls "removing signature comparison or audience checking makes an invalid token's actual POST answer201 instead of401"; R26 `81bc71e6` exchange cases "cross-tenant refusal". | measured | R26 caveat for the Vault provider: "mismatched Vault signing versions may produce provider refusal before audience checking. That provider case does not establish uniform cross-tenant HTTP status behavior." |
| No environment/root/key leakage | R25 "Signing keys remain nonexportable"; R26 "root exchange refuses"; R48 "A new-token request leaves the real secrets audit count unchanged"; R37 executable runs "without Mongo/API_SECRET" on "strict explicit environment-reference config"; R49 `1c55098a` egress control "blocked extra provider connection raises denied count2 instead of1" and "tenant statistics exclude shared index bytes"; R52 `e5fe0b5e` cache control selects "extracted acquired-SGV leakage"; R55 `2ee8b493` carries the same helper bytes ("helperblob3a97307a ... matches REST exactly"). | measured | Bounded to the exercised paths; R30 leaves "Production Vault TLS/unseal/HA, service identity, token renewal/recovery policy" outside. |
| Separate owner/data/operator routes | R41 "Serving credentials cannot mutate authority; management credentials are refused as the serving reader"; R42 standalone management factory "Data applications do not mount these management routes; no CLI binding"; R53 "Selected REST37 only; DELETE refuses and managementAuth is injected"; operator migrations are explicit CLI (R35, R39 "checked read-only before listening"). | partial | Separation is measured at the service/factory level only: R53/R54 "productionlistener unimplemented", R42 "no CLI binding, human identity provider, delegated grant ceilings or role CRUD is enabled". |
| Human management issuer/refresh | R48 "Complete human/refresh-session issuance ... remain open"; R53/R54 "humanissuer/refresh ... unimplemented". | unmeasured | Unimplemented; roadmap places it under M6, the dashboard lists it under T30-WIRING/T30-TENANT-ADMIN as remaining. |
| Existing-grant clamping | R53 "existing-grant clamping, DELETE policy and production listener remain unimplemented"; R54 repeats it. | unmeasured | Unimplemented; R53's policy constrains proposed grants only ("catalogue ∩ locked operator ceiling ∩ current matching management actor delegation"). |
| Tenant lifecycle (provision/suspend/export/delete) | Dashboard TEN-RESOLVE row: static maps "do not establish durable allocation/publication, production workload identity or provision/suspend/export/delete lifecycle"; R35 "no tenant/credential provisioning-import command". | unmeasured | Nothing to measure yet; R35 characterises only the readiness check sensitivity (`MIG_STALE` control "0 passing/1 failing"). |
| Production trust/transport provenance for resolution | R31 "Selected `TEN-RESOLVE`/`T30-WIRING` queue gates remain UNMEASURED (no runnable gate)"; R42 later: "Updated MT-CONFIG-MIN/T30-WIRING gates also pass at final source"; R34 "This is not a production transport adapter"; dashboard TEN-RESOLVE `blocked`. | unmeasured | T30-WIRING now has a passing gate (R42); TEN-RESOLVE's production trust remains without a runnable gate. |

**Promotion readiness, M2.** Four measured, two partial, four unmeasured. The
five properties in the roadmap's own M2 cell are measured or partial; the
unmeasured rows are the dashboard's additions (issuer/refresh, clamping,
lifecycle, production trust). To promote M2 on the roadmap cell alone, the
maintainer would accept versioned-write evidence from the `011802ba` slice that
the dashboard still marks "testing pending", and route separation proven at the
factory level without a mounted listener. If the dashboard's remaining items are
held to be M2 criteria, M2 cannot promote: three of them are recorded as
unimplemented in R53 and R54.

## M3: two-tenant HTTP lab

Roadmap cell: *"Real authorized entries v3 requests and stored outcomes for both
tenants, positive and negative controls; startup refuses stale/unsafe schema. Not
yet a complete [multitenant] preview."*

| criterion (atomic) | evidence | status | gap |
|---|---|---|---|
| Real authorized entries v3 requests for both tenants | Dashboard row `a19b549c`: "10 disposable-PostgreSQL HTTP lab cases pass for tenant isolation, writes, revocation, startup refusal and data-plane separation"; R38 "Focused cumulative HTTP 83" through the spawned executable "with real Vault and operator-prepared PG/RLS"; R40/R41 "Separate migration / two-tenant HTTP 30"; R54 cumulative "7144passing/80pending/0failing" with "settings differential 12". | measured | None named for entries v3; R39 extends to seven domains, R40 to derived reads. |
| Stored outcomes for both tenants, surviving restart | R38 "persisted outcomes survive process restart"; R40 "cross-version history and restart"; R48 "the same previous token observes committed grants ... across independent API processes; refused writes produce no stored record". | measured | None named. |
| Positive and negative controls on the tested tree | Lane heads: R38 three request-path controls "0passing/1failing"; R39 four; R40 memory and archived controls, "The queue control is NON-VACUOUS"; R53 four. Cumulative head R54: "Native controls remain separately captured in R51–R53. This cumulative regression does not relabel those mutations as fresh controls of359". | partial | The negative controls are not re-run on `35903069`; the positive campaigns are. |
| Startup refuses stale/unsafe schema | R30 "unsafe serving-role refusal, stale migration-catalogue refusal"; R35 `MIG_STALE` control "Missing expected rejection (0 passing/1 failing)"; R37 runtime control red "when migration readiness is bypassed (a stale catalogue child binds its listener)"; R44 control "bypassing the migration catalogue check makes the wrong-catalogue child bind ... 0passing/1failing"; R48 "disabled RLS refuse before binding". | measured | R30: "The pre-bind migration check is a test-owned read-only catalogue check, not a production readiness protocol." |
| Lab runs as actual separate processes (not one in-process pool pair) | R25 limit "Independent pools run in one process, not a two-OS-worker deployment"; superseded by R37 `93c90520` "Child-process tests run outside the checkout" (4 passing), R38 "Standalone actual executable/PG/Vault 5", R39 "7", R48 "16 passing". | measured | Provenance stays synthetic: R34 "Synthetic loopback provenance only". |
| Cumulative head contains every accepted slice | R54 composes "native R51 settings338, R52 private acquisitione5 and R53 owner policy17f"; "Clock and independent profile2ee not joined"; R55 "REST359 and PROFILE2ee remain separate accepted branches, not merged". | partial | The two-tenant lab head excludes the clock prototype and the profile branch; the dashboard's "NEXT D: history contract FAILED" row records a candidate "PENDING" for cross-process equal-timestamp history. |
| Production tenant runtime (service identity, transport, provider operations) | R30 "Production Vault TLS/unseal/HA, service identity ... remain outside this result"; R34 "No upstream CI, production transport/service identity, registry durability"; R48 keys "explicitly operator-provisioned in this preview"; R54 "no ... production owner/listener enablement". | unmeasured | Not an M3 roadmap criterion (the cell says "Not yet a complete preview"), but the dashboard keeps M3 `blocked` on M1/M2 and TEN-LAB, and the brief's prediction that a production tenant runtime is not established is confirmed by the record text. |

**Promotion readiness, M3.** Four measured, two partial, one unmeasured. The
roadmap's M3 cell is met in substance by `a19b549c` (10), R38 (83 focused) and
the cumulative R54 run, provided the maintainer accepts inherited rather than
re-run negative controls on `35903069`. What keeps M3 `blocked` on the dashboard
is its dependency edges: M1 and M2 are both `in-progress`, and the roadmap says
"M0 does not certify M1, and M3 does not certify M6". Promoting M3 before M1/M2
would be a maintainer decision to reorder the dependency map, not an evidence
finding.

## Note on M5 realtime/recovery: the two clock reports and R55

Not an M0–M3 criterion set; recorded here because the re-brief asked where the
new reports bear on M5's "durable ack/snooze, restart/double-delivery checks" and
"replay-equivalent views, tenant-local rooms and caches".

| M5 property | evidence | status | gap |
|---|---|---|---|
| Worker survives a database connection failure and recovers | [Backend-abort diagnostic](../../../reports/tenancy/tenant-clock-http-backend-abort-diagnostic-2026-11-06.md) at source `48b5bcd2`: "the explicitly faulted API worker exited with code1 after a PostgreSQL Client emitted an unhandled error"; selected case "1 passing" that "does not assert that the faulted API child remains available". [Fixed recovery](../../../reports/tenancy/tenant-clock-http-fixed-recovery-2026-11-06.md) at `3532c1a4` with repair `11770146`: functional "7 passing, 1 pending, 0 failing", operator-abort case gives "HTTP503 ... `{error: 'STORAGE_UNAVAILABLE'}`" then "GET200 and POST201" on the same worker; listener-removal control "0 passing, 2 failing"; restored "1 passing". | partial | The report says it "is not numbered clock acceptance"; "Full nonbrowser/browser tests, single/Mongo regressions on the assembled candidate, broader failure schedules and final prcheck remain outside this capture"; the pending case is the benchmark and "supplies no performance result". |
| Monotonic tenant clock across workers | Fixed recovery: stamps "advance `1793991706986 → 1793991706987 → 1793991706988`" across worker restart; same-tenant writers serialize on the clock row; another tenant progresses. | partial | "Rapid cleanup of a PostgreSQL backend after a Node process dies is not established"; "Contention and ingestion latency are **UNMEASURED**"; clock code "remains separate from the combined settings/acquisition/owner application" (R54: "not joined"). |
| Replay-equivalent views / tenant-local acquisition caches | R49 "14 passing" acquisition and "4 passing" concurrency with six semantic controls; R50 `5173864d` "38 passing" profile with `frame-clinical`/`frame-retention` reds; R55 `2ee8b493` "38passing/0failing; restored38" with `http`, `frame-clinical`, `frame-retention` each "0/1semantic"; full "6690passing/3pending/0failing", browser "684". | partial | R55: "No commonrevision, stronger snapshot, full writer/clinical/alarm/recovery/cost acceptance or defaultsubscriber/runtime-role change"; the `v1-closed` control's "2ee runtime is UNMEASURED". R49: "This reproduces the absence of a common database revision; no new snapshot guarantee follows." |
| Durable interprocess events, ack/snooze, double delivery | Dashboard M5 `not-started`; R43/R45/R47 measure only in-process physical/logical events with "Provider delivery remains fake/guarded". | unmeasured | Roadmap: "D-EVENT's in-process `storage-intent-committed` is not a durable bus"; no record exercises cross-process delivery or replay. |

## Unmeasured and partial items ranked by how much they block M3 and M4

Ranked by the number of promotion criteria they sit under, M3 first, then M4
(dashboard M4 gate: "Complete admitted REST/client workflows, direct single/Mongo
vs tenant/PG tests and explicit intended-change/refusal classification ... Actual
client execution distinguished from source-pattern replay").

1. **Negative controls not re-run on the cumulative head `35903069`** (R54:
   "does not relabel those mutations as fresh controls of359"; R24 the same for
   `8b193e18`). Blocks M0 "paired breaks" and M3 "positive and negative controls"
   as stated for the integrated tree; the roadmap's M3 packet requires that
   "paired breaks must survive integration". Cheapest to close: re-run the
   registered archived gates with `--control` against `35903069`.
2. **Production tenant runtime and transport provenance** (R31 TEN-RESOLVE
   "UNMEASURED (no runnable gate)"; R34 "Synthetic loopback provenance only";
   R30 provider TLS/unseal/HA outside). Blocks M2's dashboard criteria and the
   step from M3's lab to M4's client surface; does not block the roadmap's M3
   cell, which is explicitly a lab.
3. **Resource bounds and contention** (R26, R40 "resource bounds" open; clock
   report "Contention and ingestion latency are **UNMEASURED**"; 2026-11-02
   writes evidence "locked/materialized without a size cap"). Blocks M1's
   dashboard gate and therefore M3's dependency; blocks M4's "correct
   batch/retry/refusal semantics" under load.
4. **Mongo migration opt-in never executed** (R24 "skipped because its fixture
   writes literal ... without a path override"; "remains skipped" R27, R29, R32;
   silent after). Blocks M1 "both stores" for the migration runner and M0's
   "migration ... contracts".
5. **Client binary execution** (R40 "not execution of Swift binaries"; R41/R42
   "No old-release-to-PG transitivity is claimed"). Blocks M4 directly ("Actual
   client execution distinguished from source-pattern replay"); not M3.
6. **Populated import ordering and shared-index attribution** (R39, R40
   "UNMEASURED"; R41 "Migration downgrade/rolling-version acceptance remains
   unmeasured"). Blocks M1's import contract and M4's "tenant-local history and
   indexes".
7. **Human issuer/refresh, existing-grant clamping, lifecycle** (R53/R54
   "unimplemented"). Blocks M2 as the dashboard states it and M6 as the roadmap
   states it; M3 and M4 proceed with operator-provisioned credentials (R48).
8. **Settings versioning on the integrated head** (`011802ba` "testing
   pending"). Blocks M2's roadmap cell; M3/M4 only through the M2 edge.
9. **Equal-key tie order and pagination on populated data** (2026-11-02
   "equal-key tie order is unspecified"; R39 insertion order UNMEASURED). Blocks
   M1 ordering/pagination and M4 follower reads at the margin.
10. **Clock HTTP full/browser/benchmark on the assembled candidate and the
    `v1-closed` control at `2ee8b493`** (fixed-recovery report; R55). M5 only;
    does not block M3 or M4.

## Predictions from the brief, confirmed or refuted by the record text

| prediction | finding |
|---|---|
| M0 binding/RLS/rollback/pool criteria mostly measured by the postgres-foundation and early slices | Confirmed for binding, RLS, isolation and rollback; pool reuse and paired breaks are `partial` because no R24–R55 record re-measures them on the cumulative head. |
| M1 "no pending-as-pass" not met because R54 reports 80 pending (2 dependency plus 78 integration) | Counts confirmed verbatim ("7144passing/80pending/0failing", "dependency2 plus integration78"). The conclusion is refined: the records never count a pending case as a pass; the unmet part is a coherent enabled run on the head plus the never-run Mongo migration opt-in. |
| M1 client and resource-bounds criteria unmeasured | Resource bounds confirmed `unmeasured`; client compatibility is `partial` (pinned-pattern replay and two 768-cell corpora exist; binaries do not run). |
| M2 missing human issuer/refresh, existing-grant clamping and lifecycle | Confirmed by R53 and R54 ("humanissuer/refresh, existing-grant clamping and productionlistener unimplemented"). The roadmap's own M2 cell does not list them; the dashboard does. |
| M2 tenant-local config, unknown-tenant refusal and cross-tenant signature refusal measured | Confirmed (R51, R33/R34, R48 and dashboard `dc2c5fbf`). |
| M3 opt-in two-tenant HTTP lab passes 10 cases on `a19b549c` and later REST slices; production tenant runtime not established | Confirmed by the dashboard row text and R30/R34/R54. |

---

*Read-derived review on alignment `main` `c57589e9b553af0dafdcce49d96b3ad4b448a30c`,
2026-11-06. Promotes nothing. Requires maintainer review before any milestone
state is changed in the queue or the dashboard.*
