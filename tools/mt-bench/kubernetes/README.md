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
by the earlier of the packet and Job deadlines. Set the Job's finite
`provisionDeadlineSeconds` at commissioning to cover setup and waiting.
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
The successful receipt binds the privately exported DATA roster to the run,
namespace, Job, Pod and container. Access and load verify this receipt.
Preserve the source lock and uncertain-write journal after an interrupted
request. Commissioning owns acknowledgement of the waiting Job. A previously
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

Set `profile.phases.cohortReadySeconds` in a fresh intent to give the serving
cohort StatefulSet an explicit Pod Ready window. The controller uses the time
remaining on its original work deadline if that deadline comes first. The
legacy window is 300 seconds. The lifecycle verifies the hashed intent before
entry and records the selected window and effective deadline at the wait.

Fresh intent also accepts positive integer seconds in
`profile.phases.startupWindows.kubernetes`. Set `workloadReadySeconds` for
other unselected workload waits, or `primerReadySeconds` and `dataPrimerSeconds`
for the primer Job and DATA actor. `roleExportSeconds`, `platformVerifySeconds`,
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

For a fresh discovery workload, opt into an observation phase before ordinary
traffic with `profile.phases.preloadConvergence`:

```json
{"contract":"strict-preload-convergence-v1","seconds":1800,"intervalSeconds":15}
```

Include this selected time in `profile.phases.workSeconds`. The phase observes
the real source without dispatching work, retains every strict sample and saves
exact source bytes privately before decoding. It requires two complete strict
whole-cohort ready views with completed acquisition credit, then runs the normal
initial strict check fresh before creating the driver. The selected phase,
original work, cleanup and active Job cutoffs bound all observations. A late
response cannot admit traffic. The packet records the effective window, stop
reason, raw bytes, capture policy, source identities and command bound.

Historical failed-completion counts remain visible and prevent a qualification
pass. Unchanged valid historical counts can admit execution; an increase,
decrease, reset, poison, unknown source code or identity change refuses it.
This phase does not change the later clinical or load assessment. Omit the
selection to retain immediate initial readiness behavior; that check now also
retains its raw response and bounded refusal evidence.

Set `profile.phases.accessSetupSeconds` to give the first and last selected
socket witnesses an explicit warm-up window. The native client connects to
both exact hosts without credentials first. It may retry HTTP 403 while it
waits for a positive connection and records each host's attempts and elapsed
time. Expired setup and persistent refusal stop access. The runner then
checks both own-token exchanges, both cross-tenant refusals, and the full
connected zero-foreign-frame observation. The access window has its own
budget and remains within the fixture's entered work cutoff.

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
another point. The explicit setup allowance covers viewer priming and the
remaining native JWT setup. The entered absolute work cutoff bounds both.
`drainSeconds` bounds the final wait. The inherited probe checks an individual
write for up to 120 seconds. A longer requested drain records PARTIAL. A
shorter run can end at its declared cutoff with an incomplete ledger.
All-writer clinical drain requires its own observation. The frame recorder
retains its explicit overflow refusal.

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

`claims.cjs` reruns `completed-oracle.cjs` over raw independent SQL rows and actual
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
| `actorCeilings: {hostId: {millicpus, memoryBytes}}` | This batch's combined native driver/observer allocation per host |

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

Load assessment also joins the original M7 HTTP accounting, offered-work and
settings-fingerprint reducers. Every selected scenario and JWT setup must have
observed attempts, settled expected responses, source-counter reconciliation,
no dropped work and an observed matching source-derived settings fingerprint.
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
zero viewers is explicitly NOT_EXERCISED for client frames. Selected clinical
probe outcomes and evaluator progress do not qualify ordinary all-writer intake,
due work or fixed-target drain. The operating collector owner retains that work.
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
supplied limit must cover its corresponding request. Actual Pod readback preserves
the complete resources object: injected LimitRange caps and changed requests
remain refusals.

