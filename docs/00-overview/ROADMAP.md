# Roadmap for cgm-remote-monitor: what comes next, and in what order

*What this is: a map of the work ahead (contributor-facing). Read after [programme
status](PROGRAMME-STATUS.md); leads to [work waiting on a person](NEEDS-A-HUMAN.md). Prepared for the
Nightscout project; proposed for Nightscout Foundation stewardship. Living document: §1 dated
2026-10-21 against cgm-remote-monitor `official/master` `c6a0d8ed` (tags `v15.0.9`, `15.0.9`) and
`official/dev` `04d435eb`; other prose dated 2026-10-08 against `dev` `fade2299` and `master`
`92d08342` (tag `15.0.8`). The two order tables are generated from `queue/work-queue.yaml`, and
`make views-check` fails when they drift.*

This page gives the order of the work ahead. It records no decisions itself. The decisions
live in these places, and this page links to them:

| what | where it is decided |
|---|---|
| the release train and each release's number | [versioning policy §8.3](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#83-the-release-train) |
| tenancy decisions D1–D20 and the tenancy task definitions | [multitenancy execution plan](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) |
| defect facts, and what ships to operators today | [backfix register](../30-design/remedial/nightscout-backfix-register.md) |
| each item's state, gate and blockers | `queue/work-queue.yaml`; `make queue-status` measures it |

For where things stand, see [PROGRAMME-STATUS](PROGRAMME-STATUS.md). For which decisions are
waiting on a person, see [NEEDS-A-HUMAN](NEEDS-A-HUMAN.md). For how this work fits with the
shared schemas, identity, research commons and new interfaces across the ecosystem, see
[ECOSYSTEM-PROGRAMME](ECOSYSTEM-PROGRAMME.md). For who would do the work nobody is paid for, see the
[sponsored-team proposal](SPONSORED-TEAM-PROPOSAL.md); for the rules the ecosystem's parties would
work together under, and the dated work other organisations' calendars will bring, see
[COLLABORATION-MODEL](COLLABORATION-MODEL.md).

**How to read the order tables.** An item's *wave* comes from the blockers it is still waiting
on. An item waiting on nothing that is still open is wave 1. Any other item is one wave later
than its latest-wave open blocker. Items that are merged, done, closed or answered are left out.
A wave shows dependency, not a date. The states shown are claims about what the gates will say,
not measurements.

---

## 1. 15.0.9 is released; the next development cycle

**15.0.9 was released on 2026-10-21** (queue `RT-0`, state `released`). The maintainer merged
release PR #8598 at 20:09Z as `master` `c6a0d8ed` (parents `92d08342` = `15.0.8` and `dev`
`4bca2ac2`; tree `c53c2c7f`, the same as `dev`'s), and published the GitHub release `v15.0.9`,
"Release 15.0.9 Cinnamon Muffin", at 20:21Z as Latest, from the
[release notes](../../releases/cgm-remote-monitor-15.0.9/release-notes.md). Both approvals of
#8598 were the maintainer's, at `e3adc91d`; they were not repeated at `4bca2ac2`. The release
carries 549 commits and 100 first-parent merges since 15.0.8. Every entry of the
[backfix register](../30-design/remedial/nightscout-backfix-register.md) that was merged is now
`released 15.0.9`, and every queue item that was `merged-upstream` is `released`. Operators who
have not upgraded from 15.0.8 still have all of them.

The `master` CI run (39667944235) failed on its first attempt in one cell's `npm install`
(`ECONNRESET`, before any test ran) and cancelled the other cells; the second attempt passed all
nine test cells (Node 20/22/24 × MongoDB 4.4/5/6), both Docker builds and *Publish to Docker Hub*,
which published the `15.0.9` and `latest` images (*Validate Docker image* was skipped). The last
full local run is run 023 on `fade2299` (2026-10-08), 3566/0/4.

