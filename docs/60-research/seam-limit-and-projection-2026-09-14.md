# `limit` and `projection` across the seam — and two live API defects

Date: 2026-09-14 · Harness: [`tools/qc/shape-arm.js`](../../tools/qc/shape-arm.js)
Arms: real `mongod` 7 · real PostgreSQL 16 · the shipping `fieldsProjector.js`

Closes the last gap recorded in
[seam ordering and pagination](seam-ordering-and-pagination-2026-09-14.md) §4:

> **`limit` and `projection` are still not differentially tested.** This covers `sort` and the
> `skip`+`limit` interaction only.

**Nothing here is a seam regression.** Both defects reproduce on `origin/dev` by the same route;
the pre-seam code chained `this.limit(parseInt(opts.count))` onto a cursor and reached the
identical driver call. The seam's contribution is that the behaviour now sits in one function
instead of six, which is how it became measurable.

---

## 1. Three of `findFiltered`'s six options are driver objects

```js
findFiltered(col, ast, { sort, limit, skip, projection, options, readOptions })
```

`sort` was the subject of the ordering report. `projection` and `readOptions` are the same
problem, and `limit` is the interesting one because it *looks* like a scalar and therefore looks
safe. `.limit(n)` is not `LIMIT n` for every `n`, and the values that differ are values real
clients send.

---

## 2. `limit`: `count=0` means *unbounded*

API v1 builds its limit in five places with one expression
(`lib/server/entries.js:56` and siblings in `treatments.js`, `activity.js`, `devicestatus.js`,
`lib/authorization/storage.js`):

```js
limit: opts && opts.count ? parseInt(opts.count) : undefined
```

A truthiness test **on a string**, then `parseInt`. Measured against a ten-document collection:

| `?count=` | `parseInt` | mongod | postgres | |
|---|---|---|---|---|
| `3` | 3 | 3 rows | 3 rows | match |
| **`0`** | **0** | **10 rows** | 0 rows | **differs** |
| `abc` | NaN | 10 rows | (no clause emitted) | — |
| **`-3`** | **-3** | **3 rows** | `ERR 2201W` | **differs** |
| `2.7` | 2 | 2 rows | 2 rows | match |
| `1e2` | **1** | 1 row | 1 row | match |
| `` (empty) | undefined | 10 rows | 10 rows | match |

Three separate findings:

**`count=0` returns the entire collection.** `'0'` is a non-empty string, so it passes the
truthiness test; `parseInt` yields `0`; and **MongoDB defines `.limit(0)` as "no limit"**. A
client asking for nothing gets everything. On PostgreSQL `LIMIT 0` means what it says, so this
is also a real translation divergence — but it is a live bug first.

**`count=-3` silently becomes `count=3`.** MongoDB reads a negative limit as legacy
single-batch semantics and returns three documents. PostgreSQL raises `2201W`. There is no
translation that preserves this; it should be rejected instead.

**`count=1e2` returns one document, not a hundred**, because `parseInt('1e2')` stops at the `e`.
Minor, and recorded so the fix covers parsing and not just the zero case.

The `abc` row is marked `—` rather than `match`: PostgreSQL never saw a clause because the
harness declined to emit `LIMIT NaN`. That is the harness's choice, not agreement, and counting
it as agreement would flatter the result.

### 2.1 `toSafeInt` is faithful, and its default is the dangerous value

The seam added `toSafeInt(value, default)` around the driver call. It changes exactly one of the
above: `NaN → 0`. Since `.limit(0)` and `.limit(NaN)` are both unbounded on mongod, **behaviour
is unchanged** — the seam reproduced the old semantics correctly.

Worth stating anyway: `findFiltered` calls `toSafeInt(o.limit, 0)` and `0` is precisely the value
that means *no limit*, so the fallback for unparseable input is an unbounded read. `findMany`, on
the same file, defaults to `1000`.

### 2.2 Sized against the client corpus — and the measurement downgrades it

[`tools/qc/v1_count_census.py`](../../tools/qc/v1_count_census.py), same method and same limits
as the operator census: it reads client **source**, not request logs, because there are no
request logs. **274 `count=` occurrences across 10 projects.**

| kind | n | share |
|---|---:|---:|
| literal | 236 | 86.1 % |
| dynamic (computed at request time) | 25 | 9.1 % |
| prose (a `?count=` inside a comment or doc) | 11 | 4.0 % |
| other | 2 | 0.7 % |

**No client sends a literal `count=0`.** Literal values run `1, 2, 3, 5, 10, 20, 24, 50, 100,
288, 500, 1000, 1500, 10000, 100000, 9999999`.

That does not clear the defect — the literal arm is the arm least able to see it, since a count
that can be zero is a count that is computed — but it does change the grade. Two things point
the same way:

1. **Nothing in the corpus reaches it today.** The exposure is the 10 % of call sites that build
   the count at runtime (`'&count=' + n`), where nothing bounds the value away from zero and an
   empty window or cleared preference produces zero by construction. `oref0`, the closed loop,
   has four such sites. But that is a *latent* path, not an observed one.
2. **An unbounded read is not a novel load for this server.** Clients already ask for everything
   on purpose: `count=100000` appears 4 times and `count=9999999` once. A deployment that
   survives those survives `count=0`.

So BF-14 is **medium**, not high: it returns no wrong data, and no shipping client triggers it.
It stays in the register because a bounded request producing an unbounded read is a defect
whoever typed the URL — and because the fix is to adopt code that already exists.

The classifier earns a note. A first pass put 16 occurrences in an `empty` bucket; they were
`'&count=' + n`, cut off at the quote — the most dynamic shape there is, counted as the least.
A second pass then swept up prose like `// If "?count=" is present` as dynamic. Both were
corrected before the number above was written; the literal share fell from a misleading 86 % of
a mis-bucketed total to 86 % of a correct one, and the dynamic share moved 5.8 % -> 13.1 % ->
9.1 %.

