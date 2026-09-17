# dev-cycle review harness — plan

*Contributor-facing, technical throughout. Drafted 2026-09-17. Requires maintainer review
before any of it is executed against a branch that will be pushed.*

How to review the ten `dev-candidate` pull requests by merging them into an integration
branch, running a real local Nightscout against each state, piping data in, and judging the
result in a browser and with probes.

**Evidence convention.** Every quantitative claim is tagged `[measured]` (reproduced during
this session, command and output recorded), `[refuted]` (a claim an earlier draft made that
was tested and found false), or `[ASSUME]` (read-derived, unverified — must be measured
before anything depends on it). A claim with no tag is a design decision, not a measurement.

---

## 0. How this document was produced, and why that matters

A fifteen-agent workflow ran five reconnaissance lenses, three independent designs, three
scoring lenses, a synthesis, and three adversarial refutation passes. **All three refuters
rejected the synthesized plan**, producing 31 confirmed refutations and 34 required
amendments. This document is the synthesis *after* those amendments.

That outcome is the most useful thing here. The first plan's per-branch acceptance criteria
looked rigorous and were largely broken — thresholds stuck red on the *correct* build,
checks green on the *broken* build, one config key that disables the feature it tests. None
of that was visible by reading. All of it was visible by running.

So: **no criterion in §5 ships until its red state has been executed, not reasoned about.**
That is §5's meta-gate, and it is the single most important line in this document.

---

## 1. The answer: evaluate between each merge

**Evaluate between each merge. Do not merge all ten and bisect.** Not because bisect is
slow — it is cheap here — but because bisect cannot express the one failure mode this set
actually has, and because the machine-time it saves is worth less than a minute.

| Measure | Value | Tag |
|---|---|---|
| Pairwise conflict matrix | 66 of 66 pairs merge clean; forward and reverse order produce the identical tree. Negative control did print a real `CONFLICT (content)` in `lib/server/entries.js`, so the matrix is not vacuous. | `[measured]` |
| Per-state cycle cost | **17–20 s**, measured as boot-to-`/devbundle`-200, not boot-to-listening. Cold babel cache: listening 1019 ms, usable 7843 ms. Two instances compiling concurrently: 11 s. | `[measured]` |
| `npm ci` needed | **Zero times.** `package-lock.json` is byte-identical across all ten candidates. | `[measured]` |
| Machine time bisect saves | **~50 s** over the whole cycle. | `[measured]` |

An earlier draft claimed a 10 s cycle and a 6-minute bisect saving. Both were wrong — the
components summed to 3.6 s, and the 6 minutes came from an 87 s cycle that included a full
mocha run the plan itself forbids. `[refuted]` The decision is unchanged and in fact
strengthened: **50 seconds of machine time is not a decision variable; a bounced correct PR
is.**

### The failure mode bisect cannot express

`bf/coercion` and `bf/reads` both rewrite the same five `lib/server/` collection modules.
They merge clean in both orders. But the defect is *the absence of a partner branch*, which
is not a prefix of any merge sequence — so no bisect over merge prefixes can name it.

This claim went wrong twice before it went right, which is worth recording. An early draft
called `bf/reads`-without-`bf/coercion` "strictly worse than dev" on the strength of an
inverted `$exists` result set; a refuter knocked that down by showing the count endpoint is
uniformly dead on dev, so `bf/reads` could only be an improvement. **Both were reasoning about
the wrong surface.** Measured on a live seed, the half-merged state returns a confident
`count=5` where the true answer is `577` — see §1a, *RESTORED, on better evidence*.

**So the atomic merge is justified by measurement, not only by risk containment**, and the
`PAIR-WHOLE` arm detects a half-merge directly rather than relying on merge discipline.

---

## 1a. Priority — what this cycle is for

**Scope, confirmed 2026-09-17: remedial/backfix only. No modernization.** That is the ten
`dev-candidate` PRs and nothing else. `#8605` (`chore/nightscout-modernization`), the release
train, and the `help wanted` PRs that are features rather than defect fixes are all out.

Ranked by what the register measures — severity × `ships_to_operators_today` — not by merge
mechanics. Every entry below is `ships=yes`: present for every operator running today's
release.

