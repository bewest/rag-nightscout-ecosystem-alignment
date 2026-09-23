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

# Review packet — BF2-OPS

**bf2/ops - BF-10 compose ulimits, FU-RESIDUALS 3 and 7, BF-63 renderer**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf2/ops` |
| base | `origin/dev@74fc6619` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BF2-OPS` is the measurement |
| semver | `patch` |
| register entries | `BF-10`, `BF-63` |

## What this changes

docker-compose.yml, lib/plugins/index.js, lib/api/alexa/index.js,
lib/server/booterror.js.

## Why that semver

bug fixes and a shipped configuration file; no declared surface moves

## What an operator would notice

> Not released. Three small repairs: the bundled Docker setup stops the
> database crashing for lack of open files, an unrecognised Alexa request
> gets an answer instead of hanging, and the page that explains a start-up
> error stops failing for one kind of error.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf2/ops >/dev/null`** &nbsp;·&nbsp; kind: `static`

Merges into origin/dev with no conflict.

**`git -C externals/cgm-remote-monitor-official show bf2/ops:docker-compose.yml | grep -q nofile`** &nbsp;·&nbsp; kind: `static`

BF-10 - the compose file raises the open-file limit.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Follow-ups 3 and 7 and BF-63 keep their existing gates on FU-RESIDUALS and
  RT-BOOTERROR, which read origin/dev and go green when this merges.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf2-ops.md`](../../reports/phase0-pr-bodies/bf2-ops.md)
- [`docs/30-design/remedial/backfix-2-plan-2026-09-22.md`](../../docs/30-design/remedial/backfix-2-plan-2026-09-22.md)
- [`docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md`](../../docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md)

## Notes carried on the item

DESTINATION 15.0.9 (plan section 1a, "backfix 2 scope", 2026-09-23). Evidence
- the rc-c integration record, rc/15.0.9-additions-c b9c9828b, 2508/0/3 on
every Node and MongoDB pair; this unit's step added +6 and its three break-its
are red on the final tree. rc-c carries the superseded connector pin 338deb7f
and needs a re-merge (see BF2-AUTH). PREPARED 2026-09-22 - tip e6a50e9a on
origin/dev 74fc6619, four commits (03fba725 BF-10, e72ba30d follow-up 3,
af8eee45 follow-up 7, e6a50e9a BF-63 renderer guard). Suite Node 20.20.0,
mongo 7.0.43 - dev 2386/0/3, branch 2392/0/3, +6 exactly the new tests.
Follow-up 4 stays on bf/auth (ce82f0cd) and is not repeated here.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BF2-OPS` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
