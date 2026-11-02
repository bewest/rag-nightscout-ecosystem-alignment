# Nightscout v16 ecosystem and release acceptance

**Evidence refresh: 2026-11-02.** This is the current contributor-facing follow-up to
the [November 1 readiness snapshot](nightscout-rc-readiness-2026-11-01.md).
It records upstream metadata, maintainer reports and proposed next work separately.
It is not a release approval, clinical validation or a claim of a certified QMS.

## Release position

Official `dev` remains `61eb37335954ae42c91345a0823bd67331025165`.
The latest published release is still `v15.0.9`; no named v16 RC was returned by
the release listing. The **candidate under informal testing** is not the same
thing as a named, immutable RC. The maintainer reports multiple testers have
been using the code for over 24-48 hours and that AID authors are considering
changes. This establishes that cohort/rig testing has started, not which
versions, scenarios or outcomes have been accepted.

The merged backend storage/write/identity work, frontend bundles, dependency
refresh and optional modern dashboard are implementation outputs, not a remaining
modernization merge queue. Public CI on this head remains green: 6,323 passing /
3 pending in the top-level suite, or 7,660 passing / 3 pending counting each
reported suite once. These are the previously recorded hosted runs, not a new
test execution or proof of live acceptance.

BF-72 and BF-161 remain pre-tag private-security work. No new private inspection,
merge or disclosure is claimed here. The previously recorded 402 focused tests
do not establish full combined-tree acceptance. Integrate privately, validate the
resulting tree, and coordinate disclosure with availability of the fixed release.
Public dev testing can continue in parallel; testers need the exact new
commit/image and affected checks repeated after integration.

## Changes since the November 1 snapshot

| Evidence checked on November 2 | Meaning and next action |
|---|---|
| `gh api repos/nightscout/cgm-remote-monitor/branches/master/protection`: requires `Run Tests (22, 6)` and `Run Tests (24, 6)`, one approving review | The absent 4.4 requirement is **removed**. Both remaining lanes exist and are green. The recorded policy of requiring only `Tests pass` has not been applied in this snapshot. Review/staging remains in progress; do not keep reporting the obsolete check as the blocker. |
| nightscout/cgm-remote-monitor#8824 is open, `BLOCKED`, head `61eb3733`; its body still says 15.0.10 | Maintainer staging/review work continues. Update the upstream PR summary to v16 scope when preparing the release; no upstream edits were made here. |
| nightscout/cgm-remote-monitor#8829: reporter says the browser failure persists on dev, November 2 12:21Z; tested SHA/image not supplied | **Nonblocking, by maintainer disposition November 2.** Neither maintainer reproduced it; the maintainer reports it works in many DIY and production/service environments. Retain the reporter's observation and seek a sanitized client/server/proxy comparison and minimal reproducer as follow-up. No root cause, broad regression or closure is claimed. |
| nightscout/cgm-remote-monitor#8855: head `d3edc390`, `CLEAN`, returned test/CodeQL checks successful | Translation review/merge candidate, no longer accurately described as having no checks. Recheck after any base movement. |
| nightscout/cgm-remote-monitor#8897: head `2d46af3a`, mergeable, no checks returned | New week-to-week usage report proposal. Files include the report, test-data runner and bundle-budget test. Metadata/file-list inspection only, not a source review or evidence to admit it to v16. |
| nightscout/cgm-remote-monitor#8857 draft is mergeable; nightscout/cgm-remote-monitor#8891 draft conflicts | Registration and nonresident-profile proposals still need entry-bar decisions and current-tree validation. Draft/mergeable is not release acceptance. |
| nightscout/cgm-remote-monitor#8584 remains open with reporter-confirmed restoration | Maintainer closure candidate; no new fix or local reproduction claimed. |

No issue was closed, protection changed, external checkout advanced or upstream PR
merged by this documentation refresh.

## Compatibility without synchronized client releases

