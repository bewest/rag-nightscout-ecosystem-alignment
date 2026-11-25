# Which tenant boundary buys smaller clinical storage?

**Draft for contributors and maintainers, 2026-11-24.** D3 requires PostgreSQL row-level security (RLS) on the
multitenant serving path. D2 selects shared logical storage. D4 keeps single-site MongoDB permanently.
Changing any of those decisions needs a separate maintainer decision. The choice here is which alternatives
deserve a matched experiment. [Decisions in force](decisions-in-force.md)

**Test plain PostgreSQL first, and give one challenger the same workload.** Start with old device status. The
joined product already keeps recent documents directly readable and compresses old bodies. Much of the
remaining cost is in the individual headers and indexes. Compare a smaller identity-and-window header under
full RLS with a tenant-scoped reader for packed history that can use a different physical format. Run each
physical change first with the strongest RLS access path it supports. If the challenger needs an additional
index, a trusted service or a second copy for restore, charge it for those. Ordinary entries reads give little
reason to remove RLS across the application.

**Give the 60-day and multi-year questions separate verdicts.** At 60 days a device-status-only change cannot
reach 1.5× even if it removes every byte in that collection. Run a second, lossless entries/treatments layout
on the same fixture. For multi-year retention, first compare plain RLS bundles with a private columnstore at
the same cutoff. A policy that archives after 90 days moves zero records on a genuinely 60-day fixture.

| Design | Where bytes could fall | Main operating cost | First test |
|---|---|---|---|
| A · Full PostgreSQL RLS | Slim identity headers, sparse scalar indexes and compressed remainders across collections | Sealing, index maintenance and decoding a historical range | Replay the joined 60-day fixture with each layout change. Time the evaluator window and v1 resend. |
| B · RLS on live rows and the manifest | Native columnar compression of sealed detail and fewer historical indexes | Private cold reader, extension upgrades and restore across representations | Compare identical cold blocks with both access boundaries, then columnstore against plain bundles at multi-year depth. |
| C · Shared service without clinical RLS | Packed blocks could replace per-document cold headers if the writer can arbitrate duplicates cheaply | New trusted service and contention on the tenant writer | Compare the same layout first. Race two cross-hour resends before pricing a header-free variant. |
| D · Tenant-owned SQLite, fully RLS-free | Tenant-local rows and indexes omit the tenant prefix. Local uniqueness works across all dates. | Fenced owner, replication, fleet upgrades and cold starts | Run real Nightscout writes and windows for two tenants, then a same-ID restore with credentials rotated since export. |

## What the measurements establish

All figures below are **reproduced observations from retained synthetic runs**, read from their outputs for
this proposal. The PostgreSQL policy probes ran on 16.15. The joined allocation replay ran on 16.16. These are
separate experiments.

| Observation | Measured result | What it prices |
|---|---|---|
| Entries, forced policy plus explicit tenant predicate versus explicit predicate alone | Rare meter page 0.072 / 0.067 ms, 6 shared-buffer hits each. Recent window 2.032 / 2.060 ms, 146 hits each. Glucose page 65.941 / 65.955 ms, 5,262 hits each. | Median warm SQL execution, nine trials per arm. Ordered digests agreed. All arms bound a transaction. Pool checkout, binding round trips, network and end-to-end latency still need measurement. Evidence `rls-cost-20261124-aUE4Ah/summary.json`. |
| Insert 288 entries with the tenant ordinal trigger, RLS on/off for both entries and counter | Median 21.327 / 20.525 ms across eight measured trials per arm. Both wrote 1,943,616 bytes of statement WAL and finished with entries at 71,401,472 bytes and the counter at 65,536 bytes. | One statement before commit on fresh clones with the same identities and ordinal digest. The observed space saving from the policy toggle here was zero. Evidence `rls-cost-20261124-aUE4Ah/write-summary.json`. |
| Two packed-array identity lookups with identical indexes and explicit scope | With RLS the tenant/hour index examined the tenant's 720 hours, filtering 719. Without RLS the GIN membership plans found the matching hour. Median lookup for ID was 0.2825 / 0.0305 ms and for identifier 0.3295 / 0.0340 ms. | Warm server execution, ten measured trials, 72,000 hours with placeholder payloads. ID and identifier GIN indexes occupied 88,350,720 and 88,383,488 bytes within 254,107,648 allocated bytes. Different plans are real. Net savings and writer correctness have yet to be demonstrated. Evidence `rls-layout-20261124-xjMF7g/summary.json`. |
| Matched 60-day product replay, eight sites, 405,181 documents | PostgreSQL parent 724,450,327 bytes, storage-only 694,598,679, joined 700,390,423. Single-site MongoDB Snappy 181,100,544. The join saved 3.32% from the parent and used 3.87× Snappy. Its entries history index used 8,437,760 bytes. | All allocated database files after ordinary vacuum and checkpoint, 1,545 matched request batches and independent readback. The storage-only arm saved 56.74 MB of device-status data and added 57.83 MB of its indexes versus the parent. Reclaimable free pages counted. Neither replay qualifies live latency. Evidence `storage-performance-bytes-20261124/{REPLAY.md,result.json}` and `storage-parity-integration-20261124/STORAGE-RESULTS.md`. |

