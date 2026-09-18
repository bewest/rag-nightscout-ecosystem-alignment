# `bf/operators` — API v1 accepted any MongoDB operator a caller named, including the ones that run JavaScript

Three commits on `origin/dev` `a8888f0d`, tip `52b7b640`. 15 files, +1032/−3. Merges clean against
`dev` and against every Phase 0 branch except `bf/reads`, which touches the same function — see
[Landing order](#landing-order).

> **READ THIS BEFORE THE REST.** This branch closes **one of the three** proof-of-concepts in the
> reported NoSQL-injection advisory, plus a second defect the advisory does not mention.
> **It does not close that advisory.** Exactly what is and is not fixed is in
> [What this does not fix](#what-this-does-not-fix), stated before the good news rather than after
> it, because a partial fix that reads as a complete one is worse than no fix.

## What changes for you

**Your stored data is not touched.** What changes is which requests the API answers at all.

### 1. A web address could ask the database to run a program

Nightscout's older API lets you filter records by putting conditions in the web address —
`?find[sgv][$gte]=100` means "glucose readings of 100 or more". Those conditions were passed to the
database **without any check on which ones were allowed**, and MongoDB has conditions that are not
filters at all: `$where` and `$function` hand it a piece of JavaScript and ask it to run that
against your records.

On a default Nightscout this needed **no password and no token**, because the shipped setting
`AUTH_DEFAULT_ROLES=readable` lets anyone who knows your address read your glucose data. Those are
now refused with a clear error.

### 2. One address could ask questions about parts of the database it had no business reading

`/api/v1/count/…/where` counts matching records. It also accepted a `pipeline` setting that let the
request add its own processing steps — including a step that reads a **different** collection and
folds the result into the count. Nothing documents this setting and no known app uses it. Repeated
with different guesses, the count answers questions about data the address was never meant to
reach. **Also unauthenticated on a default install.** The setting is now refused.

### 3. Unusual filters now say so instead of appearing to work

The API now supports a fixed, documented list of filter conditions and refuses anything else with
an error naming it. Ordinary filters are unaffected — date ranges, event types, glucose thresholds,
`$exists`, text searches. A survey of 14 Nightscout client projects found **157** filter uses and
**none** of them uses anything now refused.

Two things that work today are deliberately refused: `$expr` on `/api/v1/profiles/`, and `$type`.
See [The accept set](#the-accept-set).

### 4. A refused filter no longer looks like the server breaking

Every read endpoint reported a bad filter as HTTP 500 under a name blaming the database — `Mongo
Error`, `Query Error` — and two did worse: `/api/v1/activity` never checked for the error and threw
while formatting nothing, and `/api/v1/profiles/` ignored it and answered `200` with an empty body.
A 500 on a read is indistinguishable from your server being down. These now answer `400` and name
the operator.

### What you should do

**If a report, dashboard or script you use starts returning a 400 after this lands, it is telling
you the request used a filter condition the API does not support — it is not a sign your data is
gone.** The error names the condition and lists the supported ones. Nothing stored changes.

Nightscout is not a medical device and this is not medical advice. If you rely on a tool that
breaks, raise it with that tool's author; if a gap in your data display worries you, talk it through
with your care team rather than acting on it alone.

---

<a name="what-this-does-not-fix"></a>
## What this does not fix

Measured against the reported advisory's own proof-of-concepts, on this branch:

| advisory PoC | status on `bf/operators` |
|---|---|
| **B** — `find[$where]=…`, server-side JavaScript execution | **refused, 400** |
| **A** — `find[dateString][$ne]=x`, bypasses the server's date window and returns the whole history | **still works** |
| **C** — `find[notes][$regex]=…`, blind extraction of free-text PII from treatments | **still works** |

**PoC A is the advisory's headline impact and its primary evidence.** `$ne` is an ordinary
comparison and is on the accept set; `enforceDateFilter()` applies its bound only when neither the
date field nor `dateString` appears in the query at all, so naming the date field in any form
removes the bound. An allowlist cannot close that — the operator is legitimate and the defect is in
where the bound is applied.

**That is deliberately not fixed here, and it is not a small fix.** Always AND-ing the window onto
every query breaks every historical read: 105 of the 157 measured client filter uses are
time-ranging, and asking for an older window is the normal thing for a report to do. The real fix is
to refuse an *unbounded* date predicate while still honouring a bounded one, which is a
compatibility decision with its own evidence requirement. **It needs its own issue and its own
change.**

**PoC C is also not fixed, and `$regex` is allowed on purpose.** `lib/server/treatments.js`
compiles `notes`, `eventType` and `enteredBy` through `parseRegEx` regardless, so
`find[eventType]=Bolus` is already a regular expression by the time it reaches the driver, and
`eventType` is the most common non-temporal field in the measured client surface. Removing regex
matching is a capability removal, not a bug fix.

Against the advisory's five remediation items: **1 and 2 are done here. 3, 4 and 5 are not.**

## The accept set

```
on a field   $eq $ne $gt $gte $lt $lte $in $nin $exists $regex (with $options)
at the top   $and $or, and their branches, including the indexed form
             find[$and][0][field][$op]=value
```

Everything else is refused with HTTP 400 naming the operator and listing what is supported.

**Why this set and not a shorter one.** The census of 14 client projects measured `$gte` 55, `$eq`
36, `$lte` 32, `$gt` 22, `$lt` 5, `$ne` 4, `$exists` 3, `$or` 2, `$and` 1 — all of them in the set
above, and nothing sending `$where`, `$expr`, `$elemMatch` or `$near`. **Read that with its limit:
it measured client source code, so a filter assembled at runtime or typed into a browser is
invisible to it.** It is a lower bound, not proof of absence.

So the set is **not trimmed to the measured set**. It is the set the in-progress storage seam can
already express — a superset of everything measured — so that whatever this refuses today, the seam
would have refused later anyway. That makes this one narrowing instead of the first of two.

**Two operators that work today are refused:**

- **`$expr`**, reachable through `/api/v1/profiles/`. It embeds the aggregation expression language
  in a find filter, with `$function` and `$accumulator` held out of it only by a denylist that
  enumerates them by name against a language that grows each release; it cannot use an index; and
  every future storage backend would owe it an expression evaluator.
- **`$type`**, which is harmless element matching, but is outside the seam's set and is sent by no
  surveyed client. **This collides with #8737** — see below.

### `$type` and #8737

PR #8737 added `readTypeOperand()` specifically so `find[sgv][$type]=2` keeps reaching MongoDB as
the number `2` rather than becoming a 500. This guard runs first, so once both land that reader is
unreachable over HTTP — not wrong, moot.

**Measured, not predicted**: trial-merging this branch into `bf/coercion` and running the suite
gives **2160 passing, 3 failing**, and all three failures are this allowlist refusing an operator
whose *operand handling* #8737 wrote a test around — `$type`, `$not`, `$text`.

Two resolutions, and **neither is taken here** because it is a decision about #8737, not about this
branch: add `'$type'` to `FIELD_OPERATORS` (one line, keeps the reader, makes v1 differ from the
seam by one operator), or update those three assertions to expect the 400.

## How it works

Three commits, split at the revert boundary so any one can be dropped alone.

**`3e8ce695` — the JavaScript operators.** `assertNoQueryJavascript()` refuses `$where`,
`$function` and `$accumulator` wherever they appear — inside `$and`/`$or` branches, inside
`$all`/`$elemMatch`, inside an `$expr` expression context. It runs in `lib/server/query.js`
`create()`, the one entry point every v1 `find` passes through, on the caller's literal input,
before `enforceDateFilter()` adds its own `$gte` and `updateIdQuery()` mints ObjectIds — so the
operator named in the error is one the caller actually typed.

**Values are not recursed into, deliberately.** `{payload: {$eq: {$where: 'x'}}}` asks whether the
stored document has a field literally named `$where`. It is data, MongoDB treats it as data, and
refusing it would be a compatibility break invented here.

The same commit adds `lib/api/shared/query-error.js` and wires it into all five v1 modules, which
is what turns the refusal into a 400 rather than a 500.

**`71506cf8` — the allowlist**, as above.

**`52b7b640` — the count endpoint's pipeline.** `lib/server/aggregate.js` built its aggregation as
`[{$match: find}].concat(conf.pipeline || []).concat(opts.pipeline || [])`, and `opts` is the
caller's parsed query string: `count_records` passes `req.query` straight to
`storage.aggregate()`. So `GET /api/v1/count/:storage/where` accepted arbitrary **aggregation
stages** from the URL, not merely filter operators — a wider surface than `find`, because
aggregation carries `$lookup`, which reads a collection the endpoint is not about, and the
`{$group: {count: {$sum: 1}}}` the module appends returns the joined result as a number.

The parameter is **refused, not silently dropped**: dropping it would answer a different question
under HTTP 200, which is the failure mode this whole branch exists to remove. `conf.pipeline` — set
by the code, never by a request, and `{}` at all three construction sites — is kept and still works.

`lib/storage/assert-no-query-javascript.js` is carried across from the storage-seam branch
byte-identical at the same path, so landing this ahead of the seam costs that branch nothing.

## Verifying it

```
TEST=mongo-query-javascript npm run test-single      # 23 passing,  49 ms, no database
TEST=api-v1-operator-allowlist npm run test-single   # 62 passing + 16 pending, no database
TEST=api-v1-count-pipeline npm run test-single       #  8 passing,  30 ms, no database
CUSTOMCONNSTR_mongo=… TEST=api-v1-operator-allowlist npm run test-single   # 78 passing
npm test                                             # 2137 passing, 3 pending, 0 failing
```

The 16 pending are the end-to-end section — the only place the **allowed** operators are proved to
still *select* correctly rather than merely to pass the guard. It skips without a database; CI has
one. All three new files are outside `npm run test:unit`'s brace list, so a green run there is not
evidence for this branch; `npm test` is what CI runs.

**Ablations, each confirmed applied by `grep` before the run** rather than assumed:

| ablation | result |
|---|---|
| comment out the JavaScript guard in `create()` | 14 of 23 fail |
| comment out the allowlist in `create()` | 14 fail |
| make `refuse()` return instead of throwing | 36 fail |
| restore the two lines commit 3 changes | 3 of 8 fail |

The strongest control is not a unit test: the unmodified reproduction for commit 3 recovers a
seeded value over unauthenticated HTTP on `a8888f0d` and recovers nothing on `52b7b640` — same
machine, same database, same session.

<a name="landing-order"></a>
## Landing order

Merges clean against `dev`, `bf/alarms`, `bf/auth`, `bf/cache`, `bf/coercion`, `bf/connect-pin`,
`bf/food`, `bf/merge`, `bf/parms` and `bf/throttle`.

**Conflicts with `bf/reads` (#8738)** on `lib/server/aggregate.js`: that branch makes the function
build its `$match` through the collection's own `query_for` and deletes two `console.log`s. The
edits compose and the resolution is mechanical — keep both. Resolved and measured: **2172 passing,
3 pending, 0 failing.** One test fixture here already carries a `query_for` so the file works on
either side of that merge.

## Semver: minor

It removes reachable behaviour — `$expr` on `/profiles/`, `$type` on any typed field, and the
undocumented `pipeline` parameter — so it is not a patch. It is not major either: no route removed,
no required input added, no documented contract broken, and no surveyed client sends anything now
refused. No operator action, no configuration break, stored data untouched.

**The "What changes for you" text above is the release-note source.** Two things must reach the
release notes: that unsupported filter conditions now answer 400 instead of appearing to work, and
that the `pipeline` parameter on the count endpoint is gone.

## Follow-ups deliberately not in this PR

- **The date-window bypass (advisory PoC A)** — the largest remaining item, and the one most likely
  to be mistaken for fixed. Needs its own issue.
- **`parseRegEx` compiles raw client input into a `RegExp`** on `notes`, `eventType` and
  `enteredBy` (advisory remediation item 3, and PoC C).
- **The `AUTH_DEFAULT_ROLES=readable` default** (remediation item 5) is a project policy decision,
  not a code fix.
- **API v3's storage helpers take no JavaScript guard here.** v3 has had its own nine-operator
  allowlist with a 400 since before this work, so nothing caller-controlled should reach them.
  Worth a separate look, not a separate claim.
- **User-controlled `sort`.** `opts.sort` reaches `.sort()` unvalidated; a caller can force an
  unindexed sort over a large collection. Not measured.
- **A numeric comparison nested in `$and`/`$or`** is never type-converted — the walker visits only
  top-level `find[field]` keys — so it reaches MongoDB as a string and matches nothing under BSON
  type ordering. Older than this change; noted at the fixture that would otherwise have hidden it.
