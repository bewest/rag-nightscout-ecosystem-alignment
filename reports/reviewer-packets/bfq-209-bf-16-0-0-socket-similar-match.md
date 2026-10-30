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

# Review packet — BFQ-209 (PR #8877)

**BF-209 - two identical treatments sent over the socket within 2 s are stored
as one, even from different clients**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-socket-similar-match` |
| base | `official/dev@e1f7ac41` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-209` is the measurement |
| semver | `patch` |
| register entries | `BF-209` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/websocket.js processSingleDbAdd, the similar match only (identifier
decides when present); the exact match is unchanged. Carries the socket dedupe
gate (d6b0ef47).

## Why that semver

A record that was swallowed is stored; in the 16.0.0 merge list. One matrix
cell moves on purpose (treatments x v3 x ws, now 2 records, like v1 and in-
process).

## What an operator would notice

> When two apps, or the website's chart, send the same kind of treatment
> with the same amount within two seconds of each other, Nightscout can keep
> only one of them, so a carb or insulin entry is missing from what it shows
> and passes to followers. This affects uploads over the live connection
> only (for example AndroidAPS 3.4.2.x's older Nightscout client). Not yet
> in a released version.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour gate is the socket dedupe gate on the branch (test/ws-
  dedupe, 58 tests, each rule's ablation red alone), run in the crm
  worktree; not wired here because it needs the branch's node_modules.
  Measured 2026-10-29: npm test 4759 to 4853/0/3; the exact match's selector
  identical over 559,872 inputs.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/30-design/platform/wc-step-design-note-2026-10-27.md`](../../docs/30-design/platform/wc-step-design-note-2026-10-27.md)

## Notes carried on the item

2026-10-29: draft PR #8877 opened by the maintainer (GitHub head ebed6323,
which still carries BF-210's withdrawn rule and names it in the title). Local
bf/16.0.0-socket-similar-match ac5d77fb adds the BF-210 withdrawal (567f0612)
and BF-211's fix (ac5d77fb, from 13107d1e); not pushed. In the 16.0.0 merge
list (maintainer, 2026-10-29).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-209` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
