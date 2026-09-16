# E — `bf/reads`: six read-path fixes, including a request for zero records answered with everything

> **Base: `origin/dev` `a8888f0d`. This is one of NINE INDEPENDENT PRs. There is no stack.**
> This branch was previously rebased onto `bf/coercion` (D) to resolve a `CHANGELOG.md` collision.
> **That stack is dissolved.** The changelog edits were stripped by the maintainer's instruction,
> this branch was un-stacked and rebased directly onto `origin/dev`, and D and E now merge cleanly
> against `origin/dev` and against each other. **Merge order no longer matters.**
>
> **This branch is `2ecfeb53`, six commits**, none of which is D's and none of which touches
> `CHANGELOG.md`. The SHAs `0d19bb31` (old tip, a changelog-only commit) and `88d1f8a4` (D's, which
> used to arrive with the rebase) appear in older documents and are stale. Backup:
> `bf/reads.bak-changelog`. `git range-diff` shows all six surviving commits content-identical.
>
> **Two previously-accepted requests now return an error.** They are listed under "Two new
> restrictions" and are the reason this branch is not a pure bug fix.

## What changes for you

**Several ways of reading your data that appeared to work, but were quietly giving wrong answers,
now give right ones. Two kinds of request that used to be accepted are now refused with a clear
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

### Two new restrictions — please read

These are **not** bug fixes. They refuse requests that Nightscout used to accept, so a client
relying on either will start getting an error.

- **`?count=0x10` (and other hexadecimal counts) now returns HTTP 400.** It previously meant 16.
- **`?count=2.5` (and other fractional counts) now returns HTTP 400.** It previously returned 2.

Alongside these, `?count=0`, `?count=-3`, `?count=1e2` and `?count=abc` are also refused. `count`
must now be a whole number of documents, 1 or greater. Anything else returns
`{"status":400,"message":"Bad count"}`.

**No upper limit was introduced** — a client that deliberately sends `count=100000` is unaffected.
Leaving `count` out entirely, or sending it empty, still uses each endpoint's default. The
equivalent tightening applies to `?limit=` on API v3, which is additionally capped at
`API3_MAX_LIMIT` as it always was.

**Scope is wider than the read routes, and the release notes must say so.** The check is installed
on the whole v1 API ahead of every route, so it also covers `/treatments`, `/profile`,
`/devicestatus`, `/notifications`, `/activity`, `/food`, `/status`, `/alexa` and `/googlehome`,
**and writes as well as reads**. A `POST /api/v1/treatments?count=0` now returns 400 where it
previously succeeded. *(Measured by GT4. An earlier draft of this PR body, and the changelog text
that used to sit on this branch, listed only the read routes; that understatement is corrected
here.)*

If a tool of yours stops working after this upgrade with a "Bad count" message, that tool was
sending one of these values and getting an answer it did not ask for.

Nightscout is not a medical device and this note is not medical advice. Take questions about your
therapy to your care team.

---

## Technical detail

Six commits, 17 files. **None of them touches `CHANGELOG.md`** — verified 2026-09-15 with
`git diff --name-only origin/dev...bf/reads`.

| commit | register | what |
|---|---|---|
| `4772b983` | **BF-01** | `count/:storage/where` built its filter from `query.js` defaults; now delegates to each collection's own `query_for` |
| `3b588098` | BF-05 shape | removed the unguarded filter log from the count path |
| `5a5269a3` | — | v3 paging adds a unique last-resort tiebreak to the sort chain |
| `12207df3` | — | v3 `?fields=` with a dotted path |
| `06b133a7` | **BF-33** | `?count=` validation (`lib/server/count.js`, new file) |
| `2ecfeb53` | — | v3 `?limit=` validation (`parseLimit`) |

Files touched: `lib/api/index.js`, `lib/api3/generic/collection.js`,
`lib/api3/generic/search/input.js`, `lib/api3/shared/fieldsProjector.js`,
`lib/authorization/storage.js`, `lib/server/{activity,aggregate,count,devicestatus,entries,
profile,treatments}.js`, plus five test files.

