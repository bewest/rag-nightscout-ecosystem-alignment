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

# Review packet — BFQ-241

**BF-241 - one upload limit, UPLOAD_BODY_LIMIT, for entries, treatments and
device status**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `claude/upload-body-limit-20261121` |
| base | `official/dev@79144cbd0` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-241` is the measurement |
| semver | `minor` |
| register entries | `BF-241` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

1 commit (1820bae16), 7 files, +193/-7: lib/middleware/body-limits.js (new),
lib/api/{entries,treatments,devicestatus}/index.js, lib/server/env.js,
README.md, tests/api.body-limits.test.js. Shared 1 MB parsers and every other
route unchanged.

## Why that semver

New operator setting UPLOAD_BODY_LIMIT; device status accepts larger bodies.
No route, response or default changes for entries or treatments.

## What an operator would notice

> Device-status uploads (for example Loop's status with insulin on board,
> carbs on board and predictions) are accepted up to the same size as
> glucose and treatment uploads, 50 MB by default, so a large batch is no
> longer refused. A new optional setting, UPLOAD_BODY_LIMIT, sets that size
> for all three. Not in a release yet.

## Who should review this, and why

maintainer, plus one reviewer who has not merged their own work here

## What was measured

**`node tools/queue/gates/upload-body-limits.js --bf 241 --ref claude/upload-body-limit-20261121`** &nbsp;·&nbsp; kind: `static`

The three bulk-upload routes take their JSON limit from body-limits (default
50mb) and device status no longer uses the 1 MB shared parser, on the fix
branch.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- HTTP behaviour is measured by tests/api.body-limits.test.js (needs
  MongoDB): 5 of 11 fail on dev 79144cbd0 (2 MB device status refused with
  413; a 256kb setting not enforced), 11 of 11 pass on 1820bae16. Not a
  queue gate because it needs a database.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-11-21: affected suites 342 passing / 1 pending / 0 failing on 1820bae16
(27 files, MongoDB 8.0 container, Node 22.23.4). Before the PR: merge
official/dev, full suite, tools/review/prcheck/prcheck.sh. Multitenant: the
tenant app reuses these route factories and its tenant env has no
uploadBodyLimit, so the process environment applies (read, not run on the
multitenant branch). The multitenant API v3 parser
(lib/api3/shared/jsonParser.js on official/workspace/multitenant-20261102)
stays at a hard-coded 50 MB.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-241` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
