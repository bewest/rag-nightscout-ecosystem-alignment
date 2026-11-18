# Deployment scenarios and rig testing

*Contributor-facing living runbook. Deployment structure and commands are
**read-derived** from cgm-remote-monitor
`151de0248a1e4301c85b5c638185eec3ca8c38e6`, with the nginx edge-network correction
in `4935aa77049c66793669a7be940e40ed6ba5b386`, inspected 2026-11-07. Executed
results retain their own source in the linked records. The [accepted cold
Compose measurement](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-cold-accepted.json)
records the later ed2 implementation, including its Host-preserving demo sender.
Architecture/evidence grooming: 2026-11-08; no new runtime campaign was run.
This document implements
the documentation scope of MT-DOC-DEPLOY; current claims live in the
[work queue](../../../queue/work-queue.yaml) and
[delivery dashboard](multitenant-delivery-dashboard.md).*

## Choose the experiment

| Scenario | Purpose | Boundary |
|---|---|---|
| Existing single-tenant installation | Compatibility baseline for a selected rig/client | Existing MongoDB deployment and client configuration; `nightscout single` remains the default. |
| One-host synthetic Compose preview | Exercise separate services, browser/API/socket paths and tenant-local restore | Fixed participants, private Unix sockets, direct PostgreSQL and locally generated credentials. [Cold functional acceptance](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-cold-accepted.json) passed on ed2; real-client, capacity and production admission have separate gates. |
| Headless client lab | Compare pinned clients against the admitted API surface | Follow the [binary client lab](../../../tools/lab/m4-client-binaries/README.md); its evidence does not establish every mobile device or every new source head. |
| Physical mobile or pump/CGM rig | Verify the chosen client, network path, upload/history and reconnect behavior | A separately recorded experiment using synthetic input. Device execution is not implied by source-pattern replay. |
| Multi-host, orchestrated replicas or failover | Explore later deployment design | Proposed topology: the current private socket roster is a one-host contract, not distributed discovery or HA. |

