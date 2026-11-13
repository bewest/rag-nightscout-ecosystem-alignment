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

`observe` is present in the exact deployment source pinned by the intake.
The earlier `10014` source supports only bind/start/stop. Do not call `ports.observe` directly: that bypasses the
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

`tagged_capture.py` is the smallest capture driver. It invokes the reviewed
CLI `observe`, inspects the exact expected image ID and reads its source labels,
then runs `docker inspect` for exact ledger container IDs. Every container must
use that verified image; container-label inheritance is not assumed. It retains the
CLI output and an atomic ledger snapshot, then checks actual container custody.
A nonzero inspect result is `UNKNOWN`, including a missing container; its credits
remain held. Each capture uses a new private directory, a maximum of 90 seconds and 4 MiB of output per command. One capture has at most
128 held generations, 131 commands, 16 MiB of raw command output and 120 seconds
of elapsed time. These are instrument limits, not product capacity limits or
performance targets. Each command deadline uses the smaller of 90 seconds and
the remaining episode time after reserving four seconds for exit and cleanup. It records direct process
exit codes and refuses incomplete captures. It does not run lifecycle effects.
The coordinator places captures before and after the controller commands above.
Same-incarnation shutdown ACK joins and the clinical healthy-B/TIME adapters are
separate remaining boundaries.

Run a read-only capture only after the coordinator admits the exact prepared pair:

```bash
python3 tools/mt-bench/tagged-admission/tagged_capture.py \
  "$PRIVATE_SPEC" "$NEW_CAPTURE_DIRECTORY"
```

The owner-readable-only JSON spec contains `kind` equal to
`m7-tagged-admission-observation-v1`, absolute `controllerCli` and `state` paths,
the reviewed `controllerCliSha256`, an independently pinned `collectorSha256`,
and `expected`. The collector fingerprint covers these five source, test and
contract files; it is recorded separately and must remain unchanged through
the capture. It does not enter the legacy instrument fingerprint. The expected object contains
that same kind, the independently checked source pair, immutable image ID,
project, working directory and plan hash. It must come from the qualified
prepared image and private plan, rather than copying whatever a new observation
reports. The output directory must not exist. The driver records the spec and
all direct command results before validating them. A failed capture directory is
retained unchanged; a new episode needs a new directory and owner decision.


## Explicit operator-lease v2 observation

Source/model compatibility now also covers the exact independently reviewed
companion helper `f098dcc368a80fd0fdeb25c72316523a5c6dd955` and its version-one
`lifecycleOperator` protocol. The core/deployment admission constants above are
unchanged historical fixture pins. This compatibility work does not admit that
companion as an executable pair or transfer earlier image/native evidence.

A plan without that capability requires an explicit version-one worker ledger
and no control history. An enabled plan requires a fresh version-two ledger with
explicit `controlLeases`, including empty or CLOSED-only history. Missing,
unsupported, mixed or malformed versions refuse; there is no inferred migration.
The collector validates the fixed principal/file/tenant declarations, each intent
and its hash, source, plan, nonce, incarnation, exact lifecycle tag, one-credit
lease, container custody and at most one unclosed lease. Collisions with worker
incarnations, nonces or tags and any missing/foreign census tag refuse. A source
protocol or profile change needs an explicit review rather than schema widening.

Version-two intake adds a separate private `controlProcesses` capture list.
Workers retain their existing attribution and controls are marked `actor: control`;
control history and held credit are explicit even if authenticated occupancy is
zero. ISSUED, BOUND and UNKNOWN all retain one credit. CLOSED is reported only
from the validated ledger, not inferred from an absent process, local close,
zero census, or a claimed receipt. This observer does not authenticate a new
quiescence ACK or grant closure authority. Original application names remain
UNKNOWN for control actors.

The fixed capture inspects each unclosed control lease's original exact CID,
image, source, project, directory, service, StartedAt and operator-incarnation
label. Unbound or failed inspection remains explicit uncertainty with held
credit. No PID discovery, arbitrary program, SQL, or new observer reservation is
introduced. Control actors share the existing 128-held-generation, 131-command,
16-MiB and 120-second budgets. The atomic ledger must still match after all
inspections, including empty and CLOSED-only version-two captures.

The output separates authenticated `occupancy.workers` and `occupancy.control`
from declared `heldCredits`. The controller's occupancy must exactly match the
attributed census sums. `occupancyWithinHeldCredits` reports the comparison
without hiding an observed overage or refunding an unused credit. No occupancy
snapshot proves a peak or preauthentication absence. Every result still grants
no lifecycle authority and reports native acceptance UNMEASURED. Existing valid
version-one intake bytes are preserved; the separate collector fingerprint
changes with these reviewed source/test/contract bytes. The legacy measurement
selector and its fingerprint are untouched.


## Common ledger3 compatibility: source/model only

The declared common contract at deployment `cbd631364699210a0e8d452d58e45d675e03dd51`
adds host plan2, lifecycle capability2, ledger3, and observation2/stored-count2.
The fixed control classes are lifecycle-operator, restore-commissioner and
realtime-recovery. This instrument checks exact class principals and worker
DB identity, capability-derived worker/class tags, exact process custody,
primitive identities, generation bounds, two shared held control credits,
one active execution, and stopped-predecessor/setup-terminal constraints.
Authenticated physical occupancy is classed separately from held credits.
UNKNOWN with zero clients stays UNKNOWN and charged. This instrument never
retires credit, dispatches a control, or interprets a completion as quiescence.

`observe_envelope()` validates shared ledger/census attribution for either
version2 envelope. It does not certify the stored-count payload, selector,
PG-container custody, clinical isolation, or HTTP ledger; those existing oracle
checks must still run. The fixed capture command remains `observe` and never
executes stored-counts, SQL or a caller-selected command. Both held controls
consume the existing shared generation/command/output/deadline budgets.

`common_model_fixture.cjs` is a test-only actual-helper producer using an
explicit immutable archived common module. Its deterministic JSON is synthetic
model input, not output from an actual controller CLI. For the CBD archive,
control-recovery.js SHA256 is
`82eabd74efbadd2da0ed81fc1212b7447a46e0f6b10f34838cc48475b86f5143`;
fixture JSON SHA256 is
`b0912a4d13ec5718b1f34b3f84edbaffb00fc4d08f774b1bc84f44cf331c990e`.
The archive's actual controller still refuses host plan2 and emits legacy
version1 envelopes. Producer parity with the next repaired immutable common
checkpoint remains required before final selection. The historical CORE/DEPLOY
constants remain unchanged and are model fixture pins, not a selected new pair.
Legacy v1 and f098 v2 observations keep their existing output bytes.

Focused checks: `python3 -m unittest discover -s tools/mt-bench/tagged-admission -p 'test_*.py'`.
No native, resource, SQL, capacity or clinical acceptance follows from them.

Independent review found that Python numeric equality permitted malformed plan2
metadata (negative/bool declared worker maximum, bool/float census settings, and
an array resource ID). Plan2 now validates source-bounded integer capacities,
positive worker maxima, canonical string resource identity and exact census
primitive types before credit arithmetic or comparisons. Legacy validation/output
stays separate. The model system identifier is now the canonical synthetic
numeric string `123`; the same archived CBD helper regenerated its fixture.
The unchanged independent five-case malformed-primitive oracle is red on the
original collector3 checkpoint and green after this repair. These model findings
do not change the pending actual common producer/runtime boundary.
