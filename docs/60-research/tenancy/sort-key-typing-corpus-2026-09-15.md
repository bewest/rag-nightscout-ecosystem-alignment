# Are sort keys really "one type in practice"? — measured against the corpus

> **Snapshot — research as of 2026-09-15; no commit anchor named (verifies a comment in the T2.5 seam-branch `pgCollection/sql.js`; corpus snapshots 2026-04-01 and 2026-04-26). Status: current — tenancy research, not on a shipping path. Current facts: [ordering design](../../30-design/tenancy/nightscout-seam-ordering-translation.md), [backfix register](../../30-design/remedial/nightscout-backfix-register.md) (BF-19).**

Date: 2026-09-15. Status: verification of a claim made in shipped T2.5 code. **Read-only — no
shipping code changed.** Companion to
[Ordering across the seam](seam-ordering-and-pagination-2026-09-14.md), which established *that*
the two backends order differently; this establishes *whether the real data triggers it*.

**Tooling**: `tools/qc/sort_key_typing.py`. One run reproduces everything below, including its own
non-vacuity check. Raw output: `reports/v1-query-census/sort-key-typing.json`.

---

## 1. The claim under test

`lib/api3/storage/pgCollection/sql.js`, `orderBy`, carries a comment that records a known backend
difference and then bounds it with an assertion about data:

> KNOWN DIFFERENCE, recorded rather than papered over: jsonb's cross-TYPE ordering is not BSON's.
> Both sort types before values; they disagree on the order of the types. A collection whose sort
> key holds two different types in different documents therefore orders differently on the two
> backends. **Every sort this code path issues is on a field that is one type in practice
> (`date`, `srvModified`, `identifier`, `created_at`), so it does not bite today** — but it is not
> a property the adapter can enforce.

The first two sentences are properties of the two engines and are settled — measured in
[§2 of the ordering report](seam-ordering-and-pagination-2026-09-14.md). The bolded sentence is
different in kind: it is an **empirical claim about real deployments**, and it was asserted, not
measured. This document measures it.

It matters because the claim is what downgrades a correctness difference to a note. If it is false
at one site, that deployment's rows come back in a different order on PostgreSQL than on MongoDB,
with nothing in the response to say so.

### 1.1 Two mechanisms, and the comment names only one

The comment describes the jsonb path. The shipped code has two, and which one a field takes is
decided by whether the emitted DDL gave it a generated column
(`lib/storage/postgres/generated/index.json`):

* **(A) Column-backed** (`date`, `sgv`, `sysTime`, `_id`, `created_at`, `identifier`,
  `dateString`, `type`, `mbg` on entries). `orderBy` emits `"date" ASC NULLS FIRST`, and the
  column is built with a type guard:

  ```sql
  "date" numeric GENERATED ALWAYS AS
    (CASE WHEN jsonb_typeof(doc #> '{date}') = 'number' THEN (doc #>> '{date}')::numeric END) STORED
  ```

  An **off-type value does not sort in its own type's block — it becomes SQL NULL** and goes to
  whichever end `NULLS FIRST`/`NULLS LAST` names. That is a divergence from MongoDB of a different
  shape than the one the comment describes, and the comment does not mention it.

* **(B) jsonb-backed** (`srvModified`, `isValid`, and anything the emitter flagged `AMBIGUOUS`).
  `orderBy` falls back to `doc #> '{...}'` and jsonb's own cross-type order applies. This is the
  case the comment describes.

Either way the measurement is the same question — *does any one deployment hold two JSON types in
one sort key?* — so this document measures that, and reports which mechanism each finding lands in.

### 1.2 The comment's field list is not the exposed surface

The four fields named are the ones **the code path issues today**. API v3 takes the sort key from
the query string (`?sort=`, `?sort$desc=`), so a client can name any field it likes. The two sets
are measured and reported **separately below**: conflating them would either excuse the comment
for a field it never claimed, or condemn it for one.

---

## 2. Method

