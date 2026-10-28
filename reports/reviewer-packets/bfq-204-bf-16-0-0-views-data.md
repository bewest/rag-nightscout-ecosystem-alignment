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

# Review packet — BFQ-204

**BF-204 - API v2 data-snapshot route returns the live 48 hours, not data framed
at the requested time**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-views-data` |
| base | `official/dev@db3b9e4e` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-204` is the measurement |
| semver | `patch` |
| register entries | `BF-204` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/data/endpoints.js and the cache merge in lib/data/dataloader.js
(insertDataRef).

## Why that semver

a read endpoint starts answering what it documents

## What an operator would notice

> A report or tool asking Nightscout for how things looked at an earlier
> time gets the current last two days instead, with no warning.

## Who should review this, and why

maintainer

## What was measured

**`sh tools/queue/gates/bf204-207-views-data.sh tests/data.ddata-at.test.js`** &nbsp;·&nbsp; kind: `unit`

Runs tests/data.ddata-at.test.js from bf/16.0.0-views-data (git archive)
twice: as it is, where it must pass, and with lib/ at dev db3b9e4e, where it
must fail on assertions only. It checks a past frame with a populated live
cache: nothing in the answer newer than the requested time, and the cache
unchanged; with dev's lib/ it fails with readings dated after that time (1 of
6). Needs node_modules installed at the fix ref (default the
externals/work/crm-bf-views worktree); otherwise UNMEASURED. Measured
2026-10-27 by session -65: met. Controls: the same lib/ on both sides reports
NOT MET; the official clone's older node_modules reports UNMEASURED.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-27: fixed on local bf/16.0.0-views-data by session -65 (commit
6b47afa9; branch head 80a414c7, four commits on dev db3b9e4e, not pushed; the
maintainer asked for a branch and PR). The four new test files, re-run by
session -4f in its own worktree: 39 passing on the branch, 7 failing with lib/
at db3b9e4e. Corrections are in the register entry. Filed 2026-10-27 by
session -4f from the ST-VIEWS census. Related to ST-VIEWS, whose bounded views
may be the fix's home.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-204` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
