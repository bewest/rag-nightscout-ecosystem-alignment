---
name: session-handoff
description: >-
  Write or refresh a vendor-neutral capability-lane handoff with source anchors, acceptance limits, next integration boundary and ownership. Use for an ownership or context transfer, or when a capability stops or completes.
---

# Session handoff

Two layers, linked: the **programme-level state** goes in the release records (shared, tracked),
and the **lane-level detail** goes in a local handoff file (untracked, because it names worktrees
and ports on this machine). Vendor memory is private to one tool and is never the only copy.

## Handoff granularity

Keep one evolving handoff for a capability lane. Update it when the next owner,
blocker, acceptance verdict or integration boundary changes; link immutable
captures instead of restating every run. A helper commit or individual control
is not a new lane or a reason to create another chat/handoff.

Lead with capability/criterion closed, remaining blockers and next join/owner.
Keep the source anchors and evidence needed to resume safely. Programme acceptance
is recorded per coherent batch; substantive failures, decisions and ownership
transfers are still recorded promptly. Follow the repository's completion-focused
coordination contract in `AGENTS.md` and the applicable batch plan.

## 1. Record the programme state (tracked)

Append a dated Update table to `releases/<product>-<version>/contents.md` and any decision rows to
`decisions.md` (the `release-record` skill). Hashes come from `git log` run now, not from a brief.

## 2. Write the lane handoff (local)

File: `externals/work/HANDOFF-<lane>-<YYYY-MM-DD>.md`. Template:

```markdown
# Handoff from <lane> (<date>, <time>Z)

Lane: <one line: what this lane owns>

## State
- <repo> `dev` = `<sha>` (fetched <time>Z). Merged this session, in order: #<n> (`<sha>`), ...
- Alignment `main` = `<sha>`; unpushed local commits: <list or "none">.
- Branch `<name>`: worktree `<path>`, head `<sha>` on `dev` `<sha>`, not pushed. Gates: <suite>
  <pass/fail/pending> on <tree>, <db version>; <matrix or lab result with its pin>.

## Done, and where it is recorded
- <item>: contents.md "Update, <date>" row; decisions.md row "<title>"; queue `<id>` state `<claim>`.

## Next, in order
1. <step>. Gate: <command>. Predicted: <result>. Owner: <lane or "unassigned">.
2. ...

## Local and unpushed
- <worktree path>: <branch> `<sha>`; uncommitted: <files or none>; do NOT stage: <files>.

## Traps met this session
- <symptom, exactly as seen> → <avoidance, exactly what to do>.

## Ownership
- <lane>: <what>. Send notes on <topic> to <person or lane>.
```

Rules for the content:

- **Anchors, not adjectives.** "dev is current" says nothing; `dev f54941b5, fetched 07:40Z` does.
- **Every claim has its evidence location** or is marked `read-derived`.
- **Predicted results** for each next step, so the next agent can tell a mismatch from a success.
- **What must not be staged** is listed by path, because the index is shared.
- No secrets, tokens or database URLs; container names and ports are fine.

## 3. Link the two

Put the handoff file's path in the contents.md Update row ("lane detail:
`externals/work/HANDOFF-<lane>-<date>.md`, local"). If the handoff carries decisions or traps that
outlive the lane, write them into `AGENTS.md` §5 or a skill in the same commit, so they reach every
tool.

## 4. Tell the person

In the final message: the state in two lines, what is pushed and what is not, the next step and its
owner, and the two file paths. Report a failing or skipped gate as such.
