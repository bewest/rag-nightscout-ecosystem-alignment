# Completeness critique — what this workflow is missing

**Role.** Everybody else in this workflow was asked to produce something. I was asked what is
absent. Written 2026-09-15, main repo HEAD `08753474`, against the artefacts as they stood at
20:00–21:00. Every claim below was measured in this session unless it says otherwise; where I
repeat another agent, I say so and I re-ran the measurement.

**One-line verdict.** The eight deliverables all exist and none is a stub — this is a large,
unusually honest body of work. The queue is real: it executes gates, it distinguishes UNMEASURED
from PASS, and it caught every one of the eleven defects I injected into it. But it is **stale by
construction against the register it is supposed to drive** (29 of 41 open register entries have no
queue item, 14 of them shipping to operators today, 4 of those high), and it contains **at least one
gate that reports PASS on a property that is false**, on an item marked `ready-to-push`. Details in
§B and §C.

---

## A. Deliverable coverage

All eight asks are met in substance. Sizes and structure verified by reading, not by `ls`.

| # | Ask | Artefact | Verdict |
|---|-----|----------|---------|
| 1 | Executable work queue, generated view | `queue/work-queue.yaml` (2506 L), `queue/QUEUE.md` (2000 L, generated), `queue/README.md`, `tools/queue/{manifest,validate,emit,status}.py`, 13 gate scripts | **Met mechanically, thin in coverage.** See §B, §C |
| 2 | Phase 0 prepared, nothing pushed | 9 `bf/*` branches + connect `release/v0.0.14` + tag; `reports/phase0-pr-bodies/` | **Met for the branches. PR bodies cover 7 of 10** — see below |
| 3 | Post-Phase-0 roadmap | `docs/30-design/post-phase0-roadmap-2026-09-15.md` (901 L) | **Met, and it argues against the brief's ordering** rather than restating it |
| 4 | Maintainer release brief | `docs/30-design/maintainer-release-brief-2026-09-15.md` (1230 L) | **Met, strongest artefact in the set** |
| 5 | Tenant-owner config surface (T3.0 schema) | `docs/30-design/tenant-owner-config-surface-2026-09-15.md` (1866 L) | **Met** — data model, env mapping, credential model, bootstrap, authz boundary |
| 6 | Four migration plans | `docs/40-migration/` ×4 (1470 / 1045 / 1534 / 1181 L) | **Met** |
| 7 | Semver classification + policy | `docs/30-design/semver-and-release-versioning-policy-2026-09-15.md` (1618 L) + `tools/qc/semver-surface-gate.js` | **Met, with a runnable gate** |
| 8 | Plan and register updated in place | both modified; register grew 39 → 67 entries (+1208 lines uncommitted) | **Met, and it is the update that broke the queue's currency** |

### Where it is thin

**A1. Three Phase 0 branches have no PR body, including the one the brief says to merge first.**
`reports/phase0-pr-bodies/` holds seven files: `bf-alarms`, `bf-auth`, `bf-cache`, `bf-coercion`,
`bf-connect-pin`, `bf-reads`, `fix-connect-timer-jitter`. Absent: **`bf-food`, `bf-merge`,
`bf-parms`**. The release brief itself (L139) lists eight branches to push and (L1041) says
*"`bf/food` — highest severity, one commit, smallest thing to read"* — the branch it nominates to
read first is the branch with no PR body. The brief's §G/§H/§I cover all three in depth, so the
content exists; the copy-and-paste artefact does not.

**A2. The workflow left no verification trail.** I grepped every new document, the manifest and the
generated view for `needs-revision`, `unsound`, and `verifier verdict`. **Zero hits.** Whatever
verifier passes ran, their verdicts and whether fixes landed are not recoverable from the artefacts.
Ask F cannot be answered from disk, and the next session cannot audit it either. For a programme
whose governance finding is *"confidence rests entirely on automated gates and the author's own
evidence documents"*, reproducing that shape inside the workflow is the wrong lesson learned.

**A3. Two of the best gates the workflow built are wired to nothing.**
`tools/qc/connector-pin-agreement-gate.js` and `tools/qc/semver-surface-gate.js` both run (I
reproduced the documented `semver-surface-gate` invocation against `a8888f0d → bf/reads` exactly —
same 22 files, same S1/S4 surfaces, exit 1). `connector-pin-agreement-gate.js` rule R5 is the
provenance of register entry **BF-43**. Neither appears in the `Makefile` nor in
`queue/work-queue.yaml`. The semver policy §6 proposes a Makefile target and marks it *"not added by
this document"*. So the two instruments that took the most work are outside the executable queue
that was built in the same workflow to hold instruments.

---

## B. Is the queue real?

