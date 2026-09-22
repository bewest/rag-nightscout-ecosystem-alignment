# E4 — closing the gap between the work queue and the backfix register

> **Snapshot — research as of 2026-09-15, measured against `origin/dev a8888f0d` (control-surface HEAD `08753474`). Status: point-in-time reconciliation; register and manifest counts below are as of that date and have since changed. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md), [work queue](../../../queue/work-queue.yaml).**

**Written for maintainer review.** Contributor-facing and technical throughout, except the
`operator_visible` field of each queue item, which is written for people managing their own or a
family member's diabetes and follows the rules in `queue/README.md`. Nothing here is medical
advice. Nothing was pushed, merged, published or sent anywhere: this changes only the control
surface (`queue/`, `tools/queue/`, `Makefile`, this document). No shipping repository was written
to and no branch was created or moved.

Written 2026-09-15 against (all counts point-in-time as of 2026-09-15):

| thing | value at the time of measurement |
|---|---|
| control-surface HEAD | `08753474` |
| shipping checkout | `externals/cgm-remote-monitor-official`, working tree at `a8888f0d` = `origin/dev` |
| register | `docs/30-design/remedial/nightscout-backfix-register.md`, 69 entries (67 `BF-`, `CAP-01`, `CAP-02`) |
| manifest before | 57 items, 39 distinct register ids referenced |
| manifest after | 74 items, 68 distinct register ids referenced |

---

## 1. Register ids with no queue item

A completeness critique reported **29 not-fixed register ids appearing nowhere in the manifest, 14
of them in §1**. An independent derivation — a different parser, run from the register's table
headers rather than a fixed column count — returned exactly the same 29 ids, 14 of them in §1
(point-in-time as of 2026-09-15; the register has since changed):

```
BF-40 BF-41 BF-42 BF-43 BF-44 BF-45 BF-46 BF-47 BF-48 BF-49 BF-50 BF-51 BF-52 BF-67   (§1,  14)
BF-53 BF-54 BF-55 BF-56 BF-57 BF-58 BF-59 BF-60 BF-61 BF-62 BF-63 BF-64 BF-65 BF-66   (§1b, 14)
CAP-02                                                                                 (§1c,  1)
```

`BF-12` is the thirtieth id absent from the manifest and is correctly absent: it is **closed as
invalid** (does not reproduce).

**The right repair is not 29 new items.**
"Appear nowhere in the manifest, not even in prose" is literally true — `grep -o 'BF-4[0-9]'` over
the manifest returned nothing. But **ten of the 29 were already tracked in substance by an existing
item**, several of them by a *gate script that reproduces the register entry's own ablation
verbatim*. `RT-D3` runs `d3-drag-clamp-covered.js`, which is BF-54. `RT-5` runs
`cut4-total-outage.js`, which is BF-61. `RT-VERSION` runs `version-collision.js`, which is BF-60.
`DOC-TESTSCRIPTS` runs `test-script-coverage.js`, which is BF-53. What was missing was the
`register:` cross-reference, not the work.

Filing 29 new items would have created ten duplicates of work already scheduled and measured, and
would have made the queue *less* true rather than more. So the repair is split:

- **19 register ids → 14 new items** (some batched, see §4);
- **10 register ids → a `register:` cross-reference on an existing item**, with no other field of
  that item touched;
- **plus 3 further new items** for the §5 follow-ups, which carry no register id at all — 17 new
  items in total.

`BF-58` falls in both of the first two rows: `RT-1` gets the cross-reference and
`RT-NODE-FLOOR-TESTED` is the new item that does the work. The table below shows both owners.

---

## 2. The full set difference

29 rows. Every id that was not fixed and had no item, with where it went.

