# Multitenant clinical storage layout: proposal

*Contributor- and maintainer-facing. **Stage 1 proposed. Stage 2 in implementation, pending qualification.** Initial measurements used cgm-remote-monitor
`2dee799c8e` (the #8898 round core) on PostgreSQL 16.15 and MongoDB 8.0, with 100 synthetic tenants seeded through the
product write path at 2 and 14 days of looping history. Figures are labelled measured or read-derived. Raw evidence
stays local: `HANDOFF-pg-bytes-20261123.md` (lane S) and `HANDOFF-storage-alternatives-20261123.md` (lane R). Decisions
already taken live in [multitenancy-decisions.md](multitenancy-decisions.md); this page restates none of them.*

## 1. Summary

The multitenant PostgreSQL layout stores clinical data at about **1.94 MB per tenant-day**. The same documents in
single-tenant MongoDB 8.0 grow by **0.38 MB per tenant-day with snappy compression and 0.24 MB with zstd**. That puts
PostgreSQL about 5× larger, at 4.4× MongoDB snappy on the 14-day seed (measured). The difference is the layout, not
the data and not the multitenant machinery:
- The synthetic documents match the maintainer's real-world range of 0.25–0.6 MB per tenant-day.
- Non-clinical tables are about 230 KB per tenant and do not grow with days.

Candidate 2 (`1aaa5af33`) includes the removal of the `storage_bytes` trigger and four redundant indexes.
On the matched two-day schema replay, clinical storage fell from 1.865 to 1.546 MB per tenant-day (reproduced).
The per-tenant counter preserves restore ordering. The stored evaluator frame serves cold realtime readers.
The maintainer kept both. [Storage decision and measurements](multitenancy-decisions.md#storage-machinery-removal)

This proposal goes further, in two stages:

1. **Typed columns for entries and treatments**, with the fields that are not typed kept in a small remainder document.
2. **Device status stored as one compressed row per tenant per hour.**

The scratch layouts together imply **about 0.36 MB per tenant-day**, including an estimated identity-index allowance.
The API contract applies to both designs. Each has separate gates in section 6.
[Device-status implementation decision](multitenancy-decisions.md#devicestatus-hour-chunks)

## 2. The problem, measured

### Bytes per stored row (14 days, 100 tenants, written through the product)

| collection | raw JSON | PostgreSQL heap | TOAST | indexes | **PostgreSQL total** | MongoDB snappy, data + indexes |
|---|---|---|---|---|---|---|
| entries | 231 | 767 | 0 | 1,021 | **1,788** | 74 + 239 |
| devicestatus | 2,326 | 1,635 | 309 | 948 | **2,892** | 576 + 113 |
| treatments | 331 | 826 | 0 | 998 | **1,824** | 116 + 331 |

### Why the rows are large (measured unless marked)

- **The original size trigger wrote each row twice.** A scratch comparison suggested 27% savings. The later matched
  replay measured 11.9% for removing the trigger and 17.1% with the four index removals.
- **Indexes are about half of every table.** Entries carries 15 indexes and 11 generated columns, copied from
  single-site MongoDB's index list. Generated columns alone cost 120–136 B per row.
- **Rows under about 2 KB are never compressed.** PostgreSQL compresses a value only when the whole row passes about
  2,032 bytes. `toast_tuple_target` and lz4 do not change that entry point: the entries and treatments heaps came out
  byte-identical with them. Every entries and treatments row, and most device-status rows, are stored uncompressed.
  WiredTiger compresses every block.
- **jsonb is larger than its text for small documents.** A 231-byte SGV is stored as 463 bytes of jsonb, because the
  stored document also gains `_id`, `srvCreated`, `srvModified`, `utcOffset`, `sysTime` and `dateString`.

### Consequences beyond disk

- **Size per tier (measured model, checked to 0.4 % against the 10k restore of 44.24 GB):**
  - 10k tenants with 30 days is 586 GB of database;
  - 5k with 30 days is 293 GB.
- **The 10k run's api errors** (16.4 % 5xx, against 2.4 % in a same-sized peer run) coincided with autovacuum on a
  13 GiB relation running through the load, a buffer hit rate of 0.952, and disk reads 2.7–7× slower than the peer's
  (measured; the causal chain is read-derived, `HANDOFF-pg-sizing-20261123.md`). Fewer bytes per row means less to
  vacuum, cache and read.

## 3. What other projects do (read-derived, file:line in lane R's handoff)

| project | clinical storage | what is kept |
|---|---|---|
| Nocturne (PostgreSQL) | typed tables, tenant column and row-level security; prediction curves in separate jsonb columns | unknown glucose fields and unknown nested openaps/loop keys dropped; about 0.6–0.75 KB per glucose reading and 2.5–3.5 KB per loop status including indexes (estimated from column types) |
| nighttroop (SQLite) | one STRICT-typed SQLite file per site; raw openaps/loop object as text up to 8 KB | unknown fields dropped; predictions deleted after 1 day; devicestatus thinned with age and deleted after 30 days; 20 MB cap per site |
| AndroidAPS (Room) | glucose and doses typed; devicestatus as JSON text | 186 days |
| Trio (Core Data) | one row per prediction point | forecasts 2 days, the rest 90 days |
| Loop (Core Data) | each dosing decision as one blob | 7 days locally |
| xDrip / xdripswift | glucose typed, no predictions | 90–180 days |
| single-site Nightscout on MongoDB | whole documents, WiredTiger block compression | operator tool deletes devicestatus older than N days (default 30) |

Nightscout differs from all of these in one way: it is a hub that returns each uploaded document with its unknown
fields, under [d8](multitenancy-decisions.md#d8) and [d20](multitenancy-decisions.md#d20). So the lessons to take are:

- **compression across records**, as WiredTiger and TimescaleDB do;
- **typing only what is queried**;
- not dropping fields;
- retention, which is a product decision for both modes (section 7).

## 4. Proposal

### Stage 1 — typed entries and treatments

One row per document. Each query key is stored as a typed column. Every other field is kept in a small `rest jsonb`
holding exactly the fields not represented by a column.

| collection | typed columns (proposed) | in `rest` |
|---|---|---|
| entries | `_id` (12-byte ObjectId, or text where `id_kind` is a string), `date bigint`, `type`, `sgv int2`, `mbg int2`, `direction`, `device`, `identifier`, `srvCreated`, `srvModified`, `utcOffset`, `insertion_ordinal` | every other field, plus `sysTime`/`dateString` when they differ from what `date` derives |
| treatments | `_id`, `created_at` (text `COLLATE "C"`, as now), `eventType`, `insulin`, `carbs`, `duration`, `rate`, `absolute`, `enteredBy`, `identifier`, `srvCreated`, `srvModified`, `insertion_ordinal` | every other field |

- **Indexes:** the sizing experiment used keys for tenant ordinal, window reads, history and identifier. Additional index
  removals require evidence of use and query plans. [Index decision](multitenancy-decisions.md#storage-machinery-removal)
- **Measured on scratch copies of the 14-day rows:**
  - entries 146 MB against 721 MB;
  - treatments 139 MB against 464 MB.
- **Value and query fidelity.** In the synthetic HTTP corpus at `official/dev` `79144cbd0`, two fresh MongoDB sites
  produced equivalent results across 27 observations (reproduced). A v1 numeric date-range query returned seven
  entries. V3 history returned all eight, including a string-valued date. V1 rendered a string-valued insulin field
  as a number while v3 history preserved its original string. The comparison also caught float32 rounding, a lost
  null, and a lost nested field. Retained evidence: `stage1-storage-oracle-20261123`, `reference-responses.json`
  and `controls.log`.
- Keep an original value in `rest` whenever promoting it to a column would discard a distinction visible on these
  paths, including missing versus null. Numeric filter pushdown must preserve membership. Preserve `sysTime` and
  `dateString` when they differ from the strings that `date` derives. Measure the lossless implementation's footprint.

### Stage 2 — device status by tenant-hour

One row per `(tenant, hour)` holding that hour's device-status documents as one JSON text value. The row passes the
compression threshold, so documents share redundancy, the way MongoDB's block compression works. A slim identity
index maps `_id` and `identifier` to the chunk.

- **Measured on the 14-day rows:** 187 MB as JSON text with lz4, against 825 MB for the body-only layout.
- **Not chosen:** jsonb with lz4 (216 MB), and jsonb with pglz (476 MB), because pglz gives up when the first 1 KB is
  incompressible.
- **Writes:** the hour being written is the open chunk, rewritten on each upload of about 12 documents per hour.
- **Updates and deletes:** a device-status update or delete rewrites its chunk. Read-derived: uploaders rarely update
  device status; this needs a count from a real-shaped corpus.

The first adapter on core `a5402ca99` points to the complexity cost (read-derived). It presents a document view over
the chunks, maintains identity and time bounds, rewrites chunks in triggers, and prunes the chunks read for a query.
The scratch byte measurement preceded these structures. A fresh-install design should select one representation per
collection after measuring the real reader, writer and restore paths. Historical lab fixtures alone do not justify
maintaining two storage implementations.

### Stages 1 and 2 together

**About 497 MB for 100 tenants over 14 days, 0.36 MB per tenant-day** (read-derived total of three measured scratch
relations plus an estimated 25 MB for identity lookup). MongoDB on the same documents: snappy 0.45, zstd 0.30 MB per tenant-day, including per-database
overhead.

### Predicted database and primary volume sizes

Read-derived forecasts for 30 retained days per tenant at the synthetic uploader mix and cadence. Values are decimal GB
of PostgreSQL data and indexes, before WAL, free space, backup copies and temporary restore space.

| Tenants | Original layout | Candidate 2 cleanup | Cleanup plus device-status chunks | Chunks plus typed entries and treatments |
|---:|---:|---:|---:|---:|
| 1,000 | 59 | 49 | 27 | 12 |
| 5,000 | 293 | 243 | 134 | 61 |
| 10,000 | 586 | 486 | 268 | 121 |

The model is `database MB = 12.3 + 0.44 × provisioned tenants + daily MB × retained tenant-days`. A retained
tenant-day represents one day's history at the fixture's write rate. An inactive site's retained history still counts.

- **Original, 1.938 MB/day.** The slope came from 100 tenants at two and 14 days. The model predicted 44.05 GB for
  the original 10k short-history restore, which measured 44.24 GB. This validates that layout and workload.
- **Candidate 2, about 1.61 MB/day.** Apply the matched two-day clinical byte ratio (309,108,736 / 373,006,336)
  to the original slope. The earlier 391 GB forecast at 10k used a more optimistic scratch estimate of cleanup savings.
  A second history depth through the candidate's API would measure the new slope directly.
- **Device-status stage alone, about 0.88 MB/day.** The original entries and treatments slopes were 0.510 and
  0.330 MB/day. Scale each by its two-day cleaned-to-original table-size ratio (about 0.864 and 0.820).
  Add 0.166 MB/day for device status, from 187 MB of scratch chunks plus the estimated 25 MB identity index across
  1,400 tenant-days and a 10% incremental-growth allowance. The implemented chunk metadata, indexes and live rewrites
  still need a product-path measurement.
- **Both stages, about 0.39 MB/day.** Apply the same 10% allowance to the combined scratch estimate.
  At 10k tenants this gives **59 GB at 14 days, 121 GB at 30 days, 355 GB at 90 days and 1.43 TB at 365 days**.
  Longer horizons extrapolate the same mix, write rate and compression. Retention remains a separate product decision.

For a **10k, 30-day primary**, the proposed 200 GiB volume is plausible only under the combined layout forecast.
121 GB is about 113 GiB. Allowing 32 GiB for WAL and keeping 25% of the volume free gives about 193 GiB. The reserve
is an illustrative planning assumption. Peak WAL can exceed its target. With those same assumptions the chunk-only
forecast needs about 375 GiB and candidate 2 about 646 GiB. Size backup storage and simultaneous restores separately
from the serving primary. The dedicated-node measurements still determine latency and throughput.

For **1,600 tenants each keeping three years**, 1,095 days per tenant gives 1,752,000 retained tenant-days.
The read-derived database estimates are **3.40 TB** on the original layout, **2.81 TB** on candidate 2,
**1.54 TB** with device-status chunks and **684 GB** with both stages. Under the same WAL and free-space
assumptions the combined layout needs about **892 GiB of primary volume**, which fits a **1 TiB** primary.
Every 0.10 MB change in the measured daily footprint changes the three-year database estimate by 175 GB.

### Where a three-year installation could save more

At the fixture cadence of about 852 documents per tenant-day, this installation would retain about
1.49 billion entries, treatments and device-status documents. The 684 GB forecast averages roughly 460 bytes
per document, including indexes. On the same documents the measured single-site MongoDB growth rates of 0.38
and 0.24 MB per tenant-day imply about 666 GB with Snappy and 420 GB with zstd in three years of incremental
data and indexes. These are comparisons at this uploader mix. WiredTiger compresses records together in blocks
and shares key prefixes within indexes. [MongoDB 8.0 storage engine](https://www.mongodb.com/docs/v8.0/core/wiredtiger/)

**Keep every document.** Qualify a single representation for each collection first. The scratch typed entries
and treatments had 89.3 MB and 60.9 MB of indexes respectively. Those indexes alone were about 30% of the
combined 497 MB layout. Their query plans, use during representative API traffic, and identity and ordering
obligations determine which can be combined. The 684 GB forecast already assumes the smaller index set.

For deeper savings, TimescaleDB keeps recent data in rows and converts older time chunks to compressed columnar
storage. An equivalent storage experiment here keeps 30 days in the combined layout and groups older complete
documents by tenant, collection and day. Lane R measured 26.8 MB of cold chunk tables over 200 tenant-days.
At 1,600 tenants this gives 248 GB for hot data, cold bodies and fixed costs, **before** the cold lookup and
history structures. A historical correction, an identity-based resend, an export spanning the boundary and a
restore interrupted during compaction all need to return the same documents in the same order. Retained
evidence: `HANDOFF-storage-alternatives-20261123.md`. [TimescaleDB chunks and columnstore](https://www.tigerdata.com/docs/reference/timescaledb/hypertables)

A prepaid PostgreSQL 16.15 scratch run priced one possible cold lookup table. Its unique key covered tenant,
collection, identity kind and lookup value. Its row stored the destination day. Compactly encoding canonical
ObjectId and UUID strings while preserving arbitrary UTF-8 keys reduced incremental table-plus-index bytes
by **17% at one lookup row per document**. All lookup tuples decoded to their original values; a variant
that lowercased opaque keys lost information. Two depths provided the incremental rates, with 327,168
synthetic documents at the larger depth. At one lookup row per cold document, the three-year estimate for
hot data, cold bodies and this table becomes **477 GB with packed keys or 524 GB with text**. At one lookup
per ten documents the corresponding projections are **271 GB or 277 GB**. Both lookup frequencies are
illustrative. Some documents carry two lookup keys. Measure the actual
frequency, order/history metadata, changes to old records, and live WAL before sizing volumes for this design.
Retained evidence: `deep-history-locator-20261123/sizes.csv` and `locator.sql`.

**Choose a shorter device-status history.** Keeping entries and treatments for three years but device status
for 30, 90 or 365 days projects **402, 418 or 491 GB** respectively. These read-derived values use the separate
collection rates underlying the 684 GB estimate. Older device-status uploads, including predictions and
uploader state, disappear from historical API reads and exports. Nightscout already exposes an optional
collection-specific retention setting in single-site mode. A default or an operator option for the multitenant
service is a product decision. [Nightscout configuration](https://github.com/nightscout/cgm-remote-monitor#readme)

### Not proposed

- **Typed device status** (predictions as `int2[]`, enacted object deduplicated). It measured worse: 1,026 MB against
  825 MB, because smaller bodies fall under the compression threshold.
- **Filesystem compression (ZFS).** Lane R's proxy measured 4.5×, but it saves disk only. The buffer cache and vacuum
  still see uncompressed pages, so it does not address the 10k symptoms. An operator may still choose it.
- **lz4 or `toast_tuple_target` alone.** No effect below the threshold (measured).
- **Per-tenant-day cold chunks for every collection** (lane R's candidate B, 0.13 MB per tenant-day for the cold
  part). It needs a compaction job, a read union and history rules for moving rows between hot and cold. Stage 2 gets
  most of that gain for the collection that dominates the bytes, with no background job. Revisit only if multi-year
  history makes entries and treatments dominant after stage 1.

## 5. What must not change

- **The API contract.** v1 and v3 return each stored document with its unknown fields, and the same value a single
  site returns. The current jsonb layout already normalises key order and number representation. So the bar is the
  value equality today's differential tests check against `official/dev`, not byte identity of the upload
  (read-derived; the differential decides).
- **Identity:** `_id` is the hub key and `identifier` the client sync identity
  ([d20](multitenancy-decisions.md#d20)). Re-send outcomes match `official/dev`
  ([multitenant-write-settings-at-defaults](multitenancy-decisions.md#multitenant-write-settings-at-defaults)).
- **Queries:** the closed operator set of [d8](multitenancy-decisions.md#d8) runs over typed columns plus `rest`, with
  `mingo` as the oracle. Filters on untyped fields evaluate on `rest`, correct but slower, as non-indexed filters are
  today.
- **Order and history:** reads keep the insertion-ordinal tie-break
  ([view-reads-total-order](multitenancy-decisions.md#view-reads-total-order)). v3 history never skips a late commit
  ([write-clock-history-arms](multitenancy-decisions.md#write-clock-history-arms)). A device-status chunk rewrite stamps
  `srvModified` on the changed document only.
- **The hub records, never derives dosing state** ([d18](multitenancy-decisions.md#d18)). No field is recomputed,
  stripped or summarised in storage.
- **Single-tenant MongoDB** is unchanged ([d4](multitenancy-decisions.md#d4)).
- **Schema changes in place** until an operator release
  ([prerelease-schema-in-place](multitenancy-decisions.md#prerelease-schema-in-place)).

### Fresh installs and existing lab fixtures

Read-derived at core `1aaa5af33`: nine candidate catalogue files across six clinical domains still carry both
`0099_*_storage_bytes` (ten statements to install and populate the statistic) and `0100_*_storage_bytes_removed`
(three statements to remove it). Standard and socket-order catalogues are alternatives. Some initial migrations
also build indexes that `0101` drops. The volume model assigns no daily savings to removing obsolete bootstrap steps.

**Reproduced on PostgreSQL 16.15** using the frozen migration runner, with a disposable database for each layout.
Omitting the `0099` and `0100` pair in each of the six selected catalogues reduced the number of applied migrations
from 41 to 29 and removed 78 SQL statements from the fresh bootstrap. Both sets passed migration checks.
Schema-only dumps including policies, grants and indexes matched, as did the synthetic row returned after a write
in each domain. An added index made the comparison fail and the
original result returned after the control was removed. The old path left one dropped column slot per clinical
table. The shorter path left zero. An entries database carrying the old ledger correctly returned `MIG_UNKNOWN`
when checked with the shorter catalogue. Retained evidence: `fresh-clinical-schema-20261123`. The comparison
covers the six clinical schemas. Whole-role startup, fixture conversion and production changes remain separate.

For the next clean baseline, define the retained tables, indexes and grants directly and remove the paired steps
and their special ledger-validation code together. Compare fresh and current end schemas, including privileges,
tenant restore ordinals and API-visible values. Re-seed disposable fixtures from their recipes. For an expensive
fixture, a one-time conversion on a copy can be worthwhile if counts, document digests, ordinals and a post-restore
write agree. Preserve the source snapshot for runs pinned to its original schema. The first operator release
starts the forward-upgrade contract. [Pre-release schema policy](multitenancy-decisions.md#prerelease-schema-in-place)

## 6. Gates before adoption, per stage

Each gate is measured on a candidate built on lane M's branch (the decided removals); a stage that fails a gate is not
adopted.

1. **Contract differential:** the v1/v3 write, read and history suites, the re-send differential against
   `official/dev`, and a round-trip test over a corpus with unknown and oddly typed fields (string `sgv`, `date` as
   string, nested unknown objects). Red when a field is lost or retyped.
2. **Real-shaped corpus:** bytes per tenant-day on documents shaped like each uploader (Loop, AndroidAPS, Trio, xDrip,
   CGM-only), synthetic only. The synthetic looping data repeats more than real data, so the compression figures here
   are an upper bound.
3. **Read latency** at 1k and 10k tenants (measured; not done for any alternative yet):
   - the evaluator window read;
   - `GET /api/v1/entries` and treatments;
   - v3 history;
   - a v1 query on an untyped field.

   p50 and p95 against the current layout. Device-status chunk decoding cost lands on the evaluator, so evaluator CPU
   per cycle is part of the gate.
4. **Write path:** batch-upload lock hold
   ([per-tenant-lock-bounded-hold](multitenancy-decisions.md#per-tenant-lock-bounded-hold)) and statements per write
   are no worse than after the removals. The cost of a device-status chunk rewrite is measured, including an update to
   a document in a closed hour.
5. **Restore and export:** per-tenant export and restore round-trip a tenant byte-equal at the API.

## 7. Separate decisions this proposal does not take

- **Device-status prediction retention.** Most projects keep predictions briefly. Single-site Nightscout offers a
  30-day devicestatus delete. A retention policy is a product decision taken the same way for single-tenant and
  multitenant sites; storage stays agnostic.
- **Deep history beyond 30 days** (multi-year tenants). Revisit candidate B after stage 1 and 2 measurements.

## 8. Cost (read-derived)

- **Stage 1:**
  - the entries and treatments PostgreSQL adapters (write, read, re-send, query compilation to columns plus `rest`);
  - the migration;
  - restore and export.
- **Stage 2:**
  - the device-status adapter;
  - the chunk writer under the tenant write clock;
  - the identity index;
  - the evaluator window read.

Each stage is one lane with the gates above. Stage 2 can proceed without stage 1, and it is the larger saving:
device status is about 60 % of current bytes.
