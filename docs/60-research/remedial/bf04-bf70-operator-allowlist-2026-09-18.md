# BF-04 extracted, and BF-70 found underneath it — API v1's query and pipeline surface

Date: 2026-09-18. Branch: `bf/operators`, three commits on `origin/dev` `a8888f0d`, tip
`52b7b640`. Worktree `externals/work/crm-bf-operators`.

**Started as a question about PR #8737.** A reader asked whether that branch disallows `$where`,
`$projection` "and other operators that could introduce security issues". It does not, and was
never meant to: #8737 is a type-coercion change, and `$where` appears in its
`NON_VALUE_OPERATORS` table precisely because the coercer must keep its hands *off* that operand.
Answering the question meant measuring what API v1 actually carries, which is
[BF-04](../../30-design/remedial/nightscout-backfix-register.md) — filed 2026-09-14 as
`fixed-in-seam`, and therefore fixed for nobody, with the extraction it asks for never done.

**It also turned up a second defect that is worse than the one asked about, and that nothing in
this programme had recorded.** That is BF-70, §3.

---

## 1. What was true on `origin/dev` before this branch

`lib/server/query.js` `create()` returns `params.find` essentially verbatim as the MongoDB filter,
with per-field type conversion applied to the fields a walker names. There is no allowlist, no
denylist, and no validation of operator names anywhere on the v1 path. Measured by building the
filter on both refs:

| query string | `origin/dev` `a8888f0d` | `bf/coercion` (#8737) |
|---|---|---|
| `find[$where]=this.sgv==100` | `{"$where":"this.sgv==100", …}` | identical |
| `find[$or][0][$where]=…` | `{"$or":[{"$where":"…"}], …}` | identical |
| `find[sgv][$where]=…` | `{"sgv":{"$where":NaN}, …}` | `{"sgv":{"$where":"…"}}` |
| `find[sgv][$regex]=^1` | `{"sgv":{"$regex":NaN}, …}` | `{"sgv":{"$regex":"^1"}}` |

Only the last two rows differ between the branches, and both are inert as exposure. Against live
`mongod 7.0`:

```
top-level $where    -> executes; returns the matching document
nested $where       -> ERROR: $where cannot be applied to a field
nested $expr/$text/$jsonSchema/$comment -> ERROR: unknown operator
nested $regex on a numeric field        -> []   (regex never matches non-strings)
```

So **`$where` reaches the driver identically on both branches**, because the top level was never
walked by the coercer on either. #8737 neither opens nor closes that door. The door was BF-04's,
and it was open.

`$projection` is not a MongoDB query operator and does not appear. API v1 builds no projection from
user input; API v3's `?fields=` goes through `lib/api3/shared/fieldsProjector.js`, and v3 has had a
strict nine-operator allowlist with an HTTP 400 since before this programme
(`lib/api3/generic/search/input.js:55-73`). **v1 was the only unguarded read surface.**

Reachability: `GET /api/v1/entries` is gated on `api:entries:read`, which
`AUTH_DEFAULT_ROLES=readable` — the shipped default — grants **without a token**.

## 2. BF-04, extracted — commits 1 and 2

The seam branch's `seam/t2-4-allowlist` commit `987e9657` already contained a complete, tested
allowlist, sitting on top of T1.2, T1.3 and T2.0. That is exactly why BF-04 shipped to nobody. The
extraction rebases the two useful files onto `dev` and rewrites what the seam's framing asserts.

**The framing had to invert, and that is the substantive editorial change.** On the seam, the
module is *"a better error message in front of an existing structural guard"* — the filter AST
cannot represent an unlisted operator, so `fromMongo()` already throws. On `dev` there is no AST,
so **on this branch the module IS the guard**. The seam's file says so about itself in three
paragraphs that would have been false here.

`lib/storage/assert-no-query-javascript.js` is carried across **byte-identical, at the same path**,
so landing this ahead of the seam costs that branch nothing.

### 2.1 The accept set, and why it is not the measured set

The [operator census](../tenancy/v1-operator-census-2026-09-14.md) read 14 client projects and
found 157 literal `find[field][$op]` occurrences: `$gte` 55, `$eq` 36, `$lte` 32, `$gt` 22, `$lt`
5, `$ne` 4, `$exists` 3, `$or` 2, `$and` 1. Nothing in the corpus sends `$where`, `$expr`,
`$elemMatch` or `$near`.

Read with its limit: it measured client **source**, so a filter concatenated at runtime or typed
into a browser is invisible to it. A lower bound, not a proof of absence.

So the set is **not trimmed to the measured set**. It is the storage seam's accept set exactly — a
superset of everything measured:

```
on a field   $eq $ne $gt $gte $lt $lte $in $nin $exists $regex ($options)
at the top   $and $or, and their branches, including the indexed form
             find[$and][0][field][$op]=value that Trio sends
```

Matching the seam is the point: whatever this refuses today, the seam would have refused later
anyway, so landing it now is **one narrowing rather than the first of two**.

### 2.2 Two operators that work today and are now refused

| operator | reachable today via | why refused |
|---|---|---|
| `$expr` | `/api/v1/profiles/` — `profile.list_query` reaches the raw collection | embeds the aggregation expression language in a find filter, with `$function`/`$accumulator` held out only by a denylist enumerating names against a language that grows each release; cannot use an index; every future backend would owe it an expression evaluator |
| `$type` | any typed field, e.g. `find[sgv][$type]=2` | pure element matching and harmless in itself, but outside the seam's set and sent by no surveyed client |

**`$type` is the one place this collides with PR #8737, and the collision is measured, not
predicted.** #8737 added `readTypeOperand()` specifically so that `find[sgv][$type]=2` keeps
reaching MongoDB as the number `2` rather than becoming an HTTP 500 — its commit message argues
that excluding it *"would have turned a working request into an HTTP 500."* This allowlist runs
first, so that reader becomes unreachable through the HTTP path.

Trial-merging `bf/operators` into `bf/coercion` and running the full suite: **2160 passing, 3
pending, 3 failing.** The three are all #8737's own, and all three are the allowlist refusing an
operator whose *operand handling* #8737 wrote a test around:

```
tests/query.operands.test.js  $exists  reads the operand at any depth, including under $not   -> $not refused
tests/query.operands.test.js  leaves $options, $type and $text alone                          -> $type refused
tests/query.test.js           reads a $type operand as a BSON code, and leaves aliases alone  -> $type refused
```

**This is a maintainer's decision and is recorded rather than made.** Two resolutions, neither of
which is obviously right:

1. Add `'$type'` to `FIELD_OPERATORS` in `lib/server/query-operator-allowlist.js`. One line. Keeps
   #8737's reader live, and makes v1 differ from the seam by one operator — a second narrowing
   later. Does **not** fix the `$not` and `$text` rows, which are about operators #8737 never meant
   to endorse either.
2. Update those three assertions on `bf/coercion` to expect the 400, and note `readTypeOperand()`
   as unreachable-but-harmless. Fixture-only edits; the coercion module's behaviour is unchanged.

The evidence leans to (2) — the census found zero demand for `$type`, and a set that matches the
seam is worth more than one operator — but that is an argument, not a mandate.

### 2.3 What is deliberately NOT refused

Values are not recursed into. `{payload: {$eq: {$where: 'literal'}}}` asks whether the stored
document has a field literally named `$where`. It is data, MongoDB treats it as data, and refusing
it would be a compatibility break invented here — the one failure mode this guard must not have.

A native `RegExp` value survives, which matters: the treatments walker turns `find[eventType]=Bolus`
into `{eventType: /Bolus/}` before anything else sees it, and `eventType` is the most common
non-temporal field in the measured surface (§3.1 of the census).

## 3. BF-70 — the count endpoint took its aggregation pipeline from the URL

**Found while tracing BF-04's blast radius, and worse than BF-04.**

`lib/server/aggregate.js` built its aggregation as

```js
[{$match: <find>}].concat(conf.pipeline || []).concat(opts.pipeline || [])
```

and `opts` is the caller's parsed query string — `count_records` in `lib/api/entries/index.js:519`
passes `req.query` straight to `storage.aggregate()`. So `GET /api/v1/count/:storage/where`
accepted arbitrary **aggregation stages** from the URL, not merely filter operators.

That is a wider surface than `find` by a long way. Aggregation carries `$lookup`, which reads a
collection the endpoint is not about, and the `{$group: {count: {$sum: 1}}}` the module appends
turns the joined result into a number the caller can read back. A `$lookup` followed by a `$match`
on the joined field is therefore **an oracle over any collection in the database**, answered under
HTTP 200 to whatever role can read entries.

- **Reachable unauthenticated** on the shipped default `AUTH_DEFAULT_ROLES=readable`.
- **Undocumented**: `pipeline` appears in neither swagger file, nor the README, nor any client in
  the 14-project census. `conf.pipeline` is `{}` at all three construction sites (`entries`,
  `treatments`, `devicestatus`), so nothing in the tree supplies one either.
- **Writes are blocked by accident, not by design.** `$out` and `$merge` must be the last stage and
  the module appends its `$group` after the caller's stages. Nothing asserts that ordering.

**Reproduced 2026-09-18**, through the booted v1 app against `mongod 7.0` with no `api-secret`
header: a value seeded into the auth collection was recovered character by character from the count
alone. The same probe against `bf/operators` returns HTTP 400 and recovers nothing.

> **The reproduction is deliberately not committed to this repository.** This repository is public
> and the defect is live on the current release. The probe is held outside version control; it is
> ~40 lines and reconstructable from this section by anyone who needs it, but publishing a working
> recipe against shipping deployments is not something a fix document should do. **This wants
> coordinated handling rather than an ordinary public PR** — see §5.

The fix refuses the parameter rather than dropping it: dropping it silently would answer a
different question under HTTP 200, which is the failure mode this whole branch exists to remove.
`conf.pipeline` is kept, still works, and gets a backstop pass through the JavaScript guard because
it is now the only way a stage reaches the pipeline.

## 4. Verification

Every figure below was run in this session, in `externals/work/crm-bf-operators`, against
`mongod 7.0` on port 27018 where a database was needed.

| suite | result |
|---|---|
| `tests/mongo-query-javascript.test.js` | 23 passing, 49 ms, no database |
| `tests/api-v1-operator-allowlist.test.js` | 62 passing + 16 pending, 62 ms, no database |
| the same, with `CUSTOMCONNSTR_mongo` set | **78 passing**, 130 ms |
| `tests/api-v1-count-pipeline.test.js` | 8 passing, 30 ms, no database |
| `npm test` (whole suite, live mongod) | **2137 passing, 3 pending, 0 failing** |

The 16 pending are the end-to-end section — the only place the allowed operators are proved to
still **select** correctly rather than merely to pass the guard. It skips without a database; CI
has one.

**Ablations, each confirmed applied by `grep` before the run**, because a green ablation that never
landed is the failure mode this programme has hit twice:

| ablation | result |
|---|---|
| comment out `assertNoQueryJavascript()` in `create()` | 14 of 23 fail |
| comment out `assertAllowedQueryOperators()` in `create()` | 14 fail |
| make `refuse()` return instead of throwing | 36 fail |
| restore the two lines commit 3 changes in `aggregate.js` | 3 of 8 fail |

**The strongest control is the live one**: the unchanged BF-70 probe extracts a token on
`a8888f0d` and extracts nothing on `52b7b640`, same machine, same database, same session.

### 4.1 Merge behaviour against the rest of Phase 0

Trial-merged against every Phase 0 branch:

| branch | result |
|---|---|
| `bf/alarms` `bf/auth` `bf/cache` `bf/coercion`\* `bf/connect-pin` `bf/food` `bf/merge` `bf/parms` `bf/throttle` | clean |
| `bf/reads` | **conflicts on `lib/server/aggregate.js`** |

\* `bf/coercion` merges cleanly but fails 3 of its own tests afterwards — §2.2.

The `bf/reads` conflict is mechanical and both edits compose: that branch makes `aggregate.js`
build its `$match` through the collection's own `query_for` (BF-01) and deletes two `console.log`s
(BF-05); this branch refuses `opts.pipeline` and adds the JavaScript backstop. Resolved and
measured: **2172 passing, 3 pending, 0 failing.** The resolution is recorded in §4.2 so it does not
have to be rediscovered.

One fixture in `tests/api-v1-count-pipeline.test.js` was written to survive both shapes — the stub
collection carries a `query_for` — so the file does not have to know which branch it is on.

### 4.2 The `bf/reads` resolution

```js
var assertNoQueryJavascript = require('../storage/assert-no-query-javascript');
var runWithCallback = require('../storage/run-with-callback');
// ... refusePipeline() unchanged from bf/operators ...
  function aggregate (opts, done) {
    if (opts && opts.pipeline !== undefined) { return runWithCallback(refusePipeline, done); }
    var query = api.query_for(opts);          // bf/reads
    var pipeline = (conf.pipeline || [ ]);    // bf/operators
    var groupBy = [ {$match: query } ].concat(pipeline).concat(template( ));
    assertNoQueryJavascript(groupBy);         // bf/operators
    return runWithCallback(function () {
      return api().aggregate(groupBy).toArray();
    }, done);
  }
```

`find_options` is no longer required directly; `query_for` reaches `lib/server/query.js` anyway, so
both guards still run.

## 5. What needs a human

1. **BF-70 disclosure handling.** An unauthenticated read oracle over arbitrary collections, live
   on the shipping release. The ordinary path for this stack is a public PR with a full commit
   message; that is the wrong path here. Someone has to decide sequencing — fix first, publish
   after — and whether Nightscout's security contact process is invoked. **This is the item that
   blocks; everything else here is ordinary review.**
2. **The `$type` decision** in §2.2, which changes PR #8737.
3. **Whether `$expr` on `/profiles/` has a user.** The census found none, and no test in `dev`
   pins it, but the census measured client source.
4. **The three-commit split is the revert boundary**, deliberately: commit 1 closes the JavaScript
   operators and is the narrowest, obviously-correct part; commit 2 carries the compatibility risk;
   commit 3 is BF-70 and is independent of both.

## 6. Still open, not addressed here

- **User-controlled `sort`.** `lib/server/entries.js:44` passes `opts.sort` — `req.query.sort` —
  straight to `.sort()`. Not an injection in the `$where` sense, but a caller can force an
  unindexed sort over a large collection. No register id; not measured.
- **API v3's storage helpers take no JavaScript guard here.** The seam wires
  `assertNoQueryJavascript` into `lib/api3/storage/mongoCollection/{find,modify}.js` as well. v3's
  own operator allowlist means nothing caller-controlled should reach them, so this was left out
  rather than carried across on the same reasoning that scopes the rest of the branch. Worth a
  separate look, not a separate claim.
- **The numeric-comparison-in-`$and`/`$or` gap.** The v1 type walker only visits top-level
  `find[field]` keys, so a numeric bound nested in a logical group reaches MongoDB as a string and
  matches nothing under BSON type ordering. Older than any of this; noted at the fixture that would
  otherwise have hidden it.