| id | § | severity | queue item(s) now | new item or cross-reference | parcel | linear stage |
|---|---|---|---|---|---|---|
| **BF-40** | 1 | medium | `BFQ-40` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-41** | 1 | high | `BFQ-41` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-42** | 1 | high | `BFQ-CONNECTOR` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-43** | 1 | medium | `BFQ-CONNECTOR` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-44** | 1 | high | `BFQ-MINIMED` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-45** | 1 | medium alone | `BFQ-MINIMED` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-46** | 1 | high | `BFQ-46` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-47** | 1 | medium | `BFQ-47` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-48** | 1 | medium | `BFQ-ENV` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-49** | 1 | low | `BFQ-ENV` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-50** | 1 | low | `BFQ-ENV` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-51** | 1 | medium | `BFQ-ENV` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-52** | 1 | unsettled | `BFQ-52` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **BF-53** | 1b | medium | `DOC-TESTSCRIPTS` | cross-reference only | `docs-truth` | document truth |
| **BF-54** | 1b | medium | `RT-D3` | cross-reference only | `release-train` | 2 modernization |
| **BF-55** | 1b | high | `RT-1`, `RT-REBASE` | cross-reference only | `release-train` | 2 modernization |
| **BF-56** | 1b | medium | `RT-REBASE` | cross-reference only | `release-train` | 2 modernization |
| **BF-57** | 1b | unsettled | `RT-D3` | cross-reference only | `release-train` | 2 modernization |
| **BF-58** | 1b | low | `RT-1`, `RT-NODE-FLOOR-TESTED` | cross-reference only | `release-train` | 2 modernization |
| **BF-59** | 1b | low | `RT-NODE-FLOOR-TESTED` | **NEW ITEM** | `release-train` | 2 modernization |
| **BF-60** | 1b | medium | `RT-VERSION` | cross-reference only | `release-train` | 2 modernization |
| **BF-61** | 1b | high | `RT-5` | cross-reference only | `release-train` | 2 modernization |
| **BF-62** | 1b | low | `RT-5` | cross-reference only | `release-train` | 2 modernization |
| **BF-63** | 1b | high | `RT-BOOTERROR` | **NEW ITEM** | `release-train` | 2 modernization |
| **BF-64** | 1b | high | `RT-3` | cross-reference only | `release-train` | 2 modernization |
| **BF-65** | 1b | medium | `RT-CONNECT-PIN-CUTS` | **NEW ITEM** | `release-train` | 2 modernization |
| **BF-66** | 1b | medium | `BFQ-66` | **NEW ITEM** | `tenancy` | 3 multitenant |
| **BF-67** | 1 | medium | `BFQ-67` | **NEW ITEM** | `register-open` | 1 remedial - dev now |
| **CAP-02** | 1c | one loader, plus whatever decides the BSON→jsonb transform (see BF-19/BF-20/BF-21) | `BFQ-CAP02` | **NEW ITEM** | `tenancy` | 3 multitenant |

`BF-55` and `BF-58` appear against two items each, legitimately. `RT-1` already carried each as a
recorded `no-gate:` reason — a measurement saying "nobody built the instrument" — while the *work*
lives elsewhere: `RT-REBASE` for BF-55, the new `RT-NODE-FLOOR-TESTED` for BF-58. The register id
now names both, which is what lets a reader find the measurement from the work and back.

### The six §5 follow-ups

