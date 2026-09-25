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

# Review packet — RT-PR-8419 (PR #8419)

**#8419 - tests for Loop push notifications and websockets (je-l), carried into
15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `extend-api-tests` |
| base | `origin/dev@4f705217` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=RT-PR-8419` is the measurement |
| semver | `n/a` |

## What this changes

Tests only, 9 files: moves the APNs test certificates to tests/fixtures/,
folds tests/loop-server.test.js into a new tests/loopnotifications.test.js,
adds .nycrc.json. Head b1c23e74, 152 commits behind dev; merges cleanly with
dev 4f705217 and with #8758 (measured 2026-09-25).

## Why that semver

tests only

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev refs/triage/pr-8419 >/dev/null`** &nbsp;·&nbsp; kind: `static`

#8419's head merges into origin/dev without conflict. Needs `git -C
externals/cgm-remote-monitor-official fetch official
pull/8419/head:refs/triage/pr-8419` first.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The PR's own tests: tests/loopnotifications.test.js on dev with the PR
  merged, 9 passing (2026-09-25, open-PR triage). Not yet run in a combined
  candidate.

## Evidence

- [`docs/60-research/remedial/github-triage-2026-09-25.md`](../../docs/60-research/remedial/github-triage-2026-09-25.md)

## Notes carried on the item

Outside contributor (je-l), opened 2026-01-15. Decided 2026-09-25
(maintainer): carry into 15.0.9. It is a file-level rebase cost for #8605,
which also edits tests/loop-server.test.js and the instance fixtures.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-PR-8419` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
