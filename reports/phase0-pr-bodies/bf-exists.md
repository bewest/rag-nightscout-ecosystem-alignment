# `bf/exists` — asking for records *without* a field returned the records *with* it

One commit `b6dd1e7b`, 2 files, +179. Base `origin/dev` `a8888f0d`. Merges clean against `dev` and
against all nine other Phase 0 branches.

## What changes for you

**If you have ever filtered a Nightscout API read with `$exists=false` — "show me records that do
NOT have this field" — you were given exactly the records that DO have it.** No error, HTTP 200,
nothing on screen to say the answer was the opposite of the question. Your stored data is not
touched; what changes is which records the filter finds.

Everything in a web address is text. So `find[insulin][$exists]=false` reached the database as the
*word* "false" rather than the *answer* false — and the database reads any word as "yes". The
question "which records have no insulin recorded?" was answered with the records that do.

**What this means in practice.** Filters like this are how reports, dashboards and spreadsheet
scripts ask questions such as "which treatments were entered without a carb amount?" or "which
readings arrived with no device attached?" **Any answer you have had from a `$exists=false` filter
was the inverse of what you asked**, and a count drawn from one was counting the wrong group.

### What you should do

**Re-run anything built on a `$exists=false` filter.** The set it returns now is the complement of
what it returned before, so a count will usually change substantially rather than slightly.

`$exists=true` is unaffected — it was answering correctly and still does. Nothing else about your
filters changes.

Nightscout is not a medical device and this is not medical advice. If a corrected figure changes
your understanding of a past period, discuss it with your care team rather than acting on it alone.

---

## Technical detail

Measured against live `mongod` **3.6.8 and 7.0.43**, identical on both, over
`[{_id: 1, sgv: 100}, {_id: 2}]`:

| operand | returns | reading |
|---|---|---|
| `false` (boolean), `0`, `null` | `[2]` | lacks the field — correct |
| `"false"`, `"0"`, `""`, `NaN`, `[]` | `[1]` | **has the field** — the defect |

MongoDB's truthiness for a string is "any string, including the empty one", so every spelling a
query string can produce reads as true.

**End to end**, over two treatments, one with `insulin` and one without:

```
find[insulin][$exists]=false    before -> {"$exists":"false"}   returns the doc WITH insulin
                                after  -> {"$exists":false}     returns the doc WITHOUT
find[insulin][$exists]=true     unchanged, both return the doc WITH insulin
```

### Where the fix lives, and why not where BF-40 said

The register prescribed a reader "at the point where `isValueLeaf` already special-cases the
operator". **That point is inside `walk_prop`, which only runs for fields that have a typer** — so
it would have closed this for `sgv` and left it open for every field the schema does not name.
Measured before writing: `madeUpField`, `notes` and every field of `activity` never enter
`walk_prop` at all.

So `normalizeOperands` runs over the **finished query**, keyed on the operator. That reaches every
field regardless of type, and handles `{$not: {$exists: "false"}}` and an operand inside `$or`,
both of which a per-field walker misses.

### What is read, and what is deliberately not

`"true"`/`"1"` → `true`; `"false"`/`"0"` → `false`; case-insensitive. Non-string operands pass
through — they already mean what they mean.

**The empty string is left alone on purpose.** `?find[x][$exists]` with no value parses to `''`,
and `bf/parms` (BF-37) makes that reachable rather than a crash. It is as easily "yes, I want this
flag" as "no, I do not" — and guessing would silently invert somebody's query, which is the defect
being removed, not a licence to commit it in the other direction. Anything else unrecognised passes
through for the same reason. A test pins this so that changing it has to be deliberate.

**`$regex` is untouched and must stay untouched.** It wants a string and already gets one; reading
it as a boolean would break the patterns `0`, `1` and `true`. A test pins that too.

## One dependency, stated plainly

**On `origin/dev` alone, this fixes the untyped majority and not the thirteen fields a `walker`
names.** Those have their operand converted to `NaN` before this pass can read it, and `NaN` is
truthy as well. They stay wrong until **`bf/coercion`** lands and stops the walker touching
operands.

Measured in the merged tree of the two branches: `$exists=false` is correct on typed and untyped
fields alike, and both test files pass (29 + 12). The branches merge cleanly, and `bf/coercion`
carries the one test change needed so they do not collide on an expectation.

**Landing this alone is still worth it** — every field the schema does not declare, and all of
`activity`, is fixed by this branch on its own.

## Verifying it

```
TEST=query.operands npm run test-single     # 12 passing, 6 ms, no database needed
```

`tests/query.operands.test.js` is a new file and matches **neither** local brace list, so
`npm run test:unit` does not run it. `npm test` and CI's `test-ci` over `./tests/*.test.js` do. It
is a new file rather than an addition to `tests/query.test.js` because `bf/coercion` appends its
own block at the same point and the two would collide.

**Non-vacuity**, each break confirmed to land before the suite ran:

| ablation | result |
|---|---|
| remove the `normalizeOperands` call | **6 failing** |
| also map `""` to `false` | **1 failing** — exactly the test pinning that decision |
| add `$regex` to the reader map | **1 failing** — exactly the `$regex` test |

Restoring all three returns 12 passing, so each failure belonged to its own break.

## Semver: minor

It changes which records a filter returns. No new required input, no route removed, no documented
contract broken, no operator action, stored data untouched. A report built on `$exists=false` needs
re-running, which is a release note rather than a migration.

**The "What changes for you" text above is the release-note source.** Not a `CHANGELOG.md` entry —
that is a release output.

## Evidence

- Backfix register `docs/30-design/nightscout-backfix-register.md` — **BF-40** (reproduced; the
  entry's own prescribed fix is corrected there).
