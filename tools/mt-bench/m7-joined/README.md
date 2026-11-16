# Joined M7 capacity adapter

This prepares the **next** measurement; it does not establish a capacity result.
The prior capacity record and authorization/allocation profiles retain their own
source scope. No prior working-tree lib mount or bootstrap patch is reused here.
Only committed paired core/deployment sources can serve a run.

A separate [fresh-image diagnostic](DIAGNOSTIC-SEAM.md) permits bounded useful tests
before full acceptance without claiming acceptance or capacity.

The coordinator must finish the coherent candidate and its full acceptance, then
hand over a quiet host. This lane does not stop foreign containers, including a
peer's `nsauthz-base-n1000`, or start a capacity campaign during other work.

## First pgstream sample

Use the same prepare/deploy/run/down CLI below with `--profile pgstream-sample`,
`--tenants 2` (existing global bound 1–10000), `--replicas 1`, and
`--postgres-image sha256:EXACT_EXISTING_WAL2JSON_IMAGE_ID` on `prepare`.
Pass `--backend-subnet` and `--edge-subnet` together for owner-selected private
CIDRs when Docker default address pools are exhausted. The binding validates
syntax/overlap; the owner checks host availability.
For the first diagnostic, use `--run-purpose discovery` and an existing
`joined-diagnostic` / `AUTHORIZED_DIAGNOSTIC` receipt with exact pair/image/
instrument, `functionalAcceptanceAtAuthorization: PENDING`, and limits matching
tenants, one API and selected load seconds. This route records UNACCEPTED metrics
and cannot pass capacity/pilot/campaign acceptance. Accepted mode still requires
the existing acceptance receipt. The owner supplies the exact pair and image.
Discovery preparation checks both existing image IDs and the app's core/deploy
labels before creating the cell or installing dependencies. A mismatch leaves the
target absent; retain the command refusal separately. Successful preparation records
`imageInputPreflight` in owner.json. Runtime/config/collector preflight still follows
deployment. Baseline and candidate use separate directories, receipts and exact
source/image arguments; neither substitutes for the other's attribution.
Use `--fixture-project ns-rest-joined-baseline` (and a distinct candidate name)
when preparing a new fixture for the REST helper. The selected name is passed
to the existing source binding and retained in owner.json; defaults still use a
unique generated name. Existing containers or orphaned volumes/networks under
that project refuse before source staging. This option creates a new fixture;
`attach --project` continues to bind an existing owner's fixture without changes.
After source-driven deploy and preflight, pass the prepared cell directly as the
REST attachment and its `state` directory as `--state`, with the same project and
exact expected source/image. REST retains its own source allowlist and traffic
authorization; selecting a fixture does not authorize a workload window.
This selects `NS_PGSTREAM=1`, a 60-second sampler-disabled
baseline, 120-second idle and 600-second ordinary load (`ACCEL=1`, `HOT_FACTOR=1`).
A separate synthetic correctness uploader writes every 300 seconds. Its stored
ID/glucose, durable completed versions/rows/frame and already-connected stock
clients must agree. All workload writes also pass the independent count oracle
and row-mutation control. No worker restart campaign runs in this sample. The selected startup and runtime
roster omit the retired legacy feed-reader; pgstream runs inside evaluator.

Source helpers resolve only the cell-owned lockfile dependency tree; evaluator
and realtime image processes independently check `/opt/app` pg resolution before
load. Per-process CPU-counter bookends and RSS distinguish evaluator Node from its
pgstream child; process replacement/missing data is UNMEASURED.
`sql-attribution.json` separates the configured pgstream role from adapter
roles using full private statement bookends. The frozen PostgreSQL command preloads pg_stat_statements, enables top-level
statement capture and I/O timing. Deploy creates the extension only in maintenance
database postgres after infrastructure startup; an already-running server without
the preload requires owner-controlled restart/recreation. Statement execution time is not
PostgreSQL CPU or WAL-decoding CPU. A measured diagnostic cell establishes that sample;
it grants no capacity acceptance or ceiling. Live sample behavior remains UNMEASURED until run.

`--warmup-seconds`, `--idle-seconds`, `--load-seconds`, `--accel`, `--hot-factor`
and `--sampler-interval` retain the selected values in the manifest. Short windows
record incomplete nominal-cycle/timer coverage. No automatic sweep runs.
`attach` accepts the prepare provenance arguments plus existing `--project`,
`--source-root`, `--state`, `--env-file` and repeated `--compose` inputs. It binds
metadata to exact existing container IDs/images/birth times without deployment or
installation. `--dependencies-root` selects an explicit runtime-owned lockfile
installation when the source links `node_modules` to a separate install; the
historical default is the source root. Both package files must match the exact
source commit, and stock-client and source module resolution remain confined to
that installation. `--runtime-owner /absolute/fixture/owner.json` also binds a
canonical prepared fixture's project/owner labels, source and dependency paths,
image, lockfile and recorded generator provenance. Invocation working directories
are retained separately from installed module identity; module bytes and tools
must still match. Neither option installs dependencies or guesses a sibling root.
For an attached fixture, `down` stops instrument jobs only; runtime
cleanup remains with its owner. `preflight CELL --k6-image ID` checks the existing
production modules/private config, SQL/roles, process/cgroup/sampler readability
and k6 export interface before timed phases. Setup failures have separate retained
attempts and preserve the deployment. Repair/rebind source or resource changes;
never reuse old counters or resume into existing timed phase folders.

`run`, direct readiness collection and each sampler window claim their output
once with an exclusive attempt marker. Reusing a metadata directory refuses
before overwriting its summary, bookend or collector files and writes a unique
`attempt-refusals/<id>/refusal.json`. Use a new metadata-only attachment for a
retry on the same owned runtime; preserve the original attempt and its provenance.
Host commands default to this instrument's absolute root, and sampler commands
use the absolute fixture directory. Explicit source-command working directories
remain explicit. The sampler resolves its input paths before entering the first
Compose file's accessible directory; an unavailable context refuses.

## Source and ownership

