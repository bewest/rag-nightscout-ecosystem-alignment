# Remote PostgreSQL stream calibration

> **NOT RUNNABLE (2026-11-19).** This path imports `tools/mt-bench/m7-joined` modules that the
> simplification round deleted: `orchestration_binding`, `evaluator_idle`, `evaluator_opportunities`, `discovery_rest`, `diagnostic_resources`, `experiment_batch` and `completed-oracle-v2-control.cjs`, plus adapter seams built on them (`opportunity_collector`, `enabled_idle`, the resource wrappers, the local remote projection in `run_configuration.py`). Every module here raises `ImportError` at import, and its
> tests skip, rather than half-work. Maintainer decision: port later, do not delete. The port target
> is the single assessor (`m7-joined/assessor.py`) and its raw event format (accepted, stored, output,
> frame, access, datastore, readback); the k6 roster now carries each tenant's JWT
> (`m7-joined/jwt_tenants.py`). The round's base, `ea2231e834`, still has the deleted modules.

This is a separate diagnostic extension of the existing external-generator path.
It preserves sealed M7 and the existing external profile. Its unchanged default prepares1000 tenants and2000 logical stock polling clients.
Explicit file plans admit10,1000,3000,5000 or10000 tenants with two clients per tenant.
These are supported preparation parameters, not measured capacity or a tenant ladder.

Strict reporting admits only the enumerated source/image presets in
`transport.py`. The legacy pair permits serial priming only; qualified primer
presets permit the concurrency checked there.

Explicit `reportMode: "discovery"` admits a configurable source/image **request**.
It requires the full workload/resource plan and an identical
`remoteReportMode: "discovery"` in the existing diagnostic authorization. Tenant
count (1–10000), client count (1–8), finite cadence, rate and duration travel through
the existing caller, worker, helper parser, probe and reducer. Change the private
configuration and its genuine bound authorization; do not edit source constants.
Strict presets retain their existing limits.

Discovery source admission requires actual exact Git commit objects, evaluator
inspection version 2 with due/job fields, `build.assertCleanSource`, actual app
image identity with both core and deployment labels, the pinned PostgreSQL image,
and verified dependency custody. Before ingress, traffic export or runtime, the
SUT archives the configured commits, executes that deployment's
`tools/prospective-plan-documents.js`, and gives its generated documents to that
core's `nightscout plan check`. This executes the published schemas, real role
loaders and preflight without starting services or connecting to a database.
Failed commands refuse; their raw output stays in private
`source-contract-checks/` under the cell. An attachment may resolve its deployment
repository from the build verifier's checked `.overlay.json`; historical captures
are not rewritten.

The paired controller also requires the existing hashed `sourceQualification`
record with exact core/deploy/image, canonical build and image-check return codes
of zero, no image-label mismatches and both exact labels. Compact image metadata,
SHA-shaped strings and a caller-authored claim do not supply that evidence.
A missing qualification stays missing. These checks qualify isolated synthetic
discovery only; functional, runtime and capacity acceptance remain separate.
Optional observations stay unknown/partial, and source, authority, clinical or
data mismatches still fail.

The source-bound parser and workload seams adopt committed cf7d975, d652a025 and
dfbfd84; no application code is injected into either image. The default uses
10 seconds of warmup,30 seconds of observed idle, and310 seconds of load,
ACCEL=1, HOT_FACTOR=1, probe cadence 300000 ms, sampler cadence 2 seconds,
and no restart. Cold deployment stage timings precede these steady windows.
In strict mode, an optional binding `workload` contains exactly `cadence`, `primerConcurrency` and
`resourcePlan`. Cadence may set `loadSeconds`1–3600 and `offeredRps`1–10000;
other strict cadence, seven request shapes, two stock clients per tenant and no-restart
behavior stay fixed. A resource plan carries its reference, exact cohort/client
counts and distinct SUT/driver inventory identities with CPU/RAM. The controller
checks those against its actual inventory. The plan is not measured headroom.
Nondefault parameters require this full binding and identical `remoteWorkload` in
the genuine receipt. The helper compares actual parsed arguments and prepared
manifest fields with it. The traffic generator receives the same duration and
rate through actual probe argv and k6 environment; provisioning concurrency reaches
the existing canonical prime argv. Missing or changed parameters refuse before
preparation. Expiry limits every phase; expired workload authority does not prevent
exact-owned cleanup.
The canonical deploy sequence includes evaluator pool initialization after
commission and before API startup. Existing image, source, dependency, settings,
state, ownership and receipt checks remain in force.

