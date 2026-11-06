# Multitenant integration batching plan

*Contributor-facing execution plan, 2026-11-06, living. It says how work on the
multitenant preview is batched, what verification runs at each stage, and which
batches sit on the critical path to the M3 and M4 gates. Item states, gates and
blockers live in [the work queue](../../../queue/work-queue.yaml); acceptance
evidence lives in the [integration record](../remedial/rc-16.0.0-integration-record.md)
and the [working dashboard](multitenant-delivery-dashboard.md). This plan
supplements the [REST delivery roadmap](multitenant-delivery-roadmap-2026-11-02.md)
and the [architecture seams plan](architecture-seams-execution-plan-2026-11-05.md)
without changing release placement or promoting M0–M6.*

## 1. Measured basis

Read from tool output on 2026-11-06. Counts are not additive and are not
completion percentages.

| Anchor or measure | Value |
|---|---|
| Alignment main at last refresh | `c57589e9b553af0dafdcce49d96b3ad4b448a30c` (R55 and the focused clock recovery records published; R54 at `60776e08`) |
| Accepted cumulative head | `35903069b46974cfbaddd8dce00c994fb2562bc3`, branch `codex/serial-integration-20261106` |
| Published draft #8898 head | `35903069` since 2026-11-06 18:14 UTC, body refreshed from R54 by the maintainer; earlier in the day it was `1c55098a` (R49), 19 commits behind |
| Upstream `official/dev` | `4a482627bfdafb1fef8dcbe0ac6c484811cae563`, contained in the cumulative head |
| Cumulative head versus dev | 120 commits; 216 files, of which 166 new and 50 modified |
| Largest modification to an existing shipping file | 33 lines (`lib/api/treatments/index.js`) |
| R54 campaign | full 7,144 passing / 80 pending / 0 failing; browser 684 / 0 / 0; settings 12; prcheck OK |
| R54 campaign wall clock | nonbrowser about 5.5 min (tiers 58 s, 7 s, 10 s, 0.8 s, 5 s, 4 min, 1 s); browser 4 min; prcheck about 1 min |
| #8898 CI at read-back of `1c55098a` | 15 checks green, draft, mergeable; 3 review events, all CodeQL comments; 0 human reviews. CI on `35903069` is UNMEASURED by this plan |
| CI coverage of the preview | none: every PostgreSQL and Vault suite is opt-in by environment flag, so the PR's green CI measures Mongo single-site regression only |

Three facts shape the rules below.

- **The regression surface on shipping code is narrow.** The preview is mostly
  new, opt-in, dormant modules; the modified existing files are small hooks in
  the v1 and API3 handlers. A leaf commit that adds opt-in code does not need the
  full Mongo suite.
- **The campaign is cheap; the serialized slot is not.** One full plus browser
  plus prcheck costs about ten minutes of machine time. R51, R52 and R53 each ran a
  native full campaign and R54 ran a fourth on the composition, serialized through
  one runtime slot, with more than eighty lane handoffs written in four days.
- **The queue's multitenant gates are instruments that skip without a database.**
  `tools/queue/gates/multitenant-next-slices.js --suite <name> --ref <sha>` and
  its siblings replay archived suites against a pinned head. `make queue-status`
  reports them UNMEASURED when run without `NS_TEST_POSTGRES_ADMIN_URI`; that is
  the measuring environment, not a missing instrument.

## 2. Acceptance ladder and what runs at each stage

The dashboard's ladder is **locally accepted → incorporated → integrated
acceptance recorded → milestone promoted**. Verification depth follows the stage,
not the lane's nerves.

| Stage | Claim | What runs | Who records |
|---|---|---|---|
| Locally accepted | this lane's change does what it says on its own head | lint on changed JS; `npm run test:affected`; the lane's focused suites; every authored break-it control, red then restored | the lane, in its handoff |
| Incorporated | the change is an ancestor of the frozen batch head | ancestry check; affected suites on the combined tree; tier registry check | the coordinator |
| Integrated acceptance recorded | the frozen batch head regresses nothing | **one** full nonbrowser, **one** default browser, final `prcheck.sh`; the queue gates for the batch's items run with a database against the frozen head | the coordinator, as one R entry |
| Milestone promoted | a roadmap section 4 criterion list is fully met | the milestone's own list; controls rerun on the cumulative tree; client-binary replay where the milestone claims client compatibility; benchmark where it claims capacity | maintainer decision, recorded in the roadmap and dashboard |

