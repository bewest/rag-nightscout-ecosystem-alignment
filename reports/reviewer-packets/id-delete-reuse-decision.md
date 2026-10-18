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

# Review packet — ID-DELETE-REUSE-DECISION

**Decide: after a delete, what does a re-send of the same identifier (or _id) do
- resurrect, refuse, or create new?**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@fade2299` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ID-DELETE-REUSE-DECISION` is the measurement |
| semver | `n/a` |

## What this changes

A decision row, no code. Its answer sets how ID-SIMPLE-MATCH and ID-FIRST-
MATCH treat a stored record with isValid false, and whether v1 DELETE keeps a
tombstone.

## Why that semver

a decision; the code that follows is classed in ID-FIRST-MATCH

## Who should review this, and why

maintainer, after the Loop maintainers answer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision, not measurable. Today, measured 2026-10-18 (tools/lab/record-
  identity, 15.0.8 and fade2299, identical): v1 DELETE is a hard delete, and
  a re-send stores the record again (same _id when the client sent one, a
  new ObjectId otherwise). API v3 DELETE marks isValid false; then GET and
  PUT answer 410, but a POST with the same identifier answers 200
  isDeduplication and replaces the deleted record, even with another date
  and device (the immutable-field check is skipped for a deleted record), so
  it is resurrected under the same _id. v3 DELETE ?permanent=true, then
  POST: 201, a new record.

## Blocked on

`LOOP-ID-REPLY`

## Evidence

- [`docs/10-domain/record-identity-reference.md`](../../docs/10-domain/record-identity-reference.md)
- [`tools/lab/record-identity/results/record-identity-2026-10-18.md`](../../tools/lab/record-identity/results/record-identity-2026-10-18.md)

## Notes carried on the item

Choices: resurrect (today's v3 POST), refuse (410, as v3 PUT does today), or
create a new record beside the tombstone. A deleted reading that a second
uploader still holds is re-sent on its next cycle, so "resurrect" undoes a
user's delete. Read at 15.0.8: lib/api3/generic/update/validate.js:36 skips
every immutable check when the stored record has isValid false;
update/operation.js:62 and patch/operation.js:42 answer 410. On dev, v1 reads
hide isValid false records (lib/server/soft-deleted.js) and an entries re-send
clears isValid (lib/server/entries.js $unset).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ID-DELETE-REUSE-DECISION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
