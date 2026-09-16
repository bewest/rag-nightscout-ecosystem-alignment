# E3 — gate vacuity audit of the work queue

**Status: DRAFT for maintainer review.** It changes `queue/work-queue.yaml`,
adds `queue/gate-controls.yaml` and three instruments under `tools/queue/`, and
it moves one item from `ready-to-push` to `gate-not-met`. Nothing was pushed,
merged, tagged or published. Rule 0 holds throughout: every measurement below
was taken locally, and the only network calls are two read-only `git ls-remote`
invocations against repositories this programme already tracks.

Measured 2026-09-15. Repository head `08753474`; `origin/dev` at `a8888f0d`.
**The manifest moved under this audit.** It held 62 items and 73 runnable gates
when the audit began and 74 items and 99 runnable gates when it finished —
another session was adding gates throughout. Every count below is against the
later state, and the instrument added here reports any gate added after it as
`UNCONTROLLED` rather than silently passing it.

Provenance, per rule 3: everything in the tables below was **reproduced** — each
control was executed and its exit status recorded. The three findings that are
read-derived are marked as such and are all about *intent*, not behaviour.

---

## 1. What the critic found, and what was actually wrong

The completeness critic proved the *validator* non-vacuous — eleven injected
manifest defects caught, one control passed — and observed that the *gate
scripts* had never had the same treatment. Two were demonstrably vacuous. Both
are fixed. The audit then found **four more** that the critic did not name.

| # | item | the gate | why it could not fail | provenance |
|---|---|---|---|---|
| 1 | P0-C | `grep -n "console.log('Loading', opts)" lib/authorization/storage.js && exit 1 \|\| exit 0` | the code reads `console.log('Loading',opts)` with **no space** after the comma, so the pattern never matched and the `\|\| exit 0` arm always fired. The item reported **3/3 PASS** on a property its own `describe` said was false. | reproduced |
| 2 | P0-E | `git log --format=%H bf/reads \| grep -q .` | asserts the branch has ≥1 commit. Re-run here against `origin/dev`, `origin/master` and `bf/alarms`: passes for all three. | reproduced |
| 3 | **P0-D** | `python3 -m tools.nsschema.emit.coercion_emit --drift` | the emitter's `main()` ends in `return 0` **unconditionally**. Run here: exit 0 while printing `DRIFT vs the shipping walkers: 157 disagreements`. It also compares against a hard-coded transcription of `origin/dev`'s walkers, so it says nothing about `bf/coercion` and would exit 0 with the branch deleted. | reproduced |
| 4 | **DOC-MEMORY** | `test -f queue/work-queue.yaml` | vacuous **by construction**, not by accident: `status.py` loads the manifest before it runs a single gate, so if that file were missing the runner would abort and this gate could never be *observed* failing. A gate nobody can watch fail is not a measurement. | reproduced |
| 5 | **P0-A, P0-C, P0-E** | `npm run test:unit` | filed `integration` and therefore off by default, so three items' only behavioural gate never ran. Worse, the suite does not contain the branches' own tests: `tests/authdelay.test.js`, `tests/authsubjects.test.js`, `tests/api.alexa.test.js`, `tests/api.googlehome.test.js` and all five of `bf/reads`' new files match **neither** local script. The recorded "361 passing / 0 failing" could have held with every fix reverted. | reproduced |
| 6 | **P0-PIN** | `grep -q '234d47c…' package-lock.json` | passes against `origin/dev`'s own lockfile, because that SHA is what dev pins. **This one is not a defect** — it is documented as deliberately inverted, a handoff tripwire that must go red when P0-LOCK lands. It is recorded because any mechanical rule of the form "a gate is vacuous if it passes on the base" would have condemned it. | reproduced |

### P0-C: which fix, and why

The choice was between a tolerant pattern (a **tracking** gate that correctly
reports gate-not-met) and deleting the gate and filing the residual as a
follow-up. **Tolerant pattern**, for three reasons:

1. The gate's own `describe` already said *"This gate FAILS today by design — it
   is the residual the branch has not taken."* The intent is recorded. The
   pattern was simply wrong. Changing the intent would be overriding a decision
   someone made, on no evidence. *(read-derived: the intent comes from the
   describe text, not from a run.)*
