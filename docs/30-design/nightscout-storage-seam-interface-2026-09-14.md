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

## 8. The filter AST — built and validated

`tools/seam/filter-ast.js`, validated by `tools/seam/{validate,coverage}.js`.

### 8.1 It is not a new design — v3 already had it

`lib/api3/generic/search/input.js` produces `[{field, operator, value}]` with a top-level
`logicalOperator`, and `parseFilter()` in `mongoCollection/utils.js` is **already its MongoDB
adapter**. So the work is v3's existing model plus the smallest extensions that let v1's real
output be expressed, plus a second adapter.

**Two extensions, each because a measured v1 shape needs it:**

1. **Nested groups.** v3's AST is flat — one `logicalOperator` joins every clause — and v1
   emits top-level `$or` with clause objects. This is the only structural change.
2. **`exists`.** v1 passes `$exists` through and it is not among v3's nine. Added deliberately,
   because the alternative is that v1 queries using it silently stop working.

Everything else maps unchanged: implicit equality → `eq`; `{$gte, $lte}` on one field → two
clauses under `and`; dotted paths → field names containing dots.

**`parseFilter`'s non-array pass-through (`if (!Array.isArray(filterDef)) return filterDef`)
closes for free.** Its only callers are `create`/`patch`/`update`, all passing
`identifyingFilter` — a raw Mongo `{$or:[…]}`. §4.1 rule 2 already moves identifier handling
inside the adapter, so the escape hatch that stops the AST being total disappears with it.

### 8.2 What it deliberately cannot express *is* the feature

There is no `$where`, no `$expr`, no pipeline, no operator escape hatch. Structural validation
runs before either adapter. **An AST that cannot represent an unlisted operator is the
allowlist {M} §6.5 says does not exist today** — so T2.4's security fix is structural rather
than a check somebody has to remember to write. Regex patterns are length-bounded
(`RE_MAX_LEN`), which is the ReDoS mitigation, also structural.

### 8.3 Differential validation: 3,000 randomised filters, both backends

Same AST → `toMongo` → **mingo**, and → `toSql` → **real PostgreSQL 16**, over 300 fixture
documents built to be hostile: every field independently present-or-absent, explicit JSON
nulls distinct from missing keys, empty strings, mixed types.

| run | agreement |
|---|---|
| first | **1668/2000 (83.4 %)** |
| after fixing `nin` | 1961/2000 (98.0 %) |
| after fixing `exists` | **3000/3000 (100 %)** |
| with `re` on plain patterns | 1500/1500 (100 %) |

**The two failures it found are exactly the bugs this method exists to catch**, and both would
have shipped:

1. **`nin` and missing fields.** MongoDB's `$nin` matches a document where the field is absent;
   `NULL NOT IN (…)` is NULL in SQL and matches nothing. 332 disagreements, all one direction.
   Fixed as `(x IS NULL OR x NOT IN (…))`, the same three-valued-logic gap `ne` needed.
2. **`exists` cannot read a generated column.** MongoDB's `$exists` is *key presence*, and a
   generated column is built with `->>`, which returns SQL NULL for **both** an absent key and
   an explicit JSON null — it cannot tell them apart. `doc #> '{path}'` can: jsonb `null` for
   the first, SQL NULL for the second. Verified directly, then fixed so `exists` **always**
   reads the document even when a column exists for that field.

> The second is worth dwelling on, because it is a trap in the §6.3 storage shape rather than
> in this AST: **generated columns are not a faithful projection of the document.** Anything
> that needs to distinguish absent from null must read the jsonb. A hand-written translation
> would very likely have used the column, and the resulting wrongness would have been invisible
> until someone queried a field that is sometimes null.

### 8.4 Coverage against real v1 output

`coverage.js` takes the shapes `lib/server/query.js` actually emits (captured by running it)
and checks each is expressible *and* semantically identical, compared through mingo rather than
by string equality:

