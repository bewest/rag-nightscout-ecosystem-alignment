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

# Review packet — BFQ-182 (PR #8844)

**BF-182 - on cut 3 (driver 7), boot against MongoDB 4.2 or older retries
forever with no HTTP server**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `chore/compose-mongodb6` |
| base | `official/chore/compose-mongodb6@ebb690cf` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-182` is the measurement |
| semver | `major` |
| register entries | `BF-182` |

## What this changes

lib/storage/mongo-storage.js isRetryableConnectionError (:48 on ebb690cf and
72c156fb) and the boot error path: a driver refusal of the server version
becomes a fatal boot error instead of a retry. Cut 3 only.

## Why that semver

driver 7 drops MongoDB servers older than 4.4 (cut 3's change); the fix only
makes that refusal visible

## What an operator would notice

> Not in any release. A future Nightscout release with the newer MongoDB
> driver (cut 3) does not work with MongoDB 4.2 or older. As cut 3 stands,
> such a site keeps retrying the database connection forever: the website
> never comes up, uploads fail, followers see no data and server alarms do
> not run, and only the host's log says why. The fix in progress makes
> Nightscout stop with an error page that names the problem. Check your
> MongoDB version before upgrading to a release that includes this change.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official cat-file -e 99fa8b1e^{commit}`** &nbsp;·&nbsp; kind: `static`

-f8's fix commit on wip/cut3-onto-16.0.0 exists in the shared clone; red if
the local branch is lost before it is pushed (a rebase changes the id, and
this gate must then name the new one)

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The defect needs a MongoDB 4.2 container and driver 7: reproduced
  2026-10-25 (init() on 72c156fb against 4.2.24 not resolved after 45 s;
  4.4.24 connected in 28 ms; driver 5.9.2 against 4.2.24 connected in 32
  ms). Not a queue gate.

## Evidence

- [`docs/60-research/modernization/mongodb-server-compat-matrix-2026-10-25.md`](../../docs/60-research/modernization/mongodb-server-compat-matrix-2026-10-25.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-25: fix 8f238fc5 in PR #8844 to dev (session -f8's cut 3,
chore/compose-mongodb6, head 200c1361). 2026-10-25: the driver x server matrix
is done (docs/60-research/modernization/mongodb-server-compat-
matrix-2026-10-25.md): driver 7.7.0 refuses 3.6.23, 4.0.28 and 4.2.24; 4.4.24
to 8.0.34 boot and pass integration 2013/0/1; with the fix (7b636ce6 on
wip/cut3-onto-16.0.0, the rebased form of 99fa8b1e) refused servers get the
boot error page (HTTP 500 at 32 to 50 s, process alive, no retry). Decision
(maintainer): driver 7 in 16.0.0, MongoDB 4.4 or newer required to start.
Filed 2026-10-25 by session f4 from the defaults-calendar lane (C3-2; register
§1b, kind b). The maintainer asked for confirmation that compatibility with
MongoDB 3.6 to 4.4 holds; a driver x server matrix is running, and the entry
claims only 4.2.24 and 4.4.24. -f8's cut 3 agent is adding a fatal boot-error
path (99fa8b1e on wip/cut3-onto-16.0.0, local, not pushed, not checked by
session f4).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-182` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