The aim is an explicit contract with independently deployable clients, **not**
a claim that v16 has zero behavior changes. The existing
[compatibility report](../../site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html)
classifies 2,803 changed cells with none unexplained in its measured scope.
It compares dev `497d08c9`, not the eventual security-integrated release, and uses
index `off` to seed duplicates. Index startup/races and live clients are separate evidence.

| Boundary | What is implemented / what needs agreement |
|---|---|
| Legacy v1 versus item results | Without `Nightscout-Write-Results: items` (or `?results=items`), retain the legacy reply slots/array contract. The richer `{items, documents}` reply is request opt-in. Do not silently switch existing uploaders to the new envelope. |
| HTTP success versus stored item | A 2xx batch response is not proof every item was stored. New clients must understand item outcomes before opting into refusal/retry behavior; test old clients that clear their entire upload queue on 2xx separately. |
| Re-send versus edit | Default `WRITE_RESEND=replace` may remove omitted fields on identity-matched live re-sends. `merge-except-treatments`, `acknowledge`, `refuse` are explicit site-wide choices, not per-client negotiation or a universal 15.0.9 compatibility switch. API v1/in-process entries and explicit edits retain path-specific rules. |
| Deleted records | Default `WRITE_DELETED_RESEND=stay` acknowledges an identity-matched re-send without reviving the record. Test retained client queues and deliberate edits separately; document any request to change this, not just the word "upsert". |
| Identifier validation | Unset `WRITE_IDENTIFIER` is **not identical** to explicit `lenient`: API v3 retains specific historical refusals. `strict` is opt-in. Keep default/lenient/strict distinct in author guidance. |
| Unique index and rollback | Default `WRITE_IDENTIFIER_INDEX=try` attempts the index and reports duplicate counts without cleaning up data or stopping startup for duplicates. `off` does **not** remove an index already built; `drop` does. Verify rollback on a disposable deployment before reverting server versions. |
| Additional AID fields | Optional fields should be documented and tested as optional across supported old/new endpoints. Do not make a new controller build mandatory merely because an uploader adds metadata. Unknown-field preservation/display behavior still needs endpoint-specific evidence. |
| Capability discovery | Registration/catalogue proposals are not merged capabilities clients can rely on. Do not require #8857 or invent capability flags on the released server. |

Canonical source read through GitHub at `61eb3733`:
`externals/cgm-remote-monitor/lib/api/shared/batch-reply.js:8-43` and
`externals/cgm-remote-monitor/lib/server/write-settings.js:7-68,129-144`.
The local corpus was not refreshed; these paths describe upstream files at that
commit, not an assertion that the local lockfile pin contains them.

### AID-author follow-up