Readback compares exact quantity values, so API normalization such as `0.5` CPU
to `500m` or `0.5Gi` memory to `512Mi` is accepted. Observations retain the raw
returned values. Added limits and real quantity changes still refuse.

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

Focused controls use real scratch Jsonnet renders and patched commissioner code:

```bash
K8S_BINDING_SOURCE=/absolute/deployment-repository \
K8S_COMMISSIONING_SOURCE=/absolute/released/staging/ops/staging-k8s/bin \
python3 -B -m unittest discover -s tools/mt-bench/kubernetes
```

The external-fixture controls report a skip when their source is absent. A skipped
commissioner or binding control does not qualify a runtime configuration.

### Explicitly owned worker

The optional `ownedWorkerPlacement` contract tests placement on one separately
acquired DigitalOcean Kubernetes worker. Select it only after a complete
earlier provider and Kubernetes inventory establishes that the pool and Node
are new. Prepare a private proof with the guard's named Node read, a fresh
whole-cluster Node/Pod census, the provider cluster and pool responses, and the
exact infrastructure Pod/controller identities reviewed for this fixture. The
provider evidence must explicitly report `auto_scale: false` and one worker.
An omitted flag leaves fixed-pool custody unmeasured.

Use a fresh copy of the exact phase-patched private commissioner and its fixture
constructor with the [owned-worker patch](commissioning-owned-worker.patch).
Copy `owned_worker.py` and `owned_worker_view.py` from this same instrument into
the new commissioner's `ops/staging-k8s/bin/`. The patch paths are relative to a
directory containing `ops/` and the retained `prepare-private-case.py`. The
focused control verifies the original file hashes before applying the patch.

The constructor's `--owned-worker-placement` consumes the private selection by
file. It binds the selected node name and lane label and authors one
`Equal/NoSchedule` toleration per workload. Preflight joins cluster, pool,
provider node and Kubernetes Node UID, checks the taint and workload templates,
and then evaluates the existing resource fit. `collect.py --owned-worker-node
NODE` retains the scoped, projected Node read beside its ordinary inventory.
The same guard is used before lifecycle creates and during runtime observation.
Its selected read mode emits placement and ownership fields only. A wrong UID,
label, taint, cordon, foreign or missing Pod, incomplete census, or unmeasured
provider proof refuses admission. The lifecycle keeps namespace UID cleanup
available when a worker check fails.

The taint constrains ordinary scheduling. Pods with direct node bindings or
wildcard tolerations can still appear, so each check uses the full worker Pod
roster. Placement evidence is bounded to the times it was observed. Provider
acquisition, image delivery, and managed-worker integration have separate
custody and verification. This tool issues read commands and retains no
capacity acceptance.

### Provision and serving phases

The existing lifecycle publishes provisioned Secrets and waits for the provision
Job to complete before it creates admin, primer or serving workloads. A fresh
commissioning environment can select
`"resourcePhasePlan":{"contract":"provision-before-serving-v1"}` to account
that ordering. Omission retains the full simultaneous-envelope calculation.

The selected plan preserves full namespace quota, per-role requests, Pod slots
and the native allocation grant. Preflight separately reports the per-node
provision and serving peaks used for fit, including retained memory-backed
`emptyDir` bytes as memory and disk-backed `emptyDir` bytes as local storage.
Possible disk file-cache residency is a separate sensitivity, not an additional
pinned-memory quota. Existing worker reserves, sampled usage and pressure checks
remain in force. A snapshot establishes neither a reservation nor future use.

The contract supports the rendered single provision Job with one completion,
one parallel Pod, no retries and no restartable sidecars. Lifecycle binding
checks the complete stage partition, resource projection and publisher/controller
hashes. The phase hash also binds the complete authored Pod templates: executable,
image, arguments, environment, source volumes, mounts and security settings.
Live source comparison normalizes explicit API defaults and equivalent resource
quantities, then requires the authored source. Server UID/version/controller
metadata and the existing service-account projection retain their separate rules.
Before later resources are created, the controller retains an exact
namespace/Job/Pod/container receipt: Complete Job, succeeded Pod, all declared
containers terminated successfully with no restarts. Every later install and
runtime observation checks that receipt. A replaced, running, failed, terminating
or overlapping provision actor refuses. Absence alone is insufficient; a retained
terminal proof can outlive its exact Pod while the same Job remains complete.
Existing downstream Pod-roster checks still apply.

