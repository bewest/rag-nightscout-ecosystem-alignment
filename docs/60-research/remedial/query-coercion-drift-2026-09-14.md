# The query-coercion table, emitted — and the 158 places the shipping walkers disagree

> **Snapshot, 2026-09-14, walkers transcribed from `chore/nightscout-modernization` `0a4109f6`. Historical: the coercion fix (T0.5: BF-02, BF-03, BF-11, BF-32, BF-40) is merged into `dev` as PR #8737, not released; the drift counts are as of 2026-09-14. Contributor-facing. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**

Date: 2026-09-14. Status: findings + tooling. Task **T0.5** of the
[execution plan](../../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md).
**No shipping code changed** — this builds the generator and measures the gap.

**Tooling**: `tools/nsschema/emit/coercion_emit.py` (the sixth emitter),
`tools/nsschema/test_coercion.py` (19 tests), `make schema-emit`,
`make schema-coercion-drift`, `make schema-test`.
**Output**: `specs/generated/coercion/*.coercion.json`.

---

## 1. What the emitter does, and the one design decision in it

`lib/server/query.js` turns an HTTP query string into a filter, and everything in a query string
arrives as **text**. Deciding that `find[sgv][$gte]=120` means the number `120` needs the field's
type, and today's answer is a hand-maintained `walker` dict per collection, derived from nothing.

The emitter derives it from `specs/nsschema/*.model.json` instead, and **names a type, never a
coercion function**. That is the decision worth stating:

1. **It must serve two backends.** D4 keeps MongoDB permanent for single-tenant while D3 puts the
   hosted service on PostgreSQL, so coercion sits *above* the storage seam and feeds both. A
   table of `parseInt` references would be a table of one backend's opinions.
2. **The consumer owns the edge cases.** `number` and `integer` are facts about the field;
   whether a malformed value becomes `NaN`, a 400, or is dropped is a policy decision for the
   query layer, and baking it in here would hide it.

`nullable` is emitted alongside, and it is not decoration —
[three-arm validation](../tenancy/seam-filter-ast-three-arm-validation-2026-09-14.md) §3 found that
comparisons against `null` are exactly where the two backends diverge, so the query layer has to
be able to tell a legitimate null from a failed coercion.

| collection | coercible leaves | left uncoerced |
|---|---:|---:|
| entries | 31 | 0 |
| treatments | 56 | 2 |
| devicestatus | 141 | 11 |
| profile | 22 | 5 |
| **food, activity, settings, auth_\*** | **no model at all** | — |

The last row is plan **T2.2** and it is a hard floor: those collections cannot be coerced until
they have models, and `auth_subjects`/`auth_roles` must be read out of
`lib/authorization/storage.js` because no evidence-derived model exists.

## 2. The drift: 158 disagreements

```
make schema-coercion-drift

by kind: UNDER 147, OVER 8, ORPHAN 1, no model 2
         devicestatus 98 · treatments 25 · entries 14 · profile 10
```

**These are not 158 equivalent bugs, and reporting them as one number would be the same mistake
the walker makes.** Graded by whether the corpus says anyone can actually hit them:

### Tier 1 — wrong answers on fields people really query

The model's `number` vs `integer` split comes from **observed values**, so the corpus says how
much each one matters.

| field | walker | model | observed | consequence |
|---|---|---|---|---|
| `treatments.insulin` | `parseInt` | `number` | **142,360 fractional** vs 2,791 integer, 11 sites | **OVER** — `insulin >= 1.5` becomes `>= 1` |
| `treatments.carbs` | `parseInt` | `number` | 5,029 fractional vs 10,656 integer, 11 sites | **OVER** — same |
| `treatments.duration` | **none** | `number` | **297,232 fractional** vs 39,116 integer, 91 % of docs | **UNDER** — matches nothing |
| `treatments.rate` | **none** | `number` | 102,465 fractional vs 100,212 integer, 55 % of docs | **UNDER** — matches nothing |
| `treatments.amount` | **none** | `number` | 71,320 fractional, 46 % of docs, 10 sites | **UNDER** — matches nothing |
| `treatments.absolute`, `percent`, `targetTop`, `targetBottom`, … | **none** | `number` | — | **UNDER** — matches nothing |