`adapter.py prepare` creates a unique detached core worktree from a **full commit**,
archives the deployment's committed Compose tree over its deployment directory,
and writes the product build overlay marker. Every remaining core input must pass
the shipping build's two-source admission. There is no borrowed node_modules:
probe and source-helper dependencies use a separate owned install during preparation of the exact committed core package.json
and lockfile with npm ci --include=dev --omit=optional --ignore-scripts --force.
The serving image still prunes development dependencies. generator-provenance.json
pins host Node/npm paths, hashes and versions, manifests, client entry/version/hash;
actual stock-client resolution is checked before deployment traffic and each workload.
The controller must preserve that host toolchain across cells/profiles.
Preparation failures retain private prepare-commands/ raw stdout/stderr even before
owner.json exists; prepare-failure.json contains only a sanitized error code.
Generator installation output is private under generator-commands/.
The image's core/deployment labels and immutable image ID are checked. Serving
mounts cannot replace `/opt/app` or any subtree; all existing binding mounts must
resolve within this cell's own private state. External/shared resources refuse.
Ambient NS_/BENCH_/NODE_OPTIONS settings cannot silently alter the experiment.

Every cell has a random project nonce, private worktree/state, randomly selected
loopback port and ownership labels on its containers/networks/volumes. Cleanup
verifies ownership before removing only that project and its recorded worktree.
An ownership/source mismatch refuses rather than forcing cleanup. No attach mode
or foreign teardown command exists. Raw state/config contains synthetic credentials;
keep the entire work directory private and outside any checkout. Do not commit it.

Build, deploy and traffic require a source-matched frozen acceptance receipt:

```json
{"kind":"joined-acceptance","status":"UNMEASURED","pair":{"core":"FULL_COMMITTED_CORE_SHA","deploy":"FULL_COMMITTED_DEPLOY_SHA"},"evidenceSha256":"SHA256_OF_COORDINATOR_ACCEPTANCE_RECORD"}
```

The example deliberately refuses. The coordinator supplies `PASS` only after
acceptance; provisional source heads are never silently substituted. The receipt
is an attribution gate, not a new permission dialog. A build/initial deployment
also requires load below the chosen quiet threshold and **zero foreign running
containers**. During owned workload, foreign-container checks continue; the owned
workload's own load average is measured instead of rejecting its expected CPU.
Host inventories include container IDs/labels, image IDs, load, RAM, Docker/context,
kernel and process names/CPU/RSS, never command arguments/environments. Only local
Unix-socket Docker contexts are supported: host metrics must describe that daemon.

### Shared Compose namespace and epoch custody

`orchestration_binding.py` is the shared command boundary for existing-fixture
upgrades and resumes. It does not schedule a run or replace the existing finite
GO, host ownership, PID/birth checks or guard. Artifact stages import this source
module instead of copying a `COMPOSE` shell array. The tracked instrument inventory
requires this module. Remote source packs must retain the complete tracked
`tools/mt-bench/m7-joined/` prefix, including this module; a prefix import and
manifest digest check belong before any provider allocation.

The command factory requires the immutable project, raw frozen Compose `name`,
`NS_DEMO_PROJECT` and current owner record to agree. `adapter.compose` uses this
cheap check and the frozen file hashes on every call. It renders actual Compose
configuration only for container lifecycle mutations; private SQL and inspector
polls do not acquire a new Docker-config measurement cost. Missing anchors refuse;
there is no fallback to the owner record alone.

Before the first effect, the integration owner:

1. Uses `stamp_candidate` to add the single `org.nightscout.m7.attempt` nonce to
   **new** candidate declarations only. Historical fixture declarations and owner
   labels remain unchanged. A later resume can retain a prior attempt's labels
   as its recorded original epoch; it does not recreate resources to retag them.
2. Uses read-only `image_metadata` and `make_binding` to freeze original and
   candidate epochs, exact source/image identities, state roots, environment and
   Compose hashes. An absent/null Compose command is resolved from the exact
   pinned image's OCI command, not inferred from a running container. Preserve
   historical `configFiles` when original containers used another frozen path.
3. Writes a unique `begin_journal` with actual full inspected original IDs. Bind
   `binding['sha256']` and its attempt nonce into the existing root GO. The
   supplied `authorize` callback must revalidate that authority before effects.
4. Calls `checked_run` for Compose creation/replacement. It builds the only
   project/env/config prefix, checks actual expanded configuration, writes intent
   before effect, and records created IDs even when the command fails. No shell
   namespace override is accepted. Calls `checked_ids` for exact existing
   container start/restart/stop; these retain the recorded epoch's declaration.
5. Calls `cleanup_recorded` from the existing guard/finally path. It inspects
   recorded full IDs directly and validates each against its **own** epoch.
   Discovery admits only the current attempt label plus owner, project, source,
   config-file, creation and exact command/mount/environment proofs. Foreign or
   unknown IDs are refused while proven owned IDs still stop. A declaration,
   capture, log or journal-write failure is never authority for a broad project
   stop. Cleanup preserves volumes and does not read mutable project/env/config
   files; a metadata failure remains explicit even when owned stopping succeeds.

Use the new journal API for an upgrade/resume integration; do not fall back to a
project-wide `down` or reinterpret old containers using new candidate declarations.
The focused `test_orchestration_binding.py` controls exercise wrong project,
source, owner, state mount, missing/swapped attempt, original/candidate epoch,
failed capture/stdout/journal persistence and foreign-ID refusal before effects.
All mutation calls in those controls are injected. Actual stopped-fixture
qualification uses only `ps`, `inspect`, image inspection and `compose config`.

## JWT setup concurrency

Local preparation, attachment and campaign commands accept
`--jwt-setup-concurrency 1..64`, with serial default 1. The cell owner manifest
and campaign record retain `jwtSetupConcurrency`; campaign resume refuses a
changed selection. Both local k6 launch paths forward that value explicitly.
The generated M7 workload preserves offered arrival rates, current nominal
arrival timestamps, scenario attempt/response/transport counters, status
fingerprinting and bounded setup-refusal evidence.

