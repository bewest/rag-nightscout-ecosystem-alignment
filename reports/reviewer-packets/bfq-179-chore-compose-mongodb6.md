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

# Review packet — BFQ-179 (PR #8844)

**BF-179 - postinstall runs webpack, now a devDependency, so a production
install of dev fails (dev b29f1bf7, cut 2)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `chore/compose-mongodb6` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-179` is the measurement |
| semver | `patch` |
| register entries | `BF-179` |

## What this changes

package.json scripts.postinstall (:47 on dev b29f1bf7), and possibly the build
and packaging path if the prebuilt bundle is shipped instead. Install-time
only; no runtime code.

## Why that semver

packaging and install scripts only; no API, setting or stored-data change

## What an operator would notice

> Not in any release. On the development branch (dev), installing Nightscout
> without its development packages (for example with npm ci --omit=dev, npm
> install --production or NODE_ENV=production) fails with "webpack: not
> found", so the site cannot be installed that way. The official Docker
> image and the Azure deploy script install the development packages first
> and are not affected. 15.0.9 installs normally.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced 2026-10-25 by hand (Node v22.23.4): npm ci --omit=dev on dev
  b29f1bf7 exits 127 "sh: 1: webpack: not found", on v15.0.9 c6a0d8ed exits
  0 (control). A full install takes minutes and needs the network, so it is
  not a queue gate. A static gate would read official/dev's package.json and
  fail while postinstall runs webpack unguarded with webpack outside
  dependencies.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-25: cherry-picked onto cut 3 as 200c1361 and in PR #8844 to dev
(session -f8's cut 3, chore/compose-mongodb6, head 200c1361). 2026-10-25:
fixed as 1cf70838 on local bf/179-omit-dev-install (one commit on dev
b29f1bf7, not pushed); to be cherry-picked onto cut 3 by session -f8.
postinstall runs bin/postinstall.js: build when the tools are installed, keep
an existing bundle with a warning when they are not, otherwise exit 1 naming
npm ci --include=dev then npm prune --omit=dev --ignore-scripts. Measured
(lane): npm ci --omit=dev exits 1 with that message; npm ci builds the 16
bundle files byte-identical to dev's; docker build gives the same bundle.
Decisions for the maintainer: keep-prebuilt vs always fail, and the 16.0.0
release-note line. The boot error with no bundle at all is BF-188. Filed
2026-10-25 by session f4 (register §1b, kind b: a defect in a release-train
cut). Cut 2 (#8837) moved webpack to devDependencies; postinstall still runs
it. Reach of the first-party Dockerfile and bin/azure-deploy.sh is read (they
run npm ci --include=dev, then npm prune --omit=dev --ignore-scripts). Fix
direction, UNVERIFIED: guard postinstall, or ship the prebuilt bundle.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-179` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
