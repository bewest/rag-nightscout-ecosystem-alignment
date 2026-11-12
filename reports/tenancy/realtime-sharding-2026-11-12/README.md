# Controlled realtime sharding: focused core evidence, 2026-11-12

The fixed-roster core capability is **fixed on a local branch**. Deployment binding
and coherent joined full/browser/enabled-corpus acceptance remain separate gates;
this report does not close MT-REALTIME-SHARDING or claim measured horizontal capacity.

## Source and instrument

| Anchor | Exact source |
|---|---|
| Complete core leaf | `079a3b4c9a6ece9610b32025a0826f756fbb23f0` |
| Joined coordinator boundary | `a50130e67e8a8e066ce866535aeb8b627a068904` |
| Earlier independent helper/registry admission repair | `9bcf1e50c3e07cade8e36d62da6801209999bdcf` |
| Core local branch | `codex/realtime-sharding-20261112` |

The final source includes the preceding helper history and coordinator history.
All new product tests and native fixtures are committed in the complete leaf.
The [native runner](instruments/native-run.cjs) starts only an owned disposable
PostgreSQL image pinned by digest, with generated credentials passed through the
environment; fixture-owned Vault instances are also disposable. The runner waits
for actual external PostgreSQL TCP query readiness. No shared database or deployed
operator tenant is used. Existing dependency installation was reused; no install,
push, full campaign, browser campaign or capacity campaign was run in this lane.

From an owned core checkout at the leaf, with its dependencies available:

```bash
node /absolute/path/to/instruments/native-run.cjs \
  tests/realtime-placement-owner.integration.test.js \
  tests/realtime-placement-publication.integration.test.js \
  tests/realtime-sharding-native.integration.test.js
python3 /absolute/path/to/instruments/controls.py
```

The [control instrument](instruments/controls.py) mutates only an owned core copy,
checks the intended failing symptom, and restores the exact original file bytes
in `finally`. Do not point it at a peer worktree. Captures replace local checkout
paths with `<core>`; synthetic values and assertion results remain intact.

## Measured result

| Check | Result and scope |
|---|---|
| [Exact committed native](captures/sharding-exact-head-native.txt) | **7 pass, 32s**: real held owner resource; publication/pin; actual unsharded registry API status; observed API/two-RT census; all-paused startup; assigned live-add with failed preparation and recovery; two-view client/alarm move. |
| [Affected checks after all controls restored](captures/sharding-exact-restored-focused.txt) | **147 pass, 881ms** across placement, cohort, schemas, evaluator consumer/config, startup, RT runtime/config/preview, live-add, bootstrap and pool config. |
| [Registration](captures/sharding-corpus-list.txt) | Three native suites are in the enabled corpus. Tier inventory: **696 test files, eight tiers**, all registered. |
| [Lint](captures/sharding-final-lint.txt) | **Zero errors, 38 warnings**, bounded filesystem/RegExp argument warnings. Diff whitespace check passed. |
| [Earlier exact helper archive](captures/sharding-helper-exact-focused.txt), [actual registry API status](captures/sharding-helper-exact-registry-native.txt) | **32 focused pass; one native pass** at the independent helper source, before full sharding. |

The native move uses actual stock Socket.IO polling and WebSocket clients, actual
API3 `/storage` and `/alarm` subscriptions, and real API3 HTTP collection reload.
A synthetic clinical row deleted while A is unavailable is absent from its new full
frame and explicit HTTP reload. B retains its actual socket session and continues
clinical updates and alarm delivery through held A preparation. Accepted old alarm
handoffs are not replayed on reconnect. The durable consumer and projection digest
remain identical; checkpoint position is monotonic. One actual owner backend per
RT process, including an idle owner, is observed; the original work-pool bound is
unchanged. Owner exclusion is an actual held database resource, not a UUID claim.

