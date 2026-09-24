# Release-assets critique — what is missing, and what is still vacuous

> **Snapshot, 2026-09-16, against `origin/dev` `a8888f0d`. Historical: a point-in-time review; its queue and vacuity counts (74 items then) have moved, and only the §2.1 P0-C missing-file idiom was re-checked (still present in `queue/work-queue.yaml` on 2026-09-22). Nothing here is released. Current facts: `queue/work-queue.yaml` (`make queue-status`, `make queue-vacuity`) and the [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**

**Status: DRAFT. Contributor-facing.** An adversarial completeness and non-vacuity review of the
work this workflow produced. Nothing here was pushed, merged, tagged or published. No branch SHA
moved. Written 2026-09-16 against `origin/dev` = `a8888f0d`.

**Basis convention.** Every finding below is labelled **[R] reproduced** (a command was run on this
machine and the quoted output is its output) or **[S] read-derived** (established by reading a file).
Rule 3: a source reading is never presented as a run.

**Scope.** I did not edit any other agent's output. Where I found a defect in someone else's file I
describe it here and leave the file alone.

---

## 0. The headline

The deliverables exist and are not stubs. The two named vacuous gates are genuinely fixed, and I
broke them again myself to prove it. The queue covers the register. The verification record reports
failures honestly, including the one nobody would have noticed.

Five things are weaker than the reports around them suggest, and one of them I would not ship on:

1. **Every reproduction behind the retirement decision lives in `/tmp`.** [R] Nineteen harness
   scripts back E1's 63 `[R]` claims and E2's reproductions. Zero are in the repository. §4.
2. **The repaired P0-C gate still passes when the file it greps does not exist.** [R] The fix made
   the pattern whitespace-tolerant; it did not stop the gate conflating "found nothing" with "could
   not look". A rename turns a security branch green. §2.1.
3. **The Rule 0 "have we shipped?" gate fails open.** [R] With the remote unreachable it reports
   "the tag is not published" — which is the answer it gives when it cannot ask. §2.2.
4. **`make queue-vacuity` covers 77 of 95 controls and its summary does not say so.** [R] E3's
   headline "91 NON-VACUOUS" is real but needs `--slow --integration --network`, which the target
   does not pass and the report does not name. §2.5.
5. **The connector release has no verification record** and nothing explains why. §3.2.

Two ablations were mis-scoped; they are recorded as such in §7, not as findings.

---

## 1. Check A — do the promised files exist, and is any of them a stub?

**[R]** All fifteen exist. None is a stub; the smallest is 2,420 bytes of structured template with
per-field instructions, not placeholder text.

Five more PR bodies exist beyond the five named in my brief, so **all ten Phase 0 branches are
covered**, not five:

```
bf-alarms.md 10008   bf-auth.md 14161    bf-cache.md 7773    bf-coercion.md 16064
bf-connect-pin.md 12741   bf-food.md 12447   bf-merge.md 8424   bf-parms.md 12116
bf-reads.md 15412   fix-connect-timer-jitter.md 12591
```

`releases/_template/README.md` points at `../README.md` for the convention; **[R]** that file exists
(8,201 bytes) although it was not in the promised list.

### 1.1 The structural claims in the brief, re-measured rather than taken on trust

**[R]** Every one holds:

| Claim | Measured |
| --- | --- |
| No branch touches `CHANGELOG.md` | 0 files changed vs `origin/dev` on all nine |
| All nine merge cleanly into `dev` | `merge-tree --write-tree` clean, nine for nine |
| `bf/coercion` and `bf/reads` merge cleanly with each other | clean — the stack really is dissolved |
| Backups intact | `bf/coercion.bak-changelog` `88d1f8a4`, `bf/reads.bak-changelog` `0d19bb31` |
| Six `bf/reads` commits content-identical | `range-diff` shows `=` for all six |
| `bf/coercion` differs from backup by changelog only | `range-diff` shows one `!`, hunk is `## CHANGELOG.md ##` |
| No stale "two-deep stack" language survives | 2 hits, both explicit retractions |

### 1.2 One defect in a written file

**[R]** `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md:77` gives the fork remote as
`git@github.com/bewest/cgm-remote-monitor.git`. That is a malformed SSH URL — it needs a colon,
`git@github.com:bewest/…`. Copy-pasted as written it fails. Cosmetic, but it sits in the one
document a maintainer would copy from at push time. Reported, not edited.

---

## 2. Check B — the gate audit

I created **one** throwaway worktree (`git worktree add --detach` from the shipping checkout into my
own scratchpad), used only that, and removed it. **[R]** Worktree count 19 → 18; the 18 pre-existing
worktrees are untouched and every branch SHA is unchanged.

**[R]** `make queue-validate`: 74 items, 5 parcels, 99 runnable gates, 99 explicit no-gate markers,
schema OK. `make queue-status`: **PASS=15 FAIL=29 UNMEASURED=30**, exit 1. The queue is honestly red.

### Ablation table

| # | Gate | Item | Control applied | Result |
| --- | --- | --- | --- | --- |
| 1a | `grep -nE "console\.log\('Loading',[[:space:]]*opts\)" … && exit 1 \|\| exit 0` | P0-C | as-is against `bf/auth` | **exit 1** — correctly red; matches `storage.js:113` |
| 1b | same, with the **old** pattern (space after comma) | P0-C | as-is | **exit 0** — historical vacuity independently confirmed |
| 1c | same, fixed pattern | P0-C | **repair the residual** (remove the `console.log`) | **exit 0** — correctly green. Non-vacuous |
| 1d | same, fixed pattern | P0-C | **delete the file** | **exit 0 — STILL PASSES.** See §2.1 |
| 2a | `ls-remote --tags origin v0.0.14 \| grep -q . && exit 1 \|\| exit 0` | P0-TAG | real remote | exit 0 (not published) |
| 2b | same | P0-TAG | **bogus remote name** | **exit 0 — STILL PASSES.** See §2.2 |
| 2c | same | P0-TAG | **network blocked** (`GIT_SSH_COMMAND=/bin/false`, dead proxy) | **exit 0 — STILL PASSES** |
| 2d | same | P0-TAG | query `v0.0.13`, which **is** on the remote | **exit 1** — correctly red when a tag really is published |
| 3a | `bf-reads-read-contract.js` | P0-E | as-is | exit 0, **8 checked / 0 failing** |
| 3b | same | P0-E | `--rev origin/dev` | **exit 1, 4 failing.** Non-vacuous |
| 3c | same | P0-E | `--rev bf/alarms` | **exit 1, 4 failing.** Non-vacuous |
| 3d | the **old** gate `git log --format=%H bf/reads \| grep -q .` | P0-E | run against `bf/alarms` | **exit 0** — historical vacuity independently confirmed |
| 4a | `coercion_emit --bundle … && diff -q … query-coercion.json` | P0-D | as-is | exit 0 |
| 4b | same | P0-D | **flip one `number` → `string`** in the checked-in table | **exit 1.** Non-vacuous |
| 4c | same | P0-D | diff against `origin/dev` (table absent there) | **exit 1.** Non-vacuous |
| 4d | the **old** gate `coercion_emit --drift` | P0-D | as-is | **exit 0** while printing `OVER 8, UNDER 148` — historical vacuity confirmed |
| 5a | `grep -q 'archive/refs/tags/v0.0.14.tar.gz' package.json` | P0-PIN | as-is | exit 0 |
| 5b | same | P0-PIN | against `origin/dev`'s `package.json` | **exit 1.** Non-vacuous |
| 5c | `grep -q '234d47c8…' package-lock.json` (deliberately inverted) | P0-PIN | lockfile updated to `v0.0.14` | **exit 1** — correctly flips red at handoff |
| 5d | same | P0-PIN | **lockfile deleted** | **exit 2** — fails loudly. Correct |
| 6a | `register-queue-coverage.js` | standing | as-is | exit 0, 3 checked / 0 failing |
| 6b | same | standing | strip `BF-41` from every `register:` list | **exit 1** — names `BF-41 (§1, register L153, open)`. Non-vacuous |
| 6c | same | standing | re-open `BF-12` in a register copy | **exit 1** — names `BF-12 (§1, register L127, open)`. Non-vacuous |

**Both gates the previous critic named are genuinely fixed**, and I confirmed both old versions were
vacuous by running them myself rather than believing the report. P0-D's and P0-PIN's replacements are
non-vacuous too.

### 2.1 P0-C's repaired gate still passes against a missing file — **this one matters**

**[R]** Ablation 1d. With `lib/authorization/storage.js` moved away, the gate exits **0**, which the
runner reads as PASS.

The E3 fix corrected the *pattern*. It did not correct the *idiom*. `grep … && exit 1 || exit 0`
maps grep's exit 2 ("could not read the file") onto the same branch as exit 1 ("read it, found
nothing"). So the gate answers "the residual is gone" in exactly the case where it did not look.

Why it is not cosmetic: P0-C is `bf/auth`, the **security** branch (BF-17 plaintext token, BF-30
throttle bypass). Its state is `gate-not-met` *because* this gate is red. Any refactor that moves or
renames `lib/authorization/storage.js` — and the modernization parcels move a great deal — silently
turns this gate green and moves a security branch to a state that reads as shippable. That is the
same class of failure as the original bug, with a higher blast radius, and the repair did not close
it.

The fix is one clause: `test -f lib/authorization/storage.js || exit 1` ahead of the grep.

### 2.2 The Rule 0 publication gate fails open — **I would not stake Rule 0 on this**

**[R]** Ablations 2b and 2c. `git … ls-remote --tags origin v0.0.14 | grep -q . && exit 1 || exit 0`
returns **0** when the remote is unreachable, when the remote name is wrong, and when the network is
blocked. Zero means "the tag is not published". The gate cannot distinguish *not published* from
*not asked*.

The pipe is what does it: `ls-remote`'s non-zero status is discarded by the pipeline, there is no
`set -o pipefail`, and the `|| exit 0` arm then fires on grep's empty-input exit 1.

**[R]** Ablation 2d shows the gate is not vacuous in the positive direction — asked about `v0.0.13`,
which is on the remote, it correctly exits 1. So the assertion is sound; only its failure direction
is wrong. For an ordinary gate, failing open is a nuisance. For the one gate in the system that
answers "have we already shipped this?", failing open is the wrong way round, because the whole
point of Rule 0 is that publication is irreversible.

The same unguarded-pipe shape appears in **six** gates total **[R]** (P0-C, P0-TAG, two in FU-LIMIT,
two in FU-RESIDUALS). The four `git show … | grep -q` instances have the identical flaw: a bad ref
makes `git show` fail, the pipe swallows it, and the gate reports the property satisfied.

### 2.3 Nothing asserts that a worktree-scoped gate is measuring the branch

**[R]** 13 of the 99 runnable gates run with a `cwd` under `externals/work/`, i.e. they measure a
**working directory**, not the branch that will be pushed. Today that is safe: all nine Phase 0
worktrees are at their branch tip with zero tracked modifications, measured. But **no gate asserts
it**. A worktree left dirty or checked out at an older commit by any of the concurrent sessions
sharing this checkout would make P0-C's grep, P0-PIN's two greps and every targeted test run report
on code that is not in the PR, with nothing anywhere going red.

This is cheap to close — one gate per item comparing `git -C <worktree> rev-parse HEAD` against the
branch tip and asserting a clean tree — and it is the single structural assumption the whole gate
system rests on that is currently unmeasured.

### 2.4 One residue in P0-E's otherwise good replacement

**[R]** Baseline runs 8 assertions; the `--rev origin/dev` control runs 6. The four BF-13 assertions
collapse into a single `BAD … lib/server/count.js: not present at this rev`. That is honest — the
module genuinely does not exist at `dev` — but it means the negative control for those four
assertions is *file absence*, not *wrong behaviour*. A `count.js` that exists and is wrong would be
caught; a regression in the four parse/apply behaviours has no control that has been demonstrated to
fail. Minor, and worth one line in the gate's own comment.

### 2.5 `make queue-vacuity` covers 77 of 95 controls and the summary does not say so

**[R]** Measured across flag combinations:

| Invocation | NON-VACUOUS | EXEMPT | SKIP |
| --- | --- | --- | --- |
| `make queue-vacuity` (the default) | 73 | 4 | **18** |
| `--integration` | 73 | 4 | 18 |
| `--network` | 75 | 4 | 16 |
| `--integration --network` | 75 | 4 | 16 |
| **`--slow --integration --network`** | **91** | 4 | **0** |

E3's headline — "91 NON-VACUOUS, 4 EXEMPT, 0 VACUOUS, 0 UNCONTROLLED" — **is exactly reproducible**,
but only with all three flags, which E3's summary does not state and which `make queue-vacuity`
does not pass. The default run leaves 16 `slow` and 2 `network` controls unrun and prints
`summary: EXEMPT=4 NON-VACUOUS=73 SKIP=18`. The footer does say "SKIP measured nothing and is never
read as green", which is good discipline; the Makefile help mentions `SLOW=1` but not `INTEGRATION=1`
or `NETWORK=1`.

**The consequence is specific.** The Rule 0 publication control of §2.2 is one of the two `network`
controls, so **it is skipped by the default run**. The one gate whose failure mode is "we shipped
without noticing" is the one whose negative control a maintainer running `make queue-vacuity` does
not execute. Its declared control in `gate-controls.yaml` is well designed — it substitutes `v0.0.13`,
which is on the remote — and my ablation 2d proves that control works. It just never runs.

---

## 3. Check C — does the queue cover the register?

### 3.1 Set difference, re-derived independently

**[R]** I wrote my own register parser and manifest reader rather than reusing theirs. Result:

- 69 register rows parsed (their gate also says 69).
- 68 distinct ids referenced by manifest `register:` fields.
- **One id absent: `BF-12`** — and it is correctly absent. **[R]** Its row reads
  `~~entries.rawbg is coerced but is not in the model~~ — does not reproduce … closed 2026-09-15, invalid`.
- **Zero invented ids** — nothing in the manifest names a register entry that does not exist.
- **[R]** Zero silently missing gate scripts: every `tools/queue/gates/*` and `tools/qc/*` path named
  by a gate exists on disk.

The coverage gap the previous critic found is closed, and I verified the closure rather than
accepting it.

### 3.2 But "covered" means tracked, not measured — and two gaps nobody has named

**[R]** **29 of the 74 items have zero runnable gates.** Every gate is an explicit `no-gate` marker.
Six of those 29 declare `ships_to_operators_today`: `BFQ-04`, `BFQ-CAP01`, `BFQ-40`, `BFQ-MINIMED`,
`BFQ-47`, `BFQ-52`.

I read all six markers and **they are excellent** — each states specifically why nothing can be
measured (`BFQ-40`: needs MongoDB and a JavaScript oracle gets it wrong; `BFQ-MINIMED`: what decides
active-versus-latent is a vendor payload question; `BFQ-47`: derived from source, a gate needs a
planted subject row). Several explicitly say "read, not reproduced". This is honest work and
`queue-status` reports them as UNMEASURED, never as green.

So this is **not a defect — it is a qualification on how the closure should be described.** The gap
that closed is *tracking* coverage. *Measurement* coverage is 45/74, and six defects that reach
operators today have no executable check at all. Any summary saying "the queue now covers the
register" should carry that second sentence, because a reader will otherwise hear the first.

**A second gap: `releases/nightscout-connect-v0.0.14/` has no verification record.** **[R]** The CRM
release directory has `verification-record.json` and `.md`; the connector directory has
`release-notes.md`, `contents.md` and `tag-message.txt` and nothing else. Neither
`releases/README.md` nor `releases/VERIFICATION-RECORDS.md` explains the asymmetry. P0-TAG and P0-F
are the connector's release items and both carry real gates, so the record is capturable — it simply
was not captured. If the `v0.0.14` tag is cut, there is no record of what was checked when.

---

## 4. Check D — the retirement evidence

### 4.1 Rule 3 labelling: E1 is exemplary, E2 is uneven

**[R]** E1 labels **every** claim: 63 `[R]` and 22 `[S]` markers against a stated legend
("**[R]** reproduced (a harness was run and produced the number quoted)", "**[S]** read-derived").
This is the best rule-3 discipline in the programme.

**[R]** E2 uses **zero** `[R]`/`[S]` markers. Its prose sections do carry explicit bold
`**Read-derived.**` / `**Reproduced.**` sentences and they are well placed — §1a ends
"That is documented evidence that the vendor moved … it is **not** evidence that v5 has since been
withdrawn. **Read-derived.**", which is exactly right. But of 67 table rows, **62 carry no basis
marker**. One table has a `basis` column; the side-by-side legacy-vs-Connect comparison table —
auth, region, account roles, endpoints, cadence, session renewal, error recovery — has neither a
column nor per-row labels.

That table is precisely what someone drafting a deprecation notice would lift rows from, and a
reader cannot tell which rows were executed. E2's own conclusions are careful about this distinction
in prose; the table silently discards it. Not a wrong claim — a labelling gap in the highest-traffic
part of the document.

### 4.2 The unsettleable list is honest — neither padded nor emptied

**[R]** I mapped every "unsettleable without a real account" item in E1 and E2 onto the migration
plan's §2.3 table. **All sixteen land.** Nothing was dropped to make the maintainer's case easier:

- E1's eight → U4, U5 (absorbs two E1 items), U6, U7, U11, U14, U15.
- E2's eight → U1, U2, U3, U8, U9, U12, U13, U16.
- U10 (does CareLink return history or only a snapshot?) is the plan's own addition.

And it is not padded to look cautious. U16 argues against its own
inclusion: "Not a regression: identical on both sides, so the retirement neither creates nor fixes
it … A reviewer should decide whether it belongs in this plan at all." That is the opposite of
padding.

The plan also declines to launder the maintainer's claim. §2.3 U4 says that if Dexcom throttling is
the real mechanism, "the case for retirement is stronger than anything that was measured" — it
argues the maintainer's side of a question it cannot settle, which is the right way to be uncertain.

### 4.3 The residues reach the notice and the checklist

**[R]** §6 is the checklist form of §2.3, V1–V10, each with a named owner, a concrete pass criterion
and a blocking flag. V1 (CareLink zone designators) is marked "**YES — nothing else in §8 can be
interpreted until this is known**". V2 requires the new test be "red at the parent commit and green
after (a test that has never failed is not evidence)" — rule 2 propagated into the release gate. V8
requires the soak be run by "**a named maintainer who is not the branch author**". V5 (the
`BRIDGE_SERVER` census) is correctly identified as the cheapest item with the largest effect.

And §6 states plainly that **U15 and U16 are deliberately left without a V-row so the gap is visible
rather than implied**. Leaving a hole and labelling it is better than filling it with a row nobody
will run.

Operator-facing sections (§3, §4) are placed before the technical ones, open with "This is not
medical advice", tell the reader to fall back to their CGM's own app and fingersticks, and direct
them to their care team. Rule 10 is satisfied.

**Verdict on check D: the evidence chain from E1/E2 into the plan is the strongest part of this
workflow.** Its weakness is not in the reasoning. It is in §4.4.

### 4.4 Every reproduction behind the retirement lives in `/tmp` — **this is the thing I would not ship on**

**[R]** E1's legend says: "Harnesses: `/tmp/claude-1000/…/c0ce5365-…/scratchpad/r1..r9`". E2's says:
"Harnesses: `/tmp/claude-1000/…/c0ce5365-…/scratchpad/e2/` (`compare.js`, `chain.js`, `loop.js`,
`item5.js`, `us-branch.js`, `sentinel.js`)".

