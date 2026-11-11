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

# Review packet — DEPLOY-TREE-HOME

**Move the Compose deploy tree to nightscout-deploy; core keeps the test
fixture; operator-facing README**

| | |
|---|---|
| repository | `nightscout-deploy` |
| branch | `docs/operator-readme-20261110` |
| base | `main@cda3826` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=DEPLOY-TREE-HOME` is the measurement |
| semver | `n/a` |

## What this changes

nightscout-deploy README rewritten for operators (what runs, how, pinned core
commit; stubs say not started); #8898 drops or shrinks deploy/multitenant to
the fixture its tests boot; port e6f6e248 grants as an overlay.

## Why that semver

unreleased preview

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- not started; gate: deploy repo identity check against the pinned core
  commit and the Compose demo passes from nightscout-deploy; core native/CI
  tests pass with only the fixture

## Blocked on

`MT-M6B-JOIN`

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)

## Notes carried on the item

Decisions deploy-tree-home-now and deploy-repo-readme (2026-11-10). 2026-11-10
(deploy-repo half, measured in lane): branch docs/operator-readme-20261110
9387428 on cda3826, unpushed. Operator README, shorter roadmap, tightened
placeholders; ownership-admin Compose overlay (one-shot step after the
imported bootstrap creates <prefix>_ownership_operator with the six grant
statements of core e6f6e248; admin service on a private address, no published
port). Grant statements identical to core (6/6); Compose run showed the exact
privilege set and listOwners listed; dropping the audit INSERT made admin exit
1. Mismatch: the imported tree is core ed2ced00 while core is 61 commits
newer; its health.js requires a removed module and tenant-admin exits 1 on the
mixed base (read-derived cause). Fix is one final re-import from the joined
#8898 candidate, after which the deploy repo is canonical and core keeps the
fixture (core half, at the join).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=DEPLOY-TREE-HOME` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
