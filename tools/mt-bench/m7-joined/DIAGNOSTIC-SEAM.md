# Fresh-image functional diagnostic before full acceptance

This is an explicit diagnostic authorization/result scope. It does **not** fabricate
joined acceptance, unlock a capacity run or satisfy pilot/ladder gates. The remote
controller owns all cloud activity and enforces its current maintainer-authorized spending/deadline policy. This instrument creates
no cloud resources. Use only the coordinator's selected committed source pair and
matching image/instrument identity. Do not substitute an older image or source mount.

A diagnostic receipt has this shape (replace identity placeholders from committed
source/`adapter.py manifest`; the placeholders deliberately refuse):

```json
{"kind":"joined-diagnostic","status":"AUTHORIZED_DIAGNOSTIC","pair":{"core":"FULL_CORE_SHA","deploy":"FULL_DEPLOY_SHA"},"instrument":"INSTRUMENT_CONTENT_SHA256","limits":{"tenants":2,"apiReplicas":2,"trafficSeconds":180}}
```

Absolute maximums are10 tenants,2 API instances and180 seconds client traffic.
The coordinator may authorize lower limits. The default cheap case is2 tenants.
The receipt permits only `build`, `deploy` and `diagnose` for this profile; it is
rejected by CAP `run`, remote pilot and full ladder authorization. A diagnostic
result cannot be reused as a receipt. Full acceptance remains NOT_RUN.

```bash
python3 tools/mt-bench/m7-joined/adapter.py prepare \
  --directory /private/new-diagnostic-cell --profile fresh-image-diagnostic \
  --core-repo /sources/core.git --core-commit "$M7_CORE_SHA" \
  --deploy-repo /sources/deploy.git --deploy-commit "$M7_DEPLOY_SHA" \
  --image "$M7_PAIRED_IMAGE" --receipt /private/diagnostic-receipt.json \
  --tenants 2 --replicas 2
python3 tools/mt-bench/m7-joined/adapter.py build /private/new-diagnostic-cell
python3 tools/mt-bench/m7-joined/adapter.py deploy /private/new-diagnostic-cell
python3 tools/mt-bench/m7-joined/adapter.py diagnose /private/new-diagnostic-cell
python3 tools/mt-bench/m7-joined/adapter.py check-diagnostic /private/new-diagnostic-cell/diagnostic.json
python3 tools/mt-bench/m7-joined/adapter.py down /private/new-diagnostic-cell
```

The shared shipping deployment logic is reused: infrastructure/bootstrap, admin/feed,
provision, restore commissioning, API instances, DATA prime, local private publisher,
remaining roles/UI/nginx. Exact instance health and source/binding errors stay errors;
this diagnostic adds no surrogate or weakened role. A selected sharded placement
continues to refuse without its committed controlled-replacement helper. Matching
UID/GID1000, local Docker/Git and image prerequisites from REMOTE-SEAM.md still apply.
A busy host is captured as **diagnostic-only**, not falsely called a quiet capacity
host. This permission does not authorize a local/cloud capacity campaign.

The fixed client criterion uses the owned exact-lock generator Socket.IO library and registered
hostname URLs with loopback-DNS Agent, never127URL/extraHeaders.Host. It exchanges
the DATA credential, GETs status, primes one stock polling socket per tenant, POSTs
one current synthetic SGV per tenant, and requires that tenant's frame to carry the
new timestamp. It observes an actual legacy realtime container restart and requires
unaided stock reconnect plus current frame, then GETs status again. There are exactly
4N successful criterion DATA HTTP requests on success, plus separately counted
recognized warming probes; stock polling/reconnect is bounded by the
traffic deadline. No manual reconnect workaround or k6/performance window runs.

Client acknowledgements use `load/client-acks.json` (not a claimed k6 run). Independent
SQL stored counts must match; the same owned row-marker RED/restore GREEN control is
required. PASS needs every HTTP/prime/frame/restart/recovery/oracle criterion and
source/image/instrument/host identity. `diagnostic.json` is kind
`m7-joined-fresh-image-diagnostic`, with `fullAcceptance:NOT_RUN` and
`capacity:NO-MEASUREMENT`. Exit0 plus `M7_DIAGNOSTIC_PASS_ONLY` has only this meaning.
Exit1/refusal, an incomplete observation, missing frame or failed recovery is never
PASS. It cannot satisfy `check-pilot` or `check-campaign`.

Artifacts: common source/ownership/deployment logs, diagnostic host inventory,
`load/diagnostic.log`, bounded observations/partial stage, client acknowledgements,
independent stored oracle/control and `diagnostic.json`. Credentials remain in private
custody. Host job PID/start identity is recorded so `down` stops only its own runner;
the controller owns outer budget abort, evidence checkpoint and VM teardown. Build/
bootstrap time is outside the client-traffic deadline and stays within the controller's
separate spend/deadline policy. No actual fresh app/image diagnostic is implied by a
passing mocked/fixture instrument check.

Fresh generator installation and actual client resolution run before infrastructure
startup. A development-pruned serving image is valid: its node_modules is never
borrowed by the generator. Preserve private prepare-commands/, prepare-failure.json,
generator-commands/, generator-verifications/ and generator-provenance.json on
failure. Raw stdout/stderr can contain credentials; do not publish these directories.