**[R]** They exist — 11 `r*.js` files and 8 files under `e2/` — and they still run. I re-ran two:

```
$ node e2/sentinel.js
lastSGVEntry.mgdl=55     alarms fired: ["Warning LOW"]
lastSGVEntry.mgdl=40     alarms fired: ["Urgent LOW"]
lastSGVEntry.mgdl=39     alarms fired: []
lastSGVEntry.mgdl=0      alarms fired: []

$ node r2-region.js
BRIDGE_SERVER   LEGACY host           CONNECT host after compat
US              share2.dexcom.com     US    [region=- server=US]    *** NO ***
us              share2.dexcom.com     us    [region=- server=us]    *** NO ***
EU1             share2.dexcom.com     EU1   [region=- server=EU1]   *** NO ***
eu              share2.dexcom.com     shareous1.dexcom.com          *** NO ***
```

Both headline findings independently confirmed on re-run: the gap-sentinel zero suppresses the
entire high/low alarm evaluation, and `BRIDGE_SERVER=US` becomes an unresolvable hostname.

**[R]** And **not one of the nineteen is in the repository.** `git ls-files` returns nothing for any
of them; `find` over the whole tree returns zero copies of `r5-connect-session.js`, `r7b.js`,
`compare.js`, `chain.js`, `sentinel.js` or `us-branch.js`.

