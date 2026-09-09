# Release Cadence Framework: Modernization vs. Bug Fixes vs. New Features

**Status:** Draft rubric for discussion — no release decisions are made here.

## 1. Why these three workstreams compete for the same branch

All three currently target `dev` on `cgm-remote-monitor`:

| Workstream | Current vehicle | Characteristic risk |
|---|---|---|
| Modernization | PR #8605 (`chore/nightscout-modernization`), 573 files, 30 milestones | Large surface area, but incrementally reviewed; risk is mostly *regression breadth* (many subsystems touched) not *depth per change* |
| Bug fixes / security hotfixes | `wip/bewest/security-hotfix-eval-*` branches (this repo's sibling doc set), individual small PRs (#8591 merged, #8722/#8723 folded into modernization) | Small surface area, but time-sensitive — a known vulnerability's exposure window matters | 
| New features | Not yet branched; see `feature-backlog-prioritization.md` | Currently zero committed surface area — pure prioritization/scoping risk |

**Observed pattern, not yet a decision**: security fixes are already leaking
into the modernization branch (e.g. #8722, #8723) rather than landing in
`dev` independently. This has a real tradeoff:
- *For* folding security fixes into modernization: avoids merge-conflict
  duplication (the same file, e.g. `lib/server/app.js`, would otherwise be
  touched by both an independent hotfix and the modernization branch).
- *Against*: it makes an urgent, small, easily-revertable fix (e.g. the
  `TRUST_PROXY` change) depend on the review/merge timeline of a 573-file
  branch — see `pr-8605-merge-readiness.md` §3 for the concrete instance of
  this tension (report #2's fix currently only reaches `dev` via #8605).

**Open question for maintainers**: should security/bug fixes always land in
`dev` first (smallest possible surface, fastest exposure-window closure),
with the modernization branch rebasing onto them afterward — or is the
current pattern (fix lands in the integration branch, `dev` gets it only
when the whole branch merges) intentional and acceptable given the review
overhead of maintaining two moving targets?

## 2. Split vs. large release — decision rubric (not yet decided)

The question "should modernization progress keep splitting across releases,
or should we accept an increasingly large release" has at least three
independent sub-questions that get conflated if treated as one:

| Sub-question | What decides it | Current evidence |
|---|---|---|
| **(a) Review burden** — is the diff reviewable at all? | Whether changes were already reviewed in smaller units before aggregation | Already addressed procedurally: 30 milestones, each individually gated and CI-checked before folding into the integration branch (`pr-8605-merge-readiness.md` §5) |
| **(b) Rollback granularity** — if something breaks in production after merge, how much has to be reverted? | Whether the merge to `dev` is one commit (single revert reverts everything) or several sequential merges (partial revert possible) | **Not yet decided.** #8605 as currently structured would land as one merge to `dev`. A production issue traced to, say, M14 (Flot update) would require either reverting the entire integration or a manual forward-fix — no granular rollback path currently exists once merged as a single PR. |
| **(c) Release-notes / version-bump semantics** — does this correspond to one version bump or several? | Project's own versioning convention | `15.0.8` has already shipped from `dev` independently of #8605 (tag observed during this review) — modernization has *not* been blocking other releases so far, which is evidence the split approach has been working, not that it must stop. |

**Recommendation direction (not a decision)**: (a) is already resolved by the
milestone structure — this removes "it's too big to review" as a valid
objection on its own. The real open question is (b): whether to request the
modernization branch merge to `dev` in a small number of sequential PRs
(e.g., grouped by milestone phase) to preserve rollback granularity, rather
than a single 573-file merge commit. This is a request to make **to the
maintainers**, not a decision this repo can make unilaterally, since it
affects their release process.

## 3. Proposed cadence pattern (draft, for discussion)

| Release type | Suggested cadence | Rationale |
|---|---|---|
| Security hotfix | As needed, independent of other cycles, smallest possible diff, direct to `dev` | Exposure-window minimization; matches the `security-hotfix-eval-2026` branch-per-report pattern already in use |
| Modernization | Batched, milestone-phase-aligned merges to `dev` (not necessarily one #8605-sized merge) | Preserves the review-granularity benefit already achieved while adding rollback granularity |
| New features | Gated behind modernization's stated prerequisites where applicable (see `feature-backlog-prioritization.md`) — e.g. statistics API extraction is a prerequisite for MCP resource exposure | Avoids building new-feature surface on top of a moving dependency/runtime baseline |

**This table is a starting proposal, not a ratified policy.** It needs
maintainer sign-off before being treated as guidance, and should be revisited
once the #8605 review-gate question above is resolved.