**Read-derived feasibility bound.** Grouping the joined physical inventory by owner schema gives 393,527,296
bytes for device status, 166,903,808 for entries and 123,994,112 for treatments. At 1.5× Snappy the entire
database gets 271,650,816 bytes. The gap is 428,739,607 bytes. Even setting device status to zero leaves a
shortfall of 35,212,311 bytes, and preserving its real identity and query paths makes the shortfall larger.
This prices the minimum work outside device status, without assuming a codec ratio. Evidence
`storage-performance-bytes-20261124/postgres-candidate-60d/allocation-cgm.json`.

Two earlier controls help pick the baseline. Keeping the ordinal and using existing generated columns for a
48-hour scalar glucose read cut database-to-Node bytes from 214,286 to 40,885. The evaluator and exports that
need complete documents still pay to fetch them. Packing the *open* device-status hour cut bytes at depth but,
on the parked implementation, increased evaluator p95 from 82.3 to 113.3 ms in round one and a 288-document
write hold from 44.7 to 637.5 ms. An experiment that packs only closed history avoids putting that rewrite on
each upload. [Storage layout and measurements](storage-layout-proposal-2026-11-23.md) ·
[Hour-chunk decision](multitenancy-decisions.md#devicestatus-hour-chunks)

## One scoped storage interface

Reuse the existing storage seam and tenant scope. Resolve the tenant at trusted ingress from the site registry
and the authenticated request's authority for that site, including its public-read policy. For internal work
the trusted dispatcher resolves the assigned tenant and operation. A document, filter, socket payload, report
parameter or archive manifest cannot choose the scope. Convey it once to an operation-scoped store. Its
methods take a collection, keys, filters, time bounds or a batch as needed. They expose neither a tenant
argument nor a database handle. End the scope on completion or rollback. Recheck the existing authority and
lifecycle rules on deferred work. The join's reference points are core `6819f1a41`,
`lib/storage/tenant-scope.js`, `lib/storage/devicestatus-sealing.js` and
`lib/storage/postgres-write-clock.js`.

| Caller | Operations and authority |
|---|---|
| REST v1/v3, uploaders and connectors, socket mutations | API authorizes reads and is the sole ordinary clinical writer. Socket mutations and connector uploads go through its writer. Return the actual result on commit. Dispatch tenant-specific hints after commit. |
| Evaluator, realtime and plugins | Evaluator reads a consistent tenant window with the required history, profiles and full extension fields. Realtime consumes authorized state and frames. Give each its existing read or output operation. An internal read never confers clinical write authority. |
| Reports, comparisons and background work | A report gets one tenant's range and projection. A summary job may replace that tenant's derived days. Cache keys include tenant, calendar/time zone, report definition and relevant settings/version. Fall back to scoped detail for partial days, unsupported statistics or stale summaries. |
| Owner and platform administration | Preserve separate owner, data and operator authorities. Only the operator lifecycle path may export, restore, seal or erase as authorized. Registry, placement and operational catalogues have a separate platform scope and stay outside tenant export. |

Keep the collection's existing typed `_id` and applicable nonempty `identifier` uniqueness, v1 resend matches
and reply winners, including treatment exemptions, missing versus null, unknown nested fields and insertion
order on ties. Each writer applies its collection's actual batch and retry semantics. The stamp for v3 history
must advance in commit order across collections. Preserve the live floor across restore, along with relative
order and tombstones. Clinical time locates the event, receipt time records arrival, and modification time
drives history. Keep the original time spelling and a fallback for unparseable or atypically typed values. A
mixed-tier query filters and merges under the requested public sort and tie rule *before* applying its global
limit. [Identity](multitenancy-decisions.md#d20) ·
[Ordering](multitenancy-decisions.md#tied-sort-key-permutation) ·
[Write clock](multitenancy-decisions.md#multitenant-requires-write-clock)

Single-site callers continue to use the existing MongoDB implementation, including standalone installations,
legacy report clients and existing settings. The interface can share a lossless query or report definition
without imposing tenant credentials, SQL transactions, time-based edit refusals or a migration on a single
site. Use actual single-site HTTP, history and socket responses as the behavioral reference. Record known
baseline differences separately. [Single-site decision](multitenancy-decisions.md#d4)

## Four designs to compare

### A. Plain PostgreSQL with RLS throughout

Start with the **joined product**. API, evaluator and lifecycle roles use their distinct grants, non-owner
connections, forced policies on tenant tables and transaction-local binding. PostgreSQL checks eligible rows
and the tenant of the resulting row on writes. This protects against an omitted application predicate after
trusted binding. The trusted component that selects the binding still has to authenticate the request.
[PostgreSQL row security](https://www.postgresql.org/docs/16/ddl-rowsecurity.html)

The joined device-status layout has one lockable row at every age. Its unique keys, ordinal and generated
lookup columns survive sealing. Only the unindexed remainder moves to an LZ4-compressed tenant/day block. The
invoker view reconstructs the public document. Current edits can return a sealed member to rows. An export
reads a consistent logical snapshot and restore uses the existing fence.

**First improvement to price.** Keep hot rows and compact the cold header to the fields actually needed for
identity, clinical window, history, order and location. Fetch the body only for selected results or predicates
that require it. Give selective reads typed B-tree equality, including tenant, before considering array
membership. Reuse the header itself for uniqueness across direct and sealed rows. Avoid paying for both a full
header and a separate locator. Compare the joined layout with this change under RLS, including any index
needed by older followers or reports. A bounded sealer and ordinary vacuum, tenant clock, derived-day
invalidation and logical restore remain. Candidate removals are duplicate field storage, speculative indexes
and body reconstruction for scalar reads. Lower allocated bytes, write amplification and window latency are
hypotheses.

**Entries and treatments at 60 days.** Trial lossless typed scalar columns with a sparse remainder and sparse
indexes for exceptional original representations. Keep the access paths for v1 resend, ordered glucose windows
and v3 follower history. First price those rows on their own. Then compare grouping the older remainders in
RLS-protected blocks using the same age boundary as the challenger. Preserve indexed hot data and full JSON
for extension-field filters and exports. Under the joined allocation those two main relations alone consume
87,162,880 and 57,401,344 bytes before their indexes. The earlier typed implementation reduced these
collections by 24.7% together on a two-day seed but slowed default resends and deep selective reads. Treat its
regression cases as entry criteria for a new layout. A win on typed storage requires a whole-product replay
with the retained indexes.
[Typed implementation and read paths](storage-layout-proposal-2026-11-23.md#10-typed-entries-and-treatments-on-candidate-2)

For the longer horizon, give A the same authority to group old detail as B. Keep tenant-scoped compressed
month blocks, a small manifest and only the proven range and identity indexes. Reuse scoped queries and the
same summary definitions. The costs include sealing, decode/filter for old predicates and invalidation on
correction. Native time partitioning is a separate variable. A PostgreSQL unique constraint on a partitioned
table must include its partition key. An unpartitioned tenant-and-identity header can arbitrate all time
partitions at the cost of its own heap, indexes and writes. The baseline may keep unpartitioned rows if they
are smaller or faster.
[PostgreSQL partitioning restrictions](https://www.postgresql.org/docs/16/ddl-partitioning.html#DDL-PARTITIONING-DECLARATIVE-LIMITATIONS)

### B. RLS for the live service and identity, scoped access for sealed history

Keep A for mutable clinical rows, unique identity headers, clocks, tenant settings, authority, current windows
and summary rows. Only the sealed payload relation uses a different boundary. The reader, including an
old-range API query or report, selects an authorized manifest/header under RLS. A fixed storage operation
resolves that row to its payload and verifies the same tenant, collection, generation and member on retrieval.
The caller supplies a filter or public identity. Only the implementation can read the private payload
relation. The sealer publishes its payload and tenant-owned reference atomically in PostgreSQL. The lifecycle
reader uses the same lookup for export. Restore rebuilds both under the fence. Require serving and report
roles to lack direct grants on chunks, materializations and their backing objects. For PostgreSQL, replace the
joined invoker view on this one feature with a fixed function whose restricted, non-owner execution role can
read the policy-protected manifest and the private payload. Give serving roles execute access to that
operation. Bind tenant authority through the existing trusted transaction wrapper, keep object names fixed,
and disallow independent raw logins by application callers. A handle or content digest alone is insufficient
authority.

Try the same plain packed table on both sides of the policy boundary first. Then give this arm a reason to
exist. An extension-managed columnstore for old detail could retire the application bundle codec, rewrite
triggers and some range indexes, and push scoped aggregation to SQL. It adds an extension and its upgrade,
chunk-conversion and recovery procedures. The identity header still enforces uniqueness across hot and cold. A
late arrival with old clinical time stays writable. For a correction to an already sealed member, publish a
mutable replacement or tombstone and switch the unique header to it in the same transaction. Readers follow
the current header at one snapshot. Reclaim obsolete payloads only after readers and exports are safe. Charge
the storage and rewrite work to B. A scoped sealer owns transitions. Any summary is published only for the
authorized tenant and correct input revision. Price direct cold-range reads and summary refresh alongside the
header, manifest and extension indexes.

Tiger Data documents that Hypercore columnstore chunks lack RLS and that a continuous aggregate's source
hypertable must have RLS disabled. A concrete trial uses a **private cold-only hypertable**, tenant grouping
and a restricted report path. Keep the live RLS source separate. If approximate aggregates or refresh lag
change public results, read authoritative detail for those requests. Check the exact supported extension
build, backup/restore and upgrade path on the target packaging before measuring it.
[Hypercore limitations](https://www.tigerdata.com/docs/reference/timescaledb/hypercore#limitations) ·
[Continuous aggregate restrictions](https://www.tigerdata.com/docs/build/continuous-aggregates/create-a-continuous-aggregate)

### C. Shared PostgreSQL with a scoped storage service and no clinical RLS

Put tenant selection and data access inside one trusted storage service. Its front door verifies the original
caller's authority against the resolved site or verifies a dispatcher-issued assignment for the requested
operation. It alone creates the internal scope. API, evaluator, realtime, report workers and export clients
receive operation results and hold **no raw clinical database credentials**. The service's fixed read, write
and lifecycle implementations have separate least-privilege roles. They bind every predicate, join, mutation
and cache lookup from the internal scope. A client UUID, a caller-set session variable and an EXECUTE grant on
a function accepting any UUID each leave the caller free to choose a site. None implements this boundary. A
missing tenant condition inside the trusted service can expose a peer's rows. The service and its privileged
operations therefore enter the isolation review. Registry, authority and tenant settings can retain their D3
boundaries.

For a matched first arm, use A's exact physical layout, identity constraints, clock, windows, reports and
fenced logical export. This isolates the cost of changing the enforcement point. It removes per-relation
clinical RLS policies and their bindings where they are used solely for RLS. Clock, counter and lifecycle
operations that currently consume the binding need an explicit scoped replacement. It adds a service hop,
verification, connection ownership and a deployment/recovery unit. Count them.

Then test a layout that this boundary might unlock. Keep recent rows directly indexed. Pack closed device
status with typed ID/identifier arrays and compact clinical/modified time bounds. A private GIN lookup can
locate candidate blocks. Ordinary GIN membership leaves cross-block uniqueness unenforced. One implementation
keeps the unique directory from A. Price GIN *in addition* and drop it if the directory already answers the
lookup. One header-free design serializes writes for the tenant before probing recent rows and sealed blocks
for either identity, including duplicates within the incoming batch. A conflicting key can occur in any hour,
so clinical-time pruning cannot justify skipping older keys. Perform the check and publish in one transaction
with a snapshot fresh after acquiring the lock. The sealer, updates moving between days, retries and lifecycle
replacement participate in the same protocol. Carry ordinals, exact history stamps and any resend keys inside
the blocks, with a bounded path to find cold candidates. Measure lock wait/hold, blocks visited and
decompressed, mutation cost, and report/history scans at increasing depth. Failure to bound the writer or
retain every winner rules out that variant.
[PostgreSQL unique indexes](https://www.postgresql.org/docs/16/indexes-unique.html)

### D. Tenant-owned SQLite with no RLS anywhere

Use one SQLite store per tenant for clinical records, local identity and ordinal indexes, clock, tombstones,
optional summaries, tenant settings and tenant authority. Authority includes owner assignments, subjects,
roles, credential and session state, and references to the tenant’s encrypted secrets. Preserve the existing
key-management service and per-tenant keys. The API remains the sole ordinary clinical writer. Inside a
tenant, a transaction commits the data, history floor and any retry receipt before the owner signals readers.
A local unique index spans all dates. Evaluator windows and reports read the same tenant-local store. Start
with local rows, then compare the same lossless sealed remainders as A. Include retained local headers, file
slack and idle tenants when pricing the missing tenant prefixes.

**Who can open which store.** A private platform registry maps a verified site alias to an immutable tenant
ID, current owner, generation and lifecycle phase. Give the trusted router only an exact route lookup. Only
the operator control plane may change placement or lifecycle and read fleet audit. Protect the registry with
process/network isolation and operation grants on a private service or ordinary database, with RLS disabled.
Its service credential never reaches a tenant worker. The router delivers the original request authority or a
bounded internal job assignment to the chosen owner. The owner verifies the audience, current local authority
and operation before reading tenant data. The runtime gives it exactly one database handle and permission for
that tenant’s persisted objects. A caller cannot name a file, cell, tenant or object prefix. Count this
runtime and router as trusted components.

**What operators take on.** Shared clinical policies, tenant prefixes and a shared clinical connection pool go
away. The operator now owns placement, single-owner fencing, fleet schema upgrades, durable replication,
idle-file overhead and recovery capacity. Measure a cold wake, a report during failover and the first correct
window after restart. Losing the owner must prevent its stale process from committing even if it resumes. A
separate clinical mirror would enter both the consistency contract and the byte total. D2 and D3 both need
review for adoption.

**Live restore.** The lifecycle operation takes a consistent, digest-verified logical export for the original
tenant. On live restore, suspend and drain the owner, keep the current roles, revocations, sessions, encrypted
credentials and key references under the lifecycle contract, then replace the authorized clinical data and
reconcile history above the live floor. A logical import into the fenced owner can preserve live authority in
the same file. Blindly replacing the file could reactivate a revoked credential. Rotate one credential and
revoke another after export, restore and check authorization as well as the forward history and peer traffic.
For a deleted tenant, the separate recovery contract uses the exact deletion artifact and retained keys.
Cross-tenant cloning has its own destination credentials.
[Restore identity](multitenancy-decisions.md#restore-identity-and-cloning) ·
[Deleted-tenant recovery](multitenancy-decisions.md#deleted-tenant-exact-artifact-first)

**Reproduced scope of prior work.** The celld 0.6.3 lab passed 12 synthetic checks including overlapping
identities, concurrent retries, rollback and same-disk process restarts. The deliberately shared-cell control
detected a routing error. The lab used its own small protocol and a local object store. Nightscout adapter
parity, host-loss durability, allocated bytes on the joined workload and fleet operating cost are open.
[Tenant-cell study](../../10-domain/tenant-cell-sqlite-deep-dive.md) ·
[Retained lab results](../../../tools/lab/tenant-cell-sqlite/results/local.json)

## A late import every design must serve

Import a year-old record today into a day that already contains sealed records. While its receipt-based edit
window is open, correct it and move its clinical time across a local midnight. Under the tiering proposal the
cutoff is measured from the **later** of clinical time and receipt. Exercise current unrestricted behavior
first. Treat the proposed cutoff as a separate matched variant, including the permitted no-op resend, stable
refusal and privileged correction. Test both sides of the cutoff. A storage benchmark cannot adopt a retention
or edit rule.
[Tiering proposal, §5.8](storage-tiering-proposal-2026-11-24.md#58-edit-window-old-data-is-append-only)

A–C can retain the late row in the writable set until eligible for sealing. D can keep it directly writable in
the owning store. The clinical-date report sees the corrected value in the destination day. Modification
history sees the new change after the previous watermark. Invalidate both affected days and dependent
comparison periods in the tenant's calendar, including any adjacent-day inputs used by time-weighted
calculations. Read one consistent snapshot across old and recent detail and choose one logical winner. Compare
the summary with a fresh calculation on detail after correction, sealing, an interrupted rebuild and restore.
Preserve receipt age through export. On same-tenant restore issue forward corrections and deletions beyond the
live floor, keep current authority and keys per lifecycle policy, and resume other tenants throughout.
[Restore protocol](multitenancy-decisions.md#restore-suspend-drain-replace) ·
[History continuity](multitenancy-decisions.md#restore-history-forward-correction)

## Matched experiment and decision rule

1. **Freeze the controls.** Use joined core `6819f1a41e491aec70e1ecd6642a11b1b5033968`, deploy
   `9cccbbbd8cc1453fbe46489d75308ce7693fc8a3` and the fixture digests in
   `storage-performance-bytes-20261124/result.json`. Keep MongoDB Snappy as the allocation denominator and
   single-site behavior oracle. Replay identical Loop, Trio, AndroidAPS and CGM-only arrivals, identities,
   settings, reader mix, late edits and resends. Hold recent data, directly readable 48 hours, active tenant
   skew, retention and durability constant. Use 2, 14 and 60 days, plus a predeclared deeper history that
   actually crosses the cold boundary. Include cold owners and newly activated sites. Pin runtime, resources,
   engine versions and maintenance schedule. Counterbalance repeated fresh runs and separate cold, warmed and
   restart observations.

2. **First comparison.** Replay A joined, then A with the compact header, then B with the *same* header and
   payload under scoped access. Use the packed lookup and full-document range to determine whether the access
   path changed. Compare B's private columnstore only if there is a specific codec, index or sealer it
   replaces. At 60 days, join the best passing entries/treatments representation before scoring whole-store
   acceptance. Above 90 days, compare native bundles and the columnstore on the same sealed documents, with
   identical live indexes and correction behavior. On C, the same-layout control prices the service boundary.
   Its packed challenger proceeds when a complete uniqueness protocol passes the two-writer check. D starts
   with the real Nightscout adapter and lifecycle slice before a fleet comparison. One frozen end state per
   architecture goes to any subsequent capacity qualification.

3. **Count all bytes.** Score allocated bytes after ordinary maintenance, at empty, loaded and post-churn
   checkpoints. Include heap/TOAST, every index, headers and identity maps, manifests, counters, summaries,
   tombstones, catalogues, cold objects, control-plane metadata and per-file slack. Count each authoritative
   byte once and charge additional durable copies. Compare the complete primary data footprint to the matched
   Snappy cohort. Report WAL/journal generated and retained, compaction scratch and peak space, replicas,
   backups, requests and restore working space separately, on identical durability assumptions. Show
   per-collection and per-added-tenant-day slopes alongside totals. Under 2× is the existing first milestone
   and ≤1.5× the acceptance target on long history.

4. **Time the real work.** Measure p50/p95/p99 for tenant-scoped point reads, selective filters, mixed-tier
   history pages, report ranges, export/restore and normal API writes including commit. Separate the
   288-document resend and bulk backfill. Capture lock wait and hold, CPU per evaluation, rows/blocks visited,
   buffer reads, pool waits, bytes transferred, sealer or refresh backlog, and throughput. Measure from
   accepted write to durable evaluator output and first viewer frame under the same load, including restart.
   Use the existing 30 s p95 planning objective and 120 s clinical deadline. Qualify surviving end states at
   the established 1k and 10k points, with concurrent reports and a writer/recovery burst. Show absolute live
   cost and its slope as retained history grows. Price simplicity with the actual schema objects, privileged
   entry points, services, upgrade/rollback steps, operator recovery steps and time to verified restore.
   [Latency objectives](multitenancy-decisions.md#latency-objectives) ·
   [Experiment scope](deployment-and-rig-testing.md#concurrent-experiments-and-acceptance)

5. **Select on outcomes.** Require the same public values, winners, authorized audience, commit/history
   behavior and lifecycle recovery. Report any known reference divergence explicitly. Report a bounded live
   slowdown alongside bytes saved for maintainer judgment. Keep full RLS if compact rows or indexed headers
   recover the gain. Bring a limited D3 exception forward if a specific private feature lowers whole-store
   allocation or materially simplifies the system at comparable clinical and recovery cost. Consider a broader
   change only on evidence that the smaller boundary cannot deliver the gain. Any arm that fails isolation or
   the clinical deadline has failed the comparison.

### What would falsify isolation or recovery?

Use paired synthetic tenants with the same public identities, timestamps and cache keys but distinguishable
values. Every refusal needs a successful authorized twin and an independent readback of both tenants. Exercise
the product entry points with their actual serving roles.

| Property | Observable failure and discriminating control |
|---|---|
| A read or write belongs to the resolved tenant, including after rollback, cancellation and connection reuse. | Failure is one tenant seeing its peer's value, count, conflict, acknowledgment or write effect. Alternate scopes on the same physical connection. An unbound or mismatched operation must yield zero foreign data or effects. In scratch, break the binding or trusted route and require the isolation oracle to fail. |
| Every access route enforces the selected boundary. | Exercise hot rows, sealed detail, manifests, report caches, history, sockets, export and deferred work. Try the same operation under a role without that authority. Confirm that raw access outside the selected grants fails. In A an omitted application predicate remains tenant-local under RLS. In B/C a deliberately mis-scoped private lookup must be caught by the two-tenant oracle. For D a deliberately misrouted test store must turn the oracle red on distinct values or on the authorized twin. |
| A key has one owner within the tenant/collection across all tiers. | Concurrent inserts of a colliding typed ID or eligible identifier in different hours cannot both commit as distinct records. Include an allowed identical key in the other tenant, a resend, a batch conflict, a seal race and a retry after uncertain commit. Check identity, winner, ordinal, history and stored counts independently. Break the unique arbiter in scratch and require a duplicate or wrong winner to be detected. |
| Export, restore and reports have the same tenant boundary as live traffic. | Restore one tenant while its peer continues reading and writing. A mismatched manifest, stale generation, stale owner or earlier report job cannot publish into the peer or overwrite the replacement. Validate archive membership, history above pre-restore cursors, both tenants' clinical values and the peer’s ongoing acknowledgments. A scratch cross-tenant manifest reference or stale publication must fail the oracle. |

Record the failing control and the restored passing result for each isolation or recovery claim. Local review
handoff under the workspace artifacts directory, `handoffs/HANDOFF-storage-boundaries-20261124.md`.
