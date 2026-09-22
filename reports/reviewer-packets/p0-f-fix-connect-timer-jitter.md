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

# Review packet — P0-F (PR #68)

**fix/connect-timer-jitter - PR #68, BF-34 backoff precedence and start jitter**

| | |
|---|---|
| repository | `nightscout-connect` |
| branch | `fix/connect-timer-jitter` |
| base | `official/dev@d208c7d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-F` is the measurement |
| semver | `minor` |
| register entries | `BF-08`, `BF-34` |

## What this changes

Against connector official/dev d208c7d (2026-09-22): README.md, index.js,
lib/backoff.js, lib/builder.js, lib/machines/cycle.js and four test files,
+430/-38 (`git diff --stat official/dev...official/fix/connect-timer-jitter`
in externals/nightscout-connect). Head 635cc9f contains #64's head 19af0c3,
not dev's merge commit d208c7d; trial merge into dev clean.

## Why that semver

GT4 argues for 0.1.0 rather than 0.0.14 and the argument is sound - option
precedence reversed, a changed default (use_random_slot:false ->
jitter:'equal'), a new throw on an unknown jitter mode, and duration_for
became non-deterministic. Each is breaking for a caller. It costs nothing
because ^0.0.13 matches only 0.0.13 and cgm-remote-monitor pins by exact URL.
Connector dev's package.json says 0.0.14; the choice is P0-TAG's.

## What an operator would notice

> This changes the connector, the part of Nightscout that fetches readings
> from a CGM (continuous glucose monitor) vendor's online service. When that
> service is refusing requests, the connector used to retry roughly 586
> times faster than it was configured to, and every account retried at the
> same instant. With this fix it waits the interval it was told to wait and
> spreads the retries out. Something that may seem backwards: after this fix
> a vendor outage can look like it recovers more slowly, because the
> connector no longer retries in a burst that could not have worked. For
> LibreLinkUp in particular, after a failed fetch the next attempt comes one
> to two and a half minutes later, as the connector is configured, rather
> than almost immediately. The connector can also spread out its first
> contact with the vendor after a restart; the spreading settings default to
> 0, so nothing changes for anyone who does not set them. This reaches no
> one until it is merged, a connector release is cut, and Nightscout is
> updated to use it (P0-TAG, P0-PIN).

## Who should review this, and why

maintainer, plus one reviewer other than the author of c1cce2a. Merge with a
merge commit so c1cce2a stays an ancestor of dev.

## What was measured

**`npm test`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/nc-jitter`

283 passing / 0 failing at 635cc9f; the connector suite needs no database

**`node -e "const b=require('./lib/backoff.js'); try { b({jitter:'wild'}); process.exit(1); } catch(e) { process.`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/nc-jitter`

the new throw on an unknown jitter mode is the observable half of the
precedence fix - if options were still being discarded, the bad mode would
never be read and this would not throw

**`git -C externals/nightscout-connect merge-tree --write-tree official/dev official/fix/connect-timer-jitter`** &nbsp;·&nbsp; kind: `static`

the PR branch merges into connector dev without conflicts. It contains #64's
head 19af0c3, so against dev d208c7d its diff is only this item's files. Reads
local remote-tracking refs; fetch official first.

**`git -C externals/nightscout-connect ls-remote --heads origin fix/connect-timer-jitter | grep -q 635cc9f43a5b92`** &nbsp;·&nbsp; kind: `network`

the branch behind nightscout-connect PR #68 is on the remote at the exact tip
this item was measured against. Read-only. Verified 2026-09-22.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Vendor rate limits are unmeasured (EXP-MT-051) and need real credentials,
  which rule 0 forbids here. CONNECT_START_JITTER_MS lets a pool be spread,
  but the window to set is exactly the number that is unmeasured.
- Review and merge state of PR #68 is upstream's, and cannot be gated from
  here without a GitHub API call. Tracked, not driven - the same marker
  P0-T01 carries.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/fix-connect-timer-jitter.md`](../../reports/phase0-pr-bodies/fix-connect-timer-jitter.md)
- [`docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)

## Notes carried on the item

Sequencing letter F. Merging this in the connector repository ships it to
nobody; P0-TAG and P0-PIN deliver it. `git merge-base --is-ancestor c1cce2a
official/dev` exits 1 until #68 merges. The branch carries the merge of #64's
head 19af0c3 (ffe5fb0), so c1cce2a is unchanged. dev's LibreLinkUp v4 code had
its own jitter (CONNECT_LINK_UP_STARTUP_JITTER_MS,
CONNECT_LINK_UP_INTERVAL_JITTER_MS); the two are one mechanism in
lib/machines/cycle.js: one start delay on Init over the wider of the
deployment and source windows; the wider of the two on the unaligned interval;
only the source window on the aligned interval; every window capped at five
minutes. LibreLinkUp's fixed frame retry, noRetryStatuses and the 429 throttle
path are unchanged and are still checked before the backoff. LibreLinkUp's
configured cycle backoff (2.5 minutes x 2^attempt, capped at six poll
intervals) is now honoured; its recovery test asserts that (676b80e) and fails
with dev's backoff.js. The combined jitter rules are tested in 635cc9f, and
breaking each rule fails at least one test. The LibreLinkUp real-Nightscout
lab passes locally and in CI at 635cc9f. Not re-measured on this tree: the
pool figures in c1cce2a's message (100 actors, 800 requests across 3 s before
and 67 s after under refused authentication; 400 actors, busiest second 400 to
15 with 60 s of start jitter) were taken on the pre-dev base b77e5bb.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-F` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