The PR sequencing document lists ten follow-ups "deliberately not in these PRs". Two (#1 and #8)
are struck through as resolved. #5 is `P0-F` and #6 is `BFQ-04`. **The remaining six were in a
document and in no queue.** They have no register id, and per rule 4 this reconciliation allocates
none.

| # | what | item now | note |
|---|---|---|---|
| 2 | the limit rule is written twice — *"the root cause of this whole family"* | `FU-LIMIT` | **corrected, see §5** |
| 3 | `plugins.isPluginEnabled` always returns `true` | `FU-RESIDUALS` | gate FAILS today |
| 4 | the second unguarded `console.log` at `storage.js` | `FU-RESIDUALS` | **corrected, see §5** |
| 7 | the alexa `switch` has no `default` | `FU-RESIDUALS` | gate FAILS today; should land with `bf/alarms` |
| 9 | audit the lint suppressions outside `lib/` | `FU-HYGIENE` | `no-gate:` — the audit *is* the work |
| 10 | jsdom test hygiene has no enforcement | `FU-HYGIENE` | `no-gate:` — and cut 1 retires jsdom |

---

## 3. Parcel assignment under the maintainer's linear model

> 1. remedial / backfix → PRs onto official current `dev`
> 2. modernization → the parcels, in order, each taking `dev` first
> 3. multitenant → on a stabilised, current base

The manifest's five parcels already encode this, so no schema change was needed and none was made:

| parcel | linear stage | new ids landing here |
|---|---|---|
| `register-open` | **1 — remedial, targets `dev` now** | all 14 §1 ids, in 9 items |
| `phase0` | **1 — remedial, targets `dev` now** | the 3 follow-up items |
| `release-train` | **2 — modernization** | BF-59, BF-63, BF-65 (3 new items) + 9 cross-references |
| `tenancy` | **3 — multitenant, last** | BF-66, CAP-02 |
| `docs-truth` | document truth, runs alongside | BF-53 cross-reference |

**`ships_to_operators_today` carries the §1 / §1b line and every new register item declares it.**
That field is the only thing making the register's sections mean anything, and the new standing
check (§6) now *enforces* the agreement rather than trusting it. One consequence, deliberate: the
connector credential leak is **two items, not one**, because `BFQ-CONNECTOR` (BF-42, BF-43) is on
`origin/master` and reaches operators today, while `RT-CONNECT-PIN-CUTS` (BF-65) is on cut tips and
does not. The work is identical and they should be done together; the *exposure* is not, and
merging them would have widened §1 by the back door.

---

## 4. What was batched, what was kept separate, and why

The critic suggested three thematic batches. I took one of them whole, split one on severity and
split one on the §1 / §1b line. **Everything below is separable and each item says where the seam
is, so the maintainer can split any of them back.**

| item | ids | batched? | reasoning |
|---|---|---|---|
| `BFQ-ENV` | BF-48, BF-49, BF-50, BF-51 | **yes** | One piece of work — *make the configuration surface tell the truth* — with **one runnable gate in four arms**. A reviewer reading any one alone would ask about the other three. |
| `BFQ-46` | BF-46 | **no — split out of the env batch** | The critic proposed BF-46/48/49/50 as one. BF-46 irreversibly **deletes a person's stored glucose history** through a name nobody can look up, with the result unawaited. A reviewer should not have to find that inside a batch whose other members are a README typo and a dead settings key. |
| `BFQ-CONNECTOR` | BF-42, BF-43 | **yes** | Two lines of the same `package.json`, one PR, one gate with both arms. |
| `RT-CONNECT-PIN-CUTS` | BF-65 | **no — split off on §1 / §1b** | The critic proposed BF-42/43/65/56 as one family. Same work, different exposure; see §3. BF-56 is the rebase, and `RT-REBASE` already owns it. |
| `BFQ-MINIMED` | BF-44, BF-45 | **yes** | The register grades BF-45 *"medium alone, high in combination with BF-44"*. They are decided by the same unanswerable question — what real CareLink payloads contain — and splitting them would let the combination be lost. |
| `RT-NODE-FLOOR-TESTED` | BF-58, BF-59 | **yes** | One question: *is the floor the software enforces the floor anything actually runs?* Fixing one without the other leaves it open. |
| `FU-RESIDUALS` | follow-ups 3, 4, 7 | **yes, and loosely** | Three one-line changes the sequencing document named together, each with its own gate. **Their destinations differ** — #7 belongs on `bf/alarms`, #4 on `bf/auth` — and the item says so. |
| `RT-BOOTERROR`, `BFQ-41`, `BFQ-47`, `BFQ-52`, `BFQ-67`, `BFQ-40`, `BFQ-66`, `BFQ-CAP02`, `FU-LIMIT`, `FU-HYGIENE` | one each | kept separate | Each is a distinct decision, a distinct reviewer, or a distinct file. `BFQ-47` in particular is *the one irreversible change in the Phase 0 batch* and needs the security reviewer who takes `P0-C`. |

The critic also proposed batching **BF-61 and BF-62** as "the parcel-4 outage family". I did neither
— both were already carried by `RT-5`, one as its `cut4-total-outage.js` gate and one as a
`no-gate:` reason, so they needed a cross-reference and nothing else.

---

## 5. Corrections this work produced

Rule 1: a mismatch is reported, not worked around. Rule 3: every claim below says whether it is
**read-derived** or **reproduced**.

### 5.1 BF-67's low-side sentence is wrong — REPRODUCED

The register says: *"The same applies at the bottom: a `BG_LOW` of `3.9` becomes
`bgTargetBottom - 1 = 79`."* **It does not.** The guard is `bgLow >= bgTargetBottom`, so a value
far *below* the band passes through untouched. Executing the shipping `lib/settings.js`:

| input (UNITS at the mg/dL default) | stored | `console.warn` lines |
|---|---|---|
| `BG_HIGH=14` | **181** | 2 — the entry's high-side claim, confirmed |
| `BG_LOW=3.9` | **3.9** | **0** — no rewrite at all |
| `BG_LOW=90` (against the shipped `bgTargetBottom` of 80) | **79** | 2 — the real low-side case |

**The refuted half leaves a worse residue that no entry owns**: a low alarm set to 3.9 mg/dL can
never fire, and is stored with no warning of any kind. It is not a silent *rewrite*, so it does not
belong in BF-67; it is proposed as a separate entry in this session's return value, without an id
(rule 4).

BF-67 was filed *read, not reproduced*. The gate written here reproduces it, so its provenance can
be upgraded.

### 5.2 BF-41 is now reproduced, not read-derived

The register filed BF-41 as *"derived from source on `origin/dev`, not executed end to end"* and
said the run *"is the fix for this entry's provenance, and it is cheap"*. It was cheap.
`timeago-future-reading.js` executes the shipping plugin: a reading 5 or 120 minutes ahead of the
server clock returns `checkStatus === 'current'`, while 2 / 20 / 40 minutes old return
`current` / `warn` / `urgent`. The arithmetic in the entry is confirmed exactly.

### 5.3 A vacuous gate on a `ready-to-push` item — REPRODUCED

`P0-C` declared a gate described as *"This gate FAILS today by design — it is the residual the
branch has not taken"*. It did not fail. It searched for `console.log('Loading', opts)` **with a
space after the comma**; the source is `console.log('Loading',opts)` **without one**, so the grep
matched nothing, the `|| exit 0` arm fired, and `P0-C` reported 3/3 PASS on a property that is
false. The space came from the register's own quotation at L1005, which every downstream document
copied.

`P0-C`'s corrected pattern is now in the manifest and `P0-C` reports FAIL; `FU-RESIDUALS` uses
the same space-tolerant pattern so the two cannot diverge. The register's L1005 quotation should
be corrected at source.

### 5.4 `storage.js:84` and `:113` are both right

The sequencing document says *"(this document and the register both said `:84`; measured, it is
`:113`)"*. Measured here on both refs: it is **`:84` on `origin/dev`** and **`:113` on `bf/auth`**.
Neither number is wrong; neither names its ref, which is why they read as a contradiction. The fix
has to land on `dev`, so `:84` is the number a reader of the register needs.

