# T1.1 — the storage seam: interface definition and call-site classification

Date: 2026-09-14. Status: draft for maintainer discussion. **Design only — no code changed.**
Task T1.1 of the [execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md).
Measured against `origin/chore/nightscout-modernization` @ `0a4109f6` (D9's base).

**Deliverables**: this document, plus
`reports/storage-seam/t1-1-call-site-classification.tsv` (every site, classified) and the two
scripts that produce it, so the count can be re-derived rather than trusted.

---

## 1. The count was wrong, twice

| count | method | why it was wrong |
|---|---:|---|
| "~30 call sites" | {M} §2.5, by inspection | an estimate, never enumerated |
| 68 | grep excluding `.find(` | dodging `Array.find` also dropped every `col.find(filter)` — the most common read in the codebase |
| 82 | grep excluding `.find(<identifier>)` | the same exclusion still swallowed `col.find(filter)` |
| **85** | exclude only jQuery selectors and `Array.find` callbacks, then remove one verified DOM false positive | — |

**85 storage call sites across 20 files.** `lib/plugins/pluginbase.js:45`
(`container.find(pillName)`, jQuery over `majorPills`) is the removed false positive.

## 2. The finding that changes the task: a third of it is already done

The sites are not 85 pieces of equivalent work. They stratify:

| tier | sites | what it is |
|---|---:|---|
| **T0 · interface consumers** | **15** | `lib/api3/generic/*` and `mongoCachedCollection` already call `col.storage.*` / `baseStorage.*`. **They never touch the driver.** |
| **T1 · the interface + its Mongo adapter** | **14** | `mongoCollection/{index,find,modify}.js` — this *is* a storage interface plus its MongoDB implementation, already written |
| **T2 · v1 domain modules** | **40** | `lib/server/{entries,treatments,devicestatus,profile,food,activity,aggregate}.js`, `lib/authorization/storage.js`, `lib/api/entries` — raw driver |
| **T3 · socket write path** | **15** | `lib/server/websocket.js` — raw driver (§5) |
| **T3 · factory** | **1** | `lib/storage/mongo-storage.js:216`, `createIndex` |

**API v3 is roughly three-quarters of a seam that already exists.** `MongoCollection`
(`lib/api3/storage/mongoCollection/index.js`) exposes `findOne`, `findOneFilter`, `findMany`,
`insertOne`, `replaceOne`, `updateOne`, `deleteOne`, `deleteManyOr`, `version`,
`getLastModified` and `identifyingFilter` — a real interface, with a real decorator
(`mongoCachedCollection`) already layered over it.

**So T1.2 is not "design an abstraction and apply it to 85 sites". It is "finish the
abstraction that api3 already has, then bring v1 to it".** That is a materially smaller and
lower-risk task than the plan assumed, and it changes the sequencing recommendation in §7.

## 3. Classification

Full table in `reports/storage-seam/t1-1-call-site-classification.tsv`.

| class | sites | meaning |
|---|---:|---|
| **fits** | **39** | maps onto the existing interface with no semantic loss |
| **needs-escape-hatch** | **27** | works, but needs a capability the interface must name explicitly |
| **must-change** | **19** | leaks driver semantics the caller must stop depending on |

| | fits | escape-hatch | must-change |
|---|---:|---:|---:|
| T0 consumer | 15 | — | — |
| T1 interface | 5 | — | 1 |
| T1 adapter | 2 | 5 | 1 |
| T2 v1 domain | 6 | 21 | 13 |
| T3 socket | 11 | — | 4 |
| T3 factory | — | 1 | — |

### 3.1 The 19 must-change sites are four root causes, not nineteen problems

| root cause | sites | fix |
|---|---:|---|
| **`query_for(opts)` returns a Mongo filter document** | **9** | entries 44/52, treatments 251/276, devicestatus 129/138, profile 110, activity 120, authorization 88 |
| **`$set` / `$unset` partial updates** | **4** | modify.js 49, websocket 358/411/578 |
| **Literal Mongo filters in domain code** | **2** | food 146 (`$and`), treatments 114 (`$in`) |
| **`ObjectId` construction by the caller** | **2** | entries 179, authorization 100 |
| **Raw collection/cursor handles** | **2** | websocket 749 (`ctx.store.collection()`), mongoCollection/index 65 (`self.col.find()`) |

**Nearly half of the must-change work is one root cause**, and it is a root cause three other
planned tasks already converge on — see §4.2.

### 3.2 The 27 escape hatches, grouped

| capability | sites | Postgres equivalent |
|---|---:|---|
| explicit `upsert` | 7 | `INSERT … ON CONFLICT DO UPDATE` |
| batch upsert (`bulkWrite`) | 5 | `INSERT … ON CONFLICT`, multi-row |
| bare `find` → `findMany` | 5 | — (caller shape only) |
| delete by filter | 2 | `DELETE … WHERE` |
| cursor chaining `.sort().limit()` | 2 | `findMany` args |
| batch insert (`insertMany`) | 2 | multi-row `INSERT` |
| **aggregation pipeline** | **2** | **`GROUP BY` — but see §4.3** |
| projection | 1 | column list |
| `createIndex` | 1 | migrations |

## 4. The proposed interface

### 4.1 Shape

Extends `MongoCollection`'s existing surface; **additions marked NEW**, and each exists because
§3.2 counted sites that need it.

```js
// ---- reads
findOne(identifier, projection?, options?)
findOneFilter(filter, projection?, options?)
findMany({ filter, sort, limit, skip, projection, options })
count(filter)                                   // NEW — the countable half of §4.3
getLastModified(fieldName)

// ---- writes
insertOne(doc, options?)
insertMany(docs, options?)                      // NEW — 2 sites
replaceOne(identifier, doc, { upsert })         // upsert becomes explicit — 7 sites
updateOne(identifier, patch)                    // patch is a plain object, NOT {$set: …}
deleteOne(identifier)
deleteMany(filter)                              // NEW — supersedes deleteManyOr
bulkUpsert(docs, { matchOn })                   // NEW — 5 sites

// ---- declared aggregations, not a pipeline pass-through
aggregate(spec)                                 // NEW, constrained — §4.3

// ---- lifecycle
ensureSchema(collectionSpec)                    // replaces createIndex
version()
```

**Three rules that make it a seam rather than a façade**, each aimed at a specific leak the
classification found:

1. **No member returns or accepts a driver object.** `self.col` becomes private;
   `getLastModified` goes through `findMany`. (T1 must-change ×2.)
2. **`identifier` is opaque.** The caller never constructs an `ObjectId`; `identifyingFilter`
   moves inside the adapter, where it may keep its current Mongo-specific fallback logic.
   (T2 must-change ×2.)
3. **`updateOne` takes a plain patch object.** The adapter decides `$set` versus `jsonb_set`.
   `$unset` becomes an explicit null-or-sentinel convention in the patch — the socket path's
   `dbUpdateUnset` is the only caller and it needs a deliberate decision, not a translation.

### 4.2 The filter representation — the one decision that matters

Nine of nineteen must-change sites are `query_for(opts)` handing a Mongo query document to the
driver. So the filter language *is* the seam, and there is a convergence worth taking:

> **D8 already chose the vocabulary.** API v3 declares exactly nine operators —
> `eq ne gt gte lt lte in nin re` (`lib/api3/generic/search/input.js:111`). **Make that the
> seam's filter AST.** `query_for` becomes `filterFor`, emitting
> `{op, field, value}` nodes with `and`/`or` grouping, in v3's vocabulary.

That single change resolves four planned work items at once:

| item | how it lands |
|---|---|
| **T1.1/T1.2** | 9 of 19 must-change sites |
| **T0.5** (type coercion) | the AST is where the schema-driven coercion table applies |
| **T2.3** (v3's nine operators in SQL) | the AST *is* v3's nine operators |
| **T2.4** (v1 allowlist) | an AST that cannot express an unlisted operator **is** the allowlist — {M} §6.5's security fix falls out structurally rather than being bolted on |

**Recommendation: do the filter AST first, as its own change, before converting any call
site.** It is the highest-leverage piece and everything else gets easier behind it.

### 4.3 Aggregation is the one genuinely hard escape hatch

Two sites — `lib/server/aggregate.js:26` and `lib/api/entries/index.js:520` — pass a pipeline
through. A pipeline pass-through cannot be translated in general, for the same reason v1's
operator pass-through cannot (§3.1 of the plan).

**Do not put `aggregate(pipeline)` in the interface.** Establish what those two callers
actually compute, express each as a named operation (`count`, `groupBy`, …), and implement
those. If the answer turns out to be "arbitrary pipelines", that is a finding worth having
early — it would mean reporting stays MongoDB-only for a while, which is survivable under D4
and should be recorded rather than discovered during T2.5.

## 5. A third write path, not previously named

`lib/server/websocket.js` is 15 sites — the largest single concentration — because it
implements **a complete CRUD API over Socket.IO**: `dbAdd` (`:449`), `dbUpdate` (`:332`),
`dbUpdateUnset` (`:395`), `dbRemove` (`:734`). It carries **its own deduplication logic**
(exact-match then similar-match, `:528`/`:572`) parallel to — not shared with — v1's and v3's.

Consequences the plan did not account for:

- **The seam covers three API surfaces, not two.** Any statement of the form "v1 and v3" in
  {M}, {C} or the plan is incomplete.
- **Dedup semantics exist in three places** and are not obviously identical. Unifying them is a
  behaviour change and must not ride along inside a "no behaviour change" refactor.
- **11 of its 15 sites classify as `fits`** — it is mostly `findOne`/`insertOne`/`replaceOne`,
  so the conversion itself is routine. It is the *dedup* question that needs a decision.

**Recommendation: convert websocket.js last**, and file the dedup unification as its own task
with its own tests.

## 6. What this does not cover

- **`lib/server/query.js` itself** is not in the inventory — it builds filters, it does not
  execute them. It is nonetheless the largest single item of work implied here (§4.2).
- **Read paths that bypass storage entirely** — `ctx.cache` (`lib/server/cache.js`) serves
  `/api/v1/entries` from memory with no driver call ({R} §12.2), so it does not appear as a
  call site while very much being part of the read path.
- **`lib/storage/mongo-storage.js`'s connection/pool/index management** — one `createIndex`
  site is listed, but connection lifecycle, pool configuration and `ensureIndexes` are a
  separate concern from the per-collection interface and need their own design.
- **Transactions.** Nothing in the current code uses them; RLS binding under D3 is
  per-transaction ({DB} §8.2), so the interface will need a transaction scope before T2.5.
  **This is a gap in the interface above and should be closed before T1.2 starts**, because
  retrofitting a transaction scope through 85 call sites twice would be avoidable waste.

## 7. Recommended sequencing, revised

The tiering in §2 changes the order the plan assumed:

1. **The filter AST** (§4.2) — standalone, highest leverage, unblocks four items.
2. **Add the transaction scope** to the interface definition (§6) before any conversion.
3. **Close T1's two leaks** — `self.col`, `getLastModified`. Small, inside api3, low risk.
4. **Convert T2's 40 v1 sites** behind the finished interface. The bulk of the work.
5. **Decide aggregation** (§4.3) — may run in parallel; may produce a "MongoDB-only for now".
6. **Convert T3's socket path** last, with the dedup question filed separately.

**T0's 15 sites need no work at all**, and T1's 14 are mostly already correct — which is the
practical headline: **the conversion is ~55 sites, not 85.**
