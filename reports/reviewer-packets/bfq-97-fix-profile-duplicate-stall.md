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

# Review packet — BFQ-97

**BF-97 - on the connector 0.1.0 line, a source with a profile stalls every poll**

| | |
|---|---|
| repository | `nightscout-connect` |
| branch | `fix/profile-duplicate-stall` |
| base | `official/dev@fbd4e55` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=BFQ-97` is the measurement |
| semver | `patch` |
| register entries | `BF-97` |

## What this changes

Connector lib/outputs/internal.js safePersist and lib/outputs/nightscout.js
recordingError, changed by 808ab1c (2026-09-21) to fail the whole poll on any
write failure; the Nightscout source re-inserts every profile with its source
_id each poll, so a duplicate key fails every poll after the first.

## Why that semver

A regression fix on an unreleased line; no setting or API moves.

## What an operator would notice

> Not in any release yet. With the connector version that 15.0.9 was going
> to use, a Nightscout site that copies its data from another Nightscout
> site fell 20 to 55 minutes behind whenever the other site had a profile
> saved, and showed no error. Nothing was lost; readings arrived late. It is
> being fixed before that connector version is released.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured by the lab soak (tools/lab/connector-soak/), not a queue gate.
  The fix branch is to carry a unit test that a second poll with the same
  profile does not fail, and that a genuine write failure still does.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/connector-0.1.0-dev.2-soak-2026-09-23.md`](../../docs/60-research/remedial/connector-0.1.0-dev.2-soak-2026-09-23.md)

## Notes carried on the item

DECIDED 2026-09-23 (maintainer) - (1) re-read what the sink stores each poll
instead of caching per process, with the cost bounded (the maintainer asked
whether it covers all profiles or only the latest); (2) update on change: a
source edit to an existing profile replaces the sink copy. NOT BUILDABLE AS
ASKED, found by a lab probe on 74fc6619 (no code written, f924de2 unchanged):
the connector's copies are stored with string _ids, and Nightscout's
save/remove/_id lookups convert to ObjectId, so a PUT duplicates instead of
replacing and DELETE cannot remove the copy (filed as a cgm-remote-monitor
backfix, branch bf/profile-object-id in preparation). API-style in-place edits
leave no timestamp. Reports use older profiles, so a bounded fetch misses
edits to non-newest documents. Cost today at 500 profiles of about 7 KB: about
3.5 MB per poll; bounded shape about 14 KB. Waiting on the maintainer: what
0.1.0 ships (bounded insert-only, or wait for the Nightscout fix). #8752 still
holds. PREPARED 2026-09-23 - f6359b4 on fix/profile-duplicate-stall (tip
f924de2, on fbd4e55, not pushed): profiles already stored on the sink, by _id
or identifier, are skipped instead of failing the poll, in both the internal
and REST outputs; every other write failure still fails it. Connector suite
292 -> 304 -> 308 on Node 20/22/24. 96-minute soak arm: fix polls every 5.0
min median with 0 lag before the outage, 0 profile errors; the dev.2 control
in the same run stalls at 28.9 min. A source edit to an existing profile is
skipped (as in 0.0.13); the stored set is cached per process (open question
for the maintainer). REST output covered by fake-transport tests only.
Evidence docs/60-research/remedial/connector-profile-duplicate-
stall-2026-09-23.md. DECIDED 2026-09-23 (maintainer) - fix in the connector
first, tag 0.1.0-dev.3, then 0.1.0; #8752 (P0-PIN) holds for dev.3. Fix being
built in this session on fix/profile-duplicate-stall (not pushed). Workaround
until then: CONNECT_SOURCE_COLLECTIONS=entries,treatments,devicestatus.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-97` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
