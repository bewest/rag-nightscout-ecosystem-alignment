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

# Review packet — WC-STEP-PATCH (PR #8874)

**Release 1 (patch): one write step for every v1, v3 and socket path, today's
behaviour pinned; BF-165's _id in every reply**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `feat/write-intent` |
| base | `official/dev@db3b9e4e` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=WC-STEP-PATCH` is the measurement |
| semver | `patch` |
| register entries | `BF-165` |

## What this changes

As WRITE-CONTRACT: lib/storage gains the write step (spec section 2.3,
lib/storage/write-step.js inside collectionFor); the v1 server modules
(lib/server/{entries, treatments, devicestatus, profile, food, activity}.js),
the API v3 generic operations over lib/api3/storage and
lib/server/websocket.js route through it. No stored result changes except
BF-165: lib/server/treatments.js's fallback-key re-send reply and data-update
document carry the stored _id.

## Why that semver

Spec Q6 (a), decided 2026-10-12: the step lands with today's write-contract
matrix pinned (gate G1, "no cell changed"); BF-165 adds a field a client
already expects.

## What an operator would notice

> Nothing should look different. One fix: a treatment that an app re-sends
> after a lost reply is answered with its Nightscout id, so the app (Loop in
> particular) can later edit or delete it.

## Who should review this, and why

maintainer, plus a second human - every write path moves

## What was measured

**`node tools/queue/gates/write-rule-copies.js --ref official/dev`** &nbsp;·&nbsp; kind: `static`

No write rule (merge-patch, BF-194 units, write-validation, validated-update,
srv-dates, object-id-forms, the treatment fallback key) gains a new (rule,
file) pair or a larger count outside lib/storage/write-intent.js, against
write-rule-copies.baseline.json (47 pairs at dev db3b9e4e; 45 on feat/write-
intent after slice 1). Holds the maintainer's rule of 2026-10-27: a new write
rule goes into the step, not a route.

**`bash tools/queue/gates/write-rule-copies-control.sh`** &nbsp;·&nbsp; kind: `static`

Control for the gate above: an exported copy of official/dev passes, and the
same copy with one planted call to the BF-194 helper in lib/server/food.js
fails naming only that pair.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Not started; its blocker ARCH-8854 is merged (dev c08cbe03). Its gate is
  spec G1: tools/qc/write-contract-matrix.js run through every path with
  every cell equal to the pinned dev matrix except BF-165's two cells
  (treatments v1/inproc resend-identity gain _id); control: each of the
  spec's six one-line ablations turns its predicted cells red.

## Blocked on

`ARCH-8854`

## Evidence

- [`docs/30-design/tenancy/write-contract-spec-2026-10-07.md`](../../docs/30-design/tenancy/write-contract-spec-2026-10-07.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/qc/write-contract-matrix.js`](../../tools/qc/write-contract-matrix.js)

## Notes carried on the item