Setup uses one response hook for serial requests and bounded batches. Refusal
`tenantIndex` and `requestOrdinal` follow tenant roster order; they do not assert
network dispatch order within a batch. Start and finish timestamps bound the
chunk dispatch and subsequent response processing. Serial default retains a
single-request bound. Batched refusal discovery can follow other exchanges in
the same chunk. These observations do not measure per-response wire latency.
Select a changed concurrency only when preparing a new coordinator-adopted run.

## Commands after the handoff

Run from the alignment checkout containing the committed instrument:

```bash
python3 tools/mt-bench/m7-joined/adapter.py prepare \
  --directory /absolute/private/m7-cell \
  --core-repo /absolute/core-repository --core-commit FULL_CORE_SHA \
  --deploy-repo /absolute/deploy-repository --deploy-commit FULL_DEPLOY_SHA \
  --image ns-m7:paired-image --freeze /absolute/private/frozen-acceptance.json \
  --tenants 1000 --replicas 1
python3 tools/mt-bench/m7-joined/adapter.py build /absolute/private/m7-cell
python3 tools/mt-bench/m7-joined/adapter.py deploy /absolute/private/m7-cell
python3 tools/mt-bench/m7-joined/adapter.py run /absolute/private/m7-cell --k6-image PINNED_OR_LOCALLY_RESOLVED_K6_IMAGE
python3 tools/mt-bench/m7-joined/adapter.py down /absolute/private/m7-cell
```

`build` is unnecessary when the matching image already exists. Docker's resolved
k6 image ID is recorded and used for execution. No floating tag runs after pinning.
`prepare` stages local source/TLS/config and installs the owned lockfile dependencies before source helpers execute; it sends no performance traffic.
It accepts explicit diagnostic seed counts1..10000; campaign ladders constrain
the performance steps. Binding preparation must expose committed
`primer provision`/`primer prime`, and either private `primer/tenants.json` or
`ops/tenants.json` with exact `{version:1,tenants:[{id,host,dataToken,...}]}`.
Conflicting outputs, legacy `token` fields or missing tokens refuse. Provisioning
uses the private admin API; restore commissioning precedes API priming, and a
private local publisher completes custody before remaining roles start. Seeding
uses DATA APIs. There is no direct tenant-row
or Vault seeding in the campaign adapter.

`campaign.py pilot` supplies a distinct500→750→1000 remote pilot. See
[the remote controller seam](REMOTE-SEAM.md) for host prerequisites, cost ownership,
commands, stage order, verdicts and artifacts. The controller enforces its current maintainer-authorized spending/deadline policy;
this adapter performs no cloud action.

`campaign.py all` accepts the same source/image/freeze arguments plus `--work` and
`--k6-image`. It measures 1 API at 1,000 → 3,000 → 5,000 → 10,000, then 2 and 4 APIs
at those counts on the **same frozen pair and image**. Every failed correctness or
instrument gate stops growth. `campaign.py ladder --replicas 1` (then2, then4)
provides separate explicit ladders in the same `--work` ledger. A measured profile
ceiling stays FAIL; the coordinator may start the next profile at1,000 after a
source/instrument/host-matched `measured-profile-ceiling` receipt links the failure
artifact and diagnosis hashes. Any stored-oracle, authority/refusal or functional
failure sets a global block: a ceiling receipt cannot override it. It never automatically starts anyway on a busy
host. `check-campaign` refuses missing count/replica rows, mixed source/instrument/
image identities and unmeasured cells. Realtime worker placement remains the
product binding's selected topology; the API-replica matrix is not a claim that
all possible realtime placements or automatic takeover were measured.

## Instrument

The source manifest hashes every adapter file and every reused tracked instrument.
The existing `capacity/k6/workload.js` supplies seven client shapes: CGM
entry and Loop devicestatus uploaders, AAPS-style v3 treatments, and follower
entry/devicestatus/treatment/status reads. The generated workload records two explicit adaptations: current deterministic
nominal-arrival timestamps replace prior day-old timestamps (which could suppress
current frame changes), and read4xx responses increment a functional refusal
counter. Payloads and client route shapes are reused. Default cadence is real (one CGM cycle
per 300 seconds), hot tenant factor10. Default idle600s/load900s. Two stock-browser
polling sockets per tenant use JWT exchange and preserve stock reconnect behavior;
retry-flood results are labelled separately. All sockets must prime before load.

The capacity socket probe is generated from its tracked source with explicit,
anchor-checked adaptations (and both hashes retained): actual replica-service
restart roster, hot/cold write-to-frame distributions, strict initial priming, and
sparse private runtime acquisition inspection replacing the prior lifecycle-lease
proxy. New runtime `ready && cycles>0` confirms acquisition in the restarted
process; it is **not clinical equivalence**. Write stamp→durable evaluator checkpoint
latency remains an independent per-write SQL observation with about1s resolution.
Missing/oversized inspection fails as NO-INSTRUMENT, never falls back to leases.

Inspection cadence is15s; payload byte totals, call counts and wall time are saved.
Per-role Docker CPU/memory, process RSS snapshots, cgroup CPU/anon/memory.current,
PG statement counts/time and waits/locks are retained. A60s sampler-disabled idle
window precedes the600s sampled idle window; per-minute rates and collection costs
let the reviewer assess observer overhead. Two-second sampler/controller and host
probe CPU/RSS are recorded. Load samples are bounded by load timestamps; reconnect
samples remain separate raw observations. Cgroup usage/anon and process RSS are
named separately; no figure is described as JavaScript heap or hard process bound.
`pg_stat_statements` lives only in the maintenance database to preserve application
operation-window admission. No diagnostic extension enters the application DB.

The same sampler also records `host-io-metadata.json` and `host-io.jsonl` without
additional SQL. The small host observer samples at the selected interval (2s by
default), independently of blocking Docker stats, with wall and monotonic read
brackets. It retains aggregate CPU/iowait ticks, IO PSI some/full averages and
totals, and raw disk counters for sysfs-identified physical leaves. Metadata gives
device names/major-minor/sysfs paths, units and source documentation. Missing or
changed sources are `NO-INSTRUMENT`, never zero. Match these timestamped samples
to the actual cost-window bookends; do not claim simultaneous reads.

