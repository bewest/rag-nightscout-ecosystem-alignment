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

# Review packet — MT-OIDC-NATIVE

**M6a: run the nine-stage owner/OIDC native matrix through a disposable harness**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/oidc-native-harness-20261109` |
| base | `workspace/multitenant-20261102@ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=MT-OIDC-NATIVE` is the measurement |
| semver | `n/a` |

## What this changes

Test infrastructure only: a harness that starts PostgreSQL, Mongo and Vault
containers by digest, provisions the fixture identities, runs the nine
prepared stages (vault-single, vault-multi, mongo-sessions, pg-sessions,
mongo-http, owner-consumer, owner-authority, owner-browser, owner-
compatibility) against the frozen candidate c0a67b69, and removes the
containers. No serving, policy, migration or client change.

## Why that semver

test infrastructure

## Who should review this, and why

maintainer

## What was measured

**`node tools/queue/gates/oidc-native-recorded.js reports/tenancy/oidc-native-2026-11-09/summary.json`** &nbsp;·&nbsp; kind: `static`

RECORDED-EVIDENCE only: the 2026-11-09 nine-stage run on harness head 3b09131e
(c0a67b69 + vault probe status fix + harness) has every stage PASS with its
families complete, three mutant controls red then green, and
postgres/mongo/vault recorded by digest. Reads the committed summary; no fresh
native execution. Rerun on any later head with `tests/native/oidc-
matrix/run.sh --out <dir>` in the harness worktree.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`reports/tenancy/oidc-native-2026-11-09/README.md`](../../reports/tenancy/oidc-native-2026-11-09/README.md)
- [`reports/tenancy/shared-oidc-sessions-2026-11-07/README.md`](../../reports/tenancy/shared-oidc-sessions-2026-11-07/README.md)
- [`docs/30-design/tenancy/owner-authority.md`](../../docs/30-design/tenancy/owner-authority.md)

## Notes carried on the item

Decision 2026-11-09: disposable harness, not a grant ceremony. Source is
complete and frozen (194 explicit-file checks, independent crypto audit). The
nine stages declare 960s active + 135s teardown. Local resources present on
2026-11-09: Docker 29.1.3, postgres 16-alpine and hashicorp/vault images at
the compose.yaml digests, mongo 7/8 images, Google Chrome, Node 22, oref0 at
the pinned commit. 2026-11-09 RUN (reproduced): all nine stages PASS on
postgres 16.15, mongo 7.0.43, Vault 2.2.1; zero leftover
schemas/collections/mounts; three authored mutants executed red then restored
green. Infrastructure findings: Vault 2.x answers 200 with metadata on Transit
key creation where the probe expected 204 (test instrument fixed in 2151cc5b
on the candidate branch, source-owner review); the retired driver never passed
the consume callback the sixth vault check needs, so the prepared matrix could
not have gone green as written; the settings-reader fixture lacked SELECT on
schema_migrations (fixture fixed). UNMEASURED: full/browser/corpus/prcheck on
the branch (MT-M6A-JOIN), real provider interop, 17 of 20 authored mutants
(runnable via run.sh --control). Next step is the join; `ready-to-push` here
means the gate passes and the branch is local.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-OIDC-NATIVE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
