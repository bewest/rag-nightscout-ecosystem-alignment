# Next-gen platform: one write path, four tracks

*Contributor-facing living plan. Tenancy reconciled 2026-11-06 to
[R62](../remedial/rc-16.0.0-integration-record.md#r62---bounded-owner-reader-replay-and-populated-recovery-batch-2026-11-06)
and [R64](../remedial/rc-16.0.0-integration-record.md#r64---published-control-recovery-batch-remote-verification-2026-11-06):
draft #8898 is `83582e87`, based on dev `4a482627`, with CI and CodeQL green on
that head. R67/R68 add bounded local component evidence. Earlier storage,
identity and registration measurements retain their named pins. Current milestone
claims live in the [delivery dashboard](../tenancy/multitenant-delivery-dashboard.md);
release placement lives in [release allocation](release-allocation-2026-10-27.md).*

The interactive version, with the dependency map, is the site page [nightscout-next-gen-platform.html](../../../site/pages/nightscout-next-gen-platform.html).

This plan covers the work that follows the 16.0.0 modernization:

- storage behind one write path;
- the client and server identifiers Loop asked to separate;
- controller registration, from a read-only catalogue to typed writes;
- multitenant Nightscout.

It names each piece of work, what it needs first, where it goes in the code, and the check that pins it.

## 1. Where things stand

The [tenancy reading guide](../tenancy/README.md) identifies the current plan,
decision owners and historical evidence. Start with the dashboard for sequencing;
use this map to see how the platform tracks meet.

| Scope | Current recorded acceptance | What remains |
|---|---|---|
| Multitenant foundations and initial preview | [R72](../remedial/rc-16.0.0-integration-record.md#r72---admitted-entries-and-owner-configuration-completion-batch-2026-11-06) retains M0 and promotes M1/M2, followed by M3/M4 on cumulative evidence. | Draft #8898; source acceptance is distinct from dev merge, operator release and default/production enablement. |
| Data, authority and clients | Admitted PG ports/import and actual typed/versioned owner settings pass; reader clamping is removed, legacy own-tenant credentials and writer fences retained. | M1 resource bounds deferred C. M4 actual headless/source-pattern bar, no all-client claim; Android emulator C. Human issuer/refresh, wider catalogue/lifecycle and production resolution trust remain M6. |
| Durable runtime | R67/R68 retain bounded clinical/DATA prototype evidence; R71 final-floor PostgreSQL proof is recorded and joined in R72. | M5/M6 remain open: live roles/current delivery, durable ack/snooze, notification/provider recovery and operational acceptance. Fresh-only ordering has no populated/imported-history migration or downmigration. |
| Local joined candidate | Owner CLI, clinical projection and experimental DATA components are joined in a **local candidate in verification**. | Reader option is removed in the local candidate; comprehensive verification is pending; native component evidence does not accept a fresh joined full/browser campaign or promote M2/M5. Current head and lane state belong to the dashboard. |
| Independent single/nonresident profile | R55 accepts private acquisition on `2ee8b493`, with caller policies and the physical subscriber retained. | The whole profile branch remains separate. Reusing its private helper/evaluateCycle hunk in the local candidate establishes no common atomic revision, live profile role or notification handoff. |

The [integration record](../remedial/rc-16.0.0-integration-record.md#r62---bounded-owner-reader-replay-and-populated-recovery-batch-2026-11-06)
owns measured heads, controls and source-identity reuse; the [R62 capsule](../../../reports/tenancy/control-recovery-acceptance-87133959-2026-11-06.md) retains broad campaigns executed on `87133959` and the exact runner-only difference on `83582e87`. R64 records remote publication
checks separately from local acceptance. [R67](../remedial/rc-16.0.0-integration-record.md#r67---bounded-recovered-clinical-projection-native-controls-2026-11-06)
and [R68](../remedial/rc-16.0.0-integration-record.md#r68---fresh-schema-socket-data-prototype-native-controls-2026-11-06)
are bounded local component evidence, not whole-candidate acceptance. R66's original
socket failure remains recorded. R65 supplies descriptive small clock HTTP data;
resource bounds and performance budgets are explicitly **deferred to batch C**, with no approved numeric threshold. The
older corpus benchmark remains pending in its capture. See the
[release record](../../../releases/cgm-remote-monitor-16.0.0/contents.md) for programme disposition.

| Earlier overview | Retained evidence |
|---|---|
| [R49–R55 platform checkpoints at the prior revision](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/ed18a7bceb096fc52e155fc5a005106f7e91263d/docs/30-design/platform/next-gen-platform-plan.md#1-where-things-stand) | Native and cumulative campaigns, capacity HOLD and cleanup captures, original replica failure and focused clock repair. Their named reports remain authoritative for those runs. |

## 1. 16.0.0 scope (maintainer, 2026-10-30)

16.0.0 targets **every single-tenant item of this plan**, through the entry bar and in priority order. A
miss rolls to 16.1.0, or to 17.0.0 if it changes a default.
- **The identity work is the core.** It is the substance of the agreement with the Loop maintainers:
  identifier-first on every path, re-sends recognised, the format rules, and one record per identifier.
- **The unique index on `identifier` is in 16.0.0**, behind `WRITE_IDENTIFIER_INDEX=try|require|off|drop`
  (default `try`).
  - Under `try`, boot attempts a partial unique index per collection: records with an `identifier`,
    soft-deleted ones included, built online. If existing duplicates block it, the counts per collection
    (never the values) are logged and shown on the status page, and the server runs without the index.
  - The write rule (ID-Q5) still refuses to create a second record with a stored identifier.
  - `require` refuses to start until the index exists. `off` skips building it but leaves any existing index enforced; `drop` removes the index at boot, then runs as `off`.
  - An operator-run tool reports duplicate groups and resolves them by the P4 pick.
- **Multitenant items may ship dormant, labelled alpha behind explicit `multitenant` configuration, or not ship.**

Feasibility, from the 7 days to 2026-10-30: 53 PRs merged into `dev`, and 14 of this plan's 36 items went
to done. Build speed is not the limit. Time on `dev`, cohort checks and review are, so items land in
priority order and early, and the tag is gated by the bar, not by a date.

## 1a. Priority and merge order (2026-10-29)

Identity moved up on 2026-10-29, because most of the week's defects came from records matched by
different rules on different paths: BF-121's socket gap, BF-209, and the chart split's shared
identity (BF-212, where a re-send can overwrite another record's amount). D-LOOP-ID's three rules are now decided. On 2026-10-30 the maintainer put every single-tenant item into 16.0.0's scope (§1), so identity work goes
through the entry bar before the tag, directly after `write(intent)`; ID-FIRST-MATCH slice 1 started that day.

**Before the 16.0.0 tag**, in this order:

| # | PR | risk | what review should look at |
|---|---|---|---|
| 1 | **merged 2026-10-30 (`cf3d4b8f`)**: #8877, BF-209 + BF-211 (BF-210 withdrawn 2026-10-29) | changes which socket treatment uploads are stored as separate records. That is dosing data, for AndroidAPS 3.4.2.x v1 users and the chart-drag split | the identity rule's equivalence for the exact match (559,872 inputs); the three flipped gate fixtures; the one matrix cell that moves (`treatments × v3 × ws`). Ask an AndroidAPS 3.4.2.x v1 cohort to check carbs and boluses |
| 2 | **merged 2026-10-30 (`991b0654`)**: #8865, one executable and the boot split | every site starts through it, so it carries the release's widest operational change | the image's `nightscout single` start, `npm start`, Heroku/Docker/Azure forms, SIGTERM shutdown. Ask each hosting cohort to check it |
| 2a | **merged 2026-10-30 (`d51c7a60`)**: #8878, BF-212 first part: the chart split stops copying identity fields | low; changes only what the moved half of a chart drag carries | the unit test (red on dev) and the reproduction probe; the re-upload double count remains |
| 3 | **merged 2026-10-30 with #8877 (`cf3d4b8f`)**: BF-211, per-collection cache flush | low; changes only which caches a delete by query empties | the red/green control from `tools/lab/cache-value`; v1 deletes by query and API v3 auto-prune |
| 3a | #8855, Crowdin; head `d3edc390`, returned checks green (2026-11-02) | low | usual translation review and current-base recheck |
| 3c | **merged 2026-10-31 (`2f50d944`)**: #8883 (head `789d5d9d`): BF-219, BF-220, BF-221 (v1 treatment and entry writes) and BF-222 (API v3 autoPrune names what it deletes to the cache); #8879 took it in its `dev` merge (four-file conflict, session -4e) | dosing-relevant reply and announcement fixes | HTTP-level tests red on `dev`; the write-step port reviewed |
| 3d | **merged 2026-10-31 (`37b2280f`)**: #8882 (head `32cd90e6`): hygiene, the development lint popup and drawer resize. The resize handler now registers at the first open (`2737756d`), so loading `browser-utils` without a window no longer throws | display only | browser test red on `dev` |
| 3e | **merged 2026-10-31 (`604de1cb`)**: #8885: BF-223 (a saved API secret the site refuses no longer blocks a valid `?token=` link) and BF-224 (a plain value under the date field means equality, not a 500; the defect dates from 2019); #8879 takes it in its `dev` merge (`2d79d30b`) | low; client sign-in and one query form | BF-224's equality test (`api.date-filter-equality`) |
| 3b | **merged 2026-10-30 (`305a6533`, #8880)**: BF-213, BF-214, BF-217: a missed URGENT pump alarm, a pump-plugin crash that hides every pump alarm, a device-status cache gap; BF-213 alarms at Loop's severity (maintainer, 2026-10-30) | Loop users with pump alerts get new pump alarms | each fix red then green; the release-notes line |
| 4 | BF-72 and BF-161 fork branches | security fixes held outside the public PR list until release ([register](../remedial/nightscout-backfix-register.md)) | brought up to `dev` and merged before the tag |
| 5 | #8824, dev to master | `BLOCKED`; master requires `Run Tests (22, 6)` and `(24, 6)` plus one approving review, read 2026-11-02. The absent 4.4 requirement is removed and both retained lanes are green | finish review and the decided aggregate-check policy; security/final-tree/live/cohort acceptance before tag |

**Eligible for 16.0.0 through an entry bar** (maintainer, 2026-10-29): rows 8 and 9 below, plus the
re-send switch, in that order. Each joins the merge list when its matrix result is as stated, its red
controls and ablations pass, a revert has been rehearsed, and it has had time on `dev` with its cohort
check. Whatever has not cleared the bar at the tag rolls to 16.1.0. 16.0.0 is already a major, so identity
rules that change outcomes may land there instead of 17.0.0.

**Next, through the bar** (2026-10-30: every single-tenant row targets 16.0.0; a miss rolls to 16.1.0, or to 17.0.0 if it changes a default):

| # | work | release | risk | review |
|---|---|---|---|---|
| 6 | **done 2026-10-30** (this repository, `b982fbdd8`): SPEC-ID-AMEND, spec and conformance only | 16.0.0 through the bar | none for sites | case-by-case conformance report |
| 7 | draft #8857, registration S0-S2, S5 | 16.0.0 through the bar | off by default; head `5f6c1275` is behind `dev` `497d08c9` | rebase/resolve, settle D-REG-FLAG (where the catalogue lives), and rerun its gates on current `dev` |
| 8 | **merged 2026-10-31 (`368e6c23`)**: #8874 plus slices 4 and 6, `write(intent)` release 1 | 16.0.0 (at `4f9fc4cd` against dev `991b0654`: 0 of 1,929 cells outside `cache`, merge revert rehearsed). Its cohort check is one window with the identity work, opening when slices 3 and 4 are on `dev` | every write moves, behaviour-neutral by the matrix | G1 at 0 cells; the slice 6 dedupe gate; per-rule ablations; review commit by commit |
| 9 | **#8879 merged** with slices 1, 2, 5, 3, 4, 6 and 6a; **#8890 merged** compatibility A/B and the BF-225 fix; **#8892 merged 2026-11-01** as `3c773ee5`, adding `WRITE_RESEND=replace\|merge-except-treatments\|acknowledge\|refuse` and `WRITE_DELETED_RESEND=stay\|revive`. The default-mode matrix changed 0/4,916 cells relative to its base; `refuse` changed 813. All required #8892 checks passed. | 16.0.0 through the entry bar; #8894 now completes the index-dependent batch retry. | Identity changes affect dosing data and delete/restore behavior. | Full release compatibility matrix, cohort check, and rollback review. |
| 9b | **#8894, ID-UNIQUE-INDEX, merged 2026-11-01** as `497d08c9` (full merge commit `497d08c94c0a583f056fe487d172a4634fc4a1d4`), from head `cf978f4` onto `dev`. All required PR hosted checks passed. The completed `--batch --no-idf` matrix has 3,443 cells per off/try lane, zero invalid cells on MongoDB 5.0.32 and 8.0.34, and the same 33 expected batch differences (24 `batch-dupkey-mid`, 9 `batch-repeat-identifier`) on both versions; other differences are cache-only. #8894 includes batch race retry, so no standalone ID-BATCH branch is currently required. | 16.0.0 through the entry bar; post-merge CI stabilization #8896 is merged and green; release cohort verification remains. | Index creation and duplicate-key races affect every write path. | Complete the release compatibility matrix and prepare cohort/rollback checks for a named RC. |
| 9a | **merged 2026-11-01 (`51d38f9f`)**: #8886 (head `4b8adfec`, CI green; local re-gate against `5376e6a7` showed no difference from the `6b00eb9d` gates): `write(intent)` release 2 (filter writes resolved to ids in the step, API v3 in the same shape, autoPrune through the step, Q-A/Q-U; it fixes BF-226, autoPrune flushing the cache without a reload, which dates from #6688) and, as its last commit, the per-write event (D-EVENT) | 16.0.0 through the bar, after #8879 | the cache path, which feeds what screens and alarms show; one accepted behaviour change (a record inserted while a delete by query runs survives) | client replies and stored records equal to the base on all 36 probe rows; the cache catch-up lab round 3 and the red controls re-run on the pushed head before it leaves draft; GitHub runs its tests once it targets `dev` |
| 10 | **#8875 merged 2026-11-01 (`1fc6d8be`, head `ba69e317`)**: ST-VIEWS (maintainer, 2026-10-30): in 16.0.0 in steps. Replay results measured at `7b4b724c` and re-checked on `dev` `1fc6d8be` after #8886 (0 differing minutes on 126,092 per view, r2 noise floor 0, controls as recorded, one count +10): with the newest treatment read within 60 h and the full resident windows (60 h treatments, 24 h device status), both views equal the resident path on 126,092 replayed minutes each. *Maintainer, 2026-10-31:* ships in 16.0.0 unwired, because `serve` has no role that runs alarms yet (only `api` starts). The wiring moves to the one-tenant computed profile prototype (ST-VIEWS-PROFILE, D-EXEC-PROFILE) and later to the multitenant roles; `single` keeps the resident path | 16.0.0 (unwired) | alarms are safety-relevant | the replay lab's per-dataset table at 0 differing minutes, its break-it controls and noise floor; alarm cohort checks (execution plan §7b) |
| 11 | #8810, AndroidAPS iOS push | 16.0.0 if its review items close, else 16.1.0 | device tokens are readable by read tokens | its four review items, with the author |

Research that informs the order, without being in it: the cache-value lab (BF-211), the cache
catch-up lab (rounds 1–3: release 2 resolves filter writes to ids, and API v3 takes the same write
shape; it found BF-222), and the extended write-contract matrix (QC-MATRIX-IDF), which found BF-212. The maintainer's direction on BF-212: a lossy edit of a controller-claimed record needs a
manual confirmation. Two records already sharing an identifier is a question for the ID-FIRST-MATCH design.

## 2. Why the tracks meet at the write step

Every track changes what happens when a record is written:

| track | what it needs from the write step |
|---|---|
| Identity | a single place that matches a re-sent record on `identifier` first, then on the time key, for v1, v3 and the socket alike |
| Registration | a single place that applies a controller's declared schema to its typed writes, and leaves unregistered writers byte-identical |
| Validation | a single place for #8841's rules, so the socket and the v1 modules are not checked separately |
| Tenancy | a single place that carries the tenant binding, so no path can write without one |

#8854 built that place as a boundary at the driver call, and the storage interface sits above it. Each later slice adds one rule there. Every slice must keep the following:

| must hold | pinned by |
|---|---|
| the `_id` forms: ObjectId, upper- and lower-case hex, UUID, and `UUID_HANDLING` moving a non-hex `_id` to `identifier` | #8854's matrix rows; `tests/identity-matrix.test.js` |
| the API v3 create and deduplication reply (`status`, `identifier`, `isDeduplication`, `lastModified`), and AndroidAPS's string-matched refusal texts | `tests/write-validation.test.js`; the v3 suites |
| Loop's `syncIdentifier` and Trio's `id` stored and returned untouched | write-contract matrix |
| v1 treatment upsert on `created_at` + `eventType` | write-contract matrix |

The forward constraints are two mature backends behind one interface (D2–D4), the closed query operator set as a filter tree (D8), a source label and later a tenant binding on every write, and one commit fact the change feed can carry (D6; D-EVENT decided 2026-10-31: one in-process event per write, named from WriteResult.items[], and the per-database-call event kept as backend instrumentation; delivery between processes is decided with the serve roles; its card in §5). Under #8854's merge conditions, the commit event stays internal and unstable, and the intent layer gets its own name.

## 3. The map

For multitenant status and sequencing, use the
[multitenant delivery dashboard](../tenancy/multitenant-delivery-dashboard.md).
It owns M0-M6 prerequisites, parallel lanes, bounded slices and current
acceptance. The [roadmap](../tenancy/multitenant-delivery-roadmap.md)
retains decisions, limits and detailed execution evidence; this platform
overview intentionally summarizes rather than duplicates those tenancy gates.

<!-- chart: map -->

## 4. The tracks in detail

### 4.1 Storage

Done, in 16.0.0: PR-8854, QC-MATRIX-TT (360 cells), ST-FILTER, ST-READS, ST-WRITES, ST-COUNT-ONEPATH, ST-V3-DECOUPLE, WC-STEP-PATCH (release 1).

| item | builds | needs | check |
|---|---|---|---|
| WC-STEP-PATCH | release 1 merged as #8874 (`368e6c23`, no behaviour change); release 2 merged as #8886 (`51d38f9f`, 2026-11-01), resolves filter writes to ids and gives API v3 the same write shape (Q9, Q-U, Q-A); the reached ids come back in `WriteResult.removed` and `.updated`, and `items[]` stays one slot per input (maintainer, 2026-10-31): `write(intent)` -> WriteResult.items[] above the interface; matching, server dates, the null-removes rule and validation move into it; compare-and-set behind an adapter method | ST-WRITES | [write-contract spec](../tenancy/write-contract-spec-2026-10-07.md) G1 |
| ST-V3-DECOUPLE | merged with #8865 (`991b0654`): API v3 without API v1's modules, the socket and the cache, so `serve api` serves it alone (historical headless-API stage) | ST-WRITES, PLAT-SERVE | `serve api` passes the API v3 suites (634 pass, 0 fail, 108 single-only pending, as reported at `9f7f84f8`); `single` unchanged |
| ST-EVENT | merged with #8886 (`51d38f9f`, 2026-11-01): one internal event per write, `storage-intent-committed`, carrying the write's records (`_id`, identifier, outcome, refusal problems) without document contents; the per-database-call `storage-write-committed` stays as instrumentation | WC-STEP-PATCH, D-EVENT (decided 2026-10-31) | each stored and refused record named once per write |
| ST-HARNESS | **merged 2026-11-01** as #8881 (`f54941b5`, head `993275f3`): backend-selectable harness, backend selection, tenant scope | WC-STEP-PATCH | `NS_TEST_BACKEND` controls |
| ST-VIEWS | **merged 2026-11-01** as #8875 (`1fc6d8be`), not wired in; equal to the resident path on 126,092 replayed minutes per view (re-checked on `1fc6d8be`): computed views from bounded queries, without a resident `ddata`: page, socket `dataUpdate`, plugins, alarms (M4) | ST-READS | each view equal to today's on the corpus fixtures; alarms per the execution plan §7b |
| ST-VIEWS-PROFILE | Published draft #8891 remains `744d1968`; independent local refresh `925c9527` / R43 contains current dev and bounded full/replay acceptance. Explicit single/nonresident launcher computes bounded alarms/properties after admitted physical writes and heartbeat, retaining the last cycle properties; default single stays resident. Logical no-op/refusal admission, full alarm/writer coverage, live stats freshness, quiet-hardware cost and placement remain open. It is not joined into #8898. | ST-VIEWS | [R43](../remedial/rc-16.0.0-integration-record.md#r43---independent-nonresident-profile-refresh-on-925c9527-2026-11-05): actual trigger/timer/freshness and teardown controls; remaining entry bar is explicit |
| ST-PG | Published selected-domain PostgreSQL/RLS API preview; complete admitted backend/import acceptance remains open. Resource bounds are deferred to batch C by decision | ST-HARNESS | actual HTTP/Mongo differentials and source controls; full M1 gates in the delivery dashboard |

The September seam chain is kept as reference for ST-HARNESS, ST-PG and TEN-RESOLVE (commits named on each item); it is not merged as it stands.

### 4.2 Identity

Done, in 16.0.0: DEV-8845, ID-SIMPLE-MATCH. Done in this repository: SPEC-ID-AMEND (2026-10-30).

| item | builds | needs | check |
|---|---|---|---|
| SPEC-ID-AMEND | a conformance case for the mandatory identifier on registered instances; identity I2 and §6 state API v3's refusal of a client `_id` (BF-170) | #8845 | `tools/nsschema` cases |
| ID-FIRST-MATCH | identifier-first on every collection and path | ID-SIMPLE-MATCH, WC-STEP-PATCH (D-LOOP-ID's rules decided 2026-10-29) | write-contract matrix; the re-send table, identity reference §2.7 |
| ID-BATCH | v1 per-item reply behavior and index-dependent duplicate-key retry for batch writes | WC-STEP-PATCH, ID-UNIQUE-INDEX | implemented across #8889 and #8894, including tests in `tests/api.id-batch-replies.test.js` and `tests/api.batch-race-item-level.test.js`; the old local branch is not a separate release-critical PR |
| ID-RESEND-SWITCH | site-level `WRITE_RESEND` and `WRITE_DELETED_RESEND` modes, defaulting to current behavior | ID-FIRST-MATCH and compatibility B | merged as #8892 (`3c773ee5`); local matrix showed 0/4,916 default-mode changes relative to its base; required hosted checks passed |
| ID-UNIQUE-INDEX | partial unique index on `identifier`, per collection (with the tenant under multi); duplicate-key races follow the selected resend mode (Q-IDX), including batch item retry | ID-FIRST-MATCH, ID-RESEND-SWITCH | merged as #8894 at `497d08c9` on `dev`; all required hosted checks passed. Full `--batch --no-idf` matrix: 3,443 cells per off/try lane, zero invalid cells, same 33 expected batch differences on MongoDB 5.0.32/8.0.34; remaining differences are cache-only. |

Rules in force (maintainer, 2026-10-26 and 2026-10-27; updated 2026-10-31):

- **Null removes.** An explicit null removes a field on a merged re-send (`WRITE_RESEND=merge`), API v3 PATCH and the socket's `dbUpdate` (RFC 7386; [write contract §6.1](../tenancy/write-contract-spec-2026-10-07.md#61-decided-2026-10-12)). It never does so on PUT or create, and devicestatus never merges.
- **Fallback.** A v1 entries re-send whose identifier matches nothing still matches on `sysTime`+`type`; treatments never fall back. A devicestatus re-send whose identifier is stored replaces the stored record by default (compatibility B, 2026-10-31; it merged from ID-Q2, 2026-10-29); `WRITE_RESEND=merge` keeps that, and `WRITE_RESEND=acknowledge` the rule before it (write nothing, answer with the stored `_id`).
- **Absent identifier.** `identifier` is SHOULD for legacy writers, and the time-key fallback stays. It is MUST for registered controller instances. Revisited as adoption grows.
- **Scope.** Uniqueness is per collection, with the tenant in the key under multi. Values stay globally unique by convention.
- **Re-send after delete.** It is acknowledged with a 2xx naming the stored, deleted record, and the record stays deleted. `WRITE_DELETED_RESEND=revive` (default `stay`, 2026-10-31) restores 15.0.9's re-send that revives a deleted record.
- **Format (2026-10-29, D-LOOP-ID rule 1 and ID-Q6).** Any string of 1 to 256 characters, with no character restriction, percent-encoded in a URL path; a UUID is recommended. A placeholder or over-length value is treated as absent with a warning; refusing it is `WRITE_IDENTIFIER=strict`, off by default. *2026-10-31 (compatibility A):* API v3 refuses a malformed identifier with 400 by default, as 15.0.9 did; API v1, the socket and in-process stay lenient. Which placeholders are named is open (ID-PLACEHOLDER-LIST, [identity specification](spec/identity.md) §5).
- **`_id` (2026-10-29).** A client may still send an ObjectId `_id` over API v1 (legacy). Going forward the server sets `_id` and the client sets `identifier`.
- **Replace on match (2026-10-31, compatibility B; supersedes merge on match of 2026-10-29).** A re-send matching a
  stored record replaces it on every collection, as slice 4 does for treatments. *Extended the same evening:* every
  re-send matched by identifier replaces on every path, including the identifier-first matches for profile, food,
  activity and device status over v1, in-process and the socket; entries over v1 and in-process keep merging, as
  on 15.0.9. Merge stays for edits: API v3 `PATCH` and the socket's `dbUpdate`. `WRITE_RESEND=replace|merge|acknowledge|refuse` (default `replace`) and
  `WRITE_DELETED_RESEND=stay|revive` (default `stay`) are built before the tag as opt-in ways back, parsed with the
  other `WRITE_*` settings; per-client D20 quirks may select a `WRITE_RESEND` mode. Each path that changes is
  listed cell by cell.
- **Re-send after delete, every path (2026-10-29).** "Acknowledged, stays deleted" applies on every path, and
  the spec text is corrected. Every changed cell is documented, so the change can be reverted or adjusted
  as cohort feedback arrives.
- **Records without an identifier.** Natural keys for device status and profile are a separate item,
  ID-NATURAL-KEY, with its own corpus check of what would merge. Food and activity have no natural key.
- **Socket edits and removes, and activity.** Identifier addressing is added where it changes nothing for
  writes that carry no `identifier`: socket `dbUpdate`, `dbUpdateUnset` and `dbRemove` accept an
  `identifier` when there is no `_id`, and activity creates match on `identifier`. This is conditional on
  the extended matrix showing every existing form unchanged.
- **Re-send with changed fields (2026-10-29).** Merge on match stays the default, because Loop and Trio re-send changed doses, overrides and temp targets by `POST` ([client survey](../../60-research/tenancy/identity-resend-survey-2026-10-29.md)). API v3 keeps refusing a changed date, device or event type, and `PUT` replaces. A site setting plus per-client quirks (D20) may opt a client into keep-first or refuse. A default changes only in a major: 16.0.0 if it clears the entry bar (§1a), otherwise 17.0.0.

The rules are in the [identity specification](spec/identity.md) and the [identifier conventions](identifier-conventions.md); the conversation with the Loop maintainers is in [upstream-asks-loop-identifier](upstream-asks-loop-identifier/README.md).

### 4.3 Registration

| slice | builds | needs | check |
|---|---|---|---|
| REG-S0 | capability document and catalogue, read-only, flag off by default | specs | schema validation; flag off is byte-identical to dev |
| REG-S1 | submit, etag, retire; MongoDB store; single mode | REG-S0 | negotiation conformance cases against a booted server (25 of 32 pass, 6 mapped, 1 not applicable) |
| REG-S2 | definitions, leased instances, channels and roles; instances on one flat root, `/api/v4/instances/{instanceId}` | REG-S1 | instance conformance cases |
| REG-S5 | owner actions on a single-tenant site with `API_SECRET` | REG-S1, REG-S2 | owner-action conformance cases |
| REG-S3 | typed writes and read selection | REG-S2, WC-STEP-PATCH, SPEC-ID-AMEND | unregistered writers byte-identical |
| REG-S4 | projected views for older readers | REG-S3 | projection cases |
| HUB-REG-CRM-SEAM | registrations under tenant scope | REG-S2, ST-PG, T30-WIRING | per-mode cases (SPEC-REG-MODES) |

S0, S1, S2 and S5 need no storage work and are one single-tenant PR, draft [#8857](https://github.com/nightscout/cgm-remote-monitor/pull/8857) (`f7a43fed`). S5 comes before S3 because only S3 waits on the write step. #8857 lets a `devicestatus-upload` token register its controller; that role choice is the maintainer's, in the PR. It keeps one holder document per (scope, channel, role), so each role has one live instance. Of the 186 conformance cases, 35 pass, 88 are mapped and 0 fail (at `3be98536`); the rest wait for later slices. The [hub implementer's guide](guides/hub-implementer.md) maps each slice to modules on dev; the [controller guide](guides/new-controller.md) is the same flow from the controller author's side.

### 4.4 Tenancy

The dependency map shows selected work items and their bounded component state.
Its blocked markers preserve unmet acceptance prerequisites even where a useful
preview already passes. The [M0–M6 dashboard](../tenancy/multitenant-delivery-dashboard.md)
is authoritative for milestone gates; accepted slices are not completion percentages.
The adopted M2 bar is tenant-local config/versioned writes, unknown-tenant refusal,
A's token failing on B by signature, no environment/root/key leakage, and separate
owner/data/operator routes. Versioned-write re-execution and comprehensive
listener-separation acceptance remain pending. M4's bar is executed headless clients
plus source-pattern replay for the rest, with **no all-client claim**; Android
emulator work moves to C and iOS is outside the automated lab. M4 still depends on M3.
The [promotion decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06)
own these scope changes. Headless owner `config.ownerPolicy` is retained writer
policy, distinct from the withdrawn authorization reader option.

The [architecture and compatibility comparison](../tenancy/single-and-multitenant-architecture.md)
contains request-flow, isolation and historical-comparison diagrams.

| item | builds | needs |
|---|---|---|
| PLAT-ENTRY | one executable, `bin/nightscout.js`: `single` (today's server, every old start path unchanged) and the operator tools; image ENTRYPOINT, and no image HEALTHCHECK so a boot-error page is not restarted away (D21) | dev |
| PLAT-SERVE | Merged `multitenant` CLI namespace (#8899); explicit API preview on draft #8898, with separate operator preparation/readiness. Other roles remain unenabled | PLAT-ENTRY, ST-READS |
| T30-RESEARCH | the tenant-owner configuration surface: 264 settings on dev, 12 contested | D-T30 |
| T30-SCHEMA-CONFIG | Adopted owner-authority writer policy and transactional proposed-grant fencing are retained. Reader clamping is removed; R72 accepts M2 tenant-local config/versioned writes and route separation; wider lifecycle belongs to M6. Selected preview services do not finish this item; historical old-seam gate fails its D15 predicate | T30-RESEARCH |
| TEN-RESOLVE | Direct/canonical preview resolution accepted; full production trust, durable mapping and operator lifecycle still blocked | MT-CONFIG-MIN, MIG-RUNNER, PLAT-SERVE |
| T30-WIRING | Current persisted authority composes with actual CLI/REST. Adopted local new-format token verification keeps per-operation PG session/key/grants; writer proposed-grant fencing is retained; optional reader clamping is withdrawn. Management issuer/refresh, existing-grant lifecycle policy and production trust are M6 work | TEN-RESOLVE, MT-SECRETS-CONTRACT |
| TEN-LAB | R72 promotes M3 after M1/M2, then M4 at the adopted headless/source-pattern scope; no all-client or M6 claim | ST-PG, T30-WIRING, MIG-RUNNER |

Single-tenant on MongoDB stays first-class (D1, D4). The subcommand selects tenancy (maintainer, 2026-10-27): `nightscout single` is single-tenant and the `nightscout multitenant` namespace selects multitenancy (#8899), so the API preview requires explicit multitenant configuration and `TENANCY_MODE` retires as an operator setting. Which listener and role owns each API is mapped in [interface ownership](interface-ownership-2026-10-27.md), with its eight open questions (among them whether serving every role in one process is part of the multi target). The settings census on dev is [t30-census-dev](../../60-research/tenancy/t30-census-dev-2026-10-27.md). The decisions D1–D23 are in the [execution plan](../tenancy/multitenancy-decisions.md).

Tenancy and execution are separate axes (D-EXEC-PROFILE, 2026-10-31). The subcommand selects tenancy; whether a site keeps a resident `ddata` or computes its views from bounded queries is a second choice. The current preview uses request-local loader/cache frames; it does not enable multitenant evaluator/realtime or establish a universal computed execution profile. The independent single/nonresident prototype retains properties between cycles; R50 now measures acquisition races, failed-cycle retention and recovery through actual triggers. R49/R50 retain the measured differences in bounds, frame/future behavior, identity unions, statistics and failure lifecycle. Cost remains unmeasured and default single remains resident. R54/R55 accept a shared private allocation helper behind those separate caller policies. R62/R64 retain the published REST side. The whole independent profile branch remains separate; a private helper/evaluateCycle hunk is reused in the local joined candidate. R67 bounds recovered clinical constructor evidence. No common atomic revision, live profile/evaluator role or notification handoff is accepted.

## 5. Open decisions

Select **Show on the map** on a card to see which items it holds up. Release questions (the 16.0.0 quiet period, cohort requests, when dev reopens) are Q13–Q16 in the [release allocation](release-allocation-2026-10-27.md#5-open-decisions).

<!-- chart: decisions -->

## 6. How the work moves

- **Pull requests.** Sized by milestone, not by slice: the single-tenant registration PR (S0, S1, S2, S5); storage slices grouped into few PRs. A track with many pieces in flight uses an integration branch with child PRs, the way #8605 carried 109 children. Dev is merged into a branch, not rebased, and a PR's merge records that the merged tree matches the reviewed tree.
- **What pins behaviour.** #8854's CRUD matrix and this repository's write-contract matrix (`tools/qc/write-contract-matrix.js`; v1, v3, socket and in-process). A slice that changes no behaviour changes no cell; a slice that changes behaviour lists the cells it changes and why.
- **Red controls.** Every new test is shown failing against the code it guards before the change, with the original symptom.
- **Conformance.** The registration and identity cases in `specs/sync/conformance/` run against a booted server by a harness in this repository (D12), reported case by case as passed, mapped or not applicable.
- **Agents.** Agents build slices in their own worktrees, run the checks and hand back a branch, a PR body and the push commands. They never push. Maintainers push, open, review and merge.
- **Releases.** #8865 (one executable, the image's start and stop, the boot split; `multitenant` is the current namespace after #8899; only the explicitly configured API preview is implemented in #8898) merged into 16.0.0 on 2026-10-30. Since 2026-10-30 every single-tenant item of this plan targets 16.0.0 through the entry bar (§1); a miss merges after the tag, one theme per minor; the 16.0.0 quiet period starts when its merge list is closed, not on a date. Components shipped before they are mature are labelled alpha; the label belongs to the multitenant bindings, not to code every single-tenant site runs.
- **Records.** Each landed slice updates its queue item (`queue/work-queue.yaml`) and this plan's data file, and the page is re-rendered.

## 7. Sources

- cgm-remote-monitor dev `604de1cb`; open PR heads, CI and `dev` distance read with `gh pr list`, `gh pr checks` and `gh api .../compare` on 2026-10-31 (re-read about 22:00Z). The test workflow runs only on pull requests to `dev` or `master`, so #8886 (base `feat/id-first-match`) shows only `auto-close` until it is retargeted.
- [Storage seam interface](../tenancy/nightscout-storage-seam-interface-2026-09-14.md), [write-contract spec](../tenancy/write-contract-spec-2026-10-07.md), [execution plan](../tenancy/multitenancy-decisions.md), [#8854 alignment brief](../modernization/pr-8854-alignment-2026-10-26.md).
- [Registration specification](spec/registration.md), [identity specification](spec/identity.md), [records specification](spec/records.md).
- Nocturne `970031f6`, re-checked at `36d5ef4a2`. Tenant scope is an `ITenantScoped` marker with row-level security. It keeps a sync key (tenant, data source, sync identifier) and a single record-changed seam proposed in its issue #2130. Its API v3 serves `identifier` equal to `_id` (issue #1932).
- Controllers, read at AndroidAPS dev `325e5623`, NightscoutKit `6efa02d4`, Trio dev `7ff1f777e`, xDrip+ `c42cf55c`. AndroidAPS is the only API v3 client and keeps the server's `identifier`. Loop sends `syncIdentifier`, and Trio sends `id`.
