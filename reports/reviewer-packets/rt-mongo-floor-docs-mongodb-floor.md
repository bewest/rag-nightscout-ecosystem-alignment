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

# Review packet — RT-MONGO-FLOOR

**README: MongoDB 4.4 is deprecated, not unsupported, in 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `docs/mongodb-floor` |
| base | `origin/dev@74fc6619` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=RT-MONGO-FLOOR` is the measurement |
| semver | `patch` |

## What this changes

README.md, one line of the installation requirements. No code.

## Why that semver

documentation only

## What an operator would notice

> The installation instructions said MongoDB 4.4 no longer works with this
> version. It does still work and is still tested. 15.0.9 will say instead
> that 4.4 is deprecated and support will be removed in a later release, so
> plan to upgrade the database one major version at a time.

## Who should review this, and why

maintainer

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official show docs/mongodb-floor:README.md | grep -q "MongoDB 4.4 i`** &nbsp;·&nbsp; kind: `static`

the prepared branch carries the deprecation wording

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev docs/mongodb-floor >/dev/null`** &nbsp;·&nbsp; kind: `static`

the branch merges into dev without conflict

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/backfix-2-plan-2026-09-22.md`](../../docs/30-design/remedial/backfix-2-plan-2026-09-22.md)

## Notes carried on the item

DECIDED 2026-09-23 (maintainer) - deprecate 4.4 now, drop it later. Prepared
as aabce4b1 by the other session; this item was added 2026-09-23 because the
branch had none. The commit message serves as the PR body (gh pr create
--fill).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-MONGO-FLOOR` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
