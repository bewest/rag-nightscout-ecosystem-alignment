# `bf/coercion` — API filters returned the wrong records, and one returned the exact opposite

Two commits on `origin/dev` `a8888f0d`: `f829ea11` types filter values from the collection schemas,
`b7234753` reads the operands that are not values. 10 files, +739/−23. Independent of every other
Phase 0 branch; merges clean against `dev` and against all eight of them.

**Why one PR and not two.** They are the two halves of one thing — how the text in a web address
becomes a typed database query — and each is incomplete alone. Measured: with only the second
commit, `$exists=false` stays wrong on `sgv`, `insulin`, `carbs`, `glucose` and the raw sensor
fields, because the first commit is what stops those operands being destroyed before they can be
read. Those are the fields anyone actually filters on. The commits are separate so either can be
reverted on its own.

## What changes for you

**If you have ever filtered a Nightscout API read and got an empty list for no obvious reason, or
asked for records *without* something and got the records *with* it — this is why, and both now
work. Your stored data is not touched.** What changes is which of your records a filter finds.

When you ask Nightscout for records matching a condition — a report, a dashboard, a spreadsheet
script, a URL with `find[...]` in it — everything you typed arrives as text, and Nightscout has to
decide what it meant.

**1. Filters that returned nothing now return your records.** Nightscout decided which values were
numbers from a hand-written list of 13 fields. **A field not on that list kept your value as text,
and text never matches a number**, so the database found nothing and answered with an empty list
and a success code — no error, and no way to tell "you have no records like that" from "the
question was asked wrongly." `/api/v1/treatments.json?find[duration][$gte]=30` — temp basals of 30
minutes or more — returned `[]` on a database full of them. Also affected: `duration` and `rate` on
treatments (most treatment records for anyone running an automated system), nearly every number and
yes/no field on `devicestatus` including pump and phone battery and reservoir, `entries` fields such
as `delta`, `trend`, `rssi` and `isValid`, and the `profile` `loopSettings` numbers.

**2. Asking for records *without* a field returned the records *with* it.** `$exists=false` — "show
me records that do NOT have this" — was answered with exactly the records that do. The word "false"
reached the database as a *word* rather than as an *answer*, and the database reads any word as
"yes". This is how a report asks "which treatments were entered with no carb amount?" or "which
readings arrived with no device attached?" **Every answer from such a filter was the inverse of the
question, and any count drawn from one was counting the wrong group.**

**3. Decimal amounts stop being rounded down.** `find[insulin][$gte]=1.5` was answered as though you
had asked for 1, so **1.0-unit boluses were included**. Same for `carbs`, `glucose`, and `entries`
bounds such as `sgv`, `mbg` and `date`.

**4. A pattern search that returned a server error now works.** `find[sgv][$regex]=^1` produced an
HTTP 500, because the pattern itself was being converted to a number.

### What you should do

**Re-run any report, dashboard, spreadsheet or script built on the filters above, and expect the
numbers to move.** A filter that returned nothing may now return many rows. A decimal bound now
excludes values it previously included. **An `$exists=false` filter now returns the complement of
what it returned before**, so a count from one usually changes a lot rather than a little.

**If you used these filters to review delivered therapy — total insulin over a period, how many
temp basals ran, carbs logged, how many entries were missing a value — earlier results may have
under-reported or over-reported what was actually recorded.** Nothing in your database was wrong;
the question was being asked wrongly. Nightscout is not a medical device and this is not medical
advice. If a corrected figure changes your understanding of a past period, discuss it with your care
team rather than acting on it alone.

`$exists=true` is unaffected — it was answering correctly and still does.

---

## Technical detail

### Commit 1 — `f829ea11`, types come from the schemas

`lib/server/query.js` chose a value's type from a per-collection `walker` map naming 13 fields
across three collections. MongoDB orders BSON types before comparing values, so a numeric field
never matches a string bound — empty list, HTTP 200.

`specs/nsschema/*.model.json` generates `lib/server/query-coercion.json`, mapping each declared
field to a type; `lib/server/query-coercion.js` converts values and leaves the operands of
`$exists`, `$type`, `$regex`, `$options`, `$where`, `$expr`, `$text`, `$comment` and `$jsonSchema`
alone, while still converting every element of an `$in` list. A collection opts in through its
query options:

```js
storage.queryOpts = { collection: 'devicestatus', dateField: 'created_at' };
```

**158 schema-driven coercions across 5 collections replace 13 hand-written entries.** An explicit
`walker` entry still wins, so `treatments` keeps regex search on `notes`, `eventType` and
`enteredBy`. Callers naming no collection are unchanged — they keep the legacy
`{date: parseInt, sgv: parseInt}` guess.

Closes **BF-02**, **BF-11** and **BF-03** (devicestatus and profile).

**One non-value operand still needs reading, and finding that out is why this is not just an
exclusion list.** `$type` takes a BSON type code or a string alias, so `find[sgv][$type]=2` has to
reach the server as the number `2`; as the string `"2"` it is rejected with *"Unknown type name
alias: 2"*. `origin/dev` coerced it along with everything else and it worked — so excluding it
without reading it would have turned a working request into an HTTP 500. `operandReaderFor` reads a
digits-only `$type` operand as a number and passes aliases through. Filed as **BF-68**, found by
measuring and fixed here before this PR was opened.

