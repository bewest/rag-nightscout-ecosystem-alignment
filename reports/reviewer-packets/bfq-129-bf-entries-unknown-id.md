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

# Review packet — BFQ-129

**BF-129 - GET /api/v1/entries/<id> for an id that names no entry answers 500**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/entries-unknown-id` |
| base | `origin/dev@e3adc91d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-129` is the measurement |
| semver | `patch` |
| register entries | `BF-129` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/api/entries/index.js GET /entries/:spec (an id that names no entry answers
200 [] instead of setting entries_err, which the formatter answered with 500);
the spec description in lib/server/swagger.json and swagger.yaml;
tests/api.entries.unknown-id.test.js (new).

## Why that semver

an error status for a read that finds nothing becomes 200 [], the answer every
other v1 read gives

## Who should review this, and why

maintainer

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official cat-file -e bf/entries-unknown-id:lib/api/entries/index.js`** &nbsp;·&nbsp; kind: `static`

The branch's route no longer builds the "No such id" error that the formatter
answers with 500 (origin/dev still does and fails this). Decided 200 []:
tests/api.entries.unknown-id.test.js on the branch shows an unknown id answers
200 [] and a storage error 500. A presence check only. Point it at origin/dev
once merged.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Open, found 2026-09-25 by the #8758 freeze review and queued at the
maintainer's request. Live on 15.0.8 for a lower-case id; #8758 extends it to
an upper-case id. Small enough to fold into #8758 if the maintainer wants;
otherwise after 15.0.9. Decide 404 or 200 [] first. 2026-09-25 - FIXED on
bf/entries-unknown-id f79dc732 (local, not pushed), one commit on dev
e3adc91d: an unknown 24-hex id answers 200 [] (decided over 404); storage
faults still 500; swagger updated. 11 tests; suite 3181/0/3 (Node 22.23.2,
MongoDB 7.0.43). Measured: 15.0.8 lower-case unknown 500, upper-case 200 [];
e3adc91d both 500; branch both 200 []. On 15.0.8 an entry stored under a
lower-case hex string also answered 500; #8758 fixed that. The consumer survey
finds no corpus client that fetches an entry by id. A BF-73 addendum came from
this measurement (register BF-73).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-129` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
