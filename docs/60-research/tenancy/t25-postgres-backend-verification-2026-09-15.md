# Verifying the T2.5 PostgreSQL backend — four predictions, two of them wrong

Date: 2026-09-15 · Harness: [`tools/qc/pg-backend-arm.js`](../../../tools/qc/pg-backend-arm.js)
Under test: `crm-seam` at **`7cc03cda`** ("T2.5: entries runs on PostgreSQL with RLS"), read from
an independent detached worktree. **No shipping code was changed by this work, and nothing was
committed to the branch under test.**

Arms: real `mongod` 7.0.43 (driver 7.6.0) · real PostgreSQL 16.14, the **emitted** schema
(`lib/storage/postgres/generated/entries.sql`) under RLS, connected as a
`NOSUPERUSER NOBYPASSRLS` role.

**The branch moved during this work and the findings still apply.** `crm-seam` advanced to
`903bcec9` (T3.4) while this ran; `git diff 7cc03cda..903bcec9` is **empty** for every module
measured here — `lib/storage/filter.js`, `lib/api3/storage/pgCollection/`,
`lib/storage/postgres-storage.js`, `lib/storage/postgres/`,
`lib/api3/generic/search/input.js`, `lib/api3/shared/fieldsProjector.js` and
`lib/server/entries.js`. Checked rather than assumed, because a verification of a commit nobody is
on any more is worth nothing.

| ref | document |
|---|---|
| **{F}** | [three-arm validation of the filter AST](seam-filter-ast-three-arm-validation-2026-09-14.md) |
| **{O}** | [ordering and pagination](seam-ordering-and-pagination-2026-09-14.md) (BF-13) |
| **{L}** | [limit and projection](seam-limit-and-projection-2026-09-14.md) (BF-14, BF-15) |
| **{R}** | [readOptions across the seam](seam-readoptions-2026-09-15.md) (BF-18 pre-release) |
| **{B}** | [backfix register](../../30-design/remedial/nightscout-backfix-register.md) |

---

## 0. What makes this run different from the four that preceded it

Every earlier harness in `tools/qc/` compared a real `mongod` against a **PostgreSQL arm the
harness author wrote**. {L} §4 says so in its own honest-limits section: *"The PostgreSQL arm here
is a strawman by construction."* A strawman answers *where would a naive translation differ*. It
cannot answer *does the translation that shipped differ*, and after T2.5 that is the only question
left.

So every PostgreSQL answer below comes from the shipping modules —
`lib/storage/postgres-storage.js`, `lib/api3/storage/pgCollection/{index,sql,utils}.js`,
`lib/storage/filter.js` — against the shipping emitted DDL, driven through the **same interface**
the MongoDB arm is driven through:

```js
store.storageCollection(ctx, env, 'entries', []).findFiltered(ast, opts)
```

Both arms are constructed by their own store's `storageCollection()`. A divergence reported here
is a divergence a caller above the seam would see.

**One fixture change was forced and is worth stating.** The emitted table is
`PRIMARY KEY (tenant_id, "_id")` with `_id` a `text` generated column guarded by
`jsonb_typeof = 'string'`, so a document with a numeric `_id` **cannot be stored at all**. {F}'s
corpus uses numeric ids; this one uses zero-padded strings, document for document otherwise. That
is a real property of the shipped schema, not a concession by the harness.

### Verdicts

| # | prediction | verdict |
|---|---|---|
| 1 | filter AST classes A and C still unfixed in `toSql` | **REFUTED** — all four classes closed, 3000/3000, zero runtime errors |
| 2 | `limit: 0` is a wrong answer, not just an unbounded read | **CONFIRMED** — 10 rows vs 0 rows, end to end through `lib/server/entries.js` |
| 3 | `orderBy` has no `_id` tiebreak, so BF-13 reappears | **CONFIRMED** — but 3/1000 lost, not MongoDB's 476/1000 |
| 4 | `project` handles only top-level keys | **CONFIRMED** at the seam; **client-visible impact is nil**, established rather than assumed |
| — | does PostgreSQL materialise whole result sets? | **yes** — 35.4 MiB retained for 40,000 rows vs 0.0 MiB through a cursor |

