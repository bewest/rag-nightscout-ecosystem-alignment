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

# Review packet — BFQ-47

**BF-47 - an ordinary subject edit destroys stored fields, on today's release**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/dev@a8888f0d` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=BFQ-47` is the measurement |
| semver | `major` |
| register entries | `BF-47` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/authorization/endpoints.js:40 pick(), lib/admin_plugins/subjects.js PUT,
lib/authorization/storage.js save() replaceOne with upsert. The same three
files P0-C already touches.

## Why that semver

The repair on bf/auth narrows the loss rather than introducing it, but it also
introduces an allow-list, so a third-party tool can no longer preserve its own
fields by sending them in its own PUT - which it CAN do today, because save()
writes the caller's object as given. That is a capability removal on an HTTP
surface.

## What an operator would notice

> Editing a person or device entry through Nightscout's admin page already
> throws away fields that are not shown on that page - notes, the date it
> was created, and anything a third-party tool has stored there. It happens
> silently, there is no error, and it cannot be recovered by going back to
> an older version of Nightscout. This is how today's release behaves.

## Who should review this, and why

maintainer, AND the security reviewer who takes P0-C, together - this is the
one irreversible change in the Phase 0 batch and the question has to be
answered BEFORE merge, not after

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- DERIVED FROM SOURCE on origin/dev and on bf/auth. Not reproduced against a
  deployment. A gate would need a database with a subject row carrying an
  extra field planted on it, an edit through the admin path, and an
  assertion that the field survived - with a control row that has no extra
  field so a green result is known to distinguish the two. Nobody has built
  it.
- THE MISSING FACT IS NOT CODE, IT IS AN INVENTORY. No list exists of third-
  party tools that store extra fields on subjects or roles, and nothing in
  this repository can produce one. That inventory is what decides whether
  the narrower repair - delete only the derived
  accessToken/accessTokenDigest/digest and pass unknown fields through - is
  required or merely tidier.

## Blocked on

`P0-C`

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

This entry exists because a verifier REFUTED the framing of a finding about
bf/auth, and the refutation moved the defect from an unmerged branch onto the
current release. Keeping the security goal of BF-17 - the derived token never
reaches the database - does not require the allow-list.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-47` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
