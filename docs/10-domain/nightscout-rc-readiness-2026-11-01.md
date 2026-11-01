# Nightscout 16.0.0 release-readiness triage (2026-11-01)

This is a dated readiness snapshot, not a release announcement. Official `dev`
was `497d08c94c0a583f056fe487d172a4634fc4a1d4`, after
nightscout/cgm-remote-monitor#8894, when queried on 2026-11-01.
The latest published release remains 15.0.9. No named 16.0.0 RC was observed.
Changes from this preparation use separate worktrees; the concurrently edited
alignment `main` checkout is not modified.

## Hosted CI and staging

`gh run list --repo nightscout/cgm-remote-monitor --branch dev` showed both CI
runs on this head failing: [41326509441](https://github.com/nightscout/cgm-remote-monitor/actions/runs/41326509441)
and [41326514941](https://github.com/nightscout/cgm-remote-monitor/actions/runs/41326514941).
Both CodeQL runs passed. Staging
nightscout/cgm-remote-monitor#8824 reports failures in `Run Tests (22.23.4, 8.0)`
and its aggregate `Tests pass`; the other test jobs passed. Image publication
was skipped, so a moving `latest_dev` image must not be assumed to contain this
head. The previous identity merge `3c773ee5` also has two failed CI runs.

`gh api repos/nightscout/cgm-remote-monitor/branches/master/protection` still
requires `Run Tests (22, 6)`, `Run Tests (22, 4.4)` and `Run Tests (24, 6)`,
plus one approving review. The 4.4 job no longer runs. This is a repository
settings blocker, not another source-code defect: the maintainer's already
recorded decision is to require `Tests pass` and one approving review.
No protection settings were changed and no checks were bypassed.

### CI repair prepared

nightscout/cgm-remote-monitor#8896 is open and mergeable at
`42410a4b58bff3e19f5711f7f8d6259ef16e6213`, based on `497d08c9`.
The patch fixes two test assumptions, without changing production code or
removing gates:

- The cached-read test locates its seeded record by identity rather than
  assuming it is first in the cache or response
  (`externals/work/rc-ci-20261101/tests/api.entries.test.js:648-685`).
- The start-path comparison accepts the equivalent successful identifier-index
  startup states `built` and `present`
  (`externals/work/rc-ci-20261101/tests/start-paths.test.js:119-127`).

Agent-reproduced validation: 37 focused entries integration tests passed;
targeted lint, the 455-file / eight-tier map and whitespace checks passed.
Local start-path reruns timed out before `/api/versions`; they are not counted
as a local pass. Hosted PR CI subsequently passed every test lane, all three
browsers, CodeQL, npm 12 build, both Docker validation architectures and
`Tests pass`. Publishing jobs were skipped by design on the PR.
The entries patch mirrors prior unpublished work; that existing worktree
was left untouched.

The PR is unmerged, so official dev remains red at the snapshot head.
Merge the CI repair through normal review and verify post-merge CI/image
publication rather than treating the feature PR result as an integrated pass.

## Candidate and issue dispositions

These are metadata/review dispositions, not claims that every open PR was
executed or fully code-reviewed. The current open list and issues updated
since 2026-10-21 were queried with `gh pr list` and `gh issue list`.

| Item | Evidence at this snapshot | Disposition |
|------|---------------------------|-------------|
| nightscout/cgm-remote-monitor#8892 and nightscout/cgm-remote-monitor#8894 | Both merged; current dev includes the resend switch and unique index | Do not open another identity/batch PR solely because an older local branch remains. Verify the current integrated cohort and rollback gates. |
| nightscout/cgm-remote-monitor#8857 | Draft, `BEHIND`, head `5f6c1275`; earlier checks passed | Single-tenant registration remains an entry-bar candidate. Refresh base, settle recorded flag/dependency/value decisions and rerun gates before ready/merge. |
| nightscout/cgm-remote-monitor#8891 | Draft, `DIRTY`, head `744d1968`; earlier checks passed | Do not merge as an RC fix. Resolve conflicts, replay on the current head, decide the event trigger and release placement, and remeasure cost before leaving draft. The current resident single-tenant release does not depend on this prototype. |
| nightscout/cgm-remote-monitor#8855 | Crowdin branch `6a2e84ab`, 454 behind / 70 ahead of dev, `BEHIND`, mergeable, no checks returned | Refresh and review translations, preserving corrected source strings; no evidence of an RC blocker from this metadata alone. |
| nightscout/cgm-remote-monitor#8810 | APNs background-push work, 220 behind / 5 ahead of dev, `BEHIND`, mergeable; no review/comment evidence returned | Notification candidate, not a substitute for live APNs/Pushover acceptance. Refresh and review before inclusion; no merge on stale checks. |
| nightscout/cgm-remote-monitor#8829 | Restricted-token WebSocket failure reported on 15.0.9; no follow-up comments | Keep in the RC cohort: restricted subject token through a reverse proxy, REST plus WebSocket handshake/reconnect. Do not claim closed from other authentication fixes without reproducing this scenario. |
| nightscout/cgm-remote-monitor#8584 | Reporter confirmed full-day report restoration on 2026-10-29 after testing dev; nightscout/cgm-remote-monitor#8701 merged 2026-09-06 | Closure candidate for the maintainer, not a new fix PR. Confirmation is reporter-derived, not a live test by this preparation. |
| nightscout/cgm-remote-monitor#8884 | Request to enable Lithuanian in Crowdin | Translation administration, not a code/CI defect or demonstrated RC gate. |

Older feature PRs are not promoted into the RC by this triage. Existing release
allocation and safety gates remain authoritative.
Ahead/behind counts use `gh api repos/nightscout/cgm-remote-monitor/compare/<head>...<dev>`;
the API's `ahead_by` is dev's distance ahead of the candidate.

## Security integration

The two previously recorded pre-tag fixes are BF-72 and BF-161. Their older
private-fork tips were tested against 2026-10-27 dev, not today's identity and
storage tree. Preparation must merge current dev into each isolated private
branch, preserve the fix on the current storage paths, rerun regression and
integration gates, and verify private PR targeting before merge.

This public record deliberately contains no unpublished advisory payloads,
hostile inputs or new disclosure details. No public security branch, advisory
publication or security merge is authorized by the readiness snapshot.

## Callback fix prepared

nightscout/cgm-remote-monitor#8895 is open against `dev`, head
`647ee2657912296cd6c0c83fdc30d034051adbc5`, based on `497d08c9`.
It makes a successfully handled Pushover callback return 200 when its
in-memory receipt has expired or disappeared. The existing handler still
logs an unknown receipt; a known receipt still acknowledges its alarm.
The regression also covers a known receipt followed by a duplicate, with
exactly one alarm acknowledgment. Provider callback acknowledgment and alarm
acknowledgment are deliberately separate.

Agent-reproduced evidence: 54 notification tests and 59 tests through the
integration-tier wrapper passed on Node 22.23.4 with isolated MongoDB 8.0.29;
targeted ESLint, tier map and whitespace checks passed. Input probes retained
400 for malformed/null JSON and 413 for oversized JSON. A request without a
parsed body retains the existing 500 behavior; this patch does not broaden
request parsing.

Source locations on the new PR head:
`externals/work/rc-pushover-20261101/lib/api/notifications-api.js:13-17`
and `externals/work/rc-pushover-20261101/tests/notifications-api.test.js:90-140`.
The existing missing-notification diagnostic is at
`externals/work/rc-pushover-20261101/lib/server/pushnotify.js:87-88`.
Hosted CI was still running at the initial post-publication read; CodeQL,
npm 12 build and both Docker validation architectures had passed. No live
provider/phone check was reproduced and no merge occurred.
At the later read after the CI repair PR completed, all callback PR test and
validation checks had also passed; only publishing jobs were skipped by design.
It remains open and mergeable. This does not replace CI on the eventual
combined dev/security head.

## Remaining RC acceptance

Before tagging: green CI on the integrated head; the staging protection change
and approving review; the two private security integrations and coordinated
release-time publication; live Pushover and APNs delivery/acknowledgment checks;
a real-rig dev soak; identity/client cohort and rollback evidence; release notes.
Focused offline callback tests cannot establish vendor delivery, and an
individual PR's green checks cannot establish the final combined tree.

## Later integration state (2026-11-01)

GitHub now reports nightscout/cgm-remote-monitor#8895 merged at 17:45:01Z as
`bb85d10fba9500d9e7a8a728cb4d93d557803bc6`, followed by
nightscout/cgm-remote-monitor#8896 at 17:52:18Z as
`61eb37335954ae42c91345a0823bd67331025165`. Earlier "unmerged" statements above
describe the preparation snapshot. This session did not perform those merges.
Official dev is now `61eb3733`; CodeQL passed on it. CI runs 41333672054 and
41333677576 were still in progress at this read, so post-merge test/image
publication success is not yet claimed.

Both security integration branches were prepared and pushed only to their
existing private repositories, incorporating this newer dev head:

| Fix | Private topic branch | Head |
|-----|----------------------|------|
| BF-72 | `workspace/rc-security-regex-20261101` | `7d7416e837afe0f1b17ce030e2a927530a06bf4e` |
| BF-161 | `workspace/rc-security-slice-20261101` | `3dbd25534e0c54a90af3fbecf51a741268e154ca` |

Agent-reproduced combined focused validation passed 402 tests; lint and tier
checks passed. Full-suite acceptance remains inconclusive because of local
MongoDB failures. No private PR was created: GitHub rejected the proposed
private snapshot base, and the advisory repositories report as standalone
private repositories rather than forks. Branch preparation is therefore
persistent, but security merge/publication readiness remains blocked by private
integration mechanics and final full-suite validation. No public security
branch or PR was created.

### Final preparation handoff

The later GitHub read reports both CI workflows on `61eb3733` successful
(41333672054 and 41333677576), together with both CodeQL runs. The current
dev CI blocker is cleared; this does not clear staging protection or live
acceptance gates.

Security worktrees retained:
`externals/work/crm-rc-security-regex-20261101` and
`externals/work/crm-rc-security-slice-20261101`. Both prepared heads contain
`61eb3733`. The local combined candidate was `b52360fd54343b72b6260d6ae4d5480e6e73ea40`,
merging BF-161 into BF-72; `lib/api/entries/index.js` auto-merged without
manual conflicts. The temporary combined worktree was cleaned up after testing.

The 402-test Mocha selection covered regex limits, entries, treatments, query,
Mongo storage, API v3 search/filter/find/modify utilities and entry-query
permissions, using the repository hooks and `--fail-zero`. `npm run lint`
and `npm run test:tiers` passed (456 files / eight tiers; lint warnings, no
errors), as did the existing BF-72 static gate. Full-suite runs are **not a
pass**: local Mongo test services disappeared or exited 139, and a long retry
was stopped. No security assertion failure was established by those attempts.

Private PR attempts returned HTTP 422, `PullRequest.base`, `code: invalid`,
for snapshot bases `workspace/upstream-dev-497d08c9` and
`rc-base-dev-497d08c9`. The existing private dev branches are stale; neither
matches `61eb3733`. The integration agent's advisory API requests returned 404,
while its repository metadata reported private standalone repositories.
Those access/routing results do not prove the advisories have no association.
No stale-base PR was opened and no existing private refs were moved.

The safe next step is for an authorized maintainer to use the upstream
Security / Advisories workflow, confirm the advisory-linked private patch
repository and current dev target, and bring the prepared patches into that
path. Final full-suite validation remains necessary before security merge;
advisory publication stays coordinated with the release. Do not solve this
private integration blocker by opening a public PR.
