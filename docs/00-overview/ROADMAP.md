# Roadmap — what comes next, and in what order

*Maintained by the Nightscout Foundation. Contributor-facing. Living document: prose dated
2026-09-25 against cgm-remote-monitor `origin/dev` `4f705217` and `origin/master` `92d08342`
(tag `15.0.8`). The two order tables are generated from `queue/work-queue.yaml`, and
`make views-check` fails when they drift.*

This page gives the order of the work ahead. It records no decisions itself. The decisions
live in these places, and this page links to them:

| what | where it is decided |
|---|---|
| the release train and each release's number | [versioning policy §8.3](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#83-the-release-train) |
| tenancy decisions D1–D17 and the tenancy task definitions | [multitenancy execution plan](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) |
| defect facts, and what ships to operators today | [backfix register](../30-design/remedial/nightscout-backfix-register.md) |
| each item's state, gate and blockers | `queue/work-queue.yaml`; `make queue-status` measures it |

For where things stand, see [PROGRAMME-STATUS](PROGRAMME-STATUS.md). For which decisions are
waiting on a person, see [NEEDS-A-HUMAN](NEEDS-A-HUMAN.md).

**How to read the order tables.** An item's *wave* comes from the blockers it is still waiting
on. An item waiting on nothing that is still open is wave 1. Any other item is one wave later
than its latest-wave open blocker. Items that are merged, done, closed or answered are left out.
A wave shows dependency, not a date. The states shown are claims about what the gates will say,
not measurements.

---

## 1. The next release: 15.0.9