These are shared host/device counters. Kernel disk request-time sums are not
application or PostgreSQL latency, and device activity does not identify its
cause. Guest-visible leaves do not establish backing physical media. No counter
deltas, IO cause or capacity threshold is inferred by the collector. Counter
reset, iowait decrease and hotplug limitations remain explicit in its metadata.

## Oracle and controls

Client acknowledgements are compared with independent superuser SQL stored counts
per tenant and domain/run marker. The oracle does not call the API. Empty workloads,
unknown tenants or missing accepted totals cannot be green. Uncertain writes are
reported and refuse a capacity pass. The adapter alters one owned synthetic stored
row, requires RED, restores it in `finally`, and requires GREEN. A summary cannot
claim a passing cell without complete metrics, primed/delivered/recovered sockets,
observed runtime acquisition and the oracle control. No latency or CPU capacity
threshold is invented; report those distributions and marginal costs as measured.

Focused preparation only:

```bash
python3 tools/mt-bench/m7-joined/test_contract.py -v
python3 tools/mt-bench/m7-joined/smoke.py /new/private/smoke-output
```

The smoke owns one tiny PostgreSQL fixture and six synthetic HTTP accepted writes
using the tracked payload functions under deterministic mocks. It proves the
independent SQL oracle/control wiring, **not** k6 scheduling, product authorization,
clinical behavior, full deployment, stock sockets or capacity. These remain
UNMEASURED until the coordinator runs the frozen adapter on a quiet host.

The restart observer rejects command failure or an unchanged container StartedAt;
its own PG smoke control skips a restart, requires refusal, then actually restarts
and observes a new process. Sharded placement additionally requires its committed
controlled-replacement binding helper; raw restart is refused until that seam exists.

## Successful evaluator completion observer

Profile-selection version3 pins the unchanged strict `evaluatorProgress` policy and
the separate `evaluatorIdleSafety` policy in capabilities.json version4.
The source must expose evaluator-inspection module v2 before preparation. Selectors
contain at most128 unique synthetic UUIDs. One read-only process per exact evaluator
instance pages ALL configured synthetic IDs, including foreign rows; no hash-based
query prefilter hides duplicate evaluation. Inspection invokes no clinical work.

The existing enabled-idle phase starts before either k6 or the socket/write probe:
its body only sleeps for the unchanged120s pilot/600s capacity interval. It is the
no-clinical-write idle observation. All tenants still receive the original load phase;
there is no additional cold cohort, plugin change, HTTP request, or deadline SLO.
The historical strict idle checker still requires successful time-only completion
for every owner. Current baseline idle instead uses a separate idle-safety result:
actual observed due opportunities require later successful time progression; a
healthy already-acquired owner with stable authority, no error or clinical job,
and no captured due within the complete observation may report
TIME_NOT_EXERCISED/zero completions. Explicit current null due with complete
clinical-job metadata is NO_TIMER_DECLARED; historical/missing state is UNKNOWN.
A later future due never erases an earlier observed opportunity. Any acquisition
delta during idle is new demand and refuses. Load still requires successful work
progression. Legacy `cycles` and evaluation age cannot satisfy
this check. Missing opportunity cannot manufacture a work witness. Error, ownership, runtime or lifecycle
generation changes refuse. Input/output revisions may advance normally. Every ID
must have exactly one admitted ready owner; foreign counters must remain unchanged
from their explicitly retained phase baseline. Hidden recovered errors refuse.

Three bookend/midpoint snapshots use at most4 instances,10000 IDs,1024 private
requests and64MiB response bytes per phase. Each request retains the existing
server caps and uses a conservative1MiB client cap,128 selected rows and5s timeout.
Private raw and deterministic-gzip artifacts retain compact complete rows and
source/image/instrument/profile attribution. Partial body failures preserve collected
evidence before propagating the original failure. Query/response/wall overhead and
serialization/gzip/primary-file publication CPU/wall costs are recorded separately.

Recovery is a separate scope: a bounded pre-restart runtime baseline, then the
existing900s/15s cadence. Every exact evaluator must have a different runtime ID,
at least one successful fresh owned acquisition, two stable coverage/counter
observations, and no failure/foreign progress. Its private recovery artifact is
separate from capacity-phase progression. Missing/error/stale-worker receipts cannot
pass. The restart helper still independently proves actual container starts.
Neither observer proves clinical output equivalence or native transport by itself.

Focused component controls can use a NEW owned exact product source:

```bash
M7_PROGRESS_CORE=/absolute/owned/core python3 -m unittest discover \
  -s tools/mt-bench/m7-joined -p test_evaluator_progress.py
```

This uses actual runtime/window/inspection with a recording SQL port and synthetic
component. Native product scheduling/durability and final paired-image transport
remain separately required. An omitted source fixture is explicitly skipped.

Due-observation completeness uses capabilities3, observation contract2 and explicit
`evaluator-progress-phase-v2` / `evaluator-recovery-v2` artifacts. Compact tuples
now retain dueAt/dueReason for EVERY owner/foreign row; safe finite fractional
numbers are preserved without rounding. Missing/malformed current fields refuse
rather than becoming null. Preparing a new cell requires these fields in its
exact source's private-v2 response schema, and its image/client must use that
source. An older strict private-v2 client refuses the added response fields;
there is no mixed-source compatibility claim.

This changes observation retention, not the progress predicate, deadline, cadence,
threshold, query/decompression budget or clinical claim. No future/past due value
is automatically interpreted as sufficient opportunity or a passed phase. Historical
phase/recovery v1 artifacts retain their original policy/version/columns and can
be decoded/verified as historical records. Missing old due fields stay UNKNOWN
(absent), distinct from an observed null/no timer. Current cell receipts require
v2 artifacts and cannot downgrade to an old unknown-due shape. The actual historical
195c PASS and repaired cd462 UNMEASURED captures are tested read-only and unchanged.


