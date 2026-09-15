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
count(filter)                                   // NEW — and §4.3 shows it is the ONLY one
getLastModified(fieldName)

// ---- writes
insertOne(doc, options?)
insertMany(docs, options?)                      // NEW — 2 sites
replaceOne(identifier, doc, { upsert })         // upsert becomes explicit — 7 sites
updateOne(identifier, patch)                    // patch is a plain object, NOT {$set: …}
deleteOne(identifier)
deleteMany(filter)                              // NEW — supersedes deleteManyOr
bulkUpsert(docs, { matchOn })                   // NEW — 5 sites

// ---- the only aggregation that actually occurs (§4.3)
//      `aggregate(pipeline)` is deliberately absent

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

### 4.3 Aggregation — investigated, and it is one operation

> **Resolved 2026-09-14.** §4.3 assumed this was the hard escape hatch. It is not.

`lib/server/aggregate.js` builds `[{$match: query}].concat(conf.pipeline).concat(opts.pipeline).concat(template())`,
and **every extension point is empty in production**:

- `conf.pipeline` has **no supplier** — the factory is constructed in exactly three places
  (`entries.js:223`, `devicestatus.js:162`, `treatments.js:439`), all with `{}`.
- `opts.pipeline` is **rejected with HTTP 400** before reaching storage
  (`lib/api/entries/index.js:452-457`), closed deliberately in commit `479a6a4d`.
- `template()` is a literal: `[{$group: {_id: null, count: {$sum: 1}}}]`, with `_id` hardcoded
  to `null` — **there is no code path that sets a grouping key.**

**So there is exactly one shape: `count(collection, filter)` → integer**, over
`{entries, treatments, devicestatus}`. No `groupBy`, no `distinct`. The
`[{_id: null, count: N}]` envelope is a MongoDB artifact the API leaks and the route layer can
reconstruct.

**`aggregate(spec)` therefore comes out of the proposed interface in §4.1** — `count(filter)`
is sufficient and complete. If a general `aggregate` is kept in the Mongo adapter for future
use, it must stay *off* the neutral interface or the seam leaks.

Two constraints on doing it: `tests/count-pipeline-boundary.test.js` pins the response shape
and the exact 400 message; `tests/mongo-query-javascript.test.js:75-94` constructs the helper
directly and passes `opts.pipeline`, so it depends on that parameter existing even though no
production caller supplies it.

#### 4.3.1 And a live bug found on the way

`aggregate.js:21` calls `find_options(opts)` with **one argument**, so the collection's
`queryOpts` never reach it and `lib/server/query.js` falls back to its defaults — `dateField:
'date'`, no `useEpoch`. The consequence, run directly:

```
list  path (useEpoch:true):  {"date":{"$gte":1789099222823}}       <- number
count path (defaults)     :  {"date":{"$gte":"2026-09-11T04:00:22.824Z"}}   <- ISO string
```

`entries.date` is declared `number` in `specs/nsschema/entries.model.json`, and MongoDB orders
BSON types before comparing values, so a numeric field never matches a string bound.
**`GET /api/v1/count/entries/where` with no explicit date filter silently matches nothing** —
the injected two-day window excludes every document rather than bounding it.

This is the same class as T0.5's under-coercion finding: a string where a number belongs,
returning 200 and an empty result. It should ship with T0.5 rather than wait for the seam.

### 4.4 Dedup across the three write paths — investigated, and they are not equivalent

Two sites — `lib/server/aggregate.js:26` and `lib/api/entries/index.js:520` — pass a pipeline
through. A pipeline pass-through cannot be translated in general, for the same reason v1's
operator pass-through cannot (§3.1 of the plan).

**Do not put `aggregate(pipeline)` in the interface.** Establish what those two callers
actually compute, express each as a named operation (`count`, `groupBy`, …), and implement
those. If the answer turns out to be "arbitrary pipelines", that is a finding worth having
early — it would mean reporting stays MongoDB-only for a while, which is survivable under D4
and should be recorded rather than discovered during T2.5.

The §5 recommendation — convert the socket path last, file unification separately — is
confirmed and strengthened. The three paths disagree on **match key, match scope, post-match
write semantics, and which collections dedup at all**:

