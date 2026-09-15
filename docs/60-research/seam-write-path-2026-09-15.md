# The write path across the seam — three divergences, and a vacuity trap in my own harness

Date: 2026-09-15 · Harness: [`tools/qc/write-arm.js`](../../tools/qc/write-arm.js)
Arms: real `mongod` 7 · real PostgreSQL 16, the emitted schema, both built by
`store.storageCollection()` · worktree detached at `239f8c25`

Closes the execution plan's unmeasured row **"Writes never measured — every arm is a read"**, and
the write methods the [T2.5 verification](t25-postgres-backend-verification-2026-09-15.md) listed
as untested.

**Result: 23 agree, 4 differ, 0 vacuous.** Each probe compares two things, because either can
agree while the other does not: the **return value** a caller branches on, and the **stored
state** read back afterwards.

---

## 1. Why the write path deserved this before the read path did

A divergent read returns a wrong answer once. A divergent write leaves the store wrong, and every
later read of it is correct about the wrong thing. This project's own history says the same: the
defects recorded during Phase 1 include *a synthesised `acknowledged`* and *a missing
non-upserting replace*, both on the write side.

---

## 2. BF-21 — `bulkUpsert` silently ignores the mode every caller asks for

`mongoCollection/modify.js` `bulkUpsert(col, ops, options)` takes an options bag whose `mode`
**defaults to `'replace'`** and dispatches to `replaceOne` or to `$set` accordingly.
`pgCollection/index.js` `bulkUpsert(ops)` **takes no options parameter at all** and always calls
`write(..., 'merge')`.

Measured, one stored document carrying `stale: 'was-here'`, upserted with a document that does
not carry it:

| call | mongod | postgres | |
|---|---|---|---|
| `bulkUpsert(ops)` (default) | `stale` removed | `stale` **survives** | differs |
| `bulkUpsert(ops, {mode:'merge'})` | `stale` survives | `stale` survives | agree |
| `bulkUpsert(ops, {mode:'replace'})` | `stale` removed | `stale` **survives** | **differs** |

The third row is the one that matters. **Every shipping caller passes `{ mode: 'replace' }`
explicitly** — `lib/server/activity.js:61`, `lib/server/activity.js:102`,
`lib/server/treatments.js:31`. They are asking for a replace, in writing, and on PostgreSQL the
argument reaches nothing.

The consequence is not a lost update but an **unremovable field**: any key a client deletes from a
treatment or activity document stays in the PostgreSQL row for good, and the two backends drift
further apart with every write. Nothing errors and nothing logs.

*Not yet live*: `entries` is the only collection with a PostgreSQL schema, and it has no
`bulkUpsert` caller. `activity` and `treatments` do. **The exposure arrives with T2.6** — the same
deadline as [BF-19](../30-design/nightscout-backfix-register.md).

## 3. BF-22 — `updateOne` with a dotted field stores two different documents

`updateOne(identifier, setFields)` on MongoDB becomes `$set`, where a dot is a **path**.
On PostgreSQL the merge treats the same string as a **literal key**:

```
setFields = { 'nested.leaf': 7 }
  mongod     …,"nested":{"leaf":7},…
  postgres   …,"nested.leaf":7,…
```

The PostgreSQL document now holds a key that no path lookup will ever find — not by the adapter's
own `doc #> '{nested,leaf}'`, not by a generated column, not by a client walking the object. It is
reachable only by asking for the literal string.

*Reachability*: `lib/api3/generic/patch/operation.js:85` passes the client's PATCH body to
`updateOne` after validation. So this is **client-reachable through `PATCH /api/v3/<col>/<id>`**,
subject to whatever that validation rejects — which this work did **not** audit, and which
therefore bounds the claim. The other caller,
`lib/api3/generic/delete/operation.js:86`, passes a fixed `{isValid, srvModified}` and is safe.

Note that MongoDB's behaviour is not obviously the right one either — a client sending
`{"nested.leaf": 7}` may well have meant a literal key. The defect is that the two backends
answer differently and neither refuses.

