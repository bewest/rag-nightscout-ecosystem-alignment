# Three-arm validation of the storage seam's filter AST: closing §8.5

> ## Superseded in part, 2026-09-15 — read this first
>
> Two corrections, both from
> [verifying the T2.5 backend](t25-postgres-backend-verification-2026-09-15.md) against the
> shipping adapter rather than against a harness-authored PostgreSQL arm.
>
> **1. The four divergence classes are closed.** This document reports classes A–D open, with
> mongod-vs-postgres at 2694/2802 (96.15 %) and 198/3000 `22P02` runtime errors. Re-run with the
> same generator, seed and 12 % cross-type injection against the shipped `lib/storage/filter.js`:
> **3000/3000, zero disagreements, zero arm errors.** A and C are closed by a `nullMatch()` helper
> reading `doc #> '{path}'` — where an absent key is SQL NULL and an explicit null is jsonb
> `'null'` — rather than by the `IS NOT DISTINCT FROM` mirror predicted here; B and D by
> `typedRef()`'s `CASE WHEN jsonb_typeof(…) = '<type>'`, which reproduces BSON type bracketing and
> makes the cast total.
>
> **2. This run never exercised the generated-column branch, and said nothing about it.**
> `toSql` takes `columns` as either a list of names or a **map** of name → JSON type. This harness
> passed a list, and with the type unknown every comparison falls back to the jsonb path. So the
> published figure describes the jsonb path only. The re-run passes the real map from
> `lib/storage/postgres/generated/index.json`, and the column branch agrees too — but that is new
> evidence, not evidence this document ever had.
>
> The method stands and the numbers below are what they were. They measured a strawman adapter, as
> §4 of [limit and projection](seam-limit-and-projection-2026-09-14.md) says of its own.


Date: 2026-09-14. Status: findings, for the maintainer and for whoever finishes T1.2.
**Verification only — no shipping code was changed by this work.**

Closes the open item the seam interface document records in its own §8.5:

> **mingo is a reimplementation of MongoDB's query language, not MongoDB.** Agreement is
> strong evidence about the AST; it is not proof about MongoDB. Re-running the same harness
> against a real `mongod` is a small change to `validate.js` and should happen before T1.2
> lands.

| ref | document |
|---|---|
| **{S}** | [T1.1 — the storage seam: interface and call-site classification](../30-design/nightscout-storage-seam-interface-2026-09-14.md) |
| **{P}** | [Multitenancy execution plan](../30-design/nightscout-multitenancy-execution-plan-2026-09-14.md) |

**Tooling**: `tools/qc/three-arm.js` (randomised, three arms) and `tools/qc/classes.js`
(deterministic minimal reproductions). Both validate the **shipping** module at
`lib/storage/filter.js` in the seam worktree, never a copy.

---

## 1. What was measured, and why a third arm

`tools/seam/validate.js` runs one AST two ways — through `mingo`, and through a real
PostgreSQL 16 — and compares result sets. That answers *"does the seam hold?"* only if mingo
tells the truth about MongoDB. Nothing had tested that, and under **D4 MongoDB is permanent**,
so "what mingo says" is not a substitute for "what self-hosters' databases do".

Three arms, so all three pairwise comparisons are available:

| comparison | question it answers |
|---|---|
| **mingo vs mongod** | Does the *oracle* tell the truth? — validates the **method** |
| **mongod vs postgres** | Does the *seam* hold? — validates the **claim** |
| mingo vs postgres | reproduces `validate.js` — regression check |

The first cannot be obtained any other way, and it is not only about this module: the same
oracle underwrites PR #8733's 636 fixtures. If mingo were unfaithful, every result measured
through it would inherit the doubt.

**Independence.** The fixture corpus is deliberately *identical* to `validate.js`'s, so numbers
are comparable. The filter **generator** is deliberately *not*: different seed, deeper nesting,
empty groups, and — the part that mattered — values drawn from the **wrong type for the field**
12 % of the time. A generator shared between a check and the thing it checks cannot find a bug
that lives in the generator.

## 2. Headline: the published result reproduces, and the AST is correct where it was measured

With the generator restricted to **same-type values**, which is the domain `validate.js`
generates:

```
CROSSTYPE=0, 3000 randomised filters, mongod 7.0.43 + PostgreSQL 16.14

OK    mingo-vs-mongod      3000/3000  (100.00%)  disagreements 0
OK    mongod-vs-postgres   3000/3000  (100.00%)  disagreements 0
OK    mingo-vs-postgres    3000/3000  (100.00%)  disagreements 0
```

