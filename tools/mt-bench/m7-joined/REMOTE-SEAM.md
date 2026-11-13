# Remote controller seam

The controller owns cloud creation/transport/bundling, checkpoints and teardown,
and enforces the maintainer-authorized controller-selected spending/deadline policy. This adapter makes no cloud
API call and does not estimate or waive that ceiling. Do not start it before the
coordinator supplies the accepted core/deploy tuple and frozen acceptance receipt.
A budget/deadline abort is incomplete evidence, never a passing capacity result.
An explicitly authorized bounded fresh-image diagnostic can precede full acceptance;
[its separate receipt/result contract](DIAGNOSTIC-SEAM.md) cannot unlock pilot/CAP.

## Host and source prerequisites

- Linux, local Unix-socket Docker Engine/Compose v2, cgroup v2, `/proc`, Bash,
  GNU date/coreutils, procps, OpenSSL, tar, Git, Python3.11+, a source-supported Node version and npm. Exact Node/npm paths,
  binary hashes and versions are pinned for the generator; changing them refuses
  a workload or subsequent ladder cell/profile. npm registry access is needed for
  the separate owned exact-lock install (private cache; lifecycle scripts disabled).
- Run the product's local preparation as UID/GID1000, matching the shipped app/
  bootstrap user and private0700 state. Another UID refuses before deployment;
  the controller provisions the matching account/Docker access. Do not broaden
  private permissions to compensate.
- A checked-out committed alignment instrument with its Git identity/index and
  reused tracked `capacity`/`compose-baseline` files. `adapter.py manifest` lists
  exact paths/hashes. A copied directory without Git attribution is insufficient.
- Core and deploy repositories (bare is acceptable) containing the exact full
  commits. The adapter creates its own detached worktree and archives deployment
  from its commit, not a peer worktree. No borrowed node_modules/source mount.
- Matching paired application image already transported/built, or build it through
  the adapter after source acceptance/quiet-host handoff. Both source labels and
  immutable image ID must match. Have the committed binding's pinned infrastructure
  images and a k6 image available; k6 is resolved to its immutable local ID.
- Enough disk for image layers, one active core checkout, owned lockfile generator dependencies,
  private PG/Vault volumes and raw logs. The controller budgets/checks available RAM,
  disk and runtime before spend. Captured host identity must stay identical across
  all pilot steps; a new/replaced daemon or hardware profile cannot silently join.

The adapter refuses other running containers; it records competitor/process metadata
without stopping them. A provider control-plane container must be resolved with the
coordinator before handoff rather than hidden from the record. The private outputs
contain synthetic custody material. Keep state/checkpoints private; only selected
sanitized evidence belongs in a public record. The controller preserves raw artifacts
and provenance before destroying its owned VM, subject to its budget/deadline.

## Pilot invocation

```bash
python3 tools/mt-bench/m7-joined/adapter.py manifest > /private/instrument-manifest.json
python3 tools/mt-bench/m7-joined/campaign.py pilot \
  --work /private/new-pilot-directory \
  --core-repo /sources/core.git --core-commit "$M7_CORE_SHA" \
  --deploy-repo /sources/deploy.git --deploy-commit "$M7_DEPLOY_SHA" \
  --image "$M7_PAIRED_IMAGE" --k6-image "$M7_K6_IMAGE" \
  --freeze /private/frozen-acceptance.json --quiet-load 3
python3 tools/mt-bench/m7-joined/adapter.py check-pilot /private/new-pilot-directory/campaign.json
```

`pilot` selects one API and counts500→750→1000, real cadence, hot factor10 and two
stock polling clients per tenant. Each cell has60s sampler-disabled idle,120s sampled
idle and300s load (one nominal CGM cycle), followed by bounded reconnect/runtime
inspection. These are explicit **pilot** settings, not the main600s/900s profile.
Growth requires passing attribution, measurement and correctness/oracle controls.
A pilot does not satisfy the3,000 capacity gate or claim10,000. `prepare` accepts
explicit diagnostic seed counts1..10000; main `ladder` still fixes1k→3k→5k→10k.

Deployment sequence mirrors the committed product binding:
infrastructure → bootstrap → admin/feed → primer provision → commissioning restore
via bootstrap's `commission-restore.js` → API instances → primer prime → local
`publish-primer.js` custody handoff → remaining roles/UI/nginx. Exact fixed-instance
health remains a product gate; the adapter cannot substitute another instance.
A selected sharded placement refuses raw restart with
`M7_SHARDED_RESTART_HELPER_REQUIRED` until the coordinator supplies its committed
controlled-replacement helper seam. Do not work around that by reusing an incarnation.

## Verdict and artifact contract

Exit0 plus `M7_REMOTE_PILOT_COMPLETE` means all three pilot cells passed and share
core/deploy/instrument/image/host identities. `check-pilot` rejects missing750,
mixed identities, missing measurement or a nonpassing cell. Exit1 and an `M7_*`
code means refused/failed/incomplete; inspect the private phase artifacts. Never
classify a wrong Host, stale source, missing helper or uncommissioned identity as
measured product latency. The stock socket URL uses the registered alias and
loopback-DNS Agent; it does not rely on extraHeaders.Host against a127URL.

A cell's `owner.json` records source/instrument/file hashes, image IDs, ownership,
port, profile and dependency provenance. Other outputs include:

- `deployment-stages.json`, stage logs and `deployment.json`;
- private `state/`, `env`, tenant projection and owned lockfile generator dependencies;
- host inventories before deploy/run/load and after, `runtime-readiness.json`;
- `idle-disabled/`, `idle/`, `load/` cgroups/process RSS/PG statement snapshots;
- sampled CPU/memory/PG waits/locks, sampler timing and `loadgen.jsonl`;
- generated probe/workload hashes, `probe.json`, k6 metrics/logs;
- independent stored counts, oracle and break/restore control; final `summary.json`;
- campaign/profile ledgers. A failed profile is retained as FAIL. Functional/oracle/
  authority failures block all advancement. A diagnosed nonfunctional ceiling can
  allow the next explicit replica ladder only through the coordinator's hashed
  same-source/instrument/host diagnosis receipt; it never changes the failed row.

On failure or budget interruption, the controller stops only its own active runner
and calls `adapter.py down <cell-directory>` with the exact instrument version.
That verifies resource ownership and removes only the recorded project/volumes/
private state/dependencies/worktree; raw phase evidence remains. If identity or
ownership changed, teardown refuses for coordinator diagnosis. Do not force-remove
unknown resources. The remote controller retains VM-level cleanup responsibility.


For controller checkpoints, the same pilot is available as granular cell commands:
`prepare --profile remote-pilot --tenants 500 --replicas 1`, then `deploy`,
`host-identity`, `run --k6-image ...`, and `down`. Repeat with fresh owned directories
for750 and1000 only after the previous `summary.json` is PASS. Assemble their cells
under `kind:m7-joined-remote-pilot` and check with `check-pilot`; it requires identical
pair/instrument/image/host and all three rows. The full `campaign.py pilot` is the
convenience form, not a resumable partially measured window. Preserve completed
cell checkpoints; an interrupted window restarts as a new cell, not a continuation
whose elapsed time is silently stitched together. `host-identity` returns only the
identity/source hashes and keeps its full inventory private.

Running sampler/probe host jobs are recorded with owner, PID and process-start
identity. `down` refuses changed/reused identities and stops only its own recorded
jobs before its own Docker resources. This supports budget-interruption cleanup
without a process-name sweep or stopping a peer. The controller still owns its
outer runner session and VM teardown.
