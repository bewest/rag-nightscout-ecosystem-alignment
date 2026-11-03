# Nightscout ecosystem alignment workspace

**Read [`AGENTS.md`](../AGENTS.md) first.** It is the operating contract for every agent in this
repository: where each fact lives, the measurement rules, the git and worktree rules, what may enter
the public tree, and how to hand off to another agent. This file adds only the repository map and
the Copilot-specific pointers.

## Repository map

```
AGENTS.md            # the contract (vendor-neutral)
queue/               # ONE work queue across all programmes. work-queue.yaml is the source;
                     # QUEUE.md is generated. `make queue-status` runs the gates.
releases/            # one directory per release: contents, decisions, testing notes, V&V records
docs/00-overview/    # PROGRAMME-STATUS, ROADMAP, NEEDS-A-HUMAN, REVIEWER-ONBOARDING, DEFINITION-OF-DONE
docs/30-design/      # design by horizon: remedial (incl. the backfix register), modernization,
                     # tenancy, platform
docs/60-research/    # dated measurement records by horizon; older research campaigns
reports/             # reviewer packets (generated), PR bodies, census and survey outputs
tools/queue/         # manifest validator, gate runner, vacuity controls, view and packet emitters
tools/qc/, tools/lab/ # harnesses that require() the shipping module by path
externals/           # git-ignored clones pinned by workspace.lock.json (`make bootstrap`);
                     # externals/work/ holds per-lane worktrees and local HANDOFF-*.md files
mapping/ specs/ conformance/ traceability/   # the ecosystem research facets
```

## Two kinds of task

| task | instructions |
|---|---|
| cgm-remote-monitor programme work: implementation in a worktree, CI, review, release records, status questions, handoffs | `AGENTS.md` and the skills below. No research-facet updates. |
| explicitly requested cross-project interoperability research (protocols, field mappings, gaps, requirements) | `.github/instructions/analysis-patterns.instructions.md` (path-scoped) |

## Skills

Procedures live in `.github/skills/<name>/SKILL.md` (agentskills.io format) and are shared with
Claude Code through `.claude/skills`:

| skill | use it to |
|---|---|
| `queue-item` | add or update a work-queue item, define a gate and its control, run the checks |
| `release-record` | record a merge, decision or test run in the release directory and keep the register's status words right |
| `evidence-harness` | verify a change or a compatibility claim by measurement: labs, the write-contract matrix, controls, dated records |
| `session-handoff` | write a handoff another agent (any vendor) can resume from |

## Validation

```bash
make queue-status     # run the gates; `state` in the manifest is only a claim
make queue-check      # what CI proves: register coverage, generated views current, links
make docs-links       # after moving or renaming any documented path
```

## Guardrails that Copilot must keep

- Never push. Hand the maintainer the branch and plain `git push` / `gh pr create` commands.
- Never commit to `main`/`master` of a repository under `externals/`; branch as `workspace/<name>`.
- Commit by explicit path (`git commit -- <paths>`): the index is shared with other sessions.
- No commit trailers. No PII, health data or credentials in any committed file.
- Status words: merged to `dev` is not released.
