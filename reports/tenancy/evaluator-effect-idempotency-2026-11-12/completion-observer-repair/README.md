# Condition-based clinical completion observer

Captured 2026-11-12. Fixture-only repair; no runtime source, grant, admission,
notification protocol or image change. Actual fresh-pair clinical/restore/move
qualification remains a separate subsequent criterion. The preserved
[failed continuation](../paired-continuation-observation/README.md) remains FAIL.

Binding instrument history: `81bfb31e92de1c08b2a2c408c4194b636d5785ec`
(condition observation), `3b471f380f301e04886f819e14718e49763a7d42`
(session SQL timeout), `e91a1c8b00b77d1592f54b3b57ee6aecd68e3211`
(final-read fanout). Runtime image remains
`sha256:454d58b4d30a7a34f9d02005aab44dd7868cd3db6eb27e0f30fcbd623f91feab`,
core `cd4629159809fb3cffbc6f57626f98f3ffdbdda7` / image binding
`0f8749bc954812b9d384528da733680930e3b236`. A host fixture commit is not an image
label or a claim that the image was rebuilt.

## Mechanism and controls

Read-derived source ordering explains why a frame is not a durable-completion
barrier: notification state commits attempting before calling its adapter, then
commits accepted after the response in a separate transaction. A fixed 1500-ms
sleep cannot guarantee that latter commit. The acceptedAt field is an application
finishedAt timestamp captured before finish commit; creation-to-acceptedAt is not
measured SQL commit latency. The earlier leaf's numeric difference is only a
field difference, not a commit-observation claim.

The observer explicitly waits only for expected absent/pending/attempting
changed effects or incomplete fanout. It immediately refuses duplicated effects,
clears, wrong identity/configuration, cancelled changed effects, unknown states
and unexpected transport uncertainty. Uncertain is nonterminal in the durable
protocol; its rejection is a conservative requirement of this clean proof.
No assertion catch/retry loop exists. The original strict final oracle file is
unchanged and is required for success.

The original B401 frame wait's absolute 20-second budget is shared with completion
and capped by original durable repeat deadlines. At least 1500 ms after the
exact frame is observed remains mandatory, including repeated invariant checks.
Each SQL call has remaining-budget Docker CLI and PostgreSQL session
statement_timeout controls; no durable database setting changes. Both deadlines
are rechecked after reads and before final return. Final typed rows/fanout and
read/copy/validation timestamps plus count and a last-16 trajectory are retained
on PASS/FAIL; rows and fanout inputs have explicit bounds.

Fanout is copied before primary SQL for incomplete observations, so a newly
received event is not paired with an older SQL view. At candidate PASS, complete
durable rows are already known: the observer recopies latest fanout and reruns
the strict oracle before returning. This closes a reproduced draft-observer gap
where an event received during final SQL was omitted. This is an instrument gap,
not a reproduced runtime duplication finding.

[Focused union](captures/focused.log): 25 pass, zero failures, one explicitly
unselected shipping integration skip. No native runtime acceptance is claimed.
Controls cover in-flight-to-accepted, missing frame/fanout, immediate sticky
violations, post-read monotonic/repeat deadline refusal, SQL budget construction,
and original socket/overlay/oracle contracts. Removing the minimum interval
from a scratch copy goes red at `assert(h.time>=1500)` in the
[ablation](captures/minimum-window-ablation.log). The duplicate-during-final-SQL
control on original 3b goes red with `Missing expected rejection` in its
[original capture](captures/original-final-fanout-control.log); exact repaired
source passes that same test. These controls distinguish the observation bugs,
not application clinical semantics.

## Retained-state custody and next boundary

Coordinator-authorized stop-only operation verified exact project and owned
working-directory labels for four lane-owned projects, then stopped all 54
containers. [Exact IDs/states](captures/owned-retained-stop.json) are recorded;
containers, volumes, images and private state remain retained. No down/remove,
reset/replay, foreign project stop or source overlay occurred. Immediate host
load averages are context only and do not identify the timeout's cause.

The [later starting context](captures/starting-host-context.json) verifies all
54 owned retained containers remain stopped; 16 logical CPUs, load averages
0.625 / 1.936 / 4.783. Proposed fresh qualification uses a new project/state and
nonce, same explicit 2API/2RT/shards2/3EV desired2-to-3 / Vault SERVER / diagnostics
OFF topology and the unchanged runtime image, with executed host instrument e91
attributed separately. Independent final-union reviews approved e91, followed by the coordinator's
concrete fresh-boundary authorization. No fresh stack had started when these
captures were taken; later activation/proof must be recorded separately.
Capture hashes: [sha256.json](sha256.json).