### Baseline idle-safety boundary

Current idle assessor module4 produces `evaluator-idle-safety-v2`. It retains
three complete ID/instance snapshots and common wall-minus-monotonic clock
brackets. Missing state, clock jumps and ambiguous observations remain refused.
Strict work/source inspection remain module2; old idle artifacts retain their
original module's outcome and cannot serve as current receipts.

First and midpoint observations still require every clinical job flag clear.
Only an original FINAL exact running-bit owner with a prior declared TIME
opportunity may create a completion obligation. The final legacy-body increase
must exceed the measured TIME increase by exactly one; all original readiness,
identity, generation, acquisition, failure, foreign-row and clock guards remain.
A running flag or null due is never completion evidence.

After successful original AFTER cost snapshots, the adapter may make ONE point
inspection round over at most128 obligated IDs on every fixed evaluator instance.
All RPCs share one monotonic5-second deadline and the existing phase query/byte
budgets; there is no retry. The selected owner must gain exactly one completed
TIME, retain its final legacy-body/acquisition counts and owner/runtime/generation,
show no failure, and have all jobs clear. Selected nonowners remain unchanged and
idle. Missing, still-running, reset, extra-body/acquisition or final-only demand
stays refused. No earlier busy observation is excused.

The artifact retains the original three global rounds plus a separate point-tail
round and cost/clock metadata. Original measured TIME counts and resource windows
never include the tail completion. The new classification
`TIME_COMPLETED_AFTER_WINDOW` is not throughput or a native work witness. Unselected
tenants are covered only by the original global snapshots; no global tail or
continuous quiescence claim follows. AFTER-snapshot or tail failure preserves
partial evidence and cannot yield PASS. The external app helper uses this same
adapter boundary and policy.

The private DTO exposes six existing clinical states: running (through complete
window resolution), booting, owned acquire/time and borrowed acquire/time tickets.
The new compact artifact encodes these in that order as a validated integer
bitmask0..63; bool, missing, extra or malformed state refuses. Named source DTO
booleans remain exact. Full owner/foreign rows and original byte/query/gzip budgets
are retained. Old strict phase/recovery v1/v2 artifacts keep their original checker
semantics; current idle receipts cannot downgrade to them.

An idle-safety PASS always declares `timeWitness:false`, including when actual time
progress is observed. Capacity support separately requires a coordinator-pinned
exact-source native successful-TIME witness, recomputed with the unchanged strict
v2 checker. Quiet baseline capacity never establishes active-alarm capacity. Load
and changed-runtime recovery remain strict. A future due or explicit null cannot
excuse an earlier observed opportunity without later completed time work.

Readiness collection permits one first-admission transition only when warming:
a valid admitted, ready, error-free owner with all successful and failed
completion counters zero may have an explicitly present null completion age
while its first operation-window release is pending. This remains WARMING with
no credited acquisition. Nonwarming collection, missing age, nonzero counters
with null age, errors and progress requirements remain strict. Per-row contract
refusals also retain one private `failedRow` projection in the existing diagnostic:
tenant/service/runtime identity, admitted/ready/code/alert, whitelisted progress
counters and due fields. It is capped at4096 bytes; strings over64 characters are
explicitly truncated. Bounded scalar values stay visible; unsupported structures
and nonfinite or oversized numbers use type tags. Clinical output and arbitrary
RPC fields are excluded. This adds no request, retry or
acceptance change; the original failed predicate remains a refusal. Fixed
predicate/field names and bounded positional indices accompany the projection.
Readiness deadlines, polling cadence,
workload and native TIME proof requirements are unchanged.

Idle assessor module3 accepts already observed successful TIME work after each
first/midpoint opportunity even when its due time falls inside the final fetch
bracket. It still refuses final-only demand and any opportunity without later
credited work; a later future/null due cannot erase an earlier opportunity.
This is not a deadline claim. Policy/wire row schema remains version1, while
`evaluatorIdleSafety.moduleVersion=3` explicitly pins this assessor; the source
inspection/strict-work protocol remains version2. Historical module2 records
retain their original policy/result and do not silently become current proofs.

Enabled idle attempts its existing AFTER cgroup/PostgreSQL bookend in `finally`,
including observer refusal. PASS still has only the original BEFORE/AFTER pair.
If AFTER also refuses, a bounded fixed diagnostic records actual partial-file
availability and the original phase exception is preserved. Missing bookends
are never fabricated, and an AFTER failure without a phase failure still fails
the run. No sampling window, query set, workload or retry policy is expanded.

### SQL snapshot request bounds

The existing role totals and statement-list queries are unchanged. Each existing
psql invocation now records adjacent host wall/monotonic start and finish values
in `before-sql-snapshot-timing.json` / `after-sql-snapshot-timing.json`, including
fixed status on failure. No extra query or polling is added. These are request
brackets, not exact SQL execution instants. `sql_counter_rate_bounds` requires
successful, nonoverlapping same-domain monotonic bounds and a nonnegative counter
delta; it returns a range from the shortest/longest possible elapsed interval.
Missing old timings remain unmeasured. Nominal120seconds or nearby cgroup times
cannot substitute for SQL timestamps. SQL execution time remains distinct from
database-role CPU; wall stamps support correlation, not a cross-host clock claim.


### Discovery runs

`prepare --run-purpose discovery` freezes an explicit observational route;
`acceptance` remains the default. Discovery preserves raw strict idle/work
verdicts, including UNMEASURED and failed work-completion counters, and executes
the existing bounded HTTP load despite incomplete socket priming. Missing
`.window` stops/drains the owned probe before HTTP load; it does not manufacture
a restart or probe-count proof. The original workload, deadlines and cadence
are retained. Failed HTTP requests, dropped iterations, dark sockets and
recovery timeouts are outcomes rather than performance SLOs.

