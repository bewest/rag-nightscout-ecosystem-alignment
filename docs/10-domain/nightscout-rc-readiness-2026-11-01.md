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
and `externals/work/rc-pushover-20261101/tests/notifications-api.test.js`.
Hosted CI was still running at the initial post-publication read; CodeQL,
npm 12 build and both Docker validation architectures had passed. No live
provider/phone check was reproduced and no merge occurred.

## Remaining RC acceptance

Before tagging: green CI on the integrated head; the staging protection change
and approving review; the two private security integrations and coordinated
release-time publication; live Pushover and APNs delivery/acknowledgment checks;
a real-rig dev soak; identity/client cohort and rollback evidence; release notes.
Focused offline callback tests cannot establish vendor delivery, and an
individual PR's green checks cannot establish the final combined tree.
