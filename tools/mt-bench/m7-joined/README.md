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
roster omit the retired legacy feed-reader. The default colocated topology runs
pgstream inside evaluator; explicit `external-service-v1` keeps a separate native
producer service. Record the actual selected topology in comparisons.

Source helpers resolve only the cell-owned lockfile dependency tree; evaluator
and realtime image processes independently check `/opt/app` pg resolution before
load. Per-process CPU-counter bookends and RSS distinguish evaluator Node from its
pgstream child; process replacement/missing data is UNMEASURED.
`sql-attribution.json` uses full private statement bookends for disjoint SQL-role
buckets. A native recovery connection may use the configured pgstream role on
the evaluator database. That role has a separate `shared` bucket, counted once;
the exclusive pgstream bucket and the split between processes are UNMEASURED.
The observer checks the selected recovery environment and database endpoint,
rejects other overlapping identities, and retains actual per-role SQL totals.
Historical disjoint-role captures retain their original two-bucket shape.
The frozen PostgreSQL command preloads pg_stat_statements, enables top-level
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

The current evaluator is a stream-fed bounded clinical materializer. Accepted
input, completed clinical coverage and delivered client output are separate
positions. A transport ACK requires durable acceptance; acquisition alone does
not prove clinical completion. Current tenant/owner/restore authority, coherent
transaction cohorts and subscribed raw mutation delivery remain required.
Realtime consumes completed clinical output, while the raw mutation tail remains
independent of bounded clinical membership. Bootstrap, cache loss, stream gaps
and missing history may read SQL.