**Yes, and unusually so.** I ran it rather than reading about it.

```
$ make queue-validate
queue-validate  queue/work-queue.yaml
  57 items, 5 parcels, 73 runnable gates, 68 explicit no-gate markers
OK    schema, ids, blocks_on and the gate rule all hold

$ make queue-check
OK     queue/QUEUE.md is current

$ make queue-status
summary: PASS=16  FAIL=18  UNMEASURED=23        (exit 1)
```

`status.py` genuinely `subprocess.run`s each gate. I watched real mocha suites execute
(`TEST=boluscalc.quickpick npm run test-single`), real `git merge-tree --write-tree` calls, a real
`npm ci --dry-run`, and a real `ls-remote`. It is not a reporter.

Three design decisions are right and worth preserving:

1. **`UNMEASURED` is never rendered as green.** An item with zero gates that actually ran reports
   `0/0 UNMEASURED`, and the legend says *"Never read as green."*
2. **`MISSING` (instrument not built) is distinguished from `FAIL` (property is false).** The
   comment explains why: collapsing them would later let someone "fix" a defect by writing a script
   that exits 0.
3. **The runner contradicts the manifest out loud.** `P0-B` claims `gate-not-met` while every
   runnable gate passes, and the runner prints `CLAIM UNBACKED: … The claim rests on a recorded
   measurement this runner cannot reproduce.` That is the queue catching its own author.

### Break-it battery — validator (rule 2)

I copied the manifest to a scratchpad and injected eleven defects. **Control passes; all eleven are
caught, each with a specific message.**

| Injection | Result |
|---|---|
| unmodified control | `OK` exit 0 |
| duplicate id | `FAIL duplicate id 'P0-A' appears 2 times` |
| dangling `blocks_on` | `FAIL … references 'NO-SUCH-ITEM', which is not an id in this manifest` |
| two-item `blocks_on` cycle | `FAIL blocks_on cycle: P0-A -> P0-B -> P0-A` |
| empty `gates: []` | `FAIL … Every item needs either a runnable gate or an explicit no-gate marker` |
| gate with neither `run` nor `no-gate` | `FAIL … (keys: desc, kind)` |
| `no-gate` with blank reason | `FAIL … the reason IS the gate` |
| `run: "   "` (blank command) | `FAIL … a blank command always succeeds` |
| gate naming a nonexistent script | `ADVISORY … does not exist` (+ a `describe` FAIL) |
| missing required field | `FAIL P0-D: missing required field 'semver'` |
| invalid `semver` enum / undeclared parcel | both `FAIL` |

The two the task named specifically — duplicate id, dangling `blocks_on` — are caught. So is the
cycle case nobody asked about.

### Break-it battery — a gate script

Validator soundness is not gate soundness. I rebuilt a fake repo root in the scratchpad (the gates
derive `REPO_ROOT` from `__dirname`, so this works without touching the real tree) and mutated the
input to `register-rows-vs-details.js`:

| Input | Exit | Output |
|---|---|---|
| unmodified register | **0** | `parsed 69 table rows and 69 detail sections` |
| inject `### BF-97` with no table row | **1** | `BAD BF-97: detail section at L2807, NO table row` |
| rename `### BF-19` so its row is orphaned | **1** | `BAD BF-19: table row at L191, NO detail section` |
| empty file | **1** | `BAD … the register has changed shape and this gate can no longer read it` |

The fourth case is the one that matters: the gate refuses to pass vacuously when its input stops
parsing. `_gate.js` enforces the same rule globally — a gate with zero findings prints
`VACUOUS: this gate examined nothing. Treating as failure.` and exits 1.

I also confirmed the rule-0 network gate is non-vacuous: `ls-remote --tags origin v0.0.14` exits 0
(tag absent, correct), and the identical command against `v0.0.13` — which *is* on origin — exits 1.
It detects a pushed tag.

### But: the queue contains a gate that reports PASS on a property that is false

This is the finding I would not want buried. **`P0-C` (`bf/auth`, state `ready-to-push`) carries a
gate whose pattern cannot match the code it inspects.**

```yaml
- run: grep -n "console.log('Loading', opts)" lib/authorization/storage.js && exit 1 || exit 0
  cwd: externals/work/crm-bf-auth
```

The gate's semantics: PASS means the unguarded log line is **absent**. The code at
`externals/work/crm-bf-auth/lib/authorization/storage.js:113` is:

```
      console.log('Loading',opts);$          # cat -A; no space after the comma
```

The pattern has a space after the comma. It never matches, `&& exit 1` never fires, `|| exit 0`
makes the gate PASS. Measured:

```
pattern as written (space)      -> exit 0   PASS   (false)
pattern as the code spells it   -> exit 1   FAIL   (true)
whitespace-tolerant -E pattern  -> exit 1   FAIL   (true)
```