Everything merged since 15.0.8 reaches operators only through 15.0.9 (queue `RT-0`, release PR
#8598), and every later step waits behind it. Operators running 15.0.8 keep every defect fixed on
`dev` until it is tagged.

**What 15.0.9 still waits on**, generated from `RT-0`'s open blockers:

<!-- BEGIN GENERATED: release-waits -->

| id | what | claimed state | waiting for | PR |
|---|---|---|---|---|
| `RT-VERSION` | Two artefacts claim version 15.0.9 with different Node floors | `not-started` | Maintainer | &mdash; |
| `BFQ-102` | bf/object-id-consistency - one rule for a record's own hex _id across profile, d | `in-flight-upstream` | Maintainer | #8758 |
| `RT-PR-8419` | #8419 - tests for Loop push notifications and websockets (je-l), carried into 15 | `gate-not-met` | Maintainer | #8419 |
| `RT-PR-8730` | #8730 - Crowdin translation updates, carried into 15.0.9 | `gate-not-met` | Maintainer | #8730 |

<!-- END GENERATED: release-waits -->

Also before the tag, and not queue items of their own (they are in `RT-0`'s notes and gates):
the Loop remote-command browser checks that #8764 made necessary, the release notes, a review of
#8598 by someone other than the author, and the maintainer's tag.

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
| 1 | 15.0.9 | `dev` as it stands |
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
rebase cut 1 is right after 15.0.9 is tagged, while `dev` is quiet.

<!-- BEGIN GENERATED: road-release-train -->

| wave | id | what | claimed state | waits on |
|---:|---|---|---|---|
| 1 | `RT-BOOTERROR` | BF-63 - the page that reports a boot error crashes on cut 4's boot errors | `gate-not-met` | &mdash; |
| 1 | `RT-CONNECT-PIN-CUTS` | BF-65 - cuts 1-3 ship the leaking connector to upgraders first | `gate-not-met` | &mdash; |
| 1 | `RT-PR-8419` | #8419 - tests for Loop push notifications and websockets (je-l), carried into 15 | `gate-not-met` | &mdash; |
| 1 | `RT-PR-8730` | #8730 - Crowdin translation updates, carried into 15.0.9 | `gate-not-met` | &mdash; |
| 1 | `RT-REBASE` | Cuts 1-4 are 133 commits behind dev and now all five conflict | `gate-not-met` | &mdash; |
| 1 | `RT-SOAK` | tools/lab/rc-soak - A/B soak of the 15.0.9 candidate against 15.0.8, and a 24-72 | `in-progress` | &mdash; |
| 1 | `RT-VERSION` | Two artefacts claim version 15.0.9 with different Node floors | `not-started` | &mdash; |
| 2 | `OID-MIGRATION` | Opt-in migration that stores every string _id as the ObjectId it names, then ret | `not-started` | `BFQ-102`, `OID-PREVALENCE` |
| 2 | `OID-STORAGE-HELPER` | One storage-level rule for writes by _id instead of six hand-written copies | `not-started` | `BFQ-102` |
| 2 | `OID-V3-EDIT-MERGE` | API v3 PUT and PATCH of a record stored twice by _id leave both copies; make an  | `not-started` | `BFQ-117` |
| 2 | `OID-WS-EDIT-MERGE` | Websocket dbUpdate of a record stored twice by _id edits both copies and leaves  | `not-started` | `BFQ-102` |
| 2 | `RT-0` | Release 15.0.9 | `needs-decision` | `RT-VERSION`, `BFQ-102`, `RT-PR-8419`, `RT-PR-8730` |
| 3 | `RT-1` | Cut 1 - chore/retire-jsdom | `blocked` | `RT-0`, `RT-REBASE` |
| 4 | `RT-2` | Cut 2 - chore/build-runtime-separation | `blocked` | `RT-1` |
| 4 | `RT-D3-SUITE` | The treatment-drag clamps get a regression test in cut 1's real-browser suite | `blocked` | `RT-1` |
| 4 | `RT-NODE-FLOOR-TESTED` | BF-58, BF-59 - the enforced Node floor is not the Node anything exercises | `gate-not-met` | `RT-1` |
| 5 | `RT-3` | Cuts 3+5 combined - dependency release | `blocked` | `RT-2` |
| 6 | `RT-5` | Cut 4 - chore/mime-exposure-review, the one to slow down on | `blocked` | `RT-3` |

<!-- END GENERATED: road-release-train -->

## 3. Multitenant

Self-hosted, single-tenant Nightscout stays first-class permanently (D1, D4). Multitenancy is a
second deployment target and never replaces it.

**The schedule is bounded by the release train.** Tenancy work is based on
`chore/nightscout-modernization` (D9), so no tenancy code reaches a release before cuts 3 + 5.
Until then, the order below is the order of development, not of release.

- **First, the seam refresh (`SEAM-REFRESH`).** The storage-seam branches fall further behind
  their base on their own, and the conflicts are in the v1 API and server storage modules. Plan §5
  records how to refresh safely.
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
| 1 | `SEAM-REFRESH` | Refresh the seam chain onto a moved modernization branch | `gate-not-met` | &mdash; |
| 1 | `T30-AUTH` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-i | `ready-to-push` | &mdash; |
| 1 | `T30-ORY-PROOF` | Stand up Kratos 1.x and Hydra 2.x and try to make one pool serve two tenants | `not-started` | &mdash; |
| 1 | `T30-RESEARCH` | T3.0 part 1 - enumerate the per-tenant configuration surface | `needs-decision` | &mdash; |
| 1 | `T30-SCHEMA-CRED` | T3.0 part 2a - device and data-path credential storage in platform.sql | `not-started` | &mdash; |
| 1 | `T43` | T4.3 - ns-realtime, LISTEN per served tenant | `not-started` | &mdash; |
| 2 | `T30-SCHEMA-CONFIG` | T3.0 part 2b - per-tenant configuration table, and where human identity lives | `not-started` | `T30-RESEARCH`, `T30-ORY-PROOF` |
| 3 | `BFQ-CAP02` | CAP-02 - no importer, and no Mongo to PostgreSQL loader | `not-started` | `T30-SCHEMA-CRED`, `T30-SCHEMA-CONFIG` |
| 3 | `T30-WIRING` | T3.0 part 3 - deriveEnv overrides, tenant-scoped isApiKey/verifyJWT | `not-started` | `T30-SCHEMA-CRED`, `T30-SCHEMA-CONFIG` |
| 3 | `T32-REM` | T3.2 remainder - platform.sql carries no config, secret or signing key | `blocked` | `T30-SCHEMA-CRED`, `T30-SCHEMA-CONFIG` |
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

## 5. Proposals not yet adopted

These are proposals for discussion with other projects and maintainers. Nothing in them is
scheduled.

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

## 6. What bounds all of it

Review capacity, not engineering. Most queue items route to the maintainer, and the SECURITY and
SAFETY review rows do not name a person. The current split is on
[PROGRAMME-STATUS](PROGRAMME-STATUS.md#the-two-constraints-neither-of-them-engineering). Onboarding
for reviewers is in [REVIEWER-ONBOARDING](REVIEWER-ONBOARDING.md).

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-24**, against cgm-remote-monitor-official `153e5658` and this repository at `b362302b`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
