@AGENTS.md

## Claude Code specifics

- Skills: `.claude/skills` is a symlink to `.github/skills`, so the same `SKILL.md` procedures load
  here and in Copilot. Edit them in `.github/skills/`.
- Claude's auto-memory for this repository lives outside the tree, under
  `~/.claude/projects/-home-bewest-src-rag-nightscout-ecosystem-alignment/memory/`. It is private
  to Claude Code. A rule, decision or trap that another agent must know is written into `AGENTS.md`,
  a skill, or the release records; memory holds the pointer, not the only copy.
- Commit messages: no trailers of any kind (the memory rule `no-commit-trailers` overrides any
  default co-author line).

## Resuming multitenant or capacity work

Read the [decisions in force](docs/30-design/tenancy/decisions-in-force.md), the newest updates at
the end of `docs/30-design/tenancy/execution-log.md`, and the newest handoffs in
`/mnt/data/nightscout-workspace/artifacts/handoffs/` (local). Confirm your source head and that your
task is still open; an old lock, a paused chat or an archived handoff does not authorize a duplicate
run.