The line is a known residual — GT3 measured it still present at `:113`, and
`phase0-pr-sequencing` §5 follow-up 4 records it as *"confirmed still present on `bf/auth`"*. The
queue asserts the opposite and counts it toward `3/3 PASS`. **A one-character whitespace difference
turned a tracking gate into a false green, on the branch that carries the credential-handling
change.** This is the programme's stated failure mode reproduced inside the artefact built to
prevent it. Fix: `grep -nE "console\.log\('Loading',\s*opts\)"`.

Only two absence-style gates exist in the manifest (`P0-C` above and `P0-TAG`'s rule-0 check). The
other is sound. But the class is the dangerous one, because a wrong pattern is indistinguishable
from a clean tree, and nothing in the runner can tell them apart.

### And a second gate that measures nothing

`P0-E` (`bf/reads`, `ready-to-push`, `3/3 PASS`) has this as its only content gate:

```yaml
- run: git -C externals/cgm-remote-monitor-official log --format=%H bf/reads | grep -q .
```

It asserts the branch has at least one commit. I ran the same command against other refs:
`bf/reads` PASS, **`origin/dev` PASS**, `origin/master` PASS, `bf/alarms` PASS. It passes for a tree
containing none of `bf/reads`' fixes. It is a gate in name only.

That would matter less if something else covered the branch, but `bf/reads`' only behavioural gate
is `npm run test:unit` declared `kind: integration`, which is **off by default** — so the item reads
`3/3 PASS ready-to-push` while nothing behavioural has run. This is avoidable: `bf/reads` ships six
test files, and at least one needs no database. I ran it:

```
$ TEST=api.count-parameter npm run test-single      # in crm-bf-reads
  13 passing (2s)     ✔ refuses count=0 on treatments  ✔ never asks the driver for limit(0) …
```

Two seconds, no MongoDB. The `test-single` mechanism is already used by `P0-D`, `P0-G`, `P0-H`,
`P0-I`. It was simply not applied to the branch with the widest blast radius — the one whose
`?count=` validator is `app.use`'d across the whole v1 app and turns six previously-accepted inputs
into HTTP 400 on writes as well as reads (GT4). `bf/alarms` has the same shape: its `test:unit` is
also `kind: integration`.

---

## C. Does the queue cover everything? No — and the gap is the biggest finding here

### C1. The queue is stale against the register by 29 entries, and it is stale *by construction*

File mtimes, measured:

```
queue/work-queue.yaml                  19:07
queue/QUEUE.md                         19:11   (generated)
docs/30-design/nightscout-backfix-register.md    19:57
docs/30-design/nightscout-multitenancy-execution-plan-...md   19:58
```

The register kept growing for **fifty minutes after the queue was frozen**. The manifest's own
`meta.measured_against.main_repo_head` is `75c38a17`; HEAD is now `08753474`.

The register held 39 BF entries + CAP-01 when GT3 audited it. It now holds **67 BF entries + CAP-01
+ CAP-02**, with +1208 uncommitted lines. Its own header table (L106) says:

> **40 open `BF-` entries** — 16 in §1 (BF-09, BF-10, BF-40…BF-52, BF-67) and 24 in §1b
> (BF-18…BF-27, BF-53…BF-66) — **plus CAP-01 and CAP-02**, plus BF-04 at `fixed-in-seam`

The queue's `register-open` parcel has 14 items, covering BF-09, BF-10, BF-04, CAP-01 and the ten
§1b entries BF-18…BF-27. **Programmatic set difference — 29 not-fixed register ids appear nowhere in
the manifest, not even in prose:**

`BF-40 BF-41 BF-42 BF-43 BF-44 BF-45 BF-46 BF-47 BF-48 BF-49 BF-50 BF-51 BF-52 BF-53 BF-54 BF-55
BF-56 BF-57 BF-58 BF-59 BF-60 BF-61 BF-62 BF-63 BF-64 BF-65 BF-66 BF-67 CAP-02`

**Fourteen of them are §1 — they ship to an operator on today's release — and four are high:**

| id | sev | what |
|---|---|---|
| **BF-41** | **high** | A reading timestamped ahead of the server clock silently disables *both* stale-data alarm paths. The one continuous detector a self-hoster has for "my CGM data stopped" is switched off by the condition most likely to have broken the feed |
| **BF-42** | **high** | `nightscout-connect` v0.0.13 — *the version `origin/master` pins, i.e. what every current operator runs* — writes vendor credentials, session tokens and patient glucose data to the runtime log unconditionally, with no setting that turns it off |
| **BF-44** | **high** | MiniMed CareLink and the retired `minimed-connect-to-nightscout` derive absolute time by different algorithms; a forward shift files readings in the future and **takes BF-41's stale alarm with it** |
| **BF-46** | **high** | Eleven API v3 environment variables bypass `lib/server/env.js`; "an undocumented variable that deletes a…" |
| BF-40, BF-43, BF-45, BF-47, BF-48, BF-51, BF-67 | medium | inverted `$exists=false`; silent axios constraint violation; legacy MiniMed double-start; admin UI destroys stored subject fields; webhook config bypass; azuredeploy runtime; **alarm threshold silently rewritten ±1 — `BG_HIGH=14` stored as 181 mg/dL** |
| BF-49, BF-50 | low | HSTS spelling; README variable |
| BF-52 | unsettled | age plugins grade on one threshold, request another |

BF-42 and BF-65 bear directly on the decision the queue exists to drive: BF-65 records that the
adopted train **ships the leaking connector to upgraders first** (cuts 1–3 all pin v0.0.13). Neither
has a queue item.

This is not the queue agent's error — the register moved under it. It is a **process** gap: nothing
in `queue/README.md` states the obligation to re-derive the manifest when the register changes, and
no gate detects the divergence. The queue can prove `QUEUE.md` is not stale relative to
`work-queue.yaml` (`make queue-check`) but has no way to notice that `work-queue.yaml` is stale
relative to the register. **The staleness check runs on the one edge where staleness does not
matter.**

*Recommended, and cheap:* a `register-queue-coverage.js` gate that parses open ids out of the
register and fails naming any that no item references. It is the same shape as
`register-rows-vs-details.js`, which already works.

### C2. What IS covered — verified item by item

- **Phase 0 branches (GT1's ten):** all covered. `P0-A`…`P0-I` + `P0-TAG`, `P0-PIN`, `P0-LOCK`,
  `P0-T01`, `P0-C-REMEDIATE`. No branch missing.
- **The five cuts:** `RT-1`…`RT-5`, plus `RT-0` (15.0.9), `RT-D3`, `RT-VERSION`, `RT-REBASE`.
  Complete, and `RT-REBASE` encodes GT2's correction that the "zero rebase work" premise is false.
- **§7a alarm items:** item 1 DONE, item 2 = T4.4 → covered by `T44`, items 3/4/7 → `A7A-3`,
  `A7A-4`, `A7A-7`, plus `A7A-GATE` carrying the "nothing marked done by inference" rule. Items 5/6
  correctly excluded as fixed/misfiled. **Complete.**
- **T3.0 and the DONE-EXCEPT remainders:** `T30-RESEARCH`, `T30-SCHEMA`, `T30-WIRING`, `T31-REM`,
  `T32-REM`, `T33-REM`. Complete.
- **Sequencing §5 follow-ups (ten, deliberately excluded from the PRs):** partially covered. #6
  (BF-04 extraction) → `BFQ-04`; §6 seam refresh → `SEAM-REFRESH`. **No item for #2 (the limit rule
  written twice — "two readings of one rule is the root cause of this whole family"), #3
  (`isPluginEnabled` always returns true), #4 (the `storage.js:113` console.log — which is the very
  line the broken `P0-C` gate pretends to watch), #7 (the alexa `switch` with no `default`, which
  the document says should land with `bf/alarms`), #9 (suppression audit outside `lib/`), #10 (jsdom
  test hygiene has no enforcement).** Six of ten follow-ups are recorded in a document and in no
  queue.