The stop callback executes inside the exclusive publication fence. The native
fixture observes actual child exit and independently checks kernel `ESRCH` before
new assignment. The fence remains held through target readiness and route rename;
a concurrent actual maintenance pin refuses. Backend and admitted route views are
separate. An older nonfuture route generation is accepted only for its unchanged
current worker/incarnation/logical-shard tuple. Future or displaced tuples refuse.
No automatic partition takeover, fallback worker, per-write index or durable
missed-viewer-alarm replay is introduced.

The actual census includes real API and two realtime role producers and both held
owner backend PIDs. Missing worker, wrong coverage and an unknown live clinical
backend refuse; closing the unknown backend restores success. Evaluator and admin
peers in this fixture are explicitly idle synthetic peers with no claimed clinical
work/backends. This is not a real four-role restore or full lifecycle campaign.
The fixture edge proxy is a test instrument; shipping edge and platform adapter
acceptance belong to the coordinator's deployment lane.

## Controls and reproduced findings

All five [final-source controls](captures/sharding-exact-controls.txt) exited red
with their intended assertion, and restored byte-for-byte:

| Mutation | Observed failure and interpretation |
|---|---|
| Require globally equal route generation | B alarm during unrelated A warm fails `SHARD_NATIVE_HANDOFF synthetic B during unrelated target warm: REALTIME_HANDOFF_UNAVAILABLE`. This is an actual availability defect, rather than a vacuous refusal test. |
| Omit worker-coverage guard | Missing declared RT participant produces `Missing expected rejection`. Completeness check is exercised. |
| Ignore failed publication pin | Pinned maintenance no longer rejects publication: `Missing expected rejection`. Actual database locking discrimination is exercised. |
| Remove sharded envelope reservation | Boundary configuration no longer rejects: `Missing expected exception`. Transport overhead bound is exercised. |
| Remove legitimate registry-label response acceptance | Actual unsharded API lifecycle status fails `SOCKET_IPC_UNAVAILABLE`; the former UUID-only contract prevented real registry health. |

The [earlier warm-isolation failure](captures/sharding-warm-isolation-before.txt)
is **reproduced exploratory dirty-source evidence**, not a pristine committed
baseline: a new target projection was inserted in the active scheduler before
acquisition completed, and holding that acquisition stalled B with
`SHARD_NATIVE_B_PROGRESS_DURING_WARM`. The [repair capture](captures/sharding-warm-isolation-after.txt)
was green. The exact final native includes the same held-acquisition discriminator,
plus failed-preparation refusal/recovery and concurrent pause before activation.
Private staging keeps a cold/failed target outside the healthy scheduler; fresh
activity, settings, registry membership and ownership are checked before activation.

The narrow registry-ledger readiness repair was motivated by actual CLI refusal.
The [ledger-only discriminator](captures/sharding-readiness-ledger-discriminator.txt)
removed only registry `schema_migrations` SELECT from an otherwise identical real
role and reached the listener, then restored the grant. Product admission now
allows exactly that reviewed ledger; unrelated registry-table SELECT still refuses
in the final native. The first exploratory setup had an unrelated clinical-table
grant outside the projection manifest; it was corrected in the fixture before the
ledger-only comparison. No RLS, function owner, PUBLIC EXECUTE or unknown-backend
census guard was relaxed.

All-paused/suspended tenants stay deferred without clinical projection/checkpoint
work. Real resumed tenants return to eligibility. A failed or slow target refuses
handshakes and alarm effects; existing healthy tenants continue. The global
publication/restore fence does not serialize every activity or deletion writer;
fresh target checks are still required, and already in-flight work retains its
bounded uncertainty.

## Integration boundary

The coordinator owns ordinary merging of the core history, the matching shipping
edge/platform binding, and one frozen comprehensive acceptance. Automatic failover,
durable missed-alarm replay and horizontal capacity remain unmeasured/deferred.
Local lane details remain in `externals/work/HANDOFF-realtime-sharding-2026-11-12.md`;
they are not a public source of product state.
