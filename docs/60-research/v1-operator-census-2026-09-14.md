# What API v1 operators clients actually send — the census behind T2.4's allowlist

Date: 2026-09-14. Status: findings + tooling. Task **T2.4** of the
[execution plan](../30-design/nightscout-multitenancy-execution-plan-2026-09-14.md).
**Read-only — no shipping code changed.**

T2.4 says: *derive the operators clients actually send from the corpus; support those, reject the
rest with a documented 400. Ships as a security fix regardless of Postgres — it is the allowlist
that does not exist today* (backfix register **BF-04**).

**Tooling**: `tools/qc/v1_operator_census.py`.
**Output**: `reports/v1-query-census/census.json`, `sites.tsv` (every occurrence, with file and
line, so any row can be checked).

---

## 1. Method, and what kind of evidence this is

**There are no request logs.** What this workspace has instead is 58 checked-out ecosystem
projects, and API v1 encodes its filter in the URL as `find[field][$op]=value` — a literal string
in client source. So the query surface can be read out of the clients that produce it. The same
method already underwrites field attribution in this repository
(`reports/schema-census/attribution.json`), with the same caveat.

**It measures what client *source* contains, not what a deployment *receives*.** A filter built
by string concatenation at runtime, or typed into a browser, is invisible. It is therefore a
**lower bound on the field set and a strong signal on the operator set**, because the operator is
almost always a literal even when the field and value are not.

Two exclusions worth naming, both of which changed the answer:

- **`externals/experiments` holds a full nested copy of this repository** (autoresearch run
  artifacts). Counting it double-counted our own documentation as third-party demand and
  inflated the raw total from 157 to 379.
- **Server repositories are excluded by default.** Nightscout's own occurrences are the surface
  being *offered*, not demand for it.

## 2. The result: every operator clients send is already in the AST

```
157 occurrences across 14 client projects

operator   count  projects  in-AST
gte           55        13   yes
eq            36        10   yes
lte           32        10   yes
gt            22         5   yes
lt             5         3   yes
ne             4         3   yes
exists         3         2   yes

operators OUTSIDE the seam's AST: 0
```

**Seven operators observed. All seven are among the AST's ten.** Nothing in the corpus sends
`$where`, `$expr`, `$elemMatch`, `$near`, `$type`, `$mod`, `$size` or `$all`.

> **So BF-04's allowlist costs nothing in compatibility, on this evidence.** The security fix
> {M} §6.5 asks for — bounding v1's open pass-through — rejects nothing any surveyed client
> sends. That is the finding T2.4 existed to produce, and it is the good outcome rather than the
> expected one.

The AST is a **superset** of measured demand: `in`, `nin` and `re` are in it because API v3
declares them, not because a v1 client was seen to send them.

**Per project**, so the 14 are not a black box:

| project | occurrences | | project | occurrences |
|---|---:|---|---|---:|
| LoopFollow | 22 | | NightscoutKit | 8 |
| nightscout-reporter | 20 | | nightguard | 7 |
| GlycemicGPT | 18 | | GluPredKit | 6 |
| xdripswift | 14 | | nightscout-cgm-skill | 6 |
| oref0 | 13 | | oref-digital-twin | 6 |
| Trio | 12 | | cgmsim-lib | 4 |
| xDrip | 11 | | | |
| tconnectsync | 10 | | | |

`AndroidAPS`, `LoopCaregiver` and `nightscout-connect` show **zero** — they reach Nightscout by
other means. Their absence is not evidence that v1 filtering is unused; it is evidence about
those three.

## 3. The fields, and three findings in them

| field | occurrences | projects | operators |
|---|---:|---:|---|
| `created_at` | 57 | 12 | gte 30, lte 16, lt 4, eq 4, gt 3 |
| `date` | 30 | 8 | gt 11, gte 10, lte 7, eq 1, lt 1 |
| `eventType` | 13 | 7 | eq 13 |
| `dateString` | 11 | 5 | gte 8, lte 2, eq 1 |
| `_id` | 7 | 1 | **gt 7** |
| `startDate` | 7 | 3 | lte 4, gte 2, gt 1 |
| `id` | 6 | 2 | eq 6 |
| `enteredBy` | 5 | 3 | eq 4, ne 1 |
| `type` | 4 | 3 | ne 2, eq 2 |
| `carbs` | 2 | 2 | exists 2 |
| `device` | 2 | 1 | eq 2 |

**The surface is overwhelmingly time-ranging**: `created_at`, `date`, `dateString` and
`startDate` are 105 of 157 occurrences. This is what makes BF-01 (the count endpoint's date bound
arriving as the wrong type) matter more than its single call site suggests.

### 3.1 `re` is never *sent* — and is used constantly

