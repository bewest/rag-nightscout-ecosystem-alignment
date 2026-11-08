# Deployment scenarios and rig testing

*Contributor-facing living runbook. Deployment structure and commands are
**read-derived** from cgm-remote-monitor
`151de0248a1e4301c85b5c638185eec3ca8c38e6`, inspected 2026-11-07. Executed
results retain their own source in the linked records. This document implements
the documentation scope of MT-DOC-DEPLOY; current claims live in the
[work queue](../../../queue/work-queue.yaml) and
[delivery dashboard](multitenant-delivery-dashboard.md).*

## Choose the experiment

| Scenario | Purpose | Boundary |
|---|---|---|
| Existing single-tenant installation | Compatibility baseline for a selected rig/client | Existing MongoDB deployment and client configuration; `nightscout single` remains the default. |
| One-host synthetic Compose preview | Exercise separate services, browser/API/socket paths and tenant-local restore | Fixed participants, private Unix sockets, direct PostgreSQL and locally generated credentials. Actual cold Compose/browser/restore acceptance is still pending. |
| Headless client lab | Compare pinned clients against the admitted API surface | Follow the [binary client lab](../../../tools/lab/m4-client-binaries/README.md); its evidence does not establish every mobile device or every new source head. |
| Physical mobile or pump/CGM rig | Verify the chosen client, network path, upload/history and reconnect behavior | A separately recorded experiment using synthetic input. Device execution is not implied by source-pattern replay. |
| Multi-host, orchestrated replicas or failover | Explore later deployment design | Proposed topology: the current private socket roster is a one-host contract, not distributed discovery or HA. |

The [application Compose guide](https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/deploy/multitenant/README.md)
owns runnable packaging instructions. The
[service-process decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-service-processes)
owns the deployment requirement. Compose is implemented; a Jsonnet generator is
an optional way to produce configuration, not another runtime component or a
selected prerequisite.

## One-host reference topology

```mermaid
flowchart LR
  Rig["Synthetic rig / API client"] --> Edge["nginx: one published origin"]
  Browser["Existing browser"] --> Edge
  Edge -->|"pages and assets"| UI["UI process"]
  Edge -->|"/api"| API["API process"]
  Edge -->|"/socket.io"| RT["Realtime process"]
  RT -->|"private API socket"| API
  Eval["Evaluator process"] -->|"private alarm socket"| RT
  API --> PG["PostgreSQL"]
  RT --> PG
  Eval --> PG
  Admin["Tenant-admin process"] --> PG
  API --> Vault["Vault Transit over TLS"]
  Admin --> Vault
  Operator["Private maintenance operator"] --> PG
  Operator -->|"private participant control sockets"| API
  Operator --> RT
  Operator --> Eval
  Operator --> Admin
```

These are source paths, not an assertion that this entire deployment has passed
acceptance. UI and nginx receive no database credentials. PostgreSQL, Vault,
tenant-admin and maintenance endpoints have no public port in this reference.
The UI renders the shipping templates/assets; API and realtime decide data
authority. See the [communication architecture](evaluator-realtime-communication.md)
for the two distinct record-frame and evaluator-output paths.

The [Compose file](https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/deploy/multitenant/compose.yaml#L1)
declares internal service ports: API 1337, realtime 1339, UI 1340 and tenant-admin
1341. Only nginx's 8080 is published, by default at `127.0.0.1:18080`.
The [nginx route map](https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/deploy/multitenant/nginx.conf#L14)
preserves the public Host for configured tenant resolution and strips selector
headers. Public tenant-management/operator routes are refused. The preview's
public origin is HTTP; Vault's internal connection uses the generated CA and TLS.
An external TLS ingress requires its own declared trust configuration and test.

At this inspected source, nginx attaches to the internal backend network.
Host publication is under diagnosis following the first cold Compose attempt;
do not infer that a healthy container establishes a reachable browser origin.
Any corrected topology must retain private backend services and expose only
the intended ingress.

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
node check-compose.js
./demo.sh build
./demo.sh bootstrap
./demo.sh up
./demo.sh status
```

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
remain separately attributed; [promotion decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06)
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
The [restore-history decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-history-forward-correction)
owns client convergence semantics. B's preexisting state must remain unchanged;
its explicitly authored new writes are expected differences.

| Experiment | Observe | Required failure behavior |
|---|---|---|
| Ordinary A restore | A's clinical values/public identity and relative ordering; normal forward history updates and deletions; B read/write progress | No global pause or indiscriminate rewind of current authority/consumer state. |
| Interrupted/uncertain restore | Durable claim, audit, unfinished operations and actual data outcome | Keep A unavailable; no blind replay, timeout-based reopening or orphan clearance. |
| Shared-role restart with A suspended | Fresh API/realtime/evaluator processes actually serving B; A refused with no stale output; A protected state unchanged | Deferred A initialization cannot bypass shared schema/permission checks or silently reactivate A. Native acceptance on the new source is pending. |
| Missing/restarted participant | Changed incarnation, missing acknowledgement or unresolved operation | Old restore pins cannot activate using replacement processes. |
| Database/Vault/shared-host outage | Which shared dependency failed and what each tenant can still do | Tenant-local restore does not promise tenant-local infrastructure failures or HA. |

The [startup-admission decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-local-startup-admission)
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

The lab Vault credentials expire after 24 hours and restart does not renew them.
The generated CA expires after 30 days. Preserve verification and prepare a fresh
synthetic instance when appropriate; do not disable TLS checks. Vault sealing,
key custody and eventual production service login remain governed by the
[adopted trust contracts](../../../releases/cgm-remote-monitor-16.0.0/decisions.md).

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

The [b029 native record](../../../reports/tenancy/operation-window-acceptance-2026-11-07/b029-native-accepted/README.md)
reproduces 17 separate-process restore criteria, with physical closure. It does
not accept the new startup source, Compose/UI ingress, all rigs, capacity or M6.
The [release contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md)
own the latest executed acceptance and remaining blockers.