2. **Corrected while this audit was being written.** It was the only
   machine-checked record of the residual when the audit began; it is not any
   more. A concurrent session added `FU-RESIDUALS`, whose second gate asserts
   the same absence against `origin/dev` with a whitespace-tolerant pattern and
   is `gate-not-met`. That session hit the identical bug from the other side —
   its own `describe` records that its first draft copied the with-space
   quotation, "searched for a string that is not in the file, matched nothing,
   and PASSED while the defect was present". Two agents, two instruments, one
   root cause: **the with-space spelling is what the documents say, and the
   no-space spelling is what the code contains.** The register still quotes the
   with-space form at
   `docs/30-design/remedial/nightscout-backfix-register.md:1005`. That is a doc-truth
   fix, not this audit's to make, and `FU-RESIDUALS` already carries it.
3. The residual is real and still present: `lib/authorization/storage.js:113` on
   `bf/auth`, `:84` on `origin/dev`. It is BF-05's sibling — an unguarded
   `console.log` of a query's options, i.e. filter contents to stdout. Same
   class as BF-05, which was fixed on `bf/reads`.

**Consequence, stated plainly: P0-C is no longer `ready-to-push`.** It is
`gate-not-met`, which is what the gates say. Two clean ways to green, both a
human's call and neither taken here: take the one-line removal onto `bf/auth`,
or move the residual to its own queue item and drop the gate from P0-C. What
must *not* happen is loosening the pattern again.

### P0-E: the replacement gates

The placeholder is gone. In its place:

- **`node tools/queue/gates/bf-reads-read-contract.js`** (`static`, needs no
  database) — 8 assertions driven through the four pure modules the six fixes
  live in: `parseCount`/`hasCount`/`applyCount`, the dotted-`?fields=`
  projector, the `_id` tiebreak in the v3 sort chain, and the count path's use
  of `api.query_for` with nothing printed to stdout. Its negative control is
  built in: `--rev origin/dev` runs the identical assertions against dev
  materialised from the object database into a temporary tree, and gives
  **4 failing**, one of them `lib/server/count.js: not present at this rev`.
  Also measured failing at `bf/alarms`.
- **five `integration` gates**, one per test file the branch adds.
- the ordering and CHANGELOG `no-gate` markers, kept and updated.

---

## 2. CORRECTIONS TO THIS TASK'S BRIEF (rule 1)

Three premises in the brief are wrong, and two of them would have produced a
worse queue if followed.

**(a) `TEST=api.count-parameter npm run test-single` does NOT run without a
database.** The brief says "13 passing in 2 seconds with no database" and
instructs that P0-E be given targeted test gates on that basis. Measured: with
the mongo URL pointed at a dead port it goes to **0 passing / 1 failing**,
timing out in the before-all hook. All five of `bf/reads`' test files need
MongoDB. They are fast only because a mongod happens to be listening on
`crm-bf-reads`' port 27032. They are therefore filed `integration` — and because
that would have left P0-E with no behavioural gate that runs by default, the
database-free contract gate above was written instead. *Reproduced: same file,
same command, only `CUSTOMCONNSTR_mongo`'s port changed.*

**(b) Worktree mongod isolation is only partly built.** The corrected-facts
block says "Each worktree has its OWN mongod port… the isolation is already
built." Measured, port by port:

| worktree | port in `my.test.env` | listener |
|---|---|---|
| `crm-bf-auth` | 27031 | yes |
| `crm-bf-reads` | 27032 | yes |
| `crm-bf-food` | 27033 | yes |
| `crm-bf-merge` | 27033 | yes — **shared with crm-bf-food** |
| `crm-bf-parms` | 27033 | yes — **shared with crm-bf-food** |
| `crm-bf-coercion` | 27030 | **no listener** |
| `crm-bf-alarms` | 27034 | **no listener** |
| `crm-bf-connect-pin` | — | **no `my.test.env` at all** |

Three worktrees share one instance, two name ports nothing is serving, and one
has no test environment. `bf/alarms`' two API tests cannot be run on this
machine at all, which is why their controls are marked `control-exempt` rather
than allowed to report a connection timeout as proof.

**(c) "Many gates likely invoke `npm run test:unit` believing it is 149
database-free files."** Three did, and the manifest already *said so* — each
carried a `describe` recording that test:unit is not database-free and is filed
`integration` deliberately. The real defect was different and worse: the suite
does not contain those branches' own tests. That is finding 5 above.

---

## 3. THE AUDIT TABLE

Every runnable gate, the property it asserts, how the property was broken, and
whether the gate caught it. The controls are now **declared**, in
`queue/gate-controls.yaml`, and re-runnable:

```
make queue-vacuity                 # 74 static/unit controls
make queue-vacuity SLOW=1          # plus the 15 branch ablations
make queue-vacuity NETWORK=1       # plus the two read-only ls-remote controls
python3 tools/queue/vacuity.py --self-test
```

**Result over all 95 distinct gate commands** (`vacuity.py --slow --network`,
reproduced 2026-09-15): **91 NON-VACUOUS, 4 EXEMPT, 0 VACUOUS, 0 UNCONTROLLED,
0 CONTROL-ERROR, 0 STUCK-RED.** One `STUCK-RED` was reported earlier in the
audit and is described in §3.6.

The manifest reached 74 items and 99 runnable gates (95 distinct commands) by
the end of the run. It will be larger by the time this is read: run
`python3 tools/queue/vacuity.py --list-uncontrolled` before trusting the
numbers, because a gate added after this audit is `UNCONTROLLED`, and
`UNCONTROLLED` is a failure of the instrument's subject, not a pass.

### 3.1 Ancestry gates — 12 gates

| property asserted | how it was broken | caught |
|---|---|---|
| the branch has not fallen behind `origin/dev` (`bf/alarms`, `bf/auth`, `bf/cache`, `bf/coercion`, `bf/connect-pin`, `bf/food`, `bf/merge`, `bf/parms`, `bf/reads`) | asked the same question about `origin/chore/nightscout-modernization`, a base none of them has taken | **yes**, exit 1 for all nine |
| `origin/master` is an ancestor of `origin/dev` | reversed the arguments | **yes**, exit 1 |
| the seam sits on `origin/chore/nightscout-modernization` | reversed the arguments | **yes**, exit 1 |
| `v0.0.13` is an ancestor of `release/v0.0.14` | reversed the arguments | **yes**, exit 1 |

### 3.2 Trial-merge gates — 14 gates

| property asserted | how it was broken | caught |
|---|---|---|
| the branch merges into `origin/dev` without conflict (eight Phase 0 branches) | merged each against `origin/chore/retire-jsdom`, measured to conflict with all of them | **yes**, exit 1 for all eight |
| each modernization cut merges into `origin/dev` cleanly | merged each cut against `bf/reads`, measured to conflict with all five | **yes**, exit 1 for all five |
| the seam merges with the modernization cut | merged the seam against `bf/coercion` | **yes**, exit 1 |

Four of these gates are **red against the live tree right now** — `retire-jsdom`,
`build-runtime-separation`, `compose-mongodb6` and `mime-exposure-review` all
conflict with dev — which is independent live evidence that the instrument fails
when it should. Their output is a measured conflict, not a crash; each was
inspected.

### 3.3 Branch test gates — 19 gates, ablated

Control: `tools/queue/gates/ablate.sh` builds a throwaway worktree of the
branch under `$TMPDIR`, puts the shipping code back to `origin/dev` while
keeping the branch's tests, runs the file, and exits with mocha's status. **Rule
6: it creates and removes its own worktree and never writes into another
session's.**

| item | test | ablation scope | result on ablated tree | caught |
|---|---|---|---|---|
| P0-A | `insulinage` | `lib/plugins/insulinage.js` +3 siblings | 3 passing / **2 failing** | yes |
| P0-A | `plugins` | same | 5 passing / **8 failing** | yes |
| P0-A | `api.alexa`, `api.googlehome` | — | **not runnable**: no mongod on 27034 | **EXEMPT** — see §3.6 |
| RT-D3 | `dependency-d3` | — | cwd is the shipping checkout | **EXEMPT** — see §3.6 |
| P0-C | `authdelay` | 7 lib files restored, `peer-address.js` removed | 2 passing / **9 failing** | yes |
| P0-C | `authsubjects` | same | 1 passing / **7 failing** | yes |
| P0-D | `query` | `lib/server/query.js` only | 24 passing / **4 failing** | yes |
| P0-E | five `api*`/`api3*` files | all 12 lib files | non-zero for all five | yes |
| P0-F | `npm test` (connector) | `index.js`, `backoff.js`, `builder.js`, `cycle.js` → `c1cce2a^` | node:test **failed** | yes |
| P0-G | `boluscalc.quickpick` | `lib/client/boluscalc.js` only | 6 passing / **5 failing** | yes |
| P0-G | `api.food.quickpicks` | 3 lib files + `quickpick.js` removed | 1 passing / **2 failing** | yes |
| P0-H | `receiveddata.merge` | `lib/client/receiveddata.js` | 10 passing / **2 failing** | yes |
| P0-I | `browser-utils.queryparms` | `browser-utils.js`, `language.js` | 1 passing / **5 failing** | yes |
| P0-I | `language` | same | 16 passing / **1 failing** | yes |

