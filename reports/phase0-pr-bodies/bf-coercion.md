# `bf/coercion` — filters that quietly returned nothing now return your records

One commit `f829ea11`, 9 files, +560/−23. Base `origin/dev` `a8888f0d`. Independent of every
other Phase 0 branch; merges clean against `dev` and against all nine of them.

## What changes for you

**If you have ever filtered a Nightscout API read and got back an empty list for no obvious
reason, this is why, and it now works. Your stored data is not touched.** What changes is which
of your records a filter finds.

When you ask Nightscout for records matching a condition — a report, a dashboard, a spreadsheet
script, a URL with `find[...]` in it — it has to decide whether the value you typed is a number, a
yes/no flag, or text. It decided from a hand-written list of 13 fields. **A field not on that list
kept your value as text, and text never matches a number**, so the database found nothing and
answered with an empty list and a success code. No error was shown, and you could not tell "you
have no records like that" from "the question was asked wrongly."

**1. Filters that returned nothing now return your records.**
`/api/v1/treatments.json?find[duration][$gte]=30` — temp basals of 30 minutes or more — returned
`[]` on a database full of them. Also affected: `duration` and `rate` on treatments (most treatment
records for anyone running an automated system), nearly every number and yes/no field on
`devicestatus` including pump and phone battery and reservoir, `entries` fields such as `delta`,
`trend`, `rssi` and `isValid`, and the `profile` `loopSettings` numbers.

**2. Decimal amounts stop being rounded down.** `find[insulin][$gte]=1.5` was answered as though
you had asked for 1, so **1.0-unit boluses were included**. Same for `carbs`, `glucose`, and
`entries` bounds such as `sgv`, `mbg` and `date`.

**3. A pattern search that returned a server error now works.** `find[sgv][$regex]=^1` produced an
HTTP 500, because the pattern itself was being converted to a number.

### What you should do

**Re-run any report, dashboard, spreadsheet or script built on the filters above, and expect the
numbers to move.** A filter that returned nothing may now return many rows; a decimal bound now
excludes values it previously included.

**If you used these filters to review delivered therapy — total insulin over a period, how many
temp basals ran, carbs logged — earlier results may have under-reported or over-reported what was
actually recorded.** Nothing in your database was wrong; the question was being asked wrongly.
Nightscout is not a medical device and this is not medical advice. If a corrected figure changes
your understanding of a past period, discuss it with your care team rather than acting on it alone.

### One thing this does NOT fix

**`find[<field>][$exists]=false` — "records that do NOT have this field" — returns the records that
DO have it, on every field, before and after this change.** It answers with a success code, so
nothing warns you. Open as **BF-40**, fix designed, not written. If a report or script of yours
uses `$exists=false`, its results are the opposite of what you asked for.

(`$exists=true` is unaffected: it answered correctly before and answers correctly after. Nothing
you did with it needs re-running.)

---

## Technical detail

`lib/server/query.js` chose a value's type from a per-collection `walker` map naming 13 fields
across three collections. MongoDB orders BSON types before comparing values, so a numeric field
never matches a string bound — empty list, HTTP 200.

The replacement is schema-driven. `specs/nsschema/*.model.json` generates
`lib/server/query-coercion.json`, mapping each declared field to a type;
`lib/server/query-coercion.js` converts values and leaves `$exists`, `$type`, `$regex`,
`$options`, `$where`, `$expr`, `$text`, `$comment` and `$jsonSchema` operands alone, while still
converting every element of an `$in` list.
A collection opts in through its query options:

```js
storage.queryOpts = { collection: 'devicestatus', dateField: 'created_at' };
```

**158 schema-driven coercions across 5 collections replace 13 hand-written entries.** An explicit
`walker` entry still wins, so `treatments` keeps regex search on `notes`, `eventType` and
`enteredBy`. Callers naming no collection are unchanged — they keep the legacy
`{date: parseInt, sgv: parseInt}` guess.

**One non-value operand still needs reading, and finding that out is why this is not just an
exclusion list.** `$type` takes a BSON type code or a string alias, so `find[sgv][$type]=2` has to
reach the server as the number `2`; as the string `"2"` it is rejected with *"Unknown type name
alias: 2"*. `origin/dev` coerced it along with everything else and it worked — so excluding it
without reading it would have turned a working request into an HTTP 500. `operandReaderFor` reads a
digits-only `$type` operand as a number and passes aliases through. Every other non-value operator
has no reader, which is the right answer for `$regex` and `$options`: they want the string they
already have. Filed as **BF-68**, found by measurement and fixed here before the PR was opened.

