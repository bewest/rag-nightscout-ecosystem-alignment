# Roadmap for cgm-remote-monitor

*Contributor guide, updated 2026-11-24. Use this page for work order,
[programme status](PROGRAMME-STATUS.md) for the current state and
[review routing](NEEDS-A-HUMAN.md) for decisions.*

<a id="1-1509-is-released-the-next-development-cycle"></a>
<a id="1-1600-the-development-cycle-after-1509"></a>

## 1. Close the single-tenant 16.0.0 candidate

1. Identify the exact `official/dev` commit and image under test in the [release contents](../../releases/cgm-remote-monitor-16.0.0/contents.md). The [release decisions](../../releases/cgm-remote-monitor-16.0.0/decisions.md) define its scope.
2. Record the final-tree checks and the remaining live alarm, rig/cohort and rollback observations against that build. The [testing notes](../../releases/cgm-remote-monitor-16.0.0/testing-notes.md) give the evidence to capture. The [integration record](../30-design/remedial/rc-16.0.0-integration-record.md) identifies the builds covered by earlier runs.
3. Complete the private pre-tag work through the maintainer, repeat affected checks on the resulting tree, and complete staging and release review. Record the tag and verification at publication.

The prior train, `RT-0`, shipped as [15.0.9](../../releases/cgm-remote-monitor-15.0.9/contents.md).
Its queue dependencies are retained here for readers following that release.

<!-- BEGIN GENERATED: release-waits -->

| id | what | claimed state | waiting for | PR |
|---|---|---|---|---|
| &mdash; | nothing open blocks `RT-0` | | | |

<!-- END GENERATED: release-waits -->

## 2. Modernization: the release train

