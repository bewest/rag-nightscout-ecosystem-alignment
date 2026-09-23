# Programme status — cgm-remote-monitor

*Maintained by the Nightscout Foundation. Contributor-facing; technical throughout.
Prose revised 2026-09-22 against cgm-remote-monitor `origin/dev` `74fc6619` and
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
| **Remedial** | `phase0`, `register-open`, `docs-truth` | 64 | 25 | 7 |
| **Modernization** | `release-train` | 14 | 1 | 4 |
| **Multitenant** | `tenancy` | 18 | 9 | 3 |
| | **total** | **98** | **35** | **16** |

<!-- END GENERATED: horizons -->

**Remedial** — finding and fixing defects that already ship. Thirteen backfix
pull requests are merged into cgm-remote-monitor `dev`: this programme's #8733,
#8734, #8735, #8736, #8737, #8738, #8739, #8740, #8743 (2026-09-17 to 2026-09-20) and
the three advisory fixes #8744, #8745, #8746 (2026-09-21), plus #8741 from an external
contributor (2026-09-20). None is released. The open
work is `bf/auth` (`P0-C`) and `bf/throttle` (`P0-J`), both behind `dev`, and the
connector release: every programme connector fix is in `nightscout-connect` `dev` `1946beb`
and in prerelease `0.1.0-dev.1` (2026-09-22), waiting on the full `0.1.0` (`P0-TAG`) and the pin
that delivers it (`P0-PIN`). The [backfix register](../30-design/remedial/nightscout-backfix-register.md)
holds the defect facts; `make queue-coverage` proves the queue names every entry that
is not fixed.

**Modernization** — bringing dependencies and code up to date. The adopted release
train is 15.0.9, then cut 1 (`chore/retire-jsdom`) alone, then cut 2, then cuts 3+5
combined, then a deprecation release, then cut 4. Cut 4 is held behind its own
deprecation release because it removes two CGM ingestion paths (MiniMed CareLink via
mmconnect, and the legacy Dexcom Share bridge), and the failure mode is a user's
glucose readings silently stopping. Caveat, from the maintainer on 2026-09-21
(operational knowledge, not measured here): mmconnect has been broken for some time,
and legacy Dexcom Share is intended to map to `nightscout-connect`; the register's
BF-44/BF-45 were graded assuming mmconnect works and have not been re-graded. Nothing
on the train has shipped. Measured 2026-09-22 against `origin/dev` `74fc6619`:

| cut | branch | behind `dev` | conflicting paths |
|---|---|---:|---:|
| 1 | `chore/retire-jsdom` | 133 | 7 |
| 2 | `chore/build-runtime-separation` | 133 | 14 |
| 3 | `chore/compose-mongodb6` | 133 | 16 |
| 4 | `chore/mime-exposure-review` | 133 | 18 |
| 5 | `chore/nightscout-modernization` | 9 | 1 (`lib/server/bootevent.js`) |

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
run, and no programme fix is released: `origin/master` is 308 commits behind `dev`
(`git -C externals/cgm-remote-monitor-official rev-list --count origin/master..origin/dev`,
2026-09-22) and the shipping tag is 15.0.8. Merging to `dev` publishes a Docker Hub
image; that is not a release. `RT-0` (release 15.0.9) is the item that changes this;
release PR #8598 is open, mergeable, green on every CI check, and has no approving
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
| `BFQ-10` | `not-started` | BF-10 - mongod fatal-asserts at Docker's default nofile=1024 |
| `BFQ-40` | `merged-upstream` | BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion |
| `BFQ-41` | `gate-not-met` | BF-41 - a reading dated ahead of the clock silences the stale-data alarm |
| `BFQ-46` | `gate-not-met` | BF-46 - eleven API v3 variables bypass env.js, one family deletes data |
| `BFQ-47` | `not-started` | BF-47 - an ordinary subject edit destroys stored fields, on today's release |
| `BFQ-52` | `not-started` | BF-52 - the age plugins can only ask for their urgent alarm in one window |
| `BFQ-67` | `gate-not-met` | BF-67, BF-86 - alarm thresholds quietly changed, or quietly kept when they cannot work |
| `BFQ-69` | `not-started` | BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing |
| `BFQ-71` | `gate-not-met` | BF-71 - any dateString key drops the default date window, and the window is not a control |
| `BFQ-72` | `needs-decision` | BF-72 - an unauthenticated $regex can spend minutes of database CPU |
| `BFQ-87` | `gate-not-met` | BF-87 - the root qs override holds the connector below its range and pins the server's que |
| `BFQ-90` | `not-started` | BF-90 - an alarm at a page with no reading throws in the client |
| `BFQ-91` | `not-started` | BF-91 - connector capture mode cannot find trace-axios for two sources |
| `BFQ-CAP01` | `not-started` | CAP-01 - Nightscout cannot be served from a sub-path |
| `BFQ-CONNECTOR` | `gate-not-met` | BF-42, BF-43 - master pins the leaking connector, with a violated axios override |
| `BFQ-ENV` | `gate-not-met` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies |
| `BFQ-MINIMED` | `not-started` | BF-44, BF-45, BF-85 - MiniMed ingestion divergences and the CareLink zero reading |

