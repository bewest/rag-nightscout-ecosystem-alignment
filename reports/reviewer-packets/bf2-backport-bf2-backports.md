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

# Review packet — BF2-BACKPORT

**Which modernization-only security commits fix a defect that dev has**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf2/backports` |
| base | `origin/dev@74fc6619` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BF2-BACKPORT` is the measurement |
| semver | `n/a` |

## What this changes

Six candidate commits on chore/nightscout-modernization b1bdaca0 - 31c354d8,
d3ac8026, 973a2849, 71c42c9a, d48be5e5, ad4a8cd5. Only 31c354d8 cherry-picks
cleanly onto origin/dev.

## Why that semver

triage; each confirmed backport is classified on its own branch

## Who should review this, and why

SECURITY for anything that reproduces; maintainer for the triage.

## What was measured

**`grep -q "^## Verdicts" docs/60-research/remedial/modernization-backport-triage-2026-09-22.md`** &nbsp;·&nbsp; kind: `static`

The triage exists. It must carry, per commit, a reproduction on dev and a
control.

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf2/backports >/dev/null`** &nbsp;·&nbsp; kind: `static`

The two backports merge into origin/dev with no conflict.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Whether each commit fixes a live defect is established by running a probe
  on dev, not by reading the diff. The probes live with the triage.

## Evidence

- [`docs/30-design/remedial/backfix-2-plan-2026-09-22.md`](../../docs/30-design/remedial/backfix-2-plan-2026-09-22.md)

## Notes carried on the item

DECIDED 2026-09-23 (maintainer) - the two backports (9c50788e, b5038500) move
INTO 15.0.9 rather than backfix 2, because their fix code is already public on
the modernization branch and 15.0.8 users otherwise wait a release. The two
unbuilt findings (status credential in the URL, IMPORT_CONFIG diagnostics)
stay follow-ups. MEASURED 2026-09-22 - 11 candidates (6 named + 5 from a
path/content sweep). DEFECT-ON-DEV and live on 15.0.8: 31c354d8 (alarm socket
logs the submitted credential), d3ac8026 (a per-collection read grant not
checked on two shared routes; bites scoped-token installs under denied),
973a2849 (status credential in the URL), 8458f39e (IMPORT_CONFIG diagnostics).
d48be5e5 is real but not security. 71c42c9a not a defect; Helmet pair and
479a6a4d/924aa8d7 not on dev; f2ebd7d4 unsettled. bf2/backports carries
9c50788e and b5038500 (code verbatim, tests adapted where dev's socket
differs); suite on Node 22.23.2 - dev 2386/0/3, branch 2398/0/3. Control re-
run by the coordinator - with dev's lib the two new test files fail 7 of 12.
Register entries are pending id allocation. Backports carry the modernization
commit's content unchanged (cherry-pick -x) so the later cut rebase sees
agreement, not a second implementation.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BF2-BACKPORT` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
