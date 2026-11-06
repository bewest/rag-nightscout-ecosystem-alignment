# Multitenant integration batching plan

*Contributor-facing execution plan, 2026-11-06, living. It says how work on the
multitenant preview is batched, what verification runs at each stage, and which
completion batches cover M0–M6 and where an early proof is still required.
Item states, gates and
blockers live in [the work queue](../../../queue/work-queue.yaml); acceptance
evidence lives in the [integration record](../remedial/rc-16.0.0-integration-record.md)
and the [working dashboard](multitenant-delivery-dashboard.md). This plan
supplements the [REST delivery roadmap](multitenant-delivery-roadmap-2026-11-02.md)
and the [architecture seams plan](architecture-seams-execution-plan-2026-11-05.md)
without changing release placement or promoting M0–M6.*

<a id="1-measured-basis"></a>
## 1. Historical measured basis

The following capture is the basis of the original B1–B7 dispatch, not a live
branch or CI status. Later evidence remains in its dated integration records.
Counts are not additive and are not completion percentages.

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
| Integrated acceptance recorded | the frozen batch head regresses nothing | **one** full nonbrowser, **one** default browser, the enabled multitenant corpus and batch labs, final `prcheck.sh`; applicable queue positives and paired breaks run against the frozen head | the coordinator, as one R entry |
| Milestone promoted | a roadmap section 4 criterion list is fully met | the milestone's own list; controls rerun on the cumulative tree; client-binary replay where the milestone claims client compatibility; benchmark where it claims capacity | maintainer decision, recorded in the roadmap and dashboard |

A batch does not repeat lower-stage work for its members. A fresh agent resuming a
lane does not rerun an accepted campaign.

## 3. Batch rules

1. **Batch toward completion, with one frozen candidate per completion stage.**
   The A–C schedule below governs current work. Parallel lanes join through an
   owned integration branch; do not rewrite shared published history. The
   coordinator records one comprehensive acceptance campaign per candidate.
   Publication remains the maintainer's action; agents never push.
2. **Triggers that require a full campaign on the final candidate.** Any change
   to: an existing shipping file under `lib/api`, `lib/api3`, `lib/server`,
   `lib/storage` or `lib/data`; `tests/tiers.json`; `package.json` or the lock;
   a migration; a fixture another lane shares; or any red result that is not a
   declared control. These changes do not require one full campaign per member
   slice. After a failure, run focused regression/controls during repair; a
   material source, migration, dependency or shared-fixture change invalidates
   final acceptance and requires the full campaign on the replacement head.
   New opt-in files alone never trigger a separate native full campaign.
3. **The local runtime slot serializes full, browser and whole-corpus campaigns.** Focused
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
   These counts describe the original B5 capture; every later batch reconciles
   the source inventory before freezing, including joined clock suites.
   An explicitly disabled benchmark stays named pending, never a functional pass.
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

<a id="4-critical-path-batches"></a>
## 4. Historical B1–B7 dispatch

Retained as the original dispatch and evidence history. The completion schedule
below supersedes its slice-by-slice next-action sequencing, not its captures.
Each names its owner, inputs, gate and predicted result. B1 is a
maintainer action; B2 and B3 are owned by active lanes; B4 through B7 are
dispatched by the coordinating session that wrote this plan.

