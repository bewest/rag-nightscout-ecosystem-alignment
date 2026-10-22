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

# Review packet — BFQ-176

**BF-176 - axios is declared only as a devDependency, so cut 1's production
install stops at boot when IMPORT_CONFIG is set**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/axios-runtime-dependency` |
| base | `official/dev@04d435eb` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-176` is the measurement |
| semver | `patch` |
| register entries | `BF-176` |

## What this changes

One commit 366c6ea4 on dev 04d435eb: package.json moves axios from
devDependencies to dependencies at the same ^0.34.0, package-lock.json moves
only the root entries (+1/-1 each), and three tests in tests/dependency-
axios.test.js (+34) check that every package lib/server/bootevent.js loads is
under dependencies. No runtime code changes. Full suite 3572/4/0 on Node
24.15.0 and MongoDB 7.0.43 (dev baseline 3569/4/0, plus the three tests).

## Why that semver

Packaging only: axios moves from devDependencies to dependencies at the same
version range; no API, setting or stored-data shape changes. On 15.0.x the
production tree already contains axios 0.34.0 through minimed-connect-to-
nightscout, so the installed set does not change.

## What an operator would notice

> IMPORT_CONFIG is an optional setting that tells Nightscout to load extra
> settings from a web address when it starts. In the planned 16.0.0 (cut 1,
> not released), a site that uses IMPORT_CONFIG and is installed the usual
> production way (the official Docker image, Azure, or any install that
> leaves out development packages) would stop during startup with the
> message "Cannot find module 'axios'" and would not come up until
> IMPORT_CONFIG is removed. Sites without IMPORT_CONFIG are not affected.
> Nothing changes on 15.0.9 or earlier releases: they start and apply the
> imported settings normally.

## Who should review this, and why

maintainer

## What was measured

**`BOOT_DEPS_REF=bf/axios-runtime-dependency node tools/queue/gates/boot-requires-runtime-deps.js`** &nbsp;·&nbsp; kind: `static`

every package lib/server/bootevent.js loads (axios, bootevent, moment-
timezone, nightscout-connect, semver) is declared under dependencies on the
fix branch; red on v15.0.9, official/dev 04d435eb and cut 1 806ff2f0, where
axios is only a devDependency

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The boot itself is not a queue gate: it needs npm ci --omit=dev, MongoDB
  and a local config server (minutes). Run by hand 2026-10-22, see the
  register's BF-176 detail. cut 2's tools/validate-pruned-runtime.js
  (d660e272's message) boots the pruned tree with IMPORT_CONFIG in cut 2's
  CI.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Filed 2026-10-22 from a colleague's read of package.json, then reproduced. The
read hypothesis was that 15.0.x fails; it does not, because minimed-connect-
to-nightscout depends on axios and npm hoists that 0.34.0 copy to
node_modules/axios in every production install (npm ls axios --omit=dev). Cut
1 (RT-1, #8828, 806ff2f0) removes the MiniMed bridge, and its lockfile then
marks node_modules/axios dev: true; with IMPORT_CONFIG set, npm ci --omit=dev
and the Dockerfile's commands both exit 1 at augmentSettings. Register §1b,
kind (b). Cut 2 already makes this move (d660e272, "axios is a runtime
dependency, at dev's ^0.34.0"), found there by tools/validate-pruned-
runtime.js; cut 2 lands after cut 1, so 16.0.0 as cut 1 alone would carry the
defect. The fix branch is local and not pushed; it conflicts with 806ff2f0 in
package.json and package-lock.json (git merge-tree), and on cut 1 the same
move also drops the dev flag from node_modules/axios and node_modules/proxy-
from-env in the lockfile. Open choice for the maintainer: push this to dev and
resolve in #8828's next catch-up, or make the move inside #8828 and drop this
branch. Proved on cut 1 by hand: with the move applied to 806ff2f0, npm ci
--omit=dev plus IMPORT_CONFIG boots and applies the imported settings. PR body
drafted outside the repository. Related, not filed: lib/utils.js requires
lodash/escape and lodash is not declared at all; it reaches the production
tree through node-cache and @parse/node-apn (jsonwebtoken) on both 15.0.9 and
cut 1, so nothing fails today. Read, not run.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-176` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