## Evidence

- Backfix register `docs/30-design/nightscout-backfix-register.md` — **BF-01** (count built from
  defaults), **BF-33**, and the v3 paging and `?fields=` entries.
- Read-defect evidence `docs/60-research/bf01-13-14-15-read-defects-2026-09-15.md`.
- Semver: `docs/60-research/gt4-semver-classification-2026-09-15.md` rows 13–18 — the `?count=`
  restriction is one of **three rows that make Phase 0 as a whole a major release**. Taken alone
  this branch is a minor plus one breaking row; split the `?count=` tightening out and the rest is a
  clean minor. (GT4's row SHAs predate the changelog strip and no longer resolve; the mapping to the
  six commits above is by content.)

## Test evidence

All five of this branch's test files were run individually, **measured 2026-09-15** from
`externals/work/crm-bf-reads`. **They all need MongoDB** — they were run against the mongod on this
worktree's port, which was answering today:

```
TEST=api.count-where      npm run test-single    #  5 passing, 0 failing, 2 s
TEST=api.count-parameter  npm run test-single    # 13 passing, 0 failing, 2 s
TEST=api3.paging          npm run test-single    #  3 passing, 0 failing, 552 ms
TEST=api3.fields          npm run test-single    #  6 passing, 0 failing, 1 s
TEST=api3.limit           npm run test-single    #  8 passing, 0 failing, 533 ms
                                                 # ---------------------------
                                                 # 35 passing, 0 failing
```

> **Correction to two earlier statements.** (1) An earlier version of this body recorded that
> `api.count-where` and `api.count-parameter` *could not be executed* because this worktree's
> mongod accepted a TCP connection but never completed a handshake. **They ran today.** That was a
> property of the machine on the day, not of the branch. (2) It is **not** true that these run
> without a database: pointed at a dead mongo port, `TEST=api.count-parameter` goes from 13 passing
> to 0 passing / 1 failing, timing out in the before-all hook. Any claim that these are
> database-free targeted runs is wrong.

- **None of these five files is in `npm run test:unit`.** Measured by expanding the brace lists:
  `test:unit` resolves to 44 files, `test:integration` to 89. Four of the five *are* in
  `test:integration` (`api*`, `api3*`). **A clean `test:unit` run on this branch is not evidence
  that any of these six fixes works.** CI is not blind to it — `main.yml` runs `test-ci` over all of
  `./tests/*.test.js`.
- Full suite on the merged D+E tree, run by an earlier session at 17:24 on the pre-strip SHAs:
  **2076 passing, 3 pending, 0 failing**, exactly additive — 2028 base + 35 from reads + 13 from
  coercion. Nothing lost, nothing duplicated, no existing expectation moved. Read from that
  session's record, not re-run here, and its SHAs are the pre-strip ones; `git range-diff` shows all
  six commits content-identical across the strip, so the figure carries.
- Merges clean against `origin/dev` `a8888f0d` — `git merge-tree --write-tree` re-run 2026-09-15 —
  and clean against all eight other Phase 0 branches, including `bf/coercion` at `b7234753`.

---

## The D/E interaction (this is the part that mattered, and it is no longer a merge question)

`bf/coercion` and `bf/reads` both rewrite query construction and share six files under
`lib/server/`. A clean textual merge is a statement about hunks, not about behaviour, so the merged
tree was checked directly.

**A specific gap was predicted:** `bf/coercion` gives `query.js` a new `collection:` option;
`bf/reads` fixes `aggregate.js`, which calls `query.js`. If `aggregate.js` passed no options, both
PRs would land clean and the count path would still get the legacy default walker — so
`count/.../where` on `devicestatus` would stay untyped after two changes that each looked complete.

**Measured 2026-09-15: the gap does not exist, and the reason is that BF-01's fix is better than
the prediction assumed.** `aggregate.js` no longer builds a filter at all; it calls
`api.query_for(opts)`, and every collection's `query_for` passes its own `storage.queryOpts`, each
of which names its collection. The two fixes compose — **in either merge order**, since neither
branch is based on the other.