### 5.5 `lib/server/count.js` does not exist on `dev` — REPRODUCED

Follow-up #2 says the limit rule is written twice, *"`lib/server/count.js` and v3's `parseLimit`"*,
and calls the duplication the root cause of the whole read-path family. `git cat-file -e
origin/dev:lib/server/count.js` **fails**: that file is *created by `bf/reads`*. So the duplication
does not exist yet — **it is created by landing `P0-E`**. `FU-LIMIT` is therefore `blocks_on:
[P0-E]` and carries both measurements as gates: the `origin/dev` arm passes (one rule) and the
`bf/reads` arm fails (two), which is also what proves the gate is reading the tree and not the
command.

### 5.6 The ES6-shorthand pitfall in `booterror-shape-coverage.js`

A caller-count arm matching `/\berr\s*:/` reports `origin/dev` as having **1** `bootErrors.push`
site with no `err` key, which would contradict the register's *"7 such sites on master and dev, all
passing `err`; 9 on cut 4"*. The site is `bootErrors.push({desc: synopsis.join(' '), err})` — **ES6
shorthand, no colon** — so that result is red for a reason unrelated to the property. With the
shorthand matched, the gate reproduces the register exactly: **7 / 7 / 9 sites, 0 / 0 / 2 without
`err`** on master / dev / cut 4.

### 5.7 `make queue-check`'s first ablation was mis-scoped

