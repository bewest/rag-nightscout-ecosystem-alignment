# Backfix register — defects that ship to existing operators, independent of multitenancy

**Living document.** Started 2026-09-14. Maintained alongside the
[multitenancy execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md).

This exists because the multitenancy programme keeps finding bugs in **today's** Nightscout,
and those findings must not become hostage to a large architectural change. Every entry here
is a defect that

- affects **single-tenant self-hosters running the current release**, and
- is fixable **without any tenancy decision**, and
- should therefore be landable on its own, on `dev` or on
  `chore/nightscout-modernization`, ahead of the seam.

> **D4 makes this permanent, not temporary.** MongoDB and single-tenant are first-class
> forever, so "we will fix it when the Postgres backend lands" is never an answer for anything
> in this table.

**Status values**: `open` · `fixed-in-seam` (repaired inside the seam branch as a side effect,
needs extraction to land independently) · `landed` · `wontfix`.

---

## 1. Register

| id | defect | where | severity | tenancy-independent | status |
|---|---|---|---|---|---|
| **BF-01** | `GET /api/v1/count/entries/where` silently matches nothing | `lib/server/aggregate.js:21` | **high** — wrong answer, HTTP 200 | yes | open |
| **BF-02** | `insulin`/`carbs` query bounds truncated by `parseInt` | `lib/server/treatments.js:259-266` | **high** — wrong answer, HTTP 200 | yes | open |
| **BF-03** | Numeric filters on `devicestatus`, `activity`, `food`, `profile` match nothing | `lib/server/query.js` walker, per-collection | **high** — wrong answer, HTTP 200 | yes | open |
| **BF-11** | `treatments.duration` and `rate` have no walker entry — temp-basal filters match nothing | `lib/server/treatments.js:259-266` | **high** — wrong answer, HTTP 200 | yes | open |
| **BF-12** | `entries.rawbg` is coerced but is not in the model — stale walker entry | `lib/server/entries.js:186` | low — dead entry | yes | open |
| **BF-13** | API v3 `skip`/`limit` paging silently loses and duplicates documents when the whole sort chain ties | `lib/api3/generic/search/input.js` `parseSort` | **high** — silent data loss on a read | yes | open |
| **BF-14** | API v1 `?count=0` (and `-3`, `1e2`) reaches the driver unvalidated — `.limit(0)` means *unbounded* | `lib/server/entries.js:56` + 4 siblings | medium — unbounded read from a bounded request; no client triggers it today | yes | open |
| **BF-15** | API v3 `?fields=<dotted.path>` returns an empty document with HTTP 200 | `lib/api3/shared/fieldsProjector.js` `applyProjection` | **medium** — silently empty response to a valid request | yes | open |
| **BF-16** | Food quick-pick `hidden` filter compares to the **string** `'false'`; the field has no declared type and its stored type depends on the request's content type | `lib/server/food.js` `listquickpicks` + `lib/food/food.js:69` `restoreBoolValue` | **medium** — a JSON writer's quick picks silently vanish from the quick-pick list; no shipping client triggers it today | yes | open |
| **BF-17** | Editing a subject through the stock admin UI **persists the API access token in plaintext**, into a field the server otherwise only derives | `lib/authorization/endpoints.js:38-42` + `lib/admin_plugins/subjects.js:43` + `lib/authorization/storage.js` `save` | **high** — turns read access to the database into API access; no key required | yes | open |
| **BF-04** | API v1 has no operator allowlist — filter pass-through reaches the driver | `lib/server/query.js:157` | **high** — ReDoS / full-scan exposure | yes | fixed-in-seam |
| **BF-05** | Unguarded `console.log` of every count query on the request path | `lib/server/aggregate.js:30-31` | **medium** — log noise, filter contents to stdout | yes | open |
| **BF-06** | `/api/v1/entries?count=10` costs 42× a typed read | `lib/server/cache.js:73-76` | medium — CPU | yes | open |
| **BF-07** | `cache.insertData` JSON round-trips the whole retained array | `lib/server/cache.js:81` | medium — 65 % of the load cycle | yes | open |
| **BF-08** | `nightscout-connect` actors have no start or interval jitter | `nightscout-connect`, `run()` | medium — thundering herd on restart | yes | open |
| **BF-09** | Socket dedup uses truthiness, so a `0` insulin/carbs value is skipped as a match key | `lib/server/websocket.js:535-568` | **unsettled** — may be intentional | yes | open |
| **BF-10** | `mongod` fatal-asserts at Docker's default `nofile=1024` | operational, not code | medium — self-hosters in containers | yes | open |

