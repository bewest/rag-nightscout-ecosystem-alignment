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

# Review packet — P0-H (PR #8734)

**bf/merge - PR #8734, BF-36 client delta merge reads past the end**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/merge` |
| base | `origin/dev@a8888f0d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-H` is the measurement |
| semver | `patch` |
| register entries | `BF-36` |

## What this changes

1 commit. lib/client/receiveddata.js, one new test file.

## Why that semver

availability fix in client code; no declared surface moves

## What an operator would notice

> A treatment being removed at the same time as another update arrived could
> make the page stop updating until you reloaded it. The clock that tells
> you how old the reading is runs on its own timer, so it would still have
> gone stale and warned you - the reading shown was never wrong, it just
> stopped advancing.

## Who should review this, and why

maintainer. OPENED 2026-09-16 as PR #8734, base dev.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/merge`** &nbsp;·&nbsp; kind: `static`

bf/merge has not fallen behind origin/dev

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/merge >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`TEST=receiveddata.merge npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-merge`

in NEITHER local brace list - GT1's finding. Named here so the gate actually
runs the file that proves the fix.

**`git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/merge | grep -q b06c6faf882ebd84d6274`** &nbsp;·&nbsp; kind: `network`

the branch behind PR #8734 is on the remote at the exact tip this item was
measured against. Read-only. Verified 2026-09-16.

**`node tools/queue/gates/pr-body-parity.js --only 8734`** &nbsp;·&nbsp; kind: `network`

the live body of PR #8734 still matches the file it was posted from. Bodies
drift in one direction - a correction gets written into the file first - and
the only previous record that one was owed was a sentence in a notes: field,
which is what let #8738 stay wrong in public for a day. It does NOT measure
whether the body is TRUE: parity with a wrong file is still parity, and every
figure in these bodies has been wrong at least once. NON-VACUITY, reproduced
2026-09-16: one altered file gives 1 failing, an empty body dir gives 6
failing. SKIPS with exit 0 when gh is unauthenticated.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- `dataUpdate` still has no try/catch, so the NEXT throw from anywhere in
  the merge path has the same effect. This branch fixes one throw, not the
  missing boundary. No test asserts the boundary exists because it does not.
- Review and merge state of PR #8734 is upstream's, and cannot be gated from
  here without a GitHub API call. Tracked, not driven.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-merge.md`](../../reports/phase0-pr-bodies/bf-merge.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Sequencing letter H.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-H` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