Removing a `register:` cross-reference to test the new standing check made `queue-check` fail — on
the **staleness** line, because any manifest edit also makes `QUEUE.md` stale, and Make stops at
the first failing recipe line. The harmless failure masked the one that matters, and the operator
would be told to run `make queue` when the real problem was that a defect reaching operators had no
queue item. **The target now runs coverage first**, and the ablation was redone with `QUEUE.md`
regenerated so that only coverage could fail. It did.

---

## 6. The standing check, and the proof that it is not vacuous

`tools/queue/gates/register-queue-coverage.js`, wired into `make queue-coverage` and into
`make queue-check` **ahead of** the staleness check.

The critic's point was sharp and correct: `make queue-check` proved the **generated view** was
current with the manifest — *the edge where staleness is harmless*, because one command regenerates
it — while the edge that costs, **manifest versus register**, had no check at all.

Three arms:

1. **coverage** — every not-fixed register id is named in some item's `register:` list;
2. **section agreement** — where a covering item declares `ships_to_operators_today`, it agrees
   with the register section (§1 → `true`, §1b → `false`; §1c exempt, being neither);
3. **no invented ids** — an id in the manifest that is not in the register.

Plus a **vacuity guard**: if either side parses to zero entries, the gate reports that it can no
longer read the file and fails, rather than passing on an empty comparison. The register's table
shape has changed twice in one day.

`fixed` counts as covered, because the branch carrying the repair *is* a queue item. Operator
exposure is a different question and `DOC-EXPOSURE` owns it — in this register `fixed` means
"repaired on a branch, **not merged**", so every §1 defect still reaches every operator.

### Ablation — rule 2, in an isolated copy

Register and manifest were copied to a scratch directory; nothing under `docs/` or `queue/` was
mutated for arms 1–3.

| # | what was broken | result |
|---|---|---|
| 0 | baseline: all 29 ids cross-referenced in the copy | **exit 0**, `3 checked, 0 failing` — green is reachable |
| 1 | a new `BF-90` row added to §1 of the register copy | **exit 1**, `BAD BF-90 (§1, register L166, open) is not fixed and no manifest item names it` |
| 2 | `BF-41` (§1) moved onto a `ships_to_operators_today: false` item only | **exit 1**, `BAD BF-41 is §1 in the register but every item declaring it (BFQ-21=false) says ships_to_operators_today=false` |
| 3 | `BF-777` invented in the manifest copy | **exit 1**, `BAD BF-777 is named by BFQ-10 but is not in the register` |
| 4 | gate pointed at a file that parses to zero entries | **exit 1**, `BAD parsed 0 register entries … this gate can no longer read it` |

**Step 0 matters as much as the rest.** A check that has only ever been red has not been shown to
measure anything either.

### Ablation of the `make` target itself

Done on this session's own files and restored byte-for-byte (md5 verified):

1. remove `BF-41`'s cross-reference → `make queue` → `make queue-check` → **fails on coverage**,
   naming BF-41, exit 2;
2. restore both files → `make queue-check` → **exit 0**.

---

## 7. Gates written, and the ablation for each

**Six new gate scripts, plus three one-liner gates declared inline in the manifest.** They follow
the style of `tools/queue/gates/`; **no existing gate script was edited.** All read only: `git show` into memory, `require()` of a shipping
module by path, no writes to any worktree (rules 0 and 5).

| gate | ids | verdict today | how it was proven non-vacuous |
|---|---|---|---|
| `register-queue-coverage.js` | the standing check | **PASS** | §6 — five arms, four break-it runs plus a green baseline |
| `timeago-future-reading.js` | BF-41 | **FAIL** (by design) | 3 controls (2/20/40 min → current/warn/urgent) come out the other way; and an isolated copy with a future guard makes the gate **go green** with controls still green |
| `threshold-silent-rewrite.js` | BF-67 | **FAIL** (by design) | 4 controls, incl. the one that **refuted** the register (§5.1); an isolated copy with the two rewrite sites removed makes it **go green** |
| `config-surface-census.js` | BF-46, 48, 49, 50, 51 | **FAIL** (by design) | every arm has a control through the identical lookup; arms re-run against a **doctored README/env.js go green**; the hsts control lives *inside* the same family (4 of 5 generated names ARE found) |
| `connector-pin-exposure.js` | BF-42, 43, 65 | **FAIL** (by design) | `origin/dev` is the built-in control and **passes both arms** while master and cuts 1–3 fail; the gate also **fails as unmeasured if every ref agrees** |
| `booterror-shape-coverage.js` | BF-63 | **FAIL** (by design) | 3 control shapes **render** through the identical expression; the gate refuses to run if the map expression is no longer present verbatim; see §5.6 for the construction error it caught |
| three one-liners in `FU-*` | follow-ups 2, 3, 4, 7; BF-59 | **FAIL** (by design) | each re-run against a doctored source stream **goes green**; `FU-LIMIT` and `RT-NODE-FLOOR-TESTED` each carry a **passing control arm** on a different ref, run with the identical command |