### C3. Items with a silently missing gate

None silently. The schema makes that impossible and I verified it by injection. But the honest shape
of the coverage is:

- **23 of 57 items are `UNMEASURED`** — zero gates that ran. Every `BFQ-*` seam entry, all three
  T3.x remainders, all four `A7A-*`, `BFQ-04`, `BFQ-CAP01`, `P0-C-REMEDIATE`, `T30-WIRING`,
  `DOC-PLAN`.
- **68 `no-gate` markers against 73 runnable gates.** Nearly half the declared gates are a recorded
  reason why no instrument exists.
- **Gate kinds: 58 static, 8 unit, 4 integration, 3 network.** Of the 58 static, most are
  `merge-base --is-ancestor` and `merge-tree --write-tree` — mergeability, not behaviour.

Read plainly: **the queue measures Phase 0 mergeability and document consistency. It asserts
everything else.** The manifest says so honestly, and the runner refuses to render assertions green.
That is the right failure mode. But a reader who sees "57 items, one queue across all programmes"
should know that tenancy, the seam and 29 register entries are inventory, not measurement.

### C4. Minor: the manifest records stale SHAs for some branches

`bf/reads` was rebased during this workflow (`824380a0` → `0d19bb31`; `bf/reads-prerebase` still
exists). The manifest caught that and carries an explicit correction to GT1 at L429. But five of
nine branch tips (`bf/alarms`, `bf/auth`, `bf/cache`, `bf/food`, `bf/merge`) are not recorded
anywhere in the manifest as SHAs, and **no gate asserts that any branch tip is what the queue thinks
it is.** If a branch is amended or rebased again, nothing notices. A one-line gate per item
(`test "$(git rev-parse bf/x)" = <sha>`) would close it.

