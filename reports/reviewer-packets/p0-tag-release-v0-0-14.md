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

# Review packet — P0-TAG

**nightscout-connect release/v0.0.14 and tag - prepared, needs a human push**

| | |
|---|---|
| repository | `nightscout-connect` |
| branch | `release/v0.0.14` |
| base | `v0.0.13@b394411` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=P0-TAG` is the measurement |
| semver | `minor` |
| register entries | `BF-08`, `BF-34` |

## What this changes

Two candidate 0.0.14s exist. Measured 2026-09-22 against connector
official/dev 8e26786: official/dev's package.json says 0.0.14 (bumped upstream
in e231600), and the programme's local, unpushed annotated tag v0.0.14 points
at release/v0.0.14 649a7de, whose package.json also says 0.0.14 - two
different trees with one version. `git rev-list --left-right --count
official/dev...release/v0.0.14` = 24 behind / 11 ahead. The 24 include
LibreLinkUp v4 (PR #73), the Glooko work (#71), the connector regression-CI
restore (#72) and the main->dev merge (#69). `git merge-tree --write-tree
official/dev release/v0.0.14` conflicts in 11 files at 8e26786:
.github/workflows/test.yml (added in both), index.js, lib/builder.js,
lib/machines/{cycle,fetch,poller,session}.js, lib/outputs/internal.js,
lib/sources/glooko/{convert,index}.js and lib/sources/librelinkup.js. Pushing
the prepared tag would therefore mint a v0.0.14 that is not dev's 0.0.14, and
the tarball P0-PIN pins would omit work upstream considers part of that
version. That is a release-content decision, not a mechanical reconciliation.
RECOMMENDED 2026-09-22, after upstream opened its own 0.0.14 release as
connector PR #70 (dev -> main, head 8e26786, with connectivity fixes the
maintainer reports include confirmed Dexcom access): retire the local tag and
land its content upstream, where it already exists as PRs - #64 (credential-
safe logging plus the BF-85 CareLink zero filter; rebased 2026-09-22, merges
cleanly), #67 (debug opt-in and the logger that reads CONNECT_DEBUG; conflicts
in 8 files), #68 (retry/jitter; conflicts in 11), #66. #64 and #67 must be in
upstream 0.0.14 before cgm-remote-monitor pins it: 8e26786 alone logs CareLink
login responses and Dexcom error bodies unconditionally (BF-42/43 again) and
ignores CONNECT_DEBUG. See release-readiness-15.0.9 §5.2. Nothing has been
pushed; the remote's newest tag is v0.0.13. The prepared release itself: 11
commits, 29 files, +1362/-312, of which 887 lines are new test files; b394411
fast-forwards to 649a7de.

## Why that semver

see P0-F. GT4 argues the version should be 0.1.0; the prepared tag says
0.0.14, and upstream dev has independently declared 0.0.14. Unresolved.

## What an operator would notice

> A new version of the CGM connector, the part of Nightscout that fetches
> readings from a CGM vendor's online service. See P0-F for what changes in
> behaviour. Nothing reaches anyone until the connector version is decided,
> tagged, and a Nightscout release is updated to use it.

## Who should review this, and why

maintainer - pushing the tag is the deliberate human act; the connector
repository has no release workflow, so the tag publishes nothing by itself

## What was measured

**`git -C externals/nightscout-connect merge-base --is-ancestor v0.0.13 release/v0.0.14`** &nbsp;·&nbsp; kind: `static`

v0.0.13 fast-forwards to the release - no divergence to reconcile

**`test "$(git -C externals/nightscout-connect cat-file -t v0.0.14)" = tag`** &nbsp;·&nbsp; kind: `static`

v0.0.14 is an ANNOTATED tag, not a lightweight one

**`test "$(git -C externals/nightscout-connect rev-parse v0.0.14^{commit})" = "$(git -C externals/nightscout-conn`** &nbsp;·&nbsp; kind: `static`

the tag points at the release branch tip

**`test "$(git -C externals/nightscout-connect show release/v0.0.14:package.json | python3 -c 'import json,sys; p`** &nbsp;·&nbsp; kind: `static`

package.json version matches the tag

**`git -C externals/nightscout-connect ls-remote --tags origin v0.0.14 | grep -q . && exit 1 || exit 0`** &nbsp;·&nbsp; kind: `network`

RULE 0. This gate PASSES only while the tag is NOT on origin. It is the
machine-checkable form of "nothing has been pushed". Read-only.

**`git -C externals/nightscout-connect merge-base --is-ancestor official/dev release/v0.0.14`** &nbsp;·&nbsp; kind: `static`

The release branch must contain everything on upstream dev, or the tag names a
tree missing work upstream already considers released. RED: release/v0.0.14 is
24 commits behind official/dev 8e26786 (2026-09-22). The other five gates
measure the prepared artefact against itself - tag type, tag target, version
string, fast-forward from the previous tag; this is the one that measures it
against the tree it would be pushed into.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Whether all seven connector commits are the RIGHT content for a release is
  a release-content decision, not a mechanical bump, and it is the
  maintainer's. Nothing can gate it.

## Blocked on

`P0-F`

## Evidence

- [`docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`](../../docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md)

## Notes carried on the item

v0.0.14 is the FIRST ref carrying all seven connector commits - both the
debug-logging narrowing that cgm-remote-monitor dev's pin (234d47c, connector
PR #67, open) has and the three log-redaction fixes that cut 4's pin has. GT4
found the two mitigations split across the two release trains. That is why
abandoning the branch outright is not obviously the right shape either:
connector dev at 8e26786 does NOT carry c1cce2a, the backoff-and-jitter
commit, because PR #68 is still open. Whatever is decided has to keep all
seven.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-TAG` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
