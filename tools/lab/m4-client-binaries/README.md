# M4 actual-client differential lab

*Contributor-facing lab manual, living. Measurements on archived CRM `35903069` live in
[the dated report](../../../reports/m4-client-binaries/2026-11-06/README.md); item state lives
in `queue/work-queue.yaml`.*

Runs the installed, unmodified nightscout-connect, oref0 and cgmsim-lib programs against
single-site Mongo and an explicit two-tenant PostgreSQL/Vault preview of the same CRM head.
The synthetic cgmsim driver and oref0 profile preload provide a fixed input clock;
client source files are unchanged. Baseline-as-source comparison, mobile binaries and a socket
forwarder remain separate scopes. This lab promotes no milestone.

## Current finite custody entrypoint (source checked; native pending)

The current executable profile is **cgmsim + oref0 only**, with three static services
(PostgreSQL, MongoDB and Vault), at most one live client container, and at most 64 serial
client slots. Connector opt-in runs are setup-refused by this profile; their historical
measurements remain in their dated records. No Android binary or device runs here.

A reviewed finite parent must bind the application commit, these helper files, the installed
client/build provenance, dependency source and four exact image IDs before executing
`custody-run.js`. Its fixed arguments are `--plan <absolute-private-plan> --out <initially-absent-output>
--ref <full-application-commit> --repository <absolute-source-repository> --dependencies
<absolute-node_modules>`. It runs the existing queue gate with `--clients cgmsim,oref0`.
Direct lab execution requires `NS_M4_CUSTODY_PLAN` and an independently running observer;
absence is a setup refusal. A parent plan is custody configuration, not execution permission.

The private version-1 `m4-cgmsim-oref0-v1` plan has `status: PARENT_BOUND`, a fresh v4
`ownerUUID`, `applicationHead`, `activeSeconds: 600`, `cleanupSeconds: 120`,
`dockerExecutable: /usr/bin/docker`, an absolute initially empty `dockerConfig`,
`endpointProfile: network-endpoint-stable-v1`, `images` keyed exactly `postgres`, `mongo`,
`vault`, `client` with full SHA256 image IDs, and `baseline` container/volume/network ID
arrays. The independent parent captures full baseline fingerprints with
`custody-observer.baselineSnapshot(invoke)` before resources. Inspect classes use strict
32-ID batches, exact returned sets, full IDs, caps 256/1024/64 and a 128-KiB argv ceiling.
The verbatim approved `endpoint_profile.py` (SHA256
`a37601bee57751c0bab58afbf57bfb5de624c12ce1aa068f5dc632d023d3f4b2`) is called
through a fixed stdlib Python adapter; the parent must additionally pin `/usr/bin/python3.12`
and its exact `-I -B endpoint-adapter.py` child argv. Complete Config/HostConfig, including
Env, are fingerprinted in Python before leaving the raw inspect parser; raw baseline Env
is never persisted. Every network-inspect field except Containers remains exact, including
unknown fields. Containers uses exactly the helper's five typed fields: membership, Name
and both IP strings remain exact; only EndpointID and MacAddress observations may vary.
Full private before/after maps and explicit fullEquality=false remain in the comparison.

Container NetworkSettings retains Ports and every other static/unknown field exactly.
Only per-network EndpointID/MacAddress are observations, checked against authoritative
global network maps by NetworkID, container ID, membership, name and IP/prefix. SandboxID
and SandboxKey are typed lifecycle observations retained before/after, with no mutation
or ownership authority. State, RestartCount and ExecIDs remain runtime observations.
No unrelated Sandbox transition has been reproduced by this source-only work; the
classification is prospective. It does not claim host quiescence or unchanged full endpoints.

Each container is created stopped under a fixed initially absent name, journaled by exact ID,
validated against the typed image/argv/env/mount specification, then independently inspected.
`custody/custody.jsonl` is fsynced before `custody/observer.jsonl` and its exclusive receipt
under `custody/receipts/`; actual `start` consumes that receipt. Anonymous image volumes
are captured by exact identity before start. Cleanup uses saved IDs, fresh complete identity
checks and fresh empty volume references. Unidentified create results remain unresolved;
names and later absence never grant cleanup authority. A receipt wait is bounded to eight
seconds and fails closed. A saved first-start intent admits either exact identity or the isolated-engine-measured
OomKillDisable false-to-null transition, only when projecting that one field back to false
reproduces the complete original identity. A fsynced first-start receipt retains complete
before/after/projected fingerprints before the owned identity advances. True/malformed
values, any other change and later drift refuse; baseline Config/HostConfig never use this
transition. Recovery may finish this same proof only for a previously saved exact ID and
first-start intent, before any cleanup. This is instrument lifecycle handling, not product
or client compatibility acceptance. Client output still comes from the attached process; its status
comes from the completed container's actual ExitCode, preserving oref0's HTTP/exit distinction.

After the reviewed host supervisor has reaped all children, the parent calls the M4-specific
`normalize(entries, {owner, baseline, supervisor, run})` and
`verifyBaseline(invoke, savedSnapshot)`. The supervisor phase must be explicitly
`m4-clients`, with its actual fresh process readback/unknown-child/terminal-receipt fields;
a full/browser result cannot be relabeled. On interrupted runs the parent may call
`custody.recover({plan, directory})` within the **same** cleanup budget, using only durable
identified resources. An unresolved create or missing journal is a failed release verdict.
Physical normalization omits `run` for interrupted/failed work and accepts safely closed
identified prefixes, including zero created resources. Positive scientific normalization supplies
the actual `run` and additionally requires all three services and completed client executions.
Uninspected or unresolved intents still refuse physical normalization. Scientific gate success
and physical release are separate verdicts.