**Two things follow, and both are good news.**

1. **{S} §8.3's 3000/3000 stands, and now stands against a real database.** The `nin` and
   `exists` fixes it describes are confirmed against `mongod`, not only against mingo.
2. **mingo is a faithful oracle for well-typed filters.** The method the programme has leaned
   on four times is sound within the domain it was used in. This is the reassurance §8.5 asked
   for.

**This is the number to quote for the AST.** The divergences in §3 are all outside that domain,
and the difference between the two runs is the *generator*, not a regression.

## 3. Turning on cross-type values: four divergence classes

```
CROSSTYPE=0.12, 3000 randomised filters

FAIL  mingo-vs-mongod      2794/2802  (99.71%)  disagreements 8
FAIL  mongod-vs-postgres   2694/2802  (96.15%)  disagreements 108
FAIL  mingo-vs-postgres    2701/2802  (96.40%)  disagreements 101
      arm errors 198/3000 — all of them PostgreSQL raising at runtime
```

`tools/qc/classes.js` reduces every one to a deterministic probe over four documents:

```
corpus: {_id:1, noise:2, device:'Loop'}   {_id:2, noise:null, device:'Loop'}
        {_id:3, device:'Loop'}            {_id:4, noise:2, device:'xDrip'}
generated columns: sgv, date, type        (noise and device are jsonb-only)

class  probe                                                  mingo    mongod   postgres    verdict
-----  -----------------------------------------------------  -------  -------  ---------   ----------------
A      lte against null, field absent                         2        2,3      -           BACKENDS DIVERGE
A      gte against null, field absent                         2        2,3      -           BACKENDS DIVERGE
A      eq  against null, field absent                         2,3      2,3      -           BACKENDS DIVERGE
A      ne  against null  — a shape §8.4 lists as COVERED      1,4      1,4      1,4         agree
B      lt with a STRING bound on a numeric field              -        -        1,4         BACKENDS DIVERGE
B      lt STRING bound where lexical and numeric order agree  -        -        -           agree
C      in containing null, field absent                       1,2,3,4  1,2,3,4  1,4         BACKENDS DIVERGE
D      numeric bound against a field holding text             -        -        ERR 22P02   BACKENDS DIVERGE
D      boolean bound on a jsonb field                         -        -        ERR 22P02   BACKENDS DIVERGE
```

### Class A — null comparisons, and an asymmetry that names the fix

MongoDB's comparison against `null` matches a **missing** field as well as an explicitly-null
one. `toSql` emits `doc#>>'{noise}' = $1` with `$1 = NULL`, which is never true, so
**Postgres returns nothing where MongoDB returns rows.**

**`ne` is already correct and `eq` is not, and the reason is instructive.** `toSql` special-cases
`ne` as `IS DISTINCT FROM` — the {S} §8.3 work found that gap and fixed it. `eq` never got the
mirror image. So the fix is exactly: **`eq` against a null value must emit
`IS NOT DISTINCT FROM`**, and the ordered comparisons need the same missing-field treatment.

That `ne null` *passes* matters: it is one of the ten real API v1 shapes {S} §8.4 checks, so the
coverage claim there is not undermined. The unfixed siblings are the ones no v1 shape happened
to exercise.

**Also in class A: the only place mingo is unfaithful to MongoDB.** For `$lte: null` and
`$gte: null` against an absent field, `mongod` matches and **mingo does not** — the 8
disagreements in the run above. It is a narrow, nameable infidelity rather than a general
unreliability, but it is real, and anything measured through mingo that leans on ordered
comparison against null now carries an asterisk.

### Class B — cross-type comparison diverges *silently*

MongoDB compares **only within a BSON type**: a numeric field never matches a string bound.
The SQL adapter picks its branch from the *bound's* JavaScript type, so a string bound takes the
text branch and compares lexically. `noise < '3'` returns **nothing on MongoDB and rows 1,4 on
Postgres**.

Silence is what makes this the worst of the four. There is no error; the same query returns
different data depending on which backend a deployment runs, which is precisely the property
D4 makes permanent.

The second probe is included so the class is not overstated: when lexical and numeric ordering
happen to agree, so do the backends. The divergence is data-dependent, which makes it harder to
catch, not rarer.

### Class C — `in` containing null

