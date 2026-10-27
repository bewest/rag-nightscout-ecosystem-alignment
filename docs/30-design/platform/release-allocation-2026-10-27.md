# Release allocation: what goes in 16.0.0, what follows, and in what order

*Contributor-facing. Snapshot, 2026-10-27: cgm-remote-monitor `official/dev` `8dbb60c2`,
`official/master` `c6a0d8ed` (= `v15.0.9`), open PRs read with `gh pr list` and `gh pr view` the same
day. The work items are those of the living [next-gen platform plan](next-gen-platform-plan.md); the
release's own state is in [releases/cgm-remote-monitor-16.0.0](../../../releases/cgm-remote-monitor-16.0.0/contents.md).
The versioning rules quoted are those of the
[semver policy](../modernization/semver-and-release-versioning-policy-2026-09-15.md) §2. Recommendations
are proposals for the maintainer; nothing here is decided until §5 says so.*

The maintainer asked four questions on 2026-10-27:

1. Given the progress toward multitenancy, how much of the storage seam should go into the current
   release, if any?
2. Does including the other roadmap features help multitenancy?
3. How should the releases and schedule for client identity, formal schemas, API v4 and multitenancy
   be managed against each other?
4. Where are the open questions and the briefs for understanding each scenario?

§1 answers in brief, §2–§4 give the reasoning, §5 lists the open decisions, and §6 holds the scenario
briefs. B6 and Q12 answer a follow-up the same day: whether prototypes should ship in 16.0.0 as alpha.

## 1. The answers in brief

- **Storage seam in 16.0.0: none beyond what is merged.** #8854 (the write boundary) is on `dev` and
  ships. The three seam slices in review (#8861 ST-FILTER and ST-READS, #8863 ST-WRITES) are measured
  to change no behaviour, so no rule of the versioning policy needs them in a major; adding them now
  enlarges a release whose remaining gate is a soak. They go to `dev` right after the tag and ship in
  16.1.0.
- **What 16.0.0 should still take** is the work whose behaviour change belongs at a major boundary or
  that fixes a live defect: #8859 (re-send matching and the null-removes rule), #8856 (BF-193, write
  logging), #8864 (the IOB pill on reconnect), #8866 (two CI test faults), #8858 (API docs held to the
  routes) and the BF-72 and BF-161 advisory fixes. #8862 (one executable) goes in only if it merges
  before the soak starts (Q2).
- **The other roadmap features help multitenancy unevenly.** Identity and formal record schemas are
  on its critical path: they fix the keys and columns of the PostgreSQL tables. PLAT-ENTRY and
  PLAT-SERVE are on it too. Registration, statistics and the v4 typed paths are parallel work that
  joins tenancy later through `HUB-REG-CRM-SEAM`. Their benefit to tenancy is indirect: each one
  that ships in a single-tenant minor puts the storage interface under real traffic on MongoDB
  before PostgreSQL depends on it.
- **Order the tracks by what they fix for the next one:** identity first (it fixes keys), schemas
  second (they fix columns and validation), the storage interface alongside both, then PostgreSQL and
  tenancy on top. API v4 is published in pieces as each piece's contract settles; registration
  first, typed record paths after the identity decisions.
- **Releases follow themes, not dates.** A minor ships when a theme's checks pass and it has soaked.
  Everything single-tenant operators can opt into (registration, the storage interface, v4 reads,
  multi mode itself) is additive and fits minors. The changes that refuse or migrate existing data
  (a unique `identifier` index, validation on by default, bounding v1 queries) collect for 17.0.0.

## 2. Where things stand