| Tier | Unit | Register weight | Why here |
|---|---|---|---|
| **1 — clinical** | `bf/food` #8735 | BF-35 **high**, BF-16 medium | The only unit in the set adjacent to a dose. **Urgency unsettled** — see §7: `loadFoodQuickpicks` runs once at client init, before food arrives, so whether a user reaches the populated-and-broken chooser is an open question the browser session is meant to answer. The bolus calculator's quick-pick chooser builds its option list from the whole food collection but resolves the selection against the *filtered* array, so **picking one quick pick loads a different one's carbs**. Highest consequence per unit of code in the cycle. |
| **1 — correctness** | `bf/reads` + `bf/coercion` #8738 + #8737 | 7 **high** between them: BF-01, BF-13, BF-14, BF-33, BF-02, BF-03, BF-11 | Wrong answers under HTTP 200, silent data loss in v3 paging, and three unbounded-read paths. The largest concentration of high-severity register weight in the set, and already one atomic unit for the reason in §1. |
| **2 — availability** | `bf/parms` #8736 | BF-37 **medium–high**, BF-38/39 low | A valueless URL parameter throws in the *first statement of `client.init`* — total silent page failure, nothing on screen but the loading message. |
| | `bf/merge` #8734 | BF-36 medium | The throw escapes into `dataUpdate`, which has no `try`/`catch`; the page stops advancing until reloaded. |
| **3 — alarms** | `bf/alarms` #8739 | BF-28/29 medium, BF-31 low–medium | **`minor`.** Maintainer ruling 2026-09-17: the per-request locale handling on `/api/v1/alexa` and `/api/v1/googlehome` is a **defect, not a capability**. `ctx.language.set` and `moment.locale` are process-global, so a request carrying `request.locale` re-languaged every later request for every other user — never the intent. Removing it is a correction, and the branch needs an ordinary review. The earlier `major` capability-removal grading is withdrawn. |
| **4 — performance** | `bf/cache` #8740, quadratics #8733 | BF-06/07 medium (CPU); quadratics carries no register entry | No wrong answers. Correctness checks pass on both the broken and fixed builds, which is why their acceptance is a *shape* assertion in §5. |
| **5 — no register weight** | `#8741`, `#8729` | none | Neither carries a register entry. `#8741`'s real credential path cannot be exercised without live Dexcom credentials; `#8729` has no falsifiable criterion at all (§7). Land them on maintainer judgement or defer. |

**If the cycle has to be cut short, tiers 1–2 are the release.** They carry every `high` in the
set and all four silent-wrong-answer classes.

### ✅ RETRACTED: #8737 does fix BF-40 — measured 2026-09-17

**An earlier revision of this document claimed #8737's title overstated its fix. That claim
was wrong and is withdrawn.** It was read-derived: `bf/coercion` puts `$exists` in
`NON_VALUE_OPERATORS` in `query-coercion.js`, which I read as "the operand stays the string
`'false'`". That exclusion is a *different* mechanism — it stops the field-domain coercer
mangling the operand. The actual fix is `BOOLEAN_OPERANDS` / `readBooleanOperand` in
`lib/server/query.js`, applied over the **built query** precisely so it also covers fields the
type table does not name.

Measured on a live 582-document seed (577 sgv, 5 mbg), `find[mbg][$exists]=false`:

| surface | BASE | COERCION | READS | PAIR |
|---|---|---|---|---|
| `GET /api/v1/entries.json` (list) | **5 ✗** inverted | **577 ✓** | **5 ✗** inverted | **577 ✓** |
| `GET /api/v1/count/entries/where` | `[]` dead | `[]` dead | **5 ✗** inverted | **577 ✓** |
| `count/where find[type]=sgv` | `[]` dead | `[]` dead | 577 ✓ | 577 ✓ |

**`BFQ-40` in the queue is therefore wrong**, not merely stale: its `blast_radius` locates the
fix at `query-coercion.js:90`, which is the wrong file, and its `operator_visible` text says the
defect "stays wrong after the query type-conversion fix". Measurement refutes both. The row
should move off `not-started`. *(This is the register's own read-or-run rule catching the
register — and then catching this document.)*

### ⚠ RESTORED, on better evidence: `bf/reads` alone IS strictly worse than dev

§1 withdrew the "strictly worse" claim because it rested on the list endpoint, where dev is
merely inverted rather than dead. On the **count** surface the claim holds, and now with a
measurement:

- **dev**: `/api/v1/count/entries/where` returns `[]` for *every* filter. Uniformly dead, and
  obviously so — nothing downstream can mistake it for an answer.
- **`bf/reads` alone**: returns a confident `count=5` for a filter whose true answer is **577**.

A plausible wrong number is worse than a visible failure. This is the strongest argument in the
cycle for the atomic merge, and it is the one thing no amount of reading produced — both earlier
attempts at this claim, in both directions, were wrong.

The `PAIR-WHOLE` arm in `tools/review/probes/pair-reads-coercion.js` is the detector: green only
on the pair, red on BASE (dead), red on `READS`-only (inverted), red on `COERCION`-only (dead).


---

## 2. Merge order

Ten merge units onto a scratch integration branch `rc/2026-09-dev-cycle`, each landing as
exactly one `git merge --no-ff` commit. Two properties follow, and both are required by the
**skip-and-continue** policy:

- `git revert -m 1 <sha>` is the entire undo for any unit.
- `git log --first-parent` is a ten-line ledger of what is in the build.

**Skip-and-continue, concretely.** When a unit fails its check, drop that unit and replay the
remainder onto the last-good integration state. Do not revert in place — a revert leaves the
failing merge in the first-parent ledger and every later probe then runs against a tree that
contains both the defect and its undo. Replay keeps the ledger honest. Record the skipped
unit and its evidence, and carry on.

```
 1. bf/coercion + bf/reads   ── ATOMIC UNIT ──   (#8737 + #8738, one commit, three parents)
 2. bf/cache                                     (#8740)
 3. fix/quadratic-treatment-processing           (#8733)
 4. #8741  wip/dtschida/env-credential-coercion
 5. bf/parms                                     (#8736)
 6. bf/merge                                     (#8734)
 7. bf/food                                      (#8735)
 8. bf/alarms                                    (#8739)
 9. #8729  wip/fix-chart-container-height-race
```