| Batch | Owner | Inputs | Gate and predicted result |
|---|---|---|---|
| **B1: publish the accepted head** | maintainer | cumulative `35903069` | **Done 2026-11-06:** #8898 head is `35903069`, body refreshed from R54. Remaining: read back CI and CodeQL on that head and record the result; no PG suite executes in CI until B5 lands. |
| **B2: clock batch → R56** | peer session (join, done), coordinator (publication) | R54 `35903069` + clock lane `11770146` + clock HTTP lane `3532c1a4` | **Done, recorded as R56** on frozen join head `65bb8456`, local and unpushed: clock mode 28 / 1 pending (benchmark opt-in) / 0; full 7,187 / 81 / 0; browser 684 / 0 / 0; prcheck OK. Three ablations red and restored: serialization 0/3, readiness 0/2, rollback 0/3. Passing rises by 43 over R54, five of them test-only cases of the unaccepted replica candidate `714f6c8b` that the HTTP fixture requires. Remaining: the opt-in benchmark, Mongo comparison, mixed writers, bulk ties and SIGKILL cleanup bound stay UNMEASURED; six pre-existing lint errors in the clock HTTP lane's test files; publication of `65bb8456` to #8898 is the maintainer's. |
| **B3: profile 2ee acceptance** | lane A (done), maintainer (publish) | independent head `2ee8b493` | **Recorded as R55:** full 6,690 / 3 / 0, browser 684, archived 38 with three semantic controls red and restored, final prcheck OK. Remaining: publish `2ee8b493` to #8891, whose head at read-back is in the row below this table. No join to #8898. |
| **B4: milestone promotion review M0–M3** | coordinator subagent, read-only | roadmap section 4; R24–R55 | **Done:** [milestone promotion review](milestone-promotion-review-2026-11-06.md). Rows measured / partial / unmeasured: M0 5/3/0, M1 5/5/1, M2 4/2/4, M3 4/2/1. Top blocker for M3 is that no negative control has been re-run on the cumulative head `35903069` (R24 and R54 both say so); the cheapest closure is rule 6 applied once: run every registered `multitenant-next-slices.js` suite with its `--control` variants against `35903069` in the next slot. Predicted: every control red with its recorded symptom, every positive green. |
| **B4a: controls on the cumulative head** | session `-8c` (maintainer-assigned 2026-11-06, after the Codex root coordinator did not claim it); the `--ref` moves stay root's | the registered archived suites and their `--control` variants; the current frozen head, `65bb8456` since R56 | queue gates for every multitenant item run against the frozen head with the admin URI set, positives and controls, recorded as one R entry; item `--ref` values then move to that head. Predicted: all positives green, every control red with its recorded symptom. A green control is a vacuous gate, not a pass. |
| **B5: corpus command and CI job** | coordinator subagent, lane `codex/multitenant-ci-20261106` off 359, head `b7eac9bb` (four commits: the three build commits plus one fix; no `lib/` change; one opt-in test expectation changed) | the 31 opt-in suites; `scripts/test-tiers.js`; `.github/workflows/main.yml` | **Corpus measured once on `f2be3afa` (session -38, slot 19:09–19:19 UTC): 418 passing / 0 pending / 2 failing, wall clock 3:22, the script's own three containers and volumes verified absent.** Both failures reproduced in isolation and are fixed in `b7eac9bb` with controls: (1) `tests/tenant-rest-device-activity.integration.test.js` failed only outside UTC (the script inherited the machine zone; CI and the owned runner force `TZ=UTC`); the command now sets `TZ=UTC` (pre-fix under PST 12 / 1, fixed 13 / 0). (2) `tests/tenant-authorization-postgres.integration.test.js` listed the pending migrations by name and went stale when the candidate gained `0004_owner_policy_fencing` on 2026-11-05; the owned runner never sets that suite's flag, so R51–R54 never ran it and the corpus is the first instrument to do so; the expectation now reads the catalogue (stale 7 / 1, fixed 8 / 0). **Confirming run on `b7eac9bb` (slot 19:22–19:26 UTC): 420 passing / 0 pending / 0 failing in 3:19, prediction met, 31 suites, containers and volumes of the script verified absent.** B5 is complete as a lane: it joins the cumulative head at the next batch boundary, and the `multitenant-postgres` CI job then runs for the first time on the join head. **Open finding (not fixed here):** suite-owned containers are removed without `-v`, so the corpus run left 39 anonymous Docker volumes and the isolated reruns 3 more; the script's own volumes are verified absent. A follow-on lane adds `-v` to the suites' own `docker rm` calls; the finding is attributable only by running suites one at a time. |
| **B6: M4 client-binary lab packet** | coordinator subagent, read-derived | `tools/qc/compat`, the journey lab, pinned client inventory | **Done:** [M4 client-binary lab packet](m4-client-binary-lab-packet-2026-11-06.md). Headless on Linux without a vendor cloud: nightscout-connect, oref0, cgmsim-lib; the mobile clients need an emulator or Apple platforms and are out of the automated lab. Credential finding at `35903069`: SHA-1 header and exchange-Bearer clients fit v1 and v3; query-token clients fit v1/v2 only and are refused on the API3 bridge; no pinned client emits new-format tokens. The lab needs its own queue item, allocated when dispatched. |
| **B7: M5 design acceptance** | MT-RUNTIME-PLAN owner (draft by coordinator subagent) | D-EVENT, D6 feed design, clock reports | **Drafted for maintainer review:** [durable event delivery contract](durable-event-delivery-contract-2026-11-06.md), eleven decisions and a nine-control entry bar, all UNMEASURED. Two consequences for sequencing: the contract applies only where the commit-coupled stamp exists, so the clock join (B2) precedes the first recovery slice; and the committed event at `35903069` carries neither tenant nor stamp (`lib/storage/write-intent.js:4656-4678`), so a payload slice follows B2 as its own lane and is not folded into the join. D23 (adopted and amended 2026-11-06) settles the ack path the contract left open: `realtime` is a reader and forwards every socket write and the alarm ack unchanged to an internal write endpoint on `api`, which writes with the `socket` source label; no client changes. Its entry condition 2, a replay of the pinned AndroidAPS 3.4.2.3 NSClient v1 socket upload sequence, is homed in the M4 packet. |