**Two ablations had to be narrowed, and the reason matters.** Reverting
*everything* on `bf/coercion` deletes `lib/server/query-coercion.js`, so mocha
dies at module load: a non-zero exit for the wrong reason. `--files=` restricts
the ablation to the wiring, and the control then fails on assertions
(`expected '1.5' to be 1.5`), which is the control that means something. Same
for `bf/food`'s `boluscalc.quickpick`.

**The ablation harness was itself vacuous in its first version**, and this is
the clearest illustration in the audit of rule 2's second half. v1 reverted with
`git checkout <base> -- <files>`. When a branch *adds* a file that path does not
exist at the base, git aborts the **whole** checkout, and nothing at all is
reverted — so the first `bf/coercion` ablation reported a comfortable
`28 passing, 0 failing` having broken nothing, and for several minutes looked
like proof that P0-D's test gate was vacuous. It was not. **The ablation was
mis-scoped.** v2 deletes added files instead of restoring them, prints its
scope, and refuses to run if the working tree came out unchanged. A second bug
in the same script — `( cmd | tail )` hands back `tail`'s status, which is
always 0 — would have made every ablation control report success. Both are
commented in the script so the next reader does not reintroduce them.

### 3.4 Node gate scripts — 24 gates over 19 scripts

Control: `empty-root-control.sh` runs the gate with `QUEUE_GATE_ROOT` pointed at
an empty directory. All 24 refuse to pass. **This is the weak form and the audit
says so**: it proves a gate reads its inputs, not that it reads the right
*property* of them. Where a sharper control exists it is named.

| script | sharper evidence |
|---|---|
| `bf-reads-read-contract.js` | **strong** — `--rev origin/dev` gives 4 failing; `--rev bf/alarms` likewise |
| `bf09-corpus-divergence.js` | **strong, internal** — its first finding is a control that a zero `absolute` beside a record lacking it diverges and two identical records do not |
| `d3-drag-clamp-covered.js` | **strong, internal** — it ablates the clamp expressions itself and reports the suite stayed 24-passing |
| `minimed-deprecation-path.js` | **strong, internal** — asserts the Dexcom path is still detectable, so red means MiniMed is bare |
| `register-rows-vs-details.js` | **strong, run here** — a copy of the register with one `### BF-nn` heading removed: `BF-18: table row at L190, NO detail section`, exit 1. A second ablation stripping every table row gives the shape-change finding, exit 1. |
| the other 19 gates | empty-root only; ten of them are red against the live tree, so they are not silently green |

### 3.5 Content, existence and remote gates — 26 gates

| property asserted | how it was broken | caught |
|---|---|---|
| P0-C: the residual `console.log` is gone | fixture containing the **no-space** spelling — the exact text the old pattern could not match | **yes**, and a positive fixture makes it green |
| P0-PIN: `package.json` names the v0.0.14 tarball | the same grep against `origin/dev:package.json` | yes |
| P0-PIN: the lockfile is still on the old SHA (**inverted**) | a copy of dev's lockfile with the SHA replaced by the tarball URL | yes |
| P0-LOCK: the lockfile names the tarball | fixtures both ways (gate is red today on purpose) | yes |
| P0-D: the vendored coercion table equals a fresh emission | flipped one field's declared type to `string` in a copy of the emission | yes |
| DOC-MEMORY: `queue-status` is a Make target | near-miss fixture `queue-status :` (with a space) | yes |
| DOC-MEMORY: `QUEUE.md` is not stale | `emit.py --check` against a file that is not the rendering | yes, and green against one that is |
| BFQ-10: compose sets `ulimits` | fixtures both ways | yes |
| P0-F: backoff rejects an unknown jitter mode | the same expression against `c1cce2a^:lib/backoff.js` | yes — the pre-fix merge order never saw the caller's option |
| P0-TAG: `v0.0.14` is an annotated tag | asked about `v0.0.13`, a lightweight tag (`cat-file -t` → `commit`) | yes |
| P0-TAG: the tag points at `release/v0.0.14` | compared `v0.0.13^{commit}` instead | yes |
| P0-TAG: the tagged `package.json` says `0.0.14` | same extraction at `v0.0.13` → `0.0.13` | yes |
| P0-TAG: `v0.0.14` is **not** on the remote yet | asked about `v0.0.13`, which is | yes (read-only `ls-remote`) |
| P0-T01: upstream still carries `dfe2753d` | grepped for an all-zeroes SHA | yes (read-only `ls-remote`) |
| FU-RESIDUALS ×3, FU-LIMIT ×2, RT-NODE-FLOOR-TESTED ×2 | same instrument against a ref or file where the property differs | yes, all seven |
| four `test -f` gates | an absent path, plus a positive control on a path that exists | yes — **weak by nature**; see below |

