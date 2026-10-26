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

# Review packet — BFQ-169 (PR #8845)

**BF-169 - API v3's swagger says clients must not supply identifier, but the
server keeps a client-supplied one**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-record-identity` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-169` is the measurement |
| semver | `patch` |
| register entries | `BF-169` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Documentation only: the identifierField description in lib/api3/swagger.yaml
and the same text in lib/api3/swagger.json (served at /api3-docs). No code
change.

## Why that semver

API documentation corrected to match shipped behaviour; nothing a client
receives changes

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Filed only. Reproduced 2026-10-17 by running resolveIdentifier from
  lib/api3/shared/operationTools.js at 15.0.8 and fade2299: a client-
  supplied identifier is kept (one console.warn), and one is computed only
  when none is sent. A fix's gate greps both swagger files for "The client
  should not create the identifier"; control: fade2299 still has it.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-25, later: in PR #8845 to dev (branch bf/16.0.0-record-identity; the
remote shows 539856ef; head bf37858e after merging dev 428b20b7, pending
push). 2026-10-25: fixed as a1ab22b6 and 539856ef (rewritten from 26191780) on
bf/16.0.0-record-identity (PR #8845, head bf37858e after merging dev 428b20b7,
pending push; session f4's identity lane), per the D20 two-id rule: identifier
is the client's sync identity, kept as sent and not required to be a UUID; _id
is the server's storage key. The maintainer lifted the pairing with ID-SIMPLE-
MATCH, which stays a separate item. Filed 2026-10-17 while checking the Loop
maintainers' proposal that Nightscout accept a client-supplied identifier. The
text "this field is immutable by the client (it cannot be updated or patched)"
is accurate for PUT and PATCH and stays; only the "should not create ... the
server automatically assigns it" sentence is wrong. lib/api3/doc/ and
README.md do not repeat it (read at fade2299). Decided by the maintainer
2026-10-17: ships with ID-SIMPLE-MATCH, in the same PR, on dev after cut 1's
rebase; not in 15.0.9. A docs-only change is a patch and could ride a re-cut
15.0.9 candidate if the RC is re-cut for another reason; that is the one
exception worth weighing, not a plan.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-169` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
