# nightscout-connect v0.0.14 — contents

**Status: DRAFT for maintainer review. Contributor-facing; full technical depth intended.**
Nothing has been pushed, published or `npm publish`ed. The tag exists **locally only**.

> **Status 2026-09-22: superseded. The local `v0.0.14` tag and `release/v0.0.14` branch are
> retired and must not be pushed** (delete the tag with `git tag -d v0.0.14` before tagging the
> real release). Six of the seven commits below are in connector `official/dev` `d208c7d`, through
> PR #64, which carried #61, #66 and #67; the seventh, `c1cce2a`, is PR #68, under review. The
> release is connector `dev`, tagged; current state is queue item **P0-TAG** in
> [`queue/work-queue.yaml`](../../queue/work-queue.yaml). This file describes the prepared tag
> as it was; its figures are about `649a7de`. `cgm-remote-monitor` dev pins `234d47c` (see
> [`../cgm-remote-monitor-15.0.9/contents.md`](../cgm-remote-monitor-15.0.9/contents.md)).
>
> Complements the generated changelog. The changelog is authoritative for *what merged*;
> this file is the record of *what the release is made of and what is unsettled about it*.

## Identity

| | |
|---|---|
| Repository | `nightscout/nightscout-connect` |
| Tag | `v0.0.14` — **annotated**, exists locally at `externals/nightscout-connect`, **not pushed** |
| Commit | `649a7de27b9e869154e718b0ec1d1bfa0388d0d8` |
| Branch | `release/v0.0.14` (the only local branch containing the commit) |
| Previous release | `v0.0.13` = `b394411` |
| `tag-message.txt` | **byte-identical to the live local tag body** (`diff` clean, verified) |

`git diff --stat c1cce2a release/v0.0.14` is `package.json` + `package-lock.json`, version
bump only — so the connector's own test run at `c1cce2a` (`externals/work/nc-jitter`,
`node --test`: 135 tests, 135 pass, 0 fail) covers exactly the code this tag ships.

## The seven commits since v0.0.13

Measured with `git log --oneline --no-merges v0.0.13..v0.0.14`.

| Commit | Subject | Register |
|---|---|---|
| `9fa2c3c` | Prevent Dexcom credentials and sessions from reaching runtime logs | BF-42 |
| `5349d47` | Keep MiniMed credentials and patient data out of runtime logs | BF-42 |
| `8406edf` | Preserve MiniMed glucose and measurement-time status contracts | (see below) |
| `77e2396` | Keep internal output payloads out of runtime logs | BF-42 |
| `51b6e6e` | Release connector listeners and settle output waits on stop | — |
| `234d47c` | Make embedded connector debug logging opt-in | BF-42 |
| `c1cce2a` | Every retry interval was 256 ms, and the first cycle had no jitter | **BF-34**, **BF-08** |

Plus `649a7de`, the version bump, and four merge commits.

`8406edf` is the one to read hardest. It changes what the MiniMed source reports as glucose
and as measurement time — a data-correctness change on a **CGM ingestion path**, in a
release that is otherwise security and retry work. It carries two fixes:

- the `sg !== 0 && kind === 'SG'` filter, absent from `v0.0.13` and from `dev`'s pin.
  Without it, CareLink gap sentinels are ingested as `sgv: 0`. Reproduced elsewhere in this
  programme: the same payload yields `[0, 120, 0]` on the older pins and `[120]` here and on
  the retired legacy package. **A sentinel zero is not itself alarmed, but while it is the
  newest entry it makes `lib/plugins/simplealarms.js` skip the entire high/low evaluation**
  (`lastSGVEntry.mgdl > 39`). That is the safety-relevant half and it is why this commit
  belongs in the operator notes rather than only in the changelog;
- `devicestatus.created_at` stamped from the measurement time rather than `(new Date())`.

## What the release delivers, and to whom