The browser and runtime cut (#8828), the build/runtime split (#8837), the MongoDB
cut (#8844) and the modernization merge (#8605) are ancestors of the 16.0.0 candidate.
The [versioning policy](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#83-the-release-train)
retains the rationale for their sequencing. The queue below includes follow-up
work. The `RT-16-RELEASE` row identifies its declared pre-tag dependencies.

A wave groups items by their outstanding dependencies. Wave 1 has no open
predecessor. Higher waves follow their latest open predecessor.

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

Multitenant development proceeds independently of the 16.0.0 release. Use the
[decisions in force](../30-design/tenancy/decisions-in-force.md) for role ownership,
writer-driven updates, storage and restore policy. The [execution log](../30-design/tenancy/execution-log.md)
identifies which changes joined each candidate and what its tests measured.

For a capacity claim, match the application, deployment and harness to the run,
then read its workload, completed interval, connector results and recovery evidence.
A passing point applies to that configuration. The [delivery dashboard](../30-design/tenancy/multitenant-delivery-dashboard.md)
and [production critical path](../30-design/tenancy/production-critical-path.md) give the
remaining admission criteria.

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
| 1 | `MT-D6-SLOT-READER` | D6: qualify default stream-fed clinical materialization and output recovery | `in-progress` | &mdash; |
| 1 | `MT-ENDPOINT-TRANSPORT` | Component-private UDS/HTTP API composition and deployment acceptance | `in-progress` | &mdash; |
| 1 | `MT-OIDC-NATIVE` | M6a: run the nine-stage owner/OIDC native matrix through a disposable harness | `in-flight-upstream` | &mdash; |
| 1 | `MT-POOL-PRIMITIVE` | Shared pool-membership primitive (pool kind, member count, ordinal, ring slice)  | `in-flight-upstream` | &mdash; |
| 1 | `MT-REALTIME-SOCKET-CAP` | Realtime: remove the per-process socket cap, add disconnect cause codes, an unau | `in-progress` | &mdash; |
| 1 | `MT-TENANT-EXTENDED-SETTINGS` | Tenant environment carries plugin extended settings so the stale-data alarm can  | `in-flight-upstream` | &mdash; |
| 1 | `MT-TENANT-REGISTRY` | Tenant registry in PostgreSQL; provisioning separated from bootstrap and lab pri | `in-progress` | &mdash; |
| 1 | `MT-VAULT-TOKEN-FILE` | M6c: read the Vault token from a sink file per call (Vault Agent compatibility) | `in-flight-upstream` | &mdash; |
| 1 | `PERF-IMAGE-DIGEST-CACHE` | Remote and capacity run bundles reference image exports by digest instead of sav | `not-started` | &mdash; |
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
| 2 | `MT-CONNECTOR-REVERSE` | M6d: tenant-side Nightscout connector (vcpool) pulls a family's existing site in | `in-flight-upstream` | `MT-POOL-PRIMITIVE` |
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
| 4 | `DEPLOY-TREE-HOME` | Move the Compose deploy tree to nightscout-deploy; core keeps the test fixture;  | `in-progress` | `MT-M6B-JOIN` |
| 4 | `MT-ACTIVITY-ELIGIBILITY` | Pause/suspend drive worker eligibility; evaluator stops while paused; owner may  | `in-flight-upstream` | `MT-M6B-JOIN` |
| 4 | `MT-ADMIN-ROLE-OWNERSHIP` | M6b: compose ownership operations into the multitenant admin role with an owners | `in-flight-upstream` | `MT-M6B-JOIN` |
| 4 | `MT-CONSUMER-STALE-RESELECT` | Alarm consumer survives evaluator timer publications during selection (BF-231) | `in-flight-upstream` | `MT-M6B-JOIN` |
| 4 | `MT-EVALUATOR-PARTITION` | M7: evaluator partitioning by member count and ordinal, with a pool-membership t | `in-progress` | `MT-BENCH-BASELINE` |
| 4 | `MT-EXPORT-EXPIRY` | Key destruction removes the export artifact file in the same audited step | `in-flight-upstream` | `MT-M6B-JOIN` |
| 4 | `MT-OWNER-LAST-GUARD` | M6b follow-up: refuse revoking the last usable owner's subject (BF-229) | `in-flight-upstream` | `MT-M6B-JOIN` |
| 5 | `MT-ADMIN-LIFECYCLE-FIT` | Restore census accepts non-clinical identities; ownership refuses on non-active  | `in-flight-upstream` | `MT-ADMIN-ROLE-OWNERSHIP` |
| 5 | `MT-PERF-DB` | Restore-fence epoch admission, bounded startup warm, pool configuration, serve-t | `in-flight-upstream` | `MT-EVALUATOR-PARTITION` |
| 5 | `MT-PERF-EVALUATOR` | Evaluator works on change: per-member change query and due-time timers replace t | `in-flight-upstream` | `MT-EVALUATOR-PARTITION` |
| 5 | `MT-PERF-REALTIME` | Realtime publishes on change; event-driven authorization; queued connects under  | `in-flight-upstream` | `MT-EVALUATOR-PARTITION` |
| 5 | `MT-ROOT-ADMIN-PARITY` | Multitenant tenant API_SECRET gets single-site admin parity: subjects, roles, ad | `in-flight-upstream` | `MT-OWNER-LAST-GUARD` |
| 5 | `MT-SCALE-UNBOUND` | M7: prove each component scales horizontally or vertically as intended, with no  | `in-progress` | `MT-BENCH-BASELINE`, `MT-API-FIXED-ROSTER`, `MT-REALTIME-SHARDING`, `MT-EVALUATOR-PARTITION` |
| 6 | `MT-EVAL-COST` | Evaluator per-evaluation cost: no per-cycle copies, dates parsed once, kept work | `in-flight-upstream` | `MT-PERF-EVALUATOR` |

<!-- END GENERATED: road-tenancy -->

## 4. Remedial: fix what ships

The [register](../30-design/remedial/nightscout-backfix-register.md) gives affected
versions and evidence for each defect. Use the [operator exposure table](PROGRAMME-STATUS.md#status-words-merged-is-not-released)
to find the queue items that cover the shipping release.

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

## 6. Review and decisions

The [reviewer guide](REVIEWER-ONBOARDING.md) identifies the evidence a reviewer needs.
[Work waiting on a person](NEEDS-A-HUMAN.md) groups the queue by reviewer and decision owner.

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-27**, against cgm-remote-monitor-official `7000eb18` and this repository at `18cdcce0`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