AAPS **4.0.0 was released October 31**, including changed client pairing/roles,
multiplatform clients, units/concentration support and steps/heart-rate graphs
([release notes](https://github.com/nightscout/AndroidAPS/releases/tag/4.0.0)).
Include both existing supported AAPS installations and 4.0.0 master/client roles
in the cohort; do not equate AAPS release notes with proof of Nightscout interop.
Keep the non-default `API3_SETTINGS_STRICT_READ_ENABLED` follower caveat visible
in the v16 notes.

LoopWorkspace's published release is `v3.14.11`. NightscoutKit main at `6efa02d4`
includes optional `failureCode` and `bolusCalculation` fields:
`externals/NightscoutKit/Sources/NightscoutKit/Models/LoopStatus.swift:19-36,79-96`,
read at that upstream commit. This is additive client model evidence, not proof
that a given Loop release includes that exact dependency or that every server
read/write path round-trips those fields.

For each ambiguous behavior raised by an author, capture: route and collection;
client version; old/new request and response shape using synthetic data; stored
result; retry/deletion/permission expectations; whether the change is a bug fix,
opt-in extension or changed default; and the smallest discriminating test. Decide
its release placement before changing implementation or a public specification.
Keep missing/empty/null, merge/replace, batch partial success, identity, deletion,
units and event-time/receipt-time semantics explicit.

## Acceptance evidence and workstream handoff

**Maintainer priorities confirmed November 2:** this session clarifies compatibility
first, then reconciles acceptance records. Private security integration, live
alerts/cohort/upgrade/rollback execution, candidate-PR review/placement and #8829
follow-up belong in other sessions. Selective corpus repinning is not assigned
by this decision. No agents or upstream implementation work are launched here.

The maintainer reports that contributed patches had already been tested before
submission and are high-confidence; live testers will provide further feedback.
Record this as contributor/maintainer-reported prior validation, not as absent
testing. No patch-by-patch tested-build list or new cohort outcome was supplied
in this update, so the exact evidence rows remain to be collected by those
workstreams. That is record reconciliation, not a presumption that the patches
are defective or a new reason to stop the release process.

Use the [testing notes](../../releases/cgm-remote-monitor-16.0.0/testing-notes.md)
as a collection guide now; a formal tester announcement can follow a named RC.
Do not wait to collect already-running cohort evidence.

| Workstream | Bounded next output | Placement / owner status |
|---|---|---|
| Records and publication | Current status, draft release/tester notes, all five facets, validated queue/site, push main and verify Pages | This session. No upstream code or deployment changes. |
| Private security | BF-72/BF-161 private PR integration, combined-tree checks and disclosure/release coordination | Existing `BFQ-72`, `BFQ-161`; authorized maintainer/private session. |
| Cohort and operations | Version-pinned outcome matrix for AAPS, Loop, Trio, xDrip+, a follower and an mmol/L site; live Pushover/APNs; upgrade/rollback and final quiet period | Existing `RT-16-RIG-SOAK`, `RT-16-LIVE-ALARMS`, `RT-16-RELEASE`; testing underway, outcomes/owners to collect. |
| Restricted-token report | Sanitized environment comparison and minimal reproducer | `RT-16-TOKEN-8829`; separate **nonblocking** follow-up, decided by the maintainer November 2. Neither maintainer reproduced it; many DIY and production/service environments work. |
| Author contract clarification | Prioritized concrete behavior questions with synthetic fixtures and old/new expected outcomes | Proposed follow-up session; not authorization to change defaults or require synchronized client upgrades. |
| Release stewardship | Review #8855; decide #8897/#8857/#8891 placement; staging approval/protection policy; runtime-floor waiver; approve final notes | Maintainer decisions, not automatically new blockers. |
| Wider corpus refresh | Compare relevant tracked branches and changed files, then selectively repin/reverify affected references | Separate session. Metadata survey below does not justify blanket `make refresh`/`make freeze`. |

**Quality-record closure:** inputs (requirements, defects, maintainer decisions)
and outputs (specs/designs, merged PRs) have substantial traceability. Automated
verification is not the same as live validation. Still needed: final combined
tree, attributable cohort outcomes, disposition of unresolved reports/residual
risks, upgrade/rollback evidence, and maintainer approval. Elapsed time alone
closes none of those.

### Compatibility confidence: what the record supports

**Assessment:** strong automated and source-derived evidence supports the
intended interoperability of known client contracts without coordinated client
upgrades. This review identified no confirmed requirement for all known AID
clients to upgrade together. It does **not** establish unconditional backwards
and forwards compatibility for every client version, consumer, configuration or
future feature.

The [client catalogue](../../releases/cgm-remote-monitor-16.0.0/compat/clients.json)
has **15 implementations, 120 group-specific shape matches: 11 measured-tier,
109 read-tier**. As the comparison's
[limits](../../releases/cgm-remote-monitor-16.0.0/compat/page.yaml) explicitly
state, no client application ran against those matrix trees. Even a measured
shape match is not a live-app test. Client applications and actual live testers
may have separate evidence; do not erase or double-count it.

| Claim | Supported interpretation / boundary |
|---|---|
| Old clients with v16 | Legacy routes/reply shapes are retained without forcing adoption of new item envelopes. Known request shapes and extensive regression evidence support high confidence; intended identity/deletion/unit fixes still change some stored outcomes. |
| New clients with old Nightscout | A new client that stays within the old contract can remain interoperable. A new-only feature needs an actual supported capability or tested fallback; sending an opt-in header is not by itself proof an old server supports its envelope. This reverse-version claim is not demonstrated for every client by the server write matrix. |
| Forward-compatible data | Optional additional fields avoid an inherent lockstep requirement, but preservation and interpretation must be verified per endpoint. New metadata does not make old software understand a new behavior. |
| No defect-classified matrix cells | All differences are classified within the synthetic experiment; this is not a proof of no defects in deployment, readers, third-party plugins or future data. |

The catalogue itself maps intentional changes to known shapes: deleted-record
behavior, profile identity, reply handling and Temporary Target unit corrections.
These are not automatically broken clients. Some cells cross paths: for example,
the "API v3 client _id refused" group is matched to a Loop **v1** override shape
because the synthetic seed was written using v3. It is not evidence that Loop
now sends a forbidden body `_id` to v3. Read the seed, write path and outcome
together before turning a catalogue match into an incompatibility allegation.

Recommended release wording:

> Nightscout 16 is designed to preserve interoperability with existing clients
> without coordinated client upgrades. New item-result replies are opt-in.
> Identity, re-send, deletion and unit-handling fixes have documented behavior
> changes; non-default strict/rejection settings need separate client checks.

This qualifies the compatibility claim without downgrading confidence in already
tested contributions or inventing a new release gate.

## Corpus metadata survey (2026-11-02)

Queried all 45 lockfile entries in one corrected GitHub GraphQL request:
default branch/head/date, most recently created GitHub release, and up to three
most recently updated open PRs per repository. **44 public entries** are listed;
one nonpublic entry is intentionally excluded. The initial request used an
incorrect SSH-URL parse and was discarded; the corrected request returned no
repository/access errors. Redirected public repository names are shown as GitHub
returned them. No local checkout or `workspace.lock.json` pin was changed.

This is a metadata census, **not a source refresh** or a full PR/issue audit.
Default branches may differ from frozen development refs; a different SHA does
not by itself mean the frozen source is stale. "Release" below means a GitHub
release object, not npm publication, TestFlight availability or deployment.
In particular Connect's GitHub release list does not supersede the recorded npm
0.1.0 pin in Nightscout.

| Public repository | Default branch | Head | Commit date | Latest GitHub release observed |
|---|---|---|---|---|
| LoopKit/LoopWorkspace | main | `5efba88348` | 2026-10-25 | v3.14.11 |
| bewest/cgm-remote-monitor-rc-20261101 | master | `6893781f36` | 2014-11-06 | none |
| nightscout/nightscout-connect | main | `4dde1ecdca` | 2026-09-24 | v0.0.13 |
| nightscout/AndroidAPS | master | `f77abd9b82` | 2026-10-31 | 4.0.0 |
| nightscout/Trio | main | `0b29cd5341` | 2026-10-07 | v1.0.2 |
| zreptil/nightscout-reporter | master | `518d61fb1d` | 2025-10-23 | none |
| t1pal/nightscout-roles-gateway | master | `4fdd490654` | 2023-05-26 | none |
| openaps/oref0 | master | `88cf032aa7` | 2022-06-19 | v0.7.1 |
| openaps/openaps | master | `bd9a831887` | 2020-02-25 | none |
| nightscout/nightguard | master | `608be1b548` | 2026-10-24 | V4.7.0 |
| JohanDegraeve/xdripswift | master | `ba37f26135` | 2026-10-20 | 7.2.0 |
| NightscoutFoundation/xDrip | master | `c42cf55c6b` | 2026-10-23 | 2026.10.23 (prerelease) |
| gui-dos/DiaBLE | main | `e6a909c88f` | 2026-07-30 | iOS17 |
| xdrip-js/xdrip-js | master | `0cd1c555bc` | 2022-04-30 | v2.1.8 |
| loopandlearn/LoopFollow | main | `4a74b781ad` | 2026-09-20 | v7.1.0 |
| LoopKit/LoopCaregiver | dev | `a6abd2e9b3` | 2026-10-30 | none |
| nightscout/nocturne | main | `4891685107` | 2026-11-02 | v0.3.0 |
| nightscout/share2nightscout-bridge | master | `518c85c4e5` | 2026-03-03 | 0.2.10 |
| nightscout/cgm-remote-monitor | master | `c6a0d8ed65` | 2026-10-21 | v15.0.9 |
| jwoglom/tconnectsync | master | `4de47729c0` | 2026-10-05 | v3.0.3 |
| timoschlueter/nightscout-librelink-up | main | `bff2317f5c` | 2026-03-04 | v3.3.0 |
| nightscout/minimed-connect-to-nightscout | master | `57bb042c43` | 2026-03-03 | none |
| lsandini/cgmsim-lib | main | `07ed099034` | 2026-10-31 | 0.13.0 |
| LoopKit/LoopAlgorithm | main | `e692e7708c` | 2026-11-01 | none |
| replicahealth/GluPredKit | main | `12c70117c4` | 2026-10-06 | v1.0.12 |
| karpathy/autoresearch | master | `228791fb49` | 2026-03-26 | none |
| nudgebg/babelbetes | develop | `07a7f07278` | 2026-07-21 | v0.3.2 |
| loopandlearn/OmnipodKit | dev | `0c6d68b00d` | 2026-10-22 | none |
| LoopKit/NightscoutKit | main | `6efa02d457` | 2026-10-21 | none |
| lumose-health/GlycemicGPT | main | `d1a9adb73e` | 2026-08-18 | v0.15.0 |
| lsandini/glooko2nightscout | main | `9ab8c6080b` | 2025-09-01 | none |
| itconor/glooko-nightscout-eu | main | `2b7fbc45b8` | 2026-06-25 | none |
| spamsch/glooko-reader | main | `22837f6c40` | 2026-03-29 | none |
| nightscout/GlookoServiceKit | main | `94547d3664` | 2026-10-27 | none |
| shanselman/nightscout-cgm-skill | master | `91a53ea167` | 2026-06-08 | none |
| tim2000s/oref-digital-twin | main | `b257d0c169` | 2026-10-12 | none |
| tim2000s/Insulin-Kinetics | master | `7bf690024a` | 2026-10-05 | none |
| tim2000s/dynamic-isf-calculations | main | `22cdd518b3` | 2026-10-05 | none |
| tim2000s/Smoothing-Investigations | main | `520426e7c4` | 2026-07-11 | none |
| tim2000s/exercise-eval | main | `3e9eaabaff` | 2026-08-30 | none |
| tim2000s/clinical-advice-analysis | main | `870c66fc7b` | 2026-09-21 | none |
| LoopKit/g7sim | main | `fa26c95f1c` | 2026-10-23 | none |
| LoopKit/pod | main | `df02c9dfda` | 2026-11-01 | none |
| jwoglom/trio-test-harness | main | `1da25880a1` | 2026-11-01 | none |

Relevant follow-up signals, not admitted release work:
loopandlearn/LoopFollow#796 (LF Hub),
NightscoutFoundation/xDrip#4566 (IOB model proposal),
nightscout/nightscout-connect#52 (API v3 source support), and
LoopKit/LoopAlgorithm#18 (dose-history/IOB tests, merged at `e692e770`).
The last change is test coverage, not evidence that a dosing algorithm changed.
Trio's unchanged release branch does not mean its development PRs are inactive.