Nine units, not ten, because units 1 and 2 of the original ten are the atomic pair. `bf/auth`
and `bf/throttle` are **out of scope** for this cycle per your decision — they have no PR
open, and including them would have made the `lib/authorization/storage.js` overlap a third
entanglement to manage.

> The atomic merge commit has **three** parents, not two. `git revert -m 1` still works
> (verified rc=0). A reviewer counting parents should not think the merge went wrong.

### REAL constraints — violating these produces a measurably wrong build

- **`bf/coercion` + `bf/reads` land as ONE commit.** Not "adjacent", not "same push". One
  commit, so the half-merged state is unreachable by construction rather than avoided by
  discipline. Git is structurally blind to the coupling: the two branches share no file in
  `lib/server/aggregate.js`, where `bf/reads` rewires `find_options(opts)` → `api.query_for(opts)`
  and `bf/coercion` is what makes the operand arrive typed. `[measured]`

### TIDY constraints — chosen for observability; changing them changes nothing

- **`bf/cache` after `bf/reads`** was listed as REAL in an earlier draft. Tested: `bf/cache`
  alone is byte-identical to BASE on `count=0`, `abc`, `-3`, `0x10`, `1e2`, `99999` across
  both the in-memory and mongo paths, and 40 bad-count reads left the cache unperturbed.
  There is no reachable red, so it cannot sit in a section promising a measurably wrong
  build. `[refuted]` → demoted to TIDY.
- **Client-bundle branches (5–9) as a trailing block.** Measured from webpack's own `--json`
  module graph: `lib/client/*`, `lib/language.js`, `lib/food/*`, `lib/plugins/insulinage.js`,
  `lib/plugins/index.js`, `lib/data/ddata.js` are **in** the bundle; `lib/data/calcdelta.js`,
  `lib/data/dataloader.js`, `lib/server/*` are **not**. `[measured]` That is the opposite of
  what the `lib/data/` path suggests, and it decides which units need a rebundle.
- **`bf/parms` first among the client block.** On dev a bare query-string option stops the
  page at the loading message, so until it lands, every later browser observation on an
  adversarial URL is uninterpretable.
- **`#8729` last.** It is the only unit with no falsifiable browser criterion (§7). Last =
  shallowest skip.

### Procedural

- **`#8605` will break.** GitHub reports it `MERGEABLE`, but that is measured against a dev
  that stops existing the moment unit 1 lands: it conflicts with 7 of 12 candidates
  individually and with the full integration in 8 files. `[measured]` **Tell its owner now.**
  This is a message the plan sends, not a merge it attempts.
- **Nothing here pushes.** The integration branch lives in a scratch clone, pinned to
  `a8888f0d` **by SHA** — the local `dev` inside `externals/cgm-remote-monitor-official` is
  810 commits behind, and a clone of it resolves `origin/dev` to a stale commit. `[measured]`

---

## 3. The harness

`tools/review/` — the namespace is free; `harness-*` is already taken by 7 Makefile targets
belonging to the AID cross-validation rig. `[measured]`

Everything is expressed as a queue gate so the existing machinery (`make queue-status`,
`vacuity.py`, `emit_packets.py` → reviewer packets) picks it up for free. Node gates
`require('./_gate')` and call `report()`.

**Two things this must not hang off.** `make conformance` exits 2 today with three of four
scenarios carrying zero assertions. And `npm test` — though not for the reason an earlier
draft gave. That draft said six added test files "glob into neither brace list"; in fact
`npm test` is `mocha ./tests/*.test.js` with *no* brace list and runs all of them. The brace
lists belong to `test:unit`/`test:integration`. Only `#8729`'s `tests/client-core/` file
escapes `npm test`. The correct count is 24 files added, 7 matching neither brace list.
`[refuted]` The *conclusion* still holds, for a better reason: see the baseline problem below.

### Gate lifecycle — decide this before writing probes

`status.py` invokes gates as `subprocess.run(["bash","-c",cmd], cwd=cwd, …)` with **no `env=`**
and a 600 s timeout. Of 128 existing `run:` entries, **zero** boot a server, bind a port, or
issue a request. `[measured]` There is no prior art and no setup/teardown hook. So decide
explicitly:

- **If gates attach** to instances `nsctl` started, every parameter must come from a file the
  run manifest names — never ambient env — or the gate is reproducible only by the operator
  who exported the variables.
- **If gates self-boot**, budget ~8–11 s of dev-bundle compile each, and expect
  `make queue-status INTEGRATION=1` to take 5–7 minutes. Say so in the packets so nobody
  kills it thinking it hung.

### Build order — thin first

An earlier draft sequenced 8.25 person-days of probe authoring **before the first merge**.
Against a request that was "merge a branch, restart the server, run some synthetic data
generation tools, and test in my browser", that is the wrong shape, and its realistic failure
is abandonment around branch four. `[refuted]` Inverted:

| Stage | What | Effort |
|---|---|---|
| **S0** | `nsctl.sh` — lifecycle for concurrent instances. See the four process hazards below; all four are measured, all four are silent. | 1 d |
| **S1** | `seed.js` — POST a complete self-consistent instance through the real HTTP API. Profile **first**. | 2 d |
| **S2** | **Land units 1–3 using the 42 probe scripts already written** (`tools/review/probes/`). Prove the loop end to end before building any more of it. | — |
| **S3** | `provenance.js`, `ratchet.js`, queue wiring — *only after* three merges have proved the loop. | 2.25 d |
| **S4** | `browser.js` + per-unit cards; `index.html` review page. | 1.75 d |

The 42 probe scripts preserved at `tools/review/probes/` already reproduce every one of the
twelve defects. They are the reason S2 comes before S3.

### Four measured process hazards `nsctl` must handle

Each of these is silent, and each cost an agent real time this session:

1. **Servers launched as plain background children die with the invoking shell.** Two servers
   answered HTTP 200 and served 11 MB bundles during one call and were gone by the next, with
   no error in their logs. Launch under `setsid … </dev/null`. `[measured]`
2. **`echo $!` after `( … & )` records the subshell, not node.** Recorded 3005504 while the
   actual listener was 3005505. A PID file written that way kills the wrong process or
   nothing. Discover the PID by querying the bound port. `[measured]`
3. **A shared `node_modules` symlink target must itself be named `node_modules`.** With
   `worktree/node_modules -> /path/shared_nm`, the server dies at boot with
   `Cannot find module 'jws'`, because Node resolves to the realpath and then has no
   `node_modules` to walk up into — while `require.resolve` from the worktree still succeeds,
   which makes it debug like a corrupt install. Confirmed causal in both directions.
   `[measured]`
4. **Kill-by-PID is not enough.** Discovering PIDs by port or cwd prefix reached three servers
   belonging to *sibling agents in the same scratchpad*. Allocate a port block per run, stamp
   a run id into each child's environment and working directory, and refuse to kill, drop a
   database, or write into `node_modules/.cache` for anything not carrying that run id.
   `[measured]`

### Bundle isolation — the gate an earlier draft got backwards

That draft proposed asserting that two worktrees on one shared `node_modules` serve different
bundles. In dev mode that gate **cannot fail**: `webpack-dev-middleware` is mounted with
`publicPath` only, no `writeToDisk`, so `/devbundle` is served from memory and the on-disk
cache is never touched (md5 unchanged before and after two dev servers ran). `[refuted]`

The real hazard is in production mode, and it is live: one `npx webpack --mode production` in
**one** worktree moved the shared on-disk bundle's md5, and every sibling instance symlinked
to that `node_modules` then serves that worktree's client code at `/bundle`. `[measured]`
Also note the four existing `crm-*` worktrees all symlink to `crm-bf-reads/node_modules` —
there is one shared bundle file behind four worktrees, not four.

**Gate:** hash `node_modules/.cache/_ns_cache/public/js/bundle.app.js` into the run manifest
before and after every state and fail the run if it changed; or give any production-bundle
state its own private `node_modules`.

### Baseline capture — do not use the suite exit code

Two runs of the exact `test:unit` file list produced **no passing/failing epilogue at all**.
The `--exit` form exited 0 while its log contained a 25002 ms `verifyauth` timeout; the
no-`--exit` form left mocha workers alive past reported completion. `[measured]` Capturing
the baseline by exit code records GREEN, after which any later red looks like a regression
the first merge caused. **Capture per-file verdicts with an explicit timeout.**

---

## 4. The data plan

This section survived the adversarial pass almost intact — it is the strongest part of the
original synthesis.

### De-identification rule, in one sentence

> **Nothing derived from `externals/ns-data` or `externals/ns-parquet` may reach a running
> Nightscout, a screenshot, a reviewer packet, a log line, or the git index except as a
> numeric measurement or a timestamp, passed through a single allowlist that emits only the
> named fields per collection and drops `_id`, `device`, `identifier`, `enteredBy`, `notes`,
> `userEnteredAt` and every unnamed string unconditionally.**

Allowlist — **entries**: `date`, `dateString`, `type`, `sgv|mbg|cal`, plus a synthesised
`device: "synthetic://review/<unit>"`. **treatments**: `created_at`, `eventType`, `insulin`,
`carbs`, `duration`, `rate`, `absolute`, `percent`. **devicestatus**: `created_at` plus the
re-nested numeric subtree. **profiles**: the schedule arrays, `dia`, `timezone`, `carbs_hr`,
`delay`. `delta` and `direction` are **recomputed** from the sgv series, never passed through
(null in 79% and 9% of rows). `[measured]`

This has to be strict because **`ns2parquet` performs no de-identification of record
content**: 17 functions in `normalize.py`, none redact. The only pseudonymisation is opt-in,
applies to the patient *label* only, and is an unsalted truncated SHA-256 of a lowercased
directory name — reversible by enumerating candidates. `[measured]`