No client sends `$regex`. But `lib/server/query.js`'s walker maps `notes`, `eventType` and
`enteredBy` through `find_options.parseRegEx`, so **`find[eventType]=Bolus` becomes
`{eventType: /Bolus/}` server-side.** The 13 `eq` occurrences on `eventType` and the 5 on
`enteredBy` are therefore regex matches by the time they reach the driver.

**Consequence for the seam**: a filter translator that only handles what clients literally send
will drop these. Native `RegExp` values have to survive the round trip — which is exactly what
the seam branch's commit `7c645f3c` ("Keep native RegExp filters instead of silently dropping
them") addresses. This census is independent evidence for why that commit was necessary, and it
means the regex path is **not** a rarely-exercised corner: it is on the most common
non-temporal field in the surface.

### 3.2 `_id` with `$gt` is cursor pagination, and it constrains identifier opacity

All 7 `_id` occurrences use `$gt`, from one project. `query.js:98-119` forces anything named
`_id` to an `ObjectID`, including inside operator objects (`queryLeaves`), so
`find[_id][$gt]=<hex>` becomes `{_id: {$gt: ObjectId(...)}}` — **ordered comparison over
MongoDB's ObjectId type**, used to page forward through a collection.

The seam's §4.1 rule 2 says the caller never constructs an `ObjectId` and `identifyingFilter`
moves inside the adapter. **That rule was written for equality lookups; this is an ordering
query**, and a SQL adapter has no ObjectId type to order by. It needs a deliberate answer —
a monotonic cursor column, or the shape documented as MongoDB-only — rather than discovery
during T2.5. Recorded here, not solved.

### 3.3 `id` is queried on `entries`, where the model says it does not exist

Trio sends `find[$or][0][id][$eq]=...` against the entries path
(`Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:196-200`). The nsschema model has
`id` on **treatments** but **not on entries**, and the server has no special-case mapping `id` to
`_id` or `identifier`.

**Stated as an observation, not a verdict**: it looks like a query that matches nothing, but this
was not run against a live Nightscout with Trio's data, and the corpus may simply not contain the
sites where entries carry `id`. Worth confirming before anyone acts on it — and worth confirming
*with* the Trio maintainers rather than about them.

## 4. Logical grouping: one client, and it validates the AST's only structural extension

```
$or    2  Trio
$and   1  Trio
```

Trio is the only surveyed client using the **nested indexed form**:

```swift
"find[$and][\(idx)][enteredBy][$ne]"    // NightscoutAPI.swift:111 — dynamically sized
"find[$or][0][id][$eq]"                 // NightscoutAPI.swift:196
"find[$or][1][dateString][$eq]"         // NightscoutAPI.swift:200
```

**This matters more than the count of 3 suggests.** `lib/storage/filter.js` lists nested groups
as one of its two deliberate extensions to v3's flat AST, justified by *v1's internal emission*.
This census shows a **production AID client sends them directly**, so the extension is required
by external demand as well, and a flat AST would break Trio.

It also means the allowlist must accept the indexed group syntax, not only the flat form. An
allowlist written against `find[field][$op]` alone would reject Trio's requests — turning a
security fix into an outage for one of the larger clients.

## 5. What T2.4 still needs

- ✅ *Census committed with counts per operator* — this document, `census.json`, `sites.tsv`.
- ⬜ *Allowlist enforced* — `cgm-remote-monitor` work. Structurally satisfied on the seam branch
  by `fromMongo` (BF-04, `fixed-in-seam`); extracting it to land independently is the open item.
- ⬜ *The rejected set documented in the API docs* — on this evidence the rejected set is
  everything outside the AST's ten, and **no surveyed client is affected**.

**Before enforcing, two things from §3 and §4 must be true of the implementation**, or the fix
breaks working clients: native `RegExp` values survive translation, and the indexed
`find[$and][n][field][$op]` form is accepted.

## 6. Honest limits

- **Source evidence, not traffic.** Runtime-constructed queries and hand-typed URLs are invisible.
  A deployment could be receiving operators no client repository contains.
- **14 projects is not the ecosystem.** Closed-source and self-written clients are unrepresented,
  and three major projects show zero because they use other paths.
- **Occurrence counts are code sites, not request volume.** One line in a hot loop outweighs
  twenty in rarely-run code, and nothing here can tell the difference.
- **Placeholders were filtered by a reviewable list**, not a heuristic — `k` was the only field
  name dropped as a variable. Template forms that survived (`{time_field}`, `${field}`, `%s`) are
  counted for their *operator*, which is literal, and not for their field.
- **`$nor` and `$not` were searched for and not found.** Absence of a shape the grep would have
  caught is a weaker claim than presence, but it is not nothing.