**`treatments.duration` is the one to look at twice.** It is present on 91 % of treatment
documents across 10 sites, 88 % of its values are fractional, and it has **no walker entry at
all** — so `find[duration][$gte]=30` returns an empty list and HTTP 200. Temp basal duration is
not an obscure field.

**And `insulin` is the one with review consequences.** 98 % of its non-null values are
fractional, so `parseInt` on the *bound* is not a rounding nicety: a query for boluses of at
least 1.5 units returns boluses of 1.0 units, silently. Anyone using the API to review what was
delivered — a report tool, a data export, a caregiver looking back at a day — gets records that
do not answer the question they asked. That is a data-correctness defect, and nothing in it is
advice about dosing; the point is narrower and worse, which is that **the data does not match
the query**. It warrants a release note rather than a silent fix, and anyone acting on such a
review should be doing so with their care team.

### Tier 2 — correct to fix, but no measured effect today

| field | walker | model | observed |
|---|---|---|---|
| `entries.sgv` | `parseInt` | `number` | **895,418 integer, 0 fractional** |
| `entries.filtered`, `unfiltered` | `parseInt` | `number` | 116,054 integer, 0 fractional |
| `entries.mbg` | `parseInt` | `number` | 1,169 integer, **2** fractional |
| `entries.date` | `parseInt` | `number` | 551,257 fractional — but sub-millisecond |

The model calls these `number` because JSON has no integer type and the census records what it
saw; for `sgv` it saw integers only. **Truncating an `sgv` bound has no observable effect on this
corpus**, and claiming otherwise would be overstating the finding. `date` is genuinely
fractional but the truncated part is sub-millisecond. Fix them for consistency, not because
anyone is being harmed.

### Tier 3 — declared but never observed

`isValid` (entries, treatments, devicestatus, profile) and similar spec-declared fields have
`observed: none` in the corpus. The drift is real against the spec and unmeasurable against
reality. Listed, not ranked.

### The orphan

`entries.rawbg` is coerced by the walker and **does not appear in the model at all** — not in
896,589 documents across 11 sites. The walker is carrying a field the ecosystem stopped writing,
which is the drift symptom pointing the other way: the hand-maintained list is not only missing
entries, it holds stale ones.

## 3. What this changes about T0.5

**T0.5 gets bigger in value and no bigger in work.** Its "done" criteria are met by what is
here plus the wiring:

- ✅ *Emit a coercion table from `specs/nsschema/*.model.json` (sixth emitter)* — done.
- ✅ *A test asserts the emitted table matches the model for every collection* — done, 19 tests,
  including that no leaf is silently dropped and that `nullable` is carried.
- ⬜ *Drive `lib/server/query.js`'s walker from it* — **not done; this is `cgm-remote-monitor`
  work** and is the remaining half.
- ⬜ *Release-note the behaviour change.*

**It also acquired a second justification.** T0.5 was written as a v1 bug fix. Three-arm
validation showed every measured backend divergence is gated on a type mismatch, so **T0.5 is
also a precondition for the seam's backend-equivalence claim** — with correctly-typed values all
three arms agree 3000/3000.

**But coercion is not sufficient**, and this measurement sharpens why: `nullable` is on 2 of
treatments' 56 leaves including `insulin` and `carbs`, so null-valued bounds on exactly the
Tier-1 fields are legitimate input that coercion will pass through unchanged — straight into
three-arm's class A and C, which need `toSql` fixes regardless.

## 4. Honest limits

- **The corpus is Loop-dominant.** Observed-type counts describe *this* corpus. A field that is
  all-integer here may be fractional on a site the corpus does not contain.
- **"Queryable" is inferred, not measured.** Nothing here counts how often clients actually
  filter on `duration` or `insulin`. The claim is that the field is common in *documents*; a v1
  operator census (plan T2.4) is what would measure the queries.
- **Four collections have no model**, so their drift is unmeasured rather than zero. `food`,
  `activity`, `settings`, `auth_subjects`, `auth_roles`.
- **The shipping walkers are transcribed** into `SHIPPING_WALKERS` from
  `chore/nightscout-modernization` @ `0a4109f6`. If that code changes, the transcription is
  stale — the test pins the three `treatments` over-coercions so the detector fails loudly
  rather than silently agreeing.
- **Nothing here has been run against the server.** The emitter produces a table; no request has
  yet been served through it.
