# D — `bf/coercion`: filters that quietly returned nothing now return your records

> **Base: `origin/dev` `a8888f0d`. This is one of NINE INDEPENDENT PRs. There is no stack.**
> `bf/reads` (E) was previously rebased onto this branch to resolve a `CHANGELOG.md` collision.
> **That stack is dissolved.** The changelog edits were stripped by the maintainer's instruction,
> `bf/reads` was un-stacked and rebased directly onto `origin/dev`, and the two now merge cleanly
> against `origin/dev` and against each other. **Merge order between D and E no longer matters.**
> One real interaction survives and is *not* a merge hazard — see "Follow-ups".
>
> **This branch is `ab197bf8`** (one commit, 9 files, code only). The SHA `88d1f8a4` that older
> documents quote is the pre-strip tip; its backup is `bf/coercion.bak-changelog`. `git range-diff`
> shows the two differ by exactly the 40 removed changelog lines and no code.

## What changes for you

**If you have ever filtered a Nightscout API read and got back an empty list for no obvious
reason, this is why, and it now works. Your stored data is not touched, altered or moved. What
changes is which of your records a filter finds.**

When you ask Nightscout for records matching a condition — a report, a dashboard, a spreadsheet
script, a URL with `find[...]` in it — Nightscout has to decide whether the value you typed is a
number, a yes/no flag, or ordinary text. It was deciding this from a short hand-written list that
covered only 13 fields, and got some of those wrong. **A field that was not on the list kept your
value as text, and text never matches a number.** The database compared them, found no match,
and answered with an empty list and a success code. **No error was shown.** You could not tell
the difference between "you have no records like that" and "the question was asked wrongly."

Three things change:

**1. Filters that returned nothing now return your records.**

For example, `/api/v1/treatments.json?find[duration][$gte]=30` — "show me temp basals lasting 30
minutes or more" — returned `[]` on a database full of them. It now returns them. The same was
true of:

- **Temp basal fields** on treatments: `duration` and `rate`. These are on the large majority of
  treatment records for anyone running an automated system.
- **Nearly every number and yes/no field on `devicestatus`** — pump and phone battery
  (`uploader.battery`), reservoir, and the `pump`, `loop` and `openaps` readings.
- **`entries` fields** such as `delta`, `trend`, `rssi` and `isValid`.
- **The `profile` `loopSettings` numbers.**

**2. Decimal amounts stop being rounded down.**

`insulin`, `carbs` and `glucose` bounds were rounded to whole numbers. Asking for
`find[insulin][$gte]=1.5` — "boluses of 1.5 units or more" — was answered as though you had asked
for 1, so **1.0-unit boluses were included in the answer**. It now returns only boluses of 1.5
units or more. The same rounding applied to `entries` bounds such as `sgv`, `mbg` and `date`.

**3. A text-search filter that returned a server error now works.**

Searching a numeric field for a pattern — `find[sgv][$regex]=^1` — produced an **HTTP 500 server
error**, because the search pattern itself was being converted to a number before being handed to
the database. Search patterns are now left alone, so the request is answered normally.

### An earlier version of this PR body said something here that was wrong. Please read this.

**An earlier draft told operators that `find[sgv][$exists]=true` — "records that have an sgv" —
had been returning "precisely the records you did not ask for". That was false, and it was
operator-facing text telling people to distrust answers that were correct.**

What actually happened: the filter's `true` was being converted to a not-a-number value before it
reached the database. **Measured 2026-09-15 against seven live MongoDB servers (versions 3.6.8 and
7.0.43, identical results on all seven), MongoDB reads that value as *true*** — its rule for
numbers is "anything that is not zero", and not-a-number is not zero. So
**`find[...][$exists]=true` was already answering correctly, by accident, and nothing you did with
it needs re-running.** The wrong claim came from a JavaScript stand-in used to cross-check query
behaviour, which applies JavaScript's rules rather than the database's.

**One `$exists` problem is real, is not fixed by this PR, and you should know about it:**
**`find[<field>][$exists]=false` — "records that do NOT have this field" — returns the records that
DO have it, on every field, both before and after this change.** It answers with a success code, so
nothing warns you. It is filed as an open defect (**BF-40**) with a fix designed and unwritten.
**If you have a report or script that uses `$exists=false`, its results are the opposite of what
you asked for, and this PR does not change that.**

### What you should do

**If you have a report, dashboard, spreadsheet or script built on one of the filters in points
1–3, re-run it after upgrading and expect the numbers to move.** A filter that returned nothing may
now return many rows. A decimal bound now excludes values it previously included. A pattern search
that returned a server error now returns an answer.

**If you have used these filters to review delivered therapy — total insulin over a period, how
many temp basals ran, carbs logged — the earlier results may have under-reported or over-reported
what was actually recorded, and it is worth re-running anything you relied on.** Nothing in your
database was wrong; the question was being asked wrongly. Nightscout is not a medical device and
this note is not medical advice. If a corrected figure changes your understanding of a past
period, discuss it with your care team rather than acting on it alone.