Two findings that were **not** predicted are in §6. One of them is the most serious thing in this
document.

---

## 1. Claim 1 — REFUTED. The filter AST classes are closed.

The prediction was formed by reading for `IS DISTINCT FROM`, which is still the only place that
spelling appears in `filter.js`. The reading was right and the conclusion was wrong: `toSql` now
closes classes A and C by a **different mechanism**, and closes B and D as well.

```
class  probe                                  mongod        postgres      verdict
-----  -------------------------------------  ------------  ------------  ----------------
A      lte null, field absent                 2,3           2,3           agree
A      gte null, field absent                 2,3           2,3           agree
A      eq  null, field absent                 2,3           2,3           agree
A      ne  null                               1,4           1,4           agree
A      lt  null                               -             -             agree
A      gt  null                               -             -             agree
A*     eq null on a COLUMN field              2,3           2,3           agree
A*     lte null on a COLUMN field             2,3           2,3           agree
B      lt STRING bound on numeric field       -             -             agree
B      lt STRING bound, orders agree          -             -             agree
B*     lt STRING bound on a COLUMN field      -             -             agree
B*     gte STRING bound on a COLUMN field     -             -             agree
C      in containing null, field absent       1,2,3,4       1,2,3,4       agree
C      nin containing null                    -             -             agree
C*     in containing null on a COLUMN field   1,2,3,4       1,2,3,4       agree
C      in with MIXED types                    1,2,3         1,2,3         agree
D      numeric bound against a text field     -             -             agree
D      boolean bound on a jsonb field         -             -             agree
D*     text bound on a numeric COLUMN         -             -             agree
D*     boolean bound on a numeric COLUMN      -             -             agree
```

The rows marked `*` are new: {F}'s PostgreSQL arm was handed a **list** of column names, so the
type was unknown and every comparison took the jsonb path. It never exercised the column branch at
all. This run passes the real `columnTypes` **map** from `lib/storage/postgres/generated/index.json`, so
`sgv`, `date` and `type` are compared as typed generated columns — and they agree too.

The mechanisms, all present in the shipped `filter.js`:

- **Class A** — a `nullMatch()` helper that reads `doc #> '{path}'` (where an absent key is SQL
  NULL and an explicit null is jsonb `'null'`, still distinguishable) instead of casting. `lt`/`gt`
  against null return literal `FALSE`, because there is no value above or below null inside its own
  bracket. This is more than the predicted `IS NOT DISTINCT FROM` mirror would have given.
- **Class C** — `in`/`nin` split the value list into one arm per JSON type, and the `null` arm goes
  through the same `nullMatch()`.
- **Classes B and D** — `typedRef()` wraps every extraction in
  `CASE WHEN jsonb_typeof(...) = '<type>' THEN (...)::<cast> END`, chosen from the **bound's** JSON
  type. That reproduces MongoDB's type bracketing and makes the cast total, so the 22P02 class
  cannot fire.

Randomised, same generator, same seed, same 12 % cross-type injection rate as {F} §3:

```
3000 filters, cross-type injection 12%
  evaluated 3000, skipped-as-invalid 0, arm errors 0
  OK    mongod-vs-postgres  3000/3000  (100.00%)  disagreements 0
```

**Compare with {F} §3, which is the same generator against the same corpus:**

| | {F} §3 (2026-09-14) | this run (7cc03cda) |
|---|---|---|
| mongod-vs-postgres | 2694/2802 (96.15 %) | **3000/3000 (100.00 %)** |
| PostgreSQL runtime errors | **198/3000 (6.6 %), all 22P02** | **0** |

### Non-vacuity

Two ways this could be vacuous, so two separate breaks. Both are in the harness and both run on
every invocation.

**(a) Can the comparator see these classes at all?** The *pre-fix* SQL is emitted by hand for three
probes and run on the same connection through the same comparator:

```
A  eq null, pre-fix `= $1`              mongod 2,3      pre-fix -          comparator RED
C  in [null,2], pre-fix `IN (...)`      mongod 1,2,3,4  pre-fix 1,4        comparator RED
D  gte 100 on text, pre-fix bare cast   mongod -        pre-fix ERR 22P02  comparator RED
comparator caught 3/3 planted regressions
```

**(b) Does the corpus exercise the property?** {F} §5 records that an earlier differential proved
much less than it appeared to because its generator was same-type throughout. The generator is
therefore re-walked with the same seed and its shapes counted:

```
comparison nodes 9454: null operand 222, in/nin containing null 61, cross-type bound 592
```

So the 3000/3000 is over a corpus that contains 222 null operands, 61 `in`/`nin` lists containing
null, and 592 cross-type bounds. **This pass has non-vacuity evidence of both kinds.**

---

## 2. Claim 2 — CONFIRMED. `limit: 0` is a wrong answer on PostgreSQL.

`pgCollection/index.js` gates on `o.limit !== undefined && o.limit !== null` and then emits
`LIMIT $n`. `mongoCollection/find.js` gates identically and calls `.limit(n)`. The gates match; the
**meaning of zero** does not. MongoDB defines `.limit(0)` as *no limit*.

At the seam interface, ten documents:

```
?count=      v1 limit      mongod              postgres
-----------  ------------  ------------------  ------------------
'3'          3             3 rows              3 rows
'0'          0             10 rows             0 rows              DIFFERS
'abc'        NaN           10 rows             0 rows              DIFFERS
'-3'         -3            3 rows              ERR 2201W           DIFFERS
'2.7'        2             2 rows              2 rows
'1e2'        1             1 rows              1 rows
''           undefined     10 rows             10 rows
(absent)     undefined     10 rows             10 rows
```

And through the shipping v1 read path — `lib/server/entries.js` `list()`, called with the opts
express would have built, not a transcription of its limit expression:

```
GET /api/v1/entries?count=3     mongod 3 rows     postgres 3 rows
GET /api/v1/entries?count=0     mongod 10 rows    postgres 0 rows
GET /api/v1/entries?count=abc   mongod 10 rows    postgres 0 rows
GET /api/v1/entries?count=-3    mongod 3 rows     postgres ERR 2201W
```

**Three things this changes about BF-14.**

1. **BF-14 was graded *medium* on the grounds that "it returns no wrong data"** ({L} §2.2, {B}).
   On PostgreSQL it returns wrong data. The same URL against the same collection returns the whole
   thing on one backend and an empty `200` on the other. An empty `200` from a glucose read is the
   failure mode this programme keeps naming as the worst kind.
2. **`?count=abc` behaves identically to `?count=0`**, by a second route: `parseInt('abc')` is
   `NaN`, `NaN` is not `undefined` or `null` so the gate opens, and `toSafeInt(NaN, 0)` supplies
   the zero. {L} §2 marked the `abc` row `—` rather than `match`, because its strawman declined to
   emit `LIMIT NaN`. The shipped backend does not decline; it emits `LIMIT 0`. **That row is now
   measured, and it is a divergence.**
3. **`?count=-3` is an HTTP 500 on PostgreSQL** (`2201W`, *LIMIT must not be negative*) where
   MongoDB returns 3 documents. An availability difference on top of the correctness one.

The fix {B} already names — give v1 the validation `lib/api3/generic/collection.js:76` already has
— closes all three at once, and closes BF-18 as {R} §2.1 predicted. **Nothing in the PostgreSQL
backend needs to change for that fix to work**, but if the backend is to be safe on its own terms,
`toSafeInt(o.limit, 0)` should not default to the one value that means "no limit" on the other
backend.

### Non-vacuity

The comparator is a differential, so its failure mode is being unable to print one of the two
answers. Both are forced and both are printed:

```
limit 3  -> agree     (must be agree)
limit 0  -> DIFFERS   (must be DIFFERS)
comparator distinguishes both outcomes
```

**This pass has non-vacuity evidence.**

**One thing the harness got wrong first, recorded because it would have been an invisible false
negative.** The first run of this section reported `0 rows` on *both* backends for every count,
including `count=3`. That is not a backend defect: `lib/server/query.js` `default_options()` adds
`date >= now - 4 days` to every v1 read, and the fixture corpus was stamped in 2023. The corpus was
moved into the window; the probe was not adapted until it passed.