| | socket `dbAdd` | API v3 | API v1 |
|---|---|---|---|
| treatments | `NSCLIENT_ID`, else `created_at`+`eventType`, **plus a ±2 s fuzzy window** on amount fields | UUIDv5 of `device_date_eventType`; fallback `created_at`+`eventType` | `identifier` → `_id` → `created_at`+`eventType` |
| entries | **no dedup** | identifier; fallback `date`+`type` | `sysTime`+`type`, device-blind |
| devicestatus | `NSCLIENT_ID`, else `created_at` (device-blind) | `created_at`+**`device`** | **no dedup** |
| profile | `startDate` → full replace | `created_at` | **no dedup** |
| on a match, writes | treatments: only `$set`s `created_at`, keeps the stored body; devicestatus: **nothing** | **full replace** | treatments: replace; entries: **`$set` merge** |
| permission on a match | create rights | **`api:<col>:update`** | create rights |

**Divergences that would change behaviour if unified** — the load-bearing ones:

1. **Only the socket path matches fuzzily** (±2 s plus amount fields, `websocket.js:535-568`).
   Removing it duplicates AAPS/NSClient treatments; adding it elsewhere silently swallows
   legitimate rapid boluses.
2. **`NSCLIENT_ID` is a socket-only key**; v1 and v3 treat it as opaque payload.
3. **v3's fallback clause carries `identifier: {$exists: false}`** (`utils.js:159`), which the
   others lack. A unified rule would make v3 start matching identifier-bearing documents by
   `created_at`+`eventType` — a real loosening.
4. **`created_at` normalisation differs**: v1 normalises through moment to ISO-UTC and lets
   `eventTime` override it (`treatments.js:449-450, 473-479`); the socket path uses the raw
   client string. Identical payloads produce different keys.
5. **Entries get three different answers** for the same SGV, and `devicestatus`/`profile` each
   dedup in some paths and not others.

**Also worth recording: the socket write API is not browser-only.** It is attached to the same
HTTP server and uses the same credential model as REST (`websocket.js:81-84`, `:115-131`), so
`dbAdd`/`dbUpdate`/`dbRemove` are reachable by any client that can reach the site. Anonymous
writes are denied by default, but a deployment adding `careportal` to `AUTH_DEFAULT_ROLES`
opens them — exactly as it would for REST.

**One thing the investigation could not settle**, recorded rather than guessed: whether the
socket similarity branch's use of truthiness (`if (data.data.insulin)`) rather than presence is
intentional. A `0` insulin or carbs value is skipped as a match key, and no test covers it.

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

- ~~**mingo is a reimplementation of MongoDB's query language, not MongoDB.**~~ **CLOSED** —
  re-run as a three-arm comparison (mingo / live `mongod` / live PostgreSQL) in
  [{3A}](../60-research/seam-filter-ast-three-arm-validation-2026-09-14.md). All three arms
  agree 3000/3000 on same-type values. Turning on **cross-type** values breaks that
  (mongod-vs-postgres 96.15 %), in four nameable classes — which is a finding about type
  coercion above the seam, not about the AST, and it is why T0.5 matters.
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
   covered. Remaining: write down the allowed regex
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


## 10. As built — what T1.2 actually delivered, and where it diverged from §4.1

The proposal in §4.1 survived contact with the code, with three deviations. Each is recorded
here rather than edited into §4.1, because the reason for a deviation is worth more than a
tidy-looking proposal.

### 10.1 The delivered surface

```js
// ---- reads
findOne(identifier, projection?, options?)
findOneFilter(filter, projection?, options?)
findMany({ filter, sort, limit, skip, projection, options })
findFiltered(ast, { sort, limit, skip, projection, readOptions, options })   // NEW
count(ast)                                                                   // NEW
getLastModified(fieldName)                    // now routed through findMany

// ---- writes
insertOne(doc, options?)
insertMany(docs, options?)                                                   // NEW
replaceOne(identifier, doc)
updateOne(identifier, setFields)
updateMany(ast, { set, unset })                                              // NEW
replaceFiltered(ast, doc)                     // NEW — replace in place, NO upsert
deleteOne(identifier)
deleteMany(ast)                                                              // NEW
deleteManyOr(filterDef)                       // v3's existing OR-of-clauses form, kept
bulkUpsert(ops, { mode, ordered })                                           // NEW
```

`aggregate()` is absent, as §4.3 argued it should be.

### 10.2 Deviation 1 — `bulkUpsert(ops, {mode})`, not `bulkUpsert(docs, {matchOn})`

§4.1 assumed one match rule for a batch. The call sites do not share one: each operation
carries **its own filter**, and more importantly `entries` upserts with `$set` (stored fields
absent from the incoming document survive) while `treatments`, `food` and `activity` replace
wholesale. That is a real semantic difference on a write path, so `mode: 'merge' | 'replace'`
is explicit and has no safe default — defaulting it away would silently change behaviour for
whichever group lost.

### 10.3 Deviation 2 — `updateMany(ast, {set, unset})`, not a null-sentinel patch

