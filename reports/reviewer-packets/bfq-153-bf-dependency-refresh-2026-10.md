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

# Review packet — BFQ-153 (PR #8794)

**BF-153 - dependency advisories published after the 2026-09-27 triage (BF-147
style refresh)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/dependency-refresh-2026-10` |
| base | `official/dev@50bc1084` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-153` is the measurement |
| semver | `patch` |
| register entries | `BF-153` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

package.json overrides (ip-address, fast-uri, brace-expansion, the axios
entries under minimed-connect-to-nightscout), the axios devDependency, and
package-lock.json (webpack-dev-middleware, dompurify); tests/dependency-
overrides.test.js. moment is left at 2.30.1 by decision.

## Why that semver

patch and minor dependency versions; no behaviour change intended

## What an operator would notice

> No change in how Nightscout works. Updated libraries clear published
> security notices; most of them are build and test tools.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official show bf/dependency-refresh-2026-10:package.json | grep -qE 'ip-ad`** &nbsp;·&nbsp; kind: `static`

The branch's overrides carry the fixed ip-address (a presence check;
tests/dependency-overrides.test.js on the installed tree decides).

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- npm audit depends on the advisory database on the day it runs, so it is a
  measurement, not a gate. 2026-10-01, npm 11.12.1, --package-lock-only (a
  count of packages with a finding, parents counted again): dev 50bc1084 20
  (4 high), the branch 8 (0 high); --omit=dev 16 -> 6. The 8 left are the
  2026-09-27 set of 7 plus moment, held by decision. Measured on 22d82889 in
  externals/work/crm-bf153 (Node 22.23.2, MongoDB 7.0.43): full suite
  3512/0/4 (dev 3489/0/3; the added pending is the connector's own axios
  1.20.0 copy, outside the advisory range, which the new floor check skips);
  the 27 new or raised dependency checks fail on dev's installed tree and
  pass here; test:dependencies 345/0/1; npm ci on Node 20.20.0, 22.23.2,
  24.20.0 and the npm 12 job; production bundle byte-identical (7 files);
  IMPORT_CONFIG fetched and applied as on dev with axios 0.34.0.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`releases/cgm-remote-monitor-15.0.9/contents.md`](../../releases/cgm-remote-monitor-15.0.9/contents.md)

## Notes carried on the item

2026-10-02: pushed and opened as #8794 by the maintainer (head 7cb8d0bc =
22d82889 plus a merge of dev 839a1565, which brings only #8793 and touches no
package file); taken into 15.0.9, so in RT-0's blocks_on. Dependabot #8787 and
#8789 (against master) to be closed with a pointer once it merges. 2026-10-01
(maintainer): prepare it; whether it goes into 15.0.9 is decided on the
measured result. moment stays at 2.30.1 (2026-10-01): no request input reaches
moment.locale on dev (BF-31), and 2.31.0 changes parsing and locale display
output. Not in RT-0's blocks_on until decided. Branch bf/dependency-
refresh-2026-10 22d82889 (one commit on 50bc1084), 26 lockfile version
changes, all patch or minor; @types/tough-cookie's dev flag, which npm 10 and
11 both flip on dev's own package.json, is kept as on dev. Not pushed. PR
body: reports/phase0-pr-bodies/dependency-refresh-2026-10.md.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-153` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