The release rests on the maintainers' decision of 2026-10-21 that the candidate was ready: many
days on varied real Nightscout set-ups with no complaints from the testing cohort stood in place of
the browser hand checks still listed as owed (kept in
[contents](../../releases/cgm-remote-monitor-15.0.9/contents.md#open-items-a-releaser-must-settle)).
The `follow-redirects` advisories, BF-172, BF-173 and BF-174 are known issues named in the release
notes. On `4bca2ac2` `npm audit` reports 26 findings, 11 high, 0 critical
([triage](../../releases/cgm-remote-monitor-15.0.9/contents.md#the-11-high-findings-on-4bca2ac2)).

Open blockers of `RT-0`, generated:

<!-- BEGIN GENERATED: release-waits -->

| id | what | claimed state | waiting for | PR |
|---|---|---|---|---|
| &mdash; | nothing open blocks `RT-0` | | | |

<!-- END GENERATED: release-waits -->

**Priorities for the next cycle** (maintainer, 2026-10-21): (1) modernization, cut 1 first
(`RT-REBASE`, `RT-1`); (2) backfixes that affect dosing or security; (3) other exposure fixes, only
where no cut or modernization branch already covers them.

What is left from the release, and the next cycle as it stands on 2026-10-21:

1. Done 2026-10-21: the tag `15.0.9` without the `v`, on `c6a0d8ed`, as `15.0.7` and `15.0.8`
   have both forms.
2. Done 2026-10-21: the next development cycle is open. `dev` is the 15.0.10 cycle: the maintainer pushed `04d435eb` ("Start 15.0.10 development cycle") to
   `dev` at 2026-10-21 20:40:09Z, a fast-forward from `4bca2ac2` over `c6a0d8ed`, so `dev` is one commit
   ahead of `master`: `package.json` and `package-lock.json` at 15.0.10, and in `CHANGELOG.md` the
   `[Unreleased]` entries became `[15.0.9] - 2026-10-21`, a new empty `[Unreleased]` opened, and 15.0.8
   and 15.0.7 got dated headings, which settles the `CHANGELOG.md` question. The push's CI run
   (39672291233) passed. The staging PR is #8824 ("new dev branch post 15.0.9 release", `dev` →
   `master`, opened by the maintainer 20:40:54Z at `04d435eb`): mergeable, 28 checks passed and 3
   skipped, review required.
   `dev` declares 15.0.10, but the next version is open: the maintainer has said the work decides
   patch, minor or major, and the version string may change to follow it, so it is driven by the
   semver class of what lands (each queue item's `semver`). The `dev` baseline, full suite on
   `04d435eb`: 3569 passing, 0 failing, 4 pending (Node 24.15.0, MongoDB 7.0.43 in a container).
3. Dependabot is settled apart from the `dev` bumps. On 2026-10-21 no Dependabot PR is open:
   #8818, #8811, #8805 and #8798 were closed by Dependabot as up to date, and #8822 (`sanitize-html`
   2.18.1), #8817 (`compression` 1.8.2) and #8814 (`source-map-js` 1.2.2) were closed by AndyLow91.
   15 open alerts are measured against `master` (15.0.9). The configuration question stays open
   (`DEPENDABOT-CONFIG`, `needs-decision`). The `dev` bumps for `compression`, `follow-redirects`
   and `source-map-js` are being prepared on `wip/15.0.10-lockfile-refresh` (peer session, not
   pushed); it leaves `sanitize-html` out on purpose, because GHSA-x3q4 and GHSA-cv27 need 2.18.0,
   which needs Node >=22.12.
4. `npm audit` on `dev` `04d435eb` (2026-10-21 20:49Z, npm 11.12.1, `--package-lock-only`): 27
   findings, 13 high, 0 critical in the worktree (14 / 9 with `--omit=dev`); the same lockfile
   audited in a scratch directory gives 28 / 14 (the extra high is `axios-cookiejar-support`, cause
   not found). None of cuts 1–4 or #8605 fixes `braces`, `node-forge`, `source-map-js`,
   `follow-redirects` or `compression`, and none fixes the two `sanitize-html` advisories (cut 1
   `c043fb2d` keeps 2.17.5; cuts 2–4 and #8605 have 2.17.7). GHSA-374f, a new moderate, is
   untriaged. Figures per cut are in
   [contents](../../releases/cgm-remote-monitor-15.0.9/contents.md#npm-audit-and-dependabot-triage).
5. Pushed by the maintainer on 2026-10-21 as PRs to `dev`: #8825 (`BFQ-173`,
   `bf/boluscalc-profile-units` `34c73bd7`, 3573/0/4), #8826 (`BFQ-174`, `bf/profile-spec-honoured`
   `827df15e`, 3576/0/4), which must land with or after #8825, never alone: on its own, an mmol/L
   profile chosen on an mg/dl display gives 81 U where `dev` gives 2.3 U; and #8827 (`BFQ-157`,
   `bf/treatment-bubble-units` `a9c6b3d1`, 3577/0/4, not measured in a browser). #8797 (`BFQ-09`)
   now has head `542b7e97`, with `dev` merged in (3591/0/4). #8819 (`BFQ-172`) merges cleanly with
   `dev` (3571/0/4); a review note is drafted, not posted. The four dosing changes together
   (`scratch/dosing-1510` `203027c5`: `BFQ-173`, `BFQ-174`, `BFQ-09` and #8819 on `dev`) pass
   3604/0/4. Through private advisory forks, to be published with the release that carries them:
   `BFQ-161` (`bf/entries-pattern-limit` `d2c4df9f`, 3585/0/4, patch; a depth limit of 10, the
   deepest intended use nests 1 level) and `BFQ-72` (`bf/regex-limits` `1833ab00`, 3646/0/4, minor;
   a length cap and a time limit on every regex query, and a refusal check for caller-written
   patterns behind `QUERY_REGEX_REFUSE_UNSAFE`, default off). Both keep the intended uses in the
   maintainer's public gist `dbe590ab` working.
6. The nine items whose only open blocker was `RT-0` are re-stated: `BFQ-173` and `BFQ-174`
   `in-flight-upstream` (#8825, #8826); `BFQ-72` `ready-to-push` (private fork); `BFQ-95` and `BFQ-152` `needs-decision`; `BFQ-67` and `BFQ-93`
   `not-started`; `BFQ-156` `in-progress` (its branch owes a merge of `dev`); `SEAM-REFRESH` now
   waits on `RT-REBASE`. `RT-1` and `ID-SIMPLE-MATCH` wait on `RT-REBASE`, which is in progress.
7. The version class of #8772, #8775 and #8780 stays recorded as open in
   [decisions](../../releases/cgm-remote-monitor-15.0.9/decisions.md).

The full `npm audit` triage, which findings reach a running site and what is done about each, is in
[contents](../../releases/cgm-remote-monitor-15.0.9/contents.md#npm-audit-and-dependabot-triage).

| for | read |
|---|---|
| what 15.0.9 contains, what it leaves broken, and what a releaser must settle | [contents.md](../../releases/cgm-remote-monitor-15.0.9/contents.md) |
| the decisions that shape it | [decisions.md](../../releases/cgm-remote-monitor-15.0.9/decisions.md) |
| how the candidate was tested | [15.0.9 integration record](../30-design/remedial/rc-15.0.9-integration-record.md) |
| the user-facing draft | [release-notes.md](../../releases/cgm-remote-monitor-15.0.9/release-notes.md) |

## 2. Modernization: the release train

The adopted order ([§8.3](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#83-the-release-train)):

| step | release | contents |
|---|---|---|
| 1 | 15.0.9 | `dev` as it stood at `4bca2ac2`; released 2026-10-21 |
| 2 | cut 1, `chore/retire-jsdom` | the real-browser test suite, the Node floor, and removal of the legacy Dexcom and MiniMed bridges |
| 3 | cut 2, `chore/build-runtime-separation` | page bundles and the build/runtime split |
| 4 | cuts 3 + 5 | dependency majors, including the MongoDB driver and Express 5 |
| 5 | cut 4, `chore/mime-exposure-review` | the remainder: trusted proxies, DOMPurify, Moment, MIME, webpack, ESLint |

Two questions are open in §8.3:

- whether the cuts ship as separate releases or as one combined release;
- BF-64: cut 4 is an ancestor of cut 5, so steps 4 and 5 cannot be separated as the branches
  stand.

**Rebasing costs more with every merge to `dev`.** The cuts conflict with `dev` in files the
merged remedial PRs touched (queue `RT-REBASE` re-measures the conflicts). The cheapest time to
rebase cut 1 is right after 15.0.9 is tagged, while `dev` is quiet. On 2026-10-21 cut 1's catch-up
merge is in progress (`RT-REBASE`): on `dev` `04d435eb`, `chore/retire-jsdom` `bce12ecc` is 376
commits behind and 99 ahead, with 13 conflicting paths, and 14 `dev` test files (about 109 cases)
use the jsdom harness cut 1 deletes. The maintainer chose option C that day: cut 1 ports the D3,
clock-client and pill-title coverage to the real-browser suite and keeps the jsdom harness for the
rest, which a later cut retires (`RT-JSDOM-REST`); the decided Node floor `^22.12 || >=24` and the
legacy bridge removal come into the cut 1 merge.

<!-- BEGIN GENERATED: road-release-train -->

| wave | id | what | claimed state | waits on |
|---:|---|---|---|---|
| 1 | `OID-STORAGE-HELPER` | One storage-level rule for writes by _id instead of six hand-written copies | `not-started` | &mdash; |
| 1 | `OID-V3-EDIT-MERGE` | API v3 PUT and PATCH of a record stored twice by _id leave both copies; make an  | `not-started` | &mdash; |
| 1 | `OID-WS-EDIT-MERGE` | Websocket dbUpdate of a record stored twice by _id edits both copies and leaves  | `not-started` | &mdash; |
| 1 | `RT-BOOTERROR` | BF-63 - the page that reports a boot error crashes on cut 4's boot errors | `gate-not-met` | &mdash; |
| 1 | `RT-CONNECT-PIN-CUTS` | BF-65 - cuts 1-3 ship the leaking connector to upgraders first | `gate-not-met` | &mdash; |
| 1 | `RT-PR-8730` | #8730 - Crowdin translation updates, held out of 15.0.9 (BF-132) | `gate-not-met` | &mdash; |
| 1 | `RT-REBASE` | Cuts 1-5 are far behind dev and all five conflict | `in-progress` | &mdash; |
| 1 | `RT-VERSION` | Two artefacts claim version 15.0.9 with different Node floors | `not-started` | &mdash; |
| 2 | `ID-SIMPLE-MATCH` | API v1 entries and devicestatus match on identifier like treatments (the simple  | `blocked` | `RT-REBASE` |
| 2 | `OID-MIGRATION` | Opt-in migration that stores every string _id as the ObjectId it names, then ret | `not-started` | `OID-PREVALENCE` |
| 2 | `RT-1` | Cut 1 - chore/retire-jsdom | `blocked` | `RT-REBASE` |
| 3 | `RT-2` | Cut 2 - chore/build-runtime-separation | `blocked` | `RT-1` |
| 3 | `RT-D3-SUITE` | The treatment-drag clamps get a regression test in cut 1's real-browser suite | `blocked` | `RT-1` |
| 3 | `RT-JSDOM-REST` | Retire the jsdom test harness that cut 1 keeps (option C) | `not-started` | `RT-1` |
| 3 | `RT-NODE-FLOOR-TESTED` | BF-58, BF-59 - the enforced Node floor is not the Node anything exercises | `gate-not-met` | `RT-1` |
| 4 | `RT-3` | Cuts 3+5 combined - dependency release | `blocked` | `RT-2` |
| 5 | `RT-5` | Cut 4 - chore/mime-exposure-review, the one to slow down on | `blocked` | `RT-3` |

<!-- END GENERATED: road-release-train -->

## 3. Multitenant

Self-hosted, single-tenant Nightscout stays first-class permanently (D1, D4). Multitenancy is a
second deployment target and never replaces it.

**The schedule is bounded by the release train.** Tenancy work is based on
`chore/nightscout-modernization` (D9), so no tenancy code reaches a release before cuts 3 + 5.
Until then, the order below is the order of development, not of release.

- **First, the seam refresh (`SEAM-REFRESH`), once, after the 15.0.9 freeze.** Nothing builds on
  the seam, and nine of its conflicting paths are files that now call a 15.0.9 write rule, so the
  refresh is done as the first step of the write contract (`WRITE-CONTRACT`, plan §4.1): one write
  step behind the storage interface, for all three write paths and both backends. What the refresh
  lands on depends on how the release train reaches `dev`, which is open (`RT-PROPAGATION`, plan
  §5.1). The seam chain's first 16 commits carry no tenancy behaviour and can ship to self-hosted
  operators as a refactor release, followed by the write contract. Modernization work continues in
  parallel.
- **Then the configuration and credential root (T3.0).** `T30-SCHEMA-CRED` has no blockers.
  `T30-SCHEMA-CONFIG` waits on the configuration research and on `T30-ORY-PROOF`, a proof that
  one identity pool can serve two tenants. Everything per-tenant after that waits on
  `T30-WIRING`.
- **Alarms under `TENANCY_MODE=multi` come last, and are off until then by design.** They turn on
  only when a test shows tenant A's alarm reaching A and not B, through the real producer path,
  with a snooze that survives a restart and a process change (`A7A-GATE`; plan §7a). On a hosted
  multi-tenant server, alarms stay off until that gate passes. A self-hosted Nightscout that
  serves one person or family is not affected.

<!-- BEGIN GENERATED: road-tenancy -->

| wave | id | what | claimed state | waits on |
|---:|---|---|---|---|
| 1 | `A7A-7` | §7a item 7 - the clock question | `unsettled` | &mdash; |
| 1 | `ID-CONVENTIONS` | Identifier conventions: one URL-form identifier template per record kind and sou | `in-progress` | &mdash; |
| 1 | `T30-AUTH` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-i | `ready-to-push` | &mdash; |
| 1 | `T30-RESEARCH` | T3.0 part 1 - enumerate the per-tenant configuration surface | `needs-decision` | &mdash; |
| 1 | `T43` | T4.3 - ns-realtime, LISTEN per served tenant | `not-started` | &mdash; |
| 2 | `SEAM-REFRESH` | Refresh the seam chain once after 15.0.9, onto the base the release train leaves | `blocked` | `RT-REBASE` |
| 2 | `T30-SCHEMA-CONFIG` | T3.0 part 2b - per-tenant configuration table, and where human identity lives | `not-started` | `T30-RESEARCH` |
| 3 | `T30-WIRING` | T3.0 part 3 - deriveEnv overrides, tenant-scoped isApiKey/verifyJWT | `not-started` | `T30-SCHEMA-CONFIG` |
| 3 | `T32-REM` | T3.2 remainder - platform.sql carries no config, secret or signing key | `blocked` | `T30-SCHEMA-CONFIG` |
| 3 | `WC-STEP-PATCH` | Release 1 (patch): one write step for every v1, v3 and socket path, today's beha | `blocked` | `SEAM-REFRESH` |
| 3 | `WRITE-CONTRACT` | One write step behind the storage interface: _id form, srv dates, soft delete, r | `blocked` | `SEAM-REFRESH` |
| 4 | `BFQ-CAP02` | CAP-02 - no importer, and no Mongo to PostgreSQL loader | `not-started` | `T30-SCHEMA-CONFIG`, `WRITE-CONTRACT` |
| 4 | `ID-BATCH-RESULTS` | Release 2 (minor): per-item results in v1 batch replies; one bad item no longer  | `blocked` | `WC-STEP-PATCH` |
| 4 | `ID-FIRST-MATCH` | Release 2 (minor): identifier-first matching for entries, devicestatus and socke | `blocked` | `WC-STEP-PATCH`, `ID-SIMPLE-MATCH` |
| 4 | `ID-V1-LOOKUP` | Release 2 (minor): v1 GET and DELETE by any identifier, without the default time | `blocked` | `WC-STEP-PATCH` |
| 4 | `ID-VALIDATE` | Release 2 (minor): validate identifier on every collection; empty and null mean  | `blocked` | `WC-STEP-PATCH` |
| 4 | `T30-TENANT-ADMIN` | cgm-remote-monitor: the ns-tenant-admin listener, a second bound socket inside n | `not-started` | `T30-WIRING` |
| 4 | `T31-REM` | T3.1 remainder - per-tenant signing key replaces the install-wide one | `blocked` | `T30-WIRING` |
| 4 | `T33-REM` | T3.3 remainder - the shared enclave, and language/levels per tenant | `blocked` | `T30-WIRING` |
| 4 | `T44` | T4.4 - ns-evaluator, the per-tenant evaluation loop | `not-started` | `T30-WIRING` |
| 5 | `A7A-3` | §7a item 3 - a per-tenant error boundary | `not-started` | `T44` |
| 5 | `A7A-4` | §7a item 4 - a health signal for a silent per-tenant outage | `not-started` | `T44` |
| 5 | `BFQ-66` | BF-66 - the deployment's own tokens fail its own tenant check | `blocked` | `T30-WIRING`, `T31-REM`, `SEAM-REFRESH` |
| 5 | `ID-ABSENT-DECISION` | Decide: a write that carries no identifier (and no _id) - keep the time-key fall | `needs-decision` | `LOOP-ID-REPLY` |
| 5 | `ID-CLIENT-OID-DECISION` | Decide: may a client set _id (an ObjectId it creates), and which field wins when | `needs-decision` | `LOOP-ID-REPLY` |
| 5 | `ID-DELETE-REUSE-DECISION` | Decide: after a delete, what does a re-send of the same identifier (or _id) do - | `needs-decision` | `LOOP-ID-REPLY` |
| 5 | `ID-FORMAT-DECISION` | Decide: the client identifier's format (opaque string with limits; UUID not requ | `needs-decision` | `LOOP-ID-REPLY` |
| 5 | `ID-SCOPE-DECISION` | Decide: is identifier unique per collection, across collections, and per tenant  | `needs-decision` | `LOOP-ID-REPLY` |
| 5 | `ID-V3-IMMUTABLE-DECISION` | Decide: on an identifier match, may date, device or eventType change? | `needs-decision` | `LOOP-ID-REPLY` |
| 6 | `A7A-GATE` | The alarms-on gate itself - nothing here may be marked done by inference | `blocked` | `T44`, `A7A-3`, `A7A-4`, `A7A-7` |
| 6 | `ID-UNIQUE-INDEX` | Partial unique index on identifier, retry-as-update on duplicate key, start-up s | `blocked` | `ID-FIRST-MATCH`, `ID-BATCH-RESULTS`, `ID-V3-IMMUTABLE-DECISION` |

<!-- END GENERATED: road-tenancy -->

## 4. Remedial: fix what ships

The remedial work is not a sequence. It is prioritized by what reaches operators today: the
operator-exposure table on [PROGRAMME-STATUS](PROGRAMME-STATUS.md#status-words-merged-is-not-released)
lists the queue items for defects that are present on 15.0.8. A fix reaches operators only in a
release, so each merged fix joins the next step on the release train.

## 5. Proposals

These are proposals for discussion with other projects and maintainers. None is scheduled in the
queue.

**Cross-project adoption (hub and spoke).** This is a proposal to the controller projects (AAPS,
Loop, Trio) and to Nightscout as the hub. Each phase is useful even if the next never happens:

1. A schema for controller settings documents in the existing v3 `settings` collection.
2. Two one-symbol fixes, one in Nocturne and one in NightscoutKit, that stop dosing records being
   discarded.
3. A catalogue of controller registrations shipped with the hub.
4. A read-only sync contract.
5. Therapy effects, then batched writes, then decomposition.

Nothing in it requires a Loop protocol change. Detail and evidence:
[adoption roadmap](../30-design/nightscout-adoption-roadmap-2026-09-11.md).

**Product direction after the modernization baseline.** This is a discussion between the
maintainers. It proposes these work packages once the modernization branch is accepted:

- bringing the connector's source in-tree;
- extracting the report statistics into a tested module and exposing them through a documented
  API;
- a first Svelte report (Daily Stats), also usable as a standard Web Component;
- PDF export for sharing with a clinician;
- vendor test fixtures shared across projects.

Library and implementation choices are open. Detail:
[modernization review and proposed next steps](../60-research/modernization/nightscout-modernization-next-steps-2026-09-09.md).

**A shared quality kit for the whole stack.** A proposal to every project: vector corpora for device
protocols, simulators, fixture suites and a change canary for vendor clouds, a conformance suite any
server can run, and one record shape for every test run, built in four stages. It also proposes how
requirements that touch several projects are agreed. Detail:
[quality-system proposal](QUALITY-SYSTEM.md), measured by the
[stack census](../60-research/programme/stack-census-2026-09-30.md).

## 6. What bounds all of it

Review capacity, not engineering. Most queue items route to the maintainer, and the SECURITY and
SAFETY review rows do not name a person. The current split is on
[PROGRAMME-STATUS](PROGRAMME-STATUS.md#the-two-constraints-neither-of-them-engineering). Onboarding
for reviewers is in [REVIEWER-ONBOARDING](REVIEWER-ONBOARDING.md).

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-27**, against cgm-remote-monitor-official `7000eb18` and this repository at `18cdcce0`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