Why this is the most serious finding in the review. The
entire value of the `[R]` label is that a reproduction can be re-run by the next person. These 19
scripts are the evidentiary basis for **deleting the legacy CGM ingestion path** — a change whose
failure mode is a person's glucose data quietly stopping. [2026-09-22: the maintainer reports (2026-09-21, operational knowledge, not measured here) that mmconnect has not worked for some time; legacy Dexcom `BRIDGE_*` settings are served by nightscout-connect by default since 15.0.8; BF-44 and BF-45 are graded low in the register; the durability point stands.] They are in a session-scoped temp
directory, on one machine, outside version control, with no retention guarantee. The moment that
directory is cleared, 63 `[R]` claims in E1 and every reproduction in E2 become indistinguishable
from assertions, and a future reviewer asked to check them has only the report's word.

This is inconsistent with how the same workflow treated the *queue*: those gate scripts were
correctly promoted into `tools/queue/gates/` and are runnable by anyone. The retirement evidence —
higher stakes by a wide margin — was not.

The fix is small and available right now, while the files still exist: copy them into
`tools/evidence/e1-dexcom/` and `tools/evidence/e2-minimed/`, point E1's and E2's legends at the
repository paths, and give the two or three load-bearing ones a `make` target. I did not do it
because my brief says not to edit another agent's output, and moving their harnesses into the tree
would change what their documents refer to.

