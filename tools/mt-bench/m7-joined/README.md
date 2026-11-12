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

## Source and ownership

`adapter.py prepare` creates a unique detached core worktree from a **full commit**,
archives the deployment's committed Compose tree over its deployment directory,
and writes the product build overlay marker. Every remaining core input must pass
the shipping build's two-source admission. There is no borrowed node_modules:
probe dependencies use a separate owned install of the exact committed core package.json
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
`prepare` only stages local source/TLS/config; it sends no performance traffic.
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

`evaluator-idle-safety-v1` captures all IDs/all evaluators, actual helper UTC
observations and wall-clock timestamps bracketed by monotonic timestamps around
each existing exec. A common wall-minus-monotonic offset interval must cover all
read boundaries; clock jumps, overlap, missing stamps or ambiguity are UNMEASURED.
This is sampled observation, not continuous quiescence or a timer deadline SLO.
No additional request, phase duration, clinical write, plugin change or work trigger
is introduced. Notification polling and read-only signature/backstop confirmations
are allowed and never count as successful clinical time work.

Both idle-safety classifications require every sampled owner clinical flag to
be false. Any running/booting/queued clinical job is UNMEASURED/BUSY even when
time completions are present; complete raw counters remain retained, and this is
not a stall/error claim. Strict native TIME/load/recovery may observe active jobs.
This idle-baseline rule is not a universal active-work capacity policy.

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
with null age, errors and progress requirements remain strict. Refused field
checks retain fixed predicate/field names and bounded positional indices, never
raw rows, tenant IDs or runtime values. Readiness deadlines, polling cadence,
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
