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

# Review packet — ID-ABSENT-DECISION

**Decide: a write that carries no identifier (and no _id) - keep the time-key
fallback, deprecate it, or require identifier?**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@fade2299` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ID-ABSENT-DECISION` is the measurement |
| semver | `n/a` |

## What this changes

A decision row, no code. Its answer sets the simple contract's rule 3
(reply.body.md) and what ID-SIMPLE-MATCH and ID-FIRST-MATCH do with an
unidentified write.

## Why that semver

a decision; requiring identifier would be a breaking change, classed when code
follows

## Who should review this, and why

maintainer, after the Loop maintainers answer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision, not measurable. Three choices: (1) keep the fallback (entries
  sysTime + type; treatments created_at + eventType, plus on dev the BF-121
  client-identity and amount fields; devicestatus none, insert-only); (2)
  keep it and mark it deprecated (a warning, a documented end); (3) require
  identifier and refuse a write without one.

## Blocked on

`LOOP-ID-REPLY`

## Evidence

- [`docs/10-domain/record-identity-reference.md`](../../docs/10-domain/record-identity-reference.md)
- [`tools/lab/record-identity/results/record-identity-2026-10-18.md`](../../tools/lab/record-identity/results/record-identity-2026-10-18.md)
- [`reports/consumer-impact-15.0.9/clients-8758.md`](../../reports/consumer-impact-15.0.9/clients-8758.md)
- [`docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md`](../../docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md)

## Notes carried on the item

Today (tools/lab/record-identity, 2026-10-18, 15.0.8 and fade2299): entries
without either id merge on sysTime + type; treatments merge on created_at +
eventType (15.0.8 overwrites a second carb amount at the same time; dev keeps
both, BF-121); devicestatus stores every POST. Requiring identifier would
refuse the writes of clients the consumer-impact survey read as sending
neither id (read-derived, clients-8758.md): DiaBLE (entries), oref0 (entries,
treatments, devicestatus), tconnectsync (POSTs), share2nightscout-bridge and
minimed-connect-to-nightscout (entries, devicestatus), nightscout-librelink-up
(entries over v1 and v3), and Loop's own entries and device status
(reply.body.md). Hand-written scripts (curl, spreadsheets, the careportal)
also send neither. API v3 is not affected by the choice: it computes
identifier as uuid.v5 of device, date and eventType when none is sent. Decided
2026-10-18 (maintainer): identifier becomes mandatory at a future version
boundary, and for registered instances of controllers (registration §8); until
then the legacy paths keep the time-key fallback for a write without one
(choice 1 now, choice 3 at the boundary). State stays needs-decision because
two parts remain: which version is the boundary (and whether a deprecation
warning precedes it), and how a hub recognises a registered instance's write
on a legacy path so that it can refuse one without identifier. Recorded in
docs/30-design/platform/identifier-conventions.md §1 and identity §5.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ID-ABSENT-DECISION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