---

## 5. Check E — the verification record

**[R]** The record is real and substantial: 3,742 lines of JSON, 1,125 of Markdown, from a 1,409-line
generator that reuses `status.py`'s executor rather than reimplementing it. Totals: 17 items
(9 PASS, 5 FAIL, 3 UNMEASURED), 64 gate outcomes (35 PASS, 7 FAIL, 19 NO-GATE, 13 SKIP), and
**76 `not_verified` entries across 12 categories**. The generator refuses to write a record whose
gaps section is empty and exits 2, with no flag to override.

### 5.1 T0.3 — yes, both halves are there, prominently

**[R]** `verification-record.md:158`:

> **NO-GATE** — T0.3's stated gate is "the three cache calls under 1 ms per cycle", and it was
> MEASURED at 3.747 → 2.657 ms, so the gate is not met. But that measurement is not currently
> RE-RUNNABLE: the workload that produced those two figures is not recorded anywhere in this
> repository, and a benchmark written from scratch here would emit a number that looks like the
> gate's number without being comparable to it. … So `gate-not-met` here rests on a RECORDED
> measurement by a prior agent, not on a live one.

Both facts my brief asked about — the missed gate and the unrecorded workload — are stated, in the
item section and again in the gaps section, with the house pattern to follow named
(`tools/mt-bench/cycle-fix.js`). **[R]** `make queue-status` independently flags the same item:
`P0-B … CLAIM UNBACKED: state says gate-not-met, but every RUNNABLE gate passed and the failing
property sits behind 2 no-gate marker(s).`

