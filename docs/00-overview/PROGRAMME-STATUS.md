# Programme status — cgm-remote-monitor

*Maintained by the Nightscout Foundation. Contributor-facing; technical throughout.
Last narrative revision 2026-09-16. The tables are generated — see [How to check any
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
| **Remedial** | `phase0`, `register-open`, `docs-truth` | 50 | 23 | 18 |
| **Modernization** | `release-train` | 12 | 2 | 2 |
| **Multitenant** | `tenancy` | 16 | 8 | 3 |
| | **total** | **78** | **33** | **23** |

<!-- END GENERATED: horizons -->

**Remedial** — finding and fixing defects that already ship. This is the largest
horizon and the most advanced. Nine pull requests are open upstream. The backfix
register holds 70 entries; the queue names every not-fixed one.

**Modernization** — bringing dependencies and code up to date. A release train is
adopted and ordered: 15.0.9, then cut 1 (`chore/retire-jsdom`) alone, then cut 2,
then cuts 3+5 combined, with **cut 4 held back behind its own deprecation
release** because it deletes two CGM ingestion paths and its failure mode is a
user's glucose readings silently stop arriving. Nothing on this train has shipped.

**Multitenant** — making bulk hosting feasible. Decisions D1–D15 are settled and
recorded; most implementation is not started, and five items are blocked behind
remedial and release work. Self-hosted single-tenant stays first-class permanently
(D1, D4) — multitenancy is a second deployment target, never a replacement.

---

## The sentence that changes how everything else reads

**In the backfix register, `fixed` means "repaired on a branch that has not been
released."** It does not mean an operator is safe. No entry anywhere carries a
status of `landed`, because nothing has landed.

For somebody running Nightscout today, the practical version is plainer:

> A defect this project has marked "fixed" is fixed in code that has not been
> released yet. If you are running today's Nightscout, the defect is still there.
> None of this is medical advice; if a defect affects alarms or displayed numbers
> and you are unsure what it means for you, raise it with your care team.

**The size of that, measured 2026-09-16.** The register's §1 — the section whose
defects reach existing operators — holds **43 rows**, of which one (BF-12) is
retracted as not reproducing. So **42 defects are present for every self-hoster
running today's release**. Twenty-seven of them are marked `fixed`, meaning
repaired on a branch nobody has merged. Fifteen are open.

Reading the register's open count as "the number of defects still shipping"
therefore understates it by roughly a factor of three, because it silently drops
the 27 repaired-but-unreleased ones. The distinction the register's status column
actually tracks is **work done**, not operator exposure, and that is why the queue
carries `ships_to_operators_today` as a separate field rather than inferring it.

These are the queue items covering that exposure — items, not defect ids, so
several cover more than one `BF-`:

<!-- BEGIN GENERATED: operator-exposure -->

| id | claimed state | defect |
|---|---|---|
| `BFQ-04` | `not-started` | BF-04 - extract the v1 operator allowlist out of the seam |
| `BFQ-09` | `unsettled` | BF-09 - socket dedup truthiness skips a falsy value |
| `BFQ-10` | `not-started` | BF-10 - mongod fatal-asserts at Docker's default nofile=1024 |
| `BFQ-40` | `not-started` | BF-40 - $exists is not read as a boolean, before OR after bf/coercion |
| `BFQ-41` | `gate-not-met` | BF-41 - a reading dated ahead of the clock silences the stale-data alarm |
| `BFQ-46` | `gate-not-met` | BF-46 - eleven API v3 variables bypass env.js, one family deletes data |
| `BFQ-47` | `needs-decision` | BF-47 - an ordinary subject edit destroys stored fields, on today's release |
| `BFQ-52` | `unsettled` | BF-52 - the age plugins can only ask for their urgent alarm in one window |
| `BFQ-67` | `gate-not-met` | BF-67 - an alarm threshold is quietly changed and only the server log says so |
| `BFQ-CAP01` | `not-started` | CAP-01 - Nightscout cannot be served from a sub-path |
| `BFQ-CONNECTOR` | `gate-not-met` | BF-42, BF-43 - master pins the leaking connector, with a violated axios override |
| `BFQ-ENV` | `gate-not-met` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies |
| `BFQ-MINIMED` | `not-started` | BF-44, BF-45 - the two MiniMed ingestion divergences |

<!-- END GENERATED: operator-exposure -->

---

## Where the work actually stands

Claimed state by parcel. Every cell is a **claim** about what the gates will say.

<!-- BEGIN GENERATED: state-matrix -->

| parcel | `not-started` | `gate-not-met` | `ready-to-push` | `blocked` | `in-flight-upstream` | `needs-decision` | `unsettled` | total |
|---|---|---|---|---|---|---|---|---|
| `phase0` | 1 | 1 | 4 | 3 | 9 |  |  | **18** |
| `release-train` | 2 | 4 |  | 4 |  | 2 |  | **12** |
| `register-open` | 15 | 5 |  |  |  | 1 | 2 | **23** |
| `tenancy` | 8 |  |  | 5 |  | 2 | 1 | **16** |
| `docs-truth` | 7 |  | 2 |  |  |  |  | **9** |

<!-- END GENERATED: state-matrix -->

Two states here are not what a casual reader expects:

- **`gate-not-met`** is a *measured* state, not an opinion. Work exists and a
  declared gate fails.
- **`in-flight-upstream`** means handed to upstream reviewers. It is not ours to
  land, and it is where most of Phase 0 currently sits.

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
| Maintainer | 55 | 71% |
| SECURITY reviewer | 8 | 10% |
| Maintainer + a second human | 6 | 8% |
| SAFETY reviewer | 5 | 6% |
| Whoever edits it next | 3 | 4% |
| Upstream reviewers | 1 | 1% |
| **total** | **78** | |

<!-- END GENERATED: reviewer-load -->

Read that table as a recruiting brief. The SECURITY and SAFETY rows name a *kind*
of reviewer, not a person — **no individual is assigned to any of them**. The
nearest-term consequence is concrete: `P0-C` (`bf/auth`) is gate-passing and
waiting on a security reviewer who does not yet exist.

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

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-15**, against cgm-remote-monitor-official `a8888f0d` and this repository at `75c38a17`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
