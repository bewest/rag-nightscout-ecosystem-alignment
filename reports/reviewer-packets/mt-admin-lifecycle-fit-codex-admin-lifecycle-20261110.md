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

# Review packet — MT-ADMIN-LIFECYCLE-FIT

**Restore census accepts non-clinical identities; ownership refuses on non-
active tenants; admin plane rule allows same address on a different port**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/admin-lifecycle-20261110` |
| base | `codex/ownership-role-20261110@1376c2946ce71078b477d4e0f2e4d428f29778ed` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=MT-ADMIN-LIFECYCLE-FIT` is the measurement |
| semver | `n/a` |
| register entries | `BF-230` |

## What this changes

operation-cohort.js assertComplete (grant-checked exemption), ownership
operations phase check, listeners.js plane rule.

## Why that semver

unreleased preview

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-admin-lifecycle-20261110`

Plane-rule tests including admin on the consumer address at another port: 23
passing on 26b5349d. Native admin-lifecycle-fit suite 4 passing (restore with
admin connected).

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-ADMIN-ROLE-OWNERSHIP`

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)
- [`reports/tenancy/admin-lifecycle-2026-11-10/README.md`](../../reports/tenancy/admin-lifecycle-2026-11-10/README.md)

## Notes carried on the item

Decisions restore-census-and-ownership-phase and admin-plane-same-address-
different-port (2026-11-10). 2026-11-10 (reproduced in lane): 26b5349d on
1376c294. Census exempts backends whose identity holds no privilege on
CLINICAL tables (lib/tenant-lifecycle/clinical-catalogue.js), checked in the
census SQL; ownership refuses OWNERSHIP_TENANT_INACTIVE via tenantPhase
(window lock held shared). Not run: clinical logical restore with admin
connected. 2026-11-10 second pass (reproduced): 9ef3ffa4. Census also refuses
non-participants that can write the insertion-ordinal or write-clock tables
(controls K1-K4). Clinical logical restore with admin connected is blocked by
BF-230 (driver omits ledgerNamespace; operator lacks the key-retention grant);
a probe with both fixed ran to activated. Fix routed to this lane. 2026-11-10
third pass (reproduced): 66655756 fixes BF-230 (565a96aa operator column
grant, ports to nightscout-deploy); native fit suite 6 passing, focused family
228/0. Join note: the example in lib/tenant-lifecycle/README.md calls
importArtifact without ledgerNamespace (the export-expiry lane also edits that
README); fix at the join. 2026-11-10: joined into codex/batch-join-20261110
16a1fc2d (MT-BATCH-JOIN-1110), accepted, not pushed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-ADMIN-LIFECYCLE-FIT` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
