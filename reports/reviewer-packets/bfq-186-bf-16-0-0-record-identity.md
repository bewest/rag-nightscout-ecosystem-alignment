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

# Review packet — BFQ-186 (PR #8845)

**BF-186 - API v3 logs a whole record when a client's identifier differs from
the computed one**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-record-identity` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-186` is the measurement |
| semver | `patch` |
| register entries | `BF-186` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/api3/shared/operationTools.js resolveIdentifier: the console.log(doc)
after the mismatch warning (:126-127 on dev b29f1bf7, :119-120 on v15.0.9).
Server-side log content only.

## Why that semver

log content only

## What an operator would notice

> When an app sends its own record identifier to Nightscout's API v3, the
> server writes the whole record, including glucose values and treatment
> amounts, into its log. Anyone who can read your hosting logs can see it.
> Keep access to your hosting logs limited.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official cat-file -e b34f6703^{commit}`** &nbsp;·&nbsp; kind: `static`

the fix commit on bf/16.0.0-record-identity exists in the shared clone; red if
the local branch is lost before it is pushed (a rebase changes the id, and
this gate must then name the new one)

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Read at dev b29f1bf7 and seen in the identity lane's test output; the
  branch's red and green runs are the lane's. A unit gate would write a
  record with its own identifier and assert the record's values are absent
  from captured console output; control: b29f1bf7 fails it.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-25, later: in PR #8845 to dev (branch bf/16.0.0-record-identity; the
remote shows 539856ef; head bf37858e after merging dev 428b20b7, pending
push). Filed 2026-10-25 by session f4 from the identity lane. Fixed as
b34f6703 on local bf/16.0.0-record-identity (PR #8845, head bf37858e after
merging dev 428b20b7, pending push). Present on v15.0.9 by reading.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-186` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