`check-discovery <summary.json>` accepts only the explicit discovery cell or
aggregate shape, matching source/image/profile/ownership identity and no known
hard safety violation. Status MEASURED means complete observations; PARTIAL
retains absent measurements. Both carry `capacityAcceptance: NOT_GRANTED` and
cannot pass `check-pilot` or `check-campaign`. Known wrong stored counts,
foreign/source/reset/custody violations, invalid settings fingerprints and
explicit unsafe output remain refusals. A failed evaluator completion counter
alone is preserved as a FAIL finding, not classified as unsafe clinical output.

The independent count oracle retains ACK <= stored <= ACK + uncertain. Missing
ack metadata is UNMEASURED, never zero; known per-tenant/domain bounds and
foreign scope still refuse even with other fields missing. Probe counts are
separately UNMEASURED when fanout metadata is absent. Raw process exits,
probe partials, strict progress artifacts and existing AFTER bookends are
retained on failure. A timed-out k6 CLI requires an exact owned-container stop
before recovery. No observation route grants functional or capacity acceptance.

Recording controls: `python3 -m unittest discover -s tools/mt-bench/m7-joined -p
 test_discovery.py` (join the command on one line). The optional
`discovery-transport-control.py --repo <transport> --commit <full commit>` tests
the actual Record producer against an immutable transport validator without
executing commands, applications or networks.


Discovery classification is explicit. Missing final-tail opportunity is retained
as UNMEASURED and does not suppress load. A missing midpoint may continue only
with a current-source, correctly attributed, fixed-phase 1/2-round artifact;
its available owner/foreign/reset/selector/budget invariants still apply (and
idle clock brackets, when present in that source schema). Zero/extra rounds,
wrong phase/source and unknown or malformed observations refuse. This validates
available observations only: it creates no missing round or completed-work
credit. The two previously declared work-error findings remain soft even with
FAIL; timing-code FAIL and all structural/source/owner/clock failures stay hard.

Discovery probe counts use the separately versioned `probe-accounting.json`
ledger (v2). Each attempt is persisted before HTTP; each tenant retains accepted
(200), uncertain (status 0 or 5xx), definitely refused, and pending counts.
Admission closes before awaiting all writers. A complete proof requires that
closure and zero pending attempts; interruption/open admission remains
UNMEASURED. No pending write is silently converted to zero. The frozen helper is
copied and hash-checked with the generated probe, and bounds the roster to 10,000
and attempts to 100,000. Partial ledger snapshots add host file I/O per probe
attempt/completion; they add no HTTP or SQL requests.

Discovery checks `accepted <= stored <= accepted + uncertain` independently for
each tenant's probe actor, alongside the existing workload/domain and tenant
scope checks. Another tenant's uncertainty grants no allowance. A definite
refusal grants none. Legacy ACK-only metadata cannot establish an upper bound:
missing acknowledged rows still refuse, while missing uncertainty remains
probe-specific UNMEASURED. Original historical failures are unchanged.

`stored-counts.json`, `oracle-findings.json` and bounded failure diagnostics are
retained before a known violation throws. The existing resource reducer reads
already captured files even on that refusal; it adds no queries. Wrong roster,
run identity, negative/mismatched attempt totals or ACK disagreement refuse
before the count SQL. Strict acceptance retains its original exact probe oracle.
Focused controls: `PYTHONPATH=tools/mt-bench/m7-joined python3 -m unittest
 test_probe_counts test_discovery test_discovery_classification` (one line).
The loopback control starts one finite local HTTP server with in-memory
synthetic persistence, exercises actual generated request/callback code for
committed 503 and delayed-response timeout, and closes all its sockets. It proves
accounting behavior, not PostgreSQL or application correctness.

Discovery reads counter `count` fields explicitly (flat or nested `values`).
Absent fields remain UNMEASURED, including a present empty object; they never
become zero. Present malformed, boolean, negative, fractional or nonfinite
counts refuse before the existing count query. Finite integral numeric counts
within JavaScript's safe integer range are preserved. The acceptance metric
helper is unchanged.


### Source-bound completion readers

New `pgstream-sample` preparations and attachments select
`--completion-contract evaluator-work-v1` for the legacy JSON work state or
`--completion-contract evaluator-work-v2` for typed work state. The selection
is stored in the owner manifest. Sample preflight binds it to the exact core,
deploy, image and instrument identities. It does not infer a version from a
missing column or fall back after a query failure. Existing captures remain
unchanged and require their original instrument to resume.

The v2 witness reads work arrays and output metadata columns with the clinical
JSON body in one SELECT snapshot. Versions are decimal strings, including array
elements. NULL means a source version is missing. The fixed array order is
clock, settings, policy, activity, lifecycle, bootstrap. Its assessor checks row
kind, work version, contract digest, array bounds/order, exact bigint range,
output revision precision and metadata ownership before the existing stored
write, BG-now and stock-client frame checks. It performs no duplicate writes.

Focused offline controls (no SQL/runtime execution):

```bash
node tools/mt-bench/m7-joined/completed-oracle-control.cjs
node tools/mt-bench/m7-joined/completed-oracle-v2-control.cjs
cd tools/mt-bench/m7-joined
python3 -B -m unittest test_cost_companion test_realtime_costs test_pgstream_sample
```

SQL shape controls and synthetic rows do not qualify the generated SELECT on
PostgreSQL. The runtime owner must qualify it against each paired fresh fixture
before timing. Missing source-specific realtime counters remain NO-INSTRUMENT.
The legacy statement TSV query and clinical witness scope are unchanged.

### Bounded commissioning on a fresh capacity point

`prepare --primer-concurrency N` records a worker bound from 1 to 32. Default 1
keeps the serial primer command. A larger bound adds `--concurrency N` only to
the commissioning phase; stage timeouts, API sequence and worker startup order
stay the same. The selected deployment and qualified image must contain the
bounded primer. Never copy a newer primer into an accepted image or change the
instrument of an existing attachment.

Use a fresh point with its full selected seed. Extending `provisioned.json` and
`tenants.json` alone does not revise the seed, settings fingerprint or published
operator roster. A resumed fixture and a cold commissioning run have different
setup costs.