§4.1 rule 3 proposed that `$unset` become "an explicit null-or-sentinel convention in the
patch". Rejected once the caller was read: a sentinel makes "set this field to null" and
"remove this field" the same wire shape, and `websocket.js` genuinely does both. Two named maps
cost nothing and cannot be confused.

The method also **validates field names**, refusing any that begins with `$`. On the socket
path those names arrive straight off the wire and go into `$set`/`$unset`, which is precisely
where a field name becomes an update *operator*. MongoDB rejects most of these itself; making
it structural is the same argument as the AST's operator allowlist.

### 10.4 Deviation 3 — `deleteMany` returns three fields, and the wire is shaped elsewhere

It returns `{ deleted, deletedCount, acknowledged }`. `deleted` matches `deleteManyOr`'s
existing contract; `deletedCount` and `acknowledged` are what the v1 delete endpoints put on
the wire, because `normalizeDeleteStatus` copies the whole object into the response body.

Three modules independently re-synthesised `acknowledged: true` before this was centralised —
which would misreport an unacknowledged write. The driver's value is passed through instead,
and the internal `deleted` alias is stripped in `normalizeDeleteStatus`, the single choke point
for all four v1 delete endpoints. **Three agents converging on the same workaround was the
signal that the interface, not the callers, was wrong.**

### 10.5 One change to the AST itself: `re` carries `options`

`fromMongo` originally lost a native `RegExp` **silently** — `Object.keys(/x/i)` is `[]`, so the
clause produced no nodes and vanished. `lib/server/query.js`'s `parseRegEx` returns a native
RegExp for the treatments `notes`/`eventType`/`enteredBy` filters, so this was live: a request
for boluses returned every treatment.

Flags now live on the node (`{op: 're', field, value, options: 'i'}`) rather than inline in the
pattern. Two reasons, and the second is the one that matters for Phase 2:

1. flags must not consume the `RE_MAX_LEN` budget, which is the ReDoS bound;
2. the adapters spell them differently — MongoDB has `$options`, while PostgreSQL has a
   case-insensitive **operator** (`~*`) and no inline `i` at all. A flag smuggled into the
   pattern string would have made the SQL adapter's job incorrect rather than merely awkward.

Only the flags MongoDB honours (`imsx`) are kept; `g`/`y`/`u` say nothing about whether a single
document matches, and the driver drops them too. Verified against live MongoDB 7 that
`/Bolus/i`, `/Bolus/gi` and `/change/ims` select the same documents through the seam as they do
natively.

### 10.6 What is still on the raw collection

| site | reason |
|---|---|
| `profile.list_query` | accepts `$expr` today, with a test asserting it. A query-surface decision (D8/T2.4), not a conversion detail. The T2.4 census found **no client in the corpus sends `$expr`**, so rejecting it is a security fix rather than a compatibility break — but it is still a deliberate behaviour change and belongs with the allowlist. |
| each module's `api()` / collection accessor | bootevent still needs raw collections for `ensureIndexes`. Removing these is the *last* step, once index creation moves behind `ensureSchema`. |
| `lib/server/bootevent.js:145-146` | the interface has two callers' worth of implementations behind it and **no way to choose one**: a hardcoded `require('../storage/mongo-storage')` under a `//TODO assume mongo for now` comment. This is the difference between a seam that exists and a seam that is load-bearing — until it is a lookup, no test and no deployment can be handed a store that is not MongoDB, whatever the interface says. Tracked as T2.0 in {P}. |

`websocket.js` **is** converted. Its dedup logic remains knowingly inconsistent with
`lib/server/treatments.js` (§4.4) — the storage calls moved, the logic did not, and unifying it
is filed separately as a behaviour change.

### 10.7 Deviation 4 — `replaceFiltered`, found by converting the socket path

Not in the proposal at all. The socket path's profile dedup is a **replace-in-place that must
not insert**, and every route §4.1 offered was an upsert: `replaceOne` matches on a v3
identifier *and* upserts, and `bulkUpsert` is upsert by definition. Either would resurrect a
profile deleted between the lookup and the write — a user removes a profile, a queued socket
message recreates it.

It returns `matchedCount` so a caller can distinguish "replaced" from "was already gone". That
distinction is the reason the method exists, so it is tested directly rather than inferred.

**Process note worth keeping.** This gap was found because the converting agent *stopped and
reported* rather than reaching for the nearest upsert. The same thing happened with
`acknowledged` and with the dropped `RegExp`. Three of the four real defects in T1.2 surfaced
because someone declined to paper over a mismatch — which is an argument about how to run the
remaining phases, not just a note about this one.
