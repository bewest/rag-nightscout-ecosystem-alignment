# Multitenant clinical storage by age: brief and proposal

*Contributor- and maintainer-facing proposal, 2026-11-24. **Proposed; nothing here is adopted.** It builds on the
measured [storage layout proposal](storage-layout-proposal-2026-11-23.md) and restates none of its figures beyond
what the argument needs. Figures are labelled **measured** (ours, linked), **read-derived** (arithmetic or reading
of code and records), or **vendor-documented** (a provider's page as read on 2026-11-24, linked). Prices change;
re-read them before quoting.*

## 1. Summary

- **Accept the larger volume for the first production boundary.** On the current layout, multitenant PostgreSQL
  stores about 1.6 MB per tenant-day where single-site MongoDB stores 0.24–0.38 MB on the same documents
  (measured). At 30–90 retained days this costs cents per tenant-month and the 1,000-tenant run passes with a
  0.9996 buffer hit rate. Bytes are not yet the problem.
- **Keeping years of detail in the hot layout is the problem.** Ten years at today's layout on replicated block
  storage costs about **$2.30 per tenant-month**, roughly ten times an illustrative compute share of
  $0.10–0.25 (section 3). That would erode the savings from consolidating compute.
- **Store data by age, matching how Nightscout is used.** Recent days serve live coordination at today's latency.
  Up to about 90 days serve reports and comparisons. Older data serves statistics and audits, which can be slower.
  A tiered layout keeps ten-year detail for about **$0.06–0.27 per tenant-month** (read-derived). A
  detail-retention limit with summaries kept beyond it is a later, deferred option.
- **Every lever, its trade-off and its priority** is in section 10.
- **Stay on plain PostgreSQL.** Native time partitioning and our own cold tier get most of the benefit.
  TimescaleDB's compressed chunks do not support row-level security (vendor-documented), which conflicts with
  [D3](multitenancy-decisions.md#d3). Citus solves a scale-out problem we have not measured and adds a cluster of
  database nodes.

## 2. What has been tried

All measured on synthetic tenants written through the product unless marked; detail and evidence in the
[layout proposal](storage-layout-proposal-2026-11-23.md).

| Attempt | Result | State |
|---|---|---|
| Remove the size trigger and four redundant indexes | −17.1 % clinical bytes | Adopted, [storage-machinery-removal](multitenancy-decisions.md#storage-machinery-removal) |
| `lz4` or `toast_tuple_target` | No effect: rows under ~2 KB are never compressed | Rejected |
| Typed device status (predictions as arrays) | Larger (1,026 vs 825 MB): smaller rows fall under the compression threshold | Rejected |
| Device status as one compressed row per tenant-hour (stage 2) | −82 % per added day; evaluator window p95 82 → 113–276 ms; 288-document write hold 45 → 638 ms | Parked, [devicestatus-hour-chunks](multitenancy-decisions.md#devicestatus-hour-chunks) |
| Typed entries and treatments (stage 1) | −24.7 %; indexes unchanged and 72 % of the result; window read ~2× slower, settings-off resends 1.13 → 5.23 s, a selective lookup scans the tenant | Built locally, not adopted |
| Prediction curve cap | Saves nothing: uploaders send at most 48 points | Parity only, [predictions-max-size-single-tenant-parity](multitenancy-decisions.md#predictions-max-size-single-tenant-parity) |
| Filesystem compression (ZFS, proxy) | ~4.5× on disk; buffer cache and vacuum see uncompressed pages | Not proposed for hot data |
| Per-tenant-day cold chunks (scratch) | ~0.13 MB per tenant-day for cold data | Priced, not built |

**The lesson.** Every attempt that compressed hot rows traded clinical read or write latency for bytes. The ones
that helped removed work (a trigger, indexes). The remaining large wins are in data nobody reads at low latency.

## 3. What storage costs on DigitalOcean

### Prices (vendor-documented, read 2026-11-24)

| Product | Price | Notes |
|---|---|---|
| Block storage volume | $0.10 per GiB-month | 1 GiB to 16 TiB per volume; snapshots $0.06 per GiB-month ([volumes](https://docs.digitalocean.com/products/volumes/details/pricing/)) |
| Managed PostgreSQL, Advanced Edition storage | $0.115 per GiB-month | Primary from $130/month; standby and read-only nodes cost the same as the primary ([pricing](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/)) |
| Spaces object storage | $5/month includes 250 GiB, then $0.02 per GiB-month | ([Spaces](https://docs.digitalocean.com/products/spaces/details/pricing)) |
| Spaces Cold Storage | $0.007 per GiB-month | $0.01 per GiB retrieved beyond an allowance; 30-day minimum retention |
| General Purpose droplet, 8 vCPU / 32 GiB | $252/month | CPU-Optimized 8 vCPU / 16 GiB is $168 ([droplets](https://www.digitalocean.com/pricing/droplets)) |

From 30 November 2026 every new managed PostgreSQL cluster that needs more than 4 GiB of RAM, a standby or a
read replica must use Advanced Edition ([plan changes](https://docs.digitalocean.com/release-notes/upcoming/dbaas-plan-changes/)).
The multitenant deployment currently runs PostgreSQL itself on Kubernetes with block volumes
(`nightscout-deploy` `bindings/kubernetes/lib/ns/nightscout.libsonnet:258`, read-derived), so the block price
applies.

### The three sizes asked about

Three copies means a primary and two replicas, each on its own volume; backups are extra. Read-derived from the
prices above.

| Data | Roughly | Block, 1 copy | Block, 3 copies | Spaces standard | Spaces Cold |
|---|---|---:|---:|---:|---:|
| 600 GB | 10k tenants × 30 days today | $56 | $168 | $11 | $4 |
| 60 TB | 10k tenants × 10 years today (≈102k tenant-years at 1.61 MB/day) | $5,588 | $16,764 | $1,118 | $391 |
| 600 TB | 100k tenants × 10 years today | $55,879 | $167,638 | $11,176 | $3,912 |

Monthly figures. 60 TB needs at least four 16 TiB volumes per copy; 600 TB needs 35, which is not a sensible
single database. Object storage prices include the provider's own redundancy, so one copy is shown.

### Per tenant, against compute

A per-tenant view makes the comparison with consolidated compute direct. Block storage, three copies, with a
1.4× allowance for WAL and free space (the allowance the layout proposal uses), read-derived:

| Detail kept | Today, ~1.61 MB/day | Stage 2 only, ~0.88 | MongoDB-equivalent, ~0.38 |
|---|---:|---:|---:|
| 90 days | $0.06 | $0.03 | $0.01 |
| 1 year | $0.23 | $0.13 | $0.05 |
| 3 years | $0.69 | $0.38 | $0.16 |
| 10 years | $2.30 | $1.26 | $0.54 |

**Compute share, illustrative and not measured as a fleet:** the capacity ladder targets 1,000–3,000 tenants per
host ([capacity-test-tiers](multitenancy-decisions.md#capacity-test-tiers)), and one General Purpose 8 vCPU host is
$252/month. A handful of such hosts plus a database node for a few thousand tenants is about **$0.10–0.25 per
tenant-month**. Storage passes compute at about one year of hot detail, and is ten times compute at ten years.

Two caveats:
- 1.61 MB/day is the synthetic looping mix. Real MongoDB sites measure 0.25–0.6 MB/day; synthetic data repeats
  more than real data, so real sites could be higher or lower in PostgreSQL. A real-shaped corpus is still owed
  (layout proposal, gate 2).
- Many sites upload only CGM data and are far smaller than looping sites. The fleet mix sets the real average.

## 4. Use cases set the tiers

The [nominal write-age decision](multitenancy-decisions.md#nominal-clinical-write-age) distinguishes ongoing writes from bulk historical recovery. A tenant’s existing history can be much older than its next upload. Read use cases determine the proposed tier boundaries.

| Use | Age read | Who | Latency need |
|---|---|---|---|
| Live coordination: dashboards, alarms, followers, the evaluator | Last ~48–60 hours, sometimes a week | Clients, evaluator, realtime | Today's: tens of milliseconds |
| Reports and comparisons: a 4–12 week period against another | Up to 90 days routinely; comparison periods 1–3 years back | Owners, clinicians, report tools | Seconds are acceptable |
| Statistics and audit | Months to years | Owners, auditors, researchers | Minutes, or an asynchronous job, are acceptable |

Beyond about 90 days, detail is rarely looked at directly; it feeds statistics and occasional audit. At five to
ten years it is debatable whether full detail is still needed, or only summaries.

## 5. Proposal

### Tiers

| Tier | Age (defaults; the tenant chooses within operator limits, section 6) | Storage | Served by | Latency |
|---|---|---|---|---|
| **Hot** | 0–14 days | Today's row layout, in the current time partition | Every API, evaluator, realtime | Unchanged |
| **Warm** | 14–90 days | Same rows, older partitions, fewer indexes | Every API | Same order, may be slower on unindexed filters |
| **Cold** | Over 90 days | One compressed bundle per tenant, collection and month | v1/v3 reads with a relaxed latency; export; report jobs | Seconds; audit-scale reads as jobs |
| **Summary** | Any age, kept beyond a detail-retention limit if one is chosen | One small statistics row per tenant-day | Reports | Fast |

Hot and warm differ only in partition and index set, so a report over 90 days reads ordinary rows. The 14- and
90-day boundaries are defaults (section 6).

### 5.1 Hot and warm: native time partitioning (no new dependency)

PostgreSQL's declarative partitioning splits each clinical table by time, for example monthly, under the same
table name. Row-level security, grants and the API are unchanged; serving roles keep grants only on the parent.
Partitions are created ahead of time by the `admin` role on a schedule (`pg_partman` would also do it but is one
more component).

Predicted gains (read-derived from the 10k evidence; none measured yet):
- **The working set stays in memory.** Reads of the last few days touch only the newest partition and its indexes.
  The failed 10k run coincided with a buffer hit rate of 0.952 and autovacuum running across a 13 GiB relation.
- **Vacuum work may concentrate in recent partitions.** Near a month boundary, recent uploads can touch two partitions. Bulk imports and historical corrections can also write older months. Measure vacuum on each workload.
- **Fewer indexes on older partitions.** PostgreSQL allows an index on some partitions only. Warm partitions can
  drop indexes that only live traffic uses. Indexes are about half of every table today (measured).
- **Moving data to cold, or deleting it, becomes detaching a partition**, not deleting billions of rows.

Costs and open design points:
- **No global unique index.** A unique index on a partitioned table must include the partition key, so
  tenant-wide uniqueness of `_id` and `identifier` ([d20](multitenancy-decisions.md#d20)) needs a small identity
  table mapping each key to its time. Stage 2 measured that structure at about 172 bytes per document.
- **Queries without a time range read every partition.** Identity lookups go through the identity table.
  Resend matching keys already carry a time (`created_at`, `date`), read-derived; confirm per collection.
- **The partition key** is chosen in section 5.2.
- **Late or backfilled data** writes into its older partition; this must stay under the bounded write-lock hold
  ([per-tenant-lock-bounded-hold](multitenancy-decisions.md#per-tenant-lock-bounded-hold)).

### 5.2 The partition key

Three candidates, judged on architecture, performance and compatibility. Read-derived from candidate 5's
catalogues (core `0952306f7`, `migrations/candidates/postgres-{entries,treatments-socket-order,devicestatus}-v1.json`)
and the read paths; nothing here is measured yet.

**What the key must serve.** Today's indexes show the access paths: entries by `date` (and `dateString`,
`sysTime`); treatments and device status by `created_at`; v3 history by `srvModified` in every collection; identity
through the unique `(tenant_id, identifier)` indexes and `_id`; tie order through the unique
`(tenant_id, insertion_ordinal)` index. The evaluator window, v1 lists, reports and the tier and retention policy
are all defined on clinical time.

| | Clinical time as uploaded (`date`, `created_at`) | Server receipt time (`srvCreated`) | **Normalized clinical time** (leading option) |
|---|---|---|---|
| What it is | The collection's own time field, as stored | When the hub received the record | A `clinical_ms` column computed at write from the collection's time field, parsed to UTC; `srvCreated` when missing or unparseable |
| Architecture: tiers and retention | Matches the policy, but `created_at` is text with mixed spellings and offsets, so ranges do not partition cleanly | Ages data by arrival. **An imported five-year history, the expected path for migrating existing sites, would all sit in the newest partition**, and a policy written in clinical age could not drop partitions | Matches the policy; one numeric range per partition; imports land in the right months |
| Performance: evaluator, lists, reports | Prunes on `date`; `created_at` text filters prune unreliably | **No pruning** for the main read paths: they filter by clinical time, which the database cannot relate to arrival | Prunes. `ORDER BY date DESC LIMIT n` reads the newest partition first. A text `created_at` range maps to a safe numeric bound widened by the largest UTC offset (±14 h) |
| Performance: writes | Ordinary uploads concentrate in recent months. Bulk recovery can touch older months | New inserts land by receipt time | Ordinary uploads concentrate in recent months. Bulk history lands in clinical months |
| Performance: v3 history | Scans `srvModified` on every attached partition | The `srvModified` predicate alone cannot prune creation months. An old document can be edited today | Scans every attached partition. Tiering keeps that to a few (hot and warm); cold edits are promoted (5.4) |
| Compatibility | Visible behaviour unchanged; a stored-value edit moving a row between partitions is a delete and insert inside PostgreSQL | Unchanged | Unchanged; the column is internal and never returned. Odd values (string `date`, missing `created_at`) fall back to receipt time and stay readable |

**Leading option: normalized clinical time,** monthly ranges. It compares best on the three criteria above but
needs a measured comparison before adoption (phase 2). It would come with:
- a **default partition** that takes rows whose month is already cold (late uploads, imports into old months);
  the tiering job folds them into that month's bundle;
- an **identity table** `(tenant_id, collection, key) → clinical_ms` keeping `_id` and `identifier` unique across
  partitions (about 172 bytes per document, measured in stage 2);
- the insertion ordinal kept unique by its allocator; per-partition indexes need not be unique.

Receipt time simplifies placement of new inserts. Imported old records then arrive in a recent partition. Compare the actual clinical-time and history query plans before choosing a key.

### 5.3 Index cut, first and independently

Before partitioning, read `pg_stat_user_indexes.idx_scan` from a 1k run with the realistic mix and drop indexes
never used, behind the existing end-schema comparison and API differential. Entries carries 15 indexes and 11
generated columns copied from MongoDB's list; generated columns alone cost 120–136 bytes per row (measured).
Lowest risk, no layout change, and it benefits every tier.

### 5.4 Cold: compressed monthly bundles

When a month passes the cold boundary, a job writes each tenant's documents for that collection and month as one
compressed bundle (zstd-compressed NDJSON or similar), with a small manifest of time range, counts and
identities, and then detaches the warm partition once every tenant's bundle verifies. Scratch measurement of a
similar layout: about 0.13 MB per tenant-day (measured, lane R).

- **Where bundles live.** First in a PostgreSQL table, so backup, restore and row-level security stay as they are.
  Moving them to object storage (Spaces, or Cold Storage) is a later step that changes backup and access control,
  and is what takes the 600 TB case from impossible to about $4,000/month.
- **Reading.** A v1/v3 query reaching cold months decompresses the months it covers and filters with `mingo`,
  already the query oracle under [d8](multitenancy-decisions.md#d8). Results and order match the warm path;
  latency is seconds. Very large ranges may run as jobs.
- **No edits.** Cold data is older than the edit window (section 5.8), so bundles are written once and never
  rewritten. Without an edit window, an edit would have to copy the document back to the hot table and mark it
  superseded in the bundle's manifest; the edit window removes that machinery.
- **Export and restore get cheaper:** a tenant export of old data is a copy of its bundles.

### 5.5 Summaries and detail retention

**What the ecosystem computes.** The [reports survey](reports-survey-2026-11-24.md) read the report and statistics
code of cgm-remote-monitor (`official/dev` `79144cbd0`), nightscout-reporter, Nocturne, nighttroop, AndroidAPS,
Trio, LoopFollow, xDrip, xdripswift, nightguard and GlycemicGPT, against the 2019 time-in-range consensus, GMI
and the AGP layout (read-derived and cited):
- **Spans.** Users pick 1, 7, 14, 30 and 90 days nearly everywhere. cgm-remote-monitor's reports default to
  7 days and cap at 186; xdripswift offers 365; nightscout-reporter compares a window with the same window up
  to 12 months earlier. The clinical standards work on 14–90 whole days with at least 70 % coverage.
- **cgm-remote-monitor computes every report in the browser** from day-by-day API v1 reads; there is no
  statistics endpoint. Its low/in/high split uses a target the user types per request.
- **Persisted daily aggregates are rare:** AndroidAPS and Trio keep insulin totals; nighttroop keeps a full
  per-day row (including a 288-slot glucose trace) rebuilt by a background job when writes mark a day stale. It
  is the closest prior art. cgm-remote-monitor's CGP pentagon already reduces each day to sums and merges days
  by addition.
- **Thresholds and weighting differ between tools** (inclusive or exclusive band edges, count- or
  time-weighted, population or sample SD), so a summary must store raw ingredients, not finished percentages.

**Proposed summary row** (one per tenant and local day, in the profile time zone; survey section 5): coverage
counts and observed minutes; count- and time-weighted Σ and Σ²; a 1 mg/dL glucose histogram over 39–400;
standard band minutes; the pentagon's AUC terms; per-day variability path sums; hypo episode counts; a
288-slot 5-minute glucose trace and per-hour sums; insulin and food totals per day and per hour; optionally
5-minute IOB and COB series. About **1.0–1.3 KB per tenant-day, about 2 KB with the loop series** (estimated,
not measured), about 1–2 % of a cold bundle; about 4–7 MB per tenant over ten years.

| From the summary row | Statistics |
|---|---|
| **Exact** | Coverage and the 14-day/70 % sufficiency check; mean, SD (either form), CV, GMI, eA1c over any day range; every standard band and any user target band; pooled median and quartiles; GRI, LBGI/HBGI, ADRR; the CGP pentagon; daily and average insulin, basal/bolus split and carbohydrates; hourly means; calendar-aligned week, month and comparison periods |
| **Exact for 5-minute sensors** | AGP and time-of-day percentiles across days, from the 5-minute trace. With one reading per 5 minutes the trace holds every reading, so the result equals one computed from detail. Sensors that report more often keep one value per 5-minute slot, which can shift a percentile slightly; storing every reading per time-of-day bin would remove that at about 1–2 KB more per day, which this proposal does not take |
| **Needs detail** | Day-by-day charts (daytoday, weektoweek, reporter's daily graphics); loopalyzer's meal alignment; treatment lists and edits; calibrations; prediction overlays; audit and single-document reads |

The reports that need detail are viewed over 1–14 days and occasionally up to the 90–186-day caps, which is the
hot and warm tiers, with cold reads at seconds beyond. Treatments are small and back several of them, so they are
a candidate for longer detail retention than entries and device status (section 6), pending per-collection bytes.

**Rules for summaries:**
- **Built from detail, before any deletion.** Once detail is gone a new statistic or a fix cannot be recomputed;
  `schema_version` records what a row carries.
- **Stale and rebuilt** when a backfill, an edit or a time-zone change touches the day. Under the edit window
  (section 5.8) a day older than the window changes only by an operator import, so its row is final.
- **Same deduplication as the reports** (one reading per minute, values 39–600), so a summary and a detail read
  agree.
- **Both modes.** The row is computed above the storage seam, so single-site MongoDB can build the same rows.

Detail retention stays **keep everything** by default, matching the decision taken today for device status;
section 6 sets out who may limit it. Summaries are derived statistics for reports, not dosing state; section 5.7
treats them as a cache of the statistics API, which this proposal reads as within [d18](multitenancy-decisions.md#d18).

### 5.6 Ten-year cost with tiers

Read-derived, per tenant-month, block storage three copies with the 1.4× allowance for hot and warm (90 days at
today's layout, $0.06), plus cold detail for the remaining 9.75 years:

| Cold bundles stored in | Cold at ~0.15 MB/day | Total |
|---|---:|---:|
| Block storage, 3 copies | $0.21 | **$0.27** |
| Spaces standard | $0.01 | **$0.07** |
| Spaces Cold Storage | $0.004 | **$0.06** |
| Untiered, today's layout | — | **$2.30** |

### 5.7 One statistics API for both modes

Today every reader computes its own statistics from raw reads (survey sections 2–4). cgm-remote-monitor's reports
run in the browser and fetch each day with up to three v1 calls, so a 90-day report is up to 270 requests
returning every reading; nightscout-reporter, LoopFollow, xDrip and others each repeat the same work with their
own band edges, weighting and SD form.

**Proposal:** a standard, versioned set of report endpoints, served by both single-site MongoDB and multitenant
PostgreSQL, with one statistics library in core behind them. Proposed shape (read-derived from the survey;
names illustrative):
- **daily summaries** over a date range: the section 5.5 statistics per local day;
- **period statistics** for one or more ranges, for comparisons (bands, mean, SD, CV, GMI, GRI, percentiles,
  insulin and carbohydrate totals);
- **time-of-day profile** (AGP percentiles) over a range.

Parameters cover the variations the survey found: target range and band edges, count- or time-weighting,
population or sample SD, time zone and day boundary. Defaults follow the 2019 time-in-range consensus. Read
permission is the same as for the underlying collections. Raw v1 and v3 reads stay as they are; clients adopt
the endpoints when their maintainers choose. Nocturne's analytics endpoints (period windows and comparisons) are
prior art.

**Why it stacks with the other optimizations.** The endpoint is the contract; what sits behind it can change
without clients noticing, provided every step returns the same answer as computing from detail:
1. **Compute from detail on request,** in both modes. Fewer requests and less data transferred than today's
   per-day raw reads, and one implementation of every statistic.
2. **Read per-day summary rows** (section 5.5) for the days they cover, in both modes, falling back to detail for
   stale or missing days.
3. **Tiers** (multitenant): long ranges read summaries instead of decompressing cold bundles; detail is read only
   for the hot and warm days a chart shows.
4. **Cache finished responses** for repeated report views.

Each step is gated by a differential against step 1 on a synthetic corpus. Because the endpoint computes from
records with a shared library, storing summaries is a cache of that computation while detail exists, which this
proposal reads as within [d18](multitenancy-decisions.md#d18); only after a detail-retention limit deletes detail do summaries
become the only copy.

### 5.8 Edit window: old data is append-only

Most Nightscout data is written once. Recent records are edited: treatments corrected, soft-deleted
(`isValid: false`) or replaced by a resend. Accepting that **no record older than a threshold, for example 14 or
30 days, can be edited** (maintainer direction, 2026-11-24) removes most of the cost of storing old data.

**The rule (proposed):**
- A record is editable until **the later of its clinical time and the time the hub received it, plus the edit
  window**. A history imported or backfilled yesterday can still be corrected for the window, even if its clinical
  time is years old.
- **Edits** are updates, replacements and deletions of an existing record, through v1, v3 or the socket.
  Outside the window:
  - a resend identical to the stored record succeeds and changes nothing, matching what a client sees today;
  - a change is refused with a stable, documented error code;
  - an operator correction path stays available (support, data repair, privacy erasure).
- **Inserts** of new records with old clinical times (backfill, pump history catch-up) are not edits and remain
  allowed. Within the window they land in their partition; older ones land in the default partition until the
  tiering job folds them in.
- **Whole-period removal** (single site's admin cleanup tools, a tenant's retention setting) is retention, not
  editing (section 6).
- **Default 30 days; the operator may lower it to 14 or raise it to 90** (maintainer direction, 2026-11-24).
  The window is never longer than the warm boundary, so cold data is never edited: a 90-day window needs a
  warm boundary of at least 90 days. A longer window keeps more partitions writable, so fewer are frozen and
  summary rows become final later.

**What it buys (read-derived):**
- **Partitions older than the window are read-only.** They can be frozen once, rebuilt compactly, given a smaller
  index set (no `srvModified` history index is needed for records that can no longer change) and vacuumed
  never again.
- **Cold bundles need no edit path,** no promotion and no superseded markers (section 5.4).
- **Summary rows older than the window are final** except after an operator import (section 5.5).
- **Append-only alternatives become viable** for old partitions: Citus columnar, and TimescaleDB compressed chunks
  without rewrites (section 7.1).
- **Cross-partition moves end at the window:** an edit that changes a record's clinical time can only happen
  while the record is recent.

**Compatibility risks (read-derived; gate before adoption):**
- **Clients that change old records.** AndroidAPS keeps about 186 days of local history and Trio about 90, so a
  user deleting or correcting an older treatment in the app would send an update that is now refused. How each
  uploader reacts to a refused update (retries forever, drops it, surfaces an error) must be checked per client
  before adoption: AndroidAPS, Loop, Trio, xDrip, nightscout-connect and the careportal.
- **Single-site parity.** Single-site MongoDB allows any edit at any age. Following the rule that multitenant
  behaves as single sites do, the window would be offered in both modes, with single site defaulting to no
  window unless its operator sets one.

## 6. Retention policy framework

Retention today is one rule, "keep everything", and age-related settings are scattered: `PREDICTIONS_MAX_SIZE`,
single site's devicestatus cleanup tool, `DBSIZE_MAX`, the deleted-tenant retention window. Tiering needs one
model that covers every use case, so an operator and a tenant can reason about it in one place.

### Policy dimensions

| Dimension | Values | Example default |
|---|---|---|
| **Data class** | entries, treatments, device status, profile, food, activity; summaries | — |
| **Hot boundary** | days at today's latency | 14 days |
| **Warm boundary** | days served as ordinary rows | 90 days |
| **Detail retention** | days, years or unlimited; after it, detail is deleted and summaries stay | Unlimited |
| **Summary retention** | years or unlimited | Unlimited |

Each dimension is set per data class. Device status (loop decisions and predictions) is the largest class and the
one most often trimmed elsewhere; entries and treatments carry the long-range statistics.

### Who decides

Three layers, each narrowing the one above:
1. **Product floors and ceilings**, fixed in code because something depends on them. The hot boundary covers at
   least the evaluator's window (about 60 hours) and a week of coordination. The warm boundary covers at least
   14 days, the minimum period for a glucose profile report. Summaries are never deleted before the detail
   they summarise.
2. **Operator limits** per deployment: the range the tenant may choose for each dimension, and the default.
   This is where cost is controlled: an operator bounds hot and warm days and may cap detail retention.
3. **Tenant choice** within the operator's range, made by the owner through the owner settings surface. Changes
   are recorded in the existing owner settings history.

### Rules

- **Deletion by age is a setting.** Detail is deleted by age only where a detail-retention limit is set, by the
  tenant within the operator's range. Changes are recorded in the owner settings history. Lengthening applies
  to data that still exists; deleted detail does not come back. Notices and export prompts need a user
  interface, which is out of scope.
- **Same model in both modes.** Single-site MongoDB maps the same settings onto its own mechanisms (a scheduled
  delete with summaries kept) so the behaviour matches; tiers are internal to multitenant storage, latency aside.
- **Inactive sites.** A site that stops uploading keeps its history under the same policy. Removing whole
  inactive tenants stays a lifecycle decision (deletion, export, key retention), not a retention setting.
- **Clinical age, not arrival.** Every boundary is measured in the record's clinical time (section 5.2), so an
  imported history is tiered as it would have been had it arrived live.

## 7. Plugins and alternatives evaluated

| Option | What it is | For | Against | Verdict |
|---|---|---|---|---|
| **Native partitioning** | Built into PostgreSQL | No new component; works with row-level security; available everywhere | No global unique index; partition creation to schedule | **Proposed** (5.1) |
| **pg_partman** | Extension that creates and drops partitions | Mature, saves writing the scheduler | Another component; not available on DigitalOcean Advanced Edition (vendor-documented) | Optional |
| **TimescaleDB** | Extension: time-chunked "hypertables", compressed columnar old chunks, retention policies | Exactly the hot/cold pattern; typically large compression | Row-level security is **not supported** on compressed (columnstore) chunks ([vendor-documented](https://www.tigerdata.com/docs/reference/timescaledb/hypercore)), against [d3](multitenancy-decisions.md#d3). Compression is under the Timescale License: free when not offering TimescaleDB itself as a hosted database ([licence](https://www.tigerdata.com/legal/licenses)); some operators would need a licence reading. Listed only for DigitalOcean Standard Edition, not Advanced ([extensions](https://docs.digitalocean.com/products/databases/postgresql/details/supported-extensions/)). Unique indexes must include the time column, as with native partitioning | **Not proposed.** Revisit only if cold data is served through a narrow, audited function rather than row-level security |
| **Citus** | Extension that spreads tables across worker nodes by `tenant_id`; also a columnar format | Built for tenant-keyed SaaS; row-level security on distributed tables since 11.0 ([vendor-documented](https://www.citusdata.com/updates/v11-0)) | A multi-node database cluster to operate; not on DigitalOcean managed PostgreSQL; our triggers and write clock need requalifying; columnar is historically append-only. Solves a single-node limit we have not measured: hot and warm at 10k × 90 days is about 1.5 TB at today's layout, much less after cuts | **Not now.** Several independent deployments, each with its own database and placed by the tenant registry, scale out with no new software |
| **Columnar extensions** (pg_duckdb, pg_mooncake, pgEdge ColdFront) | DuckDB or Iceberg/Parquet beside PostgreSQL | Analytics and cold data in object storage | Young; ColdFront announced June 2026 inside a vendor distribution; pg_mooncake mirrors rather than moves data | Watch |
| **Filesystem compression for cold partitions** | A tablespace on a compressed filesystem | No schema change; ~4.5× (measured proxy) | Node-level setup on Kubernetes; disk only | Possible stopgap for warm partitions |
| **MongoDB for multitenant** | Single-site's store | Compresses well | No database-enforced tenant isolation | Excluded by [d3](multitenancy-decisions.md#d3) |

### 7.1 Predicted impact of each alternative

None of these is measured here. Figures are read-derived from our own measurements, which are cited, or are
vendor claims, labelled as such. "Clinical path" means the evaluator window, realtime and recent v1/v3 reads.
Baseline: today's layout at ~1.6 MB per tenant-day; MongoDB 0.24–0.38.

| Alternative | Bytes | Clinical path | Long-range reads | Operations | Basis |
|---|---|---|---|---|---|
| **Native time partitioning** | About the same; plus ~0.15 MB per tenant-day if every document needs an identity-table row (852 documents × ~172 B) | Vacuum and index maintenance confined to the current partition; the 10k symptom of vacuum running through load should go. Cache gain is modest: at 10k tenants even a week of today's layout is ~110 GB, so the hot set fits in memory only after bytes per row fall | Pruned to the months asked for | Partition creation; identity table | Stage 2 identity bytes; 10k run evidence |
| **Fewer indexes, BRIN on time for warm and cold partitions** | Indexes are ~50 % of every table today; a BRIN index on an append-ordered time column is a few pages per partition (vendor-documented) | More rows fit in cache; fewer index writes per insert | Time-range scans stay efficient; selective lookups on warm data slow | None | Layout §2 |
| **Cold monthly bundles (ours)** | ~0.13–0.15 MB per tenant-day for cold data, a ~90 % cut | Unchanged | Seconds per range (decompress and filter) | Tiering job and manifest; no edit path under the edit window (5.8) | Lane R scratch, layout §4 |
| **TimescaleDB compressed chunks** | Similar order to cold bundles (vendor claims ~90 % on time series; JSONB bodies compress less than numeric columns) | Unchanged on rowstore chunks | Faster than application-side bundles: decompression happens in SQL | Extension and licence; **no row-level security on compressed chunks, and continuous aggregates require no row-level security on the hypertable** ([vendor-documented](https://www.tigerdata.com/docs/use-timescale/latest/continuous-aggregates/create-a-continuous-aggregate)) | Would save writing the tiering job, but tenant isolation for old data and summaries moves out of the database |
| **Citus, distributed** | Same per row; total spread over N workers, each with its own replicas | Throughput scales with workers for tenant-local queries; an extra coordinator hop per query | Unchanged | N + 1 database nodes; requalify triggers, write clock, restore | Vendor-documented |
| **Citus columnar for old partitions** | Vendor claims 3–10× | Unchanged if kept to old partitions | Fast scans | Historically append-only, which the edit window (5.8) makes acceptable for old partitions; a Citus dependency without distribution | [Vendor-documented](https://learn.microsoft.com/azure/cosmos-db/postgresql/concepts-columnar) |
| **Columnar or Parquet extensions** (pg_duckdb, pg_mooncake, ColdFront) | Object-storage prices for cold data (section 3) | Unchanged | Fast analytical scans; good fit for the statistics API over years | Young; vendor distributions; access control outside row-level security | Vendor-documented |
| **Filesystem compression** (ZFS, btrfs) on a warm or cold tablespace | ~4.5× on disk | None (the cache holds uncompressed pages) | None | Node-level setup on Kubernetes | Lane R proxy |
| **Per-row compression with a shared dictionary** (application-side zstd) | Small JSON documents could shrink several-fold (not tried) | Every read decompresses; queries need typed columns as in stage 1 | — | Dictionary versioning; stage-1-style query columns | Not tried; stage 1 showed the query-column cost |
| **Reports on a standby** | None | Report and statistics queries leave the primary | Unchanged | Routing to replicas already paid for in the three copies | Read-derived |

**What this suggests.** The cheapest clinical-path gains come from removing bytes and maintenance from the
recent data (index cut, partitioning). The large byte savings all come from compressing old data, by one of three
routes: our bundles, TimescaleDB or a columnar extension. Only our bundles keep row-level security in force for
every row. TimescaleDB is the strongest off-the-shelf alternative and would be worth revisiting if old data and
summaries were served only through a narrow, audited database function rather than row-level security; that
would be a change to [d3](multitenancy-decisions.md#d3).

## 8. Plan

Each phase is one lane with its own gates; performance results are signals
([performance-signals-not-gates](multitenancy-decisions.md#performance-signals-not-gates)) and correctness gates
stay strict.

| Phase | Work | Gate |
|---|---|---|
| **0 — first production boundary** | Accept today's volume. PostgreSQL on its own node with memory for the hot set. Size volumes for the admitted retention (90 days to 1 year). Keep everything. | The paid 5k/10k run on the qualified candidate |
| **1 — index cut** | `idx_scan` from a realistic 1k run; drop unused indexes | End-schema comparison and API differential red then green; bytes and latency signals before and after |
| **2 — time partitioning** | Compare the partition keys of section 5.2 on device status, then partition entries and treatments; identity table; warm index set; partition creation in `admin` | Key comparison on the same reads and writes; contract differential against `official/dev`; evaluator window, v1/v3, resend and lock hold at 1k and 10k; export and restore round trip |
| **3 — cold bundles** | Edit window (5.8) with its client gate; tiering job, manifest, cold read path; bundles in PostgreSQL | As phase 2, plus cold reads equal warm reads; an interrupted tiering job leaves every document readable once |
| **4 — statistics API, summaries and retention options** | The statistics API computing from detail (section 5.7; can start any time, both modes), then summary rows (section 5.5), retention settings (section 6) and bundles in object storage | Report statistics from summaries equal the same statistics from detail on a synthetic corpus, for the exact set in section 5.5; maintainer decisions in section 9 |

Any 10k latency benefit from index changes or time partitioning remains a prediction. Measure it on the corresponding read and write paths.

## 9. Maintainer direction and open questions

**Direction, 2026-11-24** (maintainer; shapes this proposal, adopts nothing):
- Relaxed latency for data older than about 90 days: **probably acceptable**, given a holistic retention
  framework across the use cases (section 6). The 90-day boundary is configurable: the tenant sets it within
  operator limits.
- Hot and warm boundaries: **the tenant sets them within operator limits** (section 6, "Who decides").
- Summaries: the statistics to keep need an analysis of the report definitions used across the open-source
  ecosystem and Nightscout's built-in reports. Done in the [reports survey](reports-survey-2026-11-24.md);
  the resulting row is in section 5.5.
- Partition key: normalized clinical time is a potential option when compared against the alternatives
  (section 5.2); it is measured against them in phase 2 before a choice.
- Automatic deletion by age: **unclear whether to build it**; if built, the tenant chooses within operator limits
  (section 6).
- Notice before deletion: **not in scope**; there is no user interface to deliver one (section 6, rules).
- Summaries and d18: produce the same statistics optimizations for both modes behind **a standard set of report
  endpoints**, so reports reuse one implementation instead of per-reader logic (section 5.7).
- AGP fidelity: settled in section 5.5 (the 5-minute trace is exact for 5-minute sensors).

- Deletion by age: **may be deferred**, for example past the initial production release; first see every lever
  with its trade-offs and priority (section 10).
- Statistics API placement and first clients: **unclear, needs more research; deferred and out of scope for now.**
- Edit window: **acceptable that no data older than a threshold can be edited**, since most data is
  append-only and it helps performance. **Default 30 days; the operator may lower it to 14 or raise it to 90**
  (section 5.8).

## 10. Levers, trade-offs and priorities

Every idea raised in this proposal and the [layout proposal](storage-layout-proposal-2026-11-23.md), in one place.
"Gain" is what it buys; figures are as labelled in the sections cited. Priorities are proposed.

### Now: before or at the first production boundary

| Lever | Gain | Trade-off | Section |
|---|---|---|---|
| PostgreSQL on its own node, memory sized to the hot set, larger `/dev/shm` | Addresses the 10k signature (buffer hit 0.952, vacuum during load, failed parallel `VACUUM`) | Operations only; a bigger node | 5.1, layout §2 |
| Size volumes for the admitted retention **including imported history** | Migrated sites bring years of history on day one; today's layout at ~1.6 MB per tenant-day sets the volume | Larger volumes than a 30-day plan | 3 |
| Index cut from `idx_scan` on a realistic 1k run | Bytes, WAL, vacuum and cache in every tier; no layout change | A dropped index a rare query needed; the API differential guards it | 5.3 |
| Real-shaped corpus (per uploader) for bytes per tenant-day | Replaces the synthetic 1.61 MB/day with fleet-shaped figures; every cost row depends on it | Lab time only | 3, layout §6 |
| Keep everything | No policy, no deletion machinery | Storage grows linearly with history | 6 |

### Next: after the first production boundary

| Lever | Gain | Trade-off | Section |
|---|---|---|---|
| Time partitioning, comparing the candidate keys first | Hot set stays cached, vacuum stays small, partitions detach instead of mass deletes; predicted latency gain at 10k | Identity table for uniqueness (~172 B per document); partition maintenance; queries without time ranges touch every attached partition | 5.1, 5.2 |
| Warm index set | Fewer bytes in older partitions | Slower unindexed filters on warm data | 5.1 |
| Statistics API, computing from detail | One implementation of every statistic, far fewer report requests, both modes | New API surface to define and maintain; placement deferred | 5.7 |
| Edit window (default 30 days; operator range 14–90) | Old partitions read-only: frozen, smaller indexes, no vacuum; final summaries; append-only storage options become viable | Clients that edit old records get refusals; must check each uploader's reaction; single-site parity | 5.8 |
| Retention settings framework (hot and warm boundaries, tenant within operator limits) | Operators bound cost; tenants choose latency for their history | Settings, validation and documentation in both modes | 6 |

### Later: when multi-year history dominates cost

| Lever | Gain | Trade-off | Section |
|---|---|---|---|
| Cold monthly bundles in PostgreSQL | Ten-year detail ~0.15 MB per tenant-day instead of ~1.6 | Reads over 90 days take seconds; tiering job, manifest, restore of an interrupted tiering | 5.4 |
| Per-day summary rows | Long-range reports without detail; about 1–2 KB per tenant-day | Rebuilds on backfill, edits and time-zone changes; schema versioning | 5.5 |
| Statistics API reading summaries, then cached responses | Report latency independent of range length | Differential gate against computing from detail | 5.7 |
| Filesystem compression for warm or cold tablespaces | ~4.5× on disk with no schema change (measured proxy) | Node-level setup on Kubernetes; disk only | 7 |

### Deferred

| Lever | Gain | Trade-off | Why deferred |
|---|---|---|---|
| Deletion by age (detail limit, summaries kept) | Caps storage per tenant | Irreversible; needs summaries first; behaviour change in both modes | Maintainer, 2026-11-24 |
| Cold bundles in object storage | Takes the 600 TB case from impossible to ~$4,000/month | Backup, restore and access control move outside PostgreSQL | Needed only at tens of terabytes |
| Statistics API placement and first clients | Adoption beyond core | Coordination with client maintainers | Needs research |
| Several independent deployments placed by the tenant registry | Scales out without new software | Fleet operations; tenant placement | No single-node limit measured yet |

### Not proposed

| Lever | Why |
|---|---|
| Typed entries and treatments (stage 1) as built | −24.7 % bytes for slower window reads, resends and selective lookups; indexes dominate the result |
| Device status by tenant-hour (stage 2) for hot data | Parked: evaluator read and write hold regressed; cold bundles take its saving for old data |
| `lz4`, `toast_tuple_target`, typed device status, prediction caps | Measured no gain or a loss |
| TimescaleDB | No row-level security on compressed chunks; licence and hosting limits |
| Citus | A database cluster to operate for an unmeasured limit |