### 5.2 Proof by breaking it — and I did not use their break

**[R]** Their `--self-test` passes (it injects `exit 7` and checks six properties). Rule 2 says a
check that has never failed is not evidence, so I broke it my own way: a **behavioural** break, not
an exit-code substitution. In a manifest copy I repointed P0-E's content gate at `origin/dev`
(`… bf-reads-read-contract.js --rev origin/dev`), which makes the gate genuinely measure a tree
without the fixes, and captured a fresh record.

Result **[R]**:

```
generator exit=0
  items=1  verdicts=FAIL=1
  gates=FAIL=1, NO-GATE=3, PASS=2, SKIP=5
  NOT VERIFIED=23 entries across 10 categories
```

and in the Markdown half:

```
| `P0-E` | … | `ready-to-push` | **FAIL** | 2/3 (5 skip, 3 no-gate) |
> **CLAIM DIVERGES FROM MEASUREMENT.** state says ready-to-push; the gates measured FAIL
- **FAIL** `[static]` `node tools/queue/gates/bf-reads-read-contract.js --rev origin/dev`
```

The record reported the failure in both halves, carried the failing command's own output, flipped
the item verdict, flagged the divergence between the claimed state and the measurement, and grew the
gaps section. **Check E passes, verified independently.**

Note: test summaries are not byte-identical across captures, because `output_summary.last_line`
quotes a benchmark duration.

