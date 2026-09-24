# T2.3 — the nine operators in SQL, and what turning `re` on found

> **Snapshot — research as of 2026-09-14, measured against the `externals/work/crm-seam/` checkout (the doc names no commit), mongod 7.0.43, PostgreSQL 16.14. Status: current — tenancy research, not on a shipping path; §5's "mongod is flat" result is narrower than it reads (see the correction there). Current facts: [execution plan](../../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) T2.3; shipping `$regex` exposure: [backfix register](../../30-design/remedial/nightscout-backfix-register.md) BF-72.**

Date: 2026-09-14. Status: findings, for whoever lands the seam's PostgreSQL adapter.
**Verification only — no shipping code was changed by this work.** `externals/work/crm-seam/`
belongs to another branch and was read, never written.

| ref | document |
|---|---|
| **{P}** | [Multitenancy execution plan](../../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) — T2.3 |
| **{S}** | [T1.1 — the storage seam](../../30-design/tenancy/nightscout-storage-seam-interface-2026-09-14.md) — §8.5, §10.5 |
| **{3A}** | [Three-arm validation of the filter AST](seam-filter-ast-three-arm-validation-2026-09-14.md) |

**Tooling**: `tools/seam/validate.js` (mingo vs live PostgreSQL, randomised, now per-operator)
and `tools/qc/re-arms.js` (new — mingo vs mongod vs PostgreSQL, deterministic, regex only).
Both run against the shipping module, never a copy.

---

## 1. What T2.3 asked for, and what was actually being measured

> *Done*: ≥500 randomised fixtures **per operator**, zero disagreements with `mingo`; `re`
> explicitly bounded (pattern guard + timeout) since it is {M} §6.5's live exposure.

Three gaps between that and the harness as it stood:

1. **`re` was behind `WITH_RE`.** The default run validated eight of the nine. The operator the
   design documents single out as the live exposure was the one opt-out — and {3A} §5 records
   the regex arm as off for its runs too, so **no published number covered `re` at all**.
2. **There was no per-operator count.** 2000 iterations over nine operators drawn uniformly is
   not 500 per operator, and nothing reported which ones were thin.
3. **`re` was not bounded.** No pattern guard, no timeout.

All three are closed. The run is now operator-balanced by construction (a focus operator cycles
round-robin and is guaranteed to appear in the fixture), every fixture is attributed to the
operators it contains, blame for a failure is isolated to a single node before it is counted,
and the run exits non-zero if any operator came in under `MIN_PER_OP`.

## 2. Headline: eight operators are clean, `re` is not

```
5000 randomised filters, 300-document corpus, PostgreSQL 16.14, mingo 7.2.4

operator  fixtures  mismatches  oracle-declined
  eq          999           0                0
  ne         1045           0                0
  gt         1032           0                0
  gte        1025           0                0
  lt         1022           0                0
  lte        1040           0                0
  in         1010           0                0
  nin         981           0                0
  re         1029          54               69   plus 95 SQL errors
  exists     1052           0                0
```

Every operator clears 500. `exists` is filter.js's tenth, beyond v3's nine, and is included
because v1 sends it.

**`re` is the only operator that disagrees, and it fails in three separate ways.**

## 3. Three defects in `toSql`'s `re` branch

All three are in `externals/work/crm-seam/lib/storage/filter.js`, in new seam code rather than
in shipping Nightscout, so none of them belongs in the backfix register. All three are
same-type, well-typed filters — which matters, because {3A} §4's summary is that *"every
divergence found is gated on a type mismatch between the filter's value and the document's
field"*. **With the regex arm on, that is no longer true.** Defect 1 needs no type mismatch at
all.

### D-RE-1 · POSIX ARE's newline modes are not MongoDB's `m` and `s`

`toSql` passes the non-`i` flags through as a leading `(?ms)` group. PostgreSQL accepts the
letters, but they do not mean what they mean in PCRE, and the **default** differs too:

| Mongo flags | what PCRE does | what `toSql` emits | what ARE does |
|---|---|---|---|
| *(none)* | `.` stops at a newline; `^$` at string ends | bare pattern | **`.` crosses newlines** |
| `s` | `.` crosses newlines | `(?s)` | same — correct |
| `m` | `^$` at line boundaries | `(?m)` | same (`m` is ARE's `n`) — correct |
| `ms` | both | `(?ms)` | **`s` cancels `m`; `^$` stop matching at line boundaries** |

ARE does not have two independent flags; it has four newline modes — `p`, `n`, `s`, `w`. The
correct translation is a lookup, not a pass-through:

```
no flags -> (?p)     m -> (?n)     s -> (?s)     ms -> (?w)
```

Measured: 7 mismatches in 5000, every one of them a value containing a newline. The commonest
shape is a client sending `^.*$`, which is what "any value" looks like from a query string.

### D-RE-2 · jsonb renders non-strings as text, and text matches

`$regex` never matches a number, a boolean or a subdocument. `doc #>> '{noise}'` renders the
number `2` as the text `'2'`, which `~ '\d'` matches happily. 47 mismatches in 5000, all reading
`mongo 0 / sql 188` — the whole corpus on one side and nothing on the other.

This is {3A}'s class B, in the one operator where it is **silent rather than a cast error**:
every other operator casts and raises 22P02, so it is at least visible.

### D-RE-3 · `re` against a numeric generated column is a hard SQL error

`ref()` returns the generated column when one exists, and a `numeric` column has no `~`
operator:

```
{"op":"re","field":"sgv","value":"\\s","options":"ms"}
  -> operator does not exist: numeric ~ unknown
```

**95 of 5000 fixtures, or 1.9 %, failed this way** — and unlike D-RE-2 it is a 500, not a wrong
answer. It fires on `sgv` and `date`; `type` survives only because it happens to be `text`. Any
indexed numeric field gives a client a one-request way to error the endpoint, and the structural
allowlist does not help, because this is a well-formed filter using an allowed operator.

### The fix, and the evidence that it is the fix

One replacement in the `re` branch — always read the document, only match when the stored value
is a string, and translate the newline mode:

```js
const op = flags.includes('i') ? '~*' : '~';
const nl = flags.includes('m') ? (flags.includes('s') ? 'w' : 'n')
                               : (flags.includes('s') ? 's' : 'p');
const embedded = nl + flags.replace(/[ims]/g, '');
const pattern = `(?${embedded})${n.value}`;
const path = `'{${n.field.split('.').join(',')}}'`;
return `(jsonb_typeof(${jsonbCol}#>${path}) = 'string' AND ` +
  `(${jsonbCol}#>>${path}) ${op} ${param(pattern)})`;
```

Applied to a scratch copy and re-run through both harnesses (`FILTER_MODULE` exists for exactly
this), it takes the randomised run to **0 mismatches and 0 SQL errors across all ten operators**
and the deterministic three-arm table from 5 diverging rows to 0.

**Cost to weigh before landing it**: `re` on `type` stops using the generated column, so a regex
on an indexed text field becomes a jsonb read. The alternative — passing column *types* rather
than column *names* into `toSql` — is an interface change and is not proposed here.

## 4. What only a third arm could say: two divergences mingo hides

`re` is the one operator whose meaning comes from a regex **engine** rather than from the AST,
and there are three engines in play: V8 (mingo), PCRE2 (mongod), POSIX ARE (PostgreSQL). So
"mingo and Postgres agree" is a weaker statement here than anywhere else. `tools/qc/re-arms.js`
runs 21 deterministic probes through all three.

```
pattern                flags  mingo          mongod         postgres         verdict
"Loop$"                -      1,4            1,3,4          1,4              ORACLE MASKS IT
"^$"                   m      3,4,6          4,6            3,4,6            ORACLE MASKS IT
"^.*$"                 -      1,5,6,7        1,3,5,6,7      1,2,3,4,5,6,7,8  ALL THREE DIFFER
"[[:alpha:]]"          -      -              1,2,3,4,5,7    1,2,3,4,5,7      ORACLE WRONG
"Loop"                 x      NO FLAG        1,2,3,4        1,2,3,4          ORACLE WRONG
"^ Loop  # comment"    x      NO FLAG        1,2,3          1,2,3            ORACLE WRONG
```

(document 3 is `"Loop\n"`, document 6 is `""`, document 8 holds the number `42`)

The `^.*$` row is all three defects at once: PostgreSQL's extra documents are §3's D-RE-1 and
D-RE-2, and mongod's extra document 3 is the engine difference below. Applying §3's fix moves
that row to `ORACLE MASKS IT` alongside the other two rather than to `agree` — which is the
point of separating the two kinds of finding.

**ORACLE MASKS IT is the finding.** All three rows are the same root cause: **PCRE's `$` matches
before a trailing newline and neither V8's nor ARE's does.** MongoDB therefore returns a
document that PostgreSQL does not, *and mingo agrees with PostgreSQL* — so the mingo-vs-Postgres
differential reports 100 % agreement on a filter where the two real backends return different
data. No amount of running `validate.js` finds this.

That is a limit on T2.3's own done criterion, and it should be written into the plan: **"zero
disagreements with mingo" is not the same claim as "the backends agree"**, and for `re` the gap
between those two claims is real and measured. {3A} established mingo as a faithful oracle for
well-typed non-regex filters; that result does not extend to `re`.

**ORACLE WRONG** is the mirror image, and it is why two constructs are deliberately outside the
randomised corpus:

- **POSIX bracket expressions** (`[[:alpha:]]`): PCRE2 and ARE both implement them; V8 reads
  the same text as an ordinary character class. Generating them would make `validate.js` report
  a defect where the adapter is correct.
- **the `x` flag**: MongoDB honours it (it is in `RE_FLAGS`), V8 rejects it as invalid. This one
  *is* still generated — 69 fixtures in 5000 — and reported on its own line as
  `oracle could not evaluate`, so the number is visible rather than silently skipped.

### The allowed regex subset, as far as it has been measured

| portable across V8, PCRE2 and ARE | not portable |
|---|---|
| literals, `^` at the start | `$` at the end, when a value may end in a newline |
| `[A-Z]`, `[^aeiou]`, `\d` `\s` `\w` | `[[:alpha:]]` and the other POSIX classes (oracle only) |
| alternation, `(?:…)`, `{n,m}`, `+` `*` `?` | the `x` flag (oracle only) |
| the `i` flag, the `s` flag, the `m` flag | `^$` under `m`, against a value ending in a newline |
| the empty pattern | |

This is §8.5's "the allowed regex subset needs writing down", to the extent 21 probes can write
it down. Lookaround, backreferences and lazy quantifiers are **not** in either column: they were
not probed.

## 5. Bounding `re`: the guard matters, the timeout mostly does not

T2.3 asks for a pattern guard and a timeout. Both are in the harness now — `statement_timeout`
on the PostgreSQL side, and, because **a V8 RegExp cannot be interrupted from inside the process
running it**, a structural guard plus an after-the-fact elapsed-time check on the JavaScript
side. The guard rejects a pattern over `RE_MAX_LEN` and a quantified group that is itself
quantified.

The measurement underneath, from `node validate.js --bound-probe` and `re-arms.js`:

```
pattern "(a+)+$" — 6 characters, so validate() accepts it

   n   mingo (V8)    mongod (PCRE2)   postgres (ARE)
  16       3.7 ms          4.2 ms           0.6 ms
  20      10.8 ms          2.8 ms           0.5 ms
  24     173.5 ms          3.2 ms           0.6 ms
  32      not run          2.6 ms           0.4 ms
  48      not run          2.6 ms           0.4 ms
```

V8 doubles every two characters (11.3 s at n=30, measured once; `(a|a?)+$` at n=32 did not
return at all). **mongod 7.0.43 and PostgreSQL 16 are flat**, and stay flat for `(a|aa)+$`,
`(a|a?)+$` and `^(a+)+b$` up to n=48.

Two things follow, and the second is a correction to a premise the plan carries:

1. **`RE_MAX_LEN` is a bound on the pattern, not on the work.** Six characters is enough.
2. **On this family, the catastrophic-backtracking exposure is the JavaScript arm's, not either
   database's.** PCRE2 possessifies these patterns and enforces a match limit; ARE does not
   backtrack this way at all. {M} §6.5's ReDoS framing is the right worry pointed at the wrong
   tier — it is live for anything that evaluates a filter **in the Node process**, which is this
   harness and any future in-process filtering, and not for mongod as measured.

[2026-09-22: the flat mongod columns hold only for the textbook family measured here, which PCRE2 optimises; they do not show that mongod's `$regex` is safe. Register **BF-72** (open, live on 15.0.8 and `dev`, no fix): a caller-supplied unbounded `$regex` on the shipping v1 API can cost minutes of database CPU, without credentials on a default install. Mechanism only here.]

What remains a genuine database exposure is the other half of the same problem, which nothing
here measures: **an unanchored regex is a full collection scan**, and that cost scales with the
document count, not with the pattern.

## 6. Non-vacuity

A differential that has never failed is not yet evidence. Each break below was applied to a
scratch copy — the patched module, whose baseline is 0 mismatches, so every number is a clean
delta — and reverted immediately.

| break | mismatches / 5000 | blamed operator | sample reading |
|---|---|---|---|
| `gt` mapped to `<` in `SQL_OP` | **736** | `gt` | `mongo 51 / sql 201`, `mongo 204 / sql 67` |
| the `i` flag ignored (always `~`) | **37** | `re` | `mongo 115 / sql 86` |
| `~` and `~*` swapped | **106** | `re` | `mongo 28 / sql 57`, `mongo 115 / sql 86` |
| embedded flag group dropped | **14** | `re` | `mongo 197 / sql 255`, classed `re-newline` |
| `nin`'s `IS NULL` guard removed ({S} §8.3's fix) | **588** | `nin` | `mongo 220 / sql 160` |
| `exists` reads the generated column ({S} §8.3's other fix) | **188** | `exists` | `mongo 206 / sql 188` |
| the `jsonb_typeof = 'string'` guard removed | **71** | `re` | `mongo 0 / sql 188`, classed `re-nonstring` |

Blame landed on exactly one operator in all seven, which is the isolation step working: without
it, a broken `gt` inside a three-node `$and` would have charged three operators.

Two more, because the new accounting needs its own check:

- **under-sampling**: at 1000 iterations every operator lands near 200 and the run exits **1**
  with `FAIL: under-sampled operators`. The criterion is not decorative.
- **the pattern guard**: `--bound-probe` prints the guard rejecting both a 129-character pattern
  and `(a+)+$`, so it is visibly not a no-op.

## 7. What was not verified

- **`re` was not run against mongod at randomised scale.** `re-arms.js` is 21 deterministic
  probes; `three-arm.js`'s regex arm is still off and its corpus still has no newline-bearing
  values. The three ORACLE-MASKS-IT rows are therefore known to exist but **not sized**.
- **Array-valued fields are in no corpus, here or in {3A}.** MongoDB matches an array element by
  element for every operator; jsonb does not. A quick probe put 28 of 120 (pattern, flags) pairs
  in disagreement on a single array-valued field, all of them `onlyMongo`. That is a storage-shape
  decision nobody has taken, not a regex question, and it is the largest unexamined gap the
  corpus has.
- **Cross-type values are deliberately absent** from this corpus; that is {3A} §3's territory and
  its recommendations are unchanged by this work, except that D-RE-2 adds a silent instance of
  class B to the list.
- **One PostgreSQL (16.14) and one mongod (7.0.43)**, one collection shape, 300 documents. Regex
  semantics are stable across versions, but engine *performance* is not, and §5's flat columns
  are one build of each.
- **Lookaround, backreferences, lazy quantifiers and Unicode property escapes** were not probed
  in any engine. They are the constructs most likely to diverge and least likely to appear in
  real v1 traffic; the T2.4 census is where that question should be settled.
- **No sort, limit, skip or projection**, and **no tenant predicate** — filters only, as before.

## 8. Reproducing

```bash
export PGPASSWORD=...        # throwaway, for the local POC container only
docker run -d --name seampg -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15434:5432 postgres:16-alpine
docker run -d --name seam-qc-mongo --ulimit nofile=64000:64000 -p 27019:27017 mongo:7

cd tools/seam && npm install
node validate.js 5000          # §2, per-operator
node validate.js --bound-probe # §5

cd ../qc && npm install
node re-arms.js                # §4 and the three-arm half of §5
```

Both tools refuse to run rather than carry a default password, and take `PG_URL` / `MONGO_URL`
if the containers are elsewhere. `FILTER_MODULE` points either at a different checkout or at a
scratch copy, which is how §3's fix and §6's breaks were measured without touching
`externals/work/crm-seam/`.