Draft #8891 head at read-back on 2026-11-06 is `dff9a8d4` (R45), so the R55
head `2ee8b493` is not yet published; that is a maintainer push, not a lane task.

Order of dependence: B1, B2 and B3 are done; B2's join head awaits publication.
B2 fed B7, whose first recovery slice can now be scheduled against `65bb8456`. B4 tells the maintainer which milestone can be promoted first; it does
not block B5 or B6. B5 removes the slot bottleneck for every later batch, so it
was started before B2 finished; its corpus ran once (418 / 0 / 2), both failures were fixed with controls, and the
confirming run on `b7eac9bb` measured 420 / 0 / 0; the lane waits only for the next join into #8898.

## 5. Current completion schedule (adopted 2026-11-06)

The maintainer approved larger implementation batches followed by comprehensive
labs and V&V, retaining targeted tests during implementation and small proofs
where uncertainty could change the architecture. Batch completion and milestone
promotion remain separate: every criterion in roadmap §4 must have an explicit
verdict on the final applicable tree. A completed dependency does not promote its
consumer, and no batch changes release placement or enables a serving default.

| Completion batch | Deliverable and owner | Work that may proceed now | Freeze and acceptance boundary |
|---|---|---|---|
| **A — data, control and clients (M0–M4)** | Coordinator joins storage/authority/config/migration/runtime-readiness completion with the client lane's compatible v1/v2/v3 surface. | Active: M4 lab findings and application repairs; integrate B4a evidence/instrument repair and the B5 corpus inventory correction; inventory remaining M0–M3 criteria as implementation, measurement or decision gaps. Populated-import and authority/lifecycle proofs run before dependent assumptions spread. | Freeze a coherent candidate after targeted lane checks. Run both-store applicable contracts, actual two-tenant HTTP and stored oracles, pooled/concurrent authority/outage/schema controls, actual pinned-client labs, full/browser/enabled corpus, then final prcheck. All semantic differences require an approved basis; unknown differences remain failures. |
| **B — durable runtime (M5)** | Runtime owner joins one proven durable producer/consumer path, realtime forwarding/fan-out, evaluator state and durable ack/snooze. | Active early proof: commit-stamp meaning and crash/replay correctness. Implementation may proceed in parallel against established interfaces after the proof and required contract approval; role-table and event-payload lanes remain separate until their gates pass. | First reference is separate roles on one machine. Freeze the assembled runtime, then exercise real process death/restart, duplicate/lost delivery, cohort pagination, current socket authorization, forwarding acknowledgements, replay-equivalent tenant views and retained evaluator results. Run batch regression and final prcheck once on that candidate. |
| **C — synthetic operational preview (M6)** | Operations owner joins import/export/deletion, ciphertext/key recovery, backup/restore, upgrade/rollback, bounded resources/egress and final-tree review. | Prepare tools and populated synthetic fixtures in parallel with A/B. Run one representative populated restore/import and contention experiment early; broader acceptance waits for stable data/runtime contracts and approved bounds. | Freeze the complete preview after A/B criteria and chosen owner capabilities are satisfied. Run populated failure/recovery and lifecycle campaigns, isolation/security/client/runtime regression, explicit capacity/latency workloads and the complete criterion matrix. Production identity/traffic, real data, role enablement and publication retain their separate approvals. |