Runtime display reads remain redacted. The selected phase captures a private
0600 source scope during attach and uses `phase_source_private.py` to compare
the current raw source in memory. This fixed port can only GET the bound
namespace, `Job/provision` and the captured provision Pod. Its output contains
typed results, identities and hashes. A nonce and pre/post identity checks bind
each proof to the current guarded whole-namespace observation. Missing tools or
unavailable evidence refuse as `UNMEASURED`; observed source, identity or proof
changes refuse as `FAIL`. Redaction never acts as a source wildcard. The retained
terminal receipt still permits verified Pod garbage collection with the same
Complete Job and no other provision owner Pod.

Lifecycle configuration captures and checks the helper and existing tool hashes
before actors. Keep the runtime helper with its frozen instrument; the private
commissioner below still requires only its two named modules. The port retains
the existing per-GET timeout and original phase/work deadlines. It adds six
private GETs and three guarded reads per observation; SQL brackets each read
with two observations. `test_phase_source_private.py` uses a retained raw pair,
the exact display redactor and inert API transport to check this boundary. Its
timing measures fixture overhead, not cluster latency.

Copy `phase_fit.py` and `resource_budget.py` from the same frozen helper into the
new commissioner's `bin/` directory. The complete
`commissioning-accounting.patch` includes this opt-in path for its declared base.
The separate [phase-only patch](commissioning-phase-fit.patch) targets the exact
already-patched operator base identified in its header and preserves that base's
volume and diagnostic guards. Use one applicable patch on a fresh source copy;
retain the original. `test_phase_fit.py` and the selected commissioner controls
exercise the stage, fit, terminal proof and changed-input boundaries without
cluster actors.

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

Use `examples.py --help` to generate 500, 1,000, 3,000 and 10,000 inputs from actual
selected receipts, an existing local configuration and an explicit prospective
envelope. Population, sparse/full viewers, realistic rate multiplier, duration,
setup/drain/work/cleanup, per-scenario VUs and driver shards are arguments. The
examples use 900 seconds each for setup and drain. They select a 60,000 ms
producer acknowledgment budget unless the input already selects one. Use
`--ack-timeout-ms` to select a different value. The generator prints these
values beside the output path. Actual allocations and qualification remain
with the execution owner.

```bash
K=tools/mt-bench/kubernetes
python3 -B "$K/examples.py" --application "$SELECTED_APPLICATION" \
  --local-config "$LOCAL_CONFIG" --envelope "$PROSPECTIVE_ENVELOPE" \
  --output "$NEW_EXAMPLES" --driver-shards 2 --full-viewers
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
| Observation | Per-write clinical/client proof retains its strict 120-second contract. A longer finite drain is admitted and reported PARTIAL for that observer. Accepted/stored ordinary writes, witnesses, frames and independent rows retain their own results. No all-writer clinical drain is inferred. |
| Resource capture | Native driver/controller/observer cgroup CPU, memory/events and lifetime peak are captured before scope exit. Stage controller retains all surviving init/steady container states and resources before exact UID cleanup. Missing/retired counters remain UNMEASURED; independent cluster sampling is still needed for actual init/steady phase peaks. |

`lifecycle_config.py capture INPUT NEW_BOUND` freezes a prepared instance's
files, exact released instrument, source, tools, binding, native allocation and
controller bytes. `check NEW_BOUND` rechecks them. `lifecycle.py NEW_BOUND`
executes the existing stage order, calls `attach.py` under the configured finite
native scope and records the first classified failure before independent
UID-conditioned namespace/trust cleanup. Snapshot freshness and actual fit are
still checked at entry. No case-name list or inherited tiny allocation is used.
The operating owner supplies aggregate host/cluster admission and live custody.

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