**The delivery mechanism is decision 2 (push the tag), not decision 3 (`npm publish`).**
Every `cgm-remote-monitor` pin is a GitHub tarball URL; nothing in the Nightscout tree
resolves `nightscout-connect` from the npm registry. Verified by reading `package.json` at
each ref.

| `cgm-remote-monitor` ref | pin | of the 6 post-v0.0.13 fixes |
|---|---|---|
| `origin/master` (15.0.8 — **what operators run**) | `refs/tags/v0.0.13.tar.gz` | **0** |
| `origin/dev` (15.0.9 candidate) | `234d47c8` | **0** |
| parcels 1, 2, 3 | `refs/tags/v0.0.13.tar.gz` | **0** |
| parcel 4 `chore/mime-exposure-review` | `c962a13f` | 4 |
| parcel 5 `chore/nightscout-modernization` | `b77e5bb` | 5 |
| **`bf/connect-pin`** (unpushed) | `refs/tags/v0.0.14.tar.gz` | **6** |

Re-measured for this document with `git merge-base --is-ancestor <commit> <pin>` for each
of `9fa2c3c`, `5349d47`, `77e2396`, `8406edf`, `51b6e6e`, `c1cce2a` against `234d47c8`,
`649a7de` and `c962a13f`. Reproduces the published table exactly. **`v0.0.14` is the first
ref carrying all six.**

## ⚠ Correction: the security headline is true of `master`, not of `dev`

**The brief this document was written from says v0.0.14 "carries three log-redaction fixes
absent from the currently-pinned commit". That is true of the *commits* and misleading
about the *effect on `dev`*, and the distinction changes who the headline is for.**

Measured — **reproduced**, by writing an independent comment- and literal-stripping scanner
and running it over `git archive` extractions of four revisions
(`tools`: scratch script; counts are *live `console.*` call sites* / *those passing a
non-literal argument*, over `index.js` + everything under `lib/`):

| revision | carried by | live / dynamic |
|---|---|---|
| `v0.0.13` (`b394411`) | **`origin/master` (15.0.8)** and parcels 1–3 | **112 / 101** |
| `234d47c8` | `origin/dev` (15.0.9 candidate) | **22 / 20** |
| `c962a13f` | parcel 4 | 108 / 44 |
| **`649a7de` (v0.0.14)** | `bf/connect-pin` | **22 / 20** |

Three findings, all reproduced:

1. **`dev`'s pin has already deleted the leaking call sites.** `234d47c8` is an 18-file
   rewrite introducing `lib/logging.js`; `lib/sources/minimedcarelink/index.js` goes from
   51 sites to none, `librelinkup.js` from 9 to none, `index.js` from 5 to none. So
   `dev`'s tree and `v0.0.14`'s tree have **identical log surfaces** — same five files,
   same counts. The three redaction commits reach `dev` as a merge, not as a behaviour
   change. **The commits are absent from `dev`'s pin; their effect is not.**
2. **The leaking pin is `master`'s.** 112/101 with no guard —
   `grep -rniE "if *\(.*(debug|verbose)"` returns nothing. That is **BF-42**, it is what
   every operator on 15.0.8 is running today, and it is the audience the headline is for.
   Parcels 1–3 pin the same tag, which is **BF-65**: the adopted train ships the leaking
   connector to upgraders first.
3. **Parcel 4's pin is a partial fix, and not monotone.** 108/44 — the MiniMed block is
   *commented out* rather than rewritten (47 sites, 0 dynamic), `internal.js` is redacted
   (7/0), but **`librelinkup.js` still leaks at 9/8** there and `index.js` still has one
   dynamic site. Redaction does **not** improve monotonically with release order.

**Non-vacuity of the scanner** (house rule 2): it is not a check that cannot fail. It
returns 112/101 on the leaking tree and 22/20 on the redacted ones, and it correctly
reports parcel 4's commented-out MiniMed block as 47 live calls with **0** dynamic
arguments — so it distinguishes *deleted* from *commented out* from *present*, which is
the discrimination the claim rests on.

