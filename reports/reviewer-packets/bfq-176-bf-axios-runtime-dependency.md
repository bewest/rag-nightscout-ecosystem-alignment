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

# Review packet — BFQ-176 (PR #8834)

**BF-176 - axios is only a devDependency and lodash is undeclared, so a
production install of dev (16.0.0 line, cut 1 merged) stops at boot when
IMPORT_CONFIG is set**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/axios-runtime-dependency` |
| base | `official/dev@eb72a1d3` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-176` is the measurement |
| semver | `patch` |
| register entries | `BF-176` |

## What this changes

One commit 43ed462a on dev 04d435eb, package files and one test file only
(+53/-2). package.json moves axios from devDependencies to dependencies at the
same ^0.34.0 and declares lodash as exactly 4.18.1, the version its existing
override pins (the overrides block is unchanged). package-lock.json: the two
root entries, plus "dev": true on node_modules/@types/tough-cookie, which npm
sets when it recomputes the lockfile (TypeScript declarations only; its one
non-dev dependent is a peerDependency that legacy-peer-deps=true does not
follow; cut 1's lockfile already has it). Five tests in tests/dependency-
axios.test.js (+48). No runtime code changes. Full suite 3574/4/0 on Node
24.15.0 and MongoDB 7.0.43 (dev baseline 3569/4/0, plus the five tests).

## Why that semver

Packaging only: axios moves from devDependencies to dependencies at the same
version range and lodash is declared at the version already installed; no API,
setting or stored-data shape changes. On 15.0.x the production tree already
contains axios 0.34.0 and lodash 4.18.1 through other packages, so the
installed runtime set does not change.

## What an operator would notice

> IMPORT_CONFIG is an optional setting that tells Nightscout to load extra
> settings from a web address when it starts. In the planned 16.0.0 (not
> released; the development branch and its Docker image already have it), a
> site that uses IMPORT_CONFIG and is installed the usual production way
> (the official Docker image, Azure, or any install that leaves out
> development packages) would stop during startup with the message "Cannot
> find module 'axios'" and would not come up until IMPORT_CONFIG is removed.
> Sites without IMPORT_CONFIG are not affected. Nothing changes on 15.0.9 or
> earlier releases: they start and apply the imported settings normally.

## Who should review this, and why

maintainer

## What was measured

**`RUNTIME_REQUIRES_REF=bf/axios-runtime-dependency node tools/queue/gates/runtime-requires-declared.js`** &nbsp;·&nbsp; kind: `static`

every package that server code loads (server.js, bin/*.js and lib/ except the
browser-only lib/client, lib/report and lib/report_plugins) is declared under
dependencies on the fix branch, with webpack-dev-middleware and webpack-hot-
middleware allowed only inside lib/server/app.js's NODE_ENV === 'development'
block; red on v15.0.9, official/dev 04d435eb and cut 1 806ff2f0 (axios only a
devDependency, lodash undeclared)

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The boot itself is not a queue gate: it needs npm ci --omit=dev, MongoDB
  and a local config server (minutes). Run by hand 2026-10-22 on v15.0.9,
  cut 1 806ff2f0 and the fix branch 43ed462a, see the register's BF-176
  detail. cut 2's tools/validate-pruned-runtime.js (d660e272's message)
  boots the pruned tree with IMPORT_CONFIG in cut 2's CI.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-25, 17:28Z: the maintainer pushed bf/axios-runtime-dependency f3d73f43
and opened #8834 ("axios and lodash are runtime dependencies (IMPORT_CONFIG
boot crash on 16.0.0 dev)") against dev; open, checked with gh pr view 8834.
2026-10-25, later: measured by the BF-176 session (Node 24.22.1, npm 11.19.1,
MongoDB 7.0.43). Crash confirmed on dev eb72a1d3: with IMPORT_CONFIG set, the
Dockerfile's install commands and npm ci --omit=dev exit 1 with "Cannot find
module 'axios'" at bootevent.js:114; unset, both boot; full npm ci with it set
boots with the imported settings. bf/axios-runtime-dependency is now f3d73f43
(43ed462a plus a merge of dev eb72a1d3; 0 behind, 2 ahead, 3 files; not
pushed), where every arm boots with the settings applied. Tests with TZ=UTC:
branch 3384/3/0, dev 3379/3/0; tests/dependency-axios.test.js 30 passing, 4
failing with dev's package.json. runtime-requires-declared on dev: 41 checked,
2 failing (axios, lodash); on the branch 0 failing. The gate control gains dev
eb72a1d3 as a negative (ee7a3cb49, merged into this records branch). The
paragraph below said these were pending. 2026-10-25: the exposure moved from
cut 1 only to dev and the 16.0.0 line. #8828 (cut 1) merged into dev as
eb72a1d3 before this fix went to dev, so dev now carries the condition BF-176
predicted for cut 1: on eb72a1d3 package.json still lists axios ^0.34.0 only
under devDependencies and declares no lodash (read with git show
official/dev:package.json). No release carries it (ships_to_operators_today
stays false; 15.0.9 boots, see below). dev's push CI run 40211895500 published
the dev Docker image, so anyone running the dev image with IMPORT_CONFIG set
is exposed. A peer session is confirming the boot failure on eb72a1d3 and
merging dev into bf/axios-runtime-dependency; its measurements, the new branch
head and the PR number are pending and are not recorded here. The state stays
ready-to-push as a claim until that session reports. Filed 2026-10-22 from a
colleague's read of package.json, then reproduced. The read hypothesis was
that 15.0.x fails; it does not, because minimed-connect-to-nightscout depends
on axios and npm hoists that 0.34.0 copy to node_modules/axios in every
production install (npm ls axios --omit=dev). Cut 1 (RT-1, #8828, 806ff2f0)
removes the MiniMed bridge, and its lockfile then marks node_modules/axios
dev: true; with IMPORT_CONFIG set, npm ci --omit=dev and the Dockerfile's
commands both exit 1 at augmentSettings. Register §1b, kind (b). lodash is
covered by the same fix: lib/utils.js requires lodash/escape and lodash is not
declared. It is supplied transitively today by node-cache, jsonwebtoken
(through @parse/node-apn) and minimed-connect-to-nightscout on 15.0.9 and dev,
and by node-cache and jsonwebtoken on cut 1 (read, and verified with npm ls
lodash --omit=dev on both installs), so nothing fails today. Route
(2026-10-22): a PR to dev from bf/axios-runtime-dependency, and #8828 takes it
in its next catch-up merge of dev. The branch conflicts with 806ff2f0 in
package.json and package-lock.json (git merge-tree); on cut 1 the resolution
also drops the dev flag from node_modules/axios and node_modules/proxy-from-
env in the lockfile. Proved on cut 1 by hand: with the axios move applied to
806ff2f0, npm ci --omit=dev plus IMPORT_CONFIG boots and applies the imported
settings. Not pushed; PR body drafted outside the repository. Cut 2 already
moves axios (d660e272, "axios is a runtime dependency, at dev's ^0.34.0"),
found by its tools/validate-pruned-runtime.js. The widened gate on d660e272
still reports lodash undeclared and webpack a devDependency required inside
the development guard of lib/server/app.js (:340); both are for cut 2's next
catch-up, not for this item.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-176` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
