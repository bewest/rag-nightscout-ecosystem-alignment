# Kubernetes boundary for the M7 synthetic instrument

This adapter prepares and observes one independently owned Kubernetes fixture.
It reuses the [existing M7 workload, stock client and oracles](../m7-joined/RUNNER.md).
Preparation and offline controls start no services. An operator or explicitly
authorized experiment owner executes on the private environment's finite
capacity, image delivery and trust allocation. Rendered resources do not grant
correctness or capacity acceptance.

The shipping application remains a secondary display for CGM and pump data.
Run only synthetic tenants on independent state. A failed clinical, authority or
tenant isolation check stops qualification. Preserve uncertain writes and raw
evidence; do not retry a mutation to make a result green.

## Frozen-image experiments

Use `experiment.py` to select an immutable source-owner receipt, materialize its
binding, and prepare a new packet for each allocation. A manifest remains stable
across namespaces, UIDs and deadlines. Its `profile` uses the existing workload
profile format with the source selection supplied by the manifest. For example,
the following selects an explicit candidate and a 1,000-tenant realistic profile.
The input paths are absolute. Obtain the receipt digests from the releasing owners.

```bash
K=tools/mt-bench/kubernetes
jq -n --slurpfile p "$K/workloads/realistic-1000.json" \
  --arg source "$SOURCE_RECEIPT" --arg ss "$SOURCE_RECEIPT_SHA256" \
  --arg build "$BUILD_RECEIPT" --arg bs "$BUILD_RECEIPT_SHA256" \
  --arg binding "$BINDING_COMMIT" --arg pg "$POSTGRES_CONFIG_ID" \
  '{version:1,kind:"k8s-frozen-experiment",sourceReceipt:{path:$source,sha256:$ss},
    buildReceipt:{path:$build,sha256:$bs},bindingCommit:$binding,postgresImageId:$pg,
    profile:($p[0] | del(.referencePins) | .workload.setupSeconds=360 |
             .workload.drainSeconds=180)}' > "$NEW_MANIFEST"
python3 -B "$K/experiment.py" describe "$NEW_MANIFEST"
python3 -B "$K/experiment.py" binding "$NEW_MANIFEST" "$BINDING_REPO" "$IMAGE_DEPLOY_REPO" "$NEW_BINDING"
```

The binder exports the selected Git tree into a fresh directory, runs the
original image constructor with its read-only filesystem and disabled network,
and compares installed deployment bytes, role commands, SQL identities and
native catalogue against the supported single-cohort binding. The generated
`bindings/kubernetes/assets/source-contract.json` carries the measured producer,
image, source and owner receipt. `binding.json` identifies every materialized
file. A changed deployment protocol or catalogue requires a compatibility review.
An unknown commit with compatible measured inputs follows the same path. The
source receipt may carry a bounded diagnostic PENDING or joined source PASS.

The execution owner renders the package with its private commissioning overlay.
The accompanying private patch is supplied in the local release packet. Apply
it to a clean copy of the indicated private base and install this release's
`frozen.py` beside `preflight.py`. Set `experimentManifest` and
`experimentBindingReceipt` in the environment to the respective
`{"path":"…","sha256":"…"}` references. The existing context, trust, node
placement, quota, headroom, cost and UID-conditioned cleanup checks apply.
Private admin verification precedes serving roles.

A binding with `Job/verification` publishes the admin proof in its completion
log. Put that Job in `stages/verification.json` when preparing the case. The
lifecycle waits for it before installing serving workloads and then launches the
lab provisioning client. The attach phase reuses the captured proof and
checks the native database source independently. The primer's private results
live on its `/run/ns-client` volume. Set its size with the renderer's
`primerStorage` input, such as `64Mi`.

The primer verifies DATA credentials for the full `population.provisionedTenants`
roster. Set `population.ordinaryRosterTenants` to the number of consecutive entries
from the start of that roster that should receive ordinary k6 traffic. Select
`workload.offeredRps` for an aggregate rate or `workloadMix: realistic-v1` and
`workloadScale` for per-tenant cadence. Both host k6 and the optional k6 Job use
this selection. The stock probe assigns `workload.logicalPollingClients` across
the full roster. Its probes, access checks and tenant-wide observers can reach
tenants outside the ordinary subset. Storage checks require both k6 write counters
for every selected tenant and query marker-tagged rows across the full database.
An ordinary row on an unselected tenant fails the check. Probe writes on any
provisioned tenant reconcile against the separate probe ledger.

The optional `bootstrapHelper` manifest entry selects the reviewed deploy source
commit and SHA-256 of `bootstrap.js`. The constructor verifies the original
image file, extracts the corrected file from Git and installs it in an immutable
ConfigMap. Only the provision Job's bootstrap init container mounts the file.
The package labels the effective diagnostic instance PENDING and retains the
base image's own source acceptance. For an early readback after foundation
creation, run `adapter.py bootstrap-map PACKET NAMESPACE_UID` against the
commissioner's recorded UID. Initial observation checks the same ConfigMap,
Job, actual Pod and bootstrap container. When the read guard masks words in
this public file, kubectl compares its known source, UID and resource version
locally and emits a Boolean. A missing or changed readback stops the check.

For a discovery fixture with an external producer, the optional manifest field
`pgstreamNotifierAckTimeoutMs` selects a positive acknowledgment budget in
milliseconds. The publisher projects the one field from the private bootstrap
wire file before creating `ns-config-pgstream`. The selected package, source
wire hash, effective wire hash and live producer incarnation are bound into
the run. The controller verifies the wire hash in the owned Pod before native
attachment. The producer binary, retry cadence, and clinical observation
windows keep their selected source behavior.

Supply the existing runtime config, inventory, render, and two independently
pinned receipts as a fresh instance file in this form.

```json
{
  "config": "/owned/instance/runtime.json",
  "inventory": "/owned/instance/inventory.json",
  "render": "/owned/instance/render.json",
  "bindingReceipt": {"path": "/owned/binding/binding.json", "sha256": "<binding receipt SHA256>"},
  "delivery": {"path": "/owned/instance/delivery.json", "sha256": "<delivery receipt SHA256>"},
  "roleDocuments": {"evaluator": "/owned/private/evaluator-config.json", "realtime": "/owned/private/realtime-config.json"}
}
```

Delivery includes the existing `app`, `postgres`, config IDs, source tuple and
cost fields, plus `registryManifests.app` and `.postgres` pointing to the raw
single-platform registry response bytes. Select the platform manifest before
using a multi-platform index. The runner hashes those bytes and reads each
config descriptor. Runtime Pod readback checks the independent mapping again.
Private role document inputs select the completion oracle. An already measured
matching `completion` projection can also be supplied in the config. Supply
the expected settings fingerprint, owned loopback port, projected synthetic
roster and finite native tools, dependencies and limits as in the adapter guide.
The runner derives pins and checks any previously supplied pins for equality.

```bash
python3 -B "$K/experiment.py" prepare "$NEW_MANIFEST" "$INSTANCE" "$NEW_PACKET" --await-primer
python3 -B "$K/adapter.py" observe "$NEW_PACKET"
python3 -B "$K/adapter.py" candidate-proof "$NEW_PACKET"
python3 -B "$K/adapter.py" policy "$NEW_PACKET"
python3 -B "$K/primer.py" "$NEW_PACKET" "$NEW_PACKET/primer"
# Start the authorized loopback forward before the access check.
python3 -B "$K/adapter.py" access "$NEW_PACKET"
python3 -B "$K/experiment.py" run "$NEW_PACKET" "$RELEASED_ALLOCATION" "$ALLOCATION_SHA256"
```