> **Correction to a recon finding.** An earlier draft flagged the 32 git-tracked files in
> `tools/ns2parquet/fixtures/` (5.8 MB) as real patient data carrying identifiers, and
> proposed pointing the hygiene gate's red control at them. I tested that directly: the
> `_id` values are random hex, not MongoDB ObjectIds — only 9% decode to a plausible
> creation time, and the year distribution is uniform, matching random uint32 rather than a
> patient's usage period. No emails, no digit runs ≥ 7, `device`/`enteredBy` ≤ 20 chars,
> `notes` ≤ 9 chars. **Those fixtures are synthetic.** `[refuted]` The hygiene gate still
> wants a reachable red; it needs a different control.

### Clock-shift rule

**Shift by a whole number of days in the site's timezone:
`shift_days = floor((now − src_end) / 86400000)`.** Close the residual gap with a live
5-minute drip. **Never anchor the newest historical reading onto `now`** — doing so rotated
time-of-day by 2h50m on one measured window, desynchronising the glucose trace from the
profile's own time-of-day basal/ISF/CR schedules and making IOB, COB, BWP and the basal
render internally inconsistent for reasons that have nothing to do with any branch.
`[measured]`

Every conversion goes through `.timestamp()`, never integer arithmetic: `entries.date` is
`datetime64[ns]` while treatments/devicestatus/profiles/grid are `[ms]` and
`settings.fetched_at` is `[us]`, against a `DATA_DICTIONARY` declaring all of them
milliseconds. A shared helper doing integer maths is off by 1000× on entries and lands
treatments in 1970, with no error. `[measured]`

The drip also keeps the site out of the stale-data alarm: the client's "now" is the
*browser's* `Date.now()` and timeago defaults are 15 min warn / 30 min urgent, so a 5-minute
drip carries ten minutes of slack.

### One patient per instance — forced, not preferred

The entries upsert key is `(sysTime, type)` and nothing else; `device` and an explicit
`identifier` are both excluded. Treatments the same on `(created_at, eventType)`. A
multi-patient terrarium replayed into one site **loses data silently, HTTP 200 on every
request.** `[measured]`

Near-miss timestamps are worse than colliding ones: two sources at different sub-minute
phases both survive, giving 575 + 574 entries in one 48 h window and `/pebble` reporting
`bgdelta: 305` against a clean control's `−5` — **and the page still renders and still looks
alive.** Recon read it as noisy CGM before spotting it. That is what the blocking sanity
gate exists to make impossible.

### Minimum seed documents

- **Profile first.** With entries but no profile, the client navigates itself to `/profile`
  and renders no chart at all — every branch then looks equally broken. `[measured]`
  Six schedule arrays plus `dia`, `timezone`, `carbs_hr`, `delay`, values as **strings**,
  with a `timeAsSeconds` beside every `time`.
- 48 h of entries (576 sgv at 5-min cadence), 60 h of treatments, 24–48 h of nested
  devicestatus. The 62-day age-pill window and the 372-day profile-switch window need
  **exactly one document each**, not a history.
- Bulk ingest is not a constraint: 10,000 entries POST in 0.90 s; 10,001 returns HTTP 400
  "Too many entries"; 50 MB body limit. A 48 h backfill is one sub-second request.
  `[measured]`
- **Separate databases for seeding and for mocha.** `tests/lib/production-safety.js` refuses
  any run when the database name lacks `test` or the entry count exceeds
  `TEST_SAFETY_MAX_ENTRIES` (default 100). Name them `nsreview_<state>` vs `nstest_<state>`.
  Nobody finds this until it bites. `[measured]`
- **Quiesce the drip around the seed-parity pre-gate**, or window the control query to
  exclude the newest document. Otherwise instances differ by drip skew and a *blocking* gate
  goes red for reasons unrelated to any branch — the fastest way to teach a reviewer to
  ignore a red.

### Replay vs synthesis

| Unit | Source | Why |
|---|---|---|
| `bf/reads` + `bf/coercion` | synthetic | needs 400 docs on one `created_at` AND one `date`, and a present/absent-field split at a *known* ratio |
| `bf/cache` | synthetic | needs two window sizes (24 h / 48 h) to show scaling |
| quadratics | **replay** — the one place it earns its keep | needs thousands of overlapping temp basals at real AID density (the store holds 475,960 Temp Basal rows); a hand-written fixture would never think to produce that. Pick an AID patient, not MDI. A synthetic 5000-at-5-min stand-in is acceptable **if the packet says it approximated density.** |
| `bf/merge`, `bf/parms`, `#8729` | synthetic | the input is a URL shape or a socket delta, not data |
| `bf/food` | synthetic, mandatory | the five-way `hidden` typing *is* the bug |
| `#8741` | synthetic | see §5 — the observable is a boot crash, not data |

---

## 5. Per-branch acceptance

**Meta-gate, binding on every row.** A probe must record the measured BASE value *and* the
measured RC value in its packet row, and the ratchet must refuse to render a verdict for any
probe whose control has not been executed **in the same session**. Four of the eleven
criteria in the earlier draft failed precisely because their red state was reasoned about
rather than executed.

Rows marked **⚠ REWRITTEN** are ones whose earlier criterion was tested and found broken.