### One narrower change, for completeness

Filters are now typed **per collection, from that collection's own schema**. Previously a single
guess (`date` and `sgv` are whole numbers) was applied to *every* collection. So
`find[sgv][$gte]=120` sent to `/api/v1/treatments` used to be converted to a number even though
`sgv` is not a treatments field; it is now left as text there. Measured 2026-09-15 — this only
affects a filter naming a field that does not belong to the collection being queried, which had no
defined meaning before.

---

## Technical detail

Single commit `ab197bf8`. `lib/server/query.js` chose a value's type from a hand-maintained
per-collection `walker` map naming 13 fields across three collections. MongoDB orders BSON types
before comparing values, so a numeric field never matches a string bound: the filter returns an
empty list and HTTP 200.

The replacement is schema-driven. `specs/nsschema/*.model.json` generates
`lib/server/query-coercion.json`, mapping each declared field to a type;
`lib/server/query-coercion.js` converts values and **leaves `$exists`, `$type`, `$regex`,
`$options`, `$where`, `$expr`, `$text`, `$comment` and `$jsonSchema` operands alone**, while still
converting every element of an `$in` list. A collection opts in with a new `collection:` option in
its query options:

```js
storage.queryOpts = { collection: 'devicestatus', dateField: 'created_at' };
```

An explicit `walker` entry still wins over the schema, so `treatments` keeps regular-expression
search on `notes`, `eventType` and `enteredBy`. **Callers that name no collection are unchanged** —
they keep the legacy `{date: parseInt, sgv: parseInt}` guess.

**158 schema-driven coercions across 5 collections replace 13 hand-written entries.**

Closes **BF-02**, **BF-11**, and **BF-03** (devicestatus and profile). **BF-32** was found while
writing it: the walker coerced operator *operands* too, so `find[sgv][$exists]=true` became
`{$exists: NaN}` and `find[notes][$regex]=ab` became `{$regex: NaN}`.

### BF-32 has been re-graded medium → low, and its stated mechanism is refuted

**Do not quote the old form of BF-32.** It said `{$exists: NaN}` is falsy and therefore returned
the documents lacking the field. **Measured against seven live `mongod` instances (3.6.8 and
7.0.43, identical on all seven), it returns the documents that HAVE the field** — MongoDB's numeric
truthiness is `value != 0`, and `NaN != 0`. `{$exists: "false"}` and even `{$exists: ""}` are
truthy for the same reason.

| operand | documents returned over `[{_id:1, sgv:100}, {_id:2}]` | reading |
|---|---|---|
| `true` (boolean) | `[1]` | has the field |
| `false` (boolean) | `[2]` | lacks it |
| `0` | `[2]` | lacks it |
| `NaN` | **`[1]`** | **has it** |
| `"true"` | `[1]` | has it |
| `"false"` | **`[1]`** | **has it** |
| `""` | `[1]` | has it |

So three consequences, and only the first is this branch's:

- **`$regex` was the real breakage.** `{notes: {$regex: NaN}}` returns the server error *"$regex
  has to be a string"* — an HTTP 500 — where `{$regex: 'ab'}` matches. On a coerced numeric field,
  `find[sgv][$regex]=ab` is a 500 today and an empty 200 after this fix. **That is the operator-
  visible improvement BF-32 actually buys**, and it has a much smaller blast radius than the one
  originally claimed.
- **`$exists=true` was answering correctly before this fix and answers correctly after it**, by two
  different accidents. Nothing needs re-running.
- **`$exists=false` is wrong before *and* after**, on every field, because the string `"false"` is
  truthy too. Filed as **BF-40**, open, fix designed and unwritten. This PR does not close it and
  does not claim to.

**Why the fix is still right.** Coercing an operand that is not a field value is wrong regardless
of which way MongoDB happens to read the result, and generalising coercion from 13 fields to 158
would have generalised that defect with it. That argument is untouched by the refutation.

**Why the wrong claim got in, and why it is worth recording.** It came from `mingo`, the
differential oracle that decision D8 names. `mingo` is a JavaScript reimplementation and applies
JavaScript truthiness, so it reports `[2]` for `NaN` where MongoDB reports `[1]`. **The oracle
disagrees with the server on operand coercion** — a limit on D8 that nothing had recorded. It does
not invalidate the oracle for its intended job, comparing *operator* semantics on well-typed
operands, but **a claim about a malformed operand must be taken from a server.**

## Evidence

- Backfix register `docs/30-design/nightscout-backfix-register.md` — **BF-02**, **BF-03**,
  **BF-11**, **BF-32** (re-graded low, mechanism refuted) and **BF-40** (open, and the entry that
  refuted BF-32).