**Existence gates cannot be made strong.** `test -f X` can only be shown to
distinguish a present path from an absent one; nothing makes it assert anything
*about* X. Three of the four are red today (the work is not started), and the
fourth, P0-A's client bundle, got the best positive control available: the same
path under `crm-bf-reads`, where the bundle **is** present. `crm-bf-alarms` and
`crm-bf-connect-pin` are the only two of fifteen worktrees missing it.

The five category counts add up: 12 + 14 + 19 + 24 + 26 = **95**.

### 3.6 The four exemptions and the one STUCK-RED

| gate | why exempt |
|---|---|
| `npm ci --dry-run` (P0-LOCK) | Rule 0 — it resolves against the npm registry and a GitHub tarball for a tag that does not exist yet, and it cannot pass until a human pushes v0.0.14 |
| `TEST=dependency-d3` (RT-D3) | its cwd is the shipping checkout, which 19 worktrees hang off; rule 6 forbids ablating it. The gate is red against the live tree, and RT-D3's companion instrument carries its own internal control |
| `TEST=api.alexa`, `TEST=api.googlehome` (P0-A) | the ablation *does* exit non-zero and `vacuity.py` *would* call it NON-VACUOUS — but it exits non-zero because the test times out reaching a mongod that is not running on port 27034, not because the code was reverted. **A control that is non-zero for the wrong reason is worse than no control, because it reads as proof.** The exact command to run once a mongod exists on 27034 is recorded in the exemption. |

**`STUCK-RED`, reported once and kept as the demonstration it is:**
T30-RESEARCH's `test -f docs/60-research/tenant-config-surface-2026-09-15.md`
was given a positive control naming *this* file, which did not exist while the
audit was being written. The harness reported `STUCK-RED` — a gate that refuses
to pass on a known-**positive** — until the file was written.

> **Path note, 2026-09-16.** The command quoted above is the one that ran during
> this audit. The September material was moved into programme subdirectories on
> 2026-09-16, so T30-RESEARCH's gate and its control now both read
> `docs/60-research/tenancy/tenant-config-surface-2026-09-15.md`. The quotation is
> left as it was — it is the record of what was measured, not a current citation.
 That is the
opposite failure to vacuity, it is what you get from fixing vacuity carelessly,
and it is worth knowing the instrument catches it.

---

## 4. The instrument that would have caught this class

`tools/queue/vacuity.py`, driven by `queue/gate-controls.yaml`. One rule, the
`run:`/`no-gate:` rule applied one level up:

> Every runnable gate carries either a **control** — the same instrument applied
> to a state where the property is **false**, which must therefore exit
> **non-zero** — or an explicit **`control-exempt`** with a reason. A gate with
> neither is `UNCONTROLLED`, and `UNCONTROLLED` is never reported as a pass.

Controls are keyed by the gate's exact command text, so **editing a gate
detaches its control** and the edit forces the control to be re-authored rather
than silently inherited.

`--self-test` proves the instrument on four gates whose answer is known in
advance — the two historical vacuous gates, one real gate and one broken
control. Output, reproduced:

```
VACUOUS       a deliberately vacuous gate — the P0-E shape, an assertion that the branch has commits
VACUOUS       a deliberately vacuous gate — the P0-C shape, a grep whose pattern can never match
NON-VACUOUS   a real gate, for contrast — the replacement P0-E read contract
CONTROL-ERROR a control that cannot be set up
self-test: 4 of 4 as expected
```

It is a **separate target** from `make queue-check`, deliberately. Other
sessions add gates to this manifest hourly; a gate with no control yet should be
reported by an instrument someone runs on purpose, not break a CI target another
agent is depending on this minute.

### Controls are authored, never derived