### 2.2 API v3 already contains the fix

`lib/api3/generic/collection.js:76` validates properly — bounds-checked against
`API3_MAX_LIMIT`, `HTTP 400` on `0`, `abc` or a negative, and a sane default when absent. v1 is
the outlier. The backfix is to give v1 the validation v3 already has, not to invent one.

Recorded as **BF-14**.

---

## 3. `projection`: missing keys, nested keys, and a second expression language

### 3.1 The same missing-vs-null divergence, now in the output

| case | mongod | naive `jsonb_build_object` |
|---|---|---|
| include `sgv`, field present | `{"_id":1,"sgv":10}` | same |
| include `sgv`, **field absent** | `{"_id":9}` | `{"_id":9,"sgv":null}` |
| `uploader.battery`, parent present | `{"uploader":{"battery":80}}` | same |
| `uploader.battery`, **leaf absent** | `{"uploader":{}}` | `{"uploader":{"battery":null}}` |
| `uploader.battery`, **parent absent** | `{}` | `{"uploader":{"battery":null}}` |
| `uploader.battery`, **parent null** | `{}` | `{"uploader":{"battery":null}}` |

MongoDB omits the key; SQL supplies an explicit `null`. This is
[three-arm](seam-filter-ast-three-arm-validation-2026-09-14.md) class A moved from the predicate
into the result shape, and it reaches clients: `'sgv' in doc` and `doc.sgv !== undefined` both
flip. Mongo produces **three** distinct shapes for a dotted path depending on where the chain
breaks, and a single SQL expression produces one.

The one shipping caller is safe: `lib/server/profile.js:203` projects `{_id: 1, startDate: 1}`,
and both are always present. So this is a translation requirement for T2.5, not a live bug.

### 3.2 A find() projection is a whole query language

Probed against mongod directly:

```
mix include + exclude     REJECTED: Cannot do exclusion on field type in inclusion projection
aggregation expression    { doubled: { $multiply: ['$sgv', 2] } }  ->  {"doubled":20}
$literal                  {"tag":"x"}
$cond                     {"high":"ok"}
```

Since MongoDB 4.4 a `find()` projection accepts aggregation expressions. So `projection` is not
a field list crossing the seam — it is a **second, unmodelled expression language**, and a wider
one than the filter AST that took this programme a month to pin down. `find.js` half-knows this:
it calls `assertNoQueryJavascript({$expr: projection})`, a guard against one abuse of a language
it otherwise does not model.

**This surface is not client-reachable and should not be reported as though it were.**
`fieldsProjector.js` builds `projection[field] = 1` — the *value* is always `1`, so no client can
inject an expression. The exposure is architectural: the seam's published interface accepts it,
so any future caller may pass one and no backend but MongoDB could honour it. T2.5 should narrow
`projection` to a field list, which is all any caller uses.

### 3.3 `?fields=uploader.battery` returns an empty document, HTTP 200

Client-reachable, and found by running the shipping module rather than reading it.

v3 projects in two stages. `storageProjection()` goes to the driver, so MongoDB's dotted-path
rules apply and a **nested** document comes back. `applyProjection(doc)` then deletes any
**top-level** key not string-equal to something the client typed. A dotted request survives stage
one and is destroyed by stage two:

```
?fields=uploader.battery
  storageProjection  {"uploader.battery":1,"identifier":1,"srvCreated":1,"created_at":1,"date":1}
  _id 1  from driver           {"_id":1,"uploader":{"battery":80}}
         after applyProjection {}                 <- driver returned uploader; DESTROYED
  _id 6  from driver           {"_id":6,"uploader":{}}
         after applyProjection {}                 <- driver returned uploader; DESTROYED
```

The data was read, paid for, and thrown away. The client gets `200` and `{}`.

`uploader.battery` is not a contrived path — it is the canonical nested field in Nightscout, and
`devicestatus` is the collection people query for it. Comma-separated top-level fields
(`?fields=sgv,type`) are unaffected, which is why this has not been noticed.

Recorded as **BF-15**.

*Checked before claiming*: the system fields that `storageProjection` adds and `applyProjection`
removes are **not** dead work — `col.resolveDates(doc)` consumes them between the two stages
(`lib/api3/generic/search/operation.js:46-47`).

---

## 4. Honest limits

- **The PostgreSQL arm here is a strawman by construction.** For ordering there were four
  plausible translations and the interesting result was that *all* of them differed. For
  projection there is one obvious naive translation and the interesting result is *where* it
  differs. Do not read §3.1 as "PostgreSQL cannot do this" — `jsonb_strip_nulls` and a
  path-existence guard reproduce Mongo's shape. The point is that nobody has written that yet,
  and the seam's interface does not ask anyone to.
- ~~**`readOptions` is still untested.**~~ **Closed** by
  [readOptions across the seam](seam-readoptions-2026-09-15.md). The guess in this bullet —
  "nothing in it is likely to be a correctness defect" — was wrong: driver 7 abandons the bound
  precisely on `.limit(0)`, which is BF-14's own path, so the two compound (BF-16).
- **BF-14 is sized now** (§2.2), and the measurement **downgraded it**. See below.
- The `$slice`-on-a-non-array probe returned the whole document rather than an error, which is
  unexplained and not pursued — it is outside what any caller sends.

## 5. Reproduction

```sh
docker run -d --name seam-qc-mongo -p 27019:27017 mongo:7
docker run -d --name seampg -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15434:5432 postgres:16-alpine
cd tools/qc && npm install
PGPASSWORD=… node shape-arm.js
```

No credential is stored in the harness; it exits `2` with instructions if `PGPASSWORD` is unset.