| | on `dev` `8dbb60c2` | open PR | size against its base |
|---|---|---|---|
| Write boundary | #8854 merged 2026-10-26 (`c08cbe03`) | | |
| Re-send and merge contract | | #8859 draft, `5c6ceabb`, 8 commits behind `dev` | 22 files, +1850/−63 |
| Write logging (BF-193) | | #8856 draft, `6b6ad320` | |
| API docs held to routes | | #8858, `38412bcc` | |
| IOB pill on reconnect | | #8864 draft (AndyLow91), `4ed92673`, opened 2026-10-27 | 2 files |
| CI test faults on `8dbb60c2` | | #8866, `bdd569a3`, 14 checks pass, 2 pending | test files only |
| ST-FILTER + ST-READS | | #8861 draft, `48e7e101` | 21 files, +2313/−88 |
| ST-WRITES | | #8863 draft, `38b910d7`, stacked on #8861 | 22 files, +723/−226 |
| PLAT-ENTRY (D21) | | #8862 draft, `b63d9b7f` | 15 files, +1014/−12 |
| PLAT-SERVE | | #8865 draft, `1dafe2a5`, stacked on #8863 | 25 files, +2023/−57 |
| Registration S0, S1, S2, S5 | | #8857 draft, `f7a43fed` | 30 files, +9871/−62 |

Sizes: `git diff --shortstat <base>...<head>` in `externals/cgm-remote-monitor-official` after
fetching each PR head. #8863's base is #8861 and #8865's is #8863.

The behavioural measurements behind "changes no behaviour" are the next-gen lane's
(plan items ST-FILTER to PLAT-SERVE): the write-contract matrix (360 cells, both validation modes)
equal to `dev` for #8861 and #8863; HTTP diff 700 of 700 and v1 read diff 2954 of 2954 identical for
#8861; `single` under #8865 4639 passing, 0 failing, 3 pending. #8862 starts every old path through
the new executable and runs an explicit container command as given (`Dockerfile` and
`tests/start-paths.test.js` on `b63d9b7f`, read).