---

## 6. Check F, G — Rule 0 and sensitive data

### 6.1 Rule 0 — verified directly, not from reports

**[R]** `git ls-remote origin` in **both** repositories:

- **cgm-remote-monitor**: no `bf/*` ref on the remote. One hit matches `fix/connect` — 
  `refs/heads/fix/connect-stop-pin` — and it is **not ours**: `git log -1` gives
  `Andy Low, Tue Sep 8 11:19:47 2026`, a pre-existing upstream branch, and the local reflog shows it
  arrived by `fetch`. Remote tags stop at `15.0.8`/`v15.0.8`; **no `15.0.9` tag exists remotely**.
- **nightscout-connect**: no `fix/connect-timer-jitter` on the remote; remote tags stop at `v0.0.13`.
  **No `v0.0.14` tag on the remote.**

**[R]** Backups intact and verified by content, not by name: `range-diff origin/dev
bf/reads.bak-changelog bf/reads` marks all six read-path commits `=` with the coercion commit and the
changelog-only commit dropping out; `bf/coercion` vs its backup shows exactly one `!` whose only hunk
is `## CHANGELOG.md ##`. **[R]** After my own work: 18 worktrees (unchanged), every branch SHA
unchanged, both shipping checkouts with zero tracked modifications, no commit made, nothing pushed.

