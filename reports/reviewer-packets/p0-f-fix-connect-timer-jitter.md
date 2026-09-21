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
| base | `b77e5bb` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-F` is the measurement |
| semver | `minor` |
| register entries | `BF-08`, `BF-34` |

## What this changes

lib/backoff.js, lib/machines/cycle.js. 19 new tests, 135 pass / 0 fail, every
part reverted in turn and caught.

## Why that semver

GT4 argues for 0.1.0 rather than 0.0.14 and the argument is sound - option
precedence reversed, a changed default (use_random_slot:false ->
jitter:'equal'), a new throw on an unknown jitter mode, and duration_for
became non-deterministic. Each is breaking for a caller. It costs nothing
because ^0.0.13 matches only 0.0.13 and cgm-remote-monitor pins by tarball
anyway. RECORDED AS A DISAGREEMENT, not resolved - the tag as cut says 0.0.14.

## What an operator would notice

> When a CGM vendor's service is refusing requests, Nightscout's connector
> used to retry roughly 586 times faster than it was configured to, and
> every account retried at the same instant. It now waits the interval it
> was told to wait and spreads the retries out. COUNTER-INTUITIVE: after
> this fix a vendor outage will look like it recovers MORE SLOWLY, because
> the connector has stopped retrying in a burst that could not have worked.
> Your data is not arriving any later than it would have; the burst was
> never getting through. Also, on restart the connector no longer reaches
> the vendor all at once - both jitter windows default to 0, so nothing
> changes for anyone who does not set them.

## Who should review this, and why

maintainer - the sequencing document says land this one first if anything is
landed first. OPENED 2026-09-16 as nightscout-connect PR #68, base dev. One
approval there covers four PRs' worth of change; see notes.

## What was measured

**`npm test`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/nc-jitter`

135 passing / 0 failing; the connector suite needs no database

**`node -e "const b=require('./lib/backoff.js'); try { b({jitter:'wild'}); process.exit(1); } catch(e) { process.`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/nc-jitter`

the new throw on an unknown jitter mode is the observable half of the
precedence fix - if options were still being discarded, the bad mode would
never be read and this would not throw

**`git -C externals/nightscout-connect ls-remote --heads origin fix/connect-timer-jitter | grep -q c1cce2a2f9623e`** &nbsp;·&nbsp; kind: `network`

the branch behind nightscout-connect PR #68 is on the remote at the exact tip
this item was measured against. Read-only. Verified 2026-09-16.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Vendor rate limits are unmeasured (EXP-MT-051) and need real credentials,
  which rule 0 forbids here. T0.4 shipped CONNECT_START_JITTER_MS so the
  pool CAN be spread - but the window to set it is exactly the number that
  is unmeasured.
- Review and merge state of PR #68 is upstream's, and cannot be gated from
  here without a GitHub API call. Tracked, not driven - the same marker
  P0-T01 carries.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/fix-connect-timer-jitter.md`](../../reports/phase0-pr-bodies/fix-connect-timer-jitter.md)
- [`docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)

## Notes carried on the item

Sequencing letter F. Merging this in the connector repository ships it to
NOBODY - cgm-remote-monitor pins by tarball. P0-TAG and P0-PIN are what
deliver it. PR TARGET SETTLED 2026-09-16 (maintainer): base `dev`, head
`fix/connect-timer-jitter`, ONE PR carrying 11 commits. The earlier sequencing
text said base `origin/main`; that was a merge-base measurement mistaken for a
PR target. Measured: `origin/dev` 6dfc4f0 is TREE-IDENTICAL to `origin/main`
b394411 (`git diff origin/dev origin/main` empty - main is only the merge
commit of PR #26), and #64 and #67 both target `dev`, so `dev` is the release
line for this batch. `git rev-list --count origin/dev..fix/connect-timer-
jitter` = 11; 27 files, +1359/-309; trial merge into `dev` CLEAN. WHAT THAT
ONE PR APPROVES, STATED SO IT IS NOT DISCOVERED LATER: only c1cce2a is this
branch's work. Nine of the other ten commits belong to four other pull
requests - #64 (OPEN, -> dev), #65 (merged into `fix/dexcom-safe-logging`, NOT
into dev or main), #66 (OPEN, -> `fix/dexcom-safe-logging`), #67 (OPEN, ->
dev) - plus the integration merge b77e5bb (`origin/fix/modernization-debug-
logging`, no PR). So one approval covers four PRs' worth of change. The
maintainer chose this over stacking on `fix/modernization-debug-logging`
(which would reduce the PR to the single commit c1cce2a) with the tradeoff on
the table. It is written into the PR body rather than left implicit. WHY NOT
REBASE c1cce2a ALONE ONTO dev - measured, not assumed: `git cherry-pick
c1cce2a` onto origin/dev CONFLICTS in three files, one hunk each (README.md,
index.js, lib/builder.js); lib/backoff.js and lib/machines/cycle.js auto-merge
clean. The builder.js resolution would have to DELETE `logger: config.logger`,
which comes from 234d47c - i.e. the commit genuinely assumes #67 is in place,
exactly as its own message says ("The precedence fix cannot ship alone"). The
135-test and per-part-ablation evidence was taken on the stacked base and
would need re-taking. PR BODY CORRECTED 2026-09-16 before publication:
reports/phase0-pr-bodies/fix-connect-timer-jitter.md called those nine commits
"already-merged". They are not. Third draft of that block; the first two both
understated what the branch carries.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-F` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `59430336`.*
