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

# Review packet — BFQ-145 (PR #8845)

**BF-145 - API v3 PATCH and PUT by the shown id miss a record whose identifier
is null, "" or 0**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-record-identity` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-145` is the measurement |
| semver | `patch` |
| register entries | `BF-145` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/api3/storage/mongoCollection/utils.js identifyingFilter (used by modify.js
for PATCH and PUT): the same falsy-identifier _id fallback as
filterForEveryForm, keeping BF-117's guard; tests beside tests/api3.delete-
every-form.test.js.

## Why that semver

a v3 lookup that matched nothing finds the record GET already shows

## What an operator would notice

> Rarely, a record saved by an app with an empty identity cannot be edited
> through API v3 by the id Nightscout shows for it: the edit is refused, or
> a second copy is saved. No commonly used app is known to save records this
> way. The same on 15.0.8. A fix is planned for after 15.0.9. This is not
> medical advice.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured on a booted server (PATCH/PUT arm of
  tools/lab/triage-2026-09/api3-empty-identifier-delete.js) on v15.0.8
  92d08342, dev ce7d754a and 1c3aeb8c: PATCH 404, PUT 201 with two records,
  for identifier null, "" and 0. Needs a tree with node_modules and MongoDB,
  so not a queue gate.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-25, later: in PR #8845 to dev (branch bf/16.0.0-record-identity; the
remote shows 539856ef; head bf37858e after merging dev 428b20b7, pending
push). 2026-10-25: fixed as d4566292 on bf/16.0.0-record-identity (PR #8845,
head bf37858e after merging dev 428b20b7, pending push; session f4's identity
lane): identifyingFilter shares filterForEveryForm's no-own-identifier clause;
PATCH 404 to 200, PUT's second record to a replace, a v3 POST with such a
record's _id as identifier deduplicates. Filed 2026-09-26 from the BF-142 fix
work; after 15.0.9 by the maintainer's decision (2026-09-26). Not a regression
from 15.0.8.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-145` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