**Provenance:** source census, executed. **No vendor account exists on this machine and no
live run against any vendor was made.** The census cannot tell you how often a leaked
credential is actually used; it tells you the lines are printed.

## Residual leak in this release

`lib/outputs/nightscout.js:20` in `v0.0.14` is still
`// TODO change this, exposes secret in logs` followed by
`console.log("SETTING UP nightscoutRestAPI", config)`, where `config` carries the
Nightscout API secret. Fifteen sites, fourteen dynamic, in that file alone.

**Not reachable from `cgm-remote-monitor`** — `index.js:71-72` hardcodes
`var internal = { name: 'internal', logger: log }` and selects the `internal` output, so
the `nightscout` output is never constructed on the embedded path. Read at the tag, not
executed; **a reviewer should confirm there is no other construction path** before the
release notes' "standalone users only" sentence is relied on. Affects standalone CLI users.

## Register entries

| Entry | State | Delivered by |
|---|---|---|
| **BF-34** — every configured retry interval discarded (`{...config, ...defaults}`), 586× too fast, `use_random_slot` forced false | fixed | `c1cce2a` |
| **BF-08** — no start jitter; a pool reaches the vendor inside one second on restart | fixed | `c1cce2a` |
| **BF-42** — the connector every operator runs logs credentials unconditionally | **only for consumers that move to this tag** | `9fa2c3c`, `5349d47`, `77e2396`, `234d47c` |
| **BF-65** — the train ships the leaking connector to upgraders first | **not fixed here.** Requires parcels 1–3 to move their pins. Same one-line change as `bf/connect-pin`; all three pin the v0.0.13 *tag* | — |
| **BF-43** — `master` forces `axios 1.16.0` into a connector declaring `^1.18.1`, suppressed by `overrides` | **not fixed here.** Must be reconciled if `master`'s pin moves | — |

### ⚠ BF-34's register entry is incomplete in a way that matters for the notes

The entry records the 586×-too-fast retry. The same `{...config, ...defaults}` merge
**also** makes the ceiling 74.6 hours on the *pinned* connector, because `exponent_ceiling`
caps the **exponent**, not the delay: with the discarded caller interval (I = 256 ms),
attempt ≥ 20 gives 256 × (2²⁰ − 1) = 74.6 h. So one defect produces a retry storm first and
a three-day dark window second, and **both halves ship on `dev` today.** `v0.0.14`'s
builder caps the cycle at 30 minutes and the frame at 5 minutes, which closes both.

The dark-window half is the one that stops a person's data, and it is the stronger argument
for moving the pin than the storm is. It is **not** in the register entry as written; it is
raised in `docs/60-research/modernization/e1-dexcom-path-comparison-2026-09-15.md` and is listed in this
document's return value as a correction rather than edited into another agent's file.

### BF-08 needs no operator note

Both jitter windows default to `0`. **Reproduced** by executing `jitter_window()` from
`index.js` at the tag: `undefined`, `''`, `'-1'` and `'abc'` all return `0`; `'5000'`
returns `5000`. An operator who sets neither `CONNECT_START_JITTER_MS` nor
`CONNECT_INTERVAL_JITTER_MS` sees no change. One line in the notes for completeness, no
more.

## BF-34's measured figures, with their methods attached

House rule 9: the **orderings** are durable, the absolutes are machine- and
method-specific.