With `--await-primer`, prepare the packet before DATA credentials exist. The
primer runs the image's checked source module inside the original verified
waiting Pod and uses its private admin and DATA Services. It bounds execution
by the earlier of the packet and active Job deadlines. The lifecycle sets the
primer Job deadline to the remaining owner work budget when it releases the Job.
An increased durable provisioned or DATA tenant count renews the matching stall
window. An unchanged checkpoint, a retry and Pod readiness alone leave it running
toward expiry.
`--concurrency N` selects the source implementation's bounded concurrency.
For fresh discovery, set `profile.phases.primerOptions` with `concurrency` and
optionally `maxTenants`. For example, `{"concurrency":64,"maxTenants":20000}`
selects up to 64 workers for a chunk of up to 20,000 pending tenants. The source
starts no more workers than the pending chunk contains. With the extended
source, both fields accept positive JavaScript safe integers. The defaults are
one worker and 10,000 pending tenants per invocation. The image constructor
checks the pinned parser and exact bytes before binding the selection. Legacy
images refuse options beyond their supported range before resource creation.
The waiting actor takes the bound selection automatically. Explicit arguments
must match it. A partial DATA result stays incomplete and keeps its custody.
Fresh discovery can also select `profile.population.maxTenants`, projected to
the binding's `populationCeiling` and bootstrap's `NS_DEMO_POPULATION_CEILING`.
Omission retains 10,000. An explicit selection requires the exact source
protocol, image constructor and binding compatibility map, including a lower
ceiling. Rendered inventory, the bootstrap environment and owned-container
private-config readback must agree. Registry pages, LRU caches, file/Secret/IPC
bytes, resources and clocks retain their independent contracts.

Population and primer chunk sizing are separate. A 10,001 fresh seed with the
default 10,000 pending-tenant chunk reports `PARTIAL_CHUNK_BUDGET` in
`populationCommissioning`. Set `profile.phases.primerOptions.maxTenants` to
10,001 for one-invocation coverage budget. The effective chunk is exposed;
the helper does not rewrite it. Constructor success grants no DATA completion
or operating capacity, and incomplete DATA continues to refuse traffic.
The successful receipt binds the privately exported DATA roster to the run,
namespace, Job, Pod and container. Access and load verify this receipt.
Preserve the source lock and uncertain-write journal after an interrupted
request. A stalled attempt records its last observed count. While the same
fixture and its private checkpoints remain available, repeat the primer command
in the same packet to resume. The lifecycle releases the namespace at cleanup.
After privately saving the complete roster and its receipt, the primer command
acknowledges export and the waiting container can exit. A previously
source-projected roster still uses the original prepare command.

For fresh discovery, `primerStorage` can select `stateMiB` and `secretCodec`
in the experiment manifest. For example, `{"stateMiB":32,"secretCodec":"gzip-v1"}`
selects a 32 MiB primer state volume and lossless transport of the primer
configuration. `raw-v1` uses the source bytes directly. The materialized
publisher checks the exact data size of every role Secret before publication.
The primer installer checks the original config's byte count and SHA-256, then
restores its private file. The actor verifies the mounted state volume and
config digest before writing and records filesystem size and usage when
available. The source retains its original atomic writes and uncertainty journal.

The lifecycle starts the split binding's platform bootstrap while Vault can
still be sealed. Once the private admin proof succeeds it starts all serving
roles, including pgstream, before releasing the tenant provision and DATA
primer. The verified client's disk-backed state has no default size limit.
Older bindings keep their own state representation.

`profile.phases.cohortReadySeconds` selects the maximum time without a new
Kubernetes startup milestone on the serving cohort. The default is 300
seconds. Pod scheduling, initialization, container startup and readiness can
extend the wait up to the operator's work cutoff. A stalled cohort records
`UNMEASURED` and the elapsed time under the readiness-as-signal policy. A
stalled required infrastructure workload or platform provision Job stops
startup. The optional pgstream convergence scenario retains its own maximum.

Fresh intent also accepts positive integer seconds in
`profile.phases.startupWindows.kubernetes`. Set `workloadReadySeconds` for
the other workload readiness stall intervals, or `primerReadySeconds` and `dataPrimerSeconds`
for the maximum interval between durable provision or DATA checkpoints. `roleExportSeconds`, `platformVerifySeconds`,
`secretSeedSeconds`, `secretPublishSeconds` and `jobCompleteSeconds` cover the
separate bootstrap handoffs. `requestSeconds`, `commandSeconds` and `execSeconds`
control individual controller calls. The lifecycle records the chosen values,
their reference defaults and native Pod probe and Job deadline settings at
preflight. Each wait is clipped to its original work deadline. The DATA actor
also honors the existing owned Job deadline. Native Pod probes and clinical
completion continue to use their existing predicates and clocks.

Set optional `workload.evaluatorProgressBudget` with `maxQueriesPerPhase` and
`maxBytesPerPhase` to select a different three-round evaluator capture budget.
The packet retains the exact policy and keeps an exhausted capture `UNMEASURED`.

An initial read records the owned evaluator's progress and tenant scope before traffic starts. A tenant without input may have zero completed acquisitions. Legacy profiles may still contain `phases.preloadConvergence`; the standard load ignores that field.

The access witness checks both own-token exchanges, both cross-tenant refusals, and foreign frames on the selected socket connections. Missing socket observations yield `UNMEASURED`. A foreign frame, an accepted wrong credential or a cross-tenant read stops the run.

For an independent database observation within the original work deadline, run
`adapter.py observe-sql PACKET NEW_DIRECTORY`. It counts the source primer's
stored seed rows and distinct tenants, checks the candidate database epoch and
requires the original Ready PostgreSQL Pod. Setup Pod retirement requires the
original Job UID, recognized terminal condition and original Pod controller
identity. Before/after captures retain serving Pod UIDs, Job failure and last
observed exit codes. Missing exits stay UNMEASURED. Full workload admission
still checks the complete census and all existing workload evidence.

Use the existing matrix allocation schema for a single fixture. Include
`experimentSha256`, the SHA256 of the original manifest. Its preflight must
bind the same run, namespace, manifest and render. The allocation binds the
observed namespace UID, exact run file, absolute deadlines, node and native
limits. Each attempt owns its result directory. For concurrent fixtures, use
`adapter.py matrix-run` and a single aggregate grant. Its
`experimentPreflights` object maps each experiment run ID to the corresponding
commissioning preflight reference. The matrix checks aggregate fit and records
each fixture's independent outcome.

