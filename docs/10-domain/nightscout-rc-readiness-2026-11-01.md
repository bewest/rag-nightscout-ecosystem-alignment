# Nightscout 16.0.0 release-readiness triage (2026-11-01)

**Historical snapshot:** for the November 2 cohort update, removal of the 4.4
protection requirement, new #8829 reporter evidence and both maintainers'
non-reproduction, see the [current ecosystem/acceptance record](nightscout-v16-ecosystem-deep-dive.md).
The dated observations below are retained, not current gate claims.

This is a dated readiness record, not a release announcement. Official `dev`
is `61eb37335954ae42c91345a0823bd67331025165`, after #8895 and #8896 merged.
The latest published release remains 15.0.9. No named 16.0.0 RC was observed.
Publication is prepared from a clean origin-main integration worktree; the
concurrently edited local alignment `main` checkout is not modified.

## Current test totals and release scope

The successful [dev push CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/41333672054)
and [staging PR CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/41333677576)
on `61eb3733` report the same suite totals, read from hosted logs:

| Suite counted once | Passing | Pending |
|--------------------|---------|---------|
| Top-level `test-ci` | 6,323 | 3 |
| Separate client-core | 319 | 0 |
| Browser suite, one browser | 684 | 0 |
| Installed Connect regressions | 334 | 0 |
| Sum of non-repeated suite counts | 7,660 | 3 |

This sum is not an identity-level deduplication across suites. Each hosted
matrix reports 31,208 passing and 13 pending executions because suites repeat
across runtime/database/browser combinations and compatibility jobs. The three
top-level pending cases concern mixed valid/invalid batches and two Ajv
dependency-resolution cases. The 402 private-security focused tests are a
different selection, not the full release suite.