| Figure | Method |
|---|---|
| **585.94× exactly** (150000 ÷ 256) at every attempt below the ceiling — a constant, not an average | both versions of `lib/backoff.js` executed |
| Shipped ceiling **30 minutes** for `dexcomshare`, `minimedcarelink`, `glooko` and `nightscout` — `lib/builder.js:89` supplies `max_interval_ms = expected_data_interval_ms × 6` and each declares `5 × 60 × 1000` | read + executed |
| **`librelinkup` is the exception**: it derives the interval from `opts.linkUpInterval × 60 × 1000`, so its ceiling is *the operator's interval × 6* and is **not** 30 minutes unless the interval is 5 | read |
| **3 s → 67 s** for 100 actors delivering the same 800 requests, upstream refusing authentication | T0.4 author's harness, on this machine. **Not re-measured for this document** |
| 400 actors, busiest second **400 → 15** (BF-08) | T0.4 author's harness. Not re-measured |
| Delay at the ceiling spreads over [15 min, 30 min] with `jitter: 'equal'` — 2,000 samples at attempt 10 fell in [900,351 ms, 1,799,757 ms] | executed |

## The version number is not settled

`docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md` §4.3 argues this should
be **`0.1.0`, not `0.0.14`**, on the rule that below 1.0.0, `y` is read as the major. Five
caller-visible changes, each independently breaking, measured by executing `lib/backoff.js`
at both revisions:

1. option precedence reversed — `{...config, ...defaults}` → `{...defaults, ...config}`;
2. a changed default — `use_random_slot: false` → `jitter: 'equal'`;
3. a new throw — `backoff({jitter:'wild'})` now throws `backoff: unknown jitter mode "wild"`;
4. a new option, `max_interval_ms`;
5. `duration_for` is now non-deterministic where it was deterministic.

**Nothing resolves by range**, so the number changes no consumer's resolution — its entire
job is to make a human stop. If the maintainer keeps `0.0.14`, the policy requires a
`BREAKING` section in these notes, because the number will not carry it. The notes above
carry (1) and (2) in operator language; **(3), (4) and (5) are not in the operator notes
and do not belong there** — they are visible only to code that calls `backoff()` directly,
which is the connector itself.

**If the maintainer takes the `0.1.0` recommendation**, this entire directory is renamed,
the local tag is re-cut, and `bf/connect-pin`'s one-line URL changes. **That decision must
be made before the tag is pushed, not after** — a pushed tag is superseded, never moved.

## Sequencing — what must happen in what order

From `docs/30-design/remedial/maintainer-release-brief-2026-09-15.md` §2 and §3. Each step is run by
a **human**; none has been run.

1. Decide the number (`0.0.14` or `0.1.0`). Re-cut the local tag if it changes.
2. Fast-forward `nightscout-connect` `main` to the release commit and push the tag.
   **Fetch first** — `origin/main` in this checkout is a cached remote-tracking ref and
   nothing here has contacted GitHub. The **local** branch `main` in that checkout is 28
   commits behind `origin/main`; do not push it and do not use it in the fast-forward check.
3. **Only then** regenerate `bf/connect-pin`'s `package-lock.json` with `npm install`, in
   the same PR. The lock's `integrity` is a hash over a tarball GitHub does not generate
   until the tag exists. **A locally invented hash breaks `npm ci` for everyone; a stale
   lock fails `npm ci` loudly, which is the correct failure.**
4. `npm publish` is a separate, optional decision. It does **not** gate this batch.
   Whether the package is currently published on npm at all could not be checked — this
   machine has no network egress by rule.

## What a reviewer must verify before this is relied on

1. That the `nightscout` output really is unreachable from the embedded path (read, not
   executed) — the "standalone users only" sentence in the notes depends on it.
2. `8406edf`'s MiniMed contract change against a **real CareLink account**. It is a
   data-correctness change on a CGM ingestion path and no live account exists here.
3. Whether the Dexcom session-invalidation window in the notes' Known Issues is a rare edge
   case or the normal case. Its severity is entirely a vendor-behaviour question and is
   unanswerable from source.
4. The 3 s → 67 s and 400 → 15 figures, if they are to be quoted publicly. Both are
   inherited from T0.4's harness and were not re-measured here.

---

*Draft, 2026-09-15. Prepared locally. Nothing pushed, tagged, merged or published. Requires
maintainer review before the tag is pushed or these notes are published.*