Change `population`, `logicalPollingClients`, `workloadScale`, `loadSeconds`,
`setupSeconds` and `drainSeconds` in the stable workload definition to select
another point. `setupSeconds` begins with ordinary driver JWT setup.
Viewer priming uses the separately configurable `workload.viewerSetup`
progress wait and connection ramp. The [runner guide](../m7-joined/RUNNER.md#phase-clocks-and-local-discovery-to-completion)
describes the equivalent local `viewer-setup` fields. Commission and recovery
use polling for stock display coverage. The entered work cutoff bounds both actors.
`drainSeconds` bounds the final wait. The clinical deadline is 120 seconds from input acceptance. Every accepted input that owes clinical work must have durable output by the end of drain. The frame recorder retains its overflow refusal.

Read `experiment/result.json`, `load/failure.json` when present, and
`experiment/observations/reduction.json` before fixture cleanup. These retain
first failure, offered work, stored writes, selected clinical witnesses, frames
and unavailable observations separately. Capacity remains NOT_GRANTED.

The strict midpoint read is scheduled from the stock probe's `.window` signal.
Native JWT setup can still be in progress when this read runs. A refusal retains
the bounded private evaluator response when available, along with source and
runtime binding for the capture. k6 phase markers stream to `load/k6.log` or
`load/k6-shard-<index>.log` while the driver runs. After an early stop the
reduction reports the markers it observed and whether a terminal summary
exists. Terminal totals stay UNMEASURED when the summary is missing.

| Existing Docker assumption | Kubernetes boundary |
|---|---|
| Compose project/container census | Explicit context, run label, namespace UID, workload/ReplicaSet owner chain, Pod UID and container incarnation |
| `docker exec` SQL | Fixed PostgreSQL container, read-only transaction, exact source/Pod checks before and after |
| Docker process inspection | The same `evaluator-progress.cjs` and Python assessor through bounded container exec |
| Docker host-network k6 and dependency mounts | Existing native k6 and source-matched owned stock-client dependencies; no install or new driver Pod |
| Docker restart/health timestamps | Separate exact Node-role restart, container ID/restart-count readback and unchanged other incarnations; no Docker health-time equivalence |
| Compose project deletion | Inspectable exact-object DELETE bodies with server-side UID preconditions; no selector deletion |

The removed `claims.cjs` reran `completed-oracle.cjs` over raw independent SQL rows and actual
stock-client observations. This proves the existing selected BG-now bucket
mean/last, typed durable output, stored row and client frame properties for the
witness subset. It does not establish all clinical properties. The original
`discovery_counts` and `viewer_plan` reducers retain missing ACK/uncertainty and
viewer semantics. Cross-tenant stock-frame checks cover the witnessed synthetic
stored IDs; the separate read/socket refusal probe covers swapped credentials.
Neither supplies an unmeasured NetworkPolicy enforcement claim.

Prepare private inputs from the immutable binding export. `pins` binds the core
and image deployment commits, the separate binding commit, render/inventory
SHA256s, pullable application manifest reference, application image config ID
and this adapter's content instrument. A local image config ID is not a registry
manifest digest. Runtime observations preserve Kubernetes `imageID` separately;
the environment owner must establish its image/source mapping.

```bash
python3 -B tools/mt-bench/kubernetes/adapter.py identity
python3 -B tools/mt-bench/kubernetes/check_export.py /absolute/binding-export /absolute/new/offline-join
python3 -B tools/mt-bench/kubernetes/adapter.py prepare /absolute/private/run.json /absolute/private/inventory.json /absolute/private/render.json /absolute/new/run
```

For the C3 candidate, carry the exported inventory's `candidateContract` into
`pins.candidate` and add the commissioned `postgresImage` and `postgresImageId`.
The adapter checks the rendered source contract and the actual kubelet app and
PostgreSQL image identities. After live `observe` and while the same primer
container is still waiting, run `candidate-proof RUN`. This captures the private
admin verification receipt from the owned Pod and compares its native PostgreSQL
source against a read-only observation of the selected database and logical
slot. Capture this before running `policy`, `access` or workload phases.

An optional third `check_export.py` argument selects Lane E's immutable
environment export directory. The join verifies its render/inventory hashes
and the same binding archive/commit, then checks that exact storage/access
profile offline. Private values remain in its local output; no live claim follows.

`check_export.py` verifies the package archive and joins the real exported
inventory/render to an offline packet. Its generated operator input is **HELD**:
the context, dependency/access/source mapping and private commissioning exports
still need the private environment's actual values. It grants no live execution.
Outputs on this workstation belong under the overflow disk's artifact directory.

A scale diagnostic uses the existing `load` phase and matches `run.json`'s
population to the rendered provision Job. The `commission` phase remains a
two-tenant check. The `access` phase checks the first and last tenant of a
larger roster with the same pairwise transport oracle and records both witness
identities. The existing load and frame reports measure their own exercised
rosters. A frozen diagnostic can have pending source acceptance.

The run input has these fields:

| Field | Meaning |
|---|---|
| `version`, `runId`, `namespace`, `context`, `ownerLabel` | Version 1, exact inventory ownership label and explicit context; no current-context fallback |
| `pins` | `pair.{core,deploy}`, `bindingCommit`, `appImage`, `appImageId`, `renderSha256`, `inventorySha256`, `instrument` |
| `kubectl`, `readonlyGuard` | Absolute compatible client and existing private `ops/bin/ro` paths |
| `deadlines` | Absolute UTC `workUntil` and `cleanupUntil`; cleanup follows work within the finite shared duration representation and the actual released allocation |
| `roles` | Role to `{workload: "StatefulSet/cohort", container: "evaluator"}`; derives from actual inventory |
| `storageMode` | `disposable` or admitted `existing-claim`; never creates a PVC |
| `driver`, `observer` | Actual `hostId`, `sharedHost: true`, planned `resources.{millicpus,memoryBytes}`; native actors execute on the same host |
| `driver` runtime fields | Native `node`/`k6` paths and `nodeSha256`/`k6Sha256`; `coreRepository` for exact source Git blobs, `dependencies`, source `packageSha256`/`lockSha256`, existing `dependency_reuse.tree()` result as `nodeModules` |
| `tenants`, `tenantsFile` | Synthetic roster count and private projection; commissioning requires two `.test` tenant hosts |
| `completion` | Source projection from the original completed-output oracle, with this instrument binding |
| `baseUrl` | Existing operator-owned loopback forward to the exact edge Pod; tenant alias Host headers stay intact |
| `workload` | `loadSeconds` is a positive integer within k6's duration representation and the actual work deadline. Select positive finite `offeredRps` or `workloadMix: "realistic-v1"` with optional positive finite `workloadScale` (default 1). Rounded scenario time units must be representable by k6. `logicalPollingClients` is independent of tenant count and must fit a JavaScript array. `probeEveryMs` must fit the Node timer range and the probe budget. Optional `probeLedger` selects `maxWrites` and `maxBytes`. Optional `hotFactor` plus the rest of the roster must fit the generated array, and realistic-v1 requires 1 |
| `settingsFingerprint` | Existing source-derived settings fingerprint for native load |

For sequential workload points on one admitted fixture, prepare a new packet
directory with a distinct `workload.pointId` (1..31 lower-case letters, digits
or hyphens, starting and ending with a letter/digit). This adds a distinct
synthetic write marker to each stage. Keep the same source/rendered fixture and
exact UIDs, obtain the finite point allocation, and capture a fresh initial
observation. Never edit an entered packet or reuse a point marker with existing
stored writes. Concurrent fixtures still require separate namespaces/state.

The original dependency tree hash function rejects escaping links. Preparation
does not copy or install packages. Runtime requires an existing finite cgroup v2
scope covering the combined driver and observer budgets, with zero swap. It
records actual CPU/memory limits and refuses an unbounded, missing or excessive
readback before traffic. All native children inherit that scope. The operator
can use an existing delegated scope; the adapter installs no service. Include
both actors in headroom accounting; a shared host is recorded as shared.

Source projections read private exports; redirect their output only to private
files and merge the safe `completion` object into `run.json` before preparation:

```bash
python3 -B tools/mt-bench/kubernetes/adapter.py completion-source /absolute/private/run.json /absolute/private/evaluator/config.json /absolute/private/realtime/config.json
python3 -B tools/mt-bench/kubernetes/adapter.py tenant-projection /absolute/private/provisioned.json 2
```

Every command below that contacts Kubernetes or sends synthetic application
traffic needs the environment owner's concrete finite allocation and explicit
operator or experiment authorization. The adapter has no apply command. All reads
use the existing read-only guard with explicit context and sensitive reads
enabled for the isolated synthetic namespace. It records guard-masked paths;
their exact values remain UNMEASURED. No credential, connection string or
private role document belongs in a public commit.

1. Complete the private environment preflight/apply/export procedure. Run
   `observe RUN` to capture initial exact identities, then `forward-plan RUN`
   for the exact owned edge Pod and finite loopback forward command. Before
   acknowledging the primer's export, run `policy RUN`: the existing waiting
   primer `done` container must connect to admin, cohort API must time out, then
   primer must connect again. This read-only TCP control creates no actor Pod
   and uses the current private admin Service/Pod identities. A completed primer
   cannot supply this control; missing observation remains UNMEASURED.
2. Run `commission RUN`, then `access RUN`, then `assess RUN`. Commissioning
   sends exactly two probe writes and independently checks storage, completion
   and stock frames. Missing essential evidence refuses qualification.
3. For role recovery, first commission a second independent fixture. Run its
   `load PEER_RUN` with an explicitly short diagnostic probe cadence while
   running `restart RUN evaluator`, then `recovery RUN`. The restart signals
   only an exact source-owned Node PID1 inside the selected container; another
   entrypoint refuses. Run `continuity RUN PEER_RUN` after both captures finish.
   Continuity requires peer frames before and after the restart and reports
   actual frame gaps as signals. It does not invent an availability SLO.
4. Only then prepare bounded workload points. `matrix-plan MATRIX.json` accepts
   `{version:1, fixtures:[absoluteRunDirectories], aggregateCeiling:{millicpus,
   memoryBytes,ephemeralBytes}}`. It refuses colliding namespaces/run ownership/
   loopback ports or mixed source, sums per-Pod peak resource limits plus
   driver/observer budgets and prints commands. It compares the core/deployment,
   binding, manifest/config image and content instrument identities. Each fixture
   retains one cohort replica and independent state. The plan reserves no cluster
   capacity. With a released allocation, `matrix-run MATRIX.json NEW_OUTPUT`
   launches the existing load commands concurrently, then reruns their original
   reducers and live identity checks. It requires actual overlapping native load
   intervals and each declared stock client's frame during the overlap. Failed
   or incomplete fixtures stay in the result beside successful peer captures;
   the command exits nonzero for an incomplete matrix. Original raw files remain
   in each fixture, and controller inputs/logs/result go to `NEW_OUTPUT`.
5. Run `cleanup-plan RUN` before the cleanup deadline. Inspect each exact UID,
   then feed each action's `stdin` to its `argv` under the same owned authorization. The adapter
   prints actions and never executes deletes. Foreground deletion and a zero
   command status are not absence proof: read each target and accept only an
   exact Kubernetes `NotFound`/404. Lane E owns remaining Namespace, Secrets,
   existing claims and cluster-scoped Vault trust cleanup.

The work deadline bounds local actors through an independent `timeout` process;
losing the controller does not extend that cutoff. It does not automatically
remove cluster objects. The operator retains the cleanup deadline/custody.
Kubernetes exec has no Pod UID precondition: reads bracket exec, and any changed
identity refuses qualification. Use namespace-isolated RBAC; do not reuse a name
or namespace while its operator command is live. Cleanup has server-side UID
preconditions and refuses a foreign UID or resource roster.

`matrix-run` adds `allocation` (absolute private JSON path) and
`allocationSha256` to the matrix input. Commissioning exports the following
finite window from its existing preflight and custody records; this is an input
to the runner and creates no reservation service. Every fixture must already
have observed commissioning, authority and private admin policy results. Its
prepared `run.json` hash and exact namespace UID must match the allocation.

| Allocation field | Meaning |
|---|---|
| `version: 1`, `status: "RELEASED"`, `existingCapacityOnly: true`, `context` | Explicit commissioning custody on existing workers |
| `workUntil`, `cleanupUntil` | Absolute UTC bounds; each fixture's bounds fit inside this window |
| `preflight: {path, sha256}` | Exact private commissioning `PREFLIGHT_ONLY` result with offline checks `PASS`; commissioning owns snapshot freshness |
| `fixtures: [{runId, namespace, namespaceUid, runSha256}]` | Exact full fixture roster; no adoption or omitted peer |
| `nodeCeilings: {nodeName: {millicpus, memoryBytes, ephemeralBytes}}` | This batch's allowed container limits on each existing worker, after peer allowances |

For each resource dimension the planner compares each init phase, including
its already-running sidecars, with the combined steady-state containers. It
adds Pod overhead to that peak, then sums Pods at their observed placements. Native driver/observer budgets
are counted for every fixture even if they share a finite cgroup. Actor readback
still enforces each fixture's combined finite CPU/memory scope with zero swap;
sharing a scope can throttle workers and is recorded as contention. Native
artifact disk enforcement remains with the commissioning allocation/runner host;
it is not claimed from a Kubernetes ephemeral-storage limit.

`load/window.json` preserves native process start/end separately from ordinary
demand. It reuses the original first-scenario-iteration witness and configured
scenario duration, capped at native exit; JWT setup and final drain are excluded
from the concurrency interval. Missing ordinary demand refuses that claim.
The join records client counts per tenant, offered rate, probe
cadence and hot-factor distribution, raw durable/client freshness signals and
observed per-client frame gaps. The original M7 semantic oracles independently
check accepted/stored writes, selected clinical outputs and witnessed frame
isolation. Uncertain ordinary writes refuse dependent qualification while the
original uncertainty evidence is retained. These measurements supply no
availability SLO or capacity promotion. The continuity join also requires
unchanged peer Pod/container incarnations and a native load interval spanning
the exact role restart; probe setup time alone cannot establish continuity.

Load assessment also joins the original M7 HTTP accounting and
settings-fingerprint reducers. Every selected scenario and JWT setup must have
observed attempts, settled expected responses, source-counter reconciliation
and an observed matching source-derived settings fingerprint. Drops are a figure
by operation (decision driver-sized-from-offer).
Missing evidence refuses its dependent load qualification. The independent
storage, clinical and frame checks remain required; HTTP counters alone cannot
establish those outcomes. Raw functional findings survive at
`load/load-functional.json`, including failures.

Database/Vault Pod-replacement recovery is UNMEASURED for disposable storage.
An admitted unshared persistent claim and separate recovery evidence are required
before making that claim. Role-container restart does not establish backing-store
Pod durability. Source acceptance and comprehensive application acceptance remain
with the joined candidate's existing owner. Performance is reported separately
from correctness, and capacity acceptance stays `NOT_GRANTED` throughout.

Focused controls, using synthetic API replies and loopback/fake process boundaries:

```bash
python3 -B -m unittest discover -s tools/mt-bench/kubernetes -p 'test_*.py' -v
node tools/mt-bench/kubernetes/claims.test.cjs
node tools/mt-bench/kubernetes/access.test.cjs
```

The [workload profiles](workloads/README.md) bind both aggregate commissioning
and realistic per-shape demand through this same prepare/load/assess path.
`realistic-v1` reuses the released M7 generator: sensor/status ingestion and SGV
reads every 300 seconds, treatment writes every 1,800 seconds, and other reads
every 900 seconds. Scale 1 preserves those per-tenant cadences; scale 2 doubles
all ordinary shape rates without changing roster or viewers. An aggregate
`offeredRps` or conflicting ambient selector refuses before actors start.

Sparse viewers use the original quotient/remainder assignment in roster order.
Every writer tenant retains independent accepted/stored count checks, including
tenants with no viewer. Every accepted probe requires its distinct retained
clinical witness. Client evidence is required for the declared viewer assignment;
zero viewers is explicitly NOT_EXERCISED for client frames. The accepted-input observer reconciles run-marked inputs against the ordinary and probe ledgers and checks durable completion through drain.
`load/k6.log` contains structured event witnesses; `k6-native.log` preserves the
full terminal summary separately so its size cannot displace the demand marker.

## Scheduling requests and optional service limits

For a fresh discovery fixture, select `"resourceAccounting":"requests-v1"`
in the commissioning environment, binding overrides and runtime template. Use
the same value in a matrix specification and its allocation grant. Inventory,
preflight and lifecycle validation check this selection before expensive setup.
Existing inputs that omit it retain `limits-v1` accounting and capped behavior.

In request mode, the binding removes reference per-container limits. A deliberate
`resources.<role>.limits` override supplies exactly those optional limits; it does
not inherit additional reference caps. Positive CPU, memory and ephemeral-storage
requests remain necessary for this instrument's scheduling calculation. Each
supplied limit must cover its corresponding request. Actual Pod readback records
the returned resources and overhead, including LimitRange defaults. Kubernetes
quota, LimitRange and the scheduler enforce those resources; the adapter compares
the rest of the Pod spec independently.

Namespace ResourceQuota readback compares exact numeric CPU, memory and
ephemeral-storage quantities, including their `requests.*` and `limits.*` forms.
For example, `4194304000` bytes and the API's canonical `4194304k` are equal.
Scheduling round-up is not used for this comparison: even a fractional budget
change refuses. Hard-map keys, pod counts, scopes and other fields remain exact;
unknown dimensions and masked values have no inferred equality. Resource
readback refusals retain only the safe resource kind/name beside the code.

Use a **new** copy of the released commissioner source with
[`commissioning-accounting.patch`](commissioning-accounting.patch). The patch
header identifies the base source hash; retained instruments are unchanged. From
the new staging directory containing `bin/preflight.py`, apply the patch with
`git apply /absolute/helper/tools/mt-bench/kubernetes/commissioning-accounting.patch`.
Select request accounting in its environment. Its namespace quota covers requests
and existing no-provider-resource boundaries; `limits.*` quotas or LimitRange
defaults that force hidden limits are refused. The preflight retains both requests
and limits, with `null` for an unbounded limit dimension, and a separate `accounted`
vector. Attachment uses the selected vector for its grant.

The planner and commissioner use init/steady peaks, restartable sidecars and Pod
overhead for either mode. Request accounting tests scheduling fit; it is not a hard
upper bound on use, a quiet-worker reservation or capacity acceptance. Capture
actual memory, throttling, OOM/restarts and contention during the run. Native
driver/observer cgroups and owned deadlines/cleanup retain their separate bounds.
Pod-level resource budgets need their own instrument extension and refuse explicitly.

The shared-socket cohort stays at one Pod. Other multi-Pod workloads currently
refuse `WORKLOAD_REPLICA_CENSUS_UNSUPPORTED`, because role selection and the
observed Pod census need an explicit topology extension. This is distinct from
the cohort's socket-sharing requirement.

The explicit `applicationTopology: "separate-k1"` profile places API, evaluator,
realtime and tenant-admin in their own one-replica Deployments. Common intents
select it under `kubernetes.applicationTopology`; projection carries the same
selection into the existing binding inputs and frozen experiment. The render,
inventory and run selection must agree. Omitting the field preserves the cohort
profile. This profile does not admit additional role replicas or HA.

The separated profile requires the twelve named fixture workloads and checks the
four role mappings, their single application processes and absence of shared
sockets. Observation still follows each Pod through its actual controller UID,
checks container identities and refuses overlapping role Pods. Cleanup uses the
existing UID preconditions for every workload. Each separated serving role uses
the existing `cohortReadySeconds` serving window; an elapsed readiness window
inside the work deadline produces a role-specific UNMEASURED signal. Clinical
completion, authority and isolation gates retain their existing requirements.

### Standard discovery runs

Select a completed discovery case as the read-only template for tools, credentials
and deployment topology. Supply the frozen package (source/build/delivery
receipts), its captured deploy binding, a workload profile and a fresh case
directory. Each point uses the same entrypoint and the same deploy request
defaults, including the k6 Job. The directory basename identifies the run.

```bash
python3 -B "$K/experiment.py" standard "$TEMPLATE_CASE" "$PACKAGE" "$PROFILE" "$CASE" --binding "$BINDING"
python3 -B "$K/experiment.py" describe "$CASE/intent.json"
python3 -B "$K/experiment.py" launch "$CASE/lifecycle-bound.json"
```

The first command prepares and checks the run offline. An error leaves its
partial output and reason in a sibling `*.failed-*/prepare-error.json`. The
same case name can then be retried. The binding defaults to `$PACKAGE/binding`.
Use `--core` to select the checkout for a new frozen core revision. The runtime
creates unpinned Pods. Add `--reserved-worker-taint KEY=VALUE` to the first
command to allow the existing reserved worker to participate. Kubernetes assigns
the nodes and the runner records Pod UID, assigned node, Pending conditions and
observed FailedScheduling events. `K8S_POD_UNSCHEDULABLE` reports the observed
placement refusal when the readiness window expires.

Change `population.provisionedTenants` and `population.ordinaryRosterTenants`
in the profile to vary population. For realistic-v1, keeping `workloadScale`
constant keeps per-tenant cadence constant. To compare populations at the same
aggregate rate, multiply `workload.workloadScale` by the ratio of the old to
new ordinary roster size, and hold `workload.logicalPollingClients` fixed. To step
the rate at fixed population, change that scale, or use
`workload.driverPlan.writeRateScale` for writes alone. The describe command
prints the seven offered rates for the selected point.

Current P platform receipts select `platformVerification: "startup-v2"` in both
the source contract and candidate inventory. Their role rows contain exactly
`role` and `generation`, without an expiry lease. Legacy candidate contracts
retain the expiry check. A topology selection alone does not change proof
semantics. Offline profile controls do not qualify private HTTP transport,
replacement or clinical/client behavior on a live cluster; those observations
belong to the lane's frozen baseline and retained run evidence.

Focused controls use real scratch Jsonnet renders and patched commissioner code:

```bash
K8S_BINDING_SOURCE=/absolute/deployment-repository \
K8S_COMMISSIONING_SOURCE=/absolute/released/staging/ops/staging-k8s/bin \
python3 -B -m unittest discover -s tools/mt-bench/kubernetes
```

The external-fixture controls report a skip when their source is absent. A skipped
commissioner or binding control does not qualify a runtime configuration.

### Placement and fit

Kubernetes places standard runs using each Pod’s declared requests. A standard
namespace quota accounts for the rendered requests and Pod count, with room
for each controller to overlap a replacement. A LimitRange supplies omitted
container requests. Explicit requests and Pod placement remain with Kubernetes. The per-run owned-worker,
provision/serving phase-fit, node-memory and private provision-source proofs were
removed on 2026-11-18 under decision
[k8s-platform-proofs-to-deploy](../../../docs/30-design/tenancy/multitenancy-decisions.md#k8s-platform-proofs-to-deploy);
the standalone fit report and image publication belong to nightscout-deploy. Reserving a
worker follows [reserved-k8s-worker](../../../docs/30-design/tenancy/multitenancy-decisions.md#reserved-k8s-worker).
`commissioning-accounting.patch` still carries an opt-in `resourcePhasePlan` hunk
for the operator's commissioner; do not select it, because its `phase_fit` module
is gone.

## Outcome evaluator gate on Kubernetes

Decision [outcome-evaluator-gate](../../../docs/30-design/tenancy/multitenancy-decisions.md#outcome-evaluator-gate)
replaces the lifetime `failedCompletions == 0` rule and the instant midpoint
readiness rule. [outcome_gate.py](../m7-joined/outcome_gate.py) is the one frozen gate; its
identity is the SHA-256 of that file. Tenants, rate, windows, budgets and
`deadlineMs` (default 120000) are configuration under the same identity.

| component | FAIL | UNMEASURED |
|---|---|---|
| failed completions (lifetime counters at the end point) | untyped, `unknown`, hard or unrecognised reason, or a transient failure still open past the deadline | typed rows without reasons or resolution fields; a transient still open at the end inside the deadline; no end point |
| isolation | runtime reset, foreign row ready, foreign counters changed, duplicate owner | one point only |
| evaluator health | hard evaluator code or alert at the end point | missing end point |
| storage | count oracle RED | oracle missing or not GREEN |
| sampled oracle | probe `completedOutput` FAIL | missing |
| catch-up per accepted input | missing durable output at the end of drain or measured after the deadline | incomplete input coverage, timing or durable evidence |

Resolved `verification-pending` and `startup-warming` failures are counted by reason.
Their maximum resolution time describes the process lifetime. The clinical deadline
uses the current run's HTTP acknowledgement and tenant-bound durable output.
On replay, the gate checks distinct input identities against each writer's accepted
count and compares individual keys wherever the writer records are available. Until the
source declares `view.failureReasonContract = evaluator-failure-reasons-v1`
with `progress.failureReasons`, `unresolvedFailure` and
`maxFailureResolutionMs`, every failed completion is untyped and fails.

The midpoint is a signal. The runner records `load/progress-midpoint-signal.json` and stops
the driver only for a hard reason (a FAIL above, or an evaluation alert). A
not-ready owner at the midpoint continues. Raw responses are written before
any decoder reads them (`progress-*.private.jsonl`; after an early load stop, `progress-stop.private.jsonl`, then `stored-counts.json`, recorded in `stop-evidence.json`). The runner publishes `load/outcome-gate.json` and a stage summary in `result.json` before returning a failure or missing measurement. It also reports HTTP latency over all k6 shard summaries, including the exact pooled count and mean, plus the quantile range across shards.
The progress reader checks the evaluator's runtime identity, owner and foreign counters across captured rounds. It records the observed work delta, including zero for idle tenants. The workload outcome combines these checks with storage, sampled clinical results and per-input catch-up. A missing component leaves the load stage `UNMEASURED`.

`assessor.py <load>` re-reduces a retained run into a new file beside it and refuses if any original file changes. Set `outcomeGate.midpointStop` to `never` to record a hard midpoint signal and continue collecting evidence.

The accepted-input observer starts before the probe and follows run-marked writes through drain. Its Kubernetes transport brackets each read-only SQL transaction with checks of the owned namespace and Pods. Each call honors the observer timeout and the entered work deadline. The observer reconciles its inputs against the workload and probe acceptance counts. Tenants with no accepted input owe no output. [Kubernetes transport](catchup.py) · [Deadline and drain decision](../../../docs/30-design/tenancy/multitenancy-decisions.md#deadline-from-acceptance)

## One intent for Compose and Kubernetes

`toolchain.py` projects a version 1 `multitenant-experiment` into the existing
Compose runner or Kubernetes experiment contract. It starts no actor. Immutable
`application` receipt references and optional `deploymentJobs` identify source,
application image and helper image separately. `profile` owns workload and finite
phase intent. `topology` owns requested role counts. `local` holds the existing
Compose resource/observer defaults. A fresh instance supplies paths, network
identity, custody and actual deadlines. A second copy of a derived source or
workload value is refused.

The common intent recognizes discovery API counts 1–16 and evaluator/realtime
worker counts 1–8. Compose projects the selected supported counts into its normal
source-bound static receipt and exact service roster. Native Kubernetes execution
still supports the existing K1/API1 external-producer binding. A different role
topology reports `KUBERNETES_TOPOLOGY_UNSUPPORTED`; admitting its numeric intent
does not implement a multi-Pod runtime or grant capacity acceptance.

The optional `kubernetes.edge` block selects Kubernetes-only nginx
`workerProcesses` and `workerConnections`. Either field can be selected
independently. Omission keeps the exact source `auto`/`1024` bytes and adds no
edge selection to the inventory. The Kubernetes projection emits
`binding-inputs.json`, an edge overlay for the fresh binding constructor's
inputs, and carries the same selection in `manifest.json`. Merge that overlay
with the fresh instance's other constructor inputs using `std.mergePatch` before
calling `ns.new`. Preparation requires the manifest, inventory and rendered
ConfigMap to agree; forgetting the overlay refuses instead of ignoring it.

```json
{"kubernetes":{"edge":{"workerProcesses":2,"workerConnections":8192}}}
```

The same common intent can retain its independent `local` settings. Compose
projection records `kubernetes.edge` as `notApplicable` and leaves local resource
mode and nginx selection unchanged. Existing local explicit-allocation `edge`
settings keep their own contract; a Kubernetes setting adds no local CPU or
memory cap.

The binding changes only the two unique known directives from the exact
`assets/nginx.conf` source. Its original source hash remains required. The
inventory records requested and effective values and the inherited descriptor
limit as `INHERITED_OS_UNMEASURED`. The prepared packet binds the full rendered
config hash; selected-edge observation requires exact ConfigMap data and records
its observed hash. Masked config data stays UNMEASURED. Routing, trusted Host and
header handling remain source bytes.

Worker counts use the Linux nginx process-table maximum of 1,024 total child
slots. Workers, cache helpers and overlapping reload generations share those
slots, so this necessary bound does not prove that the requested workers start.
The [Unix process table](https://github.com/nginx/nginx/blob/master/src/os/unix/ngx_process.h)
and [worker lifecycle](https://github.com/nginx/nginx/blob/master/src/os/unix/ngx_process_cycle.c)
define that read-derived boundary. Connection counts use positive exact
integers within Jsonnet's binary64 carrier. Kubernetes supplies no ulimit field
here, and this source asset has no `worker_rlimit_nofile`; effective OS file
descriptor limits, worker births and connection capacity need observations in
the selected environment. The local Compose descriptor budget is not inherited
by this binding. nginx documents the
[connection/descriptor relationship](https://nginx.org/en/docs/ngx_core_module.html#worker_connections).
These settings configure a fresh fixture and do not qualify a capacity result
or change edge replicas, socket topology, source images or an entered run.

Project an intent with `toolchain.py`:

```bash
K=tools/mt-bench/kubernetes
python3 -B "$K/toolchain.py" compose "$INTENT" "$FRESH_LOCAL_INSTANCE" "$NEW_PROJECTION"
python3 -B "$K/toolchain.py" kubernetes "$INTENT" "$FRESH_INSTANCE" "$NEW_PROJECTION"
```

The Compose projection emits the normal `config.json` and existing diagnostic
receipt template. The execution owner binds its fresh receipt and uses the
existing `runner.py`. Kubernetes emits `manifest.json` for `experiment.py`.
Historical direct configurations remain supported. The C3 Kubernetes-only
`bootstrapHelper` override refuses on Compose; select the local source owner's
own compatible diagnostic image receipt there. A projection never substitutes
another source or changes PENDING to PASS.

| Capability | Integrated scope and limit |
|---|---|
| Fixed topology | Compose preserves the released K1/API1 and K2/API2 structural checks, actual mounted-file/roster/ordinal checks and finite per-instance accounting. Native K2 scaling remains UNMEASURED. Kubernetes supports the existing K1/API1 external-producer binding; another role topology explicitly refuses. |
| Configured driver | Both transports reuse the same generator, seven-shape wrapper, roster splitter and scenario/shard/phase reducer. Kubernetes runs each native k6 process inside the admitted combined native scope and bounded file/subprocess limits. Missing shard custody, changed VUs/plan and missing/dropped work cannot become a complete pass. Independent valid shard rows survive in partial reduction. |
| Percentiles | Summary merging preserves counts and shard statistics. Pooled percentiles remain UNMEASURED without an adequate merged sample definition. |
| Observation | Clinical timing starts at acceptance. The load outcomes report per-input durable coverage at the end of the finite drain, alongside stored writes, witnesses and frames. |
| Resource capture | Native driver/controller/observer cgroup CPU, memory/events and lifetime peak are captured before scope exit. Stage controller retains all surviving init/steady container states and resources before exact UID cleanup. Missing/retired counters remain UNMEASURED; independent cluster sampling is still needed for actual init/steady phase peaks. |

Launch a freshly commissioned case with its lifecycle input. The input names
the selected alignment checkout in `instrumentDirectory`, the current
`caseDirectory` (intent, environment, inventory, render, preflight and stages),
and the operator's binding, run template, tools, delivery and controller allocation. All paths come from these inputs. Set `instrumentDirectory` once.
Capture records the runtime digest. An explicit `instrumentSha256` pins a
particular runtime. Test source edits leave that digest stable.

```bash
python3 -B "$K/experiment.py" launch "$CASE/lifecycle-input.json"
```

For offline preparation, add `--prepare-only`. This writes
`$CASE/lifecycle-bound.json` with exclusive creation. Pass the bound file to
the same command to enter it, or add `--prepare-only` again to check it. The
selected checkout performs capture, lifecycle, native-scope attach, packet
preparation and scheduler readback. The operating owner supplies custody at entry. The controller keeps the existing UID-conditioned
cleanup on failure.

When the stock probe's SQL transport fails, `sql-observation-failure.json`
retains the first child's exit/timeout/output-bound classification, reported
error codes, byte counts and elapsed time. It excludes SQL, command arguments
and raw output. The read still fails as UNMEASURED; the 60-second transport
bound and 120-second clinical deadline are unchanged. Keep a waiting setup
Job's native lifetime long enough for the phases that still inspect it.

The generated clinical probe uses `adapter.py clinical-sql DIRECTORY` for its
read-only SQL bridge. Full instrument, packet, render and configuration
validation still runs for each child. Each SQL read brackets the exact selected
PostgreSQL workload, Pod and running container with namespace/owner/UID, source
image/command, controller, readiness and process-incarnation checks. The strict
clinical SELECT and oracle retain actual database/system/timeline, native source
generation, tenant and restore fences. The original query bytes pass unchanged
inside `BEGIN READ ONLY … ROLLBACK`.

The clinical bracket reads the selected namespace, workload and Pod rather than
the full UI/setup/native-load roster for every clinical poll. Full campaign
census and before/after oracles remain at their existing boundaries; the general
`sql` command retains its full census. A targeted read grants no global-roster
or capacity claim. Child transport remains 60 seconds, witness completion remains
120 seconds, and the original work deadline can shorten both observation paths.
Offline scope, controls and limitations are in the
[clinical transport record](../../../reports/tenancy/clinical-sql-transport-2026-11-19/README.md).

`jobs.py` consumes the deployment repository's registered job CLI and renderer
from its selected tool commit. `plan` emits that actual contract for bootstrap,
provision, prime, platform verification or offline verification-plan. It keeps
helper and serving image identities separate, projects command-specific inputs,
uses pre-existing Kubernetes claims and never executes a networked job. An API
job may target another image build of the same measured source/runtime tuple;
bootstrap requires its exact donor image. Wider source/API compatibility needs
its own evidence. No image/hash case list is added.

`jobs.py offline PLAN_DIRECTORY` runs only verification-plan in the selected
cached tool image, with no network and explicit finite CPU/memory. It checks the
actual capability/source response and every projected input before checking the
selected namespace/roles. Networked helper integration, registry image delivery,
provision/prime/verify transport and their uncertain-write custody stay with the
operating owner and remain UNMEASURED until admitted. The original entered
helper and source acceptance retain their original scope.

Larger prospective allocations are valid for discovery and qualification.
Measure actual hardware, competing use and phase overlap before admission; CPU
maximums do not reserve dedicated processors. Container CPU bursting under a
common Docker experiment cgroup is unsupported here. When actual shared-host
protection blocks an adequately provisioned experiment, bring the maintainer one
concrete temporary allocation/exclusive-use proposal with its owner, duration,
disruption, measurement, cleanup and restoration. Ordinary parameter choices
within existing authority need no new approval. Do not change an entered fixture.

`native_load.py` is a bounded evidence adapter for lane K's existing rendered
k6 Job and `fanout.Kube` client interface. `package()` keeps the rendered image,
placement, resources and init ordering, selects `http://edge:<port>`, and supplies
an immutable synthetic input Secret. The standalone `run()` creates its Job/Secret once;
the opt-in execution releases the predeclared suspended Job without replay,
retains raw stdout before decoding, checks namespace/Job/Pod identity and exit
custody, and emits the existing `k6.log` and `k6-summary.json` reducer inputs.
Its appended `handleSummary` exports k6's actual counters/trends in framed
chunks; it changes no workload function and includes no JWT setup data.

`native_join.py` adds an opt-in `nativeLoad` selection to the existing execution,
census and fit path. The controller, probe, SQL, completed clinical output, frames and the accepted-input
observer still run on the workstation. `assess_join()` verifies the
capture/run/script bindings and calls the unchanged `execute.assess_stage()`;
Job completion alone leaves the outcome gate UNMEASURED. The 120-second clinical
contract and accepted-versus-stored accounting remain required. All-writer
post-stop WAL/ACK coverage stays UNMEASURED. Owned namespace and cluster-trust
cleanup remain the operating owner's responsibility; Job TTL is insufficient.

One-shard `driverPlan` selections use `k6-vu-driver.js` and
`driver_accounting.configured_environment()` / `retain()`. VUs come from the offer with
`workload.driverHeadroom` (default 2 on Kubernetes). `scheduling-v1`
retains the original gzipped raw CSV, including the original byte/row bounds;
`summary-v1` selects its existing summary contract. Multiple shards refuse
before a Kubernetes read or actor creation.

The configured path requires explicit `exporter_resources` and a measured
`shell_contract` bound to the selected k6 manifest digest (Alpine `/bin/sh`,
`/usr/bin/k6`, 512-byte file-limit blocks, retained evidence hash). The shell's
hard file limit is independently read back from `/proc/self/limits`. A test-only
Node exporter uses the selected application image's builtins and receives only
the synthetic inputs and shared artifact volume, with no API token or runtime
credentials. It holds the Pod until an owned exec reader has verified each
file's exact length/hash and acknowledged the manifest, or the finite Job and
exporter deadlines expire. Raw CSV never depends on kubelet log retention.
The exporter contributes its explicit requests/limits to Pod fit and quota.

For a **fresh, uncaptured prepared case**, run `python3 -B native_join.py
/absolute/case /absolute/selection.json`, then the normal lifecycle capture and
fresh entry checks. Selection requires `version: 1`, `mode: "job-v1"`, immutable
k6 `image`, measured `shellContract`, explicit `resources` and
`exporterResources`, `deadlineSeconds`, and `imagePullSecrets`. An authored `nodeName` is optional
for legacy pinned cases. The standard command selects deploy defaults. The Job deadline must cover
the authored setup, load, graceful stop and export margin, and still fit the
remaining work budget at launch.

New cases freeze `inputCodec` as `fixture-data-v1`. The primer issues the DATA
credentials. After the controller verifies the Job, Pod, namespace and
exporter identity, it streams the selected DATA identity/token pairs to that
Pod over private exec stdin. The exporter checks its downward-API Pod UID and
uses the pinned application's fixture seed and provisioned count to generate
the IDs and aliases. It verifies the complete ordered projection against the
controller's digest before publishing a mode-0400 file in a disk-backed
emptyDir. k6 mounts that volume read-only and starts when the file exists.
The input Secret contains scripts, launch parameters, counts and a digest.
Only the original waiter mounts a scoped service-account token.

The same path supports the selected ordinary prefix and a full 10,000-tenant
roster. DATA tokens stay out of Kubernetes objects, arguments, logs and
receipts. A fresh case built from an older selection records the requested codec in preflight
and freezes the private channel. Existing raw-v1 and gzip-v1
packet declarations keep their recorded codec for historical verification.

The offline preparer appends only a suspended test Job and namespace-local
waiter RBAC. It keeps every application workload unchanged, adjusts the exact
Pod request/quota/envelope, and runs the original application binding checks
beside the test Job's own exact declaration checks. Do not install the lane K
serving stack or change the application tuple. Kubernetes places the complete test Pod when the Job is released.

`execute.execute()` retains the concurrent stock probe and midpoint observer.
Only the opted-in configured-load call goes to the native Job; its original
wrapper/accounting supplies schedule start/end markers. The declared suspended
Job UID is atomically tested before release. A hard midpoint failure atomically
tests that UID and suspends the Job, then observes the k6 writer terminate (or
the original owned Pod disappear) before returning. An unobserved stop stays
UNMEASURED and retains the original failure. No failed workload is replayed.
Job backoff is zero, replacement waits for Failed, and test Pods have a finite
termination grace. Runtime application Pod and container identities stay strict;
only the exact declared test Job has a separate dynamic census.

The accepted-input observer runs across probe and driver traffic. After both writers exit, the controller reconciles storage, checks remaining clinical work through drain, captures terminal progress and calls `assess_stage()`. `assess_join()` adds capture/run/script/hash checks. The init
waiter alone gets `jobs/get` for `provision` and `primer` in its namespace;
the split verified-serving binding also names `verification` explicitly and
requires its completion before accepting primer readiness. Its lifecycle waits
for verification, then serving readiness, then releases the standalone primer.
Legacy bindings retain their original primer-ready gate. The
exporter receives no Kubernetes API permission. The test Pod uses component
`load`, so it does not match the application's
private admin/internal `operator` selectors. One additional owned
`NetworkPolicy/native-load-to-edge` explicitly permits only same-namespace,
same-run load Pods to reach the same-run edge on its selected TCP port (8080
for the qualified binding). Every application policy stays unchanged. The new
policy has exact declaration and live spec-readback checks; a missing or changed
source, target, port or namespace refuses. The original binding's private-plane
checks also inspect it, including when declarations are nested in an array.
Setup actor lifetimes still
belong to the current binding and must cover the complete owned point. Keep
owned namespace/trust cleanup even after Job completion. Fresh native live
compatibility and capacity qualification remain UNMEASURED.

An `ipBlock` match is not treated as evidence of Pod ingress. Cilium documents
that its default excludes intra-cluster Pod and Node addresses from such rules;
see the [Cilium policy reference](https://docs.cilium.io/en/stable/network/kubernetes/policy/).
The policy controls model explicit Pod selectors and same-namespace scope.
Actual CNI connectivity remains a separate live control owned by the operator.

When the read guard masks native Secret references or projected keys, only the
named owned native Job or Pod gets a bounded private spec read. Namespace and
object UIDs bracket that read, and the existing strict declaration comparison
checks the actual reference, token mounts, resources and security fields. A
redacted reference never counts as exact evidence. Native load and artifact
readers use the same adapter. `experiment.candidate_pin(inventory, binding_ref)`
resolves a split binding's full candidate pin from its hashed materialized
receipt; pre-entry tools must use that receipt instead of the legacy
`inventory.candidateContract` field.

Explicit `startup-v4` retains the source client's version-1 startup receipt and
the native completion-receipt requirement. The source owns v4 role digests,
presentation catalogue checks and tenant-floor proof authority. The helper does
not issue a tenant-floor backfill. New-image runtime qualification remains with
the run owner.

Focused offline controls: `python3 -B -m unittest -v test_native_input test_native_load test_native_files test_native_join` from this
directory. Set `NS_NATIVE_K6_TEST_BINARY` to an existing pinned local k6 binary
to execute the real summary/event export control; it opens no network listener.
Set `NS_NATIVE_K6_IMAGE_BINARY`, `NS_NATIVE_IMAGE_BUSYBOX` and
`NS_NATIVE_IMAGE_LOADER` to the inspected cached image's extracted binaries for
the real configured-wrapper/CSV and hard-file-limit controls. The former uses a
synthetic loopback HTTP fixture and the original accounting reducer.
Set `NS_NATIVE_NODE_IMAGE_BINARY` to the inspected application image's Node
binary (or its own loader/library wrapper) to check restore/export with that
runtime. The 10,000-row decoder control imports the original driver/workload and
checks its original named SharedArray; it issues no HTTP requests or setup.
These controls qualify the adapter boundary, not Kubernetes/application behavior
or capacity.

For an isolated standard point, use the existing experiment launcher with
`caseDirectory=.../RUN_ID/raw/RUN_ID`. The terminal result and cleanup receipt
are published beside `raw/`. The native receipt includes the namespace,
labelled cluster trust, host unit and port-forward observations. The load
report retains scheduling drops, per-executor start times and attributable
actor transitions alongside the independently judged product components.

The joined disposable binding uses `secrets.sh seed`, waits for the provision Job and role readiness,
then runs the deployment's primer as an init container using the private admin and API Services.
The reader mounts the same disposable results volume read-only and transfers the DATA roster for
the workload. Kubernetes removes the volume when the fixture Pod is deleted.

For a cold CSI fixture, commission matching claims and Secrets with the deployment's fixture runbook.
Use `experiment.py prepare INTENT INSTANCE NEW_PACKET --existing-fixture` on the running, operator-owned
namespace. The instance selects that namespace, its run label, the rendered inventory and the workload's
ordinary edge endpoint. Preparation projects DATA credentials from the existing results claim and the
SQL reader settings from the running roles. The namespace stays with its owner. The resulting packet
uses the ordinary observe, access and bounded run commands. Four bound native snapshot/clone claims
identify restored fixture reuse.

To reuse a fixture across fresh standard namespaces, add `--fixture-seed NEW_DIR` (with
`--storage-class` and `--snapshot-class`) to `experiment.py standard` for one seed run. It
provisions and primes on four labelled claims, stops every role, snapshots the claims through CSI,
sets their contents to Retain under the `nightscout.org/fixture` label and writes the handles, the
original Secrets, the PostgreSQL image digest and the source commits to `NEW_DIR` (private). It
runs no traffic. Each later run adds `--fixture-restore DIR`: the controller creates those
Secrets, binds the handles in the new namespace (`fixture.imported`), clones the claims and starts
through the ordinary provision Job and primer. A restore refuses another population or PostgreSQL
image. Cleanup deletes the namespace and the run's labelled contents; `fixture_copy.py delete DIR
CONTEXT` ends the fixture and the CSI driver deletes the provider snapshots. Snapshots and restored
volumes are billed storage.
