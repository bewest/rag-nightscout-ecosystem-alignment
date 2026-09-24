# T1.1 — the storage seam: interface definition and call-site classification

*Contributor-facing.* **Snapshot, 2026-09-14 (§8–§10 later). Current: the only statement of the storage seam's interface.**
Task T1.1 of the [execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md); decisions it rests on: D3, D4, D8, D9 — [plan §1](nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions).
§1–§7 were measured 2026-09-14 against `origin/chore/nightscout-modernization` @ `0a4109f6`;
§8–§10 describe what was built on the `seam/*` branch chain (tip `seam/t1-2-storage-interface`
@ `81a1f6ce`, `externals/work/crm-seam`), which is **unpublished**. That base has since moved
(to `b1bdaca0` on 2026-09-21, a merge of `dev`); the seam is 68 behind it and trial-merges with 19
conflicting paths — queue item `SEAM-REFRESH`. Nothing here is in `dev` or any release.

**Deliverables**: this document, plus
`reports/storage-seam/t1-1-call-site-classification.tsv` (every site, classified) and the two
scripts that produce it, so the count can be re-derived rather than trusted.

---

## 1. The count: 85 call sites

Method matters because two plausible greps undercount:

| count | method | why it is wrong |
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
lower-risk task, and it sets the sequencing in §7.

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

#### 4.3.1 The count path's date bound (BF-01)

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
returning 200 and an empty result. Filed as **BF-01** (reproduced); the fix routes count and list
through the same `query_for` and is **merged** to `dev` via PR #8738 (2026-09-18), not released.

### 4.4 Dedup across the three write paths — investigated, and they are not equivalent

The §5 recommendation — convert the socket path last, file unification separately — holds. The three paths disagree on **match key, match scope, post-match
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

**Unsettled:** whether the socket similarity branch's use of truthiness
(`if (data.data.insulin)`) rather than presence is intentional. A falsy value is skipped as a
match key, and no test covers it. Register **BF-09** (queue `BFQ-09`, unsettled) carries the
corpus measurement of which fields this actually affects.

## 5. A third write path, not previously named

`lib/server/websocket.js` is 15 sites — the largest single concentration — because it
implements **a complete CRUD API over Socket.IO**: `dbAdd` (`:449`), `dbUpdate` (`:332`),
`dbUpdateUnset` (`:395`), `dbRemove` (`:734`). It carries **its own deduplication logic**
(exact-match then similar-match, `:528`/`:572`) parallel to — not shared with — v1's and v3's.

Consequences:

- **The seam covers three API surfaces, not two** — v1, v3 and the socket path.
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
- **Transactions.** Nothing in the shipping code uses them; RLS binding under D3 is
  per-transaction ({DB} §8.2), so the interface needs a transaction scope. That scope is §9.

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
| all operators except `re` | **3000/3000 (100 %)** |
| with `re` on plain patterns | 1500/1500 (100 %) |

**Non-vacuity:** the differential caught two adapter defects during construction — reverting
either fix reproduces the disagreement (332 for `nin`, all one direction):

1. **`nin` and missing fields.** MongoDB's `$nin` matches a document where the field is absent;
   `NULL NOT IN (…)` is NULL in SQL and matches nothing. Fixed as `(x IS NULL OR x NOT IN (…))`, the same three-valued-logic gap `ne` needed.
2. **`exists` cannot read a generated column.** MongoDB's `$exists` is *key presence*, and a
   generated column is built with `->>`, which returns SQL NULL for **both** an absent key and
   an explicit JSON null — it cannot tell them apart. `doc #> '{path}'` can: jsonb `null` for
   the first, SQL NULL for the second. Verified directly, then fixed so `exists` **always**
   reads the document even when a column exists for that field.

> The second is a trap in the §6.3 storage shape rather than in this AST: **generated columns
> are not a faithful projection of the document.** Anything that needs to distinguish absent
> from null must read the jsonb.

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

### 8.5 Limits

