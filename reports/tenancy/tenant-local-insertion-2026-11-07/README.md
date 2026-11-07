# Tenant-local insertion state: bounded native proof

*Reproduced synthetic PostgreSQL 16.15 evidence, 2026-11-07. App source
`07f8c27d1c2c2cab1b65cd17fa4995d0bdf7f816`, tree
`a66c114ae0add5f47170de9d2cc5c682bb971cc5`, based on accepted f0 source.
[Observations](observations.json), [instrument](instrument.cjs),
[closure](closure.json), [prior failed attempt](prior-attempt.json).
This is a standalone SQL primitive proof, not deployment/M6 admission.*

## Contract and source

[Adopted direction](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-local-insertion-semantics):
only per-tenant/collection relative order is required. No examined public/client
consumer requires global insertion numbers. Public record IDs, stored documents,
history timestamps and supported first-match behavior remain separate contracts.

`lib/tenant-lifecycle/tenant-insertion-sql.js` builds explicit transaction-scoped
operator conversion SQL for entries, food and selected socket-order treatments,
devicestatus and profile catalogues. Existing rows retain their original ordinal;
a forced-RLS per-tenant counter seeds from each tenant's maximum. DROP IDENTITY
removes the native shared sequence. An invoker trigger allocates only the bound
tenant's insertion state, preserves explicit operator restoration values, and
rejects ordinal/tenant changes on UPDATE. No SECURITY DEFINER, new service,
per-tenant sequence or optional write-clock dependency is added.

The unchanged canonical lower writer and real profile reader consume this source.
Normal serving uses column INSERT excluding the ordinal; a separate restricted
restore connection may insert original ordinals. An explicit effective ACL check
refuses inherited grants that would restore serving ordinal-write authority.

## Observed capability

| Native family | Actual result |
|---|---|
| Populated conversion, all five catalogues | Exact old clinical rows/order preserved; identity attribute removed; no sequences remain in each selected namespace; counter FORCE RLS true and function SECURITY DEFINER false. |
| Ordinary writes, all five | Bound canonical writes advance their own counter. Injected rollback restores both data and counter exactly. Ordinary explicit ordinal INSERT refuses SQLSTATE42501; foreign binding and ordinal-changing UPDATE refuse. |
| Exact A restoration, all five | Separate restricted restore connection inserts original counter first, then original rows in one A transaction. Failed A restoration rolls back both. Independent B commits during both interrupted and successful A transactions. Every old B row stays exact, with only its two measured appended writes and counter increments. Next A insert sorts last. |
| Concurrency, entries | Exact pg_blocking_pids relationship proves a competing A insert waits behind held A; B commits while that same A blocker remains. A inserts then commit in their required relative order. This is not a throughput/freshness budget. |
| Existing profile consumer | Actual profile socket-order findOne returns the identical first matching full profile after conversion and after restoration. Raw pre/post-conversion rows/order are checked separately. Android binary/upload-ACK journey remains unexecuted. |
| Effective ACL refusal | An inherited grant allowing ordinary explicit ordinal INSERT makes the real effective ACL verifier refuse; revocation restores acceptance. |
| Own-counter fault diagnostic | Within A's transaction, deliberate direct-SQL floor corruption inserts a new A row in a known old gap, and the expected-new-last assertion fails as intended. Transaction rollback restores every tenant row/counter; B is exact. Fresh ordinary insertion passes. |

The own-counter diagnostic is a failure-radius measurement, not a claim to resist
a compromised trusted worker or DBA. A worker with arbitrary allowed SQL can
misuse its own floor, and trusted identities authorized across tenants remain a
separate threat boundary. Ordinary clients cannot set this physical column through
JSON payloads. Tenant-local state removes shared ordinal maintenance; it does not
isolate shared CPU, storage, pools or all privileged actors.

## Failure, restoration and attribution

First attempt stopped after all five conversions and entries ordinary checks:
B's call was incorrectly nested inside A's process-wide tenant scope. The existing
guard refused `cannot rebind the tenant inside an existing tenant scope`; no
restore success was claimed. Source stayed unchanged. Fixture correction dispatches
B through an independent root AsyncResource, representing a separate request,
without disabling/reinterpreting the guard. The corrected complete run and its
fresh ordinary restoration pass; the original failed capture is retained.

Final instrument SHA256:
`daac671252794ac42d73ecc62b8a47fa735fab09371a4f5b022651cbcaebbc92`.
Final observation SHA256:
`be758572ce200ff1613a21b8fb27f8521887634f9a3256cb9df9f4a6daa5483c`.
The finite parent pins the source, freezes instrument/plan, checks matching locked
dependencies and uses one uniquely owned PostgreSQL container/volume. Its child
exits0; exact resources are absent and complete before/after container/volume
inventories match. Root independently verifies frozen source hashes, clean source
branch and current exact owned-resource absence. Private raw parent/ownership
captures remain in `externals/work/m6-tenant-local-counter-native-20261107/`.
No credentials, database URLs or global machine inventory are exported here.

## Integration boundary

The conversion is standalone explicit SQL. Current MIG-RUNNER catalogue grammar
rejects LOCK/SET/DO; no catalogue/default/readiness entry was changed. This is an
explicit remaining adapter/precondition boundary, not hidden SQL in a migration
function. The one-time operator schema conversion takes its normal DDL lock;
no shared write pause or allocator reset occurred during the measured restores.

New counter tables, exact trigger/function/ACL admission, current catalogue checks,
lifecycle export/import/deletion order, full backup/upgrade/rollback and old-binary
refusal must join coherently. DROP IDENTITY changes column metadata: old identity
refusal alone cannot authorize the new-schema restore path. Target-A exclusion,
actor/credential authority, history/checkpoint/cache recovery and verification
before serving resume remain required. This proof changes no public default,
release state, M5 acceptance or M6 claim. Full/browser/enabled-corpus/prcheck and
capacity campaigns were not run on this standalone leaf.
