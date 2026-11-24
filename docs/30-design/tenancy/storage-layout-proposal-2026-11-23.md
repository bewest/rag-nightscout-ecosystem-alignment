# Multitenant clinical storage layout: proposal

*Contributor- and maintainer-facing. **Stage 1 has a measured candidate (section 10). Stage 2 built and parked 2026-11-24** ([devicestatus-hour-chunks](multitenancy-decisions.md#devicestatus-hour-chunks)); corrections from that build are in section 9. Measured against cgm-remote-monitor
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

**Clinical audit and change history.** At candidate 2, ordinary inserts and edits write the clinical document.
V3 history filters the collection by `srvModified` (`lib/api3/generic/history/operation.js`). A soft delete
marks the stored document for synchronization. The former size trigger updated the same row a second time.
The remaining ordinal trigger maintains one counter per tenant in each ordered collection. Neither path
creates database roles or appends an audit copy of each document (read-derived at `1aaa5af33`).
Five operational audit tables plus owner settings history occupied **557,056 bytes at both two and fourteen
days** in the 100-tenant census (reproduced, retained `pg-bytes-20261123/out/*02-seeded.sizes.tsv`).
These records cover settings, credentials, policy and lifecycle events. The forecast includes their measured
footprint. Removing a hypothetical clinical audit log supplies no further reduction.

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

**Arrival-order replay at two history depths.** With 100 tenants over two days and 76,504 device-status inserts, the implemented
chunks consumed **224.1 MB** after ordinary vacuum versus **174.8 MB** for the cleaned document layout
(reproduced). The chunk table had 4,900 inserts and 71,604 updates. Its identity table stored 76,504
key-to-location rows in 16.2 MB. These rows support lookup and uniqueness, and contain no copy of the document
body. After a diagnostic full table rewrite, the two relations occupied 31.6 MB and 12.4 MB respectively.
At fourteen days and 535,444 inserts, ordinary-vacuum sizes reached **726.1 MB with chunks versus 1,230.0 MB
with the cleaned row layout**, a **41.0% saving** (reproduced). The identity table accounted for 115.2 MB.
Each replay used one transaction per document as the serving role. The short seed and the deeper seed give
different rates of space reuse. An alternative worth comparing writes each open-hour document once and
seals the hour into a compressed chunk once, preserving immediate reads and late changes. Retained evidence:
`devicestatus-chunks-20261123/bytes/d2s2{b,c}.json`, `d2s14{b,c}.json` and `full-2d.txt`.

### Stages 1 and 2 together

**About 497 MB for 100 tenants over 14 days, 0.36 MB per tenant-day** (read-derived total of three measured scratch
relations plus an estimated 25 MB for identity lookup). MongoDB on the same documents: snappy 0.45, zstd 0.30 MB per tenant-day, including per-database
overhead.

### Predicted database and primary volume sizes

> **Status note (reconciled 2026-11-24):** stage 2 is parked ([devicestatus-hour-chunks](multitenancy-decisions.md#devicestatus-hour-chunks)), so the columns and scenarios that include device-status chunks are priced options, not the current plan. The current plan is the "Candidate 2 cleanup" column (candidate 3 carries the same storage). Stage 1 is measured in section 10 and not adopted; device-status retention stays "keep everything" to match single tenant, with `PREDICTIONS_MAX_SIZE` parity measured separately (lane Q).

Read-derived forecasts for 30 retained days per tenant at the synthetic uploader mix and cadence. The last two
columns are compact-layout targets based on scratch tables. The implemented chunk writer gives higher estimates
in the arrival-order forecast below. Values are decimal GB of PostgreSQL data and indexes before WAL, free space,
backup copies and temporary restore space.

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

**Working full-history forecast using the implemented chunk writer: 1.13–1.30 TB of database data** for those
1,600 tenants, assuming the typed entries and treatments achieve their projected 0.224 MB/day. The lower scenario
starts at the measured fourteen-day footprint and extends it at the two-to-fourteen-day incremental rate
(`(726,097,920 − 224,116,736) / 1,200` = 0.418 MB per additional tenant-day). The other scenario carries the
fourteen-day average of 0.519 MB/day through all three years. These are two extrapolations from the same
synthetic replay. With the WAL and free-space allowances above they imply **1.41–1.62 TiB** of primary volume.
For 10,000 tenants at 30 days the same methods give **211–227 GB** of database data and **305–325 GiB** of
primary volume. A longer steady workload and uploader mixes measure drift in either direction. The earlier
684 GB and 121 GB figures describe the compact targets for the two installations.

If the typed entries and treatments qualify first, the cleaned device-status table can continue to serve
the full history. In the arrival-order replay it grew from 174,817,280 to 1,229,971,456 bytes across 1,200
additional tenant-days, or 0.879 MB per tenant-day (reproduced, `devicestatus-chunks-20261123/bytes/d2s14b.json`).
Adding the projected 0.224 MB/day for typed entries and treatments gives a **1.93 TB** three-year fallback
for 1,600 tenants. This estimate assumes the typed footprint and preserves the same retention.

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
per ten documents the corresponding projections are **271 GB or 277 GB**. These examples use the compact
target for the 30 hot days. Pricing that month with the implemented chunk writer adds 14–17 GB to each
example, bringing the one-packed-key case to **491–494 GB**. Both lookup frequencies are illustrative.
Some documents carry two lookup keys. Measure the actual
frequency, order/history metadata, changes to old records, and live WAL before sizing volumes for this design.
Retained evidence: `deep-history-locator-20261123/sizes.csv` and `locator.sql`.

**Choose a shorter device-status history.** Keeping entries and treatments for three years but device status
for 30, 90 or 365 days projects **416–419, 456–468 or 640–697 GB** respectively with the implemented
chunk writer and proposed typed layout. The more compact scratch target projects 402, 418 or 491 GB.
Older device-status uploads, including predictions and
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
  part). It needs compaction, reads across both representations and history rules for moving rows.
  For multi-year installations, the scenarios above price the potential benefit. The measured open-chunk rewrite
  cost and the number of keys each uploader needs are inputs to that choice.

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

The local core branch `codex/clinical-bootstrap-cleanup-20261123` removes the paired steps and their retired
validation logic in all nine catalogue variants (`0ca92678f`, fixture pins `d946bd5ee`). The 62 focused
tests passed. Whole-role startup, restore and the full suite on the joined candidate remain open. Other
index-creation and removal pairs require their own end-schema comparison, including privileges,
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

## 9. Corrections from the stage 2 build (2026-11-24, measured by lane D2)

- **Read cost moves to PostgreSQL.** Unpacking chunks made the evaluator window read 2–3.4× slower at 1,000 tenants
  (p95 82.3 → 113.3 ms, and 276.3 ms when filtering stored `json` text, which re-reads each document per field access).
  v1 and v3 reads became 2–4× faster.
- **Writes rewrite the hour.** Per-document appends cost 2.2× WAL and leave dead chunk copies until vacuum, so a fresh
  2-day load was 16 % larger than the current layout; the steady-state saving per added day was 82 %. A one-statement
  batch append made WAL linear and smaller than the current layout.
- **The identity index costs about 172 B per document**, not the ~25 MB per 100 tenants estimated in section 4.
- **GIN on arrays cannot serve lookups under row-level security**: the array operators are not leakproof, so they are
  never index conditions. The working design uses a btree on `(tenant_id, key)`.
- **[d11](multitenancy-decisions.md#d11)** (body retained as JSONB) would need marking superseded for multitenant device
  status if a chunk layout were ever adopted.
- **Untried:** a small per-document header (`created_at`, `isValid`, `srvModified`, `_id`) beside the text, so the window
  filters without reading documents. Any revisit starts there.

## 10. Typed entries and treatments on candidate 2

**Implemented on a local branch.** The ordinary multitenant PostgreSQL deployment uses the ordered
entries and treatments catalogues. Core `b8d770b04` appends a conversion to each. The integrated follow-up head is `9e665dd04`. Each document has one
typed row. The sparse JSONB remainder retains unknown fields, explicit nulls, arrays and atypical scalar
representations. The public relation reconstructs the document for existing readers and writers.
PostgreSQL `numeric` preserves decimal values and scale. UTC timestamp strings use two presence bits
only when their original spellings can be reconstructed exactly. The frozen candidate keeps the existing
tenant-prefixed indexes, identifier rules and tenant ordinal counter. Unordered treatments remains an
upgrade predecessor. An operator upgrading a populated ordered source replays the ordinary grants
before restarting the roles.

**Reproduced on PostgreSQL 16.15.** On the HTTP corpus, the candidate matched frozen candidate 2 on
27 of 27 observations. Both matched the single-site MongoDB reference on 25 of 27. The two existing
differences are v1 filters on nested custom fields, one in each domain. The fenced lifecycle round trip
restored eight entries and seven treatments with both insertion counters, preserved the live write clock
and matched all four pre-restore v1/v3 reads. Source and restored fixtures are synthetic.

**Storage, reproduced.** The two-day fixture covers 100 synthetic tenants (28 Loop, 29 AndroidAPS, 23 Trio, and 20 CGM-only). PostgreSQL total
relation sizes include the table, its indexes and the tenant insertion counter. Every document and
the ordered per-tenant identity streams matched on both arms. MB here means 1,000,000 bytes.

| Domain | Documents | Current MB | Typed MB | Reduction |
|---|---:|---:|---:|---:|
| Entries | 57,600 | 78.36 | 56.61 | 27.8% |
| Treatments | 36,361 | 53.75 | 42.86 | 20.3% |
| Combined | 93,961 | 132.11 | 99.48 | 24.7% |

Indexes occupied 72.07 MB before and 72.07 MB after conversion. They account for roughly 72% of
the typed footprint. The 14-day scratch figures in section 4 used a smaller index set. They are unsuitable
as a prediction for this implementation. **Read-derived scenario:** extending the observed difference of
0.163 MB per tenant-day to 1,600 tenants over 1,095 days gives about 286 GB saved across these two domains.
Long-term planning still needs a multi-horizon growth measurement on representative uploader mixes; the
short fixture also includes fixed overhead.

**Evaluator window, reproduced.** Seven interleaved warmed PostgreSQL runs used the same tenant,
row-level security, indexed windows and work ceiling. Each arm returned identical row digests.
The experimental evaluator selects through the typed columns and reconstructs each selected document
once (core `16be428ee`). All three arms recorded zero physical reads in the measured plans.

| Window | Documents | Current median | Initial typed median | Typed evaluator follow-up median |
|---|---:|---:|---:|---:|
| Entries | 576 | 10.032 ms | 465.780 ms | 21.950 ms |
| Treatments | 467 | 9.639 ms | 90.226 ms | 17.620 ms |

The direct evaluator path recovers much of the reconstruction cost. Both medians still exceed
the current layout. These single-tenant window samples on a shared prepaid worker measure SQL
execution. Fleet p95 and evaluator CPU per cycle at 1,000 and 10,000 tenants remain open.

**Batch resends, reproduced.** On the initial candidate, a v1 resend of 288 existing entries exceeded the
clock-port fixture's 10-second statement timeout. The logical document was rebuilt for each alternative in an equality filter.
Core `4bb4f3ec8` applies the index bounds first and evaluates the exact filter on each candidate row.
In the follow-up, both domains inserted and resent all 288 documents and retained their original counts.
Mixed scalars, arrays, explicit nulls, missing fields, and OR filters lacking a common bound also
returned the expected rows on both physical layouts. A selective `dateString` lookup exposed
a separate read cost under the serving role. The existing layout's index fetched three rows for three
matches. Both typed plans fetched all 576 tenant rows and discarded 573. Deep-history qualification
needs a selective lookup for canonical and exceptional timestamp spellings.

**Writer cost, reproduced.** In the ordinary 288-treatment upload with late stamping enabled, both
the current and frozen typed layouts held the tenant write clock across four statements. The quieter
same-node rerun measured 47.7 ms on the current table and 422.9 ms on the typed implementation.
The existing gate requires less than 200 ms. Core `9ea9a1115` uses the selected catalogue to
pack late-stamped batches directly into the typed table with the same tenant RLS and insertion
allocator. On the joined source, the same gate measured 83.8 ms at 288 and 283.7 ms at 1,000.
All 14 tests in the stock late-stamp suite passed, including concurrent uploads and negative
controls. The settings-off v1 write path still costs more: for 288-entry resends, median 1.13 s
on the current layout versus 5.23 s with the read fix (one warmup and three measured runs per arm).

The first combined read candidate is core `64f2afa00`. Deployment companion `e81592dcc` transfers ownership
of the invoker views as well as their backing tables during fresh and repeated bootstrap. Both combined
heads (`64f2afa00` and `9e665dd04`) repeated all 27 frozen PostgreSQL observations and the four pre/post-restore reads. Its upgrade
starts from the existing nominal candidate. The size study uses that candidate's unchanged index
contracts and the frozen typed migration checksums.

Core `f17c54da9` also preserves a treatment's optional resend-index exemption across logical
restore. The earlier implementation raised PostgreSQL error 23505 when restoring two valid
historical rows sharing a resend key. The follow-up restores both documents, their identity
kinds, relative order and the exemption flag. Existing fixtures without that column are supported.

A wider synthetic top-ten probe found four treatment pages with different tie choices. All
matching documents and values agreed. Three pages cut through an equal timestamp at the page
boundary, and one reordered equal history stamps inside the page. An explicit second sort key
of `_id` made the pages agree. The existing APIs request a single sort key, so compatibility of
implicit tie behavior and page continuation remains an adoption decision. This probe is separate
from the fixed 27-observation HTTP corpus.

The retained run is `artifacts/typed-entries-treatments-20261123`. The local lane pickup is
`artifacts/handoffs/HANDOFF-typed-entries-treatments-20261123.md`.

### Scalar queries that can ship independently

**Reproduced.** A 48-hour synthetic SGV query returned 576 rows in identical date/ordinal order with
the same digest for ID kind, ID, date and SGV. Full JSONB fetched and projected in Node took 214,286
PostgreSQL DataRow bytes. Selecting the four columns took 40,885 bytes on each layout, an 80.9%
reduction. Median client times over five rotated warm reads were 8.48 ms for the current document
query, 3.65 ms for the current generated columns and 6.22 ms for the new typed columns. The 24-hour
result showed the same reduction in bytes. The database ran under RLS on a prepaid worker alongside
another test job. These are database-to-Node results for canonical numeric SGVs.

**Read-derived opportunities.** The ordinary reader selects `id_kind, doc` and applies projections in
Node (`lib/storage/postgres-entries-read.js`). Its existence-only writer callers already declare an
`_id` projection. They can use a narrow query with the same identity, scope and sort contracts.
For the operator's provisioning and restore floor check, `lib/server/serve/postgres-domains.js`
currently extracts the maximum numeric `srvModified` from the document across all selected domains.
The ordered entries and treatments expose the numeric column. Checking the same bound on that
column is a candidate for avoiding full-document work during commissioning, while preserving the
single database snapshot and the fallback for other domains.
The evaluator can also select modification stamps and identity first when it decides which rows a
resident projection needs to reload. Its existing write clock and full-snapshot fallback still own
ordering and recovery. A reporting or chart query that consumes only time and glucose can reuse the
existing generated columns when its field semantics are explicit. Plugins, exports and full-document
API routes retain lossless documents. Validate any scalar substitution against the current behavior
on missing, null, differently typed and extension fields. The retained comparison is
`lab/scalar-window-pilot.json`.

Use the existing index set for the first measurements. On PostgreSQL, fetching a subset of columns reduces
transfer even when a heap visit is required. A covering index can also avoid heap reads when its payload
covers the query and the visibility map permits it. The update rate and measured 72% index footprint
make actual plans preferable to assuming a new covering index pays for its storage.
[PostgreSQL 16 index-only scans](https://www.postgresql.org/docs/16/indexes-index-only-scans.html)

### What depends on insertion order

**Read-derived.** A fresh design can use a document's typed identity to settle ties after the
requested sort keys. That would change the evaluator contract. The SQL and in-process paths
currently use insertion order, and earlier work observed different evaluator output on tied
documents. Compare output from both paths on equal-time entries carrying different values and
reversed ID order before making that choice. [Evaluator order decision](multitenancy-decisions.md#view-reads-total-order)

The public v3 history URL resumes strictly after a timestamp. Its header alternative rounds to
seconds and includes the boundary. Neither accepts the last ID of a page. When timestamps can
tie, continuing inside a group requires carrying the full key across requests. An opaque cursor
can encode the modification stamp, ID kind and stored ID for one collection. The tenant write
clock separately orders committed writes so a later commit cannot appear behind a client's
watermark. The four limited-page probes above checked tie choices within a page.
See core `lib/api3/generic/history/operation.js` and `lib/storage/postgres-write-clock.js`.

**Reproduced in the v1 resend parity corpus.** A resend without a unique identity can match two
entries on the same `sysTime` and `type`. The earlier stored entry receives the update even when
it carries the higher ID. The response can identify the last match. Treatment fallback first
uses the existing identifier and date priority, then arrival order for the remaining ties.
These cases can arise on fresh installations. See core
`tests/v1-resend-official-parity.integration.test.js` and `lib/storage/treatment-key-order.js`.

**Read-derived from measured relation sizes.** On the 93,961-document typed fixture, the two
unique ordinal indexes occupy 6,103,040 B. The counter relations including their own indexes
occupy 516,096 B. Together they account for 6.65% of the 99,475,456 B for these two collections.
Net savings across the database require a comparative load with the replacement access paths.
The retained inputs are `lab/index-sizes.json` and `lab/frozen-size.json`.

**Design option.** Preserve the legacy selection and reply behavior only for ambiguous groups,
or explicitly choose a new winner for future v1 writes. Test a second resend, deletion of the
current winner and a restore before repricing a design without the per-row ordinal. Across hot
and cold data, the public sort and limit still select one ordered result, and sync must traverse
edits and deletions. Late uploads and lookups by ID or identifier can still require a per-document
location. Compare the same fixture in a single table and split across tiers, with an equal-key
pair on opposite sides. The [counter and restore decision](multitenancy-decisions.md#storage-machinery-removal)
remains in force.
