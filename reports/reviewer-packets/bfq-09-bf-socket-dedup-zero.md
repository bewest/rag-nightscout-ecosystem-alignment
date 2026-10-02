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

# Review packet — BFQ-09 (PR #8797)

**BF-09 - socket dedup truthiness skips a falsy value**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/socket-dedup-zero` |
| base | `official/dev@ca6fcfaf` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-09` is the measurement |
| semver | `patch` |
| register entries | `BF-09` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/websocket.js:618-638 on dev ca6fcfaf (538-566 on v15.0.8): the
socket's 2 s similar match; tests/websocket.dedup-zero.test.js.

## Why that semver

if it is a defect at all, the fix is a bug fix

## What an operator would notice

> When two treatment records arrive within two seconds of each other,
> Nightscout decides whether they are the same one. That check ignores a
> value of zero. A zero temporary basal rate - the suspend an automated
> insulin delivery system sends - is exactly such a value. It is not settled
> whether this ever discards a real record.

## Who should review this, and why

maintainer (intent decided 2026-10-02)

## What was measured

**`node tools/queue/gates/bf09-corpus-divergence.js`** &nbsp;·&nbsp; kind: `static`

GT3's corpus sweep, re-runnable. 277,690 treatments across 11 sites, 0 outcome
divergences within the ±2s window, AND a four-case injection harness proving
the comparison is not vacuous (2 DIVERGES, 2 agree). De-identified counts
only.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The corpus is SURVIVORSHIP-BIASED in exactly the direction that hides this
  defect: it counts stored data, and the defect's effect is to suppress an
  insert. A suppressed insert cannot appear in stored data. The one arm that
  would settle it is a live uploader-burst replay, which nothing here can
  run.
- No test in the suite exercises a zero-valued dedup field. The only values
  in tests/websocket.*.test.js are insulin: 1 and carbs: 9/10/15/18.

## Evidence

- [`docs/60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md`](../../docs/60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md)
- [`docs/60-research/remedial/gt3-register-truth-2026-09-15.md`](../../docs/60-research/remedial/gt3-register-truth-2026-09-15.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-02 (maintainer, later the same day, relayed by session -d4): DEFERRED
until after 15.0.9, reversing the decision to take it in; removed from RT-0's
blocks_on. #8797 stays open for the next release. Reasoning: the practical
impact is small. The affected path is AAPS NSClient v1 (3.4.2.6; removed on
AAPS master in 30fe4591a7), the standalone NSClient app xDrip+ broadcasts to,
and the chart's drag-to-move; a temp is lost only when two temps with the same
whole-minute duration start within 2 s; no field report. 2026-10-02: opened as
#8797 by the maintainer (head 7dff9f38, MERGEABLE, base dev). 2026-10-02
(session -d4's agent): bf/socket-dedup-zero 7dff9f38, one commit on dev
ca6fcfaf (lib/server/websocket.js +26/-15, new tests/websocket.dedup-
zero.test.js), not pushed. percent, absolute and duration treat 0 as a value
matched exactly; insulin and carbs treat 0 as none ({$in: [0, null]}); '',
false and null are still not keys. 22 new tests; reverting websocket.js fails
9 with the record dropped; an exact zero key on all five fields fails the 2
xDrip filler re-sends, zero-or-absent on all five fails the 2 cross-temp
cases. Full suite 3556/0/4 (dev ca6fcfaf 3534/0/4; Node 22.23.2, MongoDB
7.0.43, one cell). PR body: reports/phase0-pr-bodies/socket-dedup-zero.md.
2026-10-02 (maintainer, relayed by session -d4): taken into 15.0.9; in RT-0's
blocks_on. dev is still ca6fcfaf, so no merge is needed before the push.
2026-10-02 (maintainer, relayed by session -d4): confirm and adopt conditional
handling of zero by field and type. The maintainer's reading: a temp basal
with 0 is a real value and a bolus with 0 is a real value, but insulin: 0 on a
carbs entry is not a match key. A local fix branch is being prepared by -d4's
agent in externals/work/crm-bf09 off dev ca6fcfaf, not pushed; whether it goes
into 15.0.9 is decided once it is measured. Measured, awaiting the
maintainer's decision. docs/60-research/remedial/bf09-dedup-zero-
measurement-2026-09-23.md (dev 74fc6619 and 15.0.8, identical): treating zero
as a real value fixes 6 dedup cases and changes no control, and bec641ca, the
candidate for the old AAPS zero-temp display problem, was rendering only. No
fix branch. Decisions: - 2026-09-23 (maintainer): measure first, then decide.
The maintainer leans towards treating zero as a real value (a zero temp basal
is a real value in AID terms), and the fix must not bring back the temp-basal
display problem seen when AAPS issues zero temps seconds apart. Reproduced
2026-09-23 as cases X1 and X2: because a falsy field is left out of the
lookup, the lookup can end up keyed on fields another eventType also has, so a
zero temp can match a different eventType within the ±2 s window
(maxtimediff). Only uploaders using the socket path without NSCLIENT_ID reach
this. The register entry names the wrong fields: over 277,690 treatments there
are zero zero-valued `insulin` (0 of 107,732) and zero zero-valued `carbs` (0
of 12,394); the field that carries falsy values is `absolute`, 67,521 of
153,315 (44%), the zero temp basal, and `duration:0` adds 2,094. GT3's
reading: a bug, not intent, because the author built an explicit
selected/fallback mechanism. tools/queue/gates/bf09-corpus-divergence.js
undercounts and needs fixing before its figure is trusted. 2026-09-26 -
BF-121's fix (bf/same-time-treatments fc821024, BFQ-121) makes the socket
similar match always key on eventType, which fixes X1 and X2; Z2, Z5, P2, B2
and C2 remain. A BF-09 branch will conflict with BF-121's on the similar-match
lines.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-09` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
