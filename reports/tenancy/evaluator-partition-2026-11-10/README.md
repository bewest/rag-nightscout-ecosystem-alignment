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

## Resumed, 2026-11-10: implemented and measured

*Appended after the maintainer's decisions [alarm-output-idempotent-by-content](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#alarm-output-idempotent-by-content)
(option b) and [pool-desired-count-in-table](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#pool-desired-count-in-table).
The sections above are the stop record and stay as captured; the figures above that say UNMEASURED are
superseded by this section only where it gives a measurement.*

### Anchors

| tree | commit |
|---|---|
| base: `codex/connector-reverse-20261110` | `1792063a28a2a018709a71af5efd65dc1c212c4c` |
| lane branch `codex/evaluator-partition-20261110`, worktree `externals/work/crm-evaluator-partition-20261110` (local, unpushed) | `cb1b751d4e3875b9b9c250b1a3b6236f7c926aa4` (one commit; 35 files, 1880 insertions, 214 deletions) |
| alignment `main` when the measurements ran | `ee1621b38` |
| lab harness | [`tools/tenancy/evaluator-partition/run.cjs`](../../../tools/tenancy/evaluator-partition/run.cjs) |

Every run used one dedicated `postgres:16` container (server 16.15, name `ns-ep-pg-*`), a random password in a
mode-0700 scratch directory, and a `*_test` database. The container, its volume and the credentials were removed
afterwards (`docker ps -a` lists no `ns-ep-*`). The local mongod on 27017 was not used. Node v22.23.4.

### Design (file:line at `cb1b751d`)

| element | where | what |
|---|---|---|
| content freshness | `lib/tenant-notifications/producer-state.js:50-53` | The freshness tuple is `[identity, contentDigest, inputCheckpoint]`. An eligible output without a 64-hex digest is refused (`NOTIFICATION_PRODUCER_CONTENT_REQUIRED`). The runtime publishes the digest it already computes (`lib/server/serve/evaluator-runtime.js:123`). |
| content-derived origins | `producer-state.js:72,82,91,109` | Every emission is attributed to the step that caused it: `['output', prior output, next]`, `['repeat', next, stored repeatAt]`, `['ack', ack key, reset scope]`, `['reset', ...]`. The origin is `digest(['producer-transition-v2', cause, index within cause])`. The cause uses only shared durable state and content, so two evaluators replaying one step derive one origin, hence one `dedup_key`. Distinct steps never share one: a return to an earlier output (A→B→A) has a different prior output, and each repeat has its own slot. |
| clear provenance, acknowledgement, snooze, BF-231 repeat clock | unchanged code paths | `postgres.js` keeps a pending clear only while the current intents carry its exact origin. A clear's origin is stable across empty polls because effects persist in the producer state. Checked by the existing producer tests (stable clear origin, ack silence, stale clear retired, control clear with failed acquisition; all green) and by new tests: two acknowledgements of one output give two distinct clear origins. **No mismatch found.** |
| desired count | migration `0002_pool_desired_count` (`lib/pool-membership/postgres-candidate.json:17-19`) | Adds `pool_desired(pool_kind, members, previous_members, slice_rule, revision, updated_at)`. On `pool_membership` it replaces `expected_members` with `applied_members`, the count this member currently works. The census pin moves to `08f21d64…d60f` (`lib/tenant-operations/catalogues.js:23`). |
| agreement and switch | `lib/pool-membership/assess.js:28-35` | The count in effect is the desired count once every ordinal below it is live. Until then, and only while no live row has applied the desired count, it is the previous count if that count is fully live. Otherwise it is the desired count with the missing ordinals reported. A completed switch therefore never falls back when a member is lost: that would be an implicit stale-slice takeover, which stays undecided. Refusals: `POOL_SELF_NOT_LIVE`, `POOL_COUNT_UNSET`, `POOL_RULE_DISAGREEMENT`, `POOL_DUPLICATE_ORDINAL`. A member beyond the count is eligible with an empty slice. |
| applied count | `lib/pool-membership/postgres.js:185` | A member writes its applied count as soon as it changes, and again on every heartbeat. |
| operator command | `lib/pool-membership/operator.js:34-48`; `lib/server/serve/admin-preview.js:53,97`; contract `pool-operations` (`/pool/get`, `/pool/members`) | The admin role composes `pools` beside, or instead of, `ownership`. It uses a separate operator identity: SELECT on membership, INSERT and column UPDATE on `pool_desired`, nothing else (checked at boot and by the database). `setPoolMembers` records the count currently in effect as `previous_members`. |
| environment | `lib/pool-membership/config.js:47` | `MULTITENANT_POOL_<KIND>_MEMBERS` is refused with a message that names `setPoolMembers (POST /pool/members)`. A pod carries `_PARTITION`, `_ORDINAL`, `_LEASE_MS`, `_DATABASE_URL` and `_NAMESPACE`. |
| evaluator gate | `lib/server/serve/evaluator-pool.js` | One `slice()` per scheduled pass (`evaluator-runtime.js:207`), single flight, shared by the runtime and the consumers. A standalone evaluator admits every configured tenant and reads nothing. |
| runtime | `evaluator-runtime.js:114,152-166` | A withdrawn tenant is fenced (generation), its pending work dropped and its component and output retired. The code is `EVALUATOR_POOL_NOT_IN_SLICE` or `EVALUATOR_<reason>`. A cycle that finishes after a withdrawal does not publish. An entering tenant starts with an acquisition on a fresh component. |
| consumers | `lib/server/serve/evaluator-consumers.js:55` | A tenant the gate does not admit gets no selection, attempt, retry or repeat wake (`EVALUATOR_CONSUMER_POOL_*`). On a slice change every tenant is woken, so the repeat clock resumes from the shared producer state (`evaluator-preview.js:80`). |
| boot | `lib/server/serve/evaluator-preview.js:41-43` | A refused member boots and waits; boot no longer exits. Readiness is boot, never eligibility. Every member warms every configured tenant read-only (`evaluator-readiness.js:99`). |
| inspection | contract `evaluator-inspection` (`/evaluator/inspect`); `evaluator-preview.js:97`; `lib/server/serve/evaluator-config.js:142`; `internal-listener.js:22,50` | Configured values (mode, ordinal, rule, lease, number of configured tenants) are kept separate from observed membership (desired, previous and effective count, revision, live rows with applied count and heartbeat age, conflicts), the gate (eligible, reason, reads, refusals, heartbeats), and, for each configured tenant, its assigned ordinal, admission, code, cycles, revision and delivery state. Every partitioned member serves it. A standalone evaluator serves it only with `NS_SERVE_INTERNAL_SOCKET`, or with `_HOST` and `_PORT`. |
| vcpool | `lib/tenant-connector/runtime.js:132`, `connector-inspection.json` | The vcpool reads its count the same way: its slice now follows the table each cycle, and inspection reports the observed count. Its boot rule (exit 78 on a refusal at boot) is unchanged. |

Kubernetes names (canonical, no aliases): `NS_EVALUATOR_POOL_ORDINAL` → `MULTITENANT_POOL_EVALUATOR_ORDINAL`, from
the pod-index label. `NS_EVALUATOR_POOL_MEMBERS` has no environment counterpart. The renderer drops it, and the
operator sets the count with `setPoolMembers`. The binding also needs `MULTITENANT_POOL_EVALUATOR_PARTITION=on`,
`_LEASE_MS`, `_DATABASE_URL` (secret) and `_NAMESPACE`, plus a `pools` block and an operator identity on the admin role.

### Measurements (reproduced)

Reducer probe ([`reduce-probe.cjs`](reduce-probe.cjs), now with a content digest), identical content, 10 passes:

| arm | `1792063a` | `cb1b751d` |
|---|---|---|
| single owner | 1 | 1 |
| two runtimes alternating | 10 | **1** |
| handover A→B | 2 | 1 |
| control: one runtime id | 1 | 1 |
| two runtimes, revisions differ | 10 | 1 |

Lab, final run at `cb1b751d`: `SUMMARY 22 checks, 0 failing`. Setup: 6 synthetic tenants with one low reading each,
so an urgent alarm is active. Repeat (tenant heartbeat) 3000 ms, lease 2000 ms, heartbeat every 666 ms, evaluator
pass 500 ms, consumer poll 1000 ms. Inspection was sampled every 100 ms. The oracles are request rows read
directly from PostgreSQL (cadence from `created_at`; a duplicate is two alarm requests of one tenant less than
2400 ms apart) and the sink's own log.

| gate | output |
|---|---|
| standalone inspection | `mode standalone`, `observed: null`, 6 configured, 6 admitted, `heartbeats: null` |
| standalone baseline, 12 s | 3–4 alarms per tenant, minimum gap 3000 ms, duplicates 0, 23 rows / 23 distinct keys / 23 sink deliveries |
| standalone without explicit serve.internal | boots (`ready true`), opens no inspection listener |
| **two evaluators owning every tenant at once, 15 s** | 4–5 alarms per tenant, minimum gap 3000 ms, **duplicates 0**, 26 rows / 26 keys / 26 deliveries, no request delivered twice |
| restart with identical output | next delivery 2806 ms after the restart, 3338 ms after the previous one: it waits for the repeat clock (the accepted behaviour change) |
| 2 members cover every tenant exactly once | m0 `11,e2,e7`, m1 `22,e1,e4`, as `sha256-modulo-v1` predicts |
| 2 members, 9 s | duplicates 0, worst evaluator-tick gap 536 ms |
| count set to 3, ordinal 2 absent | `effective 2, switching true`; both members keep their slices, no refusal |
| **2 → 3, no restart** | m2 boots in 587 ms; all three switch 12 ms after m2 is ready; m0 and m1 keep their PIDs |
| **measured overlap and gap** (5 of 6 tenants move) | longest doubly-owned interval **100 ms**, longest unowned interval **200 ms** (at 100 ms sampling) |
| 2 → 3, no duplicate | 24 rows / 24 keys / 24 deliveries, duplicates 0 |
| **2 → 3 tick continuity** | worst gap per tenant 528–594 ms, against a lease of 2000 ms |
| 2 → 3 delivery continuity | worst gap 3977 ms, against repeat + lease of 5000 ms |
| **duplicate ordinal** | all 4 members refuse `POOL_DUPLICATE_ORDINAL` within 798 ms; one alert line each; **0 requests delivered** during 7 s; inspection still answers |
| duplicate removed | one recovery line per member; every tenant delivers again within 4503 ms |
| count missing from the table | all 3 refuse `POOL_COUNT_UNSET`; restored through the admin role, all eligible at count 3 |
| member 2 killed (SIGKILL) and restarted at once | the dead row is a duplicate ordinal until its lease expires. Eligible again 1575 ms after the kill. Whole kind unowned for 1000 ms, m2's tenants for 1500 ms. Worst delivery gap 5536 ms. Duplicates 0 |
| graceful restart of member 1 | its tenant unowned for 500 ms, no overlap, duplicates 0 |
| `MULTITENANT_POOL_EVALUATOR_MEMBERS=3` | boot refused: `… MULTITENANT_POOL_EVALUATOR_MEMBERS is not read: the member count is set in the pool table with the admin role's pool-operations setPoolMembers (POST /pool/members)` |

The gap is about one heartbeat plus the lease only when a member dies hard: the 1575 ms measured is under the
2000 ms lease, because the dead row's last heartbeat was up to 666 ms old. With a graceful exit or a scale change the
gap is about one evaluator pass, 100–500 ms here.

Other checks at `cb1b751d`:

| check | result |
|---|---|
| `npm run test:unit` | 3219 passing, exit 0 (base record: 3201) |
| `npm run test:tiers` | `630 test files, 8 tiers: ok` (new `tests/evaluator-partition.test.js` in the unit tier) |
| `npm run test:write-boundary` | all 9 adapter entry points checked |
| integration on PostgreSQL 16, flag off: `evaluator-consumers`, `evaluator-consumer-load`, `evaluator-consumer-timer-churn`, `tenant-activity`, `tenant-current-state-recovery-proof`, `tenant-durable-replay`, `pool-membership` | 45 passing, exit 0 |
| `tenant-projection-evaluator.integration` (`NS_TENANT_PROJECTION_EVALUATOR_TEST=1`) | 7 passing |
| `pool-membership.integration` (two kinds, unset count, 2→3 with no fallback after the switch, operator privileges, duplicate, lease expiry) | 10 passing |
| connector lab `tools/tenancy/connector-reverse/run.cjs` against this head (count set through the operator; `MEMBERS` removed from its environment) | `SUMMARY 24 checks, 0 failing` |
| eslint on the 29 changed JS files | 0 errors; 19 warnings, all `security/detect-non-literal-fs-filename` on config and fixture file reads |

### Break-it controls

Each control was applied to the worktree, run, and restored. `sha256sum -c` against copies taken first printed `OK`
for all six files.

| control | break | symptom |
|---|---|---|
| restore `runtimeId` in the tuple | `producer-state.js:53` back to `[identity, runtimeId, outputRevision, inputCheckpoint]` | **red**. Unit: 4 failing (`PRODUCER_RUNTIME_NOT_IDENTITY`, `PRODUCER_RESTART_NO_IMMEDIATE_RESEND`, …). Lab overlap: duplicates at 165 and 181 ms. The pending requests also cancelled each other, so 4 of 6 tenants got **one** alarm in 15 s (worst gap 14967 ms). The restart check went red: re-sent after 1579 ms. |
| drop the idempotence key | intent key + `randomUUID()` per pass | **red** in the standalone baseline as well as under overlap: 0–32 alarms per tenant in 12 s, minimum gap 19 ms; 140 rows under overlap. The key protects re-presentation on every pass, not only overlap. |
| revert to boot-only filtering | the gate reads membership once | **red**. The switch never happens (`switchAfterM2ReadyMs 15052`, `after null`); e4 and e7 are doubly owned for 26100 ms. The duplicate ordinal is not refused: 9 requests delivered during it, alerts `[0,0,0,1]`. Content identity kept the doubly-owned tenants at 0 duplicates. |
| skip the per-cycle agreement check | `slice()` ignores a refusal | **red**. Integration: 3 failing. Lab: the duplicate is not refused, 10 delivered, no alerts. |
| remove the cycle fence (unit) | `evaluator-runtime.js:114` removed | **red**: `POOL_CYCLE_FENCED` |
| remove the consumer gate (unit) | `evaluator-consumers.js:55` disabled | **red** on the inactive-state assertion. Delivery to the withdrawn tenant was still blocked by the notifier's `mayAttempt`, because the runtime had withdrawn its output: defence in depth. |

### Findings for the maintainer

1. **A killed member's serve.internal socket file blocks its restart in the same runtime directory.**
   Observed: `SOCKET_IPC_PATH_EXISTS` at boot. In Kubernetes, a container restart within one Pod keeps a shared
   `emptyDir` `/run/ns-ipc`, so a crashed partitioned evaluator would not come back until the Pod is replaced. This is
   existing serve.internal behaviour (endpoint-composition lane). It matters now because every partitioned member
   opens a socket. The lab modelled Pod replacement by removing the file.
2. **The admin configuration now accepts `pools` without `ownership`** (at least one service is required). This
   changes the admin role's configuration contract; the existing refusal of an empty composition still holds.
3. **The vcpool still exits 78 when it is refused at boot** (the lane R rule). With the count in the table, a
   partitioned vcpool started before the operator sets its count exits with `POOL_COUNT_UNSET`. Aligning it with the
   evaluator (boot refused and wait) is a small change; it was not made here because the decision named the evaluator.
4. Every member warms and observes every configured tenant (read-only). The configuration still lists all tenants
   on every member.

### UNMEASURED

- `multitenant-preview-process.integration` was not run: it creates its own containers outside the `ns-ep-*`
  naming. The full suite, the browser and dom tiers, and `prcheck` belong to the coordinator's frozen-head acceptance.
- Overlap while two members hold different content (one has read a new row and the other has not). Every lab phase
  holds one reading, so content never changed during an overlap.
- Scale-down 3 → 2 in the lab: covered only by the integration test (immediate switch, empty slice beyond the count).
- A partitioned vcpool with more than one member. Kubernetes and the binding itself (no cluster on this host).
  Database failover, clock behaviour across replicas, lease and pass values at scale. Each lab figure comes from one
  run (the earlier development runs agree, but run-to-run variance was not computed).
- Stale-slice takeover is still undecided. Its gap was measured above only for a member that comes back.

## Pool member hygiene, 2026-11-10

*Appended after the maintainer adopted the three follow-ups above
([pool-member-hygiene](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#pool-member-hygiene)).*

Lane head: `codex/evaluator-partition-20261110` at **`d6560468`**, one commit on `cb1b751d`. It touches 4 files:
`lib/server/internal-api/transport.js`, `lib/server/serve/vcpool-preview.js`,
`tests/internal-api-stale-socket.test.js` (new) and `tests/tiers.json`. Local and unpushed. Alignment `main` was
`768dea8b5` when the measurements ran. One dedicated `postgres:16` container (`ns-ep-pg-*`) was used and then removed.
The labs ran on the uncommitted tree that became `d6560468`; nothing changed between the run and the commit.

| follow-up | change | evidence |
|---|---|---|
| 1. stale socket reclaim | Before binding, `reclaimStale` (`transport.js`) does an `lstat` on the path. It refuses anything that is not a socket and never follows or removes it. It then connects: `ECONNREFUSED` or `ENOENT` → re-check the same inode, unlink, bind. A connection that answers, a 1000 ms timeout or any other error → `SOCKET_IPC_PATH_EXISTS`. | `tests/internal-api-stale-socket.test.js`, 3 passing. (a) A child serving the lifecycle contract is killed with SIGKILL; its socket file remains; a new child on the same path serves. (b) A live second listener is refused and left on the same inode. (c) A regular file and a symlink are refused and left untouched. Evaluator lab: `CHECK member killed with SIGKILL restarts in place over its stale socket and serves`, `{"socketLeftByKilledMember":true,"bootError":null}`. The lab no longer removes the file. The existing realtime-preview fixture refusal of file, symlink and live socket keeps its expectations. |
| 2. vcpool boots and waits | `vcpool-preview.js`: a refusal at boot logs `waiting: <reason>` instead of exiting 78; each cycle works no tenant until membership agrees. | Connector lab, new gate: `a partitioned vcpool started before its count is set boots, alerts POOL_COUNT_UNSET and works no tenant`, `{"sourceRequestsWhileWaiting":0,"exit":null,"member":{"eligible":false,"reason":"POOL_COUNT_UNSET","cycles":3},"alert":true}`. It then pulls once the count is set. The duplicate-ordinal gate now reads: the second process keeps running, both members refuse `POOL_DUPLICATE_ORDINAL` and alert. After the second process stops, the first is eligible again with one row; alerts `refused:POOL_COUNT_UNSET, recovered:POOL_COUNT_UNSET, refused:POOL_DUPLICATE_ORDINAL, recovered:POOL_DUPLICATE_ORDINAL`. |
| 3. admin pools without ownership | Already in `cb1b751d`. | `tests/admin-role.test.js` covers pools only, ownership only (the existing composition test) and ownership plus pools, and refuses the empty composition. Part of the unit tier below. |

Break-it controls for follow-up 1, each run and then restored. The file's sha256 matched its pre-control copy.

| control | symptom |
|---|---|
| always unlink (no liveness check) | **red**: `Missing expected rejection: LIVE_SOCKET_REFUSED` (the live-process test) |
| no reclaim (the previous rule) | **red**: `STALE_SOCKET_RECLAIMED SOCKET_IPC_PATH_EXISTS` (the kill -9 test) |

Checks at the committed tree:

| check | result |
|---|---|
| `npm run test:unit` | 3222 passing, exit 0 |
| `npm run test:tiers` | `631 test files, 8 tiers: ok` |
| `npm run test:write-boundary` | all 9 adapter entry points checked |
| integration on PostgreSQL 16: the seven suites of the resumed section, plus `tenant-projection-evaluator` | 52 passing, exit 0 |
| eslint on the 3 changed JS files | 0 errors; 26 warnings, all `security/detect-non-literal-fs-filename`. `transport.js` has 17, against 15 at `cb1b751d`; the new ones are the reclaim's `lstat` and `unlink`. |
| evaluator lab (`tools/tenancy/evaluator-partition/run.cjs`) | `SUMMARY 23 checks, 0 failing` (22 earlier plus the restart-in-place check). The kill-and-restart measure this run: eligible 2048 ms after the kill, unowned 1400–1900 ms, worst delivery gap 5819 ms, duplicates 0. |
| connector lab (`tools/tenancy/connector-reverse/run.cjs`) | `SUMMARY 25 checks, 0 failing` (24 plus the boot-before-count gate) |

Not run: `multitenant-preview-process.integration` (it creates its own containers), the full suite, the browser and
dom tiers, and `prcheck`.
