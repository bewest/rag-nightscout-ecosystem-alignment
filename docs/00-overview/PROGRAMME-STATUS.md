# Programme status — cgm-remote-monitor

*Maintained by the Nightscout Foundation. Contributor-facing; technical throughout.
Prose revised 2026-09-24 against cgm-remote-monitor `origin/dev` `153e5658` and
`origin/master` `92d08342` (tag `15.0.8`). The tables are generated from
`queue/work-queue.yaml`; see [How to check any of this yourself](#how-to-check-any-of-this-yourself).*

This page answers "where is the work, and what is it waiting for" across the three
horizons the project runs in parallel. The detail lives in the queue, the backfix
register and the design documents; this page says which of those to open.

The counts below are generated and `make views-check` fails when they drift. The
prose is hand-written and dated. Where the prose and a table disagree, the table is
current and the prose is stale.

---

## The three horizons

<!-- BEGIN GENERATED: horizons -->

| horizon | parcels | items | claimed `not-started` | claimed waiting on a person |
|---|---|---:|---:|---:|
| **Remedial** | `phase0`, `register-open`, `docs-truth` | 91 | 28 | 18 |
| **Modernization** | `release-train` | 25 | 5 | 3 |
| **Multitenant** | `tenancy` | 18 | 9 | 3 |
| | **total** | **136** | **42** | **24** |

<!-- END GENERATED: horizons -->

**Remedial** — finding and fixing defects that already ship. Twenty-seven pull requests
from this work are merged into cgm-remote-monitor `dev`: this programme's #8733, #8734,
#8735, #8736, #8737, #8738, #8739, #8740 and #8743 (2026-09-17 to 2026-09-20), the three
advisory fixes #8744, #8745 and #8746 (2026-09-21), #8741 from an external contributor
(2026-09-20), eleven of the thirteen 15.0.9 additions (#8748 to #8753, #8755 to #8757, #8759,
#8760, 2026-09-23), #8761 and #8762, and #8754 (login security fixes and `TRUST_PROXY`, with #8763
and #8765 folded in; merged as `4f705217`), all 2026-09-24. None is released. Open: #8758 (records
keep their own `_id`). Every programme connector fix is
in `nightscout-connect` `0.1.0`, released to npm `latest` on 2026-09-24 (`P0-TAG`, tag `v0.1.0` on
connector `main` `4dde1ec`). Nightscout `dev` pins it exactly (#8762). The freeze candidate, `dev`
`4f705217` + #8758 `ab7b22d6` (tree `25ab7afc`), passed 3066/0/3 on Node 20, 22 and 24 against
MongoDB 4.4.24 and 7.0.43 on 2026-09-25
([15.0.9 integration record](../30-design/remedial/rc-15.0.9-integration-record.md)); `dev` `4f705217`
on its own passes 2577/0/3 and is green in CI. The
[backfix register](../30-design/remedial/nightscout-backfix-register.md) holds the defect facts;
`make queue-coverage` proves the queue names every entry that is not fixed.

**Modernization** — bringing dependencies and code up to date. The adopted release
train is 15.0.9, then cut 1 (`chore/retire-jsdom`), then cut 2, then cuts 3+5 combined,
then cut 4. The separate deprecation release was dropped (`RT-4`): the MiniMed warning in
15.0.9 (#8757) names the replacement settings, and on 2026-09-23 the maintainer moved the
legacy MiniMed and Dexcom bridge removal onto cut 1, keeping the hard stop at boot
(BF-61, option A). mmconnect is reported not to work, and Dexcom `BRIDGE_*` settings have
been served by `nightscout-connect` since 15.0.8, so BF-44/BF-45 are graded low. Nothing on
the train has shipped. Measured 2026-09-23 against `origin/dev` `ddd9b600`:

| cut | branch | behind `dev` | conflicting paths |
|---|---|---:|---:|
| 1 | `chore/retire-jsdom` | 170 | 9 |
| 2 | `chore/build-runtime-separation` | 170 | 15 |
| 3 | `chore/compose-mongodb6` | 170 | 17 |
| 4 | `chore/mime-exposure-review` | 170 | 22 |
| 5 | `chore/nightscout-modernization` | 46 | 9 |

Reproduce with `git -C externals/cgm-remote-monitor-official rev-list --count
origin/chore/<branch>..origin/dev` and `git merge-tree --write-tree --name-only
origin/dev origin/chore/<branch>`; the trial merges are `RT-REBASE`'s and `RT-3`'s
gates. The files newly conflicting on cuts 2–4 were touched by the merged Phase 0
PRs, so every merge to `dev` raises the rebase cost of the train.

**Multitenant** — making bulk hosting feasible. Decisions D1–D17 are recorded in the
[execution plan](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md);
D17 is adopted in three of four rows, with row 2 (cohort-wide human identity) held
pending `T30-ORY-PROOF`. Most implementation is not started, and several items are
blocked behind remedial and release work. Self-hosted single-tenant stays
first-class permanently (D1, D4): multitenancy is a second deployment target, never a
replacement.

---

## Status words: merged is not released

**In the backfix register, neither `fixed` nor `merged` means an operator is safe.**
`fixed` means repaired on a branch that has not been merged. `merged` means merged
into `origin/dev` and not released. `released` means in a tagged release operators
run, and no programme fix is released: `origin/master` is 345 commits behind `dev`
(`git -C externals/cgm-remote-monitor-official rev-list --count origin/master..origin/dev`,
2026-09-23) and the shipping tag is 15.0.8. Merging to `dev` publishes a Docker Hub
image; that is not a release. `RT-0` (release 15.0.9) is the item that changes this;
release PR #8598 is open at `ddd9b600`, green on every CI check, and has no approving
review.

For somebody running Nightscout today:

> A defect this project has marked "fixed" or "merged" is fixed in code that has not
> been released yet. If you are running today's Nightscout (15.0.8), the defect is
> still there. None of this is medical advice; if a defect affects alarms or
> displayed numbers and you are unsure what it means for you, raise it with your care
> team.

The size of that, as computed on 2026-09-21 by the coverage gate's parser from the
register's §1 (the section whose defects reach existing operators): 56 rows, one of
which (BF-12) does not reproduce, so **55 defects are present for every self-hoster on
15.0.8** — 23 `open`, 27 `merged`, 1 `partly merged` (BF-07), 4 `fixed`. Re-derive from
the register's §1 before quoting it; it moves when entries are filed or merged.

The register's `open` count is therefore not "the number of defects still shipping":
it omits the 32 repaired-but-unreleased ones. The status column tracks work done, not
operator exposure, which is why the queue carries `ships_to_operators_today` as a
separate field.

These are the queue items covering that exposure — items, not defect ids, so several
cover more than one `BF-`:

<!-- BEGIN GENERATED: operator-exposure -->

| id | claimed state | defect |
|---|---|---|
| `ADV-ALARM` | `merged-upstream` | GHSA-8849 - /alarm broadcasts to the whole namespace (BF-75, BF-76) |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind both (BF-7 |
| `ADV-RETRO` | `merged-upstream` | GHSA-gjhc - loadRetro serves devicestatus to any socket (BF-79) |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) |
| `BFQ-04` | `merged-upstream` | BF-04 - the v1 operator allowlist - superseded by P0-K |
| `BFQ-09` | `unsettled` | BF-09 - socket dedup truthiness skips a falsy value |
| `BFQ-10` | `merged-upstream` | BF-10 - mongod fatal-asserts at Docker's default nofile=1024 |
| `BFQ-100` | `blocked` | BF-100 - devicestatus, food and activity store a hex _id as a string |
| `BFQ-101` | `blocked` | BF-101 - API v3 id filters miss records stored with a string _id |
| `BFQ-102` | `in-flight-upstream` | bf/object-id-consistency - one rule for a record's own hex _id across profile, devicestatu |
| `BFQ-103` | `merged-upstream` | BF-103 - a split drag stores the old time, so IOB and COB ignore the move |
| `BFQ-107` | `merged-upstream` | BF-107 - a failed treatments query ends the Nightscout process on 15.0.8 |
| `BFQ-108` | `not-started` | BF-108 - a list of timestamps under the date field answers 500, so bulk deletes by timesta |
| `BFQ-111` | `ready-to-push` | BF-111 - find[_id][$in] misses records stored with a string _id, for reads and bulk delete |
| `BFQ-112` | `ready-to-push` | BF-112 - an auth subject created with a hex _id is stored as a string and cannot be delete |
| `BFQ-114` | `in-flight-upstream` | BF-114 - an AAPS open-ended loop disable keeps loop and pump alerts off after the loop is  |
| `BFQ-115` | `ready-to-push` | BF-115 - an entry or treatment with an unusable _id is stored with it, and one such value  |
| `BFQ-117` | `ready-to-push` | BF-117 - an API v3 DELETE of a record stored twice leaves one copy valid; on #8758 v3 read |
| `BFQ-40` | `merged-upstream` | BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion |
| `BFQ-46` | `gate-not-met` | BF-46 - eleven API v3 variables bypass env.js, one family deletes data |
| `BFQ-47` | `in-flight-upstream` | BF-47 - an ordinary subject edit destroys stored fields, on today's release |
| `BFQ-52` | `blocked` | BF-52 - an age reminder whose 20-minute window passed without a check was never sent |
| `BFQ-67` | `gate-not-met` | BF-67, BF-86 - alarm thresholds quietly changed, or quietly kept when they cannot work |
| `BFQ-69` | `merged-upstream` | BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing |
| `BFQ-71` | `gate-not-met` | BF-71 - any dateString key drops the default date window, and the window is not a control |
| `BFQ-72` | `needs-decision` | BF-72 - an unauthenticated $regex can spend minutes of database CPU |
| `BFQ-87` | `merged-upstream` | BF-87 - the root qs override holds the connector below its range and pins the server's que |
| `BFQ-90` | `merged-upstream` | BF-90 - an alarm at a page with no reading throws in the client |
| `BFQ-91` | `merged-upstream` | BF-91 - connector capture mode cannot find trace-axios for two sources |
| `BFQ-92` | `not-started` | BF-92 - a page with no glucose reading never presents a server alarm, including device ala |
| `BFQ-93` | `not-started` | BF-93 - food changes never reach an open page |
| `BFQ-94` | `unsettled` | BF-94 - a kept profile instance can return a temp basal that has been replaced |
| `BFQ-95` | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm |
| `BFQ-98` | `merged-upstream` | BF-98 - the connector reuses a reader subject without roles, so the BF-89 fix does not rep |
| `BFQ-99` | `blocked` | bf/profile-object-id - a profile posted with its own _id is stored as an ObjectId, and str |
| `BFQ-CAP01` | `not-started` | CAP-01 - Nightscout cannot be served from a sub-path |
| `BFQ-CONNECTOR` | `gate-not-met` | BF-42, BF-43 - master pins the leaking connector, with a violated axios override |
| `BFQ-ENV` | `gate-not-met` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies |
| `BFQ-MINIMED` | `not-started` | BF-44, BF-45, BF-85 - MiniMed ingestion divergences and the CareLink zero reading |

<!-- END GENERATED: operator-exposure -->

---

## Where the work stands

Claimed state by parcel. Every cell is a **claim** about what the gates will say.

<!-- BEGIN GENERATED: state-matrix -->

| parcel | `not-started` | `in-progress` | `gate-not-met` | `ready-to-push` | `blocked` | `in-flight-upstream` | `merged-upstream` | `needs-decision` | `done` | `unsettled` | `closed` | `answered` | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `phase0` | 3 |  | 1 | 1 |  |  | 16 |  | 1 |  |  |  | **22** |
| `release-train` | 5 |  | 4 |  | 5 | 2 | 7 | 1 |  |  |  | 1 | **25** |
| `register-open` | 18 | 1 | 5 | 8 | 4 | 3 | 13 | 4 |  | 2 | 1 |  | **59** |
| `tenancy` | 9 |  | 1 | 1 | 5 |  |  | 1 |  | 1 |  |  | **18** |
| `docs-truth` | 7 |  | 1 |  |  |  |  |  | 2 |  |  |  | **10** |
| `backfix2` |  |  |  |  |  |  | 2 |  |  |  |  |  | **2** |

<!-- END GENERATED: state-matrix -->

Three states here are not what a casual reader expects:

- **`gate-not-met`** is a *measured* state, not an opinion. Work exists and a
  declared gate fails.
- **`in-flight-upstream`** means handed to upstream reviewers and not ours to land.
- **`merged-upstream`** means merged into `dev` and not released. It is deliberately
  not called `done`: nothing merged has reached an operator.

The queue also carries **explicit `no-gate:` markers** — a record that nobody has
built a way to measure a property yet, with the reason. They are bookkeeping, not
gaps in it; `make queue-validate` prints how many gate slots are in that state.

---

## The two constraints, neither of them engineering

**1. Publication is a manual human act, on purpose.** Agents prepare branches,
commits and tags locally and stop. A human pushes, merges, tags and publishes. This
is a standing rule. Pushing to cgm-remote-monitor's `dev` or `master` fires
`main.yml`'s `docker-build` job and publishes a Docker Hub image, so **`dev` and
`master` are publication events, not branches**. A release is three separate human
decisions: merge the code, push the tag, publish the package.

**2. Review capacity is one person.** This is a governance fact rather than a
technical one: all 495 modernization commits have one author, and all 100 child pull
requests were self-merged with zero human reviews. Confidence currently rests on
automated gates and the author's own evidence documents.

Where the queue says each item's review has to come from:

<!-- BEGIN GENERATED: reviewer-load -->

| the item is waiting for | items | share |
|---|---:|---:|
| Maintainer | 102 | 75% |
| SECURITY reviewer | 15 | 11% |
| Maintainer + a second human | 7 | 5% |
| SAFETY reviewer | 6 | 4% |
| Whoever edits it next | 3 | 2% |
| Unassigned | 2 | 1% |
| Upstream reviewers | 1 | 1% |
| **total** | **136** | |

<!-- END GENERATED: reviewer-load -->

The SECURITY and SAFETY rows name a *kind* of reviewer. For the one security PR still open,
#8754 (login security fixes and `TRUST_PROXY`), the reviewers are the maintainer and Andy. The
other SECURITY and SAFETY rows still have no individual assigned. `BFQ-72` (BF-72, an
unauthenticated request that can occupy the database for minutes, live on 15.0.8 and `dev`)
has a disposition decided by the maintainer and held outside version control.

If you are considering reviewing, [REVIEWER-ONBOARDING.md](REVIEWER-ONBOARDING.md)
is the read-this-first path, and `reports/reviewer-packets/` has one bounded packet
per item awaiting review.

---

## What would move the picture

These are decisions, not tasks; no amount of engineering advances them. Each is
expanded in [NEEDS-A-HUMAN.md](NEEDS-A-HUMAN.md).

| | decision | why it blocks a train |
|---|---|---|
| `RT-0` | Release 15.0.9 (PR #8598, at `dev` `153e5658`, no approving review). | Every merged fix reaches operators only through it, and every later cut waits behind it. Before the tag: #8754, #8758, the release notes. |
| `BFQ-09` | BF-09: is a zero-valued temp basal a real value in the socket dedup? Measured; waits on the maintainer. | It ships to operators now. |
| `A7A-7` | The clock question inside the alarm path. The maintainer owns it. | It gates alarms under `TENANCY_MODE=multi`. |

`P0-TAG` (done: `nightscout-connect` 0.1.0 released and pinned by #8762) left this table on
2026-09-24. `RT-D3` (answered: the drag check passed in automation and by hand, and 15.0.9 ships as numbered),
`BFQ-47` (decided: the allow-list is intended; the admin-page fix is in #8754) and `BFQ-72` (decided
privately) left this table on 2026-09-23.

---

## How to check any of this yourself

```bash
make queue-status          # run every static + unit gate. The measurement.
make queue-status PARCEL=phase0
make queue-check           # CI: register coverage, then staleness of every generated view, then links
make queue-vacuity         # ask every gate whether it can actually fail
make views-check           # fail if the generated blocks on this page are stale
```

`queue/QUEUE.md` is the full generated view of all items. `queue/README.md`
explains the manifest's fields and why `state` is a claim rather than a
measurement.

---

## Where each claim on this page comes from

| claim | authority |
|---|---|
| what "done" means for these documents | [`DEFINITION-OF-DONE.md`](DEFINITION-OF-DONE.md) |
| the order of the work ahead | [`ROADMAP.md`](ROADMAP.md) |
| item state, gates, review routing | `queue/work-queue.yaml` (source of truth) |
| defect facts and `BF-` ids | [`../30-design/remedial/nightscout-backfix-register.md`](../30-design/remedial/nightscout-backfix-register.md) |
| what 15.0.9 contains and whether it is ready | [`../30-design/modernization/release-readiness-15.0.9-2026-09-22.md`](../30-design/modernization/release-readiness-15.0.9-2026-09-22.md) |
| Phase 0 PR ordering and coupling | [`../30-design/remedial/phase0-pr-sequencing-2026-09-15.md`](../30-design/remedial/phase0-pr-sequencing-2026-09-15.md) |
| the release train and its order | [`../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md) |
| tenancy decisions D1–D17 | [`../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) |
| the governance / zero-reviews finding | [`../30-design/remedial/maintainer-release-brief-2026-09-15.md`](../30-design/remedial/maintainer-release-brief-2026-09-15.md) |

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-24**, against cgm-remote-monitor-official `153e5658` and this repository at `b362302b`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
