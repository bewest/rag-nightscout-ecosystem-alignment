# M4 actual-client differential lab

*Contributor-facing lab manual, living. Measurements on archived CRM `35903069` live in
[the dated report](../../../reports/m4-client-binaries/2026-11-06/README.md); item state lives
in `queue/work-queue.yaml`.*

Runs the installed, unmodified nightscout-connect, oref0 and cgmsim-lib programs against
single-site Mongo and an explicit two-tenant PostgreSQL/Vault preview of the same CRM head.
The synthetic cgmsim driver and oref0 profile preload provide a fixed input clock;
client source files are unchanged. Baseline-as-source comparison, mobile binaries and a socket
forwarder remain separate scopes. This lab promotes no milestone.

## Run

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

```bash
NS_M4_GATE_DEPENDENCIES="$PWD/externals/work/crm-m4-client-lab-20261106/node_modules" \
NS_M4_GATE_OUT=/tmp/m4-client-measurement-unique \
NS_M4_EXTERNALS="$PWD/externals/work/m4-pinned-clients-20261106" \
node tools/queue/gates/m4-client-binaries.js --ref 35903069b46974cfbaddd8dce00c994fb2562bc3
```

The gate archives the selected commit, verifies the private lockfile and passes the exact
archived head to the runner. `NS_M4_GATE_REPO` and `NS_M4_EXTERNALS` support an isolated
alignment worktree without relocating or editing a client checkout. The output directory
must not exist; preserve each capture rather than overwrite it. Default gate clients are
cgmsim and oref0. `--clients connect-share,connect-source,oref0,cgmsim` selects the broader
lab; connector's scheduler can take several minutes. Logs contain synthetic data only;
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
