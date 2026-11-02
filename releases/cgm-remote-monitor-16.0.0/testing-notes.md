# Nightscout 16.0.0 — testing notes for the release candidate

**Working cohort guide, 2026-11-02. Not a formal named-RC announcement.**
Informal testing has already started: the maintainer reports multiple testers
have run the code for over 24-48 hours. No named v16 RC is published. Current
official dev is `61eb37335954ae42c91345a0823bd67331025165`; record the exact
commit/image each tester actually ran rather than assuming it is this one.
The measured automated runs remain in the
[integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md);
release scope is in [contents.md](contents.md).

The maintainer reports that contributed patches were already tested before
submission and are high-confidence; live testers will inform further acceptance.
The rows below reconcile that existing confidence with build/scenario evidence,
not a requirement to restart all testing or a claim that the patches were untested.
Live cohort/operational execution belongs in separate sessions; this session
clarifies contracts and reconciles the records.

## Part 1: people using a site

Use the connected apps and displays you normally use. Report missing readings,
duplicates, unexpected displayed values, browser reconnect failures or alerts
that did not arrive or stop as expected. Include app/server versions, display
units, approximate observation interval and what happened, without personal
records, credentials or screenshots containing health data.

Check your usual phone and desktop views, including an optional modern theme
only if you chose it. Keep independent device alerts enabled; do not rely on
an experimental Nightscout build as your only alarm source. This is not dosing
advice. Do not create test treatments on an active-care site.

## Part 2: operators and app authors

Collect a cohort row for AAPS (include 4.0.0 master/client roles and existing
supported versions), Loop, Trio, xDrip+, a follower and an mmol/L site.
Multiple roles can be covered by one setup, but label each outcome separately.

| Evidence field | What to record |
|---|---|
| Server | SHA, immutable image tag/digest, Node/MongoDB versions; do not use `latest_dev` alone |
| Client/environment | App version/build, API v1/v3/socket, role/permissions without tokens, browser/proxy where relevant |
| Configuration | Units and relevant `WRITE_*`/strict-settings modes; default versus opt-in |
| Interval | Start/end and build changes; distinguish elapsed time from confirmed scenario coverage |
| Outcome | Scenario, expected/observed result, pass/fail/not exercised, sanitized issue/reference |
| Candidate transition | Previous build, new final/security-integrated build, affected checks repeated |

Capture ordinary uploads and reads, stable record identity on re-send, reconnect
and backfill, time/unit display, deleted-record behavior, and whether queues
retry or lose refused items. Exercise writes, conflicting identities and
partial-refusal cases only on a disposable site with synthetic records.
For API v1 verify the legacy array without opt-in separately from the
`Nightscout-Write-Results: items` envelope. Test AAPS strict-settings and
non-default rejection modes separately; do not enable them on every cohort.

Operator-led live checks must record Pushover emergency delivery,
acknowledgement, cancellation and duplicate-window behavior, and APNs delivery
to a phone. Record service/scenario/build/outcome, not credentials or patient
payloads. Automated callback tests are not a substitute.

Rehearse backup, upgrade and rollback on a disposable deployment, including
identifier-index startup with duplicates. `WRITE_IDENTIFIER_INDEX=off` keeps
an existing index; verify the documented `drop`/rollback sequence explicitly.
After security integration, pin the final tree/image and repeat affected
acceptance checks. Earlier cohort observations remain useful as earlier-build
evidence, not automatic acceptance of the new tree.

**#8829 is nonblocking by maintainer decision (November 2).** Its reporter
reports persistence on dev, but neither maintainer reproduced it and many DIY
and production/service environments work (maintainer report). Keep a sanitized
browser/proxy/role comparison as separate follow-up; do not claim a general
regression, root cause or a fix.

The pre-tag live-alert, final-tree and cohort/rollback gates remain. No completed
cohort row or final-candidate approval is asserted by this guide.

