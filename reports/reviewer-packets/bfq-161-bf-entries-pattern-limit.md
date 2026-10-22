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

# Review packet — BFQ-161

**BF-161 - braces 3.0.3 (direct dependency) is inside a stack-exhaustion
advisory with no fixed release, reachable from the entries pattern routes**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/entries-pattern-limit` |
| base | `official/dev@04d435eb` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-161` is the measurement |
| semver | `patch` |
| register entries | `BF-161` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/api/entries/index.js prep_patterns / count_patterns: a nesting-depth (or
input-length) limit checked before braces.parse and expand.

## Why that semver

an input limit on three read routes

## What an operator would notice

> A malformed request to the entries pattern routes gets an error reply
> instead of being processed; the site keeps running either way.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor official/dev bf/entries-pattern-limit`** &nbsp;·&nbsp; kind: `static`

the branch contains official/dev (04d435eb on 2026-10-21), so it can be pushed
without a further merge; goes red when dev moves ahead

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Read, not run: GHSA-vfj7-8cjw-p6xm (braces <= 3.0.3, no patched version);
  the routes call braces.parse and expand synchronously in Express
  middleware, so the RangeError is caught and answered 500. A gate would
  send a nested pattern within the count limit and assert a 400 before
  parsing, and that the server still answers afterwards.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-21, later: head d2c4df9f adds 9 intended-use tests from the
maintainer's public gist dbe590ab (/times echo forms and /times JSON and CSV);
the deepest real use nests 1 level, so the limit of 10 keeps a wide margin;
full suite 3585/0/4. Route decided by the maintainer: a draft security
advisory covers this defect, so the fix goes through that advisory's private
fork and is published with the release that carries it, not as a public PR.
2026-10-21: bf/entries-pattern-limit fe1f6220 on dev 04d435eb: a nesting-depth
limit of 10, answered 400 before braces parses or expands the pattern; full
suite 3576/0/4; break-it ok; patch; not pushed. The limit value 10 awaits the
maintainer's confirmation. Filed 2026-10-06 from session -d4's run 021 npm
audit on dev 1ad03e29 (15 findings, 7 high, against 10 and 2 on 2026-10-02:
new advisories for braces, @parse/node-apn and eslint-webpack-plugin). Graded
low by -d4 from the code, same class as BF-154. 2026-10-06 (maintainer): a
known issue in 15.0.9, named in the release notes; the nesting-depth limit is
after 15.0.9. Mechanism only in public records (live on 15.0.8).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-161` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
