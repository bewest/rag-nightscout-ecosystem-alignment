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

# Review packet — RT-PR-8730 (PR #8730)

**#8730 - Crowdin translation updates, carried into 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `crowdin_incoming` |
| base | `origin/dev@4f705217` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=RT-PR-8730` is the measurement |
| semver | `patch` |

## What this changes

Translations only: 32 files under translations/, +518/-454. Head f99c0e54, 85
commits behind dev; merges cleanly with dev 4f705217 and with #8758 (measured
2026-09-25).

## Why that semver

translation text only

## What an operator would notice

> Updated wording in the languages the Crowdin volunteers translate.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev refs/triage/pr-8730 >/dev/null`** &nbsp;·&nbsp; kind: `static`

#8730's head merges into origin/dev without conflict. Needs `git -C
externals/cgm-remote-monitor-official fetch official
pull/8730/head:refs/triage/pr-8730` first.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- No test reads the translation files' content. A broken JSON file would
  fail the language loader's tests, which the combined run covers once #8730
  is in it.

## Evidence

- [`docs/60-research/remedial/github-triage-2026-09-25.md`](../../docs/60-research/remedial/github-triage-2026-09-25.md)

## Notes carried on the item

Opened by the Crowdin integration (sulkaharo), last updated 2026-09-21.
Decided 2026-09-25 (maintainer): carry into 15.0.9. Translations changed after
it was opened are not in it.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-PR-8730` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