Verified by executing the real storage modules with the database call stubbed, capturing the
`$match` that the count pipeline actually builds, with two control arms:

| tree | `find[uploader.battery][$lte]=20` on `devicestatus` |
|---|---|
| `origin/dev` (control) | `{"$lte":"20"}` — **text, matches nothing** |
| `bf/reads` alone (control) | `{"$lte":"20"}` — **text, matches nothing** |
| both branches applied | `{"$lte":20}` — **number, correct** |

The same probe shows the typing is correctly per-collection: `sgv` is converted on `entries` and
left alone on `devicestatus` and `treatments`, where it is not a declared field. Because the two
control arms produce the broken result and the combined tree does not, the probe distinguishes the
branches and the result is not vacuous.

**A second instance of the same shape was hunted and cleared.**
`lib/authorization/storage.js` is the only other caller of `query.js`, and it names **no**
collection — it passes `{dateField:'created_at', noDateFilter:true}`. Had `noDateFilter` stopped
being honoured, every auth subject lookup would have silently gained a four-day window and
older subjects would have vanished, breaking logins. Measured across all three trees: no date bound
is added on any of them, identically. **No defect.** The legacy `{date: parseInt, sgv: parseInt}`
guess does still apply there, but auth documents have neither field, so it is inert.

> **Honest limit on this evidence.** The probe drives the real `query.js`, `aggregate.js` and each
> storage module with the Mongo driver call stubbed, so it measures **the filter that is built**.
> It is not an end-to-end assertion that `count/devicestatus/where` returns rows from a live
> database — that test does not exist and should be written. What was previously recorded as
> read-derived reasoning is now a measurement of the constructed filter, with controls; it is not
> yet a measurement of a returned row.

---

## Semver

**Minor plus one breaking row, which makes it major as it stands.** Row 17 of
`docs/60-research/gt4-semver-classification-2026-09-15.md` grades the `?count=` tightening **major**
— narrowly, with the counter-argument stated at length in its §3.5 — because it is a restriction on
previously-accepted input across every v1 route, reads and writes. Rows 13, 16 and 18 are minor;
rows 14 and 15 are patch. **Split the `?count=` commit (`06b133a7`) out and the remainder of this
branch is a clean minor.**

**The operator-visible text above belongs in the release notes.** It is *not* a `CHANGELOG.md`
entry, and this branch no longer carries one: under the maintainer's rule, `CHANGELOG.md` is a
**release output** generated by GitHub tooling between releases, and branches never hand-edit it.
The changelog-only commit that used to sit at this branch's tip was dropped for that reason. **The
"Two new restrictions" section and the wider-than-read-routes scope note must survive into the
release notes**, because they are the only warning a tool author gets.

---

## Follow-ups deliberately **not** in this PR

- **The end-to-end count test against a live database.** The D/E composition above is measured at
  the constructed filter, not at a returned row. That test does not exist.
- **`lib/authorization/storage.js` names no collection**, so it keeps the legacy type guess. Inert
  today; worth closing so it cannot become live. No register id.
- **The limit rule is written twice** — `lib/server/count.js` and API v3's `parseLimit` — on
  purpose, so each commit lands alone. *Two readings of one rule is the root cause of this whole
  family of defects*, so leaving it duplicated is a debt with a name. Note that
  `lib/server/count.js` does not exist on `origin/dev` — **this branch creates it**, so landing E is
  what creates the duplication. Measured 2026-09-15: the two copies currently **agree** (same
  `/^\s*\d+\s*$/` test, same `Number.isSafeInteger && > 0` rule; v3 additionally caps at
  `API3_MAX_LIMIT`), which is exactly why it is easy to forget about.
- **BF-40 — `$exists=false` is inverted on every field**, before and after `bf/coercion`. Not this
  branch's, but it is in the same query surface an operator will be testing after both land. Open.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared against
  `!== null`. No caller, so no register id.
- **`lib/authorization/storage.js` has a second unguarded `console.log` on a request path**, same
  shape as BF-05, different file (`:84` on `origin/dev`, `:82` on this branch).
