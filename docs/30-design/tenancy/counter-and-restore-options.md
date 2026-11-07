# Counters, compatibility and tenant restore options

*Living contributor-facing design analysis, 2026-11-07. Read-derived from the
published f0fac99a application unless a linked experiment says reproduced.
[Release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#allocator-preserving-restore-first)
own the adopted experiment direction and conditional preview pause allowance.
This analysis adopts no schema, new cursor format or runtime admission.*

## Two independent mechanisms

The transactional tenant history clock has one `tenant_write_clock` row per
tenant. It coordinates admitted writes through commit so a reader cannot advance
past a still-uncommitted earlier history watermark. Existing numeric timestamp
cursors remain compatible. Cross-tenant total ordering is not required.

`insertion_ordinal` is a separate PostgreSQL table identity used to emulate
existing natural-order reads. A shared table's sequence supplies values for all
its tenants, although readers remain tenant-bound. It is not the history clock,
public record `_id`, or a clinical timestamp. Source anchors on f0fac99a:
`migrations/candidates/postgres-write-clock-v1.json:8`,
`migrations/candidates/postgres-entries-v1.json:38`,
`lib/storage/postgres-entries-read.js:105`.

The engineering concern is giving implicit storage ordering application meaning.
[MongoDB defines natural order](https://www.mongodb.com/docs/manual/reference/glossary/#std-term-natural-order)
as physical RecordId order, with replica/sharding qualifications. Existing client
compatibility must be measured before changing this inherited behavior; matching
historical behavior must not silently invent a stronger universal guarantee.

## Comparison with other systems

[Kubernetes resource versions](https://kubernetes.io/docs/reference/using-api/api-concepts/#resource-versions)
support change tracking, consistent list/watch and optimistic update concurrency.
[etcd revisions](https://etcd.io/docs/v3.6/learning/api_guarantees/)
order modifying operations/transactions. This is a useful analogy for the tenant
history clock, not a reason to require cross-tenant ordering or add etcd here.
Unique sequence allocation alone cannot establish commit-order visibility.

Restore has similar problems in etcd: an old snapshot can move revisions backward
relative to clients' caches. Its documented [revision bump/compaction procedure](https://etcd.io/docs/v3.6/op-guide/recovery/#restoring-with-revision-bump)
forces stale watches to rebuild. Our restore must likewise address stored
checkpoints, history floors and derived caches; inserting rows is only one step.

[MongoDB change-stream resume tokens](https://www.mongodb.com/docs/manual/changestreams/)
and [PostgreSQL WAL/logical decoding](https://www.postgresql.org/docs/16/logicaldecoding-explanation.html)
provide other durable positions, with retention/replay/failover obligations.
These move ordering into a database/feed protocol; they do not eliminate the
need for an ordering/recovery contract or automatically preserve legacy cursors.

## Options before a shared pause

| Option | Benefit | Cost / explicit limitation |
|---|---|---|
| Preserve the live allocator | Smallest first experiment: restore original A ordinals without resetting shared state; B may continue. | Must prove future allocations cover the artifact, source/sequence identity and supported cache state; A still needs exclusive restore authority. Higher-floor artifacts refuse. |
| Recreate internal ordinals in original relative order | Potentially avoids sequence-floor maintenance using normal allocation; public IDs remain stable. | Proposal only. Requires a consumer census proving exact ordinal values have no external/checkpoint meaning, faithful relative ordering across all relevant domains, and review of artifact-fidelity changes. |
| Tenant-local insertion allocation | Removes cross-tenant insertion-counter maintenance; can reuse the existing tenant transaction fence while keeping ordinal and history meanings distinct. | Schema/migration/write-path work; same-tenant contention and all-writer coverage need proof. |
| New tenant data generation plus atomic routing switch | Stage/verify A separately and retain old generation for rollback; B remains current. | Requires routing-generation support, cache/session fencing and stale-writer refusal. Current global namespace mapping does not provide this automatically. |
| Explicit domain sorting plus stable tie-breaker | Can remove insertion-order state where no consumer actually requires it. | Client-visible ordering, ties, retries and replacement behavior require measured compatibility and an explicit change contract. |
| Narrow A suspension with ordinary transaction rollback | Limits interruption to the tenant being restored. | Must exclude every admitted A writer and stale serving/cache state; a clock-row lock alone misses lower-port callers. |

The read-derived f0fac99a consumer census finds the physical value used for
`ORDER BY insertion_ordinal ASC` while queries return only `id_kind, doc`
(`lib/storage/postgres-entries-read.js:102-113`). The common natural-order path
also serves selected entries/food and socket treatments/devicestatus/profile.
No ordinal foreign-key or checkpoint consumer was found in `lib/`/`migrations/`.
Generic lifecycle artifacts do retain and hash the original physical ordinal.
Consequently, regenerating it is a proposed **logical tenant restore** contract,
not a repair to the existing exact physical backup oracle. Whole-deployment
physical restore keeps its separate fidelity contract.

A logical prototype must sort captured rows explicitly by BigInt ordinal;
export array order is not an ordering contract. It preserves public IDs, typed
values and original history timestamps by direct validated restoration, rather
than ordinary clinical create handlers that may stamp/deduplicate/publish again.
Admit exact positive noncycling CACHE 1 behavior first; larger allocator caches
and stale writer sessions require independent ordering proof.

These alternatives reduce shared interruption, not the need to coordinate writes
to the very state being replaced. A transparent online restore would additionally
need a declared merge/replay/conflict policy for writes arriving during restore.

## Conditional pause and safe recovery

A preview shared write pause is allowed only if needed and explicitly bounded.
Define admission/exclusion, drain, transaction boundaries, interruption recovery,
verification and reopening. A watchdog deadline cannot make partial recovery safe
or promise a deterministic completion time. Failure must retain a known safe
state; reopening requires positive verification. Restoring A must not roll B's
committed state back. A service restart and a rollback of durable data are
different operations.

Keep the tenant-local history clock while measuring allocator-preserving restore.
Investigate concrete natural-order consumers before adding another counter or
requiring a shared pause. Future versioned cursors and restore generations are
incremental architecture options, not prerequisites silently added to the preview.
