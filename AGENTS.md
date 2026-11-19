# Working in this repository: the contract for any agent

*Contributor-facing operating contract for coding agents (Copilot, Claude Code, Codex, Cursor, local
models). It holds only repository facts an agent cannot infer and corrections to failures that
recurred. Everything else is left to the agent's judgement and to the gates. Living document,
2026-11-18. Onboarding: [REVIEWER-ONBOARDING](docs/00-overview/REVIEWER-ONBOARDING.md).*

## 1. What this repository is

An alignment workspace for the Nightscout ecosystem: **configuration, documentation, evidence and
harnesses**. The shipping applications live in `externals/` (git-ignored, pinned by
`workspace.lock.json`, restored by `make bootstrap`).

| body of work | state of record |
|---|---|
| **the cgm-remote-monitor programme** (remedial, the release train, multitenant), since 2026-09 | `queue/work-queue.yaml`, the [backfix register](docs/30-design/remedial/nightscout-backfix-register.md), `releases/<product>-<version>/` |
| **ecosystem research** (mappings, specs, conformance, deep dives), since 2026-01 | `mapping/`, `specs/`, `conformance/`, `traceability/`, `docs/10-domain/` |

Most work is programme work. The research instructions in
`.github/instructions/analysis-patterns.instructions.md` apply only to explicit cross-project research.

## 2. Where things are

| question | open |
|---|---|
| where the work is, what it waits for, what comes next | [PROGRAMME-STATUS](docs/00-overview/PROGRAMME-STATUS.md), [ROADMAP](docs/00-overview/ROADMAP.md), [NEEDS-A-HUMAN](docs/00-overview/NEEDS-A-HUMAN.md) |
| the next release: contents, decisions, testing | `releases/cgm-remote-monitor-<next>/` |
| a defect | the backfix register, one `BF-` entry; allocate ids from its allocation line, never from a brief |
| one item's claimed state, gates, blockers | `queue/work-queue.yaml` (then `make queue-validate && make queue`) |
| multitenant decisions and progress | [decisions in force](docs/30-design/tenancy/decisions-in-force.md), then `multitenancy-decisions.md` and the dated `execution-log.md` in `docs/30-design/tenancy/`; multitenant work stays out of `releases/` until a release ships a multitenant role |
| document conventions | [DEFINITION-OF-DONE](docs/00-overview/DEFINITION-OF-DONE.md), [DOCUMENT-CONTROL](docs/00-overview/DOCUMENT-CONTROL.md) |

Correct a fact where it lives and link to it; a restated fact goes stale. Record a new decision only
when it changes what an agent or operator does, and mark any row it replaces as superseded in the
same edit. `progress.md` is the research journal only.

## 3. Measurement rules

