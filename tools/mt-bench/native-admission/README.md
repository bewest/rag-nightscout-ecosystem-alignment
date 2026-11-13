# Admission commissioning

This first executable episode qualifies wiring and normal retirement only. It
uses core074 and deployment3d13 with the independently audited32b image. It does
not claim the full clinical admission episode or native acceptance.

`profile.cjs` admits the exact source/overlay before evaluating the actual expanded
configuration. The explicit qualification topology is API2/realtime2/evaluator2,
four realtime shards and16 synthetic tenant slots. The finite source profile
retains actual requested pool ceilings and held lifetime lanes, direct group
ceilings4 (persistent feed clients separately1), metadata observers2, control1,
bootstrap2, and one API generation of uncertain overlap. It derives PostgreSQL314
from258 current-worker credits,48 overlap,5 external and3 reserved. These are
configured ceilings, not measured connections or a production recommendation.
Cold admission1/pending9 with25..75ms jitter is an explicit functional experiment;
source startup producers remain4. Unknown/source/roster/capacity changes refuse.

## Executable boundary

Commands below take an owner-private prepared directory/spec, not public secrets:

```
node profile.cjs PRIVATE_SOURCE_INPUT NEW_PROFILE_OUTPUT
python3 commissioning.py prepare PRIVATE_PREPARED_ROOT NEW_PLAN_OUTPUT
python3 commissioning.py dry-run PRIVATE_PLAN NEW_RECORDING_OUTPUT
python3 commissioning.py preflight PRIVATE_PLAN NEW_PREFLIGHT_OUTPUT
# Only after the coordinator reviews and authorizes the exact plan:
python3 commissioning.py run PRIVATE_PLAN NEW_EPISODE_OUTPUT
```

All output directories are new and mode0700. Inputs are regular nofollow private
bounded JSON files. The plan pins the qualified image/qualification bytes,
controller and separate collector fingerprint, source pair, prepared-file digests,
nonce project, source environment, proposed port/subnets and program file hashes.
The actual source profile, state and image must agree; old479/90f does not qualify
this episode. The prepared image tag is already bound to the qualified ID.

The real run first checks the local Docker context, all Docker network ranges,
IPv4 routes, existing project resources, listener ports and declared address
capacity. It repeats that check immediately before allocation; default forwarding
is recorded separately from allocated networks. It never picks an alternative or
changes a foreign resource. A collision or unknown input refuses. The preflight
is a snapshot, not an atomic reservation against another owner.

The fixed sequence starts only PostgreSQL/Vault as infrastructure, waits for
source health, runs infrastructure bootstrap once with `--no-deps`, binds the
controller, and starts admin/API/API2 through the shipped controller. Actual
health children run with already-existing worker claims; claim file bytes must
remain unchanged. Three charged tagged captures bracket start, a clean API
stop/restart and retirement. Matching private ACK/source/nonce/full tags and
ledger retirement are checked. No tenant or clinical DATA is provisioned.
The full11-role profile remains declared even though this first episode starts
only three workers. Unstarted roles are not silently removed from the budget.

Normal worker stops use the controller. Finally capture validates every exact
CID, StartedAt, project, working directory, service and image before stopping. Each failed row is retained while later owned rows still receive cleanup attempts. A successful bounded full Docker roster can prove that an old known CID was removed, without inferring PostgreSQL credit retirement.
Infrastructure and an unbound/failed worker may need an exact-CID emergency stop;
this cleanup never refunds a generation or claims a clean ACK. This fallback is
part of the concrete plan for coordinator review, not ordinary restart authority.
A timed-out host command can leave Docker daemon work uncertain: the result keeps
that uncertainty even when the current retained containers are stopped. No
cleanup removes containers, networks, volumes, claims, locks or history.
If preflight failed before allocation, cleanup performs no Docker search/stop.

Host commands have a fresh process group, a retained WNOWAIT leader through
TERM/KILL/drain/reap, finite deadlines and kernel file-size limits. The episode
has900 seconds (90 reserved for cleanup),384 host commands (64 reserved) and32MiB host output (8MiB reserved).
Each of three nested read-only collectors has its own existing120-second/16MiB
bounds; at most three held commissioning workers yield at most15 nested commands.
Thus nested raw capture allowance is another48MiB, not included in the host32MiB.
Health is polled every two seconds under a 90-second per-readiness instrument bound. The regular command allowance covers the worst-case six readiness schedules. Parent collector stdout/stderr has its own 2 MiB per-call bound, counted in host output; the 48 MiB allowance is internal raw collector files. These are instrument/resource bounds, not product latency SLOs.

## Checks and remaining work

Run `M7_NATIVE_TEST_PREPARED=PRIVATE_PREPARED_ROOT python3 test_commissioning.py`.
The required actual private preparation is an explicit fixture; missing input
fails rather than skipping. Tests cover child status, exited-leader descendants,
closed-output timeout, output caps, foreign routes/networks/ports/projects,
address capacity, zero-effect preallocation cleanup and recording protocol order.
Recording output always says commissioning NOT_RUN/native UNMEASURED.

Actual commissioning must still demonstrate real bootstrap, selected entrypoint,
health and clean retirement on the new image. Full clinical work is separate:
honest cold/storm, whole-cohort restart, partial restart with independently healthy
B, successful acquisition/TIME and isolation still require joined traffic/IPC
observers. HTTP readbacks are not an independent SQL stored-count oracle.
The later fixed count-only controller API is separately owned and must join its
new source/image/instrument/profile declaration before that campaign. Its private
selector is `{version:1,kind:"native-synthetic-stored-counts",runId,tenants}` with
`m7-native-` plus16..32hex marker; selected and foreign aggregate counts must be
checked without extra uncharged SQL, control-reserve borrowing or payload output.

If the main runner exits or records incomplete cleanup, the coordinator can run
`python3 cleanup.py PRIVATE_ROOT_CLEANUP_SPEC NEW_CLEANUP_OUTPUT`. That separate
180-second path checks the exact project/base/image/CID/StartedAt custody,
continues after individual errors and never changes the ledger or grants a clean
retirement. Unknown daemon errors cannot prove absence. No-allocation specs have
zero cleanup effects.