---

## D. Nothing was pushed — verified directly

Rule 0 holds. I checked live remote state, not tracking refs, in both repositories.

**cgm-remote-monitor** (`externals/cgm-remote-monitor-official`; remotes `origin` and `official` both
= `nightscout/cgm-remote-monitor`, `bewest` = the fork):

- `git ls-remote --heads` against **all three remotes**: `0` refs matching `refs/heads/(bf|seam)/`.
- For each of the **26 local `bf/*` and `seam/*` tips**, `git for-each-ref refs/remotes --contains
  <sha>` returns **0** remote refs. Every one.
- `ls-remote --tags origin` ends at `v15.0.8` (`92d08342`). No new tag.
- The single expected exception from GT1 persists and is correct: `fix/quadratic-treatment-processing
  dfe2753d` is on origin as `bewest/wip/optimize-treatment-processing` — that is T0.1 / PR #8733.
  The `P0-T01` network gate asserts exactly this and passes.

**nightscout-connect** (`externals/nightscout-connect`, origin = `nightscout/nightscout-connect`):

- `ls-remote --heads origin`: no `release/v0.0.14`, no `fix/connect-timer-jitter`. `main` is still
  `b394411a`.
- `ls-remote --tags origin`: tags stop at **`v0.0.13` = `b394411a`**. **No `v0.0.14`.**
- Corroborated destructively: `P0-LOCK`'s `npm ci --dry-run` fails with
  `404 Not Found - GET https://codeload.github.com/nightscout/nightscout-connect/tar.gz/refs/tags/v0.0.14`.
  The tarball does not exist because the tag was never pushed. That 404 is the strongest available
  proof of rule-0 compliance, and it is also why leaving `package-lock.json` on the old SHA is
  correct.

**No npm publish.** The only npm operation in the whole queue is `--dry-run`, and it is `kind:
network`, off by default.

**PRs:** I did not query the GitHub API (that would be the vendor contact rule 0 forbids). Since
zero `bf/*` or `seam/*` refs exist on any remote, a PR from any of them is impossible.