**Contributor preparation update:** BF-227 / #8895 fixes late, duplicate or
expired Pushover callbacks returning 500 for no-longer-held receipts. Known
alarm acknowledgment remains once-only and the diagnostic is unchanged.
Recorded local tests passed 54 targeted / 59 integration-tier cases.
#8896 repairs entries fixture ordering and compares only successful index
`built`/`present` states as equivalent; 37 focused entries tests passed.
The local start-path rerun timed out before `/api/versions` and is not a pass.
Full hosted PR and integrated-dev CI/CodeQL passed; the push workflow published
the development image, not a release. See integration R19/R20 and
[current readiness](../../docs/10-domain/nightscout-rc-readiness-2026-11-01.md).

For the eventual named-RC call, retain live Pushover emergency delivery,
acknowledgment, cancel and duplicate-window checks, and APNs delivery to a
phone. Offline callback tests do not satisfy these. A real-rig soak, representative
REST plus WebSocket/reconnect, identity cohort and rollback remain required;
private BF-72/BF-161 acceptance is pending. #8829 itself is not a release gate.
Continue existing informal testing; a formal named-RC call should identify its
immutable build. Do not close #8829 from green CI alone.

<!--
  HISTORICAL CONTRIBUTOR PREPARATION (before the November 2 guide above).
  Earlier "no tester call" wording below is not a claim that informal testing has not started.
  The sections this release will need, from
  contents.md as of dev eb72a1d3:

  Part 1 (people who use a site; plain language, no dosing advice, talk to the care team):
  - the Careportal Bolus Wizard and the Bolus Wizard Preview on a site whose profile is in the
    other units from the display (BF-172, BF-173), and choosing a profile other than the active one
    in the Bolus Wizard (BF-174);
  - the opt-in THEME=modern dashboard (#8831), on a phone and a desktop;
  - a snooze chosen on a page that is not signed in (#8816);
  - the glucose distribution report and the Loopalyzer (#8812, #8808).

  Part 2 (people who run a site, or write tools):
  - the Node floor: the server refuses to start outside <NODE_RANGE>, and the message it prints;
  - the legacy Dexcom Share and MiniMed CareLink bridges are removed; leftover bridge settings stop
    the site with a page naming the replacements; Dexcom Share through nightscout-connect;
  - IMPORT_CONFIG on a production install (BF-176, fixed by #8834; a dev Docker image published
    2026-10-25 between 17:15Z and 17:53Z has the crash);
  - MongoDB 5.0 through 8.0 (README), with the edge versions 5.0 and 8.0;
  - notes or treatments with unusual markup: sanitize-html 2.18.1 (#8835) stores one malformed
    textarea-then-image input differently (contents.md, For the release notes);
  - AndroidAPS NSClient v1 and the standalone NSClient app: zero temps and cancels within 2 s (BF-09);
  - whatever cut 2 adds, if it ships in 16.0.0: page bundles and the boot sequence, and any
    third-party plugin that hooks into the page.

  Added 2026-11-01 (session -81, dev f54941b5), Part 2, from #8889 (ID-BATCH reply format and
  ID-STRICT-V1):
  - API v1 batch POSTs (treatments, entries, devicestatus, profile, food, activity) sent with
    `Nightscout-Write-Results: items` (or `?results=items`) answer one result per item sent, in
    order; without it the reply is the array it was before. An uploader that sends a batch with
    one bad item should see that item refused in its slot and the others stored;
  - `WRITE_IDENTIFIER=strict` now applies to API v1 too: an item whose `identifier` is null, not a
    string, empty, over-length or a placeholder is refused with 400 in its slot, the rest of the
    batch is written, and a `Warning: 299` counts the refused items (every item refused: 400).
    With `WRITE_IDENTIFIER` unset or `lenient`, API v1 still drops such an identifier and stores
    the item;
  - under the opt-in, a profile re-send that needs `api:profile:update` is refused 403 in its slot
    rather than failing the batch.
  Nothing to test for #8875 (ST-VIEWS ships unwired) or #8881 (test harness only).
  Added 2026-11-01, Part 2, from #8879/#8890/#8886/#8892 (identity matching, compatibility A/B,
  write-step release 2 and the resend switch):
  - a re-send matched by `identifier` replaces the stored record by default on every collection
    and path, except v1/in-process entries; edits retain their route-specific merge/replace rules;
  - `WRITE_RESEND` defaults to `replace` and supports `merge-except-treatments`, `acknowledge`
    and `refuse`; `WRITE_DELETED_RESEND` defaults to `stay` and supports `revive`. Unset settings
    preserve 16.0.0 behavior. Per-client D20 overrides are not implemented;
  - API v3 and API v1 batch items retain their documented compatibility and opt-in reply behavior;
    no tester-facing call is appropriate until an RC is named.
  - #8894 merged to `dev` as `497d08c9`; `WRITE_IDENTIFIER_INDEX` supports `try`, `require`,
    `off` and `drop`. Verify startup with and without stored duplicates, counts-only reporting,
    and duplicate-key races under every `WRITE_RESEND` mode. Review rollback instructions before
    deploying or reverting.
  #8894 merged to `dev` on 2026-11-01 as `497d08c94c0a583f056fe487d172a4634fc4a1d4` from head
  `cf978f4`, after #8892's merge at `3c773ee5`.
  The PR body reports `npm test` 6,319 passing / 3 pending,
  63 focused identity-race/settings tests, passing tier and write-intent gates, and lint with 0
  errors / 20 warnings. Its hosted checks are complete and green, including the no-database,
  maintained-MongoDB, Node, Chromium, Firefox, WebKit, Docker validation, and CodeQL checks.
  The post-merge runs exposed separate failures: 41326509441 failed the cache-read test in
  `tests/api.entries.test.js` because it assumed its fixture was `ctx.cache.entries[0]`, while
  41326514941 failed D21 in `tests/start-paths.test.js` because equivalent index states appeared as
  `built` and `present`. PR #8896 merged fixes for both as `61eb37335954ae42c91345a0823bd67331025165`.
  Its required checks passed, including MongoDB 5.0/8.0, browser, Docker and CodeQL checks; both
  post-merge workflows (41333677576 and 41333672054) succeeded. No separate cache-test PR is needed.
  The batch-only matrix records 33 expected index-on/off differences for duplicate-key races and
  repeated identifiers under default, `WRITE_VALIDATION=reject`, and `WRITE_IDENTIFIER=strict`.
  The broader `--batch --no-idf` matrix is complete on merged `dev`: each off/try lane had 3,443
  cells and zero invalid cells on MongoDB 5.0.32 and 8.0.34. Off-versus-try produced the same 33
  expected batch differences (24 `batch-dupkey-mid`, 9 `batch-repeat-identifier`) on both versions;
  other differences were cache-only (15 cells on MongoDB 5, 5 on MongoDB 8). Cross-version
  differences were also cache-only (7 cells off, 11 try), with 929/929 wire frames captured and no
  unattributed frames or settle-bound hits. See `contents.md` and the
  [ID-BATCH design note](../../docs/30-design/platform/id-batch-design-note-2026-10-30.md) for
  the evidence boundaries. #8889 already shipped API v1 per-item replies and strict-ID behavior;
  #8894 carries the index-dependent batch race retry. The old local `feat/id-batch` worktree is
  not a separate release-critical PR and should not be rebased wholesale: the merged branch has
  per-item reply tests in `tests/api.id-batch-replies.test.js` and item-level race tests in
  `tests/api.batch-race-item-level.test.js`. Carry forward only a specific uncovered case if
  review identifies one.

  **Candidate scenarios to prepare, not issue until an RC is named.** Use an isolated test site
  with synthetic records; do not create test treatments on a production or active-care site.
  - Loop / NightscoutKit: upload and re-send an existing synthetic entry or treatment with the
    same identifier; verify HTTP 200, the legacy array shape and item count when the results opt-in
    is absent, the stored `_id` remains stable, and no duplicate is stored.
  - Other uploaders, such as Trio and xDrip+: verify their ordinary writes still receive success
    and their normal queues continue to behave; do not use a partial-refusal scenario with clients
    that mark every item uploaded on 2xx.
  - Site operators: on a disposable database seeded with duplicate identifiers, start with
    `WRITE_IDENTIFIER_INDEX=try`; confirm startup continues and duplicate counts are reported
    without values or automatic cleanup. Separately exercise `drop` and the documented rollback
    sequence on a disposable deployment.
  - Concurrency and non-default `WRITE_RESEND` modes remain controlled synthetic race tests, not
    a request for testers to manufacture conflicting records in live data.
  No RC is named, so these are contributor notes, not a call for testers.
-->
