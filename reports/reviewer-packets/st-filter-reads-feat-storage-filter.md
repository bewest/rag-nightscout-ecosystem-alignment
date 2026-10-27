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

# Review packet — ST-FILTER-READS (PR #8861)

**Storage interface, first PR: the filter tree and interface methods under API
v3's adapter (ST-FILTER), and API v1 reads through them (ST-READS), with no v1
answer changed**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `feat/storage-filter` |
| base | `official/dev@7ad3a67f` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=ST-FILTER-READS` is the measurement |
| semver | `patch` |

## What this changes

lib/storage/filter.js (new: the filter tree, fromMongo, the MongoDB adapter),
lib/api3/storage/mongoCollection/{index,find,modify}.js (interface methods,
every write through #8854's write-step proxy), lib/server/query-operator-
allowlist.js (cycle guard); ST-READS adds the read sites of
lib/server/{entries, treatments, devicestatus, profile, food, activity}.js.
write-step.js, validated-update.js and check-write-boundary.js are unchanged.

## Why that semver

No client-visible change; the write-contract matrix (336 cells, off and
reject) and #8854's CRUD matrix are the pins.

## What an operator would notice

> Nothing should look different: every API v1 request gets the same records,
> status and error as before. Shapes the new filter tree would refuse are
> listed in the PR, not refused.

## Who should review this, and why

maintainer, plus a second human - every v1 read path moves

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured by the lab, not re-runnable from this repository alone (needs
  MongoDB and a dev tree). On feat/storage-filter 48e7e101 (dev 8dbb60c2
  merged into b752971c): npm test 4577/0/3, test:all 4905/0/3, check-write-
  boundary 8/8. On b752971c against dev 7ad3a67f: npm test 4526/0/3 (dev
  4429), test:all 4854/0/3 (dev 4757), #8854 matrix 422 = 422, write-
  contract matrix 0 of 336 cells differ off and reject (red control
  findFiltered -> []: 186 cells), tools/seam/v1-http-differential.js 700/700
  identical, tools/seam/v1-read-differential.js 2954/2954,
  tools/seam/filter-differential.js 0 mismatches. With QC-MATRIX-TT's
  Temporary Target cells (360, 823c7c68d): 48e7e101 equals dev 8dbb60c2 cell
  for cell off and reject.

## Evidence

- [`docs/30-design/platform/next-gen-platform-plan.md`](../../docs/30-design/platform/next-gen-platform-plan.md)
- [`docs/30-design/modernization/pr-8854-alignment-2026-10-26.md`](../../docs/30-design/modernization/pr-8854-alignment-2026-10-26.md)
- [`tools/qc/write-contract-matrix.js`](../../tools/qc/write-contract-matrix.js)
- [`tools/seam/DIFFERENTIALS.md`](../../tools/seam/DIFFERENTIALS.md)

## Notes carried on the item

2026-10-27: #8861 at 5310a447 is still a draft (gh pr view); hosted CI on it
16 passed, 3 skipped. It must be marked ready for review before it merges, and
it merges before #8863. 2026-10-27, final: #8859, #8866, #8868 and #8856 are
on dev (eed31dca). The maintainer merged dev into feat/storage-filter on
GitHub as 5310a447 (48e7e101 + eed31dca, 20:13:03Z); its tree 884b95ec equals
session -2e's re-merge 4fe7085b (checked by -ee), so the B6 measurements and
the re- runs apply. No push needed for #8861. npm test on that tree (session
-2e, MongoDB 7.0.43, Node 22.23.4): 4685 passing, 0 failing, 3 pending.
2026-10-27 (maintainer, Q12): goes into 16.0.0 through release allocation B6's
entry bar. Items 1, 3, 4 and 5 MET on local candidates (session -2e; cand/with
d6ba8e18 vs cand/without 2cae64f3: 360-cell matrix equal off and reject,
67-row replay equal, v1 HTTP 700/700, latency inside the noise floor, one-
commit revert cf762dd0 restores cand/without's tree). Item 2 (BF-72, BF-161 in
their private forks) is with -e4. Maintainer decided #8859 merges to dev
first. The PR branch is awaiting #8859: prep/storage-filter df4e5e9d (=
48e7e101 + dev 2dc0c1bc + #8859, clean; tree 402b22d6 equals cand/with's #8861
step 019bdce9, checked by -ee) becomes feat/storage-filter once the real dev
with #8859 is merged in. No push commands until -2e sends the final head.
2026-10-26, later: the maintainer pushed 48e7e101 and opened draft #8861. ST-
WRITES is being built on top of it (feat/storage-writes). 2026-10-26: the
maintainer decided ST-FILTER and ST-READS go up as one PR. ST-FILTER found
five defects in the September seam's fromMongo, each of which widens or
changes a read ({a: {}} dropped, empty $or and $and matching everything,
$exists undefined read as presence, RegExp g and s flags swapped, mongod-
refused $regex options coerced); the mingo round trip could not see them, the
live-mongod differential did. All five are fixed on the branch and pinned by
tests.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ST-FILTER-READS` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
