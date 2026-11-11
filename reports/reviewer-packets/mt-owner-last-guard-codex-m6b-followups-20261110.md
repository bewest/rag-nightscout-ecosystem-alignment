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

# Review packet — MT-OWNER-LAST-GUARD

**M6b follow-up: refuse revoking the last usable owner's subject (BF-229)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/m6b-followups-20261110` |
| base | `official/workspace/multitenant-20261102@b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=MT-OWNER-LAST-GUARD` is the measurement |
| semver | `n/a` |
| register entries | `BF-229` |

## What this changes

Owner-plane subject revocation in lib/subject-admin/postgres.js remove();
multitenant preview only. Refuses with SUBJECT_ADMIN_LAST_OWNER (409) when the
target is the last usable owner; legacy writer unchanged.

## Why that semver

fix to an unreleased preview behaviour

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-m6b-followups-20261110`

Source-shape test of the owner subject store, updated to model the usable-
owner lock query: 3 passing on 65657a62. The PostgreSQL family (tests/owner-
subject-policy.integration.test.js, opt-in native) is 25 passing with the fix
and 23/2 on b70ad83f; ablations in
reports/tenancy/m6b-followups-2026-11-10/README.md.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-M6B-JOIN`

## Evidence

- [`reports/tenancy/m6b-followups-2026-11-10/README.md`](../../reports/tenancy/m6b-followups-2026-11-10/README.md)

## Notes carried on the item

2026-11-10 (reproduced in lane): 65657a62 on b70ad83f. Joins the next #8898
candidate with the internal-listener reshape, deploy-tree move and ownership-
in-admin-role lane. Two related decision questions from the same lane (legacy
multi-mode writer without ownerPolicy; export-artifact expiry) are with the
maintainer. 2026-11-10: joined into codex/batch-join-20261110 16a1fc2d (MT-
BATCH-JOIN-1110), accepted, not pushed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-OWNER-LAST-GUARD` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