## 2. Detail

### BF-01 · `count/entries/where` silently matches nothing

`aggregate.js:21` calls `find_options(opts)` with **one argument**, so the collection's
`queryOpts` never arrive and `lib/server/query.js` falls back to its defaults — `dateField:
'date'`, no `useEpoch`. The two paths then inject different types for the same window:

```
list  path (useEpoch:true):  {"date":{"$gte":1789099222823}}              <- number
count path (defaults)     :  {"date":{"$gte":"2026-09-11T04:00:22.824Z"}} <- ISO string
```

`entries.date` is declared `number`, and **MongoDB compares only within a BSON type**, so the
injected two-day window excludes every document rather than bounding it. The endpoint returns
`200` with a count of zero.

*Evidence*: [seam interface](nightscout-storage-seam-interface-2026-09-14.md) §4.3.1, verified by
running `query.js` directly. Independently reconfirmed as a general class by the
[three-arm validation](../60-research/seam-filter-ast-three-arm-validation-2026-09-14.md) §3 class B.
*Fix*: pass the collection's `queryOpts` as the second argument. Ship with BF-02/BF-03 (plan T0.5).

### BF-02 · `insulin` and `carbs` bounds truncated

`treatments.js` coerces query values through a hand-maintained per-collection `walker`:

```js
walker: { insulin: parseInt, carbs: parseInt, glucose: parseInt, ... }
```

`specs/nsschema/treatments.model.json` declares `insulin` and `carbs` as `number`, not integer.
So `find[insulin][$gte]=1.5` becomes `{"insulin":{"$gte":1}}` — **a query for boluses of at
least 1.5 units returns boluses of 1.0 units.**

**This is a data-correctness defect with review implications.** Anyone using the API to review
therapy data — a report tool, a clinician export, a caregiver checking what was delivered —
gets records that do not match what they asked for, with no error. It warrants a release note
rather than a silent fix. It is not, in itself, advice about dosing, and nothing here should be
read as such; the point is narrower and worse — **the data returned does not answer the
question asked.**

**Measured**, not asserted: `treatments.insulin` was observed as **142,360 fractional values
against 2,791 integer ones** across 11 sites — 98 % of its non-null values are fractional. So
`parseInt` on the bound is not a rounding nicety.

*Evidence*: [execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md) §3.4, and
[the coercion drift measurement](../60-research/query-coercion-drift-2026-09-14.md) §2 Tier 1.

### BF-03 · Numeric filters that silently match nothing

| collection | `walker` |
|---|---|
| entries | 7 fields, all `parseInt` |
| treatments | `insulin carbs glucose` → `parseInt`; `notes eventType enteredBy` → regex |
| profile | `{}` — empty |
| **devicestatus, activity, food** | **none at all** |

A field with no `walker` entry stays a **string**, and MongoDB's type ordering means a numeric
field never matches a string bound. So `devicestatus` and `activity` have no coercion at all
and **every numeric filter on them matches nothing and returns 200**:

```
devicestatus  uploader.battery $lt=50   ->  {"uploader.battery":{"$lt":"50"}}   <- still a string
entries       delta            $gte=1.5 ->  {"delta":{"$gte":"1.5"}}            <- still a string
```

**Fixing this is user-visible in the good direction**: queries that silently returned nothing
start returning rows. Release-note it, so it arrives as a fix rather than as a surprise.

*Fix*: plan T0.5 — emit a coercion table from `specs/nsschema/*.model.json` (a sixth emitter)
and drive the walker from it, instead of four hand-maintained lists that drift.
**The emitter now exists** (`tools/nsschema/emit/coercion_emit.py`, `make schema-emit`); what
remains is wiring `lib/server/query.js` to it, which is `cgm-remote-monitor` work.

**The gap is 158 disagreements** — 147 under-coercions, 8 over-coercions, 1 stale entry, and 2
collections with no model at all. Graded by corpus evidence in
[the coercion drift measurement](../60-research/query-coercion-drift-2026-09-14.md) §2, because
they are **not** 158 equivalent bugs: `entries.sgv` is declared `number` but was observed as
895,418 integers and **zero** fractional values, so truncating its bound harms nobody today.