- T0.5 evidence `docs/60-research/t05-schema-driven-coercion-2026-09-15.md`.
- Semver classification `docs/60-research/gt4-semver-classification-2026-09-15.md` — **minor**. GT4
  measured the before/after filters directly:
  `find[duration][$gte]=30` goes from `{"$gte":"30"}` to `{"$gte":30}`;
  `find[insulin][$gte]=1.5` from `{"$gte":1}` to `{"$gte":1.5}`;
  `find[sgv][$exists]=true` from `{"$exists":null}` (NaN) to `{"$exists":"true"}` — **both of which
  a real MongoDB reads as "has the field", so that last row is a tidiness improvement, not an
  answer change.**

## Test evidence

- `TEST=query npm run test-single` in `externals/work/crm-bf-coercion`: **28 passing, 0 failing,
  16 ms** — measured 2026-09-15 on `ab197bf8`, and it needs **no database**.
- Non-vacuity: `tests/query.test.js` from this branch **cannot even load** on pristine `origin/dev`
  (`Cannot find module '../lib/server/query-coercion'`), so it distinguishes fixed from unfixed by
  construction.
- **`tests/query.test.js` IS inside the `test:unit` brace list**, so unlike `bf/food`, `bf/merge`
  and `bf/parms` this branch's own test does run under `npm run test:unit`. Note that `test:unit`
  still needs MongoDB for six unrelated files (`careportal`, `security`, `verifyauth`); an earlier
  run recorded 368 passing / 6 failing on this branch, and **those six failures are environmental**
  — the dev baseline fails the same six with Mongo down, the files are byte-identical to other
  branches' copies, and the branch diff touches neither them nor the code they exercise.
- **`tests/query.test.js:138` covers `$exists=true` only.** BF-40's regression test does not exist
  and has to be written alongside its fix.
- Merges clean against `origin/dev` `a8888f0d` — `git merge-tree --write-tree` re-run 2026-09-15 —
  and clean against all eight other Phase 0 branches, including `bf/reads` at `2ecfeb53`.

## Semver

**Minor.** It changes which records a filter returns, but adds no new required input, removes no
route and breaks no documented contract. No operator action is required, no configuration breaks,
and stored data is untouched — a report built on a broken filter needs re-running, which is a
release-note matter, not a migration. Classification from
`docs/60-research/gt4-semver-classification-2026-09-15.md` row 12.

**The operator-visible text above belongs in the release notes.** It is *not* a `CHANGELOG.md`
entry, and this branch no longer carries one: under the maintainer's rule, `CHANGELOG.md` is a
**release output** generated by GitHub tooling between releases, and branches never hand-edit it.
The 40 changelog lines this branch used to carry were stripped for that reason, with no code
change. **The safety-relevant sentence in "What you should do" — that earlier results may have
under- or over-reported delivered therapy — must survive into the release notes verbatim**, and so
must the `$exists=false` warning, which is about a defect that is still open.

---

## Follow-ups deliberately **not** in this PR

- **BF-40 — `$exists=false` is inverted, before and after this branch, on every field.** The fix is
  to route the `$exists` operand through a boolean reader that understands `"false"`, `"0"` and
  `""`, at the point where `isValueLeaf` already special-cases the operator
  (`lib/server/query-coercion.js:90` on this branch; `walk_prop` on `dev`). **Nobody has run it.**
  Deliberately not in this PR, which is already the largest behavioural change in Phase 0.
- **The §3b interaction with `bf/reads` (E) — real, and not a merge hazard.** This branch gives
  `query.js` a new `collection:` option; `bf/reads` fixes `aggregate.js`, which calls `query.js`.
  **Measured 2026-09-15: the count path is typed correctly after both land**, because BF-01's fix
  made `aggregate` delegate to each collection's own `query_for`, and every one of those names its
  collection. Verified by executing the real modules with `origin/dev` and pre-rebase `bf/reads` as
  controls — both controls produce `{"$lte":"20"}` (text, matches nothing) and the merged tree
  produces `{"$lte":20}`. Detail in `bf-reads.md`. **What is still missing is the end-to-end test
  against a live database**, which is work, not a code change.
- **`lib/authorization/storage.js` is the last caller that names no collection**, so it keeps the
  legacy `{date: parseInt, sgv: parseInt}` guess. Measured 2026-09-15: inert today, because auth
  subject and role documents have neither a `date` nor an `sgv` field, and its `noDateFilter: true`
  is honoured identically before and after. Worth naming a collection anyway so the guess cannot
  become live later. No register id.
- **The limit rule is written twice** — `lib/server/count.js` and API v3's `parseLimit` — on
  purpose, so each commit lands alone. *Two readings of one rule is the root cause of this whole
  family of defects*, so leaving it duplicated is a debt with a name. Note that
  `lib/server/count.js` **does not exist on `origin/dev`** — `bf/reads` creates it — so the
  duplication does not exist yet and is created by landing E.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared
  against `!== null`. No caller, so no register id.
- **`lib/authorization/storage.js` has a second unguarded `console.log` on a request path**, same
  shape as BF-05, different file (`:84` on `origin/dev`; the line moves per branch).