Private inspection samples owner and foreign rows throughout ordinary traffic and at
the end of drain. Runtime IDs, owner placement, counter rewinds, evaluator health and
foreign work remain checked. The acceptance observer reconciles per-input acknowledgements
against durable output and stored-write counts. Idle tenants owe no work.
[Run and gate configuration](RUNNER.md#outcome-evaluator-gate)

Restart recovery remains a separate bounded observation of changed process IDs
and successful fresh acquisition. It does not establish clinical recovery by
itself. The existing local under-demand recovery capability and operator drill
own their stronger input/completion/authority/output checks.

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
`acceptance` remains the default. Discovery preserves evaluator source and scope
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


Discovery classifies partial load observations separately. A missing midpoint may continue only
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

Current native configurations select the compact-input reader from the actual
`pgstream.generation` and recovery configuration. One SELECT binds input source
identity and restore generation, recoverable WAL positions, the local input floor,
completed clinical coverage, pending/due work, output metadata and raw-tail head/base.
The public history stamp is observed separately. Clinical completion can advance
while an unchanged output keeps its original captured input floor and revision.
Explicit lifecycle invalidation may reset the snapshot position to `0/0`; accepted
commit positions retain their own source, generation and coverage fences.
The reader checks the actual stored marker, BG-now result and stock callback;
metadata alone does not qualify clinical equivalence or raw delivery.

The unqualified selected-intake/profile reader and its mechanism-only control
are removed. Original v1/v2 readers remain for historical source fixtures and
retained baseline reproduction. A native configuration cannot fall back to them
when its source/restore/coverage proof is missing.

Client delivery is per logical viewer. Reconnection alone does not refute a valid
callback. New captures retain the exact expected viewer slots, observed transport
incarnation, connection count, SGV identity/time/value and a single-probe monotonic
request-to-callback deadline. Missing, duplicate, foreign, wrong-value or late
callbacks refuse. The historical hold4000 failure stays unchanged: retained
callbacks show timely stored-ID delivery, but omit connection counts and full
callback values needed to identify its strict-predicate rejection.

Focused offline controls (no SQL/runtime execution):

```bash
node tools/mt-bench/m7-joined/completed-oracle-control.cjs
node tools/mt-bench/m7-joined/completed-oracle-v2-control.cjs
node --test tools/mt-bench/m7-joined/native-observation.test.cjs tools/mt-bench/m7-joined/client-delivery.test.cjs
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

The existing `run` entry point checks evaluator health and scope.
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
both; do not infer equivalence to the shipping f9 binary. The notifier package, matched static CLI builds and version-only smoke are
source qualified in the reviewed build receipt. Shipping-f9 equivalence, live
replacement-binary deployment and native timing remain UNMEASURED and require
the root coordinator's next finite boundary.


The sender target file is published after the existing bootstrap/primer stages,
before either instrumented role starts. Its two IDs match the Node selection;
`clockSchema` must match the generated layout and actual receiver configuration
under the existing `pgstream-sample` namespace contract. Every new lifecycle
effect rechecks the staged bytes, receipt, exact mounts and target publication.
Preexisting outputs, unsafe permissions, symlinks, unknown schemas, wrong roles,
extra mounts and missing provenance refuse startup. Existing source, image,
finite-window, owner and exact resource identity checks remain in place.

Sender preflight reads the actual qualified primary Go process from the existing
container/process snapshot, then hashes `/proc/<pid>/exe` with matching birth
bookends. It requires the overridden digest, expected executable path, owner UID,
container/image/command and exact readonly/output mounts. Docker PID 1 is not a
substitute. This is a point observation; a native packet still needs lifetime and
clock qualification through its full target interval. Image ID or a `development`
version string alone never attests the executable. The original image f9 binary
and privileged initializer remain separately qualified and unmodified. Both twin
CLI builds report `development`; optional Go health payloads inherit that version
when enabled. The existing external service has no Compose healthcheck, and the
Node receiver/store health checks do not match the Go version string.

This is an explicit diagnostic overlay. The product's one-volume streaming
check and executable-overlay refusal in rebootstrap remain strict; the helper's
selected diagnostic contract admits only the original wire mount plus these
three exact mounts. It does not turn that overlay into canonical product
configuration or authorize rebootstrap.

Admission and cleanup are separate. Changed or missing sender material refuses
new effects. Owned teardown still runs the original source/config/image/ownership
and finite cleanup checks; a sender refusal is retained as UNMEASURED and cannot
block stop/down. Available bounded sender files are copied before private-state
wipe even after a partial failure. Their structural/target/connection assessment
remains UNMEASURED; metadata capture never grants clinical acceptance. There is
no public flag to bypass admission or resource ownership.

### Stream materializer discriminators

These focused controls import the application and deployment modules from explicit
worktrees. They do not launch a service or establish deployed recovery, clinical
equivalence, or an operating envelope.

```bash
node tools/mt-bench/m7-joined/materializer-default-control.cjs "$CORE_WORKTREE" "$DEPLOY_WORKTREE"
node tools/mt-bench/m7-joined/materializer-row-control.cjs "$CORE_WORKTREE" "$NATIVE_DECODER_JSONL"
```

The default control checks the maintained route and wire exports without a route
override: all six clinical tables enter the decoder, XIDs are enabled, delivery
is serial and strict, and output checkpoints do not feed clinical intake. Its
controls remove clinical routes, XIDs and one decoder table filter. Restored
exports must pass after each failure.

The row control consumes retained synthetic wal2json payloads from a native
PostgreSQL fixture with the candidate clinical storage-size migration. It keeps
JSONB text, omitted unchanged TOAST documents, physical size updates and delete
identities as emitted. The capture must contain an insert, ordinal-only update,
clinical update and delete in separate transactions, followed by an eight-row
COPY cohort with a shared LSN. No fixture values are normalized into the target
contract. It checks coherent XID sealing, serialization/cache-loss boundaries,
future cohorts across bootstrap, extensions, storage-size propagation and exact
row coverage. A mocked SQL commit boundary exercises the actual receiver and
clinical receipt module: raw ACK waits for COMMIT, a failed COMMIT refuses the
receipt, and raw intake does not execute clinical I/O. Actual replay bootstrap
must retain invalid-row storage bytes and history while excluding those rows
from clinical output. An actual-runtime timer cycle must acquire newly observed
input before marking that version completed. The actual scheduler must let a
newly addressed neighbor use a free slot while another tenant is held, preserve
per-tenant serialization, retain input arriving during evaluation, and keep an
unrelated tenant wake from accelerating a failed tenant retry. Recovery pages
must advance while an earlier tenant is held. Known row/byte overflow commits a
bounded non-ready gap before ACK; the input cache is evicted, its sealed
checkpoint column stays unchanged, and only successful bounded bootstrap clears
the gap. Mocked SQL checks that gap persistence replaces old cache metadata.
Full and compact receipt states must enforce the same exact byte boundary.
The actual migration inspector must preserve standard-to-ordered upgrades with
the single reviewed common storage-size tail; unknown or changed history,
missing ordinary prefixes, duplicate rows and forged typed SQL still refuse.
Actual-source mutations drop same-LSN rows, deletes or XID
isolation, restore the invalid-row bootstrap filter, remove the timer coverage
guard, restore the held-tenant batch barrier, clear every tenant retry on one
wake, block recovery paging on held work, undercount metadata bytes, mark a gap
ready, retain stale cache metadata, disable exact size-tail commutation, or
remove the raw receipt await; each must fail for its named symptom before restoration passes.

Earliest-due lookup controls use the actual scheduler with a held metadata query.
Neighbors complete while one query is in flight; a newly earlier deadline must
survive the follow-up. Sharing omission must increase lookup concurrency, and
lost follow-up must retain the wrong deadline. A removal queued as the query
settles must leave the remaining tenant's timer armed. A postponed ownership
clear must make that same case fail. These controls measure scheduling/call
boundaries, not native SQL cost or a capacity ceiling.

Capture originals stay outside Git. Retain the executed probe, schema/source
identity and checksum beside the capture. These controls preserve source-level
boundary evidence; the integrator owns the final joined runtime acceptance.

## Single-host qualification allocation

### Authored resource and nginx allocations

`--diagnostic-resource-allocation` accepts one exact version-1 JSON allocation
with `services`, `driver`, `ceiling` and `edge` fields. It replaces reference
CPU/memory sizing when preparing a fresh fixture. Named profiles retain their
exact sizes. The service roster must match the rendered fixture, including its
existing supported role names and ordinal range. There is no separate 32-service,
64-CPU or 128-GiB reference ceiling for an authored allocation. Every selected
role, declared bootstrap/primer overlap and standalone driver still counts
against the authored aggregate ceiling. Remote receiving helpers additionally
check the actual declared SUT and driver host inventories independently.

Fresh authored service allocations use integer `cpu_quota` and `cpu_period`
fields. Compose's float32 `cpus` field can round a selected value, and its native
conversion can lose precision even when config JSON looks unchanged. The integer
path preserves integer quota/period through Compose; native runtime precision
requires a separate check. Native readback requires zero
`NanoCpus`, exact quota/period and no alternate CPU limiter. Named profiles and
entered legacy explicit fixtures keep their existing `cpus`/`NanoCpus` path;
standalone Docker `--cpus` keeps its exact decimal CLI path. The frozen config
selects the mechanism, so legacy records are not migrated during an entered run.

Each new service record includes `cpuEnforcement` with quota and period in
microseconds. Fresh ordinary allocations keep a 100,000-microsecond period.
Values from 1 through 9 millicpu use 1,000,000 microseconds to meet Linux's
minimum 1,000-microsecond quota, where the runtime can represent that average.
Very large fresh values use a 1,000-microsecond period before quota exceeds
9,223,372,036,854 microseconds: runc 1.3.3's systemd conversion multiplies signed
quota by 1,000,000 before division. These recorded period changes preserve the
selected CPU average but change scheduling granularity. Entered quota records
keep their frozen period; validation and census never select a new one.
The Linux 6.18 source defines `max_bw_runtime_us=MAX_BW`, with
`BW_SHIFT=20` and `MAX_BW=(1<<(64-BW_SHIFT))-1`; at a 1,000-microsecond period,
that necessary service maximum is 17,592,186,044,415 millicpu. This read-derived
kernel representation bound is separate from host fit and actual kernel
admission. The [kernel validation](https://github.com/torvalds/linux/blob/v6.18/kernel/sched/core.c)
and [bandwidth representation](https://github.com/torvalds/linux/blob/v6.18/kernel/sched/sched.h)
own those limits. Docker also validates the
[period and minimum quota](https://github.com/moby/moby/blob/docker-v29.1.3/daemon/daemon_unix.go)
and carries explicit quota/period directly into its OCI CPU resources.

Actual fresh preparation reads the selected daemon's cgroup driver/version,
default runtime and reported runc version before resource leases or fixture
effects. This early observation does not qualify every template role. After
source rendering, the existing deployment stages and their transitive Compose
dependencies select the actual execution roles for precision qualification,
before any container command. An ops profile alone does not make a role active:
bootstrap and primer run in these stages; unused demo/operator templates may
remain dormant. All authored roles still count against the aggregate ledger.
The confirmed systemd/cgroup-v2 path with runc `1.3.3` or
`1.3.3-0ubuntu1~24.04.3` rounds CPU bandwidth up to whole percent units. Its
[runc conversion](https://github.com/opencontainers/runc/blob/v1.3.3/vendor/github.com/opencontainers/cgroups/systemd/common.go#L264-L297)
therefore represents service CPU only in multiples of 10 millicpu. It also
requires quota times 1,000,000 to fit signed int64. Preparation refuses an
affected field with its requested value, runtime and representation reason;
the stable CLI code retains the field suffix, and a bounded JSON diagnostic
reaches the runner's retained private preparation output. It never rounds the
selection. For example, 65.001 CPU is unsupported on this
path while 65.01 CPU is representable. A different period cannot change that
ratio precision. Retained native controls observed 65.01 CPU for the requested
65.001 CPU at both 100-ms and 1-second periods, despite exact HostConfig values;
both strict failures and owned cleanup remain recorded under the lane's
overflow-disk evidence. This is a runtime capability, not a reference CPU cap.

Pure configuration/receipt plans never query the daemon. Missing inventory,
other drivers and unqualified runtime versions retain runtime precision as
`UNMEASURED`; they do not acquire this runtime-specific restriction or a native
pass. A fresh explicit owner's `cpuPrecisionPreflight` records `qualifiedRoles`
and `deferredRoles`, the execution-scoped `PASS` or `UNMEASURED`, and the
classified runtime when available. A deferred role keeps its exact authored
allocation and remains unqualified. The existing Compose actor admission guard
checks requested targets, dependencies and already active quota roles before
each actor command, including later activation of a dormant template. Existing
`--no-deps` selections retain their dependency semantics; read-only commands and
exact-owned cleanup remain available after refusal.
Named profiles, entered legacy fixtures and standalone `--cpus` keep
their existing paths. Exact native admission/readback remains required.

Standalone driver CPU must fit Docker's signed-64-bit `NanoCpus` field; service
and driver memory must fit its signed-64-bit byte fields. The current memory-unit
contract starts at one MiB. Native engine and kernel admission and exact quota
readback remain required. An accepted numeric JSON allocation does not reserve
CPUs, enlarge host inventory or establish memory headroom. Docker's
[container resource API](https://docs.docker.com/reference/api/engine/version/v1.40/)
defines the native field representations.

An authored `edge` selects independent positive integer `workerProcesses` and
`workerConnections`. The helper first runs the pinned deployment renderer with
its existing reference worker settings. It then projects only those two unique
numeric directives into the owned mounted nginx config, before capturing its
digest. All routing, public Host handling, header trust and handshake admission
bytes remain source-rendered. An unexpected baseline, duplicate directive or
changed descriptor budget refuses. Named-profile output remains unchanged.
The existing runtime `nginx -T` readback must match the selected numeric values
and the retained `worker_rlimit_nofile 65536` directive.

The Linux nginx implementation has a total process-table bound of 1,024 child
slots, shared by workers, optional cache helpers and overlapping generations
during reload. This is a necessary implementation maximum, not a promise of
1,024 available worker slots or evidence that those workers started. The
[process table](https://github.com/nginx/nginx/blob/master/src/os/unix/ngx_process.h)
and [worker/helper/reload paths](https://github.com/nginx/nginx/blob/master/src/os/unix/ngx_process_cycle.c)
own that read-derived boundary. Actual process births, cgroup PID limits and
effective OS descriptor limits need observation in the selected environment.
Configured `workerConnections` cannot exceed the retained actor's 65,536-file
descriptor directive and Compose `nginx.ulimits.nofile` hard limit. A larger request reports
`ALLOCATION_EDGE_DESCRIPTOR_LIMIT`; extending it requires an explicit descriptor
budget, mounted-config and Compose-ulimit projection, and effective descriptor readback. Connections
include upstream connections and consume descriptors for other work too, so the
configured value does not prove a client capacity. See nginx's
[connection and descriptor directives](https://nginx.org/en/docs/ngx_core_module.html#worker_connections).

The Python remote receiver uses the same explicit numeric contract and retains
physical-host fit. Older remote controllers can still lack explicit allocation
support or retain their own reference validation. Their precise source guard
must be extended by the controller owner before using those values through that
controller; local rendering and receiver controls do not establish a remote run.
The existing [restriction policy](../../../docs/30-design/tenancy/deployment-and-rig-testing.md#configurable-limits-and-restrictions)
separates these instrument boundaries from application and acceptance claims.

### Named qualification profile

`--diagnostic-resource-profile local-qualification-external-pgstream-6cpu-10g-v1`
selects one proposed allocation for local synthetic qualification with
`external-service-v1`. It is not a measured supported envelope. Keep tenant
roster, connected viewers and offered HTTP rate independently selected. The
initial target is 1,000 tenants, 64 viewers and 7 offered requests per second;
clinical completion and authorized frames must pass their existing bounds.

| Role | CPU limit | Memory and memory-plus-swap limit |
| --- | ---: | ---: |
| evaluator | 1 CPU | 1,024 MiB |
| PostgreSQL | 1 CPU | 1,536 MiB |
| pgstream sender | 0.25 CPU | 256 MiB |
| Vault | 0.25 CPU | 512 MiB |

Other role limits retain the existing diagnostic values. The full selected
roster, two bootstrap instances, two primer instances and standalone k6 reserve
5,500 millicpus and 9,216 MiB within the explicit 6 CPU / 10 GiB ceiling. Host
probe/generator/helper V8 heaps reserve another 1,024 MiB; native allocations,
host RSS, Docker and operating-system costs require separate observation. This
is a shared-host limit, not an exclusive host reservation. Existing source,
image, ownership, quota readback, finite deadlines and cleanup checks apply.

The increased evaluator and PostgreSQL CPU limits let qualification distinguish
work demand from the inherited restrictive quotas. Observer commands execute
inside serving cgroups and consume those quotas. Stable primary-process CPU and
container CPU must retain separate attribution; their difference is not an
exact observer-cost measurement. Provisioning and steady serving are separate
results. In particular, the separate 10,000-set Vault component result does not
qualify this allocation for that roster or prove memory headroom.

Use the existing runner and strict count/clinical/frame oracles. A missing due
opportunity cannot establish deadline service. Preserve failed captures and
report driver errors separately from application errors. Final qualification
requires the integrator's frozen source/image and applicable functional
acceptance; this allocation changes neither application code nor acceptance.
### Sparse discovery count control

A discovery cohort need not give every tenant an ordinary write before testing
its count oracle. The discovery-only control admits complete, exact matched
ordinary/probe counts with no uncertainty or pending probe writes and at least
one accepted ordinary write. Missing counters remain unknown; an empty workload
or ambiguous counts cannot witness this control. The control selects a nonempty
ordinary domain, temporarily changes one owned run marker, requires a RED count
observation, then restores the marker and requires GREEN. It saves the three
observations beside the control result. No-op corruption or failed restoration
refuses. Strict/default acceptance keeps its requirement for a write from every
tenant. This change applies to future helper runs; it does not qualify or relabel
an earlier point whose control was not run.


### Selected admin-verified startup

New deployment pins that contain `platform-startup.js` require an explicit
`--tenant-readiness serve` or `--tenant-readiness all`. The resolved configuration,
diagnostic receipt and frozen serving environments carry that selection. The
`platform-verify` job calls the private admin API after commission and before API
launch. Its process receives no database or Vault credential. Older deployment
pins keep their original stage sequence.

For a bounded local startup experiment, select `--api-warm-cause startup-v1`
with the existing discovery receipt and resource allocation. It supports small
fixtures before a 10,000-tenant point. This source-bound observer samples actual
API process heap use, V8 heap ceiling, cgroup memory ceiling/current use and safe
startup counts once per second, retaining the first samples and a bounded recent
window. It adds file I/O and count-sampling overhead; it is not a matched CPU
baseline. No tenant identifier, credential, request body or glucose value is
emitted. `warm-v1` keeps its original 10,000-tenant refusal-correlation scope.

`deployment-stages.json` records each entry before effects and its elapsed time,
verdict and safe first error in `finally`, including a throwing primer. New
`startup-primer-boundary.json` keeps the exact API birth, process exit and Docker
health state, latest startup counts, actual memory ceilings, typed primer error,
and first useful response/completed primer events before cleanup. The raw bounded
samples survive in `startup-samples.private.json`; failure log tails are private.
Missing, stale, foreign or replaced-process observations remain UNMEASURED. A
collector failure preserves the original primer failure. A failed primer starts
no remaining roles or ordinary load.

API process readiness, first useful tenant response, completed primer and remaining
role readiness are separate stages. A warm primer proves neither cold evaluator
recovery nor steady load. Pending and future-due recovery without new input needs
its own clinical control; capacity remains ungranted until the integration owner
qualifies the selected source and operating point.