> **Sharpened by the three-arm validation.** T0.5 was written as a v1 bug fix. It is also a
> **precondition for the seam's backend-equivalence claim**: with correctly-typed values, all
> three arms agree 3000/3000; with mistyped ones, four divergence classes open, two of which
> produce *different data* depending on which backend a deployment runs.
> See [three-arm validation](../60-research/seam-filter-ast-three-arm-validation-2026-09-14.md) §4.

### BF-14 · `?count=0` is an unbounded read

API v1 builds its limit in five places with one expression:

```js
limit: opts && opts.count ? parseInt(opts.count) : undefined
```

A truthiness test **on a string**, then `parseInt`. `'0'` is a non-empty string, so it passes the
test; `parseInt` yields `0`; and **MongoDB defines `.limit(0)` as "no limit"**. `?count=0` returns
the whole collection. Measured on a ten-document collection: `count=0` -> 10 rows.

Two more from the same expression: `count=-3` silently returns 3 documents (MongoDB reads a
negative limit as legacy single-batch semantics), and `count=1e2` returns **one** document
because `parseInt('1e2')` stops at the `e`.

Not a seam regression — `origin/dev` chains `this.limit(parseInt(opts.count))` and reaches the
identical driver call.

*Fix*: API v3 already has it. `lib/api3/generic/collection.js:76` bounds-checks against
`API3_MAX_LIMIT`, returns `HTTP 400` on `0`, `abc` or a negative, and defaults sanely when absent.
Give v1 the same validation rather than inventing one.

*Also relevant to the seam*: `findFiltered` falls back to `toSafeInt(o.limit, 0)`, and `0` is the
value that means unbounded. `findMany`, in the same file, defaults to `1000`.

*Evidence*: [limit and projection](../60-research/seam-limit-and-projection-2026-09-14.md) §2,
`tools/qc/shape-arm.js`, against a real mongod.

*Sized, and the measurement downgraded it from high to medium.*
`tools/qc/v1_count_census.py` over 10 client projects: **274 `count=` occurrences, no literal
`count=0`**. 86 % are literals (`1 … 9999999`); 9 % are computed at request time, which is where
the exposure sits — nothing bounds a computed count away from zero, and `oref0` has four such
sites. Two facts hold the grade down: nothing in the corpus reaches it today, and an unbounded
read is not a novel load for a server whose clients already send `count=100000` and
`count=9999999` deliberately. It returns no wrong data. It stays in the register because a
bounded request should not produce an unbounded read, and because the fix already exists in v3.

### BF-15 · `?fields=` with a dotted path returns `{}`

v3 projects in two stages. `storageProjection()` is handed to the driver, so MongoDB's
dotted-path rules apply and a **nested** document comes back. `applyProjection(doc)` then deletes
any **top-level** key not string-equal to something the client typed. A dotted request survives
stage one and is destroyed by stage two:

```
?fields=uploader.battery
  _id 1  from driver           {"_id":1,"uploader":{"battery":80}}
         after applyProjection {}          <- driver returned uploader; DESTROYED
```

The data is read, paid for, and discarded. The client gets `200` and an empty document.

`uploader.battery` is the canonical nested field in Nightscout and `devicestatus` is the
collection people query for it, so this is an ordinary request, not a contrived one.
Comma-separated top-level fields are unaffected, which is why it has gone unnoticed.

*Fix*: `applyProjection` must compare on paths rather than top-level keys — keep a key when any
requested field equals it or is prefixed by it plus `.`, and prune within the subtree. Either
that, or reject a dotted `fields` with `HTTP 400` rather than answering `200` with nothing.

*Evidence*: [limit and projection](../60-research/seam-limit-and-projection-2026-09-14.md) §3.3,
produced by running the shipping `fieldsProjector.js` against real mongod documents.

*Checked*: the system fields `storageProjection` adds and `applyProjection` removes are **not**
dead work — `col.resolveDates(doc)` consumes them in between
(`lib/api3/generic/search/operation.js:46-47`).

### BF-04 · No operator allowlist on API v1

`lib/server/query.js:157` builds the filter with `traverse` type-coercion, injects a date
constraint, and **returns it to the driver with no operator allowlist**. Whatever
`find[x][$op]` a client sends reaches MongoDB — `$where`, `$expr`, an unbounded `$regex`.