A–C are completion stages, not three indivisible code changes. A lane continues
through a coherent family of fixes without demanding a full suite after every
commit. Every lane still runs changed-code lint, affected tests, meaningful
focused checks and authored red/restored controls. Final full acceptance belongs
to the exact assembled head; ancestry alone never transfers a control result.

### Criterion-to-test matrix for the frozen candidates

The coordinator fills the actual command/selector, tree, instrument revision,
artifact and verdict for every row before claiming completion. The rows below
are required coverage, not new passing measurements. Counts and waived criteria
cannot substitute for that mapping.

| Milestone / acceptance family | Candidate and required instrument | Current kind of remaining work |
|---|---|---|
| M0 binding, RLS, pool reuse, rollback and unsafe schema | A: real restricted-role PG/pooler positives plus paired tenant/RLS/transaction failures and actual startup refusal | Existing implementation/evidence foundation; final-tree deployment/schema/pool coverage remains measurement work. |
| M1 backend semantics, identities, queries, history, batches and imports | A: applicable Mongo/PG differential contracts, populated import/replay oracle and query/lock/materialization bounds | Bounded compatibility gaps require implementation; broad populated/resource acceptance remains measurement; new numeric limits require a maintainer decision. |
| M2 settings/current authority/secrets and listener separation | A: actual provider + PG + HTTP config/versioning/revocation and owner/data/operator boundary controls | Remaining issuer/refresh, existing-grant clamping and production lifecycle/listener composition are implementation gaps; authenticator, recovery or capability-policy choices stay decisions. |
| M3 cumulative two-tenant HTTP | A: actual executable, overlapping identities, independent stored-state oracle, grants/outages/concurrency/schema and restored controls | Combined acceptance must execute after source joins; earlier positives and controls remain historical evidence on their own heads. |
| M4 pinned client workflows | A: actual executable clients and independent responses/stored values, retries/refusals/revocation, followed by explained differential cells | Reproduced lab differences need focused diagnosis and implementation. Mobile/v3 binary feasibility and source-pattern replay coverage remain explicit; no all-client claim follows from a headless subset. |
| M5 durable feed/recovery | B: persisted checkpoint and complete-cohort oracle under commit-before-publish death, duplicates, missed notifications, soft deletion and cross-tenant checkpoint refusal | Architectural proof first. Hard-delete recovery, replay horizon, transport/provider and multi-node ownership guarantees cannot be inferred; unresolved choices stay scoped/deferred. |
| M5 sockets/evaluator/ack | B: D23 forwarding with actual ack/no-ack behavior, current authorization/reconnect, tenant rooms/caches, replay-equivalent evaluation and durable ack/snooze recovery | Implementation after interfaces are proven; ack schema/retention and notification delivery retain their own decision/acceptance gates. Live external notifications are not admitted by evaluator lab success. |
| M6 populated operations and bounds | C: export/import fidelity, tenant deletion, recoverable keys/ciphertext, interrupted restore/upgrade, egress refusal and resource workloads on final assembled tree | Early feasibility proof and substantial implementation/measurement remain. Approve numeric bounds/retention policy before using them as pass thresholds. |

### Early proofs that remain deliberately small

| Proof / owner | Question resolved before broader work | Predicted green and meaningful red |
|---|---|---|
| Stamp and recovery / runtime owner | Define a per-write stamp versus transaction floor, including nested writes allocating nothing; establish a durable checkpoint/replay model. | Green: committed state is reconstructed after writer/consumer death without losing tied rows or repeating logical effects. Red: break checkpoint persistence, cohort completion or duplicate identity and observe missing/duplicate tenant outcomes; rollback emits nothing. |
| Actual client differences / client and application owners | Diagnose each observed response/value difference against the same-head Mongo reference before widening the client claim. | Green: repaired workflow has matching supported replies and independent stored values; intentional differences have an adopted basis. Red: perturb the oracle or reply/identity handling and the client assertion/classifier fails for that mechanism. |
| Owner authority/lifecycle / control-plane owner | Establish current actor/delegation/existing-grant behavior and separate listener trust before joining management workflows. | Green: authorized current own-tenant operation persists, revoked/foreign/over-ceiling operation refuses without effects. Red: bypass one permission/current-state fence and the stored-state assertion detects it. |
| Populated restore/import and contention / operations owner | Establish fidelity, recoverable key material and practical resource/locking behavior before completing operations. | Green: recovered synthetic values/identity/tenant boundaries match, interruption resumes or explicitly refuses safely. Red: omit a populated cohort/key or break rollback/recovery and the independent oracle detects the loss. Capacity thresholds remain UNMEASURED until approved and exercised. |