### 6.2 Sensitive data

**[R]** Swept `reports/`, `releases/`, `queue/`, `tools/queue/`, `docs/40-migration/`,
`docs/60-research/` and the sequencing document for email addresses, `mongodb://` URLs, bearer
tokens, GitHub PATs, AWS keys and API secrets.

- **The maintainer's address and `nightscoutfoundation.org`: zero hits** in any artefact. The one
  match in the tree is another agent's critique reporting the same absence.
- Zero connection strings, zero tokens, zero keys, zero credentials.
- One email-shaped match: `git@github.com/bewest/…` at `phase0-pr-sequencing-2026-09-15.md:77`, a
  git remote URL, not personal data. (Malformed — see §1.2.)
- **[R]** No CGM readings, patient identifiers or device logs in any artefact. E2's harnesses use
  the retired package's own recorded fixtures and a stub adapter that rejects before any socket
  opens; no vendor endpoint was contacted by anything I ran.

### 6.3 Rule 8 — commit trailers

10 trailer lines matching `Co-authored-by` exist on `fix/connect-timer-jitter`; they are not a
Rule 8 violation. **[R]** All ten are `Co-authored-by: Copilot <…>` on
pre-existing upstream commits authored by a third-party maintainer between Sep 8 and the branch
point; `main..fix/connect-timer-jitter` spans 38 commits because `main` is far behind. The **one**
commit this programme authored, `c1cce2a`, has **zero** trailer lines and is committed under git's
configured identity (the committer name and address configured in git — which is a different address from the one in session context). **[R]** All
nine cgm-remote-monitor branches: zero trailer lines. No written artefact contains
`Co-Authored-By` or `Generated with`.

