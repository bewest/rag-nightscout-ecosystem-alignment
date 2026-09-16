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

# Review packet — P0-A (PR #8739)

**bf/alarms - PR #8739, BF-28, BF-29, BF-31**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/alarms` |
| base | `origin/dev@a8888f0d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-A` is the measurement |
| semver | `major` |
| register entries | `BF-28`, `BF-29`, `BF-31` |

## What this changes

3 commits. lib/plugins/insulinage.js, lib/plugins/index.js,
lib/api/googlehome/index.js, lib/api/alexa/index.js. Zero file overlap with
any other Phase 0 branch.

## Why that semver

GT4: the third commit REMOVES per-request locale handling from POST
/api/v1/alexa and POST /api/v1/googlehome. A request carrying request.locale
used to be answered in that language and now is answered in the server's
configured language. The removal is correct - ctx.language.set and
moment.locale are process-global, so one request re-languaged every later
request - but it is a capability removal on an HTTP endpoint with no
replacement in the same changeset.

## What an operator would notice

> Three alarm fixes. The "insulin reservoir change overdue" reminder could
> never appear at all and now can. If you list a plugin by its file name in
> ENABLE - for example "cannulaage" instead of "cage" - Nightscout used to
> switch it off without telling you, and now says so and names the plugin it
> thinks you meant. These do not change when any alarm fires, only whether
> it can. This is not medical advice; if an alarm you rely on has been
> silent, talk it through with your care team as well as checking your
> settings.

## Who should review this, and why

maintainer, plus one reviewer who has never merged their own PR in this stack
(the governance finding - 100 self-merged PRs, zero human reviews). OPENED
2026-09-16 as PR #8739, base dev. THIS ONE NEEDS AN EXPLICIT YES, not only a
review: it starts an alarm that has never fired in any deployment, with no
grace period, and it removes per-request locale from two HTTP endpoints with
no replacement. Dropping 5dcf783f leaves a clean minor, which is the option to
offer if Phase 0 should land as 15.1.0.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/alarms`** &nbsp;·&nbsp; kind: `static`

bf/alarms has not fallen behind origin/dev

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/alarms >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`TEST=insulinage npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-alarms`

BF-28, measured. 5 passing, and E3 ABLATED it - with lib/plugins/insulinage.js
put back to origin/dev the same file gives 3 passing / 2 failing. Database-
free: re-run with the mongo URL pointed at a dead port, still 5 passing.

**`TEST=plugins npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-alarms`

BF-29, measured. 13 passing, and E3 ABLATED it - with lib/plugins/index.js put
back to origin/dev the same file gives 5 passing / 8 failing. Database-free.

**`TEST=api.alexa npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-alarms`

BF-31, the branch's own test for the locale removal. 4 passing, MEASURED
2026-09-16 - the previous text here said it CANNOT BE RUN IN THIS ENVIRONMENT
because nothing listened on port 27034. That was a fact about the machine and
it was fixed by starting a mongod on 27034, not by changing the branch.
ABLATED: lib/api/alexa/index.js restored to origin/dev gives 3 passing / 1
failing.

**`TEST=api.googlehome npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-alarms`

BF-31's sibling. 2 passing, MEASURED 2026-09-16 on the same mongod. ABLATED:
lib/api/googlehome/index.js restored to origin/dev gives 1 passing / 1
failing.

**`test -f externals/work/crm-bf-alarms/node_modules/.cache/_ns_cache/public/js/bundle.app.js`** &nbsp;·&nbsp; kind: `static`

GT1 found this worktree is the only one missing the client bundle, and that
absence produced a seventh test failure that looked like a defect. `npm run
bundle` in that worktree fixes it.

**`git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/alarms | grep -q 5dcf783fdbb20188c378`** &nbsp;·&nbsp; kind: `network`

the branch behind PR #8739 is on the remote at the exact tip this item was
measured against. Read-only. Verified 2026-09-16.

**`node tools/queue/gates/pr-body-parity.js --only 8739`** &nbsp;·&nbsp; kind: `network`

the live body of PR #8739 still matches the file it was posted from. Bodies
drift in one direction - a correction gets written into the file first - and
the only previous record that one was owed was a sentence in a notes: field,
which is what let #8738 stay wrong in public for a day. It does NOT measure
whether the body is TRUE: parity with a wrong file is still parity, and every
figure in these bodies has been wrong at least once. NON-VACUITY, reproduced
2026-09-16: one altered file gives 1 failing, an empty body dir gives 6
failing. SKIPS with exit 0 when gh is unauthenticated.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- THE GATE THAT WAS HERE - `npm run test:unit` - ASSERTED LESS THAN IT
  LOOKED LIKE. It resolves to a 44-file brace list, it needs MongoDB
  (verifyauth x4 and API_SECRET x2 fail without it even on pristine dev),
  and tests/api.alexa.test.js and tests/api.googlehome.test.js - two of the
  four files this branch adds - are in NEITHER local script, so it never ran
  half the branch's own evidence. CI's `test-ci` runs all 159 files and does
  cover them; a gate that mirrors the local script is weaker than CI, not
  equal to it.
- Nothing exercises the ENABLE warning through a booted plugin registry. GT4
  had to hand-reconstruct the plugin-name list to test it, and a
  reconstructed registry is not the registry. Needs a boot-level test.
- Review and merge state of PR #8739 is upstream's, and cannot be gated from
  here without a GitHub API call. Tracked, not driven.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-alarms.md`](../../reports/phase0-pr-bodies/bf-alarms.md)
