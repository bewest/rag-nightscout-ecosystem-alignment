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

RE-GRADED ready-to-push -> needs-decision 2026-09-21, AND THE GATES DID NOT
CATCH IT. All five still pass. What changed is outside every question they
ask: upstream `dev` has independently declared itself 0.0.14. MEASURED.
official/dev moved 6dfc4f0 -> fe51c6d today and carries e231600 "Bump version
to 0.0.14" (Andy Low), so `git show official/dev:package.json` and `git show
release/v0.0.14:package.json` BOTH say 0.0.14 for two different trees.
release/v0.0.14 is 11 ahead of dev and 13 behind it; the 13 are the Glooko
work merged as PR #71, the CI restore as #72, and the main->dev merge #69. A
trial merge of dev into release/v0.0.14 CONFLICTS in six files:
.github/workflows/test.yml (added in both), README.md, index.js,
lib/machines/cycle.js, lib/outputs/internal.js, lib/sources/glooko/convert.js
and lib/sources/glooko/index.js. SO PUSHING THE PREPARED TAG WOULD MINT A
v0.0.14 THAT IS NOT DEV'S 0.0.14, and the tarball P0-PIN pins would omit the
Glooko fixes that upstream believes are in this version. That is not a
mechanical reconciliation and it is not the programme's call to make alone,
which is what moves this out of ready-to-push. Three shapes, none obviously
right: reconcile release/v0.0.14 onto dev and cut the tag from there; abandon
the prepared branch and let upstream tag dev; or cut ours as 0.0.15 and leave
0.0.14 to dev. RULE 0 IS INTACT - nothing was pushed, and the "tag is not on
origin" gate below still passes. The remote's newest tag is still v0.0.13.
PRIOR MEASUREMENT: 11 commits, 29 files, +1362/-312, of which 887 lines are
new test files. b394411 FAST-FORWARDS to 649a7de. Both still true.

## Why that semver

see P0-F. GT4 argues the version should be 0.1.0; the tag as cut says 0.0.14.
UNRESOLVED and deliberately left visible.

## What an operator would notice

> A new version of the CGM connector. See P0-F for what changes in
> behaviour.

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

ADDED 2026-09-21, AND IT IS RED, which is the point - five green gates
described a release that had been overtaken and none of them could say so. The
release branch must contain everything on upstream dev, or the tag names a
tree that is missing work upstream already considers released. Red today by 13
commits. This is the gate that should have existed before the divergence, not
after it.

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
debug-logging narrowing that dev's pin has and the three log-redaction fixes
that cut 4's pin has. GT4 found the two mitigations split across the two
release trains. STILL TRUE, and it is why abandoning the branch outright is
not obviously the right shape either: dev at fe51c6d does NOT carry c1cce2a,
the backoff-and-jitter commit, because PR #68 is still open. Whatever is
decided has to keep all seven. WHAT THIS COST, written down because the lesson
is cheaper than the incident: this item sat at ready-to-push for five days
with a complete set of passing gates, and every one of them measured the
prepared artefact against itself - tag type, tag target, version string, fast-
forward from the previous tag. None measured it against the world it was going
to be pushed into. The gate added above is the missing question and it was one
line.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-TAG` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `74fc6619`.*
