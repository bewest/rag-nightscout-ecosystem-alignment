# Multitenant delivery roadmap: current-dev integration

**Adopted direction, 2026-11-02.** One local upstream integration branch,
`workspace/multitenant-20261102`, starts at official dev `61eb3733`.
No upstream push is authorized in this session. Keep merging later dev changes
into the integration branch, not rebasing shared work. PRs may later split into
reviewable slices. Alignment records may be published separately.

Celld is **out of scope**. This supersedes its proposed feasibility workstream
in the [priorities assessment](../../10-domain/nightscout-multitenancy-priorities-deep-dive.md).
The assessment's current-dev findings still apply. No multitenant work reopens
v16's release merge list.

## Current status and parallel ownership (2026-11-06)

**Use the [working dashboard](multitenant-delivery-dashboard.md) for current
milestone dependencies, parallel lanes, next gates and slice acceptance stages.**
It is generated from queue claims plus dated acceptance metadata, not a live
branch monitor. It distinguishes local acceptance, incorporation with testing
pending, integrated acceptance and milestone promotion. Nothing is pushed or
enabled merely because a dormant slice passes. The
[integration batching plan](multitenant-integration-batching-plan-2026-11-06.md)
says how lanes join one frozen cumulative head per batch, what verification runs
at each acceptance stage, and which batches are on the critical path.

