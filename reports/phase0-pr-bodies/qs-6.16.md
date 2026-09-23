# `bf/qs-6.16`: web addresses and form posts are read by qs 6.16.0

**DRAFT. Not pushed, not opened.** Branch `bf/qs-6.16` on `origin/dev` `74fc6619`, tip
`46b20b38`, one commit. No `CHANGELOG.md` edit. The version stays 15.0.9. Register BF-87, queue
BFQ-87.

| what changes | who can see it |
|---|---|
| the library that reads web-address options and form posts moves from qs 6.15.1 to qs 6.16.0 | nobody, for any request shape a known app sends (638 shapes measured, no difference) |
| a small set of **malformed** web addresses, with brackets that do not pair up, are read differently | only someone typing such an address by hand; no surveyed app sends one |
| three published qs advisories no longer apply to this install | people who run `npm audit` on their site |

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice.*

A few words used below:

- **Query string**: the part of a web address after the `?`. Apps use it to ask Nightscout for
  particular records, for example `?count=10&find[sgv][$gte]=180` ("the last 10 readings at or
  above 180").
- **Form post**: the other way an app or a web page can send options to Nightscout, in the body of
  a request rather than in the address.
- **qs**: the small open-source library Nightscout (through Express, its web framework) uses to
  turn both of those into something the server can read.
- **Advisory**: a public notice that a version of a library has a flaw.

Nightscout pinned qs to version 6.15.1 in May 2026. Three advisories have since been published
against that version. This change moves the pin to 6.16.0, which fixes all three.

We checked, request by request, that the new version reads what apps send **exactly the same way**
as the old one: every example in Nightscout's own documentation and tests, every filter found in
14 client apps (among them Trio, LoopFollow, xDrip, xDrip4iOS, oref0, nightguard and
Nightscout Reporter), every careportal event type, and very long and very deeply nested requests.
None of those read differently.

The only requests that read differently are **broken ones**, such as an address with a `[` that
never closes. Some of those used to be quietly read as something else, and now either match
nothing or are refused with an error. No surveyed app sends them.

**What you should do:** nothing. Apps that work today keep working.

---

## Technical detail

### What the commit does

`package.json`: `overrides.qs` and `overrides.request.qs` go from `6.15.1` to `6.16.0`. These are
the only two qs pins in the file (none under `express` or `body-parser`).

`package-lock.json` (regenerated with `npm install`, npm 11.12.1, Node 20.20.0):

| package | before | after | why |
|---|---|---|---|
| `qs` | 6.15.1 (no `resolved`/`integrity`) | 6.16.0 (with both) | the override |
| `side-channel` | 1.1.0 | 1.1.1 | qs 6.16.0 declares `side-channel ^1.1.1` |
| `qs` → `es-define-property` | no edge | `^1.0.1` | new qs dependency; `es-define-property@1.0.1` was already in the tree, so no new package |

Nothing else in the lock moves. `side-channel` 1.1.1 (2026-06-08) changes one thing at runtime:
its `assert` no longer reads object keys while building an error message.

After the change `npm ls qs` shows one `qs@6.16.0` used by body-parser, express, request (under
minimed-connect-to-nightscout), nightscout-connect and superagent (tests only). `npm ci` from an
empty `node_modules` succeeds and leaves the lock unchanged.

`npm audit --omit=dev`: `origin/dev` 17 findings (1 low, 13 moderate, 3 high); this branch 13 (1
low, 9 moderate, 3 high). The four that go are `qs` itself and `express`, `body-parser` and
`nightscout-connect`, which were listed only because they depend on qs. `request` stays listed for
its other advisories. No new finding appears.

### What changed in qs between 6.15.1 and 6.16.0

The parse defaults are identical in both versions: `allowDots false`, `allowPrototypes false`,
`arrayLimit 20`, `comma false`, `depth 5`, `duplicates 'combine'`, `parameterLimit 1000`,
`strictDepth false`, `strictMerge true`, `throwOnLimitExceeded false`, and the rest.

Behaviour changes, from the qs changelog and the `lib/` diff:

| version | change | reaches Nightscout's parse? |
|---|---|---|
| 6.15.2 | `parse`: nested bracket groups (`a[b[c]]`) are kept as one key segment; an unclosed `[` becomes a literal segment instead of being dropped | **yes**, only for malformed keys (below) |
| 6.15.2 | four `stringify` crash fixes (comma format, filter arrays, `strictNullHandling`, `charsetSentinel` delimiter) | no; Nightscout never stringifies with those options |
| 6.15.3 | `parse`/`merge`: `throwOnLimitExceeded` enforced for growth by `combine`/`merge` | no; Nightscout never sets `throwOnLimitExceeded` |
| 6.15.3 | `merge`: an array grown past `arrayLimit` by a plain value becomes an object one element sooner (`>` became `>=`); array/array merges check `arrayLimit` | not reachable (below) |
| 6.15.3 | `merge`/`assign`: a `__proto__` key is written as an own property instead of through the setter | no difference measured |
| 6.15.3 | `encode`: surrogate pairs split across 1024-character chunks | stringify only; no difference measured |
| 6.15.3 | `compact` is O(n) | performance only |
| 6.16.0 | `parse`: `arrayLimit` enforced on comma groups under `[]=` when `throwOnLimitExceeded` is set | no; needs `comma: true` |
| 6.16.0 | `combine`: a collection appended to an already overflowed array is flattened (#571) | no difference measured |
| 6.16.0 | `utils.isBuffer` checks that `constructor.isBuffer` is a function | stringify only |
| 6.16.0 | `stringify`: new `depth` option (default `Infinity`), Dates serialized with a filter, `allowEmptyArrays` cycle fix, `encodeDotInKeys` on top-level keys | no; default unchanged |

Why the `merge` change cannot reach Nightscout: an array only grows past `arrayLimit` if a request
has more parameters than `arrayLimit`. For the query string Express sets `arrayLimit: 1000` and qs
keeps its `parameterLimit: 1000`, so the 1001st parameter is dropped before it can grow the array.
For form posts body-parser sets `arrayLimit` to `max(100, number of parameters)`, which is never
smaller than the array. With qs's plain defaults (`arrayLimit: 20`) the change does show (a
21-element mixed array becomes an object on 6.16.0), which is what nightscout-connect's own
`qs.parse(endpoint.query)` would see; a connector configuration address does not carry 21 repeated
keys.

### The parser options that were measured

Read from the installed modules, not from documentation:

- **Query string** (every route): Express 4.22.2's default `'query parser'` is `'extended'`, which
  calls `qs.parse(str, { allowPrototypes: true, arrayLimit: 1000 })`. Nightscout does not change
  the setting.
- **Form posts through `wares.urlencodedParser`** (`lib/middleware/index.js`; entries, treatments,
  devicestatus, profile, food, activity, alexa, notifications v2): body-parser 1.20.6 `urlencoded({
  extended: true, limit: '1Mb', parameterLimit: 50000 })`, which calls `qs.parse(body, {
  allowPrototypes: true, arrayLimit: max(100, paramCount), depth: 32, strictDepth: true,
  parameterLimit: 50000 })`.
- **Form posts through plain `urlencoded({ extended: true })`** (`lib/api/notifications-api.js`,
  `lib/authorization/endpoints.js`): the same with `parameterLimit: 1000`.

### Parsing differential

Each tree's own Express query parser (`compileQueryParser('extended')`) and both body-parser
middlewares (fed a real request stream) parsed every corpus entry, each tree resolving qs only
from its own `node_modules` (`origin/dev` → 6.15.1, this branch → 6.16.0). Results were compared
as a typed serialization that tells arrays from objects, keeps own-key order, and records holes,
null prototypes and error messages.

Corpus, 638 distinct inputs:

| source | inputs |
|---|---:|
| `README.md` API examples | 5 |
| `lib/server/swagger.yaml` and `lib/api3/swagger.yaml` examples, plus api3 `limit`/`skip`/`sort`/`fields` shapes | 29 |
| query strings in `tests/*.test.js` | 156 |
| the v1 client census (`reports/v1-query-census/sites.tsv`, 157 sites in 14 projects), each field/operator with realistic values, raw and percent-encoded, plus 7 combined requests as clients send them | 165 |
| v1 `find[...]` shapes: operators, `$in[]`, indexed `$in[0]`, nested `find[a][b][c]`, `$and`/`$or` groups, `count` spellings, duplicates, `$regex`/`$options` | 34 |
| every careportal event type, with `+` and `%20`, in `=`, `$ne` and `$in[]` filters | 85 |
| bracket grammar edges: nested, unclosed and stray brackets, encoded brackets, prototype-named keys, dots, commas, bad and multi-byte percent-encoding | 76 |
| depth: 1 to 64 levels, including 5/6 (query default) and 32/33 (form strict limit) | 17 |
| arrays at 19–22, 99–102 and 999–1002 elements (`[]`, indexed, repeated key) and mixed-shape arrays at 20, 100, 1000, 1001 | 64 |
| parameter counts at 999–1002 and 49,999–50,001 | 7 |

Result, 1,914 comparisons (638 inputs × 3 parsers): **45 differences, all from 15 inputs in the
bracket-grammar group**, each differing identically in all three parsers. **Zero differences** in
the README, swagger, tests, census, event-type, depth, array and parameter-count groups. Errors
(form parsers refusing too many parameters or too much depth) are the same on both sides: 5 for
the Nightscout form parser, 28 for the plain one, 0 for the query string.

The 15 inputs that differ are all keys whose brackets do not pair up:

```
find[a[b]]=1    a[b[c]]=1    a[b[c]][d]=1    find[$or][0[x]]=1    a[[b]]=1    a[[]]=1
a[b=1    find[sgv=1    find[sgv][$gte=1    a[=1    [[a]]=1    a[b][c=1    a[b][[c]=1
a[%5B%5D]=1    a[b%5Bc%5D]=1
```

Run through `lib/server/query.js` (which applies the v1 operator allowlist), they fall into three
kinds:

- **Quietly different before, a non-matching field name now.** `find[sgv][$gte=1` used to become
  `{sgv: 1}`, an *equality* match on 1; it now becomes `{sgv: {'[$gte': 1}}`, which matches
  nothing. `find[a[b]]=1` and `find[sgv=1` used to be dropped from the filter entirely (so the
  request returned the unfiltered default) and now become field names `a[b]` and `[sgv` that match
  nothing.
- **Refused now.** Keys where a `$` operator carries brackets, such as `find[sgv][$gte[x]]=1` or
  `find[$or[0]][sgv]=1`, now keep the brackets in the operator name, and the allowlist answers
  400 "Query operator ... is not supported". On 6.15.1 they were quietly rewritten (for example to
  `{sgv: {x: 1}}`).
- **Unchanged filter.** Keys outside `find` (`a[b[c]]=1`) change shape but nothing reads them.

No input produced a new operator that reaches MongoDB.

**The differential can see a change** (non-vacuity), shown two ways:

- *Known-different input.* The qs 6.15.2 changelog entry "handle nested bracket groups (#530)"
  predicts that `a[b[c]]=1` parses differently; under Express's options 6.15.1 gives
  `{"a[b": {c: "1"}}` and 6.16.0 gives `{a: {"b[c]": "1"}}`. The harness reports it.
- *Perturbed options.* With options Nightscout does not use (`comma: true, arrayLimit: 3,
  throwOnLimitExceeded: true`), the 6.16.0 changelog item on comma groups under `[]=` shows up:
  6.15.1 returns a four-element array and 6.16.0 throws `RangeError`.

A stringify check was also run (each parsed result, under default, `encodeValuesOnly`, `brackets`
and `indices` formats): 0 differences in 2,552 comparisons.

### The three advisories

Read from each advisory's text. None was exploited against Nightscout. Nightscout's own code has no
`qs.stringify` call; the stringify consumers are `request` (under minimed-connect-to-nightscout)
and nightscout-connect, which stringify objects they build themselves.

| advisory | which qs path | does Nightscout's configuration reach it? | evidence |
|---|---|---|---|
| GHSA-q8mj-m7cp-5q26 (≤ 6.15.1, fixed 6.15.2) | `stringify` with `arrayFormat: 'comma'` **and** `encodeValuesOnly: true` on an array holding `null`/`undefined` | no: needs two non-default stringify options together, and no Nightscout path passes them | read, not run |
| GHSA-x5fp-wj9c-mxmx (6.14.2–6.15.3, fixed 6.16.0) | `parse` with `comma: true`, where `a[]=` values escape `arrayLimit` | no: neither Express nor body-parser sets `comma`, so values are never split on commas | read; the differential parsed `a[]=1,2,3,4` and `find[type][$in]=sgv,mbg` under Nightscout's options and neither version split them |
| GHSA-4mjr-xmp4-gh2g (< 6.16.0, fixed 6.16.0) | `stringify` of an object whose own `constructor.isBuffer` is not a function; `parse` with `allowPrototypes: true` or `plainObjects: true` can produce one | half: Express and body-parser both set `allowPrototypes: true`, so the parse side is reached; the stringify side is reached only if code re-serializes a parsed request with qs, and none in Nightscout does | read, not run; the differential parsed prototype-named keys (`find[constructor][x]=1` and others) identically under both versions and did not stringify them |

### Tests

Full suite (`env-cmd -f ./my.test.env mocha --timeout 5000 --require ./tests/hooks.js --exit
./tests/*.test.js`), both trees against the same `mongo:7` container, database dropped between
runs, run back to back:

| Node | tree | passing | failing | pending |
|---|---|---:|---:|---:|
| 20.20.0 | `origin/dev` `74fc6619` | 2386 | 0 | 3 |
| 20.20.0 | `bf/qs-6.16` `46b20b38` | 2386 | 0 | 3 |
| 24.20.0 | `origin/dev` `74fc6619` | 2386 | 0 | 3 |
| 24.20.0 | `bf/qs-6.16` `46b20b38` | 2386 | 0 | 3 |

No test is added. The change is to a pinned dependency, and the differential above is the check;
it lives outside the tree.

### Suitable for 15.0.9?

Yes, on this evidence. It is a dependency pin with a two-package lock movement, no request shape
any known client sends parses differently, the only changes are to malformed bracket keys (which
now match nothing or get a 400 instead of being quietly rewritten), and it clears three moderate
advisories that `npm audit` reports on every install of 15.0.8. 15.0.8 (`master`) carries the same
two pins and the same audit findings.

### Not in this branch

- Dependencies still at an advisory range for other reasons (`request`, `form-data` under
  `request`, `uuid`, `ajv`, `sanitize-html`, `browserslist` and others in `npm audit`) are
  unchanged.
- The pin stays an exact override. qs 6.16.0 does not satisfy the `~6.15.1` that express 4.22.2
  and body-parser 1.20.6 declare (`npm ls` marks it `overridden`), so without the override those
  two would resolve a 6.15.x, which is still inside the range of two of the three advisories.