The [application Compose guide](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/deploy/multitenant/README.md)
owns runnable packaging instructions at the ed2 reference. The Compose tree
[lives in the sibling repository `nightscout-deploy`](multitenancy-decisions.md#deploy-tree-lives-in-nightscout-deploy)
and is [its home from the next #8898 batch on](multitenancy-decisions.md#deploy-tree-home-now); core
then keeps only the fixture its own tests boot. The commands below describe the
ed2 reference as accepted; run current packaging from `nightscout-deploy`. The
[service-process decision](multitenancy-decisions.md#restore-service-processes)
owns the deployment requirement. Compose is implemented; a Jsonnet generator is
an optional way to produce configuration, not another runtime component or a
selected prerequisite.

The [binding and public-name contract](deployment-bindings-and-public-names.md)
maps ordinary Kubernetes resources onto these logical roles without assuming
multi-host membership or a particular Ingress controller. Its candidate resource
layout and access-policy extensions need their own acceptance.

## Concurrent experiments and acceptance

Agents may run isolated synthetic branch experiments before the branch has full
acceptance, alongside implementation and other experiments. The maintainer's
[experiment decision](multitenancy-decisions.md#concurrent-branch-experiments)
governs this workflow. Acceptance qualifies a selected candidate and its claims;
it is not a prerequisite for discovering that candidate's faults.

| Run purpose | Execution prerequisites | Result boundary |
|---|---|---|
| Branch experiment or diagnosis | Identified source/image/instrument, synthetic input, owned resources, finite limits and focused checks for the changed path | Record failures, partial observations and unknown metrics independently. No capacity or release acceptance. |
| Performance comparison | Experiment prerequisites plus matched workload and declared host contention | Compare only compatible observations. Record setup, steady traffic, recovery and observer cost separately. |
| Candidate acceptance | Frozen coherent source/configuration plus applicable full, browser, clinical, isolation and recovery checks | Promote only the criteria actually measured on that candidate. |

Use the existing discovery path, including `pgstream-sample` with
`--run-purpose discovery` on the runner branch, for bounded experiments on pending or accepted sources.
Keep strict/default acceptance separate. The existing
[fresh-image diagnostic](../../../tools/mt-bench/m7-joined/DIAGNOSTIC-SEAM.md)
is a small functional profile; its limits do not define every discovery workload.
The reusable runner's current local qualification and remaining remote boundary
are recorded in the [release update](execution-log.md#update--concurrent-branch-experiments-and-runner-reuse-2026-11-15).

Give each concurrent lane its own worktree, project identity, database/state,
ports, networks and cleanup custody. Record contention on shared hosts. Reserve
a quiet host for a comparison that needs one; do not impose a global quiet-host
lock on diagnostics. Do not stop peer resources. Reuse immutable images and
qualified unchanged dependencies. Keep an active run on its original helper;
a new branch or helper version must not reset that run.

Within existing resource and spending authority, changing tenant count, rate or
duration needs a configuration change and applicable input checks, not another
human approval or full application campaign. Run the actual generated probe on
a tiny fixture before expensive seeding when its generator or remote environment
changes. Record focused controls on changed code; reuse unchanged evidence with
its original source attribution. Missing optional instrumentation, slow startup,
HTTP errors and expected saturation are findings, not automatic bans on collecting
other bounded observations. A missing essential oracle leaves the dependent claim
unmeasured. An intended outage or refusal stays confined to synthetic owned resources.

Stop for lost resource ownership, breached budget/deadline, credential exposure,
cross-tenant effects or a source mismatch that prevents identifying the experiment.
Preserve raw outputs and any valid observations even when a run stops. Never
convert a failed correctness check into accepted capacity. Keep independent
experiments running when one lane fails. Reusing a seeded fixture requires its
runtime owner's custody and finite deadline; record its existing history and use
new output metadata rather than overwriting a capture.

Remote provisioning has an additional tool-permission boundary. A source receipt
does not change Codex permissions. If automatic review rejects provisioning or
cleanup, retain the denial and resolve the supported approval path with the user;
do not cycle through new launch scripts or executors. A remote diagnostic must
qualify its own transport/environment, without repeating unrelated application
acceptance. Start with the smallest useful remote point and reuse that qualified
path for larger authorized configurations.

The maintainer has authorized routine private diagnostic image publication and
pulls at negligible cost, including the roughly $0.00067 storage example. Reuse
that [standing authority](multitenancy-decisions.md#routine-diagnostic-image-delivery)
for ordinary testing and repair images; do not request approval for each digest.
Keep source/image identity, measured transfer/storage, cache custody and cleanup
in the existing run record. This removes repeated image-delivery approval from
the experiment path.

### Application requirements and environment capabilities

Application correctness requires tenant/current authority and restore fences,
a durable recoverable receipt before acknowledgement, coherent cohorts, separate
accepted and clinically completed positions, actual due work, correct stock-client
output, and durable recovery. A passing reference deployment provides evidence
for those requirements within its measured source, workload and environment.

Single-host placement, one API in a discovery profile, a Unix Docker daemon,
Vault, a particular PostgreSQL image and selected quotas are properties of the
current instrument or reference deployment. They constrain tests that use them;
they are not universal application semantics. A parameter does not admit a new
topology. An unavailable provider, browser, HA rig or optional metric leaves the
dependent claim UNMEASURED while other bounded diagnosis may continue. Required
source, authority, isolation, receipt and clinical checks remain in force.

The [runner configuration contract](../../../tools/mt-bench/m7-joined/RUNNER.md#resolve-once-for-local-and-remote-discovery)
separates run purpose, source acceptance evidence and execution limits. Its
version-2 diagnostic receipts admit truthful PENDING or PASS source status without
capacity/release promotion. Legacy captures keep their original attribution.
Reuse unchanged module/source evidence with its identity and limits. Qualify a
changed remote transport with a small actual remote probe; do not repeat unrelated
application acceptance solely for a helper, configuration or environment change.

### Configurable limits and restrictions

Multitenant is in discovery and has no production deployment. Experiments establish
which configurations work. A reference profile, a measured workload and a future
production acceptance criterion have different scopes. Neither an unmeasured size
nor an unaccepted production profile is a reason to prohibit an otherwise identified,
owned, finite synthetic experiment.

| Restriction source | What it protects | How to vary an experiment |
|---|---|---|
| Application correctness | Tenant authority/isolation, durable receipts, clinical output, restore fences and recovery | Preserve the requirement. A deliberately broken synthetic control records failure; it cannot grant the dependent correctness or capacity claim. |
| Instrument capability | An implemented protocol, role roster, probe format or topology | Explain the unsupported path and extend it with focused controls. A one-Pod socket cohort does not establish a universal one-replica application limit. |
| Reference default | Example tenant/viewer/rate values, per-role sizing, nginx sizing or phase durations | Override through configuration within the implemented contract. A new size does not require a new profile name, image allowlist or population-specific wrapper. |
| Environment allocation | Actual local resources or Kubernetes placement, requests, quotas and phase peaks | Fit the declared allocation to the available environment. Record shared contention; CPU limits are ceilings, not dedicated CPU reservations or observed use. |
| Actual authority | Owned resources, approved spending/publication scope and finite cleanup custody | Stay within the existing authority. A configuration or diagnostic receipt does not enlarge it. Do not infer another approval requirement merely from a changed parameter. |
| Candidate acceptance | Promotion of a coherent source/configuration and its measured claims | Run the applicable acceptance once on the selected candidate after focused repair. Pending acceptance does not block independent discovery. |

Tenant count, offered rate, viewers and resource/phase budgets belong in the run
configuration. Setup, startup, ordinary traffic, drain and cleanup have separate
finite windows. Size them to the experiment; a small rig's timeout is not a product
deadline. An explicitly selected allocation replaces reference CPU/memory limits
when preparing a fresh fixture. Read back actual limits and identities after
application. Keep reference defaults and entered fixtures unchanged.

Use one resolved workload across local and Kubernetes paths. A transport validates
its own capabilities and placement without inventing another workload contract.
If a transport cannot execute a requested value, report the exact field, supported
path and extension needed before seeding. Do not silently downsize or rewrite the
request. Missing optional observations stay unknown; preserve independent useful
observations and the exact failure that limits each claim.

Preflight should show requested and effective values, their origin, affected phase
and configuration field. Reuse the existing runner's projection and validators.
For local batching, `runner.py batch-resources <config>` exposes the selected
whole-cell reservation and load-driver breakdown before `batch-plan` validates
the envelope. This prevents a reference allocation from silently capping a larger
cell and accounts for the actual discovery driver. The
[runner guide](../../../tools/mt-bench/m7-joined/RUNNER.md#finite-experiment-batches)
owns commands and accounting limits. Run catalogs and comparisons can consume the
same resolved values; they need no new executor or mandatory observability platform.

When adding a numerical bound, explain its source and override or implementation
extension in the existing contract. Keep representation/protocol limits where they
are required. Do not turn a conservative example into another hard-coded ceiling.
This explanation belongs with the configuration or capability change; it adds no
approval gate, separate reporting document or prerequisite for ongoing experiments.

## Deployment choices and fault domains

Tenancy, storage, execution and placement answer different questions. The
[adopted profiles](multitenancy-decisions.md#2-storage-resolution-and-profiles)
are resident `single` on MongoDB and explicit multitenant roles on PostgreSQL/RLS.
Storage ports make other combinations researchable; they do not admit a new
supported deployment. The comparison below is **read-derived architecture
analysis**; executed acceptance is linked separately.

| Axis | Current supported/reference choice | What changing it requires |
|---|---|---|
| Tenant scope | One site for `single`; bound tenant context for multitenant roles | Authorization, configuration, caches, history and lifecycle must all preserve the chosen scope. |
| Datastore | MongoDB for `single`; PostgreSQL/RLS in the multitenant preview | Backend conformance, isolation, migrations, backup/recovery and operational acceptance; a new adapter alone does not qualify a server. |
| Computation | Resident single-site runtime; request-local API frames plus independent multitenant evaluator/realtime projections | The separate nonresident-single prototype and reusable derived-result proposal need their own admission. |
| Process/container | Existing combined single-site server; separate API, realtime, evaluator and tenant-admin preview processes | Role authority, private communication, operation lifetime and recovery must work across the actual processes. A container is packaging, not a tenant boundary. |
| Host/replicas | One-host fixed-cohort multitenant reference | Fixed-roster API replicas need endpoint trust, instance-complete drain/invalidation and recovery acceptance; they do not replicate evaluator production. Multi-host/HA additionally needs partition/failover acceptance and explicit producer ownership where work is partitioned. See the [scaling plan](selectable-endpoints-and-api-scaling-plan.md). |

| Deployment model | Scope of a failure | Evidence and decision use |
|---|---|---|
| Independent single-site servers | A server process failure affects its site. Shared database/host/ingress still couple whichever sites use them. | Existing compatibility baseline; inspect the operator's actual infrastructure before calling sites independent. |
| One-host multitenant reference | Tenant authority/history/restore are scoped; role processes, PostgreSQL, Vault, ingress and host remain shared. | Actual cold UI/socket/restore and tenant-local restart proofs inform one-host composition and protocol design. They do not establish HA or capacity. |
| Per-tenant database/process/host cells | Isolation depends on what each cell actually owns; a shared controller, identity provider or ingress can still couple cells. | An architectural alternative, with no admission from the current RLS/cohort proof. Define and test cell provisioning, migration, credentials, recovery and cross-cell operations first. |
| Replicated or multi-host roles | New partitions, split ownership, delayed messages and failover can affect tenants across hosts. | Fixed-roster API scaling is planned separately from multi-host/HA. Platform inventory and stable worker identities can supply placement/assignment; actual operation lifetime, invalidation and disjoint producer ownership remain application contracts. |

The distinction matters during failures:

| Fault | Boundary established by the reference | Shared or unmeasured consequence |
|---|---|---|
| A's restore, uncertain DATA commit or unresolved operation | A remains unavailable where required; tested B traffic and fresh shared-role startup continue. | This is cooperative tenant-operation isolation, not a bound on all database locks, pool use or tenant load. |
| A role process exits | Separate roles can be restarted; incarnation checks prevent a replacement participant satisfying an old restore pin. | Tenants using that role lose its service; automatic failover and recovery-time bounds are unmeasured. |
| PostgreSQL, shared schema/privileges or pool fails | Unsafe shared readiness refuses rather than serving through it. | Shared tenants/roles depend on that infrastructure; RLS isolates rows, not database uptime or resource exhaustion. |
| Vault or credential service becomes unavailable | Current-authority and secret-dependent paths retain their refusal rules. | Do not infer that every operation fails or survives identically; production service login, key recovery and dependency-outage acceptance remain separate. |
| nginx or the host fails | No redundant public path or host is accepted in this reference. | Public reachability or all local roles can be lost together. |
| Independently authorized direct SQL bypasses the cohort | A current-session census can detect and refuse known unexpected actors. | The [adopted application ownership contract](sql-and-migration-architecture.md#supported-database-ownership-contract) excludes independent direct writers. Stronger fencing would be needed only to support that additional writer model; it is not a prerequisite for the supported cooperative topology. |

These boundaries explain why tenant-local restore can be useful before a
production topology is qualified. The accepted experiment narrows the recovery
mechanism; production admission additionally needs the intended edge/service
identity, credential custody/renewal, lifecycle/key recovery, workloads and
operating limits, monitoring and operator recovery procedures. See the
[architecture evidence guide](single-and-multitenant-architecture.md#what-the-proofs-can-inform)
for which results support current decisions.

For aligned top-to-bottom zones and explicit communication planes, use the
[current and proposed grid topology plates](runtime-topology.md). The compact
flowchart below retains the accepted reference's connection summary.

## One-host reference topology

```mermaid
flowchart LR
  Rig["Synthetic rig / API client"] --> Edge["nginx: one published origin"]
  Browser["Existing browser"] --> Edge
  Edge -->|"pages and assets"| UI["UI process"]
  Edge -->|"/api"| API["REST APIs process<br/>admitted v1 / v2 / v3 adapters"]
  Edge -->|"/socket.io"| RT["Realtime process"]
  RT -->|"private API socket"| API
  Eval["Evaluator process"] -->|"private alarm socket"| RT
  API --> PG["PostgreSQL"]
  RT --> PG
  Eval --> PG
  Admin["Tenant-admin process"] --> PG
  API --> Vault["Vault Transit over TLS"]
  Bootstrap["One-shot bootstrap"] --> Vault
  Bootstrap --> PG
  Operator["Private maintenance operator"] --> PG
  Operator -->|"private participant control sockets"| API
  Operator --> RT
  Operator --> Eval
  Operator --> Admin
```

The [accepted cold measurement](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-cold-accepted.json)
exercises this topology as a one-host synthetic reference. UI and nginx receive
no database credentials. PostgreSQL, Vault,
tenant-admin and maintenance endpoints have no public port in this reference.
The UI renders the shipping templates/assets; API and realtime decide data
authority. See the [communication architecture](evaluator-realtime-communication.md)
for the two distinct record-frame and evaluator-output paths.

The [Compose file](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/deploy/multitenant/compose.yaml#L1)
declares internal service ports: API 1337, realtime 1339, UI 1340 and tenant-admin
1341. Only nginx's 8080 is published, by default at `127.0.0.1:18080`.
The [nginx route map](https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/deploy/multitenant/nginx.conf#L14)
preserves the public Host for configured tenant resolution and strips selector
headers. Public tenant-management/operator routes are refused. The preview's
public origin is HTTP; Vault's internal connection uses the generated CA and TLS.
An external TLS ingress requires its own declared trust configuration and test.

nginx alone attaches to both the internal `backend` network and the `edge`
bridge. The edge bridge permits host publication; every application, database,
Vault and maintenance service stays on the internal backend network. The
[accepted cold measurement](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-cold-accepted.json)
reproduces reachable UI/API/socket paths and A restore with B committing work;
it retains exact source/image and independent cleanup attribution.

## Prepare a disposable synthetic instance

Use an isolated application checkout, Docker Engine with Compose v2, Node.js and
OpenSSL. The reference requires the host uid/gid to match the image's 1000:1000
account. Check the selected source and clean tracked build inputs before preparing.
The wrapper uses a fixed Compose project name. A second checkout alone does not
isolate its containers and volumes from that project: reserve it for one
experiment, or use a separate Docker context. Another project requires explicit
Compose invocations with its own project name rather than the unchanged wrapper.
Preparation records that commit, generates private state and refuses an existing
state directory or deployment `.env`. Build uses a Git archive and lockfile;
runtime commands refuse an image whose recorded source differs.

From that application's root:

```bash
cd deploy/multitenant
./demo.sh prepare
docker compose --project-name nightscout-multitenant-demo --env-file .env -f compose.yaml pull postgres vault nginx
node check-compose.js
./demo.sh build
./demo.sh bootstrap
./demo.sh up
./demo.sh status
```

On a fresh host, the explicit pull fetches the digest-pinned public dependency
images. Startup uses `--pull never`; bootstrap does not start nginx, so it cannot
be relied on to fetch that image.

These are the inspected source's commands, not commands executed by this
documentation change. `check-compose.js` checks structural boundaries; it does
not perform the browser, restore or rig experiment. Bootstrap deliberately
prepares schemas, grants, Vault and synthetic tenant configuration. Runtime
readiness checks do not migrate or repair a partially provisioned deployment.
`up` invokes bootstrap's supported restart/unseal handling before starting roles;
unknown existing state must refuse rather than be adopted.

For the already configured lab interface, choose this **instead of** the default
preparation, before any state or `.env` exists:

```bash
./demo.sh prepare --bind 169.254.1.1 --port 18080
```

[Preparation](https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/deploy/multitenant/prepare.js#L11)
accepts only loopback or that existing address. It does not create an interface,
route or firewall rule. A mobile device's loopback addresses the device itself;
reaching this host requires an explicitly arranged lab route and name resolution.
The reference does not establish remote reachability merely by selecting a bind.

## Connect clients without changing their protocol

Resolve the generated synthetic tenant aliases to the chosen ingress address.
Use the alias in the client's configured URL, including the selected port;
substituting the bare IP loses Host-based tenant selection. Check a known tenant,
an unknown alias and the other tenant's credentials before a longer experiment.
Container loopback belongs to that container, not to the host or another service.

Take credentials only from the generated private operator material. Do not print
it into a lab report, shell history or captured request URL. A legacy subject
credential must use the shipping authorization exchange before API3 Bearer use;
the resulting DATA JWT is the Bearer credential. Existing clients using their
supported tenant-local API secret or token flow retain that flow. A public login
page does not supply management membership or implement the separate optional
OIDC/session capability.

For each selected client, record the client build, server source/image, tenant
alias and transport shape without recording credentials. Use the same synthetic
records for single-tenant and multitenant runs. Check upload acknowledgement,
addressed read, history cursor advancement, deletion handling and reconnect.
For a browser/socket consumer, verify an actual new frame contains the uploaded
record; a connected socket alone proves no data delivery. Public API identifiers
and internal storage identifiers need not be identical.

The [pinned client lab](../../../tools/lab/m4-client-binaries/README.md) owns
supported headless client execution. Android emulator and physical-device runs
remain separately attributed; [promotion decisions](multitenancy-decisions.md#multitenant-promotion-bars-2026-11-06)
define their milestone scope. Avoid replacing a real client execution with a
handwritten request and describing the result as that client's acceptance.

## Restore and failure scenarios

Run the synthetic restore demonstration only in its prepared disposable instance:

```bash
./demo.sh demo
```

The [demo implementation](https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/deploy/multitenant/demo.js#L60)
captures A, changes A, restores A using the real lifecycle/controller, writes B
during the held A operation and checks forward history correction/deletion.
The [restore-history decision](multitenancy-decisions.md#restore-history-forward-correction)
owns client convergence semantics. B's preexisting state must remain unchanged;
its explicitly authored new writes are expected differences.

| Experiment | Observe | Required failure behavior |
|---|---|---|
| Ordinary A restore | A's clinical values/public identity and relative ordering; normal forward history updates and deletions; B read/write progress | No global pause or indiscriminate rewind of current authority/consumer state. |
| Interruption before activation | Durable claim, audit, unfinished operations and actual data outcome | Keep A unavailable; no blind replay, timeout-based reopening or orphan clearance. |
| Activation acknowledgement lost | Actual persisted phase and the recorded uncertain result | Activation may already have committed after its prerequisites succeeded; inspect the outcome rather than assuming suspension or blindly repeating activation. |
| Shared-role restart with A suspended | Fresh API/realtime/evaluator processes actually serving B; A refused with no stale output; A protected state unchanged | Deferred A initialization cannot bypass shared schema/permission checks or silently reactivate A. The [c23 native matrix](../../../reports/tenancy/operation-window-acceptance-2026-11-07/c23-native-accepted/README.md) reproduces the bounded shared-role restart criterion; the [ed2 cold record](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-cold-accepted.json) supplies the separate packaged ordinary-restore proof. |
| Missing/restarted participant | Changed incarnation, missing acknowledgement or unresolved operation | Old restore pins cannot activate using replacement processes. |
| Database/Vault/shared-host outage | Which shared dependency failed and what each tenant can still do | Tenant-local restore does not promise tenant-local infrastructure failures or HA. |

The [startup-admission decision](multitenancy-decisions.md#tenant-local-startup-admission)
and [application recovery contract](https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/docs/tenant-operation-cohort.md#failure-recovery-and-shared-role-restart-boundary)
own restart behavior. Process/control liveness and each tenant's readiness are
different observations. Realtime `/health` retains strict aggregate readiness;
Compose probes TCP, private sockets and participant status instead.

## Credential and recovery boundaries

Each service mounts its own private configuration. Bootstrap alone receives
initial database/Vault material; runtime roles must not reuse that administrator.
The [credential inventory](https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/deploy/multitenant/CREDENTIALS.md)
owns generated capabilities. Fixed private sockets require the common numeric
uid, 0700 directories and 0600 endpoints. No dynamic membership is inferred.

Restore excludes A's cooperating service operations. Private database ingress
and custody of serving credentials are deployment requirements. A census of
current PostgreSQL sessions can refuse unknown actors; it cannot prevent a new
independently authorized raw SQL client from bypassing the protocol. A stronger
database/authentication fence is separate work, not a requirement to combine API
and realtime into one process. Direct PostgreSQL is required; transaction-pooling
proxies and multihost coordination are outside this reference.

The preview provides no automatic orphan clearance or supported suspended-restore
resume command. Operator-verified recovery remains separate work; the native
refusal and restart evidence does not establish a recovery-time bound.

The lab Vault credentials expire after 24 hours and restart does not renew them.
The generated CA expires after 30 days. Preserve verification and prepare a fresh
synthetic instance when appropriate; do not disable TLS checks. Vault sealing,
key custody and production Vault connectivity (a [Vault Agent sidecar](multitenancy-decisions.md#vault-agent-sidecar),
maintained in `nightscout-deploy`) remain governed by the
[adopted trust contracts](multitenancy-decisions.md#m6-deployment-and-trust-2026-11-07).

## Stop, retain and report

```bash
./demo.sh stop
./demo.sh down
```

Both commands retain named data volumes and private state. `down` removes the
Compose services/network; it does not erase database/Vault volumes. Record the
exact project and owned resources before any separately authorized destruction.
Do not remove sockets from running participants or use whole-cohort restart as
a substitute for investigating an uncertain restore.

A useful report contains the exact source/image/client versions, named scenario,
synthetic workload, observed HTTP/frame/history outcomes, fault and restoration
control, and verification that owned processes/sockets/containers are released.
Separate elapsed observations from a recovery guarantee. Keep raw credentials,
private identities and record payloads out of committed evidence.

The [c23 native matrix](../../../reports/tenancy/operation-window-acceptance-2026-11-07/c23-native-accepted/README.md)
reproduces the separate-role restore and shared-role restart criteria, including
B progress while A remains unavailable, with independent physical closure. Its
fixed trusted cooperative cohort and private credential/ingress boundary remain
load-bearing. The earlier [b029 record](../../../reports/tenancy/operation-window-acceptance-2026-11-07/b029-native-accepted/README.md)
retains its own narrower scope. The [current acceptance family](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md)
keeps their source-specific verdicts separate. The [ed2 cold record](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-cold-accepted.json)
adds actual UI/socket and ordinary restore/history/B-continuity acceptance.
The [ed2 pinned-client record](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-clients-accepted.json)
adds actual cgmsim/oref0 execution with matching stored outcomes and independent
physical closure. The [final ed2 regression](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-full-accepted/README.md)
passed all seven nonbrowser tiers. Other clients and rigs, capacity, HA,
production recovery and M6 retain their own admission criteria.
The [release contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md)
own the latest executed acceptance and remaining blockers.