| Unit | What you do | Green | Red | Mode |
|---|---|---|---|---|
| **coercion+reads** ⚠ | Seed a known present/absent split; query `$exists` true and false | the two result sets **partition the seeded collection** (5 + 576 = 581) | they do not partition — catches *reads without coercion* | auto |
| | | count-equals-list catches *coercion without reads* — **a different arm.** Never compare a count against the same build's list endpoint; compare against the known seeded expectation. | | auto |
| **bf/cache** ⚠ | Seed 288 and 5700 entries; measure in-handler cost at both | BASE grows with cache size (`BASE(5700)/BASE(288) ≥ 5`) while RC stays flat (`≤ 1.5`) | BASE flat, or RC grows | auto |
| | The earlier `≥100×` threshold is **unreachable on the correct build**: measured 1.66–1.87× at 288 entries, 2.49× at 576, 14.10× at 5700; in-handler 27×; end-to-end 1.87×. Only an isolated JSON-clone microbenchmark reaches 976×, and that never calls `getData`. A stuck-red gate gets disabled, leaving the branch's headline claim ungated. `[refuted]` | | | |
| **quadratics** ⚠ | Run `processDurations` at n=500/2000/5000 | superlinear on BASE, flat on RC, **per-n thresholds** | flat on BASE | auto |
| | Measured 1.7×/3.0× at n=500 and 12.0×/11.0× at n=2000 against a required ≥20× — two of three n values stuck red on the fix. `[refuted]` **The equality arm has no demonstrated reachable red**: two independent injected defects both left the output hash unchanged. Either find a break that moves the hash, or ship it as a timing gate with an equality smoke test and mark the `cutting` property uncovered in §7. | | | |
| **#8741** ⚠ | Boot a connect-enabled instance with a numeric credential | instance reaches `Listening`; `env()` type check passes | **BASE crashes at boot** — `TypeError [ERR_INVALID_ARG_TYPE] … Received type number`, exit 1 | auto |
| | The earlier arm used `CONNECT_NS_URL`, which is the **wrong key** — validation requires `CONNECT_SOURCE_ENDPOINT` and disables the connector otherwise, so the fixed build logged "Invalid configuration, disabling connector". With the right key and a `denied` source the fix is stuck red; with a `readable` source the pull succeeds anonymously so the credential is never exercised. The boot crash is the honest discriminator. `[refuted]` | | | |
| **bf/parms** ⚠ | Grep the served `/devbundle` bundle | branch bundle lacks the **dev-spelling** token; BASE carries it once | BASE hit count is 0 → gate fails rather than passes | auto |
| | The earlier criterion quoted the **minified production** spelling, which matches nothing in the dev mode the plan mandates — green on both builds. `[refuted]` Dev bundles are `eval`-wrapped so every backslash is doubled. **Machine-select tokens: admit none that has not measured 0 on BASE and ≥1 on the branch.** `queryParms` appears 2× in *both* builds and cannot discriminate. | | | |
| **bf/merge** ⚠ | In-process probe against captured socket deltas | handcrafted out-of-order delta throws on BASE, not on RC | — | auto |
| | The "delete one treatment outside the client's loaded window" step **cannot go red**: an out-of-window delete emits *no delta item at all*, and real deltas replay cleanly through BASE. `[refuted]` Downgrade to the in-process probe and say so on the card, or first demonstrate a server-driven route to an action item the client does not hold. | | | |
| **bf/food** ⚠ | quickpicks endpoint; Bolus Wizard dropdown | endpoint returns 1 not 3; dropdown offers 7 not 3 | inverse | auto + eyes |
| | The `hidden:true` round-trip arm is **green on BASE** via curl: the defect is in a *client* function that runs when the **food editor** loads and only persists when the editor saves. Add "load `/food`, save, reload" to the card, or move the criterion to §7. `[refuted]` | | | |
| **bf/alarms** ⚠ | **Three boots, not one 90 s pass** | iage pill appears; ENABLE typo names the plugin it meant | neither | eyes |
| | The alexa route exists only when `ENABLE` contains `alexa`; the suggestion arm needs `ENABLE='insulinage'`; the iage arm needs `iage`. Three mutually exclusive `ENABLE` values. `[refuted]` The locale arm names **no HTTP surface** that reveals the server's language after a de-DE POST — supply one or drop it. | | | |
| **#8729** ⚠ | Chart renders at a 0-height container | chart draws | — | eyes only |
| | **Delete the "nothing downstream divides by either" arm**: there is no division by `focusHeight` or `contextHeight` anywhere in the client (only `focusHeight / 4`, division *of*), so it is green on every build and its red has no construction. `[refuted]` | | | |

---

## 5a. MEASURED RESULTS — 2026-09-17

Harness built at `tools/review/`. Full cycle — six states booted, seeded, six probes, five red
controls — **31.9 s**, browser work included.