**Status `fixed-in-seam`.** The seam branch's `fromMongo` (commit `68ffbd66`) parses `query.js`'s
output into the AST, and an AST that cannot represent an unlisted operator *is* the allowlist —
so this is repaired there as a structural consequence. **It should not have to wait for the
seam to land.** Extracting the allowlist as a standalone change is a small piece of work and a
security fix that ships to every current operator.

*Evidence*: {M} §6.5; seam interface §8.2.

### BF-05 · Debug logging on the count request path

```js
console.log('$match query', query);
console.log('AGGREGATE', groupBy);
```

Unguarded, on both `dev` (`a8888f0d`) and `chore/nightscout-modernization` (`0a4109f6`), so
every `/api/v1/count/*` request writes the constructed filter to stdout. Two problems: it is
noise the modernization branch's own quiet-logging work (`c2ac743c`) set out to remove, and a
filter can carry values a deployment would rather not have in its logs. **Route through the
existing logger at debug level, or delete.**

### BF-06 · Untyped `/api/v1/entries` read costs 42×

`?count=10` costs **0.83 ms** without `find[type]` and **0.02 ms** with it, for a byte-identical
response, because `ctx.cache.getData('entries')` deep-clones the whole 48-hour array before
anything is sliced. *Fix*: slice first, then clone the slice — the documents handed out are
still clones, so the defensive property is preserved. *Evidence*: {R} §12.2. Plan T0.2.

### BF-07 · `cache.insertData` round-trips the whole retained array

`insertData` returns `getData()` — a JSON round-trip over the **whole** retained array, per
datatype, per cycle: **4.08 ms**, 65 % of the post-#8733 load cycle.
**Resolve `dataloader.js:203` first** — `if (!element.mills) element.mills = element.date` writes
to the element, so a shallow copy changes behaviour there. The measurement sizes the prize; it
does not license the patch. *Evidence*: {R} §12.3. Plan T0.3.

### BF-08 · No jitter in `nightscout-connect`

800 actors fire their first upstream request inside one second on every restart and deploy
(`run()` sends `START` with no jitter), and stay phase-locked on the same five-minute boundary
afterwards. Different repository; independent of everything else here. *Evidence*: {R} §6.2.

### BF-09 · Socket dedup truthiness — unsettled, deliberately

`websocket.js` tests `if (data.data.insulin)` rather than presence, so a **`0`** insulin or carbs
value is skipped as a match key. No test covers it. **Recorded rather than guessed**: it may be
intentional. It needs a maintainer decision, and whichever way it goes it needs a test, because
nothing currently pins the behaviour. *Evidence*: seam interface §4.4.

### BF-10 · `mongod` fatal-asserts at the default file-descriptor limit

Docker's default `nofile=1024` is not enough for the collections and indexes Nightscout's own
test suite creates: WiredTiger hits `Too many open files` in `__wt_open` and `mongod` takes a
`fassert()` — **aborting the server**, not failing an operation.

This was reached by an ordinary test run, and matches EXP-MT-040b's finding at 50 tenant
databases. **So the fd ceiling is not a scale-only concern** — it is reachable by a self-hoster
running `mongod` in a container with default limits. Not a code defect; it belongs in the
operator documentation, and it is the kind of failure that looks like data loss to the person
it happens to.

### BF-11 · `treatments.duration` and `rate` filters match nothing

Neither field has a `walker` entry, so a bound stays a string and MongoDB's type ordering means
it never matches a numeric field. `find[duration][$gte]=30` returns an empty list and HTTP 200.

`duration` is present on **91 % of treatment documents across 10 sites**, and **88 % of its
values are fractional**. `rate` is on 55 % of documents. These are temp basals — not an obscure
corner of the schema. Same root cause as BF-03 and fixed by the same change; listed separately
because "devicestatus has no coercion" undersells which fields are affected.

*Evidence*: [coercion drift](../60-research/query-coercion-drift-2026-09-14.md) §2 Tier 1.

### BF-12 · `entries.rawbg` is a stale walker entry

The walker coerces `rawbg`, which does not appear in the model at all — not once in **896,589
documents across 11 sites**. Harmless in itself, and worth recording because it shows the drift
running both ways: the hand-maintained list is not only missing entries, it carries dead ones.
It disappears when the table is generated.

