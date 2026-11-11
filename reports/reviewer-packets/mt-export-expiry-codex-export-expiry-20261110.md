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

# Review packet — MT-EXPORT-EXPIRY

**Key destruction removes the export artifact file in the same audited step**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/export-expiry-20261110` |
| base | `official/workspace/multitenant-20261102@b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=MT-EXPORT-EXPIRY` is the measurement |
| semver | `n/a` |

## What this changes

Tenant lifecycle key destruction (key-retention custodian) also deletes
tenant-artifact-<digest>; one audit entry.

## Why that semver

unreleased preview

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-export-expiry-20261110`

Lifecycle unit tests including five export-expiry cases: 36 passing on
701eba6f. Native tests/tenant-key-retention.integration.test.js 6 passing;
controls in reports/tenancy/export-expiry-2026-11-10/README.md.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-M6B-JOIN`

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)
- [`reports/tenancy/export-expiry-2026-11-10/README.md`](../../reports/tenancy/export-expiry-2026-11-10/README.md)

## Notes carried on the item

Decision key-destruction-removes-export (2026-11-10). 2026-11-10 (reproduced
in lane): 701eba6f on b70ad83f. Migration 0006 adds artifact_removal
(removed/absent/failed) and its code; destroy refuses without a remover.
Partial failure: keys always destroyable, file outcome audited. Open: retry a
failed removal on repeat destroy (built: no); interrupted-after-removal
records absent. Join note: production wiring must pass removeArtifact;
operator role needs UPDATE on the two new columns; other lifecycle migrations
renumber after 0006. 2026-11-10: joined into codex/batch-join-20261110
16a1fc2d (MT-BATCH-JOIN-1110), accepted, not pushed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-EXPORT-EXPIRY` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
