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

# Review packet — MT-ROOT-ADMIN-PARITY

**Multitenant tenant API_SECRET gets single-site admin parity: subjects, roles,
admin tools**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/root-admin-parity-20261110` |
| base | `codex/m6b-followups-20261110@65657a62a1e26dde9e245f9a7651d2593da0208a` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=MT-ROOT-ADMIN-PARITY` is the measurement |
| semver | `n/a` |

## What this changes

Multitenant DATA API: restore the admin-tools authorization routes for a
tenant's root principal, writing through the owner-aware subject writer (last-
owner guard), under RLS. No owner or operator authority for root.

## Why that semver

unreleased preview

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-root-admin-parity-20261110`

Root admin plane unit tests: 5 passing on cfae532c. PostgreSQL suites owner-
subject-policy 33, subject-admin-postgres 10, subject-management-http 13,
owner-preview 9 in the evidence.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-OWNER-LAST-GUARD`

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)
- [`reports/tenancy/root-admin-parity-2026-11-10/README.md`](../../reports/tenancy/root-admin-parity-2026-11-10/README.md)

## Notes carried on the item

Decisions tenant-root-single-site-parity and root-may-edit-owner-subjects
(2026-11-10). 2026-11-10 (reproduced in lane): cfae532c on 65657a62.
/api/v2/authorization subjects (list/create/edit/delete) and roles
(list/create) for the tenant root secret on DATA; role edit/delete return 501;
store refuses construction without ownerPolicy; new nsdemo_root_writer
identity. Not run: preview API boot with subjectAdmin on real PostgreSQL and
Vault; browser admin page. 2026-11-10 second pass (reproduced): 165c13bf. Role
edit; rename 400 ROLE_RENAME_REFUSED; delete of a held role 409
SUBJECT_ADMIN_ROLE_IN_USE; catalogue default '*'; admin-role subjects use the
admin tools with their own token under single-site permissions
(admin:api:subjects:*, admin:api:roles:*). Migration
0007_root_role_administration is provisional (allocate at the join). owner-
subject-policy 38/0, focused unit 220/0; controls C1-C8. Owner and root share
one catalogue (policy row digest), so the demo gives owners '*' too.
2026-11-10: joined into codex/batch-join-20261110 16a1fc2d (MT-BATCH-
JOIN-1110), accepted, not pushed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-ROOT-ADMIN-PARITY` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