For concurrent commissioning, deployment records `primer-start.json` and reads
`primer-counts.private.json` before starting the remaining roles. The latter
checks the exact seed, provisioned and accepted custody rosters, completion and
uncertainty state, then independently counts synthetic commissioning entries in
PostgreSQL. Each selected tenant must have exactly one entry. Accepted custody
means a successful HTTP response saved by the primer, not an HTTP attempt count.
The count query and raw per-tenant output stay in the private run workspace.
Call `adapter.primer_counts(fixture, owner)` after the prime phase when using the
existing canonical command packet instead of `adapter deploy`.

Focused file/SQL-shape controls run without a database:

```bash
cd tools/mt-bench/m7-joined
python3 -B -m unittest test_primer_adoption test_contract
```

These controls cover count assessment and command wiring. Live database execution
and speedup at bounds 2 or 4 remain measurements for the next qualified point.

For a rate curve on one qualified cohort, `prepare` or a new `attach` may select
`--offered-rps 120` in `pgstream-sample` discovery mode. This changes the shared
arrival cycle for the same seven request shapes and tenant weighting; it does
not change stock-client count, payloads, credentials, authority or write oracles.
Write timestamps follow the selected arrival cycle. Ordinary cadence remains
the default. The owner and discovery result retain the requested rate and the
effective rate after millisecond rounding.

`scenario_request_attempts` counts entry into the load HTTP call;
`scenario_http_responses` counts returned HTTP responses;
`scenario_transport_failures` counts calls returning without an HTTP status.
An attempt does not establish a server receipt or a successful write. Credential
exchanges in setup and stock-client probes remain separate from this scenario
target. Keep accepted/persisted writes and evaluator/client witnesses separate.
Raw k6 `iterations` and `dropped_iterations` remain distinct; a metric absent
from the capture stays unmeasured.


### Receipt-selected serial exchange diagnostic

`prepare` and `attach` accept `--serial-exchange-diagnostic` only for a3000-tenant
`pgstream-sample` discovery. The genuine `AUTHORIZED_DIAGNOSTIC` receipt and owner
manifest must both contain exactly:

```json
{"serialExchangeDiagnostic":{"tenants":64,"phaseSeconds":120,"requestSeconds":60}}
```

The existing `run` entry point keeps canonical readiness, warmup and strict idle.
It then uses one Node actor and one fixed HTTP-agent configuration to exchange the
same first64 ordered tenant records before and after the original16-worker JWT
setup and two-per-tenant stock polling priming. Each phase has a120second budget,
each request a60second maximum, and the first non200 stops that phase without
retry. A BEFORE refusal skips stock setup. An AFTER refusal retains the priming
result. Stock setup retains safe aggregate attempt, retry, HTTP-status and transport
counts while keeping its original16 workers and retry behavior. Both serial phases
return diagnostic evidence and close every stock socket and agent.

This route never releases `.window`, sends a probe write, starts k6 or records an
ordinary310second measurement. The summary remains `PARTIAL`, with
`diagnosticOnly:true` and `ordinaryTraffic:NOT_RUN`. The ordinary route and its
default generated probe bytes are unchanged when the flag is absent.

`load/binding.private.json` binds the actual owner/source/image/instrument,
ordered credential file, actor bytes and Node executable hashes. Both phases
recheck those inputs. `load/exchange-phases/{before,after}.json` contains bounded
status, allowlisted error class, tenant index/hash, clock and elapsed observations;
it contains no returned JWT, credential, raw response body or request URL. Existing
owned-process/job sampling stays at `load/probe-job.json` and `load/loadgen.jsonl`.
The selected probe wait is bounded900seconds and remains subject to integration's
shorter finite deadline; a600second external sampler does not prove coverage of a
longer diagnostic. No PostgreSQL statistics reset is added between the paired phases.
The unchanged clinical, source, image, ownership and process guards remain in force.

Bound oneoff launches use `make_binding(..., oneoff_root=..., oneoff_images={'k6': pinned_id})`
and `checked_oneoff(binding, kind, argv, scope, runner, authorize, journal_file)`.
The only kinds are `k6-version`, `k6-help` and `k6-load`. `argv` is the existing
source-generated Docker command. `scope` contains `directory`, attachment `owner`
and pinned `imageId`. The helper verifies the attachment/project, binds the exact
command, image defaults, mount and environment layout, prewrites intent, then adds
the attempt label and exclusive CID file. The optional `oneoff` callback passed to
`sample_preflight` or `run` covers only these explicit launch sites; it does not
intercept reads or change generated scripts. Its `stop()` uses `checked_ids` for
recorded oneoff IDs. Journal cleanup also recovers attempt-qualified live IDs when
CLI output or capture failed; completed `--rm` absence is allowed.

Remote producer command suffixes use immutable named stages:
`make_binding(..., run_stages={name: {'epoch': epoch, 'argv': source_tail,
'sourceFile': producer_path}})`. The source tail starts with
`--profile ops run`, includes one declared role, and uses the existing bounded run
options. The producer file hash, exact suffix and semantic command layout are
sealed. Pass `stage=name`, matching `epoch`, `roles` and `options` to
`compose_argv` or `checked_run`. Unknown stages, changed source/options/roles and
namespace overrides refuse before effects. A default service command has no
suffix. These APIs retain the caller's finite authorization and PID guard.

### Clinical sender and early-request diagnostic (source qualified)

The clinical completion criterion remains open. This instrument separates the
actual maintained Go notifier's message admission/handoff, each HTTP attempt,
Node's first request-handler entry and later selected-row parsing. It is source
instrumentation, not a product optimization or a capacity result. No native run,
image or resource slot is selected by this implementation.

`--clinical-intake-timeline two-target-intake-timeline-raw-v2` explicitly adds a
separate Node metadata ledger. The existing `off` default and v1 selection remain.
The ledger writes before calling the original handler, then records request
abort/close and response finish/close even when parsing never identifies a row.
A later record joins the local request ID to the selected trace; it never rewrites
the original timestamp. Instance ID plus PID and local request ID prevent a join
across process starts. Validated LSNs, numeric connection/port metadata and fixed
lifecycle fields are retained; bodies, URLs, authorization and arbitrary strings
are excluded. The handler still receives the original `this` and arguments and
returns its original promise or exception. Passive lifecycle listeners add no
body consumer, scheduler work, admission or ACK.

