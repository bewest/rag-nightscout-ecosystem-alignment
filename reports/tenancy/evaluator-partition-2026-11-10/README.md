# Evaluator partitioning (MT-EVALUATOR-PARTITION, M7), lane EP: stopped at the overlap premise, 2026-11-10

*Contributor-facing evidence record for lane EP. Captured 2026-11-10; not edited after capture.
Decisions read: [evaluator-static-partition](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-static-partition),
[pool-primitive-shared](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#pool-primitive-shared),
[evaluator-partition-now](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-partition-now),
[evaluator-revision-on-content-change](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-revision-on-content-change) and
[alarm-repeat-clock](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#alarm-repeat-clock).
Synthetic data only.*

## Outcome

The lane stopped before implementation, on the condition its brief named: **the evaluator's
notification output is not idempotent across two overlapping members.** The
[evaluator-static-partition](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-static-partition)
decision accepts duplicate evaluation "bounded to one heartbeat interval after a membership change"
because "the evaluator's outputs are idempotent by contract (... notification intent with stable
identity and suppression)". The shipping producer gives a new alarm effect, and so a new delivery
request, on every pass in which the evaluator output it reads came from a different runtime than
the previous pass. The decision says a measured duplicate external effect reopens the question;
this is that measurement. No code was committed. The queue, `decisions.md`, `contents.md` and the
register are unchanged.

## Anchors

| tree | commit |
|---|---|
| base: branch `codex/connector-reverse-20261110` (on the pool primitive `5a789903`, on #8898 `16a1fc2d`) | `1792063a28a2a018709a71af5efd65dc1c212c4c` |
| lane branch `codex/evaluator-partition-20261110`, worktree `externals/work/crm-evaluator-partition-20261110` (clone `externals/cgm-remote-monitor-official`, local, unpushed) | `1792063a28a2a018709a71af5efd65dc1c212c4c` (no lane commit) |
| alignment `main` when the record was written | `c6927c7b8` |

Queue state: `not-started` at the first read (alignment `54d6ac3c0`); `in-progress` at the second,
set by the coordinator's `61f67d71a` for this lane. The worktree has its own `npm ci` (Node v22.23.4).

## The finding

### Mechanism (file:line at `1792063a`)

1. The evaluator runtime stamps every output with a per-process `runtimeId = randomUUID()` and a
   per-process counter `outputRevision` (`lib/server/serve/evaluator-runtime.js:42,115`).
2. The producer decides a pass is a fresh output by comparing the tuple
   `[identity, runtimeId, outputRevision, inputCheckpoint]` with the tuple stored in the durable
   producer state (`lib/tenant-notifications/producer-state.js:43-44`). A fresh pass runs the
   legacy notification processing, which emits the highest unsnoozed alarm (`:70-79`). The repeat
   clock applies only when the pass is not fresh (`:49`).
3. Each emitted effect gets `origin = digest(['producer-transition-v1', revision, i])`, where
   `revision` is the producer-state revision (`producer-state.js:88`). The intent key is
   `'realtime-cycle:' + digest(identity) + ':' + origin` (`lib/tenant-notifications/producer.js:62`).
4. The store coalesces a re-presented intent only on the same key (`lib/tenant-notifications/postgres.js:55,64`);
   a new key inserts a new request (`:72`), which the notifier attempts.

The producer state is shared in PostgreSQL per (tenant, consumer), and both members use the same
consumer id. When two members both work one tenant, each pass sees the other member's
`runtimeId` in the stored tuple, so every pass is fresh, re-emits the active alarm under a new key,
and is delivered. The per-tenant advisory lock (`producer-state.js:10-15`) serialises the passes; it
does not merge them.

### Measurement (reproduced, reducer level)

Probe: [`reduce-probe.cjs`](reduce-probe.cjs) drives the shipping `reduce` with one synthetic urgent
alarm request, identical content, one pass per second for 10 s, repeat interval 60 s. It counts new
non-clear alarm effects. Output at `1792063a`:

| arm | runtime ids per pass | new alarm effects |
|---|---|---|
| single owner | A ×10 | 1 |
| two owners alternating | A, B, A, B ... | 10 |
| control: same alternation, one runtime id | A ×10 | 1 |
| two owners, output revision numbers also differ | A(1), B(7) ... | 10 |
| handover, A for 3 s then B | A A A B B B | 2 |

The control arm separates the cause: alternation alone gives 1; a second runtime id gives one
effect per pass. The handover arm shows that a clean hand-over (no overlap) re-sends the active alarm
once on the new member, as a single-site restart does.

**Read-derived, not run:** that each new effect becomes a delivered request end to end through
PostgreSQL and the alarm adapter (steps 3-4 above). No container was started.

### What this means for the gate

The queue gate requires that "bounded overlapping evaluation produces no duplicate logical
durable/external effect". With the decision's overlap bound (one heartbeat interval) and the
consumer poll every `pollIntervalMs`, an overlap would deliver up to one extra alarm per poll per
overlapping member, in place of one per repeat interval (60 s by default). Acknowledgement and
snooze still hold: the alarm snapshot and the applied acknowledgements live in the shared producer
state, and every pass re-reads acknowledgements (`producer-state.js:59-68`, read-derived). The
duplicates are early repeats of an active, unacknowledged alarm. They are not a wrong alarm and not
a silenced alarm sent again.

## Decision for the maintainer

**Question:** the decision tolerated overlap on the strength of output idempotence, and the
producer is not idempotent across runtimes. Which of these replaces that premise?

| option | mechanism | trade-off | operators would notice |
|---|---|---|---|
| (a) fence the overlap | Each member treats its eligibility as valid only until its last successful heartbeat start plus `leaseMs` (a local lease bound, under the database-clock expiry of its row). The runtime re-checks before it publishes, the consumer coordinator gets a pool gate like its activity gate (`evaluator-consumers.js:51-56`), and the notifier's `mayAttempt` (`:31`) already refuses when the runtime output is withdrawn. Membership table only, no per-tenant lock. | Overlap shrinks to work already in flight when validity ends (an adapter send). Depends on process clock rate against the database clock over one lease. | Nothing in normal operation; after a stall, the stalled member stops at once rather than at its next check. |
| (b) content-based freshness in the producer | Replace `[runtimeId, outputRevision]` in the producer tuple (`producer-state.js:43`) with the evaluator's content digest (`evaluator-runtime.js:18-20`), so two runtimes with identical output are one output to the producer. Repeats stay on the durable repeat clock. | Restores the decision's premise without coordination. Touches the alarm-repeat-clock work (BF-231). A restart or hand-over with unchanged content would no longer re-send at once; the next repeat comes from the stored `repeatAt`. Two members whose inputs differ by one new row still alternate until both have read it. Affects single owner and partitioned alike. | One fewer immediate re-send after an evaluator restart, which differs from a single site (single-site re-sends after restart because its alarm state is in memory). |
| (c) per-tenant commit fence | A per-tenant lease or fencing token on publish. | Rejected 2026-11-09 as unnecessary overhead; listed only because the decision says this measurement reopens it. | Nothing visible; more writes. |

**Recommendation** (long-term direction, reliability, compatibility): **(a)** now, keep (b) open.
(a) keeps the membership-table design and the single-tenant alarm behaviour unchanged, and makes the
overlap a fault-path residue instead of a planned window. (b) changes alarm behaviour for every
deployment, including single owner, and belongs with the BF-231 repeat-clock work if it is wanted.
Unmeasured for both: the overlap window and duplicate count in the lab, and the clock-rate
assumption in (a).

Single- or multitenant: multitenant only for (a) and (c). (b) changes the multitenant producer that
a single owner also uses.

## Other findings for whoever resumes (read-derived)

1. **Boot refusal blocks a rolling count change.** `evaluator-preview.js:37` throws when the slice is
   refused at boot (exit 78 through the CLI). During a 2→3 change, the first count-3 member boots
   while count-2 rows are live, is refused with `POOL_COUNT_DISAGREEMENT` and exits, so it crash-loops
   until every old member is gone. The vcpool has the same boot rule. A partitioned evaluator should
   boot refused, raise the alert and wait.
2. **The agreement rule stops the whole kind for the length of a rollout.** From the first count-3
   row until the last count-2 row is gone, every member is refused (`lib/pool-membership/assess.js:13`).
   The tick gap per tenant is therefore the rollout duration, not one lease TTL. Under the
   Kubernetes binding's `OrderedReady` policy (lane K record, `reports/tenancy/k8s-binding-2026-11-10/README.md:54`),
   a readiness probe tied to pool eligibility would deadlock the rollout: the new pod is never
   ready while old rows disagree, and the old pods are not replaced until it is. Readiness must not
   depend on eligibility, or the evaluator StatefulSet needs `Parallel`.
3. **Consumer timers are not gated by any per-cycle check.** The realtime consumer has its own poll
   and retry timers (`evaluator-consumers.js:98-99`) and its repeat-clock wake. A gate only inside
   `evaluator-runtime` leaves those passes running on a refused member; they then reach the producer
   with whatever output the runtime still holds.
4. **The graceful path has no overlap.** `close` stops consumers and the runtime before it deletes the
   member row (`evaluator-preview.js:16,23`), so a peer can become eligible only after this member
   has stopped. Overlap needs a member that stalls past its lease and resumes (a same-ordinal
   replacement registers after `register` deletes the expired row, `lib/pool-membership/postgres.js:115`), or the check-to-work interval the decision
   describes.
5. **Inspection listener in standalone mode.** Serving an evaluator inspection contract whenever the
   evaluator runs would open a default socket (`$XDG_RUNTIME_DIR/nightscout/evaluator.sock`) in every
   evaluator process. Today a standalone evaluator opens none, and test fixtures start several
   evaluator processes on one host through `serve.start` without `internal`
   (`tests/fixtures/evaluator-preview-worker.js:40`, `tests/fixtures/evaluator-consumer-worker.js:25`).
   Proposed rule: always serve it when partitioned; serve it in standalone mode only when serve.internal
   is configured explicitly.
6. **Environment names.** The canonical names are `MULTITENANT_POOL_EVALUATOR_PARTITION`,
   `MULTITENANT_POOL_EVALUATOR_MEMBERS`, `MULTITENANT_POOL_EVALUATOR_ORDINAL`,
   `MULTITENANT_POOL_EVALUATOR_LEASE_MS`, `MULTITENANT_POOL_EVALUATOR_DATABASE_URL` and
   `MULTITENANT_POOL_EVALUATOR_NAMESPACE` (`lib/pool-membership/config.js`, `envName`). The Kubernetes
   binding's provisional `NS_EVALUATOR_POOL_MEMBERS` and `NS_EVALUATOR_POOL_ORDINAL` map to the
   `MEMBERS` and `ORDINAL` names; the renderer's `evaluatorPool` should emit the core names. No alias
   was added.

## UNMEASURED

Everything in the lane's acceptance list: 2-member coverage, the 2→3 rolling change, the overlap
window, alarm tick continuity, the duplicate-ordinal control, count disagreement, flag-off
equivalence through the evaluator integration suites, the inspection read, the three break-it
controls, `test:unit`, tiers, write-boundary and eslint. No code changed, so none of them was run.
The store-level step of the finding (a new key becomes a delivered request) is read-derived.
