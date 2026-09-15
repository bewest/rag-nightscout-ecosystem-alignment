# Backfix register — defects that ship to existing operators, independent of multitenancy

**Living document.** Started 2026-09-14. Maintained alongside the
[multitenancy execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md).

This exists because the multitenancy programme keeps finding bugs in **today's** Nightscout,
and those findings must not become hostage to a large architectural change. Every entry here
is a defect that

- affects **single-tenant self-hosters running the current release**, and
- is fixable **without any tenancy decision**, and
- should therefore be landable on its own, on `dev` or on
  `chore/nightscout-modernization`, ahead of the seam.

> **D4 makes this permanent, not temporary.** MongoDB and single-tenant are first-class
> forever, so "we will fix it when the Postgres backend lands" is never an answer for anything
> in this table.

**Status values**: `open` · `fixed-in-seam` (repaired inside the seam branch as a side effect,
needs extraction to land independently) · `landed` · `wontfix`.

---

## 1. Register

| id | defect | where | severity | tenancy-independent | status |
|---|---|---|---|---|---|
| **BF-01** | `GET /api/v1/count/entries/where` silently matches nothing | `lib/server/aggregate.js:21` | **high** — wrong answer, HTTP 200 | yes | open |
| **BF-02** | `insulin`/`carbs` query bounds truncated by `parseInt` | `lib/server/treatments.js:259-266` | **high** — wrong answer, HTTP 200 | yes | open |
| **BF-03** | Numeric filters on `devicestatus`, `activity`, `food`, `profile` match nothing | `lib/server/query.js` walker, per-collection | **high** — wrong answer, HTTP 200 | yes | open |
| **BF-04** | API v1 has no operator allowlist — filter pass-through reaches the driver | `lib/server/query.js:157` | **high** — ReDoS / full-scan exposure | yes | fixed-in-seam |
| **BF-05** | Unguarded `console.log` of every count query on the request path | `lib/server/aggregate.js:30-31` | **medium** — log noise, filter contents to stdout | yes | open |
| **BF-06** | `/api/v1/entries?count=10` costs 42× a typed read | `lib/server/cache.js:73-76` | medium — CPU | yes | open |
| **BF-07** | `cache.insertData` JSON round-trips the whole retained array | `lib/server/cache.js:81` | medium — 65 % of the load cycle | yes | open |
| **BF-08** | `nightscout-connect` actors have no start or interval jitter | `nightscout-connect`, `run()` | medium — thundering herd on restart | yes | open |
| **BF-09** | Socket dedup uses truthiness, so a `0` insulin/carbs value is skipped as a match key | `lib/server/websocket.js:535-568` | **unsettled** — may be intentional | yes | open |
| **BF-10** | `mongod` fatal-asserts at Docker's default `nofile=1024` | operational, not code | medium — self-hosters in containers | yes | open |

## 2. Detail

### BF-01 · `count/entries/where` silently matches nothing

`aggregate.js:21` calls `find_options(opts)` with **one argument**, so the collection's
`queryOpts` never arrive and `lib/server/query.js` falls back to its defaults — `dateField:
'date'`, no `useEpoch`. The two paths then inject different types for the same window:

```
list  path (useEpoch:true):  {"date":{"$gte":1789099222823}}              <- number
count path (defaults)     :  {"date":{"$gte":"2026-09-11T04:00:22.824Z"}} <- ISO string
```

`entries.date` is declared `number`, and **MongoDB compares only within a BSON type**, so the
injected two-day window excludes every document rather than bounding it. The endpoint returns
`200` with a count of zero.

*Evidence*: [seam interface](nightscout-storage-seam-interface-2026-09-14.md) §4.3.1, verified by
running `query.js` directly. Independently reconfirmed as a general class by the
[three-arm validation](../60-research/seam-filter-ast-three-arm-validation-2026-09-14.md) §3 class B.
*Fix*: pass the collection's `queryOpts` as the second argument. Ship with BF-02/BF-03 (plan T0.5).

### BF-02 · `insulin` and `carbs` bounds truncated

`treatments.js` coerces query values through a hand-maintained per-collection `walker`:

```js
walker: { insulin: parseInt, carbs: parseInt, glucose: parseInt, ... }
```

`specs/nsschema/treatments.model.json` declares `insulin` and `carbs` as `number`, not integer.
So `find[insulin][$gte]=1.5` becomes `{"insulin":{"$gte":1}}` — **a query for boluses of at
least 1.5 units returns boluses of 1.0 units.**

**This is a data-correctness defect with review implications.** Anyone using the API to review
therapy data — a report tool, a clinician export, a caregiver checking what was delivered —
gets records that do not match what they asked for, with no error. It warrants a release note
rather than a silent fix. It is not, in itself, advice about dosing, and nothing here should be
read as such; the point is narrower and worse — **the data returned does not answer the
question asked.**

*Evidence*: [execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md) §3.4.

### BF-03 · Numeric filters that silently match nothing

| collection | `walker` |
|---|---|
| entries | 7 fields, all `parseInt` |
| treatments | `insulin carbs glucose` → `parseInt`; `notes eventType enteredBy` → regex |
| profile | `{}` — empty |
| **devicestatus, activity, food** | **none at all** |