*One note for the maintainer, not a violation:* `NETWORK=1` gates do contact vendor endpoints —
`ls-remote` to GitHub and `npm ci --dry-run` to codeload/registry. They are read-only and off by
default, and the manifest documents the constraint (*"a network gate may READ (ls-remote) and may
never push"*). I triggered them deliberately for this audit. Anyone running `make queue-status
NETWORK=1` should know it leaves the machine.

---

## E. No sensitive data leaked

I grepped every file this workflow wrote — 8 design/migration documents, 3 queue files, 7 PR bodies,
4 GT reports, 4 Python modules, 13 gate scripts, 2 QC gates — for email addresses, tokens, API keys,
connection strings, private keys and commit trailers.

| Check | Result |
|---|---|
| Email addresses | **One hit, and it is not PII:** `maintainer-release-brief:134` documents the SSH remote `git@github.com:nightscout/cgm-remote-monitor.git`. That is a git URL, not an address. |
| The maintainer's own address / `nightscoutfoundation.org` | **Zero hits.** It is in this session's context and reached no artifact. |
| `mongodb://user:pass@`, `postgres://user:pass@`, `ghp_`, `sk-`, `xox[baprs]-`, `BEGIN … PRIVATE KEY`, literal `api_key=` | **Zero hits.** |
| `Co-Authored-By` / `Generated with [Claude Code]` | **Zero hits** in any written file (rule 7). |
| Patient identifiers | The corpus work (`externals/ns-data`) is summarised as counts only — "277,690 treatments across 11 corpus sites", "67,521 of 153,315". No site names, no record ids, no timestamps traceable to a person. `bf09-corpus-divergence.js` reads the corpus but emits aggregates. |

The queue manifest's `operator_visible` fields are written in plain language with jargon defined and
a care-team pointer, e.g. `P0-A`: *"These do not change when any alarm fires, only whether it can.
This is not medical advice; if an alarm you rely on has been silent, talk it through with your care
team as well as checking your settings."* That is the right register for the audience.

**One item to watch:** `meta.repo_root` in `work-queue.yaml` hard-codes
`/home/bewest/src/rag-nightscout-ecosystem-alignment`, and several documents embed absolute paths
under `/home/bewest/`. Not sensitive, but it names a user account and would need scrubbing before
anything here is published outside the project.

---

## F. Unverified claims still standing

The documents are unusually good at labelling their own provenance — the register now demands
*reproduced* vs *derived from source* explicitly, and GT2/GT4 mark `[measured]` / `[inferred]` /
`[unverified]` per claim. What follows is what remains load-bearing and **not** measured.

**Inference, not measurement, and load-bearing:**

1. **Cut 5's Express 4→5 and Helmet 4→8 "major"** rests on dependency major bumps and a 36-file
   diff, not on a measured contract break (GT4, self-labelled `[unverified]`). Cut 2's "minor" is
   unmeasured against any third-party plugin corpus — **and no plugin corpus exists on this
   machine**, so it cannot be measured here at all.
2. **CI state at each cut tip was never re-verified.** The only evidence is release-readiness §3's
   record of 21 green checks on PR #8605 as of 2026-09-14, evaluated against the *integration
   branch* as base, not against `dev`. GT2 says so explicitly.
3. **"A PR of cut 1 into dev would be unmergeable and CI unable to run"** is inferred from the
   measured merge conflict plus GitHub's documented merge-ref behaviour. Not observed.
4. **BF-09 remains unsettled and the corpus cannot settle it.** GT3 found 0 divergences over 69,604
   at-risk documents and proved the harness non-vacuous by injection — but also noted the corpus is
   **survivorship-biased in exactly the direction that hides the defect**: a treatment swallowed as a
   false duplicate cannot appear in stored data. The one arm that settles it is a live uploader-burst
   replay, which has not been run. `BFQ-09` is correctly stated `unsettled`.
5. **BF-42's credential-leak census** is a source census of a `git archive` extraction — 112 live
   `console.*` sites, 101 passing a non-literal argument — **not run against a live vendor**. It is
   high severity and is the argument for the connector pin move; it rests on reading.
6. **BF-41 and BF-67** are both `derived from source` / `not reproduced against a running
   deployment`. BF-41 is high and is the stale-alarm defect.
7. **BF-65's ordering claim** is "quoted from the adopted train and was not re-derived."
8. **`bf/alarms`' ENABLE-warning behaviour** was measured against a **hand-reconstructed plugin
   registry**, not a booted one. GT4 flags the caveat; the manifest carries it as `P0-A`'s no-gate
   marker. A reconstructed registry is not the registry.
9. **`bf/auth`'s allow-list data loss (BF-47)** is `[inferred]` — read from `SUBJECT_FIELDS` /
   `ownedFields()`, not reproduced against a real deployment. It is now a register entry graded
   medium, *silent one-way data loss on an ordinary admin action*.
10. **T0.3's gate measurement is not re-runnable.** `P0-B`'s no-gate marker says the 3.747 → 2.657 ms
    figure cannot be reproduced by the runner because the workload is not captured. That is why the
    runner prints `CLAIM UNBACKED` — the state is honest, the evidence is not re-derivable.

**Verifier verdicts:** unanswerable. No `needs-revision` or `unsound` verdict is recorded in any
artifact (§A2). If verifier passes ran, their outputs did not survive into the repository, so
whether a flagged fix landed cannot be checked by me or by the next session.

**Corrections that landed and are worth trusting** (I re-measured each): the shipping checkout is
`externals/cgm-remote-monitor-official`, not `externals/cgm-remote-monitor` (which is a 2014 commit
on a different fork); Phase 0 is ten branches; `master` pins the v0.0.13 **tag**, not `^0.0.12`;
there are **four** connect pins in flight, not three.

---

## G. What the next session must do first

1. **Fix the `P0-C` gate pattern, then re-run `make queue-status PARCEL=phase0`.** First because it
   is a false green on a `ready-to-push` item, it takes one line, and until it is fixed every other
   PASS in the queue is worth slightly less — the reader has no way to know which other gate has a
   typo. Change to `grep -nE "console\.log\('Loading',\s*opts\)"` and expect `P0-C` to move to
   `gate-not-met`, which is the truth.
2. **Replace `P0-E`'s "branch has commits" gate with `TEST=api.count-parameter npm run test-single`,
   and demote `bf/reads`' and `bf/alarms`' `test:unit` from `integration` to `unit` where they run
   without a database.** Second because `bf/reads` has the widest blast radius in Phase 0 and is
   currently marked `ready-to-push` on the strength of a gate that passes for `origin/dev`. I proved
   the replacement runs in 2 seconds with no MongoDB.
3. **Re-derive the queue against the register at `08753474`+ and add the 29 missing items.** Third
   because the register moved 50 minutes after the queue was frozen, and four of the uncovered
   entries are high severity and ship to operators today — BF-41, BF-42, BF-44, BF-46. Add a
   `register-queue-coverage` gate in the same pass so this cannot recur silently.
4. **Write the three missing PR bodies (`bf-food`, `bf-merge`, `bf-parms`).** Fourth because it is
   the smallest gap with the largest immediate cost: `bf/food` is the branch the release brief tells
   the maintainer to read first, and it carries BF-35, the highest-severity defect in the batch. The
   content already exists in the brief's §G/§H/§I.
5. **Decide BF-42 before deciding the release order.** Fifth, and it is a decision rather than work:
   `origin/master` — what every operator runs — pins a connector that logs vendor credentials and
   patient glucose unconditionally, and BF-65 says the adopted train ships that same connector to
   the first three upgrade steps. All three pin the v0.0.13 *tag*, so moving them is the same
   one-line change as `dev`'s. This may reorder the train.
6. **Add the six uncovered sequencing §5 follow-ups to the queue**, especially #2 (the limit rule
   written twice — the document itself calls it *"the root cause of this whole family"*) and #7 (the
   alexa `switch` with no `default`, which the document says should land *with* `bf/alarms` and
   currently lands nowhere).
