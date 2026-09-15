# Design — how ordering crosses the storage seam

Date: 2026-09-15 · Status: **proposal**, for whoever owns the adapter
Evidence: [ordering and pagination](../60-research/seam-ordering-and-pagination-2026-09-14.md) ·
[`tools/qc/order-arm.js`](../../tools/qc/order-arm.js)

The filter got an AST. Ordering did not, and T2.5 landed a PostgreSQL backend without one — it
has an `orderBy` in `lib/api3/storage/pgCollection/sql.js` that solves one of the three
sub-problems correctly and records a second as a known difference. This is the missing design:
what the three sub-problems are, what is already settled, and what remains a decision.

> **Scope.** This is about *ordering*, not pagination strategy. Keyset pagination is a better
> answer than `skip`/`limit` for both backends and is out of scope here — though §4 notes that
> the tiebreak below is its precondition.

---

## 1. The interface change

`findFiltered(col, ast, { sort, … })` currently takes `sort` as a **MongoDB sort document** and
hands it to `cursor.sort()`. That is a driver object crossing an interface whose stated purpose
is that driver objects do not cross it.

Ordering should become an AST the same way filters did:

```js
// lib/storage/order.js — sibling of lib/storage/filter.js
{ terms: [ { field: 'date', direction: -1 }, … ] }
toMongoSort(order)  -> { date: -1, _id: -1 }
toOrderBy(order, { columns, jsonbColumn })  -> ' ORDER BY "date" DESC NULLS LAST, id DESC'
```

Two adapters, one normaliser, and the same differential-test treatment the filter AST got. The
normaliser is where §4's tiebreak lives, so that **neither backend can forget it**.

---

## 2. Sub-problem A — null and missing placement · **settled, and already implemented**

MongoDB sorts missing and null **together, first** ascending. PostgreSQL defaults to `NULLS
LAST`, and a missing jsonb path is SQL `NULL`.

Emit `NULLS FIRST` ascending and `NULLS LAST` descending. T2.5's `orderBy` already does exactly
this, with the reasoning in a comment. Nothing further is needed.

---

## 3. Sub-problem B — cross-type ordering · **open, and harder than it looks**

Ten documents, one field holding one value each, ascending, measured against `mongod` 7 and
PostgreSQL 16:

```
BSON  asc:  null | -5 | 0 | [1] | 1000 | "120" | "a" | {a:1} | false | true
jsonb asc:  null | "120" | "a" | -5 | 0 | 1000 | false | true | [1] | {a:1}
```

Three distinct disagreements, not one:

1. **Number and String are transposed.** BSON: `Null < Number < String`. jsonb:
   `Null < String < Number`.
2. **Boolean moves.** BSON puts Boolean *after* Object; jsonb puts it *before* Array and Object.
3. **MongoDB does not give arrays a type rank at all.** `[1]` sorted between `0` and `1000` —
   an array is compared **by its minimum contained element** ascending. jsonb ranks arrays as a
   type, above every scalar.

The third one is why "write a `bson_type_rank()` function" is not a complete answer. A rank
function reproduces 1 and 2 for scalars and **cannot** reproduce 3 for arrays without
`jsonb_array_elements` and an aggregate — per row, per sort term.

### 3.1 Three options

| | what it does | cost | what it gives up |
|---|---|---|---|
| **O1** type-bucketed key | leading `bson_type_rank(doc#>'{f}')` term, then the typed value | an `IMMUTABLE` function and a composite expression index per sortable field | still wrong for arrays unless the element-minimum rule is also implemented |
| **O2** declare sortable fields single-typed | restrict `?sort=` to schema-declared single-typed fields; `HTTP 400` otherwise | a schema annotation and a validation branch | clients sorting on an undeclared field |
| **O3** accept and document | what T2.5 did | none | silent divergence when a sort key is mixed-typed |

### 3.1b The strategy T2.5 shipped is a fifth one, and it is the best of them — conditionally

`order-arm.js` measured four translations and none matched. T2.5 shipped a **fifth** that was not
in that set. From the emitted DDL:

```sql
"sgv" numeric GENERATED ALWAYS AS (
  CASE WHEN jsonb_typeof(doc #> '{sgv}') = 'number'
       THEN (doc #>> '{sgv}')::numeric END) STORED
```

`orderBy` sorts on that column whenever one exists. Measured against `mongod` 7 with
[`tools/qc/typeguard-arm.js`](../../tools/qc/typeguard-arm.js):

**On single-typed data it matches mongod exactly, ascending and descending.** That is the first
translation of the five to do so, and the guard is what earns it — without it a mixed column
raises 22P02 (divergence class D).

**On mixed-typed data it does not merely differ, it inverts.** The guard rejects a wrong-typed
value to SQL `NULL`, which is indistinguishable from an absent key and from an explicit JSON
null, so under `NULLS FIRST` it sorts to the **front** — where MongoDB sorts it *after* every
number:

```
sort {sgv: 1}
  mongod                   null | ABSENT | 40 | 100 | 400 | "120" | "high" | true
  pg, typed column (T2.5)  "120" | "high" | null | ABSENT | true | 40 | 100 | 400
```

A string `sgv` moves from last to first. The emitted DDL already warns that a column built from
`->>` cannot distinguish an absent key from an explicit null, and directs `$exists` to read
`doc #> '{path}'` instead. **The same warning applies to `ORDER BY` and is written down nowhere**
— and unlike `$exists`, ordering has no alternative expression that would be correct, because the
jsonb path diverges too (it carries jsonb's type order, not BSON's).

This is measured, not derived: the harness reports `matches` on a single-typed corpus in both
directions, so a `DIFFERS` is a fact about the data rather than about the harness.

### 3.2 Recommendation, and the measurement that decides it

**O2, falling back to O1 only if the corpus shows a mixed-typed sort key in real data.**

§3.1b turns this from a preference into a measurement: the translation T2.5 already ships is
*exactly correct* under O2's condition and *inverted* without it. So O2 is not a restriction
bolted onto the adapter — it is the precondition the adapter is already assuming. Enforcing it
makes an existing assumption checkable; declining to enforce it leaves a silent inversion behind
a `200`.

O2 is cheap, it is enforceable, and it converts a silent wrong answer into a loud rejection —
which is the trade this project has made everywhere else (BF-04's allowlist, v3's `parseLimit`).
O1 is real work and buys nothing if no deployment stores a mixed-typed sort key.

T2.5's `orderBy` comment asserts the favourable case:

> Every sort this code path issues is on a field that is one type in practice (`date`,
> `srvModified`, `identifier`, `created_at`), so it does not bite today.

That is an empirical claim, and **it is being measured against the 11-site corpus** rather than
taken on trust — see `docs/60-research/sort-key-typing-corpus-2026-09-15.md` when it lands. Two
things to hold in mind while reading it:

- The claim is about *the fields this code path issues*. API v3 lets the **client** choose the
  sort key via `?sort=`/`?sort$desc=`, so the enforceable set is not the same as the observed
  set. O2 is what closes that gap; without it the comment describes today's callers, not
  tomorrow's requests.
- A clean corpus result supports O2. It does **not** support O3, because O3 leaves the client
  free to sort on a field nobody measured.

---

## 4. Sub-problem C — ties and total order · **settled; one line, both backends**

`ORDER BY` is not a total order unless the terms uniquely identify a row, and neither engine
promises stability among equal keys. [BF-13](nightscout-backfix-register.md) is this defect on
MongoDB: when v3's whole tiebreak chain ties, `skip`/`limit` paging lost 7 of 12 documents and
duplicated two, deterministically. Sized against the corpus it is concentrated in `devicestatus`
— median **23.46** expected straddles per paginated sweep, against 0.01 for `entries`.

**The normaliser appends `_id` (ascending or matching the last term's direction) as a final
term, always, for every backend.** `_id` is present and unique by construction, so the order
becomes total and both engines become deterministic.

T2.5's `orderBy` emits only the caller's terms, so BF-13 reappears on PostgreSQL unless this
lands in the shared normaliser rather than in either adapter.

This is also the precondition for keyset pagination later: a total order is what makes
`WHERE (k, _id) > (:last_k, :last_id)` well defined.

---

## 5. What this leaves for the adapter owner

| | status |
|---|---|
| null/missing placement | **done** in T2.5 |
| `_id` tiebreak in a shared normaliser | **not done** — one line, closes BF-13 on both backends |
| `sort` as an AST rather than a driver object | **not done** |
| typed generated column + guard | **done** in T2.5, and correct under single-typed data |
| cross-type ordering | **decide O1/O2/O3** — see §3.1b and the corpus measurement |

## 6. Honest limits

- **§3.1b tested one field, one numeric column, one sort term.** `sgv` with eight values. Text
  columns, compound sorts and descending-with-`NULLS LAST` on a text column were not measured,
  and a compound sort could interact with the guard in ways a single term cannot show.
- **O1 is described, not prototyped.** No `bson_type_rank()` has been written or benchmarked,
  and the index cost of a composite expression sort key is unmeasured.
- **The array rule is established for one shape.** `[1]` versus scalars, ascending. Descending
  uses the array's *maximum*, which follows from the documented rule but was not measured here.
  Nested arrays and arrays of mixed type were not tested at all.
- **Collation is untouched.** Both engines were compared with default collation and ASCII
  values. MongoDB's default is binary; PostgreSQL's depends on the database's `LC_COLLATE`, so
  string ordering can diverge between two PostgreSQL deployments before either is compared to
  MongoDB. Nothing here measures that, and it should be measured before any string field is
  declared sortable under O2.
