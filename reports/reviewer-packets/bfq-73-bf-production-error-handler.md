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

# Review packet — BFQ-73

**BF-73 - error responses carry a stack trace and server paths in production,
for 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/production-error-handler` |
| base | `official/dev@50bc1084` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-73` is the measurement |
| semver | `patch` |
| register entries | `BF-73` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/app.js: errorhandler only when NODE_ENV is development; otherwise a
final handler that keeps the status, sends a short message without stack or
paths, and logs the full error. Tests that boot the app.

## Why that semver

error replies keep their status and message and lose the stack trace

## What an operator would notice

> When a request fails, Nightscout's error reply no longer includes
> technical details about where it is installed. The details are still
> written to the server log.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official cat-file -e bf/production-error-handler:lib/server/error-handler.`** &nbsp;·&nbsp; kind: `static`

The branch carries the production error handler (a presence check; RED on
origin/dev 50bc1084). The tests decide.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured 2026-10-01 on v15.0.8 and dev 3014f883 (NODE_ENV= production,
  readable and denied): a malformed body answers 400 with 10 stack frames
  and the install path, before any auth check. The branch's own tests
  decide: on dc64e82d (Node 22.23.2, MongoDB 7.0.43) tests/error-
  handler.test.js 13 cases; the 4 that boot the app fail with 50bc1084's
  lib/server/app.js (stack in JSON, HTML and text); full suite 3502/0/3 on a
  fresh database (dev 3489/0/3). Live, NODE_ENV=production and
  AUTH_DEFAULT_ROLES=denied: a malformed body answers 400
  {"error":{"message":"Unexpected end of JSON input", "status":400}}, no
  stack.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Decided 2026-10-01 (maintainer): fix for 15.0.9; this settles the BF-73 half
of ADV-XSS-META's decision. In RT-0's blocks_on. Branch bf/production-error-
handler dc64e82d, one commit on dev 50bc1084 (new lib/server/error-handler.js,
app.js -5/+3, tests), not pushed. PR body: reports/phase0-pr-
bodies/production-error-handler.md. Operator-visible for the release notes:
with NODE_ENV unset (some hosts), error pages also stop showing the stack; it
is in the server log. A 4xx an app path raises without err.expose now answers
with the standard reason phrase instead of its own message. Follow-up, not in
this branch: the v1 'Mongo Error' / 'Query Error' replies carry the driver's
error text (database host and port when unreachable).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-73` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
