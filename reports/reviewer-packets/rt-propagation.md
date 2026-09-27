<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->

# Review packet — RT-PROPAGATION

**How the release train reaches dev: merge dev into the cuts, or rebase the cuts
onto dev**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@ce30a94d` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=RT-PROPAGATION` is the measurement |
| semver | `n/a` |

## What this changes

A decision, no code. It decides whether the commits of cuts 1-5 (and of
chore/nightscout-modernization, the seam's base) are kept or rewritten when
they take dev, and so which path the seam refresh takes (execution plan
section 5.1).

## Why that semver

branch mechanics, not a release

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision. What is measured (2026-09-27): every propagation so far has
  been a merge. e3b22034 merged dev into the modernization branch
  (2026-09-21), and both local rehearsals keep every cut 1 commit - `git -C
  externals/cgm-remote-monitor-official rev-list --count
  official/chore/retire-jsdom ^rt/cut1` is 0, and the same for rh/cut1. RT-
  REBASE is named for a rebase, and no one has ruled one out.

## Evidence

- [`docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)

## Notes carried on the item

Merge keeps the seam's base, so SEAM-REFRESH is one merge into the seam tip,
keeping the history of its 16 branches. Rebase rewrites the base, so the seam
is re-parented onto dev instead: the Phase 1 prefix (seam/t1-2-e) after RT-3,
which brings MongoDB driver 7, and the rest after RT-5, which carries
9e869662. Recorded as open at the maintainer's request, 2026-09-27.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-PROPAGATION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `295f1177`.*
