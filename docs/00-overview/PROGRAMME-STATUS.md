# Programme status — cgm-remote-monitor

*Maintained by the Nightscout Foundation. Contributor-facing; technical throughout.
Last narrative revision 2026-09-21. The tables are generated — see [How to check any
of this yourself](#how-to-check-any-of-this-yourself).*

This is the one-page answer to "where is the work, and what is it waiting for". It
covers the three horizons the project runs in parallel, and it is deliberately
short: the detail lives in the queue, the register and the design documents, and
this page's job is to say which of those to open.

> **A page like this is exactly the thing that rots.** So the counts below are
> generated from `queue/work-queue.yaml` and `make views-check` fails when they
> drift. The prose is hand-written and carries a date. If the prose and a table
> disagree, **the table is right and the prose is stale** — that is the whole
> reason the split exists.

---

## The three horizons

<!-- BEGIN GENERATED: horizons -->

| horizon | parcels | items | claimed `not-started` | claimed waiting on a person |
|---|---|---:|---:|---:|
| **Remedial** | `phase0`, `register-open`, `docs-truth` | 59 | 21 | 12 |
| **Modernization** | `release-train` | 12 | 2 | 2 |
| **Multitenant** | `tenancy` | 18 | 9 | 3 |
| | **total** | **89** | **32** | **17** |

<!-- END GENERATED: horizons -->

**Remedial** — finding and fixing defects that already ship. This is the largest
horizon and by far the most advanced. **Ten pull requests MERGED upstream between
2026-09-17 and 2026-09-20** (#8733–#8743); one remains open, and it is in the
connector repository rather than here (`nightscout-connect` PR #68). The backfix
register holds 74 entries; the queue names every not-fixed one. Merged is not
released — see [the sentence that changes how everything else
reads](#the-sentence-that-changes-how-everything-else-reads).

**Modernization** — bringing dependencies and code up to date. A release train is
adopted and ordered: 15.0.9, then cut 1 (`chore/retire-jsdom`) alone, then cut 2,
then cuts 3+5 combined, with **cut 4 held back behind its own deprecation
release** because it deletes two CGM ingestion paths and its failure mode is a
user's glucose readings silently stop arriving. Nothing on this train has shipped,
and **the cost of not shipping it is measurable and rising**: re-measured
2026-09-21, cuts 1–4 are **124 commits behind `dev`** (was 59 on 2026-09-15) with
7, 14, 16 and 18 conflicting paths respectively (was 4–5 each). Every one of the
seven files newly conflicting on cuts 2–4 was touched by the ten Phase 0 PRs
landing — so the remedial horizon's success is what raised this bill. Cut 5 is the
exception and is 0 behind `dev`, because Andy Low merged `dev` into it on
2026-09-21 (`e3b22034`).

**Multitenant** — making bulk hosting feasible. Decisions D1–D15 are settled and
recorded; most implementation is not started, and five items are blocked behind
remedial and release work. Self-hosted single-tenant stays first-class permanently
(D1, D4) — multitenancy is a second deployment target, never a replacement.

---

## The sentence that changes how everything else reads

**In the backfix register, neither `fixed` nor `merged` means an operator is
safe.** `fixed` means repaired on a branch that has not been merged. `merged`
(added 2026-09-21) means merged into `origin/dev` and **still not released**. No
entry anywhere carries a status of `landed`, because nothing has landed:
`origin/master` is **308 commits behind `dev`** and the shipping tag is **15.0.8**.
Merging to `dev` publishes a Docker Hub image, which is not a release.

For somebody running Nightscout today, the practical version is plainer:

> A defect this project has marked "fixed" is fixed in code that has not been
> released yet. If you are running today's Nightscout, the defect is still there.
> None of this is medical advice; if a defect affects alarms or displayed numbers
> and you are unsure what it means for you, raise it with your care team.

**The size of that, re-measured 2026-09-21 late evening with the coverage gate's own
parser rather than by hand.** The register's §1 — the section whose defects reach
existing operators — holds **56 rows**, of which one (BF-12) is retracted as not
reproducing. So **55 defects are present for every self-hoster running today's
release**. Of those: **23 open**, **27 `merged`** (in `dev`, not released), **1
`partly merged`** (BF-07), **4 `fixed`** (on a branch not merged).

**That is up from 46 earlier the same day, and none of the increase is a regression.**
Nine entries (BF-73…BF-81) were filed on 2026-09-21 while three sessions worked
through the five open GitHub security advisories, and BF-07 had been dropped by every
previous hand-count. Four of the nine — BF-75, BF-76, BF-77, BF-79 — were repaired and
merged the same evening, which moves them from `open` to `merged` and moves them not
at all with respect to an operator.

Reading the register's open count as "the number of defects still shipping"
therefore understates it by well over a factor of two, because it silently
drops the 32 repaired-but-unreleased ones. Reading `merged` as done would drop 27 of
them — a newer way to get the same number wrong, which is why the status values were
split rather than collapsed. The distinction the status column actually tracks is
**work done**, not operator exposure, and that is why the queue carries
`ships_to_operators_today` as a separate field rather than inferring it.

These are the queue items covering that exposure — items, not defect ids, so
several cover more than one `BF-`:

<!-- BEGIN GENERATED: operator-exposure -->

| id | claimed state | defect |
|---|---|---|
| `ADV-ALARM` | `merged-upstream` | GHSA-8849 - /alarm broadcasts to the whole namespace (BF-75, BF-76) |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind both (BF-7 |
| `ADV-RETRO` | `merged-upstream` | GHSA-gjhc - loadRetro serves devicestatus to any socket (BF-79) |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) |
| `BFQ-04` | `merged-upstream` | BF-04 - the v1 operator allowlist, EXTRACTED 2026-09-18 - superseded by P0-K |
| `BFQ-09` | `unsettled` | BF-09 - socket dedup truthiness skips a falsy value |
| `BFQ-10` | `not-started` | BF-10 - mongod fatal-asserts at Docker's default nofile=1024 |
| `BFQ-40` | `merged-upstream` | BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion |
| `BFQ-41` | `gate-not-met` | BF-41 - a reading dated ahead of the clock silences the stale-data alarm |
| `BFQ-46` | `gate-not-met` | BF-46 - eleven API v3 variables bypass env.js, one family deletes data |
| `BFQ-47` | `needs-decision` | BF-47 - an ordinary subject edit destroys stored fields, on today's release |
| `BFQ-52` | `unsettled` | BF-52 - the age plugins can only ask for their urgent alarm in one window |
| `BFQ-67` | `gate-not-met` | BF-67 - an alarm threshold is quietly changed and only the server log says so |
| `BFQ-69` | `not-started` | BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing |
| `BFQ-71` | `gate-not-met` | BF-71 - any dateString key drops the default date window, and the window is not a control |
| `BFQ-72` | `needs-decision` | BF-72 - an unauthenticated $regex can spend minutes of database CPU |
| `BFQ-CAP01` | `not-started` | CAP-01 - Nightscout cannot be served from a sub-path |
| `BFQ-CONNECTOR` | `gate-not-met` | BF-42, BF-43 - master pins the leaking connector, with a violated axios override |
| `BFQ-ENV` | `gate-not-met` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies |
| `BFQ-MINIMED` | `not-started` | BF-44, BF-45 - the two MiniMed ingestion divergences |

<!-- END GENERATED: operator-exposure -->

---

## Where the work actually stands

Claimed state by parcel. Every cell is a **claim** about what the gates will say.

<!-- BEGIN GENERATED: state-matrix -->

| parcel | `not-started` | `gate-not-met` | `ready-to-push` | `blocked` | `in-flight-upstream` | `merged-upstream` | `needs-decision` | `unsettled` | total |
|---|---|---|---|---|---|---|---|---|---|
| `phase0` | 1 | 3 | 1 | 3 | 1 | 9 | 2 |  | **20** |
| `release-train` | 2 | 4 |  | 4 |  |  | 2 |  | **12** |
| `register-open` | 14 | 6 |  |  |  | 4 | 4 | 2 | **30** |
| `tenancy` | 9 | 1 | 1 | 5 |  |  | 1 | 1 | **18** |
| `docs-truth` | 6 | 1 | 2 |  |  |  |  |  | **9** |

<!-- END GENERATED: state-matrix -->

Two states here are not what a casual reader expects:

- **`gate-not-met`** is a *measured* state, not an opinion. Work exists and a
  declared gate fails.
- **`in-flight-upstream`** means handed to upstream reviewers and not ours to
  land. Until 2026-09-20 most of Phase 0 sat here; **one item does now** (`P0-F`,
  `nightscout-connect` PR #68).
- **`merged-upstream`** was added 2026-09-21 for the nine items whose PRs merged
  into `dev`. It is deliberately not called `done`, for the reason the section
  above gives: nothing merged has reached an operator.

The queue also carries **explicit `no-gate:` markers** — a record that nobody has
built a way to measure a property yet, with the reason. Those are bookkeeping, not
gaps in it; roughly half the gate slots in the manifest are in that state, which is
the honest shape of the programme.

---

## The two constraints, neither of them engineering

**1. Publication is a manual human act, on purpose.** Agents prepare branches,
commits and tags locally and stop. A human pushes, merges, tags and publishes. This
is a standing rule, not a property of the current batch. It is load-bearing:
pushing to cgm-remote-monitor's `dev` or `master` fires `main.yml`'s `docker-build`
job and publishes a Docker Hub image, so **`dev` and `master` are publication
events, not branches**. A release is three separate human decisions — merge the
code, push the tag, publish the package.

**2. Review capacity is one person.** This is the finding that most limits the
programme, and it is a governance fact rather than a technical one: all 495
modernization commits have one author, and all 100 child pull requests were
self-merged with **zero human reviews**. Confidence currently rests entirely on
automated gates and the author's own evidence documents.

Where the queue says each item's review has to come from:

<!-- BEGIN GENERATED: reviewer-load -->

| the item is waiting for | items | share |
|---|---:|---:|
| Maintainer | 61 | 69% |
| SECURITY reviewer | 13 | 15% |
| Maintainer + a second human | 6 | 7% |
| SAFETY reviewer | 5 | 6% |
| Whoever edits it next | 3 | 3% |
| Upstream reviewers | 1 | 1% |
| **total** | **89** | |

<!-- END GENERATED: reviewer-load -->

Read that table as a recruiting brief. The SECURITY and SAFETY rows name a *kind*
of reviewer, not a person — **no individual is assigned to any of them**. Two
near-term consequences are concrete. `P0-C` (`bf/auth`) waits on a security
reviewer who does not yet exist; it was gate-passing until `dev` moved on
2026-09-20 and now needs a `git merge dev` first, measured conflict-free. And
`BFQ-72`, filed 2026-09-21, is a one-request unauthenticated denial of service
against a default install, live on the shipping release, whose blocking question is
whether Nightscout's security contact process is invoked — the same unanswered
question `P0-K` raised on 2026-09-18.

If you are considering reviewing, [REVIEWER-ONBOARDING.md](REVIEWER-ONBOARDING.md)
is the read-this-first path, and `reports/reviewer-packets/` has one bounded packet
per open pull request.

---

## What would move the picture

These are decisions, not tasks — no amount of engineering advances them. Each is
expanded in [NEEDS-A-HUMAN.md](NEEDS-A-HUMAN.md).

| | decision | why it blocks a train |
|---|---|---|
| `RT-D3` | Does a two-major charting upgrade (D3 5.16 → 7.9) ship under a **patch** version, with no real-browser coverage on `dev`? | It is first on the adopted release train. 15.0.9 does not cut until it is answered. |
| `RT-0` | Release 15.0.9 itself. | Everything downstream of it on the train. |
| `BFQ-47` | BF-47: an ordinary subject edit destroys stored fields on today's release. Intent before code. | It ships to operators now, and the fix depends on whether the behaviour was deliberate. |

---

## How to check any of this yourself

```bash
make queue-status          # run every static + unit gate (~7s). THE MEASUREMENT.
make queue-status PARCEL=phase0
make queue-check           # CI: register coverage, then QUEUE.md staleness
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
| item state, gates, review routing | `queue/work-queue.yaml` (source of truth) |
| defect facts and `BF-` ids | [`../30-design/remedial/nightscout-backfix-register.md`](../30-design/remedial/nightscout-backfix-register.md) |
| Phase 0 PR ordering and coupling | [`../30-design/remedial/phase0-pr-sequencing-2026-09-15.md`](../30-design/remedial/phase0-pr-sequencing-2026-09-15.md) |
| the release train and its order | [`../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md) |
| tenancy decisions D1–D15 | [`../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) |
| the governance / zero-reviews finding | [`../30-design/remedial/maintainer-release-brief-2026-09-15.md`](../30-design/remedial/maintainer-release-brief-2026-09-15.md) |

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-21**, against cgm-remote-monitor-official `74fc6619` and this repository at `be480650`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
