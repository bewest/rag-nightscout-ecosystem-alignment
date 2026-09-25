# MongoDB to PostgreSQL — the hosted multi-tenant migration

**DRAFT REQUIRING REVIEW.** Nothing here has been executed against a real deployment or a real
person's data. It is a plan, written to be argued with, and it must be reviewed by the
maintainer and by whoever will operate the hosted service before any tenant's data moves. Where
it touches what a person sees on their own screen while their data is moving, it also needs a
reader who is not a developer.

Date: 2026-09-15 · Main repo HEAD `08753474` · seam worktree `externals/work/crm-seam` at
`81a1f6ce` · every example below uses **synthetic fixtures invented for this document**. No CGM
trace, site export, device log, hostname, token or identifier from any real deployment appears
anywhere in it.

> **Connector status, 2026-09-22:** no `v0.0.14` was published and none will be. The connector
> line is `0.1.0`: connector `dev` `1946beb` carries every fix this document attributes to
> `v0.0.14`, and prerelease `0.1.0-dev.1` is on npm. Where this document says `v0.0.14`, read the
> full `0.1.0` release (queue `P0-TAG`); the pin move is `P0-PIN`.

**Adversarially reviewed 2026-09-15, same HEAD.** Corrections made during that review are marked
in place rather than silently applied, and each says what it replaced. The load-bearing one is in
**§4.3** — the transform this document recommends converts only two BSON types, so the fidelity
table's `clean` verdict meant "no errors", not "faithful". §7.2 also lost an unmeasured duration
that should never have reached a reader, and gained a plain-language "how to tell if something
went wrong" list, because every failure mode in this plan is silent.

---

## 0. Scope. Read this paragraph before anything else.

**This migration is something a self-hoster never runs.** Decision D4 makes MongoDB
**permanent** for single-tenant Nightscout, and decision D1 makes self-hosted single-tenant
first-class **permanently** — it must never become a degraded mode or a waiting room for
something else. The storage seam carries **two mature backends forever, by design**. PostgreSQL
is not where MongoDB is going; it is where the *hosted* service is, because a shared multi-tenant
store needs row-level security (D3) and a tenant discriminator (D2) and MongoDB has no equivalent
on the write axis. If you run your own Nightscout, nothing in this document is a task for you,
now or later. §7 says the same thing again in plain language, and says what changes if you
*choose* to move to a hosted tenant.

What this document covers: moving one tenant's documents **into** the hosted multi-tenant
PostgreSQL service — for a family or a clinic that has chosen to be hosted, and for the hosting
operator who has to do it without silently changing anyone's data.

**Where the undo button is.** Rollback is **§8**, and it is not an appendix: §8.1 says what is
free, §8.2 names six things that do not come back once the hosted tenant has been written to, and
§8.3 says what to keep and for how long. If you read one other section before agreeing to a date,
read that one. The plain-language version is the last two bullets of §7.2.

---

## 1. The honest state of the target, measured today

A migration plan whose target does not exist yet is a design document, and saying so is the first
thing that keeps it useful.

| thing | state, measured 2026-09-15 | how measured |
|---|---|---|
| Emitted PostgreSQL DDL | **four** collections: `entries`, `treatments`, `devicestatus`, `profile` | `make schema-emit` → `specs/generated/postgres/*.sql`; re-ran the emitter, output byte-identical to what is committed (`git status --porcelain specs/` empty afterwards) |
| DDL **vendored into the server** | **one** collection: `lib/storage/postgres/generated/entries.sql` | `ls externals/work/crm-seam/lib/storage/postgres/generated/` |
| Collections with a model | **ten** (T2.2, DONE) | `ls specs/nsschema/*.model.json` |
| Collections with index declarations as data | **eight** (adds `food`, `activity`, `auth_roles`, `auth_subjects`) | `specs/nsschema/server-indexes.json` |
| Tenant provisioning | `tenants` / `tenant_members`, one writer (`bin/admin.js`), slug is a host **label** (D10) | `lib/admin/platform.sql` |
| Per-tenant **export** | **implemented** — streaming server-side cursor, one repeatable-read snapshot, emits the covered-table list before any row | `lib/admin/platform-store.js:386` `exportTenant` |
| Per-tenant **import** | **does not exist**, anywhere | grep of `lib/admin/`, `bin/`, `tools/` on `crm-seam` — no importer and no Mongo→PostgreSQL loader. **Corrected by review 2026-09-15:** the "no `mongoexport`/`mongodump` consumer outside `node_modules`" half of this cell did **not** reproduce. `tools/rehearse-database-upgrade.py:76` shells out to `mongodump`. It is a Mongo→Mongo 5→6→7→8 upgrade and backup-restore *rollback* rehearsal, not a loader, so the row's verdict stands — but the grep as published was wrong, and that harness is prior art for §8.3. |
| A Mongo→PG loader | **does not exist** | same grep |

So the load half of this migration is unwritten code, and four of the ten collections have no
table to load into. That is not a reason to postpone the plan — the plan is what says which of
those gaps are *blocking* and which are merely *absent*, and §3 is where that distinction is made.

**Three write methods on the PostgreSQL adapter throw by name**: `insertMany`, `updateMany` and
`replaceFiltered` are `unimplemented(...)` in `lib/api3/storage/pgCollection/index.js:308-318`.
A loader that goes through the seam therefore cannot bulk-insert; it has `replaceOne` (which does
upsert) and `bulkUpsert` (see BF-21, §3.2), one statement per document.

---

## 2. The data mapping, collection by collection

### 2.1 The rule, and why it is one rule

Every table has the same shape, and the shape is the whole argument:

```sql
tenant_id  uuid   NOT NULL,     -- D2's discriminator; leads the table and every index
doc        jsonb  NOT NULL,     -- THE RECORD
"<indexed field>"  <type> GENERATED ALWAYS AS (…) STORED,   -- an index accelerator, nothing else
PRIMARY KEY (tenant_id, "_id")
```

Three properties of that shape are load-bearing for a migration and each one is stated in the
emitted header rather than assumed:

1. **The document is the record.** Dropping every generated column and re-adding it must not
   change a single answer. A migration that produces the right columns and the wrong `doc` has
   produced nothing.
2. **The generated columns are `CASE WHEN jsonb_typeof(…) = '<kind>' THEN … END`, not bare
   casts.** A value of the wrong type leaves the column SQL NULL instead of raising on INSERT.
   This is what stops a single dirty stored value from turning a migration load into an ingest
   outage — and it is also, per BF-19, what makes `ORDER BY` on that column wrong (§3.1).
3. **The primary key is `(tenant_id, "_id")`, scoped to the tenant on purpose.** Two tenants
   migrated from two different self-hosted deployments can legitimately carry the same `_id`; a
   global unique constraint would make the second one unimportable. For a migration this is the
   difference between "we can onboard anybody" and "we can onboard the first person who asks".

**The tenant discriminator does not come from the source data.** `tenant_id` is minted by the
admin plane when the tenant is created — `crypto.randomUUID()` in
`lib/admin/platform-store.js:242` `createTenant`, reached through the `bin/admin.js` entrypoint,
which is itself 79 lines and holds none of the logic — and is bound per transaction with
`set_config('app.current_tenant_id', …, is_local => true)`. A loader supplies it from the
provisioning step, never from a field in a document. `slug` is a host **label** (D10) — `foo`,
not `foo.example.org` — and is not stored on any document row.

### 2.2 Per collection

Counts below come from re-running `PYTHONPATH=tools python3 -m nsschema.emit.postgres_emit
--report` on 2026-09-15. Census figures come from `reports/schema-census/*.census.json`
(11 pseudonymous sites, two collection passes, REST-derived JSON). **The census document counts
here span both snapshots (`2026-04-01` and `2026-04-26`); the sizing table in §4.1 counts the
`2026-04-01` snapshot only.** That is why `entries` is 896,589 documents in this section and
649,840 in that one — two denominators, not a contradiction.

#### `entries` — the only collection that exists end-to-end

9 generated columns, 9 indexes, **0 flagged**.

| column | SQL type | jsonb guard | note |
|---|---|---|---|
| `_id` | `text` NOT NULL | `= 'string'` | half the PK. A numeric `_id` **cannot be stored at all** — the row is refused. |
| `date` | `numeric` | `= 'number'` | `numeric`, not `bigint`, because 61.5 % of the corpus carries a fractional epoch and `bigint` would *error* on a fractional bound where `numeric` merely fails to match. **Provenance:** the 61.5 % is the emitter's own comment (`tools/nsschema/emit/postgres_emit.py:97`), not a measurement made for this document; re-derived during review from `reports/schema-census/entries.census.json` — 551,257 fractional of 896,589 values = 61.48 % |
| `type`, `dateString`, `sysTime`, `identifier`, `created_at` | `text` | `= 'string'` | `dateString`/`sysTime`/`created_at` are `datelike` in the manifest — range predicates on them are **lexicographic**, chronological only while every writer emits constant-width UTC ISO |
| `sgv`, `mbg` | `numeric` | `= 'number'` | a string `"120"` leaves the column NULL |

