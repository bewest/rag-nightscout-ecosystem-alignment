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

# Review packet — ID-SCOPE-DECISION

**Decide: is identifier unique per collection, across collections, and per
tenant under TENANCY_MODE=multi?**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@fade2299` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ID-SCOPE-DECISION` is the measurement |
| semver | `n/a` |

## What this changes

A decision row, no code. Its answer sets ID-UNIQUE-INDEX's key (which fields
the partial unique index covers) and the PostgreSQL schema's constraint under
D2/D3.

## Why that semver

a decision; the index that follows is classed in ID-UNIQUE-INDEX

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision, not measurable. Proposed for review: unique per (tenant,
  collection); the same value may name a treatment and an entry (Loop
  derives treatment and glucose ids from different sources, and API v3's
  computed uuid.v5 includes eventType only for treatments); tenants never
  share an identifier space.

## Blocked on

`LOOP-ID-REPLY`

## Evidence

- [`docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)
- [`docs/60-research/tenancy/identifier-duplicates-2026-10-17.md`](../../docs/60-research/tenancy/identifier-duplicates-2026-10-17.md)

## Notes carried on the item

Today no index on identifier is unique (entries.js:224,226,
treatments.js:430,432, devicestatus.js:168, api3 mongoCollection/index.js:21
at 15.0.8), and every match is within one collection, so uniqueness is per
collection by construction and only by convention. Cross-references: D2
(shared logical storage with a tenant discriminator) and D3 (PostgreSQL with
RLS) mean a per-tenant scope is a column in the key, not a separate database;
D20 rule 5 ("one identifier names one record") does not say per what. The
simple contract (reply.body.md rule 2) says "one identifier names one record"
without a scope.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ID-SCOPE-DECISION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
