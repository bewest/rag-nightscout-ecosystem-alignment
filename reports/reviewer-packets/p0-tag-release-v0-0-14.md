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
| claimed state | `ready-to-push` — a claim; `make queue-status ID=P0-TAG` is the measurement |
| semver | `minor` |
| register entries | `BF-08`, `BF-34` |

## What this changes

11 commits, 29 files, +1362/-312, of which 887 lines are new test files.
b394411 FAST-FORWARDS to 649a7de.

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
release trains.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-TAG` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `59430336`.*