### Commit 2 — `b7234753`, operands that are questions, not values

Measured against live `mongod` **3.6.8 and 7.0.43**, identical on both, over
`[{_id: 1, sgv: 100}, {_id: 2}]`:

| `$exists` operand | returns | reading |
|---|---|---|
| `false` (boolean), `0`, `null` | `[2]` | lacks the field — correct |
| `"false"`, `"0"`, `""`, `NaN`, `[]` | `[1]` | **has the field** — the defect |

MongoDB's truthiness for a string is "any string, including the empty one", so every spelling a
query string can produce reads as true. End to end, over two treatments, one with `insulin`:

```
find[insulin][$exists]=false    before -> {"$exists":"false"}   returns the doc WITH insulin
                                after  -> {"$exists":false}     returns the doc WITHOUT
```

`normalizeOperands` runs over the **finished query**, keyed on the operator, so it reaches every
field whether or not the schema types it — and handles `{$not: {$exists: "false"}}` and an operand
inside `$or`. **This is deliberately not inside the per-field walker**, where register entry BF-40
prescribed it: that code only runs for fields with a declared type, so a fix there would have closed
this for `sgv` and left it open on `madeUpField`, `notes` and every field of `activity`, which never
enter it at all.

**What is read:** `"true"`/`"1"` → `true`, `"false"`/`"0"` → `false`, case-insensitive. Non-string
operands pass through. **The empty string is left alone on purpose** — `?find[x][$exists]` with no
value parses to `''`, which `bf/parms` (BF-37) makes reachable, and it is as easily "yes, I want
this flag" as "no". Guessing would silently invert somebody's query, which is the defect being
removed, not a licence to commit it in the other direction. A test pins the decision.

**`$regex` is untouched and must stay untouched.** It wants a string and already gets one; reading
it as a boolean would break the patterns `0`, `1` and `true`. `$type` is the opposite case, which is
why commit 1 gives it a reader rather than an exemption — "leave every non-value operand alone" is
not a rule, it is a per-operator question.

Closes **BF-32** (re-graded low — `{$exists: NaN}` reads as *true*, so it was answering correctly by
accident; `{$regex: NaN}` was the real breakage) and **BF-40**.

> One line for anyone using `mingo` as a query oracle: it applies JavaScript truthiness and reports
> the opposite for `NaN`. **A claim about a malformed operand has to come from a server.**

## Verifying it

```
TEST=query npm run test-single             # 29 passing, 15 ms, no database
TEST=query.operands npm run test-single    # 12 passing,  8 ms, no database
```

`tests/query.test.js` is inside the `test:unit` brace list; `tests/query.operands.test.js` is a new
file and matches **neither** list, so `npm run test:unit` does not run it — `npm test` and CI's
`test-ci` over `./tests/*.test.js` do. `tests/query.test.js` **cannot load** on pristine
`origin/dev` (`Cannot find module '../lib/server/query-coercion'`), so it distinguishes fixed from
unfixed by construction. `test:unit` still needs MongoDB for six unrelated files (`careportal`,
`security`, `verifyauth`); those failures are environmental and the dev baseline fails the same six.

**Non-vacuity on commit 2**, each break confirmed to land before the suite ran:

| ablation | result |
|---|---|
| remove the `normalizeOperands` call | **6 failing** |
| also map `""` to `false` | **1 failing** — exactly the test pinning that decision |
| add `$regex` to the reader map | **1 failing** — exactly the `$regex` test |

Dropping commit 1's `$type` reader fails **1**. Restoring each returns the full count, so every
failure belonged to its own break.

## Semver: minor

It changes which records a filter returns, but adds no required input, removes no route and breaks
no documented contract. No operator action, no configuration break, stored data untouched. A report
built on a broken filter needs re-running, which is a release note rather than a migration.
Classification in `docs/60-research/gt4-semver-classification-2026-09-15.md` row 12.

**The "What changes for you" text above is the release-note source.** It is not a `CHANGELOG.md`
entry and this branch adds none — `CHANGELOG.md` is a release output. Two things must survive into
the release notes: the sentence about earlier results under- or over-reporting delivered therapy,
and the `$exists=false` inversion, which is the one an operator is most likely to have acted on.

## Evidence

- Backfix register `docs/30-design/nightscout-backfix-register.md` — BF-02, BF-03, BF-11, BF-32
  (low, mechanism corrected), BF-40, BF-68.
- T0.5 evidence `docs/60-research/t05-schema-driven-coercion-2026-09-15.md`.

## Follow-ups deliberately not in this PR

- **The interaction with `bf/reads` — real, and not a merge hazard.** This branch gives `query.js` a
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
- **`lib/authorization/storage.js:84` has an unguarded `console.log` on a request path**, same shape
  as BF-05.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared against
  `!== null`. No caller, so no register id.