These proofs reduce uncertainty; they do not each trigger a full native acceptance
campaign. A failed prediction is reported with its exact symptom and preserved
before repair. Do not silently redefine the contract or choose a provider,
authenticator, recovery guarantee, retention horizon or numeric limit to get green.

### Parallel execution and evidence accounting

Parallel implementation and test preparation are the default. Isolated focused
jobs may overlap only with recorded capacity and positive resource ownership;
unknown containers/volumes remain untouched. CI or independent workers may run
separate labs concurrently when their namespaces, ports, fixtures and teardown
are isolated and capacity is measured. The local slot is a machine constraint,
not an ordering dependency between independent implementation lanes. Quiet
performance measurements receive a separate controlled window.

Before freezing a batch, reconcile the enabled-suite inventory with source and
publish named pending/unsupported cases. A pending benchmark is not functional
acceptance and does not prove a budget. Run one comprehensive campaign on the
frozen candidate; after fixes, rerun affected assertions/controls and repeat final
full acceptance when the material candidate changed. Allocate each integration
record at write-time, preserve immutable failures and source/instrument revisions,
and move queue refs only after the actual frozen-head campaign passes.

B4a is recorded complete locally in R58 on its evidence branch, with the original
partial R57 preserved; its instrument repair is a separate change. B5's joined
clock corpus required an inventory repair; source listing is verified but expanded
runtime acceptance remains UNMEASURED. These bounded results are inputs to A,
not completion of A.

Current ownership: root coordinator owns Batch A integration and acceptance;
the existing M4 chat owns the independent client lab; the M4 application-repair
agent owns diagnosed UUID-default and literal-regexp compatibility work; the M5
agent owns an executable recovery research prototype. The durable-delivery
contract remains draft and checkpoint bookkeeping authority remains unresolved,
so this prototype cannot establish adopted production runtime semantics. Owner
session/issuer lifecycle and the wider operational implementation are **unassigned**;
the coordinator must allocate those before claiming A or C implementation complete.
Local integration ownership and exact unpushed anchors are in
`externals/work/HANDOFF-codex-completion-batches-20261106.md` (local, untracked).

<a id="5-lane-ownership-and-coordination"></a>
## 6. Lane ownership and coordination

- The **root coordinator** owns the cumulative application branch, the queue,
  release records, dashboard and map edits, and the single runtime slot.
- **Source-only lanes off the R56 head `65bb8456`** (session `-8c`, maintainer-assigned
  2026-11-06, no slot): `codex/event-payload-20261106` carries the durable delivery
  contract's decision 3 (tenant and commit stamp on the per-write event; one focused
  `clock` run with its own containers under rule 3), and `codex/role-table-20261106`
  carries D23 entry condition 4 (typed fields on the role table, `describeComposition`,
  a unit test). Each joins #8898 at a batch boundary; neither is pushed on its own.
- **Lane handoffs** are `externals/work/HANDOFF-<lane>-<date>.md`, local and
  untracked. The coordinating session's own notes are in
  `externals/work/HANDOFF-batching-coordinator-20261106.md`.
- **Publication** of alignment records and application branches remains the
  maintainer's action. Agents prepare local commits and reviewable instructions;
  agents never push.
- The two untracked November 2 draft files in this directory belong to a peer
  session and are never staged by anyone else.
- Several sessions share one git index: check `git diff --cached --name-only`
  and commit by path.

<a id="6-what-this-plan-does-not-do"></a>
## 7. What this plan does not do

It promotes no milestone, selects no backend or provider, enables no listener
or default, and adds no release gate for 16.0.0. It does not weaken the
full-suite-before-ready contract: the full campaign still runs before any batch
head is called ready. It changes where and how often that campaign runs.
