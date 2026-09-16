# `bf/reads` — six read-path fixes, including a request for zero records answered with everything

Six commits on `origin/dev` `a8888f0d`, tip `2ecfeb53`. 17 files, +746/−36, of which five are new
test files. No `CHANGELOG.md` edit. Merges clean against `dev` and against every other open Phase 0
branch, including `bf/coercion` (#8737).

**Six spellings of `?count=` that used to be accepted now return HTTP 400.** That is the part to
read before merging; it is in its own section below.

## What changes for you

**Several ways of reading your data that appeared to work, but were quietly giving wrong answers,
now give right ones. Six kinds of request that used to be accepted are now refused with a clear
error. No stored data is touched.**

### The one most likely to have bitten you

**`?count=0` asked for no records and was answered with your entire collection.**

`count` is how you say how many records you want. Zero means "no limit" to the database, so a
request for zero records downloaded **everything** — potentially years of CGM readings. Any client
that calculates its own `count` and can arrive at zero (a paging loop that has run out, a
subtraction that reaches the end of a list) was silently pulling the whole database on every such
request. On a large site that is a slow page, a spike in hosting cost, and on a metered connection
a real one. `?count=abc` did the same thing.

This now returns a clear error instead of an unbounded download.

### The rest

- **Counting returned zero for everything.** `GET /api/v1/count/entries/where` and
  `/api/v1/count/treatments/where` came back as zero, or missing, for any request that did not
  spell out its own date range. The count endpoint built its filter from generic defaults instead
  of the collection's own settings, so the automatic "last two days" window was written as a text
  date into a field holding a number, and matched nothing. **Counts that came back as zero will now
  come back with a real number** — before: `[]`, after: `[{"_id":null,"count":288}]`. The count
  endpoint now uses exactly the same filter as the matching list endpoint, so the two can never
  disagree again.
- **Every count request wrote your query to the server log**, including the values in it. Those
  lines are removed.
- **API v3 paging lost and repeated records.** When a page boundary fell inside a group of records
  the sort could not tell apart — records with no `identifier` sharing a `created_at` and a `date`,
  which is what an uploader writing in bursts or a bulk import produces — documents could be skipped
  and others returned twice. Paging three at a time through twelve such records returned **only
  seven of them, three more than once**. This affected `devicestatus` most. **If a tool paged
  `devicestatus` and appeared to be missing records, re-run it.**
- **API v3 `?fields=` with a dot returned an empty record.** `GET
  /api/v3/devicestatus?fields=uploader.battery` was answered with a success code and `{}`. It now
  returns `{"uploader":{"battery":80}}`. Comma-separated top-level fields such as
  `?fields=device,created_at` were never affected.

### Six requests that used to be accepted are now refused — please read

`count` must now be a whole number of documents, 1 or greater. Anything else returns
`{"status":400,"message":"Bad count"}`. **A client sending any of these will start getting an
error where it previously got an answer:**

Measured through the shipping v1 router against a collection of 24 entries:

| you send | before | after |
|---|---|---|
| `?count=0` | **all 24 — the whole collection** | 400 |
| `?count=abc` | **all 24 — the whole collection** | 400 |
| `?count=1e2` | 1 record — a hundred were asked for | 400 |
| `?count=-3` | 3 records | 400 |
| `?count=0x10` | 16 records | 400 |
| `?count=2.5` | 2 records | 400 |

`parseInt` was reading each of these and the driver was taking whatever came out: `NaN` and `0`
both mean *no limit* to MongoDB, which is why the first two were unbounded.

**Only the last two are pure restrictions.** `0x10` → 16 and `2.5` → 2 are defensible readings that
now do not work at all; a client sending either was getting a sane answer and will now get an error.
The first four were all returning something other than what was asked for. Integers above
`Number.MAX_SAFE_INTEGER` are also refused.

**Unchanged:** `?count=1`, `?count=10`, `?count=" 5 "`, leaving `count` out, and sending it empty.
**No upper limit was introduced** — a client that deliberately sends `count=100000` is unaffected.
The equivalent tightening applies to `?limit=` on API v3, which is additionally capped at
`API3_MAX_LIMIT` as it always was.

**The scope is wider than the read routes.** The check is `app.use`'d on the whole v1 API ahead of
every router, so it also covers `/treatments`, `/profile`, `/devicestatus`, `/notifications`,
`/activity`, `/food`, `/status`, `/alexa` and `/googlehome`, **and writes as well as reads**. A
`POST /api/v1/treatments?count=0` now returns 400 where it previously succeeded. One mount point is
**not** covered: `/experiments` is mounted at `lib/api/index.js:38`, ahead of the check at `:51`.

If a tool of yours stops working after this upgrade with a "Bad count" message, that tool was
sending one of these values and getting an answer it did not ask for.

Nightscout is not a medical device and this note is not medical advice. Take questions about your
therapy to your care team.

---

## The commits

| commit | what |
|---|---|
| `4772b983` | `count/:storage/where` built its filter from `query.js` defaults; now delegates to each collection's own `query_for` (**BF-01**) |
| `3b588098` | remove the unguarded filter log from the count path (**BF-05**) |
| `5a5269a3` | v3 paging: a unique last-resort tiebreak in the sort chain (**BF-13**) |
| `12207df3` | v3 `?fields=` with a dotted path (**BF-15**) |
| `06b133a7` | v1 `?count=` validation — `lib/server/count.js`, new file (**BF-14**) |
| `2ecfeb53` | v3 `?limit=` validation in `parseLimit` (**BF-33**) |

`3b588098` must stay after `4772b983`; they share `lib/server/aggregate.js` and
`tests/api.count-where.test.js`. Every other commit stands alone.

## Verifying it

```
TEST=api.count-where      npm run test-single    #  5 passing
TEST=api.count-parameter  npm run test-single    # 13 passing
TEST=api3.paging          npm run test-single    #  3 passing
TEST=api3.fields          npm run test-single    #  6 passing
TEST=api3.limit           npm run test-single    #  8 passing
                                                 # 35 passing, 0 failing
```

Re-measured 2026-09-16 on `2ecfeb53`.

**All five need a running MongoDB.** Pointed at a dead port, `TEST=api.count-parameter` goes from
13 passing to 0 passing / 1 failing, timing out in the before-all hook.

**None of the five is in `npm run test:unit`.** That script resolves to a 44-file brace list; four
of the five match `test:integration` (89 files) instead, and `tests/api.count-where.test.js`
matches neither. **A clean `npm run test:unit` on this branch is not evidence that any of these six
fixes works** — use `npm test`, which is what `main.yml` runs over all of `./tests/*.test.js`.

## Semver: minor, plus one breaking row that makes it major as it stands

Five of the six commits are minor or patch. `06b133a7` — the `?count=` tightening — is a restriction
on previously-accepted input across every v1 route, reads and writes, and that is what grades the
branch major. **Split `06b133a7` out and the remainder is a clean minor.** It is graded major
narrowly: only two of the six refused spellings were returning a defensible answer, and the other
four were already wrong. But it is a restriction on previously-accepted input on every v1 route
including writes, and that is the whole of the breaking surface in this branch.

The "What changes for you" text above is the release-note source; this branch adds no
`CHANGELOG.md` entry. The six-row table and the wider-than-read-routes scope note are the part that
must survive into the release notes, because they are the only warning a tool author gets.

## Interaction with `bf/coercion` (#8737)

Both branches rewrite query construction and share six files under `lib/server/`. Neither is based
on the other and they merge clean in either order, but a clean textual merge is a statement about
hunks rather than behaviour, so the merged tree was checked directly.

The specific risk: `bf/coercion` gives `query.js` a new `collection:` option, and this branch fixes
`aggregate.js`, which calls `query.js`. Had `aggregate.js` passed no options, both PRs would land
clean and the count path would still get the legacy default walker — so `count/.../where` on
`devicestatus` would stay untyped after two changes that each looked complete.

**It does not.** `aggregate.js` no longer builds a filter at all; it calls `api.query_for(opts)`,
and every collection's `query_for` passes its own `storage.queryOpts`, each of which names its
collection. Measured by executing the real storage modules with the database call stubbed and
capturing the `$match` the count pipeline builds, with two control arms:

| tree | `find[uploader.battery][$lte]=20` on `devicestatus` |
|---|---|
| `origin/dev` (control) | `{"$lte":"20"}` — text, matches nothing |
| `bf/reads` alone (control) | `{"$lte":"20"}` — text, matches nothing |
| both branches applied | `{"$lte":20}` — number, correct |

Both controls produce the broken result and the combined tree does not, so the probe distinguishes
the branches. The same probe shows the typing is correctly per-collection: `sgv` is converted on
`entries` and left alone on `devicestatus` and `treatments`, where it is not a declared field.

**Limit on this evidence.** The probe measures *the filter that is built*, with the Mongo driver
call stubbed. It is not an end-to-end assertion that `count/devicestatus/where` returns rows from a
live database. That test does not exist and should be written.

`lib/authorization/storage.js` appears in this diff for one reason and it is worth saying, since it
is the only other caller of `query.js`: it names **no** collection and passes
`{dateField:'created_at', noDateFilter:true}`. If `noDateFilter` ever stopped being honoured, every
auth subject lookup would silently gain a four-day window and older subjects would vanish, breaking
logins. Measured across all three trees: no date bound is added on any of them, identically. No
defect.

## Follow-ups deliberately not in this PR

- **The end-to-end count test against a live database.** The composition above is measured at the
  constructed filter, not at a returned row.
- **The limit rule is now written twice** — `lib/server/count.js` and API v3's `parseLimit` — so
  that each commit lands alone. `lib/server/count.js` does not exist on `dev`; **this branch creates
  it**, so merging this is what creates the duplication. The two copies currently agree (same
  `/^\s*\d+\s*$/` test, same `Number.isSafeInteger && > 0` rule; v3 additionally caps at
  `API3_MAX_LIMIT`), which is exactly why it would be easy to let them drift.
- **`lib/authorization/storage.js` names no collection**, so it keeps the legacy
  `{date: parseInt, sgv: parseInt}` guess. Inert today — auth documents have neither field — but
  worth naming a collection so it cannot become live later.
- **`lib/authorization/storage.js:82` has a second unguarded `console.log` on a request path**, the
  same shape as the count-path log removed here. It is not introduced by this branch; it is on `dev`
  at `:84`. It is repaired on the `bf/auth` branch, which is not yet open as a PR, so it is still
  live on `dev` today.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared against
  `!== null`. No caller today, so nothing observable.
- **One test label in this branch is wrong and should be corrected before or after merge.**
  `tests/api.count-parameter.test.js:59` labels the hex case *"hex notation, which parseInt reads as
  zero"*. That is v3's behaviour. On v1 `parseInt('0x10')` is **16**, because v1 calls `parseInt`
  without a radix — which is why the table above says 16. The assertion is right; only the label
  describing it is wrong.
