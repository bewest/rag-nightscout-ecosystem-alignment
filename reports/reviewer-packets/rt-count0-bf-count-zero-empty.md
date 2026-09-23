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

# Review packet — RT-COUNT0

**v1 ?count=0 answers an empty list, amending #8738 before 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/count-zero-empty` |
| base | `origin/dev@74fc6619` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=RT-COUNT0` is the measurement |
| semver | `patch` |

## What this changes

Tip 7b32d9ab, one commit, 5 files - lib/server/count.js (isZeroCount;
applyCount answers zero without querying), lib/api/index.js validateCount
(GET/HEAD only, zero allowed), lib/api/devicestatus/index.js (kept 0 instead
of its default 10), lib/server/profile.js list(), and tests/api.count-
parameter.test.js (19 new, 2 changed, each marked).

## Why that semver

narrows #8738's new refusal before any release has shipped it

## What an operator would notice

> 15.0.9 will refuse a request for a nonsense number of records (for example
> "abc" or "-3") with an error, where earlier versions guessed a number. A
> request for zero records will answer with an empty list, not an error and
> not the whole collection. Uploading data is not affected.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/count-zero-empty >/dev/null`** &nbsp;·&nbsp; kind: `static`

Merges into origin/dev with no conflict.

**`cd externals/work/crm-count-zero && TEST=api.count-parameter npm run test-single`** &nbsp;·&nbsp; kind: `integration`

31 cases. Control, re-run by the coordinator 2026-09-23 against a private
mongo - with dev's lib the 21 new or changed cases fail and 10 pass. Break-its
(agent) - zero back to unbounded fails 9, zero back to 400 fails 11, the check
back on writes fails 6.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/backfix-2-plan-2026-09-22.md`](../../docs/30-design/remedial/backfix-2-plan-2026-09-22.md)

## Notes carried on the item

DECIDED 2026-09-23 (maintainer) - accepted that a DELETE ignores count, so a
delete carrying count=0 removes everything its filter matches, as 15.0.8
already did. PREPARED 2026-09-23. Read matrix (30 entries, 120 treatments, 30
devicestatus, 15 profile, 15 activity, counted in mongo) - the ONLY change
from dev is the 0 and 00 columns, now 200 with no rows on every v1 read route;
0x10, 2.5, -3, 1e2, abc, MAX_SAFE+1, %2B5 and count=1&count=2 stay 400. Suite
Node 20.20.0 - dev 2386/0/3, branch 2404/0/3. FOR THE MAINTAINER, measured -
(1) dev (#8738) refuses every WRITE that carries any invalid count, including
count=0, with 400 and no change; the branch makes writes ignore count as
decided. (2) Neither tree limits a DELETE by count - DELETE with a find and
count=2 removed all 5 matching rows on both - so on the branch a delete
carrying count=0 removes everything its filter matches, where dev refused it.
(3) Routes that never apply count (/entries/current, /count/.../where,
/status, /echo, /food) now answer count=0 normally instead of 400. (4) v1 now
accepts zero while v3 limit=0 stays 400, so FU-LIMIT's "two implementations
that agree" no longer holds. PR body draft at reports/phase0-pr-bodies/count-
zero-empty.md. DECIDED 2026-09-23 (maintainer) - "count=0 should return a 0
length array of results." #8738 (merged to dev) answers HTTP 400 for count=0
because MongoDB reads .limit(0) as no limit; the maintainer wants an empty
list instead. Malformed counts stay 400, and the check runs on read routes
only, so writes ignore count. Ships in 15.0.9.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-COUNT0` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