The scheduled storage seam, write steps, harness and resident views have merged
(nightscout/cgm-remote-monitor#8854, nightscout/cgm-remote-monitor#8861,
nightscout/cgm-remote-monitor#8863, nightscout/cgm-remote-monitor#8870,
nightscout/cgm-remote-monitor#8874, nightscout/cgm-remote-monitor#8875,
nightscout/cgm-remote-monitor#8881, nightscout/cgm-remote-monitor#8886).
Identity matching, re-send and unique-index changes are also in dev
(nightscout/cgm-remote-monitor#8879, nightscout/cgm-remote-monitor#8888,
nightscout/cgm-remote-monitor#8889, nightscout/cgm-remote-monitor#8890,
nightscout/cgm-remote-monitor#8892, nightscout/cgm-remote-monitor#8894).
ID-BATCH is included: nightscout/cgm-remote-monitor#8889 added per-item API v1
replies and `Nightscout-Write-Results: items`
(`externals/cgm-remote-monitor/lib/api/shared/batch-reply.js:8-43`,
`externals/cgm-remote-monitor/tests/api.id-batch-replies.test.js:31`, at
`61eb3733`). Earlier local `feat/id-batch` follow-up notes are historical,
not evidence that this feature still awaits a merge.
Modernization nightscout/cgm-remote-monitor#8605 and the opt-in modern theme
nightscout/cgm-remote-monitor#8831, with drawer correction
nightscout/cgm-remote-monitor#8882, are merged. These are no longer a queue of
implementation PRs to merge before beginning release acceptance.

Draft registration nightscout/cgm-remote-monitor#8857 and nonresident profiles
nightscout/cgm-remote-monitor#8891 remain placement/decision candidates, not
automatic pre-tag blockers. The separate frontend/platform proposal
nightscout/cgm-remote-monitor#8541 has failed checks; it is not the already
merged modern theme or modernization work.

## Merged callback fix: BF-227 / BFQ-227

#8895 merged at 2026-11-01 17:45:01Z as
`bb85d10fba9500d9e7a8a728cb4d93d557803bc6`. A handled Pushover callback now
returns HTTP 200 even when its in-memory receipt has expired, been cancelled,
disappeared on restart, or already been acknowledged. This prevents retries
for a no-op callback. A known receipt still acknowledges its alarm exactly once;
the unknown-receipt diagnostic remains unchanged. Provider callback
acknowledgment and active alarm acknowledgment are separate operations.

The final patch changes only the callback route and its regression tests:
`externals/cgm-remote-monitor/lib/api/notifications-api.js:13-17` and
`externals/cgm-remote-monitor/tests/notifications-api.test.js:90-140`,
at the integrated head above. The retained diagnostic is at
`externals/cgm-remote-monitor/lib/server/pushnotify.js:87-88`.
The 15.0.9 callback route still returns 500 when `pushoverAck` returns false,
so BF-227 affects the shipping release; merged to dev does not mean released.

Recorded local validation: 54 targeted notification tests and 59 tests through
the integration-tier wrapper passed on Node 22.23.4 / MongoDB 8.0.29;
targeted lint, tier-map and whitespace checks passed. Input probes retained
400 for malformed/null JSON and 413 for oversized JSON. A request without a
parsed body retains the existing 500 behavior; request parsing is not expanded.
No live provider/phone check is claimed.

## Merged CI hygiene: RT-CI-FIXTURES-8896

#8896 merged at 2026-11-01 17:52:18Z as
`61eb37335954ae42c91345a0823bd67331025165`. The final PR diff, body and commits
and the canonical merged files were read, rather than relying on the initial
patch summary. Its final head included an intervening dev merge; the patch
still changes only two test files, with no production-code change:

- `externals/cgm-remote-monitor/tests/api.entries.test.js:648-686` finds the
  cached seed by `_id`, requests the cache's entry count, finds the served seed
  by glucose/date, and checks the same cached record remains free of `mills`
  after the read. It no longer assumes either array's first item is the seed.
- `externals/cgm-remote-monitor/tests/start-paths.test.js:119-128` normalizes
  only successful identifier-index states `built` and `present` to `ready`
  for comparison. Other states remain distinguishable; production status
  responses are unchanged.

Recorded local evidence: 37 focused entries integration tests passed, as did
lint, the 455-file / eight-tier map and whitespace checks. Local start-path
reruns timed out before `/api/versions` and are **not a local pass**. Full
hosted PR checks passed, including start paths. Canonical merged-source
inspection found no additional production change or demonstrated follow-up
regression in this final diff. The earlier unpublished mirrored work remains
untouched. This is a release task, not a duplicate backfix-register defect.

## Integrated CI and image publication

Both CI runs on `61eb3733` passed: 41333672054 (`push`) and 41333677576
(`pull_request`). Both CodeQL runs, 41333672065 and 41333677478, also passed.
The job results were read: the push run built amd64 and arm64 images by digest
and successfully published the multi-architecture Docker Hub image. Its log
records `dev_61eb37335954ae42c91345a0823bd67331025165` and `latest_dev` at
18:04Z, manifest digest
`sha256:623f72a1dcd2437a8e6e1715d205c9fba174cf5ca77b8c97d9bdf320b3bc2f2d`.
The PR run skipped publishing; the push run skipped the release-image job.
This is a development image, not a tagged release or named RC, and `latest_dev`
is moving. No deployment or live-transport success follows from these jobs.

**Historical preparation evidence, superseded:** dev `497d08c9` had failed CI
runs 41326509441 and 41326514941 (both CodeQL runs passed). #8895 and #8896
were initially open; the repairs and subsequent merged-head checks above
supersede that red/unmerged state. The earlier identity head `3c773ee5` also
had two failed CI runs. Those failures are retained as historical evidence,
not current blockers.

## Staging and candidate dispositions

The recorded `master` protection still requires `Run Tests (22, 6)`,
`Run Tests (22, 4.4)` and `Run Tests (24, 6)`, plus one approving review.
The 4.4 job no longer runs. This is a repository-settings blocker; the
maintainer's recorded decision is `Tests pass` and one approving review.
No settings were changed or checks bypassed; green dev CI does not clear it.
Rechecked after the publication request: master still has those three checks
and one review; dev requires only `Run Tests (24, 6)`, with no review requirement.
Staging nightscout/cgm-remote-monitor#8824 is `MERGEABLE` but `BLOCKED` and
`REVIEW_REQUIRED`; the 4.4 check is absent, not failing.

The following candidate metadata is the **earlier 2026-11-01 triage**, not a
new check or a claim of complete source review after the two merges:

| Item | Recorded evidence | Disposition |
|------|-------------------|-------------|
| #8892 / #8894 | Merged resend switch and unique index | No duplicate identity PR; verify integrated cohort and rollback gates. |
| #8857 | Draft, behind dev; earlier checks passed | Refresh base, settle recorded flag/dependency/value decisions and rerun gates. |
| #8891 | Draft, conflicting with dev; earlier checks passed | Do not merge as an RC fix; resolve conflicts, release placement and event-trigger/cost gates. |
| #8855 | Crowdin branch behind dev, no checks returned | Refresh/review translations; metadata alone establishes no RC blocker. |
| #8810 | APNs background-push candidate behind dev | Refresh and review; not a substitute for live APNs/Pushover acceptance. |
| #8829 | Restricted-token WebSocket failure on 15.0.9; no follow-up confirmation | Keep restricted-subject-token REST plus WebSocket handshake/reconnect through a reverse proxy in the cohort. Do not close from green CI alone. |
| #8584 | Full-day report restoration confirmed on dev after #8701 | Maintainer closure candidate, not a new fix or a reproduced live test here. |
| #8884 | Lithuanian Crowdin request | Translation administration, not a demonstrated RC gate. |

## Security integration: BLOCKED, private

BF-72 and BF-161 remain pre-tag requirements. Both retained private fix
branches now contain `61eb3733`; combined focused validation passed 402 tests,
with lint and tier checks passing. Full-suite acceptance is **inconclusive**
because the local MongoDB service exited/disappeared. Private PR targeting
was rejected for an invalid base. A subsequent REST/GraphQL check found no
open private PR. This is a private routing/validation task, not an outstanding
scope decision or a reason to delay starting the merge workflow. An authorized
maintainer must use the advisory's **Compare & pull request** workflow with the
prepared current-dev patch; private CI/protection enforcement is disabled.
The stale private base must not be mistaken for the current public dev base.
There was no security merge or advisory publication.

Only previously public mechanism-level status is recorded here: no new
advisory payloads, private branch identifiers or disclosure details.
Green public dev CI does not validate the eventual integrated security tree.

## Remaining RC acceptance

Before tagging: staging protection and approving review; private BF-72/BF-161
integration, final full-suite/hosted checks and coordinated release-time
publication; live Pushover and APNs delivery/acknowledgment/cancel checks; a
real-rig dev soak; identity/client cohort and rollback evidence; release notes.
Public integrated CI is now met on `61eb3733`, but must be rerun after further
integration. No named RC, upstream merge, setting change or issue closure is
performed by this documentation update.

The order is: prepare/merge the private patches through the advisory workflow;
validate the final combined tree; pin the candidate and development image;
collect live alerts, client cohort, quiet-period and upgrade/rollback evidence;
finish release notes and the runtime-floor policy waiver; clear staging
protection/review and then tag/publish with coordinated advisory disclosure.
The original live/soak gates remain, but no new backend/frontend modernization
implementation phase is needed to start them.
