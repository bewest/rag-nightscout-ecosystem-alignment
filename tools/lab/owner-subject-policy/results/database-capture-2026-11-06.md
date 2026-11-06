# Owner subject-policy database capture — 2026-11-06

This is bounded database evidence, not full application acceptance. Application
capture: `3106f14d5b718e27e2a179e2d637f0d06c0642c8`; immutable archive instrument
alignment: `da25af1e0d972d60b294cf5c114da3ca75fdcdd4`.

[Normalized capture](3106f14d-db-capture.json) preserves actual Mocha totals, case
names, failure assertion details, versions, cleanup counts and raw-log SHA256s.
The full original output remains in private lane scratch. Synthetic data only;
normalization omits private runtime container/volume IDs and stack paths.

Reproduced on PostgreSQL 16.15 and Node v22.23.4:

| Exact-source run | Passing | Pending | Failing |
|---|---:|---:|---:|
| First database archive | 22 | 0 | 0 |
| Second database archive | 22 | 0 | 0 |
| Remove code catalogue guard only | 0 | 0 | 1 semantic control |
| Remove current operator ceiling guard only | 0 | 0 | 1 semantic control |
| Remove explicit actor delegation guard only | 0 | 0 | 1 semantic control |
| Remove current active/update actor guard only | 0 | 0 | 1 semantic control |
| Fresh restored database archive | 22 | 0 | 0 |

Each control allowed HTTP 200 instead of expected 403 and the test independently
observed changed persisted state. None was a setup, hook or timeout failure.
The suite executes both real PostgreSQL authority-lock orderings on configuration,
policy, actor and role rows; tenant isolation; selected permission intersections;
current-state outage/recovery; exact SQL privileges/RLS; caller proposal copying;
final-audit rollback; and default-mode compatibility. No complete owner identity,
issuer, listener, arbitrary wildcard/default catalogue, grant clamping or stream
revocation is established. In-flight operations holding authority locks may finish
before a waiting revoker commits. No total-transaction deadline or arbitrary
operator lock-order deadlock freedom is claimed.

For each of the seven database archives, the private audit recorded one actual
new container and one anonymous volume before removal, then independently verified
both absent. The real Docker helper smoke also passed: one owned nonrunning
PostgreSQL-image container and one recorded anonymous volume removed, private file
permissions verified. No database process was started for that smoke. No direct
volume deletion, global prune or unrelated resource cleanup was used. No named
volume was authored by these runs; the wrapper only augments exact owned container
removal using Docker's anonymous-volume removal flag.

The private post-run verifier first rejected the engine's lowercase container
not-found message. That diagnostic and the original outputs were retained. Only
case normalization of the exact missing-object message was corrected, after which
the same recorded IDs and volumes were confirmed absent. This was not a product
failure or evidence from a passing setup fallback.

The subsequent existing subject-management corpus on the same application source
ran 25 passing and 1 failing: its migration-upgrade test expected only migration
0003 pending, whereas the new candidate also appends 0004. Both test containers and
their two volumes were verified absent. Broad acceptance stopped before full or
browser tests. Fixture-only correction `17f9a4577e649208ada6b0aa8f83c51026459875`
explicitly checks the 0003/0004 sequence and preserves all three stored prior
checksums, historical metadata and readiness assertions. Runtime on that correction
is pending a new explicit coordinator slot. The captured 3106 controls stay pinned
to 3106; no result is relabelled onto an untested head.
