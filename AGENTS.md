# Working in this repository: the contract for any agent

*What this is: the operating contract for coding agents (contributor-facing). Read before anything
else; leads to [docs/00-overview/REVIEWER-ONBOARDING.md](docs/00-overview/REVIEWER-ONBOARDING.md).
Vendor-neutral: Copilot, Claude Code, Codex, Cursor and local models all read this file. The
vendor-specific files (`.github/copilot-instructions.md`, `CLAUDE.md`) point here and add only what
their tool needs. Living document, 2026-11-03.*

## 1. What this repository is

An alignment workspace for the Nightscout ecosystem. It tracks **configuration, documentation,
evidence and harnesses**; the shipping applications live in `externals/` (git-ignored, pinned by
`workspace.lock.json`, restored by `make bootstrap`). It carries two bodies of work:

| body of work | state of record | started |
|---|---|---|
| **the cgm-remote-monitor programme**: remedial (defects that ship), modernization (the release train), multitenant. One work queue, a backfix register, release records, reviewer packets. | `queue/work-queue.yaml`, the register, `releases/<product>-<version>/` | 2026-09 |
| **ecosystem research**: field mappings, OpenAPI specs, conformance vectors, protocol and algorithm deep dives across 20 repositories. | `mapping/`, `specs/`, `conformance/`, `traceability/`, `docs/10-domain/` | 2026-01 |

Most sessions since September 2026 are programme work. The research facets have their own
instructions in `.github/instructions/analysis-patterns.instructions.md`, which apply only when a
task is explicitly cross-project research; do not update those facets for programme work.

## 2. Start here

| question | open |
|---|---|
| where is the work, and what is it waiting for | [PROGRAMME-STATUS](docs/00-overview/PROGRAMME-STATUS.md) |
| what comes next, in what order | [ROADMAP](docs/00-overview/ROADMAP.md) |
| what is waiting on a person | [NEEDS-A-HUMAN](docs/00-overview/NEEDS-A-HUMAN.md) |
| what is in the next release, and what was checked | `releases/cgm-remote-monitor-<next>/contents.md`, `decisions.md`, `testing-notes.md` |
| the facts about a defect | [backfix register](docs/30-design/remedial/nightscout-backfix-register.md) |
| one item's claimed state, gates and blockers | `queue/work-queue.yaml` (`queue/QUEUE.md` is the generated view) |
| one pull request, bounded for review | `reports/reviewer-packets/` |
| how documents are written and controlled | [DEFINITION-OF-DONE](docs/00-overview/DEFINITION-OF-DONE.md), [DOCUMENT-CONTROL](docs/00-overview/DOCUMENT-CONTROL.md) |
| the next-generation platform plan | `docs/30-design/platform/next-gen-platform-plan.{md,json}` |
| multitenant delivery | `docs/30-design/tenancy/README.md`, then the delivery dashboard and current contracts |

```bash
make queue-status      # run the gates. THE measurement; `state` in the manifest is a claim
make queue-check       # what CI proves: register coverage, staleness of every generated view, links
make docs-links        # every path the programme documents cite resolves
```

## 3. One home per fact

Correct a fact where it lives and link to it from everywhere else. Restating it creates a second
place to go stale.

| fact | home | changed by |
|---|---|---|
| a defect: mechanism, basis, status | the backfix register, one `BF-` entry | editing the entry; ids are allocated from the register's allocation line at the moment of writing, never from a brief |
| an item's claimed state, gates, blockers | `queue/work-queue.yaml` | editing the YAML, then `make queue-validate && make queue` |
| a decision that shapes a release | `releases/<product>-<version>/decisions.md` | one row per decision, stated as it stands |
| what merged, what was tested, what is left | `releases/<product>-<version>/contents.md` update tables | appending a dated table; the file is the state of record for a cycle |
| a tenancy decision (D1–D23) | `docs/30-design/tenancy/multitenancy-decisions.md` | editing the decision; the roadmap links to it |
| a measurement | a dated record under `docs/60-research/<horizon>/` or `reports/` | never edited after capture |

`progress.md` is the dated journal of the **research** facets (section 1, second row). Programme
status, merges and handoffs go in the release records, not there.

## 4. Measurement rules

These were each earned by a defect that reached a document, and every one still applies.

1. **A state is a claim; a gate is the measurement.** `make queue-status` before acting on any
   claimed state. `UNMEASURED` and `NO-INSTRUMENT` are never green.
2. **Read-derived is a hypothesis; reproduced is evidence.** Label every defect claim and every
   figure `reproduced` or `read-derived`. A prescribed fix is evaluated, not applied: brief an agent
   to test it and report if measurement refutes it.
