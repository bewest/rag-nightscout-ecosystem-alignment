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

# Review packet — BFQ-225 (PR #8888)

**BF-225 - socket re-sends that #8877 changed from one stored treatment to two
(v3-then-socket documented; UUID _id cases not)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-bf225-socket-duplicate` |
| base | `official/dev@604de1cb` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-225` is the measurement |
| semver | `patch` |
| register entries | `BF-225` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/websocket.js processSingleDbAdd, the socket similar match changed
by #8877 (cf3d4b8f): a stored treatment's identifier now keeps a re-send
without one from matching it.

## Why that semver

restores 15.0.9's single record for an identifier-less socket re-send

## What an operator would notice

> An app that re-sends a treatment over the live connection without an
> identifier could create a duplicate insulin or carb entry on the site, so
> caregivers would see doubled IOB or COB. Not in any released version
> (15.0.9 stores one record); on dev since #8877.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official fetch -q official pull/8888/head && git -C externals/cgm-remote-m`** &nbsp;·&nbsp; kind: `network`

#8888's head on GitHub contains BF-225 fix B b6e3d739; fix C (2079501a) ships
in the compatibility follow-up PR; replace with official/dev ancestry once
merged

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-31 night: fix B opened by the maintainer as PR #8888 (dev <-
bf/16.0.0-bf225-socket-duplicate, head b6e3d739); fix C on feat/id-compat-
restore-ab. 2026-10-31 night (session -4e): fix built, PR pending. B:
bf/16.0.0-bf225-socket-duplicate b6e3d739, one commit on dev 604de1cb (0
behind), push commands with the maintainer: matrix exactly the 1 predicted
cell (treatments x v3 x ws to one record, equal to v15.0.9 on stored state);
break-it red on the new test only; revert gives the dev pin; tiers 5591/0/3 on
Node 22.23.4 and 24.22.1; lint 0 errors; a different device or no numeric date
still gives a second record (tests); BF-209 test unchanged and green. C:
feat/id-first-s6c-uuid-socket 2079501a on #8879 2d79d30b: 4 predicted cells
(idf-uuidid-same and -time, v1/in-process then socket) to one record, replaced
under compatibility B; --uuid-off 0 cells; tiers 5966/0/3; ships in the
compatibility follow-up PR (order C, then B, then A). B and C composed: 5
cells as predicted, all three BF-225 cells one record. 2026-10-31 later: the
maintainer chose B and C (2026-10-31, via session -4e): B, on dev (branch
bf/16.0.0-bf225-socket-duplicate): the socket similar match also accepts a
stored treatment whose identifier equals the one API v3 computes for the
incoming body (device + date + eventType), fixing treatments x v3 x ws, while
BF-209's case (an upload without identity 1 s after an AndroidAPS v3 record)
still keeps both; C, on #8879 (a small rule commit): a UUID _id on a socket
dbAdd treatment counts as its identifier, as v1's UUID handling does, so the
two idf-uuidid-same cells become one record, replaced under decision B.
Rejected: A (full 15.0.9 revert; brings back BF-209's lost treatment) and D
(keep #8877's choice). Being built by -4e with full gates. 2026-10-31
correction (session -4e): the treatments x v3 x ws cell was a documented,
intended change in #8877 (PR body line 29, its matrix run line 72); the idf-
uuidid-same cells are undocumented. The smallest revert breaks BF-209's guard
test, so the fix scope (duplicated vs possibly lost treatment) is pending the
maintainer's choice. 2026-10-31 (maintainer, via session -4e): fix in 16.0.0.
Being fixed by -4e on bf/16.0.0-bf225-socket-duplicate off official/dev (test
first, 3-cell matrix prediction, break-it, revert, tiers, lint; trial merge
into #8879 2d79d30b). 2026-10-31: filed by session -4e (bisected to cf3d4b8f
over 12 matrix pins). 16.0.0 blocker candidate; the maintainer decides whether
it blocks the tag. Data: session -4e's compat measurement.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-225` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
