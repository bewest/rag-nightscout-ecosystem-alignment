# T0.5 — schema-driven query type coercion

*2026-09-15. Closes BF-02 and BF-11, closes BF-03 in part, closes BF-12 as
not-a-defect, and opens BF-32.*

Plan task: [execution plan](../30-design/nightscout-multitenancy-execution-plan-2026-09-14.md)
Phase 0, T0.5, with the argument in §3.4.
Register: [backfix register](../30-design/nightscout-backfix-register.md).

- **Emitter and tables** — `tools/nsschema/emit/coercion_emit.py`,
  `specs/generated/coercion/*.json`, this repo.
- **Consumer** — `lib/server/query-coercion.{js,json}` and `lib/server/query.js`
  in cgm-remote-monitor, branch `bf/coercion`, commit `88d1f8a4` on
  `origin/dev` (`a8888f0d`). Decision D12: cgm-remote-monitor carries only
  shipping code, this repo carries the generator and the evidence.

---

## 1. What the change is

`lib/server/query.js` turned an HTTP query string into a MongoDB filter and
decided each value's type from a hand-maintained per-collection `walker`. The
walker named **13 fields across three collections**. Every other field kept the
string it arrived as, and MongoDB orders BSON types before it compares values,
so a numeric field never matches a string bound — the filter returned an empty
list with HTTP 200.

The types now come from `specs/nsschema/*.model.json`, through a sixth emitter
beside `mongoose_emit.py`. A collection opts in by naming itself in its query
options; an explicit `walker` entry still wins, so treatments keeps regex search
on `notes`, `eventType` and `enteredBy`, which are search affordances and not
type claims.

**158 coercions over 5 collections** ship in the generated table, against the 13
hand-written entries they replace.

| collection | hand-written | generated | what the schema adds |
|---|---|---|---|
| `entries` | 7 (all `parseInt`) | 20 | `delta`, `trend`, `trendRate`, `glucose`, `scale`, `slope`, `intercept`, 3 booleans |
| `treatments` | 3 typed + 3 regex | 29 | `duration`, `rate`, `absolute`, `percent`, `amount`, `targetTop/Bottom`, 4 booleans |
| `devicestatus` | 0 | 99 | `uploader.battery`, and the `pump`, `loop`, `openaps`, `override` trees |
| `profile` | 0 | 10 | the `loopSettings` numbers, `utcOffset`, `srvCreated/Modified` |
| `activity` | 0 | 0 | nothing — see §3 |

## 2. The four defects, before and after

Measured against a real `mongod` (port 27030) rather than a stub, because the
thing being demonstrated *is* MongoDB's BSON type ordering. Probe fixture: two
temp basals (`duration` 30 and 45, `rate` 0.5 and 1.25), two boluses (`insulin`
1.5 and 1.0), two carb entries (`carbs` 7.5 and 7.0).

| case | before | after | expected |
|---|---|---|---|
| BF-11 `find[duration][$gte]=30` | **0 rows** | 2 | 2 |
| BF-11 `find[rate][$gte]=0.5` | **0 rows** | 2 | 2 |
| BF-02 `find[insulin][$gte]=1.5` | **2 rows** | 1 | 1 |
| BF-02 `find[carbs][$gte]=7.5` | **2 rows** | 1 | 1 |

### BF-02 · `insulin` and `carbs` bounds truncated — **fixed**

`insulin`, `carbs` and `glucose` were `parseInt` although the model declares all
three `number`. `find[insulin][$gte]=1.5` became `{"insulin":{"$gte":1}}`, so a
request for boluses of at least 1.5 U returned the 1.0 U bolus too. The register
records `treatments.insulin` as **142,360 fractional values against 2,791
integer ones across 11 sites**, so this is not a rounding nicety. Now
`{"insulin":{"$gte":1.5}}`.

### BF-03 · Numeric filters that match nothing — **fixed for two of four
collections; the other two were misfiled.** See §3.

`devicestatus` and `profile` are fixed: 99 and 10 fields respectively.
`find[uploader.battery][$lt]=50` went from `{"$lt":"50"}` to `{"$lt":50}`.

### BF-11 · `treatments.duration` and `rate` — **fixed**

Both are declared `number` and neither had a walker entry, so both filters
returned nothing. `duration` is on **91 % of treatment documents across 10
sites** and **88 % of its values are fractional**; `rate` is on 55 %. Now typed.

### BF-12 · `entries.rawbg` is a stale walker entry — **does not reproduce**

**Stopped and did not fix this.** The register says `lib/server/entries.js`
coerces `rawbg`, a field absent from the model. It does not. The walker on
`origin/dev` reads:

```js
{ date, sgv, filtered, unfiltered, rssi, noise, mbg }
```

The entry is **`rssi`, not `rawbg`**, and `git log --all -S"rawbg" --
lib/server/entries.js` returns **no commits on any branch** — the string has
never been in that file. `origin/chore/nightscout-modernization` has `rssi`
too. And `rssi` *is* in the model, as `integer`, with 32,098 observed values on
one site, so it is a **correct** entry and not a stale one.

The transcription in `coercion_emit.py`'s `SHIPPING_WALKERS` carried the same
error, which is where the register entry came from. Both are corrected. The
drift report now finds **zero ORPHAN rows** across all collections: the
hand-maintained list was missing entries, but it was not carrying dead ones.

## 3. Two things the register got wrong about BF-03

BF-03 names four collections. Two of them cannot be fixed by this change, and
neither for a reason the register anticipated.

**`food` reaches `lib/server/query.js` at no point.** `lib/server/food.js`
exposes `list(fn)`, `listquickpicks(fn)` and `listregular(fn)` — none takes
query options — and `lib/api/food/index.js` passes none. So v1 `/food` accepts
no filters at all, and there is no under-coercion on food to fix. The collection
is excluded from the shipped bundle for that reason. (Separately, 8 of food's
numeric fields are `['number','string']` unions in the model because the
built-in client writes form-encoded, so the emitter refuses to coerce them on
purpose. That is BF-16's territory, not this change's.)

**`activity` has no numeric field to fix.** Its model has exactly two leaves,
`_id` and `created_at`, both strings. The collection is open-bodied — the server
sets `created_at` and `_id`, runs the write purifier and stores the document
wholesale — so a deployment may well hold numbers there, but nothing declares
them and the table will not guess. `activity` is wired to the table and its
entry is legitimately empty, so it starts working the day the model gains a
field.

**A third, smaller correction.** §3.4's table and BF-03 both say `devicestatus`
and `activity` have "none at all". They actually inherit `query.js`'s *default*
walker, `{ date: parseInt, sgv: parseInt }`, because neither sets `walker` and
`default_options` fills one in. It does not change the conclusion — the fields
people filter on were still untyped — but "no coercion at all" is not what the
code did.

## 4. BF-32 — a new defect found while fixing these

The walker was applied to **every leaf** of a field's query fragment, including
operands that are not values drawn from the field's domain. On `origin/dev`:

```
find[sgv][$exists]=true   ->  { sgv: { $exists: NaN } }
find[sgv][$regex]=^1      ->  { sgv: { $regex: NaN } }
```

`NaN` is falsy, so **`$exists=true` returned exactly the documents that do not
have the field** — the opposite of what was asked, with HTTP 200. It was
reachable on the 10 fields that had a walker entry, and generalising coercion to
158 fields would have generalised this with it. `query-coercion.js` now leaves
`$exists`, `$type`, `$regex`, `$options`, `$where`, `$expr`, `$text`,
`$comment` and `$jsonSchema` operands alone, while still converting every
element of an `$in` list. Filed as **BF-32**.

## 5. Non-vacuity

Per the programme rule: each check was made to fail on purpose.

| break | check that caught it | result |
|---|---|---|
| Delete `treatments.duration` from the shipped table | `find[duration][$gte]=30` against mongod | filter reverts to `{"$gte":"30"}`, **0 rows**; restored, 2 rows |
| Same | `tests/query.test.js` | 1 failing — `expected '30' to be 30` |
| Same | `test_vendored_copy_matches_the_emitted_bundle` | failed |
| Re-declare `treatments.insulin` as `integer` in the **model** | `test_checked_in_bundle_matches_a_fresh_emit`, `test_vendored_copy_matches_the_emitted_bundle`, `test_known_over_coercions_are_detected` | 3 failed |

The corpus arm matters as much as the code arm: the probe fixture was built so
that every case *distinguishes* the two behaviours. The first version held
`carbs: 7.5` alone, and `find[carbs][$gte]=7.5` returned 1 row before and after
— `parseInt(7.5)` is 7, and 7.5 ≥ 7 — so the case proved nothing until
`carbs: 7.0` was added to separate them. `duration`/`rate` are the strongest
arm: 0 rows before, 2 after.

The chain model → table → vendored copy → query behaviour is now covered at
every link, and breaking any link fails a test.

