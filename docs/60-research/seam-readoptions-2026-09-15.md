# `readOptions` across the seam — a bound that stops holding exactly where it matters

Date: 2026-09-15 · Harness: [`tools/qc/readoptions-arm.js`](../../tools/qc/readoptions-arm.js)
Arms: mongodb driver **5.9.2 / 6.21.0 / 7.6.0** against real `mongod` 7 · real PostgreSQL 16

Last of the four options `findFiltered` hands the driver. `sort` was covered by
[ordering and pagination](seam-ordering-and-pagination-2026-09-14.md); `limit` and `projection`
by [limit and projection](seam-limit-and-projection-2026-09-14.md). With this the options bag is
fully measured.

`readOptions` is the odd one out: it never carries client input. It is one frozen constant —
`lib/storage/mongo-read-options.js` = `Object.freeze({batchSize: 1000})` — passed at thirteen
call sites and nowhere else. "Do the backends disagree" is therefore the wrong question. Three
better ones, and the second produced a defect.

---

## 1. Is the constant load-bearing? Yes, on driver 7 only

The constant exists because of a claim written in its own comment:

> Driver 7 no longer caps getMore batches at 1,000 documents by default.

That is a testable claim about specific driver versions, so the harness installs all three and
watches the wire with command monitoring rather than inferring batching from timing:

| driver | `find({})` | `find({}, READ_OPTIONS)` |
|---|---|---|
| **5.9.2** (what `origin/dev` ships) | `batchSize=1000` ×40 | `1000` ×40 |
| 6.21.0 | `batchSize=1000` ×40 | `1000` ×40 |
| **7.6.0** (what the modernization branch ships) | **no `batchSize` sent** ×3 | `1000` ×40 |

**The claim is correct.** Drivers 5 and 6 send `batchSize=1000` unprompted; driver 7 sends none
and lets the server fill each batch to the 16 MB wire limit — 40,000 documents in three round
trips instead of forty. So `mongo-read-options.js` is load-bearing on driver 7 and a no-op on 5
and 6. It is not cargo, and it must be carried across the seam.

---

## 2. The bound is abandoned on the one path that needs it most

Same constant, with `.limit(0)` also set:

| driver | `getMore` batch sizes requested | |
|---|---|---|
| 5.9.2 | `1000` ×40 | holds |
| 6.21.0 | `1000` ×40 | holds |
| **7.6.0** | **`1000 2000 4000 8000 16000 32000`** | **bound abandoned** |

On driver 7 the requested batch **doubles every `getMore`** until the wire limit stops it. The
explicit bound is honoured for the first batch and then discarded.

### 2.1 That path is BF-14's path, and only BF-14's path

`findFiltered` calls `.limit()` only when the caller supplied one, and API v1 supplies

```js
limit: opts && opts.count ? parseInt(opts.count) : undefined
```

So `.limit(0)` is reached by exactly two inputs: **`?count=0`**, and any unparseable `?count=`
(`NaN` → `toSafeInt(NaN, 0)` → `0`). Those are
[BF-14](../30-design/nightscout-backfix-register.md). An absent `?count=` yields `undefined`,
`.limit()` is never called, and the bound holds.

The two defects therefore **compound on the same request**. `?count=0` does not merely remove the
document limit — on driver 7 it also dismantles the memory bound that exists to make a large read
survivable. Against a 900,000-document `entries` collection, the batch the server is asked to
build grows without the operator having asked for anything.

### 2.2 It is not shipped, and that is the finding's real value

The register's first admission criterion is "affects single-tenant self-hosters running the
**current release**". This one does not:

- `origin/dev` ships `mongodb ^5.9.2` and has **no** `lib/storage/mongo-read-options.js`.
- Driver 7 and the constant both arrive on `chore/nightscout-modernization` (`b8fd24c6`,
  *"prepare MongoDB 7 migration with bounded read batches"*).

So this is a defect in an **unreleased migration branch**, caught before release. Recorded as
**BF-16** in a separate pre-release section of the register rather than by quietly widening the
register's own criterion.

The fix is not in this file. Fixing BF-14 — validating `count` the way v3's `parseLimit` already
does — makes `.limit(0)` unreachable through the API and closes BF-16 as a side effect. BF-16 is
recorded anyway because `findFiltered` is a *published interface*: any future caller passing
`limit: 0` re-opens it, and `toSafeInt(o.limit, 0)` makes `0` the fallback for unparseable input.

---

## 3. The SQL analogue is an architecture choice, not a translation

`batchSize` is one word in a Mongo `find()`. There is no word for it in SQL. The equivalent is a
server-side cursor:

| | rows | retained heap |
|---|---:|---:|
| `node-postgres` default (`pg.query`) | 40,000 | **+39.2 MiB** |
| `BEGIN; DECLARE …; FETCH 1000; COMMIT` | 40,000 | **+0.0 MiB** |

Reported as two numbers rather than a ratio: the cursor arm retains essentially nothing, so a
ratio is a division by noise that would print a precise-looking *915×* meaning only "one of these
is about zero".

The bound only holds **if the caller consumes each batch instead of concatenating them**.
`findFiltered` ends in `toArray()`. A literal port therefore concatenates, the bound the constant
exists to provide is lost, and the code still reads as though it were there — the same shape of
silent loss as `sort` crossing the seam as a driver object.

**Implication for T2.5**: `readOptions` cannot be translated. Either the interface grows a
streaming read (`findFilteredStream`, or an async iterator) and the bulk callers use it, or the
PostgreSQL backend materialises whole result sets and the `batchSize` constant becomes a
MongoDB-only comment describing a property the system no longer has.

---

## 4. Honest limits

- **`.limit(0)`'s doubling was not traced to a line in the driver.** It is measured on the wire
  across three versions, which establishes *that* it happens and *where* it changed, not *why*.
  Someone landing the fix upstream would want the cause; the backfix here does not depend on it.
- **Peak memory was measured first and thrown away.** Sampling peak heap gave a 0.9× ratio — GC
  noise dressed as a result. §3 reports retained heap after a forced collection instead, which is
  the property the seam has to preserve. The discarded attempt is recorded in the harness header
  so nobody repeats it.
- **The 16 MB wire limit is the only thing that stops the doubling**, and the harness did not
  measure what happens when documents are large enough for 32,000 of them to exceed it well
  before the sixth `getMore`. The doubling is established; its ceiling under realistic
  `devicestatus` documents is not.
- Documents here are a uniform ~1 KB. Real collections are not, and batch *count* is a weaker
  proxy for memory than batch *bytes*.

## 5. Reproduction

```sh
docker run -d --name seam-qc-mongo -p 27019:27017 mongo:7
docker run -d --name seampg -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15434:5432 postgres:16-alpine
cd tools/qc && npm install
PGPASSWORD=… node --expose-gc readoptions-arm.js
```

`--expose-gc` is required; §3 measures retained heap and the harness refuses to run without it.
The three drivers are npm aliases (`mongodb5`, `mongodb`, `mongodb7`) so all coexist; a missing
one is skipped rather than substituted, because substituting answers a version question with the
wrong version. No credential is stored in the harness.