Each was earned by a defect that reached a document. They govern **claims written into records**
(register, queue, release and tenancy records, reviewer packets), not every tool step. Add machinery
to a tool only to protect a product property (isolation, authorization, one writer per tenant,
restore fencing, clinical deadlines); see
[architecture-justified-removal](docs/30-design/tenancy/multitenancy-decisions.md#architecture-justified-removal).

1. **A state is a claim; a gate is the measurement.** Run `make queue-status` before acting on a
   claimed state. `UNMEASURED` and `NO-INSTRUMENT` are never green.
2. **Label every defect claim and figure `reproduced` or `read-derived`.** Read-derived entries have
   repeatedly been wrong. A prescribed fix is evaluated, not applied.
3. **A gate that has never failed is not yet evidence.** Break the property, see red, restore.
4. **Quote hashes, counts and dates from tool output** that you ran, never from memory or a brief.
5. **Status words:** `open` · `fixed` (on a branch) · `merged` (in `dev`) · `released` (in a tag
   operators install). Nothing is fixed for an operator until `released`.
6. **Gates read; they never write.** Use `git show`/`git archive` into scratch, never `git checkout`
   in another session's worktree. Gates read `official/*`, not the stale `origin/*` in `externals/`.

## 4. Repository facts and corrections

**Shared checkout and Git**
- The main checkout stays on `main` and several sessions share **one git index**. Branch work goes
  in a worktree; never delete or repoint a worktree you did not create. Commit by path (`git commit -- <paths>`) after checking `git diff --cached
  --name-only`. A file already modified before your edit holds a peer's work.
- **Agents never push.** Give the maintainer the branch and the push/PR commands, and say what
  leaves the machine.
- Commit messages carry no trailers; the author is git's configured identity.
- A cgm-remote-monitor fix branch merges `official/dev`, re-runs the affected tests and the full
  suite (the affected tier has missed shared-database interference), then
  `tools/review/prcheck/prcheck.sh`. Bundle PRs by theme.

**Storage on this workstation:** new worktrees, run outputs and lane handoffs go on
`/mnt/data/nightscout-workspace`, laid out by its `WORKSPACE-LAYOUT.txt`. If it is not mounted,
stop and report it. Live runs, fixtures and existing evidence stay where they are. An alignment
worktree has no `externals/`; link the main checkout's `externals/work` into it if a gate needs it.

**The public repository**
- No names, emails, identifiers or glucose traces from user data. Synthetic data only. No
  credentials, tokens or database URLs; use the environment.
- A defect live on the shipping release is described by **mechanism, never recipe**.
- Raw capacity and acceptance outputs stay outside Git; commit findings, aggregates, commands,
  limitations and a retained-evidence identifier.
- Drafted replies, PR bodies and advisories stay marked draft until a human sends them.
- Say "multitenant", never "hosted". Nightscout is a secondary display: contributor-facing records
  carry no "not a medical device / not medical advice" lines. Operator-facing text keeps every safety
  caveat in plain language and never gives individual dosing advice.
- No process hedges ("nobody has reviewed this"); say what a thing is with the status words.

**The maintainer and other sessions**
- Several sessions run at once; check whether a peer already asked or settled a question.
- A decision question carries the mechanism (`file:line`), the trade-off, what users or operators
  notice, what is measured versus read, and single- versus multitenant. One topic at a time.
  Recommend when asked. A deferred decision keeps its research running.

**Agents running agents**
- Milestones run with background agents without asking. One owner and one integration boundary
  per capability; a diagnostic or control stays inside its capability's lane. Fresh context at a
  phase boundary, not per test or commit. One acceptance campaign per frozen candidate.
- A brief is short and links rather than pastes. It states the outcome, the source head and the
  actions outside the worktree it authorizes, and it carries two instructions: **stop and report a
  mismatch rather than reaching for the nearest thing that works**, and **confirm the head commit
  and that the task is still open before starting**.
- Multitenant lanes also follow the experiment and restriction policies in
  [deployment-and-rig-testing](docs/30-design/tenancy/deployment-and-rig-testing.md).

## 5. Handoffs

Programme state goes in the records of section 2. Lane detail goes in a local handoff under
`/mnt/data/nightscout-workspace/artifacts/handoffs/` (untracked: it names worktrees and ports),
preferably one file per lane updated in place, linked from the record. The `session-handoff` skill
has the template. Anything another agent must know goes into these files, never only into one
tool's memory.

## 6. Before saying "done"

```bash
make queue-validate && make queue      # after any manifest edit
make queue-check                       # coverage, generated views, links (CI runs this)
make docs-links                        # after moving or renaming a documented path
make site-check                        # after changing a rich page or pages.yaml
```

After editing `docs/30-design/platform/next-gen-platform-plan.{md,json}`, render with
`tools/site/render_nextgen.py` and move `source_commit` in `site/pages/pages.yaml`; the publish
refuses an unrendered plan. Report results as measured: a failing gate with its output, a skipped
step as skipped.

## 7. Vendor files

`.github/copilot-instructions.md` and `CLAUDE.md` point here. Skills live in `.github/skills/`
(`queue-item`, `release-record`, `evidence-harness`, `session-handoff`); `.claude/skills` links to
them. Dormant: the `sdqctl` workflows and the 2026 January–April research campaign.