**What still stands between `dev` and the 16.0.0 tag** (contents, "Open items a releaser must
settle"): a live Pushover and APNs delivery check, a real-rig soak on `dev`, and the BF-72 and
BF-161 fixes through their advisory forks. None is met. The staging PR #8824 is `BLOCKED`:
`master`'s protection still requires `Run Tests (22, 4.4)`, which `dev` no longer emits, and one
approving review (`gh api repos/nightscout/cgm-remote-monitor/branches/master/protection`, read
2026-10-27). The maintainer's decided change (require only *Tests pass*) is not yet applied.

## 3. How much of the storage seam goes in 16.0.0

### 3.1 What the versioning policy asks

The policy classifies a release by its loudest change (R3) and says a version number is not a
substitute for a test. Applied to the seam:

| change | ladder | consequence |
|---|---|---|
| ST-FILTER, ST-READS, ST-WRITES | no question 1–13 answers yes: same records, same bodies, same stored documents | patch-class; can ship in any later release |
| PLAT-ENTRY | question 9 (a new executable and subcommands is added); the image's start changes form but every measured start path is unchanged | minor-class |
| PLAT-SERVE | question 9 (a new start mode) | minor-class |
| Registration S0–S5, off by default | question 9 (endpoints added) | minor-class |
| #8859 null removes a field; identifier matching on v1 entries and devicestatus | question 10 (a re-send that made a duplicate now matches; a `null` that was stored now removes the field) | minor-class at least; it changes what clients see, so it belongs where client notes are already being written |
| WC-STEP-PATCH, ID-BATCH | question 10 (reply shape and per-item results) | minor-class |
| ID-UNIQUE-INDEX | questions 4 and 5 (a duplicate that was accepted is refused or merged; existing databases with duplicates need cleaning) | major |
| `WRITE_VALIDATION` on by default | question 4 (inputs a real client sends that return 2xx today would return 4xx) | major |
| D8 bounding of v1 queries | question 3 (a parameter's effect narrowed) | major |

Nothing in the seam slices needs 16.0.0. The items that need a major are not ready, and none of them
is in review.

### 3.2 What including the slices would cost

16.0.0 is already 890 commits and 855 files past `v15.0.9` (contents, Identity). Its remaining gates are a soak and live delivery checks, which measure time on
real sites, not lines of code. Every merge to `dev` after a soak starts changes what the soak
measured. The three slices add about 3,000 lines over every v1 read and write path. Their matrices say
they change nothing, and the soak is where that claim is tested on real rigs, so they cost the soak
either a restart or a gap.

### 3.3 What holding them costs

- The stacked chain (#8861 → #8863 → #8865) keeps `dev` merged in rather than rebased. A week of
  holding costs one `dev` merge per branch; #8861 and #8863 are 0 commits behind `dev` today.
- Tenancy work above WC-STEP-PATCH does not start until ST-WRITES is on `dev`. ST-EVENT (decision
  D-EVENT) is a decision, not code, and can be settled while the slices wait.

### 3.4 Recommendation

Hold #8861, #8863 and #8865 until 16.0.0 is tagged; merge them to `dev` the day after, in stack
order, and ship them in 16.1.0. This needs one rule for `dev` between now and the tag (Q1). The soak has not started, so B6 states the one condition under which they go into 16.0.0 instead: an entry bar met before it starts (Q12).

## 4. How the tracks depend on each other

### 4.1 Which features shorten the path to multitenancy

The multitenant target (D1–D3) is PostgreSQL with row-level security behind the same storage
interface, with tenant resolution and per-tenant credentials. Its critical path in the plan:

```
ST-WRITES → ST-EVENT (D-EVENT) → WC-STEP-PATCH → ST-HARNESS → ST-PG ──┐
T30-RESEARCH (D-T30) → T30-SCHEMA-CONFIG ───────────────────────────────┼→ TEN-RESOLVE → T30-WIRING → TEN-LAB
PLAT-ENTRY → PLAT-SERVE ───────────────────────────────────────────────┘
```

| track | on the critical path? | why |
|---|---|---|
| Storage slices | yes | ST-PG is an implementation of the interface they build |
| Client identity (ID-FIRST-MATCH, ID-UNIQUE-INDEX) | yes, for the schema | the PostgreSQL key for a client record is (tenant, collection, `identifier`); settling identifier format, scope and immutability before the tables exist avoids migrating them. D-LOOP-ID's six questions are the slowest input, because they wait on another project's answer |
| Formal record schemas (records spec, `indexedFields`, OpenAPI) | yes, for the columns | D11 emits only declared indexed fields as columns and keeps the rest in JSONB; the declared set comes from these schemas |
| `WRITE_VALIDATION` rules | partly | WC-STEP-PATCH moves the rules into `write(intent)`; whether they reject by default is a separate, major decision |
| PLAT-ENTRY, PLAT-SERVE | yes | hosted roles (D5) are `nightscout serve <roles>` |
| Tenant configuration surface (D-T30) | yes | the per-tenant settings table (D15) cannot be written until the maintainer approves which settings a tenant owns |
| Registration S0–S5 | no | single-tenant, no storage work; joins tenancy at `HUB-REG-CRM-SEAM`, after ST-PG |
| Registration S3 (typed writes) | no, but shares WC-STEP-PATCH | applied by the same write step tenancy uses |
| API v4 statistics | no | read-only, computes over the interface |
| API v4 typed record paths | no; deferred | decision 12 of the v4 page waits on the identity decisions |

So the features that help are the ones that fix the shape of stored data (identity, schemas) and
the process shape (PLAT-*). Registration and v4 reads are parallel; bundling them into a tenancy
release would make that release larger without making it earlier.

### 4.2 The indirect benefit: real traffic on the interface

Multi mode depends on the storage interface being correct under every client the 12-site corpus and
the 67-shape replay describe. Each single-tenant minor that routes more paths through the interface
(16.1.0: v1 reads and writes; 16.2.0: `write(intent)`) puts that code on MongoDB under real
uploaders before PostgreSQL relies on it. That argues for shipping the storage slices early and
separately, not for bundling features with tenancy.

### 4.3 Proposed release themes

Each row ships when its checks pass and it has soaked; no dates are proposed. The version class is
the loudest row's (R3).

| release | theme | contents | class |
|---|---|---|---|
| 16.0.0 | modernization, the write boundary | what is on `dev`, plus #8859, #8856, #8864, #8866, #8858, BF-72, BF-161; #8862 if Q2 says so | major (already) |
| 16.1.0 | one write path, registration readable | #8861, #8863 (behaviour-neutral); #8862 and #8865 (one executable, `serve api`); #8857 off by default (D-REG-FLAG); SPEC-ID-AMEND; the OpenAPI description of what 16.1.0 serves, including the registration paths | minor |
| 16.2.0 | `write(intent)` | ST-EVENT, WC-STEP-PATCH, ID-BATCH, ST-HARNESS; REG-S3 behind its flag; v4 statistics reads | minor |
| 16.3.0 or later | multi mode, preview | ST-PG, T30-SCHEMA-CONFIG, TEN-RESOLVE, T30-WIRING behind `TENANCY_MODE=multi`; TEN-LAB passes with its control; single-tenant unchanged | minor for self-hosters |
| 17.0.0 | contract tightening | ID-UNIQUE-INDEX with a duplicate-cleaning step, ID-FIRST-MATCH where it changes outcomes, `WRITE_VALIDATION` default (if decided), D8 v1 query bounds, any v4 path promoted from unstable | major |

Two consequences:

- **Multitenancy does not wait for 17.0.0.** Multi mode is a new deployment target behind a setting
  a self-hoster never sets, so for the single-tenant surface it is additive (question 9). Its
  maturity for hosting is a separate label (preview, then supported), set by TEN-LAB and a hosted
  soak, not by the version number.
- **17.0.0 is where identity is enforced, not where it starts.** Identifier matching starts in
  16.0.0 (#8859) and spreads in 16.2.0; the unique index that makes it a guarantee is the major.

### 4.4 API v4 and formal schemas across releases

- **v4 ships in pieces, marked unstable until its contract is shared.** Registration is already under
  `/api/v4/` in #8857. Each v4 path is served as unstable (declared in the capability document)
  until REG-PROPOSE and D-NOCTURNE-ID settle what the shared contract says. Promotion from unstable
  to stable is additive; changing an unstable path is not a semver event if the capability document
  says it is unstable (Q7).
- **Formal schemas are a per-release product, not a release.** #8858 holds the API docs to the
  routes with a test; the alignment repository's OpenAPI and `nsschema` are re-vendored when it
  merges. Each release's OpenAPI describes what that release serves. Enforcing a schema on writes
  (validation on by default) is the only schema step with a major's consequences.

## 5. Open decisions

| # | question | options | recommendation | holds |
|---|---|---|---|---|
| Q1 | How is `dev` kept stable for the 16.0.0 soak? | (a) `dev` takes release fixes only until the tag; feature PRs stay draft. (b) cut `release/16.0.0` from `dev` now; soak and tag from it; `dev` takes the seam. | (a): the soak and the Docker `dev` image both run from `dev` today, and a second long-lived branch doubles the merge work for a few weeks | #8861, #8863, #8865, #8857 merge dates |
| Q2 | #8862 (one executable) in 16.0.0? | (a) yes, if merged before the soak starts; (b) 16.1.0 | (a): the image's start changes form, and a major's release notes already ask operators to check their start; if the soak has started, (b) | the soak start |
| Q3 | The seam slices in 16.0.0? | (a) hold to 16.1.0; (b) merge now | (a), §3 | tenancy start date by the time the soak takes |
| Q4 | #8857 in 16.1.0, off by default? | keep `CONTROLLER_REGISTRATION` on/off, or a staged mode (D-REG-FLAG) | 16.1.0 with whichever flag the PR review settles | REG-S3 |
| Q5 | Is ID-UNIQUE-INDEX (with duplicate cleaning) 17.0.0 material? | (a) yes; (b) add the index as opt-in in a minor, enforce in 17.0.0 | (b): an opt-in index lets operators measure their duplicates first | ID-UNIQUE-INDEX, the PostgreSQL key |
| Q6 | Does multi mode ship in 16.x minors behind `TENANCY_MODE=multi`? | (a) yes, labelled preview; (b) wait for 17.0.0 | (a), §4.3 | TEN-LAB's release |
| Q7 | How is v4's stability declared? | (a) per path in the capability document; (b) a `/api/v4-unstable` prefix; (c) no marker | (a): the capability document is already the place a client reads what the hub serves | REG-PROPOSE |
| Q8 | `WRITE_VALIDATION` default | (a) stays `off`; (b) `log` in a minor; (c) `reject` in 17.0.0 | (b) then (c), after #8841's open items (contents, item 7) | 17.0.0 contents |
| Q9 | D-EVENT: commit event per call or per driver operation | per the plan's decision card | settle while the slices wait (§3.3) | WC-STEP-PATCH, the change feed |
| Q10 | D-T30: approve the tenant configuration surface | walk through the DECISION sections | start once 16.0.0 is tagged, after re-measuring the 277 settings on `dev` | T30-SCHEMA-CONFIG, TEN-RESOLVE |
| Q11 | Review capacity | #8857, #8859, #8861, #8862, #8863 and #8865 add 17,794 lines against their bases (§2) | review in theme order (16.1.0 first), one stacked chain at a time | every row of §4.3 |
| Q12 | Put prototypes in 16.0.0 to soak them as alpha (asked 2026-10-27)? | (a) seam slices in, if they meet B6's entry bar before the soak starts; multi prototype as a prerelease outside the 16.0.0 artifact. (b) both in 16.0.0, prototype code labelled alpha. (c) neither; release as soon as the gates are met | (a), B6 | the soak start, BFQ-72 |

## 6. Scenario briefs

Each brief states what the scenario is, who it reaches, and what to measure before choosing it.

### B1. 16.0.0 with the seam held (recommended)

- **What happens.** `dev` takes only #8859, #8856, #8864, #8866, #8858 and the two advisory fixes; the
  soak runs; the tag follows; the seam chain merges the next day.
- **Who it reaches.** Operators get the modernization and the write boundary. Uploaders (AndroidAPS,
  Loop, Trio, xDrip+) see #8859's re-send matching and the null-removes rule, which the client notes
  list.
- **Measure first.** The soak and live delivery checks (RT-16-RIG-SOAK, RT-16-LIVE-ALARMS); the
  67-shape client replay on the candidate with #8859 merged.

### B2. 16.0.0 with the seam included

- **What happens.** #8861 and #8863 merge before the soak. 16.1.0 starts from a `dev` that already
  routes v1 through the interface.
- **Who it reaches.** The same as B1, plus every v1 read and write on every site going through new
  code.
- **Measure first.** The write-contract matrix, the HTTP and v1 read diffs and the client replay on
  the merged tree; the soak counts only from the merge. The gain is about one release of lead time
  for tenancy; the cost is a longer or restarted soak.

### B3. Identity first

- **What happens.** After 16.0.0, the next work is SPEC-ID-AMEND, the Loop reply (D-LOOP-ID) and
  the six ID-*-DECISION items, with WC-STEP-PATCH built to them.
- **Who it reaches.** Controller authors: Loop (`syncIdentifier`), Trio (`id`), AndroidAPS (keeps the
  server's `identifier`). Nocturne, through D-NOCTURNE-ID.
- **Measure first.** ID-DUP-MEASURE (duplicates by `identifier` across the corpus) and the replay of
  each controller's re-send.
- **Why it comes first.** It fixes the PostgreSQL key and the v4 typed paths; an answer that arrives
  after the tables exist is a migration.

### B4. Tenancy first

- **What happens.** ST-PG and TEN-RESOLVE are built before the identity decisions, with
  `identifier` as an unconstrained column.
- **Who it reaches.** Hosted tenants only; self-hosters are unaffected.
- **Risk.** The unique key and the typed record paths are decided later, against tables that hold
  data. It also puts PostgreSQL behind an interface that has had no release under real traffic.
- **When to choose it.** If a hosting partner needs a dated preview before the identity answers
  arrive; then TEN-LAB is labelled preview and ID-UNIQUE-INDEX is a migration step in the plan.

### B5. Registration and v4 as their own minors

- **What happens.** #8857 ships in 16.1.0 off by default; v4 statistics in 16.2.0; typed paths when
  decision 12 is settled.
- **Who it reaches.** Controller authors who opt in; Nocturne, as the second hub the contract is
  proposed to.
- **Measure first.** The conformance cases against a booted server (35 pass, 88 mapped, 0 fail at
  `3be98536`); flag off is byte-identical to `dev`.
- **Effect on tenancy.** None until `HUB-REG-CRM-SEAM`; registrations are per tenant (AU6), so the
  store gains a tenant column when ST-PG lands.

### B6. Prototypes in 16.0.0, labelled alpha (asked 2026-10-27)

The question: if a prototype of every REST API behind the storage interface, and a prototype of
multi mode, exist within days, are they worth shipping in 16.0.0 with their status noted, so the
release soaks them; and how does that weigh against releasing as soon as the candidate is ready?

- **The candidate is not ready to release now, so the choice is what is on `dev` when the soak
  starts.** Unmet on 2026-10-27: the real-rig soak (not started), the live delivery check, the
  BF-72 and BF-161 fork fixes, #8859 (needed in 16.0.0, draft), #8866 (`dev` CI red until it merges)
  and `master`'s protection (#8824 blocked). The soak cannot start until the code it measures is
  merged, so merging before it starts costs no restart.
- **The two prototypes behave differently in a release.**

  | | seam slices (#8861, #8863) | multi-mode prototype |
  |---|---|---|
  | reached by a self-hoster | every v1 read and write, by default | only with `TENANCY_MODE=multi` or `serve` |
  | soak value from shipping | high: every site exercises it | none: nobody running `single` runs it |
  | can be labelled alpha | no; code on the default path is either fit to ship or not | yes |
  | new public surface | none (behaviour-neutral) | subcommands and settings, which become semver surface (S3) once released |
  | security exposure | none new | tenant isolation and per-tenant credentials (T30-WIRING, D13, D14) unbuilt; a hoster can turn it on from a released image |
  | overlap with 16.0.0's required work | 7 files with the BF-72 fork fix (`adv/r3gv-1600`), 6 with #8859, 1 with BF-161's (`git diff --name-only` against `dev` `8dbb60c2`) | none measured |

- **The seam slices: in, only through an entry bar met before the soak starts.**
  1. #8859 and the seam chain merged together, the overlap resolved once.
  2. BF-72's fix re-merged onto the seam inside its private fork and its tests re-run there. The
     fix stays out of public branches until the release publishes it.
  3. The write-contract matrix (360 cells, off and reject) and the 67-shape client replay equal to
     the candidate without the slices.
  4. A read and write latency comparison on the corpus, with and without the slices. Not measured
     yet: v1 reads now translate each query into the filter tree and back.
  5. A one-step fallback: reverting the slices' merge commits restores the current paths, rehearsed
     once.
  Not met by the soak start → 16.1.0, as in §3.
- **The multi-mode prototype: shipped, but not in the 16.0.0 artifact.** Shipping it inside 16.0.0
  gives it no soak and makes its names public surface. Ship it as a prerelease instead
  (`16.1.0-alpha.1` image and tag from a branch, its status in the tag message), run in TEN-LAB
  and by a hoster who agrees to run alpha. If the maintainer still wants it in the tree for 16.0.0, the
  minimum is: unreachable without an explicit experimental setting, refused at boot without
  per-tenant credentials (no `API_SECRET` under `multi`, D13), and named in the release notes as
  outside the versioning policy.
- **Weighed against releasing at once.** Including the seam adds the entry bar's work (one or two
  days of agent time plus maintainer review of about 3,000 lines) before the soak starts, in
  exchange for one release of real traffic on the interface before PostgreSQL relies on it. If the
  gates are met before the bar is, release without the slices.

## 7. Sources

- cgm-remote-monitor `official/dev` `8dbb60c2`; PR heads `5c6ceabb` (#8859), `48e7e101` (#8861),
  `38b910d7` (#8863), `b63d9b7f` (#8862), `1dafe2a5` (#8865), `f7a43fed` (#8857), `4ed92673` (#8864),
  `bdd569a3` (#8866).
- [Next-gen platform plan](next-gen-platform-plan.md) and its data file.
- [16.0.0 contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md) and
  [decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md).
- [Semver policy](../modernization/semver-and-release-versioning-policy-2026-09-15.md) §2.
- [Execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md), D1–D21.
- [API v4 surface](v4-surface-and-nocturne-2026-10-26.md) §7.