7. **Wire `semver-surface-gate.js` and `connector-pin-agreement-gate.js` into the queue or the
   Makefile.** Last of the must-dos because nothing is wrong today — but an instrument nobody runs
   decays, and these two are the most expensive instruments the workflow built.

---

## H. The honest assessment

**Where this body of work is strong, briefly, because it is the context for the rest.** The
corrections are the product. Four ground-truth agents overturned the shipping-checkout identity, the
branch count, the test-script premise, the "zero rebase work" premise, the `^0.0.12` pin, the D3 file
list and the number of connect pins in flight — and the downstream documents were written against
the corrections rather than the brief. The register's willingness to record *"the consequence this
entry claimed is refuted"* eight times over, in its own header, is the healthiest thing in the
repository. The queue's taxonomy (`UNMEASURED` never green, `MISSING` ≠ `FAIL`, `CLAIM UNBACKED`) is
a genuinely good piece of engineering.

**Now the weaknesses, in the order I would worry about them.**

**1. The queue's credibility is load-bearing and I found two holes in it in one session.** Not by
deep analysis — by running the gates and reading what they actually execute. A whitespace typo
(`'Loading', opts` vs `'Loading',opts`) produced a false PASS, and a tautology (`log | grep -q .`)
produced another. Both sit on items marked `ready-to-push`. The queue was built to stop assertions
wearing the costume of measurements, and two assertions got into it wearing exactly that costume.
**The lesson is not "fix two gates" — it is that no gate in this queue has itself been broken to
prove it catches anything.** The validator was demonstrated non-vacuously (I confirmed: eleven
injections, eleven catches). The *gate scripts* were not, as a class. `_gate.js`'s vacuity guard
catches the zero-findings case, but not the case where the finding is computed from a pattern that
cannot match. Rule 2 was applied to the schema and skipped for the instruments.

**2. The queue's honest coverage is Phase 0 plus document hygiene, and its framing oversells that.**
"One queue across all programmes, 57 items" is true and, read quickly, misleading: 23 items are
`UNMEASURED`, 68 of 141 gates are recorded reasons why no instrument exists, and 58 of the 73
runnable gates are mergeability checks rather than behaviour. Everything tenancy is inventory. The
manifest says this plainly if you read it; the top-line count does not.

**3. The staleness is structural and nobody owns it.** A queue generated at 19:07 from a register
that kept growing until 19:57 is not a source of truth, it is a snapshot with a confident header.
`make queue-check` proves the *generated view* is current — the one edge where staleness is
harmless — while the edge that matters (manifest vs register) has no check at all. In a programme
where agents read sections and whichever section they read becomes true for them, an authoritative-
looking queue that is missing four high-severity operator-facing defects is worse than a queue that
admits it is partial. **This is rule 6 operating one level up: the queue is now another statement of
a fact that the register also states, and they disagree.**

**4. What I would not stake a release on.** Three things, concretely:

- **Any `ready-to-push` verdict in the queue, as of right now.** `P0-C` and `P0-E` are demonstrably
  overstated. Until every gate has been broken once, the state column is a better-argued assertion,
  not a measurement. The underlying branches may well be fine — GT1 ran their suites and the release
  brief reviews each in depth — but *the queue is not the evidence for that*, and it is being
  offered as if it were.
