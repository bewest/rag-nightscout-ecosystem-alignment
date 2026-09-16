# `bf/cache` — a plain read of ten entries was copying 48 hours of CGM data

Two commits on `origin/dev` `a8888f0d`, tip `4f86bab1`. 6 files, +385/−8, of which three are test
files. No `CHANGELOG.md` edit. Merges clean against `dev` and against every other open Phase 0
branch.

**No maintainer decision is required for this one.** It is the lowest-risk branch in the set:
patch-grade, no declared surface moves, and nothing an operator configured behaves differently.
It is also the one that ships with a target it did not hit, stated plainly below.

## What changes for you

**Nightscout gets faster on every data reload, and one common API read gets a lot faster.
Nothing you see on screen changes, and no stored data is touched.**

Nightscout keeps a rolling window of your recent data in memory so pages and plugins can read
it quickly. Two things were wrong with how that window was handled:

- **A request for ten recent entries was copying the entire retained window first.** Asking
  Nightscout for `/api/v1/entries?count=10` — which uploaders, phone apps and scripts do
  constantly — made the server duplicate roughly two days of CGM readings in memory in order
  to hand back ten of them. It now copies only the ten.
- **Two of the three reads in each load cycle were copying the whole window and then never
  writing to it.** The copy existed to stop one caller modifying shared data. Two of the three
  callers do not modify anything, so for them the copy was pure cost.

**Honest about what was not finished.** This branch was given a target of getting the whole
load cycle under 1 millisecond. **That target was not met** — the cycle went from roughly 3.9 ms
to roughly 2.7 ms. "The target that was not met" below says why the rest was left alone; the
short version is that taking it safely needs a proof nobody has produced yet, and guessing would
risk corrupting device status data.

There is no change to what Nightscout displays, what it stores, or what any API returns.

---

## Technical detail

| commit | what |
|---|---|
| `ddcdb1a8` | an untyped `/api/v1/entries` read cloned the whole retained window to return ten documents (**BF-06**, T0.2) |
| `4f86bab1` | two of the three load-cycle reads copy the whole retained window and never write to it (**BF-07**, T0.3) |

### T0.2 — slice first, then clone the slice. Target met.

The read path had two branches that differ by a full deep clone of the cache array. `dev` clones
then slices; this branch slices then clones.

| at `count=10` | `dev` | this branch |
|---|---:|---:|
| untyped read | 0.830 ms | **0.013 ms** |
| typed read | 0.021 ms | 0.018 ms |
| untyped cost relative to typed | **42x** | **0.7x** |

**T0.2's gate is "untyped within 2x of typed at `count=10`". `dev` fails it at 42x; this branch
passes at 0.7x.** That ratio is the durable claim. The absolute figures move between runs — an
earlier pass recorded 0.837 → 0.025 ms — because these are sub-millisecond p50s on a shared
machine. The ordering has been stable across every pass.

### T0.3 — by-reference for the two callers that only read. Target NOT met.

`cache.insertData` JSON round-tripped the whole retained array. Two of the three load-cycle
callers never write to what they get, so they now take a reference; `devicestatus`, which does
write, keeps its copy.

| three cache calls, one load cycle | `dev` | this branch | target |
|---|---:|---:|---:|
| measured 2026-09-15 | 3.747 ms | 2.657 ms | **< 1 ms — NOT MET** |
| re-measured 2026-09-16 | 3.929 ms | 2.656 ms | **< 1 ms — NOT MET** |

Both passes agree on the saving (~1.1–1.3 ms) and on the verdict.

**A dead write was removed.** `lib/data/dataloader.js:203` wrote a `mills` field that nothing
subsequently read. Removed, with a test that fails if it comes back.

### The target that was not met, and why the remainder was left

**98% of the remaining ~2.7 ms is `devicestatus`.** That caller **rewrites fields in place** on
the documents it is handed, so handing it a reference instead of a copy is only safe if no plugin
also writes to a device-status document.

**A grep is not that proof, and this branch does not pretend otherwise.** Device status is where
loop and pump state lives — reservoir, battery, last loop result, the openaps and pump fields
plugins read to decide what to display. Sharing a mutable reference there, wrongly, would let one
consumer's edit appear in another's view of the same document, and the symptom would be wrong pump
or loop information shown to someone managing diabetes. That is not worth 1.6 ms.

**What would close it:** an enumeration of every plugin write path reaching a device-status
document, or a defensive freeze under test that fails loudly on any write. Both are real work and
neither belongs in a performance PR. The target is recorded as not met rather than quietly
relaxed.

Two cheaper observations for whoever picks up the rest:

- **Retention halves it for the default operator.** The ~2.6 ms figure is at `DEVICESTATUS_DAYS=2`
  (579 documents). The default is one day; at ~288 documents the same clone is ~1.25 ms. The bench
  pins `days: 2` deliberately as the worse case, but most sites run the cheaper one.
- **The prize is shaped by the prediction arrays.** Each device status in the fixture carries a
  72-point `predicted.values` array, which is what makes `devicestatus` three times the cost of
  `entries` at the same document count. Dropping prediction arrays from the *cached* copy would
  take most of it — but the cache is also what serves API v3 reads, so a lossy cache is a larger
  decision than this task.

## Verifying it

```
npm run test:unit                          # 371 passing, 0 failing

# the two performance targets, re-runnable:
NS_ROOT=$PWD node --expose-gc tools/mt-bench/apitier.js read    # T0.2 gate -> PASS (0.7x)
NS_ROOT=$PWD node --expose-gc tools/mt-bench/apitier.js cycle   # 2.66 ms, target < 1 ms -> NOT MET
```

The bench reads the live call sites out of the tree and names the shape it found
(`clone-then-slice` on `dev`, `slice-then-clone` here), and throws on a tree it cannot recognise,
so it cannot report this branch's number for `dev`'s code. Fixture: 576 entries (183 KB JSON), 600
treatments of which 361 survive the retention filter, 576 device statuses, `DEVICESTATUS_DAYS=2`.

`tests/data.cache-clone.test.js` is new and inside the unit brace list — this is the only Phase 0
branch whose unit count rises. Copied onto pristine `dev` code it gives **8 failing**.
`tests/dataloader.test.js`, which carries the dead-write regression, is in neither local script and
runs only under `npm test`.

## Semver: patch

No declared surface moves: no API response changes shape, no environment variable is added or
removed, no default flips. The "What changes for you" text above is the release-note source; this
branch adds no `CHANGELOG.md` entry.

**The paragraph that must not be dropped is the honest one** — that the sub-1 ms target was *not*
met and why the `devicestatus` remainder was deliberately left. A performance note quoting only
the read-path win would misrepresent what shipped.

## Follow-ups deliberately not in this PR

- **The `devicestatus` clone, which is 98% of the remaining cost.** Blocked on proof that no
  plugin writes to a device-status document. This is the named, deliberate remainder of T0.3, not
  an oversight.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared
  against `!== null`. No caller today, so nothing observable.
- **`lib/authorization/storage.js:84` has an unguarded `console.log` on a request path**, printing
  request-derived values. Not introduced by this branch and not in a file it touches. It is
  repaired on the `bf/auth` branch, which is not yet open as a PR, so it is still live on `dev`.
