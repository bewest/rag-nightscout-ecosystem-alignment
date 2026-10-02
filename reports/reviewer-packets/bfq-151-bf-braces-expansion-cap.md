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

# Review packet — BFQ-151

**BF-151 - one /api/v1/times or /slice request can block the server for seconds
(brace expansion has no bound), for 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/braces-expansion-cap` |
| base | `official/dev@50bc1084` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-151` is the measurement |
| semver | `patch` |
| register entries | `BF-151` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/api/entries/index.js prep_patterns: refuse a prefix or pattern whose
expansion exceeds a fixed number of results, before expanding it, with a 400;
under the limit, unchanged. Tests beside the existing times/slice tests.

## Why that semver

an unbounded request is refused; every request within the limit answers as
before

## What an operator would notice

> A kind of request to two little-used API addresses could make Nightscout
> stop responding for several seconds. It is now refused. Nothing you see on
> your site changes.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official grep -q MAX_BRACE_PATTERNS bf/braces-expansion-cap -- lib/api/ent`** &nbsp;·&nbsp; kind: `static`

The branch's prep_patterns carries the cap (a presence check; RED on
origin/dev 50bc1084). The tests decide.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The measurement needs a booted server and is held outside version control
  while the defect is live on 15.0.8 (the report is private). 2026-10-01 on
  v15.0.8 and dev 3014f883, NODE_ENV= production: one request at 10^6
  results blocked the event loop 2.1 s; anonymous on readable, any read
  token under denied; on dev 50bc1084 a 10^7 request killed the process
  (heap OOM). The branch's own tests decide: on 185e003a (Node 22.23.2,
  MongoDB 7.0.43) 7 new tests in tests/api.entries.test.js, the 5 refusal
  tests fail with 50bc1084's lib/api/entries/index.js (2.7 s and 200, or
  500), full suite 3496/0/3 (dev 3489/0/3); 10^6 and 10^7 inputs answer 400
  in 1-3 ms with a concurrent status read unaffected.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-02: dev a143d507 (with #8793 and #8794) merged into the branch locally
as fdf88f4e, not pushed; fresh npm ci on the new lockfile; full suite 3532/0/4
(dev expected 3525 plus these 7); with a143d507's lib/api/entries/index.js the
5 refusal tests fail again. Decided 2026-10-01 (maintainer): fix for 15.0.9.
In RT-0's blocks_on. Branch bf/braces-expansion-cap 185e003a, one commit on
dev 50bc1084 (lib/api/entries/index.js +57/-2: count_patterns counts from
braces.parse without expanding, cap 2000; a whole day of minutes is 1440, the
largest documented example 192), not pushed. PR body: reports/phase0-pr-
bodies/braces-expansion-cap.md. Review notes: the counter reads braces 3.0.3's
parse tree (ranges, commas, invalid, dollar), so a braces upgrade must re-run
these tests; a single range over braces' own rangeLimit still answers 500 as
on dev. Disclosure: the tests necessarily build an input that expands past the
cap, so opening the PR publishes an easy trigger for 15.0.8; open it close to
the tag, as #8743 was handled.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-151` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
