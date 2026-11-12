# Realtime publisher failure, evidence limits and joined controls

Captured 2026-11-12. **Original controlled move FAIL / cause UNCLASSIFIED.**
Core `47b43b6246ce7f94f1f1f0d01830495a78b28add`, deployment
`be95214a6cae427e1898b0ca6ce39825163ee291`, actual image
`sha256:6138dbf5cec8dc7c4897e3c1d969868a37bb7fb3eb0af46feca7595fdbb3f361`.
Fresh state/project `ns-evaluator-binding-proof-20261112-due`, nonce
`6ca2cfd8-d54d-4f11-b03a-e5f40aa1f1ab`, explicit 2API/2RT/shards2/3EV,
desired evaluator membership2-to3, Vault SERVER, diagnostics OFF. The original
host shipping fixture bytes were e91 inside be952. No live replay, recovery,
reset, source overlay or new stack was used to diagnose/author this repair.

## Measured failure and preserved state

[Unchanged original output](captures/original-move.log) reports four fulfilled
held-warm observations, then fails after19789.19ms with
`PLACEMENT_REPLACEMENT_FAILED_OR_UNCERTAIN`. Those four observations do not prove
the host activation callback returned, holder committed or publication completed.
[Journal](captures/operation.json) remains `started`,
[backend](captures/backend.json) generation2 versus [routes](captures/routes.json)
generation1. Existing original old/new process identities and source/image/
authority/compose digests are preserved; no credential values are included.

The [later read-only worker capture](captures/phase-health-events.json) found both
current workers healthy on the same exact image: realtime-1 assigned/warm for
both tenants; realtime-2 honestly idle with ownership resource held. This current
readiness does not reconstruct readiness at failure. Retained Docker event query
returned no events; it is not extra proof of the original old-process stop.
Original old/new identities are preserved in the journal. The incomplete routed
assignment has not been rolled back or silently recovered.

The source has an evidence fork after four observations: fixture next waits for
aggregate `alarmB.alarms.length===1`, asserts A count zero/B session unchanged,
then commits and awaits its row holder. Any callback error was swallowed by the
controller's action-channel catch, ending the child's input. A separate child
readiness failure or missing completion could also reach the same generic error.
The19789ms duration fits a15s callback wait but does not establish it.

Full original child stdout/stderr and caught host callback error were NOT retained:
stderr was buffered into an unused local variable, and the private child used
--rm. They cannot be recovered by reading current healthy workers or by claiming
that a later run reproduced them. This evidence gap remains explicit.

[Later typed overlap facts](captures/typed-overlap.json) include a genuine B401
repeat created1794498610792/acceptedAt1794498612957 around new boot start
1794498611831; B's later normal161 transition produced a separate clear. Source
routes clear as clear_alarm, excluded from the original alarm/urgent_alarm array.
Neither durable acceptance nor timing proves the original socket array count or
callback failure. acceptedAt is application finishedAt before commit, not SQL
commit-observation latency. Clinical2-to3 and the once-only post-EVALUATOR-handoff,
pre-RTmove completion capture passed separately; neither clears this move failure.

## Independent oracle defect and candidate repair controls

Candidate binding `9c889035eea93fbfff7ae373bee9054776f65625`, parentbe952,
changes host controller/fixture observability and transport-probe identity only.
Core47, authority, refusal/uncertainty, recovery/no-rollback behavior, map/pin/
checkpoint/session checks and deadlines remain unchanged. It does not claim the
original publisher cause is fixed. Independent review/fresh native qualification
are subsequent coordinator boundaries.

The source-verified [pure control](captures/probe-oracle-control.cjs) uses actual
core effectIdentity and verifies the original aggregate predicates via git show.
[Old oracle RED](captures/old-oracle-red.log),
[fixed oracle GREEN](captures/fixed-oracle-green.log): expectedB+clinicalB and
clinicalA+correctB wrongly failed before; clinicalB with zero expectedB and
clinicalA substituting post-cutoverA wrongly passed. An old nonce could substitute
B under aggregate counting. These are reproduced test-oracle defects independent
of the original live failure. The first restricted control attempt hit child-Git
EPERM and was NOT counted; the published red capture executed the actual invariant.

A shared bounded per-attempt nonce now enters synthetic MESSAGE, retained by the
source identity; envelope UUID/key/debug are insufficient. Distinct cold/A/B
payloads export exact expected digests. Held B probe must match exactly once on
B/alarm, with zero cold/A/wrong-client probes across all four clients; post-cutover
A must match exactly once on A/alarm, B remains exactly once. Unrelated clinical
notifications are retained/countable but cannot satisfy or substitute probes.
Duplicate, forbidden and old-nonce probes refuse; no accepted/refusal check is
weakened and no extra clinical write is added.

[New controls](captures/new-controls.log):17pass/0skip, all in-memory/temporary-file
or pure source contracts. They discriminate caught after-start failure,
readiness failure after a completed callback, holder commit failure, zero-exit
completion loss, signal/completion, bounded private capture and client metadata,
actual-source nonce identity, background/duplicate/cold/wrong-client/old-nonce
cases. No Docker startup/mutation is made by these new controls. Discarding caught
checkpoint detail in an exact9c scratch archive makes the
[checkpoint control RED](captures/checkpoint-ablation-red.log), then restored
source passes. Raw streams/errors are bounded in host-only operator-diagnostics
0700/files0600, outside the shared placement mount; public summaries have typed
stages/codes/durations/identities, not raw args or payloads. Client and holder
metadata are retained before four observations/exact wait and on PASS/FAIL.

[Final affected checks](captures/affected-controls.log):41pass/0fail,14 explicitly
unselected Docker-native platform skips. Existing owned OS-process recovery
simulations are included; they do not replace actual application/PG/placement
acceptance. No new full/browser/corpus/capacity campaign or live replay occurred.

Coordinator owns immutable fix review and ONE new qualification boundary. The
original state/image and all above failures/limits remain exact-scoped evidence.
Capture hashes: [sha256.json](sha256.json).