**Where a distinction is deliberately collapsed:** the table records `integer`
and `number` separately, and `query-coercion.js` sends both through the same
parse. That is intentional — the value being converted is a *bound*, and `>=
1.5` on an integer field means "2 and above", which truncating to 1 gets wrong
in the other direction — but it does mean no query-layer test can distinguish
the two kinds. The distinction earns its keep in `postgres_emit.py`, not here.

## 6. Tests

*This repo* — `tools/nsschema/test_coercion.py`, **48 passing**. Covers T0.5's
"a test asserts the emitted table matches the model for every collection": it is
parameterised over every model on disk, and every leaf must be either coerced
with its declared type or explicitly listed as uncoerced.

One existing expectation was **changed deliberately**, flagged in-file:
`test_missing_models_are_reported_not_skipped` asserted that `food` and
`activity` have no model. T2.2 (`69e6bc54`) gave both one, so the assertion had
become false, and it was also masking the food finding in §3. It is now
`test_food_is_reported_as_having_no_query_path`.

The emitter previously iterated `specload.ROOT_SCHEMA`, four collections, so it
had been **silently skipping `activity` and `food` since T2.2 added their
models**. It now discovers every model on disk.

*cgm-remote-monitor* — `tests/query.test.js`, 13 new cases. `npm run test:unit`
**374 passing** (361 on the base commit, +13), `npm run test:integration`
**754 passing, 3 pending, 0 failing**.

## 7. Release note

In `CHANGELOG.md` under `[Unreleased] / Fixed`, not in the commit message. Full
text is in the file; in summary:

> **API v1 query filters now use each field's real type.** Filters that used to
> quietly return nothing now work — `treatments.duration` and `rate`, nearly
> every number and true/false field on `devicestatus` including
> `uploader.battery` and the `pump`/`loop`/`openaps` readings, `entries` fields
> such as `delta`, `trend`, `rssi` and `isValid`, and the `profile`
> `loopSettings` numbers. `/api/v1/treatments.json?find[duration][$gte]=30`
> returned `[]` on a database full of temp basals and now returns them.
> Decimal bounds are no longer rounded down: `find[insulin][$gte]=1.5` returned
> 1.0-unit boluses alongside the larger ones and now does not. `$exists` and
> `$regex` operands are no longer mangled. Stored data is untouched; only which
> records a filter selects. Anyone who has used these filters to review
> delivered therapy should re-run what they relied on, and take questions about
> their therapy data to their care team.

## 8. Honest limits

1. **`devicestatus`'s 99 entries are the widest blast radius and the least
   exercised.** The suite tests `uploader.battery`; the `pump`, `loop`,
   `openaps` and `override` subtrees are typed from the model and covered only
   by the model-vs-table test. No fixture filters on them.

2. **No API-level integration test was added.** The end-to-end evidence in §2 is
   a probe script against mongod, not a committed test; the committed tests stop
   at the filter `query.js` builds. A filter that is correct is not proof that
   every route passes it through unchanged.

3. **The model is only as good as its provenance.** `activity` and `food` are
   `provenance: code-derived, measured: false` — read out of the server source,
   never censused. `devicestatus`, `entries`, `profile` and `treatments` are
   census-backed. Where the corpus saw a field as two scalar types the emitter
   refuses to coerce it, which is protective, but a field the corpus never saw
   in a deployment's shape can still be typed against that deployment.

4. **Garbage now becomes `NaN` on 148 more fields.** `find[duration][$gte]=abc`
   used to yield the string `"abc"` and now yields `NaN`; both match nothing, so
   the observable result is the same, but it is a wider surface for it. Whether
   a malformed bound should be a 400 is a policy question this change
   deliberately left where it found it.

5. **BF-01 is adjacent and untouched.** The register says to ship it with
   BF-02/BF-03. It is a different mechanism — the injected two-day window using
   the wrong type for `entries.date` — and the `datelike` flag the emitter
   carries for it is emitted but not yet consumed. `lib/server/aggregate.js`
   still calls `query.js` with no options at all, so it gets the legacy
   `{date, sgv}` default and no schema types; that is BF-01's fix, not this one.

6. **Two copies of the table exist.** cgm-remote-monitor must carry it to load
   it at runtime while this repo owns the emitter. `make schema-coercion-vendor`
   refreshes it and `test_vendored_copy_matches_the_emitted_bundle` fails if they
   diverge — but that test lives *here*, so a cgm-remote-monitor CI run on its
   own cannot detect a stale vendored table.

7. **The four verifyauth failures on the first full `test:unit` run were a
   cold-start flake, not this change.** They did not reproduce: the base commit
   and the changed tree both give 361 passing before the new tests are added,
   and `verifyauth` passes in isolation either way.