`cell.py` runs on the SUT as the existing UID/GID 1000 runtime account. It uses a
local Unix Docker endpoint. `generator.py` runs on the separate generator under
the existing trusted supervisor, with stock traffic children under nsload UID/GID
1001 and no supplementary groups, sudo, Docker socket or application state.
The generator needs the same recorded Node/npm binary hashes and exact source
lockfile dependencies as the SUT; version names alone do not qualify it.
The trusted supervisor creates two distinct empty npm configuration files outside
the traffic-writable dependency directory. Their parent and files remain root-owned
and readable by the traffic group. The supervisor verifies their identity, empty
content and modes before and after locked installation. The child keeps its restricted
environment, UID/GID1001, disabled install scripts and exact lockfile.

The SUT retains its exact collector edge on 127.0.0.1. `ingress` adds one approved
private IPv4 edge, records the full before/after hash and JSON patch, and retains
normal full-compose verification. Actual `ip -j address show` output must
match the receipt-approved interface, MAC and assigned private IP. A private IP
from another host fails. The provider firewall must separately admit only the
actual generator identity/private IP to this exact port, plus controller SSH22.
The SUT raw/PREROUTING chain must filter that original destination before Docker
DNAT: first PREROUTING rule matches the exact destination/port on every interface
and jumps to the nonce-owned chain, which accepts only the approved NIC plus
generator /32 and drops the rest. NIC/admission are re-read before traffic and
final qualification. `transport.firewall_rules(binding)` emits
the three exact rules to install after root review; `firewall_check` reads the
actual table and refuses missing or broader rules. No firewall is installed by
file preparation. No provider API token is staged on either host.

The genuine existing `AUTHORIZED_DIAGNOSTIC` receipt must also bind
`remoteProfile`, `remoteTransport`, `remoteExtensionSha256` and, for explicit
parameters, exact `remoteWorkload`. This extension
never creates authorization or acceptance. A proposal with pending exports,
allocation, NIC inventory or receipt cannot execute.

Future execution uses these SUT entry points after root review and allocation:

```bash
python3 tools/mt-bench/remote-pgstream/cell.py prepare --binding BINDING --cell NEW_CELL \
  --core-repo CORE_REPO --core-commit CORE_SHA --deploy-repo DEPLOY_REPO --deploy-commit DEPLOY_SHA \
  --image APP_IMAGE_ID --postgres-image PG_IMAGE_ID --receipt GENUINE_RECEIPT \
  --profile pgstream-sample --run-purpose discovery --tenants 1000 --replicas 1 \
  --warmup-seconds 10 --idle-seconds 30 --load-seconds 310 --accel 1 --hot-factor 1 --sampler-interval 2
python3 tools/mt-bench/remote-pgstream/cell.py deploy --binding BINDING --cell NEW_CELL
python3 tools/mt-bench/remote-pgstream/cell.py export --binding BINDING --cell NEW_CELL
```

Prepare selects a free loopback port. Read the actual prepared owner.json port,
update the same controller-owned binding and exact-port provider/SUT admission
before deploy; do not substitute an inferred port. The receipt binds transport
identity, not a guessed free port. Do not use historical pilot-ledger prepare,
external-setup or its legacy remote-pilot campaign.

The controller `pgstream-caller.mjs` is the bounded executable caller. Its
`bundle` command reuses the existing committed source-pack exporters and checks
actual archive bytes. Its `run` command uses existing SSH/scp/Session transport,
checks explicit SSH key bytes against the root-owned known-hosts file, stages
both hosts, installs the recorded Node binary, loads/inspects app and PostgreSQL
IDs, prepares the new cell, reads its actual port, invokes root-owned exact-port
provider admission, installs/checks host admission, deploys all normal roles,
exports/transfers six traffic files, starts the bound two-per-tenant stock polling clients and the
seven-shape workload at its bound duration and offered rate, imports seven result files and collects both hosts.
Every success/failure path then attempts exact-owned Docker cleanup and invokes
the root-owned exact provider-ID deletion hook. The controller relays phases,
never HTTP or socket traffic. Requests go directly to the approved private IP.

