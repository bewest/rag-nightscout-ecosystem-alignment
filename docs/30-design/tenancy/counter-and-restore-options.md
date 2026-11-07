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


## Fault isolation and the selected next step

The maintainer [selected per-tenant insertion semantics and a tenant-local state prototype](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-local-insertion-semantics). Cross-tenant ordering is not required; same-deployment restore must preserve other tenants' current state. The global
counter concern is shared mutable state under faulty or malicious behavior, not
an observed requirement for cross-tenant ordinal values.

Ordinary atomic sequence allocation and privileged sequence maintenance have
different authority. PostgreSQL `nextval` requires USAGE or UPDATE; `setval`
requires UPDATE. Aborted transactions can leave gaps, which do not by themselves
break relative order. The [sequence contract](https://www.postgresql.org/docs/16/functions-sequence.html)
does not turn the allocator into a global application transaction lock held
until every writer commits. Avoid all-tenant read/modify/write counter code.

A faulty actor with privileged sequence mutation can affect tenants sharing that
sequence. Per-tenant allocation reduces this state coupling, but does not protect
against a compromised database administrator or a worker authorized across tenants,
or isolate shared CPU/pools. Complete admission must verify actual privileges;
table RLS alone does not bound sequence setters. The f0 serving-readiness survey
has not established a complete sequence-privilege check across all roles. The
new planner's own role check does not fill that broader boundary.

The narrower compatibility finding is in the [native consumer proof](../../../reports/tenancy/insertion-order-consumers-2026-11-07/README.md):
renumbering while preserving order retains the selected full profile; reversing
order selects a different duplicate-match profile. Explicit date-sorted entries
are unchanged. Source tracing reaches the released AndroidAPS NSClient v1 profile
upload/ack path, but no Android binary was executed. No observed client requires
cross-tenant ordinal numbers or exact private ordinal values.


## Minimal tenant-local state prototype

Use a counter row per tenant in each existing ordered collection namespace,
with forced RLS and an invoker INSERT trigger. Keep history timestamps separate.
Migration preserves existing ordinal values and seeds each tenant floor; ordinary
inserts increment only their tenant's row transactionally. Explicit operator
restoration preserves original ordinal values while advancing only the restored
tenant floor. Updates cannot change ordinal/tenant identity. Serving column
INSERT excludes the private ordinal; operator restore has separate rights.

This trades an extra small relation/trigger and per-tenant transaction lock for
removing cross-tenant allocator state and restore counter-maintenance machinery.
It is an operational simplification, not a claim of fewer SQL statements or of
Byzantine tolerance against a trusted all-tenant worker/DBA. Shared pools/CPU remain.
No new service, per-tenant native sequence or SECURITY DEFINER is needed.

The first prototype is explicit standalone SQL, not a runnable catalogue/default
selection. Current migration validation rejects LOCK, SET and DO statement forms;
runner-compatible transaction/precondition integration remains explicit work.
Do not hide those controls in an unreviewed migration function to make validation
pass. Lifecycle inventories, role grants, read-only trigger/counter readiness,
old/new upgrade/rollback and final client/cursor/cache acceptance also remain.
A normal one-time schema DDL lock is distinct from a recurring shared restore pause.