Closes **BF-02**, **BF-11** and **BF-03** (devicestatus and profile). **BF-32** was found while
writing it: the walker coerced operator *operands* too, so `find[sgv][$exists]=true` became
`{$exists: NaN}` and `find[notes][$regex]=ab` became `{$regex: NaN}`.

### What BF-32 actually costs, measured

Measured against live `mongod` 3.6.8 and 7.0.43 — seven servers, identical results — because
MongoDB's numeric truthiness is `value != 0`, and `NaN != 0`:

| `$exists` operand | over `[{_id:1, sgv:100}, {_id:2}]` | reading |
|---|---|---|
| `true` / `"true"` / `""` / `NaN` | `[1]` | has the field |
| `false` (boolean) / `0` | `[2]` | lacks it |
| `"false"` | **`[1]`** | **has it** — this is BF-40 |

So `{$regex: NaN}` is the real breakage: an HTTP 500, *"$regex has to be a string"*. `{$exists: NaN}`
reads as true and was answering correctly by accident. **BF-32 is therefore low, not medium**, and
the fix is still right: coercing an operand that is not a field value is wrong regardless of how
MongoDB happens to read the result, and generalising coercion from 13 fields to 158 would have
generalised the defect with it.

> Worth one line for anyone using `mingo` as a query oracle: it applies JavaScript truthiness and
> reports the opposite for `NaN`. **A claim about a malformed operand has to come from a server.**

## Verifying it

```
TEST=query npm run test-single     # 28 passing, 17 ms, no database needed
```

`tests/query.test.js` is inside the `test:unit` brace list, so `npm run test:unit` covers it too —
unlike `bf/food`, `bf/merge` and `bf/parms`. The test **cannot load** on pristine `origin/dev`
(`Cannot find module '../lib/server/query-coercion'`), so it distinguishes fixed from unfixed by
construction. `test:unit` still needs MongoDB for six unrelated files (`careportal`, `security`,
`verifyauth`); those failures are environmental and the dev baseline fails the same six.

`tests/query.test.js:137` covers `$exists=true` only. BF-40's regression test does not exist and
has to be written alongside its fix.

## Semver: minor

It changes which records a filter returns, but adds no required input, removes no route and breaks
no documented contract. No operator action, no configuration break, stored data untouched. A report
built on a broken filter needs re-running, which is a release note rather than a migration.
Classification in `docs/60-research/gt4-semver-classification-2026-09-15.md` row 12.

**The "What changes for you" text above is the release-note source.** It is not a `CHANGELOG.md`
entry and this branch adds none — `CHANGELOG.md` is a release output. Two things must survive into
the release notes: the sentence about earlier results under- or over-reporting delivered therapy,
and the `$exists=false` warning, which is about a defect that is still open.

## Evidence

- Backfix register `docs/30-design/nightscout-backfix-register.md` — BF-02, BF-03, BF-11, BF-32
  (low, mechanism corrected), BF-40 (open).
- T0.5 evidence `docs/60-research/t05-schema-driven-coercion-2026-09-15.md`.

## Follow-ups deliberately not in this PR

- **BF-40 is written, on its own branch `bf/exists`** — not here, because this is already the
  largest behavioural change in Phase 0 and that fix stands alone against `dev`. **The two
  compose, and the composition was measured rather than assumed**: `bf/exists` reads the `$exists`
  operand in a pass over the finished query, which reaches every field; on today's `dev` the walker
  destroys that operand first for the thirteen fields it names, so **`bf/exists` needs this branch
  to close its typed half**. Merged tree: 29 + 12 passing, `$exists=false` correct on typed and
  untyped fields alike. This branch's "operands are left alone" test asserts the operand was not
  turned into a *number* rather than pinning the exact string, so the two do not collide.
- **Interaction with `bf/reads` — real, and not a merge hazard.** This branch gives `query.js` a
  `collection:` option; `bf/reads` fixes `aggregate.js`, which calls it. Measured: the count path is
  typed correctly after both land, because BF-01's fix makes `aggregate` delegate to each
  collection's own `query_for`, and each names its collection. Both controls (`origin/dev`,
  pre-rebase `bf/reads`) produce `{"$lte":"20"}`; the merged tree produces `{"$lte":20}`. An
  end-to-end test against a live database is still missing.
- **`lib/authorization/storage.js` names no collection**, so it keeps the legacy guess. Inert today
  — auth documents have neither `date` nor `sgv` — but worth naming a collection so it cannot become
  live later.
- **The limit rule is written twice**, in `lib/server/count.js` and API v3's `parseLimit`. Note
  `count.js` does not exist on `origin/dev`; `bf/reads` creates it, so landing E creates the
  duplication.
- **`lib/authorization/storage.js:84` has an unguarded `console.log` on a request path**, same
  shape as BF-05.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared against
  `!== null`. No caller, so no register id.