The finite worker is `pgstream-worker.py`; historical pilot-ledger/external-setup
are not called. Runtime Docker/package versions are retained in private evidence.
Driver FD/socket/NIC headroom remains UNMEASURED until the separate sampler joins.
The root still owns allocation, cost/deadline, provider admission and deletion.
No provider credentials travel to hosts. See controller `PGSTREAM-CALIBRATION.md`
for caller inputs and hook output contracts.

The generator returns actual per-write, per-client frame identity/content in its
private probe result. The SUT reuses `completed-oracle.cjs` after the steady
bookend to join selected acknowledged writes with storage, durable evaluator
output/frame and BG-now mean/last. Missing client evidence or altered BG-now fails
qualification. The clinical scope remains selected witnesses, not all-roster
clinical equivalence. Due opportunity and reconnect are UNMEASURED.

SUT SQL request bookends, cgroups, processes and IO stay in its clock domain.
Driver write-to-frame uses its local monotonic clock. Write-to-evaluation is
UNMEASURED; cross-host timestamp subtraction is prohibited. Driver headroom
integration is REST-owned. Existing generator cumulative network samples include
control traffic and cannot prove NIC saturation or available capacity.

Focused checks (no services, network, SQL or Docker):

```bash
PYTHONPATH=tools/mt-bench/remote-pgstream python3 -m unittest discover -s tools/mt-bench/remote-pgstream -p "test_*.py" -v
node --test tools/mt-bench/external-generator/test_recovery.cjs
```

Measured source checks do not qualify a remote deployment. Startup timing,
throughput, p95, client completion and real host headroom remain UNMEASURED until
root runs the reviewed remote calibration.

Discovery external-service topology also accepts the existing explicit
`local-qualification-external-pgstream-6cpu-10g-v1` profile. The caller, worker,
receipt and prepared cell retain that exact name; the shared resource producer
sets the actual role limits and the collector verifies effective cgroups. This
selection retains diagnostic scope and grants no capacity acceptance. The default
4CPU/8GiB selection and strict reporting are unchanged.

Current single-process native preparation selects the `external-service-native-v1`
helper dependency profile with the external-service topology and an explicit
resource allocation. The packet binds the version-2 diagnostic configuration
to exact built-image evidence and accepted-work reader dependencies. Its default
path binds the reviewed source acceptance and sends that original hashed file
only to the SUT. Explicit `nativeSourceAdmission: diagnostic-build-v1` instead
retains exactly `sourceAcceptance: {status: PENDING}` and mirrors the selection
in `remoteNativeSourceAdmission`. The paired controller validates actual
image/build/source-plan/absence evidence and transfers a separate hashed
`source-build-proof.json`; no source-acceptance PASS is manufactured. The worker checks both revision labels again after image import.
The controller and extension still require the resource owner's genuine
diagnostic authorization and finite reviewed transport scope.

The SUT records the native producer and evaluator identities and effective
container limits before load. The existing reader checks native accepted and
completed work and sampled due opportunities in both idle and load. It joins
selected completed output with the stock viewer's exact callback, transport
incarnation and monotonic delay. A missing clinical or independent writer-count
proof refuses the native smoke. Outcomes for unobserved due events, all-writer
WAL-to-intake coverage and cross-host write-to-evaluation latency remain
unmeasured. The remote worker requires the separate driver's actual Docker
CPU, memory and no-swap readback for an explicit allocation.


### Realistic cadence and driver shards

Discovery workload bindings accept the existing `realistic-v1` mix and
`driverShards` from the canonical runner configuration. The realistic mix keeps
acceleration and hot factor at one and refuses an aggregate `offeredRps` override.
Unknown selectors, ambiguous mixes, noninteger shard counts and counts outside
1–16 or above the tenant count refuse. Strict historical presets keep their
existing contract. The local VU scheduling trace selector remains local-only.

For more than one shard, select the explicit external pgstream topology and
include exact `driver_shards.py` and `contract.py` hashes in the existing helper
dependency record. The remote projection derives these two hashes from its
selected instrument and refuses a conflicting supplied hash. The paired caller
and worker mirror the complete cadence, including the optional logical viewer
count, to the actual helper parser. The driver passes `M7_WORKLOAD_MIX` to k6.

