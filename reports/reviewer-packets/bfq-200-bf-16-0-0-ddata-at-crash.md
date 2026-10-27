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

# Review packet — BFQ-200

**BF-200 - on dev, an unusable time on API v2's data-snapshot route stops the
server**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-ddata-at-crash` |
| base | `official/dev@2dc0c1bc` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-200` is the measurement |
| semver | `patch` |
| register entries | `BF-200` |

## What this changes

lib/data/endpoints.js (/api/v2/ddata/at/:at answers 400 for a time that does
not parse, before any load starts) and lib/data/dataloader.js (update()
reports an error to its callback, without changing ddata or starting a query,
when lastUpdated or its 372-day look-back is outside the Date range); one new
test file. Responses for valid times are unchanged.

## Why that semver

a regression introduced on dev and never released is fixed; against 15.0.9 the
request's 500 becomes 400, an error answer for an input no client sends
successfully

## What an operator would notice

> On dev only: one authenticated read request on this route with a time the
> server cannot use stops the whole site until it restarts. With the fix the
> request is refused with 400 and the site keeps running. 15.0.9 answers the
> same request with 500 and keeps running.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 434c0157 bf/16.0.0-ddata-at-crash`** &nbsp;·&nbsp; kind: `static`

The fix commit 434c0157 is on the branch. Red if the branch is rewritten
without it.

**`sh -c 'd=$(mktemp -d) && git -C externals/cgm-remote-monitor-official archive bf/16.0.0-ddata-at-crash | tar -`** &nbsp;·&nbsp; kind: `unit`

Runs the branch's own tree (git archive) and its new test tests/data.ddata-
at.test.js: the 400 path, the query bounds for a valid frame, and the loader
guard (NaN and both ends of the Date range). 5 passing, measured 2026-10-27.
Uses the fix worktree's node_modules.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-27: found by session -2e's route census on dev 2dc0c1bc and #8863;
fixed by its agent on bf/16.0.0-ddata-at-crash 434c0157 (on dev 2dc0c1bc, 3
files, +142). v15.0.9 checked by -2e: not affected (500, process keeps
running), so it is a dev-only regression from 26d0908a (callback-tasks
replacing async) and goes as an ordinary 16.0.0 fix, no advisory fork. -2e's
runs (Node 22.23.4, MongoDB 7.0.43): npm test 4487 passing, 1 failing, 3
pending; test:all 4815 passing, 1 failing, 3 pending; the one failure is the
nodemon watch test on the host's inotify limit (ENOSPC), not this change. Red
control re-run by session -ee: the new test on dev 2dc0c1bc's tree gives 1
passing, 5 failing (-2e reported 0 passing, 5 failing); on the branch 5
passing. Not pushed; the maintainer pushes and opens the PR (body in -2e's
scratchpad, ddata/PR-BODY.md).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-200` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
