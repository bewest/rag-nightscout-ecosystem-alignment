# Post-Phase-0 roadmap — ordering the four next priorities

> **Snapshot — describes 2026-09-15, measured against `origin/dev` `a8888f0d`.** Status:
> superseded for ordering. Wave 2's trigger ("Phase 0 on dev") happened between 2026-09-17 and
> 2026-09-21, so R5 (seam rebase) is unblocked. Current ordering and measurements:
> [release-readiness-15.0.9-2026-09-22.md §5](modernization/release-readiness-15.0.9-2026-09-22.md#5-the-road-after-1509).
> The R-items' designs, the `ctx` analysis (§0.1–0.3), deployment metadata (§4) and the open
> questions (§6) are still the only statement of those designs.

**Status: draft for maintainer review, 2026-09-15.** Contributor-facing. Written against main-repo
HEAD `75c38a17`, `origin/dev` `a8888f0d`, `seam/t1-2-storage-interface` `81a1f6ce`. Nothing in this
document was pushed, merged or rebased; every git operation below is `merge-tree`, `rev-list` or
`show` against the shared checkout, which is still clean.

**Re-verified at main-repo HEAD `08753474`** (the two commits since `75c38a17` add the GT1-GT4
reports and a §3a to the sequencing document; neither changes a fact used here). The branch
topology, the nine-branch conflict table in §0.5, the `ctx` measurements in §0.1-0.3 and the
`bulkUpsert` census in §0.4 were all recomputed at that head and reproduce. Two stale line
citations were corrected in the process — `bootevent.js:218` → **`:212`** and
`lib/client/index.js:234` → **`:241`**.

**Adversarial review, 2026-09-15 — read this before acting on §0.4 or R8a.** An independent pass
re-ran the branch topology, the §0.5 conflict table, the §0.1-0.3 `ctx` experiment and the plugin
census, and **all of those reproduce exactly**. Three things did not survive and are corrected in
place, each marked where it occurs:

1. **§0.4's "four call sites pass no options at all" is refuted.** All four pass `{ mode: 'replace' }`
   on the call's continuation line. The census had been taken from `grep` output rather than from
   the call sites. §0.4's headline — eight of nine sites diverge, and BF-21 is not live only
   because `entries` asks for the mode PostgreSQL hardcodes — **survives**; the mechanism paragraph
   and R8a's premise did not.
2. **Every `npm test -- tests/<file>` gate was unrunnable as written.** npm appends the argument to
   the script's own `./tests/*.test.js` glob, so the command runs the whole tree. Corrected in §2
   and at each gate.
3. **Three *further* line citations were stale**, on top of the two the re-verification pass above
   already caught: `bootevent.js:17` for the `moment-timezone` require is `:19`; `clientInit`'s
   signature is at `sandbox.js:85`, not `:91`; and `sandbox.js:152` is `lastNEntries`, not
   `lastEntry`. Five stale citations in total. §7's claim that every `file:line` was re-resolved is
   therefore overstated — see the note at the end of §7.

The maintainer selected **all four** candidate areas, so this document does not choose among them.
It orders them, and it argues the ordering from measurement rather than from preference.

The four, as briefed:

| | area |
|---|---|
| **(a)** | T3.0 — credential and configuration rework (D13/D14/D15); amends T3.1/T3.2/T3.3 |
| **(b)** | the §1b pre-release highs — BF-19, BF-21, BF-22, BF-24, BF-25 |
| **(c)** | T4.3/T4.4 — alarms under `multi`, currently OFF by design |
| **(d)** | refreshing the seam and `chore/nightscout-modernization` against a dev that Phase 0 moves |

**The headline, and it inverts the obvious order.** (d) reads like hygiene and was briefed last.
Measured, **8 of the 9 Phase 0 branches conflict with the seam branch**, and the conflicts land in
exactly the files the seam rewrote. One of those conflicts is two independent fixes for the *same
defect*, written a day apart by two sessions that did not know about each other. (d) is not
hygiene; it is a decaying asset, and its cheap half belongs first.

---

## 0. Corrections this roadmap had to make before it could be written

Four premises were wrong. Two of them change the shape of the work, not just its description.

### 0.1 §7a's `ctx` hazard names one mechanism. There are three, and they need different fixes.

The execution plan §7a says:

> plugins capture `ctx.moment`, `ctx.language` and `ctx.levels` at plugin *init*, not per call. A
> per-tenant `ctx` therefore cannot re-point any of them for an already-initialised plugin — the
> closure holds the boot-time value.

Measured (`node` against `externals/work/crm-seam/lib/`, script and output in §7 below):

| | mechanism | is capture the problem? | what a fix costs |
|---|---|---|---|
| `ctx.levels` | `lib/levels.js` is `module.exports = levels` — a **require-cache singleton object**, not a factory | **No.** There is no second object to point at | make `levels.js` a factory, or make it stateless. **Two `require` call sites** |
| `ctx.moment` | `bootevent.js:19` — `require('moment-timezone')`, a require-cache singleton with no factory at all | **No.** Same reason | never re-point; pass locale per call |
| `ctx.language` | `lib/language.js` is `module.exports = init` — a **factory**. Per-tenant instances are constructible | **Yes.** This one is genuinely capture | per-tenant plugin registry, *or* move 21 plugins to per-call reads |

Two measurements make this concrete. `require('./levels')` twice returns the identical object, so
`ctxFor(A).levels === ctxFor(B).levels` is **true** and no per-tenant `ctx` can hand out two of
them. And `bootevent.js:212` already *mutates* that singleton — `ctx.levels.translate =
ctx.language.translate` — so running boot per tenant means **the last tenant to boot sets the level
names for every tenant, process-wide**. Reproduced: tenant A's `toDisplay(2)` returned `A-URGENT`
immediately after A booted and `B-URGENT` after B booted, with no further action by A.

**Why the distinction is load-bearing and not pedantry.** §7a's framing sends a designer to fix
*when plugins capture*. That work would be substantial — 21 of the 22 plugins that touch these
objects capture at init — and it would **not fix `levels` or `moment` at all**, because those are
not capture problems. Conversely the `levels` fix is far smaller than §7a implies: only
`bootevent.js` and `lib/client/index.js` `require` it; every other consumer already goes through
`ctx.levels`/`sbx.levels` — 52 such call sites across 22 files outside `lib/client/`.

### 0.2 "The closure holds the boot-time value" is false for `language`, in a way that helps

A captured `translate` is **not** frozen. It closes over its language *instance* and reads that
instance's mutable catalogue at call time: after `offerTranslations({Urgent:'MUTATED'})` a
translate captured before that call returned `MUTATED`. What is frozen is **which instance** it
reads, not the value.

That matters because it means a **per-tenant plugin registry** works. `lib/plugins/index.js` is a
factory — `require('../plugins')(ctx)` — so initialising one registry per tenant gives each
tenant's plugins a closure over that tenant's own language instance, with **no change to any plugin
source file**. That option is not in the plan and it is the cheapest path through the language half
of the hazard. Its cost is per-tenant plugin-registry memory, which §7b did **not** measure (§7b
measured the per-evaluation slice, a different thing). That is an open question, not a claim.

### 0.3 The hazard is narrower than a blanket statement: `sbx` already re-reads per evaluation

`lib/sandbox.js:55-57` assigns `sbx.levels`, `sbx.language` and `sbx.translate` from `ctx` on
**every** `serverInit`. So a plugin reading `sbx.translate`/`sbx.levels` is already per-evaluation
and is not affected by capture at all. Census over `lib/plugins/*.js`:

- **21 of 22** capture at init (`var translate = ctx.language.translate`, `var levels = ctx.levels`)
- **`treatmentnotify.js`** is purely per-evaluation (9 `sbx.` reads, 0 captures)
- **`ar2.js`** is mixed (2 captures, 6 `sbx.` reads)

`treatmentnotify` is not an incidental example — §7b identified it as one of three dependencies
that can *withhold* an alarm. The one plugin that already does the right thing is one of the three
that matters most.

### 0.4 BF-21's stated reason for not being live is wrong, and the true reason is more fragile

The register says: *"`entries` is the only collection with a PostgreSQL schema and it has no
`bulkUpsert` caller."*

Measured: `lib/server/entries.js:168` **does** call `bulkUpsert`, with `{mode:'merge', ordered:true}`.
The PostgreSQL implementation (`pgCollection/index.js:286`) takes `(ops)` — no options parameter at
all — and passes the literal `'merge'` to `write()` at line 292. So the two backends agree **because
the one live caller happens to ask for the mode PostgreSQL hardcodes** — not because the caller is
absent.

> **CORRECTION, applied by adversarial review 2026-09-15. Struck rather than deleted, per this
> programme's convention for an invalidated claim.** The paragraph below originally read *"And the
> accident is thinner than even that"* and claimed that four call sites — `authorization/storage.js:143`,
> `treatments.js:31`, `activity.js:102`, `profile.js:101` — pass **no options at all** and rely on
> MongoDB's `'replace'` default. **That is false.** All four pass `{ mode: 'replace' }` explicitly,
> on the *continuation line* of the call (`storage.js:144`, `treatments.js:32`, `activity.js:103`,
> `profile.js:102`); this codebase's leading-comma style puts the second argument on the next line,
> so a `grep -rn bulkUpsert lib/` hit shows only the opening line. The original census was taken
> from the grep output, not from the call sites, which is precisely the "naive enumeration" R8a
> was written to warn against. The register's BF-21 entry had it right all along: *"Every shipping
> caller passes `{ mode: 'replace' }` explicitly."* **Nothing silently relies on a default.**

**The accident is real but it is not silent.** MongoDB's implementation
(`mongoCollection/modify.js:255`) reads `const mode = (options && options.mode) || 'replace'`, so a
no-options caller would get `'replace'` where PostgreSQL gives `'merge'` — but **no such caller
exists today**. Full census of the nine `bulkUpsert` call sites in `lib/` (crm-seam `81a1f6ce`,
`grep -rn bulkUpsert lib/`, then each call **read through its closing parenthesis**):

| what the caller asks for | sites | Mongo does | PG does |
|---|---|---|---|
| `{mode:'merge'}` | `entries.js:168` | merge | merge — **agree** |
| `{mode:'replace'}`, stated on the call's own line | `treatments.js:120`, `activity.js:61`, `food.js:64`, `food.js:122` | replace | merge — **diverge** |
| `{mode:'replace'}`, stated on the *continuation* line | `authorization/storage.js:143-144`, `treatments.js:31-32`, `activity.js:102-103`, `profile.js:101-102` | replace | merge — **diverge** |
| **no options at all** | *(none)* | — | — |

**Eight of nine call sites diverge**; the one that does not is the only collection with a
PostgreSQL schema. All eight ask for `'replace'` **in writing** and the argument reaches nothing —
`guard()` in `mongoCollection/index.js:57-62` forwards every argument, so the options bag does
reach MongoDB's implementation and is honoured there; PostgreSQL's signature simply has nowhere to
put it. The comments at the four continuation-line sites say "bulkUpsert with one operation is
exactly replaceOne+upsert", which is true on MongoDB and false on PostgreSQL — so the misleading
artefact is the *comment*, not a missing argument.

`entries.js` carries a comment explaining that its merge is deliberate and *not* interchangeable
with replace; the day anyone revisits that decision, or any second collection gains a PostgreSQL
schema, BF-21 goes live with no other change and no warning. The register's caller list names three sites
(`activity.js:61`, `activity.js:102`, `treatments.js:31`) and **omits six**: `treatments.js:120`,
`entries.js:168`, `food.js:64`, `food.js:122`, `authorization/storage.js:143` and `profile.js:101`.
(An earlier draft of this paragraph said the register omitted one; corrected by adversarial review,
which counted the census against `grep -rn bulkUpsert lib/`.) The register also omits that
`ordered: true` is silently dropped too — PostgreSQL's loop at `pgCollection/index.js:290` is a
sequential `for` with `await`, so that one also agrees by accident rather than by contract.

This does not raise BF-21's severity — it is still pre-release. It changes what the *gate* must be,
and §2 R8a below adds a cheap one that cannot rot.

### 0.5 The Phase 0 set is no longer flat, and the seam collides with it

GT1 measured all nine `bf/*` branches as based directly on `origin/dev`, flat and independent.
Re-measured at HEAD `75c38a17`: **`bf/coercion` (`88d1f8a4`) is now an ancestor of `bf/reads`
(`0d19bb31`, 8 commits)**. `bf/reads` moved from `824380a0` since GT1 ran. The set is no longer
parallel-landable; `bf/reads` carries `bf/coercion`.

And the number this roadmap turns on — `git merge-tree --write-tree seam/t1-2-storage-interface
<branch>`:

| branch | result | conflicting files |
|---|---|---|
| `bf/parms` | **clean** | — |
| `bf/alarms` | conflict | `tests/api.alexa.test.js` |
| `bf/merge` | conflict | `lib/client/receiveddata.js` |
| `bf/connect-pin` | conflict | `package.json` |
| `bf/cache` | conflict | `lib/api/entries/index.js` |
| `bf/coercion` | conflict | `lib/server/query.js` |
| `bf/food` | conflict | `lib/client/boluscalc.js`, `lib/server/food.js` |
| `bf/auth` | conflict | `lib/api3/alarmSocket.js`, `lib/api3/security.js`, `lib/authorization/index.js`, `lib/authorization/storage.js`, `lib/server/websocket.js` |
| `bf/reads` | conflict | `lib/authorization/storage.js`, `lib/server/{activity,aggregate,devicestatus,entries,profile,query,treatments}.js` |

**The worst one is semantic, not textual.** `seam` commit `e0564167` (2026-09-14, *"Fix `$exists`: a
T1.2 regression, and the older defect under it"*) added `coerceExistsArguments()` to
`lib/server/query.js`. `bf/coercion` commit `88d1f8a4` (2026-09-15) replaced that file's
hand-written walker with schema-driven `lib/server/query-coercion` and fixed the same `$exists`
operand defect as BF-32. **Two sessions, one day apart, fixed the same defect in the same file by
different mechanisms, and neither knows the other exists.** Neither is on dev.

The schema-driven fix is strictly more general (it covers all operator operands, not just
`$exists`). But nothing anywhere records that, so whoever resolves that conflict will be choosing
between two plausible-looking fixes with no note telling them one subsumes the other — in a file
whose output the seam's `fromMongo` parses, which is where BF-04's operator allowlist lives.
A careless resolution there silently re-opens a security fix.

---

## 1. The ordering, and the argument for it

### 1.1 What actually constrains the order

Three constraints, in decreasing strength.

**C1 — Conflict cost grows, and provenance decays faster than conflicts do.** The eight conflicts
above are not the problem; conflicts are mechanical. The problem is that the *reason* two fixes
exist is held only in two agents' sessions. `e0564167` and `88d1f8a4` are three weeks from being
indistinguishable. This decays whether or not anyone works on (d), which makes it the only item
here with a real clock on it. Everything else can wait without getting worse.

**C2 — (c) cannot be *designed* until §0.1 is settled.** This is the brief's own constraint and it
survives measurement, but it is smaller than it looked: the `levels` half is a two-call-site change
and the `language` half has a no-plugin-edits option. That moves (c)'s blocker from "a research
project" to "a week's work with a gate", which changes where it sits.

**C3 — (a) and (b) have gates, not dates.** T3.0 blocks nothing today. BF-19/21/22 are not live and
their own entries name their deadline: T2.6, which is unscheduled. BF-24's deadline is a
*publication* — the maintainer decided it lands before the nginx recipe. BF-25's honest fix *is*
(a). None of these has a clock; all of them have a named event they must precede.

### 1.2 Why (d) is not last

The brief lists (d) fourth and frames it as applying the release-readiness objection about stale
unreviewed branches to the seam. That framing is right but it understates the case, because it
treats the seam as *stale* when the measured problem is that it is *colliding*.

If (d) is scheduled last, then by the time anyone does it, all nine Phase 0 branches have landed on
dev, and one person resolves conflicts across the entire v1 read path — `query.js`, `entries.js`,
`activity.js`, `devicestatus.js`, `profile.js`, `treatments.js`, `authorization/storage.js` — in one
sitting, on a 40+ commit branch that (per the release-readiness governance finding) has had zero
human reviews. That is the highest-risk single operation this programme currently has queued, and
scheduling it last is what makes it that.

**But (d) cannot be *done* first either**, because the rebase target does not exist until Phase 0
lands on dev, and that is a release-train decision the maintainer owns (§5). So (d) splits:

- **(d1)** — record the collisions and their resolutions *now*, while both authors' reasoning is
  still recoverable from the commits. No rebase, no branch touched. Cheap.
- **(d2)** — the actual rebase, after dev moves.

(d1) is the first item in this roadmap. It is also the only item here that is cheaper today than it
will ever be again.

### 1.3 Why (a)'s research half goes early and its code half does not

T3.0 is three parts: research, schema, wiring. The research half produces a `docs/60-research/`
report and touches no code — so it has **no conflict surface**, can run concurrently with the seam
refresh, and is the input every other part of (a) needs. There is no argument for delaying it.

The schema and wiring halves are different. They amend T3.1/T3.2/T3.3, all of which live on seam
branches, all of which are about to be rebased. Doing schema work on a branch that is mid-rebase is
how the collisions in §0.5 happened in the first place. **(a)'s code halves wait for (d2).**

### 1.4 Why BF-25 splits, and why that is not a dodge

BF-25 is high severity and it is the one entry (a) *structurally* kills: D14's per-tenant signing
key turns cross-tenant token reuse into a signature failure, so the claim check where BF-25 was
found stops being the thing that has to be right. Fixing BF-25 as a point fix now — teaching
`presentedCredential` to read the body — means writing a guard that D14 makes redundant, on a
branch that is about to be rebased.

But the register entry itself says the sharpest thing about it: *"The most dangerous part is the
comment, because it tells the next reader this case is already handled. Fix the sentence even if
the code takes longer."* And it names the gap: no end-to-end test exists; the two halves were
established separately.

So: **the comment and the regression test land now; the structural fix lands with (a).** That is
not deferral — the test is written against the defect, so it fails today, and it is the exact test
that proves D14 worked when (a) lands. Writing it now makes (a) checkable later.

### 1.5 Why (c) is last, and why that is not a safety failure

Alarms are OFF under `multi` by design. **Nothing about this ordering makes anything less safe than
it is today**, because `multi` is not servable today — `fromEnv` warns at boot that it is not safe
to serve two people from, and T3.5 withholds emissions outside tenant scope. (c) is the item that
*turns something on*, and §7a's rule is explicit that it turns on against a test, not against a
schedule.

(c) is last because it depends on more than anything else here: on §0.1 being settled (C2), on
(a)'s per-tenant config supplying per-tenant alarm thresholds, and on the error boundary and health
signal that have no owner yet. Putting it earlier would mean building a per-tenant evaluation loop
against a `ctx` whose shape is unsettled — which is precisely what §7a warns against.

**One piece of (c) does move early**: settling the `ctx` shape (R1). It is (c)'s blocker, it is now
measured and sized, and it unblocks a whole wave. It is not scheduled as alarm work; it is scheduled
as the thing without which alarm work cannot start.

### 1.6 The order

```
WAVE 1  — now, no release-train dependency, no shared-branch edits
  R1  Settle the per-tenant ctx shape             (unblocks wave 3)
  R2  Seam/Phase-0 collision ledger  [d1]         (decaying; cheapest today)
  R3  BF-25 comment + failing regression test
  R4  T3.0 half 1 — research                       [a]

WAVE 2  — needs Phase 0 on dev (maintainer decision, §5)
  R5  Seam rebase onto moved dev     [d2]
  R6  T3.0 halves 2-3 — schema + wiring            [a]
  R7  BF-24 — before the nginx recipe is published [b]
  R8  BF-19, BF-21, BF-22                          [b]
  R8a BF-21 mode-agreement canary (cheap, do with R8)

WAVE 3  — needs R1 and R6
  R9  T4.4 per-tenant evaluator, error boundary, health signal, clock
  R10 Deployment metadata (§4) — rides R6's schema
```

R10 is scheduled but blocks nothing; see §4.

---

## 2. The items

Every item states its "done" as a command. Where no command exists yet, the item says so rather
than inventing one — per the brief, and because a gate nobody can run is how a plan rots while
looking healthy.

**A note on every test gate here, corrected by adversarial review 2026-09-15.** GT1 measured that
`npm run test:unit` is a brace list resolving to 44 of 159 files and `test:integration` to 89, with
**52 files matching neither**. A new test file is in neither list by default, so no gate below uses
`test:unit`.

An earlier draft of this document wrote every gate as `npm test -- tests/<name>.test.js`. **That
does not run the named test on its own, and the error was verified by running it.** The `test`
script ends in `./tests/*.test.js`, so npm appends the argument and mocha receives
`./tests/*.test.js tests/<name>.test.js` — the whole tree plus the named file, with the named file
loaded twice. Two consequences matter: a single-file gate cannot be read as red-or-green for its own
subject, and R3's "must fail today" gate would report failure for any unrelated reason (GT1 measured
6 environmental failures on a tree with no mongod running), which is the first of the two ways this
programme has seen a check go vacuous.

**The invocation that does isolate a single file**, verified against `tests/language.test.js`
(16 passing in 101 ms, versus the whole tree):

```
node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js \
  --timeout 5000 --require ./tests/hooks.js --exit tests/<name>.test.js
```

Every single-file gate below is written that way. `npm test` with **no** argument remains the
correct whole-tree gate (it is what CI's `test-ci` runs, modulo the env file) and is used where a
whole-tree result is what the item needs — R5.

---

### R1 — Settle the per-tenant `ctx` shape

**Why now:** blocks (c) being *designed*, per §7a. Now measured and sized (§0.1-0.3), so it is a
week of work with a gate, not an open question.

**Scope, and the decisions it must record:**

1. **`levels`** — convert `lib/levels.js` from a singleton object to a factory, *or* make it
   stateless (`toDisplay(level, translate)`). Two `require` sites. **Recommend stateless**: a
   factory still lets `bootevent.js:212`-style mutation back in, and a function with no captured
   state cannot be re-pointed wrongly because there is nothing to point.
2. **`moment`** — do not attempt per-tenant. `moment-timezone` has no factory. Pass locale at the
   call site. This is BF-31's mechanism and BF-31 is already fixed on `bf/alarms`; R1 must not
   re-introduce it.
3. **`language`** — choose between (i) a per-tenant plugin registry (no plugin edits, unmeasured
   memory cost) and (ii) moving 21 plugins to `sbx.` reads. **Recommend (i)**, with (ii) as the
   fallback if the memory measurement refuses it.

**Gate:** `node tools/qc/tenant-ctx-shape.js` — does not exist; R1 writes it. Three arms:
- two contexts built by `ctxFor()` hand out level rendering that does not alias;
- a plugin initialised under tenant A renders A's level name *after* tenant B has booted;
- **a control arm that reverts `levels.js` to the singleton and must FAIL** — without it this
  harness is vacuous in exactly the way §7b's two runs nearly were.

**A fourth arm D1 requires, added by adversarial review.** `lib/levels.js` and
`lib/client/index.js` are **single-tenant shipping code** — they are on `master` today and every
self-hoster runs them. D1 and D4 make single-tenant first-class and permanent, so R1 is not a
tenancy-only change: it edits the alarm-level rendering path of every existing deployment. The
gate must therefore include **a single-tenant non-regression arm**: with `TENANCY_MODE` unset,
level names must render identically before and after, in at least one non-English locale (the
`levels.translate` mutation exists precisely to make that work — see §7's withdrawn claim). Without
this arm, R1 can silently make a level name render untranslated for a non-English operator, which
is a change to what an alarm *says* on a deployment that has nothing to do with multitenancy.

**Blocks on:** nothing.

---

### R2 — Seam/Phase-0 collision ledger  *(d1)*

**Why now:** the only item here that is cheaper today than tomorrow (§1.2, C1).

**Scope:** a `docs/60-research/` report recording, for each of the eight conflicting branch pairs in
§0.5, which change is authoritative and why. It must resolve at minimum:
- `lib/server/query.js` — `seam e0564167 coerceExistsArguments` vs `bf/coercion 88d1f8a4
  query-coercion`. State that the schema-driven fix subsumes the targeted one, **or measure that it
  does not**. Do not assert it.
- `lib/authorization/storage.js` — conflicts with both `bf/auth` and `bf/reads`, and `bf/auth`
  narrows stored fields to an allow-list (GT4). Three changes, one file.
- `lib/server/entries.js` — `bf/reads` vs the seam's rewritten read path, next to BF-21's only live
  caller (§0.4).

**Gate:** `node tools/qc/seam-phase0-conflicts.js` — does not exist; R2 writes it. It recomputes
`git merge-tree --write-tree` for the seam tip against each `bf/*` branch and **exits non-zero if
any conflicting file is not listed in the ledger with a named resolution.** This gate cannot rot:
a new branch or a new conflict fails it until someone writes down the reasoning.

**Blocks on:** nothing. Touches no branch — `merge-tree` writes to the object store, not the
worktree.

---

### R3 — BF-25: fix the comment, write the test that fails

**Why now:** §1.4. Cheap, and it converts (a) from unverifiable to verifiable.

**Scope:** correct the `presentedCredential` comment, which currently tells the next reader the
body case is handled when it is not. Write the end-to-end test the register names as the gap: the
real authorization stack, two tenants' subjects, A's JWT in a JSON body against B's host.

**Do not** fix the code path. D14 (R6) removes the bug class; a guard written now is a guard
rewritten later, on a branch about to be rebased.

**Gate:** `node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js --timeout 5000 --require ./tests/hooks.js --exit tests/tenant-middleware.body-credential.test.js` — **must fail today** and
pass after R6. A test that passes on landing is the wrong test here; it would mean it is not
testing BF-25.

**Blocks on:** nothing.

---

### R4 — T3.0 half 1: configuration surface and credential bootstrap research

**Why now:** no conflict surface, and it is the input to R6.

**Scope, per plan §T3.0(1):** enumerate every `SETTINGS_*` variable and plugin credential; classify
secret vs not; state what a tenant may override versus what the hoster pins; and gather the
bootstrap/rotation evidence D13/D14 currently lack. Must also answer the per-tenant signing key's
**rotation** story, which D14 explicitly flags as not free.

**Two things this report must settle that the plan does not name**, both surfaced above:
- whether per-tenant alarm thresholds are tenant-overridable (R9 needs this);
- where deployment metadata lives (§4) — it is a low-risk first consumer of the same table.

**Gate:** no command decides a research deliverable, and pretending otherwise is how a gate goes
vacuous. The checkable part is `make verify-refs`, which confirms every code reference in the
report resolves. The *real* gate is deferred to R6: **R6 must be able to name every column it adds
from R4's enumeration, with no column arriving from outside it.**

**Blocks on:** nothing.

---

### R5 — Seam rebase onto a moved dev  *(d2)*

**Why here:** cannot start before dev moves; must not start after all nine branches land (§1.2).

**Scope:** rebase `seam/t1-2-storage-interface` (and the 15 ancestor seam branches, which GT1
measured as linear) onto the post-Phase-0 dev, resolving each conflict **according to R2's ledger**.

**Gate, two parts, both required:**
- `git merge-tree --write-tree origin/dev seam/<tip>` exits 0;
- `npm test` green in `externals/work/crm-seam` (whole tree, no file argument — see §2 preamble).

**Rollback, and the one-way door — added by adversarial review, which found neither stated.** A
rebase of a 16-branch chain is the closest thing to an irreversible operation in this programme, and
nothing above told the reader how to get back.

- **Before touching anything**, record every pre-rebase tip:
  `git for-each-ref --format='%(refname:short) %(objectname)' refs/heads/seam/ > docs/60-research/seam-tips-pre-R5.txt`,
  and commit that file. `git reflog` expires; a committed file does not.
- **Rollback is `git reset --hard <recorded tip>` per branch**, and it is only real if the tips were
  recorded first. Do not rely on `ORIG_HEAD`; a 16-branch rebase overwrites it fifteen times.
- **The one-way door is squashing.** §6 item 6 leaves open whether the 15 ancestor branches rebase
  per-branch or as a squash. A squash discards the per-branch history that R2's ledger cites, so
  after a squash the ledger's "which change is authoritative and why" can no longer be checked
  against the commits it names. **Decide per-branch versus squash before starting, not during**, and
  if squashing, tag the pre-squash tips so the provenance R2 exists to preserve is not destroyed by
  the operation R2 was written to inform.
- **Rule 5 of this programme's standing rules applies literally here**: the `externals/work/crm-*`
  worktrees belong to other sessions. R5 must not delete or repoint a worktree it did not create.

**Blocks on:** R2 (the ledger is the resolution authority), **and a release-train decision** — which
Phase 0 branches land on dev and when. Owner: maintainer. See §5.

---

### R6 — T3.0 halves 2-3: schema and wiring

**Scope, per plan §T3.0(2)(3):** per-tenant configuration and credential storage in
`lib/admin/platform.sql`, including the per-tenant signing key and a referent for
`tenant_members.subject_id`; supply T3.3's `deriveEnv` overrides from it; make `isApiKey` and
`verifyJWT` tenant-scoped.

**Note on the amendment site.** GT3 measured that the plan's T3.3 row cites `tenant-context.js:137`,
which is the *comment*; the mechanism is `PER_TENANT_ENV_KEYS` at L143 and the copy loop at L278.
R6 must amend L143/L278. A change at L137 alone edits a comment and ships nothing.

**Gate:** `node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js --timeout 5000 --require ./tests/hooks.js --exit tests/tenant-signing-key.test.js`, with the arm that makes D14 worth doing:
a token minted for tenant A must fail against tenant B **as a signature failure, not a claim-check
failure** — assert on the failure *mode*, not just the rejection. A claim-check rejection would pass
a naive test while leaving BF-25's bug class alive, which is the whole point of D14.
Plus R3's test, which must now pass.

**Blocks on:** R4, R5.

---

### R7 — BF-24 before the nginx recipe

**Why separate from R8:** its deadline is a publication, not T2.6. The register records the
maintainer's decision to land BF-24 before publishing the nginx recipe, because path-prefix
multitenancy over websockets depends on the proxy asserting the tenant in a header — the exact
mechanism BF-24 makes bypassable.

**Gate:** a test asserting `TRUST_PROXY=false` + `TENANT_HOST_HEADER=x-forwarded-host` refuses to
start, **with a control** asserting that `TRUST_PROXY` *unset* also refuses. Without the control the
test passes if the guard fires for the wrong reason — which is how the defect arose (the marker is
set only on the compatibility trust function).
`node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js --timeout 5000 --require ./tests/hooks.js --exit tests/tenant-host-header-guard.test.js`.

**Blocks on:** R5. **Gates:** publication of the nginx recipe. Owner of that publication decision:
maintainer.

---

### R8 — BF-19, BF-21, BF-22

**Why wave 2, not wave 3:** all three are in `lib/api3/storage/pgCollection/`. R5 already has
someone inside the seam's storage layer with the ledger open. A separate excursion later costs the
re-learning twice.

**Why not wave 1:** none is live (§0.4 sharpens *why* for BF-21), and doing adapter work on a branch
about to be rebased is what produced §0.5.

**D4 is the reason none of these may be deferred on principle.** MongoDB is permanent for
single-tenant, so the seam carries two mature backends forever. That does **not** make these urgent
to operators — they are §1b, pre-release, and PostgreSQL is wired for `entries` only. It makes them
**undeferrable**: there is no future event that removes them. "Fix it when Postgres lands" is
unavailable because Postgres landing is what *exposes* them, and "fix it when Mongo goes" is
unavailable because Mongo does not go. BF-21 is the sharpest case — a permanent divergence that
compounds with every write, where the deleted field never comes back.

**Gates** (both harnesses exist; both need their own mongod and PostgreSQL — they write, so pointing
them at a shared instance corrupts it; defaults 27023 and 15439):
- BF-19: `WORKTREE=<seam> PGPASSWORD=… node tools/qc/typeguard-arm.js` — column and jsonb branches
  must order identically to mongod, including on mixed-type data, which is where the shipped
  translation currently sorts a string `sgv` first where MongoDB sorts it last.
- BF-21/BF-22: `WORKTREE=<seam> PGPASSWORD=… node tools/qc/write-arm.js` — currently 23 agree /
  4 differ / 0 vacuous. **Gate: 0 differ**, with the vacuity count still reported and still 0.

**Blocks on:** R5. **Gates:** T2.6 must not start until these pass.

---

### R8a — BF-21 mode-agreement canary  *(do with R8; it is an afternoon)*

**Why it exists:** §0.4. Today's agreement is an accident of `entries.js` asking for `'merge'` —
**eight of the nine call sites already disagree across the two backends**. All eight ask for
`'replace'` explicitly; none relies on a default (see §0.4's correction block — an earlier draft of
this item claimed four silent sites and that claim is withdrawn). A one-word change to `entries.js`,
or any second collection gaining a PostgreSQL schema, makes BF-21 live with no other edit.

**Gate:** a test that enumerates every `bulkUpsert` call site in `lib/`, resolves the *effective*
mode for each — **parsing the call, not a line-oriented `grep`, because this codebase puts the
options argument on the call's continuation line and a grep-based census reads it as absent; that
error is what §0.4 had to correct** — and **fails if any collection with a PostgreSQL schema
resolves to a mode the PostgreSQL adapter does not implement.** It must also fail if any call site
resolves to *no options at all*, since MongoDB would then default to `'replace'` while PostgreSQL
hardcodes `'merge'` — that case does not exist today and the gate's job is to keep it that way. It
passes today and fails the moment the accident ends.
`node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js --timeout 5000 --require ./tests/hooks.js --exit tests/pg-bulkupsert-mode-agreement.test.js`

**Non-vacuity arm, required:** the test must be run once with `entries.js:168` flipped to
`{mode:'replace'}` and must FAIL. Without that arm the gate passes trivially on a census that
happens to find nothing, which is the first of the two ways this programme has seen checks go
vacuous.

This gate is worth more than BF-21's own fix if the fix slips, because it converts a silent
divergence into a red test.

**Blocks on:** nothing technically; scheduled with R8.

---

### R9 — T4.4: the per-tenant evaluator, and alarms back on

**Four items, from §7a rows 2, 3, 4 and 7.**

**(i) Per-tenant evaluation loop inside `withTenant`.** §7b sized it: 32.7 KB and 1.94 ms p50 /
2.14 ms p95 per tenant per evaluation, versus 852.1 KB and 27.5 ms p50 for whole `ddata` — 26x less
memory, 14x less CPU, identical alarm emitted. At a 30% event-loop budget, ~155 evaluations/s/process.
Two agents measured this independently, bottom-up and top-down, without reading each other.
**The ordering that survived and the absolute that may not**: the slice is decisively cheaper than
whole `ddata` on every axis both agents measured; the specific figure 1.94 ms is one fixture (576
SGVs, 600 treatments, 576 devicestatus, 1 profile) on one machine. Treat 26x/14x as the finding and
155/s as a planning figure, not a capacity guarantee. Per this programme's §8 convention, the
ordering is what has been stable across passes.

**(ii) Per-tenant error boundary.** Confirmed by reading `bootevent.js:360-369` (crm-seam): the
`data-loaded` handler calls `sandbox().serverInit`, `plugins.setProperties`,
`notifications.initRequests`, `plugins.checkNotifications` and `notifications.process` with **no
try/catch around any of them**. The only guards are *per-plugin*, inside `plugins/index.js:187-191`
and `:199-203`. So a throw from `serverInit`, `initRequests` or `process` escapes the handler
entirely — and in a plain per-tenant loop over that block, one tenant throwing means **every later
tenant is never evaluated**. Read from source, not executed.

**(iii) Health signal for a silent per-tenant outage.** The same per-plugin `try/catch` that
contains a bad plugin also *hides* it: it `console.error`s and continues, so a plugin that throws on
one tenant's data stops contributing alarms and nothing but stdout says so. Under `multi` that is a
per-tenant alarm outage with no signal. Note the precedent T3.2 set and follow it: **health reports
only what has a producer** — do not emit `alarms: ok` for a tenant whose evaluator has never run.

**(iv) The clock.** `lib/sandbox.js:50` — `serverInit(env, ctx)` hardcodes `sbx.time = Date.now()`,
and both `lastEntry` (`:143`) and `lastNEntries` (`:152`) drop entries whose mills exceed
`sbx.time`. **The mechanism
already exists one function away**: `clientInit(ctx, time, data)` at `:85` takes `time` as a
parameter and assigns it at `:91` (`sbx.time = time`). So the fix is to give `serverInit` the parameter `clientInit` already has, not to invent
a clock. The design decision that remains is the one §7a names and T4.4a only half-answered: snooze
is measured in **data** time, ack in **wall** time. T4.4a chose wall time for ack with reasons; the
evaluator must state its choice for snooze explicitly rather than inherit `Date.now()` by default.

**Gate — this is §7a's rule, and it is carried verbatim rather than softened:**

> Alarms go back on when a test shows tenant A's alarm reaching A and not B, through the real
> producer path, with a snooze that survives a restart and a process change.

As a command: `node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js --timeout 5000 --require ./tests/hooks.js --exit tests/alarm-tenant-isolation.test.js`, with four arms, all required:
1. A's alarm reaches A and **not** B, through the real producer path — not a stubbed emitter;
2. a snooze set on A survives a **process restart** (T4.4a's durable ack store);
3. a snooze set on A in process 1 is honoured by **process 2** (the sibling-ack path,
   `loadDurableAcks`);
4. **a control that removes the tenant binding and must FAIL** — without it, a harness where no
   alarm ever fires passes every one of arms 1-3. This is the same vacuity that made §7b's two runs
   nearly worthless (`settings.enable` matching `plugin.name`, not the file name, left every alarm
   plugin inert and nothing looked wrong). It must not be re-learned a third time.

**Nothing here may be marked done by inference**, including by this roadmap. The `ctx` work in R1 is
a prerequisite, not a partial completion of R9.

**Blocks on:** R1, R6.

---

### R10 — Deployment metadata

See §4. Scheduled to ride R6's schema; blocks nothing.

**Gate:** `node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js --timeout 5000 --require ./tests/hooks.js --exit tests/deployment-metadata.test.js` — asserts the platform-level contact is
servable **with no tenant binding** (the failure case it exists for), that a tenant value overrides
it for a bound request, and that the two are never concatenated into one string.

---

## 3. How the ordering respects the three stated constraints

**D4 — MongoDB is permanent, so (b) cannot be deferred on "Postgres will replace it".** Handled in
R8. The argument is made in the *undeferrable* form rather than the *urgent* form, because the
urgent form is not true and claiming it would be the kind of overstatement this programme's §8
exists to prevent. These are pre-release entries with a named gate (T2.6), not operator exposure
today. What D4 removes is the escape hatch: two mature backends forever means a divergence is
permanent, and BF-21's is cumulative — every write widens it and a deleted field never returns.

**§7a's rule — carried, not softened.** R9's gate is the sentence verbatim, decomposed into four
arms of which one is a deliberate failure control. The roadmap adds nothing to the rule and removes
nothing from it. It also does not let R1 count as progress toward it: R1 is listed as a
prerequisite, and §7a's "nothing may be marked done by inference" is restated at R9 so that a future
reader of R9 alone still meets it.

**The `ctx` hazard — settled *before* a per-tenant `ctx` is designed.** R1 is in wave 1 and R9 is in
wave 3, with R9 explicitly blocked on R1. §0.1-0.3 do part of the settling already, by measuring
that the hazard is three mechanisms rather than one; R1's job is the decision and the harness, not
the discovery. The hazard is now *sized*, which is what moved it from a blocker of unknown depth to
a scheduled item.

---

## 4. Deployment metadata: the parked question, answered

**The question** (parked at `nightscout-multitenancy-discussion-2026-09-09.md:2941`, by explicit
direction so it would not delay the rest): is operator-supplied deployment metadata — support
contact and similar — **static per deployment** or **per tenant group**?

**Recommendation: two distinct fields with different owners, a required platform-level value, a
tenant-level value that takes precedence when present, and no merging of the two.**

Not "per tenant". Not "static". Both, with a stated precedence — which is D7's two-planes shape
applied one layer up.

**The reasoning, in the order that decides it.**

**1. The failure mode picks the answer.** A support contact matters at exactly one moment: when
something is broken. If it is stored *only* per tenant, then the cases where a user most needs it —
an unresolvable slug, a suspended tenant, a database outage, the boot-error page — are precisely the
cases where the tenant record cannot be read. A per-tenant-only contact is unreachable when it is
needed. So a platform-level value must exist and must be **servable with no tenant binding**. This
is the same argument D7 makes for the admin plane's unreachability, one layer up, and it is why
R10's gate tests the unbound case first.

**2. D15 already forces the storage split.** Under `single`, the value comes from the process
environment and there is exactly one — unchanged, and this recommendation must not disturb it (D1:
single-tenant is not a degraded mode). Under `multi`, D15 says hosted entrypoints must not read
env-sourced config, so the platform value is a **deployment row** and the tenant value is a
**tenant row**. The two modes do not share a code path for this, which is what D15 requires anyway.

**3. Do not merge them into one resolved string.** A single "whichever is set" value hides *which
party is being contacted*, and those are different actions with different response times. For
someone whose glucose data has stopped arriving, "ask the person who set up your site" and "ask the
company hosting it" are not interchangeable. Render both, labelled.

**4. It is a good first consumer of R6's schema.** It is not a secret, so it needs none of the
credential machinery — but it *is* tenant-administrable, which makes it a low-risk canary for the
per-tenant config table before that table carries signing keys. That is why R10 rides R6 rather than
preceding it.

**5. A constraint the question does not mention, and it is the one to get wrong.** A tenant owner is
frequently a private individual — commonly a parent running a site for a child. A tenant-supplied
support contact is **that person's personal contact details**. It must be treated as tenant-controlled
personal data: not exposed on any unauthenticated endpoint by default, not written to logs, and not
included in any export that crosses a tenant boundary. The platform-level contact is an
organisational address and carries no such constraint. Collapsing the two fields into one would
collapse this distinction too, which is a second and independent reason not to merge them.

**Audience note.** Wherever this metadata is *rendered* — a boot-error page, a suspended-tenant
response, a push notification — that text is read by someone managing their own or a family member's
diabetes, often while something is already wrong. It must use plain language, say plainly which
party to contact and for what, and must not imply that contacting anyone is a substitute for the
person's own care team where the problem concerns their therapy rather than the software. This
roadmap does not draft that copy; it records that the copy is user-facing and is governed by that
standard rather than by contributor-facing conventions.

**Why it recurs despite blocking nothing.** It surfaces at three sites that each get designed
independently: the boot-error page (`lib/server/app.js` installs `app.get('*', bootErrorView)`), the
tenant-suspended response (plan §2.10), and push notification text. Each designer needs to know whose
name goes on the message. Recording the answer once is cheaper than answering it three times
inconsistently — which is the actual cost of leaving it parked, and the reason to close it with R6
rather than park it again.

---

## 5. Release-train dependencies, and who owns each decision

| # | decision | who owns it | what it gates here |
|---|---|---|---|
| 1 | **Which Phase 0 branches land on dev, and when** | maintainer | **R5**, and therefore all of wave 2 and wave 3. The rebase target does not exist until this happens |
| 2 | **Whether `bf/reads` still lands independently** | maintainer | Sequencing. `bf/coercion` is now an ancestor of `bf/reads` (§0.5), so they are one unit unless deliberately re-split. The sequencing document's parallel-landing assumption predates this |
| 3 | **When the nginx / path-prefix recipe is published** | maintainer | **R7**. The decision to land BF-24 first is already recorded; what is unscheduled is the publication |
| 4 | **When cut 5 (`chore/nightscout-modernization`) ships** | maintainer | Everything in (a), (b) and (c) is based on cut 5 per D9. On the adopted train that is the **fourth** release: 15.0.9, then cut 1, then cut 2, then 3+5 combined (release-readiness §5; cut 4 is held back behind a deprecation release and is not in this count). **No tenancy work reaches any artefact before then** — which is a reason the ordering above can afford to be careful |
| 5 | **When T2.6 starts** | maintainer | **R8** gates it. T2.6 is what makes BF-19/21/22 live |

**One thing this roadmap deliberately does not do.** It does not propose a date for R5. GT2 measured
that the release-readiness document's "each cut costs zero rebase work today" was false when it was
written, because it was measured on a basis that hid 59 commits of drift. Proposing a rebase date
from here would repeat that error in the other direction. R5's trigger is an event — Phase 0 on dev —
and the event has an owner.

---

## 6. Open questions

Each names who must settle it. An honest open question is worth more here than a confident guess,
and three of these are questions this roadmap **could not** settle rather than chose not to.

1. **Per-tenant plugin-registry memory is unmeasured.** §0.2's recommended path for the `language`
   half of R1 initialises one plugin registry per tenant. §7b measured the per-evaluation *slice*
   (32.7 KB), which is a different thing and does not bound registry residency. If registries are
   expensive, R1 falls back to editing 21 plugins. **Settled by: whoever takes R1**, with a
   measurement, before choosing.

2. **Does `bf/coercion`'s schema-driven coercion actually subsume the seam's `coerceExistsArguments`?**
   It is more general in principle — operator operands generally, versus `$exists` only — but the
   seam's version runs *before* the walker and detaches/reattaches, which may cover an ordering the
   schema-driven one does not. **Not measured here.** R2 must measure it rather than assert it.
   **Settled by: whoever takes R2.**

3. **Whether per-tenant alarm thresholds are tenant-overridable or hoster-pinned.** R9 cannot build
   a per-tenant evaluation loop without knowing which. It is a policy question with a safety edge —
   a hoster pinning thresholds constrains what a tenant can be alerted about — and it is not one an
   agent should answer. **Settled by: maintainer, as an input to R4.**

4. **Snooze in data time versus wall time.** T4.4a chose wall time for ack and gave reasons. The
   evaluator's choice for *snooze* is unsettled, and §7a flags that a batching or replaying
   evaluator cannot own its clock today. This is not purely technical: a snooze that means "20
   minutes of wall clock" and one that means "20 minutes of CGM data" behave differently during a
   sensor gap, which is when alarms matter. **Settled by: maintainer, with R9's author.**

5. **Whether `cob.setProperties` is quadratic in treatments.** §7b measured it as ~74% of a 27.5 ms
   evaluation block and explicitly named this as unmeasured. It bounds R9's per-tenant throughput
   and it is the single largest term in the alarm path's cost. **Settled by: whoever takes R9**, or
   earlier by anyone with a corpus.

6. **Whether the 15 ancestor seam branches rebase as cleanly as the tip.** GT1 measured the chain as
   linear and every branch as an ancestor of `seam/t1-2-storage-interface`. The conflict measurement
   in §0.5 was taken against the **tip only**. A per-branch rebase may surface conflicts the tip
   measurement hides. **Settled by: whoever takes R5**, before committing to a per-branch rebase
   rather than a squash.

---

## 7. How every number in this document was measured

Per the programme's §8 convention: what was measured, on what, and by what method.

**Environment.** Main repo HEAD `75c38a17`; `externals/cgm-remote-monitor-official` at `a8888f0d`
(`origin/dev`); `externals/work/crm-seam` at `81a1f6ce`. Node v24.15.0. No fetch was performed, so
all remote-tracking refs are as of GT1's fetch. No branch, worktree or shipping file was modified;
no network call was made.

**Branch topology (§0.5).** `git merge-base`, `git rev-list --count` and `git log` per branch.
`git merge-base --is-ancestor bf/coercion bf/reads` → true. Conflict table from
`git merge-tree --write-tree --name-only seam/t1-2-storage-interface <branch>` for each of the nine,
reading the exit code and the conflict block. `merge-tree` writes only to the object store; no
working tree was touched.

**Duplicated `$exists` fix (§0.5).** `git log -S coerceExistsArguments seam/t1-2-storage-interface --
lib/server/query.js` → `e0564167`, 2026-09-14. `git log -1 bf/coercion` → `88d1f8a4`, 2026-09-15.
`git merge-base --is-ancestor e0564167 origin/dev` → false (seam-only).

**`ctx` shape (§0.1-0.3).** Executed, not read. Script at
`<scratchpad>/ctx-capture2.js`, run with cwd `externals/work/crm-seam` (required — `loadLocalization`
resolves `./translations/...` relative to cwd). Results:

```
levels singleton (require twice, ===)            : true
ctxA.levels === ctxB.levels                      : true
ctx.language re-pointed to B, ctx reader         : B-URGENT
  ... but the plugin's CAPTURED translate        : A-URGENT   <- capture confirmed
  ... control: a per-call reader on same ctx     : B-URGENT   <- non-vacuity
tenant A toDisplay(2) right after A booted       : A-URGENT
tenant A toDisplay(2) after tenant B booted      : B-URGENT   <- last boot wins
captured translate after offerTranslations       : ORIGINAL -> MUTATED
```

The per-call control matters: without it, the `A-URGENT` result is also consistent with the
re-point simply not having happened. The control shows the re-point *did* happen and that capture
is what ignores it.

**Plugin census (§0.3).** `grep -cE '^\s*(var|let|const)\s+(translate|levels|moment)\s*=\s*ctx\.'`
and `grep -cE 'sbx\.(translate|levels|language)'` over `lib/plugins/*.js` in crm-seam. 22 files
match either; 21 capture, `treatmentnotify.js` is 0-capture/9-sbx, `ar2.js` is 2/6.
`grep -c` over `require('../levels')|require('./levels')` → 2 files (`lib/server/bootevent.js`,
`lib/client/index.js`); `ctx.levels|sbx.levels` outside `lib/client/` → 52 occurrences.

**BF-21 (§0.4).** `grep -rn bulkUpsert lib/` in crm-seam (`81a1f6ce`) returns nine call sites in
`lib/server/` and `lib/authorization/`. **The original pass claimed each was read to extract its
options argument; it was not** — the options bag was taken from the grep line, which truncates the
four calls that continue onto a second line, and that produced the "no options at all" row §0.4 now
retracts. The corrected census reads each call through its closing parenthesis
(`storage.js:143-144`, `treatments.js:31-32`, `treatments.js:120`, `entries.js:168`,
`activity.js:61`, `activity.js:102-103`, `food.js:64`, `food.js:122`, `profile.js:101-102`) and was
cross-checked against `guard()` at `mongoCollection/index.js:57-62`, which forwards every argument. Read
`lib/server/entries.js:163-172`, `lib/api3/storage/pgCollection/index.js:286-300`,
`lib/api3/storage/mongoCollection/modify.js:253-266`. PostgreSQL's `bulkUpsert (ops)` declares no
options parameter and passes the literal `'merge'` to `write()` at line 292; MongoDB's
`bulkUpsert (col, ops, options)` resolves `const mode = (options && options.mode) || 'replace'` at
line 255. The 1 / 4 / 4 split in §0.4's table is that census, counted by hand from the nine sites.
Read, not executed — no database was contacted, which is also why R8a's gate is specified with a
break-it arm rather than claimed to pass.

**Line citations re-checked at HEAD `08753474`.** Every `file:line` in this document was re-resolved
against crm-seam `81a1f6ce` with `sed -n`. `sandbox.js` `:50`, `:55-57`, `:85` (`clientInit (ctx,
time, data)`), `:91`, `:143`, `:152` resolve exactly; `plugins/index.js:187-191` and `:199-203`
resolve to the two per-plugin `try/catch` blocks; `bootevent.js:360-369` resolves to the unguarded
`data-loaded` handler. **Two did not resolve and were corrected**: the `ctx.levels.translate`
mutation is at `bootevent.js:212` (this document said `:218`) and its browser twin at
`lib/client/index.js:241` (said `:234`). **Adversarial review found three more, so the
sentence above overstates the coverage of that re-resolution pass and is left standing only so the
overstatement is visible**: `ctx.moment = require('moment-timezone')` is at `bootevent.js:19`, not
`:17`; `clientInit`'s signature is at `sandbox.js:85` (`:91` is the `sbx.time = time` assignment
inside it); and `sandbox.js:152` belongs to `lastNEntries`, not `lastEntry`. All three are corrected
in the body, bringing the total to five. A re-resolution pass that reports "two did not resolve" and
misses three more is itself an unverified claim, and is recorded here rather than quietly amended. Recorded rather than quietly fixed because GT3 found the
same class of drift in the register, and a wrong line number is how a reader concludes a mechanism
is not there.

**§7a items (ii)-(iv) (R9).** Read from source, not executed: `bootevent.js:360-369`,
`plugins/index.js:184-203`, `sandbox.js:45-57` and `:85-95`. Marked as read rather than run because
executing the alarm path end-to-end is R9's own gate, not a prerequisite for scheduling it.

**Inherited, not re-measured.** §7b's 32.7 KB / 1.94 ms / 852.1 KB / 27.5 ms / 155 per second, and
BF-19's and BF-22's reproductions, are taken from the cited reports and their named harnesses
(`tools/qc/typeguard-arm.js`, `tools/qc/write-arm.js`, `tools/qc/alarm-critical-slice.js`,
`tools/qc/ns-evaluator-arm.js` — all present on disk). GT1-GT4's findings are taken as given except
where §0.5 re-measured and found movement.

**One claim withdrawn, recorded because the withdrawal is the useful part.** An intermediate run
showed `levels.translate` behaving as the identity function — `levels.language =
require('./language')()` is called with **no `fs` handle**, so its catalogue never loads. That looked
like a shipping defect: alarm level names untranslated for every non-English operator. It is not.
`lib/server/bootevent.js:212` re-assigns `ctx.levels.translate = ctx.language.translate` at boot, and
`lib/client/index.js:241` does the same in the browser. The result was an artefact of testing the
module without booting it. It is reported here because the *same* mutation, harmless with one
tenant, is exactly what makes `levels` unshareable across tenants — the artefact and the real defect
are the same line of code seen from two directions.
