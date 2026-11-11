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

# Review packet — MT-ADMIN-ROLE-OWNERSHIP

**M6b: compose ownership operations into the multitenant admin role with an
ownership_operator identity**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/ownership-role-20261110` |
| base | `official/workspace/multitenant-20261102@b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=MT-ADMIN-ROLE-OWNERSHIP` is the measurement |
| semver | `n/a` |

## What this changes

New multitenant admin role start (lib/server/serve/admin-config.js, admin-
preview.js, roles.js, serve/index.js, cli multitenant command); admin listener
serves only ownership-operations v1; deploy plan gains the ownership_operator
identity and grants (e6f6e248, to be ported to nightscout-deploy).

## Why that semver

new role start on an unreleased preview

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-ownership-role-20261110`

Admin role config, composition and grant-plan unit tests: 9 passing on
1376c294. The native suite (tests/admin-role-ownership.integration.test.js,
NS_ADMIN_ROLE_DOCKER_TEST=1) is 11 passing through a real admin process;
controls in reports/tenancy/ownership-role-2026-11-10/README.md.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-M6B-JOIN`

## Evidence

- [`reports/tenancy/ownership-role-2026-11-10/README.md`](../../reports/tenancy/ownership-role-2026-11-10/README.md)

## Notes carried on the item

2026-11-10 (reproduced in lane): three commits on b70ad83f. Decision inputs
(read-derived): default admin bind vs plane rule; restore cohort census
refuses while admin is connected; no lifecycle fence on ownership changes.
2026-11-10: joined into codex/batch-join-20261110 16a1fc2d (MT-BATCH-
JOIN-1110), accepted, not pushed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-ADMIN-ROLE-OWNERSHIP` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