`$in: [null, 2]` matches a missing field on MongoDB; `IN (NULL, 2)` does not on Postgres.
**Exactly the three-valued-logic gap `nin` already needed and got** ({S} §8.3 finding 1) — the
fix was applied to `nin` and not to `in`, for the same reason `eq` was missed: the randomised
generator never put a null inside an `in` list.

### Class D — Postgres raises where MongoDB returns empty

`(doc#>>'{device}')::numeric` against `'Loop'` raises **22P02 `invalid input syntax for type
numeric`** *at runtime*, on the row, not at plan time. **198 of 3000 generated filters (6.6 %)
hit this.**

Under the shipping API this is the difference between **an empty 200** and **a 500**. It is also
reachable by any client that can send a query string, which makes it an availability concern as
well as a correctness one — and note the AST's structural allowlist does not help here, because
these are *well-formed* filters using *allowed* operators.

## 4. What this means for the plan

**The AST and both adapters are correct for well-typed filters, and every divergence found is
gated on a type mismatch between the filter's value and the document's field.**

That lands directly on a task {P} already has:

> **T0.5 · Schema-driven query type coercion.** Emit a coercion table from
> `specs/nsschema/*.model.json` … and drive `lib/server/query.js`'s walker from it.

**T0.5 is not only a v1 bug fix. It is a precondition for the seam's backend-equivalence
claim**, and that is a stronger argument for it than the one currently written down. Classes B
and D largely disappear once values arrive correctly typed.

**But coercion is not sufficient, and the residue needs adapter fixes:**

| class | fixed by T0.5? | why |
|---|---|---|
| **A** null comparisons | **no** | `null` is a legitimate value, not a coercion failure. v1 emits `$ne null` today. Needs `toSql`. |
| **C** `in` with null | **no** | same |
| **B** cross-type | mostly | coercion has no entry for fields with no schema, and a client can always send a mistyped value |
| **D** cast errors | mostly | same residue — and the residue is a 500, so it needs a guard regardless |

**Recommended, in order:**

1. **Fix `eq`/`in` null handling in `toSql`** — mirrors the `ne`/`nin` fixes already made, small
   and self-contained. Add the class A and C probes as regression tests.
2. **Make the cast branch total.** A cast that can raise on data must not be emitted bare;
   the shapes are known (`::numeric`, `::boolean` over jsonb text). Whatever the chosen
   construct, class D must become an empty result rather than a 500, because that is what the
   other backend does.
3. **Decide class B deliberately and write it down.** Either the seam promises MongoDB's
   type-bracketing semantics on both backends, or it promises coerced input and rejects
   mistyped bounds at the boundary. Both are defensible; leaving it undecided means the
   behaviour is whichever backend the deployment happens to run.
4. **Raise the cross-type rate in `tools/seam/validate.js`.** Its generator cannot produce
   these shapes, so it will keep reporting 100 %.

## 5. Honest limits

- **The 96 % figures are not comparable to {S} §8.3's 100 %** and must not be quoted as a
  regression. Different generator. The comparable figure is §2's **3000/3000**.
- **12 % cross-type injection is a stress rate, not a traffic model.** Nothing here measures how
  often real clients send a mistyped bound. The `count` endpoint bug in {S} §4.3.1 shows the
  rate is not zero, and that is all this establishes.
- **One `mongod` version (7.0.43), standalone, one collection shape.** Type-bracketing is
  long-standing MongoDB semantics, but no other version was tested.
- **Sort, limit, skip and projection are still not covered** — filters only, same as before.
- **The regex arm was off** for these runs. {S} §8.5's note that the allowed regex subset needs
  writing down is still open.
- **No tenant predicate is in any of these filters**, so this says nothing about RLS isolation.

## 6. Reproducing

```bash
export PGPASSWORD=...        # throwaway, for the local POC container only
docker run -d --name seam-qc-mongo --ulimit nofile=64000:64000 -p 27019:27017 mongo:7
docker run -d --name seampg -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15434:5432 postgres:16-alpine
cd tools/qc && npm install

node classes.js                      # the deterministic probe table in §3
CROSSTYPE=0 node three-arm.js 3000   # §2 — all three arms agree
node three-arm.js 3000               # §3 — the four classes
```

Both scripts refuse to run rather than carry a default password, and take `PG_URL` / `MONGO_URL`
if the containers are elsewhere.

`tools/qc` has its own dependency tree on purpose: the thing being checked and the thing doing
the checking should not share one.
