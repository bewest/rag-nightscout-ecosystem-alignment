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

### 2.2 `$expr` is refused; `$type` was, and #8737 merging settled it the other way

| operator | reachable today via | outcome |
|---|---|---|
| `$expr` | `/api/v1/profiles/` — `profile.list_query` reaches the raw collection | **refused** — embeds the aggregation expression language in a find filter, with `$function`/`$accumulator` held out only by a denylist enumerating names against a language that grows each release; cannot use an index; every future backend would owe it an expression evaluator |
| `$type` | any typed field, e.g. `find[sgv][$type]=2` | **allowed** — see below |

**This is the one conclusion in this document that was reversed, and the reversal is the useful
part.** The first revision refused `$type` on the ground that the seam's AST cannot express it and
the census found no sender, and recorded the collision with PR #8737 as a decision for the
maintainer — *"Nothing here presumes it."* Deferring was right at the time and the deferral is what
made the reversal cheap.

`dev` then moved `a8888f0d..fdd08706` and #8737 merged. That changed the facts, not the argument:

- `readTypeOperand()` is no longer a proposal. It is on `dev` because `find[sgv][$type]=2` must
  arrive as the **number** `2` — as `"2"` the server answers *"Unknown type name alias: 2"* and a
  working request becomes an HTTP 500. Code, test, and a measurement against mongod 3.6.8 and
  7.0.43.
- Refusing `$type` would regress a fix that landed a week earlier in the same release train, to
  gain nothing. It executes nothing, evaluates nothing, reads nothing outside the document.
- *"Matches the seam exactly"* is a good tie-breaker while nothing is at stake. It is not a reason
  to undo a measured decision.

**So `$type` is allowed, and it is the one departure from the seam's set. Priced here rather than
discovered later: when the seam lands, its AST needs a `$type` node, or v1 narrows by one operator
at that point.**

`$not` and `$text` stay refused. Both were *fixtures* in #8737's tests, not subjects — chosen to
express "the operand is reached by operator, not by position" and "this reader does not
generalise" — and neither has a measured caller. `$text` could never have worked on a field anyway:
MongoDB answers "unknown operator: $text" outside the top level, and Nightscout creates no text
index for the top-level form. Both assertions are **rewritten, not deleted**: the depth property is
asserted through `$and`, which is allowed and is the same claim, and each file gains an explicit
assertion that the operator is refused, because a deleted assertion and a deleted capability look
identical six months later. `tests/query.test.js` is untouched — its `$type` test passes as written
once `$type` is allowed, which is the point.

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
| `tests/api-v1-operator-allowlist.test.js` | 63 passing + 16 pending, 60 ms, no database |
| the same, with `CUSTOMCONNSTR_mongo` set | **79 passing**, 129 ms |
| `tests/api-v1-count-pipeline.test.js` | 8 passing, 30 ms, no database |
| `npm test` (whole suite, live mongod) | **2223 passing, 3 pending, 0 failing** |

*(Figures re-measured on the `dev` merge `9745cae2`, not carried over from the pre-merge run.)*

The 16 pending are the end-to-end section — the only place the allowed operators are proved to
still **select** correctly rather than merely to pass the guard. It skips without a database; CI
has one.

**Ablations, each confirmed applied by `grep` before the run**, because a green ablation that never
landed is the failure mode this programme has hit twice:

| ablation | result |
|---|---|
| comment out `assertNoQueryJavascript()` in `create()` | 7 of 23 fail |
| comment out `assertAllowedQueryOperators()` in `create()` | 14 fail |
| make `refuse()` return instead of throwing | 35 fail |
| restore the two lines commit 3 changes in `aggregate.js` | 3 of 8 fail |

**The first row was 14 before the merge and is 7 after, and the drop is a finding rather than a
weakening.** The guards overlap: with the JavaScript guard removed the allowlist still refuses
`$where`, as an unlisted operator with the generic message. The 7 are the cases asserting the
*specific* "server-side JavaScript is not allowed" wording. That guard is now mostly about the
message, not the refusal — worth knowing before anyone proposes dropping it as redundant.

**The strongest control is the live one**: the unchanged BF-70 probe extracts a token on
`a8888f0d` and extracts nothing on `52b7b640`, same machine, same database, same session.

### 4.1 `dev` moved, and the branch is merged up

`dev` went `a8888f0d..fdd08706` while #8743 was open, taking #8733, **#8737 (`bf/coercion`)**,
**#8738 (`bf/reads`)** and #8734 (`bf/merge`). Merged in at `9745cae2`. Two conflicts:

- **`lib/server/aggregate.js`, textual** — resolved exactly as §4.2 predicted on 2026-09-18 against
  the then-unmerged `bf/reads`. The prediction held. `lib/server/query.js` auto-merged and the
  result is correct by inspection: both guards on the caller's literal input, then the schema
  walker, then `normalizeOperands`.
- **`$type`, semantic** — §2.2. This is the one that mattered, and it was invisible to
  `git merge-tree`: the trial merge reported *clean* against `bf/coercion` and the branch's own
  test suite is what caught it, three failures, all fixtures.

**That is the reusable lesson: a clean textual merge against a branch is not evidence of
compatibility with it.** The pre-merge check recorded `bf/coercion` as "clean" with an asterisk
only because the suite was also run. Without that run the collision would have landed silently.

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
- **API v3 needs no equivalent — resolved 2026-09-18, by measurement, after the question was asked
  in review.** The earlier text here said v3's allowlist means "nothing caller-controlled *should*
  reach" its storage helpers, and marked it "worth a separate look, not a separate claim". The look
  has now happened and the claim is safe to make.

  v3 is structurally non-injectable. `lib/api3/storage/mongoCollection/utils.js` `parseFilter()`
  assigns `filter[field]['$eq'] = value`, so a client value is only ever the **operand** of one of
  nine hard-coded operators; `lib/api3/generic/search/input.js:71` refuses any other operator with a
  400. A value can never become a key, which is the position an operator must occupy.

  The one client-controlled key is the field *name* (`filterRegex` is `/(.*)\$([a-zA-Z]+)/` and the
  `(.*)` is unvalidated). Every dangerous operator placed there errors on mongod 7.0, because none
  accepts an operand of the shape those nine produce — `$where` "got bad type", `$or`/`$nor` "must
  be an array", `$expr` arity, `$text` missing `$search`, `$jsonSchema` unknown keyword. `$comment`
  is accepted and inert.

  Write paths were already closed on purpose: `identifyingFilter()` wraps client values in `$eq`
  with a comment saying it is there to stop `{$ne: null}` in a posted document becoming an operator.
  `deleteManyOr()` is reachable only from `autoPrune()` with a server-built filter. Projections are
  `0`/`1` only.

  **What v3 does share with v1 is `re` → `$regex` over a client-supplied string** — the same
  exposure as advisory PoC C, reached through a documented operator rather than by injection. The
  `parseRegEx` decision on v1 and the `re` decision on v3 should be taken together.

  **The field-name position is worth remembering even though it is inert.** It is inert because of
  what MongoDB rejects, not because Nightscout validates it, so it would become live if anyone ever
  changed `parseFilter` to pass a value through unwrapped.
- **The numeric-comparison-in-`$and`/`$or` gap.** The v1 type walker only visits top-level
  `find[field]` keys, so a numeric bound nested in a logical group reaches MongoDB as a string and
  matches nothing under BSON type ordering. Older than any of this; noted at the fixture that would
  otherwise have hidden it.