A field with no `walker` entry stays a **string**, and MongoDB's type ordering means a numeric
field never matches a string bound. So `devicestatus` and `activity` have no coercion at all
and **every numeric filter on them matches nothing and returns 200**:

```
devicestatus  uploader.battery $lt=50   ->  {"uploader.battery":{"$lt":"50"}}   <- still a string
entries       delta            $gte=1.5 ->  {"delta":{"$gte":"1.5"}}            <- still a string
```

**Fixing this is user-visible in the good direction**: queries that silently returned nothing
start returning rows. Release-note it, so it arrives as a fix rather than as a surprise.

*Fix*: plan T0.5 — emit a coercion table from `specs/nsschema/*.model.json` (a sixth emitter)
and drive the walker from it, instead of four hand-maintained lists that drift.

> **Sharpened by the three-arm validation.** T0.5 was written as a v1 bug fix. It is also a
> **precondition for the seam's backend-equivalence claim**: with correctly-typed values, all
> three arms agree 3000/3000; with mistyped ones, four divergence classes open, two of which
> produce *different data* depending on which backend a deployment runs.
> See [three-arm validation](../60-research/seam-filter-ast-three-arm-validation-2026-09-14.md) §4.

### BF-04 · No operator allowlist on API v1

`lib/server/query.js:157` builds the filter with `traverse` type-coercion, injects a date
constraint, and **returns it to the driver with no operator allowlist**. Whatever
`find[x][$op]` a client sends reaches MongoDB — `$where`, `$expr`, an unbounded `$regex`.

**Status `fixed-in-seam`.** The seam branch's `fromMongo` (commit `68ffbd66`) parses `query.js`'s
output into the AST, and an AST that cannot represent an unlisted operator *is* the allowlist —
so this is repaired there as a structural consequence. **It should not have to wait for the
seam to land.** Extracting the allowlist as a standalone change is a small piece of work and a
security fix that ships to every current operator.

*Evidence*: {M} §6.5; seam interface §8.2.

### BF-05 · Debug logging on the count request path

```js
console.log('$match query', query);
console.log('AGGREGATE', groupBy);
```

Unguarded, on both `dev` (`a8888f0d`) and `chore/nightscout-modernization` (`0a4109f6`), so
every `/api/v1/count/*` request writes the constructed filter to stdout. Two problems: it is
noise the modernization branch's own quiet-logging work (`c2ac743c`) set out to remove, and a
filter can carry values a deployment would rather not have in its logs. **Route through the
existing logger at debug level, or delete.**

### BF-06 · Untyped `/api/v1/entries` read costs 42×

`?count=10` costs **0.83 ms** without `find[type]` and **0.02 ms** with it, for a byte-identical
response, because `ctx.cache.getData('entries')` deep-clones the whole 48-hour array before
anything is sliced. *Fix*: slice first, then clone the slice — the documents handed out are
still clones, so the defensive property is preserved. *Evidence*: {R} §12.2. Plan T0.2.

### BF-07 · `cache.insertData` round-trips the whole retained array

`insertData` returns `getData()` — a JSON round-trip over the **whole** retained array, per
datatype, per cycle: **4.08 ms**, 65 % of the post-#8733 load cycle.
**Resolve `dataloader.js:203` first** — `if (!element.mills) element.mills = element.date` writes
to the element, so a shallow copy changes behaviour there. The measurement sizes the prize; it
does not license the patch. *Evidence*: {R} §12.3. Plan T0.3.

### BF-08 · No jitter in `nightscout-connect`

800 actors fire their first upstream request inside one second on every restart and deploy
(`run()` sends `START` with no jitter), and stay phase-locked on the same five-minute boundary
afterwards. Different repository; independent of everything else here. *Evidence*: {R} §6.2.

### BF-09 · Socket dedup truthiness — unsettled, deliberately

`websocket.js` tests `if (data.data.insulin)` rather than presence, so a **`0`** insulin or carbs
value is skipped as a match key. No test covers it. **Recorded rather than guessed**: it may be
intentional. It needs a maintainer decision, and whichever way it goes it needs a test, because
nothing currently pins the behaviour. *Evidence*: seam interface §4.4.

### BF-10 · `mongod` fatal-asserts at the default file-descriptor limit

Docker's default `nofile=1024` is not enough for the collections and indexes Nightscout's own
test suite creates: WiredTiger hits `Too many open files` in `__wt_open` and `mongod` takes a
`fassert()` — **aborting the server**, not failing an operation.

This was reached by an ordinary test run, and matches EXP-MT-040b's finding at 50 tenant
databases. **So the fd ceiling is not a scale-only concern** — it is reachable by a self-hoster
running `mongod` in a container with default limits. Not a code defect; it belongs in the
operator documentation, and it is the kind of failure that looks like data loss to the person
it happens to.

## 3. How to use this register

1. **Anything found while doing multitenancy work that is also broken today gets an entry
   here**, at the time it is found, with its evidence link. The register is the mechanism that
   keeps that promise.
2. **Prefer landing these independently.** Each one is small, each ships to every current
   operator, and none needs a tenancy decision.
3. **Release-note the behaviour changes.** BF-02 and BF-03 change what queries return. That is
   the point, and it should arrive as a documented fix.
4. **Keep severities honest.** "Wrong answer with HTTP 200" is worse than "slow", and both are
   worse than "noisy". The table is sorted by that, not by effort.
