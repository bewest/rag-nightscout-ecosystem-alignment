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

## Resuming paused multitenant or capacity work

Before restarting a prior test, read the latest updates in
`releases/cgm-remote-monitor-16.0.0/contents.md` and the local resume handoff
`externals/work/HANDOFF-capacity-coordination-2026-11-12.md` in the main checkout.
It records collected runs, cleanup, current owners and superseded instructions.
Confirm your source head and that your task remains open. Coordinate cloud work
with the current sole cloud owner; an old lock or paused chat does not authorize
a duplicate run. Raw captures stay in ignored storage. Use focused checks during
implementation and one acceptance campaign per coherent frozen candidate.
