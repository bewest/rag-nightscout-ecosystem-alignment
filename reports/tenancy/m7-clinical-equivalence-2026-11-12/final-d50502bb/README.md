# Final frozen-core clinical timeline equivalence — 2026-11-12

**Reproduced:** all six fresh cross-tree traces are byte-identical between
capacity baseline `5c60aec669362b032a10d6dd7ac368e9c61e8003` and frozen final
core `d50502bb6126bda2bb0af384569e1d95de114f2f`. This closes the specified
synthetic timeline criterion with the limits below; it is not complete clinical,
database, browser, deployment or capacity acceptance. Earlier D5 captures remain
unchanged and are not relabeled.

## Exact sources and instruments

New owned source worktrees were created for both commits; neither was repointed
from an old or peer tree and both remained clean. New owned dependencies were
copied only from this lane's prior owned exact-lock installation, not a peer
installation. Both source locks and the dependency lock have SHA256
`6418fe21c18346435f643b8496d6b7ec23c9c6de28f1925c3bb2028eb575e93e`.
[Environment](runs/environment.json) records source identities, Node 22.23.4,
npm 10.9.9, UTC and diagnostics OFF.

Unmodified clinical instruments were extracted from alignment commit
`275b3bb4b0b0f67d7b0552ef00a90420b6e6a73a`:

- `trace.cjs`: `47a1de898c1e4be658599832b91f3f04774cc9560c2d97abdc9a55860969f593`.
- `compare.cjs`: `0df9c949b1a897a14babe781cd645f15d1e332d5a2cbb8cd4b5bc2f8c55dd921`.
- `equivalence.cjs`: `1a37bcea1ab415786a7bc5b6b00764245c4eb5ef7b1b1feacd3d18170207a28b`.

[Execution instrument hashes](runs/execution-instruments.json) include the
unchanged observer and checker helpers. The orchestration's only path adaptation
selects the new `crm-clinical-final-{tree}-20261112` owned trees. The actual
[driver](instruments/run-clinical.py) verifies the exact starting source heads
and clean worktrees; post-run source checks are also clean. Publication replaces
execution-local state/workspace path prefixes and trailing log whitespace only; clinical trace bytes remain exact. The published driver is
an execution record rather than a directly runnable path-filled command.
[Raw/published artifact hashes](instrument-and-artifacts.json) preserve that
normalization. No source expectation or clinical value was changed to obtain
matching outputs.

## Fresh same-scenario comparisons

Each run replays the original one-hour lead-in plus twelve-hour synthetic
timeline through fresh shipping component/view/plugin instances. Deploy is the
instrument's five-plugin set, not the registry-default capacity profile. Full
is its 22-plugin set. No peer or D5 trace was reused.

| Plugin set | Schedule | Cycles per tree | Cross-tree verdict |
|---|---|---:|---|
| deploy | base one-second |46,801|IDENTICAL; zero differences|
| deploy | due, slow1000ms |6,093|IDENTICAL; zero differences|
| deploy | due, slow60000ms |288|IDENTICAL; zero differences|
| full | base one-second |46,801|IDENTICAL; zero differences|
| full | due, slow1000ms |46,917|IDENTICAL; zero differences|
| full | due, slow60000ms |1,032|IDENTICAL; zero differences|

[Trace manifest](trace-manifest.json) pins each independently executed trace's
whole-file SHA256 and cycle count. The fourteen synthetic traces, including
control/restoration, are retained as deterministic gzip files. Per-case
comparison logs and the [driver transcript](runs/cross-tree-driver.log) retain
actual comparator results. Each line compares evaluation instant, cycle kind,
first 128 bits of SHA256 over JSON `{emitted, requested, properties, due}` and
alarm summary. All JSON-serializable properties and requested messages
participate; functions are omitted by JSON serialization.

## Causal clinical property control

