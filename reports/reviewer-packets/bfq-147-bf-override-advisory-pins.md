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

# Review packet — BFQ-147

**BF-147 - two package.json overrides hold ajv and request's form-data inside
published advisory ranges**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/override-advisory-pins` |
| base | `origin/dev@295f1177` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-147` is the measurement |
| semver | `patch` |
| register entries | `BF-147` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

package.json overrides ("ajv@^6.0.0" 6.12.6 -> 6.14.0, request > form-data
2.5.5 -> 2.5.6) and package-lock.json, with a refresh of browserslist,
baseline-browser-mapping and postcss-selector-parser inside their declared
ranges: 9 lockfile versions, all patch or minor, all build tooling or request
internals. No lib/ change.

## Why that semver

dependency versions within declared ranges; no server or page behaviour change
measured

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Run 2026-09-27 on bf/override-advisory-pins (64a9cc13, one commit on
  295f1177; worktree externals/work/crm-audit-exp): npm audit --package-
  lock-only 17 -> 7 (0 high); npm ci and the bundle build (webpack 5.106.2,
  3 warnings); suite 3473/0/3 on Node 24.15.0 with MongoDB 7.0.43;
  tests/dependency-overrides.test.js 5/5, 0/5 on 295f1177's tree. Needs
  node_modules and MongoDB, so not a queue gate.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`releases/cgm-remote-monitor-15.0.9/contents.md`](../../releases/cgm-remote-monitor-15.0.9/contents.md)

## Notes carried on the item

Filed 2026-09-27 from the 15.0.9 npm audit triage. On v15.0.8 too. Whether it
goes into 15.0.9 is the maintainer's call; a lockfile change re-anchors the
15.0.9 records. Retired on the modernization line (rh/cut4 audits at 0).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-147` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `295f1177`.*