`tools/qc/sort_key_typing.py` streams every document of every collection file in the corpus and,
for each field of interest, counts the JSON type of the value (`jsonb_typeof`'s vocabulary:
`string`, `number`, `boolean`, `null`, `object`, `array`) or records the key as absent. A field is
**single-typed** at a site if every *present* value has the same type.

* **Present vs absent is kept distinct.** An explicit JSON `null` is a *type* — jsonb returns
  `null` for it and BSON has a Null type — whereas an absent key yields SQL NULL and is governed by
  `NULLS FIRST`/`NULLS LAST` instead. Counting them together would hide a real mixture; counting
  absence as a type would invent one.
* **Per site, not corpus-wide.** A deployment sorts its own rows and nobody else's, so a field that
  is one type at every site and a different one between sites cannot reorder anything. That case is
  reported in its own section rather than as a mixture.
* **Scope**: both snapshots of the corpus — `externals/ns-data/patients/` (2026-04-01) and
  `externals/ns-resync-2026-04-26/raw/` (2026-04-26) — 11 sites, 4 collections,
  **1,968,464 documents**. This matches the scope of `reports/schema-census/*.census.json`, so the
  two artifacts are directly comparable.

**Privacy.** The tool reads document *structure* only: which keys exist and what type each value
has. No value, document, key content, URL or identifier is emitted or stored, here or in the JSON
output. Sites are the corpus's own single letters. `ns_url.env` and `manifest.json` are never
opened — both carry the deployment URL.

### 2.1 What this method cannot see — stated before the result, because it bounds it

The corpus is **JSON captured from the REST API, not a BSON dump**. JSON has six types; BSON has
roughly twenty, and the export collapses several:

| Collapsed on the way out | Consequence for this measurement |
|---|---|
| BSON `Date` → JSON string | A collection holding `created_at` as a Date in some documents and a String in others reads here as **single-typed**, and is not. In MongoDB those sort in different blocks. **This is the blind spot that matters most**, because the three date-like fields are exactly where a driver-vs-client write split would produce it. |
| BSON `ObjectId` → JSON string | Same blind spot, for `_id`. |
| `Int32` / `Int64` / `Double` / `Decimal128` → JSON number | **Harmless.** MongoDB sorts all numeric types as one block, and so does jsonb, so collapsing them loses nothing for an ordering question. |

Therefore:

* a **"single-typed"** result here is **necessary but not sufficient** for the comment's claim;
* a **"mixed"** result is **conclusive** — two JSON types in the export were two BSON types in the
  database.

A second limit: the corpus is 11 sites. It cannot show that no Nightscout deployment anywhere holds
a mixed sort key; it can only show whether these do.

