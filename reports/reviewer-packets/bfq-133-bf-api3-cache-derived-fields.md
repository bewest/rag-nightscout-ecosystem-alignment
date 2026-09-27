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

# Review packet — BFQ-133

**BF-133 - the COB pill's last-carbs detail can name an older carb entry than
the newest one (fixed by BF-146's branch)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/api3-cache-derived-fields` |
| base | `official/dev@699eb5fa` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-133` is the measurement |
| semver | `patch` |
| register entries | `BF-133`, `BF-146` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

No change of its own. Fixed by BFQ-146's commit db99bba4
(lib/api3/storage/mongoCachedCollection/index.js): with every held treatment
carrying mills, the dataloader's sort puts the treatments in time order and
lib/plugins/cob.js fromTreatments, which takes the last carb entry in array
order, names the newest one. cob.js is not changed.

## Why that semver

a display detail names the newest carb entry

## What an operator would notice

> The last-carbs line under the carbs-on-board (COB) pill could show an
> older carb entry than your newest one, for example after an older entry
> was edited. The cause also affected the COB number itself; see BF-146.
> Fixed together with BF-146, not yet released. Check your treatment list
> for the time of your last carbs. This is not medical advice.

## Who should review this, and why

maintainer

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official grep -q "processRawDataForRuntime" bf/api3-cache-derived-f`** &nbsp;·&nbsp; kind: `static`

BFQ-146's gate: the branch's v3 cache wrapper derives the v1 fields
(official/dev 699eb5fa and v15.0.8 fail this). A presence check only; the
"last carbs" test in tests/api3.cache-derived-fields.test.js decides (red on
699eb5fa and 92d08342, green on db99bba4). Point it at official/dev once
merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The test needs MongoDB, so it is not a queue gate. 2026-09-26, Node
  22.23.2, MongoDB 7.0.43: a v3 write, then an edit of an older carb entry;
  "last carbs" names the older entry on v15.0.8 92d08342 and 699eb5fa, the
  newest on db99bba4.

## Blocked on

`BFQ-146`

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/rc-soak/results/proof-2026-09-25.md`](../../tools/lab/rc-soak/results/proof-2026-09-25.md)
- [`tools/lab/rc-soak/results/proof-2026-09-27.md`](../../tools/lab/rc-soak/results/proof-2026-09-27.md)

## Notes carried on the item

Filed 2026-09-25 from the soak's CANDIDATE-2, which turned out to be 15.0.8
behaviour, not a 15.0.9 regression. 2026-09-26/27 - cause traced by RC run 019
(04a873ce): treatments written or edited through API v3 are held without mills
(BF-146), so the sort is not in time order. 2026-09-26 - FIXED by BF-146's
branch bf/api3-cache-derived-fields db99bba4 (local, not pushed). Ships with
BFQ-146; no separate PR.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-133` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-26, against cgm-remote-monitor-official `ff93fa94`.*