- **mingo is a reimplementation of MongoDB's query language, not MongoDB.** A three-arm
  comparison (mingo / live `mongod` / live PostgreSQL) in
  [{3A}](../../60-research/tenancy/seam-filter-ast-three-arm-validation-2026-09-14.md) agrees
  3000/3000 on same-type values. Cross-type values gave mongod-vs-postgres 96.15 % in four
  nameable classes before the type guard of §8.6; with it, 100 % (§8.6.2).
- **The regex result covers a deliberately plain subset** — literals, anchors, character
  classes. Mongo's `$regex` is PCRE-flavoured and Postgres `~` is POSIX; they diverge on lazy
  quantifiers, lookaround and `\d`-style shorthands. **The measured 100 % describes the subset
  we would allow, not the whole language**, and the allowed subset needs to be written down.
  `RE_MAX_LEN` is a length bound, not a work bound (T2.3, plan Phase 2).
- **300 documents, one collection shape.** Sort, limit, skip and projection are not covered —
  only the filter.
- **No tenant predicate is in these filters.** Under D3 the tenant bound comes from RLS, not
  from the AST, which is the point — but it means this validation says nothing about isolation.

### 8.6 The cross-type break is also *inside* the adapter — found by T2.1

The cross-type disagreement is not only a coercion problem above the seam. Building the T2.1 DDL
forced a decision about generated columns, and measuring it produced this on live PostgreSQL 16
over four rows (`sgv: 120`, `sgv: "120"`,
`sgv: null`, key absent):

| predicate | rows |
|---|---:|
| `WHERE "sgv" >= 100` — the guarded generated column | **1** |
| `WHERE (doc #>> '{sgv}')::numeric >= 100` — `toSql`'s fallback | **2** |

Both are `toSql` emitting `gte sgv 100`. Which one it emits depends only on whether that field
happens to appear in the column manifest. So **whether a field has an index accelerator can
change a query's answer** — and the accelerator is supposed to be exactly the thing that
cannot. The emitted DDL says so in every file header ("dropping every generated column must not
change an answer"); today, dropping one would.

The guarded column is the *correct* arm: MongoDB orders BSON types before values, so
`sgv: "120"` does not match `{sgv: {$gte: 100}}`, and the column agrees while the fallback does
not. Two further consequences of the same mismatch: a dirty value makes the fallback **raise**
`22P02` at query time where the column is merely NULL, and a numeric field given an ISO-string
bound raises where MongoDB silently matches nothing — BF-01's live defect arriving as an error
instead of an empty page. Louder, still a behaviour difference.

**Fixed on the seam branch 2026-09-15** (`d75c1154`, unpublished): the jsonb path carries the same
`CASE WHEN jsonb_typeof(…) = '<type>' THEN … END` the emitted DDL builds its columns with, so
the two agree by construction rather than by review. `CASE` and not
`AND jsonb_typeof(…) = t`, because SQL does not promise to evaluate conjuncts in order — a
planner free to try the cast first turns one dirty value into a `22P02` for the whole query.

Three things came with it, each a defect in its own right:

- **A generated column is *typed*, so `columns` is now a map of name → JSON type.** Comparing a
  string against a numeric column emitted `numeric = text` and raised `22P02` *at query time* —
  a 500 where MongoDB simply matches nothing. With names alone the type is unknown, so every
  comparison takes the (correct, unaccelerated) jsonb path; `specs/generated/postgres/index.json`
  now carries `columnTypes`, and passing it is what turns the accelerator on.
- **Mixed-type `in`/`nin` lists get one arm per type.** `{$in: [1, 'a']}` is two questions; a
  single cast has to pick one and silently loses every value of the other.
- **A null operand is its own type bracket.** Measured against mongod 7.0.43 over
  `{null, missing, 0, 'a', false}`: `$eq`, `$lte` and `$gte` against null all match null **and**
  missing, while `$lt` and `$gt` match **nothing** — there is no value above or below null inside
  its own bracket. Without this handling the ordering operators emit the literal string
  `undefined` into the SQL (114 of 3000 three-arm fixtures fail).

### 8.6.1 Non-vacuity of the cross-type differential

Without cross-type fixtures the differential cannot see the guard: every fixture `mkDocs` builds
stores each field's own type, so removing the guard changes no result. With `--cross-type` (both halves: a document of the wrong type, and a *query* of the wrong type,
which are opposite sides of the bracket):