3. **A check that has never failed is not yet evidence.** Break the thing under test, confirm the
   check goes red, put it back. A green ablation has two meanings (the check is vacuous, or the
   break broke nothing); a red control has two meanings too. Say which, with the exact symptom.
4. **Quote hashes, counts and dates from tool output**, never from memory or a brief, and never in
   the same tool batch as the command that produces them. Re-measure before quoting a peer's number.
5. **Status words mean one thing.** `open` · `fixed` (on a branch) · `merged` (in `dev`, not
   released) · `released` (in a tag operators install). Merged to `dev` is not released. Nothing is
   fixed for an operator until `released`.
6. **Gates read; they never write.** A gate script uses `git show` or `git archive` into scratch,
   never `git checkout` into a worktree that belongs to another session. Each runnable gate declares
   its control in `queue/gate-controls.yaml`; `make queue-vacuity` runs them.

## 5. Working rules

**Writing designs and handoffs**

Write for a reader who has none of the chat history. Lead with the purpose or
outcome, then explain the mechanism and its practical limits. Use short, active
sentences and one consistent name for each component. Define technical terms on
first use; retain precise contract names and safety requirements. Keep **must**
for obligations, **does** for supported behavior and **proposed** for a design
that has not been adopted.

Use a diagram for relationships and a table for comparisons when either replaces
repeated prose. Link to the fact's existing home. A design explains responsibilities,
interfaces, state ownership, failure/recovery behavior and compatibility. A handoff
leads with what closed, what blocks progress, and the next action and owner; keep
the source anchors and evidence needed to resume. Update the existing document
or lane handoff rather than adding a parallel summary, style score or reporting
step. Use ASD-STE100-inspired plain language without claiming formal conformity.

**Git and worktrees**

- The main checkout stays on `main`. Branch work happens in a worktree (`git worktree add`), one
  per lane, named for the lane. Never delete or repoint a worktree you did not create.
- Several sessions share this checkout and **one git index**. Before every commit run
  `git diff --cached --name-only`, confirm every path is yours, and commit with
  `git commit -- <paths>`. Never `git add -A` a directory a peer may be writing to. If
  `git status --short <file>` shows a modification before your edit, the file holds a peer's work:
  have them commit first.
- **Agents never push.** Hand the maintainer the branch, the verification figures, and plain bash
  blocks for `git push` and `gh pr create`, with a per-step brief of what leaves the machine
  (commits, files, PR body, anything disclosure-sensitive). Before any push of `main`, read
  `git log origin/main..main --no-merges` and confirm every commit is yours; never pipe a
  fast-forward into a push.
- Commit messages carry no trailers (no `Co-Authored-By`), and the author is git's configured
  identity.
- For a cgm-remote-monitor fix branch: `git fetch official && git merge --no-edit official/dev`,
  re-run the affected tests, then `tools/review/prcheck/prcheck.sh` as the last step. Run the full suite
  before saying "ready": the affected tier has missed shared-database interference.
- Bundle PRs by theme and milestone, not one PR per queue item; prefer adding to an open PR with the
  same theme and reviewers.

**What goes into the public repository**

- No names, emails, identifiers or glucose traces from user data, logs or exports. Synthetic data
  only in commits. No credentials, tokens or database URLs anywhere; use the environment.
- A defect live on the shipping release is described by **mechanism, never recipe**: no request,
  payload or pattern that would work against a deployed site.
- Drafted replies, PR bodies and advisories are marked draft until a human sends them; the site
  excludes unsent correspondence (`tools/site/exclusions.yaml`).
- Say "multitenant", never "hosted", for the tenancy target. Nightscout is a secondary display for
  CGM and pump data; contributor-facing records carry no "not a medical device / not medical advice"
  lines. Operator-facing text (release notes, `operator_visible`) keeps every safety caveat in plain
  language and never gives individual dosing advice.
- No process hedges ("nobody has reviewed this", "no app asks for this"). Say what a thing is with
  the status vocabulary; credit the ideas a design borrows rather than listing what it is not.

**Asking the maintainer**

- Several sessions may be open at once; the maintainer answers in whichever is in front of them.
  Check whether a peer session has already raised or settled a question before asking again.
- A decision question carries its own description: the mechanism from the code with `file:line`,
  the trade-off, what users or operators would notice, what is measured and what is only read, and
  whether it is single- or multitenant. One topic at a time. When asked for a recommendation, give
  one under: long-term direction, architecture, backward/forward compatibility, maintenance,
  reliability, performance; name what is unmeasured.
