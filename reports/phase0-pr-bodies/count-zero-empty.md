# `bf/count-zero-empty`: a request for zero records gets an empty answer, and writes ignore `count`

**DRAFT. Not pushed, not opened.** Branch `bf/count-zero-empty` on `origin/dev` `74fc6619`, tip
`7b32d9ab`, one commit. No `CHANGELOG.md` edit. The version stays 15.0.9. This implements the
maintainer's 2026-09-23 decision on how PR #8738 treats `?count=`.

| what changes | who can see it |
|---|---|
| a read with `count=0` gets `200` and an empty list, where `dev` answers `400` | any app or script that asks the API for zero records |
| a write (save, update or delete) that carries a `count` is carried out, where `dev` answers `400` and does not make the write | any app or script that sends a `count` along with a write |

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice.*

A few words used below:

- **API**: the web address that apps such as uploaders, phone apps and reporting tools use to read
  from and save to your Nightscout site.
- **`count`**: a number an app can add to a request to say how many records it wants back, for
  example "the last 10 glucose readings".
- **Read** and **write**: a read asks Nightscout for records. A write saves, changes or deletes
  them.

### Asking for zero records

Before 15.0.9, asking for zero records (`count=0`) did something surprising: Nightscout sent back
**every record in that part of the database**, for example your whole glucose history. That could
be slow, and it was never what the app asked for. The next release already fixes that, but the fix
answered with an **error** instead.

With this change, asking for zero records gets an **empty answer**: no records, and no error. It
still **never** returns your whole history.

Other numbers Nightscout cannot read as a plain whole number still get an error, as they do in the
current development version: `-3`, `2.5`, `1e2`, `0x10`, `abc`, and numbers too large to handle
exactly. Asking for no particular number still gets the usual default (for glucose readings, the
last 10).

### Saving, changing and deleting records

In the current development version, a save, change or delete that happened to include a `count`
that Nightscout could not read was **refused, and the change was not made**. No write uses `count`,
so this was never needed. With this change, writes ignore `count` completely and work exactly as
they do without it.

One thing to know: a delete deletes **every record it matches**, and `count` does not limit that.
That was already true before 15.0.9 and has not changed. `count=0` on a delete does **not** mean
"delete nothing".

**What you should do:** nothing. Apps that already work keep working. If you use an app that asks
for zero records, it now gets an empty answer instead of an error.

---

## Technical detail

### What the commit does

- `lib/server/count.js`: new `isZeroCount()` (the same digits rule as `parseCount`, so `0`, `00`
  and ` 0 ` are zero and `-0`, `0x10` are not). `applyCount()` answers a zero count with an object
  whose `toArray()` resolves `[]`, so the driver is never called. `.limit(0)` means *no limit* in
  MongoDB and there is no limit that means "none". Every `list()` helper ends its chain with
  `.toArray()` straight after `applyCount`.
- `lib/api/index.js` `validateCount`: runs on `GET` and `HEAD` only, and lets a zero count through.
  The 400 description now says "0 or greater".
- `lib/api/devicestatus/index.js`: the route's own parse turned `0` into its default of 10. It now
  keeps 0 (the cache slice and the storage layer then both return `[]`).
- `lib/server/profile.js` `list(fn, count)` (behind `GET /api/v1/profile`): a zero count returns
  `[]` in place of falling back to `PROFILES_DEFAULT_COUNT`.

Routes that do not apply `count` at all still ignore it, so they answer `count=0` normally rather
than with `[]`: `/entries/current` (always 1 record), `/count/:storage/where` (an aggregate),
`/echo`, `/status`, `/food`. On `dev` all of these answered `count=0` with 400.

### Read matrix

Server booted from each tree against a fresh `mongo:7` container. Seeded directly in mongo and
counted there, not through the API: 30 entries, 120 treatments, 30 devicestatus, 15 profile, 15
activity, 0 food. `(db)` rows add a `find[...]` so the runtime cache cannot answer. Cells are
`status:rows`; `cnt30` is the aggregate's count.

`origin/dev` `74fc6619`:

```
route                (none)     5       0    00   0x10 2.5  -3  1e2  abc  MAXSAFE  MAXSAFE+1 empty   %205  +5    %2B5  05    1&2
entries(cache)       200:10     200:5   400  400  400  400  400  400  400  200:30   400       200:10  200:5 200:5 400   200:5 400
entries(db)          200:10     200:5   400  400  400  400  400  400  400  200:30   400       200:10  200:5 200:5 400   200:5 400
entries/sgv          200:10     200:5   400  400  400  400  400  400  400  200:30   400       200:10  200:5 200:5 400   200:5 400
entries/current      200:1      200:1   400  400  400  400  400  400  400  200:1    400       200:1   200:1 200:1 400   200:1 400
treatments(cache)    200:100    200:5   400  400  400  400  400  400  400  200:120  400       200:100 200:5 200:5 400   200:5 400
treatments(db)       200:120    200:5   400  400  400  400  400  400  400  200:120  400       200:120 200:5 200:5 400   200:5 400
devicestatus(cache)  200:10     200:5   400  400  400  400  400  400  400  200:30   400       200:10  200:5 200:5 400   200:5 400
devicestatus(db)     200:10     200:5   400  400  400  400  400  400  400  200:30   400       200:10  200:5 200:5 400   200:5 400
profile              200:10     200:5   400  400  400  400  400  400  400  200:15   400       200:10  200:5 200:5 400   200:5 400
profiles             200:10     200:5   400  400  400  400  400  400  400  200:15   400       200:10  200:5 200:5 400   200:5 400
activity             200:15     200:5   400  400  400  400  400  400  400  200:15   400       200:15  200:5 200:5 400   200:5 400
food                 200:0      200:0   400  400  400  400  400  400  400  200:0    400       200:0   200:0 200:0 400   200:0 400
times                200:10     200:5   400  400  400  400  400  400  400  200:30   400       200:10  200:5 200:5 400   200:5 400
slice                200:10     200:5   400  400  400  400  400  400  400  200:30   400       200:10  200:5 200:5 400   200:5 400
count/where          200:cnt30  cnt30   400  400  400  400  400  400  400  cnt30    400       cnt30   cnt30 cnt30 400   cnt30 400
echo / status        200        200     400  400  400  400  400  400  400  200      400       200     200   200   400   200   400
```