---

## 3. Claim 3 — CONFIRMED. BF-13 reappears on PostgreSQL, smaller and deterministic.

`sql.js` `orderBy()` emits only the client's sort terms plus an explicit `NULLS FIRST`/`NULLS LAST`.
No unique final key. {O} §3.3 says in as many words: *"Carry it across the seam. Whatever ordering
translation §2 produces must also append a unique final key, or the same defect reappears on
PostgreSQL."* It was not appended.

BF-13's precondition, unchanged: **no `identifier`**, **tied `created_at`**, **tied `date`**, so
v3's whole default sort chain `{identifier, created_at, date}` ties on every document.

**Twelve documents, paged three at a time:**

```
mongod    lost  7/12   [001 002 003][001 003 006][001 003 007][001 003 007]
          duplicated: 001x4 003x4 007x2
postgres  lost  0/12   [002 003 001][004 005 006][007 008 009][010 011 012]
```

At this size PostgreSQL loses nothing. That is not the whole answer, and reporting it as one would
have been the error.

**One thousand documents, paged 100 at a time, three identical sweeps each:**

```
mongod    lost 476, duplicated 241   (3 trials: 476/241  476/241  476/241 — deterministic)
postgres  lost   3, duplicated   1   (3 trials:   3/1      3/1      3/1   — deterministic)
          lost: 00101 00201 00301
          dup:  00001 x4
```

**Three of a thousand documents are never returned by a full paginated sweep, and one is returned
four times.** Deterministic across trials — a blocking sort that is unstable, not a race.

The plan says why:

```
Limit
  ->  Sort
        Sort Key: identifier NULLS FIRST, created_at NULLS FIRST, date NULLS FIRST
        ->  Bitmap Heap Scan on entries
              Recheck Cond: (tenant_id = (NULLIF(current_setting(...), ''))::uuid)
              ->  Bitmap Index Scan on entries_tenant_identifier
```

A blocking `Sort` under a `Limit`, re-executed for every page — structurally the same shape as
{O} §3's `SORT <- COLLSCAN` on MongoDB, and PostgreSQL promises no more about ties than MongoDB
does. The pattern of the loss (documents `00101`, `00201`, `00301` lost; `00001` repeated on
pages 1–4) is what a top-N sort selecting a different tie member for each `LIMIT+OFFSET` produces.

Forcing parallelism (`parallel_setup_cost = 0`, four workers — a stress, **not** a self-hoster's
settings) gives the same `3/1000`. Reported separately and never mixed into the default numbers.

**The one-line fix works on both backends.** Appending `_id` to the sort chain, which is exactly
what `parseSort` would do:

```
same sweep, sort chain + _id:
  mongod    lost 0, duplicated 0
  postgres  lost 0, duplicated 0
```

**Grading.** MongoDB loses 47.6 % of a thousand tied documents; PostgreSQL loses 0.3 %. Both are
silent data loss on a read, so the severity of the defect is the same; the *quantity* is two orders
of magnitude apart, and that difference should not be smoothed over in either direction. It also
means a PostgreSQL deployment is **worse to diagnose**: a sweep that loses 3 of 1000 looks like
nothing at all, where losing 476 of 1000 gets noticed.

### Non-vacuity

If PostgreSQL had reported `0` at both sizes, "paging is safe" would have been a check that never
went red. Two breaks:

**(a) the same checker, on a corpus known to break it.** `lost 7/12` on mongod, through the same
`lossReport()` — the checker works.

**(b) a planted ordering difference.** A sort key holding `{100, '120', true, null, absent, 9}`:

```
mongod   004 005 006 001 002 003     (BSON: null/missing < number < string < boolean)
postgres 005 004 002 006 001 003     (jsonb: SQL NULL, jsonb null, string, number, boolean)
order comparator RED
```

**This pass has non-vacuity evidence.** Break (b) is also a finding in its own right — see §6.

---

## 4. Claim 4 — CONFIRMED at the seam. Client-visible impact is nil, and that was measured.