- A deferred decision keeps its prototypes and benches running; relay it as "decision deferred,
  research continuing".

**Agents running agents**

Milestones run with background agents without asking each time. Give each lane a complete
capability or an explicit milestone criterion, one owner and one integration boundary. Keep its
helper changes, fixture repairs and authored controls in that lane; use another agent when the
work is independently deliverable or resolves a material unknown. Reuse an ongoing chat through
its fixes rather than starting a new one for each test or commit.

Every brief is self-contained: the outcome/criterion, relevant measured findings and source head,
expected focused checks and meaningful break-it controls, remaining decision boundaries, and the
two standing instructions: **stop and report a mismatch rather than reaching for the nearest
thing that works**, and **confirm the head commit and that the task is still open before starting**.
A brief that cannot be written clearly is a task not yet understood.

During implementation, run the affected/focused checks and controls appropriate to the capability.
For cgm-remote-monitor integration, the coordinator freezes the coherent joined candidate for
full/browser/enabled-corpus acceptance and final prcheck. A leaf commit or resumed session does not trigger another comprehensive
campaign. A failed campaign requires focused diagnosis, then final acceptance on the repaired
frozen candidate; planned fixes should join before that acceptance is repeated. Preserve exact
source/instrument attribution and all isolation, authorization, clinical and compatibility gates.

Report capabilities or criteria closed, remaining blockers, the next integration boundary/owner
and the evidence link. Counts and hashes support that verdict. Maintain one evolving handoff per
lane and one programme acceptance update per coherent batch; record substantive failures,
decisions and ownership transfers promptly. The tenancy [batching plan](docs/30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md#completion-focused-coordination)
defines its operational detail.

## 6. Handing off to another agent

A handoff is for a reader with none of your context, possibly a different tool. It names:

1. **Anchors**: the commit of every tree it talks about (`official/dev <sha>`, alignment `main
   <sha>`, branch heads), read from `git log` at the moment of writing.
2. **What is done**, each with where it is recorded (the contents.md table row, the decisions.md
   row, the queue id).
3. **What is next**, in order, with the gate each step must pass and the predicted result.
4. **What is local and unpushed**, by worktree path and branch, and what must not be staged.
5. **Traps** met this session: the exact symptom and the exact avoidance.
6. **Who owns what** among the open lanes, and where to send notes.

Record the programme-level state in `releases/<product>-<version>/contents.md` (a dated "Update"
table) and `decisions.md`. Write the lane-level detail to `externals/work/HANDOFF-<lane>-<date>.md`
(local, untracked: it names worktrees and ports on this machine). Link the second from the first.
Vendor memory (Claude's memory directory, Copilot session state) is private to one tool: anything
another agent must know goes in the files above or in this contract, never only in memory.

## 7. Before saying "done"

```bash
make queue-validate && make queue      # after any manifest edit
make queue-check                       # coverage, every generated view current, links
make docs-links                        # after moving or renaming any documented path
make site-check                        # after changing a rich page or pages.yaml (needs tools/site/.venv)
```

After editing `docs/30-design/platform/next-gen-platform-plan.{md,json}`: render with
`tools/site/render_nextgen.py`, move `source_commit` in `site/pages/pages.yaml` to the plan commit,
and commit both; the site publish refuses an unrendered plan.

Batch document edits before consistency checks and any required render/site build. Repeat a
check when a subsequent change can invalidate its result or a failure needs investigation.

Report outcomes as measured: a failing gate is reported with its output, a skipped step is reported
as skipped. A result nobody ran is `UNMEASURED`, never green.

## 8. Agent skills and vendor files

| file | read by | holds |
|---|---|---|
| `AGENTS.md` (this file) | every agent | the contract |
| `.github/copilot-instructions.md` | Copilot (chat, coding agent, CLI) | a pointer here plus the repository map |
| `.github/instructions/*.instructions.md` | Copilot, path-scoped by `applyTo` | the research-facet patterns |
| `.github/skills/<name>/SKILL.md` | Copilot, Claude Code (via `.claude/skills`), any agentskills.io reader | step-by-step procedures: `queue-item`, `release-record`, `evidence-harness`, `session-handoff` |
| `CLAUDE.md` | Claude Code | an import of this file plus the memory-directory note |

Dormant tooling kept for its history: `sdqctl` workflows (`workflows/*.conv`,
`docs/sdqctl-proposals/`, the `sdqctl-*` make targets) and the January–April 2026 research campaign
(`docs/archive/verification-campaign-2026-04/`, `docs/60-research/figures/`). Neither is part of the
programme's gates.
