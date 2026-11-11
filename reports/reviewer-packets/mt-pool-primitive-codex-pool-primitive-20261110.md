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

# Review packet — MT-POOL-PRIMITIVE

**Shared pool-membership primitive (pool kind, member count, ordinal, ring
slice) for evaluator and vcpool**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/pool-primitive-20261110` |
| base | `official/workspace/multitenant-20261102@16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-POOL-PRIMITIVE` is the measurement |
| semver | `n/a` |

## What this changes

Multitenant only. One PostgreSQL pool-membership table keyed by pool kind and
ordinal, plus one slice function (tenant ID hashed onto the member count). The
evaluator pool and the vcpool connector pool use the same table and function
but never share a pool: a member of one kind is invisible to the other. Flag
off keeps one owner of every tenant, as today. The evaluator adopts it flag-
off in this item; its scale-event acceptance stays with MT-EVALUATOR-
PARTITION.

## Why that semver

unreleased preview

## Who should review this, and why

maintainer; architecture review

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- UNMEASURED until implemented. Gate: two kinds with overlapping ordinals
  stay independent; a member count disagreement or duplicate ordinal within
  one kind stops that kind's members and raises the alert; flag off selects
  every tenant. Control: key the table without pool kind and show the cross-
  kind test go red.

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)

## Notes carried on the item

2026-11-10: decided (decisions.md#pool-primitive-shared), built now ahead of
M7.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-POOL-PRIMITIVE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