The trusted generator derives contiguous readonly roster slices from the one
verified traffic roster. It reuses the shared shard planner and script inside
one existing admitted k6 container. CPU, memory, no-swap, UID, owner, image,
mount, cleanup and finite lifetime checks remain on that container. The exact
canonical shell program, environment and roster hashes are checked before
launch; an arbitrary entrypoint or changed program refuses. No additional
traffic file, database credential or provider credential is exported.

Each shard retains its own summary, log and exit code. The shared reducer creates
the aggregate summary only when all shards exit successfully. Counters and
weighted means reduce the retained fields; each reported merged percentile is
the largest shard statistic. The legacy `quantileBounds` field retains its range
across shards, not pooled-percentile bounds. `pooledPercentiles` remains
`UNMEASURED` without raw samples and a verified definition. This method makes no
claim about a particular k6 percentile algorithm. The paired
worker transports every selected shard artifact plus the hash-only roster
record through its existing bounded result archive. Missing or failed shards
remain visible and do not become zero traffic.

This tooling support starts no remote job and proves no operating envelope.
Use a new plan, helper digest, receipt and paired controller after changing the
selection. Preserve entered run inputs and all independent clinical, stored-write
and exact client-frame checks.


The optional `cadence.workloadScale` bounds a uniform rate bracket to 0.25–8
when `workloadMix` is `realistic-v1`. Its default one preserves nominal cadence;
other factors scale all seven intervals together and retain the fixed roster,
viewers and resource limits. The caller, worker, helper and k6 environment mirror
the exact value. Dropping the worker flag, changing the receipt or changing the
canonical driver environment refuses before entry. `shapeCycleMs` in the driver
preallocation declaration is the selected, rounded time unit after scaling.
A scaled point is a rate bracket, not a sensor-cadence capacity claim.

### Explicit remote static K1/N1

Native discovery supports only `staticTopology: {kind: static-hash-v1, workers: 1}`
with the paired `remoteStaticTopology` receipt and `limits.staticWorkers: 1` plus
`apiReplicas: 1`. It requires an authored allocation with socket-edge and without additional
serving ordinals. The ordinary Compose definition retains a dormant placement
operator, so its resource row stays reserved; the actual launch excludes it. Other remote K/N
shapes refuse; the helper retains exact source-pair qualification.

The projection, caller binding, worker CLI and actual cell parser bind the same
selector and configuration digest. The ordinary product generator, real published
plan parser and mounted role/producer documents remain authoritative. The remote
launch plan includes socket-edge and skips retired pool initialization. Source
slot/ordinal/peer checks run after bootstrap; actual role/edge census and private
configuration contexts run before ordinary traffic. Native inspection v3 preserves
configured count/ordinal separately from unknown peer liveness.

Source and synthetic-host controls prove those paths and refusal/restoration.
Actual remote startup, transport, resource observations and delivery still need a
finite tiny qualification on the selected image. This support grants no capacity
and does not qualify remote K2/N2. Entered helpers, source and clocks stay fixed.
### Native driver kernel counters

The existing trusted root supervisor adds optional `driverCgroup` observations
inside `generator-metrics.json`; the existing worker export retains that file.
Traffic children keep their original user and receive no Docker, SQL or credential
authority. Each measured row qualifies the exact creation intent, full container
ID, owner nonce, pinned image, canonical command, mounts and security, then checks
the host PID birth and cgroup path before and after the kernel reads. A changed
identity refuses the observation. Explicit driver CPU and memory selections must
also match the kernel quota and memory cap.

Rows retain cumulative `cpu.stat` counters (including `nr_throttled` and
`throttled_usec`), `cpu.max`, `memory.current`, `memory.peak`, `memory.max` and
`memory.events`. They cover the k6 container and all of its selected shards, apart
from the probe child and SUT. The memory peak covers the container lifetime;
interval CPU/throttling deltas require two measured rows with identical identity.
Each row retains the monotonic CPU-counter read time and kernel read span, so
interval normalization need not use the later Docker qualification timestamp.
Missing/unsupported files or absent actors are `UNMEASURED` with a reason and no
counter substitution. Docker-stats and native readback availability stay separate.
Source controls cover owner/image mismatch, birth change, missing peak, unsupported
cgroup version, missing CPU counters and unlimited quota, with restoration. Actual
remote qualification of these new fields requires a new frozen point; historical
commissioning captures retain their original scope.
