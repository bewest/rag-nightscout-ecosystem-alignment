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

# Review packet — BFQ-201 (PR #8866)

**BF-201 - npm run dev's nodemon watches nearly the whole repository (1,502
Linux file watches); watch the paths the server loads**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `test/16.0.0-ci-flakes` |
| base | `official/dev@2dc0c1bc` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-201` is the measurement |
| semver | `n/a` |
| register entries | `BF-201` |

## What this changes

package.json nodemonConfig (ignore list to watch list), tests/development-
watch.test.js and tools/probe-development-watch.py (fixture and expectations),
docs/test-specs/development-watch.md (M24 addendum), docs/audits/development-
watch.json and one plan line. npm start and the Docker image never run
nodemon.

## Why that semver

developer tooling; no API, page, setting or runtime change

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official show test/16.0.0-ci-flakes:package.json | node -e "const c=JSON.p`** &nbsp;·&nbsp; kind: `static`

#8866's branch's nodemonConfig is a watch list that includes lib and leaves
out static, with no ignore list.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The watch test starts nodemon and native watch in owned fixtures for about
  50 s, so it is not a queue gate. Measured 2026-10-27 at dev 2dc0c1bc on
  Linux, Node 22.23.4, nodemon 3.1.14: inotify watches 1,502 before against
  385 after (lib and views alone 345; node --watch-path scoped the same way
  346). The test passes on the branch and, with the previous configuration
  and the new expectations, fails at docs/unlisted.js.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-27: asked for by the maintainer through session -a7, after
tests/development-watch.test.js failed with ENOSPC on 2026-10-26. Measured
counts replace -a7's at dev 47723cda (1,396 and 339); the list adds
translations, webpack and package.json, which the server reads at startup, so
editing them still restarts it. Prepared as 426d2835 on chore/16.0.0-nodemon-
watch-allowlist; npm test 4483 passing, 0 failing, 3 pending (Node 22.23.4,
MongoDB 8.0.34). At the maintainer's request, cherry-picked onto #8867 as
5d9f84b5 and pushed 2026-10-27 (the CI and tooling PR), not a PR of its own.
Later that day, at the maintainer's request, #8867 was merged into #8866's
branch as 7a96b912, so it ships with #8866.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-201` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
