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

# Review packet — BFQ-163 (PR #8835)

**BF-163 - compression 1.8.1 (every response) is inside a high memory-leak
advisory fixed in 1.8.2**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `deps/16.0.0-security-refresh` |
| base | `official/dev@eb72a1d3` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-163` is the measurement |
| semver | `patch` |
| register entries | `BF-163` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

package-lock.json only: compression 1.8.1 -> 1.8.2 (package.json's ^1.7.4
already allows it; 1.8.2 adds destroy, already in the tree).

## Why that semver

a patch-level dependency update

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Read, not run: GHSA-vc2v-76pw-4v95 (compression < 1.8.2); app.js:235
  compresses every response. A gate would assert the locked version is 1.8.2
  or later (npm ls compression).

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-25, 17:28Z: the maintainer pushed deps/16.0.0-security-refresh
341b843a and opened #8835 ("Update compression, follow-redirects and source-
map-js") against dev; open, checked with gh pr view 8835. The follow-redirects
and source-map-js updates have no register entry or item of their own and are
tracked here. 2026-10-25, later: deps/16.0.0-security-refresh 341b843a (in
externals/work/crm-deps-1600; 0 behind dev eb72a1d3, 3 ahead, merges cleanly):
feb3944c compression 1.8.2 (package.json range raised to ^1.8.2), ad458fa0
follow-redirects 1.16.1 (an override pin), 341b843a source-map-js 1.2.2; only
those three lockfile entries change. Tests (Node 24.22.1, npm 11.19.1, MongoDB
7.0.43): npm test 3378 passing / 3 pending / 1 failing on both dev eb72a1d3
and the branch, the one failure the time-zone-dependent glucosedistribution
case (RT-TEST-TZ-GLUCOSEDIST); browser suite Chromium 455 passing on both. npm
audit, 2026-10-25 17:13Z: dev 23 findings (8 high, 1 critical), the branch 18
(3 high, 1 critical); with --omit=dev 16 -> 11. A reading a minute earlier
gave 20 on dev, from the advisory service, not the tree. sanitize-html stays
at 2.17.5, pending a maintainer decision: 2.17.6 and later need the
htmlparser2 12, domhandler 6, domutils 4, dom-serializer 3 and domelementtype
3 majors, and 1 of 35 purifier inputs is stored differently (a malformed
textarea sequence is stored as an img element with src x instead of the empty
string; the event handler is still stripped). The Node 20 reason for the pin
in lib/server/purifier.js:38 is stale under the 16.0.0 floor. The three
sanitize-html advisories the 2026-10-21 triage names stay open. All figures
are that session's; not re-run here. sanitize-html 2.18 is no longer part of
this branch: it goes to dev as its own PR for 16.0.0 from deps/sanitize-
html-2.18 (in flight in a peer session; the maintainer asks for it to be
integrated as quickly as possible). 2026-10-25: session -40's
wip/15.0.10-lockfile-refresh (dbc4519f, compression, follow-redirects and
source-map-js on dev 04d435eb) was never pushed, and is now 182 commits behind
dev. A peer session is redoing the refresh on dev eb72a1d3 as
deps/16.0.0-security-refresh (local, not pushed), with sanitize-html 2.18.x in
scope, which the 16.0.0 floor ^22.23.4 || ^24.22.1 || >=26.12.1 permits
(2.18.0 needs Node >=22.12; dev locks 2.17.5). Its result is the paragraph
above. 2026-10-21: peer session -40 is preparing wip/15.0.10-lockfile-refresh
(worktree externals/work/crm-1510-deps), a lockfile refresh for compression,
follow-redirects and source-map-js on the next cycle's dev; this item's state
is left to that session. Dependabot #8817 (compression 1.8.2, against master)
was closed by AndyLow91 on 2026-10-21. None of cuts 1-4 or #8605 updates
compression (npm audit 2026-10-21). Filed 2026-10-07 from session -d4's npm
audit on dev 43289dde. Decision 2026-10-07 (maintainer): a known issue in
15.0.9, named in the release notes; the update goes early in the modernization
releases (the first cut after 15.0.9, RT-1, or the dependency refresh that
precedes it).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-163` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