---

## 7. Mis-scoped ablations

Rule 2 distinguishes a vacuous check from a break that did not break anything. Two were the latter.

1. **Coverage-gate control A, first attempt.** I tried to remove a `register:` reference with a
   string replace on `- 'BF-41'`. The manifest writes it as an inline flow list, `register: [BF-41]`,
   so my replacement matched nothing — the script printed `changed: False` and the gate correctly
   stayed green. **The ablation was mis-scoped, not the gate vacuous.** Redone by loading the YAML,
   stripping `BF-41` from every item's list and re-serialising: the gate then went red naming
   `BF-41 (§1, register L153, open)`.

2. **"`--integration` is a no-op".** `--integration` did not change the vacuity totals; this is not
   a defect in the instrument: the 18 skipped controls are 16 `slow` and 2 `network`,
   **[R]** and `--slow --integration --network` reaches 91 NON-VACUOUS / 4 EXEMPT / 0 SKIP, exactly
   reproducing E3's figure. The real finding is narrower and survives —
   the *default* target covers 77 of 95 and its summary line does not say so (§2.5).

---

## 8. Check H — where this is weakest

Ranked by what I would actually refuse to ship on.

**1. The retirement evidence is not durable.** §4.4. Nineteen harnesses in `/tmp`, backing the
deletion of the legacy CGM ingestion path. The reasoning built on them is the best work here; its
foundation is the least durable thing in the programme. **I would not cut a deprecation release
while the evidence for it cannot be re-run by anyone but this session.** Fixable today, in minutes,
while the files still exist.

**2. The Rule 0 publication gate fails open, and its control is skipped by default.** §2.2, §2.5.
Two independent weaknesses compounding on the one gate that answers "have we already shipped?".
Neither is hard to fix — `set -o pipefail` plus a `--network` default for that one control — and
until both are fixed, "nothing has been published" is a claim the system cannot actually make when
it matters most, which is when something is wrong with the network or the remote.

**3. P0-C's repaired gate passes against a missing file.** §2.1. Same failure class as the bug that
was fixed, on the security branch, and the modernization parcels move files for a living.

**4. Nothing asserts a worktree is at its branch tip.** §2.3. Thirteen gates measure working
directories across a checkout that several sessions share concurrently. It happens to be true right
now. Nothing makes it stay true.

**5. "The queue covers the register" needs its second sentence.** §3.2. 74/74 tracked, 45/74
measured, six operator-facing defects with no executable check. The `no-gate` markers are honest and
specific — this is a framing risk in how the closure gets summarised, not dishonesty in the queue.

**6. E2's comparison tables carry no basis labels.** §4.1. Sixty-two rows in the document a
deprecation notice would be drafted from, where E1 labels every claim. E2's prose is careful; its
tables are where the carefulness stops.

**7. The connector release has no verification record** and nothing says why. §3.2.

### What I would stake a release on

The migration plan (§4.2, §4.3). The unsettleable list is complete against both evidence documents,
argues the maintainer's side of the question it cannot settle, and lands every residue in
a checklist with an owner, a pass criterion and a blocking flag. It says plainly what it does not
know. The operator-facing sections put "your data has stopped" before the technical content and keep
every safety caveat.

And the verification record (§5). It reports its own gaps, refuses to be written without them, names
the one measurement in the release that cannot be reproduced, and survived a behavioural break I
designed specifically to avoid its own self-test's shape.

### What would change my mind about #1

If the 19 harnesses are moved into the repository and E1/E2 repointed at the new paths, finding #1
disappears entirely and the retirement evidence becomes the strongest artefact in the programme
rather than the most fragile. Nothing else about it needs to change.

---

*Draft, 2026-09-16. Adversarial review; prepared locally. Nothing merged, pushed, tagged or
published. No branch SHA changed; the one worktree used was created and removed by this review. No
other agent's output was edited. Requires maintainer review before any of it is acted on.*
