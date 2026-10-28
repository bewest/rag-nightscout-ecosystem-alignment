# Roadmap for cgm-remote-monitor: what comes next, and in what order

*What this is: a map of the work ahead (contributor-facing). Read after [programme
status](PROGRAMME-STATUS.md); leads to [work waiting on a person](NEEDS-A-HUMAN.md). Prepared for the
Nightscout project; proposed for Nightscout Foundation stewardship. Living document: §1 and §2 dated
2026-10-25 against cgm-remote-monitor `official/master` `c6a0d8ed` (tags `v15.0.9`, `15.0.9`) and
`official/dev` `eb72a1d3` (16.0.0, cut 1 merged as #8828); other prose dated 2026-10-08 against `dev` `fade2299` and `master`
`92d08342` (tag `15.0.8`). The two order tables are generated from `queue/work-queue.yaml`, and
`make views-check` fails when they drift.*

This page gives the order of the work ahead. It records no decisions itself. The decisions
live in these places, and this page links to them:

| what | where it is decided |
|---|---|
| the release train and each release's number | [versioning policy §8.3](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#83-the-release-train) |
| tenancy decisions D1–D21 and the tenancy task definitions | [multitenancy execution plan](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) |
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

## 1. 16.0.0: the development cycle after 15.0.9

<a id="1-1509-is-released-the-next-development-cycle"></a>

**16.0.0 is the next release** (maintainer, 2026-10-21; `RT-VERSION`), and **cut 1 is on `dev`**:
AndyLow91 merged #8828 on 2026-10-25 at 16:29:06Z as `dev` `eb72a1d3` (head `12154df9`), after ten other
PRs the same day. `dev` declares 16.0.0 and `engines.node` `^22.23.4 || ^24.22.1 || >=26.12.1`
(AndyLow91's `6a146a4c`, "require Node Brotli security patches", which supersedes the decided
`^22.12 || >=24`). The release record is open:
**[releases/cgm-remote-monitor-16.0.0](../../releases/cgm-remote-monitor-16.0.0/contents.md)**, with its
[decisions](../../releases/cgm-remote-monitor-16.0.0/decisions.md), the open items a releaser must settle
and the suggested order of the next merges, and the
[16.0.0 integration record](../30-design/remedial/rc-16.0.0-integration-record.md) for the runs.

**Priorities for the next cycle** (maintainer, 2026-10-21): (1) modernization, cut 1 first
(`RT-REBASE`, `RT-1`); (2) backfixes that affect dosing or security; (3) other exposure fixes, only
where no cut or modernization branch already covers them.

What is left, as it stands on 2026-10-26, 19:10Z (`dev` `47723cda`, `master` `c6a0d8ed`):

1. **Merged to `dev`, none released:** 34 PRs on 2026-10-25 and 2026-10-26, among them all five
   modernization cuts (cut 1 #8828, cut 2 #8837, cut 3 #8844, cut 4 #8847, cut 5 #8605), the CI
   diagonal (#8843), the alarm fixes (#8842), record identity (#8845), opt-in `WRITE_VALIDATION`
   (#8841) and boot resilience (#8849). 857 commits and 35 first-parent commits ahead of `master`. CI
   on `47723cda` passed and published the `dev` Docker image. The list, with each PR's register and
   queue ids, is in [16.0.0 contents](../../releases/cgm-remote-monitor-16.0.0/contents.md#what-is-merged-so-far).
2. **The staging PR #8824** (`dev` → `master`) is open at `47723cda`, mergeable, review required, and
   blocked by `master`'s required check `Run Tests (22, 4.4)`, which no `dev` workflow emits.
3. **In flight.** Draft #8854 (AndyLow91: a shared write step and stored-data contracts, on `dev`
   `47723cda`). BF-72 and BF-161 are in the private forks of their draft advisories, no fork PR opened
   yet, each owing a merge of `dev` (`BFQ-72`, `BFQ-161`); BF-191 goes through the maintainer's
   advisory process.
4. **Not started:** `ID-SIMPLE-MATCH`, `RT-JSDOM-REST` and `RT-BUNDLE-THEME-SPLIT`.
5. **Open decisions and settings** are listed with their owners in
   [16.0.0 contents](../../releases/cgm-remote-monitor-16.0.0/contents.md#open-items-a-releaser-must-settle),
   with the maintainer's branch-protection changes and the live alarm-delivery checks owed before the
   tag.
6. The version class of #8772, #8775 and #8780 stays recorded as open in
   [15.0.9 decisions](../../releases/cgm-remote-monitor-15.0.9/decisions.md).

**15.0.9, for the record.** Released on 2026-10-21 (queue `RT-0`, `released`): #8598 merged as `master`
`c6a0d8ed` (tree `c53c2c7f`, `dev` `4bca2ac2`'s), GitHub release `v15.0.9` "Release 15.0.9 Cinnamon
Muffin", tags `v15.0.9` and `15.0.9`, Docker `15.0.9` and `latest` published by `master` CI run
39667944235 (attempt 2). Its records are in
[releases/cgm-remote-monitor-15.0.9](../../releases/cgm-remote-monitor-15.0.9/contents.md) and the
[15.0.9 integration record](../30-design/remedial/rc-15.0.9-integration-record.md). Open blockers of
`RT-0`, generated:

<!-- BEGIN GENERATED: release-waits -->

| id | what | claimed state | waiting for | PR |
|---|---|---|---|---|
| &mdash; | nothing open blocks `RT-0` | | | |

<!-- END GENERATED: release-waits -->

| for | read |
|---|---|
| what 16.0.0 contains so far, what is in flight and what a releaser must settle | [16.0.0 contents.md](../../releases/cgm-remote-monitor-16.0.0/contents.md) |
| the decisions that shape 16.0.0 | [16.0.0 decisions.md](../../releases/cgm-remote-monitor-16.0.0/decisions.md) |
| how 16.0.0 is being tested | [16.0.0 integration record](../30-design/remedial/rc-16.0.0-integration-record.md) |
| what 15.0.9 contains and leaves broken | [15.0.9 contents.md](../../releases/cgm-remote-monitor-15.0.9/contents.md) |

## 2. Modernization: the release train

The adopted order ([§8.3](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#83-the-release-train)),
as it stands on 2026-10-25:

| step | release | contents | state |
|---|---|---|---|
| 1 | 15.0.9 | `dev` as it stood at `4bca2ac2` | released 2026-10-21 |
| 2 | 16.0.0: cut 1, `chore/retire-jsdom`, PR #8828 | the real-browser test suite (option C), the Node floor `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1`, removal of the legacy Dexcom and MiniMed bridges | merged to `dev` 2026-10-25 (`eb72a1d3`); not released |
| 3 | cut 2, `chore/build-runtime-separation` | page bundles and the build/runtime split | next: catch-up merge of `dev` `eb72a1d3` in progress; in 16.0.0 or its own release is open |
| 4 | cuts 3 + 5 | dependency majors, including the MongoDB driver and Express 5 | blocked on cut 2 |
| 5 | cut 4, `chore/mime-exposure-review` | the remainder: trusted proxies, DOMPurify, Moment, MIME, webpack, ESLint | blocked on cuts 3 + 5 |

Two questions are open in §8.3:

- whether the cuts ship as separate releases or as one combined release, which now decides whether
  cut 2 is in 16.0.0;
- BF-64: cut 4 is an ancestor of cut 5, so steps 4 and 5 cannot be separated as the branches stand.

**Rebasing costs more with every merge to `dev`.** Against `dev` `eb72a1d3` (`git rev-list
--left-right --count` and `git merge-tree --write-tree --name-only --no-messages`): cut 2 `b6e8c7cd` is
459 behind and 159 ahead with 20 conflicting paths; cut 3 459 / 222, 25; cut 4 459 / 301, 43; cut 5
`b1bdaca0` (#8605) 335 / 399, 42 (`RT-REBASE`). Cut 2's catch-up is under way, and it keeps cut 2's
`queryLeaves` walker instead of the `traverse` package when it takes `dev`'s query rules (`948a142e`,
2026-10-21). Cuts 2–5 still declare the old floors and take `dev`'s at their catch-up merges. The jsdom
harness cut 1 keeps is retired later under scope B (`RT-JSDOM-REST`, decided 2026-10-21).

<!-- BEGIN GENERATED: road-release-train -->

| wave | id | what | claimed state | waits on |
|---:|---|---|---|---|
| 1 | `MOD-UNITS-CANONICAL` | Canonical units at write: spelling only (N1) or mg/dL plus the original (N2), an | `needs-decision` | &mdash; |
| 1 | `MOD-WRITE-VALIDATION-READ` | Flag stored records that break a write-validation rule on API v3 reads (read-sid | `needs-decision` | &mdash; |
| 1 | `OID-STORAGE-HELPER` | One storage-level rule for writes by _id instead of six hand-written copies | `not-started` | &mdash; |
| 1 | `OID-V3-EDIT-MERGE` | API v3 PUT and PATCH of a record stored twice by _id leave both copies; make an  | `not-started` | &mdash; |
| 1 | `OID-WS-EDIT-MERGE` | Websocket dbUpdate of a record stored twice by _id edits both copies and leaves  | `not-started` | &mdash; |
| 1 | `RT-16-LIVE-ALARMS` | 16.0.0 pre-tag check: live Pushover and APNs delivery on dev | `not-started` | &mdash; |
| 1 | `RT-16-RIG-SOAK` | 16.0.0 pre-tag check: a real-rig soak on dev | `not-started` | &mdash; |
| 1 | `RT-BOOTERROR` | BF-63 - the page that reports a boot error crashes on cut 4's boot errors | `gate-not-met` | &mdash; |
| 1 | `RT-BUNDLE-THEME-SPLIT` | Load the modern theme's client code only when it is chosen (page-bundle budget o | `not-started` | &mdash; |
| 1 | `RT-JSDOM-REST` | Retire the whole-bundle jsdom harness that cut 1 keeps; secure-jsdom stays as th | `not-started` | &mdash; |
| 2 | `OID-MIGRATION` | Opt-in migration that stores every string _id as the ObjectId it names, then ret | `not-started` | `OID-PREVALENCE` |
| 2 | `RT-16-RELEASE` | Release 16.0.0 | `blocked` | `RT-16-LIVE-ALARMS`, `RT-16-RIG-SOAK`, `BFQ-72`, `BFQ-161` |

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
| 1 | `ID-CLIENT-OID-DECISION` | Decide: may a client set _id (an ObjectId it creates) over API v1? (API v3 decid | `needs-decision` | &mdash; |
| 1 | `ID-CONVENTIONS` | Identifier conventions: one URL-form identifier template per record kind and sou | `in-progress` | &mdash; |
| 1 | `ID-FORMAT-DECISION` | Decide: the client identifier's format (opaque string with limits; UUID not requ | `needs-decision` | &mdash; |
| 1 | `ID-V3-IMMUTABLE-DECISION` | Decide: on an identifier match, may date, device or eventType change? | `needs-decision` | &mdash; |
| 1 | `MIG-RUNNER` | `nightscout migrate`: one runner (umzug) with the project's PostgreSQL and Mongo | `not-started` | &mdash; |
| 1 | `SEAM-REFRESH` | Refresh the seam chain once after 15.0.9, onto the base the release train leaves | `blocked` | &mdash; |
| 1 | `T30-AUTH` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-i | `ready-to-push` | &mdash; |
| 1 | `T30-RESEARCH` | T3.0 part 1 - enumerate the per-tenant configuration surface | `needs-decision` | &mdash; |
| 1 | `T43` | T4.3 - ns-realtime, LISTEN per served tenant | `not-started` | &mdash; |
| 1 | `WC-R1-QG` | Refresh the write-contract spec's matrix tables against the dev db3b9e4e pin | `not-started` | &mdash; |
| 1 | `WC-R1-QI` | Retire websocket.js idMatch when the socket update slice moves into the step | `not-started` | &mdash; |
| 1 | `WC-STEP-PATCH` | Release 1 (patch): one write step for every v1, v3 and socket path, today's beha | `in-flight-upstream` | &mdash; |
| 2 | `ID-BATCH-RESULTS` | Release 2 (minor): per-item results in v1 batch replies; one bad item no longer  | `blocked` | `WC-STEP-PATCH` |
| 2 | `ID-FIRST-MATCH` | Release 2 (minor): identifier-first matching for entries, devicestatus and socke | `blocked` | `WC-STEP-PATCH` |
| 2 | `ID-V1-LOOKUP` | Release 2 (minor): v1 GET and DELETE by any identifier, without the default time | `blocked` | `WC-STEP-PATCH` |
| 2 | `ID-VALIDATE` | Release 2 (minor): validate identifier on every collection; empty and null mean  | `blocked` | `WC-STEP-PATCH` |
| 2 | `T30-SCHEMA-CONFIG` | T3.0 part 2b - per-tenant configuration table, and where human identity lives | `in-progress` | `T30-RESEARCH` |
| 2 | `WC-R2-QA` | Release 2: Re-express API v3 writes as filter writes under the step, or keep two | `not-started` | `WC-STEP-PATCH` |
| 2 | `WC-R2-QB` | Release 2: One timing for removing a stored string-form _id twin on every path | `not-started` | `WC-STEP-PATCH` |
| 2 | `WC-R2-QC` | Release 2: Separate source labels for API v1 and in-process callers | `not-started` | `WC-STEP-PATCH` |
| 2 | `WC-R2-QD` | Release 2: One rule for a non-hex _id on in-process create and save | `not-started` | `WC-STEP-PATCH` |
| 2 | `WC-R2-QE` | Release 2: Answer an identical re-send as unchanged (nothing written, no srvModi | `not-started` | `WC-STEP-PATCH` |
| 2 | `WC-R2-QF` | Release 2: Move the lower half of write validation into the step, or decide it s | `not-started` | `WC-STEP-PATCH` |
| 2 | `WC-R2-QH` | Release 2: Decide whether v1 create keeps replace-on-match or follows merge-on-m | `not-started` | `WC-STEP-PATCH` |
| 2 | `WRITE-CONTRACT` | One write step behind the storage interface: _id form, srv dates, soft delete, r | `blocked` | `SEAM-REFRESH` |
| 3 | `BFQ-CAP02` | CAP-02 - no importer, and no Mongo to PostgreSQL loader | `not-started` | `T30-SCHEMA-CONFIG`, `WRITE-CONTRACT` |
| 3 | `ID-UNIQUE-INDEX` | Partial unique index on identifier, retry-as-update on duplicate key, start-up s | `blocked` | `ID-FIRST-MATCH`, `ID-BATCH-RESULTS`, `ID-V3-IMMUTABLE-DECISION` |
| 3 | `T30-WIRING` | T3.0 part 3 - deriveEnv overrides, tenant-scoped isApiKey/verifyJWT | `not-started` | `T30-SCHEMA-CONFIG` |
| 3 | `T32-REM` | T3.2 remainder - platform.sql carries no config, secret or signing key | `blocked` | `T30-SCHEMA-CONFIG` |
| 4 | `T30-TENANT-ADMIN` | cgm-remote-monitor: the ns-tenant-admin listener, a second bound socket inside n | `not-started` | `T30-WIRING` |
| 4 | `T31-REM` | T3.1 remainder - per-tenant signing key replaces the install-wide one | `blocked` | `T30-WIRING` |
| 4 | `T33-REM` | T3.3 remainder - the shared enclave, and language/levels per tenant | `blocked` | `T30-WIRING` |
| 4 | `T44` | T4.4 - ns-evaluator, the per-tenant evaluation loop | `not-started` | `T30-WIRING` |
| 5 | `A7A-3` | §7a item 3 - a per-tenant error boundary | `not-started` | `T44` |
| 5 | `A7A-4` | §7a item 4 - a health signal for a silent per-tenant outage | `not-started` | `T44` |
| 5 | `BFQ-66` | BF-66 - the deployment's own tokens fail its own tenant check | `blocked` | `T30-WIRING`, `T31-REM`, `SEAM-REFRESH` |
| 6 | `A7A-GATE` | The alarms-on gate itself - nothing here may be marked done by inference | `blocked` | `T44`, `A7A-3`, `A7A-4`, `A7A-7` |

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