A batch does not repeat lower-stage work for its members. A fresh agent resuming a
lane does not rerun an accepted campaign.

## 3. Batch rules

1. **Theme batches by milestone, three to six lanes each, one frozen head per
   batch.** Each lane joins by rebase or merge onto the current cumulative head;
   the coordinator freezes one head, runs the stage-three campaign once, and
   publishes that head to #8898 once. Target cadence: one batch per working day.
2. **Triggers that force a full campaign before the batch closes.** Any change
   to: an existing shipping file under `lib/api`, `lib/api3`, `lib/server`,
   `lib/storage` or `lib/data`; `tests/tiers.json`; `package.json` or the lock;
   a migration; a fixture another lane shares; or any red result that is not a
   declared control. New opt-in files alone never trigger one.
3. **The runtime slot serializes full and browser campaigns only.** Focused
   suites own their random ports, schemas and containers and may overlap, after
   checking free disk and the inotify watch budget, both of which caused the
   November 5 ENOSPC holds. Capacity for overlap is unmeasured; the coordinator
   decides and records the check.
4. **One command for the preview's own corpus.** Measured by B5: 31 opt-in
   suites, all in the integration tier, gated by 23 flag variables plus the bare
   PostgreSQL admin URI; 18 start at least one container of their own, and 15
   also open a real MongoDB client. `npm run test:multitenant` provisions one
   disposable PostgreSQL 16, one MongoDB 8.0 where a selected suite needs it and
   one Vault dev server where needed, then runs every opt-in suite with
   `--fail-zero`, so the corpus is one tier for the local slot and for CI.
5. **CI runs the corpus.** A PostgreSQL plus Vault job on #8898 moves the
   stage-three campaign off the single local slot. The roadmap's section 4 already
   calls for explicit PG jobs as applicable suites execute.
6. **Queue gates measure the batch head.** After a batch's campaign passes,
   move each member item's `--ref` to the frozen batch head and run
   `make queue-status` with the admin URI set, inside the slot. Native refs stay
   in the R record as history.
7. **Fuller V&V is a batch property.** Escalate to stage four work only when a
   batch claims a milestone gate, touches shared code beyond rule 2, or fails its
   own controls. Never because a session resumed.
8. **Every brief carries the standing instructions.** Confirm the head commit
   and that the task is still open before starting; stop and report a mismatch
   rather than reaching for the nearest thing that works. Agents never push.

## 4. Critical-path batches

Ordered. Each names its owner, inputs, gate and predicted result. B1 is a
maintainer action; B2 and B3 are owned by active lanes; B4 through B7 are
dispatched by the coordinating session that wrote this plan.