| | mismatches over 5000 |
|---|---:|
| guard removed | **398 unclassified, plus hard cast errors** — readings like `mongo 0 / sql 140` |
| guard in place | **0** |

A generated column declared with a bare cast fails at *insert*: one document holding `sgv` as the
string `"120"` kills the `INSERT` with `22P02`. That is exactly the argument `postgres_emit.py` makes
for emitting a `CASE` guard — on a real deployment it is an ingest outage caused by a
data-quality problem.

### 8.6.2 The seam now matches real MongoDB, and the oracle is what is wrong

`tools/qc/three-arm.js` against a live **mongod 7.0.43**, 3000 fixtures, cross-type injection on,
regex arm on:

| comparison | result |
|---|---|
| **mongod vs postgres** | **3000/3000 — 100 %** |
| mingo vs mongod | 2977/3000 — **23 disagreements** |
| mingo vs postgres | 2977/3000 — 23 disagreements |

(Without the §8.6 guard, {3A} measured mongod-vs-postgres at 96.15 % on cross-type values.) The
seam's claim holds exactly against the database self-hosters actually run.

**Every remaining disagreement is the oracle's**, and the defect is pinned to one construct:
**mingo's `$lte`/`$gte` against a null operand does not match a missing field; mongod's does.**
mingo agrees with mongod on `$eq`, `$ne`, `$lt` and `$gt` null. With T2.3's `re` finding (where
the oracle *masked* a real divergence; here it *manufactures* one) the conclusion is the same: **`mingo ≡ postgres` is a claim about the AST,
never about MongoDB.** `validate.js` now declares these fixtures oracle-declined at the point of
use, the way it already declares the `x` flag, rather than counting them against the adapter.

### 8.7 Two capability gaps T2.1 surfaced

- **Multikey is not expressible as a generated column.** `treatments.boluscalc.foods` is an
  array and the live query is `?find[boluscalc.foods._id]=…` (`lib/report/reportclient.js:294`).
  `doc #>> '{boluscalc,foods,_id}'` is NULL on an array, so no column can reproduce MongoDB's
  multikey semantics. T2.1 emitted **nothing** rather than an approximation that would have
  looked right and answered wrong. This is why the emitted index count is 30 secondary + 4
  primary = **34**, not {M} §6.7's 41: 6 of the difference is food and activity, which have no
  model yet (T2.2), and the remaining 1 is this. §6.7 counts six collections; T2.1 had four
  models.
- **Seven indexed field paths no model declares**: `NSCLIENT_ID` (treatments, devicestatus,
  profile), `date` (treatments, devicestatus), `created_at` (entries), plus the multikey one.
  They get no column and appear in the index as a jsonb expression carrying an inline
  `UNDECLARED` note, so the index stays faithful to the Mongo declaration and the gap stays
  visible. `NSCLIENT_ID` is a real field the websocket write path uses
  (`lib/server/websocket.js:538`) — a T2.2 input, not a T2.1 defect.

### 8.8 Date-like columns are `text`, and cannot be anything else

`created_at`, `startDate`, `sysTime` and `dateString` are declared `string` + `date-time`.
Range predicates on them are therefore **lexicographic**, which is chronological only while
every writer emits a UTC-normalised ISO string of constant width. `timestamptz` would fix the
ordering and break `eq` — **and its cast is not immutable, so it cannot be a generated column at
all.** Left as text and flagged rather than quietly made wrong.

## 9. The transaction scope

{S} §6 flagged that the interface had none and that D3's RLS binding is per-transaction.
Confirmed: `set_config('app.current_tenant_id', …, is_local => true)` is transaction-scoped, so
**every tenant-bound operation must run inside a transaction that has been bound.**

