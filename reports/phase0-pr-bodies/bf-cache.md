# B — `bf/cache`: a plain read of ten entries was copying 48 hours of CGM data

> **Base: `origin/dev` `a8888f0d`. This is one of NINE INDEPENDENT PRs. There is no stack — no
> Phase 0 branch is based on another, and this one merges cleanly against `origin/dev` and against
> all eight of the others.**
>
> **No maintainer decision is required for this one.** It is the lowest-risk branch in the set:
> patch-grade, no declared surface moves, and nothing an operator configured behaves differently.

## What changes for you

**Nightscout gets faster on every data reload, and one common API read gets a lot faster.
Nothing you see on screen changes, and no stored data is touched.**

Nightscout keeps a rolling window of your recent data in memory so pages and plugins can read
it quickly. Two things were wrong with how that window was handled:

- **A request for ten recent entries was copying the entire retained window first.** Asking
  Nightscout for `/api/v1/entries?count=10` — which uploaders, phone apps and scripts do
  constantly — made the server duplicate roughly two days of CGM readings in memory in order
  to hand back ten of them. That read is now **about 33 times faster** (0.837 ms to 0.025 ms,
  measured).
- **Two of the three reads in each load cycle were copying the whole window and then never
  writing to it.** The copy existed to stop one caller modifying shared data. Two of the three
  callers do not modify anything, so for them the copy was pure cost.

**Honest about what was not finished:** this branch was given a target of getting the whole
load cycle under 1 millisecond. **That target was not met.** The cycle went from 3.747 ms to
2.657 ms. See "The gate was not met" below for why the rest was left alone — the short version
is that taking it safely needs a proof nobody has produced yet, and guessing would risk
corrupting device status data.

There is no change to what Nightscout displays, what it stores, or what any API returns.

## Technical detail

**T0.2 / BF-06 — `ddcdb1a8`.** An untyped `/api/v1/entries` read cloned the whole retained
window to return ten documents.

| | before | after |
|---|---:|---:|
| `/api/v1/entries?count=10` (untyped read) | 0.837 ms | **0.025 ms** |
| cost relative to a typed read | 42.0x | **0.7x** |

Measured on this machine; **the ordering is the durable claim, the absolute figures are not.**
Across four measurement passes in this programme the ordering of options has been stable while
absolute numbers moved.

**T0.3 / BF-07 — `4f86bab1`.** `cache.insertData` JSON round-tripped the whole retained array.
Two of the three load-cycle reads copy that array and never write to it; those two now take a
reference.

| | before | after | gate |
|---|---:|---:|---:|
| three cache calls, one load cycle | 3.747 ms | **2.657 ms** | **< 1 ms — NOT MET** |

**A dead write was removed.** `lib/data/dataloader.js:203` wrote a `mills` field that nothing
subsequently read. Removed, with a test that fails if it comes back.

### The gate was not met, and why the remainder was left

**98% of the remaining 2.657 ms is `devicestatus`.** The `devicestatus` caller **rewrites
fields in place** on the documents it is handed. Handing it a reference instead of a copy is
therefore only safe if no plugin also writes to a device-status document.

**A grep is not that proof, and this branch does not pretend otherwise.** Device status is
where loop and pump state lives — reservoir, battery, last loop result, the openaps/pump
fields plugins read to decide what to display. Sharing a mutable reference there, wrongly,
would let one consumer's edit appear in another's view of the same document, and the symptom
would be wrong pump or loop information shown to someone managing diabetes. That is not worth
1.6 ms.

**What would close it**: an enumeration of every plugin write path that reaches a
device-status document, or a defensive freeze under test that fails loudly on any write. Both
are real work and neither belongs in a performance PR. The gate is recorded as **not met**
rather than quietly relaxed.

## Evidence

- `docs/60-research/t02-t03-cache-clone-2026-09-15.md`
- Register entries **BF-06** (fixed) and **BF-07** (**partly** fixed) in
  `docs/30-design/nightscout-backfix-register.md`

## Test evidence

- 2 commits: `ddcdb1a8` (T0.2 / BF-06), `4f86bab1` (T0.3 / BF-07).
- 6 files, +385/-8, including `tests/data.cache-clone.test.js` (+260, new) and
  `tests/dataloader.test.js` (+5, the dead-write regression test).
- `npm run test:unit` in `crm-bf-cache`: **371 passing, 0 failing** — the only Phase 0 branch
  whose unit count rises, because `data.cache-clone.test.js` is inside the unit brace list.
- The tests were checked against unfixed code: `tests/data.cache-clone.test.js` copied onto pristine `origin/dev` code fails
  with **8 failing**. `tests/dataloader.test.js` is outside both local test scripts, so it runs
  under CI's `test-ci` but not under `npm run test:unit` — **run the whole tree** to exercise
  the dead-write test.
- `git merge-tree --write-tree --messages origin/dev bf/cache` — **clean**, re-confirmed
  2026-09-15. Clean against all eight other Phase 0 branches.

## Semver

**Patch.** No declared surface moves: no API response changes shape, no environment variable is
added or removed, no default flips. This is the least risky branch in the Phase 0 set and a
reasonable one to land first to exercise the process. Classification from
`docs/60-research/gt4-semver-classification-2026-09-15.md`.

**The operator-visible text above belongs in the release notes.** It is *not* a `CHANGELOG.md`
entry and this branch adds none: under the maintainer's rule, `CHANGELOG.md` is a **release
output** generated by GitHub tooling between releases, and branches never hand-edit it. The "What
changes for you" section is written to be usable verbatim as that source text. **The paragraph that
must not be dropped is the honest one** — that the sub-1 ms gate was *not* met and why the
`devicestatus` remainder was deliberately left alone. A performance note that quotes only the 33x
figure would misrepresent what shipped.

---

## Follow-ups deliberately **not** in this PR

- **The `devicestatus` clone, which is 98% of the remaining cost.** Blocked on proof that no
  plugin writes to a device-status document. This is the named, deliberate remainder of T0.3,
  not an oversight.
- **The limit rule will be written twice** — `lib/server/count.js` and API v3's `parseLimit` —
  on purpose, so each commit lands alone. Unify afterwards. *Two readings of one rule is the
  root cause of this whole family of defects*, so leaving it duplicated is a debt with a name.
  **Correction, measured 2026-09-15: `lib/server/count.js` does not exist on `origin/dev`** —
  `git cat-file -e origin/dev:lib/server/count.js` fails, and it is present only on `bf/reads`,
  which creates it. So the duplication **does not exist today and is created by landing E
  (`bf/reads`)**, not by this branch. The earlier text here claimed the two copies "currently
  agree", which measured a file on `bf/reads` and described it as the state of `dev`. What is
  true: they agree *on `bf/reads`* — same `/^\s*\d+\s*$/` test, same `Number.isSafeInteger && > 0`
  rule, with v3 additionally capping at `API3_MAX_LIMIT` — and they agree from the moment the
  duplication is born, which is exactly why it is easy to forget about. This branch touches
  neither copy.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared
  against `!== null`. No caller, so no register id.
- **`lib/authorization/storage.js` has a second unguarded `console.log` on a request path**,
  same shape as BF-05, different file (`:84` on `origin/dev`; the line moves per branch).
