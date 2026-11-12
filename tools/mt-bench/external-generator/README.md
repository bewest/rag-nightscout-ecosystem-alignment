# External traffic generator — isolated profile

Contributor-facing source capability. Runtime and cloud behavior are **UNMEASURED**
until the remote owner runs a reviewed smoke. The current colocated pilot is unchanged.

The new `joined-external-generator-v1` profile uses one application/PostgreSQL host
and one generator. Both k6 and the stock Socket.IO traffic move to the generator.
SQL, stored-count controls, evaluator inspection and role restart stay on the app
host. A controller mediates fixed, ordered, run/nonce/cell-bound phases over its
existing SSH connections. No private inspection or SQL RPC is exposed to traffic.

Traffic runs as `nsload` without sudo, supplementary groups or a Docker socket.
The trusted root supervisor launches only the pinned k6 image, fixed script,
read-only scoped tenant input, fixed workload and bounded run. The stock SDK is
installed from the exact application lockfile and verified by its resolved entry.
The public edge binds only to the selected private VPC address. Database and
private application listeners retain the original internal binding.

Request-to-frame durations use the generator's monotonic clock. Restart-to-frame
observation starts at the generator arm and therefore includes controller delay.
A connected old socket with a post-arm frame cannot pass recovery: the observer
requires a new disconnect/connect generation and a later frame, plus the actual
app restart acknowledgement. App-local helpers prove the real role restart and
fresh evaluator work independently. Cross-host clock subtraction is not used.

The per-write SQL latency poller is **NOT_RUN** in this profile. Strict evaluator
progress and recovery remain app-side, but they are different observers. The old
`writeToEvaluationMs` diagnostic is explicitly `UNMEASURED`. Load query/CPU deltas
therefore reflect both placement and observer changes; they cannot be attributed
solely to moving generators. Common traffic, correctness and idle metrics retain
their stated scopes. No result automatically grants capacity acceptance.

Preparation and the two-node driver live in `nightscout-deploy` under
`tools/perf-cloud/prepare-external-generator.js`. The new extension descriptor is
hashed separately from the unchanged base joined instrument. Its producer file
allowlist is checked against the actual controller transfer interface before keys
or deployment. Unsupported layouts, a second generator and separate PostgreSQL
refuse. A later PostgreSQL split or retained per-write correlated SQL observer is
outside this increment.

Focused source controls (no Docker, cloud, npm install or application campaign):

```bash
python3 -I -B tools/mt-bench/external-generator/test_contract.py
node --test tools/mt-bench/external-generator/test_recovery.cjs
```

They cover bounded partial-line/EOF handling, run/node/nonce/sequence mismatches,
metric envelope compatibility, completeness failures, producer transfer equality,
readiness ordering, server recovery/oracle refusal and real reconnect semantics.
The deployment repository's existing `npm run test:perf-cloud` includes the
self-contained controller controls. Controls use synthetic fixtures; source-only
passes do not qualify real networking, imports, resource use or cloud teardown.

Enabled idle uses the base adapter's failure-bookend helper. It attempts the
existing AFTER snapshots when assessment refuses and preserves the original
failure. The sampler-disabled and enabled windows remain 60 and 120 seconds.
