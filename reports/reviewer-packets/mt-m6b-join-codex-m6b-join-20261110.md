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

# Review packet — MT-M6B-JOIN

**Join M6b ownership/retention, single-site OIDC provisioning, listener
composition and CodeQL 150 into #8898**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/m6b-join-20261110` |
| base | `codex/m6a-join-20261109@dc795bd1515f11808a8d0732f2be9925cb2ffcd1` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-M6B-JOIN` is the measurement |
| semver | `minor` |
| register entries | `BF-228` |

## What this changes

Frozen candidate b70ad83f: dc795bd1 plus merges of codeql-150 (7b30a6f2),
listener-composition (d69b873a with docs 3a534e89/692bd507), key-retention
(ed46cc43), ownership-ops (6ee8fb04), oidc-single-provision (4b81f59d), and
two join repairs: 665119fb pins the four ownership paths in the public-port
isolation test, 3545236d registers the provisioning test in the integration
tier, b70ad83f sets a fresh API secret before that test boots (shared-tier
order).

## Why that semver

opt-in features on the dormant multitenant preview branch

## What an operator would notice

> Optional, off by default. Single-site sites may sign people in with an
> identity provider without Vault, using a list of people and their roles.
> Multitenant operators gain assisted ownership changes and a 30-day key
> retention window after a tenant is deleted; destroying retained keys
> cannot be undone.

## Who should review this, and why

maintainer; security review of ownership, key destruction and identity
provisioning

## What was measured

**`node tools/queue/gates/oidc-native-recorded.js reports/tenancy/m6b-join-2026-11-10/b70ad83f-acceptance/oidc-ma`** &nbsp;·&nbsp; kind: `static`

RECORDED-EVIDENCE: full acceptance on frozen head b70ad83f (2026-11-10). unit
3106, dom 205, dependency 368/2 pending, core 319, harness 99, integration
3643/547 pending, stress 18, browser 686, multitenant corpus 550/1 pending (49
suites), all 0 failing; OIDC matrix 9/9 with three controls red then green
(this gate: 13 checked, 0 failing; 1 failing before the controls were merged);
key-retention native 6, ownership family 20, internal-api-compose pass and its
blanket-window control exit 1; test:tiers ok (614); write-intent and write-
boundary clean; lint 0 errors; prcheck OK. The stopped run on 3545236d (2
integration failures, repaired by b70ad83f) is kept beside it.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-M6A-JOIN`

## Evidence

- [`reports/tenancy/listener-composition-2026-11-10/README.md`](../../reports/tenancy/listener-composition-2026-11-10/README.md)
- [`reports/tenancy/key-retention-2026-11-10/README.md`](../../reports/tenancy/key-retention-2026-11-10/README.md)
- [`reports/tenancy/ownership-ops-2026-11-10/README.md`](../../reports/tenancy/ownership-ops-2026-11-10/README.md)
- [`reports/tenancy/oidc-single-provision-2026-11-10/README.md`](../../reports/tenancy/oidc-single-provision-2026-11-10/README.md)

## Notes carried on the item

Coordinator-owned join. Push of the accepted head and taking #8898 out of
draft remain the maintainer's. 2026-11-10: lanes MT-KEY-RETENTION, MT-
OWNERSHIP-OPS, MT-OIDC-SINGLE-PROVISION and the listener-composition part of
MT-ENDPOINT-TRANSPORT ship through this push. Lane unit ablations were run in
the lanes, not repeated on the joined head.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-M6B-JOIN` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