Everything else in the document — 32 model nodes, 19 observed census paths over 896,589
documents — stays in `doc` and is reachable only through the jsonb path. That is correct and not
a gap.

#### `treatments` — 13 columns, 14 indexes, **2 flagged**

Columns: `_id`, `created_at`, `eventType`, `insulin`, `carbs`, `glucose`, `enteredBy`, `notes`,
`percent`, `absolute`, `duration`, `identifier`, `date`.

MongoDB declares 15 indexes on `treatments`. The emitter emits **14** and flags **2**: one index
does not survive at all, and one survives in a weaker form. Both matter for migration.
(*Corrected by review 2026-09-15*: this paragraph previously read "two … do not survive", which
contradicts the bullet below it and the emitter's own reconciliation line, re-run today —
`15 → 14, 1 dropped: boluscalc.foods._id`.)

* **`boluscalc.foods._id` — MULTIKEY, dropped entirely.** No column, no index. A generated column
  cannot reproduce MongoDB's multikey semantics: `doc #>> '{boluscalc,foods,_id}'` is NULL on an
  array, not one value per element. The live query `?find[boluscalc.foods._id]=…` is issued by
  `lib/report/reportclient.js:294`, so this is a **capability a migrated tenant loses**, not a
  vestige. It comes back with D11's decomposition and not before.
* **`NSCLIENT_ID` — AMBIGUOUS**, observed as both number and string, so no typed column. The
  index is still emitted, over the raw jsonb path. `NSCLIENT_ID` is the websocket write path's
  **sole** deduplication key when present, so its behaviour after migration is worth a probe of
  its own — check **C2** (§6) with `NSCLIENT_ID` predicates in the probe set. (*Corrected in
  review*: this pointed at "§6.4", which does not exist in this document.)

65 model nodes; 41 observed census paths over 369,419 documents.

#### `devicestatus` — 4 columns, 3 indexes, **1 flagged** (D11)

Columns: `_id`, `created_at`, `identifier`, `date`. `NSCLIENT_ID` is AMBIGUOUS, so its index is
over the jsonb path.