- [`docs/60-research/remedial/bf28-29-31-alarm-delivery-2026-09-15.md`](../../docs/60-research/remedial/bf28-29-31-alarm-delivery-2026-09-15.md)
- [`docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`](../../docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

THE TWO INTEGRATION GATES ARE NOW MEASURED, 2026-09-16, AND THE CAVEAT IS THE
SAME SHAPE AS THE BUNDLE GATE'S. api.alexa and api.googlehome had never been
run anywhere in this programme - the branch's own evidence for BF-31, the
commit that grades it major, was unexecuted. Nothing was listening on port
27034, which crm-bf-alarms' my.test.env names. A mongod was started on 27034
with a scratch dbpath and both gates went green (4 and 2 passing), each
ablated against origin/dev (3/1 and 1/1 failing). THAT MONGOD IS NOT
PERSISTENT: its dbpath is under this session's scratchpad and it dies with the
machine. Anyone who sees these two gates red should check for a listener on
27034 before reading it as a regression - green here is a property of the
branch AND of a running database, and only the first half travels. ---
Sequencing letter A. §7a items 5 and 6 are these commits; neither may be read
as making alarms safe to turn on under TENANCY_MODE=multi. STATE CORRECTED
2026-09-15 from ready-to-push to gate-not-met, by the manifest's own
definition: a declared gate fails. The failing gate is the client-bundle
check, and what it catches is a LOCAL worktree artifact, not a defect in the
branch - crm-bf-alarms is the only worktree missing
node_modules/.cache/_ns_cache/public/js/bundle.app.js, and that absence is
what produced the seventh test failure GT1 had to rule out by hand. `npm run
bundle` in that worktree clears it. The branch CONTENT is ready; this entry is
not a doubt about the three commits. It was not fixed here because crm-bf-
alarms belongs to another session and rule 5 forbids writing into a worktree
this session did not create. RESOLVED 2026-09-16 on the maintainer's
instruction: `npm run bundle` was run in crm-bf-alarms (webpack exit 0, 1.76
MB artifact), the gate passes, and the state is back to ready-to-push with all
5 runnable gates green. No commit was needed and the worktree is still clean -
the artifact is build output under node_modules, not tracked content. CAVEAT
ON WHAT THIS GATE MEASURES: it tests for a LOCAL build product, so it goes red
again in any fresh worktree or after `npm ci`, and green here is NOT a
property of the branch. Anyone who sees it red elsewhere should run `npm run
bundle` before reading it as a regression.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-A` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
