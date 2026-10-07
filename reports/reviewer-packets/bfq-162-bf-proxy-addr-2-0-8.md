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

# Review packet — BFQ-162

**BF-162 - an explicit TRUST_PROXY address list reaches proxy-addr 2.0.7, inside
a critical advisory fixed in 2.0.8**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/proxy-addr-2.0.8` |
| base | `official/dev@1ad03e29` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-162` is the measurement |
| semver | `patch` |
| register entries | `BF-162` |

## What this changes

package.json and package-lock.json: proxy-addr ^2.0.7 -> 2.0.8 (direct
dependency, shared with Express 4.22.2's ~2.0.7); no code change.

## Why that semver

a patch-level dependency update

## What an operator would notice

> Sites that list their proxy addresses in TRUST_PROXY get a corrected
> address check; other sites see no change.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Read, not run: GHSA-jqcg-44mw-7w3h (proxy-addr >= 1.1.0, < 2.0.8); client-
  ip.js compileTrust passes an explicit address list to proxyaddr.compile. A
  gate would compile an affected trust entry with the locked proxy-addr and
  assert an unrelated IPv4 peer is not trusted: fails on 2.0.7, passes on
  2.0.8.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Filed 2026-10-06 from session -d4's re-measured npm audit (25 findings, 9
high, 1 critical; lockfile unchanged since run 021, the advisory database
grew). Not on 15.0.8 (no TRUST_PROXY; trust proxy is enabled for every hop).
2026-10-07 (maintainer): goes into 15.0.9. Branch bf/proxy-addr-2.0.8
7dd4f400, one commit on dev 1ad03e29, not pushed: package.json ^2.0.8 and the
lockfile's one entry (npm ls: one 2.0.8, deduplicated under Express); the
unrelated @types/tough-cookie "dev" flag npm 10.9.8 adds is left out. Measured
in-process: on 2.0.7, ::ffff:10.0.0.0/8 and ::/1 trust an unrelated IPv4
client's own X-Forwarded-For; 2.0.8 does not. New test in tests/client-
ip.test.js fails on 2.0.7 only. Full suite 3564/0/4 (Node 22.23.2, MongoDB
7.0.43, fresh database; dev 3563 plus 1). npm audit (npm 10.9.8): 25/9 high/1
critical on dev, 24/9/0 on the branch. PR body reports/phase0-pr-bodies/proxy-
addr-2.0.8.md. Merging it costs a run 022 and the #8598 re-approval.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-162` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
