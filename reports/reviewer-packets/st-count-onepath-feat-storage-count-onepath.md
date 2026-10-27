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

# Review packet — ST-COUNT-ONEPATH (PR #8870)

**API v1 count only through the storage interface: lib/server/aggregate.js loses
its constructor pipeline hook and no-store path**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `feat/storage-count-onepath` |
| base | `official/dev@9668b179` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=ST-COUNT-ONEPATH` is the measurement |
| semver | `patch` |

## What this changes

lib/server/aggregate.js (create(api, store), store required), its three
callers in entries, treatments and devicestatus, a comment in lib/api3
modify.js, and three test files; 8 files, +66/-130.

## Why that semver

unreachable over HTTP; the API v1 HTTP differential is 700/700 identical,
including 219 count requests

## What an operator would notice

> Nothing changes: no request reached the removed path.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 9668b179 feat/storage-count-onepath`** &nbsp;·&nbsp; kind: `static`

The branch is on dev 9668b179 (both slices merged). Red if it is rebased off
dev or deleted.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/platform/next-gen-platform-plan.md`](../../docs/30-design/platform/next-gen-platform-plan.md)

## Notes carried on the item

2026-10-27: opened as #8870 (base dev, head 0955f25b, not a draft; 13 checks
passed at the time of the report, three still running), by the maintainer from
session -2e's branch. Decided 2026-10-27 as a follow-up after the slices, done
before the 16.0.0 tag. Session -2e (Node 22.23.4): npm test 4698 passing, 0
failing, 3 pending and test:all 5026/0/3 on MongoDB 7.0 (dev 4700 and 5028:
three tests removed with the hook, one added); v1 HTTP differential against
dev 9668b179 on MongoDB 5.0 700/700 identical (219 counts). The new
construction test fails on dev's code, and fails alone when only the
construction check is removed (53 pass, 1 fails).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ST-COUNT-ONEPATH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
