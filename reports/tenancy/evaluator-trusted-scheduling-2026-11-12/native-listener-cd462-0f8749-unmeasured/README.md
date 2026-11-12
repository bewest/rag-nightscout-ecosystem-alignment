# Repaired-pair collector: once-only UNMEASURED observation

Captured2026-11-12. The existing successful-time-work assertion returns
UNMEASURED / M7_EVALUATOR_PROGRESS_NOT_OBSERVED. This is preserved as measured,
not changed to PASS and not diagnosed as a scheduler defect or future due instant.
There was ONE authorized21.259140285197645s observation; no extension/retry,
cadence/plugin change, work trigger, settings write or lifecycle operation.

Exact runtime corecd4629159809fb3cffbc6f57626f98f3ffdbdda7 / deployment
0f8749bc954812b9d384528da733680930e3b236. Independently inspected image
sha256:454d58b4d30a7a34f9d02005aab44dd7868cd3db6eb27e0f30fcbd623f91feab
has both exact source labels. All three exact evaluator containers/StartedAt,
runtime UUIDs, ordinals, owner coverage and generations stay stable before/after.
Only NEW observe-project state was read after RT's explicit no-write release;
all earlier failed/stopped projects remain untouched. The host clinical instrument
is separatelye91a1c8b00b77d1592f54b3b57ee6aecd68e3211, not relabelled as the
running0f image. Collector source remains alignmentd58756664c4a29c2261c0cbd8c405836e2860179,
helper SHAc9e0370e8a3ca4d08dfd70b1290a36a0d57f33c34f3a5639a2e6d81b77b707e8.

## Exact observed counters

Both synthetic IDs were selected on EVERY evaluator, three snapshots10s apart:
9/9 successful private calls,17362 encoded response bytes,6 rows per snapshot,
including4 retained foreign rows. All foreign work/failure counters stay unchanged;
there is no ownership reset or observed failure delta. Parallel round wall sum
1.2249531610868871s, individual instance-exec wall sum3.507815989200026s.
These aggregates are not CPU measurements or subtractable latency percentiles.

| Owner | Acquisition baseline→end | Time cycles baseline→end | Legacy cycles | Failures | Generation |
|---|---|---|---|---|---|
| A/evaluator-2 |1→1|75→94|76→95|0→0|11→11|
| B/evaluator |2→2|5→5|7→7|0→0|15→15|

A completes19 time-only jobs. B completes no additional acquisition/time job,
so the existing EVERY-owner work/time predicate is unmet. B's lastCompletedAgeMs
rises73800→94621ms, while legacy evaluation.ageMs is885→700ms. Source confirms
unchanged-signature checks call confirm without completing a clinical job; legacy
freshness/readiness cannot substitute for successful-work counters. Both owners
remain ready/code null/no alert, with stable checkpoint/output revisions.

## Actual due state is missing, not inferred

Captured private module-v2 rows omit evaluator dueAt/dueReason/current requested
model. B delivery.repeatAt=null/state idle/passes13 at both ends is a CONSUMER
clock, not its evaluator timer. It cannot establish the evaluator's next due.
Runtime health internally has dueAt/dueReason, but the versioned inspection DTO
mapping drops them. Thus actual B evaluator due state is UNMEASURED here.

Read-derived scheduling rule: runtime.arm chooses an exact future due, or a slow
interval only when due.slow is nonempty; evaluator-due adds alarm-message slow
when the CURRENT result requests notify. A historical accepted alarm does not
prove that current premise. A current-notify premise would make flat time-work
suspicious, but the captured DTO cannot establish it. Neither expected no-op nor
stall, nor any specific future deadline, is claimed. A blind longer observation
cannot repair that missing state contract or retroactively clear this capture.
Root/D6 own opportunity classification and any separately approved completeness
work before another exact-source observation.

## Offline recomputation and controls

The unchanged decoder/assessor recomputes UNMEASURED from complete captured rows.
Actual-capture mutations independently refuse hidden failures, foreign work,
runtime reset and missing foreign row as FAIL. Merely wrapping this proof as
PASS still returns NOT_OBSERVED. Restoration returns the ORIGINAL UNMEASURED,
not GREEN. These are offline capture controls, not live stopped-worker/restart
claims. Raw and deterministic-gzip decoded bytes match; hashes and controls are
in classification.json. No full capacity/pilot/recovery receipt was fabricated.

This run proves actual private transport/typed completion data was collected;
it does not close the every-owner time-progress criterion. RT/root separately
reported stock/restore, settings, strict clinical3-effects/fanout and controlled
RT movement PASS on this fresh pair. Those outcomes neither clear this observation
nor are invalidated solely by its insufficient unclassified opportunity. Earlier
195c collector PASS and failed clinical captures stay immutable and source-specific.

## Observation instrument review boundary

Host-only socket diagnostics retain original predicates/options20s; exported ACK
tails were fixed to64/count/truncation ind229 after a reproduced200-ACK bound gap.
A later condition-observer81 approval by this lane missed stale final fanout and
was explicitly withdrawn. Independent reproduction against3b returned false PASS
when a duplicate arrived during final SQL. Finale91 synchronously recopies fanout,
reruns the unchanged strict verdict and rechecks both deadlines; the same targeted
race now refuses. Its9 observation tests plus unchanged6 oracle/5 diagnostic tests
pass independently. Numeric1..20000ms session SQL/CLI budgets, minimum1500ms
observation and original absolute20s/repeat bounds remain. These test-instrument
reviews do not change the running image or collector's counter policy.

Private originals remain0600 under a0700 lane directory; only IDs were projected
from credential-bearing primer output. No raw credentials/event secrets were
exported. The no-write window was released immediately on completion. Root owns
final source freeze/acceptance; no cloud, broad campaign or new service resource
was run by this lane. Capture manifest pins raw/public bytes; only workspace paths
in text/scripts are normalized. JSON/JSONL/gzip evidence is unchanged.
