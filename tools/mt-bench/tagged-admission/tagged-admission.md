# Tagged admission measurement

The proposed instrument measures the selected connection-admission candidate.
It does not change the reference measurement selector. Its first implemented
boundary is a read-only intake in `tagged_admission.py`. It attributes the source
observer's authenticated connection counts to exact ledger generations and
capabilities. The result always states `nativeAcceptance: UNMEASURED` and grants
no lifecycle authority.

The intake checks the exact core/deployment pair, image, plan hash, PostgreSQL
identity and epoch, original process container ID and start time, held-generation
roster and complete tag set. It retains the raw observer rows. Empty counts do
not release credits. A preauthentication backend can be absent from the database
census. Original application names remain `UNKNOWN` unless an actual snapshot
from the same incarnation supplies them. There is no live `state.json`: the
worker callback currently updates memory, and shutdown writes a private ACK.
An ACK from a different incarnation cannot supply a mapping.

The controller contract lives in the deployment repository at
`bindings/compose/multitenant/CONNECTION-BUDGET.md`.
The intake is pinned to the reviewed pair in its constants. A new deployment
observer command needs its own reviewed source pin before the intake admits it.
Do not substitute a similar source or change the old selector's refusals.

## Controller-owned driver boundary

The smallest real driver must use the deployment's fixed controller API:

```bash
node "$BINDING/connection-budget-cli.js" "$STATE" bind
node "$BINDING/connection-budget-cli.js" "$STATE" start "$DECLARED_SLOT"
node "$BINDING/connection-budget-cli.js" "$STATE" observe
node "$BINDING/connection-budget-cli.js" "$STATE" stop "$DECLARED_SLOT"
```

`observe` is a source-owner addition under review. The existing source supports
only bind/start/stop. Do not call `ports.observe` directly: that bypasses the
controller lock and durable observer reservation. Do not substitute an uncharged
`psql` command. The observer reports authenticated PostgreSQL connections only.

The driver must first verify the prepared pair and private files against the
actual built image and retained source-input attestation. It must retain exact
controller command results, direct process exit codes and immutable raw files in
an ignored run workspace. A failed or uncertain effect stops the driver; it does
not retry, remove locks, force a stop or refund a generation.

| Episode | Controlled effects | Required actual capture |
|---|---|---|
| Initial startup | Start declared slots in dependency order through the controller; process initialization may overlap after starts | Observer snapshots, actual source health, exact container identities, readiness and held-generation counts |
| Full application restart | Stop exact declared workers, collect matching ACKs, then start new generations | Old CID/start-time custody, retirement decisions, new incarnations and finite recovery |
| Partial restart | Stop and start the selected role through the controller | Before/after observer snapshots and independent healthy tenant B observation during the interruption |
| Storm | Run the declared request workload against the admitted services, within its pinned bounds | Sample counts, reserved observer costs, overflow refusals and recovery; never infer preauth absence from SQL |
| TIME and isolation | Use the clinical owner's source-pinned bounded workload and observer | Fresh accepted input, changed acquisition/checkpoint, finite due time, tenant isolation and unchanged authority checks |

The clinical owner must supply the actual healthy-B and TIME capture interfaces.
A role marked running, an empty census, or source-only tests cannot replace those
observations. Each episode retains its own actual source, workload and instrument
identity. Full/browser/clinical acceptance and final prcheck remain coordinator
owned. No episode has run through this new instrument yet.

`tagged_capture.py` is the smallest capture driver. It invokes only the reviewed
CLI `observe` and `docker inspect` for exact ledger container IDs. It retains the
CLI output and an atomic ledger snapshot, then checks actual container custody.
A nonzero inspect result is `UNKNOWN`, including a missing container; its credits
remain held. Each capture uses a new private directory, fixed 90-second command
deadlines and a four-MiB combined command-output cap. It records direct process
exit codes and refuses incomplete captures. It does not run lifecycle effects.
The coordinator places captures before and after the controller commands above.
Same-incarnation shutdown ACK joins and the clinical healthy-B/TIME adapters are
separate remaining boundaries.

Run a read-only capture after the reviewed observer API is frozen:

```bash
python3 tools/mt-bench/tagged-admission/tagged_capture.py \
  "$PRIVATE_SPEC" "$NEW_CAPTURE_DIRECTORY"
```

The owner-readable-only JSON spec contains `kind` equal to
`m7-tagged-admission-observation-v1`, absolute `controllerCli` and `state` paths,
the reviewed `controllerCliSha256`, and `expected`. The expected object contains
that same kind, the independently checked source pair, immutable image ID,
project, working directory and plan hash. It must come from the qualified
prepared image and private plan, rather than copying whatever a new observation
reports. The output directory must not exist. The driver records the spec and
all direct command results before validating them. A failed capture directory is
retained unchanged; a new episode needs a new directory and owner decision.