| probe | unit | verdict | what the control measured on BASE |
|---|---|---|---|
| `pair` | #8737+#8738 | **PASS** 12/0 | count endpoint dead; `$exists=false` inverted |
| `pair-half-reads` | #8738 *alone* | FAIL 2 | *expected* — the half-merge detector firing |
| `pair-half-coercion` | #8737 *alone* | FAIL 3 | *expected* — same |
| `food` | #8735 BF-16 | **PASS** 8/0 | 1 quick pick, and the **wrong one** |
| `food-boluscalc` | #8735 **BF-35** | **PASS** 5/0 | 8 chooser entries; **5 page-error crashes** |
| `credentials` | #8741 | **PASS** 5/0 | password `007700` → number `7700` |
| `alarms` | #8739 BF-28 | **PASS** 7/0 | 72 h and 96 h reservoir both report **WARN**; URGENT unreachable |
| `parms` | #8736 BF-37 | **PASS** 10/0 | `?debug`, `&`, `&&` → **no chart rendered** + throw |
| `merge` | #8734 BF-36 | **PASS** 5/0 | stale inner bound throws on `undefined._id` |
| `quadratics-shape` | #8733 | **PASS** 6/0 | `processDurations` **62.8×** and `calcDelta` **88.9×** for a 10× input — the quadratic signature |
| `cache-shape` | #8740 BF-06/07 | **PASS** 3/0 | cost tracks the window: 1.123 ms sparse → **6.658 ms** dense (5.93×) |

**Eight of nine units qualified.** The integration branch `rc/2026-09-dev-cycle` carries all six as
six first-parent merge commits, and every probe is re-run against it — that re-run is what catches
a later merge breaking an earlier fix, and is the whole reason this cycle evaluates between merges
rather than bisecting at the end.

Remaining: **`#8729` only**, which still has no falsifiable criterion (§7).

For cache the fix does not merely go faster — it *decouples*: 0.518 ms sparse → 0.472 ms dense
(0.91×), i.e. per-request cost stops tracking the retained window at all, which is precisely the
claim BF-07 makes about `cache.insertData` round-tripping the whole array.

### The performance units: shape, not multiples

Both fixed-multiple thresholds from the first draft measured **stuck red on the correct build** —
`≥100×` for cache (real request-level ratios 1.66–2.49×) and `≥20×` at every *n* for quadratics
(1.7× and 12× at *n*=500 and 2000). Both are replaced by scale-free shape assertions:

> BASE cost must **grow** with input size; the candidate's must stay **flat or near-linear**.

Measured for quadratics: BASE 62.8× / 88.9× for a 10× input increase (linear would be 10×) against
the fix at 6.6× / 8.2×. The separation is an order of magnitude, and neither bound depends on this
machine's speed.

**I repeated the very mistake this section documents.** The first version of `quadratics-shape.js`
set the near-linear bound to `≤6` — below the 10× that *perfect linearity* costs — and the correct
fix failed at 7.6×. Writing the warning into the file header did not prevent it; **running the
probe did.** The bound is now 13. That is the third distinct stuck-red threshold in this cycle, and
the argument for the meta-gate no longer rests on the refuters' findings alone.

**BF-35 is verified.** On dev the quick-pick chooser offers all five plain foods *and* the quick
pick the user deliberately hid — 8 entries — while the option value indexes a 3-element array.
Options 0–2 resolve silently to the wrong quick pick under a plain food's label; options 3–7
throw `Cannot read properties of undefined (reading 'foods')` (`boluscalc.js:579-580`). Measured:
**5 page errors on BASE, 0 on the fix.**

### A fourth harness defect: a probe that reseeded the shared control

The cache probe reseeds its states to compare two window sizes. Its first version defaulted to
`--base-state BASE` — **the control every other probe compares against** — and reseeded it with
`--no-adversarial` dense data, removing the mbg entries and the food documents. `pair` and `food`
against the RC then reported failures.

They reported them **as `UNATTRIBUTABLE` on BASE**, not as regressions in the branch, which is the
invariant-arm design working exactly as intended: a probe that had only discriminating arms would
have blamed the merge. The default is now a dedicated `PERFBASE`, and the episode is the argument
for invariant arms carrying their own failure mode rather than being informational.

### Three readouts that looked right and were not

Beyond the two harness defects below, three *criteria* had to be discarded after measurement:

- **`#bc_carbs`** for BF-35 — written only on the "(none)" branch, so it read 0 on **both** builds.
- **`#loadingMessageText` visibility** for BF-37 — true in every cell, including ones that render
  a chart perfectly well. The chart SVG is the readout; the loading message is not.
- **Unauthenticated URLs** for BF-37 — without a token the page stops at the loading message on
  *both* builds for an auth reason unrelated to the defect. The token is now held constant so the
  parameter is the only variable.

All three would have passed anything. This is what §5's meta-gate is for.

### Two harness defects that would have faked results

1. **Dropping a database under a live server leaves the cache populated.** BASE served 1145
   distinct sgv documents from a 582-document database — the previous seed merged with the
   current one. Every read measurement in that state was invalid and nothing said so. Fixed:
   `nsctl.sh reset` stops before dropping.
2. **All states shared one production bundle.** Webpack's output path is inside `node_modules`,
   which every state symlinks, so all three served byte-identical `d765fe44…` containing **none**
   of `bf/food`'s client code. The branch's own instance was serving dev's client. Every
   client-side probe would have compared dev to dev and passed. Fixed: client probes require
   `NODE_ENV=development`, and `probes/provenance.js` is a **blocking pre-gate** that refuses to
   vouch when it cannot find a token that measures 0 on BASE and ≥1 on the candidate.

