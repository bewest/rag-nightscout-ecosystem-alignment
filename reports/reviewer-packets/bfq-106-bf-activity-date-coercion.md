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

# Review packet — BFQ-106

**BF-106 - a numeric date filter on API v1 activity matches nothing on dev**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/activity-date-coercion` |
| base | `origin/dev@e3adc91d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-106` is the measurement |
| semver | `patch` |
| register entries | `BF-106` |

## What this changes

lib/server/query.js default_options (a named collection with no walker gets
legacyNumericDefaults: date and sgv read as numbers where the schema does not
type them) and lib/server/profile.js (walker: {} as on 15.0.8);
tests/api.activity-date-coercion.test.js (new) and a group in
tests/query.test.js. Read filters on activity and devicestatus, and the
devicestatus bulk DELETE, which on dev deletes nothing for an sgv filter.

## Why that semver

restores a 15.0.8 read behaviour that the coercion change removed

## What an operator would notice

> On 15.0.9 as it stands, a tool that asks the older API for activity
> records by their numeric date gets an empty list instead of the records it
> got on 15.0.8, and a tool that deletes device status records by a glucose
> value deletes nothing. The Nightscout pages do not use these filters. The
> fix restores the 15.0.8 behaviour.

## Who should review this, and why

maintainer

## What was measured

**`node tools/queue/gates/bf106-activity-date-coercion.js --ref bf/activity-date-coercion`** &nbsp;·&nbsp; kind: `static`

Builds the activity query with the branch's own query.js and activity.js and
checks that a find[date][$gte] bound is a number. Its control is origin/master
(15.0.8), where the bound is a number. Exits 1 on origin/dev e3adc91d (the
same script without --ref) and 0 on 20c197bb. Drop --ref once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The HTTP behaviour (7 activity records on 15.0.8, 0 on dev; the
  devicestatus sgv filter and bulk DELETE) is measured by the branch's
  tests/api.activity-date-coercion.test.js, which boots a server against
  MongoDB and so is not a queue gate.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md`](../../docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md)

## Notes carried on the item

2026-09-25 - FIXED on bf/activity-date-coercion 20c197bb (local, not pushed),
one commit on dev e3adc91d: default walker restored per field where the schema
does not type it; profile walker {} as on 15.0.8. 18 new tests; suite 3188/0/3
(Node 22.23.2, MongoDB 7.0.43). Correction: the item first said no write or
delete was affected; the devicestatus bulk DELETE with an sgv filter deletes
nothing on dev, and the fix restores it. The mis-transcription started in the
SHIPPING_WALKERS comment of tools/nsschema/emit/coercion_emit.py, which
records walker {} for activity and devicestatus although both inherited the
default on 15.0.8 (register BF-106; the emitter is not edited). Earlier: open,
no branch. Reproduced 2026-09-23 by the consumer-replay lab: 7 records on
v15.0.8, 0 on dev ddd9b600 and on the candidate (tree 2ce67b27), with the
created_at control at 7 on all three. The gate is red on origin/dev 153e5658
(2026-09-24). Filed with the maintainer's go-ahead (session -6a). Whether it
goes into 15.0.9 is the maintainer's call; no decision is recorded.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-106` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
