# Repaired pgstream candidate: first 1,000-tenant run

*Captured 2026-11-14 UTC. Contributor-facing measurement record. Reproduced unless
marked read-derived. This capture is retained unchanged; subsequent repairs and
runs require their own source attribution.*

The repaired candidate starts and passes fresh readiness and idle checks, but its
load run fails `M7_EVALUATOR_PROGRESS_RESET`. The evaluator process stays alive.
Tenant model generations change and failed-completion counters increase during
load. Later durable catch-up and matching stored counts do not erase that failure.
Final connected-client delivery is **UNMEASURED** because the runner terminates
the probe after the hard refusal. Capacity acceptance is **NOT GRANTED**.

## Inputs and boundary

| Input | Exact identity |
|---|---|
| Application | `6df5c576f6105235580d2c2546b065619876cbfc`, local branch `codex/pgstream-rest-join-20261114` |
| Deployment | `883c516bc2b60a66ef5ae8e211cff4955449fea6` |
| Canonical application image | `sha256:3a620507c852f87a196167ed1eb27766429d351113a7106d44953d85522476cf` |
| Image tag | `ns-pgstream-rest-app:6df5c576f610` |
| PostgreSQL/wal2json image | `sha256:21e7e1665c3dd2fdd80ebd9ce6d36fb160d6a4129683b315b6492a71d87bfda7` |
| M7 instrument source | `9ad52a3364d9175d5b4ba372766b204753dab14c` |
| Instrument content | `a135a49f5a40d6cfe0d90cbce2adeb2209301aa40bd2d6b569ce3605c560cdab` |
| Original bootstrap application | `311ac50023d95815540cc7e718ebffb6eb933b8f` |
| Source baseline incorporated | `official/dev` `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| Alignment records before capture | `238eca6773f846877be3e412eca1c8014c98be50` |

The one coherent candidate joins the stale transport-recovery clock repair,
bounded private child diagnostics, evaluator/realtime verification and refresh
coordination, reduced checkpoint/output transfers and redundant watched work,
narrow REST read transactions, narrow Single observation receipts, same-backend
held-owner readoption, and actual realtime demand wakeup. These changes are fixed
on local branches, not merged to application `dev` or released.

One canonical build used the exact application and deployment archives. Builder
inspection matched 872 files. Independent integration-owner inspection matched
the labels, source binding, Node 24.22.1 and all 19 changed production files.
Previous image tags remain unchanged. The owned fixture retained its database,
Vault, data, networks, ports and original bootstrap records. All six old
application containers and thirteen recorded process incarnations were excluded
before the six normal application services started on the repaired image. All
eleven application declarations select that image; dormant tools were not started.
Independent startup inspection found healthy application services, zero restarts
and unchanged original owner, frozen Compose and environment hashes.

## Measurements

The unchanged discovery envelope uses 1,000 tenants, one API replica, diagnostics
off, warmup 10 seconds, idle 30 seconds, load 310 seconds, acceleration 1, hot
factor 1, two stock sockets per tenant, a 300,000 ms probe cadence and a two-second
sampler. No retry, timeout extension or tuning followed the failure.

| Measurement | Result and practical limit |
|---|---|
| New attachment preflight | **CHECKED**, instrument setup only. Original startup failure remains retained. |
| Fresh readiness and idle | **PASS**. These do not establish load correctness. |
| Client priming | 2,000 of 2,000 sockets primed; zero dark or disconnected during priming. Final frame delivery **UNMEASURED**. |
| Load progress | **FAIL**, `M7_EVALUATOR_PROGRESS_RESET`. All three rounds cover 1,000 rows with the same evaluator runtime identifier. No completed counter decreases. |
| Model and completion transitions | Final round changes 38 tenant model generations. Of these, 32 increase failed completions by one, five by two, and one has no failed-completion increase. Model generation is distinct from process incarnation and operation-window ownership. |
| Process continuity | All nine retained role restart counts are zero; evaluator is healthy and not OOM-killed. |
| HTTP driver | Exit 0; 12,371 requests, 3,102 accepted writes, zero uncertain writes and HTTP failure rate zero. Global HTTP duration p95 86.0670025 ms and p99 113.5765364 ms. These are partial-run measurements, not functional or capacity acceptance. An absent metric is not reported as zero. |
| Original runner oracle | Aborted after the hard refusal. Probe terminated by the runner; no final completed-output/client or storage-oracle pass. |
| Later read-only storage audit | At `2026-11-14T07:06:32.539147+00:00`, 3,102 ordinary accepted writes match stored counts with zero per-tenant mismatches. All 1,000 observed/completed/stored-clock/input-checkpoint values match; zero pending rows. This is a separate later observation. |
| SQL bookends | Exact post-reset before-to-after full statement keys: 21 to 212, zero missing keys and zero decreasing counters. SQL execution time is not database CPU. |
| Resource bookends | 347.8091080188751 seconds. Average evaluator CPU 0.203742465 cores, realtime 0.180802413, API 0.466899610 and PostgreSQL 1.344367621. Shared-host conditions and the failed functional run limit comparisons. No memory saving is claimed. |

The captured due dates are after load end, so a proposed simultaneous due-timer
wave is refuted for this capture. Routine operational verification overlaps this
load according to the source cadence; whether it caused these transitions is
**read-derived**, not uniquely reproduced by the retained trace. The runtime
does not retain the underlying refusal code on these catch paths. Focused
diagnosis must distinguish legitimate model replacement from failed work or lost
state before changing either product behavior or the observer's assertions.

## Focused source checks and remaining work

The preceding joined source `3e990ab2e6b647c11d039ff79f58c2ab4be767d1` passed 132
affected unit checks and 29 native checkpoint/bootstrap/Single receipt/completed
delivery checks. The final commit replaces a lazy `??=` assignment with an
equivalent `if` guard accepted by the configured lint parser. On that final delta,
30 realtime checks pass and all 19 changed production files lint with zero errors.
These overlapping test counts are not additive. Native checks were not rerun on
the final syntax-only delta. The native fixture's nine containers were stopped
with PID zero and evidence retained.

Full/browser/enabled-corpus acceptance and final prcheck on this candidate remain
**UNMEASURED**. The existing pgstream capability owner diagnoses the generation
and failed-completion transition; the integration owner owns the next coherent
freeze, and capacity support owns the single runner. The complete actual-role
recovery, authority/restore and effect-fencing criteria remain open in the
[communication plan](../../../docs/30-design/tenancy/evaluator-realtime-communication.md#actual-role-integration-objective-and-completion-criteria).
The [closed REST comparison](../rest-api-performance-2026-11-13/final-joined-local-ab.md)
uses the earlier `311ac500` source and is not a measurement of this repair.

## Retained evidence

Raw outputs remain outside Git under
`/mnt/data/nightscout-workspace/artifacts/`:

| Retained identifier | Contents |
|---|---|
| `pgstream-repaired-build-6df5-20261113` | Canonical build, source manifest, builder and independent image qualification. |
| `joined-repair-seal-20261114` | Focused source checks, original parser failure and repaired lint result. |
| `pgstream-restart-due-20261113/joined-native-03` | Native result and stopped-fixture receipt, attributed to `3e990ab2`. |
| `pgstream-n1000-repair-upgrade-20261113/runtime-6df5-01` | Upgrade provenance, old-process exclusion, startup qualification and separate runtime attachment. |
| `runtime-6df5-01/attachment-01` within the preceding identifier | Unchanged failed attempt, raw progress rounds, HTTP, SQL, cgroups and host I/O. |
| `runtime-6df5-01/root-failed-run-audit.json` | Independent partial audit; SHA-256 `fb0aceeea5435b5b5f9ce2e1449bcdef5b22978c692b665558864c344dc17581`. |
| `runtime-6df5-01/diagnostics/post-run-0ee589242fff4ea995c283f7b5b1ef46` | Separate later read-only SQL and role/log capture. SQL input SHA-256 `bc2bbd078b3a57976614b9619f50440135548104d281c46f5a8b7d6cfd42bb12`. |

Local worktree, resource and lane custody remains in the single evolving
`externals/work/HANDOFF-pgstream-flow-2026-11-13.md`. No new paid resources,
application-dev merge, push or release occurred.