**Note on comparing with the schema census.** `reports/schema-census/*.census.json` splits `integer`
from `number` (JSON Schema's distinction). Those are the *same* jsonb type and the same MongoDB sort
block, so this tool collapses them. A reader who sees `entries.date` listed there as
`{integer: 345332, number: 551257}` should not read that as a mixed sort key — it is not one.

---

## 3. Non-vacuity: proving the detector can fail

A detector that reports "no mixed types" because it is broken is indistinguishable from one that
reports it because the data is clean. Two independent checks, both of which the tool runs on every
invocation (it aborts the corpus pass if the first fails).

### 3.1 Planted mixture, synthetic

Six documents in which `date` holds a number in four and a string in one, `created_at` holds a
string in five and a number in one, `identifier` holds a string in five and an explicit `null` in
one, and one document omits `date` entirely:

```
NON-VACUITY CHECK -- synthetic corpus, mixed type planted
  documents: 6   skipped: 0
  date         absent=1  types={'number': 4, 'string': 1}  ->  MIXED:number+string
  identifier   absent=0  types={'string': 5, 'null': 1}  ->  MIXED:null+string
  created_at   absent=0  types={'string': 5, 'number': 1}  ->  MIXED:number+string
  [PASS] date mixes number and string
  [PASS] created_at mixes string and number
  [PASS] identifier mixes string and an explicit JSON null
  [PASS] a single-typed field is NOT flagged (no false positive)
  [PASS] an absent key is not counted as a type
NON-VACUITY: PASS -- the detector sees a planted mixed type
```

The `created_at` case is verbatim the divergence the comment says does not happen: an ISO string in
one document and an epoch number in another.

### 3.2 Real-data positive control

A synthetic file proves the comparison logic, not the corpus reader. So three fields were added to
the measured set **specifically because the schema census already records them holding two types**
— `treatments.carbs`, `treatments.insulin`, `profile.mills`. The detector flags all three, reading
the same 235 MB-scale files as the rest of the run:

```
  2026-04-01 a/treatments    carbs     {'null': 28108, 'number': 800}     [client-choosable]
  2026-04-01 a/treatments    insulin   {'null': 27914, 'number': 994}     [client-choosable]
  ... 44 rows, every site, both snapshots
```

**Non-vacuity: PASS on both checks.** The clean result in §4 is a fact about the data, not about
the tool.

---

## 4. Measured

11 sites, 2 snapshots, 4 collections, 88 (snapshot, site, collection) triples, **1,968,464
documents. 0 documents skipped. 0 files skipped or missing.** Full 88-row breakdown in
`reports/v1-query-census/sort-key-typing.json`; condensed by collection here, because every site
behaves identically except where noted.

### Table A — the four fields the comment names (issued by the code path today)

| collection | field | present in | verdict |
|---|---|---|---|
| **entries** | `date` | 896,589 docs, 22/22 triples | **single: number**, all 11 sites, both snapshots |
| entries | `srvModified` | **0 docs** | absent everywhere |
| entries | `identifier` | **0 docs** | absent everywhere |
| entries | `created_at` | **0 docs** | absent everywhere |
| **treatments** | `created_at` | 369,419 docs, 22/22 | **single: string**, all sites |
| treatments | `identifier` | 48 docs, 2/22 (one site) | single: string |
| treatments | `date`, `srvModified` | 0 docs | absent everywhere |
| **devicestatus** | `created_at` | 702,254 docs, 22/22 | **single: string**, all sites |
| devicestatus | `date`, `srvModified`, `identifier` | 0 docs | absent everywhere |
| **profile** | `created_at` | 22 docs, 4/22 (two sites) | single: string |
| profile | `srvModified` | **2 docs, 1 site** | single: number |
| profile | `date`, `identifier` | 0 docs | absent everywhere |

**No mixture, anywhere, in any of the four.**

### Table B — reachable by a client via `?sort=` / `?sort$desc=`

| collection | field | present in | verdict |
|---|---|---|---|
| **entries** | `sysTime` | 896,589 docs, 22/22 | single: string |
| entries | `_id` | 896,589 docs, 22/22 | single: string |
| entries | `sgv` | 895,418 docs, 22/22 | single: number (1,171 docs lack the key — `mbg` records) |
| entries | `srvCreated`, `startDate`, `NSCLIENT_ID`, `mills`, `carbs`, `insulin` | 0 docs | absent |
| **treatments** | `_id` | 369,419 docs, 22/22 | single: string |
| treatments | `mills` | 2 docs, 2/22 | single: number |
| treatments | **`carbs`** | 369,419 docs, 22/22 | **MIXED: null + number — every site, both snapshots** |
| treatments | **`insulin`** | 369,419 docs, 22/22 | **MIXED: null + number — every site, both snapshots** |
| **devicestatus** | `_id` | 702,254 docs, 22/22 | single: string |
| **profile** | `startDate` | 202 docs, 22/22 | single: string |
| profile | `_id` | 202 docs, 22/22 | single: string |
| profile | `mills` | 202 docs, 22/22 | single per site, but **number at 1 site, string at 10** |

### Single-typed per site but disagreeing between sites

```
  profile       mills          number: 1 site(s), string: 10 site(s)
```

Not an ordering divergence for any deployment as the corpus stands — each site's `profile.mills` is
internally consistent. It becomes one under two concrete conditions the design already anticipates:
a site that changes client and starts writing the other type, and the cross-deployment import that
`entries.sql` explicitly plans for ("two tenants restored from different deployments"). At that
point `mills` is `string`+`number` in one collection, which is the pairing that **does** reorder
(§5).

---

## 5. Which mixtures actually reorder — and why the ones found do not

The ascending type orders, as measured in
[§2 of the ordering report](seam-ordering-and-pagination-2026-09-14.md) against mongod 7.0.43 and
PostgreSQL 16.14:

* **MongoDB**: Null < Number < String < Object < Array < Boolean < Date (missing ties with Null)
* **jsonb**: Null < String < Number < Boolean < Array < Object

| pairing | MongoDB ASC | jsonb ASC | agree? | found in corpus? |
|---|---|---|---|---|
| `null` + `number` | null, then numbers | null, then numbers | **yes** | yes — `carbs`, `insulin`, 11/11 sites |
| `number` + `string` | numbers, then strings | strings, then numbers | **no** | not within any one site |
| `number` + `boolean` | numbers, then booleans | numbers, then booleans | yes | no |
| `string` + `boolean` | strings, then booleans | strings, then booleans | yes | no |
| `string` + `object`/`array` | string, then object, then array | object/array after string, **array before object** | **no** | no |

So the single mixture the corpus actually contains — `null` + `number` — sits in the one row where
the two engines happen to agree.

It agrees on the column path too, and for a second reason worth naming. `carbs` and `insulin` are
column-backed on `treatments`, so the guard maps a JSON `null` to SQL NULL — collapsing it together
with an *absent* key. MongoDB independently collapses null and missing for sorting. The explicit
`NULLS FIRST`/`NULLS LAST` then puts that combined group where MongoDB puts it. **The type guard's
lossiness and MongoDB's own null/missing conflation cancel out.** That is a coincidence, not a
design, and it holds only for this pairing.

**Caveat, flagged rather than glossed:** the agreement for `null`+`number` on the **jsonb** path is
directly readable from the measured fixture table in the ordering report. The agreement on the
**column** path is *derived* from the DDL and the documented `NULLS FIRST` semantics — mongod and
PostgreSQL were **not** re-run here (neither is installed in this environment). See §7.

---

## 6. Verdict

**The comment's claim, as written, is CONFIRMED — and its reasoning is narrower than its scope.**

1. **On the four fields it names: confirmed.** Across 1,968,464 documents, 11 sites and two
   snapshots, `date`, `srvModified`, `identifier` and `created_at` are single-typed wherever they
   appear. Not one mixture. Subject to the BSON `Date`-vs-string blind spot in §2.1, which this
   method cannot rule out.

2. **On `entries` — the only collection T2.5 actually puts on PostgreSQL — it is stronger than
   claimed, and thinner than it reads.** Stronger: the schema census records **no multi-typed field
   at all** among all 19 paths entries carries, over 896,589 documents (`truncated: false`,
   `path_cap_reached: false`) — so *every* field a client could name in `?sort=` is single-typed,
   not just four. Thinner: three of the four fields the comment names — `srvModified`,
   `identifier`, `created_at` — **are absent from every entries document in the corpus**. For those
   three the claim is vacuously true on entries; the corpus supplies zero evidence either way. The
   comment's real, non-vacuous evidence on entries is `date` alone.

3. **The sentence does not cover the surface the code exposes.** Because v3 takes the sort key from
   the query string, "every sort this code path issues" is not the set of sorts the code path can be
   *made* to issue. On the reachable set, "one type in practice" is **false at 11 of 11 sites**:
   `treatments.carbs` and `treatments.insulin` each hold `null` and `number` in every single site,
   in both snapshots. They do not reorder — but that is because of *which* two types they hold
   (§5), not because the field is one type. **The conclusion survives; the stated reason for it does
   not.** `treatments` is T2.6, so this lands before the code does rather than after.

4. **A field in the emitted manifest is flagged on evidence it does not have.**
   `lib/storage/postgres/generated/index.json` flags `NSCLIENT_ID` `AMBIGUOUS` on `devicestatus`,
   `treatments` and `profile` with the reason *"observed as number, string — not one type"*.
   `NSCLIENT_ID` appears in **0 of 1,968,464 corpus documents**, and the census never mentions it.
   Tracing it: `tools/nsschema/code_model.py` puts it in `INDEXED_ONLY` with
   `type_undetermined: True`, and `tools/nsschema/model.py:187` says in as many words that these are
   paths "no OpenAPI document declares and no census observed [...] and it is *not* evidence."
   The **decision is right** — an undetermined type should not get a typed column, and denying it
   one routes it to the jsonb path where a future mixture at least orders by a defined rule. The
   **stated reason is wrong**: "observed as" describes a corpus observation that was never made.
   The emitter should distinguish `AMBIGUOUS (observed)` from `AMBIGUOUS (undetermined)`; anyone
   auditing the DDL currently reads a code-derived guess as a measurement.

### Recommended wording

The comment's parenthetical is the part that misleads. Something closer to the measurement:

> Measured against the 11-site corpus (`tools/qc/sort_key_typing.py`, 1.97M documents, two
> snapshots): no sort key this code path issues holds two JSON types at any site. Note this is a
> property of the *data*, and the export cannot distinguish a BSON Date from a string. It is also
> narrower than the exposure — v3 takes the sort key from the query string, and on that wider
> surface `treatments.carbs` and `treatments.insulin` do hold two types at every site. They happen
> not to reorder, because `null`+`number` is the one pairing jsonb and BSON agree on.

---

## 7. What is still not measured

1. **BSON `Date` vs string is invisible here** (§2.1). Closing it needs a `mongodump`/BSON-level
   census, not a REST export. Until then, "single-typed" on any of `created_at`, `sysTime`,
   `dateString`, `startDate`, `_id` is a JSON-level statement only. This is the largest remaining
   hole and it sits under three of the four fields the comment names.

2. **The shipped ordering translation is not among the arms that were differentially tested.**
   `tools/qc/order-arm.js` compares four translations against mongod — `text (naive)`,
   `numeric cast`, `jsonb native`, `text + NULLS FIRST`. T2.5 shipped a **fifth**: a typed generated
   column with a `jsonb_typeof` guard, ordered with explicit `NULLS FIRST`/`NULLS LAST`. Its test
   table even builds its generated column *without* the guard
   (`date numeric GENERATED ALWAYS AS ((doc->>'date')::numeric) STORED`), so it is not the shipped
   shape. **The ordering that actually ships has never been run against mongod on mixed-type data.**
   [Note 2026-09-22: a guarded-column arm was added the same day,
   [`tools/qc/typeguard-arm.js`](../../../tools/qc/typeguard-arm.js); results are summarised in the
   2026-09-15 update to [the ordering report](seam-ordering-and-pagination-2026-09-14.md) §2 and in
   the ordering design §3.1b.]
   Adding a fifth arm that mirrors the emitted DDL, with a `null`+`number` fixture and a
   `string`+`number` fixture, would turn §5's derivation into a measurement. That is the single
   highest-value follow-up here, and it is small.

3. **11 sites is not the ecosystem.** These deployments are self-selected. A `string`+`number` sort
   key at some other site is entirely possible; §5 says what would happen if it existed, and nothing
   in the adapter would report it.

4. **No per-tenant view after import.** `profile.mills` disagreeing across sites (§4) becomes a
   within-tenant mixture the moment two deployments' data land in one tenant. Nothing measures that,
   because nothing has done it yet.

---

## 8. Artifacts

| path | what |
|---|---|
| `tools/qc/sort_key_typing.py` | the detector; `--self-test` runs §3.1 alone |
| `reports/v1-query-census/sort-key-typing.json` | all 88 triples, per-field type counts, skip records |
| `reports/schema-census/*.census.json` | pre-existing corpus-wide field census, cross-checked in §2.1 and §6.2 |
| [seam-ordering-and-pagination-2026-09-14.md](seam-ordering-and-pagination-2026-09-14.md) | the measured engine-level ordering difference this document sizes |
