# Remote PostgreSQL stream calibration

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