```js
store.withTenant(tenantId, async (tx) => { … })   // NEW
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

### 9.1 As built — 2026-09-14

Built after T1.2, which had left **one choke point** — the `MongoCollection` delegations — so
the change touched three files.

`lib/storage/tenant-scope.js`, with `withTenant` exposed on the store (`lib/storage/mongo-storage.js`)
and `requireTenant` asserted in `lib/api3/storage/mongoCollection/index.js`. All three findings
are implemented rather than deferred:

1. **The assertion.** Every document-touching delegation calls `requireTenant(<collection>.<op>)`
   first. **Non-vacuity checked**: removing the call makes the unbound-multitenant test fail
   with the query reaching the driver — which is the whole exposure, one tenant's query
   returning another's documents.
2. **No transaction on MongoDB.** `withTenant` binds and does not open one. The interface
   therefore **does not promise atomicity across operations**, and that is stated at the method,
   not left to be discovered from a partial write.
3. **`SINGLE_TENANT` is a `Symbol`**, not a reserved string. A Symbol cannot compare equal to a
   tenant id, be serialised into a log line, or be concatenated into a query — so the
   single-tenant binding cannot leak into a multitenant code path by accident. Binding a tenant
   id under `'single'` is refused, and `SINGLE_TENANT` under `'multi'` is refused.

**AsyncLocalStorage, not a threaded handle**, and the *failure mode* is the argument rather than
the diff size. If the async chain breaks and the scope is lost, the caller has **no** binding —
which throws here and returns zero rows under RLS. A lost scope cannot silently become a
*different* tenant's binding, because there is nothing to fall back to. It fails closed in both
directions. Rebinding a different tenant inside an existing scope is refused outright: crossing
a tenant boundary is an admin-plane operation and belongs on its own request.

**What this is not.** The only caller of `setTenancyMode('multi')` is T3.1's `fromEnv` under
`TENANCY_MODE=multi`, on the same unpublished branch chain, so the assertion is **inert in every
deployment that exists**. It is the scope T2.5 needed; it is not tenancy.

14 tests; the suite is **2229 passing, 1 pending, 0 failing**, lint clean.

## 7. Sequencing

The tiering in §2 sets the order. Status as of the seam tip `81a1f6ce`; the queue is
authoritative for item state.

1. **The filter AST** — built and validated (§8). Owed: write down the allowed regex subset.
2. **The transaction scope** — built (§9.1).
3. **Close T1's two leaks** — `getLastModified` now routes through `findMany` (§10.1); whether
   `self.col` is private on the seam tip is not recorded here and should be checked there.
4. **Convert T2's 40 v1 sites** behind the finished interface — done in T1.2 except
   `profile.list_query` (§10.6).
5. **Aggregation** (§4.3) — resolved as `count(ast)`.
6. **Convert T3's socket path** — converted; dedup unification filed separately (§4.4).

**T0's 15 sites need no work at all**, and T1's 14 are mostly already correct — which is the
practical headline: **the conversion is ~55 sites, not 85.**


## 10. As built — what T1.2 actually delivered, and where it diverged from §4.1

The delivered interface differs from §4.1 in four places. §4.1 is kept as proposed so the reason
for each deviation stays readable.

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
for all four v1 delete endpoints.

### 10.5 One change to the AST itself: `re` carries `options`

A `fromMongo` that reads clauses with `Object.keys` loses a native `RegExp` **silently** —
`Object.keys(/x/i)` is `[]`, so the clause produces no nodes and vanishes. `lib/server/query.js`'s
`parseRegEx` returns a native RegExp for the treatments `notes`/`eventType`/`enteredBy` filters,
so on the seam branch before this change a request for boluses returned every treatment.

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
| `lib/server/bootevent.js:145-146` | a hardcoded `require('../storage/mongo-storage')` under a `//TODO assume mongo for now` comment — no way to choose a backend. Replaced on the seam branch by T2.0 (`lib/server/storage-backends.js`, selection by URI scheme); see the plan's Phase 1. |

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