This page retains the adopted decisions and promotion criteria below. The
[execution evidence](#execution-evidence-2026-11-02) is collapsed under section 6;
existing heading anchors are preserved. Older "next" instructions and relative
"this/other session" assignments describe their dated handoff, not today's
ownership. The dashboard supersedes them for coordination.

**Current acceptance:** [R60](#accepted-coherent-ci-client-batch-and-m0-foundations-2026-11-06)
accepts `d89a44e1`, now published on open/draft #8898. **M0 foundations is promoted**
and the bounded `M4-CLIENT-LAB` card is complete. The tenant clock is joined with
bounded correctness acceptance; its performance benchmark remains pending.
M1–M6 retain their own remaining criteria. Independent R55 profile `2ee8b493`
and later dormant owner/replay/operations branches remain separate.

Use the [reading guide](README.md) to select a current contract or a dated record.
The detailed checkpoints below retain their captured heads and remaining work at
that time. Read them as evidence, rather than as current dispatch instructions.
Current PR publication and remote checks are separate from local acceptance and
belong in the release record.

<details markdown="1">
<summary>Historical R51–R55 checkpoints and earlier lane instructions</summary>

### Accepted independent private acquisition profile (2026-11-06)

R55 independently accepts profile `2ee8b493`: full6690/3pending/0failure,
default browser684, canonical archive38 and finalprcheckOK/currentdev4a
contained/source clean. Actual-trigger (`http`), clinical and retention controls
each fail0/1 semantically; restored38 pass. Notification-close (`v1-closed`)
remains declared at2ee but its new-head runtime is UNMEASURED; prior517 measurement
is historical, not a fourth R55 red. Positive38 retains live-handoff assertions.

The private helper matches accepted REST bytes and independent evaluateCycle
is retained. REST359 and PROFILE2ee are **separate accepted branches, not merged**.
No runtime-role/subscriber/notification policy promotion. The R50–R54 captures and
all milestone/queue states are unchanged; profile gate/current metadata now pin2ee.
The [canonical profile report](../../../reports/private-acquisition-profile-2026-11-06/README.md),
[acceptance capture](../../../reports/private-acquisition-profile-2026-11-06/acceptance.json)
and additive [artifact index](../../../reports/private-acquisition-profile-2026-11-06/artifact-index.json)
record exact scope and source; all22indexed artifact lengths/hashes were independently
verified, with original capture/README unchanged. Seven serial campaigns capture
11containers/20volumes, all recorded absent; no global leak-freedom claim.

### Focused clock connection recovery; broader acceptance open (2026-11-06)

The [original backend-abort diagnostic](../../../reports/tenancy/tenant-clock-http-backend-abort-diagnostic-2026-11-06.md)
retains faulted-worker exit1 despite its passing selected functional oracle.
The separate [focused recovery report](../../../reports/tenancy/tenant-clock-http-fixed-recovery-2026-11-06.md)
and [capture](../../../reports/tenancy/tenant-clock-http-fixed-recovery-2026-11-06.json)
measure source3532 with repair117: actual HTTP7passing/1benchmarkpending;
listener-removal control0passing/2failing (primary ECONNRESET instead of required
HTTP, secondary strict afterEach sees exit1); restored selected1passing receives
503/STORAGE_UNAVAILABLE, same-worker GET200/POST201 and strict exit0. All3raw log,
5source, preparer and passive-monitor hashes were independently verified. Canonical
report records6containers/9volumes absent; original diagnostic remains immutable.

This is focused branch repair evidence, **not full clock acceptance or readiness**.
Clock code is not joined/default-enabled. Full assembled single/Mongo/nonbrowser/
browser/prcheck, broader failure controls, contention and ingestion latency remain
UNMEASURED; the optional benchmark stayed pending. No new numbered clock acceptance,
M0–M6/RC promotion or application push. Earlier sections retain their dated scopes.

### Accepted cumulative settings acquisition and owner policy (2026-11-06)

R54 accepts local integration `35903069` (B338+A e5+C17f):
full7144/80pending/0failure, browser684, actual settings12, fresh finalprcheckOK,
current official/dev4a482627 contained and final source clean. Changed JavaScript
lint has0errors/0warnings. Final359 changes only a settings-test normalization
helper to remove unused bindings; no product scope change. R51–R53 native and
R49/R50 historical captures remain unchanged, not replaced by this cumulative run.

The [sanitized public cumulative record](../../../reports/tenancy/serial-cumulative-acceptance-2026-11-06.md)
and [machine capture](../../../reports/tenancy/serial-cumulative-acceptance-2026-11-06.json)
retain independently verified raw-output hashes, exact source pins, commands,
counts and scope. Initial sandbox prcheck DNS failure is preserved separately;
the successful final fresh check is the accepted one.
Successful settings3containers/5volumes, full18/26 and browser3/5 are independently
absent; all219preserved volumes remain present, with private0700/0600 audit.
This is bounded recorded cleanup, not global leak freedom.

Accepted composition preserves selected explicit ownerPolicy REST37, injected
managementAuth/refused DELETE and R48 data-token behavior. Human issuer/refresh,
full wildcard/default catalogue, existing-grant clamping and production listener
remain unimplemented. Private allocation retains caller policies and adds no
common revision/stronger snapshot. Clock code and independent profile2ee are not
joined. Clock HTTP/full/bench acceptance remains separately pending; no new D
result is allocated here. No M0–M6/RC promotion, default production enablement or
application push. Earlier pending-composition sections below are their dated
captures, not current cumulative acceptance status.

### Accepted selected owner policy and pending composition (2026-11-06)

R53 accepts native C `17f9a457`: full7127/80pending/0failure, browser684,
final prcheckOK/source clean with current dev contained. Actual owner22 and
existing affected26 pass at17f. Static catalogue29 plus subjectunit3 are32
positive cases, not36; four guards are separate negative evidence. Parent
archived22 and each catalogue/ceiling/delegation/actor mutation fails0/1 with
actual HTTP200vs403 and persisted effects; restored22 pass. Six owned gate
containers/volumes are independently absent with private0700/0600 audit.

Root `codex/serial-integration-20261106` now `4a15802c` incorporates B+A+C;
tier506files/8tiers passes, but **combined full is PENDING, not accepted**.
R51/R52 remain unchanged native acceptance captures, R49/R50 unchanged historical
scopes. Neither clock code nor independent profile2ee is joined.

Explicitly selected ownerPolicy bounds proposed grants inside the existing
subject transaction: reviewed catalogue ∩ locked operator ceiling ∩ current
matching management actor delegation. Actor/authority row fencing precedes
subject/credential mutation and final audit. This is selected REST37, not a full
permission catalogue. DELETE refuses and managementAuth remains injected. Human
issuer/refresh, wildcard/default catalogue, existing-grant clamping and production
listener are unimplemented. R48 data-token readers remain unchanged.

Prior3106 product-identical DB22 twice/restored22 and guards remain qualified.
Initial affected25/1 exposed stale migration003-only expectation; fixture-only17f
expects003+004, applies prior3 then004 and preserves all prior3 stored checksums.
Affected26 then pass; no production guard was weakened. See the immutable
[public C record](../../../reports/owner-subject-policy-acceptance-2026-11-06.md)
and [R53](../remedial/rc-16.0.0-integration-record.md#r53---selected-owner-proposed-grant-policy-on-17f9a457-2026-11-06).

The [sanitized clock lower record](../../../reports/tenancy/tenant-commit-clock-lower-proof-2026-11-06.md)
separates originalPG8/controls from corrected all-domain9. Restoring old readiness
SQL fails42703 on catalogues without generated srvModified; portable JSONB
readiness fixes this selected SQL incompatibility. Corrected DHTTP retry is active;
HTTP/full/bench acceptance remains pending. No clock code joined or default enabled,
no contention/latency result or universal history guarantee accepted. Canonical
correctness clock flags are registered source-only for future combined execution;
benchmark remains off. No milestone promotion or application push follows.
The R51/R52 sections below retain their dated capture, not current slot ownership.

### Accepted private acquisition and pending composition (2026-11-06)

R52 accepts the native REST extraction `e5fe0b5e`: a fresh post-recovery full run
passes7080/80pending/0failure, its same-head prior browser684 remains valid and
final prcheckOK confirms current dev contained/source clean. Acquisition14 and
concurrency4 pass; six semantic controls fail0/1 each and restore14/4. Caller
ownership/error4 pass; reused-target scratch control fails2 ownership assertions,
then restored4 pass. This supersedes the earlier incomplete ENOSPC campaign for
native acceptance; failed-run evidence stays preserved.

The26-line private helper allocates fresh context/helper-data/bus and private
cache/materialization target, invoking the existing loader. Callers retain bounds,
query/frame/future policy, typed union, statistics, errors, tenant authority and
lifecycle. No common database revision, full consistency or atomic snapshot follows.
Adaptive alignment cache control `334dc571` now covers historical and extracted
trees without changing accepted worktrees or silently skipping missing anchors.

Root `codex/serial-integration-20261106` at `c7778436` incorporates B338 plus A,
with tier registration504files/8tiers. **Combined full is PENDING; this composition
is not accepted.** R51 settings338 and R49/R50 remain unchanged scoped captures.
A's owned outer audit verifies3containers/5recorded anonymous volumes absent;
nested old fixtures were not audited and unknown volumes were not deleted.

Independent evaluator descendant `2ee8b493` of accepted `5173864d` is SOURCE ONLY:
helper blob matches REST exactly and views integration preserves evaluateCycle.
New-head profile38/controls/full/browser/prcheck are **UNMEASURED**, pending a
separate slot. It is not joined into REST and changes no subscriber/notification
or production runtime admission. A step is finished; D/clock lower PG proof and
controls are active, HTTP/full/bench acceptance pending, C queued. The adopted
[clock proof direction](postgres-tenant-clock-proof.md) has no production clock fix
or accepted contention/fresh-ingestion latency result yet.

Exact native commands/counts/limits are in [R52](../remedial/rc-16.0.0-integration-record.md#r52---native-private-acquisition-extraction-on-e5fe0b5e-2026-11-06).
Evidence was independently read from the local updated
`HANDOFF-private-acquisition-extraction-20261105.md` and
`private-acquisition-evidence-20261105/full-recovery-summary-20261106.json`.
No M0–M6 promotion, full combined proof or application push is claimed.
The R51 and earlier sections below are dated captures, not current slot ownership.

### Accepted settings differential and serial recovery (2026-11-06)

R51 accepts bounded settings at `33870764`: full7089/80pending/0failure,
default browser684, tier registration503files/8tiers and final prcheckOK. Root
`codex/serial-integration-20261106` fast-forwarded the exact tested application
head. R49 REST `1c55098a` and independent R50 profile `5173864d` remain their
unchanged historical captures; profile is not joined. Published drafts #8898
`bc4ee1a9`/#8891 `dff9a8d4` remain open on `4a482627` at the2026-11-06 remote
capture; candidate CI is not claimed.

The only product edit raises global PG sort cap4→5 for requested scalar plus
four stable tie breakers; six-key sorts refuse. Actual settings focused12 and
parent archived12/restored12 pass. Sortcap control fails0/1 with HTTP500vs200;
predicate control0/1 exposes a distractor; projection control0/1 leaks raw private
fields. Regex/dotted predicates retain explicit sanitized PG500 capability
refusals. Synthetic single-process patterns are not client binaries, complete
backend parity, replica history/revision or measured performance.

The earlier full attempt at `0a4a7d59` failed actual fixture setup: duplicate
Vault transit mount400, reproduced by the settings+profile/food pair12passes+
setup failure. Unique owned mount naming and owned-only cleanup fix the fixture;
final pair25/0 and two focused12 repeats pass at338. This was not ENOSPC; failed
full attempts remain unaccepted. Application source after0a is unchanged.

Authorized cleanup audit records3779inventoried/deleted,0missing/preserved/errors
and no outside-inventory loss. Four actual cleanup-block cases cover success and
controlled removal failure, continued attempts, private0700/0600 diagnostics and
six owned anonymous volumes independently absent. Five settings gate audits
verify15owned containers and25recorded volumes absent. B's75recorded volumes are
absent and219preserved volumes remain;40unknown nested volumes stay inventoried
and untouched. These are bounded infrastructure results, not complete leak freedom.
New canonical all flags await a future combined campaign.

B released its slot; **A fresh full active → D → C → clock queued**. A `e5fe0b5e`
is unaccepted after its incomplete ENOSPC/NUL/truncated exit7 campaign; prior
bounded14/4/browser684 stays scoped and alignment `334dc571` is NOT JOINED.
D `714f6c8b` remains unaccepted and its [measured history gap](../../../reports/tenancy/rest-replica-history-characterization-2026-11-05.md)
at `2a6eaf73` is unfixed. C `3106f14d` has static preparation only, with new
DB/full/browser/prcheck pending. Existing accepted R48 is retained.

The maintainer adopted the [transactional tenant-clock proof direction](postgres-tenant-clock-proof.md).
Separate source prototypes, independent HTTP proof and contention/fresh-ingestion
latency measurements are unmeasured; no clock implementation is production enabled.
Root owns joins and final cumulative acceptance. R51 and its bounded ST-PG gate
promote no milestone; wider M0–M6 and all remaining lanes remain open.
Local evidence is in `HANDOFF-settings-verification-20261106.md`,
`HANDOFF-cleanup-settings-runtime-20261106.md` and their home scratch logs;
counts above are reproduced in those logs and independently read for this record.
The2026-11-05 HOLD table below is a historical capture, not current slot status.

### Next lanes and shared capacity hold (2026-11-05)

This is continuation/status upkeep, not a new numbered acceptance wave.
The frozen accepted baseline remains REST `1c55098a` ([R49](../remedial/rc-16.0.0-integration-record.md#r49---cumulative-frame-acquisition-and-concurrent-read-characterization-on-1c55098a-2026-11-05): full7076/80pending/0failure, browser684) and independent profile `5173864d`
([R50](../remedial/rc-16.0.0-integration-record.md#r50---independent-evaluator-frame-characterization-on-5173864d-2026-11-05): full6690/3pending/0failure, browser684), within their recorded boundaries.
The following **NEXT lanes are separate and not accepted**. Figures below are
read-derived from lane handoffs and the immutable replica measurement, not new
campaigns run for this upkeep. Counts overlap and are not completion percentages.

| Lane | Candidate and bounded evidence | Status and next gate |
|---|---|---|
| A — private acquisition | CRM `e5fe0b5e` has bounded acquisition14/concurrency4, semantic controls, caller ownership/error checks and browser684. Alignment cache-control `334dc571` is separate and **NOT JOINED**. | Full campaign **UNACCEPTED**: exit7 during root ENOSPC, NUL/truncated output, no complete reliable summary. Do not assign every numbered failure to capacity without isolation. Final prcheck and separate evaluator adaptation **NOT RUN**. Hold new campaigns until capacity and a serialized slot are released. |
| B — settings differential | Separate `0a4a7d59` has focused12 and predicate/projection semantic controls. Its only product edit raises the **global PostgreSQL sort cap4 to5**; six-term refusal remains explicit. | Full/browser, cross-binding and cap-restoration controls, and final prcheck **PENDING capacity**. This bounded compiler extension does not establish all-settings/query parity or measured resource cost. |
| C — owner proposed-grant enforcement | Existing accepted R48 baseline retained. New transactional catalogue/operator-ceiling/actor-delegation enforcement has no accepted head. | **UNMEASURED**; source-preparation/runtime acceptance on HOLD. Prior token verification does not implement these ceilings, the human issuer/refresh or the complete owner catalogue. |
| D — replica/history | [Immutable actual HTTP measurement](../../../reports/tenancy/rest-replica-history-characterization-2026-11-05.md) at `2a6eaf73` has five passing characterization assertions of a **FAILED history contract**. Latest test-only instrument/cleanup candidate is `714f6c8b`, superseding `d93b7fca`. | Two already-running processes assign equal raw `srvModified` to successive writes: exclusive history omits the later row despite successful addressed GET. Same-process advances1, restart hydration2, foreign tenant unchanged. Corrected controls/cleanup runtime, full/browser and prcheck remain **PENDING**; no general replica acceptance. |

**Capacity HOLD, reproduced host snapshot:** `df -h / /home /tmp` reported root
453G total/431G used/0 available, with96G available on /home. All new DB/full/browser
campaigns remain held globally; source, rendering and static checks use /home
scratch/TMPDIR. Incomplete campaigns retain their original failures and logs;
ENOSPC plus incomplete output is not evidence that every failure is environmental.
Old cleanup removed containers before anonymous volume IDs were captured, so it
cannot attribute orphan ownership. The separate3779-entry unattached-anonymous-volume
inventory awaits user approval; **no deletion is authorized or recorded here**.
No peer/global resource cleanup follows from this status work.

The clock investigation is **read-derived design work**: unique allocation alone
cannot establish commit order if a lower timestamp can commit after a higher one
has been exposed. Legacy paths also plan timestamps before their PG transaction.
A same-data-commit/fencing design needs evaluation; **no production clock fix or
workaround is selected or applied**. The user-selected single-machine-first
expansion boundary remains; these tests do not admit multi-node/HA operation.
No M0–M6 promotion, shared implementation acceptance, queue-state change or release
admission follows from this continuation.

Local untracked coordination detail (machine-local references, not public links):
`externals/work/HANDOFF-next-lanes-20261105.md`,
`externals/work/HANDOFF-private-acquisition-extraction-20261105.md`,
`externals/work/HANDOFF-settings-differential-20261105.md` and
`externals/work/HANDOFF-rest-replicas-20261105.md`. The coordinator owns additive
joins; runner/gate cleanup is a separate branch, not part of these source records.

### Accepted adapter consolidation and index race continuation (2026-11-05)

[R46](../remedial/rc-16.0.0-integration-record.md#r46---bounded-pg-consolidation-and-identifier-races-on-44331668-2026-11-05)
accepts local cumulative `44331668038dca5bc23af24c4125052b9c8e5612`:
identical PG projection, identifying-read and owned-commit/event mechanics are
shared while source-specific translation/natural-order policy remains explicit.
Actual index-on Mongo/PG races cover all entries resend modes, stored outcomes,
current grants and foreign-tenant invariance. Full nonbrowser, default-browser
on application-identical source, real-port/baseline comparison and semantic
controls pass; R46 owns exact figures and diagnostic fixture corrections.
Broader helper relocation and backend capability review remain open.

**Next:** characterize common loader-to-private-frame materialization under
explicit acquisition bounds, frame flags, tenant/error/statistics policy and
concurrent writes before sharing implementation. Continue settings/identity/index
families, actual clients, remaining receipt/egress routes, import/resources and
production lifecycle. Preserve existing behavior during any further PG helper
extraction. Owner identity/ceilings and logical no-op admission remain separate
decisions; durable events/recovery remain M5/M6. No milestone or RC promotion.

### Accepted independent v1 evaluator continuation (2026-11-05)

[R47](../remedial/rc-16.0.0-integration-record.md#r47---independent-shipping-v1-evaluator-replay-on-0c98ad06-2026-11-05)
accepts independent local test-only `0c98ad06f8e01114639d58e1bc0724499af97f1f`:
shipping v1 configurators over the real nonresident context now exercise batches,
resends, hard deletes, retained properties, request signatures and selected live
notification handoff. Whole/full/default-browser and trigger/closed-service
controls pass. Production source, subscriber and executable routes are unchanged;
no socket admission, REST join or durable multitenant evaluator follows.

The [source-pinned frame inventory](architecture-seams-execution-plan-2026-11-05.md#shared-frame-inventory-and-next-characterization)
prepares `ARCH-DERIVED-FRAME` with read-derived policy/lifecycle boundaries.
Runtime convergence and cross-collection consistency remain UNMEASURED. Broaden
remaining writer/alarm cohorts alongside direct frame characterization; retained
freshness and request-local HTTP semantics keep their own policies.

### Accepted composition and direct identity continuation (2026-11-05)

[R44](../remedial/rc-16.0.0-integration-record.md#r44---explicit-backend-composition-and-imported-identity-on-bc4ee1a9-2026-11-05)
accepts local cumulative `bc4ee1a91b84a657012dbb77ee835fdeb78ef707`:
logical domain metadata is separate from explicit PG factories/catalogues and
read-only readiness; dependency recognition is separate from HTTP rendering.
Actual CLI startup and incomplete-port/wrong-catalogue refusal, HTTP error
provenance and direct imported-identity Mongo/PG HTTP checks pass, with full
nonbrowser/default-browser regression and semantic controls. R44 owns exact
campaign figures, setup failures and limits. Independent source review finds
no blocking extraction issue. Current default single, query/write policy and
version-specific refusal semantics are preserved.

This direct identity corpus covers typed raw identity with absent/falsy shown
identifier fallback. The R42 historical comparison keeps its own scope; neither
settings/index-race coverage nor real client binaries follows transitively.
The separate profile branch is not joined into REST or admitted to the RC.

**Next:** consolidate only proven common PG adapter mechanics against the
accepted current-port/direct compatibility baseline. Keep source-specific
ordering, representation, projection and write outcomes explicit; controls must
detect ordering changes and pre-commit publication. Continue remaining REST
receipts/egress, identity/settings/index races, actual clients, import/resource
and lifecycle acceptance. Owner authority is adopted in the [current contract](owner-authority.md);
application integration and full ceiling/session enforcement remain open. Logical-event
no-op admission remains a separate decision; these do not block this bounded
consolidation. Shared frame and durable M5/M6 work retain their separate gates.
No milestone promotion, production role enablement or SQLite dispatch follows.

### Accepted independent HTTP profile continuation (2026-11-05)

[R45](../remedial/rc-16.0.0-integration-record.md#r45---independent-actual-http-profile-writers-on-dff9a8d4-2026-11-05)
accepts local test-only `dff9a8d42860be09c7f187f5e3d0527d6eb31d80` over
published #8891 R43 `925c9527`. Actual API3 mutations/resends now observe
persistence, physical/logical event cadence, retained-property and request-signature
parity, and selected live notification handoff. Parent archived replay and
trigger/closed-service controls pass; independent full/default-browser regression
and review pass. The reproduced notification-fixture lifecycle failure and scoped
ownership correction are recorded in R45; superseded runs are not acceptance.

The physical subscriber and timer are unchanged; acknowledge/refuse still do not
refresh a retained cycle. Full writer/alarm coverage, logical no-op admission,
live statistics/freshness, quiet cost and shared-frame/release placement remain
open. This branch is independent of REST; no actual provider delivery or durable
multitenant runtime is accepted.

### Architecture and execution-profile priority (2026-11-05)

The maintainer requests seam improvements and PR #8891 integration alongside
existing REST/compatibility lanes. The [architecture execution plan](architecture-seams-execution-plan-2026-11-05.md)
owns packet scope, ordering and controls: portable contracts and backend/domain
composition first; measured adapter consolidation and refreshed single/nonresident
profile next; shared derived frames then join M5 durable evaluator/recovery.
SQLite/celld experiments are deferred low priority, unassigned and not dispatched.
Existing REST/admin/compatibility owners continue; integration stays with the
REST coordinator. No new RC tag gate, preview-wide merge prerequisite or
production role enablement is introduced by this schedule.

### Prioritized REST and compatibility execution (2026-11-05)

**Maintainer direction:** prioritize subject administration and remaining REST/client
acceptance, with parallel single/multitenant cross-compatibility and backwards
compatibility modulo documented RC corrections, defined edge cases and existing
client quirks. CodeQL mitigation remains tracked separately; it does not serialize
this delivery wave. Celld remains outside implementation scope; a hypothetical
third backend is an architectural smell test, not an adopted dependency.

Fresh read-back: #8898 remains OPEN/draft at
`ded254b9acf5a94e3a4fd99c85b23e1413fa08b6`; `official/dev` remains
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`. Alignment dispatch base is
`2294a8944a0eac8e72da866cb70f0580fc7b0c18`. These anchors identify the
starting trees, not new acceptance. Root `make queue-status` measures ST-PG's
selected unit gate PASS with integrations skipped; TEN-LAB and T30-WIRING are
UNMEASURED at that invocation; T30-SCHEMA-CONFIG's historical-seam predicate
FAIL remains visible. No milestone is promoted by this dispatch.

| Order / existing milestone | Concrete task and owner | Exit gate / next task |
|---|---|---|
| Now: M2 authority; MT-CONFIG-MIN / T30-WIRING | `codex/tenant-subject-admin-20261105`: persisted subject update/delete and known-role assignment, stable IDs, metadata/omission/rename semantics; separately authorized writer and append-only migration. | Actual PG persistence/rollback/isolation, shipping semantic characterization, same earlier credential denied on the next operation after deletion/grant removal; serving role cannot write authority. Paired controls, then cumulative integration. No HTTP management admission in this packet. |
| Parallel: M1/M4 compatibility; ST-PG / TEN-LAB | `codex/tenant-cross-compat-20261105`: expand shared Mongo/PG HTTP corpus for mixed legacy/v3 treatment edits, omitted versus null fields, retries, replacement and tombstone/history. | Compare replies AND stored results, stable identity, exact retained/removed fields and tenant isolation. Only incidental time/opaque-ID normalization, with explicit refusal rows. Source-pinned client patterns remain distinct from client binaries. |
| Parallel: RC backwards compatibility; TEN-LAB | `codex/rc-compat-refresh-20261105`: fresh same-corpus old release, current dev and PR-single comparison, with repeated runs and classified intended changes. | Preserve immutable prior captures; every semantic difference needs an existing decision/bugfix/client-contract basis or remains unexpected. A classifier control must detect a planted unapproved difference. No old-release-to-PG transitivity claim. |
| Next: M2/M4 administration | Join the accepted subject service to a separately authenticated owner/management boundary; characterize stable role IDs and unresolved/default roles before full roles CRUD. | Actual owner requests and persisted effects, no management route on the data listener, permission ceilings/current grants and cross-worker revocation controls. Implement the [adopted owner authority](owner-authority.md); provider deployment, permission catalogue and transactionally enforced proposed-grant checks remain acceptance work. |
| Next: M1/M4 remaining REST/client/import | Complete one missing route/domain workflow at a time, including notices/debug and notification/assistant receipts/egress; extend import/rerun fidelity and populated-data/query bounds. | Fake-provider no-egress/cross-tenant controls, supported-shape/refusal inventory, bounded failures/reruns; execute actual clients where tooling permits, otherwise keep binary acceptance UNMEASURED. Numeric bounds and new lifecycle semantics require explicit decisions. |
| Integration: M3; TEN-LAB | Coordinator joins clean lanes into the existing PR continuation and reruns exact-head focused/provider/migration, full nonbrowser/browser campaigns and final prcheck after dev merge. | No unexplained compatibility deltas, meaningful restored controls, owned-service cleanup and current QMS/dashboard. M3 promotion still requires complete M1/M2; partial M4 work may proceed in parallel. |
| Then: M5/M6 | Durable events/replay, realtime/evaluator and synthetic operational recovery on accepted authority/storage contracts. | Commit-coupled recovery, tenant-local caches/current socket authority, restart replay, backup/restore/upgrade/rollback and resource/egress evidence. No in-process event substitutes for durability. |

Compatibility is a **direct comparison matrix**, not one blanket equivalence claim:

| Comparison | Purpose / expected result |
|---|---|
| Release 15.0.9 vs current dev (single/Mongo) | Attribute intended RC fixes/defaults/edge-case definitions to the release decisions and register. Historical quirks remain supported where decided; fixing a defect may intentionally change output. |
| Current dev vs PR single/Mongo | Detect regressions caused by shared seam/composition changes independently of PG differences. Same RC contract should hold unless an explicit PR change is approved. |
| PR single/Mongo vs PR multitenant/PG | Directly exercise admitted HTTP routes, stored results, isolation and current authority. Representation/query refusals and JSONB equality limits are explicit capabilities, not hidden normalizations. |
| Pinned client workflow vs each applicable endpoint | Verify retries, edits, defaults, identifiers, ordering, batch replies and delete/history behavior. New-client-to-old-server support needs tested fallback; synthetic pattern replay is not application execution. |

Every corpus case names its source/client pin, endpoint and settings, expected
observable behavior, allowed incidental normalization and intended-change basis.
Compare logical contents, identity, status/headers, per-item reply and history;
do not erase omitted/null/zero/false distinctions or failure categories. Classify
as unchanged, intended RC correction, preserved client quirk, explicit unsupported
capability, unexpected regression or unmeasured. An unclassified difference fails
the compatibility acceptance; a broad allowlist is not a fix. Deliberate duplicate
fixtures with the index disabled and default-index/race acceptance are separate
campaigns. A historical green result never stands in for testing the final join.

Lane implementation/testing uses GPT-6.1 Sol with high reasoning; the historical
comparison/independent interpretation uses GPT-6 Astra with high reasoning.
Each lane owns worktrees and unique disposable services. Parent review re-reads
heads/results before records, integrates only completed contracts and preserves
unexpected results. Local handoffs are under `externals/work/` and are not public
evidence or publication authorization.

### Accepted contract management and independent profile wave (2026-11-05)

[R42](../remedial/rc-16.0.0-integration-record.md#r42---storage-contracts-and-separate-management-http-on-d4570e58-2026-11-05)
accepts local REST `d4570e585d0e12e46386ed26772790b269b2b736`: actual
Mongo/PG lower/preview port contracts, shared subject validation and a standalone
authenticated JSON management facade. Full/focused acceptance, direct bounded
historical comparison and semantic controls pass. This is a factory, not an
enabled owner listener or selected management identity/grant-ceiling policy.

Independent [R43](../remedial/rc-16.0.0-integration-record.md#r43---independent-nonresident-profile-refresh-on-925c9527-2026-11-05)
accepts local #8891 refresh `925c95278ed04954d1181201da79ae5d6c48c095`
with full/default-browser regression and selected actual-trigger/timer/property
replay. It stays separate from #8898. Current physical subscriber remains;
logical no-op/refusal cadence, full writers/cohorts and placement remain open.
No multitenant evaluator, actual provider delivery or runtime-cost claim follows.

**Next:** begin the architecture plan's bounded domain/backend and storage-error/
HTTP composition packet using the measured contract; extract common helpers only
after its runtime/refusal controls pass. Continue owner ceilings/role-ID and
identity characterization, remaining REST receipts/egress, identity/index/race
and actual clients, import/rerun/resource bounds, then M1/M2 completion and M3
promotion review. Broaden #8891 writer/outcome replay before selecting logical
event admission or joining shared derived frames. Durable M5/M6 acceptance and
SQLite deferral remain unchanged. Current [dashboard](multitenant-delivery-dashboard.md)
and the R42/R43 records supersede the delivered dispatch instructions below.

### Accepted subject administration and compatibility continuation (2026-11-05)

[R41](../remedial/rc-16.0.0-integration-record.md#r41---subject-administration-and-cross-compatibility-on-94c57f1f-2026-11-05)
accepts local `94c57f1f37370215ef25b69691ef63918c876db3`, joining the persisted
subject packet and test-only mixed-version/rename corpus. The three dispatch
lanes above have delivered their bounded slices; their wider milestone gates
remain open. Full nonbrowser/browser/enabled/provider/migration campaigns,
parent semantic controls, restored acceptance and final prcheck pass. The
[archived subject instrument](../../../tools/lab/multitenant-subject-admin/README.md)
is PASS with NON-VACUOUS control; this is not owner HTTP admission or policy.
The separate [historical refresh](../../../reports/compat-refresh-2026-11-05/README.md)
is source-pinned to published `ded254b9`, not this new join; its diagnostic
full-corpus residuals are outside the explicit pass scope. See those homes for
figures and limitations rather than treating the comparison matrix as transitive.

**Next executable packets, in priority order:**

1. Compose subject management behind a separately authenticated management HTTP
   boundary, preserving data-listener refusal. Reuse the accepted service;
   characterize stable role IDs and unknown/default role behavior before full
   roles CRUD. Implement the [adopted owner authority](owner-authority.md) rather
   than treating policy as undecided. The injected callback remains a test seam
   until real authentication, proposed-grant ceilings and current-policy fencing
   pass actual management-request tests.
2. Extend the remaining REST inventory one concrete workflow at a time: notices/
   debug, then notification/assistant receipt and egress seams with fake-provider
   controls. Preserve current authority and version-specific refusals.
3. Extend shared compatibility fixtures into omitted identity/default-index/race
   families and actual client execution where tooling permits; rerun affected
   historical/current comparisons on the final joined tree. Keep intended RC
   corrections and preserved quirks individually grounded in decisions/source.
4. Finish supported import/rerun/populated-order/resource criteria for M1 and
   remaining production authority/lifecycle M2 gates; then assess M3 promotion.
   M4 work continues in parallel. M5/M6 retain durable replay and synthetic
   operational acceptance; no completed service promotes them.

The prepared continuation stays on existing draft #8898. Maintainer-operated
publication sends only the new clean commits, followed by fresh remote CI;
there is no automatic upstream push or alert dismissal.

### REST continuation and QMS reconciliation (2026-11-04)

**Current delivery wave, authorized by the maintainer.** Continue from accepted
and published `ae471ac7`, retaining the already incorporated domain deliveries.
[R38](../remedial/rc-16.0.0-integration-record.md#r38---executable-entries-crud-cumulative-acceptance-on-21145d0d-2026-11-04)
and [R39](../remedial/rc-16.0.0-integration-record.md#r39---explicitly-selected-rest-domains-on-ae471ac7-2026-11-04)
are the prior acceptance records; their historical publication observations retain
capture-time meaning. Current-head CI and CodeQL succeeded. The PR body and
older dashboard metadata require reconciliation with the published implementation.

| Owned lane | Deliverable and acceptance |
|---|---|
| `codex/rest-derived-reads-20261104` | Actual properties/ddata/summary HTTP through tenant snapshots; shipping Mongo differential, current permissions for every exposed domain, two-tenant isolation and semantic red controls. |
| `codex/rest-client-replay-20261104` | Source-pinned synthetic uploader/follower workflows against admitted routes, retry and cross-version history/stored-result checks. Distinguish pattern replay from execution of the client binary. |
| `codex/rest-authority-review-20261104` | Independent adversarial review and reproduction of credential/current-authority, snapshot isolation and listener boundaries; findings are read-derived until reproduced. |
| `codex/rest-integration-20261104` and `codex/rest-qms-20261104` | Clean cumulative joins, repeatable queue instruments, full enabled-provider/nonbrowser/browser acceptance, final prcheck, release records and generated views. |

[R40](../remedial/rc-16.0.0-integration-record.md#r40---derived-rest-and-pinned-pattern-cumulative-acceptance-on-ded254b9-2026-11-04)
records acceptance of this bounded wave at published `ded254b9`; full REST and
production milestone criteria remain open. Implementation/replay use
GPT-6.1 Sol with high reasoning; independent review uses GPT-6 Astra. Each lane
owns its worktree/services and preserves single/Mongo. Existing T/D/F/H histories
and their cherry equivalents are incorporated; do not reapply them. Full REST
still includes administration, notices/debug and notification/assistant side
effects. These proceed only against their own persisted authority/receipt/egress
contracts. Production provisioning, transport identity, lifecycle, durable events,
realtime/evaluator and operations retain separate acceptance. No milestone or
shipping candidate change follows from dispatch.

### Next administration and side-effect implementation boundary (2026-11-04)

**Read-derived next packet; new administration is not implemented by this wave.**
This is the captured November 4 packet: R41 now accepts its bounded persisted
service. The [current continuation](#accepted-subject-administration-and-compatibility-continuation-2026-11-05)
owns remaining HTTP/policy/role and side-effect work.
The independent authority review identifies subject update/delete and known-role
assignment as the next bounded persisted service before enabling HTTP management.
At CRM `ae471ac7`, shipping `lib/authorization/storage.js:100-125` preserves omitted
notes/created_at but treats omitted roles as removal of grants; the tenant schemas
currently lack notes/created_at. An append-only candidate migration and a separately
authorized writer must preserve stable subject IDs and atomically update display
name, role links and legacy credential metadata. Serving credentials remain
read-only for authority tables. Do not expose the existing data listener to operator
or owner authority as a shortcut.

Characterize prefix rename against existing credential suffix matching; rename is
not assumed to revoke a stable subject. Verify deletion and grant removal against
the same previously issued credential on the next protected operation. Known-role
assignment can be bounded independently; full roles CRUD needs stable `_id` mapping
because shipping management addresses roles by `_id` while the PG candidate keys
roles by name. Shipping unresolved/default role semantics also require differential
characterization before a compatibility facade. This is a concrete next coding/test
packet, not a reason to rediscover the accepted data-domain graph.

Notification/assistant routes follow their own tenant receipt/egress/runtime ports
and fake-provider controls. Their explicit exclusions remain unfinished REST rows;
no production delivery, token issuance/renewal, new authenticator or operator
lifecycle policy is selected here. Durable events/realtime/evaluator and operational
preview keep the existing M5/M6 gates.

### Accepted POST provider and canonical continuations (2026-11-04)

The state of record is the release
[integration record](../remedial/rc-16.0.0-integration-record.md):
[R29](../remedial/rc-16.0.0-integration-record.md#r29---dormant-tenant-entries-post-on-6cad7a42-2026-11-04)
accepts actual POST/create/resend at `6cad7a42`;
[R30](../remedial/rc-16.0.0-integration-record.md#r30---real-provider-runtime-lab-on-e410b163-2026-11-04)
accepts the real Vault/PG HTTP lab at `e410b163`;
[R32](../remedial/rc-16.0.0-integration-record.md#r32---real-provider-post-composition-on-4621d5c4-2026-11-04)
joins their actual write path at `4621d5c4`;
[R33](../remedial/rc-16.0.0-integration-record.md#r33---canonical-ingress-on-468c41dc-2026-11-04)
accepts explicit canonical ingress at `468c41dc`; and
[R34](../remedial/rc-16.0.0-integration-record.md#r34---cumulative-canonical-provider-post-on-c527fb7e-2026-11-04)
accepts their cumulative composition at `c527fb7e`.
The generated dashboard carries dated slice stages, not independently rerun
results. These local acceptances preserve direct aliases and single/Mongo;
static maps and test-local loopback provenance do not establish registry
durability or production transport/service identity.

### Completion checkpoints and publication (2026-11-04)

**Finish criteria, not additional completed work.** Each implementation has a
bounded contract and stops on a new policy decision. Applicable
full suites, paired source controls and exact-head integration remain required.
`UNMEASURED` and a passing historical foundation gate do not close a checkpoint.

**Implementation-first delivery, maintainer direction 2026-11-04:** two
deliverables ran in parallel from accepted `c527fb7e`: actual entries CRUD
in `workspace/entries-crud-20261104`, and runnable
`nightscout multitenant api` in `workspace/runnable-multitenant-20261104`.
Each delivered code, tests/controls and one handoff. The
[approved continuation contracts](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#runnable-preview-and-parallel-crud-delivery-2026-11-04)
settle current-name/refusal policy and explicit config/environment-bound API
preview boot. A real child-process CLI test, not another injected-app-only
fixture, is the runtime acceptance target. R38 joins both clean heads with the
test-only credential fidelity slice `9e97d073` and validates the cumulative
implementation. Do not make production HA, durable registry or all
owner capabilities prerequisites for implementing the clearly bounded runtime.
The checkpoints below retain full-programme completion criteria, not an
instruction to create separate administrative tasks or block independent code.

The [REST v1-v3 delivery plan](multitenant-rest-api-delivery-plan-2026-11-04.md)
inventories actual mounted routes and divides follow-on implementation by
collection/domain across versions. Its shared-port owner coordinates legacy
storage/auth/context injection; entries, treatments, devicestatus/activity,
profile/food and status/identity/derived-read teams preserve version-specific
behavior. Notification/assistant side effects remain explicitly tracked, not
silently counted complete. This read-derived plan does not expand or block the
accepted CLI/entries CRUD boundary; actual HTTP/client acceptance determines support.

| Checkpoint / queue home | Next bounded action and prerequisite | Completion evidence / decision stop |
|---|---|---|
| C1: entries methods, ST-PG | R38 accepts API3 entries CRUD/history through the actual executable; retain those tests while adding legacy entries through the REST plan. | Actual Mongo/PG HTTP comparisons, current authority, preconditions, rollback and controls are measured for API3. Legacy/client replay and resource/import bounds remain separate; this alone does not complete M1. |
| C2: import and resource acceptance, ST-PG/MIG-RUNNER | After identifying the supported source/target contract, measure import/rerun fidelity and bounded queries/writes. Do not equate one-time best-effort import with snapshot or hard-delete reconciliation. | Explicit supported/unsupported shapes, rerun and failure recovery, schema/RLS checks and measured bounds. Numeric limits, consistency/recovery guarantees and unsupported shape policy require decisions before implementation. Completes M1 only with all C1/M0 requirements. |
| C3: provisioning fidelity, T30-WIRING/TEN-RESOLVE | R35 distinguishes existing operator tooling from test hand-seeding; test-only fidelity is incorporated through R38. No credential/tenant provisioning-import command exists at the accepted head. | Stable IDs, current exact names/grants, root-reference/secrets linkage and incomplete-state refusal through existing operator seams, with controls. Test choreography is not a supported importer, idempotent multi-store rerun or atomic activation. No invented authenticator, secret export or lifecycle defaults. |
| C4: runtime and production trust/lifecycle, TEN-RESOLVE/MT-SECRETS-CONTRACT | R38 accepts explicit-config API boot, prebind readonly checks, owned shutdown and actual two-tenant CLI CRUD. Next extend only tested REST capabilities; production identity/provider renewal, durable mapping lifecycle and other roles remain separate. | Full M2 still requires approved production trust/auth/recovery, provision/suspend/export/delete, durable allocation/publication and listener boundaries. Static operator config/development Vault is not production acceptance. |
| C5: repeatable cumulative gates, TEN-LAB | Turn accepted combined fixtures into read-only queue instruments with paired controls; select the complete M1/M2 set after C1-C4. Existing no-gate markers remain until real instruments exist. | `make queue-status` with relevant integrations, non-vacuous controls, exact-head full suites and unsafe-schema/isolation/current-authority acceptance. Only then assess M3 promotion; adding a passing narrow gate alone is insufficient. |
| C6: client surface, M4 | R40 accepts source-pinned synthetic NightscoutKit/LoopFollow patterns for admitted domains. Extend route/client coverage one workflow at a time; client binary execution remains unmeasured and promotion follows M3. | Reproducible client replay and stored-result comparison, legacy defaults unchanged, paired retry/identity/response controls. Source inspection is not replay. |
| C7: realtime recovery, M5 | Contract work can run independently: reconcile D6/D-EVENT durable checkpoints, commit coupling, replay/duplicates/deletes/config invalidation before wiring a consumer. | Approved ordering/retention/recovery contract, kill/restart replay equivalence, current socket authorization and tenant-local evaluator/cache state. No in-process bus or timer substitutes for durability. |
| C8: operational preview, M6 | Join accepted M4/M5 with explicitly chosen owner capabilities; one backup/restore, upgrade/rollback, export/deletion or resource/egress packet at a time. | Synthetic failure/recovery evidence and final immutable-tree review; real-data/human identity, production traffic, serving-role enablement and publication remain separate explicit approvals. |
| C9: records and publication | Keep release records, queue claims and generated dashboard current after each accepted slice. Maintainer requested alignment records merged to main and assessment of updating existing draft PR #8898. | Validate/generate records before main fast-forward. Published #8898 is OPEN/draft at accepted `ded254b9` with refreshed title/description. Current-head CI and CodeQL succeeded at read-back; retain their exact run links in the release contents until a later measurement. Continue accepted slices on the existing PR through maintainer-operated non-force publication; do not use the dirty original worktree or open a duplicate PR. |

Packet ownership is local and resumable: the entries and provisioning lanes
write `externals/work/HANDOFF-entries-patch-packet-20261104.md` and
`externals/work/HANDOFF-provisioning-runtime-packet-20261104.md`, respectively.
PATCH characterization is complete, with original fixture-assumption failures retained;
the bounded attribution/refusal policy is approved and R38 accepts CRUD implementation.
Provisioning fidelity is committed as test-only `9e97d073`; focused33 and
its controls pass; R38 measures the full/browser cumulative join retaining that
test history. It is not a production importer or activation/rerun policy.
OIDC remains optional, deferred research;
it is not a prerequisite for these checkpoints or for the 16.0.0 candidate.

</details>

## 1. Owner journeys and supported boundary

The supported deliverable is a **headless, documented, versioned tenant-owner
API**, with conformance tests independent of vendor UI. A first-party hosted
owner UI is deferred, not prohibited. Vendors may build UI; they must not bypass
Nightscout's validation/floors or put an all-tenant service credential on the
owner's request path. Existing single-site behavior stays unchanged.

The initial tenant lifecycle is operator-only: provision, suspend, export and
delete through the private operator plane, never public signup. Export and
deletion have different audiences: an owner may export or request deletion;
the operator authorizes and executes lifecycle deletion. A deletion request
is not permission to bypass confirmation, retention or recovery policy.

Before a hosted preview, the selected owner use cases are:

| Journey | Contract needed | Delivery boundary |
|---|---|---|
| Understand configuration | Effective value, source/default/pin/constraint, stored owner value and explicit ignored/rejected reasons | First config slice; no raw secrets in reads |
| Change display, units and timezone | Reviewed typed catalogue, validation, version/precondition, audit attribution, live invalidation and rollback | Small catalogue first, not all historical environment settings |
| Manage uploaders/followers | Tenant-local subjects, roles, root and subject-token rotation/revocation | Preserve legacy credential forms; explain root versus least-privilege tokens |
| Configure connectors/push targets | Typed integration kinds, bounded egress and tenant-owned secret references, split operator/owner credential parts, health status | Enable a kind only when its consuming runtime passes its gate |
| Export and request deletion | Tenant-local export, request/confirmation status and operator execution | No cross-tenant rows or secret plaintext in exports |
| Change alarm settings | Preview/confirmation, complete ordered thresholds, correct units, evaluator version and invalidation | Hidden/unavailable until multitenant alarm acceptance |

Controller registration, command/intent execution and delegated access have
separate later journeys. Choosing these owner capabilities does not imply
their runtime is already implemented.

## 2. Configuration and authentication decisions

**Owner authority amendment, November 5:** the maintainer adopted the
[owner authority contract](owner-authority.md): explicit management authority and
delegation ceilings, initial human session limits, recent reauthentication for
sensitive operations, local public-key verification for new tokens and one current
PostgreSQL authority snapshot per operation. Private signing keys and recoverable
vendor/APNs/connect secrets remain protected by the secrets component. The
[synthetic measurement](../../60-research/tenancy/owner-authority-local-verification-2026-11-05.md)
records local prototype timing, revocation and settled-outage behavior; it does
not enable listeners, complete management ceilings/sessions or promote a milestone.

Retain D22: code floors > operator default/bounds/pins > permitted owner values.
Initially offer only a reviewed catalogue; refuse unsupported names explicitly.
Start with units, timezone, display preferences and authorization policy.
Deployment/runtime values remain in each role's environment; credentials are
never settings. Re-census current dev before claiming full catalogue coverage.
Detailed names, API paths and optimistic-concurrency/error shapes are design
outputs of MT-CONFIG-MIN, not silently chosen here.

**Continuation decisions (November 2):** include owner-editable authorization
policy in the first slice: tenant-local subject grants and bounded token
lifetimes, under the code/operator floors. Mandatory authentication, tenant
isolation and operator access cannot be weakened by an owner. Exact permission
names, lifetime limits, revocation/invalidation and API cases remain contract
outputs, not implemented settings.

**Revocation decision (November 2 continuation):** grant removal or token
revocation takes effect on the **next protected operation across workers**.
That operation checks current authorization and refuses if it cannot establish
current state; an unexpired JWT or cached earlier grant is not sufficient.
Socket writes, subscription changes and protected stream delivery must obey the
same boundary, removing/closing revoked access rather than waiting for token
expiry. An operation already authorized/in flight is not retroactively undone.
The implementation must define its authorization linearization point and test
revocation races, worker-local cache invalidation, reconnect and authorization
store outages. No bounded stale-permission window is adopted. This is a contract
decision, not a claim that current sockets or auth code implement it.

Preserve hashed `api-secret` headers, subject tokens and socket secret forms
using **each tenant's** root credential. Resolve and authorize the tenant before
credential verification; per-tenant JWT signing keys remain per-tenant. There
is no process-wide hosted `API_SECRET`. The owner's root is not a claim that
every uploader should receive owner permissions.

Device/token/root credentials come first. Human login needs a separate plan:
interchangeable identity provider, verified provider/subject, access grants,
tenant-bound token exchange, session/re-authentication/revocation and edge
acceptance. No custom username/password/recovery system. A token-authenticated
config audit names its verified subject or root-credential principal; it must
not invent a verified human identity.

## 3. Secrets: preserve the prior compromise, measure Vault first

The [execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md)
at lines 973-1040 already adopts:

- one secrets component, including sign/verify and logged reveal;
- signing keys never exported from it;
- a built-in encrypted signer for development/small operators;
- Vault Transit and cloud-key-service production adapters behind the same
  contract; the built-in master key stays outside the application database.

The maintainer asks to try Vault integration early if feasible, rather than
assuming a built-in signer is the faster path. Execute a bounded Vault Transit
lab before deciding implementation order. Do not equate cryptographic API
availability with a production-reviewed integration.

Transit encrypts/signs but **does not store submitted application data**.
The design still needs tenant-bound ciphertext/reference storage, authenticated
consumer authorization, scoped provider credentials, rotation/version handling,
outage policy and audit redaction. Scope storage and data keys to tenants;
ordinary consumers cannot choose another tenant's key path. An owner reveal is
an explicit audited operation, never a generic decrypt on the data API.

The first lab uses only disposable synthetic keys/payloads. A Vault development
server can establish API/ACL/key-lifecycle feasibility, not persistence, TLS,
unseal/recovery, HA, production auth or operational suitability. Record the
image digest and the checks that remain. Failure is explicit; never fall back
to plaintext, another tenant's key or an unapproved local signer.

## 4. Milestones and continuous integration

| Milestone | Build / dependencies | Acceptance before promotion |
|---|---|---|
| M0: foundations | Current-dev integration worktree; PG connection/transaction binding and real RLS proof; migration and secrets contracts can proceed independently | Non-bypass application role, overlapping IDs, unbound reader, read/write isolation, rollback/error cleanup, demonstrated pool reuse and paired breaks. No multitenant default or production role enabled; explicit D21 lab preview is permitted. |
| M1: entries adapter | ST-PG, on the M0 binding; current filter/read/write/identity contracts; reviewed DDL managed through MIG-RUNNER before deployment | Applicable backend tests execute against both stores; no pending-as-pass. Explicit unsupported collections/operations. Include null, ordering/pagination, resend/delete and batch outcomes; preserve source labels/events. |
| M2: tenant control plane | MT-CONFIG-MIN, MT-SECRETS-CONTRACT, MIG-RUNNER, TEN-RESOLVE, T30-WIRING | Tenant-local effective config and versioned writes; unknown tenant refuses; A token works on A and fails on B by signature; no environment/root/key leakage; separate owner/data/operator routes. |
| M3: two-tenant HTTP lab | M1 + M2, TEN-LAB | Real authorized entries v3 requests and stored outcomes for both tenants, positive and negative controls; startup refuses stale/unsafe schema. Not yet a complete multitenant preview. |
| M4: existing-client surface | M3; further collections and v1/storage wiring; v2 exchange; tenant-local history and indexes | v1 and v3 uploader/follower shapes exercised on pinned versions; no coordinated app upgrade requirement; tenant-local identity and correct batch/retry/refusal semantics. |
| M5: realtime and evaluator | MT-RUNTIME-PLAN; computed views; durable interprocess event delivery/recovery; settings/secrets consumer integration | Socket authorization/reconnect/write compatibility, tenant-local rooms and caches, replay-equivalent views, durable ack/snooze, restart/double-delivery checks; live notification gate remains separate. |
| M6: multitenant preview | M4 + M5 + chosen owner capabilities and multitenant operations | Export/deletion, import fidelity, backup/restore, upgrade/rollback, bounded resource/egress policies and final-tree review. Real-data/identity acceptance is explicit, never inferred from lab success. |

CI is cumulative, not a calendar: keep default MongoDB/single tests green,
add explicit PG jobs only as their applicable suites execute, and preserve a
visible unsupported/pending inventory. Each isolation property has a red
control, with positive own-tenant behavior, against the actual implementation.
M0 does not certify M1, and M3 does not certify M6.

MIG-RUNNER can begin now; MIG-VV is already done. Build the runner against
both stores with lock/ledger/drift/restart semantics from the measured lab.
Hosted roles refuse stale schemas. Do not add a new default single-site boot
migration behavior to the v16 candidate without its own placement/review.

The maintainer selects **explicit operator-run hosted migrations**; serving
roles check schema compatibility but do not migrate it. This does not revise
the separately planned single-site boot behavior or change today's boot.

Interprocess event delivery is a named design task: D-EVENT's in-process
`storage-intent-committed` is not a durable bus. Reconcile D6's PG feed design
with it, with a durable checkpoint/replay story and explicit ordering,
duplication, deletion and configuration invalidation semantics before wiring
distributed evaluators. A timer may drive time-based alarms, not silently
repair lost write events.

## 5. Next-generation contracts proceed in parallel

| Track | Can progress independently | Hosted/runtime prerequisites |
|---|---|---|
| Registration and instance identity | Definition/catalogue/conformance and single-mode slices | Tenant-scoped storage, owner-action routing, lease/source-of-record conflicts and compatibility projections |
| Intent/command queue | Typed envelopes, lifecycle/status, expiry/cancellation, audit and replay tests | Authorized destination, registered instance where required, durable queue state, idempotency/reconciliation and tenant-local delivery |
| Delegation | Use-case/permission/consent model, bounded grants, revocation/audit design | Human identity/access-grant plan, owner authorization and independently reviewed command authority; no implicit grant from a device token |

None is a blanket prerequisite to the first storage/HTTP lab or a reason to
delay v1/v3 compatibility. The hub observes and routes; the AID controller
remains responsible for its dosing decisions and reconciliation.

## 6. Queue and execution record

### Execution phases and subagent plan (2026-11-03)

**Execution plan, not acceptance or role enablement.** Work advances through
bounded slices on the existing queue items. M3/M4/M6 dependencies constrain
promotion, not isolated development. The supported profile remains the MongoDB
single monolith; the target is PostgreSQL/RLS multitenant. Single PostgreSQL,
multitenant MongoDB, SQLite/Celld, human login and next-generation commands are
outside this execution series. Multitenant completion is not a 16.0.0 tag gate;
placement of each reviewed dormant slice remains separate from enabling roles.

**Planning anchors, captured 2026-11-03 at 17:19:20-08:00:** refreshed
`official/dev` is `4a482627bfdafb1fef8dcbe0ac6c484811cae563`; the published,
open draft nightscout/cgm-remote-monitor#8898 head and clean tested lane
`externals/work/crm-pr8898-ci-20261103` are
`0afdb87f83c3b66a5206fa8bd9e5046696bcc2d1`. Alignment planning starts from
records branch `records/pr8898-confidence-20261103` at `32fca4abe`.
These are starting anchors, not instructions to use an obsolete head.

Read-derived from `gh pr checks 8898 --repo nightscout/cgm-remote-monitor`:
CodeQL, all four diagonal/required-name database jobs, both no-database jobs,
both Docker validations and npm install/build pass on the published head.
Browser jobs and maintained MongoDB remain pending at capture; the whole PR
is not yet green. R23 retains the earlier local execution evidence.

Reproduced prerequisite measurement:

```sh
python3 tools/queue/status.py --id ST-PG --id TEN-RESOLVE \
  --id T30-WIRING --id TEN-LAB --id MIG-RUNNER --id MT-CONFIG-MIN \
  --id MT-SECRETS-CONTRACT --id MT-RUNTIME-PLAN
```

Only the ST-PG unit identity gate ran and passed. Integration gates were
explicitly skipped; the other seven items were UNMEASURED. This is not M1/M2
acceptance. Future packets must select the relevant integration instruments,
provide disposable dependencies and record the actual verdicts.

#### Sequence and joins

| Phase | Bounded output / queue home | Prerequisite and exit gate |
|---|---|---|
| P0: establish the common baseline | Coordinator checks published #8898 head, current dev, CI, clean lanes and ownership. Pending CI is monitored separately from implementation. | Read current PR checks, preserve any failed job's exact symptom, and diagnose rather than waive it. Later slices may start dormant from the tested head while CI is pending; no PR-ready claim until all required checks pass. |
| P1: prepare the first two packets | Storage/API agent produces an entries operation/contract inventory and failing cases; authority/runtime agent produces an injected-port/deployment contract inventory and failing cases. Both use shipping source, not the fixture as a compatibility specification. | Each inventory distinguishes reproduced gaps, read-derived hypotheses, supported shapes and explicit refusals. Coordinator agrees on the smallest first slice, file ownership, test selectors and controls before implementation. No blanket full-REST rewrite. |
| P2: implement entries reads and authority wiring in parallel | ST-PG first slice: entries v3 GET/list/conditional response behavior and adapter gaps required by those cases. TEN-RESOLVE/T30-WIRING first slice: deployment-owned aliases, tenant credentials and current HTTP authority feeding the existing composition, still unbound by default. | Actual MongoDB/PG differential reads and real handler response assertions; positive own-tenant behavior, cross-tenant/refused/outage cases and red implementation controls. Authority uses independently pooled current-state reads, not fixture constants or JWT claims as grants. |
| P3: complete entries mutation acceptance and runtime composition | Storage lane adds real entries create/patch/replace/delete/search/history slices, one contract family at a time. Runtime lane adds schema-readiness/privilege separation, runtime validation and distinct owner/data/private-operator listeners in explicit synthetic labs. | Shared write rules, retry/batch/precondition/header outcomes and post-commit visibility measured on actual handlers. Startup/readiness remains read-only; revoked/suspended/unknown access fails closed. No public operator mount, process-wide tenant secret, global PG registry change or automatic role enablement. |
| P4: integrate and assess M0-M3 | Coordinator joins accepted slices, reviewed schema/catalogues, remaining M1 resource/import contracts and M2 control-plane acceptance. TEN-LAB runs the combined two-tenant application, not only the earlier narrow fixture. | Full applicable backend and HTTP acceptance, pooled isolation, concurrent identities, current authorization and unsafe-schema refusal on the exact combined head. Remaining gaps stay named; only complete milestone criteria permit promotion. |
| P5: expand M4 and advance M5 independently | API lane expands supported collections and v1/v2/v3 contracts in measured client-priority order. Runtime lane completes MT-RUNTIME-PLAN's durable event/replay contract before evaluator/websocket implementation. | Pinned uploader/follower cases and tenant-local batch/history/index behavior; separately, durable checkpoints, ordering/duplicate/delete recovery, socket revocation/reconnect and replay-equivalent evaluator views. M4 development may begin earlier, but promotion follows M3. |
| P6: multitenant preview acceptance | M6 joins M4/M5 with chosen owner capabilities, private lifecycle, export/deletion and operational acceptance. | Synthetic backup/restore, upgrade/rollback, bounded resources/egress, provider/recovery review and final-tree validation. Real-data/identity acceptance and role enablement require separate explicit approval; no inference from lab passes. |

### Preview dispatch packets M1-M6 (2026-11-04)

This is the continuation of P3-P6, not a second milestone system. M0
foundation acceptance remains a prerequisite within M1. The next six
milestones are M1 through M6; they are not six agents dispatched together.
Two fresh-context implementation lanes run initially, with the coordinator
owning integration, decisions, CodeQL disposition and alignment records.
Future packets are instantiated from the accepted cumulative head, never
blindly from the planning anchor below.

**Anchors read for this dispatch:** published PR head `81bc71e6`, current
`official/dev` `4a482627`, local cumulative CRM `c10290d2`, alignment
`main` `82826a22e`, records branch `59ebd0efe`. R27's agent-run nonbrowser
result is 6764 passing / 88 pending / 0 failing, browser separately 684/0/0;
eight reader differential and two actual HTTP search checks pass. These
overlapping campaigns are not additive. Source controls caught revoked
search succeeding, wrong tenant rows and ignored pagination. Broad client
replay, actual HTTP mutations/history and production runtime remain outside
that acceptance.

#### Common fresh-context dispatch contract

Each agent reads AGENTS.md, confirms the current head and that the task is
still open, checks ownership and creates its own lane. Stop and report a
mismatch rather than reaching for the nearest thing that works. A handoff
must carry the facts, not require retained chat context.

Every instantiated packet names: parent queue IDs; exact base and dev heads;
owned branch/worktree and allowed files; shipped contract with file:line;
reproduced gap versus read-derived hypothesis; one bounded output; explicit
non-goals; test commands and environment-variable names; expected positive,
refusal and outage outcomes; actual source-ablation controls; cleanup; and
the decision that stops the slice. No credentials, connection URLs, user data
or shipping-defect recipes enter tracked records.

Use the configured high-capability general-purpose agent defaults for
implementation, cross-store authorization and lifecycle reasoning. Do not
hard-code a model/version in the plan. Bounded command execution may use a
task agent when it needs separate context; do not delegate simple lookups.
A fresh agent takes each independent slice; retained agents receive only
same-slice follow-ups. No agent spawns another agent or changes its scope.

The first turn is an inventory/reproduction packet, not permission for a
blanket implementation. The coordinator approves its exact change surface
before code. Shared auth/handler/schema files have one owner at a time.
Committed migration bytes remain immutable; schema additions require the
schema owner. Integration starts only after clean committed lane results.

After implementation, run focused real-store/actual-handler checks first;
then the full applicable nonbrowser and browser suites, lint/tier checks,
current-dev synchronization, affected tests and final prcheck. Report
per-tier totals, skipped opt-ins and overlapping campaigns separately.
Use owned disposable loopback services, synthetic fixtures and scratch
outside the package tree. A non-test database name trips the existing guard;
select a test database, never bypass it. The Mongo migration fixture's shared
temporary path remains a named skip, not a workaround.

#### M1 packet: entries mutation and history acceptance

**Queue home:** ST-PG and MIG-RUNNER. Initial lane:
`workspace/entries-mutations-20261104`, from `c10290d2`. Inventory the actual
shipping POST handler through write-intent, stored-identity resolution,
permission decisions and post-commit events. Reproduce the smallest gap,
then propose one POST/create/resend family, not POST/PATCH/PUT/DELETE at once.
The earlier lab's test-only mutation adaptation is not the reference.

Own entries adapter/API-specific tests; a shared handler or private permission
bridge change requires coordinator agreement. Use actual handlers and
MongoDB/PostgreSQL differentials, independently pooled tenants with overlapping
IDs, and current branch-sensitive create/update grants. Expected outcomes:
own-tenant success with matching stored result and response; no anonymous
write, foreign row or revoked success; failure does not emit a committed
intent. Break permission enforcement, tenant binding and identity/retry
handling in owned scratch and observe exact assertion failures.

Follow with separately scoped PATCH/PUT/DELETE/history packets, then import,
query/resource and complete applicable backend acceptance. Stop for a new
permission/linearization policy, client-required change, approximate MongoDB
semantics or an unapproved schema/limit. M1 promotion requires its whole
contract, not the first mutation slice.

#### M2 packet: real-provider composition and readiness

**Queue home:** MT-CONFIG-MIN, MT-SECRETS-CONTRACT, MIG-RUNNER, TEN-RESOLVE
and T30-WIRING. Initial lane: `workspace/runtime-composition-20261104`, from
`c10290d2`. Inventory existing provider/readiness ports and reproduce the
missing real-provider + PostgreSQL + actual HTTP join. Prefer the smallest
explicit synthetic lab composing existing adapters; do not invent a runtime
framework or duplicate the entries API.

Own provider/runtime-specific composition and tests, not mutation handlers.
Expected outcomes: scoped real-provider credentials support own-tenant
exchange/read; cross-tenant keys/hosts and untrusted selectors refuse;
committed revocation is observed; unavailable provider/authority is not stale
success; stale/unsafe schema refuses without DDL. Break provider ACLs and
tenant binding in scratch and show the actual isolation/refusal assertion
fails. A real-provider development lab does not certify production auth,
TLS, unseal, HA or recovery.

Follow with explicit provisioning/import fidelity, trusted runtime identity,
separate data/owner/private-operator listeners and shutdown/recovery packets.
Stop before selecting a new operator authenticator, secret-recovery policy,
numeric resource default or deployment trust assumption. Existing OIDC work
is separate, not a prerequisite invented for this join.

#### M3 packet: cumulative two-tenant acceptance

**Queue home:** TEN-LAB, gated by complete M1/M2 acceptance. A fresh integration
agent receives exact clean lane heads, allowed conflict resolutions and all
applicable selectors. Merge into a new owned integration lane; do not rebase
shared published history. Exercise the combined application, not only narrow
fixtures: overlapping identities, actual authorized requests/stored outcomes,
pool reuse, concurrent changes, current grants, outages and schema refusal.
Expected positives and paired breaks must survive integration. Stop on
changed behavior or unexplained test accounting rather than waive a failure.
Full suites and final prcheck apply to the exact combined head. Record
remaining gaps before any milestone promotion; keep all roles dormant.

#### M4 packet: pinned clients and wider REST surface

**Queue home:** ST-PG, TEN-LAB and MT-RUNTIME-PLAN; promotion follows M3.
First inventory actual pinned uploader/follower operations, then choose one
client/collection/route family. The inventory must name version/hash and
ordinary handshake, read, write, retry and refusal behavior; source inspection
alone is not replay acceptance. Extend further collections, v1/v2/v3,
history/indexes and tenant-local batches in that measured order.
Expected output is a reproducible synthetic client replay and stored-result
comparison, including an unchanged legacy response without opt-in.
Break retry/identity or response semantics and demonstrate a client assertion
fails. Stop if a coordinated app upgrade, changed default or unsupported
client safety assumption would be required.

#### M5 packet: durable events, realtime and evaluator

**Queue home:** MT-RUNTIME-PLAN. Contract work may proceed independently of
M3/M4; runtime acceptance still requires its storage/authority inputs.
First reconcile the existing D6 feed and D-EVENT commit contract, naming
durable checkpoint ownership, commit coupling, ordering, duplicates, hard
and soft deletes, configuration invalidation and restart boundaries.
No timer substitutes for lost writes.

Only after that contract is approved, implement one producer/consumer recovery
slice. Expected output: kill/restart and duplicate/replay tests reconstruct
the same tenant-local view; disconnected/revoked sockets do not retain
authority; caches and evaluator state do not cross tenants. Break checkpoint
or replay handling to make those assertions fail. Owner ack/snooze and actual
notification delivery retain their separate gates. Stop for a new ordering,
retention or recovery guarantee rather than infer one from the in-process bus.

#### M6 packet: synthetic operational preview

**Queue home:** TEN-LAB and MT-RUNTIME-PLAN, plus their named operational
items; promotion requires M4/M5 and chosen owner capabilities. Dispatch one
backup/restore, upgrade/rollback, export/deletion or resource/egress family
at a time, with exact artifacts and expected recovery boundaries.
Verify import fidelity, tenant-local ciphertext/key recovery and audit
redaction; inject failed restore/upgrade/provider operations and prove explicit
refusal and recovery. No preview claim follows from a fresh empty database.

The final packet joins accepted operations on one immutable tree, documents
supported/unsupported capabilities and obtains maintainer review. Real-data,
human identity, production traffic, serving-role enablement and publication
require explicit separate approval. An unresolved numeric bound, retention
rule or owner capability becomes a decision question, not an agent default.

#### Records and decision join after every packet

Record measurements in the next integration R entry and a dated release
contents update; record maintainer choices in decisions.md. Update existing
queue claims and dashboard slice metadata when they change, regenerate their
views, and run queue-check/docs-links (site-check for dashboard changes).
SQLite tracks session tasks/dependencies, never substitutes for those files.
Questions carry the mechanism with file:line, measured versus unmeasured
behavior, compatibility/operator impact and a recommendation. Check peer
decisions first; ask one topic at a time. No automatic push or milestone
promotion is delegated.

### Canonical internal hostname boundary (2026-11-04)

**Adopted direction, not implemented ingress or durable provisioning.** Keep
three separate concepts: optional disposable public aliases, a durable
DNS-friendly internal tenant name, and the stable tenant ID used by data and
credentials. The authoritative deployment mapping binds internal name to ID;
an internal name is not a backend IP/port, a public domain or caller identity.
Alias rotation must not recreate tenants or change data/credential ownership.

First-party scope is the provider-neutral mapping/ingress contract, validation,
trust checks and conformance. Consul, Kubernetes and vendor discovery are
optional adapters. Public domain provisioning, customer mappings, certificates
and private edge routing remain deployment/vendor concerns; no private
implementation or configuration is copied into the public tree.

Read-derived prior art: node-multienv at `2602c94e` separates tenant naming
from discovered host/port (`lib/consul.js:215-240`) and configures workload
hostname/subdomain from the internal name
(`lib/webhook/tenant-phases/resources.js:35-46`). Its complete DNS allocation
and durability rules were not verified or adopted wholesale.

**Reproduced current gap on `c10290d2`:** configure only a synthetic canonical
internal Host in `lib/tenant-resolution`; direct Host resolves to its stable
ID. Add a trusted but unknown disposable public `X-Forwarded-Host` and the
same request refuses `TENANT_HOST_UNKNOWN`. The current resolver deliberately
uses forwarded alias precedence (`index.js:65-79`); a resolved-ID assertion
cannot replace that alias lookup. Existing DNS validation/static alias
rotation is not a durable canonical-name registry or an internal-ingress mode.

Next packet must preserve direct-alias mode and define an explicit
internal-ingress mode where only trusted transport may supply canonical
internal selection; public forwarded names do not override it. The source
of selection must be deployment configured, never selected by caller headers.
No DNS lookup itself grants authority. Define durable allocation/collisions,
rename/reassignment/deletion behavior and consistency before adding the
operator writer. Prove public alias rotation preserves identity, spoofed or
conflicting selectors refuse, trust loss closes access, and mapping changes
do not leak cached authority. No provider, production transport trust or
automatic Consul dependency is selected by this direction.

### Accepted read and authority continuations (2026-11-04)

The [integration record](../remedial/rc-16.0.0-integration-record.md)
is the measurement home: R24 records combined projection/current authority
at `8b193e18`; R25 records legacy credential/current-authority GET at
`7eb76c71`; R26 records compatible exchange/GET at `81bc71e6`; R27 records
actual entries list/search at `c10290d2`. R27's agent-run nonbrowser total
is 6764/88 pending/0 failing, browser separately 684/0/0. Current authority,
wrong-tenant and pagination controls fail as intended. No parent replay,
pinned-client acceptance, full REST or production runtime is asserted.

### Published exchange checkpoint CodeQL disposition (2026-11-04)

Read-derived source review on PR head `81bc71e6` found three opt-in synthetic
fixture alerts, individually dismissed as false positives via GitHub API:
144, missing rate limiting on the loopback ephemeral test handler
(`tests/tenant-credential-http.integration.test.js:99,112-114`); 145 and
146, deliberate SHA1 reference derivation of synthetic legacy credentials
(`tests/vault-secrets.integration.test.js:146-149,180-183`). The latter tests
measure the existing compatibility contract; actual JWT signing uses Transit
keys, not the reference hash. No query/path exclusion, production suppression,
algorithm change or rate-limiting acceptance follows. API read-back confirms
all three dismissed; subsequent PR check read-back reports CodeQL and Tests
pass SUCCESS. This is disposition of the existing analysis, not a new scan.

### Published REST checkpoint CodeQL review (2026-11-04)

Read-derived live review of [#8898](https://github.com/nightscout/cgm-remote-monitor/pull/8898)
at `ded254b9acf5a94e3a4fd99c85b23e1413fa08b6`, against `official/dev`
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`: CodeQL workflow success is
completion of analysis, not disposition of its findings. The PR review has one
unresolved inline production thread, for alert 147. Querying open alerts on
`refs/pull/8898/merge` additionally finds 148; the branch-ref query is empty
because these instances belong to the PR merge analysis, not that branch ref.
Both instances are open on merge commit
`c6174f6037137c6e119713996cb6dc4dd99f30f1`. No dismissal, review reply or risk
acceptance was performed in this review.

| Finding | Source assessment (read-derived) | Recommended PR follow-up |
|---|---|---|
| [147: sensitive GET query](https://github.com/nightscout/cgm-remote-monitor/security/code-scanning/147), `lib/api/status.js:34` | The extraction expression is inherited from base `status.js:29`; tag 15.0.9 also accepted query credentials at `:22`. The tenant status callback deliberately preserves issuance compatibility. Removing only this fallback changes issuance while leaving other query authentication paths. URL credentials can still reach history and upstream logs despite `no-store`. | Keep the finding open pending explicit compatibility/security disposition. Coordinate extraction, issuance, client/shared-link migration and tests before retiring query carriers. Inheritance does not make this a false positive. |
| [148: missing rate limiting](https://github.com/nightscout/cgm-remote-monitor/security/code-scanning/148), `lib/api/status.js:22` | Failed-authentication delay in `lib/authorization/index.js` is not aggregate request limiting. Token extraction precedes that delay; valid traffic and tenant exchange have no demonstrated request-rate protection. This is source review, not a reproduced load or deployment claim. | Establish trusted client identification, tenant separation, pre-verification limits and distributed-worker behavior; measure normal polling/bursts before choosing limits. An arbitrary status-only limiter is not acceptance of the broader authentication surface. |

A bounded compatibility-preserving adjustment is recommended: set
`Referrer-Policy: no-referrer` in tenant `base()`
(`lib/server/tenant-app/index.js:83–92`), matching the single app's
`lib/server/app.js:66`. Verify tenant/operator success, refusal, error and
status-redirect responses; removing the header must make the header check fail,
then restore and rerun. This is a proposed patch, **UNMEASURED**, not implemented
or ready for publication. It reduces referrer exposure but resolves neither
147's residual URL exposure nor 148. The factories remain an explicit preview;
this observation is not evidence of an exposed deployment.

Reproduced on unchanged `ded254b9`: isolated
`mocha --exit tests/status-headers.test.js` passes **8 / 0 failing**, including
header/query compatibility and non-cacheable refusals. These existing checks
were not ablated in this audit and do not establish rate-limit or referrer
protection. An initial direct combined invocation with `tests/api.status.test.js`
gave **8 passing / 1 failing**: its boot hook raised
`TypeError: Cannot read properties of undefined (reading 'sendJSONStatus')`
in `lib/api/experiments/index.js:9`. That invocation was stopped; it is not a
replacement for the owned-service R40 campaign and is not reported green.
No application source changed and no new full-suite result is claimed.

The [CodeQL query guidance](https://codeql.github.com/codeql-query-help/javascript/js-sensitive-get-query/)
explains why URL credentials remain sensitive. Existing fixture dismissals in
the earlier checkpoint above do not disposition these production findings.

#### First dispatch packets (historical 2026-11-03)

Use **two implementation lanes at most initially**, plus the coordinator.
P1 is the first bounded task in each lane; P2 is dispatched only after its
packet is concrete. Do not launch another agent to rediscover the same trace.
Later independent runtime work can use a new agent once its inputs are ready.

**Storage/API lane (ST-PG; later M4).** First inventory the actual entries
collection interface and API3 read/write handlers against
`lib/storage/postgres-entries-{read,write,intent}.js`. The current reader refuses
v1, driver read options, nonempty projections and unsorted pagination;
the intent adapter only accepts source `v3`. The HTTP lab deliberately uses a
test-only POST/PATCH adaptation and duplicate POST refusal, not complete legacy
handler response semantics. Do not reproduce that shortcut as the target.

Deliver an operation table covering GET/list/count/search/history,
POST/PATCH/PUT/DELETE, identifier resolution, ordering/projection,
preconditions/headers, batch/retry outcomes and source labels/events. Each row
names the shipping implementation, PostgreSQL applicability, existing test,
remaining case and refusal. Start implementation with the smallest entries
read/conditional-response gap exposed by the table, then progress through
mutations before broadening collections. Preserve POST replacement versus
PATCH merge and JSONB logical equality; do not invent BSON-key-order parity.
Public client priority is established by pinned client/version evidence, not
assumed popularity. The inventory itself is not compatibility acceptance.

Own entries adapter/API-specific source and focused tests only. Any shared
handler extraction must preserve the MongoDB path and obtain coordinator
agreement before touching it. Do not change auth, secrets, migration catalogue
bytes, CLI enablement or the backend registry. Candidate DDL additions go
through the schema owner; committed migration checksums stay immutable.

**Authority/runtime lane (TEN-RESOLVE, T30-WIRING, MT-CONFIG-MIN).** Inventory
`lib/tenant-resolution`, `lib/server/tenant-app`, current secrets verification,
subject/operator policy and tenant settings. Deliver the deployment-owned
alias/configuration shape, verified credential-to-principal mapping, current
data/owner/operator permission contract, authorization linearization point,
suspension/revocation behavior, readiness privileges and listener layout.
Name unresolved operator choices rather than selecting a provider, permission
vocabulary, lifetime ceiling or numeric resource policy by convenience.
Existing subject-policy grants authorize secrets operations only; they are not
general HTTP ACLs. Preserve current authorization on the next protected
operation across workers and fail-closed authority outages.

First implement the smallest reviewed adapter feeding the existing injected
ports with persistent trusted state. Use the existing data-router port for
cross-lane integration; this lane does not implement a competing entries API.
Prove alias selection and verified/current authority with actual two-tenant
requests and independent workers. Listener and lifecycle slices follow under
explicit synthetic opt-ins. No global app context, default tenant, process-wide
root credential, public signup or change to single startup.

**Shared baseline commands**, run from each owned CRM lane with dependencies
already installed. These are proposed selectors, not new measured results:

```sh
NODE_ENV=test node node_modules/mocha/bin/mocha.js --no-config --no-package \
  --fail-zero --reporter ./scripts/execution-reporter.js --timeout 20000 --exit \
  tests/postgres-filter.test.js tests/postgres-identity.test.js \
  tests/tenant-resolution.test.js tests/tenant-app.test.js \
  tests/tenant-jwt-http.integration.test.js
NS_TENANT_HTTP_DOCKER_TEST=1 NODE_ENV=test \
  node node_modules/mocha/bin/mocha.js --no-config --no-package \
  --fail-zero --reporter ./scripts/execution-reporter.js --timeout 60000 --exit \
  tests/tenant-entries-http.integration.test.js
node scripts/test-tiers.js check
```

Storage acceptance also selects `tests/postgres-entries-read.test.js`,
`tests/postgres-entries-write.test.js`, shared write-intent/API regressions and
import cases as applicable, with both disposable database URI variables set.
Authority acceptance selects the existing secrets/Vault/PostgreSQL campaign
with its required Docker flags when exercising persisted policy. Run new cases
through the same execution reporter; disabled labs remain pending, never
passes. Derive exact selectors and required setup from the chosen slice;
do not run an unrelated full campaign for every inventory edit.

#### Dispatch, controls and integration rules

Every dispatch carries the freshly read head and task-open/ownership check,
owned worktree/branch, permitted files, reproduced evidence, predicted
positive/negative outcomes, exact commands and teardown. Explicitly instruct:
**confirm the head commit and that the task is still open before starting**;
**stop and report a mismatch rather than reaching for the nearest thing that
works**. No shipping implementation agents are launched by recording this plan.

Each behavior change needs a focused case that fails without it and a paired
break-it control against the actual implementation in owned scratch. Expected
symptoms include foreign-only data appearing when binding is removed,
revoked access succeeding when current lookup is bypassed, an incorrect HTTP
response when conditional logic is removed, and data/event visibility before
commit. Select the control appropriate to the slice and explain what red
proves. Never mutate a peer worktree. Queue gate additions declare their exact
controls in `queue/gate-controls.yaml`; a test selector is not a complete
parent acceptance gate.

At each join, the coordinator reconciles shared handlers, schema and tier
entries, refreshes/merges current `official/dev` into the owned branch, and
reruns affected combined tests. Before calling a shipping branch ready, run
the full suite (including the browser tier), explicit applicable PostgreSQL
campaigns, existing lint/tier checks and the final `prcheck` step. A failed or
pending required check stops promotion/publication readiness, not unrelated
bounded design. Do not repeatedly launch agents on an unexplained failure.

Keep measurements in dated evidence, status/dependencies in the single queue,
and cycle updates in the release records. Dashboard metadata changes only
when recording a newly measured slice or changing the next gate; generated
views are regenerated, never hand-edited. Confirm peer lane ownership before
dispatch; preserve the pre-existing dependency-test edit in the shared
integration worktree. Use fresh isolated worktrees from the confirmed common
head rather than repointing existing lanes. Commit explicit paths with no
trailers. Agents never push; prepare themed PR updates and maintainer commands.

#### P2 entries projection slice handoff (2026-11-03)

**Read-derived from agent-executed evidence, not a coordinator replay.**
Owned lane `externals/work/crm-entries-next-20261103`, branch
`workspace/entries-next-20261103`, reports clean head
`cabb5eecb5a15ee9050f8894299a78ae300ae731`, from common baseline `0afdb87f`.
Changed paths are `lib/storage/postgres-entries-read.js`,
`tests/postgres-entries-read.test.js` and `tests/postgres-filter.test.js`.
The adapter supports API3 dotted inclusion projection after decoding JSONB;
unsupported exclusions/mixed projections refuse. Default Mongo serving and
shared handlers are unchanged.

With both URI variables set locally to owned disposable PostgreSQL/MongoDB
services, the agent ran:

```sh
NODE_ENV=test ./node_modules/.bin/mocha --no-config --no-package --fail-zero \
  --reporter ./scripts/execution-reporter.js --timeout 30000 \
  --require ./tests/hooks.js tests/postgres-filter.test.js \
  tests/postgres-identity.test.js tests/postgres-entries-read.test.js \
  tests/api3.storage.find.test.js tests/api3.storage.filter-semantics.test.js \
  tests/api3.read.test.js tests/api3.fields.test.js --exit
```

Reported result: **50 passing**. Differential cases cover dotted nested-array
projection, missing paths and `_id` inclusion; real API3 reads assert projected
200 responses, Last-Modified and conditional 304 behavior. Refusing all nonempty
projections makes the handler check fail `500 !== 200`. Returning array members
without recursive projection makes `uploader.radios.id` retain extra `signal`
fields compared with MongoDB. Restored implementation passes. An attempted
unsupported-overlapping-path assertion was removed because that refusal was
not an established contract; no differential mismatch was reported.

Focused lint, tier classification and whitespace checks pass; owned containers
were removed. Reproducible setup uses ephemeral loopback mappings
`127.0.0.1::5432` and `127.0.0.1::27017`, with assigned ports read through
`docker port`; never put live database URLs in evidence.
SQL-side projection/performance, broader list/history/mutation acceptance,
full-suite and combined integration remain UNMEASURED. The branch is unpushed,
not incorporated and not PR-ready.

#### P2 authority slice handoff (2026-11-03)

**Read-derived from agent-executed evidence, not a coordinator replay.**
Owned lane `externals/work/crm-authority-next-20261103`, branch
`workspace/authority-next-20261103`, reports clean head
`ad0cbdac058789bd806ae49047c7f95a6670332c` from the common `0afdb87f`
baseline. It is not incorporated into the integration branch or published.

The bounded slice adds `lib/tenant-authorization/{README.md,postgres.js,postgres-candidate.json}`,
`tests/tenant-authorization-postgres.integration.test.js` and its tier entry.
The explicit operator-run candidate has forced-RLS tenant configuration,
subjects, roles and tenant-composite subject-role links. A read-only adapter
accepts resolved tenant, trusted subject/root/anonymous context and the actual
handler-required Shiro permission. Current configuration and grants are read
in one statement; that committed snapshot is the authorization linearization
point. Defaults preserve `denied`, `readable`, `status-only`, with no anonymous
writes. Subject/default permissions combine; unknown configuration and malformed
authority state refuse explicitly, while a known subject without permission denies.
Root requires a configured tenant and remains a trusted injected identity,
not a credential selected by request input.

Agent command, from its owned lane:

```sh
NS_TENANT_AUTHORITY_POSTGRES_DOCKER_TEST=1 \
  ./node_modules/.bin/mocha --no-config --no-package --fail-zero \
  --reporter ./scripts/execution-reporter.js --timeout 30000 \
  tests/tenant-resolution.test.js tests/tenant-app.test.js \
  tests/tenant-jwt-http.integration.test.js \
  tests/tenant-authorization-postgres.integration.test.js
```

Reported result: **26 passing, 0 failing, 0 pending**, including seven authority
integration tests. Focused lint and tier classification pass (474 files,
eight tiers). Own disposable PostgreSQL containers are removed.
The stale-decision-cache mutation fails committed revocation with
`true !== false`; restoring the current lookup passes. Disabling RLS makes
adapter initialization reject `TENANT_AUTHORITY_UNSAFE`, while a direct
app-role query exposes foreign rows. That control proves the guard and unsafe
state, not HTTP behavior under broken RLS.

The outage case replaces an earlier closed-pool-only check. A live child pool
survives termination of its owned PostgreSQL container through the existing
`postgres-connection.js` idle-error listener; the next authorization rejects
`TENANT_AUTHORITY_UNAVAILABLE`, and the child exits zero without an unhandled
error. Isolate with the same integration selector and
`--grep 'idle-connection termination'`. This measures a request after
termination, not an in-flight query during termination.

A broader tier attempt hit ten-second MongoDB setup hook timeouts in
`00_production-safety` and `XX_clean`; it is not a successful full-suite run.
Production credential-to-stable-subject verification, provisioning, HTTP
adapter integration, readiness/listeners, in-flight outage and the full suite
remain UNMEASURED. This is a bounded implementation handoff, not integrated
acceptance, milestone promotion or PR readiness.

New queue items ST-PG, TEN-RESOLVE and TEN-LAB give the existing platform cards
an executable-work index. MT-CONFIG-MIN scopes the initial subset without
claiming the full T30-SCHEMA-CONFIG catalogue complete. T30-WIRING's current-dev
slice follows TEN-RESOLVE and the secrets contract; old seam evidence is retained.
MT-RUNTIME-PLAN and MT-NEXTGEN-PLAN cover the explicit design outputs above.
Do not delete or bulk-refresh shared old worktrees.

Implementation results and commands are appended after measurement. No complete
adapter, production secret backend, client compatibility or hosted acceptance
is claimed by adopting this roadmap.

<details markdown="1">
<summary>Execution history and acceptance commands (dated evidence, not the current work board)</summary>

### Execution evidence (2026-11-02)

### Tenant JWT Proof Integration and HTTP Gate

The one-commit `workspace/tenant-jwt-proof-20261102` branch is integrated at
`dc2c5fbf`. Its real secrets-backed HTTP tests pass for tenant-bound
verification, current-grant checks, and fail-closed authority outage. The
combined tenant HTTP suite passes 19 with its 10 PostgreSQL lab cases skipped
when Docker is not enabled; explicitly enabling the disposable M3 PostgreSQL
lab passes all 10. `npm run test:tiers` classifies 470 test files across 8
tiers. The trusted-proxy test accepts the fixture's IPv4 and IPv6 loopback
addresses.

This proves the JWT-to-HTTP authorization seam and the M3 test lab, not
production tenant runtime wiring. M1 source import/backend acceptance and M2
production control-plane/runtime acceptance remain open; M3 is not promoted.
No serving enablement or upstream push.

**Upstream local commits `27f085c93ad3f1eaef2bfcecc5cfa8544f2036d5`
and `ce14d637` (explicit connection-URI guard)** on
`workspace/multitenant-20261102` adds `pg` 8.23.1 and a dormant
`lib/storage/postgres-connection.js` foundation. It opens a tenant-bound
transaction, binds with `set_config(..., true)`, joins same-tenant nesting,
rolls back errors, refuses use after release and discards a connection if
rollback fails. A caught SQL error cannot turn PostgreSQL's aborted-transaction
`COMMIT` response into success. The store rejects superuser/BYPASSRLS application
connections. No backend registry or `serve` availability flag is changed.

Measured on PostgreSQL **16.15** and disposable MongoDB 8.0: **43 focused checks
pass**, including **9 PG foundation checks**, across:
`tests/postgres-connection.test.js`, `tests/storage.tenant-scope.test.js`,
`tests/storage-backend-selection.test.js` and `tests/test-backends.test.js`.
ESLint passes for the new module and test. Changing the actual binding call
from transaction-local to session-local made the cleanup check fail; restoring
it passes. The test probes the same pooled backend after commit/rollback,
not merely a new unbound connection. RLS-disable and session-binding controls
also demonstrate the exposure.

**Limits:** this is M0 progress, not the complete M1 adapter or even full M0
promotion. The test uses a synthetic entries-shaped table, not a newly reviewed
generated production migration. PgBouncer revalidation, entries methods/filter
translation, write-contract/backend suite integration and the migration runner
remain. The original PG backend availability remains false; no hosted role
starts. The first regression attempt lacked the project's test environment and
failed; the corrected run used `NODE_ENV=test` and an owned synthetic MongoDB.

**Vault:** [the persisted lab result](../../../tools/lab/vault-transit/results.json)
records **9/9 checks** on Vault **2.2.1**, image
`hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2`.
Scoped encrypt/decrypt, HMAC verification (including wrong-tenant key),
non-exportability, denied key mutation, rotation/rewrap, token revocation and
the overbroad-policy control pass. The first run exposed an incorrect harness
assumption: this server's HMAC encoding is versioned base64, not hex.
The corrected check verifies a 32-byte result.

Vault's cryptographic feasibility supports proceeding with a Vault-facing
adapter contract instead of presuming the built-in signer must come first.
It does **not** establish comparative implementation efficiency, Nightscout
JWT compatibility, least-privilege tenant/consumer integration, ciphertext
storage or production operational acceptance. The built-in option remains
available; it was not implemented or removed.

### Reproduction and maintainer push command

Worktree: `externals/work/crm-multitenant-20261102`.
Install its locked dependencies with `npm ci --include=dev --ignore-scripts`.
For the focused suite, set `NODE_ENV=test`, `MONGODB_URI` to a disposable
test database whose name contains `test`, and `NS_TEST_POSTGRES_ADMIN_URI`
to a disposable PostgreSQL admin connection. Do not use a production database.

```sh
cd externals/work/crm-multitenant-20261102
npx eslint lib/storage/postgres-connection.js tests/postgres-connection.test.js
node_modules/.bin/mocha --fail-zero --timeout 15000 --exit --require ./tests/hooks.js \
  tests/postgres-connection.test.js tests/storage.tenant-scope.test.js \
  tests/storage-backend-selection.test.js tests/test-backends.test.js

# Only the maintainer runs this after review; no upstream push was made here:
git push bewest workspace/multitenant-20261102
```

MT-IDENTITY-PLAN names the separate human-identity design work. The initial
configuration slice still owes its exact setting names, paths, preconditions
and executable API cases; documenting the journey is not claiming that API
already exists.

### Continuation: pooler proof and typed identity primitive (2026-11-02)

The reproducible [pooler/DDL lab](../../../tools/lab/postgres-foundation/README.md)
and [sanitized results](../../../tools/lab/postgres-foundation/results.json)
exercise the actual connection module, not the September adapter. PostgreSQL
**16.15**, PgBouncer **1.25.2**, transaction pooling with one backend and no
per-transaction reset: **9 foundation checks pass**. Two independent clients
execute 24 interleaved tenant transactions on a measured single server PID.
Reads/writes, rollback, binding cleanup, unbound readers and dirty/null/missing
generated-column values pass. Disabling RLS, granting BYPASSRLS and mutating the
actual connection module to session-local binding demonstrate the failures.
The historical emitted entries DDL applies unchanged.

**A discovered M1 blocker, not a passing adapter test:** the current
`externals/work/crm-multitenant-20261102/lib/server/object-id-forms.js:82-106`
returns both an ObjectId and the same-spelling string. Ordinary JSON
serialization collapses them, so the historical `(tenant_id, _id)` DDL rejects
the second stored form with `23505`; raw Extended JSON instead fails its
generated string key with `23502`. The maintainer explicitly requires preserving
the distinction from the first adapter slice, not deferring it to import.

**Local upstream commit `6b1bf889a275b52bd119d122553bceb717e06ca9`**
adds the dormant identity codec:
`externals/work/crm-multitenant-20261102/lib/storage/postgres-identity.js:13-38`.
It keeps kind metadata outside the JSON document and reconstructs the original
ObjectId/string; unsupported/corrupt identities refuse rather than coerce.
The existing emitter now offers **opt-in** `--identity-kinds`
(`tools/nsschema/emit/postgres_emit.py:284-318`), producing the lab candidate
key `(tenant_id, id_kind, _id)` and kind/encoding constraints. The normal
generated production-shaped files are unchanged. This is a migration candidate,
not a boot-time schema modification.

**4 real-PG identity checks pass** using that generated candidate and actual
codec: both forms in both tenants, case/custom-string preservation, kind-scoped
deletion and constraint refusals. Flattening the actual codec's kind recreates
the collision; the restored codec stores both. **65 focused upstream checks**
pass across six files with disposable PG/MongoDB, plus ESLint and test-tier
classification. Both new PG files are now in their appropriate test tiers.
The schema pipeline has **291 passing tests**, including unchanged default DDL.
One attempted regression run omitted the required MongoDB environment; the
corrected isolated PG/MongoDB run is the reported green result.

**Still open:** this is not the entries collection adapter, arbitrary BSON
import fidelity, filter/sort parity, durable events or migration-runner
acceptance. The historical DDL also lacks current v3 `srvModified`/`isValid`
indexes and the tenant-scoped partial unique identifier index. Those unsatisfied
properties stay visible in the report's `adapterBlockers`; the separate
`identityChecks` prove only the typed candidate. No backend availability flag,
hosted role or single-site behavior changes. No upstream push was made.

**Next implementation, without another architecture vote:** integrate the
typed identity into entries reads/writes and emitted migration plans. Preserve
the current choice among identifier matches and ObjectId/string copies, not
only their stored keys. Translate identifier-constraint collisions specifically
and preserve retry outcomes without continuing an aborted PG transaction.
Exercise the current filter/null/array/order/pagination, resend/delete/batch and
source/event contracts before marking M1 accepted. Do not copy the old SQL
compiler or registry availability flag as a shortcut.

**Parallel:** build MIG-RUNNER with explicit hosted operator execution; complete
the minimum settings/subject-policy API and provider-neutral secrets contract.
The recommendation is the Vault-facing adapter next, retaining the built-in
option—not a claim that Vault is cheaper, more efficient or production-ready.
Human identity, evaluator/events and next-generation execution remain separate.

### Continuation: explicit PostgreSQL operator migrations (2026-11-02)

**Local upstream commit `68828b8d`** adds the PostgreSQL-only MIG-RUNNER
foundation using Umzug **3.8.3**. An explicit `nightscout migrate
<up|status|check>` command takes a reviewed, checksummed JSON catalogue, a
non-system namespace and an explicitly named connection environment variable.
No production catalogue is supplied. `--direct` is the operator's assertion
that the endpoint is not a transaction pooler; it is not automatic detection.

`externals/work/crm-multitenant-20261102/lib/migrations/postgres.js:105-164`
uses one pinned direct client and a namespace-specific session advisory lock.
Each migration's SQL and ledger row commit in the same transaction. Read-only
status/check operations neither create schema nor acquire the migration lock;
stale checks, unknown history, checksum drift and non-prefix history refuse.
The catalogue validation is at
`externals/work/crm-multitenant-20261102/lib/migrations/catalogue.js:19-38`;
checksums detect drift, not catalogue authenticity or review.

**39 checks pass**: 5 migration unit checks, 12 disposable-PostgreSQL acceptance
checks and 22 existing CLI checks. These include four overlapping runners,
bounded lock wait, rollback, SIGKILL/restart, explicit connection configuration,
read-only/restricted-role inspection, drift/history refusals and a split-commit
control that demonstrates committed-but-unrecorded DDL. ESLint reports zero
errors and two filesystem-path warnings. Reproduce in the upstream worktree:

```sh
NS_MIGRATION_DOCKER_TEST=1 node_modules/.bin/mocha --timeout 30000 \
  tests/migrations.test.js tests/postgres-migrations.integration.test.js \
  tests/nightscout-cli.test.js
```

**MIG-RUNNER remains in progress:** MongoDB's fencing-safe renewable lease and
resumable steps, real reviewed catalogues/baselines, rollback/export policy,
catalogue distribution/authenticity and serving-role compatibility wiring are
not implemented. Default single-site MongoDB boot is unchanged; no hosted role
or storage backend is enabled and no upstream push was made.

### Continuation: entries read/filter subset (2026-11-02)

**Local upstream commit `7d4f3872`** adds dormant `findFiltered`, `count` and
`findOne` methods. They use the actual tenant-bound connection and typed
identity codec, not the old adapter. The strict filter AST compiles top-level
scalar comparisons, `in`/`nin`, existence and a bounded type subset into
parameterized SQL. ObjectId/string `_id` comparisons retain their kinds;
scalar fields retain MongoDB type brackets, null/missing and array-element
matching. Text comparison uses byte ordering rather than the database locale.

Source:
`externals/work/crm-multitenant-20261102/lib/storage/postgres-filter.js:82-229`
and
`externals/work/crm-multitenant-20261102/lib/storage/postgres-entries-read.js:49-98`.
**6 real PG/MongoDB differential checks** compare results and counts across a
filter matrix, seven sort specifications with skip/limit, nine `findOne`
identifiers with normalized/raw output and empty projections, and overlapping
tenant fixtures. A SELECT-only non-bypass role reads the typed generated
entries table; tenant B's different values expose accidental leakage.
An unbound read refuses. **4 unit checks** exercise unsupported-input refusals
and bound field names/values. The test DDL fixture is byte-identical to
`tools/lab/postgres-foundation/generated/entries.sql` (SHA-256
`0460c76bed932b35472595745491fb61ae918cc6ff4b403b51ba0cc9cffa6a69`);
it is still an experimental typed-key schema, not a production catalogue.

**Combined integration acceptance: 145 passing, no pending**, across 12 files:
the new read/filter and migration checks, existing PG connection/identity,
MongoDB filter semantics, tenant scope, backend selection/harness and CLI
tests. This run used owned disposable PostgreSQL 16 and MongoDB 8.0 with
`NODE_ENV=test`, the project hooks and both database URIs. ESLint has no errors;
the migration slice retains its two filesystem-path warnings. All 461 test
files are classified. Owned containers and private credentials were removed.

Reproduce the read/filter portion from the upstream worktree with
`NS_TEST_POSTGRES_ADMIN_URI` and `CUSTOMCONNSTR_mongo` pointing only to
disposable databases (the MongoDB database name must contain `test`):

```sh
NODE_ENV=test node_modules/.bin/mocha --fail-zero --timeout 30000 --exit \
  --require ./tests/hooks.js tests/postgres-connection.test.js \
  tests/postgres-identity.test.js tests/postgres-filter.test.js \
  tests/postgres-entries-read.test.js tests/storage.filter.test.js \
  tests/api3.storage.filter-semantics.test.js
```

Missing database URIs leave the differential checks pending; that is not
acceptance. Keep the fixture synchronized with the opt-in emitter candidate
until an actual reviewed migration catalogue replaces it.

**Still not M1:** regex (different dialects), dotted paths, v1, nonempty
projections, driver read options, non-JSON scalar operands, unsupported types,
array/object sort semantics, unsorted pagination and negative bounds explicitly
refuse rather than approximate. Shape refusals occur before SQL; sort-value
refusal is data-dependent after querying. Read results are materialized without
a cursor/batch cap and equal-key tie order is unspecified. `findMany`,
`findOneFilter`, `findEveryForm`, writes/events, identifier collision/retry,
current indexes and backend-suite wiring remain. No PG backend registration
or hosted role was enabled.

**Next bounded work:** entries writes/current write-intent outcomes and
identifier constraints; reviewed entries schema/migration catalogue; MongoDB
runner lease/fencing/resume; then trusted tenant resolution/config/auth wiring
for the two-tenant HTTP lab. Regex/projection/array-sort parity belongs in the
remaining compatibility inventory, not an implicit change to supported API
behavior. The owner authorization/revocation contract can proceed independently.
The maintainer push command above now includes both local continuation commits;
no upstream push was made.

### Continuation: dormant entries writes (2026-11-02)

**Local upstream commit `7bcfc8b0e42cacda67ca0bfd62a9374099a26759`** adds
`insertOne`, `updateOne`, `deleteOne`, `updateMany` and `deleteMany` in
`externals/work/crm-multitenant-20261102/lib/storage/postgres-entries-write.js:1-156`.
This is a persistence subset, not a registered backend or integrated write-intent
implementation. It uses the existing experimental typed-key entries fixture;
no migration catalogue or index policy is added here.

Updates/deletes lock their matching rows and write in the same SQL statement.
By-identifier writes follow the existing storage preference (identifier first,
then ObjectId over its string twin), unless an explicit stored `_id` chooses
the exact typed record. Scalar sets/unsets preserve unrelated fields, including
already-stored nested data. Replies distinguish matched from modified rows;
repeating an unchanged patch reports zero modifications. Inserts preserve the
stored identity kind and the requested input normalization behavior.

**Measured: 1 input-refusal check and 8 real PG/MongoDB checks** compare
supported replies and stored documents through the actual MongoCollection
interface and the tenant-bound PostgreSQL connection. Fixtures overlap across
tenants, test the ObjectId/string twins and include unrelated nested data.
Tenant B is unchanged by A's writes and can independently update/delete/insert
its own overlapping identities. Unbound writes refuse; duplicate-key and
explicit callback failures roll back the surrounding transaction.

The concurrency check uses **two distinct backend PIDs** and observes the second
statement waiting on a real PostgreSQL lock before allowing the first commit.
It covers both disjoint patches and restoring a field's pre-wait value.
No-op comparison must use the locked target document: the update relation's
earlier statement snapshot can otherwise skip that second patch. Three actual
implementation mutations fail as intended: removing the identity-kind join,
counting unchanged updates as modifications, and using the stale snapshot
for no-op detection. The restored implementation passes.

**Combined regression: 158 passing, no pending, across 11 files**, on
PostgreSQL 16.15 and MongoDB 8.0.34. This includes the read/filter/identity/
connection tests and existing MongoDB filter, tenant-scope, backend-selection
and v3 write-intent regression tests; those existing tests are not a claim that
the PG subset now executes complete write intents. ESLint, all 462 test-file
classifications and the existing write-boundary check pass. The latter still
covers the existing nine adapter entry points, not promotion of the dormant
PG module. Only this session's two disposable containers were removed.

Reproduce the write slice from the upstream worktree using disposable database
URIs (`CUSTOMCONNSTR_mongo` must name a database containing `test`):

```sh
test -n "$NS_TEST_POSTGRES_ADMIN_URI" && test -n "$CUSTOMCONNSTR_mongo" &&
NODE_ENV=test node_modules/.bin/mocha --fail-zero --timeout 30000 --exit \
  --require ./tests/hooks.js tests/postgres-entries-write.test.js
```

Missing either URI leaves the eight database checks pending, not accepted.
The persistence slice refuses nested/array/BSON set or inserted values,
non-finite numbers and negative zero, dotted/operator/identity update fields,
conflicting set/unset fields, v1 and unsorted `one` filter options. Complex
identifier sort values refuse without modifying any matching row; an explicit
stored id needs no sort. Existing filter-compiler refusals still apply.

**Still not M1:** there is no replacement/upsert/batch/every-form write API,
identifier-index retry or duplicate-error translation, source-label/validation/
commit-event integration, complete read/query parity, cursor cap or backend
registration. Native PostgreSQL constraint errors propagate; no retry is
attempted inside an aborted transaction. Matching sets are locked/materialized
without a size cap; lock ordering/resource bounds still need acceptance.
The typed DDL remains experimental. No serving role or default MongoDB behavior
changes, and no upstream push was made.

**Workstream boundary:** the other session owns MIG-RUNNER, minimum settings/
subject-policy APIs and the provider-neutral secrets contract/Vault-facing
adapter, retaining the built-in option. This slice does not modify those files
or claim Vault cost/efficiency/production readiness. Human identity,
evaluator/events and next-generation execution remain separate. The next
storage slice is entries upsert/resend/batch outcomes with constraint-specific
retry, coordinated with the reviewed schema/catalogue owner.

### Integration: entries and Vault-facing secrets (2026-11-02)

**Local merge `6943dccb25e680d063a00e69ee0434d8bcb3eedb`** joins entries
`7bcfc8b0` and the parallel secrets branch at
`fec19ba5b0526e9c94c751dc24ea4505eb5d92ae`. Its three imported commits are
`a3888080` (provider-neutral component/Vault adapter), `cbbe9179` (PG ciphertext
and audit persistence) and `fec19ba5` (audited rewrap/CAS). The integration branch
remains `workspace/multitenant-20261102`; nothing was pushed upstream.

The dormant component authorizes each operation against injected current
authority, awaits a redacted audit receipt, and binds encrypted plaintext and
JWT audience to the tenant. Vault keys are not exported. The optional PG adapter
persists immutable references and independently committed append-only audit
attempts. A separate maintenance identity can rewrap ciphertext using CAS;
it has neither record INSERT nor plaintext-decrypt authority. Concurrent
rewraps have one winner; retries reload after a conflict or uncertain reply.
The experimental secrets catalogue upgrades through the existing explicit
operator runner; no migration is performed at serving boot.

**Integrated acceptance: 230 passing, no pending, across 17 files.** This runs
entries writes/reads/filter/identity/transactions, existing MongoDB filter,
scope/backend/v3-write-intent regression checks, migrations/CLI, and the full
33-test secrets/Vault/PG acceptance together. All three Docker opt-ins were
enabled, as were disposable entries PG/MongoDB URIs. Real scoped Vault calls,
PG restart, migration SIGKILL/restart, audit-before-provider visibility, tenant
RLS, maintenance-only privileges, rewrap races and simulated lost replies
execute rather than skip. Lab-owned containers were removed.

`tests/tiers.json` merged without conflicts and keeps all four new test files:
the entries-write file, secrets unit file and two secrets integration files.
**All 465 files classify**. ESLint and the existing write-boundary check pass.
No dependency-manifest, migration-runner, entries-source or serving-role file
changed in this merge.

The CI no-database runner was also exercised. Initially missing local frontend
artifacts caused bundle/map, DOM and gzip-accounting failures; building with
`npm run bundle` resolved them. On the built tree:

| Tier | Result |
|---|---|
| unit | 2,108 passing |
| DOM | 205 passing |
| core | 319 passing |
| harness | 92 passing |
| dependency | 368 passing, 1 pending, 1 failing |

The remaining unchanged dependency assertion finds `har-validator` and AJV
6.12.6 in ancestor `/home/bewest/node_modules`, outside the integration tree,
while requiring AJV >=6.14.0. No dependency manifest changed and no ancestor
installation was altered. **The full no-database command is not green**;
this is an explicit environment/dependency limitation, not a secrets/entries
acceptance pass or permission to waive the gate. The production bundle builds
with its three webpack performance warnings.

Reproduce the combined checks in the integration worktree:

```sh
# Both URI variables must name disposable databases; MongoDB name contains test.
test -n "$NS_TEST_POSTGRES_ADMIN_URI" && test -n "$CUSTOMCONNSTR_mongo" &&
NODE_ENV=test NS_MIGRATION_DOCKER_TEST=1 NS_VAULT_DOCKER_TEST=1 \
NS_SECRETS_POSTGRES_DOCKER_TEST=1 node_modules/.bin/mocha \
  --fail-zero --timeout 30000 --exit --require ./tests/hooks.js \
  tests/postgres-entries-write.test.js tests/postgres-entries-read.test.js \
  tests/postgres-filter.test.js tests/postgres-identity.test.js \
  tests/postgres-connection.test.js tests/storage.filter.test.js \
  tests/api3.storage.filter-semantics.test.js tests/storage.tenant-scope.test.js \
  tests/storage-backend-selection.test.js tests/test-backends.test.js \
  tests/write-intent.v3.test.js tests/migrations.test.js \
  tests/postgres-migrations.integration.test.js tests/nightscout-cli.test.js \
  tests/secrets.test.js tests/vault-secrets.integration.test.js \
  tests/postgres-secrets.integration.test.js
node scripts/test-tiers.js check
NODE_ENV=test node scripts/test-tiers.js run unit,dom,dependency,core,harness --ci
```

**Parallel continuation handoff:** the clean secrets worktree can first
fast-forward to this integrated baseline, preserving the original commits:

```sh
git -C externals/work/crm-secrets-20261102 merge --ff-only \
  workspace/multitenant-20261102
```

Its next bounded objective is **synthetic secrets backup/restore and process
crash/retry acceptance** in that isolated worktree. Restore ciphertext/audit
and necessary key versions; demonstrate unchanged references/values and
explicit missing-key/provider refusal, then exercise actual process termination
around rewrap/CAS. Do not equate an interrupted-call test or database restart
with that result. Keep `0001`/`0002` catalogue checksums immutable; any schema
change appends a reviewed candidate migration. Do not modify entries, enable
consumers or push. Reconcile any new tier entry during the next integration.

The entries lane retains upsert/resend/batch/constraint-retry work. MIG-RUNNER's
MongoDB fencing/resume, minimum settings/subject-policy API and current-grant
integration remain separate unfinished work; merging the secrets boundary
does not complete them. Built-in signing remains an adopted option, with no
Vault cost/efficiency/production claim. Human identity, evaluator/events and
next-generation execution remain separate. M1/M2 and backend availability
remain unpromoted.

Source:
`externals/work/crm-multitenant-20261102/lib/secrets/component.js:16-140`,
`externals/work/crm-multitenant-20261102/lib/secrets/postgres.js:34-153`,
`externals/work/crm-multitenant-20261102/lib/secrets/vault-transit.js:29-123`,
`externals/work/crm-multitenant-20261102/tests/postgres-secrets.integration.test.js:19-443`.

### Continuation: entries upserts and post-commit v3 intents (2026-11-02)

**Local upstream `14ae16db2ae090f668672af26b148d620b47fc7a`** extends the dormant
entries lane without changing secrets, migration catalogues, dependencies,
backend registration or default MongoDB behavior. It remains on the single
integration branch; no upstream push was made.

Test follow-up **`a8dd162da2efece40a78eca8783e1e0ba2d341df`** also exercises
resolved OR deletion and pruning through the shared v3 seam; it is the current
local integration tip.

The persistence facade now measures merge upserts/resends, insert-only values,
unsets, changing replacements, ordered/unordered duplicate-key outcomes,
ordered removals, every-displayed-form writes and capped identity resolution.
Stored ObjectId/string identities remain distinct, including upper-case hex
addresses and explicit resolved-id scoping. Ambiguous multi-match upserts,
identity-changing replacements and unsupported input/query shapes refuse.
The bulk implementation is sequential, not a single database round trip.

**Constraint/retry contract:** the typed primary key and a lab-only
`identifier_unique` partial index are distinguished by exact table/schema and
constraint names. The lab index covers tenant-local nonempty scalar strings;
this is not acceptance of legacy MongoDB multikey identifiers or a reviewed
production DDL/catalogue. Only those recognized duplicate errors are translated
for the existing write-step handlers. Unrelated constraints propagate. Each
recoverable operation uses an actual savepoint, so a failed insert does not
leave the surrounding PG transaction aborted. Ordered batches expose the
successful prefix; unordered batches continue past recognized duplicates.
An enclosing caller transaction still rolls everything back if its error
escapes. Concurrent/nested savepoint operations explicitly refuse.

The new **dormant v3 intent seam** reuses the shared entries rule table,
identifying reads, source labels, resend policy, timestamps, identity resolution
and event payload/emitter. A write owns a new transaction, refuses nesting and
emits the existing internal intent event only after COMMIT. It preserves the
current v3 resend rule: **POST replaces; PATCH merges**. This does not apply the
v1 entries merge rule to v3. Route authorization and immutable/domain validation
still belong upstream of this seam, as in MongoDB; trusted tenant resolution,
current-grant enforcement and cache/socket consumers are not wired.

**Measured acceptance:**

| Gate | Result |
|---|---|
| Integrated storage, all shared write-intent suites, migration/CLI and secrets/Vault | **878 passing, no pending, 31 files** |
| Changed entries/transaction checks against MongoDB 5.0.32 | **28 passing, no pending** |
| Same changed checks against MongoDB 8.3.9 | **28 passing, no pending** |
| ESLint, tier classification, existing write-boundary check | Pass; **465 files**, existing nine boundary entry points |

The lab used PostgreSQL 16.15 and Node 22.23.4. The integrated run enabled all
three migration/Vault/secrets Docker opt-ins and both disposable entries URIs.
The entries file contains one refusal check and 17 real differential/intent
checks; the connection file contains ten real PG checks. Existing shared-rule
regressions are not all PG backend tests.

The concurrent-insert check observes the contender waiting on a real unique
index lock held by another transaction. After the winner commits, the failed
insert is rolled back to its savepoint and the existing shared v3 rule applies
the contender as one resend. Update-permission refusal produces no event.
Post-commit observation verifies independently visible stored data and the
completed transaction boundary. Three actual implementation mutations fail:
broadening duplicate classification to an unrelated constraint, publishing the
event before commit, and removing savepoint rollback. Restored code passes.

**Newly measured compatibility boundary:** repeated MongoDB replacements can
report a modification because BSON field order matters, even when their JSON
values are equal. JSONB alone cannot reproduce that count. `replaceFiltered`
and replacement bulk operations therefore refuse JSON-equal replacements
instead of fabricating `modifiedCount`. The identifier `replaceOne` contract
returns only `matchedCount`, so that method can accept the same values.
Exact replacement counters need a reviewed field-order/import representation
and differential acceptance; no schema workaround is silently introduced.

Reproduce the integrated gate from the integration worktree:

```sh
test -n "$NS_TEST_POSTGRES_ADMIN_URI" && test -n "$CUSTOMCONNSTR_mongo" &&
NODE_ENV=test NS_MIGRATION_DOCKER_TEST=1 NS_VAULT_DOCKER_TEST=1 \
NS_SECRETS_POSTGRES_DOCKER_TEST=1 node_modules/.bin/mocha \
  --fail-zero --timeout 30000 --exit --require ./tests/hooks.js \
  tests/postgres-entries-write.test.js tests/postgres-entries-read.test.js \
  tests/postgres-filter.test.js tests/postgres-identity.test.js \
  tests/postgres-connection.test.js tests/storage.filter.test.js \
  tests/api3.storage.filter-semantics.test.js tests/storage.tenant-scope.test.js \
  tests/storage-backend-selection.test.js tests/test-backends.test.js \
  tests/write-intent*.test.js tests/migrations.test.js \
  tests/postgres-migrations.integration.test.js tests/nightscout-cli.test.js \
  tests/secrets.test.js tests/vault-secrets.integration.test.js \
  tests/postgres-secrets.integration.test.js
```

**M1/M2 remain open; bounded code slices are now committed locally.** M1 has
the one-time API importer and entries-schema candidate (`327cbb1f`,
`025704cd`); JSONB key-order parity is not required. The importer target and
candidate-schema/RLS checks pass, but this does not establish full API/storage
compatibility or a point-in-time import. M2 has persistent policy/settings
services, atomic policy/write fencing, tenant resolution and dormant HTTP
composition (`c496d009`); the injected-authority boundary is tested, but no
deployment adapter or serving role is enabled. The opt-in M3 lab
(`a19b549c`) passes its 10 PostgreSQL HTTP cases but does not promote M3.

Remaining M1 work is complete backend compatibility, route and query behavior,
resend/delete/batch outcomes, resource bounds, and documented source-import
limitations. Remaining M2 work is a deployment-owned alias/credential/current-
authorization adapter, production data-router and listener composition, and
owner/operator lifecycle acceptance. The earlier broad no-database AJV failure
remains unresolved and was not waived or reclassified by these targeted runs.

Parallel ownership is unchanged: secrets backup/restore and process-crash
acceptance, minimum settings/subject policy and MongoDB migration fencing stay
outside these entries files. The secrets worktree can integrate this newer
baseline instead of the earlier merge when ready; inspect its current state
before fast-forwarding. Celld, human identity, evaluator/events and
next-generation execution remain separate.

Source:
`externals/work/crm-multitenant-20261102/lib/storage/postgres-entries-write.js:76-91`,
`externals/work/crm-multitenant-20261102/lib/storage/postgres-entries-write.js:202-347`,
`externals/work/crm-multitenant-20261102/lib/storage/postgres-entries-intent.js:46-97`,
`externals/work/crm-multitenant-20261102/lib/storage/postgres-connection.js:91-124`.

### Integration: secrets recovery acceptance and next control-plane slice (2026-11-02)

**Local merge `0de908522a47da6659f2fc0fc9254189a80ca815`** joins entries
`a8dd162d` with parallel secrets recovery
`78b915ab0e5e9e8c158d3b892f9934b0d45f06ef`. The imported delta is only the
secrets README, PG integration test and isolated worker fixture. There are no
new migration/catalogue/checksum, dependency, entries-source or runtime changes.
Both original branches remain in history. No upstream push or backend
enablement was made.

The documented combined command in the preceding section was rerun on this
merge: **879 passing, zero pending across 31 files**, including all **34**
secrets/Vault/PG checks with the Docker opt-ins enabled. ESLint, all **465**
test-file classifications, the existing nine-entry write-boundary check and
diff checks pass. The earlier broad no-database AJV limitation remains.

**Recovery evidence:** actual custom-format `pg_dump`/`pg_restore` restores
ciphertext, audit and migration state into a distinct empty database. Actual
encrypted snapshots of non-dev single-node Vault Raft restore the required
data/signing key versions after the source Vault is removed. References and
values survive; old snapshots explicitly refuse newer versions; absent keys
and provider outages refuse without fallback. Restored RLS and audit/
maintenance privileges are checked.

An owned child uses the actual component and maintenance CAS. SIGKILL before
CAS preserves original ciphertext plus the committed attempt audit; a new
process completes the rewrap. SIGKILL after the actual CAS commit preserves the
new ciphertext; a new process retries without changing those committed bytes.
Both paths verify audit attempts and unchanged reference/plaintext.

**Limits:** the database restore shares a disposable cluster whose roles
already exist. The Vault fixture uses test-only loopback HTTP, one-share
unseal and forced snapshot restoration with separately retained synthetic
unseal credentials. This does not recover cluster globals, production auth,
current grants, consumer configuration or external credentials, and does not
prove HA, coordinated online snapshots, remote archive integrity/retention,
RPO/RTO, key-retirement readiness, host failure or a kill during database commit.
The bounded backup/restore and worker-crash gaps are measured; production
recovery remains open.

**Parallel continuation: MT-CONFIG-MIN/current-authority boundary.** Start by
fast-forwarding the clean secrets worktree, after checking it has not advanced:

```sh
git -C externals/work/crm-secrets-20261102 merge --ff-only \
  workspace/multitenant-20261102
```

Then continue one bounded control-plane slice in that isolated worktree:

- Reconcile the minimum settings/subject-policy contract against the existing
  reviewed catalogue, permission vocabulary and code/operator floors. Specify
  version preconditions, effective-value provenance, attribution and explicit
  unsupported-name/conflict/refusal cases before exposing routes.
- Implement a dormant tenant-local subject-policy/current-authority service
  behind the existing secrets `authorize` boundary, not a second secrets
  provider. Define the authoritative-read linearization point. Keep any new
  schema in a separate reviewed candidate; preserve existing secrets migration
  bytes/checksums.
- Use two independent workers/adapters and real persistence: a committed grant
  removal or revocation is refused on the next authorization check; an
  unavailable authoritative store fails closed. Cover stale-version writes,
  concurrent policy changes, A/B identity overlap, floor weakening and positive
  own-tenant operations. Do not equate service tests with socket/data enforcement.
- Reuse existing test tiers, report opt-ins/pending honestly, and return a
  clean commit plus the exact combined acceptance command. Stop for maintainer
  input only where the reviewed sources leave a real product decision open.

Do not modify entries, enable serving/owner routes or runtime consumers, push
upstream, weaken authentication, add human identity or claim end-to-end
revocation. MongoDB migration fencing/resume, the built-in signer option,
production recovery and credential-consumer cutover remain separate unfinished
work. This prioritizes the current-grant dependency for M2, not more Vault
feature expansion or a cost/efficiency claim. This session retains entries
schema/import/compatibility acceptance.

Source:
`externals/work/crm-multitenant-20261102/tests/postgres-secrets.integration.test.js:332-679`,
`externals/work/crm-multitenant-20261102/tests/fixtures/secrets-rewrap-worker.js:1-49`,
`externals/work/crm-multitenant-20261102/lib/secrets/README.md:324-408`.

### Parallel control-plane acceptance and next handoff (2026-11-02)

**Verified local state:** clean `externals/work/crm-secrets-20261102` on
`workspace/secrets-vault-20261102` at `011802ba`, following `1dd8990b` and
integrated baseline `0de90852`. The integration worktree still points to
`0de90852`; neither new commit is its ancestor. These are complete bounded
local slices, **not integrated acceptance or M2 promotion**.

`1dd8990b` adds persisted exact subject grants behind the existing secrets
authorization callback, versioned replacement and atomic redacted change audit.
Real independently pooled adapters prove committed revocation on the next
authorization read, code/operator ceilings, conflicts, tenant isolation,
audit rollback and actual database-outage refusal. Management authentication
and current operator limits remain injected trusted dependencies.

`011802ba` adds only typed `DISPLAY_UNITS` and `SHOW_SECONDS`, effective-value
provenance, whole operator-rule overrides, full owner snapshot replacement,
immutable attributed history and whole rollback refusal under current policy.
Real persistence proves cross-adapter visibility, concurrency, isolation,
history rollback and database type/RLS/privilege refusals. Operator policy is
injected; its snapshot and owner CAS are **not atomically fenced**.

**Recorded local acceptance:** **36 passing, zero pending** with both Docker
opt-ins, ESLint clean, all **465** test files classified and diff checks clean.
This is not a fresh integrated run or the full application suite. Existing
migration bytes/checksums, entries, runtime consumers and serving remain
unchanged; the new schemas are separate experimental candidates. Actual
mutations bypassing persisted-grant enforcement and rollback refusal failed;
restored implementations passed.

**Integration handoff:** the integration session should inspect its clean
worktree and current ancestry, then incorporate `workspace/secrets-vault-20261102`
with both commits. Do not fast-forward the advanced secrets branch to the old
baseline or modify a peer's dirty worktree. Rerun from the incorporated worktree:

```sh
NS_SECRETS_POSTGRES_DOCKER_TEST=1 NS_VAULT_DOCKER_TEST=1 \
  node_modules/.bin/mocha --fail-zero --timeout 30000 \
  tests/secrets.test.js tests/vault-secrets.integration.test.js \
  tests/postgres-secrets.integration.test.js
node_modules/.bin/eslint lib/secrets lib/subject-policy lib/tenant-settings \
  tests/secrets.test.js tests/vault-secrets.integration.test.js \
  tests/postgres-secrets.integration.test.js tests/fixtures/secrets-rewrap-worker.js
npm run test:tiers
```

Then rerun the integration session's broader combined gate; do not extrapolate
its count from these local results. Record the actual merge SHA and results on
alignment `main` before marking the slices integrated.

**Next parallel milestones:** the control-plane lane should persist reviewed
operator settings rules and subject-grant ceilings, with coordinated policy
generation/preconditions so tightening cannot permit stale-policy owner writes
or rollback. Prove real cross-worker races, outage refusal, isolation and
atomic history before route enablement. Synthetic recovery of the new policy/
settings/authority state can follow. Entries schema/import/compatibility stays
with the integration session. MongoDB MIG-RUNNER fencing/renewable leases/resume
is a separate feasible lane only after confirming ownership, with explicit
hosted operator execution and real competing-runner/crash acceptance.

Keep alignment records current at bounded acceptance and integration handoffs:
update this status summary, append measured evidence, refresh progress/queue
notes without promoting unfinished parents, and rebuild the generated HTML.
No upstream push, publication or serving enablement is implied. Human identity,
evaluator/events, built-in signer implementation and next-generation execution
remain separate; Vault has no comparative cost/efficiency/readiness claim.

Source:
`externals/work/crm-secrets-20261102/lib/subject-policy/README.md:1-143`,
`externals/work/crm-secrets-20261102/lib/tenant-settings/README.md:1-148`.

### Parallel MIG-RUNNER transactional MongoDB slice (2026-11-02)

**Local commit `562f6206`**, on the clean isolated
`workspace/secrets-vault-20261102` worktree, extends the existing explicit
Umzug operator command with `--backend mongodb`. The peer branch now contains
`1dd8990b` and `011802ba`; their integrated runs are pending, not accepted here.
The runner commit is not yet incorporated. No peer worktree was modified.

**Bounded scope:** MongoDB 5+ writable replica-set primaries, transactional
idempotent scalar-equality `$set` backfills against existing collections.
No arbitrary JavaScript, standalone mutation, application DDL/index steps,
production catalogue, rollback, serving integration or single-site boot change.
Existing PostgreSQL/secrets/settings/subject-policy migration bytes and
checksums are untouched, as are entries and dependency manifests.

An expiry-only lease cannot fence a paused worker's arbitrary cross-document
standalone writes. This slice instead changes lease owner/epoch and a shared
fence together in a transaction. Every data migration checks the current lease,
writes that fence and commits its data plus ledger in one transaction. Takeover
must write the same fence, so a stale transaction refuses/conflicts before a
data command; a takeover cannot commit across an active fenced transaction.
Server-time expiry and serialized renewal use a separate lease document.
Failed renewal is surfaced, not ignored. Release cannot remove a successor's
lease or reset its epoch. Completed migrations survive; retries apply the
pending suffix. A transaction already holding the fence may finish after lease
expiry but before successor takeover; expiry is not retroactive cancellation.

**Measured acceptance:**

| Gate | Result |
|---|---|
| Combined PG/MongoDB/CLI, PostgreSQL 16 and MongoDB 8.3.9 | **53 passing, zero pending** |
| All MongoDB checks against 5.0.32 | **12 passing, zero pending** |
| Shared-fence removal mutation | Fails: a stale worker attempts data after takeover |
| Data-session removal mutation | Fails: uncommitted data becomes externally visible |
| Restored affected mutation selectors | **2 passing, zero pending** |
| ESLint / tiers / diff checks | Zero errors, two filesystem-path warnings; **466 files** classified; clean diff |

Real authenticated disposable single-node replica sets prove renewal across
two lease periods, overlapping runners, SIGSTOP/expiry/takeover, blocked
takeover across a live transaction, actual SIGKILL before and after commit
with new-process retries, failed-ledger rollback, drift/history refusal,
read-only checking and paused-database outage refusal. A separate actual
standalone server refuses before metadata or data mutation. Fixtures use
synthetic credentials, loopback-only random ports, no persistent volumes and
owned worker/container teardown. The lab bounds abandoned transactions to
five seconds; production parameters and replica-set failover are not accepted
by these tests.

From `externals/work/crm-secrets-20261102` (or the incorporated worktree):

```sh
NS_MIGRATION_DOCKER_TEST=1 NS_MIGRATION_MONGO_DOCKER_TEST=1 \
NS_MIGRATION_MONGO_IMAGE=mongo:8 node_modules/.bin/mocha --fail-zero --timeout 40000 \
  tests/migrations.test.js tests/postgres-migrations.integration.test.js \
  tests/mongodb-migrations.integration.test.js tests/nightscout-cli.test.js
NS_MIGRATION_MONGO_DOCKER_TEST=1 NS_MIGRATION_MONGO_IMAGE=mongo:5.0.32 \
  node_modules/.bin/mocha --fail-zero --timeout 40000 tests/mongodb-migrations.integration.test.js
node_modules/.bin/eslint lib/migrations lib/cli/commands/migrate.js \
  tests/migrations.test.js tests/mongodb-migrations.integration.test.js \
  tests/fixtures/migrations/mongo-worker.js
npm run test:tiers
```

Local `mongo:8` measured 8.3.9; always report the actual server version rather
than assuming a moving tag. The new MongoDB suite needs its own explicit
`NS_MIGRATION_MONGO_DOCKER_TEST=1` opt-in: do not count skipped tests as passing.

**Handoff/remaining:** integrate `562f6206`, rerun these and the broader
integration gates, then record actual SHA/results on alignment `main`.
MIG-RUNNER remains in progress: safe standalone/index operation or quiescence
contract, bounded/chunked backfills, actual catalogues/baselines, authenticity,
rollback/export policy and serving compatibility wiring remain unfinished.
Persistent operator policy and atomic policy/write fencing remain the next
independent control-plane option; neither was silently implemented here.
No push, publication or serving enablement is authorized.

**API import clarification and implementation:** this is a one-time database
population by reading the source Nightscout API, not schema migration over an
API and not ongoing NS-to-NS synchronization (`nightscout-connect` remains
separate). The committed importer (`externals/work/crm-multitenant-20261102/lib/import/entries.js:108-181`)
uses a bounded live `/api/v3/entries` baseline followed by best-effort
`srvModified` history. It runs from the beginning on rerun; durable checkpoints
are not required. The source bearer token is read-scoped and not persisted.
The entries schema is an explicit operator-migration candidate, not applied by
the importer. JSONB logical equality is accepted; no known client depends on
JSON object field ordering.

The zero-pause reconciliation is best effort, not snapshot-isolated: the
baseline uses offset pages, so concurrent source writes may shift page
boundaries. History can catch updates and soft-delete markers with
`srvModified`, but there is no guarantee of a complete point-in-time copy.
API v3 permanent delete removes a row, and v1 DELETE physically removes
matching rows; neither leaves a history tombstone
(`externals/work/crm-multitenant-20261102/lib/api3/generic/delete/operation.js:21-24`,
`externals/work/crm-multitenant-20261102/lib/server/soft-deleted.js:18-20`).
Hard deletes during import can therefore leave stale target rows or be missed.
History also cannot return legacy rows without `srvModified`, so the baseline
scan must cover them. Repeated textual IDs fail closed rather than merge
ambiguous string/ObjectId identities. API projections may omit stored fields;
do not call this a raw database backup or claim lossless import. The importer
does not enable the global PostgreSQL serving backend or the `serve` roles.
This policy does not change the explicit schema operator boundary.

Source:
`externals/work/crm-secrets-20261102/lib/migrations/mongodb.js:59-199`,
`externals/work/crm-secrets-20261102/tests/mongodb-migrations.integration.test.js:108-287`.

### Parallel MIG-RUNNER primary recovery and renewal loss (2026-11-02)

**Local `436ef543`** follows runner `562f6206` on
`workspace/secrets-vault-20261102`. This continuation changes only the MongoDB
integration tests, synthetic worker fixture and migration README. Implementation,
catalogue/checksum bytes, dependency manifests, entries and serving remain
unchanged. The peer branch still points to `011802ba`: both runner commits
are ready for integration, not yet incorporated or integrated-tested here.

**New measured cases:**

- Pause the actual database across two lease periods while a worker waits
  before the transaction fence. Expired renewal explicitly matches zero rows;
  the worker reports `MIG_LOCK_LOST`, attempts no data, does not reacquire its
  epoch, and leaves original data/empty ledger. A new process acquires a higher
  epoch and completes.
- Abruptly restart the actual owned primary with
  `docker restart --signal SIGKILL`, after transactional data but before commit,
  or after committed completion. Verify a changed primary host PID, kill the
  waiting worker to prevent replay, reconnect using the rediscovered published
  port, and inspect persisted state independently. Uncommitted data/ledger
  roll back; committed values and the exact ledger row survive. A fresh worker
  applies only the pending suffix or no-ops when already committed.

**Validation:** **56 combined PG/MongoDB/CLI checks**, zero pending on MongoDB
8.3.9; all **15 MongoDB checks** pass at 5.0.32 too. The same combined and floor
commands in the preceding section apply, with the additional three cases.
Removing renewal expiry produces a matched-count failure (1 instead of 0);
removing the transactional data session leaves changed data after primary
crash without its ledger and fails the persisted-value assertion. Restored code
passes. ESLint: zero errors/two filesystem-path warnings; **466 files** classify;
diff checks pass and owned fixtures are removed.

**Limits and handoff:** this is single-node primary-process/journal recovery,
not multi-member failover, network partition, lost-disk/host/power recovery,
archive restoration, unknown-commit-response recovery or production RPO/RTO.
No new serving or schema API is enabled. Integrate both commits from the clean
parallel branch and rerun targeted plus broader integration gates; record actual
SHA/results before promoting any slice. Persistent operator-policy fencing,
standalone/index migrations and the deferred source-Nightscout API importer
remain separate unfinished milestones.

Source:
`externals/work/crm-secrets-20261102/tests/mongodb-migrations.integration.test.js:195-321`,
`externals/work/crm-secrets-20261102/tests/fixtures/migrations/mongo-worker.js:10-45`.

</details>

### M1-M2 code slices and acceptance (2026-11-02)

The integration worktree `externals/work/crm-multitenant-20261102` now has
four bounded commits, with no upstream push:

| Commit | Slice | Acceptance boundary |
|---|---|---|
| `327cbb1f` | One-time Nightscout API entries importer, candidate entries schema, JSONB-safe PostgreSQL target | Importer replay and tenant-bound PostgreSQL write pass; no snapshot guarantee, full backend compatibility, or serving registration |
| `025704cd` | Candidate entries schema and forced-RLS migration acceptance | Generated v3 fields, typed IDs, identifier uniqueness and RLS are checked through the operator runner |
| `c496d009` | Persistent settings/subject/operator policy, atomic write fencing, tenant resolution and dormant HTTP composition | Provider-neutral dependencies fail closed; no deployment-owned authority adapter or production listener |
| `a19b549c` | Opt-in two-tenant entries HTTP lab | All 10 PostgreSQL lab cases pass; this is a test harness, not an enabled service role |

**Measured checks:** the importer, CLI and PostgreSQL writer unit tests pass
(9 total; importer and CLI account for 7); its disposable PostgreSQL target
test passes (1). The migration and tenant HTTP Docker suites
pass 23 combined (13 migrations, 10 HTTP lab). The provider-neutral
resolver/app/JWT HTTP tests pass 19. The combined secrets, Vault and PostgreSQL
policy gate passes 37, including persisted current grants and atomic
settings/grant fencing. ESLint passes for the changed CRM code, and
`npm run test:tiers` classifies 473 files across 8 tiers.

These slices do not promote M1 or M2. M1 still needs full entries/API/storage
compatibility and resource acceptance; the importer is offset-paginated and
best-effort, not a consistent snapshot. M2 still needs deployment-owned tenant
aliases, trusted credential/current-authorization adapters, production data
router and listener separation. `serve` roles remain disabled. The M3 test lab
does not replace those prerequisites. The broader no-database suite's known
AJV failure remains separate and unresolved.

### PR #8898 security-check disposition (2026-11-03)

Read-derived review of `nightscout/cgm-remote-monitor#8898`, still open at
`a19b549ce524b93eb5f91f013c573e4e44aed217`, found that CodeQL alerts
141, 142 and 143 (`js/missing-rate-limiting`) refer only to
`tests/fixtures/tenant-entries-lab.js:54-57,104-105`. The fixture's only caller
is the opt-in disposable integration test, with a loopback listener and
generated credentials. Its enclosing tenant middleware verifies credentials
and current authorization before these handlers. No shipping startup imports
the fixture; these alerts do not establish production exposure.

The three alerts were individually dismissed as false positives. GitHub API
read-back confirmed `state: dismissed`, `dismissed_reason: false positive`
for each, at `2026-11-04T01:01:38Z` (November 3 locally). No source suppression,
global rule exclusion or production rate-limiting change was made.
The CodeQL check subsequently reported `pass` in `gh pr checks 8898`.
This disposition does not establish full security acceptance of the branch
or resolve the separate failing database CI jobs in run `41574423920`.

### PR #8898 database-CI accounting fix (2026-11-03)

Reproduced on PR head `a19b549c`: eight deliberately disabled integration
lab files registered pending tests through ordinary `describe.skip`, but
`scripts/execution-reporter.js` recognized only backend exclusions.
The representative Node 22.23.4/MongoDB 8.0 CI job completed 3,583 integration
tests and 18 stress tests, then exited 8 for missing test-body execution.
Running the eight files without their opt-ins reproduced 77 pending tests
and eight `TEST_EXECUTION` missing-body errors, not failed lab assertions.
The inspected MongoDB 6 and maintained-MongoDB jobs had the same accounting
symptom.

Fix `04321de0e3b3a7ea8d624fc5b8d3673aab218c56` adds an explicit
`optInSuite` requirement marker to those eight suites and accounts for its
pending events. Disabled labs remain visibly pending, not passing.
Enabled labs, ordinary skipped files and empty labs retain execution
enforcement. Serial/parallel regression tests cover enabled, disabled,
failing, skipped, nested and empty cases. Ablating the reporter's opt-in
recognition makes the regression fail with
`TEST_EXECUTION: no test body completed in tests/fixtures/opt-in.fixture.js`;
the restored implementation passes. No shipping REST implementation,
dependency manifest or lockfile changed.

The separate merge `0afdb87f83c3b66a5206fa8bd9e5046696bcc2d1` incorporates
`official/dev` `4a482627bfdafb1fef8dcbe0ac6c484811cae563`, preserving
`migrate`, `single`, `multitenant` and rejection of the former `serve` alias.
The tested isolated branch is `workspace/pr8898-ci-20261103`; the existing
`workspace/multitenant-20261102` integration branch was fast-forwarded to
that head. Its pre-existing uncommitted dependency-resolution test edit
was preserved and is not part of the tested committed tree.

Reproduced on the merged tree, Node 22.23.4 and disposable MongoDB 8.0.34,
with `TZ=UTC` and CI shuffle seed `41574423920`: all seven non-browser
tiers passed, 6,711 passing / 100 pending / 0 failing. Tier totals:
unit 2,125; DOM 205; dependency 368 with 2 pending; core 319; harness 93;
integration 3,583 with 98 pending; stress 18. Focused selection/backend
regressions passed 39. Additional enabled PostgreSQL/Vault/import/HTTP
and selected migration/persistence checks passed 36. Pending opt-in
cases are not evidence of exercised PostgreSQL behavior.

Changed-file ESLint: zero errors, two existing filesystem-path warnings.
Test classification: 473 files across eight tiers. Whitespace checks and
the final `tools/review/prcheck/prcheck.sh` passed; it confirmed the tested
branch contains current `official/dev`. Browser replay, MongoDB migration
opt-ins and the remaining PostgreSQL migration/secrets campaigns were not
rerun. These results do not promote M1-M6 or establish fresh remote CI
success. No agent push was performed.
Exact run commands and acceptance limits are recorded in
[R23](../remedial/rc-16.0.0-integration-record.md#r23---8898-opt-in-ci-accounting-on-0afdb87f-2026-11-03).


### Accepted frame acquisition and concurrent-read characterization (2026-11-05)

R49 records cumulative runtime characterization over R46 and the adopted R48
owner-authority data-token integration. Actual Mongo/PG acquisition and actual PG
HTTP concurrent reads now have bounded executable gates and semantic controls.
The [architecture plan](architecture-seams-execution-plan-2026-11-05.md#reproduced-frame-acquisition-and-concurrent-reads)
owns the measured bounds/frame/statistics/identity differences and mixed-frame
observation. No common revision or shared production implementation is inferred.
Next extract private acquisition behind the explicit path policies and rerun
these gates; durable realtime/evaluator recovery remains MT-RUNTIME-PLAN work.
Exact tree, regression and control results live in R49 of the
[integration record](../remedial/rc-16.0.0-integration-record.md).

### Accepted independent evaluator frame characterization (2026-11-05)

Independent `codex/evaluator-frame-20261105` at
`5173864da1835da7aecf1f73121b28463f6a6a70` extends R47 with actual Mongo read
barriers, concurrent raw writes and a real subsequent write trigger. R50 records
full/browser regression, parent archived38 replay and clinical/retention controls.
Selected A/B then B/B results, callback-error retention and recovery are reproduced;
late-read teardown establishes no late fake-provider delivery only. Cancellation,
internal closed-state immutability, all-writer/alarm coverage, live statistics/cost,
logical no-op policy and multitenant durable recovery remain open. The independent
profile is not joined into REST or admitted as a multitenant evaluator.


### Accepted optional local data-token authority (2026-11-05)

The adopted [owner authority contract](owner-authority.md) and its D22 amendment
own the policy. [R48](../remedial/rc-16.0.0-integration-record.md#r48---local-public-token-verification-through-actual-api-on-3d5eac19-2026-11-05)
accepts optional new-format data-token Ed25519 local verification through the
actual API, with current PostgreSQL tenant/session/credential/key/grants on each
operation and same-state legacy compatibility. The signature, audience, session
and stale-snapshot controls fail semantically. Human issuer/refresh, full
individual-setting catalogue and proposed-grant/delegation ceiling enforcement,
production provider/key distribution and protected streams remain incomplete.


### Accepted coherent CI client batch and M0 foundations (2026-11-06)

[R60](../remedial/rc-16.0.0-integration-record.md#r60---coherent-ci-client-batch-and-m0-foundations-2026-11-06)
accepts the coherent compatibility/CI batch at `d89a44e1`. Its
[final capsule](../../../reports/tenancy/batch-a-acceptance-d89a44e1-2026-11-06.md)
records the final corpus/prcheck and the exact product/test/dependency identity
supporting reuse of the earlier full/browser/client/pooler captures. The failed
provisioner attempt remains immutable; its test-database safety guard was retained.
No classifier waiver or relaxed credential policy was used.

**M0 foundations is promoted.** Current restricted-role binding, overlapping
identities, unbound refusal, read/write isolation, rollback/error cleanup,
physical pool reuse and paired breaks are measured. The expanded corpus supplies
current migration/catalogue and executable schema/privilege refusal; the separate
pooler proof supplies transaction-pooling behavior without substituting its
historical DDL for the current migration catalogue. D21's explicit lab preview
is permitted; this promotion enables no default or production role.

The bounded `M4-CLIENT-LAB` measurement card is complete after canonical
integration. It establishes the selected actual cgmsim/oref0 payload, stored-value
and refusal workflows, with independent oracle/classifier controls. Connector
observations retain their own ancestor scope. M4 as a milestone still needs its
broader client/onboarding/v3 surface and M3 prerequisite.

M1 remains open for complete admitted backend/import semantics, populated
identity/order fidelity and broader resource behavior. Existing write-set/import
caps are implemented and must not be described as absent; capacity, wider read
work and scaling remain unmeasured. M2 still needs deployable owner/control-plane
composition and current authority/lifecycle completion; human management
issuer/refresh and full owner capabilities retain the roadmap's M6 gates.
M3 retains complete M1/M2 dependencies even though its bounded HTTP lab passes.

B7 direction approval is recorded in the
[adopted contract](durable-event-delivery-contract-2026-11-06.md#11-maintainer-acceptance-and-experiments).
The first dormant replay implementation and recovery experiments proceed under
that approval. Dormant owner-ceiling readers and populated PostgreSQL recovery
labs also proceed on separate branches; their source tests are not runtime
acceptance or activation. M5/M6 remain open. Work continues in larger completion
packages under the [batching plan](multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06).

Programme figures live in R60 and its linked immutable captures. Current milestone
claims live in the [dashboard source](multitenant-delivery-status.json), and queue
claims remain in the manifest. Publication/remote CI is recorded after execution;
local acceptance does not imply release or production enablement.

### Accepted bounded owner reader and recovery batch 2026-11-06

[R62](../remedial/rc-16.0.0-integration-record.md#r62---bounded-owner-reader-replay-and-populated-recovery-batch-2026-11-06)
accepts candidate `83582e87`: optional current subject-grant clamping, dormant
persisted typed replay and populated PostgreSQL recovery lab. Comprehensive
campaigns executed on 871; the descendant changes only the source-control runner
and passed final prcheck. R62 and its immutable capsules own counts, controls,
identity-based reuse and failures. No new milestone promotion or default enablement.
Selected actual-client, full runtime/management and operational criteria remain.

### Accepted bounded clinical projection controls 2026-11-06

[R67](../remedial/rc-16.0.0-integration-record.md#r67---bounded-recovered-clinical-projection-native-controls-2026-11-06)
measures dormant current-row clinical recovery on unpublished1990: actual typed
identity/bootstrap assertion controls and seven restored native cases. This is
local component evidence, not whole1990 acceptance, live evaluator scheduling,
notification/ack delivery or M5 promotion. R66's socket failure remains separate;
current published835 retains its verified R64 scope.

### Measured fresh schema socket DATA controls 2026-11-06

[R68](../remedial/rc-16.0.0-integration-record.md#r68---fresh-schema-socket-data-prototype-native-controls-2026-11-06)
measures optional fresh-schema DATA pattern/transaction/current-authority controls
and restored four native cases. Catalogue matrix retains its original source.
No populated import, downgrade, production transport/rollout, protected stream,
alarm ack or broader M4/M5/M6 completion is adopted. Later joined acceptance must
name its own frozen head; published835 retains R64 scope.
