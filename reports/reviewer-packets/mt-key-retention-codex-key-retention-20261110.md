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

# Review packet — MT-KEY-RETENTION

**M6b: 30-day retained-key destruction and after-window refusal**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/key-retention-20261110` |
| base | `codex/m6a-join-20261109@dc795bd1515f11808a8d0732f2be9925cb2ffcd1` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=MT-KEY-RETENTION` is the measurement |
| semver | `minor` |
| register entries | `BF-228` |

## What this changes

Deletion ceremony tail: the export artifact must hold every ciphertext/key
reference before secret/audit rows are removed; keys retained 30 days; an
operator destroy; restore refused after the window.

## Why that semver

lifecycle completion on the preview

## What an operator would notice

> After a site is deleted its encrypted data can be restored by the operator
> for 30 days; after that the keys are destroyed and the data cannot be
> recovered.

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-m6b-join-20261110`

tenant-lifecycle unit file on the joined candidate 3545236d: 31 passing (23
existing + 8 retention cases). Native PostgreSQL 16 + Vault suite
tests/tenant-key-retention.integration.test.js 6 passing in the lane; source
ablations in reports/tenancy/key-retention-2026-11-10/README.md.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-M6A-JOIN`

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)

## Notes carried on the item

Builds on the export/delete work recorded 2026-11-06 (HANDOFF-tenant-export-
delete). 2026-11-10 (reproduced in lane): ed46cc43 on dc795bd1. Deletion
refuses an artifact missing a key reference (LIFECYCLE_KEY_REFERENCE_MISSING)
before any secret/audit row goes; 30-day retention record (lifecycle migration
0005); restore refused after the window or after destroy; operator destroy
needs the exact intent string and an ended window, Vault key confirmed 404.
Four ablations red then green. Also fixed a defect in the dc795bd1 tree: the
ceremony ledger check admitted two of six lifecycle tables, so every ceremony
call refused on a fully migrated namespace (LIFECYCLE_RELATION_UNADMITTED,
reproduced natively; never released). Joined into MT-M6B-JOIN. Open for the
maintainer: early destroy refused by design; export-file expiry not automated.
2026-11-10: ships in #8898 at b70ad83f (MT-M6B-JOIN); CI green.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-KEY-RETENTION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