This branch: **identical except the `0` and `00` columns**, which become:

```
route                0          00
entries(cache)       200:0      200:0
entries(db)          200:0      200:0
entries/sgv          200:0      200:0
entries/current      200:1      200:1     (route ignores count)
treatments(cache)    200:0      200:0
treatments(db)       200:0      200:0
devicestatus(cache)  200:0      200:0
devicestatus(db)     200:0      200:0
profile              200:0      200:0
profiles             200:0      200:0
activity             200:0      200:0
food                 200:0      200:0     (route ignores count; 0 food seeded)
times                200:0      200:0
slice                200:0      200:0
count/where          200:cnt30  200:cnt30 (route ignores count)
echo / status        200        200       (route ignores count)
```

Spellings the decision did not name keep their `dev` behaviour: empty `count=` is the default;
`count=%205` (a space, then 5) and a literal `count=+5` (which a query string decodes to a space,
then 5) read as 5; `count=%2B5` (a real `+`) is 400; `05` reads as 5; `count=1&count=2` (repeated,
so Express hands over an array) is 400. `MAXSAFE` is `9007199254740991` and is accepted; one more
is 400.

### Write probe

Each request authenticated with the API secret. Its effect was measured in mongo directly: rows
stored, updated or left over from a set seeded for that request.

On `origin/dev`, every write route below answered **400 and made no change** when `count` was
`0`, `abc` or `count=1&count=2`, and 200 with the write made when `count` was absent or `2`:
POST `/entries`, `/entries/preview`, `/treatments`, `/devicestatus`, `/profile`, `/food`,
`/activity`; PUT `/treatments`, `/profile`, `/food`, `/activity`; DELETE `/entries?find`,
`/entries/:id`, `/treatments?find`, `/treatments/:id`, `/devicestatus?find`, `/devicestatus/:id`,
`/profile/:id`, `/profile?keep=10000`, `/food/:id`, `/activity/:id`.

On this branch every one of those answers 200 and makes the write, for every spelling, exactly as
without `count`. `count` limits no delete on either tree: `DELETE /entries/?find[...]&count=2`
removed all 5 of 5 matching rows on `dev` and on this branch.

### Tests

`tests/api.count-parameter.test.js`. New: 9 read routes answer `count=0` (or `00`) with `[]` over
collections that hold matching documents, so a read that lost its bound shows up as non-empty; the
storage layer's `list()` answers `'0'`, `0` and `'00'` with `[]`; 9 write tests (POST entries,
DELETE entries by `find`, POST devicestatus, each with `count=abc`, `0` and `-3`) check the write
in the database.

**Changed expectations** (each marked in the file as a 2026-09-23 decision): `count=0` on entries,
on `/profiles` and on `/treatments` was expected to be 400 and is now 200 with `[]`.

Non-vacuity: all 21 new or changed tests fail on `origin/dev`'s `lib/`: 20 with `400`, and the
storage test with 24 rows where it expected none. Breaking the fix:

| break | result |
|---|---|
| zero falls through to no limit (`applyCount` and `profile.list`) | 9 fail, "length of 0 (got 24)" / "(got 3)" |
| `validateCount` refuses zero again | 11 fail, `expected 200, got 400` |
| `validateCount` runs on writes again | 6 fail (the `abc` and `-3` writes), `expected 200, got 400` |
| devicestatus route turns 0 into 10 again | 2 fail, "length of 0 (got 3)" |

Full suite (`mocha --timeout 5000 --require ./tests/hooks.js --exit ./tests/*.test.js`, Node
20.20.0, `mongo:7`), run back to back:

| tree | passing | failing | pending |
|---|---:|---:|---:|
| `origin/dev` `74fc6619` | 2386 | 0 | 3 |
| `bf/count-zero-empty` `7b32d9ab` | 2404 | 0 | 3 |

The difference of 18: 19 new tests, minus the `count=0` case that left the refusal list.

### Not in this branch

- **API v3 is unchanged.** `?limit=0` on v3 search and history is still 400 (`tests/api3.limit.test.js`
  "refuses zero: limit=0" passes on this branch), the same as before
  #8738. v1 and v3 now differ about zero: v1 accepts it, v3 refuses it, and only v3 has a ceiling.
  The follow-up that would merge the two readings (`lib/server/count.js` and v3's `parseLimit`)
  therefore has to keep two rules, not one.
- The storage `list()` helpers still read `-3`, `abc` and `1e2` as "no count": no limit at all,
  not `.limit(0)`. The API refuses those on reads before they get there. Only a caller that
  reaches the storage layer directly sees it. This was already the case on `dev`.
- `/pebble?count=0` is not under `/api/v1` and still reads 0 as 1 (`parseInt(...) || 1`); measured on this branch, it returned 1 reading.
