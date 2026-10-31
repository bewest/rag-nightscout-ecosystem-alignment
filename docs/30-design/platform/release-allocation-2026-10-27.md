# Release allocation: what goes in 16.0.0, what follows, and in what order

*Contributor-facing. Snapshot, 2026-10-27: cgm-remote-monitor `official/dev` `8dbb60c2`, re-anchored
for §0, §3.5 and Q13–Q16 at `ca1652d6` the same evening,
`official/master` `c6a0d8ed` (= `v15.0.9`), open PRs read with `gh pr list` and `gh pr view` the same
day. The work items are those of the living [next-gen platform plan](next-gen-platform-plan.md); the
release's own state is in [releases/cgm-remote-monitor-16.0.0](../../../releases/cgm-remote-monitor-16.0.0/contents.md).
The versioning rules quoted are those of the
[semver policy](../modernization/semver-and-release-versioning-policy-2026-09-15.md) §2. Recommendations
are proposals for the maintainer; nothing here is decided until §5 says so. A dated section on the
16.0.0 scope decided 2026-10-30 follows; the rest of the page is kept as written, with notes where that
decision supersedes it.*

## 16.0.0 scope, decided 2026-10-30

*Added 2026-10-30 at cgm-remote-monitor `official/dev` `991b0654` (merge of #8865). Source: the
[next-gen plan](next-gen-platform-plan.md) §1 and §1a and the
[ID-FIRST-MATCH design note](id-first-match-design-note-2026-10-29.md) §6a; the release's decision rows
are in [decisions.md](../../../releases/cgm-remote-monitor-16.0.0/decisions.md).*

- **16.0.0 targets every single-tenant item of the next-gen plan**, through the entry bar and in priority
  order (maintainer, 2026-10-30). The entry bar (maintainer, 2026-10-29): an item joins the merge list when its
  matrix result is as stated (0 cells, or named cells), its red controls and ablations pass, a revert has been
  rehearsed, and it has had time on `dev` with its cohort check. A miss at the tag rolls to 16.1.0, or to
  17.0.0 if it changes a default. The tag is gated by the bar, not by a date.
- **The identity work is the core.** It is the substance of the agreement with the Loop maintainers:
  identifier-first on every path, re-sends recognised, the format rules, and one record per identifier.
  D-LOOP-ID's three rules and ID-Q1..ID-Q11 were decided on 2026-10-29; ID-FIRST-MATCH goes to the bar as
  slices in the order 1, 2, 5, 3, 4, 6, 6a.
- **The unique index on `identifier` is in 16.0.0**, behind `WRITE_IDENTIFIER_INDEX=try|require|off`
  (default `try`). Under `try`, boot builds a partial unique index per collection online; on existing
  duplicates it logs the counts per collection (never the values), shows them on the status page and runs
  without the index, while the write rule (ID-Q5) still refuses a second record with a stored identifier.
  `require` refuses to start without the index; `off` skips it. An operator-run tool reports duplicate groups
  and resolves them by the P4 pick. The other settings named on 2026-10-29: `WRITE_RESEND`,
  `WRITE_IDENTIFIER`, `WRITE_DELETED_EDIT`.
- **Moved from 17.0.0 to 16.0.0, through the bar:** ID-UNIQUE-INDEX (Q5 below) and the parts of
  ID-FIRST-MATCH that change outcomes (slices 3 to 6a). **Moved from 16.1.0 and 16.2.0 to 16.0.0, through
  the bar:** `write(intent)` release 1 (#8874, WC-STEP-PATCH), ID-BATCH, the re-send switch, SPEC-ID-AMEND,
  #8857 registration (off by default; it needs a rebase onto `dev`), ST-HARNESS, and ST-EVENT and ST-VIEWS
  if they clear it.
- **Multitenant items may ship dormant, labelled alpha behind `serve`, or not ship.** Their rows in §4.3 are
  otherwise unchanged; Q12a's rule (the alpha label belongs to the multitenant bindings only) applies.
- **Merged since this page's snapshot** (to `991b0654`): #8871, #8872, #8873, #8877 (BF-209 and BF-211; BF-210
  withdrawn), #8878 (BF-212's split fix) and #8865 (one executable and the boot split, with ST-V3-DECOUPLE).
  The pre-tag merge order left: #8855, the BF-72 and BF-161 fork branches, then the `master` protection fix and
  #8824 (which still cannot meet `master`'s required `Run Tests (22, 4.4)`). The release's state is in
  [contents.md](../../../releases/cgm-remote-monitor-16.0.0/contents.md).

The maintainer asked four questions on 2026-10-27:

1. Given the progress toward multitenancy, how much of the storage seam should go into the current
   release, if any?
2. Does including the other roadmap features help multitenancy?
3. How should the releases and schedule for client identity, formal schemas, API v4 and multitenancy
   be managed against each other?
4. Where are the open questions and the briefs for understanding each scenario?

§1 answers in brief, §2–§4 give the reasoning, §5 lists the open decisions, and §6 holds the scenario
briefs. B6 and Q12 answer a follow-up the same day: whether prototypes should ship in 16.0.0 as alpha.

**Re-anchored the same evening at `official/dev` `ca1652d6`** (merge of #8858, 22:29Z). Between
`8dbb60c2` and `ca1652d6` ten PRs merged: #8864, #8866, #8859, #8868, #8856, #8861, #8863, #8870,
#8869 and #8858. Milestone M1 (every REST and socket record read, write and count through the storage
interface) is therefore on `dev` and ships in 16.0.0. §0 answers the four questions again from that
state; §1–§6 keep the morning's reasoning, with their decided rows marked. 16.0.0 is now
954 commits, 48 first-parent, 890 files, +139618/−18627 past `v15.0.9`
(`git rev-list --count`, `--first-parent --count`, `git diff --shortstat official/master official/dev`).

## 0. The questions again, after M1 landed (evening 2026-10-27)

- **How much more of the seam goes in 16.0.0: none, beyond what is on `dev`.** The behaviour-neutral
  slices that every single-tenant site runs (ST-FILTER, ST-READS, ST-WRITES, ST-COUNT-ONEPATH) are
  merged, so the soak value B6 argued for is already being collected. Every storage item left
  (§3.5) either changes what clients see (WC-STEP-PATCH, ID-BATCH), changes a safety-relevant
  computation (ST-VIEWS: the page, plugins and alarms), or is reached only by multi mode
  (ST-V3-DECOUPLE, PLAT-SERVE, ST-HARNESS, ST-PG). None of them improves 16.0.0 for a self-hoster,
  and each would spend the short quiet period the pre-tag definition of done asks for
  (`RT-16-RELEASE`, item 4, decided 2026-10-27). Recommendation: the remaining storage items wait for
  16.1.0. The quiet period is not a date: it starts when the 16.0.0 merge list is closed (Q13,
  corrected by the maintainer 2026-10-27: merging is still under way). D-EVENT was deferred by the maintainer the same evening (Q9); ST-EVENT stays tied to
  WC-STEP-PATCH in 16.2.0. **2026-10-29:** the maintainer added BF-209 (the socket's ±2 s similar
  treatment match follows client identity) to the 16.0.0 merge list; BF-210 was withdrawn the same day as
  not a defect. It is draft PR #8877 (`ebed6323`). BF-211 (a delete by query flushes all three in-memory caches; the fix flushes only the collection deleted from) joined the list the same day.
  **Also 2026-10-29 (maintainer):** `write(intent)` release 1 (#8874 with slices 4 and 6), then
  ID-FIRST-MATCH, ID-BATCH and the re-send switch (D-LOOP-ID rule 3) are **eligible for 16.0.0 through an
  entry bar**, in that order. Each item joins the merge list only when four things hold: its matrix result
  is as stated (0 cells, or named cells), its red controls and ablations pass, a revert has been rehearsed,
  and it has had time on `dev` with its cohort check. What has not cleared the bar when the maintainer
  chooses to tag rolls to 16.1.0. Because 16.0.0 is already a major, the identity rules planned for 17.0.0
  may land there instead.
- **Does including other roadmap features help multitenancy: not by being in 16.0.0.** The one
  indirect benefit, real traffic on the interface before PostgreSQL depends on it (§4.2), is now
  bought by M1. What shortens the path from here is decisions and a reopened `dev`: D-T30,
  D-LOOP-ID's remaining items, the identifier and schema rules that fix the PostgreSQL keys and
  columns, and ST-V3-DECOUPLE for `serve api`. Registration and v4 reads stay parallel work.
- **Schedule: tag 16.0.0 as soon as its four pre-tag items are met; then one theme per minor.**
  The fastest route to a multi-mode preview is to release 16.0.0 and reopen `dev`, not to load it.
  *(Superseded for the single-tenant items by the 16.0.0 scope of 2026-10-30, above.)*
  The revised themes are in §4.3 (16.1.0 one executable, `serve api` and registration off by
  default; 16.2.0 `write(intent)`, the commit event and identity on every path; 16.3.0 or later the multi preview;
  17.0.0 enforcement). Client identity and formal schemas run ahead of tenancy because they fix its
  tables; v4 publishes in pieces, unstable until shared.
- **Open questions and briefs:** Q13–Q16 in §5 and B7–B9 in §6 are new this evening.

What still stands between `dev` and the tag, at `ca1652d6`:

| pre-tag item (`RT-16-RELEASE`) | state |
|---|---|
| 1. live Pushover and APNs delivery (`RT-16-LIVE-ALARMS`) | not started |
| 2. cohort confirmations from `dev` users: AndroidAPS, Loop, Trio, xDrip+, a follower app, an mmol/L site (`RT-16-RIG-SOAK`); the M1 cohort table in B6 says what to ask each | not started |
| 3. BF-72 and BF-161 through their forks | fix branches `bf/regex-limits` `a9da33ff` and `bf/entries-pattern-limit` `1dce7722` contain ST-WRITES and the count commit, and are 15 commits behind `dev` `ca1652d6` (`git merge-base --is-ancestor`, `git rev-list --count`); a `dev` merge and re-run inside each fork is owed |
| 4. a short quiet period on `dev` with the final candidate | starts when the 16.0.0 merge list is closed (Q13); merging is still under way |
| `master` protection (#8824 `BLOCKED`) | still requires `Run Tests (22, 6)`, `Run Tests (22, 4.4)` and `Run Tests (24, 6)` and one approval (`gh api …/branches/master/protection`, read 22:4xZ); the decided change to require only *Tests pass* is not applied |
| `dev` CI on `ca1652d6` | CodeQL passed; *CI test and publish Docker image* in progress at the time of reading |

## 1. The answers in brief

- **Storage seam in 16.0.0: in, if it meets the entry bar with time left on `dev` before the tag
  (decided by the maintainer 2026-10-27, Q12).** #8854 (the write boundary) is on `dev` and ships. The three seam slices
  in review (#8861 ST-FILTER and ST-READS, #8863 ST-WRITES) are measured to change no behaviour, so no
  rule of the versioning policy needs them in a major. The first recommendation was to hold them to
  16.1.0 to keep the soak small (§3). The soak is informal (§2.1): whatever is on `dev` is run by
  people who use it as a nightly, so B6's measured checks decide, and the slices then need time on
  `dev` and targeted cohort checks before the tag. Building to the bar is worth doing either way, because it prepares the work that follows.
- **What 16.0.0 should still take** is the work whose behaviour change belongs at a major boundary or
  that fixes a live defect: #8859 (re-send matching and the null-removes rule), #8856 (BF-193, write
  logging), #8864 (the IOB pill on reconnect), #8866 (two CI test faults), #8858 (API docs held to the
  routes) and the BF-72 and BF-161 advisory fixes. #8862 (one executable) goes in only if it merges
  before the tag with time on `dev` (Q2).
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
  *(2026-10-30: the unique index moved to 16.0.0 behind `WRITE_IDENTIFIER_INDEX`, default `try`, which
  does not refuse existing data; see the 16.0.0 scope above.)*

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

*By `ca1652d6` (evening): #8859, #8856, #8858, #8864, #8866, #8861 and #8863 merged, with #8870
(the count commit) and #8868 and #8869. Still open: #8862 (`b63d9b7f`, 64 behind `dev`), #8865
(`1dafe2a5`, base `feat/storage-writes`, 55 behind), #8857 (`f7a43fed`, 64 behind, `DIRTY`:
conflicts with `dev`), and #8871 (editor `jsconfig.json`, 0 behind).*

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

### 2.1 How 16.0.0 is soaked (maintainer, 2026-10-27)

The soak is informal. Anything on `dev` is run by people who follow it as a nightly, so merging to
`dev` starts exposure; there is no separate soak start. When a change needs a specific behaviour
checked, the maintainers ask for it, or look for the cohort that exercises it (one uploader, one
follower app, mmol/L users, a hosting provider). RT-16-RIG-SOAK is met by those reports. Two
consequences for this plan:

- The deadline for anything entering 16.0.0 is the tag, less the time on `dev` its cohort checks
  need; it is not a soak start date.
- A change merged to `dev` early gets more exposure than one merged late, so a change that is going
  into 16.0.0 should merge as soon as its measured checks pass.

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

*Written before the maintainer said the soak is informal (§2.1). With no soak start to restart, the cost below becomes exposure time: slices merged late get less of it.*

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
order, and ship them in 16.1.0. This needs one rule for `dev` between now and the tag (Q1). The soak has not started, so B6 states the one condition under which they go into 16.0.0 instead: an entry bar met before it starts. *Decided 2026-10-27 (Q12): that condition applies; the slices are built to the bar and go in if they meet it.*
*Outcome: the bar was met and #8861, #8863 and #8870 merged to `dev` the same afternoon
(`84fac457`, `9668b179`, `7abe1cf6`), after #8859 and #8856 in the agreed order.*

### 3.5 The rest of the seam, after M1 (evening 2026-10-27)

| item | state at `ca1652d6` | ladder (§3.1) | who in 16.0.0 would run it | proposed release |
|---|---|---|---|---|
| ST-EVENT (D-EVENT) | deferred, research continuing (maintainer, 2026-10-27): counts-only and internal; reopened when WriteResult.items[], a first subscriber and the BF-164 re-measure are in hand (the replica-set count dropped 2026-10-31: a replica set is optional, so the event's source is the write result) | none while nothing in `lib/` subscribes; the commit event is internal and unstable (#8854 condition) | nobody | 16.2.0, with WC-STEP-PATCH |
| ST-V3-DECOUPLE (M3) | planned; it is the cause of `serve api`'s 81 failing API v3 suites at #8865 `1dafe2a5` | patch-class if `single` is unchanged | every site, for no gain under `single` | 16.1.0, with PLAT-SERVE |
| PLAT-ENTRY (#8862) | superseded by #8865, which carries its four commits (2026-10-27 night) | minor-class (question 9) | — | lands with #8865 |
| PLAT-SERVE (#8865) | **in the 16.0.0 merge list (maintainer, 2026-10-27 night)**; open, base `dev`, head `53ba192a` (2026-10-27 night): CodeQL alert 138 fixed (CodeQL marks it fixed on the PR); image start forms measured unchanged against `dev` apart from stop and signals (`tools/lab/image-start-forms`) | minor-class | every Docker site: same start, clean stop; `serve api` nobody under `single` | 16.0.0 if it joins the merge list (Q13), otherwise 16.1.0; `serve` labelled alpha |
| WC-STEP-PATCH, ID-BATCH (M2) | planned | minor-class (question 10: reply shape, per-item results) | every uploader | 16.2.0 |
| ST-VIEWS (M4) | planned | patch-class only if every view equals today's; the alarms are safety-relevant (execution plan §7b) | every page and alarm | 16.2.0 or later, with alarm cohort checks; before multi |
| ST-HARNESS, ST-PG (M5) | planned | none for `single` | nobody | 16.3.0 or later (multi preview) |

So the morning's question (how much of the seam goes ahead of multitenancy into 16.0.0) is answered
by what merged: the part every single-tenant site exercises went in; the part only multi mode needs
waits for the minors, where it can ship as alpha without holding the tag.

*2026-10-30:* the "proposed release" column is superseded for the single-tenant items by the 16.0.0 scope
(above): WC-STEP-PATCH, ID-BATCH, ST-EVENT, ST-VIEWS and ST-HARNESS target 16.0.0 through the entry bar,
rolling to 16.1.0 (or 17.0.0 for a default change) on a miss. ST-V3-DECOUPLE and PLAT-SERVE merged with
#8865 (`991b0654`). ST-PG stays with the multitenant rows.

## 4. How the tracks depend on each other

### 4.1 Which features shorten the path to multitenancy

The multitenant target (D1–D3) is PostgreSQL with row-level security behind the same storage
interface, with tenant resolution and per-tenant credentials. Its critical path in the plan:

```
ST-WRITES → WC-STEP-PATCH → ST-HARNESS → ST-PG ─────────────────────────┐
T30-RESEARCH (D-T30) → T30-SCHEMA-CONFIG ───────────────────────────────┼→ TEN-RESOLVE → T30-WIRING → TEN-LAB
PLAT-ENTRY → PLAT-SERVE ───────────────────────────────────────────────┘
```

| track | on the critical path? | why |
|---|---|---|
| Storage slices | yes | ST-PG is an implementation of the interface they build |
| Client identity (ID-FIRST-MATCH, ID-UNIQUE-INDEX) | yes, for the schema | the PostgreSQL key for a client record is (tenant, collection, `identifier`); settling identifier format, scope and immutability before the tables exist avoids migrating them. D-LOOP-ID's six questions are the slowest input, because they wait on another project's answer |
| Formal record schemas (records spec, `indexedFields`, OpenAPI) | yes, for the columns | D11 emits only declared indexed fields as columns and keeps the rest in JSONB; the declared set comes from these schemas |
| `WRITE_VALIDATION` rules | partly | WC-STEP-PATCH moves the rules into `write(intent)`; whether they reject by default is a separate, major decision |
| PLAT-ENTRY, PLAT-SERVE | yes | multitenant roles (D5) are `nightscout serve <roles>` |
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

> **Superseded for the single-tenant items, 2026-10-30 (maintainer).** The single-tenant items in the
> 16.1.0, 16.2.0 and 17.0.0 rows below target 16.0.0 through the entry bar, and a miss rolls to 16.1.0, or
> to 17.0.0 if it changes a default (the 16.0.0 scope, above). ID-UNIQUE-INDEX and the outcome-changing parts
> of ID-FIRST-MATCH moved from 17.0.0 to 16.0.0 through the bar. The multitenant rows (16.3.0 or later) are
> unchanged, except that multitenant items may also ship in 16.0.0, dormant and labelled alpha behind `serve`.
> `WRITE_VALIDATION`'s default and D8's v1 query bounds are not part of the 2026-10-30 decision. The table is
> kept as proposed on 2026-10-27.

| release | theme | contents | class |
|---|---|---|---|
| 16.0.0 | modernization, the write boundary, one read and write path | what is on `dev` `ca1652d6` (M1 included: #8859, #8856, #8861, #8863, #8870, #8864, #8866, #8868, #8869, #8858 merged 2026-10-27), plus BF-72, BF-161, #8865 (decided 2026-10-27 night; `single` supported, `serve` reserved for a multitenant Nightscout) and any release fix found in the quiet period | major (already) |
| 16.1.0 | registration readable | #8857 off by default (D-REG-FLAG); SPEC-ID-AMEND; the OpenAPI description of what 16.1.0 serves, including the registration paths | minor |
| 16.2.0 | `write(intent)` and identity on every path | WC-STEP-PATCH, ST-EVENT, ID-BATCH, ID-FIRST-MATCH where it changes no outcome, ST-HARNESS; ST-VIEWS if its alarm checks pass; REG-S3 behind its flag; v4 statistics reads | minor |
| 16.3.0 or later | multi mode, preview | ST-PG, T30-SCHEMA-CONFIG, TEN-RESOLVE, T30-WIRING behind `nightscout serve` (the subcommand selects tenancy, 2026-10-27; formerly `TENANCY_MODE=multi`); TEN-LAB passes with its control; single-tenant unchanged | minor for self-hosters |
| 17.0.0 | contract tightening | ID-UNIQUE-INDEX with a duplicate-cleaning step, ID-FIRST-MATCH where it changes outcomes, `WRITE_VALIDATION` default (if decided), D8 v1 query bounds, any v4 path promoted from unstable | major |

Two consequences:

- **Multitenancy does not wait for 17.0.0.** Multi mode is a new deployment target behind a setting
  a self-hoster never sets, so for the single-tenant surface it is additive (question 9). Its
  maturity for multitenant use is a separate label (preview, then supported), set by TEN-LAB and a multitenant
  soak, not by the version number.
- **17.0.0 is where identity is enforced, not where it starts.** Identifier matching starts in
  16.0.0 (#8859) and spreads in 16.2.0; the unique index that makes it a guarantee is the major.
  *(2026-10-30: superseded. Identifier-first on every path and the unique index target 16.0.0 through the
  bar; the index ships with the default `try`.)*

**Milestones proposed by session -2e (2026-10-27); M3 and M4 adopted as plan items the same day (maintainer): `ST-V3-DECOUPLE` and `ST-VIEWS`.** A finer split of the storage and
tenancy work, from its route census of `dev` `2dc0c1bc` (129 routes and 7 socket events):

| milestone | contents | exit check | release row |
|---|---|---|---|
| M0 | route census | done | — |
| M1 | one read and write path: every REST and socket record read and write, and count, through the storage interface (#8861, #8863, the count commit, ST-COUNT-ONEPATH) | the census finds no direct driver call in `lib/server` or `lib/api` | 16.0.0 (Q12) |
| M2 | `write(intent)`, then the commit event (D-EVENT deferred until it exists) | | 16.2.0 |
| M3 | API v3 decoupled from v1 and the cache (the cause of `serve api`'s 81 failing suites in #8865) | | 16.1.0 or 16.2.0 |
| M4 | computed views without a resident `ddata` | | before multi |
| M5 | backend-selectable harness and PostgreSQL | | 16.3.0 or later |
| M6 | tenant resolution, per-tenant credentials, realtime, the multitenant lab, as a preview | | 16.3.0 or later |

M3 is `ST-V3-DECOUPLE` and M4 is `ST-VIEWS` in the [next-gen plan](next-gen-platform-plan.md) (adopted 2026-10-27); the other milestones map onto existing items.

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
| Q1 | How is `dev` kept stable before the 16.0.0 tag (the soak is informal, §2.1)? | (a) `dev` takes release fixes only until the tag; feature PRs stay draft. (b) cut `release/16.0.0` from `dev` now; soak and tag from it; `dev` takes the seam. | (a): the soak and the Docker `dev` image both run from `dev` today, and a second long-lived branch doubles the merge work for a few weeks | #8861, #8863, #8865, #8857 merge dates |
| Q2 | #8862 (one executable) in 16.0.0? | (a) yes, if merged with time on `dev` before the tag; (b) 16.1.0 | (a): the image's start changes form, and a major's release notes already ask operators to check their start; if the soak has started, (b) | the soak start |
| Q3 | The seam slices in 16.0.0? | (a) hold to 16.1.0; (b) merge now | *Superseded by Q12 (decided 2026-10-27):* in, through B6's entry bar, merged to `dev` once its measured items pass (§2.1); otherwise 16.1.0 | tenancy start date by the time the soak takes |
| Q4 | #8857 in 16.1.0, off by default? | keep `CONTROLLER_REGISTRATION` on/off, or a staged mode (D-REG-FLAG) | 16.1.0 with whichever flag the PR review settles | REG-S3 |
| Q5 | Is ID-UNIQUE-INDEX (with duplicate cleaning) 17.0.0 material? | (a) yes; (b) add the index as opt-in in a minor, enforce in 17.0.0 | (b): an opt-in index lets operators measure their duplicates first. *Decided 2026-10-30 (maintainer), neither: in 16.0.0 through the entry bar, behind `WRITE_IDENTIFIER_INDEX=try\|require\|off`, default `try` (built where no duplicates block it; counts logged and shown otherwise), with an operator-run report and clean tool* | ID-UNIQUE-INDEX, the PostgreSQL key |
| Q6 | Does multi mode ship in 16.x minors behind `TENANCY_MODE=multi`? *(Since 2026-10-27 the gate is `nightscout serve`, not a setting. 2026-10-30: multitenant items may also ship in 16.0.0, dormant and labelled alpha behind `serve`, or not ship.)* | (a) yes, labelled preview; (b) wait for 17.0.0 | (a), §4.3 | TEN-LAB's release |
| Q7 | How is v4's stability declared? | (a) per path in the capability document; (b) a `/api/v4-unstable` prefix; (c) no marker | (a): the capability document is already the place a client reads what the hub serves | REG-PROPOSE |
| Q8 | `WRITE_VALIDATION` default | (a) stays `off`; (b) `log` in a minor; (c) `reject` in 17.0.0 | (b) then (c), after #8841's open items (contents, item 7) | 17.0.0 contents |
| Q9 | D-EVENT: commit event per call or per driver operation | per the plan's decision card | *Deferred, maintainer 2026-10-27:* no shape adopted; the event stays counts-only and internal; reopened when WC-STEP-PATCH's WriteResult.items[], a named first subscriber, the BF-164 websocket cursor re-measure and a count of replica-set sites are in hand. Research continues as input: a post-write variant, with a capped pre-read as the comparison (session -2e). *2026-10-30 (maintainer, via session -7d, on the cache catch-up lab):* "the cache needs records named" is dropped as a reason to reopen D-EVENT; the four reopen conditions stay for its other subscribers (sync, alarms, screen refresh), and when it reopens it names records from the same `WriteResult.items[]`. For release 2 the write step resolves every write by filter (v1 delete by query, update by filter, socket filter writes) to ids first, writes `{filter AND _id in ids}`, returns the ids in `items[]`, and the cache removes or re-reads exactly those; over 1,000 ids it falls back to today's per-type reload; no timestamp watermark (this replaces the srvModified watermark proposal). One behaviour change: a matching record inserted during a delete by query survives. Condition: a lab arm confirms the `{filter AND ids}` write first (session -7d, on `dev` `305a6533`). **Q-A adopted for release 2** (maintainer, 2026-10-30: adopt once the conditions are met; both remaining conditions met the same day, session -7d: the cache-announcement fixture on `proto/v3-unify` `3b7f054a`, and cache lab round 3 exact in all 15 v3 scenarios at both sizes with its break-it arm flagged 10/10). Its rule-copy reduction is a follow-up (of the 23 pairs: 3 become removable with one shape, 9 follow their own release-2 decisions, 11 are wiring). Earlier record, kept: *leaning towards one write shape, conditional*: API v3's writes by identifier become the simplest filter write resolved to ids (its identifying read supplies the `_id`; the step writes `{identifier AND _id}`; `items[]` returns the document; the cached wrapper's filter methods go), decided only when a v3 prototype slice shows (1) backward compatibility (G1 0/360, the commit-event copy 0, socket tests green), (2) quality (fixtures that fail without each kept behaviour: Q-S every stored form, PUT/PATCH on writeFilter's pick, duplicate-`_id` refusal; fewer duplicated rule copies than today's 23) and (3) the cache lab's round 2 confirms the resolved write is exact; if any fails, two write shapes stay. **Q-U decided**: autoPrune goes through the write step with id resolution (up to 1,000 resolved and named; when the prune days exceed the cache's retention for that collection the pruned records are already out of the cache, so nothing reloads, and where they are shorter the named ids are removed from the cache (BF-222 is today's gap there); over 1,000 the unscoped delete and today's reload); no change for users or clients. **The 1,000 cap is a fixed named constant** shared by v1, the socket, v3 and autoPrune, not a setting and not a D22 policy entry; revisited only on a measurement *2026-10-31 (maintainer, via session -81):* the fourth reopen condition, a count of replica-set sites, is dropped: "The number of sites using mongo replica set is not relevant; many using Mongo Atlas are using a replica set, practically all using some nightscout as a service solution, but many DIY or 'Google NS' folks do not use replica set. It's optional." Consequence: change streams cannot be the required source of the event; the write's own result (`WriteResult.items[]`) is the source on every site, and change streams can at most be an optional transport. Three conditions remain (items[], a named first subscriber, the BF-164 re-measure); the rest of D-EVENT is being walked through with the maintainer one question at a time (session -81). **D-EVENT question 1 (scope) decided, 2026-10-31 (maintainer, via session -81):** the in-process commit event names its records' ids from the write step's own `WriteResult.items[]`; that source is complete because every supported write goes through Nightscout ("Nightscout does not support other writers to mongodb; xdrip's mongodb upload is considered deprecated by Nightscout authors"). Delivery between processes is deferred to the `serve` roles. A timer runs only for time-driven alarms (stale data, not looping), never to catch up on writes. The event stays internal and unstable until a subscriber outside `lib/` exists. Follow-up topic, not answered here: the CLI run-and-subcommands pattern, `nightscout single [roles,...]` against `nightscout multitenant [roles,...]` (maintainer: "the serve roles do exist, and are planned soon"), which would make roles orthogonal to tenancy (ties to D21 and D-EXEC-PROFILE). Question 2 (one event per `write(intent)` call or per driver operation) is next | ST-EVENT, the change feed, WC-STEP-PATCH release 2 |
| Q10 | D-T30: approve the tenant configuration surface | walk through the DECISION sections | start once 16.0.0 is tagged, after re-measuring the 277 settings on `dev` | T30-SCHEMA-CONFIG, TEN-RESOLVE |
| Q11 | Review capacity | #8857, #8859, #8861, #8862, #8863 and #8865 add 17,794 lines against their bases (§2) | review in theme order (16.1.0 first), one stacked chain at a time | every row of §4.3 |
| Q12 | Put prototypes in 16.0.0 to soak them as alpha? | *Decided, maintainer 2026-10-27:* the seam slices go into 16.0.0 if feasible and B6's entry bar is met with time on `dev` before the tag (§2.1); building them to that bar is worth doing whether or not they ship, because it prepares the work that follows. Components that ship before they are mature are labelled alpha in the release notes. Still open: Q12a | B6 | the soak start, BFQ-72 |
| Q12a | If the slices ship, how is an alpha label made meaningful for code on the default path? | *Decided, maintainer 2026-10-27:* option (a). The slices are default on in the single-tenant release, named in the release notes as new internals, with the rehearsed revert as the fallback. Once verified, exercised on `dev` and released, that code is trusted for what single-tenant sites run. The alpha label belongs to the multitenant bindings only: `serve` roles, tenant resolution and scope, per-tenant credentials, and the PostgreSQL backend. Trust covers the paths real clients exercise; code no single-tenant site runs (the filter tree's SQL translation, the tenant binding the interface carries, rarely used endpoints without a cohort check) does not inherit it | — | the release notes' wording |
| Q13 | When does the quiet period start? | *Corrected by the maintainer, 2026-10-27:* not now; merging is still under way. Proposed: it starts when the 16.0.0 merge list is closed: what is in flight for 16.0.0 (#8872 BF-194, merged 2026-10-27 as `db3b9e4e`; #8855 translations, BF-72 and BF-161 through their forks) plus whatever the maintainer adds to it, with #8865 decided either way. Until then `dev` keeps taking 16.0.0 work, and the cohort requests (Q14) start now, because M1 and #8859 are already on `dev` | *#8865 in (maintainer, 2026-10-27 night).* Open: the rest of the merge list | the tag date; #8865, #8857 merge dates |
| Q14 | Who asks the cohorts, and when? | (a) now, one request per cohort in B6's table, naming M1 and #8859 as what changed; (b) after the alarms check | (a): the cohort confirmations are pre-tag item 2 and the slowest, because they wait on other people | `RT-16-RIG-SOAK` |
| Q15 | #8865's base | (a) retarget to `dev` now and merge `dev` in, still draft; (b) close it and reopen with ST-V3-DECOUPLE | (a), by the maintainer; re-measure `serve api` after | PLAT-SERVE, ST-V3-DECOUPLE |
| Q16 | When does `dev` reopen for 16.1.0 work? | (a) the day 16.0.0 is tagged; (b) a `release/16.0.0` branch for fixes, `dev` reopened earlier | (a), as Q1 (a); (b) only if the quiet period runs longer than about two weeks | every 16.1.0 row |

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

- **What happens.** #8861 and #8863 merge to `dev` as soon as their checks pass (now the decided path, Q12). 16.1.0 starts from a `dev` that already
  routes v1 through the interface.
- **Who it reaches.** The same as B1, plus every v1 read and write on every site going through new
  code.
- **Measure first.** The write-contract matrix, the HTTP and v1 read diffs and the client replay on
  the merged tree; `dev` users exercise them from the merge (§2.1). The gain is about one release of lead time
  for tenancy; the cost is less time on `dev` for the rest of 16.0.0's changes to be told apart from the slices if something regresses.

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
- **Who it reaches.** Tenants of a multitenant Nightscout only; single-tenant sites are unaffected.
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

*Decided, maintainer 2026-10-27: the seam slices go in if feasible and the entry bar below is met; components that ship before they are mature are labelled alpha (Q12, Q12a).*

The question: if a prototype of every REST API behind the storage interface, and a prototype of
multi mode, exist within days, are they worth shipping in 16.0.0 with their status noted, so the
release soaks them; and how does that weigh against releasing as soon as the candidate is ready?

- **The candidate is not ready to release now, so the choice is what is on `dev` long enough before
  the tag.** Unmet on 2026-10-27: the real-rig soak (not started), the live delivery check, the
  BF-72 and BF-161 fork fixes, #8859 (needed in 16.0.0, draft), #8866 (`dev` CI red until it merges)
  and `master`'s protection (#8824 blocked). The soak is informal (§2.1): `dev` users exercise
  whatever is merged, so a change merged sooner is soaked longer.
- **The two prototypes behave differently in a release.**

  | | seam slices (#8861, #8863) | multi-mode prototype |
  |---|---|---|
  | reached by a self-hoster | every v1 read and write, by default | only with `TENANCY_MODE=multi` or `serve` |
  | soak value from shipping | high: every site exercises it | none: nobody running `single` runs it |
  | can be labelled alpha | no; code on the default path is either fit to ship or not | yes |
  | new public surface | none (behaviour-neutral) | subcommands and settings, which become semver surface (S3) once released |
  | security exposure | none new | tenant isolation and per-tenant credentials (T30-WIRING, D13, D14) unbuilt; a hoster can turn it on from a released image |
  | overlap with 16.0.0's required work | 7 files with the BF-72 fork fix (`adv/r3gv-1600`), 6 with #8859, 1 with BF-161's (`git diff --name-only` against `dev` `8dbb60c2`) | none measured |

- **The seam slices: in, only through an entry bar, merged to `dev` as soon as items 1, 3, 4 and 5
  pass.**
  1. #8859 and the seam chain merged together, the overlap resolved once.
  2. BF-72's fix re-merged onto the seam inside its private fork and its tests re-run there. The
     fix stays out of public branches until the release publishes it.
  3. The write-contract matrix (360 cells, off and reject) and the 67-shape client replay equal to
     the candidate without the slices.
  4. A read and write latency comparison on the corpus, with and without the slices. Not measured
     yet: v1 reads now translate each query into the filter tree and back.
  5. A one-step fallback: reverting the slices' merge commits restores the current paths, rehearsed
     once.
  Not met with time on `dev` before the tag → 16.1.0, as in §3.
- **Results, 2026-10-27: all five items met** on local candidates (session -2e's agent;
  Node 22.23.4, MongoDB 5.0.33; `dev` `2dc0c1bc`, #8859 `5c6ceabb`, #8861 `48e7e101`, #8863
  `38b910d7`). Item 2 met the same day by session -e4, inside the private forks (below).

  | item | result |
  |---|---|
  | 1. merged together | `cand/without` `2cae64f3` = `dev` + #8859 (clean); `cand/with` `d6ba8e18` = that + #8861 (clean) + #8863 (five conflict resolutions, in `profile.js`, `websocket.js` and a test stub; #8859's four direct reads in `entries.js` and `devicestatus.js` moved onto the interface) + the count commit `079f20ae` (clean); 36 files, +3124/−251. Order: #8859 first; seam first was measured and is not cheaper |
  | 3. behaviour | write-contract matrix, 360 cells: with = without in off and in reject (0 differing; off vs reject differ in 12 on each, so the matrix can see a change). Client replay, 67 rows / 201 cells: equal; its dead-port and wrong-expectation controls fail. v1 HTTP differential: 700 of 700 identical. Suites, passing/failing/pending: without `npm test` 4575/0/3, `test:all` 4903/0/3; with 4687/0/3 and 5015/0/3 |
  | 4. latency | 16 read and write shapes, 200 runs each, interleaved, on a 90-day synthetic database: with/without median 0.99–1.04 and p95 0.93–1.04, inside the noise floor (median 0.97–1.05). No measurable change. Not measured: concurrent load, larger databases, MongoDB 8, Node 26 |
  | 5. revert | `cand/with-reverted` `cf762dd0`: one commit reverting the three merges; its tree equals `cand/without`'s (`7a6f5c20`, checked by session -ee) and `npm test` gives 4575/0/3 |
  | 2. advisory fixes | BF-72's and BF-161's fixes merged onto `cand/with` in their private forks, local only (session -e4; Node 22.23.4, MongoDB 8.0.34). BF-72: seven files resolved where the slices move v1 reads onto the interface; its read time limit now travels through the interface, the new count path included; `npm test` 4765/0/3, `test:all` 5093/0/3; removing the limit from either path fails the matching test. BF-161: no conflicts; its check still runs before the pattern is expanded; 4703/0/3 and 5031/0/3. Both are published with the release, through the forks |
  | the count operation | `GET /api/v1/count/:storage/where`, the one REST storage call still direct after #8863 (approved by the maintainer 2026-10-27), on `feat/storage-writes-count` `079f20ae`: its test fails 2 of 4 on `38b910d7`; v1 HTTP differential 700 of 700 identical including 219 count requests, and a deliberate break gives 102 differing |

  The candidates are local. On `dev` `94899828` (#8866 and #8859 merged) the slices are re-merged as
  `479e33d1` and `a3f74a08`; outside the 11 files #8866 changed, their trees equal the measured ones
  (checked by session -ee). Re-run on `a3f74a08` (session -2e): `npm test` 4687/0/3 and `test:all` 5015/0/3,
  the same totals as `cand/with`; the 360-cell matrix equals `dev` `94899828` in off and in reject
  (off vs reject differ in 12 cells on each). The client replay, v1 HTTP differential and latency are
  not re-run: their inputs are the non-CI tree, which is unchanged. Before anything is
  pushed, the conflict resolutions go onto the PR
  branches (`dev` and #8859 merged into `feat/storage-filter` and `feat/storage-writes`, the count
  commit added to #8863), and the maintainer merges #8859 before #8861 and #8863.
  Merge order to `dev`, agreed 2026-10-27 (maintainer; sessions -2e and -e4): #8859, then #8856
  (BF-193), then #8861 and #8863. #8856 is resolved against the slices on `prep/writes-plus-8856`
  `699a70c4` (`npm test` 4694 passing, 0 failing, 3 pending; session -2e).
- **Cohort checks to request once the slices are on `dev`** (they move every v1 read and write onto
  the interface):

  | cohort | what to check | why |
  |---|---|---|
  | AndroidAPS (API v3 client) | uploads, re-sends and deletions sync without duplicates or refusals | v3 already uses the adapter the slices extend |
  | Loop and Trio (v1 treatments, `syncIdentifier`, `id`) | carbs, boluses and temp targets appear once; edits and deletes take effect | ST-WRITES moves v1 treatment writes |
  | xDrip+ and other v1 entries uploaders | readings appear on time, no gaps after a reconnect | v1 entries writes and the dedup key |
  | follower apps (LoopFollow, Nightguard, Nightscout watch faces) | current reading, IOB and COB match the site | v1 reads through `fromMongo` |
  | report users (Nightscout Reporter, the site's reports) | long-range reports load and match 15.0.9's numbers | large v1 queries; the latency item |
  | mmol/L sites | values and targets shown in the right unit | units handling on the paths that moved |

- **The multi-mode prototype: shipped, but not in the 16.0.0 artifact.** Shipping it inside 16.0.0
  gives it no soak and makes its names public surface. Ship it as a prerelease instead
  (`16.1.0-alpha.1` image and tag from a branch, its status in the tag message), run in TEN-LAB
  and by a hoster who agrees to run alpha. If the maintainer still wants it in the tree for 16.0.0, the
  minimum is: unreachable without an explicit experimental setting, refused at boot without
  per-tenant credentials (no `API_SECRET` under `multi`, D13), and named in the release notes as
  outside the versioning policy.
- **Weighed against releasing at once.** Including the seam adds the entry bar's work (one or two
  days of agent time plus maintainer review of about 3,000 lines) before merging to `dev`, in
  exchange for one release of real traffic on the interface before PostgreSQL relies on it. If the
  gates are met before the bar is, release without the slices.

### B7. Close the merge list, then a short quiet period, then the tag (recommended, evening 2026-10-27)

- **What happens.** The 16.0.0 merge list (Q13) is merged; then `dev` takes release fixes only for a
  few days with the final candidate. The cohort requests (Q14) and the live alarms check start now and
  run in parallel; BF-72 and BF-161 are brought up to `dev` inside their
  forks. D-T30 and the remaining identity questions are settled while `dev` is quiet.
- **Who it reaches.** Every 16.0.0 user, through M1 and #8859, which are new code on every v1 read
  and write; B6's cohort table is the check list.
- **Measure first.** The cohort confirmations; a 360-cell matrix and client replay on the final
  candidate, which will include the fork fixes.
- **Effect on tenancy.** 16.1.0 work (ST-V3-DECOUPLE, registration, and PLAT-SERVE unless it joins
  the merge list) builds on branches and merges when `dev` reopens.

### B8. Take #8865 into 16.0.0 (it supersedes #8862) — decided 2026-10-27 night

- **What happens.** #8865 joins the 16.0.0 merge list (Q13) and merges before the list closes;
  #8862 is closed as superseded.
- **Who it reaches.** Every Docker site. Measured 2026-10-27 night on images built from `dev`
  `dcf20bfb` and #8865 `9bb1f0b4` (`tools/lab/image-start-forms`): every `docker run` form that
  started a server on `dev` starts the same server, with the same entrypoint, user, workdir and
  environment, one node process and no HEALTHCHECK; `status.json` is identical apart from the server
  time. What changes: `docker stop` takes 0.13 s and exits 0 instead of 10.1 s and 137; SIGINT and
  SIGTERM, ignored by node as PID 1 on `dev`, now shut the server down; `nightscout single` and
  `nightscout healthcheck` work as commands.
- **Measure first.** Nothing left to measure on the image. The release notes name the one case the
  lab cannot reach: a supervisor that sends SIGTERM itself under `restart: on-failure` (the site used
  to keep running; it now exits 0 and stays down), and tooling that matches PID 1's command line.
- **Trade.** A cleaner stop for every Docker site in the major, against one more PR in the merge
  list; `serve` is reserved for a multitenant Nightscout and refuses every role until one is
  multitenant (maintainer, 2026-10-27 night).

### B9. Multitenant roles in 16.0.0 as alpha

- **What happens.** ST-V3-DECOUPLE is built and #8865 merged before the tag, `serve api` labelled
  alpha.
- **Why not.** Nobody under `single` runs it, so the release gives it no soak (B6), its names
  become public surface, and the quiet period moves out. The prerelease route in B6
  (`16.1.0-alpha.1` from a branch, run in TEN-LAB) gives the same exposure to the people who would
  run it.
- **Outcome (2026-10-30).** #8865 merged with ST-V3-DECOUPLE (`991b0654`); `serve` still refuses every role.
  The 16.0.0 scope allows multitenant items to ship dormant, labelled alpha behind `serve`, or not ship.

## 7. Sources

- Evening re-anchor: `official/dev` `ca1652d6`, `official/master` `c6a0d8ed`; open PR heads
  re-read with `gh pr view` and fetched; fork fix heads `a9da33ff` and `1dce7722`; `RT-16-RELEASE`'s
  pre-tag definition of done (`queue/work-queue.yaml`, 9fb924b0f).
- cgm-remote-monitor `official/dev` `8dbb60c2`; PR heads `5c6ceabb` (#8859), `48e7e101` (#8861),
  `38b910d7` (#8863), `b63d9b7f` (#8862), `1dafe2a5` (#8865), `f7a43fed` (#8857), `4ed92673` (#8864),
  `bdd569a3` (#8866).
- [Next-gen platform plan](next-gen-platform-plan.md) and its data file.
- [16.0.0 contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md) and
  [decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md).
- [Semver policy](../modernization/semver-and-release-versioning-policy-2026-09-15.md) §2.
- [Execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md), D1–D21.
- [API v4 surface](v4-surface-and-nocturne-2026-10-26.md) §7.
