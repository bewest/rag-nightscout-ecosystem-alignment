# Programme status — cgm-remote-monitor

*What this is: a record (contributor-facing; technical throughout). Read after the
[mission](mission.md); leads to the [roadmap](ROADMAP.md). Prepared for the Nightscout project;
proposed for Nightscout Foundation stewardship.
Prose revised 2026-10-08 against cgm-remote-monitor `official/dev` `fade2299` and
`official/master` `92d08342` (tag `15.0.8`); the remedial horizon and the register paragraph
2026-10-21, against `official/master` `c6a0d8ed` (tag `v15.0.9`). The tables are generated from
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
| **Remedial** | `phase0`, `register-open`, `docs-truth` | 184 | 38 | 9 |
| **Modernization** | `release-train` | 50 | 8 | 2 |
| **Multitenant** | `tenancy`, `platform` | 72 | 16 | 8 |
| | **total** | **308** | **62** | **19** |

<!-- END GENERATED: horizons -->

**Remedial** — finding and fixing defects that already ship. 15.0.9 was released on 2026-10-21: #8598 merged as `master` `c6a0d8ed` (tree `c53c2c7f`, the same as
`dev` `4bca2ac2`'s), GitHub release `v15.0.9` "Release 15.0.9 Cinnamon Muffin", Latest, and the
`15.0.9` and `latest` Docker images published by the `master` CI run (39667944235, second attempt;
the first failed in one cell's `npm install` on `ECONNRESET` before any test ran). It carries 549
commits and 100 first-parent merges since 15.0.8, among them the fixes for two published-advisory
defects that survive `AUTH_DEFAULT_ROLES=denied`, GHSA-gjhc (BF-79, #8744) and GHSA-8849 (BF-75/76,
#8745), the boot notice for world-readable sites (#8746), and the two backported security fixes
(BF-104, BF-105, #8751). Operators who have not upgraded from 15.0.8 still have all of them. Both
approvals of #8598 were the maintainer's, at `e3adc91d`; they were not repeated at `4bca2ac2`. The
release rests on the maintainers' readiness decision of 2026-10-21. Both tags exist, `v15.0.9` and
`15.0.9`, on `c6a0d8ed`. `dev` is `04d435eb`, the 15.0.10 version bump on top of the release, and
#8824 is the new `dev` → `master` staging PR. Known issues and what is left are in
[ROADMAP §1](ROADMAP.md#1-1509-is-released-the-next-development-cycle).

The [backfix register](../30-design/remedial/nightscout-backfix-register.md) holds the defect facts;
`make queue-coverage` proves the queue names every entry that is not fixed.

**Modernization** — bringing dependencies and code up to date. The adopted release
train is 15.0.9, then cut 1 (`chore/retire-jsdom`), then cut 2, then cuts 3+5 combined,
then cut 4. The separate deprecation release was dropped (`RT-4`): the MiniMed warning in
15.0.9 (#8757) names the replacement settings, and on 2026-09-23 the maintainer moved the
legacy MiniMed and Dexcom bridge removal onto cut 1, keeping the hard stop at boot
(BF-61, option A). mmconnect is reported not to work, and Dexcom `BRIDGE_*` settings have
been served by `nightscout-connect` since 15.0.8, so BF-44/BF-45 are graded low. Nothing on
the train has shipped. Measured 2026-10-03 against `official/dev` `74942ec6`:

| cut | branch | behind `dev` | conflicting paths |
|---|---|---:|---:|
| 1 | `chore/retire-jsdom` | 362 | 12 |
| 2 | `chore/build-runtime-separation` | 362 | 19 |
| 3 | `chore/compose-mongodb6` | 362 | 22 |
| 4 | `chore/mime-exposure-review` | 362 | 36 |
| 5 | `chore/nightscout-modernization` | 238 | 27 |

Reproduce with `git -C externals/cgm-remote-monitor-official rev-list --count
official/chore/<branch>..official/dev` and `git merge-tree --write-tree --name-only
official/dev official/chore/<branch>`; the trial merges are `RT-REBASE`'s and `RT-3`'s
gates. The files newly conflicting on cuts 2–4 were touched by the merged Phase 0
PRs, so every merge to `dev` raises the rebase cost of the train. Whether the train reaches `dev`
by merge or by rebase is open (`RT-PROPAGATION`); so far every propagation has been a merge.

**Multitenant** — making bulk hosting feasible. Decisions D1–D21 are recorded in the
[execution plan](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md);
D17 is adopted in three of four rows, with row 2 (cohort-wide human identity) held
pending `T30-ORY-PROOF`. Most implementation is not started, and several items are
blocked behind remedial and release work. The seam branches refresh once, after the 15.0.9 freeze,
as the first step of the write contract (`WRITE-CONTRACT`, plan §4.1 and §5.1). Self-hosted single-tenant stays
first-class permanently (D1, D4): multitenancy is a second deployment target, never a
replacement.

---

## Status words: merged is not released

**In the backfix register, neither `fixed` nor `merged` means an operator is safe.**
`fixed` means repaired on a branch that has not been merged. `merged` means merged
into `origin/dev` and not released. `released` means in a tagged release operators
run. 15.0.9 (`RT-0`) was released on 2026-10-21 (tag `v15.0.9`, `master` `c6a0d8ed`), so every
entry merged before then is `released 15.0.9`. Merging to `dev` publishes a Docker Hub
image; that is not a release. If a defect marked `fixed` or `merged` exists in 15.0.9, anyone running 15.0.9 still has it; anyone still on 15.0.8 also has every `released 15.0.9` entry.

The size of that, from the register's §1 (the section whose defects reach existing operators),
measured 2026-10-07 with `node tools/queue/gates/register-exposure-legend.js`: **120 defects**
(BF-12, invalid, BF-41, closed, and BF-71, closed as working as intended, excluded) — 27 `open`,
89 `merged`, 1 `partly merged`, 3 `fixed` (BF-52; BF-09 and BF-156 on unmerged branches). A few were introduced and repaired on `dev` before any release (BF-80, BF-106 and
BF-142, as of 2026-09-26), so they never reached 15.0.8. The count moves when entries are filed or
merged; re-run the gate before quoting it.

The register's `open` count is therefore not "the number of defects still shipping":
it omits the 83 repaired-but-unreleased ones (81 merged, 1 partly merged, 1 fixed). The status column tracks work done, not
operator exposure, which is why the queue carries `ships_to_operators_today` as a
separate field.

These are the queue items covering that exposure — items, not defect ids, so several
cover more than one `BF-`:

<!-- BEGIN GENERATED: operator-exposure -->

| id | claimed state | defect |
|---|---|---|
| `ADV-ALARM` | `released` | GHSA-8849 - /alarm broadcasts to the whole namespace (BF-75, BF-76) |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind both (BF-7 |
| `ADV-RETRO` | `released` | GHSA-gjhc - loadRetro serves devicestatus to any socket (BF-79) |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) |
| `BFQ-04` | `released` | BF-04 - the v1 operator allowlist - superseded by P0-K |
| `BFQ-09` | `merged-upstream` | BF-09 - socket dedup truthiness skips a falsy value |
| `BFQ-10` | `released` | BF-10 - mongod fatal-asserts at Docker's default nofile=1024 |
| `BFQ-100` | `released` | BF-100 - devicestatus, food and activity store a hex _id as a string |
| `BFQ-101` | `released` | BF-101 - API v3 id filters miss records stored with a string _id |
| `BFQ-102` | `released` | bf/object-id-consistency - one rule for a record's own hex _id across profile, devicestatu |
| `BFQ-103` | `released` | BF-103 - a split drag stores the old time, so IOB and COB ignore the move |
| `BFQ-107` | `released` | BF-107 - a failed treatments query ends the Nightscout process on 15.0.8 |
| `BFQ-111` | `released` | BF-111 - find[_id][$in] misses records stored with a string _id, for reads and bulk delete |
| `BFQ-112` | `released` | BF-112 - an auth subject created with a hex _id is stored as a string and cannot be delete |
| `BFQ-114` | `released` | BF-114 - an AAPS open-ended loop disable keeps loop and pump alerts off after the loop is  |
| `BFQ-115` | `released` | BF-115 - an entry or treatment with an unusable _id is stored with it, and one such value  |
| `BFQ-117` | `released` | BF-117 - an API v3 DELETE of a record stored twice leaves one copy valid; on #8758 v3 read |
| `BFQ-118` | `released` | BF-118 - on an mmol site, targets set without BG_HIGH are never converted, so low alarms c |
| `BFQ-119` | `released` | BF-119 - PUMP_WARN_ON_SUSPEND never raises a suspended-pump warning (issue #5622) |
| `BFQ-120` | `released` | BF-120 - the clock view shows an old reading as current when its data fetch fails (issue # |
| `BFQ-121` | `released` | BF-121 - two carb entries at the same time are stored as one, and the carbs of one are los |
| `BFQ-122` | `released` | BF-122 - records written, changed or deleted through API v1 never appear in API v3 history |
| `BFQ-123` | `released` | BF-123 - an AndroidAPS Profile Switch percentage is ignored in the basal, ISF and carb rat |
| `BFQ-125` | `released` | BF-125 - IFTTT Maker alarm events use translated level names; a failed call re-sends every |
| `BFQ-126` | `released` | BF-126 - an authorization subject without a name ends the server at every boot (issue #711 |
| `BFQ-127` | `released` | BF-127 - clock views opened from the menu are blank for a token viewer on a site that deni |
| `BFQ-128` | `released` | BF-128 - /pebble on an mmol site returns the delta in mmol when mg/dL is asked for (issue  |
| `BFQ-129` | `released` | BF-129 - GET /api/v1/entries/<id> for an id that names no entry answers 500 |
| `BFQ-133` | `released` | BF-133 - the COB pill's last-carbs detail can name an older carb entry than the newest one |
| `BFQ-134` | `released` | BF-134 - every Loop remote command leaves an APNs connection and a heartbeat timer open |
| `BFQ-136` | `released` | BF-136 - API v3 refuses an AndroidAPS write that lands on a record written through v1 (Fie |
| `BFQ-137` | `merged-upstream` | BF-137 - with more than one IFTTT Maker key, an alarm's Maker calls run out of order and a |
| `BFQ-142` | `released` | BF-142 - API v3 DELETE answers 404 for a record whose stored identifier is 0 or an array,  |
| `BFQ-145` | `merged-upstream` | BF-145 - API v3 PATCH and PUT by the shown id miss a record whose identifier is null, "" o |
| `BFQ-146` | `released` | BF-146 - API v3 treatments are held in the server's memory without mills: a late or edited |
| `BFQ-147` | `released` | BF-147 - two package.json overrides hold ajv and request's form-data inside published advi |
| `BFQ-149` | `not-started` | BF-149 - the Day to Day report draws a cancelled or replaced temp target or override for i |
| `BFQ-152` | `merged-upstream` | BF-152 - API v3 settings are admin-only through search and history, readable by identifier |
| `BFQ-154` | `blocked` | BF-154 - node-forge 1.4.0 (pinned in overrides) is inside an advisory range with no fixed  |
| `BFQ-156` | `merged-upstream` | BF-156 - API v3 auto-prune never handles its delete's result; a failed delete ends the pro |
| `BFQ-157` | `merged-upstream` | BF-157 - a treatment's glucose bubble is placed as mg/dL when its units are spelled mmol/L |
| `BFQ-159` | `merged-upstream` | BF-159 - the main page sometimes leaves for the Profile Editor while a profile exists, wit |
| `BFQ-160` | `merged-upstream` | BF-160 - the clock designer's link target is written with curly quotes |
| `BFQ-161` | `in-flight-upstream` | BF-161 - braces 3.0.3 (direct dependency) is inside a stack-exhaustion advisory with no fi |
| `BFQ-163` | `merged-upstream` | BF-163 - compression 1.8.1 (every response) is inside a high memory-leak advisory fixed in |
| `BFQ-164` | `blocked` | BF-164 - writes outside API v3 never reach the v3 storage socket |
| `BFQ-165` | `merged-upstream` | BF-165 - a treatment re-send matched by its fallback key is answered without _id |
| `BFQ-166` | `merged-upstream` | BF-166 - a profile re-sent with its own _id answers 500 |
| `BFQ-168` | `released` | BF-168 - the context chart's window sometimes cannot be dragged back to now |
| `BFQ-169` | `merged-upstream` | BF-169 - API v3's swagger says clients must not supply identifier, but the server keeps a  |
| `BFQ-170` | `merged-upstream` | BF-170 - API v3 stores a client's 24-hex body _id as a string, in the case sent |
| `BFQ-172` | `merged-upstream` | BF-172 - the Bolus Wizard Preview mixes the profile's units with the display units (#8819  |
| `BFQ-173` | `merged-upstream` | BF-173 - the Careportal Bolus Wizard mixes the profile's units with the display units, a k |
| `BFQ-174` | `merged-upstream` | BF-174 - the bolus calculator's profile picker is ignored; every value comes from the acti |
| `BFQ-180` | `merged-upstream` | BF-180 - a careportal temp target on an mmol/L site is converted to mg/dL twice when the h |
| `BFQ-181` | `not-started` | BF-181 - one future srvModified pins the shared write clock ahead, across restarts |
| `BFQ-183` | `merged-upstream` | BF-183 - the API v3 storage socket logs the supplied credential on a failed authorization |
| `BFQ-184` | `not-started` | BF-184 - API v3 /status apiPermissions reports only wildcard permissions |
| `BFQ-186` | `merged-upstream` | BF-186 - API v3 logs a whole record when a client's identifier differs from the computed o |
| `BFQ-187` | `not-started` | BF-187 - an entries pattern segment over the braces parser's input limit answers 500, not  |
| `BFQ-188` | `not-started` | BF-188 - with no client bundle the server exits at boot with an unexplained module error |
| `BFQ-190` | `merged-upstream` | BF-190 - an alarm on a page without a current reading cannot be silenced from the page |
| `BFQ-191` | `in-progress` | BF-191 - a stored treatment can stop the server process, and keeps doing so after a restar |
| `BFQ-193` | `merged-upstream` | BF-193 - the realtime socket and other write paths log every record written through them |
| `BFQ-194` | `merged-upstream` | BF-194 - API v1 drops the units of a temp target with no glucose value, so mmol/L targets  |
| `BFQ-195` | `merged-upstream` | BF-195 - a stale profile is pushed over the socket after a profile re-send |
| `BFQ-196` | `not-started` | BF-196 to BF-199 - API v1 error paths and the README's read window, found by PR #8858's ro |
| `BFQ-40` | `released` | BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion |
| `BFQ-46` | `merged-upstream` | BF-46 - eleven API v3 variables bypass env.js, one family deletes data |
| `BFQ-47` | `released` | BF-47 - an ordinary subject edit destroys stored fields, on today's release |
| `BFQ-52` | `blocked` | BF-52 - an age reminder whose 20-minute window passed without a check was never sent |
| `BFQ-67` | `not-started` | BF-67, BF-86 - alarm thresholds quietly changed, or quietly kept when they cannot work |
| `BFQ-69` | `released` | BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing |
| `BFQ-71` | `closed` | BF-71 - any dateString key drops the default date window, and the window is not a control |
| `BFQ-72` | `in-flight-upstream` | BF-72 - an unauthenticated $regex can spend minutes of database CPU |
| `BFQ-87` | `released` | BF-87 - the root qs override holds the connector below its range and pins the server's que |
| `BFQ-90` | `released` | BF-90 - an alarm at a page with no reading throws in the client |
| `BFQ-91` | `released` | BF-91 - connector capture mode cannot find trace-axios for two sources |
| `BFQ-92` | `merged-upstream` | BF-92 - a page with no glucose reading never presents a server alarm, including device ala |
| `BFQ-93` | `merged-upstream` | BF-93 - food changes never reach an open page |
| `BFQ-95` | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm |
| `BFQ-98` | `released` | BF-98 - the connector reuses a reader subject without roles, so the BF-89 fix does not rep |
| `BFQ-99` | `released` | bf/profile-object-id - a profile posted with its own _id is stored as an ObjectId, and str |
| `BFQ-CAP01` | `not-started` | CAP-01 - Nightscout cannot be served from a sub-path |
| `BFQ-CONNECTOR` | `gate-not-met` | BF-42, BF-43 - master pins the leaking connector, with a violated axios override |
| `BFQ-ENV` | `needs-decision` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies |
| `BFQ-MINIMED` | `not-started` | BF-44, BF-45, BF-85 - MiniMed ingestion divergences and the CareLink zero reading |
| `RT-PR-8815` | `released` | #8815 - a bearer token whose subject was deleted is refused instead of stopping the server |

<!-- END GENERATED: operator-exposure -->

---

## Where the work stands

Claimed state by parcel. Every cell is a **claim** about what the gates will say.

<!-- BEGIN GENERATED: state-matrix -->

| parcel | `not-started` | `in-progress` | `gate-not-met` | `ready-to-push` | `blocked` | `in-flight-upstream` | `merged-upstream` | `released` | `needs-decision` | `done` | `unsettled` | `closed` | `answered` | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `phase0` | 3 |  |  | 1 |  |  |  | 17 |  | 1 |  |  |  | **22** |
| `release-train` | 8 |  | 1 |  | 1 |  | 18 | 15 | 2 | 1 |  |  | 4 | **50** |
| `register-open` | 28 | 3 | 1 | 1 | 3 | 2 | 38 | 58 | 5 |  |  | 4 |  | **143** |
| `tenancy` | 8 | 2 |  | 1 | 12 |  | 3 |  | 4 | 3 | 1 |  | 3 | **37** |
| `docs-truth` | 7 |  | 1 |  |  |  |  |  |  | 11 |  |  |  | **19** |
| `backfix2` |  |  |  |  |  |  |  | 2 |  |  |  |  |  | **2** |
| `platform` | 8 | 1 |  |  |  | 2 |  |  |  | 24 |  |  |  | **35** |

<!-- END GENERATED: state-matrix -->

Three states here are not what a casual reader expects:

- **`gate-not-met`** is a *measured* state, not an opinion. Work exists and a
  declared gate fails.
- **`in-flight-upstream`** means handed to upstream reviewers and not ours to land.
- **`merged-upstream`** means merged into `dev` and not released. It is deliberately
  not called `done`: nothing merged has reached an operator.

The queue also carries **explicit `no-gate:` markers** — a record that a property
has no measurement built yet, with the reason. They are bookkeeping, not
gaps in it; `make queue-validate` prints how many gate slots are in that state.

---

## The two constraints, neither of them engineering

**1. Publication is a manual human act, on purpose.** Agents prepare branches,
commits and tags locally and stop. A human pushes, merges, tags and publishes. This
is a standing rule. Pushing to cgm-remote-monitor's `dev` or `master` fires
`main.yml`'s `docker-build` job and publishes a Docker Hub image, so **`dev` and
`master` are publication events, not branches**. A release is three separate human
decisions: merge the code, push the tag, publish the package.

**2. Review routes to the maintainer.** The modernization commits have one author, so
each cut needs a reviewer other than its author before it reaches `dev`.

Where the queue says each item's review has to come from:

<!-- BEGIN GENERATED: reviewer-load -->

| the item is waiting for | items | share |
|---|---:|---:|
| Maintainer | 271 | 88% |
| SECURITY reviewer | 17 | 6% |
| Maintainer + a second human | 8 | 3% |
| SAFETY reviewer | 6 | 2% |
| Whoever edits it next | 3 | 1% |
| Unassigned | 2 | 1% |
| Upstream reviewers | 1 | 0% |
| **total** | **308** | |

<!-- END GENERATED: reviewer-load -->

The SECURITY and SAFETY rows name a *kind* of reviewer. For #8754 (login security fixes and
`TRUST_PROXY`, merged as `4f705217`), the named reviewers were the maintainer and Andy. The other SECURITY
and SAFETY rows still have no individual assigned. `BFQ-72` (BF-72, an
unauthenticated request that can occupy the database for minutes, live on 15.0.8 and `dev`)
has a disposition decided by the maintainer. It is held outside this public repository because the
defect is live on the shipping release (the disclosure rule, [DOCUMENT-CONTROL §3.8](DOCUMENT-CONTROL.md#38-external-and-restricted-documents)).

If you are considering reviewing, [REVIEWER-ONBOARDING.md](REVIEWER-ONBOARDING.md)
is the read-this-first path, and `reports/reviewer-packets/` has one bounded packet
per item awaiting review.

---

## What would move the picture

These are decisions, not tasks; no amount of engineering advances them. Each is
expanded in [NEEDS-A-HUMAN.md](NEEDS-A-HUMAN.md).

| | decision | why it blocks a train |
|---|---|---|
| `BFQ-09` | BF-09: is a zero-valued temp basal a real value in the socket dedup? Measured; waits on the maintainer. | It ships to operators now. |
| `A7A-7` | The clock question inside the alarm path. The maintainer owns it. | It gates alarms under `TENANCY_MODE=multi`. |

`P0-TAG` (done: `nightscout-connect` 0.1.0 released and pinned by #8762) left this table on
2026-09-24. `RT-D3` (answered: the drag check passed in automation and by hand, and 15.0.9 ships as numbered),
`BFQ-47` (decided: the allow-list is intended; the admin-page fix is in #8754) and `BFQ-72` (disposition
decided; held outside this public repository while the defect is live) left this table on 2026-09-23.

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
| how documents and records are controlled (proposal) | [`DOCUMENT-CONTROL.md`](DOCUMENT-CONTROL.md) |
| item state, gates, review routing | `queue/work-queue.yaml` (source of truth) |
| defect facts and `BF-` ids | [`../30-design/remedial/nightscout-backfix-register.md`](../30-design/remedial/nightscout-backfix-register.md) |
| what 15.0.9 contains and leaves broken | [`../../releases/cgm-remote-monitor-15.0.9/contents.md`](../../releases/cgm-remote-monitor-15.0.9/contents.md) |
| how 15.0.9 was released, and what is left | [`ROADMAP.md` §1](ROADMAP.md#1-1509-is-released-the-next-development-cycle) (generated) |
| Phase 0 PR ordering and coupling | [`../30-design/remedial/phase0-pr-sequencing-2026-09-15.md`](../30-design/remedial/phase0-pr-sequencing-2026-09-15.md) |
| the release train and its order | [`../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md) |
| tenancy decisions D1–D21 | [`../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) |
| the governance / zero-reviews finding | [`../30-design/remedial/maintainer-release-brief-2026-09-15.md`](../30-design/remedial/maintainer-release-brief-2026-09-15.md) |

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-27**, against cgm-remote-monitor-official `7000eb18` and this repository at `18cdcce0`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