The proposed finite envelope is 600 seconds active plus one shared 120-second cleanup
budget, including observer and all exact-ID cleanup/verification. These are ceilings, not
measured durations. The parent starts its deadline before all pre-resource commands and
must reject insufficient remaining time; it must not reset cleanup or adopt unknown actors.
The wrapper does not enforce the outer host deadline or claim host-process custody itself.
Native M4 performance, complete baseline/container shape and physical closure remain
unmeasured for this source until the acceptance lead binds and runs the reviewed parent.
The separate isolated engine proof measures only its first-start field transition.

Offline checks: `node tools/lab/m4-client-binaries/test-custody.js`, existing `test-lab.js`,
`test-endpoint-adapter.js`, and `test-classify.py`. Optional private retained endpoint/engine
inputs use NS_M4_ENDPOINT_BEFORE/AFTER and NS_M4_FIRST_START_BEFORE/AFTER; never commit
those captures. Actual retained maps/config are replayed inside explicit synthetic inspect
and identity envelopes; that does not create native M4 evidence. The custody checks use
recording transports and synthetic rows;
they do not execute Docker, a client, a server, or a listener.

## Historical direct invocation and preparation

Prepare private CRM dependencies and bundle in the worktree named below; installed clients
and their dependencies must be present under `externals/` or the explicit `NS_M4_EXTERNALS` root.
The gate requires the declared clean client heads. It archives cgmsim source, compiles it in
scratch with its locked TypeScript, and compares every emitted runtime JS file before starting
fixtures. A stale generated `dist` is a setup refusal. Build a separate owned client worktree;
do not overwrite a shared generated artifact. The dated report records the provenance control. Build the client runtime with
`docker build -t m4-client-lab:node22-jq tools/lab/m4-client-binaries`. The runner refuses
missing dependencies/images. It starts only uniquely named owned fixtures on loopback ports,
uses direct-alias resolution and `AUTH_DEFAULT_ROLES=denied`, and removes its own resources.
Coordinate fixture ownership before running; never delete another lane's resources.

The following invocation documents the earlier capture interface; current execution uses
the finite custody entrypoint above and requires its bound plan/observer.

```bash
NS_M4_GATE_DEPENDENCIES="$PWD/externals/work/crm-m4-client-lab-20261106/node_modules" \
NS_M4_GATE_OUT=/tmp/m4-client-measurement-unique \
NS_M4_EXTERNALS="$PWD/externals/work/m4-pinned-clients-20261106" \
node tools/queue/gates/m4-client-binaries.js --ref 35903069b46974cfbaddd8dce00c994fb2562bc3
```

The gate archives the selected commit, verifies the private lockfile and passes the exact
archived head to the runner. `NS_M4_GATE_REPO` and `NS_M4_EXTERNALS` support an isolated
alignment worktree without relocating or editing a client checkout. The output directory
must not exist; preserve each capture rather than overwrite it. The historical broader selection was
`--clients connect-share,connect-source,oref0,cgmsim`; it is outside the current finite
custody profile. Logs contain synthetic data only;
query values and exchange-token path segments are redacted.

## Oracle and classification

The recording proxy records HTTP status and reply shape. Independent Mongo/PostgreSQL
readers record stored documents after each cell. Only generated primary keys and top-level
server clock stamps are separated from the value comparison; identifier kinds remain in
cells. Nested values are retained. Explicit fixture assertions prove ordinary writes stored
the synthetic values. Every differing field needs a measured explanation with a decision
basis in `groups.yaml`; the default explanations list is empty. Missing cells on either
stack also refuse acceptance. The compat classifier supplies the mechanical effect vocabulary;
value-document differences use `Other` until an explanation exists.

Run `python3 tools/lab/m4-client-binaries/test-classify.py` for the classifier's deliberate
value corruption and missing-cell checks. These checks prove the classifier notices the
break and accepts restoration; they do not measure a client or server.

## Controls and limits

Run the same gate with `--control hosts`, `--control oracle`, or `--control unexplained`, then
restore by running without `--control`. Controls are expected to fail on the deliberately broken property. Evidence must
also show the intended symptom: resolution failure without a proxy request, empty stored
outcomes from tenant B, or a planted unexplained reply-shape difference. A nonzero exit
alone is insufficient evidence. Wrong-oracle fixture assertions must fail; cells alone are
not the assertion. Run negatives measure cross-alias, revocation, unknown alias and absent
credential behavior and check stored effects. oref0 HTTP refusal is separate from its exit:
its curl invocation lacks `--fail`. A missing secret can be a client-local refusal.

No real vendor account is used. Connector uses this lab's fixed synthetic Share upstream. One-poll captures do not measure incremental new readings. Connector
negative coverage, subject-creating onboarding, malformed-batch per-item parity, long retry
soak, mobile/v3 binaries, sockets, TLS and capacity require their own measured evidence;
a partial run cannot claim those properties. A mismatch is recorded before any repair or
classification decision; no broad field exemption should turn it green.
