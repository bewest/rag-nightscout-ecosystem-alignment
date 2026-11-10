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

# Review packet — MT-OWNERSHIP-OPS

**M6b: operator-assisted ownership add, transfer and recovery**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/ownership-ops-20261110` |
| base | `codex/m6a-join-20261109@dc795bd1515f11808a8d0732f2be9925cb2ffcd1` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=MT-OWNERSHIP-OPS` is the measurement |
| semver | `minor` |

## What this changes

Headless operator API on the private plane: add co-owner, transfer, recover.
Tenant-bound, audited; concurrent changes cannot orphan a tenant or silently
replace an owner; unauthorized operations have no effect; recovery reveals no
secret.

## Why that semver

new private operator operations on the preview

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-m6b-join-20261110`

Ownership source and contract tests on the joined candidate 3545236d: 13
passing. The PostgreSQL/HTTP family (race and foreign-authority controls) is
opt-in native: 20 passing in the lane, with 12 ablations in
reports/tenancy/ownership-ops-2026-11-10/README.md.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-M6A-JOIN`

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)

## Notes carried on the item

Adopted policy: preview-operator-assisted-ownership (2026-11-07). Self-service
co-owner/transfer is not a preview gate. 2026-11-10 (reproduced in lane):
6ee8fb04 on dc795bd1. ownership-operations v1 private contract
(list/add/transfer/recover) with expectedOwners optimistic check, in-
transaction operator authority, separate operator database identity,
authorization migration 0006 (audit outcome/detail columns). Race: two
transfers, one applied and one OWNERSHIP_CONFLICT, both audited. Foreign
authority: no effect. Not yet composed into the admin role and no operator
identity in deploy/multitenant/config.js. Read-derived: subject-admin remove()
can delete the last owner subject; legacy subject-admin writers without
ownerPolicy do not serialize with ownership changes. Joined into MT-M6B-JOIN.
2026-11-10: ships in #8898 at b70ad83f (MT-M6B-JOIN); CI green.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-OWNERSHIP-OPS` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
