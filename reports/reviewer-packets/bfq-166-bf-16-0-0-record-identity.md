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

# Review packet — BFQ-166 (PR #8845)

**BF-166 - a profile re-sent with its own _id answers 500**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-record-identity` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-166` is the measurement |
| semver | `patch` |
| register entries | `BF-166` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/profile.js create path over API v1 and in-process.

## Why that semver

a retried write stops failing; nothing stored changes

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced: profile v1 resend-hex answers 500, profile inproc resend-hex a
  duplicate-key error. A gate asserts 200 and one stored record; control:
  43289dde fails it.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/30-design/tenancy/write-contract-spec-2026-10-07.md`](../../docs/30-design/tenancy/write-contract-spec-2026-10-07.md)

## Notes carried on the item

2026-10-25, later: in PR #8845 to dev (branch bf/16.0.0-record-identity; the
remote shows 539856ef; head bf37858e after merging dev 428b20b7, pending
push). 2026-10-25: fixed as c62a16c9 on bf/16.0.0-record-identity (PR #8845,
head bf37858e after merging dev 428b20b7, pending push; session f4's identity
lane), implementing the decided write-contract Q1 merge (2026-10-12): a
profile re-sent with a stored _id is merged into it and answered 200 with that
_id; an identical re-send writes nothing; Q1b (null deletes a field) is not
implemented and stays unconfirmed. Evidence, reported by the lane: write-
contract matrix b29f1bf7 against 26191780, 42 of 336 cells differ, 40 intended
and 2 in the racy cache field. Filed 2026-10-07 from the WRITE-CONTRACT write
matrix. Present on 15.0.8 too. BF-116 fixed the same shape for devicestatus.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-166` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