**D11 governs this and the 182-node question is retired, not answered.** The model holds 184
descendant nodes (measured by walking `specs/nsschema/devicestatus.model.json`), of which 182 are
spec- or census-derived and two — `NSCLIENT_ID` and `date` — are code-supplemented; 182 is the
figure the emitter's own comment uses. The census observed 166 distinct paths over 702,254
documents. **None of those 180 non-indexed nodes gets a column.** Choosing which of them deserve
one would be building half of a design that is going somewhere else: the real direction is
**decomposition into normalised time series declared by registered controller descriptions**
(`tools/nsschema/decompose.py` measures whether a granular-primitive model can express the
corpus; Nocturne's V4 `TreatmentDecomposer` is the built reference). A migration that widened
this table would have to be migrated again.

For sizing: `devicestatus` is **75 % of the bytes** in the corpus snapshot and 1,725 bytes per
document (§4.1). It is the collection the migration schedule is actually about.

#### `profile` — 3 columns, 4 indexes, **1 flagged**

Columns: `_id`, `startDate`, `created_at`; `NSCLIENT_ID` AMBIGUOUS. 73 model nodes, 66 observed
paths over 202 documents across 11 sites — a *tiny* collection with a *large* schema, most of it
inside the nested `store` object, all of which stays in jsonb.

`profile` is the collection whose correctness matters most per byte: it carries basal rates,
insulin sensitivity and carb ratios. A wrong profile document is not a display bug.

#### `food`, `activity`, `settings`, `auth_subjects`, `auth_roles`, `status` — **no table yet**

`food` and `activity` are the two with real migration content. Both have models (T2.2) **and**
index declarations in `specs/nsschema/server-indexes.json`; what is missing is the emitter's
hand-transcribed `INDEXED_FIELDS` entry (see Correction 2, §9). Predicted shape, from the models:

* `activity` — `_id` `text`, `created_at` `text` (date-time). One index. Mechanical.
* `food` — `_id` `text`, `type` `text`. **`position` (number, string) and `hidden` (boolean,
  string) are both AMBIGUOUS and would be flagged, not columned.** That is the same two-spellings
  problem BF-16 fixed above the seam: `lib/server/food.js` compared `hidden` against the literal
  string `'false'`; `bf/food` changes it to `{hidden: {$nin: [true, 'true']}}`. On PostgreSQL,
  with no `hidden` column, that predicate runs against the jsonb path — so the fix and the DDL
  agree by accident rather than by design, and it should be checked rather than assumed.

`auth_subjects` **must not be migrated as data**. Its model carries an explicit
`credential_warning`: `accessToken` is a bearer credential, derived at read time but persisted in
plaintext by an ordinary subject edit through the admin UI. Moving a tenant means **reissuing
credentials**, not copying them (§5.4). `settings` has no writer in `cgm-remote-monitor` at all
and `status` is a response shape, not a collection.

---

## 3. The known divergences, and which ones block

These are open register entries. They are not incidental bugs: **each one is a mechanism by
which a migration completes successfully and produces different answers afterwards.** All five
were measured against a real `mongod` and a real PostgreSQL, not reasoned about.

**Coverage of this enumeration, stated because a partial list that does not say so is worse than
no list (added in review).** These five are the **storage-seam divergence** entries — the ones
where the two backends answer the same question differently. They are not every open register
entry that touches a migrating tenant. Three more are relevant and are deliberately out of scope
here, with the reason:

* **BF-24 and BF-25**, both `high`, both open — tenant authentication and the tenant claim check.
  A migrating tenant lands on exactly that path. They are not divergences, so they are not in this
  section; they are prerequisites for hosting anybody, and D13/D14 (§5.4) are the decisions that
  answer them. **A migration cannot be scheduled before they are closed**, and this document does
  not otherwise say so.
* **BF-13**, `high`, **fixed** on `bf/reads` `399dc283` — the missing `_id` tiebreak. It is closed
  above the seam but §4.5 and §3.1 both depend on ordering being deterministic, so the fix has to
  be in the tree the migration runs against; it is not automatically there, because no `bf/*`
  branch has been merged.
* **BF-04**, `high`, status `fixed-in-seam` — the v1 filter pass-through with no operator
  allowlist. It ships to every current operator and appears in no open list because of that
  status. It is a source-side exposure, not a migration divergence, but a hosting operator reading
  this document should know it is there.

### 3.1 BF-19 — `ORDER BY` reads the generated column · **high** · open · **BLOCKING**

`pgCollection/sql.js` `orderBy` (lines 100-110) picks between two branches:

```js
const ref = Object.prototype.hasOwnProperty.call(columnTypes, field)
  ? `"${field}"`
  : `doc #> '{${field.split('.').join(',')}}'`;
```

They do not order the same values the same way, and neither matches MongoDB. **I reproduced this
independently** on a fixture of my own (8 synthetic `entries`, one `sgv` stored as the string
`"160"`, one explicit `null`, one absent), against `mongo:7` and `postgres:16-alpine` in throwaway
containers I created and removed:

```
mongod       ffffff 111111 aaaaaa bbbbbb cccccc dddddd 222222 eeeeee
pg column    eeeeee 111111 ffffff aaaaaa bbbbbb cccccc dddddd 222222
pg jsonb     111111 ffffff eeeeee aaaaaa bbbbbb cccccc dddddd 222222
```

Three orders where there should be one. The string-valued row (`eeeeee`) sorts **last** on
MongoDB — BSON orders Number before String — **first** on the column branch, because the type
guard makes it SQL NULL and it joins the missing-and-null bucket, and **third** on the jsonb
branch, because jsonb's own cross-type order is Null < String < Number. Two harnesses reached this
before me from two other directions (`tools/qc/pg-backend-arm.js` §6a and
`tools/qc/typeguard-arm.js`); this is a third fixture and a third agreement.

*Read the rows, not the columns.* **Added by review 2026-09-15:** on the column branch the string
row, the explicit null and the absent row are **all** SQL `NULL`, and PostgreSQL does not define
an order within a tie — that is BF-13, the missing `_id` tiebreak this document cites in §4.5. So
the relative order of those three cells is not reproducible and should not be quoted as if it
were. What is reproducible, and is the defect, is that the three orders **differ from each
other** and that the string row changes bucket depending on whether the field has a column.

**Why it blocks a migration specifically.** Client-reachable via v3 `?sort=<field>`, which
`parseSort` puts first in the chain unvalidated. But worse: **the migration's own verification
depends on ordering.** Any check that compares "the first N documents from each side" — which is
how a reasonable person writes a spot check — is comparing two different sets and will report
agreement or disagreement for reasons that have nothing to do with whether the data moved
correctly. BF-19 does not just break the product after migration; it breaks the instrument.

### 3.2 BF-21 — `bulkUpsert` ignores the mode every caller asks for · **high** · open · **BLOCKING, and it is a migration-integrity problem**

`mongoCollection/modify.js` has `bulkUpsert(col, ops, options)` with `mode` defaulting to
`'replace'`. `pgCollection/index.js:286` has **`bulkUpsert(ops)`** — no options parameter — and
always calls `write(..., 'merge')`. Its own doc comment, in the block immediately above the
signature (`index.js:272-285`), reads:

> `mode` carries the same difference it does on the other backend and **must not be defaulted
> away**

and then defaults it away. The behaviour — a stored document carrying `stale: 'was-here'`,
upserted with a document that does not carry it, keeps `stale` on PostgreSQL and loses it on
MongoDB — was measured by the write-path report. **The tally `23 agree / 4 differ / 0 vacuous` is
quoted from BF-21's evidence line (`tools/qc/write-arm.js`); it was not re-run for this
document.** The caller census below *was* measured here.

**The caller census, measured 2026-09-15** (`grep -rn 'bulkUpsert(' lib/server/*.js
lib/authorization/*.js` on `crm-seam` 81a1f6ce, reading two lines past each call): there are
**nine** call sites in six files, and **eight** pass `{mode: 'replace'}` —
`lib/server/activity.js:61` and `:102`, `lib/server/food.js:64` and `:122`,
`lib/server/treatments.js:31` and `:120`, `lib/server/profile.js:101`, and
`lib/authorization/storage.js:143`. Three things follow, and the register does not say any of
them:

* **The blast radius includes `profile` and `auth_subjects`.** `profile` is the collection this
  document calls the one whose correctness matters most per byte — basal rates, insulin
  sensitivity, carb ratios — and it is written through a `'replace'` `bulkUpsert` that
  PostgreSQL merges. `lib/authorization/storage.js:143` is the subject/role writer, which is
  credential-adjacent (§5.4).
* **The ninth caller asks for `merge` on purpose, and PostgreSQL is accidentally right for it
  alone.** `lib/server/entries.js:168` passes `{mode: 'merge'}` above a comment that says
  `mode:'merge'` is *not* interchangeable with the `'replace'` the other v1 modules use, because
  that path was `updateOne`+`$set` and a wholesale replace would delete stored fields absent from
  the incoming entry. So the shipping code distinguishes the two modes deliberately, in writing.
* **Therefore "make PostgreSQL always merge" is not available as a shortcut fix**, and neither is
  "always replace" — `entries.js` would start deleting fields. The mode has to be threaded. That
  the one caller PostgreSQL honours is the one that never needed the argument is why this defect
  survived: the collection with by far the most write traffic is the collection where the bug is
  invisible.

The register's own phrasing — "the `{mode:'replace'}` **every** shipping caller sends" — is
therefore inaccurate in a way that matters, because it implies a uniform intent that would make
"always replace" a safe fix. See Correction 7.

**This is the one on the list that corrupts a migration rather than mis-answering a query.**
Three reasons, and the third is the one that is not in the register entry:

1. The consequence is an **unremovable field**. Any key a client deletes stays in the PostgreSQL
   row for good.
2. The two backends **drift apart with every write**, so a dual-write cutover (§4.5) does not
   converge — it diverges monotonically, and the longer it runs the worse it gets. Dual-write is
   the cutover strategy that BF-21 specifically forbids.
3. **A re-runnable loader is the obvious design, and BF-21 makes re-running unsafe.** A migration
   that can be resumed after a partial failure has to be idempotent, and the idiomatic way to be
   idempotent is upsert-by-`_id`. On PostgreSQL that silently merges: if a document was corrected
   between two loader passes — deduplicated, redacted, or had a bad field stripped — the second
   pass *adds to* the first rather than replacing it, and the result is a document that existed
   in neither source state.

*Correction to the register entry's proposed fix*: it says to "implement `'replace'`". Replace is
**already implemented** — `write(ast, doc, 'replace')` emits
`$N::jsonb || jsonb_build_object('_id', doc -> '_id')` and `replaceOne` uses it. The fix is to
thread the existing `mode` through the signature, or to refuse a mode that cannot be honoured. It
is smaller than the entry implies, which is an argument for doing it before the migration rather
than after.

### 3.3 BF-22 — a dotted field stores two different documents · **medium** · open · **BLOCKING for the transform, not for the load**

`updateOne(identifier, {'nested.leaf': 7})` is `$set` on MongoDB, where a dot is a **path**:
`{"nested": {"leaf": 7}}`. The PostgreSQL merge (`doc || $N::jsonb`) treats it as a **literal
key**: `{"nested.leaf": 7}`. The PostgreSQL document then holds a key that no path lookup will
ever find — not `doc #> '{nested,leaf}'`, not a generated column, not a client walking the object.

For migration this cuts twice:

* **On the write path after cutover**, reachable through `PATCH /api/v3/<collection>/<identifier>`
  (`lib/api3/generic/patch/operation.js:85` passes the client's body to `updateOne`, after adding
  `srvModified`/`modifiedBy` and normalising treatment duration). Every PATCH with a dotted key
  writes an unreachable key.

  **The register bounds this claim and the bound can now be lifted.** BF-22's entry says the
  reachability is "subject to a validation layer that was not audited". Audited during review,
  2026-09-15, on `crm-seam` 81a1f6ce: the only two filters between the body and `updateOne` are
  `lib/api3/shared/writePurifier.js` → `lib/server/purifier.js` `purifyObject`, which sanitises
  string **values** and never touches a key (lines 165-191), and
  `lib/api3/generic/update/validate.js`, which checks an immutable-field list and then
  `validateCommon`'s `date` / `utcOffset` / `app` type tests — all three skipped when the field is
  absent from a patch. **Nothing inspects key names.** A dotted key reaches `updateOne` unaltered.
  This should go back to the register as a correction (§9, item 8).
* **On the transform**, and this is the part that is not in the entry: if the *source* MongoDB
  document already contains a literal dotted key — which MongoDB permits in stored documents even
  where it forbids it in `$set` — then a faithful jsonb load reproduces it, and a
  round-trip-through-`$set` load does not. The two loaders produce different documents from the
  same source. **A migration must decide which one it is doing and say so**, because "faithful"
  and "what the application would have written" are not the same document here.

### 3.4 BF-20 — a `Date`-valued filter bound silently inverts · low · open · **not blocking, but it is the shape of the real hazard**

`scalarize()` (`pgCollection/sql.js:27`) turns a JavaScript `Date` into an ISO string before it
reaches the adapter. A `gte <Date>` bound against an ISO-string `created_at` matches **nothing**
on MongoDB (BSON compares only within a type) and **everything in range** on PostgreSQL (both
sides are now text). No shipping caller passes a `Date`; every one emits epoch numbers or ISO
strings. Recorded because the adapter is a published interface.

**The migration-relevant twin is on the document side, and it is not low.** `scalarizeDoc` applies
the same conversion to stored documents: a BSON `Date` in a document becomes an ISO string in
`doc`. So a stored `dateString` that is a **BSON Date** on MongoDB becomes a **string** on
PostgreSQL. That is probably the behaviour you want — but it is a **type change to stored data**,
performed silently, and **the corpus cannot tell you how often it happens**. The census is built
from Nightscout REST responses (`tools/nsschema/corpus.py`: "the Nightscout REST response
verbatim"), which have already serialised BSON to JSON. Confirmed structurally: **zero** census
paths in `entries`, `treatments`, `devicestatus` or `profile` contain a `$` character, so no
extended-JSON wrapper survives into the evidence. **The corpus is blind to BSON types.** That is
not evidence that BSON Dates are absent from real databases; it is evidence that this programme
has never looked. **C4** (§6) is the check that looks — the cross-reference in this paragraph
previously read "§6.2", which is not a section this document has; corrected in review.

**And `Date` is the easy case.** §4.3's correction block measures what `scalarizeDoc` does to the
*other* BSON types: it converts only `ObjectId` and `Date`, and turns `Decimal128`, `Binary`,
`Timestamp` and an out-of-range `Long` into jsonb **objects**, which null the generated column
without erroring. So BF-20's document-side twin is wider than a type change — for those types it
is a value the migrated store cannot answer a predicate about at all. C4 is what sizes it.

### 3.5 BF-23 — the duplicate-key error class crosses the seam · low · open · **not blocking**

`MongoServerError` / `E11000` on one side, `DatabaseError` / `duplicate key value violates unique
constraint` on the other. Both refuse the duplicate, which is what matters for correctness. `grep`
for `11000`, `E11000` and `MongoServerError` across `lib/` finds no caller branching on it.
Relevant to a migration only in that **a loader is exactly the kind of caller that would branch on
it** — "already loaded, skip" is the natural idempotence idiom — so a loader must not, and should
test `rowCount`/`upsertedCount` instead.

### 3.6 The verdict, stated plainly

| entry | fix before any real data moves? | why |
|---|---|---|
| **BF-21** | **Yes, unconditionally** | corrupts stored data on every write; makes a resumable loader unsafe; makes dual-write divergent by construction |
| **BF-19** | **Yes** | breaks the migration's own verification instrument, not only the product |
| **BF-22** | **Yes, at least as a decision** | the transform must state which document it produces; the PATCH half can follow |
| BF-20 | No — but **C4**'s type census must run first | the document-side twin is unmeasured, not absent, and §4.3's correction block shows the recommended transform mishandles four more BSON types |
| BF-23 | No | no caller branches on it; constrain the loader instead |

Three of five block. Two are small and one is not, and the original wording here said "none is
large", which review does not support. BF-21 is threading an argument that already has an
implementation behind it. BF-22 is a written-down choice plus a guard. **BF-19 is not settled**:
`nightscout-seam-ordering-translation.md` §3 is headed "open, and harder than it looks", and what
it carries is a *recommendation* — option O2, restrict sortable fields to declared single-typed
ones — conditional on a corpus measurement (§3.2). Adopting O2 is also a **client-visible
restriction**: a v3 request that sorts on an undeclared field stops being answered and starts
being rejected. For a migrating tenant that is a behaviour change to disclose, not a silent
internal fix, and it belongs in §7.2's list once the maintainer picks an option.

**One more that is not on the brief's list and belongs on it.** The register and three research
reports pin BF-19's and BF-21's exposure to "**T2.6**". The execution plan defines no T2.6 — Phase
2 stops at T2.5 plus T2.1a. A deadline attached to a task that does not exist cannot be scheduled,
cannot be checked, and will be discovered by whoever loads `treatments` onto PostgreSQL. See
Correction 1.

---

## 4. Migration mechanics

### 4.1 Sizing, measured

From the 2026-04-01 snapshot (11 pseudonymous sites; JSON file bytes ÷ document count, no
document content read):

| collection | documents | JSON bytes | bytes/doc | share of bytes |
|---|---|---|---|---|
| `entries` | 649,840 | 175.9 MB | 271 | 15 % |
| `treatments` | 277,690 | 113.2 MB | 408 | 10 % |
| `devicestatus` | 514,259 | 887.1 MB | 1,725 | **75 %** |

Per site, that is roughly 59,000 entries / 25,000 treatments / 47,000 devicestatus and **~107 MB
of JSON**. **These are lower bounds.** The corpus is a bounded REST read over eleven sites that
agreed to be sampled, not a full database dump, and a long-running deployment will be larger by an
unknown factor. Quote the *ordering* — devicestatus dominates by bytes, entries by count — rather
than the absolutes, per the programme's standing rule.

The practical consequence: **`devicestatus` decides the migration window**, and `devicestatus`
also has the fewest columns (four) and the largest jsonb bodies. If a schedule needs to fit inside
a window, the lever is devicestatus retention, not parallelism.

### 4.2 Export

Source is the tenant's MongoDB. Two candidate readers, and the choice is not cosmetic:

**(a) Read through the driver, in `_id` order, with an explicit resume point.** Preferred.
`find({}).sort({_id: 1})` with a `_id > <last>` cursor is resumable, does not depend on a
transaction MongoDB cannot open on a standalone `mongod` (`lib/storage/tenant-scope.js` documents
exactly this: plenty of self-hosters run standalone, which cannot start a replica set, so the
Mongo adapter has no transactions), and lets the transform run streaming.

**(b) `mongoexport` / `mongodump`.** Available and familiar, and **the encoding is a trap**. See
§4.3.

Whichever is used, the export must **state what it covered** before it is trusted. The hosted
side already does this — `exportTenant` calls `onCollection` with the table list before any row,
because "an export that is truncated by a dropped connection is otherwise indistinguishable from a
complete one". The *inbound* reader needs the same property and does not have it, because it does
not exist yet.

### 4.3 Transform — and the encoding finding

**Measured, 2026-09-15**, on 8 synthetic `entries` documents carrying an `ObjectId`, a BSON
`Date`, a `Long`, a `Double`, a string-valued `sgv`, an explicit `null`, an absent field and a
`Decimal128`; loaded into the emitted `entries` table shape on `postgres:16-alpine`; harness at
`/tmp/…/scratchpad/fidelity.js` (scratchpad, not committed):

| export encoding | rows loaded | load errors | result |
|---|---|---|---|
| relaxed EJSON (`mongoexport` default) | 0 | 8 | `null value in column "_id" of relation "entries" violates not-null constraint` |
| canonical EJSON (`--jsonFormat=canonical`) | 0 | 8 | same |
| `scalarizeDoc` (the seam's own write path) | **8** | 0 | clean |
| relaxed EJSON **with `_id` rewritten to a plain hex string** | **8** | **0** | **loads clean and silently corrupts** |

The first three rows are the good news: **the emitted DDL fails closed on an EJSON-encoded load**,
because `_id` is `text NOT NULL` guarded by `jsonb_typeof = 'string'` and EJSON writes
`{"$oid": "…"}`, which is an object. Every row was attempted individually in the harness, which is
why the error count is 8 rather than 1; a loader batching inside one transaction stops on the
first row instead. Either way it fails loudly, which is the point.

**The fourth row is the finding.** A site whose `_id` is *already* a 24-hex string — which API v1
permits a client to supply, and which is therefore not hypothetical — exports with a plain-string
`_id`, so the row loads. Every *other* EJSON wrapper then passes silently: one document's
`dateString` landed in `doc` as `{"$date": "2025-09-15T01:38:20Z"}`, the `dateString` generated
column went SQL NULL for that row, **and nothing errored**. That document is now invisible to
every `dateString` predicate and sorts into the missing bucket, with a success status on the load
and a plausible-looking row count.

**Therefore: the transform is `scalarizeDoc`, or something that provably agrees with it.**
`lib/api3/storage/pgCollection/sql.js:51`. It is the function the hosted service's own write path
uses, so a migrated document and a natively-written document are the same document. Its rules:
`ObjectId → 24-hex string` (which is what every v1 client has always seen on the wire),
`Date → ISO string`, recursively through objects and arrays. **`_id` is not stripped on insert** —
the loader supplies it (`pgCollection/index.js:188-197` keeps a supplied `_id` and mints one only
when it is absent), because it is half the primary key and it is what the tenant's clients already
hold.

#### Correction, found in review 2026-09-15: `scalarizeDoc` is not a BSON transform. It handles two types.

**The recommendation above is right about *which function* and wrong about *what it covers*, and
the table's `clean` verdict cannot be read as `faithful`.** Measured during review by calling the
shipping `sql.scalarizeDoc` directly in `externals/work/crm-seam` (bson 7.3.2, mongodb 7.6.0,
Node in that worktree), on one document holding one value of each BSON type:

| value handed in | what `scalarizeDoc` returns | `jsonb_typeof` of the stored value |
|---|---|---|
| `ObjectId` | `"6aa9f9ac…"` (24-hex) | `string` ✔ |
| `Date` | `"2025-09-15T01:38:20.000Z"` | `string` ✔ |
| `Long` | `{"high":409,"low":-1414615903,"unsigned":false}` | **`object`** ✘ |
| `Double` | `{"value":1.5}` | **`object`** ✘ |
| `Decimal128` | `{"bytes":{"0":210,"1":4,…}}` | **`object`** ✘ |
| `Binary` | `{"buffer":{"0":171},"sub_type":0,"position":1}` | **`object`** ✘ |
| `Int32` | `{"value":7}` | **`object`** ✘ |
| `Timestamp` | `{"high":1,"low":2,"unsigned":true}` | **`object`** ✘ |

The rule is one line of the source: `scalarize()` converts a value only if it has a
`toHexString()` method or `instanceof Date`. Everything else that is an object is **recursed into
as an ordinary object**, so the BSON wrapper's internal representation is what lands in `doc`.

**That is the same silent corruption as row 4 of the table above, inside the recommended
transform.** A `date` arriving as a `Long` loads with no error, leaves the `date` generated column
SQL `NULL` because `jsonb_typeof(…) = 'object'`, and the document becomes invisible to every
`date` predicate and sorts into the missing bucket — success status, plausible row count.
The refusal list below as originally written **does not catch it**: `{"high":…,"low":…}` contains
no `$`.

*How much of this is reachable.* With the Node driver's defaults (`promoteLongs`/`promoteValues`
both true, measured on bson 7.3.2 by round-tripping a serialised document): a `Long` inside 2^53
and a `Double` come back as plain JS numbers and are safe. **`Decimal128`, `Binary`, `Timestamp`
and any `Long` outside 2^53 come back as BSON objects and are not.** A reader that sets
`promoteLongs: false` or `promoteValues: false` — which is exactly what a fidelity-minded loader
author would reach for — makes *every* numeric field unsafe.

*What this means for the table above.* `clean` in the `scalarizeDoc` row means **0 load errors**,
which is the whole point of the section: 0 errors is what silent corruption looks like. A fixture
carrying a `Long`, a `Double` and a `Decimal128` cannot have round-tripped them through
`scalarizeDoc`, so that row does not support the conclusion it was offered for. The conclusion
survives in a narrower form: *`scalarizeDoc` is the right agreement target because it is what the
hosted write path does, and the loader must extend it to the BSON types `scalarizeDoc` does not
handle, with the extension reviewed as a data decision rather than written as a default.*

**This is a defect in shipping code, not only in a migration plan, and D4 forbids deferring it to
"Postgres will replace that".** It is described in this reviewer's return value as a proposed
register entry with **no id allocated** (rule 3); the reconciliation agent allocates one.

The transform must also **refuse**, not coerce, on:

* a non-string `_id` (the row cannot be stored; the DDL already refuses, and the loader should say
  which document rather than letting PostgreSQL say which constraint);
* any remaining `$`-prefixed top-level key after transform, which means an EJSON wrapper survived;
* **any value that is still a JSON object where the model declares a scalar** — this is the check
  that catches the `scalarizeDoc` gap above, and it is the one the original list was missing.
  `jsonb_typeof` is already the test the DDL uses, so the loader can ask the same question before
  the row is written instead of after;
* **any value carrying a BSON wrapper's shape** (`_bsontype` on the JavaScript object, before
  serialisation) — cheaper than the previous check and it names the cause rather than the symptom;
* a literal dotted key, which is BF-22's transform half and needs a decision, not a default.

### 4.4 Load

Provision first: the admin plane creates the tenant and mints `tenant_id`
(`lib/admin/platform-store.js:242`, reached through the `bin/admin.js` entrypoint). The slug is a
host label (D10) and is validated in two places on purpose — a `CHECK` constraint at
`lib/admin/platform.sql:37` and `requireSlug` in **`lib/admin/slug.js`** — because the admin plane
is cross-tenant by construction and cannot be protected by RLS. (*Corrected in review*: this
paragraph named `bin/admin.js` as the second enforcement point. That file is 79 lines and does not
contain the string `slug`; the shipping comments use "bin/admin.js" as shorthand for the admin
plane, and this programme has been bitten three times by a stale file reference, so the real path
is named here.)

Then, per collection, in one transaction per batch with the tenant bound:

```
SET LOCAL app.current_tenant_id = '<uuid>';
INSERT INTO <collection> (tenant_id, doc) VALUES ($1, $2::jsonb)   -- batched
```

Notes that are not optional:

* **Connect as a role that is `NOSUPERUSER NOBYPASSRLS`.** RLS is silently not enforced for a
  superuser; a load that ran as one has verified none of its isolation. T2.5 records that an
  earlier measurement in this programme nearly published two false findings for exactly this
  reason.
* **Do not go through `bulkUpsert`** until BF-21 is fixed (§3.2). Until then the loader's own
  idempotence is a merge.
* **`insertMany` throws by name** on the PostgreSQL adapter, so a seam-mediated loader issues one
  statement per document, or goes below the seam and issues `COPY`/multi-row `INSERT` directly.
  Going below the seam is defensible for a bulk load — the seam exists so *application* callers
  do not see driver objects — but it means the loader is a second writer of the storage shape and
  must be kept in step with the emitted DDL. `make schema-vendor-drift` is the precedent for how
  that is policed.
* **Generated columns are computed by PostgreSQL**, not supplied. A loader that writes them is
  rejected, which is the correct failure.

### 4.5 Verify — differential, not counted

**Row counts are worthless here and it is worth being blunt about why.** Every divergence in §3
returns HTTP 200 with a wrong answer and a right count. BF-19 reorders, BF-21 keeps a field,
BF-22 relocates a key, BF-20 changes a type, the EJSON case in §4.3 nulls a column. Not one of
them changes how many rows exist.

The programme already has the instrument. Reuse it as follows.

| harness | what it already does | how the migration uses it |
|---|---|---|
| `tools/qc/three-arm.js` | randomised filter ASTs across **mingo / real mongod / real PostgreSQL**, all three pairwise comparisons; validates the **oracle** as well as the claim | point `FILTER_MODULE` at the shipping `lib/storage/filter.js`, `MONGO_URL` at the **source tenant's** database and `PG_URL` at the **loaded tenant** (bound). Randomised filters over the tenant's *real* shapes is the only cheap way to reach predicates nobody wrote a probe for. Run `WITH_RE=1` only after `re-arms.js` has said which regex constructs are comparable — mingo, PCRE2 and POSIX ARE are three languages. |
| `tools/qc/pg-backend-arm.js` | the same questions against the **shipping** modules and the **shipping emitted DDL**, through `store.storageCollection(...).findFiltered(ast, opts)`; sections 1-6, non-vacuity built in | the primary migration acceptance harness. Its **§6a** is BF-19's detector — it puts identical values in `sgv` (which has a generated column) and `noise` (which does not) and compares the two orders against `mongod`, so the only variable is the accelerator. Its **§1** (filter classes A-D) is the answer differential, and its **§3** is a *different* ordering defect, BF-13's missing `_id` tiebreak — run it too, because a migration that reorders ties is as unverifiable as one that reorders values. Both arms are constructed by their own store, so a divergence it reports is one a caller above the seam would see. |
| `tools/qc/order-arm.js` + `tools/qc/typeguard-arm.js` | ordering and pagination; the fifth (shipped) `ORDER BY` translation | run per sortable field the tenant's clients actually use, **before** cutover. If BF-19 is unfixed these will be red and that is the gate, not a note. |
| `tools/qc/shape-arm.js` | `limit` and `projection` | `limit: 0` is an unbounded read on one backend and an empty one on the other — v1's `?count=` reaches it. Run it because reports paginate. |
| `tools/qc/write-arm.js` | the write path: return value **and** stored state, per probe | run it against the loaded tenant before opening writes. It is the harness that found BF-21, BF-22 and BF-23, and it is the one that will notice if the loader itself wrote something the application would not have. |
| `tools/qc/readoptions-arm.js` | `batchSize` and materialisation | lowest priority for correctness; relevant because the PostgreSQL read path materialises and a migrated tenant's largest report is the first thing to find that out. |
| `tools/seam/validate.js` | mingo ≡ PostgreSQL over randomised filters | the regression check; cheaper than `three-arm.js` and does **not** substitute for it, because a mingo/PostgreSQL agreement is evidence about the AST, not about MongoDB. |

Every one of these compares **answers**. That is the property that makes them the right tool and
a count the wrong one.

---

## 5. Cutover

### 5.1 The two candidates

**Read-only window.** Freeze writes at the source, drain in-flight uploads, export, transform,
load, verify, flip DNS/routing to the hosted tenant, open writes there.

**Dual-write.** Run both stores, write to both, backfill history behind the live edge, compare,
cut reads over when they agree.

### 5.2 Recommendation: **read-only window**, and dual-write should not be attempted on this code

The argument is not about effort. It is that **BF-21 makes dual-write divergent by construction**.
A dual-write scheme's entire premise is that the two stores converge; with `bulkUpsert` silently
merging on PostgreSQL, a field deleted on MongoDB survives on PostgreSQL, forever, and the
divergence is monotonic — every write widens it. The comparison step that is supposed to say "safe
to cut over" would report a growing set of differences it cannot attribute, and the natural
response to that report is to tune the comparator rather than to fix the backend. This programme
has a name for that shape.

Even with BF-21 fixed, dual-write needs one more thing this system does not have: an ordering
guarantee across two stores for a client that writes the same document twice in quick succession.
`lib/storage/tenant-scope.js` says plainly that the interface **does not promise atomicity across
operations on both backends** and will not until something says so explicitly. Dual-write is that
something, and it is not written.

The read-only window is also the only option that is honest to the person whose data it is: there
is a stated moment when their site is not accepting new data, and it is on a calendar, rather than
an indefinite period during which their data is in two places and nobody can say which one is
right.

### 5.3 What the window actually costs, and what a tenant's clients do in it

Sizing from §4.1: ~107 MB of JSON and ~131,000 documents for an **average** corpus site
(the three sized collections' totals ÷ 11 — an arithmetic mean; the census reports no per-site
median, and "median" is what this sentence said before review), dominated by `devicestatus`.
The export and load are both streaming and neither is obviously the bottleneck;
**the verification is**, because `three-arm.js` and `pg-backend-arm.js` are randomised differentials
and their cost is a choice about how many iterations buy enough confidence. **This has not been
timed end-to-end and I am not going to invent a number** — see Open Question 3.

The cutover can be shortened honestly by splitting it: **bulk-load the cold history days ahead**,
then take a short window for only the tail. That works because the tail is small and because
`_id`-ordered resumption makes "everything since `<_id>`" a cheap query. It requires BF-21 fixed,
because the tail load is an upsert over a store that already has rows.

**What the tenant's clients do during the window** — and this is the part that has to be written
for a non-developer before it is implemented:

* **Uploaders (phone apps, bridges, `nightscout-connect`)** keep collecting locally and retry.
  They will retry into a site that is refusing writes. `nightscout-connect` v0.0.14's backoff is
  the relevant behaviour and it is now bounded: `lib/builder.js` supplies
  `max_interval_ms = expected_data_interval_ms * 6`, so the ceiling is 30 minutes, with `'equal'`
  jitter spreading the delay over [15 min, 30 min]. **The old behaviour was a 256 ms retry with
  jitter forced off** (BF-34), which meant a pool of uploaders hitting a read-only site would have
  retried in lockstep, 586× too fast (585.94× = 150000/256 exactly, at every attempt below the
  ceiling). A migration window is precisely the burst BF-34 was worst at, so **v0.0.14 should be
  in place before any migration window is opened**. **Added in review:** v0.0.14 is prepared
  locally and **has not been released** — the tag and the branch are unpushed, and
  `cgm-remote-monitor`'s `dev` still pins the commit tarball `234d47c8`, which carries the
  debug-logging narrowing but none of the three log-redaction commits. So this prerequisite is a
  release that has to happen first, not a version an operator can install today.
* **Viewers** see data up to the freeze and then nothing new. They should see a message that says
  so, not a stale graph that looks current. A stale graph on a glucose display is a safety problem,
  not a cosmetic one.
* **Alarms** are the thing to be most careful about. Alarms are **off** under `TENANCY_MODE=multi`
  by design (T3.5 withholds emissions outside tenant scope), so **a tenant arriving at the hosted
  service is arriving somewhere alarms do not yet fire.** That is not a migration defect but it is
  a migration *disclosure*, and it belongs in what the tenant agrees to, in plain language, before
  anything moves — see the consent paragraph at the end of §7.2. (*Corrected in review*: this
  pointed at "§7.3", which does not exist.)

### 5.4 Credentials do not migrate

`auth_subjects.accessToken` is a bearer credential. The tenant's root credential is its own under
D13 — there is no deployment-wide secret under `TENANCY_MODE=multi`, on any interface — and D14
gives each tenant its own JWT signing key, resolved before any credential is examined. So
**every token the tenant's clients hold must be reissued**, and every uploader reconfigured. This
is the most visible part of the migration for the person doing it and it is not a data-movement
problem; it is a checklist, and it is the reason the window is a scheduled event rather than a
background job.

---

## 6. Verification that the migration was *correct*

A migration that completes and is wrong is this project's characteristic failure mode. Each check
below is specified with **the break that proves it is not vacuous** — because a check that has
never failed is not yet evidence, and there are two ways it goes vacuous: the corpus never
exercises the property, or the code never distinguishes the branches. Only breaking it tells you
which.

Checks C1-C3 were **run**, on synthetic fixtures, in throwaway containers created and removed for
this document. C4-C7 are **specified, not run**.

### C1 — Canonical document checksum · **run, non-vacuous**

Serialise every document on both sides with recursively sorted keys, apply `scalarizeDoc` to the
MongoDB side, order by `_id`, hash. Equal hashes or the migration is not accepted.

Key sorting is not a detail: jsonb does not preserve key order and the driver does not promise
insertion order, so an unsorted comparator reports a faithful load as a changed one. **My first
version did exactly that** — the control arm came back RED on a correct load, which is a
comparator that cannot go green and is worth as little as one that cannot go red.

Measured, four deliberate breaks, one document altered per break:

| break | C1 |
|---|---|
| control: faithful load | **green** |
| drop one `sgv` value | **RED** |
| shift one `date` by 1 ms | **RED** |
| `sgv` 120 → `"120"` (string) | **RED** |
| explicit `null` → absent | **RED** |

**Its limit, stated because it is easy to over-trust.** C1 hashes the *post-transform* document on
both sides, so it verifies the **load**, not the **transform**. A transform bug is invisible to
it: if `scalarizeDoc` did the wrong thing, C1 compares two copies of the wrong thing and goes
green. C2 and C3 are what cover that, and neither fully does. **§4.3's correction block is a
worked example of exactly this**: a `Decimal128` mangled identically on both sides by
`scalarizeDoc` produces two identical hashes and a green C1. **C4 is the only check in this list
that can see it**, which is why §6.1 puts C4 before the load and not after it.

### C2 — Answer differential · **run, non-vacuous, and weaker than it looks**

Same predicates against both sides through the shipping modules, comparing **answers**. Using the
same four breaks and five hand-written probes:

| break | C2 |
|---|---|
| control: faithful load | green |
| drop one `sgv` value | **RED** (`sgv exists`: mongo=7 pg=6) |
| shift one `date` by 1 ms | **green — missed** |
| `sgv` 120 → `"120"` | **green — missed** |
| explicit `null` → absent | **RED** |

**Two of four missed.** That is the measurement, and it is the argument for the whole section: a
hand-written probe set catches what its author thought of. The 1 ms shift and the type flip were
both invisible because no probe's bound fell between the altered value and its neighbour. This is
why C2 must be **`tools/qc/three-arm.js` and `tools/qc/pg-backend-arm.js` with randomised filters
over the tenant's own document shapes**, not a hand-written list — and why C1 is not optional even
though C2 sounds stronger.

### C3 — Ordering equivalence · **run, currently RED, and that is the gate**

For every field a client can reach through v3 `?sort=`, compare the returned **order** with
`mongod`. Measured in §3.1: column branch ≠ mongod, jsonb branch ≠ mongod, and the two branches ≠
each other. **Non-vacuity is inherent**: the check is already failing on the shipped code, which
is the strongest possible evidence that it can go red. The break that proves it can go *green* is
the interesting one and it is not available until BF-19 is fixed — so C3 is written now and
**re-run as the acceptance test for BF-19's fix**.

### C4 — BSON type census on the source · **specified, not run** · run this before anything else

Read the source database **through the driver** and count, per collection and per path, the BSON
type actually stored. This is the measurement the corpus cannot make (§3.4), and it is the one
that says whether the `scalarizeDoc` transform is a no-op for this tenant or a silent type change
to thousands of documents.

*Non-vacuity*: seed a scratch database with one document per BSON type of interest (`Date`,
`Long`, `Double`, `Decimal128`, `ObjectId` in a non-`_id` position) and confirm the census names
each. A census that reports only `string` and `number` over a corpus that contains a `Date` has
measured the driver's JSON serialiser, not the database — which is exactly the mistake the
REST-derived corpus makes structurally.

### C5 — Field-set closure · **specified, not run** · BF-21's detector

For every `_id`, assert the **key set** of the PostgreSQL document equals the key set of the
MongoDB document — not the values, the keys. This is the check that catches a survived field, and
it is the check that a re-run of an idempotent loader must still pass.

*Non-vacuity*: after a clean load, `updateOne` the same document on both sides through the seam
with a field removed, then re-run the loader's upsert path. With BF-21 unfixed the PostgreSQL
document keeps the key and C5 goes red. **That red is the acceptance criterion for BF-21's fix**,
and it is also the proof that C5 is not vacuous, because it distinguishes the merge branch from
the replace branch in the code rather than in the fixture.

### C6 — Dotted-key audit · **specified, not run** · BF-22's detector

Assert that no migrated document contains a top-level key matching `/\./`, and that every nested
path present on MongoDB resolves on PostgreSQL via `doc #> '{a,b}'`.

*Non-vacuity*: write `{'nested.leaf': 7}` through `updateOne` on both backends and confirm the
audit flags the PostgreSQL row and not the MongoDB one. The write-path report already measured
that the two backends produce different documents here, so the break is known to be reachable.

### C7 — RLS isolation · **specified, not run** · the check that must not be run as superuser

With a second tenant loaded, assert that a connection bound to tenant A returns zero rows from
tenant B's documents, and that an **unbound** connection returns zero rows from either. Assert
also that a connection returned to the pool carries **no** binding.

*Non-vacuity*, and this one has a recorded false negative in the programme: T2.5 broke
`set_config(…, is_local => true)` to `false` and got **0 failures**, because the adapter binds
every operation anyway, so nothing in the run distinguished a transaction-local binding from a
session-local one. **The entire argument for `is_local` was unmeasured.** The check that is not
vacuous is `store.pooledTenantBinding()` over a pool of one — a *question*, not a query hatch —
and the break that proves it is flipping `is_local` to `false` and seeing it go red. Run C7 as a
role that is `NOSUPERUSER NOBYPASSRLS`, or it has verified nothing.

### C8 — The completeness trailer · **specified, not run**

The export must declare what it covered before any row, and the load must assert it received
exactly that. `exportTenant` already does the outbound half for the reason stated in its own
comment: a truncated export is otherwise indistinguishable from a complete one, "and this is the
file someone deletes a tenant on the strength of". The inbound half does not exist.

*Non-vacuity*: kill the exporter mid-collection and confirm the loader refuses rather than
reporting a successful partial load.

### 6.1 The order these run in

C4 (before deciding anything) → load → C1 → C5 → C6 → C2 → C3 → C7 → C8. C1 before C2 because a
cheap total check should fail before an expensive sampled one. C3 last among the correctness
checks because until BF-19 is fixed it is a known red and running it earlier trains people to
ignore it.

**And one thing that runs afterwards, because C1-C8 all stop at the moment writes open.** The
failure this migration produces is silent, so the hosted side needs something watching for it
after the window closes. `tenants.last_reading_at` already exists for this
(`lib/admin/platform.sql`: "Signal-loss detection. The INGEST path updates this"), and the admin
plane's health endpoint is where it surfaces. **A migrated tenant whose `last_reading_at` stops
advancing is the operator-visible form of "their uploader was never reconfigured", and it must be
alerted on rather than looked at.** Nothing in this document currently specifies that alert; it is
work the loader's author inherits, and §7.2's "how to tell if something went wrong" list is the
tenant-facing half of the same problem.

---

## 7. What this means for a self-hoster

*This section is for people managing their own or a family member's diabetes, not for developers.
It avoids jargon on purpose. It is not medical advice.*

### 7.1 If you run your own Nightscout: nothing changes. Nothing.

**You will never run this migration.** Your Nightscout keeps using MongoDB — the database it has
always used — and that is a permanent decision, not a temporary one. It is written down as
decision D4 and it is not under review.

You do not need to move to PostgreSQL. There will not be a version that requires it. Running your
own site will not become a second-class way to use Nightscout: keeping it first-class is
decision D1, and it applies for as long as the project exists.

The reason a second database exists at all is narrow. If somebody offers to *host* Nightscout for
many different families on shared computers, they need a way for the computer itself to enforce
that one family's data can never be returned to another family — not by being careful in the code,
but as a rule the database refuses to break. PostgreSQL has that feature. MongoDB does not have an
equivalent one for writes. That is the entire reason, and it does not apply to a site that has one
family on it.

### 7.2 If you *choose* to move to a hosted Nightscout

Your data is yours, and moving it is something you ask for. It is never done to you and it does
not happen automatically.

**What you get**

* Somebody else runs the server, applies updates, and is responsible for it staying up.
* Your data is kept separate from every other family's by the database itself, not only by the
  program.
* You can ask for a complete copy of your data back at any time. The hosted service can already
  produce one, and it tells you which parts of your data it included, so a copy that got cut off
  halfway is not mistaken for a complete one. **One honest detail:** today only the people running
  the service can press that button — there is no "download my data" link for you to press
  yourself. That is planned, not built. Ask how quickly they will answer such a request, and get
  the answer in writing.

**What you give up, and this list is the honest one**

* **Alarms do not work on the hosted service yet.** They are switched off there deliberately while
  the code that keeps one family's alerts from reaching another family is still being built. If
  you rely on Nightscout alarms, do not move yet. **Ask, and get a plain answer, before you
  agree.** Your insulin pump's and CGM app's own alarms are unaffected — those come from your own
  devices — but any alert you get from Nightscout itself will not.
* **One feature is genuinely missing**: searching your treatment records by an individual food item
  inside a bolus calculation. This comes back later. *Everything else the reports do is expected to
  work, but "expected" is the right word* — the checks that would prove it for food and activity
  records have not been run yet (Open Question 4). Ask whether they have been run for your site
  before you agree a date.
* **You have to set your devices up again.** Every phone app, uploader and bridge that sends data
  to your site needs a new access code, because the old ones do not travel with the data. Plan for
  an afternoon, not five minutes.
* **There is a planned quiet period.** While your data is being copied, your site stops accepting
  new readings, on a date you agree in advance. Your phone and pump keep working normally and keep
  their own records; it is Nightscout that pauses. Your apps will catch up afterwards.
  **Nobody has measured yet how long the pause is** — an earlier draft of this document said
  "likely hours", and that number was not measured by anyone. Do not accept a date until somebody
  gives you a figure they have actually timed, and a plan for what happens if it runs long.
* **During that quiet period, do not treat your Nightscout screen as current.** It should tell you
  it is paused. If it does not, and you see a graph that stops, assume it is out of date and use
  your own CGM app. Making a treatment decision from a Nightscout screen that has silently stopped
  updating is the specific risk of this window.
* **Going back is possible for a while, and then it stops being simple.** For a stated period
  after the move your old database is kept, switched to read-only, so going back means switching
  the site over and copying across what arrived in between. After that period, some things cannot
  be put back the way they were — §8 lists them, and the person offering to host you should be
  able to say which period they are offering and what happens at the end of it. Ask before you
  move, not after.

**How to tell if something went wrong — this is the part that fails quietly.** Nothing in this
migration announces itself by breaking. The way it goes wrong is that a page loads, a number looks
plausible, and something is missing. So, in the first few days after the move, check these and
report anything that does not match:

* **Your history goes back as far as it used to.** Scroll or run a report to a date you remember
  well — a month ago, six months ago — and check the readings are there.
* **A day you know well looks the way you remember it.** Pick a day with a big meal or a site
  change on it and compare what the reports say now with what you remember or wrote down.
* **Your treatments are still there** — boluses, carbs, site and sensor changes — and the totals
  for a day match what you would expect.
* **New readings are arriving.** After you have reconfigured your uploaders, watch that the newest
  reading stays recent rather than quietly stopping an hour later.
* **Your profile is right.** Check your basal rates, correction factor and carb ratio on the
  hosted site against what you had before, value by value, before you rely on anything Nightscout
  calculates from them. **If they do not match, stop and say so** — do not adjust anything to
  compensate, and talk to your care team.

If any of these looks wrong, say so immediately and ask for your old site to be brought back
rather than working around it. A gap that is noticed in the first week is recoverable; the same
gap noticed in six months may not be.

**Your consent.** Nobody should move your data on the strength of a support ticket. What you are
agreeing to is: which collections move, that your access codes are replaced, that alarms are off,
the date of the quiet period, and what happens if it goes wrong. That should be written down and
shown to you in words like these ones.

**None of this is medical advice**, and nothing here tells you anything about doses. How you
monitor your glucose, whether it is safe for you to be without Nightscout alarms for a period, and
what to do during the quiet period, are conversations for you and your care team. Keep whatever
backup you normally use for when Nightscout is unavailable, and use it during the quiet period.

---

## 8. Rollback, and the one-way doors

### 8.1 Before the tenant writes to PostgreSQL: rollback is free

Up to the moment writes are opened on the hosted tenant, the source MongoDB is untouched and
authoritative. Rollback is: do not flip routing, or flip it back. Delete the loaded rows. **Keep
the source database read-only but intact until §6's checks have passed and a person has looked at
the result** — not until the loader exited zero.

### 8.2 After the tenant writes to PostgreSQL: it is a one-way door, and here is exactly why

Going back means exporting from PostgreSQL and loading into MongoDB, and **that reverse path does
not exist either** — `exportTenant` produces the rows, and nothing consumes them into MongoDB. But
the missing code is the easy part. These are the things that do not come back:

1. **Type information that `scalarizeDoc` flattened.** A BSON `Date` became an ISO string on the
   way in. On the way back it is a string, and there is no record of which strings used to be
   Dates. Any MongoDB query that compared against a `Date` — and BF-20 says such a query matches
   nothing on MongoDB when the stored value is a string — is now silently answering differently.
   **This is the sharpest one-way door and it is invisible.** C4 is what tells you, before you
   move, whether this tenant has any of them; if C4 says zero, this door does not exist for that
   tenant and it is worth knowing which case you are in.
2. **`_id` identity, if any document arrived without one.** `mintId()` reproduces ObjectId's
   layout — 4 bytes of seconds then 8 random — but a minted id is not the id a client would have
   received from MongoDB. Documents created on the hosted service have hosted-service ids.
3. **Fields that BF-21 preserved and should not have.** Until BF-21 is fixed, every field any
   client deleted while the tenant was hosted is still on the PostgreSQL row. Rolling back
   *reintroduces those fields into MongoDB*. The rollback does not merely fail to restore the
   original state; it writes a state that never existed.
4. **Dotted keys BF-22 created.** A PATCH with a dotted field left a key no path lookup finds.
   Loaded back into MongoDB it is a key MongoDB will also not find by path, and `$set` semantics
   will not reconstruct the nesting.
5. **Everything the hosted service holds that has no MongoDB home.** Durable ack/snooze state
   (`lib/storage/ack-store.js`, `alarm-ack.sql`) and the `tenants` / `tenant_members` rows are
   PostgreSQL-only by construction. The admin plane is PostgreSQL-only with, by design, no export
   for a MongoDB target. Rolling back loses the tenant's acknowledgement history.
6. **Time.** Everything written between cutover and rollback is on PostgreSQL only, so a rollback
   is either a second migration in the other direction or an accepted data loss window. There is
   no third option.

### 8.3 What to do about it

**Keep the source MongoDB, read-only and intact, for a stated period** — long enough that a
problem found in normal use is still recoverable, and stated to the tenant rather than assumed.
During that period, rollback is "stop writing to PostgreSQL, replay the hosted period's writes
into MongoDB, flip back", and the replay is bounded and auditable rather than a full reverse
migration. After it, rollback means accepting §8.2's list.

**Write the reverse loader before the forward one is used in anger.** Not because it will be run,
but because writing it is what discovers which of §8.2's items are real for this schema, and
discovering that during an incident is the wrong time.

**There is prior art in this repository for the shape of that rehearsal**, found in review:
`tools/rehearse-database-upgrade.py` rehearses MongoDB 5→6→7→8 upgrades *and a backup-restore
rollback* on UUID-named throwaway volumes, refusing by construction to be pointed at a real
deployment URI, container, volume or database. That refusal, and the expected-state file it writes
before it starts, are the two properties a Mongo↔PostgreSQL rehearsal needs and the reason it is
worth copying rather than starting from scratch.

---

## 9. Corrections to existing documents

I have not edited any of these; per the brief they go to the reconciliation agent.

1. **`nightscout-backfix-register.md` (BF-19 and BF-21 detail sections) and three research
   reports** pin the exposure of BF-19 and BF-21 to "**T2.6**". The execution plan defines no
   T2.6 — Phase 2 is T2.0-T2.5 plus T2.1a, and T2.5 is `entries` only. A deadline attached to a
   task that does not exist cannot be scheduled or checked. Either add T2.6 (the remaining
   collections on PostgreSQL) to the plan, or repoint the deadline at a task that exists.
   Verified 2026-09-15: `grep -n 'T2\.6'` finds the register at lines 214 and 260, three reports
   under `docs/60-research/`, and the new [post-phase0-roadmap-2026-09-15.md](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/b362302b/docs/30-design/post-phase0-roadmap-2026-09-15.md), which also gates
   work on T2.6 while calling it "unscheduled" — five documents scheduling against a task that
   no document defines. `grep -oE 'T2\.[0-9a-z]+'` on the execution plan returns only T2.0-T2.5
   and T2.1a.

2. **`tools/nsschema/emit/postgres_emit.py`, "WHAT THIS DOES NOT DO"** says `food`, `activity`,
   `settings` and `auth_*` "have no model yet (plan T2.2)". **T2.2 is DONE (2026-09-14) and
   `specs/nsschema/` carries a model for all ten collections.** What is missing is an entry in the
   emitter's own hand-transcribed `INDEXED_FIELDS` dict — and the index declarations already exist
   as data in `specs/nsschema/server-indexes.json`, which covers eight collections including
   `food` and `activity`. The comment sends the next reader to write models that exist.

3. **`nightscout-backfix-register.md` BF-21's proposed fix** says "give the PostgreSQL
   `bulkUpsert` the same `(ops, options)` signature **and implement `'replace'`**". Replace is
   already implemented: `write(ast, doc, 'replace')` at `pgCollection/index.js:220-229` emits
   `$N::jsonb || jsonb_build_object('_id', doc -> '_id')`, and `replaceOne` uses it. The fix is to
   thread the mode through. Worth correcting because the entry makes the fix sound larger than it
   is, and its size is an argument for doing it before a migration.

4. **`postgres_emit.py`'s "182 nodes"** for `devicestatus` is unexplained. Measured: the model has
   **184** descendant nodes; 182 excludes the two `code_supplemented_fields` (`NSCLIENT_ID`,
   `date`). Not an error — but a reader who counts gets a different number and has no way to know
   which is meant.

5. **The execution plan §2.3** lists per-tenant export among "**Endpoints (proposed, to be
   argued)**". It is **implemented** — `lib/admin/platform-store.js:386` `exportTenant`, a
   streaming server-side cursor inside one repeatable-read transaction, emitting the covered-table
   list before any row. There is **no import counterpart anywhere**, which is the more useful
   thing for the plan to say.

6. **`nightscout-backfix-register.md` BF-20's location column** says
   `lib/api3/storage/pgCollection/utils.js`. `scalarize()` is in
   **`lib/api3/storage/pgCollection/sql.js:27`**, and `utils.js` contains no `scalarize` at all
   (`grep -n scalarize .../utils.js` returns nothing). The register sends a reader to the wrong
   file for a defect whose whole content is one function. This is the same class of stale
   reference the register audit found for BF-05 and BF-09.

7. **`nightscout-backfix-register.md` BF-21's summary** says "the `{mode:'replace'}` **every**
   shipping caller sends is silently ignored". Measured: nine `bulkUpsert` call sites, eight send
   `'replace'` and `lib/server/entries.js:168` sends `'merge'` deliberately, above a comment
   explaining that the two are not interchangeable. The correction matters because "every caller
   wants replace" makes "always replace" look like a safe fix, and it is not — it would make
   `entries.js` delete stored fields. The mode must be threaded. §3.2 carries the full census.
   *Note for the reconciliation agent:* BF-21's own detail section names only three call sites
   (`activity.js:61`, `:102`, `treatments.js:31`), so the entry undercounts the blast radius twice
   over — it misses `food`, `profile` and `lib/authorization/storage.js` as well as misstating the
   intent.

8. **`nightscout-backfix-register.md` BF-22's reachability caveat can be lifted.** The entry says
   the PATCH path is reachable "subject to a validation layer that was not audited". Audited
   2026-09-15 on `crm-seam` 81a1f6ce: between `req.body` and `updateOne` there is
   `lib/api3/shared/writePurifier.js` → `lib/server/purifier.js` `purifyObject`, which rewrites
   string **values** only and never a key (lines 165-191), and `lib/api3/generic/update/validate.js`,
   which checks an immutable-field list then `validateCommon`'s `date`/`utcOffset`/`app` type tests,
   all of which are skipped for a field absent from the patch. Nothing inspects key names. The
   caveat can be replaced with "audited; no layer inspects key names", which raises BF-22's
   confidence without changing its grade.

9. **A proposed new register entry, with NO id allocated (rule 3): `scalarizeDoc` converts only
   `ObjectId` and `Date`, and turns every other BSON wrapper into a jsonb object.** Measured in
   review; the full table, the reachability analysis and the consequence for the generated columns
   are in §4.3's correction block. It is filed here rather than as a correction because it is a
   defect in shipping code (`lib/api3/storage/pgCollection/sql.js:27-61`), not a documentation
   error, and because D4 forbids deferring it on the grounds that the seam will be revisited.

---

## 10. Open questions

1. **BF-22's transform half: faithful or normalising?** If a source document already contains a
   literal dotted key, does the migration reproduce it or nest it? The two loaders produce
   different documents and the register entry only addresses the PATCH path. **The maintainer must
   decide**, and it should be written down before a loader is written, not discovered by one.
2. **Does any real Nightscout database store BSON `Date`, `Long` or `Decimal128` in the fields the
   generated columns read?** The corpus is structurally incapable of answering (§3.4) and this is
   the single measurement that most changes the migration's risk. **C4 answers it, per tenant,
   and it needs a real database and that tenant's consent to look.**
3. **How long is the read-only window actually?** Unmeasured. §4.1 sizes the data but nothing here
   has timed an export, a transform, a load or — the likely bottleneck — the differential
   verification, end to end. **Whoever writes the loader must measure it before a date is offered
   to anybody.**
4. **`food.hidden` and `food.position` are both AMBIGUOUS**, so the `food` table would carry no
   columns for them and BF-16's `{$nin: [true, 'true']}` fix would run against the jsonb path.
   Does it give the same answer there? **Unmeasured** — nobody has run a food differential, and
   `food` has no table to run it against.
5. **Should alarms-off be a blocker on hosting a tenant at all, rather than a disclosure?** §5.3
   and §7.2 treat it as something a tenant consents to. A reviewer may reasonably say that a
   glucose monitoring service that cannot alarm should not accept a migration from one that can.
   **That is a maintainer and clinical-reviewer decision, not a technical one**, and this document
   should not be read as having settled it.
6. **Does `scalarizeDoc` need to handle the remaining BSON types, or must the loader refuse them?**
   §4.3's correction block shows it converts only `ObjectId` and `Date`. `Decimal128`, `Binary`,
   `Timestamp` and an out-of-53-bit `Long` become jsonb objects that null the generated column
   without erroring. Two answers are defensible — extend the transform with a declared
   representation per type, or refuse the document and make the tenant's source data the thing that
   changes — and they are **different stored documents**, so this is the same class of decision as
   Open Question 1 and belongs to the maintainer, not to whoever writes the loader.

7. **Who is the hosting operator, legally?** Everything above assumes a hosting entity exists that
   can hold a consent record and a data-retention commitment. **That is outside this document and
   needs qualified legal review** — it is a data-protection question about health data, not an
   engineering one.

---

## 11. Reproduction

Everything measured for this document:

```
# DDL and mapping (main repo, HEAD 08753474)
PYTHONPATH=tools python3 -m nsschema.emit.postgres_emit --report
#   -> entries 9 cols/9 idx/0 flagged; treatments 13/14/2;
#      devicestatus 4/3/1; profile 3/4/1. Output byte-identical to the
#      committed specs/generated/postgres/*.sql (git status clean afterwards).

# Sizing: file bytes / document count per collection, 2026-04-01 snapshot.
#   No document content was read or printed. Site identities are the
#   single-letter pseudonyms the collection pass assigned.

# bulkUpsert caller census (§3.2), in the seam worktree at 81a1f6ce:
grep -rn -A2 'bulkUpsert(' lib/server/*.js lib/authorization/*.js
#   -> 9 call sites / 6 files; 8 pass {mode:'replace'},
#      entries.js:168 passes {mode:'merge'} with an explanatory comment.

# Corpus sizing cross-check (§4.1), file bytes and array lengths only:
#   -> devicestatus 75.4% of bytes over the three sized collections.

# Fidelity, answer differential, ordering and the non-vacuity breaks (§3.1, §4.3, §6):
docker run -d --name mig-pg-$$   -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15501:5432 postgres:16-alpine
docker run -d --name mig-mongo-$$ --ulimit nofile=64000:64000        -p 27201:27017 mongo:7
node <scratchpad>/fidelity.js
docker rm -f mig-pg-$$ mig-mongo-$$
```

Both containers were created for this document and removed afterwards. **No worktree was created,
modified, repointed or deleted; no branch was checked out, committed to, pushed or tagged; no
other session's database was touched.** The fixtures in `fidelity.js` are eight `entries`
documents invented for the purpose, with `_id` values `aaaa…`/`bbbb…`/… and a device name of
`synthetic-cgm`.

**This document is a draft. It must be reviewed before it is relied upon.**
