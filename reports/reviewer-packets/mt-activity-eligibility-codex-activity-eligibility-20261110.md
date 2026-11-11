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

# Review packet — MT-ACTIVITY-ELIGIBILITY

**Pause/suspend drive worker eligibility; evaluator stops while paused; owner
may pause**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/activity-eligibility-20261110` |
| base | `official/workspace/multitenant-20261102@b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-ACTIVITY-ELIGIBILITY` is the measurement |
| semver | `n/a` |

## What this changes

Evaluator (and future connector workers) build work lists from tenants
eligible under pause/suspend instead of configured presence (evaluator-
runtime.js:101,152); owner-API pause verb with audit; restore/restart preserve
state.

## Why that semver

unreleased preview

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-activity-eligibility-20261110`

Activity policy and store unit tests: 16 passing on 07981b55 (12 on 8f3e3c60).
Native evaluator acceptance (29 passing across four suites) in the evidence.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-M6B-JOIN`

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)
- [`reports/tenancy/activity-eligibility-2026-11-10/README.md`](../../reports/tenancy/activity-eligibility-2026-11-10/README.md)

## Notes carried on the item

Decisions activity-is-pause-suspend and owner-may-pause (2026-11-10). Owner-
facing text says alarms stop while paused. 2026-11-10 (reproduced in lane):
8f3e3c60 on b70ad83f. New lib/tenant-activity (migration 0001,
paused/suspended flags, audit); evaluator and realtime consumers skip
ineligible tenants; owner pause/unpause routes with audit. Not wired: API
ingest/serving refusal under suspend, read blocking under pause, socket
disconnect on suspend; owner-facing suspend text currently overstates (says
uploads stop). 2026-11-10 second pass (reproduced): 07981b55. Suspend refuses
uploads and reads (423 TENANT_SUSPENDED) and disconnects sockets; pause
refuses reads/UI (423 TENANT_PAUSED), admits uploads and the credential
exchange; activity tables moved to the lifecycle catalogue as migration
0007_tenant_activity with backfill (number provisional; export-expiry adds
0006, root-admin-parity an authorization 0007); provisioning writes the row in
the tenant's transaction; unreadable row stops only that tenant (measured: B
kept delivering); deletion request pauses, cancel restores, execution
suspends. Native 33 passing; nine controls. Open: 423 vs 503 for refused
uploads; deploy wiring and grants; full API/realtime role runs with activity
selected; per-request read cost. 2026-11-10: joined into codex/batch-
join-20261110 16a1fc2d (MT-BATCH-JOIN-1110), accepted, not pushed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-ACTIVITY-ELIGIBILITY` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