`sql.js` `project()` tests `Object.prototype.hasOwnProperty.call(doc, key)`, so a dotted key
matches nothing. MongoDB walks the path and produces **three different shapes** depending on where
the chain breaks.

```
projection {"uploader.battery":1}            mongod                        postgres
  prj001 uploader.battery = 80    {"_id":"prj001","uploader":{"battery":80}}  {"_id":"prj001"}   DIFFERS
  prj002 uploader = {}            {"_id":"prj002","uploader":{}}              {"_id":"prj002"}   DIFFERS
  prj003 uploader absent          {"_id":"prj003"}                            {"_id":"prj003"}
  prj004 uploader = null          {"_id":"prj004"}                            {"_id":"prj004"}
```

Two of MongoDB's three shapes are lost. The two that agree agree by accident — `{}` is what
`project()` returns for *every* dotted path, and for two of the four documents that is also the
right answer.

**Does it reach a client?** {L} §4 left this open, and the instruction was to establish it rather
than assume either way. The shipping `lib/api3/shared/fieldsProjector.js` was run, not described:

```
?fields=uploader.battery
storageProjection {"uploader.battery":1,"identifier":1,"srvCreated":1,"created_at":1,"date":1}

mongod    from backend           {"_id":"prj001","date":1,"created_at":"…","uploader":{"battery":80}}  …
          after applyProjection  {} {} {} {}
postgres  from backend           {"created_at":"…","date":1,"_id":"prj001"}                            …
          after applyProjection  {} {} {} {}

client-visible bodies are identical on both backends
```

**BF-15 masks the divergence completely.** `applyProjection` deletes every top-level key not
string-equal to something the client typed, and `uploader.battery` never string-equals `uploader`,
so both backends emit `{}`. The client-visible impact of claim 4 **is nil today** — and it stops
being nil the moment BF-15 is fixed, because fixing BF-15 means teaching `applyProjection` about
dotted paths, at which point MongoDB starts returning the nested document and PostgreSQL still
returns nothing.

**So these two must be fixed together.** Fixing BF-15 alone converts a defect that returns `{}` on
both backends into a defect that returns different data on each. That is a worse state than the one
it replaces, and it is not obvious from either entry read alone.

### Also measured, not predicted

**Key order differs on every projection.** MongoDB returns projected fields in the *document's*
order, `sql.project()` in the *projection's*. No JSON client can observe it — an object has no
order once parsed — so it is reported here as an observation and not counted as a divergence.

**A mixed include/exclude projection raises on MongoDB and is silently answered on PostgreSQL.**

```
projection {"sgv":1,"type":0}
  mongod   ERR Cannot do exclusion on field type in inclusion projection
  postgres ok  (treats it as an inclusion of sgv, and drops type silently)
```

Not client-reachable: `fieldsProjector` only ever writes `1`. Architectural, and the same shape as
{L} §3.2's point that `projection` is an unmodelled expression language.

### Non-vacuity

**The non-vacuity check caught a bug in the harness, which is the best evidence it works.** The
first comparator was `JSON.stringify(a) !== JSON.stringify(b)`, which reported *every* projection
as divergent including `{sgv: 1}`. The pair that must agree came back `DIFFERS`, the section
printed `comparator IS VACUOUS`, and the fault was in the harness — key ordering — not the backend.
Comparing raw strings would have published four false findings. After the fix to a canonical
(key-sorted) comparison:

```
{sgv:1}                -> agree     (must be agree)
  [{"_id":"prj001","sgv":100}]  vs  [{"sgv":100,"_id":"prj001"}]
{'uploader.battery':1} -> DIFFERS   (must be DIFFERS)
  [{"_id":"prj001","uploader":{"battery":80}}]  vs  [{"_id":"prj001"}]
comparator distinguishes both outcomes
```

**This pass has non-vacuity evidence.**

---

## 5. Materialisation — confirmed, through the shipping read path

`pgCollection/index.js` says `readOptions` is *"accepted and ignored"*, with the reason that there
is no `getMore` to bound. The reason is right. The consequence is the one {R} §3 predicted, now
measured on the shipping `findFiltered` rather than on a hand-written `pg.query`:

| | rows | retained heap |
|---|---:|---:|
| `PgCollection.findFiltered` (`readOptions` passed and ignored) | 40,000 | **+35.4 MiB** |
| `BEGIN; DECLARE …; FETCH 1000; COMMIT`, batches consumed and dropped | 40,000 | **+0.0 MiB** |

Two numbers, not a ratio: the cursor arm retains essentially nothing, so a ratio would be a
division by noise. ~1 KB documents, retained heap after a forced collection, `--expose-gc`
required.

{R} §3's conclusion stands unchanged and is now a measured property of shipped code rather than a
prediction: **either the interface grows a streaming read and the bulk callers use it, or the
PostgreSQL backend materialises whole result sets and `mongo-read-options.js` becomes a
MongoDB-only comment describing a property the system no longer has.**

**No non-vacuity evidence, and this is not a parity check.** It is a single measurement of one
implementation against one alternative implementation of the same read. There is no second arm to
break. The `0.0 MiB` figure is the load-bearing one and it is a *negative* result — the honest
weakness is that a measurement of "approximately zero" cannot itself be shown to be sensitive. The
40,000-row / 35.4 MiB arm is the one that carries the claim.

---

## 6. Not predicted — two findings, and the first is the serious one

### 6.1 The index accelerator changes an answer in `ORDER BY` — proposed **BF-19**

The emitted DDL states the invariant in its own header, in capitals:

> **THE COLUMNS BELOW ARE AN INDEX ACCELERATOR. THE DOCUMENT IS THE RECORD.**
> Dropping every generated column must not change an answer.