An isolated archive of exact final core changed the actual `bgnow` calculation
from `details.mean = mean` to `details.mean = mean + 1`. The actual
[patch](instruments/actual-bgnow-control.patch) and
[source hashes](runs/control-source.json) pin this run's byte-exact mutation.
The original/restored plugin SHA256 is
`8202e0223e6d604bf91c39065c083aed4b80d2a84456d47399ce5b0c9e579770`;
this run's mutant is
`926b95699f231c12f6492ebda55e306b991a7094b6de033a1f6d0560db006d4b`.
The copied historical `bgnow-control.patch` is an unused reference; the driver
applies the explicit replacement itself, not that historical patch.

On deploy/due60000 the [full-output comparison goes RED](runs/control-red.log):
286 of 288 output hashes differ, while all instants, kinds and alarm summaries
remain identical. Restoring the plugin bytes returns
[GREEN](runs/control-green.log), 288 of 288 identical. The
[control assertion](runs/control-summary.json) verifies those properties rather
than relying on alarm-summary equality alone. Product worktrees were untouched.

## Preserved schedule and database limits

The [within-tree checker](runs/within-summary.json) reproduces identical verdict
lines and alarm transition arrays between the fresh baseline and final core.
Deploy alarm sets and requested-message content pass at both slow timers.
Full-plugin alarm sets pass with 52 transitions, due at most 999 ms before base.
Full requested-message content remains **DIFF in both trees**: slow 1000 has 245
base versus 245 due content transitions; slow 60000 has 245 versus 156. The first reported slow-1000 timing difference is 1 ms late in both trees. These are
preexisting schedule-characterization limits, not full message equivalence
between schedules. The helper explicitly checks those cross-tree verdicts and
arrays; the underlying equivalence process exit code alone does not establish
content equivalence.

A uniquely owned actual PostgreSQL 16.15 container/database was provisioned and
queried, with [image/server facts](runs/pg-facts.json).
The unmodified observer records **zero Pool queries and zero Pool connects in
all 18 selected clinical executions**, including trace controls and within-tree
runs: the selected projection reads are in memory.
[Per-run observations](pg-observations.json) retain that boundary. A separate
[real query positive control](runs/pg-positive-control.log) records one query
and one connect. No PostgreSQL projection/RLS/authority/restore/pool coverage is
claimed from these clinical traces.

The first disposable PG setup used socket readiness, which saw the temporary
initialization server; the following version query then saw shutdown. That
[setup failure](runs/clinical-prepare.log) is preserved. The exact same
label-verified owned container was resumed only after TCP readiness; no
product or trace expectation changed. The provided corrected fresh-create
helper is not a second executed provisioning run.

[Cleanup](runs/cleanup.json) independently verifies the sole clinical container
is absent and zero owner-labeled containers remain. The initial combined
volume/private-file cleanup was rejected by automatic approval review before
execution. Read-only [mount/ownership inspection](runs/cleanup-ownership-inspection.json)
proved no bind mounts or volumes, only tmpfs. After coordinator clarification
that old benchmark/peer/V6 retention does not cover this new disposable fixture,
the approved narrower action removed only its exact container ID, with no
volume flag. Private credential files and logs remain retained at 0600. No peer
resource, volume or network was removed.

Candidate E same-checkpoint deletion/signature invalidation is absent because
this replay advances the checkpoint on every write. The timeline has no ordering
ties, so insertion-ordinal/typed-identity tie behavior is not discriminated.
Corresponding enabled-corpus invalidation/tie criteria remain independently
required. These traces also do not exercise actual ingestion, reconciliation,
external notification delivery, sockets, alarm transport, browser presentation
or lifecycle coordination. CPU/time/load in raw captures are incidental shared
host observations and support no speedup or capacity claim.

The separate [native identity leaf](../../m7-core-acceptance-2026-11-12/oidc-d50502bb/README.md)
records the final source's nine-stage matrix and three semantic controls.
Full source/browser/enabled-corpus acceptance, final paired binding proof,
programme records and prcheck remain coordinator work. No core changes,
cloud/pilot/capacity activity, queue/release edits or pushes were performed.

`make queue-check` was attempted in this isolated evidence checkout and stopped
at queue validation because historical programme gate working directories are
absent. [Output](runs/queue-check.log) is retained as local setup UNMEASURED, not
a product failure. No gate settings or programme records were changed.