### BF-13 · v3 paging loses documents when the sort chain ties

`parseSort` appends `identifier`, `created_at` and `date` as tiebreaks. When **all** of them tie
— documents with no `identifier`, sharing one `created_at` and one `date`, as a bulk import
stamps them — the order is not total, MongoDB's blocking sort is not stable among equal keys, and
each `skip` re-runs the query. Measured: **7 of 12 documents never returned, two returned three
times**, deterministically.

**Not fixable by indexing**: only an index matching the sort exactly gives a stable `IXSCAN`, and
the sort's leading key is client-chosen (`?sort=`). Under every index set Nightscout creates the
plan is `SORT <- COLLSCAN`.

**Fires on the default path** — with no `?sort=` the chain is just the three tiebreaks, so an
ordinary paged read is exposed.

*Fix*: append `sort._id = sortDirection`. `_id` is always present and always unique, so the order
becomes total. Verified: 0/12 lost. Carry the same rule into the seam's ordering translation, or
it reappears on PostgreSQL.

*Precondition is specific and should not be overstated*: all three of no-`identifier`,
tied `created_at`, tied `date`. Any one of them differing makes it safe.

**Sized against the 11-site corpus** (~1.5 M documents) and it is **concentrated in
`devicestatus`** — expected tie-group straddles per full paginated sweep: `devicestatus` median
**23.5** (max 64), against `entries` 0.01, `treatments` 0.02, `profile` 0.09. Uploaders write
`devicestatus` in bursts sharing one `created_at`/`date`. So a client paging `entries` will
typically lose nothing, and a tool paging `devicestatus` to reconstruct controller behaviour
loses records silently — on the collection replay fidelity depends on.

*Evidence*: [ordering and pagination](../60-research/seam-ordering-and-pagination-2026-09-14.md) §3.
**Reproduced synthetically against `mongod` 7.0.43, not against a live Nightscout** — confirm
before treating as settled.

### BF-16 · `food.hidden` has no type; the server filter and the client disagree

The `food` collection stores quick picks with a `hidden` flag, and the quick-pick list filters on
it. The two ends of that round trip do not agree on what the value is:

- `lib/server/food.js` `listquickpicks` queries `cmp('eq', 'hidden', 'false')` — the **string**
  `'false'`. Pre-existing upstream: released `cgm-remote-monitor` spells the same filter
  `{ 'hidden' : 'false' }` at `lib/server/food.js:146`, so this is not a regression from the
  storage-seam work.
- `lib/food/food.js:377` writes `foodquickpick[index].hidden = this.checked` — a **boolean**.
- `lib/food/food.js:69-73` `restoreBoolValue` reads it back as `record[key] === 'true'`, i.e. the
  client expects a **string** from storage.

It works today only by an accident of transport. The editor posts with
`$.ajax({ method: 'PUT', url: '/api/v1/food/', data: foodrec })` and **no `contentType`**, so
jQuery form-encodes; `wares.urlencodedParser` is `extended: true`, so every leaf arrives as a
string. `hidden: false` becomes `'false'`, which is what the filter matches and what
`restoreBoolValue` expects.

**The field therefore has no declared type. Its stored type is a property of the request, not of
the field.** A client that sends `application/json` with a real boolean stores a boolean, and
`{hidden: 'false'}` never matches it: that quick pick disappears from `/api/v1/food/quickpicks`
while remaining in `/api/v1/food/`. Nothing reports an error. The same holds for
`hideafteruse`.

*Fix*: give the field one type and accept both on read — match `$in: [false, 'false']` (or
normalise on write) rather than picking a side, since both spellings are already on disk
wherever a non-jQuery client has ever written. Do not "fix" the client to send JSON without
fixing the filter first; that is the change that breaks it.

**Secondary consequence, same root cause.** Form encoding stringifies *every* non-string value in
a food document, not just the booleans — `carbs`, `portion`, `fat`, `protein`, `energy`, `gi` and
`position`. `listquickpicks` sorts `{ position: 1 }`, and a lexicographic sort of `'0' … '10'`
orders `'10'` between `'1'` and `'2'`. A user with eleven or more visible quick picks sees them in
the wrong order. Unlike the `hidden` mismatch this one fires on the **shipping** path, with the
built-in editor and no third-party client involved.

