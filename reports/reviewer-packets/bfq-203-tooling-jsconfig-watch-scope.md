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

# Review packet — BFQ-203 (PR #8871)

**BF-203 - an editor opening a cgm-remote-monitor file inside a larger workspace
watches every sibling worktree (450,689 inotify watches); add jsconfig.json**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `tooling/jsconfig-watch-scope` |
| base | `official/dev@7abe1cf6` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-203` is the measurement |
| semver | `n/a` |
| register entries | `BF-203` |

## What this changes

One new file, jsconfig.json (8 lines: module commonjs, target es2022, checkJs
false, exclude node_modules, coverage, .nyc_output, tmp). Read only by
editors' TypeScript servers; build, lint, tests and the server ignore it.

## Why that semver

editor tooling; nothing the server, build or tests read

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official show tooling/jsconfig-watch-scope:jsconfig.json | node -e "const `** &nbsp;·&nbsp; kind: `static`

The branch has a jsconfig.json that scopes the project by exclude only (no
include or files list, so new folders stay covered) and excludes node_modules.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The watch count needs a TypeScript server started as an editor starts it,
  about 2.5 minutes per measurement, so it is not a queue gate. Measured
  2026-10-27 with tsserver 5.9.3 on Linux, opening lib/server/app.js with
  --useInferredProjectPerProjectRoot, JavaScript enabled for inferred
  projects and the alignment repo as project root: 450,689 watches and 1.4
  GB without the file, 2,007 and 358 MB with it. Plain tsserver without
  those settings gives 1,203 either way.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-27, 22:21:20Z: #8871 opened by the maintainer into dev, head f28d40bb.
2026-10-27: draft e737d310 by the maintainer through session -a7 (437,239
against 5,616 watches in its probe), re-measured by session -e4 and dev
7abe1cf6 merged in as f28d40bb. tsc -p jsconfig.json --listFilesOnly lists
lib/server/app.js; test:tiers 401 files ok; npm test on dev 9668b179 plus the
file 4700 passing, 0 failing, 3 pending. No tooling PR is open, so it starts
the next one. The editor-side companion of BF-201.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-203` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