`filter.js` holds it on the `WHERE` side deliberately, with a comment explaining exactly why
(`typedRef()`'s `CASE` is *"exactly what the emitted DDL builds its columns with, so the two paths
agree by construction rather than by review"*). §1 above confirms it holds: 3000/3000.

`sql.js` `orderBy()` picks between the **same two branches** — typed column when
`columnTypes` has the field, raw `doc #> '{path}'` when it does not — and the two branches **do not
order the same values the same way**. Nothing makes them agree, and nothing tests that they do.

The probe puts **identical values in two fields of the same documents**: `sgv`, which has a
generated column, and `noise`, which does not. Everything else is equal.

```
values, both fields:  100  '120'  true  null  (absent)  9

mongod   sort sgv   (column on pg)  004 005 006 001 002 003
mongod   sort noise (no column)     004 005 006 001 002 003
postgres sort sgv   (COLUMN)        005 004 003 002 006 001
postgres sort noise (jsonb)         005 004 002 006 001 003

mongod   orders the two identical fields THE SAME
postgres orders the two identical fields DIFFERENTLY   <- the accelerator changed the answer
```

Three distinct orders where there should be one. The mechanism:

- **the typed column** is `CASE WHEN jsonb_typeof(…) = 'number' THEN …::numeric END`, so it is SQL
  `NULL` for an explicit null, for an absent key, **and for every value of another type**. All of
  `null`, `absent`, `true` and `'120'` collapse into one NULL bucket and sort together.
- **the jsonb path** keeps them apart and uses jsonb's own type order
  (`Null < String < Number < Boolean`).
- **MongoDB** uses BSON's, which is a third order (`Null/missing < Number < String < Boolean`).

**It is client-reachable through API v3, and the code comment's reason for thinking it is not is
incorrect.** `sql.js` argues:

> Every sort this code path issues is on a field that is one type in practice (`date`,
> `srvModified`, `identifier`, `created_at`), so it does not bite today.

But `lib/api3/generic/search/input.js` `parseSort` puts the **client's** `?sort=` field first in
the chain, unvalidated:

```js
if (req.query.sort$desc) { sortDirection = -1; sort[req.query.sort$desc] = sortDirection; }
else if (req.query.sort) { sort[req.query.sort] = sortDirection; }
```

So the sort key is not drawn from a fixed set of four — it is any field name a client can put in a
query string. `GET /api/v3/entries?sort=sgv` is a supported request, and the moment one document
in the collection carries a non-numeric `sgv` the ordering diverges from MongoDB's and from the
same field's ordering without a column.

**Sizing, honestly, and it holds the grade down.** The emitted manifest
(`lib/storage/postgres/generated/index.json`) flags **no** ambiguous field on `entries`, which is the only
collection T2.5 implements — so on the 11-site corpus this does not fire today. It is flagged on
`NSCLIENT_ID` for `devicestatus`, `profile` **and** `treatments`, all of which are T2.6 and later.
So the exposure arrives with the next collection, not with this one.

**Why it still deserves an entry.** It is not a translation difficulty; it is a stated invariant
being violated by code that was written after the invariant was written down, in the one place
nobody checked. The `WHERE` side got a `CASE` that mirrors the column definition precisely *because*
somebody noticed the same hazard there — the comment in `typedRef()` records the measurement that
caught it. `ORDER BY` got the same two branches and no such reconciliation.

*Proposed fix*: `orderBy()` must not use the generated column as a sort key unless it can produce
the same order the jsonb path would. Ordering on `doc #> '{path}'` unconditionally is correct and
loses the index; ordering on a type-bucketed expression mirroring BSON's order is what {O} §2
proposed for the seam and would satisfy both. Either way the choice must not depend on whether a
column happens to exist.

*Register note (resolved)*: `BF-16` had been used twice — the other session landed
`food.hidden` as BF-16 and a plaintext-token defect as BF-17 while this session was adding
the driver-7 getMore entry under the same number. The pre-release entry was renumbered to
**BF-18**; the findings below take **BF-19** and **BF-20**.

**Non-vacuity.** The same comparison on a single-typed corpus:

```
non-vacuity: single-typed corpus, postgres orders both fields THE SAME (comparison is not always red)
```

So the comparison is not simply always red. **This finding has non-vacuity evidence.**

### 6.2 A `Date`-valued filter bound compares differently on each backend — proposed **BF-20**, low

`sql.js` `scalarize()` converts a `Date` to `value.toISOString()` on its way into SQL, for a stated
and correct reason: `pg` would otherwise send something the jsonb comparison cannot use. But
MongoDB compares a BSON `Date` **only** to a BSON `Date`, so the same AST node asks two different
questions:

```
created_at gte <Date>          mongod -      postgres 1,2    DIFFERS
created_at gte <ISO string>    mongod 1,2    postgres 1,2
```

Against documents whose `created_at` is an ISO **string** — which is what every Nightscout
collection stores — a `Date` bound matches **nothing** on MongoDB and **everything in range** on
PostgreSQL. This is {F}'s class B, silent cross-type comparison, moved out of the filter language
and into the value adapter, where the type-bracketing `CASE` cannot see it.

**Not reachable today, and that is most of the grade.** Every shipping caller of `findFiltered`,
`count` and `deleteMany` was checked; none passes a `Date`. `lib/server/query.js` emits
`opts.useEpoch ? minDate : new Date(minDate).toISOString()` — an epoch number or an ISO string,
never a `Date` object. It is recorded because `findFiltered` is a published interface, `scalarize()`
accepts a `Date` deliberately rather than rejecting it, and the conversion is silent.

*Proposed fix*: either `scalarize()` refuses a `Date` on a jsonb comparison (the seam's stated rule
is that no member accepts a driver object, and `Date` is the same class of problem as `ObjectId`),
or the AST grows a date type that both adapters honour.

### 6.3 Checked and clean

Reported so the absence is on the record rather than unexamined.

- **`count()`** — 5 probes over 40 documents (everything, an equality, an ordered comparison, an
  `exists false`, an `eq null`): identical on both backends, 40/19/11/0/9.
- **The `re` operator** — 14 patterns including anchors, character classes, the `i` flag, `m` and
  `s` newline modes, `^.*$` and `\d` against a corpus holding a number, a null, an absent key and
  an embedded newline: **14/14 identical**. This exercises `toSql`'s newline-mode lookup, its
  `~`/`~*` operator choice, and its `jsonb_typeof = 'string'` guard, all of which {F} §5 recorded
  as untested.
- **`skip`/`limit` edges** — `skip: 5`, `skip: 20` (past the end), `skip: 3, limit: 4`,
  `limit: 1000`, `skip: 'abc'`, `limit: 2.7`: identical. `skip: -3` raises on both (`51024` vs
  `2201X`), so it is an error-message difference, not a correctness one.

---

## 7. Honest limits

- **One collection.** T2.5 implements `entries` and nothing else, so everything above is measured
  on `entries`. The BF-19 exposure is sized against a census that says it does not fire on
  `entries`; the collections it *does* fire on have no PostgreSQL implementation to test yet. That
  makes §6.1's sizing a statement about the corpus, not a prediction about T2.6.
- **Nothing here was driven over HTTP.** Claim 2 reaches `lib/server/entries.js` `list()`, which is
  the shipping v1 read path, but express, the router and the response serialiser are not in the
  loop. §6.1's reachability argument is read from `parseSort` rather than observed against a
  running server, exactly as {O} §4 had to say about BF-13. **A maintainer should confirm
  `GET /api/v3/entries?sort=sgv` against a real deployment before §6.1 is treated as settled.**
- **One PostgreSQL version (16.14), one `mongod` (7.0.43), one driver (7.6.0), standalone, small
  collections.** §3's loss counts are properties of a plan the planner chose for this data at this
  size; the *defect* does not depend on the version, the exact documents lost certainly do.
- **§3's 1000-document corpus is one tie group of 1000.** Real `devicestatus` tie groups reach 69
  ({O} §3.2) and none exceeds one page. A corpus of many small groups straddling page boundaries is
  the realistic shape and was not built; the number measured here is therefore an upper bound on
  loss per sweep, not an estimate of it.
- **The write path is barely touched.** `insertOne` is used to seed, and `replaceOne`, `updateOne`,
  `bulkUpsert`, `deleteOne` and `deleteManyOr` were not differentially tested at all. Three methods
  (`insertMany`, `updateMany`, `replaceFiltered`) throw by name on PostgreSQL by design and were not
  exercised.
- **§5 has no non-vacuity evidence and cannot easily have any** (see the note in that section).
  §1–§4 and §6.1 all do.
- **Nothing here tests RLS or tenant isolation.** Every query runs under the single-tenant binding.
  The run does connect as a `NOSUPERUSER NOBYPASSRLS` role, so the policy is enforced rather than
  silently bypassed — but that is a precondition for the measurements above, not a measurement.
- **The `re` result is over 14 hand-chosen patterns, not a randomised sweep.** {F} §5's note that
  the allowed regex subset still needs writing down is not closed by it.
- **A path in a code comment does not exist.** `filter.js`'s `toSql` comment points at
  `specs/generated/postgres/index.json` for the columnTypes map; the emitted file is at
  `lib/storage/postgres/generated/index.json`, which is where `postgres-storage.js` actually reads
  it from. Cosmetic, and mentioned only because the comment is the one place a reader is told where
  the map comes from.
- **`?count=` was measured at the module boundary, so the exact HTTP status of the `2201W` was not
  observed.** It is reported as "an error where MongoDB returns rows", and the 500 is an inference
  from the error escaping `list()`.

## 8. Reproduction

```sh
git -C <crm-seam> worktree add --detach <crm-verify> 7cc03cda
cd <crm-verify> && npm install

docker run -d --name verify-mongo --ulimit nofile=64000:64000 -p 27021:27017 mongo:7
docker run -d --name verify-pg -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15436:5432 postgres:16-alpine

cd tools/qc && npm install
PGPASSWORD=… WORKTREE=<crm-verify> node --expose-gc pg-backend-arm.js
# or one section: filter | limit | order | project | extra | materialise
```

`--expose-gc` is required by the materialisation section, which refuses to run without it.
The harness exits `2` with instructions if `PGPASSWORD` is unset and stores no credential anywhere:
the unprivileged role it connects as is created per run by
[`tests/support/postgres.js`](../../externals/work/crm-verify/tests/support/postgres.js) with a
password that exists only in the process's memory.
