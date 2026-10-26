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

# Review packet — ID-CLIENT-OID-DECISION

**Decide: may a client set _id (an ObjectId it creates), and which field wins
when identifier and _id match different records?**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@fade2299` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ID-CLIENT-OID-DECISION` is the measurement |
| semver | `n/a` |

## What this changes

A decision row, no code. Its answer amends D20's 2026-10-16 walk-through (rows
2 and 3: every legacy _id is one the hub assigns, carrying the hub's receipt
time) and sets the write step's conflict rule in ID-FIRST-MATCH.

## Why that semver

a decision; the code that follows is classed in ID-FIRST-MATCH

## Who should review this, and why

maintainer, after the Loop maintainers answer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision, not measurable. Two questions, raised 2026-10-17 in the Loop
  reply: (1) may a client create an ObjectId and send it as _id, so it needs
  no cache of server ids; (2) when a write carries both identifier and _id
  and they match different stored records, refuse, trust identifier, or
  trust _id.

## Blocked on

`LOOP-ID-REPLY`

## Evidence

- [`docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md`](../../docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md)
- [`docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)

## Notes carried on the item

2026-10-26: the API v3 half is settled in dev: #8845 (900abf7a) refuses any
body _id on API v3 create, PUT and PATCH with 400 (BF-170, BFQ-170). API v1
keeps its legacy _id handling as a version-scoped quirk (#8845's body). The v1
question is unchanged. Read at the tags: no release up to 15.0.6 converted a
client _id on POST (it was passed to MongoDB as sent, so 24-hex values were
stored as strings, BF-99..102); only PUT and by-id reads and deletes converted
with ObjectID(). MongoDB never required _id to be an ObjectId. Since #8758
(dev) a re-sent 24-hex _id is matched. A client-set _id cannot serve the
phone-and-watch case (two devices create two ObjectIds), so identifier is
needed either way. Maintainer, 2026-10-18: (2) identifier decides when the two
match different records, keeping D20 rule 5's identifier-first order and v1
treatments' behaviour today (lib/server/treatments.js:356-362 at 15.0.8); the
reply's earlier _id-first proposal is reversed. (1) still recommended, pending
Loop's answer: a client may send an ObjectId it creates as _id over v1 (API v3
stores it as a string, BF-170); any other _id value is not valid
(UUID_HANDLING keeps moving a non-24-hex string _id to identifier).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ID-CLIENT-OID-DECISION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