- **The claim that Phase 0 is understood well enough to merge as a batch.** Three of nine branches
  have no PR body, the one the brief nominates to read first among them. `bf/reads` restricts six
  previously-accepted `?count=` spellings across every v1 route including writes, and its CHANGELOG
  documents only the read routes — a gap the manifest records as a no-gate marker and nothing
  resolves. `bf/auth` narrows stored subject documents to an allow-list and drops unknown fields
  silently; that became register entry BF-47 and it is `[inferred]`, not reproduced.
- **Cut 4, emphatically, and the adopted train's ordering.** GT4 executed the shims: a MiniMed
  operator without `CONNECT_COUNTRY_CODE` gets a boot error, and a boot error serves the error page
  for `*` — the whole deployment, not just ingestion. An operator running `BRIDGE_*` and `MMCONNECT_*`
  together, which works today, gets the same total outage. Cut 4's own evidence document says *"No
  real Dexcom account or live database has been used and no live migration is claimed."* The
  migration plan for it is thorough and its §6 test plan is exactly right — **and unexecuted.** For a
  change whose failure mode is "a person's glucose data stops arriving", a thorough unexecuted plan
  is a plan, not evidence.

**5. The workflow reproduced the governance failure it diagnosed.** The programme's central finding
is that 100 PRs were self-merged with zero human reviews and confidence rests on automated gates
plus the author's own evidence documents. This workflow produced ~13,000 lines of documents and a
queue, all written by agents, verified by agents, with **no verifier verdict surviving anywhere on
disk**, and the queue that is supposed to be the independent check has two false greens in it. The
shape is the same. That does not make the work wrong — most of it re-measured its own premises and
found them false, which is more than the stack under review did. But the maintainer should read this
body of work as *a very well-documented argument*, not as an independent verification, and the one
artefact that claims to be verification should be the first thing they distrust until §G items 1–3
are done.

**What a critic finding nothing would have looked like.** It would have run `make queue-validate`,
seen `OK`, run `make queue-status`, seen a runner that honestly reports 18 FAIL and 23 UNMEASURED,
concluded the queue is rigorous, and stopped. The queue *is* rigorous. Two of its gates are still
false, and the only way to learn that was to read every gate command and run it against something it
should reject.

---

## Appendix: reproduction

Every measurement in this document, in order. All read-only; nothing pushed; no worktree created,
modified or removed. Mutation testing used copies in the session scratchpad.

```bash
cd /home/bewest/src/rag-nightscout-ecosystem-alignment
git log -1 --format='%h %ad %s' --date=iso          # 08753474

# §A file census
wc -l -c <each of the 15 artefact paths>; ls -la reports/phase0-pr-bodies/

# §B queue execution
make queue-validate ; make queue-check ; make queue-status
make queue-status STATE=ready-to-push VERBOSE=1
make queue-status ID="P0-TAG P0-PIN P0-LOCK" NETWORK=1 VERBOSE=1

# §B validator mutation battery (11 injections + control), scratchpad copies only
python3 tools/queue/validate.py --manifest <scratchpad>/{control,dup-id,dangling,cycle,
    nogates,bogus-gate,empty-reason,ghost-script,missing-field,bad-semver,bad-parcel,blank-run}.yaml

# §B gate-script break test: gates copied to a fake REPO_ROOT, register mutated 3 ways
node <scratchpad>/fakerepo/tools/queue/gates/register-rows-vs-details.js

# §B the false-green proof
cd externals/work/crm-bf-auth
grep -n "console.log('Loading', opts)" lib/authorization/storage.js && exit 1 || exit 0   # exit 0
grep -n "console.log('Loading',opts)"  lib/authorization/storage.js && exit 1 || exit 0   # exit 1
sed -n '113p' lib/authorization/storage.js | cat -A

# §B the tautological gate
for ref in bf/reads origin/dev origin/master bf/alarms; do
  git -C externals/cgm-remote-monitor-official log --format=%H $ref | grep -q . ; done   # all pass
cd externals/work/crm-bf-reads && TEST=api.count-parameter npm run test-single           # 13 passing, 2s

# §C coverage set difference (register ids vs manifest text)
python3 - <<'PY' ... # parses '| **BF-nn** |' rows, greps ids out of queue/work-queue.yaml

# §D rule 0, live
git -C externals/cgm-remote-monitor-official ls-remote --heads {origin,official,bewest}
git -C externals/cgm-remote-monitor-official for-each-ref refs/remotes --contains <each of 26 tips>
git -C externals/nightscout-connect ls-remote --heads origin ; ls-remote --tags origin

# §E sensitive data
grep -rInE '<email|secret|token|connstring|trailer patterns>' <every written file>

# §A3 the unwired QC gates
node tools/qc/semver-surface-gate.js --repo externals/cgm-remote-monitor-official \
     --base a8888f0d --head bf/reads
node tools/qc/connector-pin-agreement-gate.js
```