```
10/10 v1 filter shapes expressible AND semantically identical
```

implicit equality · injected date bound · range on one field · two fields · top-level `$or` ·
dotted path · `$ne null` · `$in` · `$exists` · `$regex`.

The two `_id` shapes are **not filters** — they are identifier lookups, resolved by §4.1
rule 2's identifier opacity rather than by the AST.

### 8.5 Honest limits

- **mingo is a reimplementation of MongoDB's query language, not MongoDB.** Agreement is strong
  evidence about the AST; it is not proof about MongoDB. Re-running the same harness against a
  real `mongod` is a small change to `validate.js` and should happen before T1.2 lands.
- **The regex result covers a deliberately plain subset** — literals, anchors, character
  classes. Mongo's `$regex` is PCRE-flavoured and Postgres `~` is POSIX; they diverge on lazy
  quantifiers, lookaround and `\d`-style shorthands. **The measured 100 % describes the subset
  we would allow, not the whole language**, and the allowed subset needs to be written down.
- **300 documents, one collection shape.** Sort, limit, skip and projection are not covered —
  only the filter.
- **No tenant predicate is in these filters.** Under D3 the tenant bound comes from RLS, not
  from the AST, which is the point — but it means this validation says nothing about isolation.

## 9. The transaction scope

{S} §6 flagged that the interface had none and that D3's RLS binding is per-transaction.
Confirmed: `set_config('app.current_tenant_id', …, is_local => true)` is transaction-scoped, so
**every tenant-bound operation must run inside a transaction that has been bound.**

```js
store.withTenant(tenantId, async (tx) => { … })   // NEW — required before T1.2
```

**Three findings that make this more than a signature change:**

1. **The safety property differs by backend, and only one of them fails closed.** On Postgres an
   unbound transaction returns **0 rows** ({DB} §8.2) — forgetting the scope is visible and
   harmless. On MongoDB there is no equivalent: an unbound context queries without a tenant
   predicate and **returns everything** ({DB} §7.1). **The MongoDB adapter must therefore assert
   an explicit binding and throw**, to reproduce by hand what RLS gives Postgres for free.
2. **MongoDB transactions require a replica set.** A standalone `mongod` — which many
   self-hosters run — does not support them, and `grep` confirms the codebase uses none today.
   Under D4 the Mongo adapter must therefore degrade to "no transaction, assert the binding",
   and the interface cannot promise atomicity across operations on both backends.
3. **Single-tenant has no tenant.** Under D4 `withTenant` must have a legitimate
   single-tenant mode rather than a fake tenant id, or {M} §11's "never a degraded mode" is
   violated on the first line of the adapter.

**Implication for implementation order**: adding this after T1.2 means touching ~55 call sites
twice. It belongs in the interface definition now.

## 7. Recommended sequencing, revised

The tiering in §2 changes the order the plan assumed:

1. ~~**The filter AST**~~ — **built and validated, §8.** `tools/seam/filter-ast.js`, 3,000
   randomised filters at 100 % agreement across mingo and real PostgreSQL, 10/10 v1 shapes
   covered. Remaining: re-run against a real `mongod` (§8.5), and write down the allowed regex
   subset.
2. ~~**Add the transaction scope**~~ — **designed, §9**, including the finding that MongoDB
   needs an explicit assertion to match RLS's fail-closed behaviour and cannot offer
   transactions on a standalone server at all.
3. **Close T1's two leaks** — `self.col`, `getLastModified`. Small, inside api3, low risk.
4. **Convert T2's 40 v1 sites** behind the finished interface. The bulk of the work.
5. **Decide aggregation** (§4.3) — may run in parallel; may produce a "MongoDB-only for now".
6. **Convert T3's socket path** last, with the dedup question filed separately.

**T0's 15 sites need no work at all**, and T1's 14 are mostly already correct — which is the
practical headline: **the conversion is ~55 sites, not 85.**
