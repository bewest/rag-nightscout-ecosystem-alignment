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

# Review packet — MT-CONSUMER-STALE-RESELECT

**Alarm consumer survives evaluator timer publications during selection (BF-231)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/consumer-refusal-20261110` |
| base | `official/workspace/multitenant-20261102@b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-CONSUMER-STALE-RESELECT` is the measurement |
| semver | `n/a` |
| register entries | `BF-231` |

## What this changes

lib/tenant-notifications/producer.js select re-runs on
NOTIFICATION_PRODUCER_STALE (up to 3); multitenant evaluator preview only.

## Why that semver

fix to an unreleased preview behaviour

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-consumer-refusal-20261110`

Producer tests including two controlled-interleaving stale cases: 7 passing on
1adb17f8 (head now 956d0940); red on b70ad83f and under the no-reselect
control. Native evaluator-consumers 5, tenant-notifications 7, churn 1
passing.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-M6B-JOIN`

## Evidence

- [`reports/tenancy/consumer-refusal-2026-11-10/README.md`](../../reports/tenancy/consumer-refusal-2026-11-10/README.md)

## Notes carried on the item

2026-11-10 (reproduced): 1adb17f8 on b70ad83f. Open: the outputRevision
freshness-gate path (component.js:38-43) needs a maintainer decision (wake the
consumer on timer publications, or compare effects). 2026-11-10 second pass
(reproduced): 956d0940. Revision only on content change (digest of checkpoint,
progress, emitted, requested, properties); alarm repeat on the tenant
heartbeat (60 s default) with ack/snooze silence and outbox suppression
unchanged; targeted wake. Deployed intervals: deliveries per active alarm
60/min -> 1/min, selections 360 -> 125/min, 0 refusals; 150 ms churn 8/8
delivered. Repeat covers any requested notification, as single-site processing
does. Handed to the batch join. 2026-11-10: joined into codex/batch-
join-20261110 16a1fc2d (MT-BATCH-JOIN-1110), accepted, not pushed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-CONSUMER-STALE-RESELECT` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