### Where a gate was deliberately *not* written

`no-gate:` is the bookkeeping, not a failure. The ones worth knowing:

- **BF-40** needs a **real MongoDB**. A JavaScript-side oracle gets it wrong: `mingo` applies
  JavaScript truthiness, MongoDB applies `value != 0`, and that difference *is* the entry. A gate
  reproducing it against `mingo` would agree with BF-32 and be wrong.
  [Correction 2026-09-22: BF-40 (`$exists`) is fixed by PR #8737 via `BOOLEAN_OPERANDS`/`readBooleanOperand` in `lib/server/query.js`, merged to dev 2026-09-18, unreleased.]
- **BF-44** is reproduced in the register but is **not** re-run as a gate, because the arm and
  control roles **invert with the server's own timezone** — the divergence is (pump offset − *server*
  offset) when the payload carries no zone designator. A gate that did not pin `TZ` would report
  the opposite result on a differently configured machine, which is worse than no gate.
- **BF-66** is reproduced on `crm-seam` `81a1f6ce`, and gating it would pin the item to one seam
  commit that `SEAM-REFRESH` exists to move.
- **BF-42, BF-44, BF-51, BF-61** all have residues that **cannot** be settled here at all: a real
  vendor account, a real CareLink payload, a live Azure deployment. Rule 0 forbids every one.

---

## 8. What a reviewer should check

1. **The batching.** §4 is a judgement call. Each item names its seam; split any of them back.
2. **`BFQ-47` before `P0-C` merges.** The missing fact is an *inventory* of third-party tools that
   store extra fields on subjects — not code, and not producible from this machine. It is the one
   irreversible change in the Phase 0 batch.
3. **§5.1 and §5.4 are corrections to the register itself** and need to be made at source. So does
   the L1005 quotation in §5.3, which is what propagated a vacuous gate into two items.
4. **`BFQ-CONNECTOR` and `RT-CONNECT-PIN-CUTS` both block on `P0-TAG`**, which needs a human to
   push a tag. Rule 0: nothing here did.
5. **The severity of `BFQ-41` + `BFQ-MINIMED` read together.** BF-44 is a concrete shipping way to
   produce the future timestamp that BF-41 says silences the one continuous "my CGM data stopped"
   detector a self-hoster has. Neither item is high on its own account alone.
   [Caveat 2026-09-22: the maintainer states (2026-09-21, operational knowledge, not measured here) that mmconnect / minimed-connect-to-nightscout has been broken for some time, and legacy Dexcom Share is intended to map to nightscout-connect. BF-44/BF-45 were graded assuming mmconnect is live and have not been re-graded.]

## 9. Related documents

| document | relationship |
|---|---|
| [`nightscout-backfix-register.md`](../../30-design/remedial/nightscout-backfix-register.md) | authoritative for **defect facts and ids**. This document never allocates one (rule 4) |
| [`queue/work-queue.yaml`](../../../queue/work-queue.yaml), [`queue/README.md`](../../../queue/README.md) | authoritative for item **state**, because state is measured by a gate rather than asserted |
| [`workflow-completeness-critique-2026-09-15.md`](../programme/workflow-completeness-critique-2026-09-15.md) | §C is the finding this work answers, and §1 above records where its framing needed correcting |
| [`phase0-pr-sequencing-2026-09-15.md`](../../30-design/remedial/phase0-pr-sequencing-2026-09-15.md) | §5 is the ten follow-ups; §5.4 and §5.5 above correct two of them |