Explicit diagnostic HTTP calls retain `load/diagnostic-http.json` even on refusal.
The bounded trail contains at most4N+512 records and262,144 serialized bytes: request number, logical stage,
zero-based tenant index, method, fixed route class, response status, a bounded
uppercase typed `error` code, and a sanitized local failure code. It records no
URL, exchange path, query, host, tenant identifier, request/response body or token.
The private file is mode0600; diagnostic observations link it and retain the
terminal instrument code. In-flight records can have null status when no response
arrived. This trail describes explicit DATA HTTP calls, not Socket.IO internals.

GET status retries only an actual503 response with exact typed `TENANT_WARMING`.
The first refusal remains recorded and classified in the current run. Polls use
200ms cadence inside the existing global deadline, with at most512 recognized
warming probes globally; reaching the probe limit refuses. Exchange, mutation,
401, unknown503 and untyped503 refusals stop immediately. No credential fallback,
role change or deadline extension exists. This policy follows the measured API
cold-start contract; it does not retroactively classify historical remoteD.

HTTP accounting version2 requires successful `criterionHttpRequests=4N` (also
retained as `dataHttpRequests`), separate `warmProbeHttpRequests`, and
`physicalHttpRequests=criterionHttpRequests+warmProbeHttpRequests` for a passing
result. Trail records equal physical requests and retain the explicit byte bound.
Failed results can also contain refused or pending requests, so they do not claim
that passing equation. Warm responses alone never satisfy HTTP, write, SQL, frame,
observed restart or stock-recovery criteria. Historical profiles/results keep their
original instrument source; no old capture is reinterpreted as version2.

On terminal cleanup the owned Socket.IO HTTP agent rejects late queued polling
requests before destroying its sockets. Agent.destroy() alone permits later
requests to create new referenced sockets. Actual spawned CLI controls cover an
HTTP refusal after one stock socket connects with no frames; failure exits with
its original diagnostic code rather than waiting for the traffic deadline. Python
retains that safe terminal code and reports process termination or exit timeout
separately. This does not force process exit or change the traffic budget.

## Explicit independent pgstream topology

Fresh `pgstream-sample` discovery configurations for a separately managed Go
service select `--pgstream-topology external-service-v1` and
`--diagnostic-resource-profile local-diagnostic-external-pgstream-4cpu-8g-v1`.
The default remains `colocated-v1`; a standalone Compose service under that
selection refuses. The new selection validates the exact pinned core schema,
canonical frozen service command, source/image identity and separate process
instrumentation. The existing paired producer and core CLI source-contract check
still applies. It does not imply image or runtime acceptance.

The new resource profile explicitly divides the former evaluator allocation:

| Role | CPU limit | Memory limit |
|---|---:|---:|
| Evaluator Node | 125 millicpus | 256 MiB |
| Independent pgstream Go | 125 millicpus | 256 MiB |

All other role, driver, oneoff and host-heap limits remain the existing policy.
The complete one-replica roster reserves 3875 millicpus, 8192 MiB container memory
and 1024 MiB host V8 heaps. This is a bounded diagnostic policy; whether these
quotas are adequate for a workload is UNMEASURED. A constrained generator or
service is a finding, not capacity acceptance. The old profile retains its
250 millicpu/512 MiB evaluator allocation and refuses the new Go role.

The explicit `local-diagnostic-external-pgstream-evaluator250-4cpu-8g-v1`
variant changes only evaluator CPU to 250 millicpus. Evaluator memory remains
256 MiB; the independent Go service remains at 125 millicpus/256 MiB. Its full
reservation is 4,000 millicpus, 8,192 MiB container memory and 1,024 MiB host V8
heaps. It is a separate diagnostic profile for a CPU comparison, not evidence
that the original profile passes. The frozen configuration and actual container
limits must match that selection. Capture effective `cpu.max` separately;
requested CPU is not a measurement of the kernel's quota rounding.

Deployment includes the independent service in the maintained role roster.
Preflight requires Node counters in the evaluator container and Go counters in
the pgstream container, with exact image/command and running-container birth
checks. Reduction requires both roles and stable process births across each
window. Go logs use the existing bounded collector; Node diagnostics environment
flags are validated only for Node roles. Raw log, source and runtime receipts
retain their existing homes. Old captures remain on their original helper.

The opt-in `local-diagnostic-external-pgstream-evaluator250-memory512-4cpu-8448m-v1`
variant keeps evaluator CPU at 250 millicpus and changes only its container
memory and memory-plus-swap limit from 256 to 512 MiB relative to evaluator250.
It reserves 4000 millicpus and 8448 MiB across the selected services, declared
oneoff overlaps and standalone k6, plus the unchanged 1024 MiB host V8 heap
allowance. Native host RSS remains separately observed. The old profiles retain
their 8192 MiB ceiling. This local finite memory discriminator grants no capacity
and changes no default or remote allocation. The existing 8192 MiB batch
reservation explicitly refuses this larger variant; it must not underreserve it.
Timeline preloads, mounts and extra observations are separate instrument changes
and must be sealed and reported, not called a pure performance comparison.
