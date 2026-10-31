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

# Review packet — BFQ-224 (PR #8885)

**BF-224 - a v1 filter with a plain value under the date field
(find[created_at]=<ISO>) answers 500**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-small-backfixes` |
| base | `official/dev@37b2280f` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-224` is the measurement |
| semver | `patch` |
| register entries | `BF-224` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/query.js enforceDateFilter (:121-131): a plain value under the date
field must not be iterated as an operator object. Every v1 route that builds
its query with query.js and a created_at or startDate date field (treatments
measured; devicestatus, activity, profile read).

## Why that semver

a query that failed with 500 since 2019 gets an answer; no change for any
query that works today

## What an operator would notice

> A report or tool asking Nightscout for the treatments at one exact time
> (find[created_at]=<time>) gets a server error instead of an answer, and a
> delete written that way removes nothing. Adding [$eq] works today. On
> 15.0.9 and dev.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/work/crm-small-backfixes merge-base --is-ancestor f59d7872 HEAD`** &nbsp;·&nbsp; kind: `static`

the local branch carries the BF-224 fix f59d7872 (16 new tests red on dev with
the TypeError, green with it); replace with the #8885 head gate once pushed

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-31 later: built by an agent of session -d1 as f59d7872 on
bf/16.0.0-small-backfixes (on the #8885 head ecbc9c06): a non-empty plain
string under the date field becomes {$eq: value} before the date rewrite (6
lines in lib/server/query.js); plain numbers unchanged; every operator form
and the BF-108 $in handling build byte-identical queries. Red on dev: 16 (9
unit, 7 HTTP incl. devicestatus); green 63/0; test:unit 1896, integration
subset 287, test:browser 684, eslint 0 errors; break-it (dev query.js) red on
exactly the 16. A plain value counts as a date filter like $eq, so the default
window does not apply (2020-dated records returned and deleted). Measured:
treatments, devicestatus (GET and DELETE), activity and profile also 500 on
dev. Ready to push to #8885. 2026-10-31: filed by session -d1; reproduced on
dev 37b2280f, v15.0.9 and f5bd2642 (probe worktrees externals/work/crm-repro-
dcreated-*). The fix needs a choice: treat a plain value as equality
(MongoDB's meaning of a plain value) or refuse it with 400. 2026-10-31
(maintainer): equality, bundled with BF-223 in one '16.0.0 small backfixes'
PR; being built by an agent of session -d1 on bf/16.0.0-small-backfixes (from
BF-223's ecbc9c06).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-224` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
