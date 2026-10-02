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

# Review packet — BFQ-155

**BF-155 - a failed storage read on GET /api/v1/activity ends the server
process, for 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/activity-read-error` |
| base | `official/dev@25fc41d9` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-155` is the measurement |
| semver | `patch` |
| register entries | `BF-155` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/api/activity/index.js and lib/api/profile/index.js (/profile/current) read
callbacks: any storage error is answered with a 500 without its text (logged
on the server); a refused query still 400. tests/api.read-storage-
failure.test.js. Branch bf/activity-read-error e20b66ba, one commit on dev
25fc41d9, worktree externals/work/crm-bf155, not pushed.

## Why that semver

a failed read answers an error instead of ending the process

## What an operator would notice

> A problem reading from the database could stop Nightscout until it was
> restarted. It now answers that request with an error and keeps running.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official cat-file -e bf/activity-read-error:tests/api.read-storage-failure`** &nbsp;·&nbsp; kind: `static`

The branch carries the storage-failure test (a presence check; RED on
origin/dev 25fc41d9). The test decides.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced 2026-10-02 on local test servers of v15.0.8 and dev 25fc41d9;
  the method is held outside version control while the defect is live on
  15.0.8. The branch's tests decide, using a stubbed storage failure
  delivered through run-with-callback: on e20b66ba (Node 22.23.2, MongoDB
  7.0.43) both answer 500 without the error text and the server keeps
  serving; with dev 25fc41d9's handlers both requests are never answered
  (timeout). Full suite 3534/0/4 (dev 3532/0/4).

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Decided 2026-10-02 (maintainer): fix for 15.0.9; in RT-0's blocks_on. Found
while reviewing bf/regex-limits (BFQ-72), which does not cover it. The audit
of the other v1 read callbacks found /profile/current with the same failure
(fixed here). /api/v1/food and /api/v1/profile answer null with 200 on a
failed read, which does not end the process; left for a later change. PR body:
reports/phase0-pr-bodies/activity-read-error.md.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-155` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
