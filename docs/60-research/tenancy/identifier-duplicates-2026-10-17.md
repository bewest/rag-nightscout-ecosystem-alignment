# ID-DUP-MEASURE: duplicate `identifier` values in the 12-site corpus

*Contributor-facing.* **Snapshot, 2026-10-17.** Input to queue item `ID-UNIQUE-INDEX`: would a
partial unique index `{identifier: {$type: "string", $gt: ""}}` build on the stored data, and what
would identifier-first matching (`ID-FIRST-MATCH`) meet? Companion to
[write-contract null and keys](write-contract-null-and-keys-2026-10-12.md), whose corpus and site
labels this note reuses.

Marks: **[M]** measured by
[`identifier-duplicates-2026-10-17/iddup.py`](identifier-duplicates-2026-10-17/iddup.py), output in
[`results-2026-10-17.txt`](identifier-duplicates-2026-10-17/results-2026-10-17.txt); control in
[`control-results-2026-10-17.txt`](identifier-duplicates-2026-10-17/control-results-2026-10-17.txt).
Output is aggregate counts by pseudonymous site label, collection and client class; no identifier
value or record content is printed or committed.

---

## 0. Verdicts

| question | verdict |
|---|---|
| **Would the partial unique index build?** | **Yes, on every collection at every site** [M]: entries, treatments, devicestatus and profile each have 0 `identifier` values held by more than one document. The corpus has no `food` collection. |
| **How much carries `identifier` at all?** | **505 of 1,589,356 documents** [M], all Loop treatments, at 2 of 12 sites (L: 494, i: 11). No entry, devicestatus or profile carries the field. No document carries `identifier` as `null`, `""` or a non-string. |
| **So does the "yes" say much?** | **Little.** The corpus has almost no `identifier`, and no AndroidAPS, xDrip+ uploader or other API v3 writer (the clients that write `identifier` in volume). A "yes" here is a floor, not a forecast. The pre-flight duplicate report in `ID-UNIQUE-INDEX` is what decides on a real site. |
| **If Loop sent `syncIdentifier` as `identifier`** | **The index would not build at 2 sites** [M]: 13 treatment `syncIdentifier` values are held by 29 Loop documents (L: 4 values / 11 documents; i: 9 / 18). 12 of the 13 are on **different** natural keys, so identifier-first matching would fold distinct treatments into one (§2). |

---

## 1. Corpus

- `externals/ns-data` in the main checkout (not committed): sites a to k
  (`patients/{a..k}/raw`, 180-day exports, `capturedAt` 2026-04-01 to 04-04 in each `manifest.json`)
  and site L (`live-recent-180-json/live-recent`; treatments span 2026-01-01 to 2026-06-29; capture
  date not recorded in the corpus).
- Fetched through **API v1 GET** only (`tools/cgmencode/ns_fetch.py`, per the companion note §1.1).
  The hosting servers' versions are not recorded.
- **What it cannot see.** Only what v1 GET returns: no indexes, no server-side state, no documents
  outside the 180-day window, and none the v1 GET of that server did not return. Whether a
  stored `identifier` was sent by the client or set by the server (`UUID_HANDLING` moves a UUID `_id`
  into `identifier` on v1, `lib/server/treatments.js:387-401`, `entries.js:262-274` [R]) is not
  visible in the stored document.
- Document counts: 307,996 treatments, 561,690 devicestatus, 719,559 entries, 111 profile
  (`results-2026-10-17.txt`, `## collections present`).

## 2. Results

### 2.1 `identifier` presence [M]

| site | treatments with a non-empty string `identifier` | entries, devicestatus, profile |
|---|---:|---|
| L | 494 of 30,306 | 0 |
| i | 11 of 31,152 | 0 |
| a–h, j, k | 0 | 0 |

Shape of the 505, from a one-off aggregate check (not in the script): at site i, 11 Temporary
Override with a UUID-shaped value; at site L, 5 Temporary Override with a UUID-shaped value and 489
Temp Basal whose `identifier` equals their own `syncIdentifier`. Every one of the 505 has a 24-hex
`_id`. At site L the identified documents fall between 2026-03-16 and 2026-05-22, inside a window
that runs to 2026-06-29; why they start and stop is not known from the data.

Duplicates: **0** values held by more than one document, in every collection at every site.

### 2.2 `syncIdentifier` on treatments, as a proxy [M]

`syncIdentifier` is on 255,811 Loop treatments at 11 sites (all but j). API v1 does not key on it
today; it is measured because it is the value a Loop client would most plausibly send as
`identifier`.

| site | values on more than one document | documents | shape |
|---|---:|---:|---|
| i | 9 | 18 | each a **Suspend Pump + Temp Basal** pair with the same `created_at`, different `eventType` (different natural key); neither carries `identifier` |
| L | 4 | 11 | Temp Basal only: two groups of 3 and 4 spread over more than a day (different natural key); one pair 1 s apart (different natural key); **one pair on the same natural key, one with `identifier` and one without**, differing in `duration` and `amount` |

Readings, not measured:

- The site-i pairs look like one pump event uploaded as two treatments under one `syncIdentifier`.
  Loop's upload code was not read for this note.
- The site-L pair on the same natural key is the case `ID-FIRST-MATCH`'s adoption rule (Q1)
  covers: an identified write that finds no identifier match may adopt a stored record with no
  `identifier` on the natural key.
- The groups spread over more than a day suggest `syncIdentifier` values are reused after a long
  interval. If so, a unique `identifier` drawn from them would refuse or merge records months apart.

### 2.3 Index verdict per collection [M]

| collection | partial unique index on `identifier` builds? |
|---|---|
| entries | yes, 12 of 12 sites |
| treatments | yes, 12 of 12 sites |
| devicestatus | yes, 12 of 12 sites |
| profile | yes, 12 of 12 sites |
| food | not in corpus |
| treatments, if `syncIdentifier` were sent as `identifier` | no, at sites i and L |

## 3. Non-vacuity [M]

`iddup.py --control` plants, in site a: two identical treatments sharing a new `identifier`; two
entries sharing one on different natural keys; a devicestatus with `identifier: ""` and one with
`null`; a treatment with a numeric `identifier`. Each moves exactly its counter (35 deltas, listed
in `control-results-2026-10-17.txt`); the planted run reports that entries and treatments would
not build. The first control run printed no duplicate deltas, because the delta loop iterated only
the counters the clean run had created; the loop was fixed to take the union before this result
was taken.

## 4. Reproduce

```sh
python3 -I docs/60-research/tenancy/identifier-duplicates-2026-10-17/iddup.py
python3 -I docs/60-research/tenancy/identifier-duplicates-2026-10-17/iddup.py --control
```

Needs `externals/ns-data` at the main checkout's path, as `BASE` in the script names. Runs in
about 15 s.
