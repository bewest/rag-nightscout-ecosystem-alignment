# Roadmap for cgm-remote-monitor: what comes next, and in what order

*What this is: a map of the work ahead (contributor-facing). Read after [programme
status](PROGRAMME-STATUS.md); leads to [work waiting on a person](NEEDS-A-HUMAN.md). Prepared for the
Nightscout project; proposed for Nightscout Foundation stewardship. Living document: §1 and §2 dated
2026-10-25 against cgm-remote-monitor `official/master` `c6a0d8ed` (tags `v15.0.9`, `15.0.9`) and
`official/dev` `eb72a1d3` (16.0.0, cut 1 merged as #8828); §3 prose 2026-11-10; other prose dated 2026-10-08 against `dev` `fade2299` and `master`
`92d08342` (tag `15.0.8`). The two order tables are generated from `queue/work-queue.yaml`, and
`make views-check` fails when they drift.*

This page gives the order of the work ahead. It records no decisions itself. The decisions
live in these places, and this page links to them:

| what | where it is decided |
|---|---|
| the release train and each release's number | [versioning policy §8.3](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#83-the-release-train) |
| tenancy decisions D1–D23 | [tenancy decisions reference](../30-design/tenancy/multitenancy-decisions.md) |
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
| 1 | `RT-16-RIG-SOAK` | 16.0.0 pre-tag check: a real-rig soak on dev | `in-progress` | &mdash; |
| 1 | `RT-16-TOKEN-8829` | Nonblocking restricted-token browser report: environment comparison and reproduc | `not-started` | &mdash; |
| 1 | `RT-BOOTERROR` | BF-63 - the page that reports a boot error crashes on cut 4's boot errors | `gate-not-met` | &mdash; |
| 1 | `RT-BUNDLE-THEME-SPLIT` | Load the modern theme's client code only when it is chosen (page-bundle budget o | `not-started` | &mdash; |
| 1 | `RT-JSDOM-REST` | Retire the whole-bundle jsdom harness that cut 1 keeps; secure-jsdom stays as th | `not-started` | &mdash; |
| 2 | `OID-MIGRATION` | Opt-in migration that stores every string _id as the ObjectId it names, then ret | `not-started` | `OID-PREVALENCE` |
| 2 | `RT-16-RELEASE` | Release 16.0.0 | `in-progress` | `RT-16-LIVE-ALARMS`, `RT-16-RIG-SOAK`, `BFQ-72`, `BFQ-161` |

<!-- END GENERATED: road-release-train -->

## 3. Multitenant

Self-hosted single-tenant Nightscout stays first-class permanently (D1, D4).
Multitenant is an additional deployment target.

The [multitenant delivery roadmap](../30-design/tenancy/multitenant-delivery-roadmap.md)
owns milestone acceptance criteria; the [batching plan §5](../30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06)
owns the current completion sequence. Start with the
[tenancy reading guide](../30-design/tenancy/README.md). Use the
[delivery dashboard](../30-design/tenancy/multitenant-delivery-dashboard.md) for bounded
accepted evidence and remaining gates, and the
[next-generation platform map](../../site/pages/nightscout-next-gen-platform.html)
for architecture dependencies and parallel lanes. The generated table below gives
queue dependencies; `make queue-status` measures its claimed states. Release readiness
is recorded separately in the
[release contents](../../releases/cgm-remote-monitor-16.0.0/contents.md).

The [published one-host reference](../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md)
now includes cold Compose/UI/restore/client acceptance; native shared-role restart
and the functional M5 runtime retain their exact source scope. This evidence can
inform component and recovery decisions. M6 is split into M6a–M6d and M7
([decision](../../releases/cgm-remote-monitor-16.0.0/decisions.md#m6-split-and-queue-collapse)):
the M6a and M6b joined candidates have acceptance records on draft #8898
([M6a](../../reports/tenancy/m6a-join-2026-11-09/README.md),
[M6b](../../reports/tenancy/m6b-join-2026-11-10/b70ad83f-acceptance/README.md)), with
no milestone promoted. Deployment trust (M6c) and the M7 bench, scale, evaluator
partition, realtime sharding and Android items follow, in the order the generated
table gives; multi-host failover has no acceptance.
Use the [deployment models and fault domains](../30-design/tenancy/deployment-and-rig-testing.md)
to distinguish these boundaries. Tenant-local suppression and controlled notification
handoff are measured; live provider/device delivery remains separately gated by
[runtime and clinical acceptance](../30-design/tenancy/multitenancy-decisions.md#5-runtime-isolation-and-clinical-acceptance).

<!-- BEGIN GENERATED: road-tenancy -->

| wave | id | what | claimed state | waits on |
|---:|---|---|---|---|
| 1 | `A7A-7` | §7a item 7 - the clock question | `unsettled` | &mdash; |
| 1 | `ARCH-SEAM-CONTRACT` | First: portable storage and commit contract characterization | `in-progress` | &mdash; |
| 1 | `BFQ-CAP02` | CAP-02 - no importer, and no Mongo to PostgreSQL loader | `not-started` | &mdash; |
| 1 | `DISPLAY-MEAL-GROUP` | Show a bolus and its carbs as one meal in the display layer; storage de-duplicat | `not-started` | &mdash; |
| 1 | `ID-BATCH-RESULTS` | Release 2 (minor): per-item results in v1 batch replies; one bad item no longer  | `in-progress` | &mdash; |
| 1 | `ID-CONVENTIONS` | Identifier conventions: one URL-form identifier template per record kind and sou | `in-progress` | &mdash; |
| 1 | `ID-NATURAL-KEY` | Natural keys for re-sends that carry no identifier: device status and profile, w | `not-started` | &mdash; |
| 1 | `ID-RESEND-SWITCH` | A site setting plus per-client D20 quirks that opt a client into keep-first or r | `not-started` | &mdash; |
| 1 | `ID-V1-LOOKUP` | Release 2 (minor): v1 GET and DELETE by any identifier, without the default time | `blocked` | &mdash; |
| 1 | `ID-VALIDATE` | Release 2 (minor): validate identifier on every collection (1 to 256 URL-safe ch | `blocked` | &mdash; |
| 1 | `MT-AUTHZ-COST` | API authorization cost: permission snapshot, batched audit, bounded lifetime ses | `in-progress` | &mdash; |
| 1 | `MT-BATCH-JOIN-1110` | Join the 2026-11-10 decision batch (eight lanes) onto #8898 and run full accepta | `in-flight-upstream` | &mdash; |
| 1 | `MT-CAPACITY-FIXES` | Capacity campaign fixes: operator-set config size cap, realtime warm retry, boot | `in-progress` | &mdash; |
| 1 | `MT-D6-SLOT-READER` | D6 stage 2: replication-slot reader emits NOTIFY on one channel; bounded backsto | `in-progress` | &mdash; |
| 1 | `MT-ENDPOINT-TRANSPORT` | Component-private UDS/HTTP API composition and deployment acceptance | `in-progress` | &mdash; |
| 1 | `MT-OIDC-NATIVE` | M6a: run the nine-stage owner/OIDC native matrix through a disposable harness | `in-flight-upstream` | &mdash; |
| 1 | `MT-POOL-PRIMITIVE` | Shared pool-membership primitive (pool kind, member count, ordinal, ring slice)  | `ready-to-push` | &mdash; |
| 1 | `MT-REALTIME-SOCKET-CAP` | Realtime: remove the per-process socket cap, add disconnect cause codes, an unau | `in-progress` | &mdash; |
| 1 | `MT-TENANT-EXTENDED-SETTINGS` | Tenant environment carries plugin extended settings so the stale-data alarm can  | `in-flight-upstream` | &mdash; |
| 1 | `MT-TENANT-REGISTRY` | Tenant registry in PostgreSQL; provisioning separated from bootstrap and lab pri | `in-progress` | &mdash; |
| 1 | `MT-VAULT-TOKEN-FILE` | M6c: read the Vault token from a sink file per call (Vault Agent compatibility) | `in-flight-upstream` | &mdash; |
| 1 | `ST-VIEWS-PROFILE` | Next: refresh and integrate PR 8891 single nonresident profile | `in-progress` | &mdash; |
| 1 | `T31-REM` | T3.1 remainder - per-tenant signing key replaces the install-wide one | `blocked` | &mdash; |
| 1 | `T33-REM` | T3.3 remainder - the shared enclave, and language/levels per tenant | `blocked` | &mdash; |
| 1 | `T43` | T4.3 - ns-realtime, LISTEN per served tenant | `not-started` | &mdash; |
| 1 | `T44` | T4.4 - ns-evaluator, the per-tenant evaluation loop | `not-started` | &mdash; |
| 1 | `WC-R1-QG` | Refresh the write-contract spec's matrix tables against the dev db3b9e4e pin | `not-started` | &mdash; |
| 1 | `WC-R1-QI` | Retire websocket.js idMatch when the socket update slice moves into the step | `not-started` | &mdash; |
| 1 | `WC-R2-QA` | Release 2: Re-express API v3 writes as filter writes under the step, or keep two | `not-started` | &mdash; |
| 1 | `WC-R2-QB` | Release 2: One timing for removing a stored string-form _id twin on every path | `not-started` | &mdash; |
| 1 | `WC-R2-QC` | Release 2: Separate source labels for API v1 and in-process callers | `not-started` | &mdash; |
| 1 | `WC-R2-QD` | Release 2: One rule for a non-hex _id on in-process create and save | `not-started` | &mdash; |
| 1 | `WC-R2-QE` | Release 2: Answer an identical re-send as unchanged (nothing written, no srvModi | `not-started` | &mdash; |
| 1 | `WC-R2-QF` | Release 2: Move the lower half of write validation into the step, or decide it s | `not-started` | &mdash; |
| 1 | `WC-R2-QH` | Release 2: Decide whether v1 create keeps replace-on-match or follows merge-on-m | `not-started` | &mdash; |
| 2 | `A7A-3` | §7a item 3 - a per-tenant error boundary | `not-started` | `T44` |
| 2 | `A7A-4` | §7a item 4 - a health signal for a silent per-tenant outage | `not-started` | `T44` |
| 2 | `ARCH-DERIVED-FRAME` | Next join: shared bounded frames and derived calculations | `in-progress` | `ARCH-SEAM-CONTRACT`, `ST-VIEWS-PROFILE` |
| 2 | `ARCH-SEAM-COMPOSE` | First: separate domain definitions from backend and HTTP bindings | `in-progress` | `ARCH-SEAM-CONTRACT` |
| 2 | `BFQ-66` | BF-66 - the deployment's own tokens fail its own tenant check | `blocked` | `T31-REM` |
| 2 | `DEPLOY-VAULT-AGENT` | M6c: Vault Agent sidecar in the Compose binding (auto-auth, sink, renewal) | `in-progress` | `MT-VAULT-TOKEN-FILE` |
| 2 | `ID-UNIQUE-INDEX` | Partial unique index on identifier, retry-as-update on duplicate key, start-up s | `in-progress` | `ID-VALIDATE` |
| 2 | `MT-API-FIXED-ROSTER` | Independent API scaling with a fixed restore participant roster | `in-progress` | `MT-ENDPOINT-TRANSPORT` |
| 2 | `MT-CONNECTOR-REVERSE` | M6d: tenant-side Nightscout connector (vcpool) pulls a family's existing site in | `ready-to-push` | `MT-POOL-PRIMITIVE` |
| 2 | `MT-INTERNAL-LISTENER` | Internal listener: one serve.internal per role (Ory pattern, socket default) and | `in-flight-upstream` | `MT-ENDPOINT-TRANSPORT` |
| 2 | `MT-M6A-JOIN` | M6a: join the accepted owner/OIDC candidate to #8898 and run the final campaign | `in-flight-upstream` | `MT-OIDC-NATIVE` |
| 2 | `MT-REALTIME-SHARDING` | M7: realtime tenant sharding, controlled ownership moves and recovery | `in-progress` | `MT-ENDPOINT-TRANSPORT` |
| 2 | `MT-TENANT-LIVE-ADD` | Running evaluator and realtime pick up newly provisioned tenants without a resta | `in-progress` | `MT-TENANT-REGISTRY` |
| 3 | `A7A-GATE` | The alarms-on gate itself - nothing here may be marked done by inference | `blocked` | `T44`, `A7A-3`, `A7A-4`, `A7A-7` |
| 3 | `ARCH-SEAM-CONSOLIDATE` | Next: consolidate proven common adapter mechanics | `in-progress` | `ARCH-SEAM-CONTRACT`, `ARCH-SEAM-COMPOSE` |
| 3 | `DEPLOY-IDP-PROFILE` | M6c: Authentik identity-provider profile over HTTPS with synthetic people | `not-started` | `MT-M6A-JOIN` |
| 3 | `DEPLOY-TRUST-PROBES` | M6c: live spoof, conflict and outage probes against the Compose edge and Vault;  | `not-started` | `DEPLOY-VAULT-AGENT` |
| 3 | `MT-ANDROID-LAB` | M7: Android emulator acceptance for the pinned uploader and follower shapes | `not-started` | `MT-M6A-JOIN` |
| 3 | `MT-BENCH-BASELINE` | M7: benchmark the one-host reference and publish the numbers | `in-progress` | `MT-M6A-JOIN` |
| 3 | `MT-KEY-RETENTION` | M6b: 30-day retained-key destruction and after-window refusal | `in-flight-upstream` | `MT-M6A-JOIN` |
| 3 | `MT-M6B-JOIN` | Join M6b ownership/retention, single-site OIDC provisioning, listener compositio | `in-flight-upstream` | `MT-M6A-JOIN` |
| 3 | `MT-OIDC-SINGLE-PROVISION` | Single-site OIDC: declarative identity-to-role list and a role for signed-in str | `in-flight-upstream` | `MT-M6A-JOIN` |
| 3 | `MT-OWNERSHIP-OPS` | M6b: operator-assisted ownership add, transfer and recovery | `in-flight-upstream` | `MT-M6A-JOIN` |
| 4 | `ARCH-SQLITE-SPIKE` | Deferred low priority: hypothetical SQLite and cell adapter probe | `not-started` | `ARCH-SEAM-CONSOLIDATE`, `ARCH-DERIVED-FRAME` |
| 4 | `DEPLOY-K8S-BINDING` | M7: Kubernetes binding (one Pod per cohort, private socket volume, no-overlap up | `in-progress` | `DEPLOY-TRUST-PROBES` |
| 4 | `DEPLOY-TREE-HOME` | Move the Compose deploy tree to nightscout-deploy; core keeps the test fixture;  | `ready-to-push` | `MT-M6B-JOIN` |
| 4 | `MT-ACTIVITY-ELIGIBILITY` | Pause/suspend drive worker eligibility; evaluator stops while paused; owner may  | `in-flight-upstream` | `MT-M6B-JOIN` |
| 4 | `MT-ADMIN-ROLE-OWNERSHIP` | M6b: compose ownership operations into the multitenant admin role with an owners | `in-flight-upstream` | `MT-M6B-JOIN` |
| 4 | `MT-CONSUMER-STALE-RESELECT` | Alarm consumer survives evaluator timer publications during selection (BF-231) | `in-flight-upstream` | `MT-M6B-JOIN` |
| 4 | `MT-EVALUATOR-PARTITION` | M7: evaluator partitioning by member count and ordinal, with a pool-membership t | `in-progress` | `MT-BENCH-BASELINE` |
| 4 | `MT-EXPORT-EXPIRY` | Key destruction removes the export artifact file in the same audited step | `in-flight-upstream` | `MT-M6B-JOIN` |
| 4 | `MT-OWNER-LAST-GUARD` | M6b follow-up: refuse revoking the last usable owner's subject (BF-229) | `in-flight-upstream` | `MT-M6B-JOIN` |
| 5 | `MT-ADMIN-LIFECYCLE-FIT` | Restore census accepts non-clinical identities; ownership refuses on non-active  | `in-flight-upstream` | `MT-ADMIN-ROLE-OWNERSHIP` |
| 5 | `MT-PERF-DB` | Restore-fence epoch admission, bounded startup warm, pool configuration, serve-t | `ready-to-push` | `MT-EVALUATOR-PARTITION` |
| 5 | `MT-PERF-EVALUATOR` | Evaluator works on change: per-member change query and due-time timers replace t | `ready-to-push` | `MT-EVALUATOR-PARTITION` |
| 5 | `MT-PERF-REALTIME` | Realtime publishes on change; event-driven authorization; queued connects under  | `ready-to-push` | `MT-EVALUATOR-PARTITION` |
| 5 | `MT-ROOT-ADMIN-PARITY` | Multitenant tenant API_SECRET gets single-site admin parity: subjects, roles, ad | `in-flight-upstream` | `MT-OWNER-LAST-GUARD` |
| 5 | `MT-SCALE-UNBOUND` | M7: prove each component scales horizontally or vertically as intended, with no  | `in-progress` | `MT-BENCH-BASELINE`, `MT-API-FIXED-ROSTER`, `MT-REALTIME-SHARDING`, `MT-EVALUATOR-PARTITION` |
| 6 | `MT-EVAL-COST` | Evaluator per-evaluation cost: no per-cycle copies, dates parsed once, kept work | `ready-to-push` | `MT-PERF-EVALUATOR` |

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