| Batch | Owner | Inputs | Gate and predicted result |
|---|---|---|---|
| **B1: publish the accepted head** | maintainer | cumulative `35903069` | **Done 2026-11-06:** #8898 head is `35903069`, body refreshed from R54. Remaining: read back CI and CodeQL on that head and record the result; no PG suite executes in CI until B5 lands. |
| **B2: clock batch → next R number** | lane D (HTTP, done), root compatibility (lower port), coordinator (join) | D head `3532c1a4` with product fix `11770146`; lower-port fixture `887c4aad`; cumulative `35903069` | **Focused HTTP part done** (tenant-clock-http-fixed-recovery report: functional 7 / 1 pending / 0 failing; listener-removal control 0 / 2 with ECONNRESET and worker exit 1; restored 1 / 0). Remaining: lower-port eight cases on `887c4aad`; freeze clock plus connection repair on 359; one full/browser/prcheck; serialization, readiness and rollback source ablations that the focused slot did not run. Predicted: full passing count rises by the new cases, 0 failing; opt-in default off; contention and latency stay UNMEASURED until the opt-in benchmark runs in the slot. |
| **B3: profile 2ee acceptance** | lane A (done), maintainer (publish) | independent head `2ee8b493` | **Recorded as R55:** full 6,690 / 3 / 0, browser 684, archived 38 with three semantic controls red and restored, final prcheck OK. Remaining: publish `2ee8b493` to #8891, whose head at read-back is in the row below this table. No join to #8898. |
| **B4: milestone promotion review M0–M3** | coordinator subagent, read-only | roadmap section 4; R24–R55 | **Done:** [milestone promotion review](milestone-promotion-review-2026-11-06.md). Rows measured / partial / unmeasured: M0 5/3/0, M1 5/5/1, M2 4/2/4, M3 4/2/1. Top blocker for M3 is that no negative control has been re-run on the cumulative head `35903069` (R24 and R54 both say so); the cheapest closure is rule 6 applied once: run every registered `multitenant-next-slices.js` suite with its `--control` variants against `35903069` in the next slot. Predicted: every control red with its recorded symptom, every positive green. |
| **B4a: controls on the cumulative head** | root coordinator, next runtime slot | the registered archived suites and their `--control` variants; `35903069` | queue gates for every multitenant item run against `35903069` with the admin URI set, positives and controls, recorded as one R entry; item `--ref` values then move to `35903069`. Predicted: all positives green, every control red with its recorded symptom. A green control is a vacuous gate, not a pass. |
| **B5: corpus command and CI job** | coordinator subagent, lane `codex/multitenant-ci-20261106` off 359, head `f2be3afa` (three commits, four files, no `lib/`, no test or fixture change) | the 31 opt-in suites; `scripts/test-tiers.js`; `.github/workflows/main.yml` | **Built and controlled, corpus run UNMEASURED.** `scripts/test-multitenant.js` with `--list`, `--only`, `--record`; inventory page `docs/multitenant-test-corpus.md`. Smoke on the PostgreSQL connection suite: 10 / 0 / 0, container and volume verified absent. Controls: unreachable admin URI exit 2 with nothing run; no matching suite exit 2; one flipped assertion exit 1 with 1 failing. CI job `multitenant-postgres` on ubuntu-22.04 added to the `tests-pass` needs. **Before this lane is pushed:** run the whole corpus once in a batch slot and record its counts, or hold the job out of `needs` until that run exists; the inventory guard's red control is pending. |
| **B6: M4 client-binary lab packet** | coordinator subagent, read-derived | `tools/qc/compat`, the journey lab, pinned client inventory | **Done:** [M4 client-binary lab packet](m4-client-binary-lab-packet-2026-11-06.md). Headless on Linux without a vendor cloud: nightscout-connect, oref0, cgmsim-lib; the mobile clients need an emulator or Apple platforms and are out of the automated lab. Credential finding at `35903069`: SHA-1 header and exchange-Bearer clients fit v1 and v3; query-token clients fit v1/v2 only and are refused on the API3 bridge; no pinned client emits new-format tokens. The lab needs its own queue item, allocated when dispatched. |
| **B7: M5 design acceptance** | MT-RUNTIME-PLAN owner (draft by coordinator subagent) | D-EVENT, D6 feed design, clock reports | **Drafted for maintainer review:** [durable event delivery contract](durable-event-delivery-contract-2026-11-06.md), eleven decisions and a nine-control entry bar, all UNMEASURED. Two consequences for sequencing: the contract applies only where the commit-coupled stamp exists, so the clock join (B2) precedes the first recovery slice; and the committed event at `35903069` carries neither tenant nor stamp (`lib/storage/write-intent.js:4656-4678`), so a payload slice follows B2 as its own lane and is not folded into the join. |

Draft #8891 head at read-back on 2026-11-06 is `dff9a8d4` (R45), so the R55
head `2ee8b493` is not yet published; that is a maintainer push, not a lane task.

Order of dependence: B1 and B3 are done except for publication read-backs. B2
feeds B7. B4 tells the maintainer which milestone can be promoted first; it does
not block B5 or B6. B5 removes the slot bottleneck for every later batch, so it
is started now rather than after B2.

## 5. Lane ownership and coordination

- The **root coordinator** owns the cumulative application branch, the queue,
  release records, dashboard and map edits, and the single runtime slot.
- **Lane handoffs** are `externals/work/HANDOFF-<lane>-<date>.md`, local and
  untracked. The coordinating session's own notes are in
  `externals/work/HANDOFF-batching-coordinator-20261106.md`.
- **Publication** of alignment records follows the standing authorization for
  reviewed record-keeping commits, by pinned fast-forward only. Application
  pushes and PR edits remain the maintainer's.
- The two untracked November 2 draft files in this directory belong to a peer
  session and are never staged by anyone else.
- Several sessions share one git index: check `git diff --cached --name-only`
  and commit by path.

## 6. What this plan does not do

It promotes no milestone, selects no backend or provider, enables no listener
or default, and adds no release gate for 16.0.0. It does not weaken the
full-suite-before-ready contract: the full campaign still runs before any batch
head is called ready. It changes where and how often that campaign runs.
