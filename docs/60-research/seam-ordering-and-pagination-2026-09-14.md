# Ordering across the seam — and a live pagination defect in API v3

Date: 2026-09-14. Status: findings + tooling. **Read-only — no shipping code changed.**

Closes the "sort, limit, skip and projection are not covered — only the filter" gap that both
[three-arm validation](seam-filter-ast-three-arm-validation-2026-09-14.md) §5 and the
[seam interface](../30-design/nightscout-storage-seam-interface-2026-09-14.md) §8.5 record.

**Tooling**: `tools/qc/order-arm.js`. Reproduces everything below in one run.

---

## 1. The seam gap: the filter got an AST, the sort did not

`lib/storage/filter.js` gives filters a backend-neutral AST with two adapters. **There is no
equivalent for ordering.** `findFiltered(ast, { sort, limit, skip, … })` passes `sort` straight
to the driver:

```js
if (o.sort) cursor = cursor.sort(o.sort);      // find.js:120
```

So `sort` is **a MongoDB sort document crossing an interface whose stated first rule is that no
member accepts or returns a driver object** ({S} §4.1 rule 1). It is invisible while MongoDB is
the only backend, and it is the kind of defect this programme has repeatedly found late.

## 2. There is no obvious correct translation — all four naive ones are wrong

Nine documents, `sgv` jsonb-only, sorted ascending. `mongod` 7.0.43 against PostgreSQL 16.14:

```
corpus   1:100  2:80  3:null  4:(absent)  5:9  6:1000  7:"120"  8:true  9:100 (ties with 1)

sort {sgv: 1}
  mongod              3 4 5 2 1 9 6 7 8
  text (naive)        1 9 6 7 2 5 8 3 4   DIFFERS
  numeric cast        ERR 22P02           raises on mixed types
  jsonb native        3 7 5 2 1 9 6 8 4   DIFFERS
  text + NULLS FIRST  3 4 1 9 6 7 2 5 8   DIFFERS
```

**Not one strategy matches, in either direction.** Three separate rules have no SQL equivalent:

1. **MongoDB sorts missing and null together, first ascending.** Postgres defaults to
   `NULLS LAST`. Adding `NULLS FIRST` fixes *that* and still leaves the order wrong.
2. **BSON has a total order across types** — `Null < Number < String < Boolean` — so `true` sorts
   after `"120"` sorts after `1000`. `doc->>'f'` throws the types away and compares text, so
   `1000 < 120 < 80 < 9`. `doc->'f'` uses jsonb's own ordering, which is a *third* order.
3. **Casting is not available as a fallback**, because a mixed-type column makes `::numeric`
   raise 22P02 — the same class D failure the filter adapter has.

**So ordering needs a design, not a one-line translation**, and it needs one before T2.5.
A reasonable shape is to emit a type-bucketed sort key mirroring BSON's order, but that is a
proposal, not a finding, and it belongs to whoever owns the adapter.

## 3. A live defect in API v3, found by the same harness

> **This is not about the seam and does not need a tenancy decision.** Registered as **BF-13**.

API v3 exposes `skip` (`lib/api3/generic/search/input.js:191-206`; **v1 does not**), and
`parseSort` builds the sort chain:

```js
if (req.query.sort)  sort[req.query.sort] = sortDirection;
sort.identifier  = sortDirection;
sort.created_at  = sortDirection;
sort.date        = sortDirection;
```

Those three tiebreaks look sufficient. **They are not, when every key in the chain ties.**
Twelve documents with **no `identifier`** sharing one `created_at` and one `date` — a batch
import of legacy data — paged three at a time:

```
  no indexes                   lost  7/12  [1 2 3][1 3 6][1 3 7][1 3 7]
                               plan: SORT <- COLLSCAN
  v3's ensureIndexes           lost  7/12  [1 2 3][1 3 6][1 3 7][1 3 7]
                               plan: SORT <- COLLSCAN
  entries-like                 lost  7/12  [1 2 3][1 3 6][1 3 7][1 3 7]
                               plan: SORT <- COLLSCAN
  compound matching the sort   lost  0/12  [1 2 3][4 5 6][7 8 9][10 11 12]
                               plan: LIMIT <- FETCH <- IXSCAN
```

**Seven of twelve documents are never returned, and two are returned three times.**
Deterministic: identical across every trial, not a race.

**It cannot be fixed by indexing.** Only a compound index matching the sort *exactly* produces a
stable `IXSCAN` — and the sort's leading key is chosen by the client at request time (`?sort=`),
so that index cannot exist in general. Under every index set Nightscout actually creates, the
plan is a blocking `SORT` over a `COLLSCAN`, which MongoDB does not promise to make stable among
equal keys, and each `skip` re-runs the query.

### 3.1 The precondition, stated precisely

It is narrower than "paging is broken", and saying so matters:

| shape | result |
|---|---|
| identifier-less, **same** `created_at` **and** `date` | **7/12 lost** |
| unique `identifier` present | 0/12 lost — safe |
| identifier-less, **distinct** `created_at` | 0/12 lost — safe |

So all three must hold: **no `identifier`**, **tied `created_at`**, **tied `date`**. That is a
bulk import or migration that stamped one timestamp across many documents, on a site old enough
to hold pre-`identifier` records. Real, and specific — not every deployment, and not every query.

It also fires on the **default path**: with no `?sort=` at all the chain is just
`{identifier, created_at, date}`, so a client simply paging a collection is exposed without
having asked for an unusual sort.

### 3.2 The fix is one line

```js
sort._id = sortDirection;      // always present, always unique
```

`_id` makes the order **total**, so the blocking sort becomes deterministic and paging is exact —
verified: `lost 0/12`, `[1 2 3][4 5 6][7 8 9][10 11 12]`.

**Why this and not an index or a cursor:** it costs nothing, needs no schema change, and works
regardless of which key the client sorts by. Cursor-based pagination (`find[_id][$gt]`, which the
[operator census](v1-operator-census-2026-09-14.md) §3.2 shows one client already uses) is the
better long-term answer and a much larger change.

**Carry it across the seam.** Whatever ordering translation §2 produces must also append a
unique final key, or the same defect reappears on PostgreSQL — where a blocking sort is likewise
free to reorder ties.

## 4. Honest limits

- **`limit` and `projection` are still not differentially tested.** This covers `sort` and the
  `skip`+`limit` interaction only.
- **One `mongod` version, standalone, small collections.** Sort stability among ties is
  explicitly not promised by MongoDB, so the *defect* does not depend on the version; the exact
  documents lost would differ.
- **Nothing here was run against a live Nightscout server.** The v3 sort chain is reproduced from
  `parseSort`, and the shapes are synthetic. **A maintainer should confirm against a real
  deployment before this is treated as settled** — the reproduction is a strong prediction about
  the endpoint, not an observation of it.
- **No claim is made about how many deployments hold the triggering shape.** The corpus was not
  queried for identifier-less documents with tied timestamps, and it should be before anyone
  sizes the impact.
- **The §2 ordering strategies are the ones a person would plausibly write**, not an exhaustive
  search. A correct translation may well exist; none of the obvious four is it.
