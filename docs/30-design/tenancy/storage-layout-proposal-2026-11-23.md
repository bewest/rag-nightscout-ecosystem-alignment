# Multitenant clinical storage layout: proposal

*Contributor- and maintainer-facing. **Proposal, 2026-11-23, not adopted.** Measured against cgm-remote-monitor
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

[storage-machinery-removal](multitenancy-decisions.md#storage-machinery-removal) already removes the retired machinery
(the `storage_bytes` trigger, the per-tenant counter, the stored output frame, and the duplicate and prefix indexes).
Predicted from the measurements, that brings the layout to about 1.3 MB per tenant-day.

This proposal goes further, in two stages:

1. **Typed columns for entries and treatments**, with the fields that are not typed kept in a small remainder document.
2. **Device status stored as one compressed row per tenant per hour.**

Together, on the same documents, they measured **about 0.36 MB per tenant-day**, which is where MongoDB is. Each stage
is a separate decision with its own gates (section 6). Neither changes what the API returns or what single-tenant
sites do.

## 2. The problem, measured

### Bytes per stored row (14 days, 100 tenants, written through the product)

| collection | raw JSON | PostgreSQL heap | TOAST | indexes | **PostgreSQL total** | MongoDB snappy, data + indexes |
|---|---|---|---|---|---|---|
| entries | 231 | 767 | 0 | 1,021 | **1,788** | 74 + 239 |
| devicestatus | 2,326 | 1,635 | 309 | 948 | **2,892** | 576 + 113 |
| treatments | 331 | 826 | 0 | 998 | **1,824** | 116 + 331 |

### Why the rows are large (measured unless marked)

- **The size trigger writes every row twice.** An AFTER INSERT trigger updates each row just inserted. Removing it
  saves 27 % (decided).
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

- **Indexes:** the decided set only (tenant ordinal unique, the window and history keys, identifier).
- **Measured on scratch copies of the 14-day rows:**
  - entries 146 MB against 721 MB;
  - treatments 139 MB against 464 MB.
- **Lossless:** `sysTime` and `dateString` are dropped only where they equal what `date` derives; otherwise they stay
  in `rest`.

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

### Stages 1 and 2 together

**About 497 MB for 100 tenants over 14 days, 0.36 MB per tenant-day** (measured on scratch copies, including the
identity index). MongoDB on the same documents: snappy 0.45, zstd 0.30 MB per tenant-day, including per-database
overhead.

### Predicted database size per tier (decimal GB, before WAL and headroom)

| tenants | current, 30 d | after the decided removals, 30 d | after this proposal, 30 d |
|---|---|---|---|
| 1k | 58.6 | 39.1 | 12.1 |
| 5k | 292.9 | 196 | 60.7 |
| 10k | 585.8 | 391 | 121 |

The current column is measured, the other two predicted, with a 10 % allowance for incremental growth.

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
