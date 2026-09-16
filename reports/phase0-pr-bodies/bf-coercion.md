# `bf/coercion` — API filters returned the wrong records, and `$exists=false` returned the opposite

Two commits on `origin/dev` `a8888f0d`, tip `b7234753`. 10 files, +739/−23. Merges clean against
`dev` and against every other Phase 0 branch.

Everything in a URL arrives as text, and Nightscout has to decide what that text meant before it
can query the database. It was deciding badly in two different ways, so both are here:
`f829ea11` takes field types from the collection schemas; `b7234753` reads the operands that are
questions rather than values. They are one PR because the second is incomplete without the first —
see [Why one PR](#why-one-pr) — and two commits so either can be reverted alone.

## What changes for you

**Your stored data is not touched.** What changes is which of your records a filter finds.

### 1. Filters that returned nothing now return your records

Nightscout decided which values were numbers from a hand-written list of 13 fields. **A field not on
that list kept your value as text, and text never matches a number.** The database found nothing and
answered with an empty list and a success code — no error, and no way to tell "you have no records
like that" from "the question was asked wrongly."

`/api/v1/treatments.json?find[duration][$gte]=30` — temp basals of 30 minutes or more — returned
`[]` on a database full of them. Also affected: `duration` and `rate` on treatments (most treatment
records for anyone running an automated system), nearly every number and yes/no field on
`devicestatus` including pump and phone battery and reservoir, `entries` fields such as `delta`,
`trend`, `rssi` and `isValid`, and the `profile` `loopSettings` numbers.

### 2. Asking for records *without* a field returned the records *with* it

`$exists=false` — "show me records that do NOT have this" — was answered with exactly the records
that do. The word `false` reached the database as a *word* rather than as an *answer*, and the
database treats any word as "yes".

This is how a report asks "which treatments were entered with no carb amount?" or "which readings
arrived with no device attached?" **Every answer from such a filter was the inverse of the question,
and any count drawn from one was counting the wrong group.**

**Exactly which spellings work.** Two treatments, one with `insulin` and one without,
`find[insulin][$exists]=…`:

| you write | before | after |
|---|---|---|
| `=false` | the one **with** insulin | the one **without** — correct |
| `=0` | the one **with** insulin | the one **without** — correct |
| `=true` `=1` | the one with insulin | unchanged, was already correct |
| `=False` `=TRUE` | wrong / correct | read the same as lowercase |
| `=null` `=no` `=off` `=undefined` `=2` | the one with insulin | **unchanged — still the one with insulin** |
| `=` (nothing after the `=`) | the one with insulin | **unchanged** |

**Only `false`, `0`, `true` and `1` are read.** Any other spelling — including `=null` and an empty
value — still means "has the field". If you have used one of those, it is not fixed by this change
and you should rewrite it as `=false`.

An empty value is left alone deliberately: `?find[x][$exists]` with nothing after it reads as easily
"yes, I want this flag" as "no, I don't", and picking one would silently invert somebody's query.

### 3. Decimal amounts stop being rounded down

`find[insulin][$gte]=1.5` was answered as though you had asked for 1, so **1.0-unit boluses were
included**. Same for `carbs`, `glucose`, and `entries` bounds such as `sgv`, `mbg` and `date`.

### 4. A pattern search that returned a server error now works

`find[sgv][$regex]=^1` produced an HTTP 500, because the pattern itself was being converted to a
number.

### What you should do

**Re-run any report, dashboard, spreadsheet or script built on the filters above, and expect the
numbers to move.** A filter that returned nothing may now return many rows. A decimal bound now
excludes values it previously included. **An `$exists=false` filter now returns the complement of
what it returned before**, so a count from one usually changes a lot rather than a little.

**If you used these filters to review delivered therapy — total insulin over a period, how many temp
basals ran, carbs logged, how many entries were missing a value — earlier results may have
under-reported or over-reported what was actually recorded.** Nothing in your database was wrong;
the question was being asked wrongly. Nightscout is not a medical device and this is not medical
advice. If a corrected figure changes your understanding of a past period, discuss it with your care
team rather than acting on it alone.

---

## How it works

### Commit 1 `f829ea11` — field types come from the schemas

`lib/server/query.js` chose a value's type from a per-collection `walker` map naming 13 fields
across three collections. MongoDB orders BSON types before comparing values, so a numeric field
never matches a string bound: empty list, HTTP 200.

`specs/nsschema/*.model.json` generates `lib/server/query-coercion.json`, mapping each declared field
to a type. `lib/server/query-coercion.js` converts values and leaves operator *operands* alone. A
collection opts in through its query options:

```js
storage.queryOpts = { collection: 'devicestatus', dateField: 'created_at' };
```

**158 schema-driven coercions across 5 collections replace 13 hand-written entries.** An explicit
`walker` entry still wins, so `treatments` keeps regex search on `notes`, `eventType` and
`enteredBy`. Callers naming no collection are unchanged — they keep the legacy
`{date: parseInt, sgv: parseInt}` guess.

**Operands need a per-operator decision, not a blanket exemption.** `$regex` and `$options` want the
string they already have. `$type` does not: it takes a BSON type code, so `find[sgv][$type]=2` must
arrive as the number `2` — as `"2"` the server rejects it with *"Unknown type name alias: 2"*.
`origin/dev` converted it along with everything else and it worked, so exempting it would have turned
a working request into an HTTP 500. `operandReaderFor` reads a digits-only `$type` operand as a
number and passes aliases like `number` through.

Closes **BF-02**, **BF-11**, **BF-03** (devicestatus and profile), **BF-32**, **BF-68**.

### Commit 2 `b7234753` — operands that are questions, not values

`normalizeOperands` reads the `$exists` operand on the finished query, keyed on the operator rather
than on the field. That matters: the per-field converter only runs for fields the schema types, so
placing it there would fix `sgv` and leave `madeUpField`, `notes` and every field of `activity`
inverted. Keying on the operator also covers `{$not: {$exists: "false"}}` and operands inside `$or`.

`"true"`/`"1"` → `true`, `"false"`/`"0"` → `false`, case-insensitive. Everything else, including a
non-string operand, passes through unchanged.

Closes **BF-40**.

<a name="why-one-pr"></a>
### Why one PR

The `$exists` fix does not stand alone. On `origin/dev` the per-field converter turns the operand
into `NaN` before the new pass can read it, and `NaN` is treated as "yes" too — so with only commit 2
the inversion persists on `entries.sgv`, `.filtered`, `.unfiltered`, `.rssi`, `.noise`, `.mbg` and
`treatments.insulin`, `.carbs`, `.glucose`. Those are the fields people filter on. Commit 1 is what
stops the operand being destroyed; commit 2 is what reads it.

## Verifying it

```
TEST=query npm run test-single             # 29 passing, 15 ms, no database
TEST=query.operands npm run test-single    # 12 passing,  8 ms, no database
```

`tests/query.test.js` is inside the `test:unit` brace list. **`tests/query.operands.test.js` is a new
file and matches neither list, so `npm run test:unit` does not run it** — use `npm test`, which is
what CI runs. `tests/query.test.js` cannot load at all on pristine `origin/dev` (no
`query-coercion` module), so it cannot pass against unfixed code.

Both suites were checked by reverting each part of the fix in turn and confirming the tests fail:
removing the operand pass fails 6, removing the `$type` reader fails 1, and each deliberate decision
— that an empty operand is left alone, that `$regex` is not read as a boolean — fails exactly the
test that pins it.

`test:unit` also needs MongoDB for six unrelated files (`careportal`, `security`, `verifyauth`);
those failures are environmental and the dev baseline fails the same six.

## Semver: minor

It changes which records a filter returns, but adds no required input, removes no route and breaks no
documented contract. No operator action, no configuration break, stored data untouched. A report
built on a broken filter needs re-running, which is a release note rather than a migration.
Classification in `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md` row 12.

**The "What changes for you" text above is the release-note source.** It is not a `CHANGELOG.md`
entry and this branch adds none. Two things must reach the release notes: that earlier results may
have under- or over-reported delivered therapy, and the `$exists=false` inversion with the list of
spellings that are still not read.

## Evidence

- Backfix register `docs/30-design/remedial/nightscout-backfix-register.md` — BF-02, BF-03, BF-11, BF-32,
  BF-40, BF-68, including the measurements behind each claim here.
- T0.5 evidence `docs/60-research/remedial/t05-schema-driven-coercion-2026-09-15.md`.

## Follow-ups deliberately not in this PR

- **`$exists` spellings other than `false`/`0`/`true`/`1` are still not read**, so `=null`,
  `=undefined`, `=no` and an empty value all still mean "has the field". Widening the list is a
  decision about how much to guess, not a bug fix, and is left open.
- **The interaction with `bf/reads`.** This branch gives `query.js` a `collection:` option;
  `bf/reads` fixes `aggregate.js`, which calls it. Measured: the count path is typed correctly after
  both land, because BF-01's fix makes `aggregate` delegate to each collection's own `query_for`, and
  each names its collection. An end-to-end test against a live database is still missing.
- **`lib/authorization/storage.js` names no collection**, so it keeps the legacy guess. Inert today —
  auth documents have neither `date` nor `sgv` — but worth naming a collection so it cannot become
  live later.
- **The limit rule is written twice**, in `lib/server/count.js` and API v3's `parseLimit`. `count.js`
  does not exist on `origin/dev`; `bf/reads` creates it, so landing that branch creates the
  duplication.
- **`lib/authorization/storage.js:84` has an unguarded `console.log` on a request path**, same shape
  as BF-05.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared against
  `!== null`. No caller, so no register id.
