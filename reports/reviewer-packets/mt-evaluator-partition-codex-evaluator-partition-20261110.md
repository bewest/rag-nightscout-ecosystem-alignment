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

# Review packet — MT-EVALUATOR-PARTITION

**M7: evaluator partitioning by member count and ordinal, with a pool-membership
table**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/evaluator-partition-20261110` |
| base | `workspace/multitenant-20261102@ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-EVALUATOR-PARTITION` is the measurement |
| semver | `minor` |

## What this changes

Evaluator role only. Two environment variables (member count, this worker's
ordinal) behind a feature flag select the tenant slice by hash; flag off keeps
the single owner. A pool-membership table in PostgreSQL holds one heartbeat
row per member (ordinal, expected members, ring slice, lease expiry). A member
evaluates its slice only while every live row agrees on the member count and
no two live rows share an ordinal; otherwise it stops its own cycle and
alerts. No per-tenant lock; duplicate evaluation is bounded to one heartbeat
interval after a membership change and the evaluator's outputs are idempotent
by contract. Compose and Kubernetes bindings set the variables; a StatefulSet
ordinal supplies the worker index. A read-only private operational module must
expose configured mode/count/ordinal/rule/slice separately from observed
membership, heartbeat freshness/conflicts, eligibility and actual workload
progress. Standalone reports all configured tenants without fabricating a
membership lease. The endpoint-composition lane owns shared listener plumbing;
this lane owns evaluator payload/schema and observed-state semantics.

## Why that semver

opt-in flag; default behaviour unchanged

## What an operator would notice

> Optional setting for very large multitenant deployments to run more than
> one evaluator process. Off by default. Misconfiguration causes a visible
> alert and a refused computation, never two conflicting results.

## Who should review this, and why

maintainer; architecture and clinical-path review

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- UNMEASURED until implemented. Gate: scale-event control under the baseline
  workload. Run with members=2, then change to members=3 mid-cycle with a
  rolling restart; independently observe that bounded overlapping evaluation
  produces no duplicate logical durable/external effect, measure the overlap
  window, and show none misses more than one lease TTL of alarm ticks;
  control: start two workers with the same ordinal and show the second's
  commits are refused with the membership-conflict symptom and an alert is
  raised. Inspect the actual private operational API during standalone,
  healthy multi-member and conflicted/stale states; configuration-only false
  health is a separate red control. Inspection remains callable while
  evaluation is blocked and must not schedule work or acquire ownership.

## Blocked on

`MT-BENCH-BASELINE`

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)
- [`docs/30-design/tenancy/runtime-topology.md`](../../docs/30-design/tenancy/runtime-topology.md)

## Notes carried on the item

Decision evaluator-static-partition (2026-11-09, revised the same day): pool
membership table, not a per-tenant lease; the maintainer judged the per-tenant
fence unnecessary overhead given idempotent outputs. Open design choices
inside the item: whether a member with a stale peer row may take over that
slice after the lease expires; modulo vs consistent hashing. MT-SCALE-UNBOUND
measures the overlap window for any duplicate external effect. The operational
API is planned, not provided by current lifecycle status/in-process health.
See the runtime-topology ownership inventory: notification attempts, future
connector actors, realtime checkpoint/fanout and maintenance claims need their
own ownership semantics; the evaluator ring is not imposed on every component.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-EVALUATOR-PARTITION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
