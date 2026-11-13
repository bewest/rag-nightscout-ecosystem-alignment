# Cohort constructor admission snapshot — 2026-11-12

The focused source repair is fixed on branch at
`43b6b99d196e48eed2a228cdda9999b535eac7e9`. The source criterion passes its
focused and isolated native controls. Actual joined shipping restore and the
remaining evaluator deployment acceptance are **UNMEASURED on the repair**.
No comprehensive acceptance, capacity, release or production claim is made.

## Attribution and reproduced mechanism

The actual shipping observation used core
`d8d6b547bb17fc91e440bcab48f323a81a6cd66c`, deployment
`962fbdbe8617ed8abe63cad7039fde70f91fcbce`, and fresh paired image
`sha256:5b785befb5a5a89689148cbbc50c2159506a7a831b9a382a7238350a3f3684b9`.
It is a synthetic, independently owned Compose project with one API, one
unsharded realtime role and three fixed evaluator participants.

A failed restore left the synthetic A tenant suspended. Investigation retained
that phase and did not replay restore or reopen the tenant. A focused cache
invalidation against that already suspended tenant produced successful replies
from every participant, followed by realtime status HTTP 503. The
[peer/operation/status capture](capture/actual-peer-status-refusal.log) retains
only bounded operational metadata. It is not an HTTP body or clinical trace.

The initial hypothesis came from `lib/storage/postgres-connection.js`: connection
construction adds its resource record with `datastore: null` before awaiting
role and physical backend identity admission. The synchronous
`cohortDatastore()` refuses any such record. Realtime's short-lived persisted
settings readers can overlap a lifecycle status observation.

The [native discriminator](instrument/cohort-constructor-probe.cjs) reproduces
that mechanism using an actual operation window and PostgreSQL connections:
a baseline snapshot is valid, holding another connected constructor before
identity publication makes the snapshot refuse, and releasing admission restores
the same datastore. The [capture](capture/native-before-held.log) records both
outcomes. This is reproduced native initialization behavior; the peer status
capture independently measures the actual deployment refusal. No private error
body was substituted for a measured handler cause.

The exact source/stock restore failure artifacts and suspended state remain
local. They have not been replaced with a passing result on the later source.

## Repair and controls

The repair starts from joined source
`c833e1de4788b9ebbcd4d8125299dad1051c6ed8` and preserves its cache cleanup history.
It changes `lib/storage/postgres-connection.js` and
`lib/server/serve/operation-cohort.js`:

- Each status captures one connection-record set and waits for every captured
  initializer under a monotonic timer. It returns their actual datastore and
  backend identities together. Later constructors continue independently and
  do not extend that cut. No captured null or failed admission is skipped.
- The independent SQL actor census remains authoritative. If it observes an
  actor born after a status cut, one complete peer re-observation may recognize
  only the original actor's exact PID, role and birth. Persistent unknown actors,
  wrong births, mismatched datastores and failed initialization still refuse.
- Initial and optional subsequent snapshot RPCs share one monotonic budget,
  selected from the shortest configured peer timeout. Elapsed SQL time is
  deducted before another RPC round; the SQL deadline remains unchanged.
- After awaiting snapshots and before success, the coordinator rechecks its
  live cohort and exact held pin. Closing a cohort or releasing its pin cannot
  turn a delayed reply into successful admission.

This is a bounded observation boundary. It does not claim a global database
fence against raw connections born after the SQL actor cut. Existing tenant
suspension, operation-window admission, credential custody and pinned participant
identity checks remain required.

| check | measured outcome |
|---|---|
| [Affected source checks](capture/focused-after.log) | 48 pass: constructor cuts, monotonic timeout, failed role, mismatched database, continuous constructor stream, original actor recognition, persistent unknown/wrong-birth refusal, incarnation/census controls, close/release refusal and storage failure behavior |
| [Native exact committed source](capture/native-after-commit.log) | 3 pass on a newly owned disposable PostgreSQL instance: a held real backend plus continuing constructor stream, bounded timeout, rejected native role and another actual database |
| [Admission wait removed](capture/native-await-removed-control.log) | 1 pass, 2 fail: held backend yields datastore unavailable; timeout no longer reports the required timeout cause |
| [Exact source bytes restored](capture/native-await-restored.log) | 3 native pass |
| [Tier inventory](capture/tier-inventory.log) | 702 files, 8 tiers |

The continuous native stream exercises the physical connection constructor and
admission boundary. It is not a clinical tenant-B workload or capacity result.
The focused peer protocol uses a recording transport; it does not replace the
actual shipping role/restore proof that remains pending. Native fixtures use
synthetic capabilities, no clinical mutations, and their own disposable resource.
The retained shipping failure project was not modified with source overlays.

The source commit registers both new tests in the existing tiers. The native
instrument is `tests/postgres-cohort-snapshot.integration.test.js` at that
commit; the source protocol controls are in
`tests/postgres-cohort-snapshot.test.js`, `tests/operation-cohort.test.js` and
`tests/operation-cohort-peers.test.js`.

A separate agent reviewed the final runtime byte boundary read-only and found
no remaining blocking mismatch in constructor/snapshot/census authority or live
pin ownership. That review did not rerun the owner's native measurements.

## Integration boundary

The coordinator owns the ordinary source join, programme records and eventual
comprehensive acceptance. The evaluator binding lane must next use a fresh owned
project and exact paired image, demonstrate actual stock-client restore with
healthy B/settings traffic, and complete the adopted member transition/effect
oracle. The earlier suspended tenant and immutable failure evidence stay retained.
No new owner configuration authority protocol, failover, census exception or
clinical protocol was introduced by this repair.

Captured files and the two original diagnostic instruments are pinned by
[SHA256SUMS](SHA256SUMS). Lane details remain in local
`externals/work/HANDOFF-evaluator-binding-2026-11-12.md`.