Raw bounds are 32,768 rows, 8 MiB and 128 pending writes, separate from the existing
4,096-row/2 MiB selected trace. Saturation, short writes, pending drain, missing
status or an entry without an abort/response terminal record is UNMEASURED.
Retention verifies the record count, byte count, sequence, instance/PID, permitted
fields and lifecycle coverage. Status fields are mandatory with exact types and
ranges; missing counters and falsey substitutes never mean zero. Each raw phase
has an exact field schema, typed lifecycle flags, bounded numeric connection/port
fields and consistent request identity. Response finish requires `finished:true`;
response close with `finished:false` and explicit abort remain valid capture
observations. A request-close alone is not a response terminal. Selected capture
counts and its optional seal also match the retained bytes. COMPLETE here describes metadata capture; it does
not prove target delivery or clinical completion. Node entry is a JavaScript
handler boundary, not socket or kernel arrival. Malformed selected-row inspection
forwards to the actual receiver's validation and preserves its rejection.

`clinical-sender-trace.patch` is an experimental patch against the retained
maintained v1.6.0 source archive, bound by `clinical-sender-source.json`. Original
archive, go.mod and go.sum bytes stay unchanged. It instruments the actual
notifier rather than introducing a proxy or substitute sender. It is disabled
unless `NS_M7_CLINICAL_SENDER_TIMELINE=1`. That explicit mode reads two IDs and an explicit `clockSchema` at
`/run/ns-intake-timeline/targets.json` and creates private, exclusive output under
`/run/ns-ipc/clinical-sender-{timeline.jsonl,status.json}`. Deployment mounts and a
replacement binary are **not** installed by the Node selector. Its sender target
file is a separate role mount: the next packet must bind `clockSchema` to the
actual selected receiver route, with no default namespace fallback. Node target
inspection uses the original receiver clock routes.

Go records message-ready after serialization and before queue-byte admission;
fast admission or blocking Acquire enter/return/refusal; unbuffered handoff-wait;
consumer receive; and per-attempt client.Do call/return plus passive httptrace
connection, request-write and first-response-byte callbacks. Byte reservation
continues through delivery and checkpoint. Consumer receipt is the dequeue
observation; producer resumption after channel send is not an ordered substitute.
The emitter has a process-instance nonce, PID, message and attempt IDs, two fixed
selected tenant-clock rows, role enums and a 4,096-row/2 MiB synchronous write cap.
Its observation writes add cost. Existing request bytes, headers, context,
deadline, transport, retries, queueing, checkpoint and errors remain in use.
Zero/shared LSNs do not authorize a target join; unsubscribed events are not target
deliveries. Data LSN and commit position are separate. Missing message-ready leaves
subscription lookup, serialization and upstream WAL timing unknown.

Go status is `CAPTURED_REQUIRES_STRUCTURAL_CHECK`, never an automatic clinical pass.
Drops, writer errors and unsupported bindings are UNMEASURED. A future native
packet must verify per-message/attempt phases and connection joins, including late
callbacks and aborted/unparsed attempts. LSN equality alone cannot identify a
retry or destination. Missing or ambiguous joins remain UNMEASURED. Go elapsed
nanoseconds are source-local; they cannot be subtracted from Node hrtime. A future
run needs measured wall/monotonic alignment and qualified primary process births.

Minimal independent source review uses a fresh owned extraction of the archive
whose SHA256 is in the manifest, and the explicitly verified Go 1.26.7 executable.
Check the original file digests and unchanged go.mod/go.sum before applying:

```bash
# From the verified fresh source root; CLINICAL_PATCH is an absolute path.
patch --batch --fuzz=0 -p1 --input "$CLINICAL_PATCH"
export GOTOOLCHAIN=local GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org
export GOPRIVATE= GONOPROXY= GONOSUMDB=
# Use owned GOMODCACHE/GOCACHE directories; retrieve only pinned public modules.
"$CLINICAL_GO" test -mod=readonly -count=1 -timeout=30s ./pkg/wal/processor/webhook/notifier
"$CLINICAL_GO" test -mod=readonly -race -count=1 -timeout=30s ./pkg/wal/processor/webhook/notifier
```

Focused Node/Python controls, from the alignment root:

```bash
node tools/mt-bench/m7-joined/clinical-intake-raw.test.cjs "$CLINICAL_CORE"
node tools/mt-bench/m7-joined/clinical-intake-timeline.test.cjs "$CLINICAL_CORE"
node tools/mt-bench/m7-joined/clinical-timeline-startup.test.cjs "$CLINICAL_PAIRED_SOURCE"
PYTHONPATH=tools/mt-bench/m7-joined python3 -B -m unittest test_clinical_timeline test_probe_counts test_discovery test_pgstream_sample test_runner -q
```

The startup control needs the actual application archive plus its exact deployment
overlay and matching dependency lock; it intercepts CLI execution before services.
A bare application worktree has no deployment entrypoint. Controls plant missing
or late hooks, lost attempt identity, saturation suppression and changed request
bytes, then restore the source. Original promises, `this`, exceptions, timer
handles, module descriptors/lazy loading, per-request admission, ACK order and
malformed/aborted coverage are checked with actual receiver/notifier code and
synthetic clients/streams. They do not prove native socket delivery.

A future twin CLI build, if selected, requires two fresh extractions of the same
archive, patching only the instrumented tree. Build both with the same checked
Go executable, unchanged module sums, environment and dependencies; for example
`CGO_ENABLED=0 "$CLINICAL_GO" build -mod=readonly -trimpath -buildvcs=false -o "$CLINICAL_OUTPUT" .`
in each tree. Retain source/patch/toolchain/build-command/binary digests and test
both; do not infer equivalence to the shipping f9 binary. Only the notifier-focused
package/test executable is qualified here. Twin CLI builds, private mounts,
replacement binary deployment and native timing remain UNMEASURED and require the
root coordinator's next finite boundary.