2026-10-28: draft PR #8874 to dev opened by the maintainer (head 0671b430);
not for 16.0.0. Slices 4 and 6 still to come. 2026-10-28, slice 5 (session
-4f's agent; heads, the two write-intent test files (169 passing), G2 and the
copies gate re-checked by -4f, and G1 re-run by -4f against the v2 pin): local
feat/write-intent 5d97fb59 (treatments), 869a7de1 (entries), 6115c755
(devicestatus), daaa3db9 (profile), 0671b430 (release-2 comments). G1 on the
360-cell pin: 0 cells and 0 commit events per collection; on the v2 pin (456
cells): 2 cells differ in the racy cache field only, the same two that vary
between runs of untouched dev. WRITE_VALIDATION=reject: matrix 0 cells, suites
608/0 before and after. npm test 4919/0/3; test:all passes. Write-rule copies
37 (baseline 47). G2 enrols 7 entries. A new test file runs the db3b9e4e
modules and the step side by side over a recording driver (calls, events,
emissions, log lines, replies), the only check on preBolus, UUID_HANDLING, the
profile permission and log lines. New questions Q-J..Q-P (design note). Slices
left: 4 (v3) and 6 (socket treatments, devicestatus, profile adds and
updates), held for the maintainer's review. 2026-10-27: G1's pin is now dev-
db3b9e4e-v2.json (456 cells: the 360 of the first pin, identical, plus update-
twin, idread-fail, harddelete-custom and harddelete-num; b6c19bc5a). Slices
1-3 (a0e7fcac) equal it in every cell, setting aside the racy cache field. The
activity save-twin break the first pin could not see turns activity update-
twin red on both v1 and in-process. Transition target (maintainer,
2026-10-27): every write path enrolled in the step before 16.2.0, measured by
G2's enrolled set covering every writer and by the write-rule copies gate
falling toward zero (47 at dev db3b9e4e). The mixed state (some paths through
the step, some not) is the riskiest one, so it is kept short. Release-2
questions are queue items WC-R2-QA..WC-R2-QH; WC-R1-QG and WC-R1-QI stay in
release 1. Contributor guide: docs/30-design/platform/guides/write-intent.md.
2026-10-27 late, slices 2 and 3 (session -4f's agent; heads, unit tests, G2,
the copies gate and the G1 compare outputs re-checked by -4f): local
feat/write-intent f0d51ee7 (activity, v1 and in-process) and a0e7fcac (the
socket's generic dbAdd for entries, food and activity, and dbRemove for all
six collections). G1 0 of 360 cells after each, commit events included; every
step ablation red only in enrolled cells, one (activity save-twin) red only in
the suite because no matrix form PUTs over a string twin; G2 enrols function
by function in websocket.js. npm test 4821/0/3; test:all passes. Write-rule
copies on the branch: five fewer than the dev baseline, none new. No dev test
expectation changed. New question Q-I: the step's id-match duplicates
websocket.js idMatch until the dbUpdate slice. Slices left: 4 v3 (after Q-A);
5 v1/in-process treatments, entries, devicestatus, profile; 6 socket dbAdd for
treatments/devicestatus/profile plus dbUpdate/dbUpdateUnset; 7 the event,
after D-EVENT. 2026-10-27, milestone 1 (session -4f's agent; heads, unit
tests, G2 and the G1 compare re-checked by -4f): local feat/write-intent
2b9d3687 + 84e21a66 on dev db3b9e4e, not pushed. Slice 1: food writes from API
v1 and in-process go through write(intent) (lib/storage/write-intent.js, 5
files +530/-77). G1: 0 of 360 cells differ from the pin
tools/qc/results/write-contract-matrix/dev-db3b9e4e.json (two baseline runs
identical; the six ablations all red, two report MISMATCH only because their
expected lists predate the Temporary Target cells). npm test 4761/0/3
(baseline 4750 + 11); test:all passes. Step ablations red only in enrolled
cells; unit tests and G2 (scripts/check-write-intent.js) shown to fail when
broken. Design note: docs/30-design/platform/wc-step-design-
note-2026-10-27.md, with slices 2-8 proposed and questions Q-A..Q-H for the
maintainer. 2026-10-26, later: ARCH-8854 is merged (#8854, dev c08cbe03, head
246313e4; dev now 7ad3a67f), so this item can start on dev, building on the
persistence boundary lib/storage/write-step.js; its write(intent) layer takes
a separate name such as write-intent.js, as #8854's data-contracts.md (its
architecture docs) says. State moves from blocked to not-started. The
September chain stays reference only. 2026-10-26: blocks on ARCH-8854 instead
of SEAM-REFRESH. The maintainer leans to building the seam on #8854's write
boundary (next-gen plan D-SEAM), and #8854 is decided into 16.0.0 (outcome B);
its condition 4 gives this item's write(intent) layer its own name, layered on
the boundary. The September chain is reference for the filter AST and
bulkUpsert modes. WRITE-CONTRACT has no sub-items: it is one item covering
both releases of spec Q6 (a). This item is its first release, split out so the
identifier items can block on it; WRITE-CONTRACT stays the umbrella and is not
duplicated. BFQ-165 (BF-165) can still land on dev first as a narrow fix; if
it does, this item keeps it pinned rather than re-making it. BFQ-169 (the v3
swagger text about identifier) is documentation only and independent; it is
linked because the identifier items below make the corrected text a promise.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=WC-STEP-PATCH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
