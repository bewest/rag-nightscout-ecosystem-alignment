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

# Review packet — MT-TENANT-EXTENDED-SETTINGS

**Tenant environment carries plugin extended settings so the stale-data alarm
can be enabled (BF-232)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/tenant-extended-settings-20261110` |
| base | `official/workspace/multitenant-20261102@b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-TENANT-EXTENDED-SETTINGS` is the measurement |
| semver | `n/a` |
| register entries | `BF-232` |

## What this changes

lib/server/tenant-app/environment.js projection of extendedSettings; owner
settings surface for plugin alert settings; multitenant only.

## Why that semver

unreleased preview

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-tenant-extended-settings-20261110`

Tenant extended-settings catalogue, isolation and refusal tests: 9 passing on
2f1ae027. HTTP and evaluator integration (tenant-rest-context 10,
projection/derived/recovery 25) in the evidence.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`reports/tenancy/tenant-extended-settings-2026-11-10/README.md`](../../reports/tenancy/tenant-extended-settings-2026-11-10/README.md)

## Notes carried on the item

Read-derived 2026-11-10. Survey every plugin's extended-settings reads first.
2026-11-10 (reproduced): 2f1ae027 on b70ad83f; joins the next batch. Open:
owner editing of plugin alert enables after the first preview (documents
settle only the first preview); devicestatus.advanced defaults true on a
single site but is unset for a tenant (read-derived, env.js:396 vs
receiveddata.js:159). 2026-11-10: joined into codex/batch-join-20261110
16a1fc2d (MT-BATCH-JOIN-1110), accepted, not pushed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-TENANT-EXTENDED-SETTINGS` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