*Not reproduced against a live instance.* Both readings are derived from the source and from
jQuery's and `qs`'s documented behaviour; the corpus contains no `food` collection to check
against — no snapshot ever fetched one.

*Recorded here rather than fixed* because the point is the class, not the instance: this is
exactly what a typed model exists to prevent. `specs/nsschema/food.model.json` therefore declares
`hidden` and `hideafteruse` as `["boolean", "string"]` with `type_undetermined`, and says why,
instead of papering over the ambiguity by choosing one.

*Evidence*: `specs/nsschema/food.model.json` (`type_undetermined_why`);
`tools/nsschema/code_model.py` `SOURCE_ASSERTIONS` anchors the string comparison so that fixing
it fails `make schema-code-drift` and forces the model to be revisited.

### BF-17 · A subject edit writes the access token into the database in plaintext

Found while deriving `specs/nsschema/auth_subjects.model.json`, by asking the narrow question
"which of these fields are actually stored?"

**`accessToken` is normally a derived value, not a stored one.** `lib/authorization/storage.js`
`reload()` recomputes it for every subject from the subject's `_id`, its `name` and the enclave
key. A stored subject document does not carry it.

Three steps put it there anyway, and each is reasonable on its own:

1. `lib/authorization/endpoints.js:38-42` — `GET /subjects` serves
   `pick(subject, ['_id', 'name', 'accessToken', 'roles'])`. Including the token is deliberate:
   the admin UI has to display it so an operator can copy it into a device.
2. `lib/admin_plugins/subjects.js:43` — the edit dialog sends the object it was given straight
   back, `data: subject`. It does not construct a payload of changed fields.
3. `lib/authorization/storage.js` `save` — `replaceOne({_id}, obj, {upsert: true})` replaces the
   document **wholesale** with the request body.

So changing a subject's name, or its roles, or its notes, writes the bearer token into the
subject's document as an ordinary string. Nothing warns, and the UI looks identical afterwards.

**Why this is worth more than the tidiness of it.** Derivation is what keeps the database from
being sufficient on its own: a reader of the stored documents alone — a backup, a replica, a
hosted MongoDB snapshot, a support export — cannot mint tokens without the enclave key. After any
subject edit, that separation is gone for that subject, and read access to the collection is read
access to a working credential. It converts a database-disclosure incident into a full API
compromise, silently and retroactively, for every subject an operator has ever edited.

Two related observations from the same reading, neither a separate entry:

- `accessTokenDigest` and `digest` are also derived and also not stored, but `GET /subjects` does
  not serve them, so they are not round-tripped. The exposure is `accessToken` alone.
- `auth_subjects.notes` has the mirror-image bug: it *is* stored, but `GET /subjects` does not
  return it, so the dialog populates its input from `undefined` and the wholesale PUT writes `''`
  back. **Any note an operator saves is erased by the next edit of that subject.**

*Fix*: the durable one is for `save` to write only the fields a subject document owns, rather
than the request body — which fixes the token and the notes together, and is the same shape of
fix as "don't replace a document with whatever a client sent". Stripping `accessToken` in the PUT
handler is the smaller change and closes the exposure; it leaves `notes` broken. Either way, a
deployment that has edited subjects already has tokens on disk, so a fix should also clear the
field on the next reload rather than only stopping new writes.

*Not reproduced against a live instance.* The chain is read from the released
`cgm-remote-monitor` source in `externals/cgm-remote-monitor-official`; every link is a literal
in that tree. **Not a regression from the storage-seam work** — the seam changed `save` from
`replaceOne` to a one-operation `bulkUpsert` with `mode: 'replace'`, which is the same wholesale
replacement.

*Evidence*: `specs/nsschema/auth_subjects.model.json` (`credential_warning`), which also records
that the field is `secret`/`credential` so no emitter or exporter can treat it as ordinary text.

## 3. How to use this register

1. **Anything found while doing multitenancy work that is also broken today gets an entry
   here**, at the time it is found, with its evidence link. The register is the mechanism that
   keeps that promise.
2. **Prefer landing these independently.** Each one is small, each ships to every current
   operator, and none needs a tenancy decision.
3. **Release-note the behaviour changes.** BF-02 and BF-03 change what queries return. That is
   the point, and it should arrive as a documented fix.
4. **Keep severities honest.** "Wrong answer with HTTP 200" is worse than "slow", and both are
   worse than "noisy". The table is sorted by that, not by effort.