Two gates prove the point. `P0-PIN`'s lockfile gate is deliberately inverted and
passes against `origin/dev` **on purpose** — any mechanical rule of the form "a
gate is vacuous if it passes on the base" would have condemned it. `RT-D3`'s
suite runs inside the shipping checkout, which no control may modify.

---

## 5. The branches moved; what the manifest said about them did not

| was | is | what was corrected |
|---|---|---|
| P0-E `base: bf/coercion@88d1f8a4` | `origin/dev@a8888f0d` | the two-deep stack existed only to resolve a CHANGELOG collision and is dissolved |
| P0-E gate: `is-ancestor bf/coercion bf/reads` | `is-ancestor origin/dev bf/reads` | the old gate asserted a fact that is now deliberately false, and was red |
| P0-E `blocks_on: [P0-D]` | `[]` | nine independent PRs, not four plus a stack |
| P0-E "8 commits at 0d19bb31" | "6 commits at 2ecfeb53" | third SHA this branch has been recorded at; all three are noted in `notes` so the next reader is not surprised |
| P0-E review "after P0-D is merged" | "NOT after P0-D" | — |

The **§3b concern survives and is not a merge hazard**, and P0-E's `notes` now
say so: `bf/coercion` gives `query.js` a new `collection:` option and `bf/reads`
fixes `aggregate.js`, which calls `query.js` through `api.query_for` and passes
no options — so the count path still gets the legacy default walker after both
land. Deliberately in neither PR.

`bf/coercion` was re-checked at `ab197bf8`: all gates green, and `TEST=query`
now has a real ablation behind it. Re-checked again at **`f829ea11`** on
2026-09-16 after a comment-only amend: still 4/4, still 28 passing.

---

## 6. Observations that are not defects

- **`seam/t1-2-storage-interface` conflicts with both `bf/coercion` and
  `bf/reads`** (`merge-tree` exit 1 for both), while merging cleanly with
  `origin/dev`, `origin/master` and every modernization cut. Expected — all
  three touch the query path — and it is the pair used as the seam's merge-tree
  control. It is recorded because the maintainer's linear ordering puts the
  backfixes under the seam eventually, and this is where that cost lands.
- `crm-bf-connect-pin` has no `my.test.env` and no client bundle, so no test
  gate is possible in it today. P0-PIN's gates are all `grep`, which is
  appropriate for a one-file, +1/−1 pin move.
- **Two sessions found the same defect independently within an hour**, from
  opposite directions: this audit from P0-C's gate, `FU-RESIDUALS` from the
  register's prose. Neither had read the other. The shared cause is that a
  string was quoted in prose, propagated into two gates by copy, and never
  compared against the file — which is the argument for a control rather than
  for more careful copying.

---

## 7. What a reviewer must check

1. **P0-C's state change.** `ready-to-push` → `gate-not-met` is the honest
   reading of a gate that is now correctly red, but whether an unguarded
   `console.log` of query options should block a *security* branch is a
   judgement, not a measurement.
2. **Whether the residual should move to its own item.** It effectively
   already has: `FU-RESIDUALS` (added by another session during this audit)
   gates the same absence against `origin/dev`. If the maintainer wants P0-C
   green, dropping the gate from P0-C is now a clean move, because the residual
   would still be tracked. What must not happen is loosening the pattern.
   Note the two gates are not redundant: P0-C's reads the `bf/auth` **worktree**
   and FU-RESIDUALS' reads `origin/dev` from the object database, and after
   `bf/auth` lands those are different questions.
3. **The four exemptions**, especially the two that exist only because no mongod
   is listening on port 27034. Start one and they become ordinary controls.
4. **The five P0-E integration gates.** They are the branch's real evidence and
   they are off by default. Someone has to run
   `make queue-status ID=P0-E INTEGRATION=1` before this branch is pushed.
5. **`coercion_emit --drift`.** This audit removed it as a *gate* and replaced
   it with a comparison that can fail. The emitter still returns 0 while
   reporting drift, which is fine for a report and wrong for a gate; whether
   `--drift` should also gain a non-zero exit is the emitter owner's call.

---

*Not medical advice.* This document is contributor-facing. Where these gates
cover behaviour an operator can see — alarm delivery, what a read request
returns, whether CGM data keeps arriving — the operator-facing wording lives in
each item's `operator_visible` field in `queue/work-queue.yaml`, and anyone
relying on Nightscout for their own or a family member's diabetes care should
talk changes through with their care team.