Both produced *plausible* wrong numbers rather than errors — which is the whole reason §5 carries
a meta-gate.

---

## 6. Sequence of work

1. **Now.** Open the `#8605` conversation with its owner. Capture the per-file baseline with
   explicit timeouts (**not** the suite exit code).
2. **S0–S1 (≈3 d).** `nsctl.sh` and `seed.js`, with the four process hazards handled.
   → *Decision point:* boot two states, seed both, look at one in a browser. If the site does
   not look alive, nothing downstream is evidence.
3. **S2.** Land units 1–3 using the preserved probe scripts. → *Decision point:* has the loop
   earned more investment?
4. **S3 (≈2.25 d).** `provenance.js`, `ratchet.js`, queue wiring — with every §5 red control
   **executed**, not reasoned about.
5. **S4 (≈1.75 d).** Browser cards and the review page, for the five units with an honest
   browser observable.
6. Land units 4–9, skipping and replaying on failure.

---

## 7. What this plan does not cover

- **`#8729`** has no falsifiable automated criterion at all. Its only check is a human
  looking at a chart. Shipping it is a judgement call, not a measurement.
- **quadratics' output-equality property** has no demonstrated reachable red. Two injected
  defects left the hash unchanged because `cutIfInInterval` re-validates the interval and
  absorbs both extra and missing boundary candidates.
- **`bf/merge`'s browser-level failure mode** is unreachable by any server-driven route found
  so far.
- **BF-35's dose consequence is inferred, not read.** The probe measures the chooser's membership
  and the crash. "Picking one quick pick loads a *different* one's carbs" follows from the index
  arithmetic — `foods` is module-private, `#bc_carbs` is written only on the "(none)" branch, and
  `#bc_food` renders empty in the synthetic state. An earlier revision asserted on `#bc_carbs` and
  read 0 on **both** builds: a criterion that would have passed anything.
- **`loadFoodQuickpicks` is called once, at client init**, before the socket delivers any food, so
  the shipping chooser is empty until something rebuilds it. The probe calls it directly. Whether a
  real user ever reaches the populated-and-broken state is a question for the maintainer, and it
  bears on how urgent BF-35 actually is.
- **`#8741`'s actual credential path** is never exercised — the discriminator is a boot
  crash. Testing the real Dexcom coercion needs live credentials.
- **`bf/alarms`' locale removal** on `/api/v1/alexa` and `/api/v1/googlehome` has no named
  observable. This is the capability removal that graded the branch `major`, and it is the
  least-covered thing in the set.
- **Everything about `bf/auth` and `bf/throttle`**, by scope decision.
- **`help wanted` PR triage** — **dropped from this cycle.** Scope is remedial only; most of
  the eleven are features or modernization (`pr/platform`, `pr/trio-ui`, `pr/reports-agp`).
  If any are later judged remedial, they join a subsequent cycle, not this one.
- **BF-40** — still open after this cycle, by design. `bf/coercion` does not fix it (§1a), and
  no other candidate touches it. It remains `ships_to_operators_today: true`.

---

## Appendix — preserved probe scripts

`tools/review/probes/` — 42 scripts (172 KB), preserved from the session scratchpad and
**committed 2026-09-17**. They reproduce all twelve defects: `mongochk`, `quadbench`,
`clonebench`, `mergechk`, `parmschk`, `iagechk`, `foodchk`, `delaychk`, `querychk`,
`projchk`, `enablechk`, plus boot/seed/latency helpers and `ns-client-gate.js`.

**The sanitisation claim in the first draft of this appendix was wrong, and re-running the
scan is what caught it.** `[refuted]` It said two hardcoded throwaway `API_SECRET` values had
been replaced with `${NS_HARNESS_SECRET:?}`. Two *environment* sites had been — `boottime.sh`
and `rf-boot.sh` — and **ten credential literals were still in the tree**: the plaintext
harness secret in five shell probes (`loop`, `verify`, `cycle`, `probe`, `decisive`), and a
bare SHA-1 in `rf-thr.sh`, `rf-seed.js`, `rf-lat.js`, `rf-lat2.js` and `rf-sock.js`. The
SHA-1 is not the hash of the plaintext that was sanitised, so it belonged to an earlier
secret the first pass never saw — which is why a scan for the *known* string could not find
it. Nightscout accepts that hash directly as `api-secret`, so a hash is a credential here and
not a redaction of one.

All ten now derive from `NS_HARNESS_SECRET` and **fail loudly when it is unset** — `:?` in
shell, a thrown `Error` in the Node one-liners, both executed in both states rather than
read. `[measured]` One token-shaped fixture that read like a real family subject name was
replaced with an obviously synthetic value in the first pass; that part held. Re-scanned for
emails, patient ids, connection strings with credentials and `ns-data` references — none
found. All 42 pass `node --check` / `bash -n`. `[measured]`

These were untracked, and the programme's gates cannot see untracked files, so nothing here
counted as evidence. That is the reason they are committed: **S2 cannot cite a probe the
gates cannot see.**