<!-- END GENERATED: operator-exposure -->

---

## Where the work stands

Claimed state by parcel. Every cell is a **claim** about what the gates will say.

<!-- BEGIN GENERATED: state-matrix -->

| parcel | `not-started` | `in-progress` | `gate-not-met` | `ready-to-push` | `blocked` | `merged-upstream` | `needs-decision` | `done` | `unsettled` | total |
|---|---|---|---|---|---|---|---|---|---|---|
| `phase0` | 1 |  | 4 | 1 | 3 | 11 | 2 |  |  | **22** |
| `release-train` | 1 | 1 | 4 | 2 | 4 |  | 2 |  |  | **14** |
| `register-open` | 18 |  | 7 |  |  | 4 | 3 |  | 1 | **33** |
| `tenancy` | 9 |  | 1 | 1 | 5 |  | 1 |  | 1 | **18** |
| `docs-truth` | 6 |  | 1 |  |  |  |  | 2 |  | **9** |
| `backfix2` |  |  |  | 2 |  |  |  |  |  | **2** |

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
| Maintainer | 66 | 67% |
| SECURITY reviewer | 15 | 15% |
| Maintainer + a second human | 6 | 6% |
| SAFETY reviewer | 5 | 5% |
| Whoever edits it next | 3 | 3% |
| Unassigned | 2 | 2% |
| Upstream reviewers | 1 | 1% |
| **total** | **98** | |

<!-- END GENERATED: reviewer-load -->

The SECURITY and SAFETY rows name a *kind* of reviewer, not a person; no individual
is assigned to any of them. Two concrete consequences: `P0-C` (`bf/auth`) waits on a
security reviewer and needs a `git merge dev` first (trial merge measured
conflict-free); and `BFQ-72` — BF-72, an unauthenticated request that can occupy the
database for minutes, live on 15.0.8 and on `dev`, with no fix — is blocked on whether
Nightscout's security contact process is invoked.

If you are considering reviewing, [REVIEWER-ONBOARDING.md](REVIEWER-ONBOARDING.md)
is the read-this-first path, and `reports/reviewer-packets/` has one bounded packet
per item awaiting review.

---

## What would move the picture

These are decisions, not tasks; no amount of engineering advances them. Each is
expanded in [NEEDS-A-HUMAN.md](NEEDS-A-HUMAN.md).

| | decision | why it blocks a train |
|---|---|---|
| `RT-D3` | Does a two-major charting upgrade (D3 5.16 → 7.9) ship under a **patch** version, with no real-browser coverage on `dev`? | It is first on the adopted release train. 15.0.9 does not cut until it is answered. |
| `RT-0` | Release 15.0.9 (PR #8598). | Every merged fix reaches operators only through it, and every later cut waits behind it. |
| `P0-TAG` | When to cut `nightscout-connect` 0.1.0. Connector `dev` `1946beb` declares `0.1.0` and carries every fix; prerelease `0.1.0-dev.1` is on npm (2026-09-22). | `P0-PIN` and `P0-LOCK` are blocked behind it, and the connector fixes reach operators only through a pin. |
| `BFQ-47` | BF-47: an ordinary subject edit destroys stored fields on 15.0.8. Intent before code. | It ships to operators now, and the fix depends on whether the behaviour was deliberate. |
| `BFQ-72` | Is the security contact process invoked for BF-72? | It is live on the shipping release with no fix. |

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
| item state, gates, review routing | `queue/work-queue.yaml` (source of truth) |
| defect facts and `BF-` ids | [`../30-design/remedial/nightscout-backfix-register.md`](../30-design/remedial/nightscout-backfix-register.md) |
| what 15.0.9 contains and whether it is ready | [`../30-design/modernization/release-readiness-15.0.9-2026-09-22.md`](../30-design/modernization/release-readiness-15.0.9-2026-09-22.md) |
| Phase 0 PR ordering and coupling | [`../30-design/remedial/phase0-pr-sequencing-2026-09-15.md`](../30-design/remedial/phase0-pr-sequencing-2026-09-15.md) |
| the release train and its order | [`../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md) |
| tenancy decisions D1–D17 | [`../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) |
| the governance / zero-reviews finding | [`../30-design/remedial/maintainer-release-brief-2026-09-15.md`](../30-design/remedial/maintainer-release-brief-2026-09-15.md) |

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-22**, against cgm-remote-monitor-official `74fc6619` and this repository at `4c7f7cfa`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