## 4. BF-23 — the duplicate-key error class leaks the backend through the seam

```
mongod     MongoServerError: E11000 duplicate key error collection: …
postgres   DatabaseError: duplicate key value violates unique constraint "entries_pkey"
```

Both refuse the duplicate, which is the part that matters. But the seam's purpose is that callers
above it do not see driver objects, and an error class is a driver object. `err.code === 11000` is
the standard MongoDB idiom for "already exists" and it would silently stop being true.

*Graded low on evidence*: no shipping caller branches on it — `grep` for `11000`, `E11000` and
`MongoServerError` across `lib/` returns nothing. It is recorded because the interface is
published and the next caller may.

---

## 5. What agreed, and it is most of the surface

`insertOne` (return and stored state), `replaceOne` (including that it does **not** upsert a
missing identifier, on either side), `updateOne` for ordinary fields and for a missing identifier,
`deleteOne`, `deleteMany(ast)`, `deleteMany` matching nothing, `deleteManyOr`, `bulkUpsert` when
inserting, `bulkUpsert([])`, and `bulkUpsert {mode:'merge'}`.

The three methods PostgreSQL declines — `insertMany`, `updateMany`, `replaceFiltered` — all throw,
and all **name themselves** in the message, which is what makes an unimplemented method a
deliberate refusal rather than a crash.

---

## 6. The vacuity trap this harness fell into, and how it was caught

The first run reported **23 agree, 3 differ** and was partly worthless.

The adapters address one document through `utils.filterForOne(identifier)`, which matches the
**`identifier` field** — falling back to `_id` only for a 24-character hex string. The fixtures
carried `_id` values and no `identifier`. So nothing matched, `replaceOne` fell through to an
insert, that insert raised a duplicate key on **both** engines, and every state comparison
afterwards "agreed" because neither side had done anything.

**The comparator's own non-vacuity check passed throughout**, because it only ever proved that the
comparator can tell two collections apart. It cannot prove that the probe *bit*.

The fix is `effect()`: every mutating probe records the state before and after and is reported
**VACUOUS** if neither engine moved. Re-run with identifiers and effect assertions: **0 vacuous**,
and a divergence appeared that the broken run had hidden — §3, `updateOne` with a dotted field,
which cannot show up in a run where `updateOne` never matches anything.

Two lessons, both already in this project's rules and both re-learned the hard way here: a
non-vacuity check on the *instrument* is not one on the *experiment*, and an "agree" from an
operation that did nothing is indistinguishable from an "agree" from an operation that worked.

---

## 7. Honest limits

- **One collection.** `entries` is the only one with a PostgreSQL schema, so BF-21's real callers
  (`activity`, `treatments`) could not be driven through their own code — the divergence is
  demonstrated on `entries` through the same adapter those callers use.
- **No concurrency.** Every probe is sequential. Lost updates, write skew and the behaviour of
  `bulkUpsert` under two writers are untouched, and RLS's transaction binding means the PostgreSQL
  side has isolation semantics the MongoDB side does not.
- **BF-22's reachability is bounded by a validation layer I did not audit.** `applyPatch` calls
  `validate(opCtx, doc, storageDoc)` first. If that rejects dotted keys the finding is latent
  rather than live, and nobody has checked.
- **No write-path performance figures.** The plan's unmeasured row is about correctness here; the
  cost side of "writes never measured" is still open.
- Return values were compared after canonicalising key order, which hides ordering differences
  that no JSON client can observe but a string comparison would report.

## 8. Reproduction

```sh
docker run -d --name write-mongo -p 27023:27017 mongo:7
docker run -d --name write-pg -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15439:5432 postgres:16-alpine
git worktree add --detach <path>/crm-write <commit>
cd tools/qc && WORKTREE=<path>/crm-write PGPASSWORD=… node write-arm.js
```

The harness writes, so it must not be pointed at a shared instance. It stores no credential and
exits `2` with instructions if `PGPASSWORD` is unset; the unprivileged per-run role comes from
`tests/support/postgres.js`, reused rather than re-implemented.
