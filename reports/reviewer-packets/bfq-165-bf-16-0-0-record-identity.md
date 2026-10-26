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

# Review packet — BFQ-165 (PR #8845)

**BF-165 - a treatment re-send matched by its fallback key is answered without
_id**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-record-identity` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-165` is the measurement |
| semver | `patch` |
| register entries | `BF-165` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/treatments.js's fallback-key re-send reply, over API v1 and in-
process; the reply and data-update document would carry the stored _id.

## Why that semver

the reply gains the field a client already expects

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced: matrix cells treatments v1 resend-identity and treatments
  inproc resend-identity answer 200 with one document without _id. A gate
  asserts the _id is present; control: 43289dde fails it.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/30-design/tenancy/write-contract-spec-2026-10-07.md`](../../docs/30-design/tenancy/write-contract-spec-2026-10-07.md)

## Notes carried on the item

2026-10-25, later: in PR #8845 to dev (branch bf/16.0.0-record-identity; the
remote shows 539856ef; head bf37858e after merging dev 428b20b7, pending
push). 2026-10-25: fixed as 0d5edc66 on bf/16.0.0-record-identity (PR #8845,
head bf37858e after merging dev 428b20b7, pending push; session f4's identity
lane): a fallback-key match is answered with the stored _id (one indexed
findOne per unmatched item), and data-update carries it. Semver: the write-
contract spec's U6 says minor; 16.0.0 is a major either way. Filed 2026-10-07
from the WRITE-CONTRACT write matrix. Present on 15.0.8 too. NightscoutKit's
'NA' handling is read, not run.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-165` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
