<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit.py   (make queue)
  Staleness check:  python3 tools/queue/emit.py --check

  Every edit to this file will be destroyed by the next `make queue`. Edit the
  YAML instead. It is generated so that a status cannot be edited into the
  human-readable view by hand.

  Even here, `state` is only a CLAIM about what the gates will say. The
  measurement is `make queue-status`, which runs them.
  ============================================================================
-->

# Work queue

Generated from `queue/work-queue.yaml` by `tools/queue/emit.py`. **Do not hand-edit.**

- Manifest schema version: `1`
- Measured at: 2026-09-23
- Measured against cgm-remote-monitor-official: `ddd9b600`
- Measured against nightscout-connect: `977da8a`
- Measured against main_repo_head: `c1a5e719`

One queue spans every programme on purpose, so that a tenancy task colliding with a release train is visible in one place. The `parcel` field does the separating.

## Totals

| | count |
|---|---|
| items | 115 |
| runnable gates | 184 |
| explicit `no-gate:` markers | 159 |

A `no-gate:` marker is not a gap in the bookkeeping; it is the bookkeeping. It records that nobody has yet built a way to measure the property, and it carries the reason. 159 of the 343 gate slots in this queue are in that state.

### Claimed state (NOT a measurement -- run `make queue-status`)

| state | n | ids |
|---|---|---|
| `not-started` | 35 | RT-VERSION, BFQ-10, BFQ-21, BFQ-19, BFQ-22, BFQ-23, BFQ-25, BFQ-24, BFQ-26, BFQ-27, BFQ-18, BFQ-20, BFQ-CAP01, T30-SCHEMA-CRED, T30-SCHEMA-CONFIG, T30-ORY-PROOF, T30-WIRING, T43, T44, A7A-3, A7A-4, DOC-SEQUENCING, DOC-PLAN, DOC-REGISTER, DOC-MEMORY, DOC-LAYOUT, DOC-TESTSCRIPTS, BFQ-MINIMED, BFQ-92, BFQ-93, BFQ-96, BFQ-CAP02, FU-HYGIENE, BFQ-106, BFQ-108 |
| `in-progress` | 1 | RT-D3 |
| `gate-not-met` | 14 | P0-C, P0-J, RT-REBASE, SEAM-REFRESH, DOC-EXPOSURE, BFQ-71, BFQ-CONNECTOR, BFQ-46, BFQ-ENV, BFQ-67, RT-CONNECT-PIN-CUTS, RT-NODE-FLOOR-TESTED, RT-BOOTERROR, FU-RESIDUALS |
| `ready-to-push` | 2 | P0-C-REMEDIATE, T30-AUTH |
| `blocked` | 16 | P0-PIN, P0-LOCK, RT-1, RT-2, RT-3, RT-5, T31-REM, T32-REM, T33-REM, A7A-GATE, BFQ-52, BFQ-66, FU-LIMIT, BFQ-99, BFQ-100, BFQ-101 |
| `in-flight-upstream` | 3 | BFQ-47, BF2-AUTH, BFQ-102 |
| `merged-upstream` | 29 | P0-A, P0-B, P0-D, P0-E, P0-F, P0-G, P0-H, P0-I, P0-K, P0-CONNECT-ROLE, BFQ-91, P0-PUBLISH, P0-T01, RT-COUNT0, RT-MONGO-FLOOR, RT-4, BFQ-04, BFQ-69, BFQ-40, BFQ-87, BFQ-90, ADV-RETRO, ADV-ALARM, BF2-BACKPORT, BF2-OPS, BFQ-103, BFQ-107, BFQ-97, BFQ-98 |
| `needs-decision` | 9 | P0-TAG, RT-COUNT-COMPAT, RT-0, T30-RESEARCH, BFQ-72, BFQ-95, FU-PRBODIES, ADV-XSS-META, ADV-CONFIG |
| `done` | 2 | DOC-VIEWS, DOC-LINKS |
| `unsettled` | 3 | BFQ-09, A7A-7, BFQ-94 |
| `closed` | 1 | BFQ-41 |

### Reaches an operator on today's release

The register's `§1` vs `§1b` distinction, carried as `ships_to_operators_today`. Preserving it is the only thing that makes the register mean anything.

- **BFQ-91** BF-91 - connector capture mode cannot find trace-axios for two sources
- **BFQ-09** BF-09 - socket dedup truthiness skips a falsy value
- **BFQ-10** BF-10 - mongod fatal-asserts at Docker's default nofile=1024
- **BFQ-04** BF-04 - the v1 operator allowlist - superseded by P0-K
- **BFQ-CAP01** CAP-01 - Nightscout cannot be served from a sub-path
- **BFQ-69** BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing
- **BFQ-71** BF-71 - any dateString key drops the default date window, and the window is not a control
- **BFQ-72** BF-72 - an unauthenticated $regex can spend minutes of database CPU
- **BFQ-40** BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion
- **BFQ-87** BF-87 - the root qs override holds the connector below its range and pins the server's query parser
- **BFQ-CONNECTOR** BF-42, BF-43 - master pins the leaking connector, with a violated axios override
- **BFQ-MINIMED** BF-44, BF-45, BF-85 - MiniMed ingestion divergences and the CareLink zero reading
- **BFQ-46** BF-46 - eleven API v3 variables bypass env.js, one family deletes data
- **BFQ-47** BF-47 - an ordinary subject edit destroys stored fields, on today's release
- **BFQ-ENV** BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies
- **BFQ-52** BF-52 - an age reminder whose 20-minute window passed without a check was never sent
- **BFQ-90** BF-90 - an alarm at a page with no reading throws in the client
- **BFQ-92** BF-92 - a page with no glucose reading never presents a server alarm, including device alarms
- **BFQ-93** BF-93 - food changes never reach an open page
- **BFQ-94** BF-94 - a kept profile instance can return a temp basal that has been replaced
- **BFQ-95** BF-95 - an uploader clock running ahead delays the stale-data alarm
- **BFQ-67** BF-67, BF-86 - alarm thresholds quietly changed, or quietly kept when they cannot work
- **ADV-RETRO** GHSA-gjhc - loadRetro serves devicestatus to any socket (BF-79)
- **ADV-ALARM** GHSA-8849 - /alarm broadcasts to the whole namespace (BF-75, BF-76)
- **ADV-XSS-META** GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74)
- **ADV-CONFIG** The readable-by-world warning, the careportal role, and the two settings behind both (BF-77, BF-78, BF-81)
- **BFQ-103** BF-103 - a split drag stores the old time, so IOB and COB ignore the move
- **BFQ-107** BF-107 - a failed treatments query ends the Nightscout process on 15.0.8
- **BFQ-108** BF-108 - a list of timestamps under the date field answers 500, so bulk deletes by timestamp do nothing
- **BFQ-98** BF-98 - the connector reuses a reader subject without roles, so the BF-89 fix does not repair it
- **BFQ-99** bf/profile-object-id - a profile posted with its own _id is stored as an ObjectId, and string-_id profiles can be edited and deleted
- **BFQ-100** BF-100 - devicestatus, food and activity store a hex _id as a string
- **BFQ-101** BF-101 - API v3 id filters miss records stored with a string _id
- **BFQ-102** bf/object-id-consistency - one rule for a record's own hex _id across profile, devicestatus, food, activity, treatments, entries and API v3

---

## Phase 0 backfixes - ships to every existing operator

`parcel: phase0` &mdash; 22 items

Eight of the ten cgm-remote-monitor Phase 0 branches are merged into
origin/dev (PRs #8733 to #8743, 2026-09-17 to 2026-09-20); their items are
`merged-upstream`, meaning in dev and not released. Until RT-0 ships 15.0.9,
no operator carries any of them. Remaining on the cgm-remote-monitor side:
bf/auth (P0-C) and bf/throttle (P0-J), both behind origin/dev and trial-
merging clean. Connector side, measured against nightscout-connect
official/dev 1946beb (2026-09-22): PRs #64 (carrying #61, #66, #67), #68, #74,
#75 and #76 are merged. Connector dev declares 0.1.0 and carries the
credential-safe logging, the opt-in logger, listener release on stop, the
BF-85 CareLink zero filter and the backoff and jitter fix. Prerelease
0.1.0-dev.1 is on npm under `next`, built from 1946beb; npm's `latest` is
still 0.0.12 and there is no full connector release. cgm-remote-monitor dev
still pins connector commit 234d47c, so none of this reaches an operator yet:
P0-TAG is the full release, P0-PIN and P0-LOCK move the pin. None of these
needs a tenancy decision.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `P0-A` | bf/alarms - PR #8739, BF-28, BF-29, BF-31 | `merged-upstream` | `bf/alarms` | minor | 9 run + 3 no-gate |
| `P0-B` | bf/cache - PR #8740, T0.2 and T0.3 read-path cost | `merged-upstream` | `bf/cache` | patch | 6 run + 2 no-gate |
| `P0-C` | bf/auth - BF-17 plaintext token (BF-30 split out to P0-J) | `gate-not-met` | `bf/auth` | major | 4 run + 3 no-gate |
| `P0-J` | bf/throttle - BF-30, failed-auth throttling, compatibility default | `gate-not-met` | `bf/throttle` | patch | 5 run + 2 no-gate |
| `P0-C-REMEDIATE` | Operator remediation for tokens already stored in plaintext - text, not tooling | `ready-to-push` | `-` | n/a | 1 run + 2 no-gate |
| `P0-D` | bf/coercion - PR #8737, query filter typing (T0.5) and the $exists inversion | `merged-upstream` | `bf/coercion` | minor | 7 run + 1 no-gate |
| `P0-E` | bf/reads - PR #8738, six read-path fixes, independent of bf/coercion | `merged-upstream` | `bf/reads` | major | 10 run + 5 no-gate |
| `P0-F` | fix/connect-timer-jitter - PR #68, BF-34 backoff precedence and start jitter | `merged-upstream` | `fix/connect-timer-jitter` | minor | 4 run + 1 no-gate |
| `P0-G` | bf/food - PR #8735, BF-16 quick-pick filter, BF-35 bolus calculator chooser | `merged-upstream` | `bf/food` | minor | 6 run + 1 no-gate |
| `P0-H` | bf/merge - PR #8734, BF-36 client delta merge reads past the end | `merged-upstream` | `bf/merge` | patch | 5 run + 2 no-gate |
| `P0-I` | bf/parms - PR #8736, BF-37, BF-38, BF-39 | `merged-upstream` | `bf/parms` | patch | 6 run + 1 no-gate |
| `P0-K` | bf/operators - PR #8743, BF-04 extracted, BF-70 found | `merged-upstream` | `bf/operators` | minor | 7 run + 2 no-gate |
| `P0-TAG` | nightscout-connect 0.1.0 - the full release, from connector dev | `needs-decision` | `dev` | minor | 5 run + 1 no-gate |
| `P0-CONNECT-ROLE` | nightscout-connect's nightscout source creates its reader subject with role, not roles (BF-89) | `merged-upstream` | `fix/nightscout-reader-roles` | patch | 3 run |
| `P0-PIN` | bf/connect-pin - pin dev to the published nightscout-connect 0.1.0 | `blocked` | `bf/connect-pin-0.1.0` | patch | 2 run + 1 no-gate |
| `P0-LOCK` | Regenerate package-lock.json for the nightscout-connect 0.1.0 pin | `blocked` | `bf/connect-pin-0.1.0` | n/a | 2 run |
| `P0-PUBLISH` | nightscout-connect publishes to npm from a version tag | `merged-upstream` | `ci/npm-trusted-publish, ci/prerelease-tags` | n/a | 3 run + 1 no-gate |
| `P0-T01` | T0.1 - PR #8733, the two quadratic treatment scans | `merged-upstream` | `fix/quadratic-treatment-processing` | patch | 1 run + 1 no-gate |
| `FU-LIMIT` | Follow-up 2 - the limit rule is written twice, and that is the root cause | `blocked` | `-` | patch | 2 run + 1 no-gate |
| `FU-RESIDUALS` | Follow-ups 3, 4, 7 - three named residuals beside branches already prepared | `gate-not-met` | `-` | patch | 3 run + 1 no-gate |
| `FU-PRBODIES` | Merged PR bodies have drifted from the files they were posted from | `needs-decision` | `-` | n/a | 1 run + 2 no-gate |
| `FU-HYGIENE` | Follow-ups 9, 10 - the two audits that have no instrument | `not-started` | `-` | n/a | 0 run + 2 no-gate |

### `P0-A` &mdash; bf/alarms - PR #8739, BF-28, BF-29, BF-31

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/alarms` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-alarms` |
| semver | `minor` |
| review | maintainer, plus one reviewer who has never merged their own PR in this stack (the governance finding - 100 self-merged PRs, zero human reviews). PR #8739 merged into dev on 2026-09-20; not released. Two behaviour changes a reviewer of the release should know: it starts an alarm that has never fired in any deployment, with no grace period, and it removes per-request locale from two HTTP endpoints with no replacement (ruled a defect correction, see semver_reason). |
| register | `BF-28`, `BF-29`, `BF-31` |

**Blast radius.** 3 commits. lib/plugins/insulinage.js, lib/plugins/index.js, lib/api/googlehome/index.js, lib/api/alexa/index.js. Zero file overlap with any other Phase 0 branch.

**What an operator sees.** Three alarm fixes, arriving with the next release (15.0.9); they are not in the version you run today. The "insulin reservoir change overdue" reminder could never appear at all, and will be able to. If you list a plugin by its file name in ENABLE (the setting that switches features on) - for example "cannulaage" instead of "cage" - Nightscout switches it off without telling you; after the update it says so and names the plugin it thinks you meant. These do not change when any alarm fires, only whether it can. This is not medical advice; if an alarm you rely on has been silent, talk it through with your care team as well as checking your settings.

**Why `minor`.** Maintainer ruling 2026-09-17: the per-request locale handling on POST /api/v1/alexa and POST /api/v1/googlehome is a defect, not a capability. ctx.language.set and moment.locale are process-global, so a request carrying request.locale re-languaged every later request for every other user - which was never the intent. Removing it is a correction, and the branch needs an ordinary review, not an explicit capability-removal yes.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/alarms origin/dev`
  - Containment: this tip is an ancestor of origin/dev, so the fix is in dev (PR #8739, merged 2026-09-20) and cannot silently leave it. An upstream revert or force-push turns it red.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/alarms >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[unit]` _(cwd: `externals/work/crm-bf-alarms`)_ `TEST=insulinage npm run test-single`
  - BF-28, measured. 5 passing. Ablated: with lib/plugins/insulinage.js put back to origin/dev the same file gives 3 passing / 2 failing. Database-free: re-run with the mongo URL pointed at a dead port, still 5 passing.
- `[unit]` _(cwd: `externals/work/crm-bf-alarms`)_ `TEST=plugins npm run test-single`
  - BF-29, measured. 13 passing. Ablated: with lib/plugins/index.js put back to origin/dev the same file gives 5 passing / 8 failing. Database-free.
- `[integration]` _(cwd: `externals/work/crm-bf-alarms`)_ `TEST=api.alexa npm run test-single`
  - BF-31, the branch's own test for the locale removal. 4 passing, measured 2026-09-16. Needs a mongod on port 27034 (named by crm-bf-alarms' my.test.env). Ablated: lib/api/alexa/index.js restored to origin/dev gives 3 passing / 1 failing.
- `[integration]` _(cwd: `externals/work/crm-bf-alarms`)_ `TEST=api.googlehome npm run test-single`
  - BF-31's sibling. 2 passing, measured 2026-09-16 on the same mongod. Ablated: lib/api/googlehome/index.js restored to origin/dev gives 1 passing / 1 failing.
- **NO GATE** &mdash; `npm run test:unit` is not a gate here because it asserts less than it looks like. It resolves to a 44-file brace list, it needs MongoDB (verifyauth x4 and API_SECRET x2 fail without it even on pristine dev), and tests/api.alexa.test.js and tests/api.googlehome.test.js - two of the four files this branch adds - are in neither local script. CI's `test-ci` runs all 159 files and does cover them; a gate that mirrors the local script is weaker than CI, not equal to it.
- `[static]` `test -f externals/work/crm-bf-alarms/node_modules/.cache/_ns_cache/public/js/bundle.app.js`
  - The worktree has its client bundle. Without it the suite shows an extra test failure that looks like a defect and is not. This tests a LOCAL build product, not the branch: it goes red in any fresh worktree or after `npm ci`, and `npm run bundle` in that worktree clears it.
- **NO GATE** &mdash; Nothing exercises the ENABLE warning through a booted plugin registry. GT4 had to hand-reconstruct the plugin-name list to test it, and a reconstructed registry is not the registry. Needs a boot-level test.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 5dcf783fdbb20188c378d79121dcbe860425eede origin/dev`
  - containment: the measured tip of bf/alarms is in origin/dev, so the merge carried it. Holds after the branch moves or is deleted; reads local remote-tracking refs, so fetch origin first.
- **NO GATE** &mdash; Review and merge state of PR #8739 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8739`
  - the live body of PR #8739 still matches the file it was posted from. Corrections are written into the file first, so this catches a body that was not updated after its file. It does NOT measure whether the body is true: parity with a wrong file is still parity. Non-vacuity, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/60-research/remedial/bf28-29-31-alarm-delivery-2026-09-15.md`
- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`
- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Sequencing letter A. §7a items 5 and 6 are these commits; neither may be read as making alarms safe to turn on under TENANCY_MODE=multi. Two gates depend on the machine, not the branch. The integration gates (api.alexa, api.googlehome) need a mongod listening on 27034; the one used for the 2026-09-16 measurement ran from a scratch dbpath and is not persistent. Anyone who sees them red should check for a listener on 27034 before reading it as a regression. The bundle gate tests a local build output under node_modules (not tracked content); if it is red, run `npm run bundle` in the worktree before reading it as a regression.

### `P0-B` &mdash; bf/cache - PR #8740, T0.2 and T0.3 read-path cost

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/cache` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-cache` |
| semver | `patch` |
| review | maintainer. PR #8740 merged into dev on 2026-09-20; not released. No decision is asked of the reviewer, but the branch ships with a target it did not hit, and the body says so in the operator-facing text rather than only in the technical detail. What cannot be read off the diff: T0.2's gate is MET (0.7x against a 2x budget, dev fails at 42x) and T0.3's is NOT (2.66 ms against 1 ms), and both are re-runnable from this repository with one command each. |
| register | `BF-06`, `BF-07` |

**Blast radius.** 2 commits at 4f86bab1, 6 files, +385/-8. lib/server/cache.js, lib/data/dataloader.js, lib/api/entries/index.js, plus three test files.

**What an operator sees.** Pages that read recent glucose values get faster, from the next release (15.0.9). Nothing you see changes value or meaning.

**Why `patch`.** performance only; no declared surface moves.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/cache origin/dev`
  - Containment: this tip is an ancestor of origin/dev, so the fix is in dev (PR #8740, merged 2026-09-20) and cannot silently leave it. An upstream revert or force-push turns it red.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/cache >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[integration]` `node tools/queue/gates/t02-read-ratio.js`
  - T0.2's stated gate, run live, and it is MET - an untyped /api/v1/entries read must come within 2x of a typed one at count=10, and it is 0.7x. It sits beside the T0.3 gate on purpose: that one is red and this one is green, and showing only one would misrepresent the branch. Non-vacuity is structural: the harness reads lib/api/entries/index.js out of the worktree and names the shape it found - clone-then-slice on dev, slice-then-clone on the branch. Measured 2026-09-16: dev FAILS at 42.3x, the branch PASSES at 0.7x. SKIPS when the worktree has no node_modules.
- `[integration]` `node tools/queue/gates/t03-cycle-clone-budget.js`
  - T0.3's stated gate, run live, and red by design - the budget is under 1 ms and the three cycle calls are 2.66. The workload is recorded in docs/60-research/remedial/t02-t03-cache-clone-2026-09-15.md: §2 names the harness (tools/mt-bench/apitier.js, arm `cycle`) and the fixture - 576 entries, 600 treatments of which 361 survive retention, 576 device statuses with 72-point prediction arrays, DEVICESTATUS_DAYS=2 - and §10 gives the command. Measured 2026-09-16 on Node v24.15.0: branch 2.656 ms (recorded 2.657), origin/dev 3.929 ms (recorded 3.747) - ordinary variance on a timing bench, same direction and magnitude. Non-vacuity is structural: the harness reads the live call sites out of the worktree and prints them (dev entries=insertData, branch entries=insertDataRef) and throws on a tree it cannot recognise, so it cannot report the branch's number for dev's code. Positive control: --budget 5 passes. SKIPS when the worktree has no node_modules.
- **NO GATE** &mdash; The 98% of the remaining cost is devicestatus, whose caller rewrites fields in place. Taking it needs proof that nothing in the plugin tier writes to a device-status document. A grep is not that proof when the failure mode is a field silently vanishing from every API read served out of the cache. There is no test that would catch it.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 4f86bab1637e926502c9b02af008cbba4f424c28 origin/dev`
  - containment: the measured tip of bf/cache is in origin/dev, so the merge carried it. Holds after the branch moves or is deleted; reads local remote-tracking refs, so fetch origin first.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8740`
  - the live body of PR #8740 still matches the file it was posted from. It does NOT measure whether the body is true; parity with a wrong file is still parity.
- **NO GATE** &mdash; Review and merge state of PR #8740 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.

**Evidence.**

- `docs/60-research/remedial/t02-t03-cache-clone-2026-09-15.md`
- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`
- `tools/mt-bench/apitier.js`

**Notes.** This item reports FAIL under INTEGRATION=1 by design. The T0.3 gate asserts a budget of under 1 ms and the branch ships at 2.66 ms. The target was deliberately not met - 98% of the remainder is devicestatus and taking it needs a proof nobody has produced - and the branch says so in its operator- facing text. The red is the record of a decision, not a regression; the gate's own first line of output says so. T0.2's gate sits beside it and is green, so the pair moves if either target does. Both performance gates are kind: integration because they run a benchmark, so a default queue-status skips them; use `make queue-status ID=P0-B INTEGRATION=1` before drawing any conclusion from this row. --- Sequencing letter B. T0.2 passed its gate (0.837 -> 0.025 ms, asserted identical over HTTP). T0.3 did not. A dead `mills` write at dataloader.js:203 was found and removed with a test that goes red if it returns.

### `P0-C` &mdash; bf/auth - BF-17 plaintext token (BF-30 split out to P0-J)

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `bf/auth` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-auth` |
| semver | `major` |
| review | SECURITY - a human security reviewer first, before any other Phase 0 branch. This is the one the sequencing document singles out. |
| register | `BF-17` |

**Blast radius.** Content: 2 commits at ce82f0cd, 3 files, +310/-18. lib/authorization/endpoints.js, lib/authorization/storage.js, tests/authsubjects.test.js. Tip 404e714c is a merge of origin/dev 59430336 into ce82f0cd (2026-09-21). The BF-30 throttle work is on bf/throttle (P0-J), not here.

**What an operator sees.** Two security fixes, not yet merged or released. Editing a subject (an access entry on the admin page) writes that subject's API access token into the database in readable form, which turns read access to your database into API access; with this fix it no longer does. IMPORTANT: tokens already written that way stay in your database - fixing the code does not remove them (see P0-C-REMEDIATE for what to do). Brute-force slowdown on failed logins is keyed on a value the caller can choose, so it never engages; the fix makes it engage. Existing access tokens keep working - they are re-derived on every load and are not invalidated by this change.

**Why `major`.** GT4: beyond the two fixes, the branch narrows lib/authorization/storage.js to write only an allow-list of fields (name, roles, notes, created_at), so any field a third-party admin tool has stored is dropped on the next edit with NO error. It also adds `notes` to the GET /api/v1/subjects response. The throttle change alone would be minor - the sleep moved to the failure path, so no request that authenticates is delayed by another client's failures behind a shared proxy.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/auth`
  - bf/auth has not fallen behind origin/dev. This branch is waiting to be pushed, so falling behind dev is a real defect in it. RED as of 2026-09-22: the tip merges origin/dev 59430336, and dev has since moved to 74fc6619 (the three advisory merges). The remedy is `git merge dev`, which the trial-merge gate below measures as conflict-free; see notes for why it has not been done.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/auth >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[static]` _(cwd: `externals/work/crm-bf-auth`)_ `grep -nE "console\\.log\\('Loading',[[:space:]]*opts\\)" lib/authorization/storage.js && exit 1 || exit 0`
  - Regression guard for BF-05's sibling: a per-request debug print of request-derived values, `console.log('Loading',opts)` in storage.js. The pattern is whitespace-tolerant on purpose - the code has no space after the comma, and a pattern requiring one never matches, which makes the gate pass on a false property. Do not narrow it. Green because commit 56ed29d2 removed the line from bf/auth (maintainer's choice, 2026-09-16), not because the pattern was weakened.
- `[integration]` _(cwd: `externals/work/crm-bf-auth`)_ `TEST=authsubjects npm run test-single`
  - BF-17. Not in either local script. 8 passing with MongoDB; 1 passing / 7 failing with the fix ablated.
- **NO GATE** &mdash; `npm run test:unit` is not evidence for this branch: its 44-file brace list contains neither of the two test files bf/auth adds, so the suite could pass in full with every one of these fixes reverted.
- **NO GATE** &mdash; Nothing here checks that plaintext tokens ALREADY written into existing databases get cleaned up, and nothing will: the code fix does not remove them, there is no migration, and by decision (2026-09-16) there is no detector script. What is measured is next door - P0-C-REMEDIATE's gate checks that this branch's PR body and the release notes tell an operator the truth about it, including that a rename is not a rotation. Read that item before signing this one off.
- **NO GATE** &mdash; One conflict with PR #8605 remains and it is this branch's own - lib/authorization/storage.js, which the modernization branch also narrows, for different reasons. Measured 2026-09-16: bf/auth against origin/chore/nightscout-modernization conflicts in that one file and nothing else (the four other conflicts were the BF-30 peer plumbing, which is why that half became P0-J). Not gated, because resolving it is a merge somebody has to sit down and do, and which side wins depends on whether the allow-list lands at all.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** SUPERSEDED BY BF2-AUTH (2026-09-23) - bf2/auth-hardening contains bf/auth by ancestry, and BF2-AUTH is what ships (15.0.9, plan section 1a). This item's freshness gate fails only because bf/auth is 9 commits behind origin/dev; it is not merged up because it will not be pushed on its own. The queue has no superseded state, so the state is left as measured. DECIDED 2026-09-23 (maintainer) - the security reviewers are the maintainer and Andy (a connector maintainer). Sequencing letter C. GT3 found BF-17's created_at residual: the pick() at endpoints.js:44 is ['_id','name','accessToken','roles','notes'] - notes was added by the fix, created_at was not. Commit 56ed29d2 removes the leftover console.log('Loading',opts). That line was not introduced by this branch - it is on origin/dev at storage.js:84 - and it is taken here because it sits in a file this branch already rewrites and is the same defect class as the count-path filter leak fixed on bf/reads. FU-RESIDUALS follow-up 4 is carried BY THIS BRANCH and should not be fixed there a second time; it is `fixed` (on a branch), not merged, and FU-RESIDUALS' gate, which reads origin/dev, correctly still fails. Green gates here do not mean an operator is safe - tokens written in plaintext before the upgrade are untouched by it. The remediation is TEXT, not tooling (P0-C-REMEDIATE): no detector and no migration, rotation instructions carried by this branch's PR body and the 15.0.9 release notes, and a gate guarding what they say, including that renaming a subject is not a rotation because the matcher is name-independent. --- The 2026-09-21 merge-up (tip 404e714c, origin/dev 59430336 merged into ce82f0cd, on the maintainer's instruction). Exactly one file is touched by both sides, lib/authorization/storage.js, in different functions: dev's 06b133a7 (BF-01, from bf/reads) replaces the limit() helper on the READ path, while this branch narrows save() to a field allow-list and removes the console.log('Loading',opts) on that same read path. The merge changed 2 lines and removed 4 in lib/authorization/. merge-tree is not trusted alone here (the register's BF-04 detail records a merge-tree CLEAN result that hid a semantic collision), so it was measured: TEST=authsubjects 8 passing at ce82f0cd and 8 passing at 404e714c; tracking gate green; full suite 2319 passing, 3 pending, 0 failing at 404e714c against mongod 7.0.43 started with --ulimit nofile=64000:64000. That qualifier matters - at Docker's default descriptor limit mongod dies mid-suite (BF-10) and every downstream timeout looks like a regression. --- Current state (2026-09-22): behind origin/dev 74fc6619 by the three advisory merges; trial merge clean. The merge is not done here because a merge without re-running the full suite would trade a red gate for an unmeasured green one. While this branch is ready and unpushed it goes stale every time dev moves, and at gate-not-met it has no reviewer packet (emit_packets builds only for in-flight-upstream, ready-to-push and needs- decision). Pushing it is what stops that.

### `P0-J` &mdash; bf/throttle - BF-30, failed-auth throttling, compatibility default

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `bf/throttle` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-throttle` |
| semver | `patch` |
| review | maintainer. Split out of bf/auth on 2026-09-16 on the maintainer's instruction, without the lib/server/peer-address.js plumbing that conflicted with PR #8605 in five files - that PR replaces the client-address derivation wholesale with a TRUST_PROXY-driven module. This branch merges CLEAN against #8605, measured, and the throttle keys on data.ip, which #8605 then makes trustworthy with no further change here. What a reviewer needs and cannot read off the diff: THE DEFAULT IS TODAY'S BEHAVIOUR BY DESIGN, an attacker varying both credential and header is still not throttled, and that gap is asserted by a test rather than left implied. |
| register | `BF-30` |

**Blast radius.** Content: 1 commit at 435419ce, 3 files, +388/-45. lib/authorization/delaylist.js, lib/authorization/index.js, tests/authdelay.test.js. Tip a0823c4f is a merge of origin/dev 59430336 into 435419ce (2026-09-21).

**What an operator sees.** Two fixes to the delay Nightscout applies after a failed login, and one thing it will tell you. These are not yet merged or released. Today that delay is applied on the way IN to every request, so a device presenting the CORRECT password can be made to wait for somebody else's failed attempts - and if your Nightscout sits behind a proxy or a CDN (a service in front of your site), where many devices can look like they share one address, a single misconfigured uploader can slow everything down. With the fix the delay applies only to the request that actually failed. Separately, the list of recent failures is not cleared properly and grows for as long as Nightscout keeps running; the fix bounds it. THERE WILL ALSO BE A NEW MESSAGE IN YOUR LOG, and it tells you something true - the protection against password guessing is weaker than it looks, because the address it counts against can be set by whoever is connecting. Nothing you configured changes and nothing you rely on stops working. Restricting access at your proxy or hosting provider is the thing that actually helps today. None of this is medical advice.

**Why `patch`.** no declared surface moves and no default changes. For any given request the delay only ever SHRINKS - a successful authentication is no longer delayed at all - so nothing that worked stops working. An added log line is not a surface. The secure default is a later and deliberate bump.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/throttle`
  - bf/throttle has not fallen behind origin/dev. This branch is waiting to be pushed, so falling behind dev is a real defect in it. RED as of 2026-09-22: the tip merges origin/dev 59430336, and dev has since moved to 74fc6619 (the three advisory merges). The remedy is `git merge dev`; the trial-merge gate below measures it as conflict-free.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/throttle >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree bf/throttle origin/chore/nightscout-modernization >/dev/null`
  - The property this branch exists for - it merges clean with PR #8605. With the peer-address plumbing included it conflicted in five files (index.js, storage.js, alarmSocket.js, security.js, websocket.js). Non-vacuity, reproduced 2026-09-16: the identical command against bf/auth, which narrows storage.js, CONFLICTS - so this is not passing because merge-tree always passes.
- `[static]` `sh -c 'git -C externals/cgm-remote-monitor-official grep -qI peer-address bf/throttle && exit 1 || exit 0'`
  - lib/server/peer-address.js is NOT on this branch and nothing references it. A tracking gate against the obvious regression - re-adding that module re-creates the four-file conflict with #8605, and it would look like a harmless improvement to anyone who had not measured it.
- `[integration]` _(cwd: `externals/work/crm-bf-throttle`)_ `TEST=authdelay npm run test-single`
  - The branch's own test, 11 passing, measured 2026-09-16 and again at a0823c4f on 2026-09-21. Needs MongoDB - this worktree names 27031. It is in neither local brace list, so a green `npm run test:unit` is no evidence for any of this. Ablated: lib/authorization/delaylist.js and lib/authorization/index.js restored to origin/dev give 3 passing / 8 failing. It includes the test that PINS THE REMAINING WEAKNESS - `does NOT yet throttle a guess that varies both the secret and the address` - which asserts the gap rather than pretending it is closed, and which should be INVERTED into a positive assertion when the TRUST_PROXY boundary lands. A red here can be mongod having died (BF-10) rather than the branch; check the server before reading it as a regression.
- **NO GATE** &mdash; Nothing measures the boot warning's words. init() logs that the throttle is keyed on an address the caller may control, and that restricting access at the proxy is what helps today. That text IS the notification half of the maintainer's compatibility decision, and it is prose - the same shape as P0-C-REMEDIATE, where prose needed a gate to stay correct. A real gate would check that the message names no setting that does not exist on this branch, and that it never claims the throttle protects against credential guessing.
- **NO GATE** &mdash; THE ADDRESS KEY IS STILL CALLER-CONTROLLED, DELIBERATELY. This branch does not close BF-30. It makes the control cheap for legitimate clients, bounds the list, stops retaining the credentials people tried, adds a second key, and says so out loud. An attacker who varies both the credential and the forwarded header is throttled by neither key. Closing it needs the TRUST_PROXY boundary from PR #8605, after which data.ip is an address the caller cannot choose and this file needs no edit. BF-30 MUST NOT BE READ AS FIXED on the strength of this item.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** SUPERSEDED BY BF2-AUTH (2026-09-23) - bf2/auth-hardening contains bf/throttle by ancestry, and BF2-AUTH is what ships (15.0.9, plan section 1a). This item's freshness gate fails only because bf/throttle is 9 commits behind origin/dev; it is not merged up because it will not be pushed on its own. The queue has no superseded state, so the state is left as measured. Why the split. The modernization branch (PR #8605) does not touch lib/authorization/delaylist.js - it is byte-identical to dev there - but it REPLACES THE IP DERIVATION THAT FEEDS IT, swapping the forwarded-for package for lib/server/client-ip.js driven by TRUST_PROXY, in exactly the call sites the peer-address plumbing also edited. The two were fixing one root cause with two different modules. Without peer-address.js the conflict with #8605 is one file, and that one belongs to BF-17 (P0-C). What the compatibility default costs, recorded because it was argued and decided: another release in which an attacker rotating X-Forwarded-For is not throttled. The usual price of turning it on - one failing client behind a shared proxy slowing others - is already paid for by the sleep-timing change in this same commit, because only failing requests wait. So the compatibility case is weaker here than for the allow-list on P0-C, and that was said at the time. The maintainer's instruction was compatibility defaults plus notification across this area. --- The 2026-09-21 merge-up (tip a0823c4f, origin/dev 59430336 merged into 435419ce, on the maintainer's instruction). Zero overlap, measured before merging: dev had no commit touching any of this branch's three files. Both properties the split exists to preserve hold after the merge - no conflict against chore/nightscout-modernization, and no peer-address plumbing. TEST=authdelay: 11 passing at 435419ce and at a0823c4f. Current state (2026-09-22): behind origin/dev 74fc6619 by the three advisory merges, so the freshness gate is red and the state is gate-not-met; the other three static gates pass. Not merged up, for the reason given under P0-C. `pr: []` is declared because the review text names #8605, which is RT-3's PR, not this item's; without the declaration the packet generator would infer the wrong PR from the prose.

### `P0-C-REMEDIATE` &mdash; Operator remediation for tokens already stored in plaintext - text, not tooling

| | |
|---|---|
| state (claimed) | `ready-to-push` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `-` |
| semver | `n/a` |
| review | maintainer, plus the security reviewer who takes P0-C |
| register | `BF-17` |
| blocks on | `P0-C` |

**Blast radius.** Operator-facing text only, in three documents this repo owns - releases/cgm- remote-monitor-15.0.9/release-notes.md, reports/phase0-pr-bodies/bf-auth.md and the report they are written from. No shipping code path, no script, no migration.

**What an operator sees.** If you have ever edited a subject (an access entry on your Nightscout admin page), a readable copy of that subject's API access token is sitting in your database. Upgrading will not remove it - it clears for a subject only when you next save that subject through the admin page, and clearing the copy does not retire the token. There are exactly TWO ways to retire an exposed token: delete and recreate the subject, or change API_SECRET (your site's main admin password). RENAMING THE SUBJECT IS NOT ONE OF THEM, even though the token's appearance changes. Anyone who has had read access to your database since the first edit could have used that token.

**Why `n/a`.** not a code change to the shipped surface

**Gates.**

- `[static]` `node tools/queue/gates/bf17-remediation-note.js`
  - 17 checks. The deliverable is prose, and the prose has to match the code: a rename is cosmetic - checkToken keeps the LAST dash-segment of the presented token and matches it against subject.digest, which is getSubjectHash(subject._id); the name reaches only the abbrev at the front, which is never read back. An operator who renamed and stopped would believe a leaked credential was retired while it still authenticated. The gate pins the CODE property on origin/dev AND the bf/auth worktree, so the prose cannot drift from it in either direction, then checks each of the four documents for what must be said and for sentences known to be wrong (rename as a rotation; the stored copy discarded on load). Non-vacuity, reproduced 2026-09-16: restoring the rename row to the release notes -> 1 failing; restoring the PR body's "discarded when Nightscout next loads it" -> 2 failing; restoring the rename option to report 2.3 -> 1 failing; empty QUEUE_GATE_ROOT -> 17 failing.
- **NO GATE** &mdash; No detector script, by decision (maintainer, 2026-09-16). A count is not remediation - remediation is rotation, and rotation is an operator decision no script can take. The per-operator form of the question is already written out in the PR body ("look in your auth_subjects collection for any document with an accessToken, accessTokenDigest or digest field"). A fleet-wide count has no consumer. THE RESIDUAL THIS LEAVES: an operator who never re-saves a previously-edited subject keeps a plaintext row indefinitely and nothing prompts them. The release notes say so.
- **NO GATE** &mdash; NOTHING MEASURES WHETHER AN OPERATOR ACTS. This item ships words. No gate in this repository can show that a single exposed token was rotated, and none should claim to.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf17-bf30-auth-defects-2026-09-15.md`
- `releases/cgm-remote-monitor-15.0.9/release-notes.md`
- `reports/phase0-pr-bodies/bf-auth.md`

**Notes.** Settled 2026-09-16 as TEXT rather than tooling: the maintainer decided against a detector script and against a migration, on the ground that the notes carry the operator's actual decision and a script does not. The two facts the text must get right, both measured: renaming a subject does not retire its token (the matcher is name-independent - lib/authorization/storage.js:326 on bf/auth, :288 on origin/dev); and upgrading does not discard the stored copy (reload() deletes the derived fields from the IN-MEMORY record only; the row clears when the subject is next saved through the admin path). The release notes, the PR body and the source report state both correctly, and the gate above guards them.

### `P0-D` &mdash; bf/coercion - PR #8737, query filter typing (T0.5) and the $exists inversion

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/coercion` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-coercion` |
| semver | `minor` |
| review | maintainer. PR #8737 merged into dev on 2026-09-18; not released. It merged clean against dev and against all eight other Phase 0 branches. Three things a reviewer cannot get from the diff: the classification is minor and rests on no request that worked ceasing to work; `tests/query.operands.test.js` matches neither local brace list, so a green `npm run test:unit` is evidence for the typing fix and none for BF-40; and the composition with bf/reads is a property of the PAIR, not of either diff, and is deliberately in neither PR. |
| register | `BF-02`, `BF-03`, `BF-11`, `BF-32`, `BF-40`, `BF-68` |

**Blast radius.** 2 commits at b7234753, the largest change in the set. lib/server/query.js plus a generated coercion table over 5 collections; 158 coercions replace 13 hand- written entries.

**What an operator sees.** Two fixes to searches through the API (the interface apps and scripts use to read your data), arriving with the next release (15.0.9); the version you run today still has both problems. First, searches that filter on a number compare that number against text, so many of them quietly match nothing and still answer "OK". After the update they compare correctly. If you have a saved search, a script or a third-party app that was returning nothing, it may start returning results - that is the fix working, not a new problem. Second, and the one most likely to have been acted on: asking for records that are MISSING a particular field (a filter written $exists=false) returns exactly the records that HAVE it, with a success code and nothing to say the answer is inverted. Any report, dashboard or script using that filter is answering the opposite question, and a count from one is counting the wrong group. Re-run anything built on one after the update; the set it returns will be the complement of what it returned before. Asking for records that DO have a field ($exists=true) is correct before and after. This is not medical advice; if a report like this informed decisions about care, talk it through with your care team.

**Why `minor`.** GT4 measured the change in answers: find[duration][$gte]=30 goes from {"$gte":"30"} (matched nothing) to {"$gte":30}; find[insulin][$gte]=1.5 from {"$gte":1} to {"$gte":1.5}. $exists operands are no longer coerced as field values: the old walker produced {"$exists":NaN}, which MongoDB reads as true, so $exists=true answered correctly by accident; the branch reads the operand as a boolean (BOOLEAN_OPERANDS / readBooleanOperand in lib/server/query.js), which is what makes $exists=false correct (BF-40). No request that worked stops working.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/coercion origin/dev`
  - Containment: this tip is an ancestor of origin/dev, so the fix is in dev (PR #8737, merged 2026-09-18) and cannot silently leave it. An upstream revert or force-push turns it red.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/coercion >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[unit]` _(cwd: `externals/work/crm-bf-coercion`)_ `TEST=query.operands npm run test-single`
  - BF-40's own test, 12 cases, on the second commit. In neither local brace list (GT1), so a green `npm run test:unit` is not evidence for it. Ablated three ways with each break confirmed to land: removing the call fails 6, mapping "" to false fails exactly the test pinning that decision, adding $regex to the reader map fails exactly the $regex test.
- `[unit]` _(cwd: `externals/work/crm-bf-coercion`)_ `TEST=query npm run test-single`
  - 29 passing, database-free (measured against a dead mongo port). Ablated behaviourally: reverting ONLY lib/server/query.js and keeping the new table gives 24 passing / 4 failing on assertions ("expected '1.5' to be 1.5"). (Running the file against pristine dev fails at module resolution, which is not a behavioural control.)
- `[static]` `T=$(mktemp -d) && trap 'rm -rf "$T"' EXIT && python3 -m tools.nsschema.emit.coercion_emit --bundle "$T/emitted.json" >/dev/null && diff -q "$T/emitted.json" externals/work/crm-bf-coercion/lib/server/query-coercion.json`
  - The coercion table vendored into the branch is byte-identical to what the emitter produces today, so the branch is not shipping a stale generated file ("emit, then check the emission"). `coercion_emit --drift` is not usable as a gate: it returns 0 unconditionally (it exited 0 while printing "DRIFT vs the shipping walkers: 157 disagreements") and compares against a hardcoded transcription of origin/dev's walkers, so it says nothing about bf/coercion.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor b72347538ba29f965c531bdd47f81dc52d895a13 origin/dev`
  - containment: the measured tip of bf/coercion is in origin/dev, so the merge carried it. Holds after the branch moves or is deleted; reads local remote-tracking refs, so fetch origin first.
- **NO GATE** &mdash; Review and merge state of PR #8737 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8737`
  - the live body of PR #8737 still matches the file it was posted from. Corrections are written into the file first, so this catches a body that was not updated after its file. It does NOT measure whether the body is true: parity with a wrong file is still parity. Non-vacuity, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `tools/nsschema/emit/coercion_emit.py`
- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Sequencing letter D. BF-03 is closed for devicestatus and profile only - `food` reaches query.js at no point and `activity`'s model has no numeric field, so those two halves were misfiled rather than fixed.

### `P0-E` &mdash; bf/reads - PR #8738, six read-path fixes, independent of bf/coercion

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/reads` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-reads` |
| semver | `major` |
| review | maintainer. PR #8738 merged into dev on 2026-09-18; not released. Independent of P0-D - the two branches merge cleanly with each other. Three things a reviewer cannot get from the diff: it is graded major on one commit only (06b133a7, the ?count= tightening, which is app.use'd ahead of every v1 router and so covers writes); none of the five test files is in `npm run test:unit`, so a green run there is evidence for none of the six fixes; and ?count=0 answers TWO different ways on dev before this branch, depending on whether the runtime cache can serve the request - see notes. |
| register | `BF-01`, `BF-05`, `BF-13`, `BF-14`, `BF-15`, `BF-33` |

**Blast radius.** 6 commits at 2ecfeb53, all its own, based directly on origin/dev. lib/server/aggregate.js, entries.js and four siblings, lib/api3/generic/search/input.js, lib/api3/shared/fieldsProjector.js, lib/api3/generic/collection.js, lib/server/count.js, lib/api/index.js.

**What an operator sees.** Six fixes to how the API (the interface apps and scripts use to read your data) answers read requests, arriving with the next release (15.0.9); the version you run today still has these problems. Counting entries that matched a filter returns nothing at all; paging through results can skip or repeat records; asking for a nested field returns an empty answer; and three different ways of asking for "no limit" return the entire collection instead. CHANGE YOU MAY NOTICE after the update: six spellings of ?count= that used to be accepted will return an error instead of a surprising answer - count=0, count=0x10, count=2.5, count=-3, count=1e2 and count=abc. If a script of yours uses one of those, it will fail loudly instead of quietly returning the wrong number of records.

**Why `major`.** GT4: six previously-accepted ?count= spellings now return 400, and the validator is app.use'd on the WHOLE v1 app before every router - so it covers /treatments, /profile, /devicestatus, /notifications, /activity, /food, /status, /alexa, /googlehome, and WRITES as well as reads. A POST /api/v1/treatments?count=0 now returns 400 where it previously succeeded. The branch CHANGELOG lists read routes only.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/reads origin/dev`
  - Containment: this tip is an ancestor of origin/dev, so the fix is in dev (PR #8738, merged 2026-09-18) and cannot silently leave it. An upstream revert or force-push turns it red.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/reads >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[static]` `node tools/queue/gates/bf-reads-read-contract.js`
  - The database-free half of the branch's behaviour, driven through the four pure modules the six fixes live in: parseCount/hasCount/applyCount, the dotted-?fields= projector, the _id tiebreak in the v3 sort chain, and the count path's use of query_for with nothing printed. 8 assertions. Built-in negative control: `--rev origin/dev` runs the identical assertions against dev materialised from the object database and gives 4 failing. (A branch-has-a-commit check is not a substitute: it passes for origin/dev, origin/master and bf/alarms too.)
- `[integration]` _(cwd: `externals/work/crm-bf-reads`)_ `TEST=api.count-parameter npm run test-single`
  - BF-13/BF-33, 13 passing. Needs MongoDB: pointed at a dead port it goes to 0 passing / 1 failing, timing out in the before-all hook. It is fast only because a mongod is listening on crm-bf-reads' port 27032.
- `[integration]` _(cwd: `externals/work/crm-bf-reads`)_ `TEST=api.count-where npm run test-single`
  - BF-01, 5 passing. Needs MongoDB.
- `[integration]` _(cwd: `externals/work/crm-bf-reads`)_ `TEST=api3.fields npm run test-single`
  - BF-15, 6 passing. Needs MongoDB (5 of 6 survive without it).
- `[integration]` _(cwd: `externals/work/crm-bf-reads`)_ `TEST=api3.limit npm run test-single`
  - BF-33, 8 passing. Needs MongoDB.
- `[integration]` _(cwd: `externals/work/crm-bf-reads`)_ `TEST=api3.paging npm run test-single`
  - BF-14, 3 passing. Needs MongoDB.
- **NO GATE** &mdash; `npm run test:unit` is not a gate here: not one of the five test files this branch adds is in its 44-file brace list - all five are api*/api3* and match test:integration's glob - so the suite could pass in full with every fix reverted.
- **NO GATE** &mdash; The ordering constraint inside the branch (BF-05's commit must follow BF-01's) is not machine-checked. The two commits are 3b588098 and 4772b983 on the current tip; any gate quoting other SHAs is stale. A real gate would assert the relative order of the two by subject line, and nobody has written it.
- **NO GATE** &mdash; The CHANGELOG on this branch lists read routes only, while the ?count= validator covers writes too. Nothing checks a release note against the code it describes.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 2ecfeb53ff1e6121ef5f76e1f08e97af1ca6c2fa origin/dev`
  - containment: the measured tip of bf/reads is in origin/dev, so the merge carried it. Holds after the branch moves or is deleted; reads local remote-tracking refs, so fetch origin first.
- **NO GATE** &mdash; Review and merge state of PR #8738 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- **NO GATE** &mdash; The two-path behaviour of ?count=0 is measured but not asserted. tools/probes/count0-two-paths.js reproduces it - 0 rows from the cache and all 24 from the database on dev, 400 on both after this branch, with two controls that stay sane on each tree - but it PRINTS rather than exits non-zero, so it is a probe and not a gate. Making it one means deciding what the contract IS, and that is a reviewer's call, not this queue's. It also needs two worktrees and a mongod.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8738`
  - the live body of PR #8738 still matches the file it was posted from. Corrections are written into the file first, so this catches a body that was not updated after its file. It does NOT measure whether the body is true: parity with a wrong file is still parity. Non-vacuity, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`
- `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`
- `docs/60-research/remedial/e3-gate-vacuity-audit-2026-09-15.md`

**Notes.** ?count=0 before this branch, measured 2026-09-16 against dev a8888f0d with 24 stored entries: with no `find`, the runtime cache serves it and returns 0 rows, which is what the client asked for; with a `find` that forces the read past the cache to the database, `.limit(0)` means unbounded and it returns all 24. Controls sane (count=5 -> 5 rows, no count -> 10, the default). After this branch both paths return 400. #8738's body states both paths (edited 2026-09-16; the parity gate is green). A red pr-body-parity gate means the posted PROSE is stale, not that the code is defective; the state model does not separate those, so read the gate output before treating a red here as a code regression. --- Sequencing letter E. Current tip 2ecfeb53, 6 commits, re- cut directly onto origin/dev after a CHANGELOG-only commit was dropped; `git range-diff` showed all six content-identical to their earlier selves. Older documents quote 824380a0 (7 commits, GT1) and 0d19bb31 (8 commits, on bf/coercion); both are superseded by 2ecfeb53. blocks_on is empty: bf/reads and bf/coercion are independent. The §3b concern is NOT a merge hazard: bf/coercion gives query.js a new `collection:` option and bf/reads fixes aggregate.js, which calls query.js through api.query_for and passes no options - so the count path still gets the legacy default walker after both land. Deliberately in neither PR.

### `P0-F` &mdash; fix/connect-timer-jitter - PR #68, BF-34 backoff precedence and start jitter

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `nightscout-connect` |
| branch | `fix/connect-timer-jitter` |
| base | `official/dev@d208c7d` |
| worktree | `externals/work/nc-jitter` |
| semver | `minor` |
| review | done upstream; merged with a merge commit, so c1cce2a is an ancestor of connector dev |
| register | `BF-08`, `BF-34` |

**Blast radius.** Merged into connector dev as 3f73288 on 2026-09-22. README.md, index.js, lib/backoff.js, lib/builder.js, lib/machines/cycle.js and four test files, +430/-38 against d208c7d.

**What an operator sees.** This changes the connector, the part of Nightscout that fetches readings from a CGM (continuous glucose monitor) vendor's online service. When that service is refusing requests, the connector used to retry roughly 586 times faster than it was configured to, and every account retried at the same instant. With this fix it waits the interval it was told to wait and spreads the retries out. Something that may seem backwards: after this fix a vendor outage can look like it recovers more slowly, because the connector no longer retries in a burst that could not have worked. For LibreLinkUp in particular, after a failed fetch the next attempt comes one to two and a half minutes later, as the connector is configured, rather than almost immediately. The connector can also spread out its first contact with the vendor after a restart; the spreading settings default to 0, so nothing changes for anyone who does not set them. It is in the connector's 0.1.0-dev.1 prerelease and in no full release, and reaches no one until Nightscout is updated to use a release that has it (P0-TAG, P0-PIN).

**Why `minor`.** Option precedence reversed, a changed default (use_random_slot:false -> jitter:'equal'), a new throw on an unknown jitter mode, and duration_for became non-deterministic: each is breaking for a caller, so under 0.x semantics the first release carrying it is a minor bump. Connector dev declares 0.1.0 (PR #76).

**Gates.**

- `[unit]` _(cwd: `externals/work/nc-jitter`)_ `npm test`
  - 283 passing / 0 failing at 635cc9f, the merged head; the connector suite needs no database
- `[unit]` _(cwd: `externals/work/nc-jitter`)_ `node -e "const b=require('./lib/backoff.js'); try { b({jitter:'wild'}); process.exit(1); } catch(e) { process.exit(/unknown jitter mode/.test(e.message)?0:1); }"`
  - the new throw on an unknown jitter mode is the observable half of the precedence fix - if options were still being discarded, the bad mode would never be read and this would not throw
- `[static]` `git -C externals/nightscout-connect merge-base --is-ancestor c1cce2a official/dev`
  - containment: c1cce2a is in connector dev. Reads local remote-tracking refs; fetch official first.
- `[network]` `git -C externals/nightscout-connect merge-base --is-ancestor c1cce2a "$(npm view nightscout-connect@0.1.0-dev.1 gitHead)"`
  - the published prerelease 0.1.0-dev.1 was built from a commit that contains c1cce2a. Read-only.
- **NO GATE** &mdash; Vendor rate limits are unmeasured (EXP-MT-051) and need real credentials, which rule 0 forbids here. CONNECT_START_JITTER_MS lets a pool be spread, but the window to set is exactly the number that is unmeasured.

**Evidence.**

- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** Sequencing letter F. The branch carried the merge of #64's head 19af0c3 (ffe5fb0), so c1cce2a is unchanged. dev's LibreLinkUp v4 code had its own jitter (CONNECT_LINK_UP_STARTUP_JITTER_MS, CONNECT_LINK_UP_INTERVAL_JITTER_MS); the two are one mechanism in lib/machines/cycle.js: one start delay on Init over the wider of the deployment and source windows; the wider of the two on the unaligned interval; only the source window on the aligned interval; every window capped at five minutes. LibreLinkUp's fixed frame retry, noRetryStatuses and the 429 throttle path are unchanged and are still checked before the backoff. LibreLinkUp's configured cycle backoff (2.5 minutes x 2^attempt, capped at six poll intervals) is honoured; its recovery test asserts that (676b80e). The LibreLinkUp real-Nightscout lab passed locally and in CI at 635cc9f. Not re- measured on the merged tree: the pool figures in c1cce2a's message (100 actors, 800 requests across 3 s before and 67 s after under refused authentication; 400 actors, busiest second 400 to 15 with 60 s of start jitter) were taken on the pre-dev base b77e5bb.

### `P0-G` &mdash; bf/food - PR #8735, BF-16 quick-pick filter, BF-35 bolus calculator chooser

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/food` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-food` |
| semver | `minor` |
| review | maintainer - the sequencing document calls this the one to read first, and BF-35 is why. PR #8735, base dev, merged 2026-09-20. It merged without a review from anyone outside this stack (the governance finding), and the /api/v1/food/quickpicks filter change was the point to get an explicit yes on; a release reviewer should look at both. |
| register | `BF-16`, `BF-35` |

**Blast radius.** 1 commit. lib/client/boluscalc.js, lib/food/food.js, lib/food/quickpick.js (new), lib/server/food.js, 2 new test files.

**What an operator sees.** Important. In the bolus calculator (the screen that suggests an insulin amount from the carbohydrates you enter), choosing a saved "quick pick" food could load a DIFFERENT record's food, so the carbohydrate number that went into the calculation came from a record you did not choose, and nothing on screen said so. Picking the last entry in the list could throw an error, and plain foods that are not quick picks appeared in the chooser. Separately, quick picks saved by some apps, or saved before the "hidden" setting existed, were missing from the quick-pick list. The fix is merged into the development version and arrives with the next release (15.0.9); if you are running 15.0.8 or earlier, the problem is still there. If you have used the bolus calculator's quick picks, the amount it suggested may not have matched the food you selected. The calculator is a suggestion tool, not a dosing instruction - please raise this with your care team if you think a past suggestion was wrong. This is not medical advice.

**Why `minor`.** GT4: it changes an HTTP API v1 response. /api/v1/food/quickpicks goes from filtering on the literal string {hidden:'false'} to {hidden:{$nin:[true,'true']}}, so quick picks written by any JSON client, and any record saved before the field existed, start appearing. Position ordering moves from lexicographic (in-query) to numeric (in-process). Records appear that did not; none disappears.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/food origin/dev`
  - Containment: this tip is an ancestor of origin/dev, so the fix (PR #8735, merged 2026-09-20) is in dev and cannot silently leave it. An upstream revert or force-push turns it red.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/food >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[unit]` _(cwd: `externals/work/crm-bf-food`)_ `TEST=boluscalc.quickpick npm run test-single`
  - BF-35's own test, 11 cases. The file is in NEITHER the test:unit nor the test:integration brace list (GT1), so a green `npm run test:unit` on this branch is not evidence that BF-35's fix works; it is named explicitly here for that reason.
- `[integration]` _(cwd: `externals/work/crm-bf-food`)_ `TEST=api.food.quickpicks npm run test-single`
  - BF-16 over the real HTTP path; needs MongoDB
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 73495331e68c4cda3a63e8c047387bdf404b89b0 origin/dev`
  - containment: the measured tip of bf/food is in origin/dev, so the merge carried it. Holds after the branch moves or is deleted; reads local remote-tracking refs, so fetch origin first.
- **NO GATE** &mdash; Review and merge state of PR #8735 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8735`
  - the live body of PR #8735 still matches the file it was posted from. A correction is written into the file first, so drift runs from file to live body. It does NOT measure whether the body is true: parity with a wrong file is still parity. NON-VACUITY, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`

**Notes.** Sequencing letter G. BF-35 is a regression from 3457de5b (2017) and was found while fixing BF-16 - which is the argument for landing BF-16 even though BF-16 itself has no in-tree consumer. Schema-drift anchors. The SOURCE_ASSERTIONS in tools/nsschema/code_model.py pinned text that bf/food deletes. Each affected anchor now accepts EXACTLY the pre-fix and post-fix spelling and nothing else, and lib/food/quickpick.js isTrue is in a SOURCE_ASSERTIONS_IF_PRESENT tuple that arms when the file appears. Measured 2026-09-16: schema-code-drift exits 0 against crm-seam, cgm-remote-monitor-official and crm-bf-food. Ablated three ways, each break confirmed to land first - filter narrowed to `{ hidden: false }` FAILS, restoreBoolValue rewritten to Boolean() FAILS, quickpick.isTrue renamed FAILS; all three restored exits 0. STILL OWED now that the branch is in dev: delete the pre-fix arm of each anchor and promote the quickpick.js entry, or a revert passes silently.

### `P0-H` &mdash; bf/merge - PR #8734, BF-36 client delta merge reads past the end

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/merge` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-merge` |
| semver | `patch` |
| review | maintainer. PR #8734, base dev, merged 2026-09-18. |
| register | `BF-36` |

**Blast radius.** 1 commit. lib/client/receiveddata.js, one new test file.

**What an operator sees.** A treatment being removed at the same time as another update arrived could make the page stop updating until you reloaded it. The clock that tells you how old the reading is runs on its own timer, so it would still have gone stale and warned you - the reading shown was never wrong, it just stopped advancing. The fix is merged into the development version and arrives with the next release (15.0.9).

**Why `patch`.** availability fix in client code; no declared surface moves

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/merge origin/dev`
  - Containment: this tip is an ancestor of origin/dev, so the fix (PR #8734, merged 2026-09-18) is in dev and cannot silently leave it. An upstream revert or force-push turns it red.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/merge >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[unit]` _(cwd: `externals/work/crm-bf-merge`)_ `TEST=receiveddata.merge npm run test-single`
  - in NEITHER local brace list (GT1). Named here so the gate actually runs the file that proves the fix.
- **NO GATE** &mdash; `dataUpdate` still has no try/catch, so the NEXT throw from anywhere in the merge path has the same effect. This branch fixes one throw, not the missing boundary. No test asserts the boundary exists because it does not.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor b06c6faf882ebd84d627468c75dade0fe1fd01a1 origin/dev`
  - containment: the measured tip of bf/merge is in origin/dev, so the merge carried it. Holds after the branch moves or is deleted; reads local remote-tracking refs, so fetch origin first.
- **NO GATE** &mdash; Review and merge state of PR #8734 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8734`
  - the live body of PR #8734 still matches the file it was posted from. A correction is written into the file first, so drift runs from file to live body. It does NOT measure whether the body is true: parity with a wrong file is still parity. NON-VACUITY, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Sequencing letter H.

### `P0-I` &mdash; bf/parms - PR #8736, BF-37, BF-38, BF-39

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/parms` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-parms` |
| semver | `patch` |
| review | maintainer. PR #8736, base dev, merged 2026-09-20. What a release reviewer should know: classification is patch with one judgement call (the underscore decoding, see semver_reason); the BF-37 test is invisible to `npm run test:unit`, so a green run there is evidence for BF-38 and none for BF-37; and BF-39 breaks nothing live today - both token spellings return 200 - which the PR body says outright. |
| register | `BF-37`, `BF-38`, `BF-39` |

**Blast radius.** 3 commits at eb0bc918. lib/client/browser-utils.js, lib/language.js.

**What an operator sees.** A web address with a bare option in it - anything ending in "?", or containing "&&", or a setting with no value such as "?debug" - stopped the page loading entirely, leaving only the loading message. Two smaller fixes go with it: a translation containing ten or more substitutions came out with a stray digit, and an access token belonging to a subject whose name contains an underscore was being altered in the address bar (the server was accepting it anyway, so nothing was broken for you). These are merged into the development version and arrive with the next release (15.0.9).

**Why `patch`.** all three are bug fixes with no declared-surface movement. BF-38 is latent - no shipped catalogue uses more than %3.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/parms origin/dev`
  - Containment: this tip is an ancestor of origin/dev, so the fix (PR #8736, merged 2026-09-20) is in dev and cannot silently leave it. An upstream revert or force-push turns it red.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/parms >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[unit]` _(cwd: `externals/work/crm-bf-parms`)_ `TEST=browser-utils.queryparms npm run test-single`
  - BF-37 and BF-39; in NEITHER local brace list (GT1)
- `[unit]` _(cwd: `externals/work/crm-bf-parms`)_ `TEST=language npm run test-single`
  - BF-38. Non-vacuous by GT1's control - 1 failing when the fix is removed from pristine dev code.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor eb0bc918036a7802a0b88156e9722f45fd9107f3 origin/dev`
  - containment: the measured tip of bf/parms is in origin/dev, so the merge carried it. Holds after the branch moves or is deleted; reads local remote-tracking refs, so fetch origin first.
- **NO GATE** &mdash; Review and merge state of PR #8736 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8736`
  - the live body of PR #8736 still matches the file it was posted from. A correction is written into the file first, so drift runs from file to live body. It does NOT measure whether the body is true: parity with a wrong file is still parity. NON-VACUITY, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Sequencing letter I. Branch commit order, measured: 522c6ffb (BF-37), c9a7a21c (BF-38), eb0bc918 (BF-39). The sequencing document (line 165) lists them as 522c6ffb, eb0bc918, c9a7a21c mapped to BF-37, BF-39, BF-38; the order above is the measured one, and GT3 found the same.

### `P0-K` &mdash; bf/operators - PR #8743, BF-04 extracted, BF-70 found

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/operators` |
| base | `origin/dev@fdd08706` |
| worktree | `externals/work/crm-bf-operators` |
| semver | `minor` |
| review | MAINTAINER. PR #8743, base dev, merged 2026-09-18 (merged up to dev fdd08706 first). Three things a release reviewer should be told rather than left to find: (1) This does NOT close the reported NoSQL-injection advisory. Of its three proofs of concept only $where is refused. The other two are filed as BFQ-71 and BFQ-72 and were re-measured with controls. The date-window path is not a privilege boundary: the allowlisted, documented date-range filter returns the identical records on the identical authorisation, and every form is 401 under AUTH_DEFAULT_ROLES=denied. The unauthenticated full-history read is what the shipped `readable` default means, not something that code path grants; BF-71 is low severity. BF-72 is an AVAILABILITY defect rather than the extraction the advisory describes: 60-71 s of database CPU from one unauthenticated request against a 22 ms control, live on 15.0.8 and on dev, no fix yet. Against the advisory's five remediation items this does 1 and 2, not 3, 4 or 5, and item 3 as the advisory frames it is disputed on measurement. The PR body as merged still carries the advisory's framing - see BFQ-71's notes. (2) BF-70 has NO advisory of its own. It is a second unauthenticated read path with the same reachability, and the advisory covers find[...] only. (3) The $type question is closed - see semver_reason. |
| register | `BF-04`, `BF-70` |

**Blast radius.** 3 commits at 52b7b640. New: lib/storage/assert-no-query-javascript.js, lib/server/query-operator-allowlist.js, lib/api/shared/query-error.js and three test files. Modified: lib/server/query.js, lib/server/aggregate.js, the five v1 API modules, both swagger files. OVERLAPS bf/reads on lib/server/aggregate.js - the only Phase 0 branch it conflicts with; resolution written out in the report §4.2 and measured.

**What an operator sees.** Nightscout's older API (the web interface apps use to read your data) let a web address ask the database to run JavaScript, and let one particular address ask questions about parts of the database it had no business reading - including, on a default setup, without any password or token. Both are closed in the development version and arrive with the next release (15.0.9); the running release, 15.0.8, still has them. What you may notice after updating: a filter using an unusual option answers with a clear error instead of appearing to work, and the "count" address no longer accepts a `pipeline` setting, which was never documented and which no known app uses. Ordinary filters - date ranges, event types, glucose thresholds - are unchanged. Your stored data is not touched. Nightscout is not a medical device and this is not medical advice; if a report or app you rely on starts showing an error after updating, it is telling you the request was malformed, not that your data is gone.

**Why `minor`.** It removes reachable behaviour - $expr on /profiles/ and the undocumented pipeline parameter - so it is not a patch by the project's own reading. It is not major either: no route is removed, no required input is added, no documented contract breaks, and the census of 14 client projects found zero senders of anything now refused. $type is ALLOWED. PR #8737 put readTypeOperand() on dev because find[sgv][$type]=2 must arrive as the number 2 or the request becomes an HTTP 500, measured against mongod 3.6.8 and 7.0.43. Refusing $type would regress that fix to gain nothing - it executes nothing and reads nothing outside the document. It is the one departure from the storage seam's set, and the cost is known: when the seam lands its AST needs a $type node or v1 narrows by one operator then. $not and $text stay refused - both were fixtures in #8737's tests rather than subjects, and their assertions are rewritten, not deleted.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/operators origin/dev`
  - Containment: this tip is an ancestor of origin/dev, so the fix (PR #8743, merged 2026-09-18) is in dev and cannot silently leave it. An upstream revert or force-push turns it red.
- `[unit]` _(cwd: `externals/work/crm-bf-operators`)_ `TEST=mongo-query-javascript npm run test-single`
  - BF-04, the JavaScript half. 23 passing, 49 ms, no database. ABLATED on the dev merge - commenting out the create() call gives 7 failing, confirmed applied by grep before the run. The allowlist also refuses $where, as an unlisted operator with the generic message, so the 7 are the cases asserting the SPECIFIC JavaScript wording: this guard is mostly about the message, not the refusal.
- `[unit]` _(cwd: `externals/work/crm-bf-operators`)_ `TEST=api-v1-operator-allowlist npm run test-single`
  - BF-04, the allowlist. 63 passing + 16 pending without a database; the 16 are the end-to-end section, which is the only place the ALLOWED operators are proved to still SELECT rather than merely to pass the guard. ABLATED two ways, both confirmed applied by grep - removing the create() call gives 14 failing, making refuse() return instead of throwing gives 35.
- `[unit]` _(cwd: `externals/work/crm-bf-operators`)_ `TEST=api-v1-count-pipeline npm run test-single`
  - BF-70. 8 passing, 30 ms, no database. ABLATED - restoring the two lines the commit changes gives 3 failing.
- `[integration]` _(cwd: `externals/work/crm-bf-operators`)_ `TEST=api-v1-operator-allowlist npm run test-single`
  - the same file with CUSTOMCONNSTR_mongo set - 79 passing, mongod 7.0 on port 27018, measured on the dev merge 9745cae2. This is the run that matters: without a database the end-to-end section skips and the suite proves only that refusals refuse.
- **NO GATE** &mdash; The strongest control this branch has is not runnable from here. The BF-70 reproduction extracts a seeded value over unauthenticated HTTP on a8888f0d and extracts nothing on 52b7b640 - same machine, same database, same session, same unmodified probe. It is deliberately NOT committed: this repository is public and the defect is live on the shipping release, and a gate that ran it would have to carry it. Held outside version control; see the register's BF-70 detail before reconstructing it.
- **NO GATE** &mdash; `npm test` over the whole suite is 2223 passing / 3 pending / 0 failing on the dev merge 9745cae2 with a live mongod. Not a gate because it needs a database on a port other sessions share, and because a whole-suite number says nothing about WHICH assertion covers this branch - the three TEST= gates above do.
- `[network]` _(cwd: `.`)_ `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/operators | grep -q .`
  - the branch behind PR #8743 is on the remote. Read-only. The tip is deliberately NOT pinned to a sha: the branch merged dev forward while it was open, so a pinned tip would go red on every merge-up and say nothing about correctness.
- `[network]` _(cwd: `.`)_ `node tools/queue/gates/pr-body-parity.js --only 8743`
  - the live body of PR #8743 still matches the file it was posted from. A correction is written into the file first, so drift runs from file to live body. It does NOT measure whether the body is true. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/60-research/remedial/bf04-bf70-operator-allowlist-2026-09-18.md`
- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/tenancy/v1-operator-census-2026-09-14.md`

**Notes.** Sequencing letter K. PR #8737 does not disallow $where or other dangerous operators and was never meant to - $where is in that branch's NON_VALUE_OPERATORS table as an exemption from type conversion, not a refusal. Measuring what API v1 actually carries is BF-04. BF-04 had been `fixed-in- seam` since 2026-09-14, high severity, live for every operator, and in no open-work list: a fix that exists only on the seam branch is invisible to operators and needs its own queue item. The allowlist and the JavaScript guard are extracted from the seam branch (seam/t2-4-allowlist 987e9657) rather than written fresh, with the framing inverted: on the seam that module is a better error message in front of a structural guard, and on dev there is no AST behind it, so there it IS the guard. lib/storage/assert-no-query-javascript.js is carried across byte-identical at the same path so the seam merge is free.

### `P0-TAG` &mdash; nightscout-connect 0.1.0 - the full release, from connector dev

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `nightscout-connect` |
| branch | `dev` |
| base | `official/dev@1946beb` |
| worktree | `externals/nightscout-connect` |
| semver | `minor` |
| review | maintainer - when to cut the full release is the decision. Pushing tag v0.1.0 on dev runs publish.yml, which waits for a reviewer from team c-r-m-dev on the npm-publish environment and then publishes to npm as `latest`. After it, merge #70 and open the next version bump on dev. |
| register | `BF-08`, `BF-34`, `BF-42`, `BF-85` |
| blocks on | `P0-CONNECT-ROLE`, `BFQ-91` |

**Blast radius.** The release is connector dev; there is no release branch. Measured 2026-09-22 at official/dev 1946beb, which declares 0.1.0: it carries 9fa2c3c, 5349d47, 77e2396 (credential-safe logging, BF-42), 8406edf (the BF-85 CareLink zero filter), 51b6e6e (listener release on stop), 234d47c (the opt-in logger, the commit cgm-remote-monitor dev pins), c1cce2a (the backoff and jitter fix, BF-08 and BF-34), LibreLinkUp v4 (#73), Glooko (#71), connector CI (#72) and the publish workflow (#74, #75). Prerelease 0.1.0-dev.1 (tag v0.1.0-dev.1 -> 1946beb) is on npm under `next`; npm's `latest` is 0.0.12. Upstream PR #70 (dev -> main) is open.

**What an operator sees.** A new version of the CGM connector, the part of Nightscout that fetches readings from a CGM vendor's online service. It stops the connector writing vendor credentials, session tokens and readings to the log, stops a CareLink "no reading" marker being stored as a glucose value of 0, and carries the retry fixes in P0-F. A test version (0.1.0-dev.1) is published for people who ask for it; the full version is not released yet, and nothing reaches Nightscout users until a Nightscout release is updated to use it (P0-PIN).

**Why `minor`.** 0.1.0, set on connector dev by PR #76: the first release carrying the backoff change (P0-F), which is caller-visible under 0.x semantics.

**Gates.**

- `[static]` `for c in 9fa2c3c 5349d47 77e2396 8406edf 51b6e6e 234d47c c1cce2a; do git -C externals/nightscout-connect merge-base --is-ancestor $c official/dev || exit 1; done`
  - all seven programme connector commits are in connector dev
- `[static]` `test "$(git -C externals/nightscout-connect show official/dev:package.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')" = 0.1.0`
  - connector dev declares 0.1.0, the version the full release must match
- `[static]` `! git -C externals/nightscout-connect rev-parse -q --verify refs/tags/v0.0.14`
  - no local v0.0.14 tag exists. RED while the retired local tag (649a7de, release/v0.0.14) is still present: it names a tree that is not the release. Delete it with `git tag -d v0.0.14`.
- `[network]` `git -C externals/nightscout-connect merge-base --is-ancestor c1cce2a "$(npm view nightscout-connect@next gitHead)"`
  - npm's `next` prerelease was built from a commit carrying the whole fix set. Read-only.
- `[network]` `git -C externals/nightscout-connect ls-remote --tags origin v0.1.0 | grep -q . && exit 1 || exit 0`
  - RULE 0. PASSES only while no v0.1.0 tag is on the remote - the machine-checkable form of "the full release has not been cut". Read-only.
- **NO GATE** &mdash; Whether 0.1.0-dev.1 has been exercised enough to cut 0.1.0 is the maintainer's judgement.

**Evidence.**

- `docs/30-design/modernization/release-readiness-15.0.9-2026-09-22.md`
- `docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`

**Notes.** 2026-09-23 - v0.1.0-dev.3 TAGGED at 977da8a and PUBLISHED to npm next with provenance (the maintainer approved the publish); Nightscout dev installs it via #8759. Still owed - the maintainer judges the prerelease tested enough, tags v0.1.0, then a Nightscout pin to exact 0.1.0 and a combined re-run. 2026-09-23 - connector dev is 977da8a after #79 (BF-97 stall fix, bounded profile fetch, update-on-change, BF-98 warning). Next: tag v0.1.0-dev.3 on 977da8a (maintainer), then the P0-PIN move to dev.3 and the combined rc re- run; exact 0.1.0 after testing. HELD 2026-09-23 (maintainer) - v0.1.0 waits for the idempotent-profile-write fix (the dev.2 soak's sync stall) in a dev.3 prerelease, and for a clear log warning when the reused nightscout-connect- reader subject has no roles (maintainer: warn clearly, don't repair; the release notes keep the manual steps). 2026-09-23 - v0.1.0-dev.2 tagged at fbd4e55 (dev, carrying BF-89 and BF-91) and published to npm next with provenance (publish run 35809963748). The longer prerelease testing the maintainer asked for starts here; v0.1.0 is still not tagged. DECIDED 2026-09-23 (maintainer) - tag 0.1.0 only after the additional needed connector fixes are merged into connector dev; the set is exactly BF-89 (P0-CONNECT- ROLE, prepared as fix/nightscout-reader-roles dea2bec) and BF-91 (BFQ-91). #54 and #52 are not required for 0.1.0. DECIDED 2026-09-23 (maintainer) - 0.1.0 is pinned in 15.0.9, but only after the prerelease has been tested longer; tagging waits for that. Before the full release, connector dev also fixes BF-89 (the nightscout source sends role for roles; P0-CONNECT-ROLE). Tagging remains the maintainer's action. DECIDED 2026-09-22 (maintainer) - tag 0.1.0 and pin it inside 15.0.9. Tagging remains the maintainer's action. The programme's local release/v0.0.14 branch and v0.0.14 tag are retired: every commit on them is in connector dev. No 0.0.14 will be published; the line is 0.1.0.

### `P0-CONNECT-ROLE` &mdash; nightscout-connect's nightscout source creates its reader subject with role, not roles (BF-89)

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `nightscout-connect` |
| branch | `fix/nightscout-reader-roles` |
| base | `official/dev@1946beb` |
| worktree | `externals/work/nc-roles-typo` |
| semver | `patch` |
| review | maintainer |
| register | `BF-89` |

**Blast radius.** lib/sources/nightscout.js (the subject it POSTs to /api/v2/authorization/subjects) and a test.

**What an operator sees.** If you use nightscout-connect to copy data from one Nightscout site to another, it creates an access entry on the source site so that it can read. That entry is created without any permission, because the field name is misspelled. If the source site does not allow anonymous reading (AUTH_DEFAULT_ROLES=denied), copying has never worked - every attempt is refused - and on the default setting the mistake is invisible. The fix gives the entry read permission as intended. IMPORTANT: an entry already created by the old version is reused and stays without permission after upgrading. Either give it the "readable" role on the source site's admin page, or delete it so the connector recreates it correctly.

**Why `patch`.** a bug fix inside the 0.1.0 line before its full release

**Gates.**

- `[static]` `sh -c 'git -C externals/nightscout-connect show official/dev:lib/sources/nightscout.js | grep -q "role: \[" && exit 1 || exit 0'`
  - FAILS while connector dev's nightscout source still sends the misspelled role field. Red on 2026-09-23 (line 83).
- `[static]` `sh -c 'git -C externals/nightscout-connect show fix/nightscout-reader-roles:lib/sources/nightscout.js | grep -q "roles: \[ .readable. \]" && ! git -C externals/nightscout-connect show fix/nightscout-reader-roles:lib/sources/nightscout.js | grep -q "role: \["'`
  - The prepared branch sends roles, and no longer sends role.
- `[unit]` `cd externals/work/nc-roles-typo && n exec 22.23.2 node --test test/nightscout-source.test.js`
  - 6 cases. Control, re-run by the coordinator 2026-09-23 - with dev's lib/sources/nightscout.js the new case fails (actual undefined, expected ['readable']) and the other 5 pass.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** MERGED 2026-09-23 - #77 (dea2bec) is in connector official/dev fbd4e55, and in prerelease 0.1.0-dev.2. Not in a full connector release yet. OPENED 2026-09-23 as nightscout/nightscout-connect PR #77 (head dea2bec, base dev) by the maintainer. The red gate reads official/dev and turns green when it merges. The one red gate reads official/dev and goes green only when the fix merges there; both branch gates pass, and the next step is a human push. PREPARED 2026-09-23 - fix/nightscout-reader-roles dea2bec on official/dev 1946beb, one commit. Measured end to end against Nightscout dev 74fc6619: under denied the created subject gets no permissions and every poll is 401 with 0 entries copied; with the fix, reads succeed and the entry arrives. Invisible on readable. Connector suite 290/290 on Node 20, 22 and 24 (dev 289/289). An existing subject is reused by name, so the release notes must carry the repair step. PR body draft at reports/connector-pr-bodies/nightscout-reader-roles.md. DECIDED 2026-09-23 (maintainer) - fix in connector dev before the full 0.1.0 release (P0-TAG). Found while checking BF-47: Nightscout's subject allow-list stores roles, so this subject is stored with no roles at all.

### `P0-PIN` &mdash; bf/connect-pin - pin dev to the published nightscout-connect 0.1.0

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `bf/connect-pin-0.1.0` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/work/crm-connect-pin-010` |
| semver | `patch` |
| review | maintainer |
| blocks on | `P0-TAG` |

**Blast radius.** One line of package.json (the nightscout-connect dependency) plus the lockfile entry that follows it (P0-LOCK). The branch today holds 0807eb1c, which points at a v0.0.14 tag tarball that will never exist; the pin replaces it.

**What an operator sees.** Nightscout picks up the new connector (the part that fetches readings from a CGM vendor's online service): the fixes that keep CGM vendor credentials and personal health data out of the log file, the CareLink "no reading" fix that keeps high and low alarms working, cleaner shutdown and the retry timing fixes. Not released; waits on the connector's full 0.1.0 release (P0-TAG).

**Why `patch`.** a dependency pin move; the behaviour change is the connector's and is classified at P0-F.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official show origin/dev:package.json | grep -q '"nightscout-connect": "0.1.0"'`
  - origin/dev pins the exact published 0.1.0 from npm. RED until that pin merges; it waits on P0-TAG.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor f61870f0 origin/dev`
  - The prerelease pin is on origin/dev: #8759's head f61870f0 (exact 0.1.0-dev.3, after #8752's 0.1.0-dev.2) is contained in dev.
- **NO GATE** &mdash; A cgm-remote-monitor dev branch can pin a prerelease (for example "0.1.0-dev.1") to test it; a cgm-remote-monitor release pins only a full connector release.

**Evidence.**

- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`

**Notes.** 2026-09-23 - state blocked on P0-TAG. dev pins exactly 0.1.0-dev.3 (#8752, then #8759 feafa533); this item's goal, the exact 0.1.0 pin, waits for the connector release. Both gates, and P0-LOCK's, now read origin/dev. 2026-09-23 - #8759 MERGED into dev as feafa533 (21:51Z): dev installs nightscout-connect exactly 0.1.0-dev.3. Combined rc rc/15.0.9-combined-36b d087588f (every open 15.0.9 PR head, #8758 and f61870f0; tree identical to feafa533 plus the other nine units) passes 3015/0/3 on Node 20/22/24 x MongoDB 4.4/7, matrix 336/336, lab NS->NS smoke 5 polls no twins or gaps (docs/30-design/remedial/rc-15.0.9-combined-2026-09-23.md). Owed before the tag: exact 0.1.0 and its pin. 2026-09-23 - dev.3 pin OPEN upstream as #8759 (head f61870f0, verified with ls-remote), CI running. 2026-09-23 - NEXT PIN PREPARED: bf/connect-pin-0.1.0-dev.3 f61870f0 on dev 1f9a9d10 (worktree externals/work/crm-connect-pin-dev3, built by session -59, verified here: one package.json token plus the lockfile's connector entry, 2 files). npm 0.1.0-dev.3 is from connector dev 977da8a (gitHead verified), integrity sha512-rkL4364OZdPM0...; suite 2386/0/3 on Node 20 and 22; debug-logging 23/23 with dev.3 (v0.0.13 fails 5). Not pushed. The combined rc re-run merges it. Exact 0.1.0 follows after testing. MERGED 2026-09-23 08:37 UTC - #8752 merged into dev as f0954a6a (dev now 1f9a9d10), although the plan had it holding for dev.3. dev, and the Docker image a dev push publishes, now install connector 0.1.0-dev.2, which carries BF-97 (Nightscout-to-Nightscout sync with a source profile stalls 20-35 min). SUPERSEDES the HELD note below. Still owed before 15.0.9 is tagged: a new PR moving the pin to the fixed connector (dev.3, then exact 0.1.0 for the release), and a combined re-run with it. HELD 2026-09-23 (maintainer) - #8752 is not merged at 0.1.0-dev.2. The dev.2 soak (docs/60-research/remedial/connector-0.1.0-dev.2-soak-2026-09-23.md, e916d3fe) found Nightscout-to-Nightscout sync with a source profile stalls: the profile is re-inserted with its source _id each poll, and since connector 808ab1c the duplicate-key error fails the whole poll (0.0.13 logged it and continued), so the destination runs 20-35 min behind. Decided: make profile writes idempotent in the connector (-29 is building it), cut dev.3, move #8752 to dev.3 and re- test, then 0.1.0. 15.0.9 waits on this. OPENED 2026-09-23 as nightscout/cgm- remote-monitor #8752 (head adf5120c, base dev) - exact 0.1.0-dev.2. Whether it merges on dev.2 or moves to exact 0.1.0 after the P0-TAG release first is open. 2026-09-23 - moved to 0.1.0-dev.2: bf/connect-pin-0.1.0 is now adf5120c (the dev.1 commit 338deb7f amended; never pushed). Lock moves only the connector entry; installed package carries #77 and #78. Suite 2386/0/3 on Node 20.20.0 and 22.23.2 against mongo:7 with nofile 64000; debug-logging 23/23, and with a checkout of tag v0.0.13 swapped in exactly 5 fail. With Docker's default nofile the suite kills mongod whichever connector is installed (BF-10). The maintainer may open this into dev now so that dev tests the prerelease; gate 1 stays red until the swap to exact 0.1.0 for the release. DECIDED 2026-09-23 (maintainer) - this pin swaps to 0.1.0 only after the prerelease testing P0-TAG now waits on, and after BF-89 is fixed in connector dev. PREPARED 2026-09-22 - bf/connect-pin-0.1.0 at 338deb7f pins exact 0.1.0-dev.1 from the registry (package.json 1+/1-, lock 4+/4-); full suite 2386/0/3 on both arms; the debug-logging control fails exactly its five cases on v0.0.13. The swap to 0.1.0 is one token plus lock regeneration once 0.1.0 is on npm; commands in reports/phase0-pr-bodies/connect-pin-0.1.0.md. Gate 1 stays red until then, by design. The old bf/connect-pin (0807eb1c) is superseded and was not modified. This closes the split GT4 found: neither dev's pin (234d47c) nor cut 4's pin carries both the logging narrowing and the redaction commits. Master pins connector tag v0.0.13. Pin the exact version rather than a range, so package.json and not only the lockfile says which connector ships. COMPATIBILITY MEASURED 2026-09-22 (connector 1946beb = v0.1.0-dev.1 source swapped into cgm-remote-monitor dev 74fc6619, no dependency change between the two): full suite 2386 passing / 0 failing / 3 pending, identical to the shipped 234d47c arm, against a private mongo:7. Red control: with v0.0.13 swapped in, tests/debug-logging.test.js fails exactly its five installed-connector cases (18 pass), so the suite distinguishes connectors. Connector's own suite 289/289 on Node 20.20.0, 22.23.2 and 24.20.0 (its CI covers only 22 and 24). Evidence: release-readiness-15.0.9 §5.2.

### `P0-LOCK` &mdash; Regenerate package-lock.json for the nightscout-connect 0.1.0 pin

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `bf/connect-pin-0.1.0` |
| base | `bf/connect-pin-0.1.0@338deb7f` |
| worktree | `externals/work/crm-connect-pin-010` |
| semver | `n/a` |
| review | maintainer - same PR as P0-PIN |
| blocks on | `P0-PIN`, `P0-TAG` |

**Blast radius.** package-lock.json, the nightscout-connect entries.

**What an operator sees.** Nothing you see. Until this is done, the install command `npm ci` fails with an out-of-sync error on this branch - which is intentional and correct, not a bug.

**Why `n/a`.** lockfile only

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official show origin/dev:package-lock.json | python3 -c "import json,sys; e=json.load(sys.stdin)['packages']['node_modules/nightscout-connect']; sys.exit(0 if e.get('version')=='0.1.0' and e.get('resolved','').startswith('https://registry.npmjs.org/') else 1)"`
  - the lockfile resolves nightscout-connect 0.1.0 from the npm registry. RED until P0-PIN's pin is written and the lock regenerated.
- `[network]` _(cwd: `externals/work/crm-connect-pin-010`)_ `npm ci --dry-run`
  - npm ci resolves against the registry

**Evidence.**

- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`

**Notes.** Regenerate with `npm install` after writing the pin, in the same PR. The integrity hash comes from the npm registry, so it exists as soon as the version is published.

### `P0-PUBLISH` &mdash; nightscout-connect publishes to npm from a version tag

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `nightscout-connect` |
| branch | `ci/npm-trusted-publish, ci/prerelease-tags` |
| base | `official/dev@1946beb` |
| worktree | `externals/nightscout-connect` |
| semver | `n/a` |
| review | done upstream |

**Blast radius.** Merged into connector dev 2026-09-22 (#74 5837abc, #75 89be9d9): .github/workflows/publish.yml, scripts/release-version.js, docs/releasing.md and test/release-version.test.js. No library code.

**What an operator sees.** Nothing changes for anyone running Nightscout. It changes how the connector is published: a version tag publishes it to npm after a person approves, with a public record linking the published package to the exact source it was built from, and with no stored npm password or token. Test versions are published separately from full releases, so installing the connector normally never picks up a test version.

**Why `n/a`.** release tooling only; no published surface of the package moves

**Gates.**

- `[static]` `git -C externals/nightscout-connect cat-file -e official/dev:.github/workflows/publish.yml`
  - the workflow is in connector dev
- `[static]` `git -C externals/nightscout-connect cat-file -e official/dev:scripts/release-version.js`
  - the tag rules are in connector dev
- `[network]` `npm view nightscout-connect@0.1.0-dev.1 dist.attestations.provenance.predicateType | grep -q slsa.dev/provenance`
  - the first package it published, 0.1.0-dev.1, carries a provenance attestation. Read-only.
- **NO GATE** &mdash; Settings outside any repository, measured 2026-09-22 with the GitHub API: environment npm-publish exists, limited to tags matching v*, with required reviewers team c-r-m-dev and self-review allowed. The npm trusted-publisher entry is not readable from here; the successful publish of 0.1.0-dev.1 shows it matches.

**Evidence.**

- `docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`

**Notes.** Tag rules (scripts/release-version.js): package.json on dev declares the version being worked on. A full release tag must equal it and publishes as `latest`; a prerelease tag must be that version plus a suffix (v0.1.0-dev.N, v0.1.0-rc.N) and publishes as `next`, with the version set in the workflow's own checkout, not committed. Anything at or below npm's `latest` is refused. The npm package has one owner account.

### `P0-T01` &mdash; T0.1 - PR #8733, the two quadratic treatment scans

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `fix/quadratic-treatment-processing` |
| base | `origin/dev` |
| worktree | `externals/work/crm-quadratics` |
| semver | `patch` |
| review | upstream reviewers on PR #8733 - not ours to land |

**Blast radius.** dfe2753d. Pushed as bewest/wip/optimize-treatment-processing.

**What an operator sees.** Sites with a lot of treatment records load faster. Nothing you see changes value or meaning. Merged into the development version (2026-09-17) and arrives with the next release (15.0.9).

**Why `patch`.** performance only

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor dfe2753d origin/dev`
  - containment: the measured tip of bewest/wip/optimize-treatment-processing is in origin/dev, so the merge carried it. Holds after the branch moves or is deleted; reads local remote-tracking refs, so fetch origin first.
- **NO GATE** &mdash; PR merge state is upstream's and cannot be gated from here without a GitHub API call. This item is tracked, not driven.

**Evidence.**

- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** The plan says "everything downstream assumes it". PR #8733 merged into dev on 2026-09-17; not released.

### `FU-LIMIT` &mdash; Follow-up 2 - the limit rule is written twice, and that is the root cause

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-reads` |
| semver | `patch` |
| review | maintainer - this is the design debt the whole read-path family came out of, so it deserves a reviewer who has read that family |
| blocks on | `P0-E` |

**Blast radius.** lib/server/count.js (which bf/reads CREATES) and lib/api3/generic/collection.js parseLimit. Two readings of one rule.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `patch`.** Unifying two implementations of one rule that already agree. If it changes an answer, the change belongs to whichever fix moved, not to this.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official cat-file -e origin/dev:lib/server/count.js 2>/dev/null && git -C externals/cgm-remote-monitor-official show origin/dev:lib/api3/generic/collection.js | grep -q "self.parseLimit" && exit 1 || exit 0`
  - CONTROL, and it PASSES. The sequencing document says the rule is written twice, in lib/server/count.js and v3's parseLimit; count.js does not exist on origin/dev - bf/reads creates it. So the duplication does not exist yet and this follow-up is created by P0-E landing.
- `[static]` `git -C externals/cgm-remote-monitor-official cat-file -e bf/reads:lib/server/count.js 2>/dev/null && git -C externals/cgm-remote-monitor-official show bf/reads:lib/api3/generic/collection.js | grep -q "self.parseLimit" && exit 1 || exit 0`
  - FAILS on bf/reads, where both readings of the rule are present. Paired with the control above, a red here is the duplication and not the command - the identical command run against origin/dev exits 0.
- **NO GATE** &mdash; Nothing asserts that the two implementations AGREE while they both exist. A differential test - the same limit value through both paths, including 0, a negative, a non-numeric and a value above the maximum - is what would make the duplication safe until it is removed, and it does not exist. Two readings of one rule is the root cause of this whole family, so leaving it duplicated is a debt with a name.

**Evidence.**

- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`

**Notes.** Follow-up #1 in the same list is resolved by the combination - BF-01 delegates to each collection's query_for, which already names its collection, so coercion's option reaches query.js on the count path. What remains there is an end-to-end test asserting it, which does not exist, and it is not this item.

### `FU-RESIDUALS` &mdash; Follow-ups 3, 4, 7 - three named residuals beside branches already prepared

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `patch` |
| review | maintainer. Follow-up 7 sits beside a line bf/alarms changed; the other two are independent. |

**Blast radius.** Three one-line changes in three files - lib/plugins/index.js:241, lib/authorization/storage.js:82, lib/api/alexa/index.js switch (line numbers on origin/dev 74fc6619).

**What an operator sees.** One of these three is visible to you. If an Amazon Alexa request arrives that Nightscout does not recognise, Nightscout answers nothing at all and the request hangs until Alexa gives up, rather than saying it did not understand (the fix answers without speech, because Amazon does not accept a spoken reply to these request types). The other two are internal - a check that always answers "yes" but that nothing currently asks, and a leftover log line that prints request details to the server log.

**Why `patch`.** Three bug fixes. None moves a declared surface. The alexa change adds a response where there is currently none, which is a repair of a hang rather than a new capability.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official show origin/dev:lib/plugins/index.js | grep -q "return (p !== null)" && exit 1 || exit 0`
  - Follow-up 3. FAILS today - plugins.isPluginEnabled compares find()'s result with !== null, and find() returns UNDEFINED when it misses, so the function always returns true. No caller today, which is why it has no register id, but it is what the next instrument will reach for.
- `[static]` `git -C externals/cgm-remote-monitor-official show origin/dev:lib/authorization/storage.js | grep -qE "console\\.log\\('Loading',[[:space:]]*opts\\)" && exit 1 || exit 0`
  - Follow-up 4. FAILS today. BF-05's unfixed sibling - the same shape, a different file. The shipping source is console.log('Loading',opts) with NO SPACE after the comma, and several documents quote it with a space; a pattern copied from them matches nothing and passes while the defect is present. This pattern is space-tolerant, shared with P0-C's gate so the two cannot diverge. The line is storage.js:82 on origin/dev 74fc6619; line numbers quoted elsewhere may refer to bf/auth. This gate measures origin/dev, which is where the fix has to land.
- `[static]` `bash -c 's=$(git -C externals/cgm-remote-monitor-official show origin/dev:lib/api/alexa/index.js); echo "$s" | grep -q "switch (req.body.request.type)" || exit 1; echo "$s" | grep -q "default:"'`
  - Follow-up 7. FAILS today. The switch on request.type has no default, so an unrecognised type calls neither res.json nor next() and the request hangs until the client times out. The first clause is the control - it asserts the switch is still there, so a red result cannot come from the file having been restructured. Measured: 0 occurrences of "default:" in the file. googlehome has no switch at all, so this is alexa-only.
- **NO GATE** &mdash; Reachability of follow-up 7 is not measured. It needs an Alexa request type outside SessionEndedRequest, LaunchRequest and IntentRequest, and nothing here enumerates what Amazon can send.

**Evidence.**

- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`

**Notes.** PREPARED 2026-09-22 on bf2/ops - follow-up 3 at e72ba30d, follow-up 7 at af8eee45; each test fails on dev with the original symptom. Correction to operator_visible - Amazon forbids a spoken reply to these request types (System.ExceptionEncountered, SessionEndedRequest), so the fix answers with an empty 200, mirroring the SessionEndedRequest branch, rather than saying it did not understand. Three small residuals the sequencing document named together, each one file and each measurable. Follow-up 4 (the console.log in lib/authorization/storage.js) is fixed on bf/auth as commit ce82f0cd and must not be fixed here as well - this is a cross-reference, not a second item. Its gate fails, correctly, because it reads origin/dev and P0-C has not merged; when P0-C merges it goes green on its own and only follow-ups 3 and 7 remain. Follow-up 7 sits beside the ctx.language.set(locale) line that bf/alarms (P0-A, merged) changed.

### `FU-PRBODIES` &mdash; Merged PR bodies have drifted from the files they were posted from

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | MAINTAINER, and the decision is narrow: are merged pull request bodies worth correcting at all? For: a merged PR body is the durable public record of why a change was made, and four of these cite file paths that 404 for anybody who follows them. Against: few people read a merged PR body and the edit costs a push. If the answer is yes, #8739 must be handled differently from the other four. Its live body is ahead; the upstream text has to be reconciled INTO reports/phase0-pr-bodies/bf-alarms.md before anything is pushed, or that work is destroyed. A one-way `gh pr edit <pr> --body-file <local>` on #8739 would overwrite it and then report green. Do not restore #8743, #8744 or #8745 to their long form, and do not overwrite them from any file, until a release containing their fixes ships and the advisories are published. |
| ships to operators today | no (pre-release) |

**Blast radius.** No code. Pull request bodies and the files under reports/phase0-pr-bodies/ they were posted from. Measured 2026-09-23 by tools/queue/gates/pr-body- parity.js over its eight pairs: #8738, #8740 and #8743 match; #8734, #8735, #8736, #8737 and #8739 differ. The drift runs in two directions. #8734, #8735, #8736 and #8737 differ only in documentation paths - the local files were updated when the docs tree moved into programme subdirectories, so the LIVE bodies still cite the pre-move spellings (the backfix register without its `remedial/` segment, the semver classification without `modernization/`), and those paths no longer resolve. The spellings are deliberately not written out here: doc-links.js gates this file, and a dead path quoted in a note is indistinguishable to it from a dead path being relied on. Word counts are identical each way. #8739 is the opposite: the live body is 1640 words to the file's 1537 and carries paragraphs the file does not have - the urgent- severity versus notification-delivery distinction, and a note about Alexa and Google Home locale handling - added upstream after posting. #8743, #8744 and #8745, the three advisory fixes, were edited on GitHub on 2026-09-23 (00:28:08Z to 00:28:11Z) from the maintainer's account to withhold detail until a fixed release ships and the advisories are published; each now opens "Details withheld". They are 396, 189 and 318 words (`wc -w`). bf-operators.md was trimmed to #8743's text the same day; the full text is at 9ddad0cc (2641 words) for restoring after release. #8744 and #8745 have no file under reports/phase0-pr-bodies/, so the gate does not see them; their full drafts are under docs/30-design/remedial/advisory-response-2026-09/pull-requests/.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation of changes already merged; no shipped behaviour

**Gates.**

- `[network]` `node tools/queue/gates/pr-body-parity.js`
  - All eight bodies match their files. Red with five failing as of 2026-09-23. Read-only - it fetches bodies and never edits one. Its direction advice is a word-count heuristic: read the PR's last-edited time before acting on it.
- **NO GATE** &mdash; Whether a body is TRUE is not measured by anything here, and parity with a wrong file is still parity. Figures in these bodies have been wrong before - bf/parms had two, bf/reads had four - and only re-running the claim catches that.
- **NO GATE** &mdash; Nothing gates the reconciliation of #8739. Merging upstream prose into a local file is an editorial act; a gate can say the two differ and cannot say the merge was faithful.

**Evidence.**

- `tools/queue/gates/pr-body-parity.js`
- `reports/phase0-pr-bodies/bf-alarms.md`

**Notes.** DECIDED 2026-09-23 (maintainer) - fix only the dead links in the bodies of #8734-#8737; do not otherwise re-sync them. Reconcile #8739 the other way: its file follows the live body. #8743-#8745 are withheld and are not touched until release. The parity gate belonged to eight Phase 0 items that are all merged- upstream, so its red reads as expected post-merge noise on rows nobody revisits; this item gives it an owner. No PR body was edited; all twelve Phase 0 and advisory PR bodies were read on 2026-09-23 with their last-edited times.

### `FU-HYGIENE` &mdash; Follow-ups 9, 10 - the two audits that have no instrument

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer |

**Blast radius.** An audit and a lint or test-harness rule. No production source is expected to change, which is exactly what makes the result worth having.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** test and lint hygiene; no shipped surface

**Gates.**

- **NO GATE** &mdash; Follow-up 9 - audit the suppressions OUTSIDE lib/: detect-non-literal-fs-filename, detect-possible-timing-attacks, no-cond-assign. There is no instrument because the audit IS the work: object-injection's 34 suppressed lines yielded five real defects (BF-35, BF-36, BF-37, BF-38 and BF-39), and the same reasoning applies to each remaining category. What could be gated afterwards is a rule that no NEW suppression is added without an entry, and that rule does not exist.
- **NO GATE** &mdash; Follow-up 10 - jsdom test hygiene has no enforcement. A suite that sets global.window or global.document must restore them in afterEach or it breaks browser-settings.test.js later in the same run. hashauth.modern.test.js does the restore; nothing requires it, and the failure lands in a DIFFERENT file from the one that caused it, which is the shape that costs the most review time. The instrument is a harness-level check, and cut 1 retires jsdom entirely, so it should be decided against the release train rather than built twice.

**Evidence.**

- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`

**Notes.** Both are unmeasured and say so. They are in the queue because the sequencing document listed them, and because the first is how five of the Phase 0 defects were found - the trivial lint rule was the best signal in the programme.

---

## Modernization release train

`parcel: release-train` &mdash; 16 items

The adopted order (maintainer, 2026-09-15): 15.0.9, then cut 1, then cut 2,
then cuts 3+5 combined, then a deprecation release, then cut 4. The premise of
"zero rebase work" was measured false (GT2); the rebase items here are what
that costs.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `RT-D3` | Answer the D3 question before 15.0.9 ships | `in-progress` | `origin/dev` | minor | 2 run + 1 no-gate |
| `RT-VERSION` | Two artefacts claim version 15.0.9 with different Node floors | `not-started` | `-` | n/a | 1 run + 1 no-gate |
| `RT-COUNT0` | v1 ?count=0 answers an empty list, amending #8738 before 15.0.9 | `merged-upstream` | `bf/count-zero-empty` | patch | 2 run |
| `RT-MONGO-FLOOR` | README: MongoDB 4.4 is deprecated, not unsupported, in 15.0.9 | `merged-upstream` | `docs/mongodb-floor` | patch | 2 run |
| `RT-COUNT-COMPAT` | Two real clients meet the 15.0.9 count rule: a correction or a compatibility break? | `needs-decision` | `-` | n/a | 0 run + 1 no-gate |
| `RT-REBASE` | Cuts 1-4 are 133 commits behind dev and now all five conflict | `gate-not-met` | `chore/retire-jsdom, chore/build-runtime-separation, chore/compose-mongodb6, chore/mime-exposure-review` | n/a | 6 run + 1 no-gate |
| `RT-0` | Release 15.0.9 | `needs-decision` | `origin/dev` | minor | 1 run + 2 no-gate |
| `RT-1` | Cut 1 - chore/retire-jsdom | `blocked` | `chore/retire-jsdom` | major | 2 run + 2 no-gate |
| `RT-2` | Cut 2 - chore/build-runtime-separation | `blocked` | `chore/build-runtime-separation` | minor | 1 run + 1 no-gate |
| `RT-3` | Cuts 3+5 combined - dependency release | `blocked` | `chore/nightscout-modernization` | major | 1 run + 2 no-gate |
| `RT-4` | Deprecation release - recommended folded into 15.0.9's release notes | `merged-upstream` | `-` | minor | 1 run + 1 no-gate |
| `RT-5` | Cut 4 - chore/mime-exposure-review, the one to slow down on | `blocked` | `chore/mime-exposure-review` | major | 2 run + 2 no-gate |
| `RT-CONNECT-PIN-CUTS` | BF-65 - cuts 1-3 ship the leaking connector to upgraders first | `gate-not-met` | `chore/retire-jsdom, chore/build-runtime-separation, chore/compose-mongodb6` | patch | 1 run + 1 no-gate |
| `RT-NODE-FLOOR-TESTED` | BF-58, BF-59 - the enforced Node floor is not the Node anything exercises | `gate-not-met` | `chore/compose-mongodb6, chore/mime-exposure-review, chore/nightscout-modernization` | n/a | 2 run + 2 no-gate |
| `RT-BOOTERROR` | BF-63 - the page that reports a boot error crashes on cut 4's boot errors | `gate-not-met` | `-` | patch | 2 run + 1 no-gate |
| `BF2-BACKPORT` | Which modernization-only security commits fix a defect that dev has | `merged-upstream` | `bf2/backports` | n/a | 2 run + 1 no-gate |

### `RT-D3` &mdash; Answer the D3 question before 15.0.9 ships

| | |
|---|---|
| state (claimed) | `in-progress` |
| repo | `cgm-remote-monitor` |
| branch | `origin/dev` |
| base | `origin/master` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer - this is the decision the adopted train puts first |
| register | `BF-54`, `BF-57` |

**Blast radius.** Commit 48075a18 touches three production files - lib/client/renderer.js +25/-25, lib/client/chart.js +2/-2, lib/report_plugins/daytoday.js +3/-3, 30 lines in all (GT2, 2026-09-15). The 2026-09-14 release-readiness document lists five files; three is the measured figure.

**What an operator sees.** The charts on the main page were rebuilt on a new version of the drawing library. What is being checked is whether dragging a treatment on the chart still behaves - because dragging one changes the time that treatment is recorded at, and insulin-on-board and carbs-on-board are calculated from that time.

**Why `minor`.** GT4: D3 5.16 -> 7.9 by itself moves NO declared surface, so it forces neither minor nor major. 15.0.9 is a minor for reasons independent of D3 - lib/server/env.js gains DEBUG_LOGGING and CONNECT_DEBUG, debug logging flips to off by default, and a new lib/api2/loop-notification-errors.js appears.

**Gates.**

- `[unit]` `sh -c 'd=$(mktemp -d) && git -C externals/cgm-remote-monitor-official archive origin/dev | tar -x -C "$d" && ln -s "$PWD/externals/cgm-remote-monitor-official/node_modules" "$d/node_modules" && cd "$d" && NODE_ENV=test ./node_modules/.bin/mocha --timeout 15000 --require ./tests/hooks.js --exit tests/dependency-d3.test.js; r=$?; rm -rf "$d"; exit $r'`
  - Runs origin/dev's own tree (git archive), not the checkout's working tree, which is not kept at dev. 24 passing (GT2), driving the real renderer and chart against the D3 7 browser bundle. Non-vacuous: it catches reverting mouseover handlers to the D3-5 signature and catches breaking d3.pointer.
- `[static]` `node tools/queue/gates/d3-drag-clamp-covered.js`
  - The coverage gap. With BOTH treatment-drag clamps deleted (renderer.js:764 and 770-771) the suite stays at 24/24 - the handler runs 25 times with only x in {20,400}, all strictly inside 0..900, so the boundary is never reached (GT2). This gate re-runs that ablation and FAILS while the clamps are uncovered.
- **NO GATE** &mdash; lib/plugins/cob.js +49/-73 is filed under the D3 heading in release-readiness §2 and is NOT D3 work - it is 34e9b2da, "fix(cob): use the COB reported by the uploading system". It is more than twice the size of the entire D3 migration, it changes what a user reads when deciding about food and correction, and it has no line of its own in the 15.0.9 release decision. Nothing gates it because nobody has decided what it is.

**Evidence.**

- `docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`
- `docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md`
- `docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md`

**Notes.** 2026-09-23 - both gates measure again. They had been red without testing anything: dev's suite refuses to run unless NODE_ENV=test, the unit gate ran the official checkout's working tree (a8888f0d, not dev) without my.test.env, and the ablation gate borrowed node_modules from an old worktree. Now: the unit gate passes on origin/dev ddd9b600 (24 passing); the ablation gate's control passes (24) and deleting the three drag clamps still leaves 24 passing. That is the known mocha-suite gap, and the browser probe tools/review/probes/rt-d3-drag-browser.js covers it (2 of 19 checks go red without the clamps). Whether the mocha gap must close before RT-D3 counts as answered for RT-0 is the maintainer's call. 2026-09-23 - BOTH HALVES DONE for 15.0.9. Manual check passed by hand on the combined rc ec70aab0 (-6d): mouse in mg/dL and mmol/L, and touch, same as 15.0.8. Automated half as recorded below. The drag clamps behave as on 15.0.8. Found on the way, pre-existing on 15.0.8 and not a D3 regression: BF-103 (a split drag stores the old time, so IOB and COB ignore the move), tracked as BFQ-103. DECIDED 2026-09-23 (maintainer) - answered two ways: a manual check in a browser, plus an automated browser test (possibly driven through a Chrome DevTools MCP as a hybrid). The automated half has a first run: docs/60-research/modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md (7e86ab91) finds 15.0.8 and dev identical on every drag measured, with 0 page errors, and deleting the clamps turns 2 of 19 checks red. Its probe, tools/review/probes/rt-d3-drag-browser.js, was untracked then; it is committed now. The manual check was done by hand on 2026-09-23 (note above; docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md). The clamps bound a user-initiated rewrite of a treatment's created_at emitted over the socket, and a treatment's timestamp is what IOB/COB key off. They are the exact lines the D3 6 migration rewrote and the least covered lines it touched.

### `RT-VERSION` &mdash; Two artefacts claim version 15.0.9 with different Node floors

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `-` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer |
| register | `BF-60` |

**Blast radius.** package.json "version" on origin/dev and all five cut tips.

**What an operator sees.** Right now two quite different builds of Nightscout both call themselves 15.0.9 - one runs on Node 20, one refuses to start on anything below Node 22.23.2, and one of them removes two ways of getting CGM data in. If you report "my 15.0.9 will not start", nobody can tell from the version number which one you have.

**Why `n/a`.** this item IS the versioning decision

**Gates.**

- `[static]` `node tools/queue/gates/version-collision.js`
  - FAILS while origin/dev and any cut tip carry the same package.json version string (GT4's finding, as a measurement).
- **NO GATE** &mdash; Both cut-4 migration shims emit error text saying "retired in Nightscout 15.0.9", but on the adopted train 15.0.9 is the bug-fix release and retires nothing. Nothing checks error strings against the release they name.

**Evidence.**

- `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`

**Notes.** DECIDED 2026-09-22, amended 2026-09-23 (maintainer) - the dev to master release is 15.0.9. #8743 ships as-is. #8738 is amended before the tag (RT- COUNT0): ?count=0 answers an empty list, malformed counts stay HTTP 400, saves and updates ignore count, and a delete with an invalid count (0 included) is still refused. Both are declared as corrections in the release notes, with no compatibility flag. The cut tips still need distinct numbers - DECIDED 2026-09-23: each cut is renumbered when it is rebased; see docs/30-design/remedial/backfix-2-plan-2026-09-22.md. Given the governance gap - 100 self-merged PRs, zero human reviews - the version number is the only warning an operator gets, and right now it does not distinguish these builds.

### `RT-COUNT0` &mdash; v1 ?count=0 answers an empty list, amending #8738 before 15.0.9

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/count-zero-empty` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/work/crm-count-zero` |
| semver | `patch` |
| review | maintainer |

**Blast radius.** Tip ce9503ac, two commits, 5 files - lib/server/count.js (isZeroCount; applyCount answers zero without querying), lib/api/index.js validateCount (GET/HEAD - zero allowed; DELETE - dev's rule, zero refused; POST/PUT/PATCH - not checked), lib/api/devicestatus/index.js (kept 0 instead of its default 10), lib/server/profile.js list(), and tests/api.count-parameter.test.js.

**What an operator sees.** 15.0.9 will refuse a request for a nonsense number of records (for example "abc" or "-3") with an error, where earlier versions guessed a number. A request for zero records will answer with an empty list, not an error and not the whole collection. Uploading data is not affected.

**Why `patch`.** narrows #8738's new refusal before any release has shipped it

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/count-zero-empty >/dev/null`
  - Merges into origin/dev with no conflict.
- `[integration]` `cd externals/work/crm-count-zero && TEST=api.count-parameter npm run test-single`
  - 36 cases at ce9503ac (the env file expects mongo on 127.0.0.1:27087, which must be started first). Break-its, re-run 2026-09-23 at ce9503ac - zero back to unbounded (applyCount only) fails 8, zero back to 400 on reads fails 11, deletes skipping the check (the first commit) fails 6, deletes letting zero through fails 3, deletes refusing every count fails 1. The 8 delete cases pass on dev by design; they pin dev's rule.

**Evidence.**

- `docs/30-design/remedial/backfix-2-plan-2026-09-22.md`

**Notes.** 2026-09-23 - the merged rule may be reopened before the tag: oref0 and GluPredKit send count shapes it refuses or answers empty. Tracked as RT-COUNT- COMPAT (a semver and compatibility decision, not a defect). MERGED 2026-09-23 into dev (now 4011193e); NOT RELEASED. #8748 as 42c5e21e (head fc2d25ca). CI and CodeQL green on the merge commit. 2026-09-23 - CodeQL on #8748 reported 2 high alerts, both in the test file: the write suites built the api-secret header with sha1(API_SECRET) at run time. d19043b2 (local, not pushed) uses the precomputed header value the other API tests use; test-only, 36/36. OPENED 2026-09-23 as nightscout/cgm-remote-monitor #8748 (head ce9503ac, base dev). REVERSED 2026-09-23 (maintainer) - the record below that the maintainer "accepted that a DELETE ignores count" is withdrawn; the maintainer had not realised the branch changed dev's delete behaviour. A DELETE carrying a count that is not a whole number of 1 or more, count=0 included, is refused with 400 and deletes nothing, as on dev. A valid count on a DELETE is accepted and, as on dev, does not limit it. Saves and updates still ignore count. Implemented as ce9503ac on top of the pushed 7b32d9ab; suite Node 20.20.0 2409/0/3. Not yet pushed. WITHDRAWN - accepted that a DELETE ignores count, so a delete carrying count=0 removes everything its filter matches, as 15.0.8 already did. PREPARED 2026-09-23. Read matrix (30 entries, 120 treatments, 30 devicestatus, 15 profile, 15 activity, counted in mongo) - the ONLY change from dev is the 0 and 00 columns, now 200 with no rows on every v1 read route; 0x10, 2.5, -3, 1e2, abc, MAX_SAFE+1, %2B5 and count=1&count=2 stay 400. Suite Node 20.20.0 - dev 2386/0/3, branch 2404/0/3. FOR THE MAINTAINER, measured - (1) dev (#8738) refuses every WRITE that carries any invalid count, including count=0, with 400 and no change; the branch makes writes ignore count as decided. (2) Neither tree limits a DELETE by count - DELETE with a find and count=2 removed all 5 matching rows on both - so on the branch a delete carrying count=0 removes everything its filter matches, where dev refused it. (3) Routes that never apply count (/entries/current, /count/.../where, /status, /echo, /food) now answer count=0 normally instead of 400. (4) v1 now accepts zero while v3 limit=0 stays 400, so FU-LIMIT's "two implementations that agree" no longer holds. PR body draft at reports/phase0-pr-bodies/count-zero-empty.md. DECIDED 2026-09-23 (maintainer) - "count=0 should return a 0 length array of results." #8738 (merged to dev) answers HTTP 400 for count=0 because MongoDB reads .limit(0) as no limit; the maintainer wants an empty list instead. Malformed counts stay 400, and the check runs on read routes and deletes (see REVERSED above); saves and updates ignore count. Ships in 15.0.9.

### `RT-MONGO-FLOOR` &mdash; README: MongoDB 4.4 is deprecated, not unsupported, in 15.0.9

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `docs/mongodb-floor` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `patch` |
| review | maintainer |

**Blast radius.** README.md, one line of the installation requirements. No code.

**What an operator sees.** The installation instructions said MongoDB 4.4 no longer works with this version. It does still work and is still tested. 15.0.9 will say instead that 4.4 is deprecated and support will be removed in a later release, so plan to upgrade the database one major version at a time.

**Why `patch`.** documentation only

**Gates.**

- `[static]` `sh -c 'git -C externals/cgm-remote-monitor-official show docs/mongodb-floor:README.md | grep -q "MongoDB 4.4 is \*deprecated\*"'`
  - the prepared branch carries the deprecation wording
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev docs/mongodb-floor >/dev/null`
  - the branch merges into dev without conflict

**Evidence.**

- `docs/30-design/remedial/backfix-2-plan-2026-09-22.md`

**Notes.** MERGED 2026-09-23 - #8750 is in dev (1f9a9d10). Not released. OPENED 2026-09-23 as nightscout/cgm-remote-monitor #8750 (head aabce4b1, base dev). DECIDED 2026-09-23 (maintainer) - deprecate 4.4 now, drop it later. Prepared as aabce4b1 by the other session; this item was added 2026-09-23 because the branch had none. The commit message serves as the PR body (gh pr create --fill).

### `RT-COUNT-COMPAT` &mdash; Two real clients meet the 15.0.9 count rule: a correction or a compatibility break?

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@ddd9b600` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer - a semver and compatibility decision, with a safety dimension on the oref0 side |

**Blast radius.** The v1 count rule from #8738 as amended by #8748 (lib/server/count.js, lib/api/index.js validateCount), and the number 15.0.9 ships under.

**What an operator sees.** Some apps ask Nightscout for records in a way this release reads more strictly than 15.0.8 did. OpenAPS (oref0) asks for its latest treatment with a malformed count and would get an error; GluPredKit asks for "zero" records meaning "all of them" and would get none. What changes, and how the release notes describe it, is being decided before 15.0.9 ships.

**Why `n/a`.** this item decides whether the count rule is patch, minor or major

**Gates.**

- **NO GATE** &mdash; Reproduced end to end on 15.0.8, dev ddd9b600 and the candidate tree 2ce67b27 with a control in each run (consumer-replay lab, -6a, 2026-09-23). Nothing gates the decision itself; it is the maintainer's.

**Evidence.**

- `docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`

**Notes.** 2026-09-23 - REPLAY VERDICTS (-6a lab; docs/60-research/remedial/consumer- impact-15.0.9-2026-09-23.md). oref0: 15.0.8 200, dev and candidate 400 in both auth modes under readable and denied; the plain count=1 control is 200 everywhere. Through oref0's own jq/date pipeline the rig re-uploads 57 treatments per loop instead of 1. NO DUPLICATES: 137 records after each of three posts, because the created_at+eventType upsert is idempotent. A Nightscout-side edit to a rig treatment from the last 24 h is overwritten on the next loop; that replace also happens on 15.0.8, but only 15.0.9 makes the rig re-post every loop. GluPredKit: count=0 returns [] for profile, treatments and entries on dev and the candidate (15.0.8: 1 / 137 / 576 in a 50 h window); the count=100000 control is full on all three. Filed 2026-09-23 from the -6a consumer-impact survey, on the maintainer instruction to document it as a compatibility and semver item, not a backfix. oref0 (dev d219baf9, master 88cf032a) sends count as "1?<credential>" from latest-openaps-treatment; 15.0.8 parseInt read 1, 15.0.9 answers 400. GluPredKit sends count=0 as "no limit"; 15.0.9 answers []. Under the semver policy rule (section 3.2) both make the narrowing major as written. Options, in outline - ship as a declared correction naming both clients; tolerate the shapes real clients send and keep 15.0.9 a patch; or number the release as a major. The release notes count section carries a hidden OPEN BEFORE THE TAG note.

### `RT-REBASE` &mdash; Cuts 1-4 are 133 commits behind dev and now all five conflict

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `chore/retire-jsdom, chore/build-runtime-separation, chore/compose-mongodb6, chore/mime-exposure-review` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer - this changes the cost of the adopted train |
| register | `BF-55`, `BF-56` |

**Blast radius.** Measured 2026-09-21 against origin/dev 74fc6619 (re-checked 2026-09-22, dev unchanged). Published cuts 1-4 are each 133 commits behind dev; the missing commits are 148 files, +8111/-304. Conflicting paths under merge-tree: cut 1 seven (lib/plugins/pluginbase.js, lib/server/bootevent.js, package.json, package-lock.json, plus three modify/delete - tests/clock-client.test.js, tests/pluginbase.modern.test.js, tests/profile-sinks.test.js); cut 2 fourteen; cut 3 sixteen; cut 4 eighteen. Reproduce the distance with `git -C externals/cgm-remote-monitor-official rev-list --left-right --count origin/dev...origin/chore/retire-jsdom` (and likewise per cut). Cut 5 (origin/chore/nightscout-modernization) is 9 behind dev and 498 ahead, with one conflict, lib/server/bootevent.js: 74731433, the BF-77 boot-notice fix merged as PR #8746, is the only commit in 59430336..74fc6619 touching that file, and cut 5 edits it too. Where the conflicts come from, measured: every one of the seven files that newly conflict on cuts 2-4 since a8888f0d - lib/server/query.js, lib/server/aggregate.js, lib/api/entries/index.js, lib/authorization/storage.js, lib/server/food.js, lib/client/boluscalc.js and tests/mongo-query-javascript.test.js - was touched by the Phase 0 PRs merging into dev. On 2026-09-15 the cuts were 59 behind with 4-5 conflicting files each. Merging the backfixes was right - they fix defects on the shipping path - and each further merge to dev raises the cost of leaving the cuts unrebased.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** rebase mechanics, not a release

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/retire-jsdom >/dev/null`
  - cut 1 trial-merges into dev cleanly - FAILS as of 2026-09-22
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/build-runtime-separation >/dev/null`
  - cut 2 trial-merges into dev cleanly - FAILS as of 2026-09-22
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/compose-mongodb6 >/dev/null`
  - cut 3 trial-merges into dev cleanly - FAILS as of 2026-09-22
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/mime-exposure-review >/dev/null`
  - cut 4 trial-merges into dev cleanly - FAILS as of 2026-09-22
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/nightscout-modernization >/dev/null`
  - cut 5 trial-merges into dev cleanly - FAILS as of 2026-09-22, one conflict in lib/server/bootevent.js (from PR #8746). Because it is red it cannot show the command is capable of going green; the gate below does that.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/dev >/dev/null`
  - Control arm. Merging dev with itself must succeed. If this goes red then merge-tree, the repository or the ref is broken and the five failures above say nothing about the cuts. Deliberately trivial: a control fails only for the reason it names.
- **NO GATE** &mdash; The sharpest cost is a NON-mechanical conflict and no command can resolve it. dev's 06372e1d adds 56 lines to tests/clock-client.test.js covering the low-and-falling clock concern; cut 1 DELETES that file as part of jsdom retirement (b95ee628), and cut 1's Playwright replacement has ZERO references to concern or falling (positive control: 3 hits on dev). Resolving the conflict the obvious way keeps the production fix and loses its only test, on a screen people read at a glance. The same modify/delete shape covers tests/pluginbase.modern.test.js and tests/profile-sinks.test.js on all four cuts. Nobody has checked what those two cover or whether cut 1's replacements reach it.

**Evidence.**

- `docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`

**Notes.** A rebase is prepared locally (2026-09-21, on the maintainer's instruction) in externals/work/crm-cuts: rt/cut1 77d6ffaf, rt/cut2 6106332e, rt/cut3 5bff9225, rt/cut4 8a692d88. NOT PUSHED. The published cut branches the gates measure are unchanged. Method: dev was propagated UP the stack (dev into cut 1, cut 1 into cut 2, and so on), so the prefix property is preserved and cut 1's resolutions are inherited. Measured: each cut is an ancestor of the next, each contains origin/dev, and all four trial-merge into dev cleanly. Propagation needed 7 conflict resolutions at cut 1, then 9 / 5 / 4, against the 14 / 16 / 18 each would have had against dev directly. Nine of the 25 conflicts were Phase 0 fixes the cuts predate, and taking the cut's side would have reintroduced each: BF-01 (?count=0 answering with the whole collection), BF-07 (cloning the retained window), BF-16 and BF-35 (the bolus calculator quick-pick filter and chooser), BF-36 (delta merge past the end), plus the BF-04 allowlist and BF-70 pipeline refusal. All seven verified present on cut 4 after the merges. The cut 5 tip carries only two thirds of BF-07, and these branches do not copy that: b1bdaca0 keeps getDataRef in lib/server/cache.js and both lib/data/dataloader.js callers but reverted lib/api/entries/index.js to getData - origin/dev has 7 occurrences under lib/, b1bdaca0 has 6, these branches have 7. Worth raising against e3b22034 upstream. The connector pin at cut 4 was a real fork: dev's 234d47c8 and cut 4's c962a13f are neither an ancestor of the other, so either side loses something. Resolved to b77e5bb7, which has both, is pushed to the connector remote, and is what the local tip pins. Every connector commit in b77e5bb7 is also in connector dev and in the 0.1.0 line, so when the rebased cuts land they move to the same exact npm pin as dev (P0-PIN, RT-CONNECT-PIN-CUTS). Test results on Node 24.20.0 against mongod 7.0.43 (the Node version matters - see RT-NODE-FLOOR-TESTED): cut 1 348 passing, cut 2 357, cut 3 324, cut 4 310, zero failures. Counts differ because later cuts remove suites (cut 4 retires the bridge and mmconnect tests). Cut 1's ported browser coverage was ablated: removing dev's 06372e1d takes it from 21 passing to 12 passing / 9 failing, so it measures the fix. Not done: the coverage of tests/pluginbase.modern.test.js and tests/profile-sinks.test.js, both deleted by cut 1's jsdom retirement, has not been audited against cut 1's Playwright replacements - 12 it() cases in the first and 6 in the second are unaccounted for. Only clock-client's was audited, because it had a named production fix behind it. Release-readiness §5's "each costs zero rebase work today" was false when written: the cut tips date to 2026-09-05/06 and dev's tip to 2026-09-09. "0 commits behind dev" was true of the stack tip only, because of one commit, 0a4109f6.

### `RT-0` &mdash; Release 15.0.9

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `origin/dev` |
| base | `origin/master` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer, and at least one human reviewer who is not the author. Release PR #8598 (dev -> master) was, on 2026-09-22, open, mergeable and green on every CI check, with reviewDecision REVIEW_REQUIRED and zero approving reviews. Integration PR #8605 carries the modernization cuts (RT-3), not this release. |
| blocks on | `RT-D3`, `RT-VERSION` |

**Blast radius.** 15.0.9 is everything in origin/master..origin/dev: master 92d08342 (tag 15.0.8) to dev 74fc6619, measured 2026-09-22. 308 commits, 48 first-parent merges, 200 files, +14381/-1262. Among them the thirteen backfix PRs from this programme (#8733, #8734, #8735, #8736, #8737, #8738, #8739, #8740, #8743, #8744, #8745, #8746, and #8741 from an external contributor on the same work), the D3 5.16 -> 7.9 chart migration (RT-D3), the opt-in debug logging change (#8726), profile, treatment-query and clock fixes, report and chart fixes, dependency updates and translations. Reproduce with `git -C externals/cgm- remote-monitor-official log --first-parent --oneline origin/master..origin/dev` and `git diff --shortstat origin/master origin/dev`.

**What an operator sees.** Version 15.0.9 is the next Nightscout release. Nothing below reaches your site until 15.0.9 is released and your site is updated to it - if you run 15.0.8 today, every problem listed here is still present for you. ALARMS: the urgent "insulin reservoir change overdue" reminder could never appear and now can. If a feature name in your ENABLE setting (the list that switches features on) is misspelled or uses a file name instead of the feature's short name, Nightscout now warns you instead of silently leaving that feature off. The clock view now shows concern when a low reading is falling. These change whether an alarm or warning can appear, not the thresholds you set. BOLUS CALCULATOR QUICK PICKS: quick picks are saved food shortcuts in the Bolus Wizard (the calculator that suggests insulin for carbs). Picking one could load a different quick pick's foods or show foods meant to be hidden; that is corrected. A separate problem - the quick-pick list is built once when the page opens and not refreshed - is NOT fixed in this release. DATA SHOWN AND SEARCHED: many searches and counts that quietly returned nothing, or the wrong records, now return the right ones - for example filtering treatments by insulin, carbs, temporary basal rate or duration, and "records missing this field" searches. Profiles without a name and profile switches carrying their own schedule are handled correctly. Pages that read recent glucose values load faster. The carbs-on-board (COB) figure now uses the value reported by the system that uploads it (for example your phone app) when that system provides one, so the COB you see may differ from before. The main charts are rebuilt on a newer version of their drawing library, and several report and display fixes are included. SECURITY OF THE LIVE-UPDATE CONNECTION: the connection that pushes new readings and alarms to open pages had two gaps - recent device status could be sent to a page that had not signed in, and alarm messages went to every connected page. Both are closed, including on sites set to require sign-in. The "readable by world" warning also appears again in one setup where it had been hidden. DEBUG LOGGING QUIETER: detailed debug logging is now off unless it is switched on (the DEBUG_LOGGING setting), so server logs are shorter; if you or a helper rely on those logs to diagnose problems, switch it on. This is not medical advice. If a change to alarms or to a number such as carbs on board affects how you manage diabetes, talk it through with your care team.

**Why `minor`.** GT4: cannot be a patch, for reasons INDEPENDENT of D3. lib/server/env.js gains DEBUG_LOGGING and CONNECT_DEBUG, debug logging flips to off by default (removing log lines an operator relies on when diagnosing), and a new API file lib/api2/loop-notification-errors.js appears.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/master origin/dev`
  - dev descends from master with no divergence to reconcile
- **NO GATE** &mdash; CI at dev's tip is not re-run here. Release PR #8598's checks (Node 20/22/24 x Mongo 4.4/5/6, CodeQL, Docker build and publish) were all green on 2026-09-22, read from GitHub. Re-running them needs the full matrix with replica sets, and dev has no real-browser test job, so the D3 chart behaviour is not covered by that green.
- **NO GATE** &mdash; RT-D3's drag-clamp gap is unresolved and this release ships the D3 7 charts. The decision to ship anyway is the maintainer's; recording it as a no-gate keeps it from reading as covered.

**Evidence.**

- `docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md`
- `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`
- `docs/30-design/modernization/release-readiness-15.0.9-2026-09-22.md`
- `docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md`

**Notes.** 2026-09-23 - OPEN BEFORE THE TAG: RT-COUNT-COMPAT, whether the 15.0.9 count rule is a correction or a compatibility break for oref0 and GluPredKit. Hold #8598 and the tag until the maintainer decides it. 2026-09-23 - COMBINED RUN GREEN (-59): rc/15.0.9-combined-59 (local) = ddd9b600, then #8754 ef3404fd (merge 2731b658), then #8758 6d120fa2 (merge 509235b3). Both merges were automatic; tree 2ce67b27. Suite 2453/0/3 on dev, 2548/0/3 with #8754 and 3028/0/3 with #8758, on Node 20, 22 and 24 x MongoDB 4.4 and 7, with the CRUD- by-_id matrix in each cell (docs/30-design/remedial/rc-15.0.9-combined-59-2026-09-23.md). So #8754 and #8758 can merge on evidence. Still owed before the tag: one run after the pin to exact 0.1.0. 2026-09-23 (01:43Z 09-24) - dev ddd9b600 adds #8760 (BF-103). Open: #8754 (head ef3404fd: three dev merges on 0a74ef4e, its own changes line-identical to 0a74ef4e) and #8758 (6d120fa2). Their merge with dev is clean (tree 2ce67b27) and differs from the verified combined rc d087588f in exactly #8760's five files, so no combined run covers today's candidate. DECIDED 2026-09-23 (maintainer, relayed via -59) - run the combined suite now on dev ddd9b600 + #8754 ef3404fd + #8758 6d120fa2, so both PRs can merge on evidence, and once more after the pin to exact 0.1.0, before the tag. The first run is rc/15.0.9-combined-59 (session -59). #8598 carries the manual- check comment and the BF-103 update (2026-09-24 00:33Z and 04:41Z); it still has zero reviews. 2026-09-23 (late) - dev 4011193e carries #8750, #8752, #8759, #8757, #8749, #8748, #8755, #8756, #8753 and #8751; open: #8754 (security review: maintainer and Andy) and #8758. The combined rc (rc/15.0.9-combined-36b d087588f, 3015/0/3 on all six Node x MongoDB cells) tested exactly this set, so no re-run is owed unless #8754 or #8758 changes head. Manual checks passed on ec70aab0 (-6d): RT-D3, alarms under AUTH_DEFAULT_ROLES=denied and with AUTHENTICATION_PROMPT_ON_LOAD (ec70aab0 also carried #8754, which changes lib/api3/alarmSocket.js and is not on 4011193e; every other client file those checks use is identical). Still before the tag - connector v0.1.0 and a pin to exact 0.1.0 (with a re-run), release notes, #8598 review. 2026-09-23 - COMBINED CANDIDATE VERIFIED (-1f): rc/15.0.9-additions-e 1b1977e0 (local only) on dev 74fc6619 contains the live heads of all nine 15.0.9 PRs - #8748 d19043b2, #8749 46b20b38, #8750 aabce4b1, #8751 b5038500, #8752 adf5120c, #8753 e6a50e9a, #8754 0a74ef4e, #8755 92544d8f, #8756 83cfff14 (containment checked). 2534/0/3 on all 12 cells (Node 20/22/24 x MongoDB 4.4.24/7.0.43, nofile 64000); break-its red for the original reason; connector control dev.2 23/23, v0.0.13 18/5. Record: docs/30-design/remedial/rc-15.0.9-additions-e-2026-09-23.md. Still before the tag - the swap of #8752 to exact 0.1.0 (a re-run is owed then), reviews, release notes, #8598. DECIDED 2026-09-23 (maintainer) - what 15.0.9 carries beyond dev as it stands: ?count=0 answers an empty list (RT-COUNT0); MongoDB 4.4 is declared deprecated in the release notes and dropped in a later release; the legacy-ingestion notice goes in the release notes and RT-4 is dropped; nightscout-connect 0.1.0 is pinned only after longer prerelease testing (P0-TAG); RT-D3 is answered by a manual check plus an automated browser test. See docs/30-design/remedial/backfix-2-plan-2026-09-22.md section 1a. First on the adopted train. Every merged backfix in dev - the items in state merged-upstream - reaches operators only through this release; until it ships they are in code nobody runs. Merging dev publishes a Docker Hub image, which is not a release. dev pins nightscout-connect at 234d47c by source URL (the commit is in connector dev since #64 merged; measured 2026-09-23 with merge-base --is-ancestor), where master pins tag v0.0.13 - see P0-PIN and P0-TAG.

### `RT-1` &mdash; Cut 1 - chore/retire-jsdom

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `chore/retire-jsdom` |
| base | `9205ea30` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `major` |
| review | maintainer plus a human reviewer; low blast radius is the reason it is second on the train, not a reason to skip review |
| register | `BF-55`, `BF-58` |
| blocks on | `RT-0`, `RT-REBASE` |

**Blast radius.** 99 commits. Incremental production diff 11 files +68/-54 (GT2, 2026-09-15), not the 21 files +91/-123 the release-readiness §5 table publishes - that row was measured on a different basis from rows 2-5 and counts dev's own commits as deletions. Total 106 files, not 163.

**What an operator sees.** A maintenance release. THE ONE THING TO CHECK BEFORE UPGRADING: it will refuse to start on older versions of Node. You need Node 22.23.2 or newer, or 24.20.0 or newer. Node 20 no longer works, and neither do Node 21, 23, or 25 and above - the requirement is two specific ranges, not a minimum. If Nightscout stops starting after this upgrade, that is why.

**Why `major`.** GT4: the ENFORCED floor today is Node >=16 in bootevent.js, not the >=20 that `engines` declares - engines is not enforced on dev or master. Cut 1 introduces runtime-policy.js, which reads engines.node and calls process.exit(1). So the enforced floor jumps SIX majors, the declared range becomes a whitelist excluding Node 21/23/25+ and 22.0-22.23.1, and the check becomes a hard exit. Cut 1 also drops MongoDB 4.4 from CI in the same branch.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/retire-jsdom >/dev/null`
  - trial-merges into dev cleanly - FAILS as of 2026-09-22, see RT-REBASE
- `[static]` `node tools/queue/gates/node-floor-consistency.js`
  - "Trivially revertible - the engines field plus a boot check" is mechanically true and operationally misleading. Six other files state the floor independently (.nvmrc, bin/setup.sh, azuredeploy.json, README.md, CONTRIBUTING.md, docs/meta/architecture-overview.md). This gate checks they agree; a one-field revert would leave them stale.
- **NO GATE** &mdash; Dockerfile is node:22-alpine on both dev and cut 1, while cut 1's engines requires ^22.23.2 - a floating major tag against a patch floor. Nothing checks a Dockerfile base tag against an engines range.
- **NO GATE** &mdash; The clock-client concern/falling coverage is lost in the conflict resolution (RT-REBASE). Porting it to the Playwright suite is real work nobody has scheduled, and release-readiness §2 Option 1's "one CI run plus a cherry-pick of tests/browser/" undercosts it - cut 1 also deletes tests/dependency-d3.test.js, tests/fixtures/d3.js, tests/fixtures/d3-chart.js and tests/client.renderer.test.js, and its browser suite requires a playwright-core fixture and a module builder that dev does not have.

**Evidence.**

- `docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`
- `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`

**Notes.** 2026-09-23 (maintainer decision): the legacy CGM bridge removal (MiniMed mmconnect and Dexcom share2nightscout-bridge) is lifted from cut 4 onto cut 1. Built on local rh/cut1-retire-legacy (c043fb2d, from rh/cut1, not pushed): 8 cherry-picks plus the decision-A fixes (BF-61 named fix boots, no release number, BF-62 logged). Node suite 2121/0/1 on 22.23.2 and 24.20.0 x Mongo 7; npm audit --omit=dev 15 -> 9 (request and form-data highs clear). Connector pin stays 0.1.0-dev.1, which contains every cut 4 pin. Operator-visible: leftover MMCONNECT_* settings stop the site with a page naming the fix. See docs/60-research/modernization/cut1-legacy-bridge-lift-2026-09-23.md. From cut 1 onward docker-build and docker-build-pr carry needs: [test, browser-test], so a browser-test failure blocks image publication. On dev, docker-build has needs: test only.

### `RT-2` &mdash; Cut 2 - chore/build-runtime-separation

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `chore/build-runtime-separation` |
| base | `chore/retire-jsdom` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer plus a human reviewer |
| blocks on | `RT-1` |

**Blast radius.** 159 commits, prod 60 files +923/-465 (GT2 reproduced §5's row exactly). Page bundles, narrowed D3, event bus, boot sequence, Babel 8.

**What an operator sees.** A maintenance release that changes how the page's code is packaged and loaded. You should see no difference. If you run a third-party plugin that hooks into the page, test it before upgrading.

**Why `minor`.** GT4's judgement, explicitly UNMEASURED against any third-party plugin corpus - none exists on this machine to run. The boot sequence and event bus are where a plugin would break.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/build-runtime-separation >/dev/null`
  - trial-merges into dev cleanly - FAILS as of 2026-09-22, see RT-REBASE
- **NO GATE** &mdash; The minor classification rests on no plugin ever being run against it. A plugin corpus does not exist here. Until one does, "minor" is a judgement and the queue says so rather than letting the field imply a measurement.

**Evidence.**

- `docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`

**Notes.** Third on the adopted train, as a separate low-blast-radius release.

### `RT-3` &mdash; Cuts 3+5 combined - dependency release

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `chore/nightscout-modernization` |
| base | `chore/build-runtime-separation` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `major` |
| review | maintainer plus a human reviewer |
| register | `BF-64`, `BF-88` |
| blocks on | `RT-2` |

**Blast radius.** Cut 3: 63 commits, prod 23 files +294/-54 (MongoDB driver 7, jQuery UI). Cut 5: prod 36 files +397/-131 (Express 5, Helmet, EJS, Axios, Mocha 12, Swagger); of its 154 commits as §5 counted them, 95 are modernization work and 59 were dev's, pulled in by the merge 0a4109f6 (GT2, 2026-09-15). Cut 5's tip is b1bdaca0: an external contributor merged dev into it as e3b22034 ("Merge dev into modernization and reconcile regression coverage") and added two fixture commits, so it carries the Phase 0 PRs merged before 2026-09-21. Measured 2026-09-22 against origin/dev 74fc6619: origin/chore/nightscout-modernization is 9 behind dev and 498 ahead, and its trial-merge into dev conflicts in lib/server/bootevent.js (see RT-REBASE, which measures all five cuts). This item is PR #8605, declared in `pr:`.

**What an operator sees.** A dependency upgrade release. The database driver, the web framework and several libraries move to new major versions. You should see no difference in what Nightscout does. The bundled Docker setup moves from MongoDB 5.0 to 6.0; MongoDB 5.0, 6.0, 7.0 and 8.0 are all still tested, so no database version you are running today stops being supported.

**Why `major`.** Cut 3 alone is minor - GT4 verified the CI matrix runs 5.0.32, 6.0.27, 7.0.40 and 8.0.29, so NO tested server is lost; only the bundled docker-compose default moves. Cut 5 is classified major on dependency major bumps (Express 4->5, Helmet 4->8) and a 36-file production diff, NOT on a measured contract break. Combined, the release is major.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/nightscout-modernization >/dev/null`
  - cut 5 trial-merges into dev cleanly. FAILS as of 2026-09-22 against origin/dev 74fc6619: one conflict, lib/server/bootevent.js, which the BF-77 fix merged as PR #8746 also touches.
- **NO GATE** &mdash; Express 4->5 and Helmet 4->8 are classified major on dependency version numbers and diff size, not on any measured contract break. Nobody has run a contract test against the route surface.
- **NO GATE** &mdash; Combining cuts 3 and 5 skips cut 4 in the middle of a LINEAR stack. Cut 5 is a descendant of cut 4, so "3+5 without 4" is not a prefix and the parcel-as-prefix property the whole plan rests on does not hold for this step. Nobody has measured what that costs.

**Evidence.**

- `docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`
- `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`

**Notes.** §5's commits column sums to 554 against a 495-commit stack (GT2). Counted as modernization work, cut 5 is 95, and 95 + 400 = 495. BF-88 DECIDED 2026-09-23 (maintainer): with TRUST_PROXY unset the cuts keep 15.0.9's resolution (forwarded-for, 8b975b41), not 395f3207's fixed-precedence normalisation; when cut 5 is rebased its four tests/client-ip.test.js expectations take 15.0.9's values and forwarded-for stays a dependency, as in the cut rehearsal. No flag for the other normalisation. Separate from BF-88 and still to carry: cut 5's client-ip.js (b1bdaca0) refuses the hop counts and true that #8754 (81623f9b) accepts.

### `RT-4` &mdash; Deprecation release - recommended folded into 15.0.9's release notes

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `chore/nightscout-modernization` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer - this release exists to buy operators time before cut 4 |
| blocks on | `RT-3` |

**Blast radius.** New code, not just a warning string. lib/server/mmconnect-connect-compat.js does NOT exist on dev or master - it is born in cut 4, the same branch that deletes lib/plugins/mmconnect.js.

**What an operator sees.** A warning release. If you get your CGM data through the built-in Dexcom Share or MiniMed CareLink connection, a future release removes both of them, and you will need to move to the nightscout-connect connector first. This release tells you whether that applies to you and what to change. If you use MiniMed CareLink you will also need to set your country, because Nightscout cannot work it out from your existing settings. Nothing stops working in this release. Your glucose data continuing to arrive is the thing at stake, so please do not skip this one.

**Why `minor`.** adds warnings and a migration shim; removes nothing

**Gates.**

- `[static]` `node tools/queue/gates/minimed-deprecation-path.js`
  - FAILS while dev carries no named MiniMed escape hatch. GT4 measured the asymmetry: Dexcom HAS one - bridge-connect-compat.js is on master AND dev with five DEPRECATION WARNING lines, one naming DEXCOM_BRIDGE_USE_LEGACY. MiniMed's only warning today is a generic "PLEASE CONSIDER nightscout-connect instead." naming no setting.
- **NO GATE** &mdash; Nobody knows how many operators run MMCONNECT_*, or how many run BRIDGE_* and MMCONNECT_* together. Both populations are what decides how long this release has to sit before cut 4 follows it, and neither can be measured from here.

**Evidence.**

- `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`

**Notes.** MERGED 2026-09-23 into dev (now 4011193e); NOT RELEASED. #8757 (the MiniMed warning names its replacement settings) as d0d6b433; CI and CodeQL green. The notice itself is in the 15.0.9 release notes; the removal moves onto cut 1 (maintainer, in -1f). Its gate stays red BY DESIGN after this merge: #8757 satisfies the warning half, and the other half checks for a migration shim that ships with the removal on cut 1 (RT-1). OPENED 2026-09-23 as nightscout/cgm-remote-monitor #8757 (bf3/mmconnect-deprecation-warning, head 5d342ac1, base dev), for 15.0.9. Full suite on the branch 2387/0/3 (Node 20, MongoDB 7; -59); the setting names match the connector's extendedSettings keys. DECIDED 2026-09-23 (maintainer) - dropped. The notice goes in 15.0.9's release notes, as recommended below; no separate deprecation release. 2026-09-23: local branch bf3/mmconnect-deprecation-warning (5d342ac1, on dev 1f9a9d10, not pushed) replaces the generic MiniMed warning with one naming every replacement setting, for 15.0.9. With QUEUE_GATE_REF set to it, the gate's settings check passes; the shim check stays red by design, because the shim ships with the removal, which the maintainer lifted onto cut 1. The maintainer confirms (2026-09-22, operational knowledge) that legacy mmconnect does not work, and Dexcom BRIDGE_* settings have been served by nightscout- connect by default since 15.0.8 (a91e8ee4, with a deprecation warning and the DEXCOM_BRIDGE_USE_LEGACY escape hatch). No working path is left for a separate release to protect. Recommended: put the notice in 15.0.9's release notes (MiniMed users: move to CONNECT_SOURCE with your CareLink country; Dexcom legacy-flag users: the escape hatch goes with cut 4) and drop this release. The MiniMed shim is still real code and ships with cut 4. BF-44/BF-45 re- graded low.

### `RT-5` &mdash; Cut 4 - chore/mime-exposure-review, the one to slow down on

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `chore/mime-exposure-review` |
| base | `chore/compose-mongodb6` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `major` |
| review | maintainer, a human reviewer, AND a deliberate hold. Its own evidence document says "No real Dexcom account or live database has been used and no live migration is claimed." |
| register | `BF-61`, `BF-62` |
| blocks on | `RT-4` |

**Blast radius.** 79 commits, prod 66 files +324/-511. DELETES TWO CGM INGESTION PATHS (legacy Dexcom Share and MiniMed CareLink), trusted proxies, DOMPurify, Moment/tz. Caveat: the maintainer stated on 2026-09-21 that mmconnect has been broken for some time (operational knowledge, not measured here) and that legacy Dexcom Share is intended to map to nightscout-connect, so whether both deleted paths are working today is not established.

**What an operator sees.** READ THIS BEFORE UPGRADING. This release removes the built-in Dexcom Share and MiniMed CareLink connections. If you have not moved to the nightscout-connect connector, your glucose data stops arriving. If you use MiniMed CareLink and have not set a country, Nightscout will not start at all - not just the CGM part, the whole site, showing an error page instead. The same happens if you currently use Dexcom Share AND MiniMed CareLink together, which works today and does not after this release. If your data stops arriving you may not have a glucose reading when you expect one; please make sure you have another way to check your glucose before upgrading, and talk to your care team about what you rely on Nightscout for. This is not medical advice.

**Why `major`.** GT4 EXECUTED the shims. An MMCONNECT operator with no CONNECT_COUNTRY_CODE gets {migrated:false,error:...}; bootevent.js pushes it to ctx.bootErrors; app.js:202 then installs app.get('*', bootErrorView) and returns, and server.js:61 returns before websocket setup. The WHOLE deployment serves the boot-error page - no API, no sockets, no charts. Separately, running BRIDGE_* and MMCONNECT_* together - two independent boot stages today - gets the same total outage, because there is now one CONNECT_SOURCE and the second source has nowhere to go. That is a capability removal (concurrent multi-source CGM ingestion) absent from every summary of the cut.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/mime-exposure-review >/dev/null`
  - trial-merges into dev cleanly - FAILS as of 2026-09-22, see RT-REBASE
- `[static]` `node tools/queue/gates/cut4-total-outage.js`
  - Decision A (2026-09-23): runs both legacy shims in bootevent.js order over six env shapes with the ENABLE rule modelled. FAILS unless every shape that stops the site names a fix, names no release number, and boots once that fix is applied as written. Ref from QUEUE_GATE_REF, default rh/cut1-retire-legacy (where the removal now lives).
- **NO GATE** &mdash; "No real Dexcom account or live database has been used and no live migration is claimed" - the cut's own evidence document. No gate can substitute for a real migration, and nothing in this repository may use real credentials (rule 0).
- **NO GATE** &mdash; Cut 4 deletes bridgeUseLegacy and the log line naming it, so DEXCOM_BRIDGE_USE_LEGACY becomes accepted-and-ignored. Credentials are still migrated so ingestion continues; only the operator's expressed intent is discarded silently. Nothing checks for accepted-and-ignored settings.

**Evidence.**

- `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`
- `docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`

**Notes.** DECIDED 2026-09-23 (maintainer) - BF-61's hard stop is intended: MMCONNECT_* is usually the primary data source, so a misconfigured one shows the error page naming the fix. Still owed under that decision: the named fix must boot (CONNECT_COUNTRY_CODE alone does not, unless connect is in ENABLE), the messages must not say 15.0.9, and cut4-total-outage.js must be rewritten to pass when each stopping shape names a fix that boots. Also directed: deprecate and remove mmconnect as early as possible (it does not work and carries deprecated dependencies), partly in the current cycle where appropriate; with RT-4 dropped, the separate hold below is moot. 2026-09-23: the removal is lifted onto cut 1 (RT-1, local rh/cut1-retire-legacy c043fb2d), with the three owed fixes done there. cut4-total-outage.js is rewritten to decision A (QUEUE_GATE_REF, default rh/cut1-retire-legacy): green there, red on rh/cut4. Cut 4's remainder is trusted proxies, DOMPurify, Moment, MIME, webpack and ESLint; a trial merge into the lifted cut 1 conflicts only in legacy files and manifests. HELD BACK on the adopted train, behind a deprecation release. If the Connect migration misbehaves the symptom is a user's glucose data stops arriving - a data-availability failure for someone managing diabetes.

### `RT-CONNECT-PIN-CUTS` &mdash; BF-65 - cuts 1-3 ship the leaking connector to upgraders first

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `chore/retire-jsdom, chore/build-runtime-separation, chore/compose-mongodb6` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `patch` |
| review | maintainer, plus the security reviewer who takes BFQ-CONNECTOR - it is the same disclosure, shipped by a different route |
| ships to operators today | no (pre-release) |
| register | `BF-65` |
| blocks on | `P0-TAG` |

**Blast radius.** One line of package.json on each of three cut tips.

**What an operator sees.** The first two releases on the planned upgrade path are presented as low-risk maintenance releases. As the branches stand, upgrading to either of them leaves you on the same version of the connector (the part of Nightscout that fetches readings from services such as Dexcom Share or LibreLinkUp) that writes your CGM account credentials and glucose readings into the server log. Moving each branch to the fixed version is a one-line change, and it should happen before those releases are cut.

**Why `patch`.** a dependency pin moves to a newer patch of the same package

**Gates.**

- `[static]` `node tools/queue/gates/connector-pin-exposure.js --refs origin/chore/retire-jsdom,origin/chore/build-runtime-separation,origin/chore/compose-mongodb6,origin/dev`
  - FAILS on all three cut tips, which pin the v0.0.13 tag tarball, and PASSES on origin/dev (pinned to connector commit 234d47c) as the control. The gate refuses to report when every ref agrees, because a run that distinguishes nothing is not a result.
- **NO GATE** &mdash; The pins are measured; the release ordering is quoted from release-readiness §5 and was not re-derived. So "ships the leaking connector to upgraders first" is an inference from combining the two, and nothing gates a claim about the order of releases. All three cuts pin the v0.0.13 tag, so the fix is the same one-line change as dev's.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Filed separately from BFQ-CONNECTOR because the §1/§1b line runs between them: master ships to operators today, cut tips do not, and that line is what gives the register's sections their meaning. The work is identical and they should be done together.

### `RT-NODE-FLOOR-TESTED` &mdash; BF-58, BF-59 - the enforced Node floor is not the Node anything exercises

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `chore/compose-mongodb6, chore/mime-exposure-review, chore/nightscout-modernization` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-58`, `BF-59` |
| blocks on | `RT-1` |

**Blast radius.** Dockerfile (builder and runtime FROM lines), the .github/workflows test-job matrix and package.json engines, on the cut tips. No production source.

**What an operator sees.** As the pushed modernization branches stand, Nightscout refuses to start on Node (the JavaScript runtime it runs on) older than 22.23.2 or 24.20.0 and exits immediately with a message. The container image those branches build uses the floating "node 22" image, which on 2026-09-21 resolved to Node 22.22.0 - below that minimum - so a container built from them starts, prints the message and stops. That looks like a crash and is not data loss. A wider minimum that the current image satisfies has been prepared but not published; see the notes. The release notes should name the message so you recognise it.

**Why `n/a`.** CI and image configuration. It changes no declared surface. The Node floor itself is classified on RT-1 and this item does not restate it.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official show origin/chore/retire-jsdom:.github/workflows/main.yml | grep -q "'22.23.2'" && git -C externals/cgm-remote-monitor-official show origin/chore/retire-jsdom:.github/workflows/main.yml | grep -q "'24.20.0'"`
  - CONTROL, and it PASSES - cut 1's test matrix is ['22.23.2','22','24.20.0','24'], so the two floor versions the runtime policy refuses to start below are exercised. A green here is what makes the red below a fact about cut 3 rather than about the grep.
- `[static]` `git -C externals/cgm-remote-monitor-official show origin/chore/compose-mongodb6:.github/workflows/main.yml | grep -q "'22.23.2'" && git -C externals/cgm-remote-monitor-official show origin/chore/compose-mongodb6:.github/workflows/main.yml | grep -q "'24.20.0'"`
  - BF-59. FAILS - from cut 3 onward the matrix is ['22','24'] and the two exact versions the software refuses to start below are exercised by no test job. engines is byte-identical across all five pushed cuts, so this is lost coverage rather than a changed requirement.
- **NO GATE** &mdash; BF-58 has no gate: nothing checks a Dockerfile base tag against an engines range, and a gate may not pull or build an image. Measured by hand on 2026-09-21: node:22-alpine resolved to v22.22.0, which violates the pushed cuts' ^22.23.2 floor, and runtime-policy.js refused it inside that image with exit 1. Every pushed cut pins node:22-alpine and enforces ^22.23.2 || ^24.20.0; origin/dev is unaffected at >=20.x.
- **NO GATE** &mdash; Partial mitigation already in CI, recorded so the residual is not overstated - from cut 1 the docker-build-pr job builds the image and runs runtime-policy against it plus a start-up smoke test. The gap is narrower: the docker-build job that PUBLISHES to Docker Hub on master/dev has no such step and builds with no-cache, so it re-resolves node:22-alpine at publish time without re-validating.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Measured 2026-09-21 with `n exec` and `docker run`. BF-58, severity high. A container built from any pushed cut's own Dockerfile does not boot: node:22-alpine resolves to v22.22.0 and the runtime policy refuses it. Pushing to dev or master fires main.yml's docker-build and publishes to Docker Hub, so merging any cut as it stands PUBLISHES the non-booting image rather than failing CI. It is the whole containerised install path on the first modernization release. The defect is the floor, not the image tag. With runtime-policy.js stubbed to a no-op, cut 4's unit suite is 310 passing / 0 failing on 20.20.0, 22.12.0, 22.22.0, 22.23.2, 24.15.0 and 24.20.0 - identical on every version the floor rejects - and cut 1's Playwright suite is 21/0 on Node 20.20.0. The only real break is 18.20.8, and it is not Nightscout's code: all 15 failures are ERR_REQUIRE_ESM from sanitize-html requiring the ESM-only htmlparser2; require(esm) is unflagged in 22.12 and backported to 20.19, exactly where the results flip. The dependency-derived floor is ^20.19 || ^22.12 || >=24. docs/runtime-upgrade.md (commit a95c2ce5, 2026-09-05) says the minimum patches "reflect the supported release baseline at the time of this change" - 22.23.2 and 24.20.0 were 8 and 10 days old then - and in the same document says the image should track "the official major tag", which a patch- level floor makes impossible. Changing only the Dockerfile tag would hide this rather than resolve it; the four candidate tags measured that day (node:22.23.2-alpine, node:24.20.0-alpine, node:24-alpine -> v24.21.0, node:lts-alpine -> v24.21.0) all satisfy the floor today. Prepared fix, MAINTAINER DECISION 2026-09-21, NOT PUSHED: engines.node is `^22.12 || >=24`, committed as ed21961f on rt/cut1 and merged up the stack to rt/cut2 b5bf7d77, rt/cut3 c313f5b1, rt/cut4 95bb6295. Node 20 is left out deliberately: it works (310/0) but reached end of life 2026-04-30 and gets no security updates. `>=24` admits odd and future majors (25.x, 26.x) deliberately, and tests/runtime-policy.test.js says so; prereleases stay out via semver's default. The Dockerfile is unchanged: under a minor floor the floating major tag is correct and is the strategy docs/runtime-upgrade.md describes. Verified in the image: `runtime ACCEPTED inside node:22-alpine (v22.22.0)`. Boundary: 18.20.8 and 20.20.0 refused, 22.12.0 / 22.22.0 / 24.15.0 / 24.20.0 accepted, confirmed by running lib/server/server.js (the `npm start` entry) on each. Cut 4's suite including tests/runtime-policy.test.js is 332 passing / 0 failing at both 22.12.0 and 24.20.0. Non-vacuity: widening engines to >=18 as an ablation takes the boundary test from 22 passing to 11 passing / 11 failing. The two gates above measure the pushed origin/ branches, not rt/cut*. tools/queue/gates/node-floor-consistency.js asks semver whether a major is permitted (a patch-precision regex found no majors in "^22.12 || >=24" and reported six false strays), and gates the actual incompatibility - a floating major tag plus a patch floor inside that major - rather than requiring a patch-pinned Dockerfile. NODE_FLOOR_REF lets it measure a prepared branch; it defaults to the published ref so CI measures what operators would get. BF-59, severity low. From cut 3 onward the matrix drops to ['22','24'], so a regression exactly at the floor would go uncaught. There is none today: cut 4's unit suite is 310 passing / 0 failing on 22.23.2 and on 24.20.0, and cut 1 gives the same count on each. Lost coverage, not a live defect. For any future run: use `n exec <version> <cmd>`, not `n install`, which switches the machine default under other live sessions. Batched because both are one question - is the floor the software enforces the floor anything actually runs? RT-1 carries BF-58 as a no-gate; this item is the work, that is the measurement.

### `RT-BOOTERROR` &mdash; BF-63 - the page that reports a boot error crashes on cut 4's boot errors

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `patch` |
| review | maintainer, and it should be reviewed WITH RT-5, because the message it destroys is that cut's mitigation |
| ships to operators today | no (pre-release) |
| register | `BF-63` |

**Blast radius.** lib/server/booterror.js error-line map (one expression), plus lib/server/bootevent.js:330 and :335 on cut 4 - the only two bootErrors.push sites in the tree that omit err.

**What an operator sees.** When Nightscout cannot start it shows a page explaining why. For one shape of start-up error that page itself fails, so instead of the sentence telling you what to fix you get nothing at all. The error that triggers it is the one a MiniMed CareLink user hits on the planned release that removes the built-in CareLink connection - the message that would tell them to set their country. Losing that message is what makes this worth fixing before that release, not after.

**Why `patch`.** A crash fix in an error renderer. No declared surface moves. The call-site half on cut 4 is part of that cut's own classification.

**Gates.**

- `[static]` `node tools/queue/gates/booterror-shape-coverage.js --ref origin/chore/mime-exposure-review`
  - FAILS on the two err-less shapes and reports that cut 4's bootevent.js has 2 of 9 push sites producing them. Three control shapes - the Mongo string, the ENV array and a real Error - RENDER through the identical expression, so the failure is the input shape and not the harness. The gate refuses to run if the map expression is no longer present verbatim in the shipping file.
- `[static]` `node tools/queue/gates/booterror-shape-coverage.js --ref origin/dev`
  - THE §1b CONTROL, and it also fails - on origin/dev the renderer throws on the same two shapes while 0 of 7 push sites produce them. That is the register's filing decision as a measurement: the weakness is in SHIPPING code today and is awaiting a caller, and the caller arrives with cut 4. `git diff origin/dev origin/chore/mime-exposure-review -- lib/server/booterror.js` is EMPTY, so a reviewer reading only cut 4's diff will not see the renderer half.
- **NO GATE** &mdash; Nothing renders the actual error.html template. The gate exercises the map that builds each error line, which is where the TypeError is thrown, but a full render needs EJS, express and a views path. The fix must be BOTH halves - pass err at both call sites AND make the renderer defensive - with a regression test asserting a desc-only boot error renders as HTML. Fixing only the call sites leaves the next caller to rediscover it.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** 2026-09-22 - the renderer half is on bf2/ops e6a50e9a as a guard: on dev all 7 bootErrors.push sites pass a non-null err, so the crash is not reachable on dev today. The call-site half at cut 4 bootevent.js:330 and :335 is still open. Separately, booterror.js interpolates desc and err into HTML unescaped; every input today is server-side. The gate's caller-count arm matches ES6 shorthand `err` as well as `err:` - dev's `bootErrors.push({desc: synopsis.join(' '), err})` has no colon and is not an err-less site. It reproduces the register exactly: 7/7/9 push sites, 0/0/2 err-less, on master/dev/cut 4.

### `BF2-BACKPORT` &mdash; Which modernization-only security commits fix a defect that dev has

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf2/backports` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/work/crm-bf2-backports` |
| semver | `n/a` |
| review | SECURITY for anything that reproduces; maintainer for the triage. |
| register | `BF-104`, `BF-105` |

**Blast radius.** Six candidate commits on chore/nightscout-modernization b1bdaca0 - 31c354d8, d3ac8026, 973a2849, 71c42c9a, d48be5e5, ad4a8cd5. Only 31c354d8 cherry-picks cleanly onto origin/dev.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** triage; each confirmed backport is classified on its own branch

**Gates.**

- `[static]` `grep -q "^## Verdicts" docs/60-research/remedial/modernization-backport-triage-2026-09-22.md`
  - The triage exists. It must carry, per commit, a reproduction on dev and a control.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf2/backports >/dev/null`
  - The two backports merge into origin/dev with no conflict.
- **NO GATE** &mdash; Whether each commit fixes a live defect is established by running a probe on dev, not by reading the diff. The probes live with the triage.

**Evidence.**

- `docs/30-design/remedial/backfix-2-plan-2026-09-22.md`

**Notes.** MERGED 2026-09-23 into dev (now 4011193e); NOT RELEASED. #8751 as 4011193e (CI was running when recorded). Register ids filed 2026-09-23: BF-104 (alarm- subscription credentials in the server log) and BF-105 (two shared read routes skip the per-collection read permission). OPENED 2026-09-23 as nightscout/cgm- remote-monitor #8751 (head b5038500, base dev), with the withheld-style body in reports/phase0-pr-bodies/bf2-backports.md. DECIDED 2026-09-23 (maintainer) - the two backports (9c50788e, b5038500) move INTO 15.0.9 rather than backfix 2, because their fix code is already public on the modernization branch and 15.0.8 users otherwise wait a release. The two unbuilt findings (status credential in the URL, IMPORT_CONFIG diagnostics) stay follow-ups. MEASURED 2026-09-22 - 11 candidates (6 named + 5 from a path/content sweep). DEFECT-ON- DEV and live on 15.0.8: 31c354d8 (alarm socket logs the submitted credential), d3ac8026 (a per-collection read grant not checked on two shared routes; bites scoped-token installs under denied), 973a2849 (status credential in the URL), 8458f39e (IMPORT_CONFIG diagnostics). d48be5e5 is real but not security. 71c42c9a not a defect; Helmet pair and 479a6a4d/924aa8d7 not on dev; f2ebd7d4 unsettled. bf2/backports carries 9c50788e and b5038500 (code verbatim, tests adapted where dev's socket differs); suite on Node 22.23.2 - dev 2386/0/3, branch 2398/0/3. Control re-run by the coordinator - with dev's lib the two new test files fail 7 of 12. Register entries are pending id allocation. Backports carry the modernization commit's content unchanged (cherry-pick -x) so the later cut rebase sees agreement, not a second implementation.

---

## Open backfix-register entries

`parcel: register-open` &mdash; 48 items

The §1 / §1b distinction is preserved in `ships_to_operators_today`. That
distinction is the only thing that makes the register mean anything - widening
§1's criterion would destroy it.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `BFQ-91` | BF-91 - connector capture mode cannot find trace-axios for two sources | `merged-upstream` | `fix/trace-axios-path` | patch | 2 run + 1 no-gate |
| `BFQ-09` | BF-09 - socket dedup truthiness skips a falsy value | `unsettled` | `-` | patch | 1 run + 2 no-gate |
| `BFQ-10` | BF-10 - mongod fatal-asserts at Docker's default nofile=1024 | `not-started` | `-` | patch | 1 run + 1 no-gate |
| `BFQ-04` | BF-04 - the v1 operator allowlist - superseded by P0-K | `merged-upstream` | `bf/operators` | minor | 0 run + 1 no-gate |
| `BFQ-21` | BF-21 - pg bulkUpsert ignores {mode:'replace'} | `not-started` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `BFQ-19` | BF-19 - pg ORDER BY reads the generated column | `not-started` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `BFQ-22` | BF-22 - dotted field stores nested on Mongo, literal dotted key on PG | `not-started` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `BFQ-23` | BF-23 - duplicate-key error reaches the caller as the backend's class | `not-started` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `BFQ-25` | BF-25 - credential in the request body bypasses the tenant claim check | `not-started` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `BFQ-24` | BF-24 - TRUST_PROXY=false bypasses the TENANT_HOST_HEADER guard | `not-started` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `BFQ-26` | BF-26 - HTTPS redirect drops the tenant path prefix | `not-started` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `BFQ-27` | BF-27 - config() hands back an enclave that was never armed | `not-started` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `BFQ-18` | BF-18 - driver 7 doubles the getMore batch size on .limit(0) | `not-started` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `BFQ-20` | BF-20 - scalarize() converts a Date bound to an ISO string | `not-started` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `BFQ-CAP01` | CAP-01 - Nightscout cannot be served from a sub-path | `not-started` | `-` | minor | 0 run + 1 no-gate |
| `BFQ-69` | BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing | `merged-upstream` | `bf3/quickpick-rebuild` | patch | 3 run + 1 no-gate |
| `BFQ-71` | BF-71 - any dateString key drops the default date window, and the window is not a control | `gate-not-met` | `-` | patch | 2 run + 2 no-gate |
| `BFQ-72` | BF-72 - an unauthenticated $regex can spend minutes of database CPU | `needs-decision` | `-` | minor | 1 run + 3 no-gate |
| `BFQ-40` | BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion | `merged-upstream` | `-` | minor | 1 run |
| `BFQ-41` | BF-41 - a reading dated ahead of the clock silences the stale-data alarm (closed, does not reproduce) | `closed` | `-` | n/a | 1 run + 1 no-gate |
| `BFQ-87` | BF-87 - the root qs override holds the connector below its range and pins the server's query parser | `merged-upstream` | `bf/qs-6.16` | patch | 3 run + 1 no-gate |
| `BFQ-CONNECTOR` | BF-42, BF-43 - master pins the leaking connector, with a violated axios override | `gate-not-met` | `-` | patch | 1 run + 2 no-gate |
| `BFQ-MINIMED` | BF-44, BF-45, BF-85 - MiniMed ingestion divergences and the CareLink zero reading | `not-started` | `-` | minor | 0 run + 3 no-gate |
| `BFQ-46` | BF-46 - eleven API v3 variables bypass env.js, one family deletes data | `gate-not-met` | `-` | minor | 1 run + 1 no-gate |
| `BFQ-47` | BF-47 - an ordinary subject edit destroys stored fields, on today's release | `in-flight-upstream` | `bf2/subject-edit-keeps-fields` | major | 2 run + 1 no-gate |
| `BFQ-ENV` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies | `gate-not-met` | `-` | minor | 4 run + 2 no-gate |
| `BFQ-52` | BF-52 - an age reminder whose 20-minute window passed without a check was never sent | `blocked` | `bf3/age-push-once` | patch | 2 run + 1 no-gate |
| `BFQ-90` | BF-90 - an alarm at a page with no reading throws in the client | `merged-upstream` | `bf3/alarm-no-reading` | patch | 1 run + 2 no-gate |
| `BFQ-92` | BF-92 - a page with no glucose reading never presents a server alarm, including device alarms | `not-started` | `-` | minor | 0 run + 1 no-gate |
| `BFQ-93` | BF-93 - food changes never reach an open page | `not-started` | `-` | patch | 0 run + 1 no-gate |
| `BFQ-94` | BF-94 - a kept profile instance can return a temp basal that has been replaced | `unsettled` | `-` | patch | 0 run + 1 no-gate |
| `BFQ-95` | BF-95 - an uploader clock running ahead delays the stale-data alarm | `needs-decision` | `-` | minor | 0 run + 1 no-gate |
| `BFQ-96` | BF-96 - the headless test fixture's bundle cache key is an un-normalised path | `not-started` | `-` | n/a | 0 run + 1 no-gate |
| `BFQ-67` | BF-67, BF-86 - alarm thresholds quietly changed, or quietly kept when they cannot work | `gate-not-met` | `-` | minor | 1 run + 1 no-gate |
| `ADV-RETRO` | GHSA-gjhc - loadRetro serves devicestatus to any socket (BF-79) | `merged-upstream` | `bf/ws-loadretro-auth` | patch | 2 run + 1 no-gate |
| `ADV-ALARM` | GHSA-8849 - /alarm broadcasts to the whole namespace (BF-75, BF-76) | `merged-upstream` | `bf/alarm-socket-scope` | minor | 2 run + 2 no-gate |
| `ADV-XSS-META` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) | `needs-decision` | `-` | n/a | 2 run + 1 no-gate |
| `ADV-CONFIG` | The readable-by-world warning, the careportal role, and the two settings behind both (BF-77, BF-78, BF-81) | `needs-decision` | `-` | patch | 2 run + 1 no-gate |
| `BFQ-103` | BF-103 - a split drag stores the old time, so IOB and COB ignore the move | `merged-upstream` | `bf/split-drag-time` | patch | 0 run + 1 no-gate |
| `BFQ-106` | BF-106 - a numeric date filter on API v1 activity matches nothing on dev | `not-started` | `origin/dev` | patch | 1 run |
| `BFQ-107` | BF-107 - a failed treatments query ends the Nightscout process on 15.0.8 | `merged-upstream` | `fix/treatments-query-errors-8675` | patch | 1 run + 1 no-gate |
| `BFQ-108` | BF-108 - a list of timestamps under the date field answers 500, so bulk deletes by timestamp do nothing | `not-started` | `origin/dev` | patch | 1 run |
| `BFQ-97` | BF-97 - on the connector 0.1.0 line, a source with a profile stalls every poll | `merged-upstream` | `fix/profile-sync-bounded-update` | patch | 0 run + 1 no-gate |
| `BFQ-98` | BF-98 - the connector reuses a reader subject without roles, so the BF-89 fix does not repair it | `merged-upstream` | `fix/profile-duplicate-stall` | patch | 0 run + 1 no-gate |
| `BFQ-99` | bf/profile-object-id - a profile posted with its own _id is stored as an ObjectId, and string-_id profiles can be edited and deleted | `blocked` | `bf/profile-object-id` | patch | 0 run + 1 no-gate |
| `BFQ-100` | BF-100 - devicestatus, food and activity store a hex _id as a string | `blocked` | `bf/object-id-other-collections` | patch | 0 run + 1 no-gate |
| `BFQ-101` | BF-101 - API v3 id filters miss records stored with a string _id | `blocked` | `bf/api3-string-id` | patch | 0 run + 1 no-gate |
| `BFQ-102` | bf/object-id-consistency - one rule for a record's own hex _id across profile, devicestatus, food, activity, treatments, entries and API v3 | `in-flight-upstream` | `bf/object-id-crud` | patch | 0 run + 1 no-gate |

### `BFQ-91` &mdash; BF-91 - connector capture mode cannot find trace-axios for two sources

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `nightscout-connect` |
| branch | `fix/trace-axios-path` |
| base | `official/dev@1946beb` |
| worktree | `externals/work/nc-trace-axios` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-91` |

**Blast radius.** Two require paths - lib/sources/nightscout.js:190 and lib/sources/dexcomshare.js:243.

**What an operator sees.** Only affects people who run the connector's "capture" command by hand to record test data. For the nightscout and Dexcom Share sources it stops straight away with a "module not found" error. Fetching readings is not affected.

**Why `patch`.** a broken import path in a developer command

**Gates.**

- `[static]` `sh -c 'git -C externals/nightscout-connect grep -q "require(.../../trace-axios.)" official/dev -- lib/sources/nightscout.js lib/sources/dexcomshare.js && exit 1 || exit 0'`
  - FAILS while either top-level source still requires ../../trace-axios.
- `[unit]` `cd externals/work/nc-trace-axios && n exec 22.23.2 node --test test/capture-tracker.test.js`
  - 2 cases - every source's capture tracker starts, and every literal relative require in lib/ and commands/ resolves. Control, re-run by the coordinator - restoring dev's dexcomshare.js fails with MODULE_NOT_FOUND at dexcomshare.js:243.
- **NO GATE** &mdash; The crash itself needs the capture CLI to run against a source; the static check stands in for it, and the path is the whole defect.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** MERGED 2026-09-23 - #78 (894b132) is in connector official/dev fbd4e55, and in prerelease 0.1.0-dev.2. Not in a full connector release yet. PREPARED 2026-09-23 - fix/trace-axios-path 894b132 on official/dev 1946beb. Reproduced by running capture for both sources (exit 1 at the require, before any request). Suite 291/291 on Node 20, 22 and 24 (dev 289/289). Merges cleanly with fix/nightscout-reader-roles. The red gate reads official/dev and turns green when the fix merges there. Found 2026-09-23 while running the BF-89 end- to-end test. Small enough to ride with P0-CONNECT-ROLE before the full 0.1.0, if the maintainer wants it.

### `BFQ-09` &mdash; BF-09 - socket dedup truthiness skips a falsy value

| | |
|---|---|
| state (claimed) | `unsettled` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-alarms` |
| semver | `patch` |
| review | maintainer - this needs a decision on intent before it needs code |
| ships to operators today | **yes** |
| register | `BF-09` |

**Blast radius.** lib/server/websocket.js:538-566 (the register cites 535-568).

**What an operator sees.** When two treatment records arrive within two seconds of each other, Nightscout decides whether they are the same one. That check ignores a value of zero. A zero temporary basal rate - the suspend an automated insulin delivery system sends - is exactly such a value. It is not settled whether this ever discards a real record.

**Why `patch`.** if it is a defect at all, the fix is a bug fix

**Gates.**

- `[static]` `node tools/queue/gates/bf09-corpus-divergence.js`
  - GT3's corpus sweep, re-runnable. 277,690 treatments across 11 sites, 0 outcome divergences within the ±2s window, AND a four-case injection harness proving the comparison is not vacuous (2 DIVERGES, 2 agree). De-identified counts only.
- **NO GATE** &mdash; The corpus is SURVIVORSHIP-BIASED in exactly the direction that hides this defect: it counts stored data, and the defect's effect is to suppress an insert. A suppressed insert cannot appear in stored data. The one arm that would settle it is a live uploader-burst replay, which nothing here can run.
- **NO GATE** &mdash; No test in the suite exercises a zero-valued dedup field. The only values in tests/websocket.*.test.js are insulin: 1 and carbs: 9/10/15/18.

**Evidence.**

- `docs/60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md`
- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`
- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** MEASURED 2026-09-23, awaiting the maintainer - zero-is-real fixes 6 dedup cases and changes no control; bec641ca was rendering only. The options are in docs/60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md. DECIDED 2026-09-23 (maintainer) - measure first, then decide. The maintainer leans towards treating zero as a real value (a zero temp basal is a real value in AID terms), but recalls a temp-basal display problem when AAPS issues zero temps seconds apart, fixed at some point (bec641ca, rendering, is the candidate); the fix must not bring it back. Measure the impact on the corpus before choosing. First read, then reproduced 2026-09-23 as cases X1 and X2: because a falsy field is left out of the lookup, the lookup can end up keyed on fields another eventType also has, so a zero temp can match a different eventType within the window. Only uploaders using the socket path without NSCLIENT_ID reach this. tools/queue/gates/bf09-corpus-divergence.js undercounts and needs fixing before the measurement is trusted. The register entry names the wrong fields. Measured over 277,690 treatments: ZERO zero- valued `insulin` (0 of 107,732) and ZERO zero-valued `carbs` (0 of 12,394). The field that actually carries falsy values is `absolute` - 67,521 of 153,315, 44% - the zero temp basal. `duration:0` adds 2,094. The entry also omits the ±2s window (maxtimediff). GT3's reading: a bug, not intent - the author built an explicit selected/fallback mechanism, so truthiness on `absolute` means the code treats a zero temp as "no value here", which is false in AID terms.

### `BFQ-10` &mdash; BF-10 - mongod fatal-asserts at Docker's default nofile=1024

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-10` |

**Blast radius.** docker-compose.yml at the repo root, one `ulimits:` block.

**What an operator sees.** If you run Nightscout with the bundled Docker setup, the database can stop with a fatal error because the container is allowed too few open files. Adding one setting to the compose file fixes it.

**Why `patch`.** a configuration file the project ships

**Gates.**

- `[static]` _(cwd: `externals/cgm-remote-monitor-official`)_ `grep -q 'ulimits' docker-compose.yml`
  - FAILS today. GT3 verified the mongo service carries no ulimits block on EITHER master or dev (both mongo:5.0.32 since d91a9b4c, 2026-03-17; an earlier "dev (mongo:4.4)" here was wrong), and grep for ulimit/nofile over the whole released tree returns nothing.
- **NO GATE** &mdash; REPRODUCED 2026-09-21: one branch's full suite (~2200 tests) against a plain `docker run -d mongo:7` with no ulimits killed the server. Startup warning `Soft rlimits for open file descriptors too low` (currentValue 1024, recommendedMinimum 64000), then during index creation `__posix_directory_sync` / `Too many open files` / error_code 24, then `Fatal assertion 23089 msgid 50853` at wiredtiger_util.cpp:772, then abort; container exit 14. Control: the same image with `--ulimit nofile=64000:64000` logs that warning ZERO times against TWO on the default. It is not a gate because reaching it takes a full suite against a deliberately under-provisioned mongod, and the side effect is a DEAD server - sibling worktrees sharing that mongod then fail their own suites with a `before all` timeout, which reads like a code regression. A gate whose failure mode breaks other items' gates does not belong in a shared runner. Evidence is in the register's BF-10 detail. The reproduction also shows it is not specific to the 5.0.32 image the shipped compose files pin - 7.0.43 does it too - and it does not need tenant scale: EXP-MT-040b reached it at 50 tenant databases; one ordinary test run is enough.

**Evidence.**

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`

**Notes.** PREPARED 2026-09-22 on bf2/ops 03fba725. Reproduced with the SHIPPED compose file (mongo 5.0.32) - ulimit -n 1024 in the container and a WiredTiger error-24 abort, exit 14, about 35 s into the FIRST full suite (one run, not repeated); the branch file gives 64000 and three consecutive clean full runs of 2386. The gate reads origin/dev and goes green when bf2/ops merges. The register entry's "Not a code defect; it belongs in the operator documentation" does not hold: there is a one-block landing site in the file most self-hosters actually use. The fix is that file first, docs second.

### `BFQ-04` &mdash; BF-04 - the v1 operator allowlist - superseded by P0-K

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/operators` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-operators` |
| semver | `minor` |
| review | SECURITY. Graded as code execution against the database, not only a ReDoS / full-scan exposure: measured against mongod 7.0 on origin/dev a8888f0d, the v1 filter passes a server-side JavaScript operator through to the driver, which executes it. Reachable without a token on the shipped AUTH_DEFAULT_ROLES=readable default. The ReDoS and full-scan exposures are also real. |
| ships to operators today | **yes** |
| register | `BF-04` |
| blocks on | `P0-K` |

**Blast radius.** lib/server/query.js:157 - API v1 filter pass-through reached the driver with no operator allowlist. The fix is on bf/operators, merged to dev as PR #8743 and not released; this item is a pointer and P0-K carries the gates.

**What an operator sees.** The version 1 API passed search operators straight through to the database with no list of which ones are allowed - including the ones that ask the database to run a program. The fix is merged into the development branch and arrives with the next release (15.0.9); sites running 15.0.8 still have this problem. See P0-K.

**Why `minor`.** an allowlist narrows an open pass-through, so some requests that worked will start being refused. The corpus census (T2.4) bounded which: of 157 literal find[field][$op] uses across 14 client projects, ZERO send anything the allowlist refuses. Read with its limit - it measured client source, not deployment traffic.

**Gates.**

- **NO GATE** &mdash; Superseded by P0-K, which carries the branch, the three test gates and the integration run. Duplicating them here would mean two places to keep true. The row stays as a pointer so BF-04 remains visible in the open-work lists it was once missing from.

**Evidence.**

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`
- `docs/60-research/remedial/bf04-bf70-operator-allowlist-2026-09-18.md`

**Notes.** BF-04 is HIGH severity and ships to every current operator on 15.0.8. Its register status was `fixed-in-seam`, which kept it out of every open-work list until it was extracted onto bf/operators on 2026-09-18.

### `BFQ-21` &mdash; BF-21 - pg bulkUpsert ignores {mode:'replace'}

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-21` |

**Blast radius.** lib/api3/storage/pgCollection/index.js bulkUpsert.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release; the PostgreSQL backend does not ship

**Gates.**

- **NO GATE** &mdash; The three-arm write-path harness found this (23 agree, 4 differ, 0 vacuous) but there is no standing gate that re-runs the differential against both backends. Writing one needs a live PostgreSQL and a live MongoDB, so it will be an integration gate when it exists.

**Evidence.**

- `docs/60-research/tenancy/seam-write-path-2026-09-15.md`

**Notes.** HIGHEST of the §1b entries. bulkUpsert takes no options argument, so the {mode:'replace'} every shipping caller sends is silently ignored and the write merges - a deleted field survives for good and the two backends drift apart with every write. D4 makes this permanent: "we will fix it when Postgres lands" is not available, because Postgres IS the thing landing.

### `BFQ-19` &mdash; BF-19 - pg ORDER BY reads the generated column

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-19` |

**Blast radius.** lib/api3/storage/pgCollection/sql.js orderBy.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; No differential ordering test exists between the two backends. The gate this needs is a v3 ?sort= query answered by both and compared element by element, with a deliberately tied sort chain as the control - because a comparison on a corpus that never ties is vacuous, which is exactly how BF-13 hid.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** High severity and CLIENT-REACHABLE via v3 ?sort=. It breaks the DDL's own stated invariant, which means the DDL documents a property nothing enforces.

### `BFQ-22` &mdash; BF-22 - dotted field stores nested on Mongo, literal dotted key on PG

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-22` |

**Blast radius.** lib/api3/storage/pgCollection/index.js and lib/api3/generic/patch/operation.js:85.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; Same missing differential harness as BF-21. Client-reachable via v3 PATCH; the PostgreSQL key is unreachable by any path lookup, so the write succeeds and the value can never be read back.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Id collision: the execution plan at L351 and L1189 uses "BF-22" for the process-wide language/levels leak, which is BF-31 in the register. BF-22 means this defect (GT3).

### `BFQ-23` &mdash; BF-23 - duplicate-key error reaches the caller as the backend's class

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-23` |

**Blast radius.** both adapters.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; Low severity - no shipping caller branches on it - so no gate has been written. Recorded rather than dropped because the seam's whole point is that a caller CAN branch on it, and the first one that does will find two error classes.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

### `BFQ-25` &mdash; BF-25 - credential in the request body bypasses the tenant claim check

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SECURITY - cross-tenant read AND write with any client on default config |
| ships to operators today | no (pre-release) |
| register | `BF-25` |
| blocks on | `T30-WIRING` |

**Blast radius.** lib/server/tenant-middleware.js presentedCredential and lib/authorization/index.js:40-50.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; No tenant-isolation test sends a credential in the BODY. The test that would catch it is a two-tenant request where tenant A's token is presented in the body against tenant B's host, with a control sending the same token in the header - so the two paths are shown to be distinguishable before a pass means anything.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** D14 removes this bug class structurally. Per-tenant JWT signing keys mean tenant resolution runs BEFORE any credential is examined, so cross-tenant token reuse becomes a SIGNATURE failure rather than a claim-check failure. That is why this blocks on T3.0's wiring rather than getting a patch.

### `BFQ-24` &mdash; BF-24 - TRUST_PROXY=false bypasses the TENANT_HOST_HEADER guard

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SECURITY - a client can choose its own tenant with a header |
| ships to operators today | no (pre-release) |
| register | `BF-24` |

**Blast radius.** lib/server/env.js fromEnv trust-marker check.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; The guard exists and is tested; what is untested is the ONE config pairing that bypasses it, which is the pairing the guard exists to catch. A gate needs the false/non-host pairing plus a control at the true/non-host pairing that still refuses.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** T3.1 already chose req.headers.host over req.hostname for this reason - compileTrust(''), Nightscout's DEFAULT, returns a function that always says yes. This entry is the remaining hole in that reasoning.

### `BFQ-26` &mdash; BF-26 - HTTPS redirect drops the tenant path prefix

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-26`, `CAP-01` |

**Blast radius.** lib/server/app.js:132.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; No test issues a plain-HTTP request under a path-mode tenant and follows the redirect. On by default in path mode, so the gate is cheap once written.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** This is the ONE part of CAP-01 that is a defect rather than an absence, so the register says it can land first and on its own.

### `BFQ-27` &mdash; BF-27 - config() hands back an enclave that was never armed

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-27` |

**Blast radius.** lib/server/env.js module scope and setAPISecret.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release; not reachable in production - one call site, lib/server/server.js:33. 62 test files call it.

**Gates.**

- **NO GATE** &mdash; Low and unreachable in production, so nothing has been written. The reason it stays in the register is that 62 TEST files call config(), which means a test-order change can make it reachable in the suite without anyone touching production code.

**Evidence.**

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`

**Notes.** BF-27 is the ONLY id in the register with a table row (L124) and NO detail section. That is a documentation defect in itself and is tracked at DOC- REGISTER.

### `BFQ-18` &mdash; BF-18 - driver 7 doubles the getMore batch size on .limit(0)

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-18` |
| blocks on | `RT-3` |

**Blast radius.** lib/storage/mongo-read-options.js plus driver 7.6.0.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release; compounds BF-14, which P0-E fixes

**Gates.**

- **NO GATE** &mdash; The measurement exists - drivers 5 and 6 send batchSize=1000 unprompted, driver 7 sends none and lets the server fill to the 16 MB wire limit - but no standing gate re-runs it. It needs a live MongoDB on driver 7, so it will be an integration gate.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Blocks on RT-3 because driver 7 arrives with cut 3. The constant Object.freeze({batchSize: 1000}) is load-bearing, not cargo.

### `BFQ-20` &mdash; BF-20 - scalarize() converts a Date bound to an ISO string

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-20` |

**Blast radius.** lib/api3/storage/pgCollection/utils.js.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release; no shipping caller passes a Date

**Gates.**

- **NO GATE** &mdash; Same missing two-backend differential as BF-21 and BF-22. A Date-valued filter matches NOTHING on MongoDB and EVERYTHING on PostgreSQL, which is the worst shape of divergence: both answer 200.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

### `BFQ-CAP01` &mdash; CAP-01 - Nightscout cannot be served from a sub-path

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `CAP-01` |

**Blast radius.** 6 client call sites, 1 redirect, 1 Socket.IO client option.

**What an operator sees.** Nightscout cannot be hosted at an address like example.org/nightscout/ - it has to have a web address of its own. This is a missing capability, not something that used to work and broke.

**Why `minor`.** adds a capability; nothing that works today stops working

**Gates.**

- **NO GATE** &mdash; Nothing serves Nightscout under a sub-path in any test, so there is nothing to measure against. The first gate would be a proxy fixture mounting the app at /nightscout/ and asserting the page loads and the socket connects - with a control at / so a green result is known to distinguish the two.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** The only capability entry in the register. BFQ-26 (BF-26) is the one part of it that is a defect rather than an absence.

### `BFQ-69` &mdash; BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf3/quickpick-rebuild` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/work/crm-bf3-quickpick` |
| semver | `patch` |
| review | maintainer, and whoever reviewed P0-G (#8735). The design choice to confirm is rebuilding at drawer open only, not on every data update: an option's value is an index into the quick-pick array, so a rebuild under a selection is BF-35's failure class. |
| ships to operators today | **yes** |
| register | `BF-69` |
| blocks on | `P0-G` |

**Blast radius.** One commit, 83cfff14, 2 files, +215/-2. lib/client/boluscalc.js only - prepare() begins with rebuildQuickpickChooser(), which calls the existing loadFoodQuickpicks(); the change handler is bound once at construction. tests/boluscalc.quickpick-rebuild.test.js (new, 8 tests); #8735's tests/boluscalc.quickpick.test.js unchanged. Client-side, so it needs a rebundle, not a restart.

**What an operator sees.** Not released. The Bolus Wizard is Nightscout's built-in bolus calculator. It has a Quickpick list of saved meals, each with a name and a total amount of carbohydrate. On today's release that list only ever shows (none), however many quick picks are saved, so people have to add foods one at a time instead. After this fix, opening the Bolus Wizard shows the saved quick picks in their saved order, and choosing one fills in that quick pick's own carb total. Hidden quick picks are not listed, and one set to "hide after use" disappears the next time you open the Bolus Wizard after you submit with it. Two things to know - the Bolus Wizard appears only if the site owner lists boluscalc in SHOW_PLUGINS, and only to a viewer who is allowed to enter treatments; and a quick pick added or changed elsewhere does not appear on a page that is already open until that page reloads or reconnects (see BFQ-93). Whatever the calculator shows, check the carbs against the meal you are actually eating before you rely on them; this software does not decide a dose. This is not medical advice - if you use quick picks for meal dosing, go over how you use them with your care team.

**Why `patch`.** Restores a documented feature that is inert. No API or configuration surface changes.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf3/quickpick-rebuild >/dev/null`
  - Merges into origin/dev with no conflict.
- `[unit]` `cd externals/work/crm-bf3-quickpick && n exec 20.20.0 npx mocha --timeout 30000 --exit tests/boluscalc.quickpick-rebuild.test.js tests/boluscalc.quickpick.test.js`
  - The 8 new tests and #8735's quick-pick tests, no database; 19 passing. These require lib/client/boluscalc.js directly, not the bundle. Control, run 2026-09-23 with tools/queue/gates/ablate.sh (boluscalc.js put back to origin/dev) - the new test file exits 6, the chooser offering only (none). The evidence's break-its B1 (the register's one-line candidate, handler stacked 4 times), B2 (rebuild removed) and B3 (BF-35's loop put back, wrong carbs) are each red.
- `[integration]` `NSREVIEW_ROOT=${NSREVIEW_ROOT:?} node tools/review/probes/quickpick-chooser-browser.js --base "$NSREVIEW_BASE_URL" --candidate "$NSREVIEW_CANDIDATE_URL" --secret "$NS_HARNESS_SECRET"`
  - Clicks the Bolus Wizard exactly as a user does and reads the chooser. It does not call loadFoodQuickpicks itself, which probes/food-boluscalc-browser.js does deliberately to reach BF-35; the difference between the two probes is this defect. Green only when the chooser is both populated and correct, because a build that repairs it without bf/food offers 8 entries and throws 5 times. 4/4 on the branch against dev and against 15.0.8, 2026-09-23.
- **NO GATE** &mdash; The sequencing constraint (never ship before P0-G, #8735) is met by ancestry - the branch is one commit on 74fc6619, which carries #8735 - and blocks_on still records it. Nothing gates a reviewer cherry-picking the commit onto a base without #8735. The full suite (2394/0/3 on Node 20.20.0 and 22.23.2, +8 exactly) needs MongoDB and a rebuilt bundle and is recorded in the evidence.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf69-quickpick-rebuild-2026-09-23.md`
- `docs/30-design/remedial/dev-cycle-review-harness-plan-2026-09-17.md`
- `docs/30-design/remedial/rc-15.0.9-additions-d-2026-09-23.md`
- `docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md`

**Notes.** MERGED 2026-09-23 into dev (now 4011193e); NOT RELEASED. #8756 as c11888ed. CI and CodeQL green. PREPARED 2026-09-23 - bf3/quickpick-rebuild 83cfff14, one commit on 74fc6619, not pushed. BF-35's probes still pass on the branch (food- boluscalc-browser.js 5/5 against 15.0.8). The register's one-line candidate was not used as written, because it stacks one more change handler per open. SHIPS IN 15.0.9 (maintainer, 2026-09-23). Integrated on rc/15.0.9-additions-d 5764156e, 2520/0/3 on every Node and MongoDB pair (docs/30-design/remedial/rc-15.0.9-additions-d-2026-09-23.md); PR body drafted in reports/phase0-pr-bodies/bf3-quickpick-rebuild.md. Food edits made while a page is open still do not reach it (BFQ-93). Reproduced 2026-09-17 in a browser against the review harness, on a8888f0d and on rc/2026-09-dev-cycle: 8 food records present, chooser empty on both. SEQUENCING, MEASURED: the one- line change applied to a8888f0d without bf/food makes the chooser offer eight entries - every plain food plus the quick pick the user hid - and selecting them throws five times. BF-35's dose consequence is latent on 15.0.8 only because BF-69 hides it. Repairing the chooser first converts a latent high- severity defect into a live one in a bolus calculator. Ship with P0-G (merged to dev as #8735) or after it, never before.

### `BFQ-71` &mdash; BF-71 - any dateString key drops the default date window, and the window is not a control

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@59430336` |
| worktree | `externals/work/crm-advisory` |
| semver | `patch` |
| review | maintainer. Severity low: this is not a privilege boundary, reproduced with its control in the same run (2026-09-21). The security advisory framed it as a date-window bypass exposing full history; the default window is a paging default, and the allowlisted wide date bound reaches the same records on the same authorisation. What remains is an ordinary correctness defect - two spellings of one intent that behave differently. |
| ships to operators today | **yes** |
| register | `BF-71` |

**Blast radius.** lib/server/query.js - the guard at :98, `!dateValue && !query.dateString`, and the default set at :47-48 (TWO_DAYS * 2). One function. Server-side, so a restart carries it; no rebundle.

**What an operator sees.** Nothing changes for you, and nothing you are running is less safe than you thought. Nightscout's older API returns about four days of data when a request does not say what period it wants. A request that mentions the date field in a particular way gets the whole history instead - but so does a request that simply asks for the whole history, which the API has always allowed and documents. Both need whatever password or token your site requires; on a site that allows anonymous reading, which is Nightscout's default setting, both work without one. If it matters to you that strangers cannot read your glucose history, the setting to look at is AUTH_DEFAULT_ROLES, not this fix. Nightscout is not a medical device and this is not medical advice.

**Why `patch`.** No declared surface moves. A request that used to receive the full history because it named dateString would receive the default window instead, which is the documented behaviour for a request that expresses no date constraint; the full history stays available through find[date][$gte]=0. Caveat: if any client in the wild relies on the current behaviour, this is a behaviour change for that client, and the client census measured source rather than runtime, so it cannot rule that out.

**Gates.**

- `[static]` `node tools/queue/gates/bf71-date-window-presence-check.js`
  - Reads the shipping lib/server/query.js out of the object database and asserts the dateString arm is not a bare presence check. FAILS today, by design. Non-vacuity proven both directions on 2026-09-21: against the scratch ref tmp/bf71-vacuity-probe (a date-constraint test spliced into an isolated copy) the gate goes green with its control still green, and against an empty QUEUE_GATE_ROOT it fails rather than passing by absence. The in-file control - the configured date field is tested by value - distinguishes "the matcher sees nothing" from "the defect is present".
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/operators origin/dev`
  - A dependency check, not a claim about BF-71. The measurement that establishes this entry's severity was taken on a dev tip that already contained #8743; if the allowlist ever left dev the reproduction would need retaking before the `low` severity could be quoted. Green today.
- **NO GATE** &mdash; The severity measurement is not in this repository and must not be read off the static gate. What set this entry to `low` was a booted v1 app against mongod 7.0.43 running the allowlisted control and both role settings in one process - five requests, two configurations. A static gate over one function cannot express that. The probe is externals/work/crm-advisory/tmp/bf71-date-window-default.js, gitignored in both repositories, and it carries its own control.
- **NO GATE** &mdash; Nothing here gates the fix shape. One was verified on a scratch ref, not prescribed: testing dateString for a date constraint instead of for existence restored the 4-day window (3 records instead of 10) while the allowlisted wide bound still reached 10. The register does not choose between "test it like the other field" and "bound on whichever date field the query names".

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Filed 2026-09-21, before any fix was attempted. There is no boundary here. `opts.deltaAgo` is a paging default whose own source comment is `// TODO: discuss/consensus on right value/ENV?`, and the allowlisted find[date][$gte]=0 reaches the same records on the same authorisation. P0-K's review note and the register's BF-04 detail block now say so; the merged PR #8743 body still describes it as a bypass and cannot be edited after merge. Why it is still worth fixing: two spellings of one intent are not equivalent when one silently removes the bound, and BFQ-72 is the case where the size of the scan a single anonymous request can cause is the entire finding.

### `BFQ-72` &mdash; BF-72 - an unauthenticated $regex can spend minutes of database CPU

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@59430336` |
| worktree | `externals/work/crm-advisory` |
| semver | `minor` |
| review | SECURITY, and the same person who has to answer P0-K's sequencing question, because it is the same question about the same advisory. Disclosure-sensitive: this is a one-request unauthenticated denial of service against a default install, live on 15.0.8 and on dev 74fc6619, with no fix yet. The register describes the mechanism only; the reproducing patterns are deliberately not in any tracked file, and the probe is outside version control. The ordinary path for this stack - a public issue or PR carrying the reproduction - would publish a working attack against every unpatched Nightscout, and there is no patch to move to. The open decision is whether Nightscout's security contact process is invoked. |
| ships to operators today | **yes** |
| register | `BF-72` |

**Blast radius.** No line is wrong, which is why this is needs-decision and not not-started. $regex and $options are in lib/server/query-operator-allowlist.js FIELD_OPERATORS by design, and lib/server/query.js promotes a treatments text field to a regex as a documented search affordance. A fix changes what the search affordance accepts, so its blast radius is every client that sends a pattern - which the 14-project census counted as source, not runtime.

**What an operator sees.** DRAFT - DO NOT PUBLISH AHEAD OF A DISCLOSURE DECISION. Nightscout's older API lets a request search some text fields using a search pattern. There is no limit on how complicated that pattern may be, and a complicated one can make the database work for minutes on a single request - long enough that the site stops answering for everyone using it. On a site that allows anonymous reading, which is Nightscout's default, no password or token is needed to send one. Your data is not exposed or altered by this; what is at risk is the site being there when you look at it. If you watch Nightscout to make decisions, this is a reason to have a second way to see your readings - which is good practice regardless. Restricting access at your proxy or hosting provider is what helps today. Nightscout is not a medical device and this is not medical advice; discuss what you rely on Nightscout for with your care team.

**Why `minor`.** Every candidate fix removes reachable behaviour from a documented search affordance - a pattern that works today stops working - so it is not a patch by the project's own reading of its surface. Not major: no route is removed, no required input is added, and ordinary patterns are unaffected. If the chosen fix turns out to reject a pattern shape a real client sends, that reclassifies it, which is an argument for measuring runtime traffic before choosing.

**Gates.**

- `[static]` `node tools/queue/gates/bf72-regex-operand-bounded.js`
  - Asserts that some bound on the $regex operand exists on the v1 read path - a length cap, a required literal prefix, a complexity rejection or a linear-time engine - without prescribing which. FAILS today, by design. Its first finding is the control: $regex must be reachable for the finding to exist, so a future change that refused the operator outright flips the control rather than passing silently. Non-vacuity proven both directions on 2026-09-21 against the scratch ref tmp/bf72-vacuity-probe. The detector is line-scoped and name-based, because the natural site for a fix is over a thousand characters from the accept-set literal and a proximity-based detector did not flip under the same ablation.
- **NO GATE** &mdash; The timing measurement is deliberately not in this repository; the static gate above is the cheaper half of the evidence, not the finding. Recording the timing measurement here would mean recording the patterns, and this repository is public while the defect is live on the shipping release (the same constraint as BF-70). Held outside version control at externals/work/crm-advisory/tmp/bf72-regex-cpu.js with its README. Reproduced 2026-09-21 on dev 59430336, 20 000 seeded entries, mongod 7.0.43: control 22 ms, benign anchored prefix 29 ms, three adversarial patterns 60 s / 65 s / 71 s, stable across two runs.
- **NO GATE** &mdash; No fix is gated because no fix has been measured. Four candidates are named in the register - pattern length cap, required literal prefix, complexity rejection, linear-time engine - and each trades capability for cost. Choosing is a decision about the search affordance's contract, not an engineering task with a prescribed answer.
- **NO GATE** &mdash; The amplification figure is a floor, not a measurement of a real site. 20 000 documents is small; a real entries collection is far larger and the cost grows with it. Nothing here measures a real deployment, and nothing should - rule 0 forbids pointing this at anyone's instance.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Disposition decided by the maintainer 2026-09-23; details are held outside version control. Found 2026-09-21 while re-measuring the security advisory's third proof of concept, which the advisory frames as $regex data extraction. On the shipped `readable` default that is close to vacuous - entries, treatments and devicestatus are the three collections prep_storage admits, all three are already readable, and the API returns whole documents, so a regex oracle reveals nothing a plain read does not. What the same operator does do is cost the database, which the advisory does not describe. Sequencing with P0-K: #8743 merged on 2026-09-18 and did not narrow $regex, because the client census found real clients sending it. So this entry is not a regression from that branch and is not fixed by it. State is needs-decision rather than gate- not-met: a gate fails, but the blocking thing is not work. It is whether Nightscout's security contact process is invoked and in what order - the same question P0-K left open, still unanswered.

### `BFQ-40` &mdash; BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-coercion` |
| semver | `minor` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-40` |

**Blast radius.** BOOLEAN_OPERANDS / readBooleanOperand in lib/server/query.js, applied over the built query so it also covers fields the type table does not name. Merged to dev via #8737 on 2026-09-18; not released. The NON_VALUE_OPERATORS exclusion in lib/server/query-coercion.js is a different mechanism - it stops the field- domain coercer mangling the operand, which is what lets the boolean reader own it.

**What an operator sees.** If you or a tool you use asks Nightscout for records that do NOT have a particular field - for example entries with no "sgv" (sensor glucose) value - today's release (15.0.8) gives you back exactly the records that DO have it: the opposite of what was asked, with no error. Asking for records that DO have a field works correctly. The repair has been merged into the development version and arrives with the next release (15.0.9); until you are running that release, the problem is still present.

**Why `minor`.** It changes what a documented v1 endpoint returns for a documented query parameter, in the direction of correctness, which is the same class as BF-02 and BF-03 and needs the same release note.

**Gates.**

- `[integration]` `NSREVIEW_ROOT=${NSREVIEW_ROOT:?} node tools/review/probes/pair-reads-coercion.js --base "$NSREVIEW_BASE_URL" --candidate "$NSREVIEW_CANDIDATE_URL" --secret "$NS_HARNESS_SECRET"`
  - Measured 2026-09-17 on a 582-document seed (577 sgv, 5 mbg): find[mbg][$exists]=false returns 577 on bf/coercion and 5 on dev. The arm asserts against the seeded expectation, never against the same build's list endpoint - on bf/reads alone those two agree at 5 and both are wrong.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** The merged PR #8737 body's operator-facing text says find[sgv][$exists]=true "became $exists: NaN, which MongoDB reads as false, so the query returned exactly the records you did not ask for". That sentence is false - $exists=true is answered correctly before and after - and a release note must not repeat it, because it tells operators to distrust queries that were right. What #8737 repairs is $exists=false (this entry, BF-40) and the $regex server error (BF-32).

### `BFQ-41` &mdash; BF-41 - a reading dated ahead of the clock silences the stale-data alarm (closed, does not reproduce)

| | |
|---|---|
| state (claimed) | `closed` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer - decided 2026-09-23: closed as not reproducing (evidence section 5, option 1), no tolerance setting. |
| ships to operators today | no (pre-release) |
| register | `BF-41` |

**Blast radius.** Nothing built. The behaviour lives in lib/sandbox.js lastEntry (the notInTheFuture filter, since 556091bf, 2015) and lib/plugins/timeago.js checkStatus and checkNotifications. Local branch bf3/future-reading-stale exists at 74fc6619 with no commits.

**What an operator sees.** Nightscout can warn you when no new glucose reading has arrived for a while. By default it warns in the browser at 15 and 30 minutes. An earlier note said that one reading stamped with a time in the future would switch that warning off. That is not what happens: Nightscout skips readings that are dated in the future when it decides whether your data is stale, and the warning still comes. The related case that does happen, a device clock set ahead making the warning come late, is BFQ-95. This is not medical advice.

**Why `n/a`.** nothing ships; the item is closed as not reproducing

**Gates.**

- `[static]` `node tools/queue/gates/timeago-future-reading.js`
  - Loads readings into the data the sandbox is built from and lets the shipping lib/sandbox.js lastEntry choose the reading, on the server path (serverInit, checkStatus, checkNotifications with alerts on, the push request recorded) and the browser path (clientInit, checkStatus). PASSES when the registered defect does not reproduce - a real reading 40 or 20 minutes old still gives urgent or warn on both paths, and the push alarm, when a reading 3 to 120 minutes ahead is also loaded - and FAILS if a future-dated reading ever silences either path. Three controls (2, 20, 40 minutes, no future reading) must come out current, warn and urgent. Measured 2026-09-23 - green, 8 checked / 0 failing, on the official checkout; with the notInTheFuture filter replaced by `return true` in a scratch copy of the dev tree (--tree), the four future arms go current with no push, 4 failing, exit 1, and the controls stay green. The earlier version of this gate stubbed sbx.lastSGVEntry past that filter and was vacuous.
- **NO GATE** &mdash; "No usable reading means no alarm" (every loaded reading in the future, or none loaded) is the checkStatus no-reading branch assuming current. It is not specific to future readings, and nothing gates it.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf41-future-reading-2026-09-23.md`
- `tools/remedial/bf3/bf41-real-sandbox.js`

**Notes.** CLOSED 2026-09-23 (maintainer) - does not reproduce as stated; no tolerance setting is added. The evidence section 7 text ships as a 15.0.9 known issue. The gate above runs through the real sandbox since b248bb73. The clock-ahead residual is BFQ-95 (BF-95). MEASURED 2026-09-23 - does NOT reproduce as registered (reproduced-negative through the real sandbox on 74fc6619 and 15.0.8, with a break-it that removes the 556091bf filter and brings the symptom back). The decided tolerance was not built: in the case "a real reading 20 minutes old plus one 3 minutes ahead" the warning fires today and would stop firing. It changes nothing in the clock-ahead case, which is the consequential one. SUPERSEDED by the closure above - DECIDED 2026-09-23 (maintainer) - a reading dated ahead of the clock is kept as sent, and the stale-data check uses the newest reading that is not in the future; no new warning. "In the future" means more than a tolerance ahead of the server clock, configurable, default 5 minutes. Snooze runs on the wall clock. The hosted evaluator may apply the same rule, but never to live alarms. BF-44 is a concrete, shipping way to produce a future-dated reading, which is why BFQ- MINIMED carries the same severity argument from the other end.

### `BFQ-87` &mdash; BF-87 - the root qs override holds the connector below its range and pins the server's query parser

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/qs-6.16` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/work/crm-qs-616` |
| semver | `patch` |
| review | maintainer - whether it rides in 15.0.9 or backfix 2 is a release decision |
| ships to operators today | **yes** |
| register | `BF-87` |

**Blast radius.** package.json overrides.qs and overrides.request.qs (both 6.15.1, from 5ab0af7a) and the lockfile. The single resolved qs is the one express and body-parser parse every query string with.

**What an operator sees.** Not released. Nightscout forces an older version of a small library that reads the part of a web address after the "?". That version sits inside three published security advisories rated moderate, and it is older than the connector says it needs. Whether any of those advisories can be used against Nightscout has not been measured. The fix is to move to the library's newer version.

**Why `patch`.** a dependency override moves; no declared surface changes unless the parser's behaviour does, which the suite must show it does not

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official show origin/dev:package.json | python3 -c "import json,sys; o=json.load(sys.stdin)[\"overrides\"]; sys.exit(1 if o.get(\"qs\")==\"6.15.1\" or o.get(\"request\",{}).get(\"qs\")==\"6.15.1\" else 0)"`
  - FAILS today - origin/dev still overrides qs to 6.15.1 at the root or under request.
- `[static]` `git -C externals/cgm-remote-monitor-official show bf/qs-6.16:package.json | python3 -c "import json,sys; o=json.load(sys.stdin)[\"overrides\"]; sys.exit(0 if o.get(\"qs\")==\"6.16.0\" and o.get(\"request\",{}).get(\"qs\")==\"6.16.0\" else 1)"`
  - The prepared branch sets both qs overrides to 6.16.0.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/qs-6.16 >/dev/null`
  - Merges into origin/dev with no conflict.
- **NO GATE** &mdash; Exploitability through Nightscout's routes is not measured, and the remedy (6.16.0) changes the parser every request passes through; the full suite plus Nightscout's documented query shapes are the evidence it needs, and neither is a static gate.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** MERGED 2026-09-23 into dev (now 4011193e); NOT RELEASED. #8749 as 9fd4600e. CI and CodeQL green on the merge commit. OPENED 2026-09-23 as nightscout/cgm- remote-monitor #8749 (head 46b20b38, base dev). DECIDED 2026-09-23 (maintainer) - qs 6.16.0 goes into 15.0.9. The only measured behaviour change is that 15 malformed bracket spellings no longer get silently rewritten into a different filter. PREPARED 2026-09-23 - bf/qs-6.16 46b20b38, one commit; the lock moves qs 6.15.1 -> 6.16.0 and side-channel 1.1.0 -> 1.1.1 (required by qs), nothing else; one qs@6.16.0 resolves for all five consumers. Parse differential under express's and body-parser's own options - 638 inputs (README, swagger, tests, census, eventTypes, depth/array/parameter limits), 1,914 comparisons, 45 differences, all from 15 malformed bracket keys (e.g. nested brackets, an unclosed bracket); every documented or client shape is identical. Those keys now match nothing or get a 400 from the operator allowlist instead of being silently rewritten. Control - the 6.15.2 changelog's nested-bracket example is detected. Suite dev 2386/0/3 = branch 2386/0/3 on Node 20.20.0 and 24.20.0. npm audit --omit=dev - qs and its three dependants leave the list; no new findings. Advisory reachability is read, not run (PR body). Candidate for 15.0.9. Found 2026-09-22 while pinning the connector (P0-PIN). The same class as BF-43. Candidate for 15.0.9 given it is one override value, but that is the maintainer's call.

### `BFQ-CONNECTOR` &mdash; BF-42, BF-43 - master pins the leaking connector, with a violated axios override

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/master` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `patch` |
| review | SECURITY, and a human security reviewer, for the same reason P0-C gets one - this is credential disclosure, not a dependency bump |
| ships to operators today | **yes** |
| register | `BF-42`, `BF-43` |
| blocks on | `P0-TAG` |

**Blast radius.** Two lines of origin/master's package.json - the nightscout-connect dependency URL (tag v0.0.13) and overrides['nightscout-connect'].axios - plus the lockfile that follows them. No cgm-remote-monitor source changes.

**What an operator sees.** The version of the connector (the part of Nightscout that fetches your readings from your CGM company's cloud service) that today's release (15.0.8) installs writes your CGM service's username and password, its session tokens, and your glucose readings into Nightscout's log. It does this every time Nightscout starts, for every data source, before it contacts anything, and there is no setting that turns it off. Anyone who can read your logs - which on many hosting platforms is more people than you might expect - can read those credentials. If you have been running this, treat the password for your CGM account as exposed and change it, and change it anywhere else you have used it. The fix changes which connector version is installed; it does not change how your data is collected, and it has not been released yet.

**Why `patch`.** A dependency pin moves to a newer patch of the same package. No declared surface of cgm-remote-monitor moves. It nonetheless needs a security note, which is a different obligation from a version number.

**Gates.**

- `[static]` `node tools/queue/gates/connector-pin-exposure.js --refs origin/master,origin/dev`
  - FAILS on origin/master for both arms - the v0.0.13 tag tarball (112 live console.* sites, 101 passing a non-literal argument, no debug guard anywhere) and an axios override of 1.16.0 against the connector's declared ^1.18.1. origin/dev is the control and passes both, which proves the gate reads the pins and not the command: dev's pin 234d47c deletes the leaking call sites (so "dev only makes the logging opt-in" is inaccurate). 234d47c is in connector dev (1946beb, 2026-09-22) and in prerelease 0.1.0-dev.1, and in no full connector release.
- **NO GATE** &mdash; No live run and no vendor account. The census is a source census of a git archive extraction, and rule 0 forbids creating an account or contacting a vendor. It is non-vacuous in the way that matters - the same scanner returns 112/101 on the leaking tree, 22/20 on the redacted ones, and correctly reports cut 4's commented-out MiniMed block as 47 calls with zero dynamic arguments, so it distinguishes deletion from commenting-out.
- **NO GATE** &mdash; No runtime failure is claimed for the axios override, and no axios API was identified that the connector uses and 1.16.0 lacks. The defect is the silent constraint violation - `overrides` exists precisely to suppress the ERESOLVE that would report it - and nothing gates "a constraint was overridden into violation" in general.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/40-migration/connector-pin-consolidation-2026-09-15.md`

**Notes.** 2026-09-23 - the gate resolves an exact registry pin through the connector's v<version> tag. On origin/dev ddd9b600 both checks pass: the pin is 0.1.0-dev.3 (not the v0.0.13 tag) and the axios override 1.20.0 (dependabot #8565, 2026-09-05) satisfies the connector's ^1.18.1. It stays red for origin/master (15.0.8) until 15.0.9 is released. Register BF-42 and BF-43 are merged. 2026-09-22 - connector-pin-exposure.js reports BF-43 UNRESOLVED for a registry-version pin (bf/connect-pin-0.1.0): it only maps tarball URLs to a connector revision. It needs to resolve a registry pin via tag v<version> or the registry gitHead before it can certify the 15.0.9 pin. Checked by hand meanwhile - 1946beb declares axios ^1.18.1, the override is 1.20.0. BF-87 (qs) is the same override class, tracked on BFQ-87. The fix is the same one-line pin move as P0-PIN, applied to master rather than dev, and it cannot be prepared until a full connector release exists. Connector dev 1946beb (2026-09-22) carries the fixes and prerelease 0.1.0-dev.1 is on npm; P0-TAG is the full 0.1.0 release. RT-CONNECT-PIN-CUTS is the same change on cuts 1-3 and is filed separately because those are pre-release (§1b) and this is not.

### `BFQ-MINIMED` &mdash; BF-44, BF-45, BF-85 - MiniMed ingestion divergences and the CareLink zero reading

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer, plus somebody who actually runs a MiniMed pump, because the open question is about real CareLink payloads |
| ships to operators today | **yes** |
| register | `BF-44`, `BF-45`, `BF-85` |

**Blast radius.** BF-44 - nightscout-connect's CareLink source reassign_zone, against the retired minimed-connect-to-nightscout transform.js:41-85. BF-45 - setupMMConnect in lib/server/bootevent.js, which references Connect nowhere while setupBridge stands down for it.

**What an operator sees.** Two problems that affect people using a MiniMed pump with CareLink. First, the old built-in CareLink connection and the newer connector work out WHEN a reading happened in different ways, so the same reading can be filed at a different time by each. If it is filed in the future, the "no new data" warning stops working - see the separate item on that. Second, if you set up the new connector while the old CareLink connection is still switched on, BOTH run at once. For Dexcom the old one stands aside automatically; for MiniMed it does not. So any advice to "set up the new connection before removing the old one" is safe for Dexcom and NOT safe for MiniMed. The project maintainer confirms that the old built-in CareLink connection does not work, so in practice the first two problems do not corrupt data: the old connection fails to log in rather than filing readings. Third, when CareLink reports "no reading" for a moment, the connector saves it as a glucose value of 0, and while that is the newest value Nightscout's high and low alarms are not checked. Keep your pump's and CGM's own alarms switched on. Your glucose data continuing to arrive, at the right time, and your alarms being checked is what is at stake here. This is not medical advice; if you are changing how your data reaches Nightscout, plan it with your care team.

**Why `minor`.** BF-45's repair adds a stand-down guard to a boot stage, which changes what a deployment with both configurations does. BF-44's repair changes the timestamp a reading is stored with, which is a data-affecting change and cannot be a silent patch.

**Gates.**

- **NO GATE** &mdash; The divergence itself is reproduced and recorded in the register - both shipping implementations loaded side by side, three arms diverging by exactly the offset (UTC+2, UTC-7, UTC+5:30) and two controls agreeing (UTC+0, and UTC+2 with a zone-bearing lastConduitDateTime). It is not re-run as a queue gate because the arm/control roles invert with the server's own timezone: the magnitude is (pump offset minus server offset) whenever the payload carries no zone designator, so under TZ=Europe/Berlin the Berlin arm agrees and the UTC control diverges. A gate that did not pin TZ would report the opposite result on a differently configured machine, which is worse than no gate.
- **NO GATE** &mdash; What decides active versus latent cannot be measured from here - do real CareLink payloads omit lastConduitDateTime, and do sgs[].datetime, markers[].dateTime and sMedicalDeviceTime carry zone designators of their own? That needs a real CareLink account, which rule 0 forbids. Coverage is thin in exactly the way that hides it: lastConduitDateTime appears zero times in tests/fixtures/minimed-cutover.json and in tests/connect-minimed-cutover.test.js, and the one connector test that sets the field passes a Z-suffixed value, which makes the rewrite a no-op - that test is a control, not coverage.
- **NO GATE** &mdash; BF-45's double ingestion is read-derived from both function bodies in full on master and dev, not run as a live double ingestion. Medium alone, because the sysTime+type upsert absorbs duplicate writes; high in combination with BF-44, where the two paths compute different keys and nothing absorbs them. That combination is why these two are one item.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md`

**Notes.** Also recorded on BF-44 and not separately filed: pump.clock is not parsed at all, deviceStatusEntry assigns data['sMedicalDeviceTime'] verbatim, so a client doing new Date(pump.clock) can get Invalid Date. And the legacy transform throws RangeError on a Z-suffixed payload outside the MMCONNECT_SERVER=EU / GUARDIAN branch rather than producing a comparison value, so the reproduction arms hold only with MMCONNECT_SERVER=EU. BF-44 and BF-45 are graded low: the maintainer confirms the legacy mmconnect path does not work, which is operational knowledge and not measured here. BF-85's connector fix, 8406edf, is in connector dev (via PR #64, 2026-09-22) and in prerelease 0.1.0-dev.1, and in no full connector release; it reaches operators through P0-TAG and P0-PIN.

### `BFQ-46` &mdash; BF-46 - eleven API v3 variables bypass env.js, one family deletes data

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer - the documentation half is the load-bearing half and it is a decision about what to promise, not only what to write |
| ships to operators today | **yes** |
| register | `BF-46` |

**Blast radius.** lib/api3/index.js:24-38 setENVTruthy and its call sites at :70-76, plus lib/api3/generic/collection.js:32 and :129-152. Documentation for eleven names that appear in no documentation at all.

**What an operator sees.** Nightscout's newer API reads eleven settings straight from the environment (the configuration values your hosting platform passes to Nightscout), and none of them is written down anywhere - not in the README and not in the settings list. Six of them, one per kind of record, DELETE your stored history older than a number of days you give. One of those covers entries, which is your glucose history. The deletion cannot be undone, and Nightscout does not check whether it worked, so a failure is not reported either. If you run Nightscout on a hosting platform where someone else sets environment variables for you, this is worth checking. Nothing here changes unless one of these is set.

**Why `minor`.** Routing them through env.js makes eleven names part of the documented configuration surface for the first time. Nothing that works today stops working; a surface appears.

**Gates.**

- `[static]` `node tools/queue/gates/config-surface-census.js --arm api3`
  - FAILS today on both arms. Ten API3_* names (four flags plus API3_AUTOPRUNE_ for six collections) are absent from README.md and from lib/server/env.js, and the autoprune path calls storage.deleteManyOr without awaiting the result. Controls come out the other way through the identical lookup - MONGO_CONNECTION and DISPLAY_UNITS are found in both files - so "not found" means absent rather than a broken grep, and the call sites are confirmed present before their names are reported on.
- **NO GATE** &mdash; The deletion path is read-derived, not executed. Nobody has run API3_AUTOPRUNE_ENTRIES against a database and watched rows go. Doing so needs MongoDB and a corpus that can be destroyed; the right instrument is a rehearsal harness with a restore, not a gate.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Kept out of BFQ-ENV deliberately. The other three are a documentation and plumbing residue; this one irreversibly deletes a person's glucose history through a name nobody can look up, with the result unawaited. A reviewer should not have to find it inside a batch whose other members are a README typo and a dead settings key.

### `BFQ-47` &mdash; BF-47 - an ordinary subject edit destroys stored fields, on today's release

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf2/subject-edit-keeps-fields` |
| base | `bf2/auth-hardening@29e6430e` |
| worktree | `externals/work/crm-bf47` |
| semver | `major` |
| review | maintainer, AND the security reviewer who takes P0-C, together - this is the one irreversible change in the Phase 0 batch and the question has to be answered BEFORE merge, not after |
| ships to operators today | **yes** |
| register | `BF-47` |
| blocks on | `P0-C` |

**Blast radius.** lib/authorization/endpoints.js:40 pick(), lib/admin_plugins/subjects.js PUT, lib/authorization/storage.js save() replaceOne with upsert. The same three files P0-C already touches.

**What an operator sees.** Editing a person or device entry (a "subject") through Nightscout's admin page already throws away fields that are not shown on that page - notes, the date it was created, and anything a third-party tool has stored there. It happens silently, there is no error, and it cannot be recovered by going back to an older version of Nightscout. This is how today's release (15.0.8) behaves.

**Why `major`.** The repair on bf/auth narrows the loss rather than introducing it, but it also introduces an allow-list, so a third-party tool can no longer preserve its own fields by sending them in its own PUT - which it can do today, because save() writes the caller's object as given. That is a capability removal on an HTTP surface.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 29e6430e bf2/subject-edit-keeps-fields`
  - Built on bf2/auth-hardening, whose allow-list is the declared schema.
- `[integration]` `cd externals/work/crm-bf47 && TEST=authsubjects npm run test-single`
  - 13 cases, 5 of them new - an admin-page form edit, removing every role, a PUT omitting notes and created_at, a PUT clearing notes, and the role variants. Control, re-run by the coordinator 2026-09-23 - with 29e6430e's storage.js the 5 new cases fail and 8 pass.
- **NO GATE** &mdash; The admin-page path in a real browser is shown by tools/review/probes/subject-edit-keeps-fields-browser.js (passes --expect base on 29e6430e, --expect fixed on the branch); a browser run is not a queue gate.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md`

**Notes.** 2026-09-23 - the fix, 7103f657, is the last-but-two commit on bf2/auth- hardening and so is in review as #8754 (head 0ca46d92). Nothing of BFQ-47 is pushed separately. DESTINATION 15.0.9 (plan section 1a, "backfix 2 scope", 2026-09-23). Evidence - the rc-c integration record, rc/15.0.9-additions-c b9c9828b, 2508/0/3 on every Node and MongoDB pair; this unit's step added +5 and its three break-its are red. The record recommends folding this branch into the auth-hardening PR as its last commit; the auth-hardening PR body at b248bb73 records that as the maintainer's 2026-09-23 decision (see BF2-AUTH). PREPARED 2026-09-23 - bf2/subject-edit-keeps-fields 7103f657, one commit on bf2/auth-hardening. REPRODUCED in a real browser, read back from mongo - on dev an admin-page subject edit sets notes to "" and replaces created_at with the edit time; on bf2/auth-hardening notes survive but created_at is still replaced; the role editor keeps both on every base (its GET serves whole documents), so the admin-page defect is subjects only. Fix is a server-side fill-in in storage.js save() for notes and created_at only - an absent notes key keeps the stored value, a present one (even '') is written, so clearing still works. roles is deliberately NOT filled in - the admin page sends no roles field when the last role is removed, and filling it would silently keep access. Suite 2462/0/3 -> 2467/0/3. DECIDED 2026-09-23 (maintainer) - NO compatibility flag for the subject-field allow-list. The allow-list IS the declared schema for subjects (name, roles, notes, created_at) and roles (name, permissions, notes, created_at); fields outside it are not part of the contract. What remains is the admin-page defect - an edit through the admin page must keep notes and created_at. DECIDED 2026-09-23 (maintainer) - the allow-list is intended and stays (option 2). No open-source client in the corpus depends on storing other subject fields. The loss that remains is the admin page: it fetches subjects without notes and created_at, then saves the whole subject back, so an ordinary edit clears both. That is the defect to fix. A verifier's review of bf/auth established that the field loss already happens on the current release, not only on the unmerged branch. Keeping the security goal of BF-17 - the derived token never reaches the database - does not require the allow-list.

### `BFQ-ENV` &mdash; BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-48`, `BF-49`, `BF-50`, `BF-51` |

**Blast radius.** lib/plugins/webhook.js:36-39, lib/settings.js:48-49 against lib/server/env.js:114, README.md:240 and :399, azuredeploy.json. Four files plus documentation; no request path changes.

**What an operator sees.** Four settings problems, none of which changes how Nightscout treats your data. The webhook plugin reads four settings that appear in no documentation. One security setting - whether the HTTPS security header also covers sub-domains - has two different spellings, and only the one in the README works, so setting it the other way does nothing. Four more security-related setting names in Nightscout's own settings list are read by nothing at all. The README documents a MONGODB_COLLECTION setting that no code reads, so setting it silently does nothing. And the one-click Azure deployment offers a Node version field that controls nothing.

**Why `minor`.** Making the second HSTS spelling work, and routing WEBHOOK_* through the settings layer, both cause a setting that previously did nothing to start doing something on deployments that already set it. That is a behaviour change for those deployments even though it is a repair.

**Gates.**

- `[static]` `node tools/queue/gates/config-surface-census.js --arm webhook`
  - BF-48. FAILS today - WEBHOOK_PROTOCOL, _HOST, _PORT and _PATH are in neither README.md nor env.js, while the call site reading process.env.WEBHOOK_* is confirmed present first, so a green result could not come from the plugin having been renamed.
- `[static]` `node tools/queue/gates/config-surface-census.js --arm hsts`
  - BF-49. Executes lib/settings.js and records the env names its own nameFromKey asks for, rather than grepping for a spelling - the defect is that two spellings exist, so a gate hardcoding one could not detect a third. FAILS on SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS. The control is inside the same family: 4 of the 5 generated security names are read by env.js, so the miss is a divergence and not a broken compare.
- `[static]` `node tools/queue/gates/config-surface-census.js --arm readme`
  - BF-50. FAILS while README.md documents MONGODB_COLLECTION and none of the five configuration and storage modules reads it. Control - the same files do contain ENTRIES_COLLECTION.
- `[static]` `node tools/queue/gates/config-surface-census.js --arm azure`
  - BF-51. FAILS while azuredeploy.json declares a WEBSITE_NODE_DEFAULT_VERSION parameter and references it via parameters(...) zero times. Control - parameters('mongoConnection') occurs once, so a zero is a fact about that knob and not about the regex.
- **NO GATE** &mdash; BF-51 is not reproduced against a live Azure deployment - there is no Azure environment on this machine and rule 0 forbids creating one. Why deployments work today is an open question attached to the entry rather than a finding: the platform presumably ignores the literal 8.11.1 as unavailable and falls back.
- **NO GATE** &mdash; Nothing checks that a key in the settings dictionary has a consumer. BF-49's five dead keys were found by grep over lib/, views/ and static/; the general check - every settings key is read somewhere - would have caught all five at once. It does not exist, and D7/D13 tenant-admin work will generate a UI from that dictionary.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** Batched because it is one piece of work with one runnable gate in four arms - make the configuration surface tell the truth - and because a reviewer reading any one of them alone would ask about the other three. Split it back by arm if the documentation half lands separately from the plumbing half. BF-46 is deliberately not batched here; see that item.

### `BFQ-52` &mdash; BF-52 - an age reminder whose 20-minute window passed without a check was never sent

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `bf3/age-push-once` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/work/crm-bf3-agepush` |
| semver | `patch` |
| review | maintainer, who should confirm the behaviour choices named in the evidence - all three levels rather than urgent only; the record lives in memory, so a restart re-sends one reminder for an item already overdue; the first check after upgrading sends one reminder per overdue item; a catch-up request can be swallowed by an active silence (not measured). |
| ships to operators today | **yes** |
| register | `BF-52` |
| blocks on | `BFQ-92` |

**Blast radius.** One commit, 896629f8, 8 files, +338/-66. lib/plugins/agenotify.js (new, shared), lib/plugins/{cannulaage,sensorage,insulinage,batteryage}.js, tests/age-notify-once.test.js (new, 24 tests), tests/sensorage.test.js (one expectation changed: it asserted the defect), README.md (the *_ENABLE_ALERTS entries and IAGE_URGENT).

**What an operator sees.** Not released. Nightscout can remind you when a cannula (infusion site), sensor, insulin reservoir or pump battery is getting old. The coloured indicator on screen already stays red for as long as the item is overdue, and that does not change. The optional push reminder (a notification sent to your phone or other device, which is off unless you switched it on with a setting such as SAGE_ENABLE_ALERTS) could only be sent during the first 20 minutes of the hour when the item reached its reminder time. If Nightscout was restarting, asleep or otherwise not checking during those 20 minutes, the reminder was never sent. With this change, a reminder that was missed that way is sent once, the next time Nightscout checks, and it is not repeated after that. Two things you may notice - after Nightscout restarts, an item that is already overdue may send its reminder one more time, and right after upgrading you may get one reminder for each item that is already overdue. This is not medical advice; talk to your care team about how you manage site, sensor, reservoir and battery changes.

**Why `patch`.** A bug fix to an opt-in notification, matching the maintainer's 2026-09-23 decision. Nothing that fires today stops firing; a missed request is made once. No setting, API or on-screen level changes.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf3/age-push-once >/dev/null`
  - Merges into origin/dev with no conflict.
- `[unit]` `cd externals/work/crm-bf3-agepush && n exec 20.20.0 npx mocha --timeout 10000 --exit tests/age-notify-once.test.js tests/sensorage.test.js`
  - The sequence tests (24, each plugin driven the way bootevent.js does, missed windows included) and the changed sensorage test, no database; 32 passing. Control, run 2026-09-23 with tools/queue/gates/ablate.sh (the four plugins put back to origin/dev, agenotify.js removed) - the new test file exits 16, the missed-window tests failing with the original symptom. The evidence's full-tree break-it gives 17 red.
- **NO GATE** &mdash; The full suite (2410/0/3 on Node 20.20.0 and 22.23.2, against 2386/0/3 on dev, +24 exactly by title) needs MongoDB and is recorded in the evidence, not gated here. Delivery after requestNotify (pushnotify, Pushover, the alarm socket) and a real restart were not measured.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf52-age-push-once-2026-09-23.md`

**Notes.** PREPARED 2026-09-23 - bf3/age-push-once 896629f8, one commit on 74fc6619, not pushed. Reproduced red on dev and on 15.0.8 first. The window is minutes 0-20 of the threshold hour, not a single evaluation, and the shape is the same at all three levels in all four plugins. DEFERRED 2026-09-23 (maintainer) - not in 15.0.9. It ships in a later release, paired with BFQ-92, and delivery after requestNotify through pushnotify and Pushover is measured first. The branch stays prepared at 896629f8. DECIDED 2026-09-23 (maintainer) - send once, even if the exact check is missed: fire the push the first time the age is at or past the threshold and remember that it was sent, so a restart or a data gap cannot swallow it and it does not repeat every check. That makes today's exact-match behaviour a defect; the fix is on bf3/age-push-once (above). BF-28 masked this on insulinage for years - the level line was broken, so nobody reached the notification line. The three sibling plugins have shipped with the same shape unmasked. Any release note for BF-28 (merged to dev via #8739, arriving in 15.0.9) must get two things right - the push alarm is opt-in and off by default, and what does reach everyone is the on-screen pill, because the level is assigned outside the alerts guard.

### `BFQ-90` &mdash; BF-90 - an alarm at a page with no reading throws in the client

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf3/alarm-no-reading` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/work/crm-bf3-alarmnoread` |
| semver | `patch` |
| review | maintainer. Decide whether the log text "no reading loaded" is acceptable. The alarm decision itself is deliberately not changed here - that is BFQ-92, a clinical-behaviour decision that should not ride along on a crash fix. |
| ships to operators today | **yes** |
| register | `BF-90` |

**Blast radius.** One commit, 92544d8f, 2 files, +165/-4. lib/client/index.js - two helpers, latestMgdlForLog() for the two log lines and updateChartAfterAlarm() for the two chart.update calls, so two guards per handler; the alarm decision (isAlarmForHigh, isAlarmForLow, enabled) is unchanged. tests/client.alarm-no- reading.test.js (new, 4 tests). Client-side, so it needs a rebundle, not a restart.

**What an operator sees.** Not released. If a Nightscout page that has no glucose reading to show (the big number reads ---) receives an alarm - for example an optional pump, loop or site-change alert that the site owner has switched on - the page hits an internal error while handling it. You would not see the error; it appears only in the browser's developer console. This fix removes the error. It does not change when alarms sound. The error costs no alarm only because a page with no reading already shows and sounds no server alarm at all, including device alarms (see BFQ-92). That silence is the part that matters for safety, and this fix does not change it. If you rely on a Nightscout page for device alarms such as pump, loop or site-change alerts, do not assume a page showing --- will alert you; keep the alarms on the devices themselves switched on. This is not medical advice; talk to your care team about how you get alerted.

**Why `patch`.** a client-side bug fix; what is shown and sounded is unchanged with or without data

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf3/alarm-no-reading >/dev/null`
  - Merges into origin/dev with no conflict.
- **NO GATE** &mdash; The branch's own test, tests/client.alarm-no-reading.test.js (4 passing), runs against the PRODUCTION BUNDLE in node_modules/.cache, not against lib/client/index.js. Measured 2026-09-23 - tools/queue/gates/ablate.sh with the fix reverted stays green (exit 0), because the ablated worktree borrows the donor's already-built bundle. So as a queue gate it would be vacuous. A gate needs the bundle rebuilt inside the ablated tree (npm run bundle). The evidence records the break-its run by hand with the bundle rebuilt - A (log lines back) 2 of 4 red, B (chart guard back) 2 of 4 red, C and D showing the invariants can fail - and a browser run on 15.0.8, dev and the branch.
- **NO GATE** &mdash; The full suite (2390/0/3 on Node 20.20.0 and 22.23.2, +4 exactly) needs MongoDB and a rebuilt bundle, and is recorded in the evidence.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf90-alarm-no-reading-2026-09-23.md`
- `docs/60-research/modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md`
- `docs/30-design/remedial/rc-15.0.9-additions-d-2026-09-23.md`
- `docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md`

**Notes.** MERGED 2026-09-23 into dev (now 4011193e); NOT RELEASED. #8755 as 728351e3. CI and CodeQL green. BF-92 (a page with no reading presents no server alarm) is unchanged by it, as intended. PREPARED 2026-09-23 - bf3/alarm-no-reading 92544d8f, one commit on 74fc6619, not pushed. Reachability corrected: it is reached with no forcing, on 15.0.8 and dev, by any opt-in device alert at a site with no stored CGM reading (and on 15.0.8 also by a page that may not read data, BF-75). It was first seen with the /alarm gate forced open. Register grade re-stated 2026-09-23 as low - reachable, not latent - because the throw's own cost is a skipped chart redraw; "no alarm is lost" holds only because the page drops every server alarm when it has no reading (BF-92, BFQ-92). A second throw behind the first (no chart on a page that never received data) is why each handler needs two guards. SHIPS IN 15.0.9 (maintainer, 2026-09-23). Integrated on rc/15.0.9-additions-d 5764156e, 2520/0/3 on every Node and MongoDB pair (docs/30-design/remedial/rc-15.0.9-additions-d-2026-09-23.md); PR body drafted in reports/phase0-pr-bodies/bf3-alarm-no-reading.md.

### `BFQ-92` &mdash; BF-92 - a page with no glucose reading never presents a server alarm, including device alarms

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer. Position taken 2026-09-23 - non-glucose alarms (pump, loop, age) should present on a page with no reading. It should not ride along on BFQ-90's crash fix. |
| ships to operators today | **yes** |
| register | `BF-92` |

**Blast radius.** lib/client/index.js:1196-1204 (isAlarmForHigh, isAlarmForLow, both beginning with client.latestSGV &&) and the enabled expressions at :1225 and :1237 in the alarm and urgent_alarm handlers. The same code on 15.0.8.

**What an operator sees.** Nightscout can raise alarms for things other than glucose if the site owner has switched them on - for example a pump reservoir running low, a loop that has stopped, or a cannula or sensor that is overdue for a change. A Nightscout page decides whether to sound a server alarm by looking at the latest glucose reading. When the page has no reading to show (the big number reads ---), it treats every alarm as "not for me", including a pump or loop alarm that has nothing to do with glucose. In our test the same "URGENT: Pump Reservoir Low" alarm filled the page's title bar in red and played the alarm sound when readings were on screen, and the page showed nothing at all when there were none. This is how today's release (15.0.8) and the development version behave. If you rely on a Nightscout page for device alarms, do not assume a page showing --- will alert you; keep the alarms on the devices themselves (pump, phone app, CGM receiver) switched on. This is not medical advice; talk to your care team about how you get alerted.

**Why `minor`.** Changes which alarms a page presents; safety-adjacent, so not a silent patch.

**Gates.**

- **NO GATE** &mdash; Measured in a real browser, not by a queue gate: tools/review/probes/alarm-no-reading-browser.js with --reading none and --reading present, on 15.0.8, dev and bf3/alarm-no-reading (evidence section 4). It needs two booted instances and MongoDB. A unit gate would be the headless test's "still does not sound with no reading" invariant inverted for non-glucose alarms, per the maintainer's 2026-09-23 position; it does not exist yet.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf90-alarm-no-reading-2026-09-23.md`

**Notes.** Filed 2026-09-23 from the BF-90 work. Safety-relevant - graded high in the register if unintended. Reproduced with ordinary pump-status uploads and PUMP_ENABLE_ALERTS=true; no server decision was forced. MAINTAINER POSITION 2026-09-23 - non-glucose alarms should present on a page with no reading. A later release, not 15.0.9, paired with BFQ-52. 15.0.9 carries it as a known issue.

### `BFQ-93` &mdash; BF-93 - food changes never reach an open page

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-93` |

**Blast radius.** lib/data/calcdelta.js - compressArrays covers sgvs, treatments, mbgs, cals and devicestatus, deleteSkippables covers profiles, and food is in neither. The same on 15.0.8.

**What an operator sees.** When a food or a saved quick pick is added or changed - through the food editor in another tab, or by an app that writes to Nightscout - a Nightscout page that is already open does not receive the change. It appears only after that page reloads or reconnects. Until then the page keeps the old food list, and the Bolus Wizard (Nightscout's built-in bolus calculator) can offer a quick pick with an old carb total. This is how today's release (15.0.8) behaves. Whatever the calculator shows, check the carbs against the meal you are actually eating before you rely on them; this software does not decide a dose. This is not medical advice; if you use quick picks for meal dosing, go over how you use them with your care team.

**Why `patch`.** If fixed by adding food to the broadcast delta, it is a bug fix; no API or setting moves.

**Gates.**

- **NO GATE** &mdash; Measured in a real browser, not by a queue gate: tools/review/probes/quickpick-rebuild-browser.js, the arm "a pick added while the page is open reaches the page by broadcast", on 15.0.8, dev and bf3/quickpick-rebuild (evidence section 4). A unit gate would call calcdelta with a changed food array and assert the delta carries it; it does not exist yet.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf69-quickpick-rebuild-2026-09-23.md`

**Notes.** Filed 2026-09-23 from the BF-69 work (evidence section 8.1). An edited carb total on an existing quick pick takes the same path and was not run separately.

### `BFQ-94` &mdash; BF-94 - a kept profile instance can return a temp basal that has been replaced

| | |
|---|---|
| state (claimed) | `unsettled` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-94` |

**Blast radius.** lib/profilefunctions.js:19 (module-scope prevBasalTreatment), :455-456 (the early return in tempBasalTreatment), updateTreatments at :292-311 (clears the cache, not prevBasalTreatment). The same on 15.0.8.

**What an operator sees.** Nightscout keeps a remembered copy of the most recent temporary basal rate it looked up. When new treatment data arrives, that copy is not always refreshed, so a page that stays open might show a temporary basal rate that has since been changed or cancelled. This was shown inside Nightscout's code but has not been checked on a real page, so it is not yet known whether you would ever see it. The server's own checks are not affected. This is not medical advice; your pump or AID app is the record of what was delivered.

**Why `patch`.** if it is a defect at all, the fix is a bug fix

**Gates.**

- **NO GATE** &mdash; Reproduced at module level while building tools/remedial/bf3/bf09-dedup-zero.js (evidence section 3.2); no standalone instrument exists. A unit gate would create one profilefunctions instance, load a temp, replace it through updateTreatments and assert the lookup returns the new value. The browser, where the instance is kept, was not measured.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md`

**Notes.** Filed 2026-09-23, a side finding of the BF-09 measurement. Not BF-09.

### `BFQ-95` &mdash; BF-95 - an uploader clock running ahead delays the stale-data alarm

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer - a design decision before code |
| ships to operators today | **yes** |
| register | `BF-95` |

**Blast radius.** lib/sandbox.js lastEntry, lib/plugins/timeago.js checkStatus. v1 entries store no server-receipt time (lib/server/entries.js:118-126), so an arrival-based check needs new data.

**What an operator sees.** If the phone or device uploading your readings has its clock set ahead of the real time, Nightscout treats each reading as newer than it is. If your readings then stop, the stale-data warning comes late, by roughly how far ahead that clock is: an hour fast means the 15-minute warning comes after about an hour and a quarter. Check the date, time and time zone on the uploading device, and have another way to notice that readings have stopped. This is not medical advice; talk to your care team about what you rely on Nightscout for.

**Why `minor`.** any fix changes when an alarm that is on by default fires

**Gates.**

- **NO GATE** &mdash; Characterised by tools/remedial/bf3/bf41-real-sandbox.js cases F7 and F8 (it always exits 0 - a characterisation, not a gate). A gate needs the decided product first, because which way it should go red depends on it.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf41-future-reading-2026-09-23.md`

**Notes.** Filed 2026-09-23 from the BF-41 measurement (F7/F8) when BF-41 was closed. Open, needs a design decision; one option is a notice for readings that arrive already ahead of the clock (evidence section 5, option 3). 15.0.9 carries it as a known issue. BF-44 (BFQ-MINIMED) is a shipping source of forward skew.

### `BFQ-96` &mdash; BF-96 - the headless test fixture's bundle cache key is an un-normalised path

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-96` |

**Blast radius.** tests/fixtures/headless.js and tests/fixtures/benv-shim.js only; test harness, nothing an operator runs.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** test harness only

**Gates.**

- **NO GATE** &mdash; Seen while writing BF-90's tests/client.alarm-no-reading.test.js, which clears the resolved key itself. A gate would load two headless suites in one mocha process and assert the second gets a fresh bundle; it does not exist yet.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf90-alarm-no-reading-2026-09-23.md`

**Notes.** Filed 2026-09-23 from the BF-90 work; found, not fixed. The candidate fix (path.resolve in the shim) is unverified.

### `BFQ-67` &mdash; BF-67, BF-86 - alarm thresholds quietly changed, or quietly kept when they cannot work

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer, and it is a decision with a safety dimension before it is code. Refusing a contradictory threshold set, correcting it and announcing it, and unit-checking the input are three different products. |
| ships to operators today | **yes** |
| register | `BF-67`, `BF-86` |

**Blast radius.** lib/settings.js verifyThresholds(), four branches. Unconditional at settings load on every deployment.

**What an operator sees.** Nightscout checks that your four glucose alarm thresholds are in a sensible order. If they are not, it does not tell you and ask - it changes one of them by one unit and carries on, and the only record is a line in the server log, which on many hosting setups you will never see. The case this actually reaches is a units mix-up. If you think in mmol/L and set your high alarm to 14, Nightscout is reading mg/dL unless you have told it otherwise, 14 is below the target range, and it is stored as 181 mg/dL. You believe you have set a high alarm and you have set a different one. The same happens if you ask for a low alarm at 90 while the target range still starts at 80 - it is stored as 79. A low alarm entered as 3.9 (meaning mmol/L) is stored as 3.9 mg/dL with no warning at all, and can never fire. If you have set thresholds and the alarms do not behave as you expect, check what Nightscout actually stored, and please discuss your alarm settings with your care team. This is not medical advice.

**Why `minor`.** Every option changes what a deployment with contradictory thresholds does at boot - refuse, announce, or convert. Alarm thresholds are what alarms fire on, so this cannot arrive as a silent patch under any of the three.

**Gates.**

- `[static]` `node tools/queue/gates/threshold-silent-rewrite.js`
  - Executes the shipping settings layer. FAILS today on both arms - BG_HIGH=14 with UNITS at the mg/dL default is stored as 181, and BG_LOW=90 against the shipped bgTargetBottom of 80 is stored as 79, each with two console.warn lines and no other surface. Four controls come out the other way through the same harness, and the gate was proven to go green against an isolated copy with the two rewrite sites removed. This gate is BF-67's reproduction (provenance: reproduced).
- **NO GATE** &mdash; Nothing checks that a corrected setting is surfaced. The gate proves the value changes; the defect is that the only evidence is stdout. Grep over lib/client/ and views/ finds no surface that reports the rewrite, and building one is the fix, not the measurement.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/e4-queue-register-reconciliation-2026-09-15.md`

**Notes.** Correction to BF-67's text, measured while building the gate: a BG_LOW of 3.9 does not become bgTargetBottom - 1 = 79. The low check is `bgLow >= bgTargetBottom`, so a value far below the band passes through untouched and BG_LOW=3.9 is stored as 3.9. The low-side rewrite is real from the other direction (BG_LOW=90 -> 79). The residue no entry owns: a low alarm set to 3.9 mg/dL can never fire, and is stored with no warning of any kind. Also relevant to T3.0: the per-tenant configuration spec proposes a CHECK constraint as a backstop for this, and it is not one - a partial override leaves absent paths SQL NULL, the AND chain evaluates to NULL rather than FALSE, and PostgreSQL accepts the row.

### `ADV-RETRO` &mdash; GHSA-gjhc - loadRetro serves devicestatus to any socket (BF-79)

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/ws-loadretro-auth` |
| base | `origin/dev@59430336` |
| worktree | `externals/work/crm-adv-retro` |
| semver | `patch` |
| review | SECURITY. The advisory is a GitHub draft with no CVSS vector and a bare `high`, and three of its statements need correcting before publication. (1) Affected range. It says >0.8.1; loadRetro is absent from tags 0.8.1 through 0.8.4 and first appears in 0.9.0 - which is also the first tag carrying DataReceivers and authDefaultRoles, so the handler and the authorization it skips shipped together. Should be >=0.9.0. (2) "This does not require any specific configuration on the system" is true of reachability and false as an impact claim. On the shipped readable default the payload is a STRICT SUBSET of what GET /api/v1/devicestatus.json already serves anonymously - measured field by field: 0 socket record _ids absent from the REST answer, 0 JSON field paths present only on the socket, and REST returned 1730 records to the socket's 574. Marginal disclosure on a default install is zero. (3) It understates the hardened case. Under AUTH_DEFAULT_ROLES=denied, with every REST read answering 401 in the same run, the handler returns 576 records - 28.8x more than an authorized reader gets on connect, because authorize() trims to 10 per device-and-type. No setting stops it: denied, status-only, AUTHENTICATION_PROMPT_ON_LOAD and TREATMENTS_AUTH=off were each measured. DEVICESTATUS_DAYS=2, the only knob touching the path, doubles it to 1150. Recommended: score CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N = 7.5 and say it scores the hardened configuration; the default arm is 0.0 and publishing a high score against it would alarm the majority of self-hosters about their own public output. PATCHED-VERSION FIELD: leave empty until a tagged release carries this. The fix is merged to dev (PR #8744) and not released: origin/master is 308 commits behind dev at 92d08342, the shipping tag is 15.0.8, and no operator is carrying it. |
| ships to operators today | **yes** |
| register | `BF-79` |

**Blast radius.** 1 commit at 9765e8cd. lib/server/websocket.js (+36/-4) and one new test file, tests/websocket.loadretro-authorization.test.js (210 lines, 4 cases). No other file. The change adds resolveReadAccess(), which calls the verifyAuthorization() already in that file with an empty message, so an anonymous socket resolves through the same AUTH_DEFAULT_ROLES shiros the REST surface uses. Verified NOT to interact with the failed-login throttle - an empty auth message takes authorization.resolve()'s !authAttempted branch and never records a failure.

**What an operator sees.** Nightscout's live-update connection (the channel your browser or app keeps open to receive new readings) had one message that answered anybody. If you run the default setup, where your site is already readable by anyone with the address, this exposed nothing you were not already publishing. If you followed the documentation and turned off unauthorised access, it did matter: about a day of pump and loop information - insulin on board, reservoir and battery levels, whether the pump was delivering or stopped, your pump's serial number and your phone's name - could still be read by anyone who knew your address, even though every other way in was refused. The fix makes that message follow the same rule as everything else. It is in the development branch and arrives with the next release (15.0.9); sites running 15.0.8 or earlier are still affected. Nightscout is not a medical device and this is not medical advice.

**Why `patch`.** No route removed, no input added, no documented contract changed. The only behaviour that disappears is behaviour nobody was entitled to: on a `readable` instance an anonymous client still receives retroUpdate, which was confirmed as a live positive control on the fixed build.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/ws-loadretro-auth origin/dev`
  - Containment: this tip is an ancestor of origin/dev, so the fix is in dev; an upstream revert or force-push turns it red.
- `[static]` `test -f externals/work/crm-adv-retro/tests/websocket.loadretro-authorization.test.js`
  - The regression test exists in the worktree. Deliberately a file- existence check rather than a suite run - see the no-gate below.
- **NO GATE** &mdash; No gate runs the suite here. `npm test` on this tree needs a my.test.env and a mongod of its own, with the container's nofile limit raised first (the default 1024 exhausts mongod's descriptors part-way through - BF-10's failure mode). Measured by hand on 2026-09-21 on mongod 7.0.43: 2311 passing / 3 pending / 0 failing before, 2315 / 3 / 0 after, delta exactly the four new cases. Ablation - revert lib/server/websocket.js to origin/dev, keep the test - turns the two negative cases red, showing canaried devicestatus arriving at a socket the server had already resolved as unable to read, while the two positive cases stay green. Automating this needs a fixture that owns its own mongod.

**Evidence.**

- `docs/60-research/remedial/ghsa-gjhc-loadretro-2026-09-21.md`
- `docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md`
- `docs/30-design/remedial/security-advisory-disposition-2026-09-21.md`
- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** REPRODUCED on v15.0.7, v15.0.8 and dev 59430336, both arms, mongod 7.0.43, with the isolating control in every run: the same unauthenticated socket without the loadRetro message sees only the `clients` event. Six of the seven handlers on that namespace check authorization - dbAdd, dbUpdate, dbUpdateUnset and dbRemove all answer "Not authorized" and write nothing, confirmed against the collection rather than the reply string. loadRetro is the single unguarded one, and it does not depend on the socket having authorized first. Merged 2026-09-21 as PR #8744 into dev, merge commit a9acd313, from bf/ws-loadretro-auth at 9765e8cd - the exact tip this item was measured against. dev moved 59430336 -> 74fc6619 carrying this and the two advisory PRs after it. Still live on 15.0.8. The reply to the reporter, including the two corrections to the advisory, is drafted at docs/30-design/remedial/advisory-response-2026-09/advisories/ghsa-gjhc- comment.md and NOT yet posted.

### `ADV-ALARM` &mdash; GHSA-8849 - /alarm broadcasts to the whole namespace (BF-75, BF-76)

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/alarm-socket-scope` |
| base | `origin/dev@59430336` |
| worktree | `externals/work/crm-adv-alarm` |
| semver | `minor` |
| review | SECURITY. Fix shape: MAINTAINER DECISION 2026-09-21, SHAPE B - admit at connection time when the deployment's anonymous default role already permits reading, re-evaluate on subscribe, and gate delivery on api:*:read. The maintainer separately judged the shipped web client to be the only consumer of /alarm - the fact that would have argued for the strict shape - and chose B anyway, as insurance against that judgement being wrong. What was weighed: shape A required subscribed AND authorized. On the shipped `readable` default, receiving without subscribing is behaviour third-party clients have observed for five releases: the /alarm protocol is in no swagger file and nothing under docs/, so implementers had only the observed behaviour to go on. Measured, the marginal CONTENT disclosure on that default is zero - every field in all five payloads is already in treatments.json, entries.json or status.json, and notifyhash/key are sha1 over already-readable fields. So the strict version breaks non-subscribing clients for no confidentiality gain on the majority configuration, while B closes the `denied` bypass identically. Too tight and a follower app silently stops delivering hypo alarms; too loose and the bypass stays open. A second PR exists: the advisory's reporter opened one in GitHub's private advisory fork (nightscout/cgm-remote-monitor-ghsa-8849-qjp5-vrrj PR #1, based on v15.0.8) on 2026-09-18. Measured, it does NOT close the bypass: it gates on AUTHENTICATION_PROMPT_ON_LOAD rather than AUTH_DEFAULT_ROLES, so on a hardened instance with the prompt flag at its default a socket that never subscribes still receives everything; and even where it engages it never consults api:*:read, so a token granting only api:treatments:create hears every alarm while getting 401 on every REST read in the same run. A reviewer should read ghsa-8849-reporter-pr-evaluation-2026-09-21.md and decide how the two PRs are reconciled and how the reporter is credited. BF-76 is NOT part of the advisory. It was found while fixing BF-75 - the access-token branch of subscribe registered the ack handler with no permission check, so a valid token of any role could silence alarms on the instance, for a caller-chosen duration with no upper bound. Authorization is fixed; the unbounded silence duration is left open on purpose, because what a legitimately authorized client may ask for is a product decision. No automated test drives hashauth against a live socket. A human must load a `denied` instance, authenticate at the prompt, force an alarm and confirm it arrives. That is the one path the new cases do not cover. DONE 2026-09-23 by hand (the maintainer, manual lab on the combined rc ec70aab0; each page in its own browser profile). On AUTH_DEFAULT_ROLES=denied, pages that logged in at the prompt with the API secret or a readable token, or opened with ?token=, received the warning and urgent alarms; a status-only page did not. The same held with AUTHENTICATION_PROMPT_ON_LOAD=true. A readable token's silence stayed on its own page (no notifications:*:ack); the API secret's silence reached every page (server logged ack received). A remembered secret survived a reload. The automated probe (alarm-denied-browser.js) re-run on the same tree gave 10 checked, 0 failing. Caveat: ec70aab0 also carries #8754, which touches lib/api3/alarmSocket.js and is not on dev 4011193e. |
| ships to operators today | **yes** |
| register | `BF-75`, `BF-76`, `BF-80` |

**Blast radius.** 2 commits at 012f1623, built on fix shape B (see review). fd80e6a2 is the broadcast fix plus a 49-case regression test; 012f1623 is the ack- authorization fix plus 2 cases. A superseded shape-A tip is kept at refs/backup/alarm-shapeA = 842d81fb in that worktree and can be deleted. lib/api3/alarmSocket.js (+74/-19), lib/client/hashauth.js (+8), two new test files. The client change is the part to look at hardest: it re-runs subscribeForAlarms from hashauth.updateSocketAuth, because client.subscribeForAlarms had exactly ONE call site - the socket's connect handler - and nothing re-subscribed when a viewer authenticated in the page. Without it, load -> refused -> prompt -> enter secret would leave that socket in no room, silently receiving no alarms, for the one user who had just proved entitlement. The source already asked this at alarmSocket.js:150: "TODO: how will perms get updated after authorizing?".

**What an operator sees.** Nightscout sends alarms and treatment notifications over its live-update connection (the channel your browser or app keeps open). That connection was sending them to everyone attached to it, whether or not they had signed in. If you run the default setup your site already publishes this information to anyone with the address, so nothing new was exposed - what it added was that someone could watch it arrive in real time without ever making a request your logs would record. If you had turned off unauthorised access, it did matter: carb entries, insulin doses, loop activity, and your high and low alarms were still going out to anyone who connected. The fix sends them only to viewers your site has authorised. It is in the development branch and arrives with the next release (15.0.9); sites running 15.0.8 or earlier are still affected. If you use a third-party follower app that shows Nightscout alarms and it stops showing them after you update, that is this change - please report it, because the connection it uses has never been documented. Nightscout is not a medical device and this is not medical advice; if you rely on these alarms, keep a second way of being alerted until you have confirmed yours still works, and talk to your care team if you are unsure.

**Why `minor`.** It removes reachable behaviour that undocumented third-party clients may depend on - receiving alarms without subscribing - so it is not a patch by the project's own reading, whichever variant of the fix is chosen. Not major: no route removed, no required input added, and the shipped web client is unaffected because it subscribes.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/alarm-socket-scope origin/dev`
  - Containment: this tip is an ancestor of origin/dev, so the fix is in dev; an upstream revert or force-push turns it red.
- `[static]` `test -f externals/work/crm-adv-alarm/tests/api3.alarm-socket.security.test.js -a -f externals/work/crm-adv-alarm/tests/api3.alarm-socket.ack.test.js`
  - Both regression test files exist in the worktree.
- **NO GATE** &mdash; No gate runs the suite, for the same reason as ADV-RETRO: it needs a my.test.env and a dedicated mongod whose nofile limit has been raised. Measured by hand on mongod 7.0.43, shape B: 2311 passing / 3 pending / 0 failing before, 2362 / 3 / 0 after, delta exactly the 51 alarm cases. Run against UNFIXED dev code the new tests go 29 passing / 22 failing, and the 29 that pass are the positive-delivery and REST-control assertions - which is what makes the 22 attributable to the defect rather than to the harness. Five ablations, each breaking one thing, each red for its own reason: A1 reverts the five to(ROOM) emits -> 20 fail, symptom named on the never-subscribed socket, all 25 delivery assertions green; A2 forces the read check true -> 21; A3 forces entitlement true ONLY on the subscribe path -> exactly the 15 unauthorized-subscriber cases plus the ack report, never-subscribed rows green; A4 removes the connect-time admission, i.e. reverts to shape A -> exactly the five [SHAPE B] cases, which is the regression guard for the maintainer's decision; A5 removes the ack guard -> 2. A1 and A3 are the two independently load-bearing halves. A suite asserting only non-delivery would pass a too-tight room, so the value is in the delivery rows. Five cases assert shape-B behaviour specifically - a never-subscribed socket on a readable instance must RECEIVE - and are tagged [SHAPE B] in their names so a reviewer sees them in the runner output; A4 proves they are the ones that go red if anyone re-tightens the room. There are no anonymous REST controls against /api/v3/entries: v3 demands a bearer token on every value of AUTH_DEFAULT_ROLES, so such controls measure nothing.
- **NO GATE** &mdash; No gate covers the client half. Nothing drives lib/client/hashauth.js against a live socket, and the client change is the part that could silently drop a real hypo alarm. Human verification required - see the review field.

**Evidence.**

- `docs/60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md`
- `docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md`
- `docs/30-design/remedial/security-advisory-disposition-2026-09-21.md`
- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md`

**Notes.** REPRODUCED on v15.0.8 and dev 59430336, both arms, all five event classes (notification, announcement, alarm, urgent_alarm, clear_alarm), each caused through the real server path - threshold crossings into simplealarms, treatment writes into treatmentnotify - with no synthetic bus events. In every `denied` row the four v1 REST routes answered 401 in the same process at the same moment; that is the control that makes it a bypass rather than the documented default. Sharpest datum: under `denied` the server tells a subscribing anonymous socket that it has neither read nor ack rights - it computes the correct authorization decision, sends it to the client, and delivers everything anyway. subscribe gated acknowledgement rights and nothing on the receive side. The advisory's authenticationPromptOnLoad claim is confirmed exactly: the subscribe is refused, the socket is not disconnected, and it still receives all five. Range >=15.0.0 is correct; 89d7eb679 is first contained in tag 15.0.0. Turning careportal off via ENABLE= removes notification and announcement by removing the feature, and alarm/urgent_alarm/clear_alarm still arrive - so that is not a mitigation either. BF-80 is the cost of this fix and is filed against it deliberately. Once delivery depends on a resolved entitlement it inherits the failed-login delay list: a socket from an address that recently failed an authentication sits outside the delivery room for the accumulated penalty, 5 s per failure, and the list is keyed on the remote address so a household behind one NAT address is one key. Measured on the fixed build with the alarm fired 2 s after connect: 0 failures -> received at 2.0 s (clean control), 1 -> 4.9 s, 3 -> 10.0 s, 6 -> 15.0 s. A shape assertion, not a threshold. No shape of this fix avoids it - the pre-fix code avoided it only by checking nothing. Deliberately not fixed here: narrowing a brute-force control needs its own change and its own review. Merged 2026-09-21 as PR #8745 into dev, merge commit 2b22c0ce. origin's bf/alarm-socket-scope is at a198e308, not this item's measured tip 012f1623, because an integration merge of dev was added to the branch before it went in; nothing was re-measured on a198e308. The ancestry gate therefore tests containment in dev rather than tip equality. Not released: dev is 308 ahead of master and operators run 15.0.8, so BF-75 and BF-76 remain live on every deployed instance, and BF-80 is not yet a cost anyone is paying. The reply to the GHSA-8849 reporter at docs/30-design/remedial/advisory- response-2026-09/pull-requests/reply-to-reporter-ghsa-8849.md is drafted and NOT sent.

### `ADV-XSS-META` &mdash; GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74)

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/master@92d08342` |
| worktree | `externals/work/crm-adv-xss` |
| semver | `n/a` |
| review | MAINTAINER, plus whoever owns the GitHub advisory drafts. Four metadata corrections, all derived rather than estimated: GHSA-mjp4-84fw-gj4v - affected <= 15.0.7 confirmed; set patched_versions to 15.0.8, which currently sits BLANK against a closed vulnerable range, saying "fixed in something" and "fixed in nothing" at once. Severity high unchanged. Add CVSS 4.0 AV:N/AC:L/AT:N/PR:L/UI:A/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N = 8.4 (its own proposed vector with UI:P corrected to UI:A) and CVSS 3.1 AV:N/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:N = 8.7. GHSA-5mrq-gpqw-q5v5 - `critical` overstates it; recommend `high` at the same 8.4. Correcting UI:P to UI:A moves 9.3 to 9.2, still Critical; what produces Critical is SC:H/SI:H, and that is a double count - the stolen API secret's entire blast radius IS the Nightscout instance, which is the vulnerable system and is already counted by VC:H/VI:H. There is no subsequent system. The escalation itself must NOT be softened: lib/client/hashauth.js stores sha1(API_SECRET) in localStorage and that hash IS the value the api-secret header accepts, so same-origin script gets admin. That belongs in VC:H/VI:H. BOTH should state that no stored-data remediation is needed after upgrading from 15.0.7 - see notes. The current state, one `critical` with SC:H/SI:H and one `high` with SC:N/SI:N for the identical credential theft, is the thing most needing correction. Then two decisions that are contract questions, not bugs. BF-73: express's errorhandler is mounted with its NODE_ENV === 'development' guard COMMENTED OUT, identically at v15.0.7, v15.0.8 and dev, and git log -L carries those four lines back to 7947e300 in 2019 - so it was deliberate, and restoring the guard is a decision about what a production error page owes an operator debugging their own site. BF-74: API v3 `settings` writes skip the purifier every other v3 collection gets; purifying UI-configuration values could corrupt them, and no first-party sink consumes the field, so the right answer may be a comment rather than a fix. |
| ships to operators today | **yes** |
| register | `BF-73`, `BF-74` |

**Blast radius.** No code change proposed for the two advisories - the fixes shipped in 15.0.8 (72a2257e, a6835ca3, da548d2a, all contained in tag v15.0.8). What is outstanding is advisory metadata plus two decisions, BF-73 and BF-74, that were found beside them and that neither advisory covers.

**What an operator sees.** Two reported ways of storing malicious content in your Nightscout were fixed in release 15.0.8. If you are on 15.0.8 or later you need do nothing, including nothing about entries that were already saved: content of this kind stored by an older version does not run on a patched server. This was checked by putting an example straight into the database and then opening the pages that display it. If you are still on 15.0.7 or earlier, upgrading is the fix. Nightscout is not a medical device and this is not medical advice.

**Why `n/a`.** No code change is proposed by this item; the fixes already shipped.

**Gates.**

- `[static]` `git -C externals/work/crm-adv-shipping tag --contains a6835ca3 | grep -qx v15.0.8`
  - The purification commit is in the 15.0.8 tag. This is the claim the whole item rests on - that operators on the shipping release are already fixed - so it is gated rather than asserted.
- `[static]` `git -C externals/work/crm-adv-shipping grep -q "purifyObject" v15.0.8 -- lib/server/websocket.js`
  - The socket write path calls the purifier at v15.0.8; it does not at v15.0.7.
- **NO GATE** &mdash; The render-side and stored-payload results are not gated and cannot cheaply be. They needed a real headless Chromium against /report and a jsdom+d3 harness loading each ref's own renderer.js, with the payload inserted straight into mongo to bypass every write path. Recorded in the evidence document with their v15.0.7 positive controls; re-running them is a half-day, not a gate.

**Evidence.**

- `docs/60-research/remedial/ghsa-xss-pair-verification-2026-09-21.md`
- `docs/reports/security-hotfix-eval-2026/report-01-stored-xss.md`
- `docs/30-design/remedial/security-advisory-disposition-2026-09-21.md`
- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** DECIDED 2026-09-23 (maintainer) - apply all four metadata corrections to the draft advisories. The advisories stay drafts; applying is a human step (advisories/apply-metadata.sh --apply). REPRODUCED, and every "fixed" cell is paired with a positive v15.0.7 control from the same run - four write paths across three refs, end-to-end over real HTTP and socket, with the document read back out of mongo, and v3 driven with a real JWT on all three refs. The fix is broader than either advisory claims: PUT /api/v1/treatments/, POST /api/v1/food and POST /api/v1/activity also had no purification at 15.0.7 and now do. The headline, which source-reading could not have answered: a payload a 15.0.7 server had ALREADY STORED does not fire on a patched server. At 15.0.7 the day-to-day report executed it in a real browser; at 15.0.8 and dev it renders as visible text. That is true only because the output-escaping half of the fix (da548d2a) landed alongside the purification half - had only the purifier shipped, the answer would be the opposite. Both advisories should say so. Residual sinks: none. 32 `.html(` sites on dev classified; a mechanical scan for unescaped free-text interpolation found 25 hits across 10 files at v15.0.7 and zero at v15.0.8 and dev. The internal report's sweep claim names 4 files; the shipped sweep covers 10. Sanitizer bounds: a string over the size budget is NOT passed through unsanitized - it throws RangeError and the write is REFUSED on all four paths, fail-closed. The POSSIBLE_HTML_MARKUP pre-filter is evadable, but none of the three evading forms executes at any sink on any ref, including v15.0.7 - the defence-in-depth argument the purifier's own header makes, now measured. BF-73 was filed because the XSS fix created its trigger: the new RangeError escapes uncaught to the error page. Independently reproduced against v15.0.8 - the 500 body named six absolute paths and the deployment's directory layout.

### `ADV-CONFIG` &mdash; The readable-by-world warning, the careportal role, and the two settings behind both (BF-77, BF-78, BF-81)

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/master@92d08342` |
| worktree | `externals/work/crm-advisory` |
| semver | `patch` |
| review | MAINTAINER - the two that remain are contract questions about the configuration surface, not bugs with an obvious patch. BF-77 was merged on its own, leaving BF-78 and BF-81 as the pair to decide together. The coupling: TREATMENTS_AUTH=off appends ' careportal' to authDefaultRoles; the boot warning compared that string for equality with 'readable'; so on 15.0.8 the notice is suppressed in exactly the configuration that is both world-readable AND anonymously writable. Meanwhile careportal alone grants only api:treatments:create and is refused by the router's api:treatments:read gate before reaching the create route - so the ONLY configuration in which careportal does anything is the one whose warning BF-77 suppresses. An operator who wants anonymous careportal entry is steered, by the only route that works, into the configuration that stops warning them. BF-78 fails CLOSED - nothing is exposed - which is why it is low; the defect is silence, not access. |
| ships to operators today | **yes** |
| register | `BF-77`, `BF-78`, `BF-81` |

**Blast radius.** BF-77 is merged; the item stays `needs-decision` for BF-78 and BF-81. BF-77 merged 2026-09-21 as PR #8746 - bf/readable-warning, measured at 74731433, merged as 74fc6619, with an integration merge of dev (91ed8d95) added to the branch on the way in. Rather than string equality at lib/server/bootevent.js:149 it adds a second notice wording for the readable+careportal configuration, wording the maintainer approved the same day. 2311 -> 2331 passing / 0 failing; the ablation goes red on exactly the three careportal cases with thirteen still passing, so the new cases are not vacuous. Not released. BF-78 is untouched by that merge. Three possible shapes and none obviously right: give the careportal role the read permission its routes require; move the router-wide read gate at lib/api/treatments/index.js:26 below the create route at :146; or document that careportal only functions alongside `readable` and say so at boot when it does not. BF-81 is prose - README.md and the swagger documents - with no branch, and the wording is a maintainer's to write.

**What an operator sees.** Two things about the settings that control who can see your Nightscout. First, on release 15.0.8 and earlier, if you set TREATMENTS_AUTH=off, the warning that normally tells you "your Nightscout is readable by anyone who knows the address" stops appearing - even though that setting also lets anyone add treatments. The site is not more exposed than you asked for, but you stop being told. This is corrected in the development branch and arrives with the next release (15.0.9). Second, setting AUTH_DEFAULT_ROLES=careportal on its own does nothing at all: the documentation says any valid role name works, and this one is silently ignored, with no error anywhere. If you wanted "nobody can read my site, but my family can enter carbs without a token", that combination does not currently exist. Nightscout is not a medical device and this is not medical advice.

**Why `patch`.** BF-77 restores a notice that was intended; no interface changes. BF-78's semver depends on which of the three shapes is chosen - giving careportal a read permission would widen a documented role and is at least minor, so that half is deliberately left unscored until the decision is taken.

**Gates.**

- `[static]` `git -C externals/work/crm-adv-shipping grep -q "authDefaultRoles == 'readable'" v15.0.8 -- lib/server/bootevent.js`
  - The exact-string compare is present on the shipping release tag. The tag is immutable, so this records the shipping state rather than tracking the fix; BF-77's fix is in dev via PR #8746.
- `[static]` `git -C externals/work/crm-adv-shipping grep -q "isPermitted('api:treatments:read')" v15.0.8 -- lib/api/treatments/index.js`
  - The router-wide read gate BF-78 is about is present on the shipping release.
- **NO GATE** &mdash; The behavioural half is not gated. Both findings were measured by booting the tree in three and four configurations respectively and reading GET /api/v2/adminnotifies and the result of an anonymous treatment POST. Automating that needs a fixture that boots the app per configuration, which does not exist in this repo. The measurements and their controls are in the evidence document; the two source gates above are the cheap proxy and they measure presence, not behaviour.

**Evidence.**

- `docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md`
- `docs/30-design/remedial/security-advisory-disposition-2026-09-21.md`
- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** DECIDED 2026-09-23 (maintainer) - BF-78 (the careportal role) is documented and warned about at boot; no behaviour change. Found while building the configuration matrix that answers "were the right flags set when the five advisories were evaluated"; these two fell out of enumerating what AUTH_DEFAULT_ROLES actually gates. REPRODUCED on v15.0.8 AND dev 59430336, mongod 7.0, with both controls in the same run. BF-77: default -> notifyCount 1, title "Nightscout readable by world" (POSITIVE CONTROL, the notice does fire when it should); TREATMENTS_AUTH=off -> notifyCount 0 while anonymous read is 200 and anonymous POST /api/v1/treatments is 200 with the record stored; AUTH_DEFAULT_ROLES=denied -> notifyCount 0, correctly (NEGATIVE CONTROL, so absence in the middle row is attributable to the string compare and not to the notice being broken generally). These are documented configurations, not a bypass. BF-78, anonymous POST /api/v1/treatments: `readable careportal` 200 stored, `careportal` 401, `denied careportal` 401, `denied` 401. BF-81 was filed on the maintainer's instruction, 2026-09-21, as the shared root of the other two: the configuration surface carries two authorization-shaped settings with adjacent names - AUTH_DEFAULT_ROLES, which is the boundary, and AUTHENTICATION_PROMPT_ON_LOAD, which is a client prompt that grants nothing - and nothing documents the difference. Its strongest evidence is that the reporter of GHSA-8849 keyed their own security patch to the wrong one. It is prose in README.md and the swagger documents, there is no branch, and the wording is a maintainer's to write.

### `BFQ-103` &mdash; BF-103 - a split drag stores the old time, so IOB and COB ignore the move

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/split-drag-time` |
| base | `origin/dev@4011193e` |
| worktree | `externals/work/crm-bf-split-drag` |
| semver | `patch` |
| review | SAFETY - the move changes when carbs or insulin count for IOB and COB |
| ships to operators today | **yes** |
| register | `BF-103` |

**Blast radius.** One commit 8d797ba4 on dev 4011193e: new lib/client/treatmenttime.js, wired into lib/client/renderer.js (Move, Move carbs, Move insulin) and lib/report_plugins/treatments.js (Reports editor save); tests/treatmenttime.test.js (13) and tests/dependency-d3.test.js updated to the new emitted messages. ddata.js's read rule and the server write path are unchanged.

**What an operator sees.** If you drag a treatment on the chart into the "Move carbs" or "Move insulin" area to split it, the chart shows the moved part at its new time, but Nightscout keeps using the old time when it works out insulin on board and carbs on board. Until this is fixed, avoid splitting a treatment by dragging it into those areas. This is not medical advice; talk to your care team about any treatment record you are unsure of.

**Why `patch`.** a client bug fix

**Gates.**

- **NO GATE** &mdash; Reproduced by hand on 15.0.8 and the combined rc ec70aab0 with a control (COB 0 vs 25 g, IOB 0 vs 2.49 U for the same record). No fix and no automated test yet; the test to add drags into each split zone and asserts the stored mills and date of the new record.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/bf103-split-drag-stale-time-2026-09-23.md`
- `docs/60-research/remedial/bf103-fix-2026-09-23.md`
- `docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md`

**Notes.** 2026-09-24 - #8760 MERGED into dev as ddd9b600 (01:43Z), CI and CodeQL green. 2026-09-23 - VERIFIED BY HAND on #8760 8d797ba4 (the maintainer, manual lab port 15204, Chrome, mouse): Move carbs and Move insulin land at the new time with no console errors and survive a reload; plain move, cancel and both edge limits unchanged; a plain move of a pre-damaged record (stale mills, date string, mgdl, scaled) cleared mills, mgdl and scaled and set date to the new created_at as a number. Stored split records carry none of the page fields. Not shown live: COB for the repaired record (its new time was past absorption). Record: docs/60-research/remedial/manual- lab-15.0.9-rc-2026-09-23.md. 2026-09-23 - OPEN upstream as #8760 (head 8d797ba4, verified with ls-remote). BUILT 2026-09-23, CLEAN by the plan section 1a conditions, so it goes into 15.0.9: browser probe red on dev and green on the branch for split, plain move of a damaged record (both stored shapes), split of a damaged record and a v3 record (e.g. COB 0 vs 25 on dev, equal on the branch); dependency-d3 21/3 on dev, 24/0 on the branch; suite 2440/0/3 dev, 2453/0/3 branch on Node 20 and 22 (after npm run bundle); 9 of 9 break-its caught by the browser probe (7 by unit tests); merge-tree clean with #8754 8211f8e2 and #8758 6d120fa2. The split copy drops page-added mills, endmills, mgdl, scaled, cuttedby, cutting and a Date-typed date; a move clears them on the stored record and sets a disagreeing stored date to the new time (API v3 and AAPS use date). A raw v1 PUT still leaves a stale mills (server- side, not in scope). Server-side options measured, not built: ddata preferring created_at retimes other collections too; stripping on websocket dbAdd leaves existing records stale. Read-only repair query in the evidence section 8. Evidence docs/60-research/remedial/bf103-fix-2026-09-23.md; PR body reports/phase0-pr-bodies/bf-split-drag-time.md. DECIDED 2026-09-23 (maintainer): into 15.0.9 if bf/split-drag-time comes back clean (plan section 1a, "BF-103"); otherwise a known issue (advice: avoid splitting by drag; edit- the-time is unmeasured). Branch being built by session -36b (worktree externals/work/crm-bf-split-drag). Filed 2026-09-23 by -6d (register 0c022da5); queue item added by -59. Graded medium to high in the register. Not a 15.0.9 blocker as recorded; it is on 15.0.8 too. Scope for 15.0.9 is the maintainer's.

### `BFQ-106` &mdash; BF-106 - a numeric date filter on API v1 activity matches nothing on dev

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `origin/dev` |
| base | `origin/dev@ddd9b600` |
| worktree | `-` |
| semver | `patch` |
| review | maintainer |
| register | `BF-106` |

**Blast radius.** lib/server/query.js default_options, or the activity entry in the coercion schema. Read path only; nothing is written or deleted differently.

**What an operator sees.** On 15.0.9 as it stands, a tool that asks the older API for activity records by their numeric date gets an empty list instead of the records it got on 15.0.8. Nothing stored changes, and the Nightscout pages do not use this filter.

**Why `patch`.** restores a 15.0.8 read behaviour that the coercion change removed

**Gates.**

- `[static]` `node tools/queue/gates/bf106-activity-date-coercion.js`
  - Builds the activity query with origin/dev's own query.js and activity.js and checks that a find[date][$gte] bound is a number. Its control is origin/master (15.0.8), where the bound is a number. RED while BF-106 is present.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md`

**Notes.** 2026-09-23 - FILED (maintainer's go-ahead, session -6a) after the consumer- replay lab reproduced it: 7 records on v15.0.8, 0 on dev ddd9b600 and on the candidate (tree 2ce67b27), with the created_at control at 7 on all three. Whether it goes into 15.0.9 is the maintainer's call.

### `BFQ-107` &mdash; BF-107 - a failed treatments query ends the Nightscout process on 15.0.8

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `fix/treatments-query-errors-8675` |
| base | `origin/dev` |
| worktree | `-` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-107` |

**Blast radius.** lib/api/treatments/index.js serveTreatments: the query error is answered with HTTP 500 JSON instead of throwing on null results.

**What an operator sees.** On 15.0.8 one kind of failed treatment search stops the whole Nightscout server, so the site, its glucose display and its alarms go offline until it restarts. 15.0.9 answers that search with an error instead. Until you upgrade, keep your CGM app's or pump's own alarms on.

**Why `patch`.** a crash fix

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 0ab266a3 origin/dev`
  - #8697's merge 0ab266a3 is contained in origin/dev.
- **NO GATE** &mdash; Reproduced in the consumer-replay lab on 2026-09-23 (15.0.8 exits, dev and the candidate answer 200). The trigger is kept out of this public repository because the defect is live on the shipping release.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md`

**Notes.** 2026-09-23 - FILED (session -6a) after the consumer-replay lab. Upstream issue #8675 and PR #8697 (merged 2026-09-06) predate the entry; the register had no id for it, so the exposure count left it out.

### `BFQ-108` &mdash; BF-108 - a list of timestamps under the date field answers 500, so bulk deletes by timestamp do nothing

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `origin/dev` |
| base | `origin/dev@ddd9b600` |
| worktree | `-` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-108` |

**Blast radius.** lib/server/query.js enforceDateFilter, the ISO rewrite of date operator values.

**What an operator sees.** If you use xDrip4iOS, readings it asks Nightscout to delete in bulk stay on your site. Nothing is lost or changed; the extra readings are ones the app meant to remove.

**Why `patch`.** a bug fix; the request answers 500 today

**Gates.**

- `[static]` `node tools/queue/gates/bf108-date-in-list.js`
  - Builds the entries query from origin/dev's own query.js with a two-timestamp find[date][$in]; its control is the same filter with one timestamp. RED on v15.0.8, dev ddd9b600 and the candidate 1067e668. No ref carrying a fix exists yet, so the gate has never been seen green.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md`

**Notes.** 2026-09-23 - FILED (session -6a) after the consumer-replay lab reproduced it on all three builds with a one-value control. xdripswift c268542e NightscoutSyncManager.swift:794-806 is the client that sends it.

### `BFQ-97` &mdash; BF-97 - on the connector 0.1.0 line, a source with a profile stalls every poll

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `nightscout-connect` |
| branch | `fix/profile-sync-bounded-update` |
| base | `official/dev@fbd4e55` |
| worktree | `externals/work/nc-profile-sync` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `BF-97` |

**Blast radius.** Connector lib/outputs/internal.js safePersist and lib/outputs/nightscout.js recordingError, changed by 808ab1c (2026-09-21) to fail the whole poll on any write failure; the Nightscout source re-inserts every profile with its source _id each poll, so a duplicate key fails every poll after the first.

**What an operator sees.** Not in any release yet. With the connector version that 15.0.9 was going to use, a Nightscout site that copies its data from another Nightscout site fell 20 to 55 minutes behind whenever the other site had a profile saved, and showed no error. Nothing was lost; readings arrived late. It is being fixed before that connector version is released.

**Why `patch`.** A regression fix on an unreleased line; no setting or API moves.

**Gates.**

- **NO GATE** &mdash; Measured by the lab soak (tools/lab/connector-soak/), not a queue gate. The fix branch is to carry a unit test that a second poll with the same profile does not fail, and that a genuine write failure still does.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/connector-0.1.0-dev.2-soak-2026-09-23.md`

**Notes.** MERGED 2026-09-23 - connector #79 (fix/profile-sync-bounded-update, de3cee1, all four commits f6359b4, f924de2, 1d2ebc8, de3cee1) merged into connector dev as 977da8a, CI green; verified here with merge-base. Not tagged: v0.1.0-dev.3 is the maintainer's next step (npm next is still 0.1.0-dev.2). The pin PR to dev.3 and the combined re-run follow its publish. 2026-09-23 - #8752 MERGED into dev (f0954a6a, 08:37 UTC), so dev and the Docker image built from it install 0.1.0-dev.2, which carries this stall for Nightscout-to-Nightscout sites whose source has a profile. The pin must move to the fixed connector before 15.0.9 is tagged. DECIDED 2026-09-23 (maintainer) - (1) re-read what the sink stores each poll instead of caching per process, with the cost bounded (the maintainer asked whether it covers all profiles or only the latest); (2) update on change: a source edit to an existing profile replaces the sink copy. NOT BUILDABLE AS ASKED, found by a lab probe on 74fc6619 (no code written, f924de2 unchanged): the connector's copies are stored with string _ids, and Nightscout's save/remove/_id lookups convert to ObjectId, so a PUT duplicates instead of replacing and DELETE cannot remove the copy (filed as a cgm-remote-monitor backfix, branch bf/profile-object-id in preparation). API-style in-place edits leave no timestamp. Reports use older profiles, so a bounded fetch misses edits to non-newest documents. Cost today at 500 profiles of about 7 KB: about 3.5 MB per poll; bounded shape about 14 KB. Waiting on the maintainer: what 0.1.0 ships (bounded insert-only, or wait for the Nightscout fix). #8752 still holds. PREPARED 2026-09-23 - f6359b4 on fix/profile-duplicate-stall (tip f924de2, on fbd4e55, not pushed): profiles already stored on the sink, by _id or identifier, are skipped instead of failing the poll, in both the internal and REST outputs; every other write failure still fails it. Connector suite 292 -> 304 -> 308 on Node 20/22/24. 96-minute soak arm: fix polls every 5.0 min median with 0 lag before the outage, 0 profile errors; the dev.2 control in the same run stalls at 28.9 min. A source edit to an existing profile is skipped (as in 0.0.13); the stored set is cached per process (open question for the maintainer). REST output covered by fake-transport tests only. Evidence docs/60-research/remedial/connector-profile-duplicate-stall-2026-09-23.md. DECIDED 2026-09-23 (maintainer) - fix in the connector first, tag 0.1.0-dev.3, then 0.1.0; #8752 (P0-PIN) holds for dev.3. Fix being built in this session on fix/profile-duplicate-stall (not pushed). Workaround until then: CONNECT_SOURCE_COLLECTIONS=entries,treatments,devicestatus. BUILT 2026-09-23 - fix/profile-sync-bounded-update, tip de3cee1 on f924de2 (so it carries f6359b4 and the BF-98 warning), not pushed. 1d2ebc8 reads only the profiles a poll needs (6.8 KB per steady poll against 3.4 MB); de3cee1 copies a changed source profile when the sink can replace it in place, checked by a find by _id, so sinks without BF-99 get no copies and one warning. Connector suite 308 -> 319 -> 334 on Node 20/22/24, also under four faked clocks (a wall-clock test dependency was found by re-running at 20:19 UTC and fixed in the test). Lab (synthetic, 46-80 min, 10 sinks incl. 15.0.8, dev, 9b8cc2f9, 597e2899): no twins, edits arrive on BF-99 sinks, polls 4.7-5.3 min, entries/treatments/devicestatus counts match. Maintainer decisions (plan section 1a): newest-1 bound, no backfill, source wins. Next: tag 0.1.0-dev.3 from it, then the pin PR. Evidence docs/60-research/remedial/connector- profile-sync-bounded-update-2026-09-23.md; PR body reports/connector-pr- bodies/profile-sync-bounded-update.md.

### `BFQ-98` &mdash; BF-98 - the connector reuses a reader subject without roles, so the BF-89 fix does not repair it

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `nightscout-connect` |
| branch | `fix/profile-duplicate-stall` |
| base | `official/dev@fbd4e55` |
| worktree | `externals/work/nc-profile-dup` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-98` |

**Blast radius.** Connector lib/sources/nightscout.js reader-subject lookup (v0.0.13 lines 75-77), which takes the accessToken of any subject named nightscout-connect- reader without checking its roles.

**What an operator sees.** If your Nightscout copies data from another Nightscout site that requires sign-in (AUTH_DEFAULT_ROLES=denied), and it has never managed to read from it, an access entry named nightscout-connect-reader on the other site was probably created without a role. Upgrading the connector does not fix that entry. On the other site's admin page, either give nightscout-connect-reader the readable role or delete it so the connector creates it again.

**Why `patch`.** Adds one log message; no setting or API moves.

**Gates.**

- **NO GATE** &mdash; Reproduced by the lab soak's control (c), not a queue gate. The warning commit is to carry tests for both triggers and for logging once.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/connector-0.1.0-dev.2-soak-2026-09-23.md`

**Notes.** MERGED 2026-09-23 - connector #79 (fix/profile-sync-bounded-update, de3cee1, all four commits f6359b4, f924de2, 1d2ebc8, de3cee1) merged into connector dev as 977da8a, CI green; verified here with merge-base. Not tagged: v0.1.0-dev.3 is the maintainer's next step (npm next is still 0.1.0-dev.2). The pin PR to dev.3 and the combined re-run follow its publish. PREPARED 2026-09-23 - f924de2 on fix/profile-duplicate-stall (not pushed): one warning per process when the reused nightscout-connect-reader has no roles, or when a read returns 401, naming the subject and both fixes; no writes to the source; no token, secret or URL in the message. Exact wording in the evidence doc for the release notes. DECIDED 2026-09-23 (maintainer) - warn clearly, don't repair: one plain log message naming the subject and both fixes, no writes to the source; the release notes carry the same steps. Being built as a second commit on fix/profile-duplicate-stall (not pushed).

### `BFQ-99` &mdash; bf/profile-object-id - a profile posted with its own _id is stored as an ObjectId, and string-_id profiles can be edited and deleted

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `bf/profile-object-id` |
| base | `origin/dev@1f9a9d10` |
| worktree | `externals/work/crm-bf-profile-id` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-99` |
| blocks on | `BFQ-102` |

**Blast radius.** lib/server/profile.js create, save, remove and the find[_id] path, plus tests/api.profiles.object-id.test.js (13 tests). One commit, 9b8cc2f9.

**What an operator sees.** If your Nightscout copies data from another Nightscout, or you restored profiles from an export, editing one of those profiles on today's release (15.0.8) adds a second profile and keeps the old one, and deleting it does not remove the old one. With this fix an edit replaces the profile and a delete removes it, including profiles saved before you upgrade. Reports that show basal rates or insulin-on-board for past days read the profiles that were active then, so a leftover old copy can affect what they show. This is not medical advice; if a report looks wrong, check the profile against your care team's settings.

**Why `patch`.** Bug fix; no API or setting moves. Stored _id type changes from string to ObjectId for new hex _ids, as treatments already do.

**Gates.**

- **NO GATE** &mdash; The new test file passes on the branch and fails 11 of 13 on dev 1f9a9d10 and on 15.0.8; a queue gate running it against both trees does not exist yet.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/60-research/remedial/profile-object-id-2026-09-23.md`

**Notes.** SUPERSEDED 2026-09-23 - the maintainer chose BFQ-102 for 15.0.9, and this item's fix is carried by #8758 (bf/object-id-crud 6d120fa2). This branch will not be opened; the item follows #8758 and is marked merged-upstream when it merges. PREPARED 2026-09-23 on the maintainer's instruction ("another backfix issue"). Merge-tree clean against every open 15.0.9 PR head and rc/15.0.9-additions-e 1b1977e0; the merged tree with 1b1977e0 passes the profile and count tests 112/0. Destination release not decided. Unblocks the connector's profile update-on-change (BFQ-97). PR body draft reports/phase0-pr-bodies/bf-profile-object-id.md. SUPERSEDED BY BFQ-102 (2026-09-23, maintainer): 15.0.9 takes bf/object-id-consistency; this branch is not pushed. The queue has no superseded state, so the state is left as measured. Conflicts in lib/server/profile.js with bf/object-id-consistency (BFQ-102), which carries the same fix on a shared helper; land one. modernization b1bdaca0 reproduces it (11 of 13 red on Node 22.23.2 and 24.20.0).

### `BFQ-100` &mdash; BF-100 - devicestatus, food and activity store a hex _id as a string

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `bf/object-id-other-collections` |
| base | `origin/dev@1f9a9d10` |
| worktree | `externals/work/crm-bf-object-id` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-100` |
| blocks on | `BFQ-102` |

**Blast radius.** lib/server/devicestatus.js, food.js and activity.js create, update, remove and find[_id], plus the shared helper lib/server/object-id-forms.js. Two commits, 1a445864 and 2fac53f5.

**What an operator sees.** Records sent with their own id by another program can end up impossible to delete by that id, and editing a food or activity record that way adds a second copy. This is how today's release (15.0.8) behaves.

**Why `patch`.** Bug fix, same shape as BF-99.

**Gates.**

- **NO GATE** &mdash; New tests fail 27 of 31 on dev 1f9a9d10 and pass on the branch; suite 2432/0/3 on Node 20 and 22. No queue gate runs them yet.

**Evidence.**

- `docs/60-research/remedial/profile-object-id-2026-09-23.md`
- `docs/60-research/remedial/object-id-other-collections-2026-09-23.md`

**Notes.** SUPERSEDED 2026-09-23 - the maintainer chose BFQ-102 for 15.0.9, and this item's fix is carried by #8758 (bf/object-id-crud 6d120fa2). This branch will not be opened; the item follows #8758 and is marked merged-upstream when it merges. Filed 2026-09-23 beside BF-99; built the same day. Narrow alternative to BFQ-102, which includes it as commit c. devicestatus has no create guard; the connector's in-process output does not re-send (strict created_at watermark, measured). PR body draft reports/phase0-pr-bodies/bf-object-id- other-collections.md.

### `BFQ-101` &mdash; BF-101 - API v3 id filters miss records stored with a string _id

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `bf/api3-string-id` |
| base | `origin/dev@1f9a9d10` |
| worktree | `externals/work/crm-bf-api3-id` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-101` |
| blocks on | `BFQ-102` |

**Blast radius.** lib/api3/storage/mongoCollection/utils.js filterForOne and identifyingFilter, plus the shared helper. Two commits, 96eaca1b and 7295bc8c.

**What an operator sees.** Apps that use Nightscout's newer API cannot find, by id, records that were saved with a text id through the older API. This is how today's release (15.0.8) behaves.

**Why `patch`.** Bug fix.

**Gates.**

- **NO GATE** &mdash; New v3 route tests fail 9 of 10 on dev and pass on the branch; suite 2411/0/3 on Node 20 and 22; explain() keeps IXSCAN, no COLLSCAN. No queue gate yet.

**Evidence.**

- `docs/60-research/remedial/profile-object-id-2026-09-23.md`
- `docs/60-research/remedial/object-id-other-collections-2026-09-23.md`

**Notes.** SUPERSEDED 2026-09-23 - the maintainer chose BFQ-102 for 15.0.9, and this item's fix is carried by #8758 (bf/object-id-crud 6d120fa2). This branch will not be opened; the item follows #8758 and is marked merged-upstream when it merges. Filed 2026-09-23 beside BF-99; built the same day. Narrow alternative to BFQ-102 (its commit e). PR body draft reports/phase0-pr-bodies/bf- api3-string-id.md.

### `BFQ-102` &mdash; bf/object-id-consistency - one rule for a record's own hex _id across profile, devicestatus, food, activity, treatments, entries and API v3

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/object-id-crud` |
| base | `origin/dev@1f9a9d10` |
| worktree | `externals/work/crm-bf-object-id-crud` |
| semver | `patch` |
| review | maintainer |
| ships to operators today | **yes** |
| register | `BF-99`, `BF-100`, `BF-101`, `BF-102` |

**Blast radius.** Five commits to 597e2899: the helper lib/server/object-id-forms.js; profile (BF-99); devicestatus, food, activity (BF-100); treatments and entries, moved onto the helper with the UUID path unchanged (BF-102); API v3 filters (BF-101). Then bf/object-id-crud adds eight commits to 6d120fa2: entry re-POST with its own _id ($setOnInsert), upper-case hex on /entries/<id>, websocket dbAdd/dbUpdate/dbRemove through the helper, a 336-cell CRUD-by-id matrix over v1, v3 and the websocket, then the maintainer's D2 (v3 reaches non-hex string _ids), D3 (entries POST answers the stored _id), D1 (devicestatus re-send guard) and D4 (helper header). The only existing test changed is tests/api3.storage.modify.test.js, three filter-shape assertions (D2).

**What an operator sees.** Records that arrive with their own id (copied from another Nightscout by the connector, restored from an export, or saved by 15.0.6 or earlier) can be edited and deleted normally: an edit replaces the record instead of adding a second copy. Nothing in the database changes until a record is edited or deleted. This is not medical advice; if settings or history look wrong, check them with your care team.

**Why `patch`.** Bug fixes; no API or setting moves.

**Gates.**

- **NO GATE** &mdash; New tests red on dev (11/13, 27/31, 13/15, 9/10); each commit's full suite green on Node 20 and 22 (2401, 2414, 2445, 2460, 2470 passing, 0 failing, 3 pending); every hunk broken singly goes red. bf/object-id-crud: 2478, 2483, 2496, 2832, 2848, 2858, 2866, 2866 passing, 0 failing, 3 pending per commit on Node 20 and 22; matrix 336/336 on MongoDB 7 and 4.4 (dev: 176/336). No queue gate runs them yet.

**Evidence.**

- `docs/60-research/remedial/object-id-other-collections-2026-09-23.md`
- `docs/60-research/remedial/profile-object-id-2026-09-23.md`
- `docs/60-research/remedial/crud-by-id-matrix-2026-09-23.md`

**Notes.** 2026-09-23 - OPEN upstream as #8758 (head 6d120fa2, verified with ls-remote), CI green. One PR from bf/object-id-crud (contains bf/object-id-consistency 597e2899). D1 to D4 decided 2026-09-23 (plan section 1a) and applied. The D1 check adds about 1 ms to a 100-row devicestatus batch that carries hex _ids and nothing without. Merge-tree clean with every open 15.0.9 PR head incl. #8757 5d342ac1 and rc-e; the narrow alternatives 2fac53f5 and 7295bc8c now conflict with it and are not to land. Built 2026-09-23 on the maintainer's question whether one PR could carry the through-line. Merge-tree clean with every open 15.0.9 PR head and rc/15.0.9-additions-e 1b1977e0; conflicts with bf/profile-object-id (BFQ-99) in lib/server/profile.js, so land one. Merged trees not run through the suite. DECIDED 2026-09-23 (maintainer): this ships in 15.0.9 instead of BFQ-99, with consistent working CRUD across the API (plan section 1a, "15.0.9 ID consistency"). PR body draft reports/phase0-pr- bodies/bf-object-id-consistency.md.

---

## Multitenancy programme

`parcel: tenancy` &mdash; 18 items

T3.0 and the DONE-EXCEPT remainders it amends, T4.3, T4.4, the four open §7a
alarm-readiness items, and the seam branch refresh.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `T30-RESEARCH` | T3.0 part 1 - enumerate the per-tenant configuration surface | `needs-decision` | `-` | n/a | 1 run + 3 no-gate |
| `T30-AUTH` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-interface split | `ready-to-push` | `main` | n/a | 2 run + 4 no-gate |
| `T30-SCHEMA-CRED` | T3.0 part 2a - device and data-path credential storage in platform.sql | `not-started` | `-` | n/a | 1 run + 2 no-gate |
| `T30-SCHEMA-CONFIG` | T3.0 part 2b - per-tenant configuration table, and where human identity lives | `not-started` | `-` | n/a | 1 run + 2 no-gate |
| `T30-ORY-PROOF` | Stand up Kratos 1.x and Hydra 2.x and try to make one pool serve two tenants | `not-started` | `-` | n/a | 0 run + 3 no-gate |
| `T30-WIRING` | T3.0 part 3 - deriveEnv overrides, tenant-scoped isApiKey/verifyJWT | `not-started` | `-` | n/a | 0 run + 1 no-gate |
| `T31-REM` | T3.1 remainder - per-tenant signing key replaces the install-wide one | `blocked` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `T32-REM` | T3.2 remainder - platform.sql carries no config, secret or signing key | `blocked` | `seam/t1-2-storage-interface` | n/a | 0 run + 1 no-gate |
| `T33-REM` | T3.3 remainder - the shared enclave, and language/levels per tenant | `blocked` | `seam/t1-2-storage-interface` | n/a | 0 run + 2 no-gate |
| `T43` | T4.3 - ns-realtime, LISTEN per served tenant | `not-started` | `-` | n/a | 1 run + 2 no-gate |
| `T44` | T4.4 - ns-evaluator, the per-tenant evaluation loop | `not-started` | `-` | n/a | 1 run + 2 no-gate |
| `A7A-3` | §7a item 3 - a per-tenant error boundary | `not-started` | `-` | n/a | 0 run + 1 no-gate |
| `A7A-4` | §7a item 4 - a health signal for a silent per-tenant outage | `not-started` | `-` | n/a | 0 run + 1 no-gate |
| `A7A-7` | §7a item 7 - the clock question | `unsettled` | `-` | n/a | 0 run + 1 no-gate |
| `A7A-GATE` | The alarms-on gate itself - nothing here may be marked done by inference | `blocked` | `-` | n/a | 0 run + 2 no-gate |
| `SEAM-REFRESH` | Refresh the seam chain onto a moved modernization branch | `gate-not-met` | `seam/t1-2-storage-interface` | n/a | 2 run + 1 no-gate |
| `BFQ-66` | BF-66 - the deployment's own tokens fail its own tenant check | `blocked` | `crm-seam` | n/a | 0 run + 2 no-gate |
| `BFQ-CAP02` | CAP-02 - no importer, and no Mongo to PostgreSQL loader | `not-started` | `crm-seam` | n/a | 0 run + 2 no-gate |

### `T30-RESEARCH` &mdash; T3.0 part 1 - enumerate the per-tenant configuration surface

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer. The document is a DRAFT carrying sections marked DECISION that need a yes before T30-SCHEMA-CONFIG can start; the item is a decision surface, not an unstarted research task. |

**Blast radius.** A design report. Every SETTINGS_* variable, every plugin credential, which are secrets and which are not, what a tenant may override versus what the hoster pins. Delivered as section B of the tenant-owner config-surface document: 277 distinct names, classified T / TS / D / B / X, measured against crm-seam at 81a1f6ce.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** research deliverable

**Gates.**

- `[static]` `test -f docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md`
  - the deliverable exists. A presence check only; it says nothing about whether the enumeration is complete or correct.
- **NO GATE** &mdash; Nothing checks that the enumeration is COMPLETE. The only non-vacuous form is a differential: enumerate from the report, enumerate from lib/server/env.js by parsing, and require the two sets to agree - with a planted extra variable as the control. The census script exists, at section G.3 of the deliverable, and reproduces {"s1":70,"s2":51, "s3prefixes":37,"s4":208,"union":247} against crm-seam at 81a1f6ce. It is not checked in anywhere and nothing re-runs it, so the 247 is a transcript rather than a measurement. Lifting G.3 into tools/queue/gates/ is the cheapest real gate this item can have.
- **NO GATE** &mdash; The document names five gaps in its own coverage and none is closed. (1) the grep cannot see process.env['X'], which is how it missed the API v3 family that includes the one that irreversibly deletes data; (2) three AWS names are read directly and appear in no source; (3) twelve ADMIN_* / FEED_* names read by the hosted entrypoints appear in no source, no gap and no total; (4) webhook's four reads are inside the plugin factory, not at module scope; (5) the per-group counts inside each class are hand-expansions, not script output, and the document says so. Completeness is therefore bounded by a method the document itself argues against.
- **NO GATE** &mdash; Section A's DDL has never been executed against a PostgreSQL server, and two findings against it - the ?| operator being top-level only, and a CHECK passing when its expression is NULL, which lets a PARTIAL mmol threshold override through - are read-derived from PostgreSQL's documented semantics, not run on a server. Those two are the first thing the section A harness must test, and the second is about alarm thresholds.

**Evidence.**

- `docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md`
- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** T3.0 is the largest correction owed in the programme. It does not block T3.3, which landed first; it AMENDS T3.1, T3.2 and T3.3, all marked DONE-EXCEPT. The enumeration was written and adversarially reviewed on 2026-09-15; the surface total is 277. What remains is not enumeration: it is the maintainer decisions the document defers, and the harnesses that would turn its numbers into measurements. The three decisions with the longest reach are where the tenant- owner API lives, what issues and verifies a tenant-owner credential, and whether D7's credential-free platform plane holds against Nocturne's design, which puts platform admin on the consumer API behind a platform_admin role instead.

### `T30-AUTH` &mdash; The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-interface split

| | |
|---|---|
| state (claimed) | `ready-to-push` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@671bc88d` |
| worktree | `.` |
| semver | `n/a` |
| review | maintainer decided 2026-09-16; SECURITY still owes D17 row 2 a look, and that row is deliberately left provisional. Under the one-deployment shape the authentication plane is cohort-wide by construction, so tenant isolation rests entirely on the authorization layer and RLS - written down as the D13 amendment. |

**Blast radius.** No code; the deliverable is a document in this repository. Decided 2026-09-16: D16 adopted whole, D17 adopted in three rows of four. Recorded in the execution plan section 1 and section 2.9.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** research and decision, no shipped surface

**Gates.**

- `[static]` `test -f docs/60-research/tenancy/auth-plane-ory-vs-inhouse-2026-09-16.md`
  - the deliverable exists. A presence check and nothing more - it cannot say whether the recommendation is right, only that it was written.
- `[static]` `grep -q '\*\*D16\*\*' docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md && grep -q '\*\*D17\*\*' docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`
  - the decision reached the execution plan's decisions table, not just a research document - the place a later reader looks first. It cannot tell whether the rows say the right thing.
- **NO GATE** &mdash; Every Ory claim in the deliverable is read-derived, not run. No Kratos and no Hydra instance was started. Read-derived claims in this programme have failed on contact with running code before, so this is a hypothesis. The discharge is specific: stand up Kratos 1.x and Hydra 2.x, register two tenants against one pool, and confirm a session for tenant A cannot be exchanged for a Nightscout token on tenant B (T30-ORY-PROOF).
- **NO GATE** &mdash; nightscout-roles-gateway was read, not executed. Its dependencies are 2022-era - @ory/kratos-client 0.9.0-alpha.3 and @ory/hydra-client 1.11.8 - and V0alpha2Api, which lib/privy/index.js:20 constructs, no longer exists under that name in Kratos 1.x. Whether its decision pipeline still works is unknown, and it is the first thing a port would measure.
- **NO GATE** &mdash; Nothing measures what a cohort-wide identity pool costs in isolation risk. Section 3.1 names the hazard - one identity, one session, one login spanning every tenant - and bounds nothing. A gate would need a cross-tenant session test, which needs the running stack the first no-gate asks for.
- **NO GATE** &mdash; No cost model. Ory Network pricing is not analysed and does not need to be under the one-deployment shape, which needs no Enterprise License - but the compliance question of any third-party processor adjacent to health data is not analysed either, and that one does not go away by self-hosting.

**Evidence.**

- `docs/60-research/tenancy/auth-plane-ory-vs-inhouse-2026-09-16.md`
- `docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md`

**Notes.** Decided 2026-09-16 (maintainer). D16 adopted whole, including the prerequisite: tenant resolution and credential verification extract to one module BEFORE the third listener exists, which lands on T30-WIRING. D17 adopted in three rows of four: devices and the data path keep a native per- tenant credential permanently (forced by D1 - an uploader cannot run an OAuth flow); Hydra deferred; D7 unchanged. Row 2 - Ory Kratos as one cohort-wide pool for human identity - is direction of travel, NOT adopted, because every Ory claim behind it is read-derived and a shared identity pool is irreversible once identities exist. It is gated on T30-ORY-PROOF. The deployment shape is settled: ONE Kratos and ONE Hydra for the whole cohort, unified auth for Nightscout tenants, not a Kratos tenant per Nightscout tenant - so Ory OSS being single-tenant (its multi-tenancy is the paid boundary) does not bind us. Other findings: Nocturne uses no Ory and built identity in-house; this project shipped an Ory integration once and stopped one component short of finishing it; and, measured after the decision (research document section 3.5), Nocturne's identity plane is deployment-scoped too, arrived at independently - the nearest thing to corroboration this decision has.

### `T30-SCHEMA-CRED` &mdash; T3.0 part 2a - device and data-path credential storage in platform.sql

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SECURITY - this is where D13's per-tenant credential root and D14's per-tenant signing key live |

**Blast radius.** lib/admin/platform.sql. GT3 measured it as holding exactly two tables - tenants (L23) and tenant_members (L49) - with subject_id uuid NOT NULL at L52 and NO foreign key and no signing-key column. This half adds D13's per-tenant root credential, D14's per-tenant signing key, the device and uploader credential tables, and a referent for tenant_members.subject_id.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release schema

**Gates.**

- `[static]` `node tools/queue/gates/platform-sql-surface.js --subset=cred`
  - FAILS while platform.sql carries no signing-key column, no per-tenant root credential and no referent for tenant_members.subject_id. Re-runs GT3's grep as a machine check. It measures that a COLUMN EXISTS and nothing about whether anything reads it - T30-WIRING owns that, and its D14 gate is the non-vacuous one.
- **NO GATE** &mdash; D13 forbids any deployment-wide secret under TENANCY_MODE=multi on any interface. Nothing checks for one. A gate would have to enumerate every place a secret can enter and assert none is deployment-wide under multi - which is the T30-RESEARCH deliverable. This item is not blocked on that, because a credential column can be added before the enumeration is complete, but the enumeration is what would turn this no-gate into a gate.
- **NO GATE** &mdash; Nothing here is executed against a PostgreSQL server. Section A of the config-surface document already carries two read-derived findings from PostgreSQL's documented semantics - the ?| operator being top-level only, and a CHECK passing when its expression is NULL - and the same hazard applies to any DDL this item writes.

**Evidence.**

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`
- `docs/60-research/tenancy/auth-plane-ory-vs-inhouse-2026-09-16.md`

**Notes.** The device and data-path half of the T3.0 schema work. D17 row 1 - native per- tenant credentials for devices and the data path, permanently - is adopted, so this half is unblocked. It takes nothing from the Ory question: row 1 holds however row 2 lands, because an uploader cannot run an OAuth flow and D1 keeps the self-hosted path first-class permanently. The human-identity columns are NOT in this item - they are in T30-SCHEMA-CONFIG, gated on T30-ORY-PROOF, so that no DDL is written for a table that may hold nothing.

### `T30-SCHEMA-CONFIG` &mdash; T3.0 part 2b - per-tenant configuration table, and where human identity lives

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SECURITY - a settings table holds plugin credentials, so the secret/non-secret split in T30-RESEARCH's classification is load-bearing here |
| blocks on | `T30-RESEARCH`, `T30-ORY-PROOF` |

**Blast radius.** lib/admin/platform.sql. D15's per-tenant configuration table, which hosted entrypoints read instead of the process environment, over the 277-name surface T30-RESEARCH enumerated - plus the human-identity columns, which exist only if D17 row 2 does not land.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release schema

**Gates.**

- `[static]` `node tools/queue/gates/platform-sql-surface.js --subset=config`
  - FAILS while platform.sql carries no configuration table. A presence check on a table name - it cannot see whether the 277 names reach it, which is what the T30-RESEARCH census script would measure if it were lifted out of section G.3 into tools/queue/gates/.
- **NO GATE** &mdash; Nothing measures that the settings table covers the surface. The census in T30-RESEARCH section G.3 reproduces a 247-name union against crm-seam at 81a1f6ce and is checked in nowhere, so it is a transcript rather than a measurement. Until it is a gate, "the configuration table is complete" is an assertion.
- **NO GATE** &mdash; Nocturne's shape is the one to copy and nothing checks that we did - a settings table keyed tenant_id + key with a JSON value, plus typed side-tables where constraints matter (TenantAlertSettingsEntity, TenantDataRetentionConfigEntity). The alarm-threshold side-table is the one that matters, because a NULL-passing CHECK on an mmol threshold is already a known hazard in section A's DDL.

**Evidence.**

- `docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md`
- `docs/60-research/tenancy/auth-plane-ory-vs-inhouse-2026-09-16.md`

**Notes.** Two different blockers. T30-RESEARCH blocks the configuration table, because the settings surface is what that item enumerates and what a tenant may override versus what the hoster pins is a decision it still defers. T30-ORY- PROOF blocks the human-identity columns, because D17 row 2 is direction of travel and not adopted: if one cohort-wide Kratos pool lands, human identity lives in Kratos with only a subject reference here; if it does not, these tables carry credentials, recovery and MFA. Those are different schemas. If this item is claimed before T30-ORY-PROOF resolves, do the configuration table and stop at the identity columns.

### `T30-ORY-PROOF` &mdash; Stand up Kratos 1.x and Hydra 2.x and try to make one pool serve two tenants

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `-` |
| base | `main@671bc88d` |
| worktree | `.` |
| semver | `n/a` |
| review | SECURITY. The property under test IS the isolation property the whole cohort-wide design rests on. |

**Blast radius.** A harness under tools/, no shipping code. It discharges the largest no-gate on T30-AUTH: every Ory claim behind D17 row 2 is read-derived, not run.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** harness only, nothing ships

**Gates.**

- **NO GATE** &mdash; Not started, so there is nothing to run. The gate it needs: register two tenants against ONE Kratos pool and confirm a session for tenant A cannot be exchanged for a Nightscout token on tenant B. WITH A CONTROL - the same session against tenant A's own host must succeed, or the failure is not known to come from the tenancy boundary. A red control can be red for the wrong reason, so the control itself must be checked.
- **NO GATE** &mdash; nightscout-roles-gateway was read, not executed. Its dependencies are 2022-era - @ory/kratos-client 0.9.0-alpha.3 and @ory/hydra-client 1.11.8 - and V0alpha2Api, which lib/privy/index.js:20 constructs, no longer exists under that name in Kratos 1.x. Whether its decision pipeline still works is the second thing this item should measure, and it is the whole cost estimate for a port.
- **NO GATE** &mdash; No cost model, and self-hosting does not dispose of it. Ory Network pricing does not apply under the one-deployment shape, which needs no Enterprise License - but the compliance question of any third-party processor adjacent to health data is unanalysed, and that one survives self-hosting because it is about who can reach the data, not who is billed for it.

**Evidence.**

- `docs/60-research/tenancy/auth-plane-ory-vs-inhouse-2026-09-16.md`

**Notes.** The condition on D17 row 2 (maintainer, 2026-09-16). Three of D17's four rows are adopted; row 2 - Ory Kratos as one cohort-wide identity pool for human identity, hosted-only - is direction of travel pending this measurement, because read-derived claims are hypotheses and a shared identity pool is effectively irreversible once identities exist. Roughly a day of work; it unblocks the identity half of T30-SCHEMA-CONFIG.

### `T30-WIRING` &mdash; T3.0 part 3 - deriveEnv overrides, tenant-scoped isApiKey/verifyJWT

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SECURITY |
| register | `BF-25` |
| blocks on | `T30-SCHEMA-CRED`, `T30-SCHEMA-CONFIG` |

**Blast radius.** lib/server/tenant-context.js, lib/server/tenant-middleware.js, lib/authorization/index.js.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; The task is not started, so there is nothing to run. The gate it will need is the D14 property stated as a test: tenant A's token presented against tenant B's host fails as a SIGNATURE failure, not a claim check - with a control where the same token against A's own host succeeds, so the failure is known to come from the key and not from everything failing.

**Evidence.**

- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** Line references for the implementer (GT3, crm-seam): the plan's amendment table cites tenant-context.js:137 as T3.3's site, but L137 is a comment stating the rejected reasoning; the mechanism is PER_TENANT_ENV_KEYS at L143 and the copy loop at L278 (`if (PER_TENANT_ENV_KEYS.includes(key)) continue;`). enclave.js's key read is at line 30. tenant-middleware.js's tenantClaim opens at L139 with verifyJWT at L144, so the range to change is 139-144.

### `T31-REM` &mdash; T3.1 remainder - per-tenant signing key replaces the install-wide one

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SECURITY |
| register | `BF-25` |
| blocks on | `T30-WIRING` |

**Blast radius.** lib/server/tenant-middleware.js tenantClaim (L139, verifyJWT at L144).

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; Blocked on T30-SCHEMA-CRED - there is no per-tenant key to verify against until the column exists, and that work is unblocked and can start. This row exists so that T3.1's DONE-EXCEPT does not read as DONE to an agent that only loads that section.

**Evidence.**

- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** Everything else in T3.1 stands: 18 guards broken one at a time, three changed nothing and all three were the tests' fault. Only the credential assumption is wrong.

### `T32-REM` &mdash; T3.2 remainder - platform.sql carries no config, secret or signing key

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |
| blocks on | `T30-SCHEMA-CRED`, `T30-SCHEMA-CONFIG` |

**Blast radius.** lib/admin/platform.sql; tenant_members.subject_id references nothing.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; Same as T30-SCHEMA-CRED and T30-SCHEMA-CONFIG, which are the work - this item spans both because platform.sql is missing a secret AND a signing key AND a config table. This row exists so T3.2's DONE-EXCEPT has a visible remainder rather than living only in a parenthesis in the plan.

**Evidence.**

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`

**Notes.** Also still open from T3.2's own "not done" list: two-role deployments are untested; logical-slot lag arithmetic has no producer until Phase 4; the admin plane is PostgreSQL-only by construction with no export for a single-tenant MongoDB deployment; reserved labels (www, api, admin) and xn-- prefixes are flagged, not enforced.

### `T33-REM` &mdash; T3.3 remainder - the shared enclave, and language/levels per tenant

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |
| register | `BF-31` |
| blocks on | `T30-WIRING` |

**Blast radius.** lib/server/tenant-context.js - PER_TENANT_ENV_KEYS at L143 and the copy loop at L278 (not L137, which the plan cites). Plus the process-wide `language` instance at lib/server/server.js:34 and the one authorization subjects array.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; The enclave half is blocked on T30-WIRING. The language half is partly discharged - BF-31 is merged to dev via bf/alarms (P0-A, PR #8739), not released - but `language` and `levels.translate` are still one process-wide instance, and authorization subjects remain one process-wide array. Neither has a test that would notice a second tenant.
- **NO GATE** &mdash; Tenant settings have no SOURCE. Overrides are an input to the substrate, not something read from storage. That is the T30-SCHEMA-CONFIG deliverable, and until it exists there is nothing to gate.

**Evidence.**

- `docs/60-research/tenancy/tenant-shared-state-audit-2026-09-15.md`

**Notes.** The plan's T3.3 "not done" paragraph (around L1189) is wrong in two places: it says the alarm-text catalogue "is how alarm text reaches a push notification", but BF-31's measurement shows the catalogue is read once at boot and never reloaded; and it uses the id BF-22, which now names a different defect. A hazard this row carries: plugins capture ctx.moment, ctx.language and ctx.levels at plugin INIT, not per call, so a per-tenant ctx cannot re-point any of them for an already-initialised plugin. That needs settling BEFORE a per-tenant ctx is designed.

### `T43` &mdash; T4.3 - ns-realtime, LISTEN per served tenant

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |

**Blast radius.** A new entrypoint. GT3 confirmed bin/ holds only admin.js and feed.js, so two of D5's four hosted entrypoints do not exist.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release, hosted-only entrypoint

**Gates.**

- `[static]` `test -f externals/work/crm-seam/bin/realtime.js`
  - the entrypoint exists. Fails while bin/ holds only admin.js and feed.js (GT3).
- **NO GATE** &mdash; The design constraint cannot be gated by existence: the connection must NOT go through pgbouncer, because transaction-mode pooling accepts LISTEN and silently delivers nothing ({DB} §10.3). "Accepts and silently delivers nothing" is precisely the shape a naive test passes. The gate has to assert a delivered notification on a direct connection AND assert non-delivery through the pooler as its control.
- **NO GATE** &mdash; Reconnect storms and UNLISTEN churn are the interesting realtime case and are not covered anywhere (plan §7).

**Evidence.**

- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`

### `T44` &mdash; T4.4 - ns-evaluator, the per-tenant evaluation loop

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SAFETY - this is the loop that decides whether a tenant's alarm fires |
| blocks on | `T30-WIRING` |

**Blast radius.** A new entrypoint, hash-partitioned by tenant for per-tenant ordering of ack state. §7b sized the slice: 32.7 KB and 1.94 ms per tenant per evaluation, against 852 KB and 27.5 ms for the whole of ddata, emitting the IDENTICAL alarm.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release, hosted-only entrypoint

**Gates.**

- `[static]` `test -f externals/work/crm-seam/bin/evaluator.js`
  - the entrypoint exists. Fails while it does not.
- **NO GATE** &mdash; §7b names three things the loop must not get wrong, none of which an existence check touches: `treatments` can WITHHOLD an alarm (treatmentnotify.js:64-75 snoozes every URGENT for 10 min after any treatment), `profiles` can withhold one via boluswizardpreview.highSnoozedByIOB, and only the NEWEST devicestatus document is needed despite it being the largest field. A loop that drops a withholding path fires alarms that should not fire.
- **NO GATE** &mdash; Residency tiering is NOT a prerequisite - §7b settled that - so an evaluator built around a resident per-tenant ddata would be building the expensive version of a cheap problem. Nothing prevents someone doing that; it is a design note with no gate.

**Evidence.**

- `docs/60-research/tenancy/ns-evaluator-spike-2026-09-15.md`
- `docs/60-research/tenancy/alarm-critical-slice-2026-09-15.md`

**Notes.** Ack state is already durable (T4.4a). What remains is the loop itself. This is §7a item 2.

### `A7A-3` &mdash; §7a item 3 - a per-tenant error boundary

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SAFETY |
| blocks on | `T44` |

**Blast radius.** serverInit / initRequests / process are unguarded.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; Not started. The gate: three tenants, the middle one throwing, and the THIRD tenant's alarm still arrives. Without the boundary, in a plain loop one tenant throwing means every later tenant is never evaluated. The control that makes the test non-vacuous is a run with no thrower where all three arrive, because a test where nobody's alarm arrives also "passes" a badly written assertion.

**Evidence.**

- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** Named by the T4.4 spike.

### `A7A-4` &mdash; §7a item 4 - a health signal for a silent per-tenant outage

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SAFETY |
| blocks on | `T44` |

**Blast radius.** the per-plugin try/catch in the plugin tier.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; Not started. The defect shape is that the per-plugin try/catch turns bad data into an alarm OUTAGE nobody is told about - so the gate is "feed one tenant data that makes a plugin throw, and assert a health signal changes", with a control tenant on good data whose signal does not. An outage nobody is told about is the exact failure a presence check cannot see.

**Evidence.**

- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`

### `A7A-7` &mdash; §7a item 7 - the clock question

| | |
|---|---|
| state (claimed) | `unsettled` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SAFETY - snooze is measured in DATA time, ack in WALL time |

**Blast radius.** sbx.time is hardcoded Date.now(); lastEntry drops entries ahead of it.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; Unsettled by design. T4.4a chose wall time for ack; the rest is open. A batching or replaying evaluator cannot own its clock today, and until someone decides whether it may, there is nothing to test. Recorded as unsettled rather than not-started so nobody builds against undecided semantics.

**Evidence.**

- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** DECIDED 2026-09-23 (maintainer) - the maintainer owns this question. Answers already given with BF-41: snooze runs on the wall clock, and an evaluator may own its clock, but never for live alarms. Still unsettled until the maintainer writes up the rest.

### `A7A-GATE` &mdash; The alarms-on gate itself - nothing here may be marked done by inference

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SAFETY - the most safety-relevant line in the execution plan |
| blocks on | `T44`, `A7A-3`, `A7A-4`, `A7A-7` |

**Blast radius.** The decision to turn alarms back on under TENANCY_MODE=multi. Alarms are OFF under multi by design - T3.5 withholds emissions outside tenant scope. Failing closed is right; staying closed indefinitely is not.

**What an operator sees.** On a hosted multi-tenant Nightscout (one server shared by many people), alarms are switched off on purpose until this work is finished. A self-hosted Nightscout that serves one person or family is not affected. Do not rely on a hosted deployment for alarms until this says otherwise. This is not medical advice; talk to your care team about what you rely on alarms for.

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; The plan's own wording is the gate: "Alarms go back on when a test shows tenant A's alarm reaching A and not B, through the real producer path, with a snooze that survives a restart and a process change - not when the last row above is edited." That test does not exist. It is a no-gate rather than a to-do because a to-do that gets ticked is exactly the failure this sentence forbids.
- **NO GATE** &mdash; §7a's tally (re-derived by GT3): the plan reads 3-of-7 done; the accurate count is 1. Item 1 (durable ack/snooze) is done with two control arms. Item 6 says of itself that it "does not make per-tenant arming trustworthy". Item 5 (BF-31) was discharged by being found misfiled - its own row text says it is a shared-state item, not an alarm-text one. So: 1 complete, 1 partial, 1 misfiled, 4 open.

**Evidence.**

- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`
- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`

### `SEAM-REFRESH` &mdash; Refresh the seam chain onto a moved modernization branch

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@b1bdaca0` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |

**Blast radius.** 16 seam branches. GT1 measured the chain as LINEAR - all 15 others are ancestors of seam/t1-2-storage-interface (81a1f6ce), and that still holds. The base moved on 2026-09-21: dev was merged into chore/nightscout-modernization as e3b22034 ("Merge dev into modernization and reconcile regression coverage"), 0a4109f6..b1bdaca0, 68 commits. Measured 2026-09-22 against origin/chore/nightscout-modernization b1bdaca0: the seam is 68 behind its base and 50 ahead (`git rev-list --left-right --count origin/chore/nightscout- modernization...seam/t1-2-storage-interface`), and the trial-merge has 19 conflicting paths. Three are add/add supersessions rather than real conflicts: lib/server/query-operator-allowlist.js, lib/api/shared/query-error.js and tests/api-v1-operator-allowlist.test.js exist on BOTH sides because BF-04 was extracted out of the seam onto bf/operators and merged to dev via #8743, while the seam kept its own copy. Upstream's version wins on all three; BF-04's register detail prices that as the seam owing a $type node to its AST. The other sixteen are content conflicts across the v1 API and server storage modules - lib/api/{activity,entries,profile}/index.js, lib/server/{activity,ag gregate,devicestatus,entries,food,profile,query,treatments}.js, lib/authorization/storage.js, both swagger files, and two test files - and those are the actual cost.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release rebase mechanics

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/chore/nightscout-modernization seam/t1-2-storage-interface`
  - the seam tip has not fallen behind its base. Red since 2026-09-21, when dev was merged into the modernization branch directly (e3b22034), outside any release-train step.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/chore/nightscout-modernization seam/t1-2-storage-interface >/dev/null`
  - the seam trial-merges into its base cleanly. Red since 2026-09-21 - 19 conflicting paths, enumerated in blast_radius.
- **NO GATE** &mdash; What the 19 conflicts cost to resolve is unmeasured: the conflict COUNT is measured, the resolution is not, and RT-REBASE shows that conflict counts grow quickly while nobody re-runs them. Three of the nineteen are known supersessions (upstream's BF-04 extraction wins); the remaining sixteen touch the v1 API and storage modules the seam exists to replace, so some may be "delete ours, take theirs" and some may be genuine re-work. None has been opened. Also ungated: whether the seam should rebase onto the modernization branch at all, rather than onto dev. The seam was cut against modernization because that was where the work was; dev has since taken the thirteen backfix PRs, including the allowlist the seam duplicates, and cut 5 is 9 behind dev and 498 ahead (measured 2026-09-22, `git rev-list --left-right --count origin/dev...origin/chore/nightscout-modernization`). That is a re-basing decision, not a merge-conflict question.

**Evidence.**

- `docs/60-research/remedial/gt1-branch-inventory-2026-09-15.md`

**Notes.** GT1 also found that crm-pool, crm-tenant and crm-write are three separate worktrees all detached at the SAME commit 239f8c25, a mid-chain commit of seam/t1-2-storage-interface, with no branch of their own. Rule 5 - do not repoint a worktree you did not create - so they are recorded, not touched.

### `BFQ-66` &mdash; BF-66 - the deployment's own tokens fail its own tenant check

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `crm-seam` |
| base | `crm-seam@81a1f6ce` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer, as part of T3.0 - not separately |
| ships to operators today | no (pre-release) |
| register | `BF-66` |
| blocks on | `T30-WIRING`, `T31-REM`, `SEAM-REFRESH` |

**Blast radius.** lib/authorization/index.js:289, the only JWT minting path besides enclave.js:58. One payload.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** Pre-release, in an unmerged seam branch, under a mode no released artefact enables. It moves no surface anyone can reach.

**Gates.**

- **NO GATE** &mdash; The reproduction is recorded in the register - both modules executed on crm-seam 81a1f6ce with the exact minted payload, tenantClaim returning null and credentialRefusal returning "This credential does not name a Nightscout site", with a control token carrying a tenant field proceeding. It is not a queue gate because it would pin this item to one seam commit, and SEAM-REFRESH exists because that branch has to move. Re-point the gate after the refresh, not before.
- **NO GATE** &mdash; It fails safe - refusing rather than admitting - which is why it went unnoticed and why the severity is medium. Nothing gates "fails safe rather than open", and treating a safe failure as equivalent to an unsafe one is how a real refusal gets downgraded.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** The fix belongs to T3.0 and should not be taken separately. The task that introduces the per-tenant signing key (D14) is the task that chooses the payload; fixing this first would mean choosing the tenant claim twice. Filed as its own item rather than folded into T30-WIRING so the reproduced defect keeps an id a reviewer can find.

### `BFQ-CAP02` &mdash; CAP-02 - no importer, and no Mongo to PostgreSQL loader

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `crm-seam` |
| base | `crm-seam@81a1f6ce` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer |
| ships to operators today | no (pre-release) |
| register | `CAP-02` |
| blocks on | `T30-SCHEMA-CRED`, `T30-SCHEMA-CONFIG` |

**Blast radius.** One loader, plus whatever decides the BSON to jsonb transform. The outbound half already exists - exportTenant is a streaming server-side cursor in one repeatable-read transaction that declares its covered-table list before any row.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** a capability that does not exist yet; no surface moves

**Gates.**

- **NO GATE** &mdash; There is nothing to measure: the thing is absent. The first gate is the loader's own round-trip test - export a known corpus, load it, and assert the loaded rows equal the exported ones - with a control that plants a value the transform is known to mangle so a green result is known to distinguish. That test cannot exist before the loader does.
- **NO GATE** &mdash; The transform itself is unsettled, which is what would make a naive loader silently lossy. scalarizeDoc turns Long, Decimal128, Binary, Int32 and Timestamp into jsonb OBJECTS, which the generated columns then read as SQL NULL with no error. Measured and recorded in the hosted migration plan §4.3; nothing gates it because no loader calls it yet.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/40-migration/mongodb-to-postgres-hosted-2026-09-15.md`

**Notes.** §1c, so it is neither §1 nor §1b. ships_to_operators_today is false because an operator on today's release sees nothing - the capability is needed by hosted- tenant onboarding, which does not exist yet. The execution plan lists per- tenant EXPORT under "Endpoints (proposed, to be argued)" although it is implemented, and says nothing about import, so the asymmetry is invisible to a reader of either document. Prior art for the rehearsal shape, and not the missing piece - tools/rehearse-database-upgrade.py:76.

---

## Document-truth sweeps

`parcel: docs-truth` &mdash; 9 items

Rule 6 work. Agents read SECTIONS, not documents, so a fact stated twice and
differently is a live hazard, not untidiness. GT1/GT3/GT4 enumerated these.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `DOC-SEQUENCING` | phase0-pr-sequencing contradicts itself on the branch count | `not-started` | `main` | n/a | 1 run + 1 no-gate |
| `DOC-PLAN` | The execution plan's tallies and line references are stale | `not-started` | `main` | n/a | 0 run + 1 no-gate |
| `DOC-REGISTER` | The register's own header undercounts and its suppression tally is stale | `not-started` | `main` | n/a | 1 run + 4 no-gate |
| `DOC-EXPOSURE` | Say in the register that `fixed` does not mean an operator is safe | `gate-not-met` | `main` | n/a | 1 run + 2 no-gate |
| `DOC-MEMORY` | The two memory files disagree with each other, and one cites a file that does not exist | `not-started` | `main` | n/a | 2 run + 1 no-gate |
| `DOC-LAYOUT` | The repository-layout preamble names the wrong shipping checkout | `not-started` | `main` | n/a | 1 run + 1 no-gate |
| `DOC-TESTSCRIPTS` | 52 test files match neither local test script | `not-started` | `origin/dev` | n/a | 1 run + 1 no-gate |
| `DOC-VIEWS` | A reviewer-facing surface over the queue: three overview pages and a packet per PR | `done` | `main` | n/a | 2 run + 3 no-gate |
| `DOC-LINKS` | Every path the programme's documents and tooling cite must resolve | `done` | `main` | n/a | 1 run + 2 no-gate |

### `DOC-SEQUENCING` &mdash; phase0-pr-sequencing contradicts itself on the branch count

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@75c38a17` |
| worktree | `.` |
| semver | `n/a` |
| review | whoever edits it next. The document is edited often by other sessions; re-read it immediately before editing. |

**Blast radius.** docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation

**Gates.**

- `[static]` `node tools/queue/gates/doc-branch-count.js`
  - FAILS while the document states more than one branch count. Found by GT1 and GT3 (2026-09-15): "five branches" in the title and at L3, "the seven Phase 0 branches", "all six other branches", "all seven" twice - while its own tables list A-I, which is nine, plus the unlettered bf/connect-pin, which is ten.
- **NO GATE** &mdash; The trial-merge matrix at L71-79 covers only 6 pairs among bf/reads, bf/coercion, bf/cache, bf/auth and bf/alarms. It predates bf/food, bf/merge, bf/parms and bf/connect-pin, whose rows claim "clean against all six" / "all seven" in prose that the matrix does not support. Extending the matrix is work, not a sweep.

**Evidence.**

- `docs/60-research/remedial/gt1-branch-inventory-2026-09-15.md`
- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`

**Notes.** Also at L388: the document says master pins nightscout-connect as "^0.0.12", an npm semver range. GT4 measured master as pinning the v0.0.13 tag tarball; there is no npm-range pin for the connector anywhere in the tree. The ^0.2.12 on master is share2nightscout-bridge, a different package. L165 lists bf/parms' commits in the wrong order.

### `DOC-PLAN` &mdash; The execution plan's tallies and line references are stale

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@75c38a17` |
| worktree | `.` |
| semver | `n/a` |
| review | whoever edits it next |

**Blast radius.** docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md at L7, L8, L351, L1189, and the T3.0 amendment table.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation

**Gates.**

- **NO GATE** &mdash; A prose tally cannot be gated without a machine-readable source for the number. This queue is that source for the items it covers, so the fix is to make the plan cite queue/QUEUE.md rather than restate counts. Until it does, no gate.

**Evidence.**

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`

**Notes.** GT3's list (2026-09-15). L7 says "Phase 0 is done and is not the blocker any more", contradicted by its own L529 (T0.1 "In flight") and L541 (T0.3 "GATE NOT MET"). L8's tallies: "13 register entries closed" (actual 26 closed or partly), "3 new defects found" (actual 8, BF-32..BF-39), "4 register entries corrected as wrong" (at least 7). L351 and L1189 use "BF-22" for what is now BF-31, and L1189 still carries the claim BF-31's measurement refuted. The T3.0 amendment table cites tenant-context.js:137, which is a comment. Line numbers are as of GT3's reading; re-locate before editing.

### `DOC-REGISTER` &mdash; The register's own header undercounts and its suppression tally is stale

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@75c38a17` |
| worktree | `.` |
| semver | `n/a` |
| review | whoever edits it next. The register is edited often; re-read it immediately before editing. |

**Blast radius.** docs/30-design/remedial/nightscout-backfix-register.md at L26 and L41-53.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation

**Gates.**

- `[static]` `node tools/queue/gates/register-rows-vs-details.js`
  - Every table row id has a detail section and vice versa. Passes as of 2026-09-16 at 70 rows / 70 sections. When it fails, read its output for the id it names rather than assuming a previously missing section.
- **NO GATE** &mdash; The header's "Five entries have now had a claim fail on contact" is at least seven - the §1 table itself flags two the header omits, BF-08 and BF-30. The same undercount is copied into plan L8 and sequencing L526. Counting "claims that failed on contact" needs a marked field per entry, which the register does not have. Adding one is the real fix.
- **NO GATE** &mdash; The suppression-audit tally at L48-53 is stale. BF-39 is a third defect from the no-useless-escape category, on BF-37's own site. Correct: five defects, 40 of 45, row = 2 sites / 3 defects. L41's "from BF-35, BF-36, BF-37 and BF-38. All four" should be five.
- **NO GATE** &mdash; Three entries contradict themselves on provenance - the one property the header says must be marked. BF-17, BF-30 and BF-31 each carry a prepended "reproduced against a running instance" block while their original bodies still read "*Not reproduced against a live instance.*"
- **NO GATE** &mdash; Two line references no longer resolve: BF-05's unfixed sibling console.log('Loading', opts) is at lib/authorization/storage.js:113, not :84; BF-09's block is websocket.js:538-566, not 535-568 (the seam interface document carries the same stale range).

**Evidence.**

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`

**Notes.** BF-14's detail section contradicts itself, which makes a naive grep read it as open: L587 re-grades it to high and withdraws "it returns no wrong data", then L594-600 restates that sentence in the present tense.

### `DOC-EXPOSURE` &mdash; Say in the register that `fixed` does not mean an operator is safe

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@9ddad0cc` |
| worktree | `.` |
| semver | `n/a` |
| review | maintainer - this is the correction that changes how the whole register reads |

**Blast radius.** The register's status legend, and every document that restates operator exposure - the plan, the sequencing document and memory/multitenancy-target- decision.md. The legend now defines three distinct values (`fixed` on an unmerged branch, `merged` in dev and unreleased, `landed` - the register's word for released - in a release an operator can install) and says that neither of the first two means an operator is safe. Operator exposure as computed 2026-09-21 by the coverage gate's parser (tools/queue/gates/register- queue-coverage.js): 55 §1 defects reach every self-hoster on 15.0.8 - 23 open, 27 merged, 1 partly merged, 4 fixed. Re-derive from the register rather than quoting this line.

**What an operator sees.** A defect marked "fixed" or "merged" in the project's register has been repaired in code that has not been released yet. If you are running today's Nightscout (15.0.8), it is still there.

**Why `n/a`.** documentation

**Gates.**

- `[static]` `node tools/queue/gates/register-exposure-legend.js`
  - Parses the status column of §1/§1b/§1c, reports how many defects are live for an operator today, and checks whether the legend says so. FAILS, correctly, on the counting arm (see the next marker). It replaced a `grep -q 'landed'` gate that passed vacuously - its only hits were the legend line and two unrelated prose uses of the word.
- **NO GATE** &mdash; The correction itself cannot be gated: no entry has status `landed`, so the status column tracks work done, not operator exposure. A reader taking the open count as "the defects still shipping" mis-sizes the release train. Every §1 defect, open, fixed or merged, is present for every self-hoster on 15.0.8.
- **NO GATE** &mdash; The gate above measures two things and only one is this item's, which is why the item is gate-not-met and not done. Its prose arm - does the legend say that a repaired entry is still present on today's release - is green since 2026-09-21. Its counting arm is red because nothing has status `landed`, which is a fact about the world, not about this document: it goes green when 15.0.9 is released, which is RT-0's item. Do not read the red as the documentation being unwritten, and do not split the gate to make this item green - the point of the correction is that the document and the exposure are different claims.

**Evidence.**

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`

**Notes.** GT3's largest correction, and the reason this queue carries `ships_to_operators_today` as a field rather than inferring exposure from `state`.

### `DOC-MEMORY` &mdash; The two memory files disagree with each other, and one cites a file that does not exist

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@75c38a17` |
| worktree | `.` |
| semver | `n/a` |
| review | maintainer - whichever file an agent loads becomes true for it |

**Blast radius.** memory/multitenancy-target-decision.md:67-68 and memory/release-train-and- work-queue.md:13-14.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation

**Gates.**

- `[static]` `python3 tools/queue/emit.py --check`
  - memory/release-train-and-work-queue.md declares queue/work-queue.yaml the source of truth and queue/QUEUE.md generated from it. This asserts the checkable half of that claim: the generated view is not stale with respect to the source. (A `test -f queue/work-queue.yaml` gate would be vacuous by construction - status.py loads the manifest before running any gate, so a missing file aborts the runner and the gate could never be observed failing.)
- `[static]` `grep -q '^queue-status:' Makefile`
  - The same memory names `make queue-status` as the gate runner; this asserts the Makefile target exists (GT3 found it absent on 2026-09-15).
- **NO GATE** &mdash; The memory directory lives outside this repository, so no check here can reach it. Reconciled 2026-09-16: release-train-and-work-queue.md said "only three open register entries reach an operator on today's release", which counts open work, not exposure - the same correction DOC-EXPOSURE owns (every §1 defect not released reaches an operator; the current figure lives in the register). Both memory files' citations of the register and the execution plan were updated to the post-2026-09-16 paths.

**Evidence.**

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`

**Notes.** memory/release-train-and-work-queue.md also declares queue/QUEUE.md generated, which this queue makes true.

### `DOC-LAYOUT` &mdash; The repository-layout preamble names the wrong shipping checkout

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@75c38a17` |
| worktree | `.` |
| semver | `n/a` |
| review | maintainer - it has already misdirected at least one agent session |

**Blast radius.** Every brief and preamble that says externals/cgm-remote-monitor is the pristine shipping checkout at detached HEAD 6893781f.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation

**Gates.**

- `[static]` `node tools/queue/gates/shipping-checkout-identity.js`
  - FAILS if externals/cgm-remote-monitor is presented as this programme's shipping checkout. GT1 measured it at 6893781f, a 2014-11-06 commit ("Merge pull request #207 from nightscout/release/0.5.0") on a different fork. It holds none of this programme's work. The shipping checkout is externals/cgm-remote-monitor-official.
- **NO GATE** &mdash; Briefs are composed outside this repository, so no gate here reaches them. The only durable fix is to correct the source the briefs are generated from, which is not a file in this tree.

**Evidence.**

- `docs/60-research/remedial/gt1-branch-inventory-2026-09-15.md`

**Notes.** The crm-* worktrees belong to externals/cgm-remote-monitor-official. `git -C externals/cgm-remote-monitor worktree list` returns exactly one entry: itself.

### `DOC-TESTSCRIPTS` &mdash; 52 test files match neither local test script

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `origin/dev` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer |
| register | `BF-53` |

**Blast radius.** package.json test:unit and test:integration brace lists. Measured on a8888f0d: 159 files in tests/*.test.js; test:unit resolves to 44, test:integration to 89, union 107, leaving 52 matched by neither. The gate below re-measures the count.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** developer tooling

**Gates.**

- `[static]` `node tools/queue/gates/test-script-coverage.js`
  - FAILS while any tests/*.test.js matches neither brace list. GT1's finding as a standing measurement. The four files that are the evidence for the BF-35/36/37 batch are among the 52, so an agent told "run test:unit" would never execute BF-35's test, and bf/food's clean 361-passing run is not evidence that BF-35's fix works.
- **NO GATE** &mdash; CI is not blind to this - main.yml runs test-ci, which is ./tests/*.test.js, all 187 on origin/dev ddd9b600 (2026-09-23). The gap is in the local scripts only, so the fix is a convenience fix; it matters because agents and contributors read the local scripts as the suite. Nothing can gate "a human believed the wrong thing".

**Evidence.**

- `docs/60-research/remedial/gt1-branch-inventory-2026-09-15.md`

**Notes.** test:unit is not database-free: without MongoDB it fails 6 tests (verifyauth x4, API_SECRET x2) on pristine dev. Every gate in this manifest that invokes test:unit is therefore filed as `integration`.

### `DOC-VIEWS` &mdash; A reviewer-facing surface over the queue: three overview pages and a packet per PR

| | |
|---|---|
| state (claimed) | `done` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@1a10007b` |
| worktree | `.` |
| semver | `n/a` |
| review | maintainer, and then ideally a person who has never seen this repository - the only way to find out whether REVIEWER-ONBOARDING.md works, and this queue cannot gate it. The reading path claims about an hour. |

**Blast radius.** docs/00-overview/{PROGRAMME-STATUS,NEEDS-A-HUMAN,REVIEWER-ONBOARDING}.md, reports/reviewer-packets/ (one generated packet per item awaiting review, plus a README), tools/queue/emit_views.py, tools/queue/emit_packets.py, and four Makefile targets. No shipping code.

**What an operator sees.** Nothing changes in Nightscout itself. This is a set of pages explaining what the project is working on and what is still waiting on a person.

**Why `n/a`.** documentation and repository tooling

**Gates.**

- `[static]` `python3 tools/queue/emit_views.py --check`
  - FAILS when a generated block inside docs/00-overview is stale with respect to the manifest. The overview pages are hybrid: hand-written prose around generated blocks. Ablated 2026-09-16: editing one row of the horizons table inside the fence is reported stale and queue-check goes red.
- `[static]` `python3 tools/queue/emit_packets.py --check`
  - FAILS when a reviewer packet is stale or orphaned. Both ablated 2026-09-16 - a changed semver row in P0-A's packet, and a spare file added to the directory. Orphaned matters because a packet left behind for an item that no longer wants a reviewer points a volunteer at finished work.
- **NO GATE** &mdash; Nothing here measures whether the prose is true. The generated blocks are checked against the manifest; the hand-written text around them - which horizon matters, what a new reviewer should read first, that review capacity rather than engineering is the binding constraint - is a dated human claim, and it is where DOC-PLAN and DOC-SEQUENCING's class of defect can recur.
- **NO GATE** &mdash; The operator-exposure figure in PROGRAMME-STATUS.md (55 §1 defects as of 2026-09-21) is prose, not a generated block. It was computed by the coverage gate's register parser, but nothing re-derives it on the page, so it goes stale silently when register statuses change; whoever edits the register's §1 statuses must re-derive it.
- **NO GATE** &mdash; Whether REVIEWER-ONBOARDING.md actually onboards anybody is not measurable from inside the repository, and it is the only question about this item that matters. The evidence would be a first-time reviewer completing a packet.

**Evidence.**

- `docs/00-overview/PROGRAMME-STATUS.md`
- `docs/00-overview/NEEDS-A-HUMAN.md`
- `docs/00-overview/REVIEWER-ONBOARDING.md`
- `reports/reviewer-packets/README.md`

**Notes.** DECIDED 2026-09-23 (maintainer) - done. Built 2026-09-16 on the maintainer's instruction: a view of progress and a place where reviewers and teammates can collaborate. Hybrid generation for the overview pages, full generation for the packets, audience the maintainer plus reviewers being recruited. The pages are built around the reviewer-load table (generated in PROGRAMME-STATUS.md): most items route to the maintainer, and the SECURITY and SAFETY rows name a kind of reviewer with no individual attached.

### `DOC-LINKS` &mdash; Every path the programme's documents and tooling cite must resolve

| | |
|---|---|
| state (claimed) | `done` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@6574b28d` |
| worktree | `.` |
| semver | `n/a` |
| review | maintainer. The gate carries four exemption classes - FROZEN, NOT_REAL, PLANNED and QUOTED - and each is a place where a future defect could be parked with a plausible reason. The register's suppression audit found 5 real defects behind 45 suppressions, so read the exemption list, not just the exit code. |

**Blast radius.** tools/queue/gates/doc-links.js (new), and the 55 September documents moved into programme subdirectories on 2026-09-16 with 280 links and 212 repo-root paths rewritten.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation and repository tooling

**Gates.**

- `[static]` `node tools/queue/gates/doc-links.js`
  - FAILS when any path cited by the groomed programme material or the live queue tooling does not resolve (852 references across 116 files on 2026-09-16). Three detection passes: markdown links (in every scoped text file, not only .md, because one was embedded in a Python edit script), repo-root-absolute paths (which catches a backticked citation the link regex cannot see), and piecewise path.join(REPO_ROOT, 'docs', ...) in gate sources - the class that broke four gates, three of which were already expected to fail, so the ENOENT was invisible inside an intended red.
- **NO GATE** &mdash; The legacy tree is out of scope on purpose. The Jan-Apr research campaign, docs/backlogs/archive/ and specs/ carry 109 dead links that predate this work, and the maintainer's instruction (2026-09-16) was to groom the recent material and leave the older material alone. Gating them would make this gate permanently red for reasons nobody intends to fix. Bringing them into scope is work, not a sweep.
- **NO GATE** &mdash; 25 root-path references name a subtree this repository does not have: they are cgm-remote-monitor's own docs/ - docs/meta/, docs/INDEX.md, docs/proposals/ present on origin/dev and origin/master; docs/runtime-upgrade.md present only on cut 1's branch. Telling the two repositories' docs/ trees apart properly needs a per-reference repository marker, which the documents do not carry.

**Evidence.**

- `docs/60-research/remedial/e3-gate-vacuity-audit-2026-09-15.md`

**Notes.** DECIDED 2026-09-23 (maintainer) - done. Non-vacuity, run 2026-09-16: three ablations, one per detection pass, each confirmed to land before its result was read. A markdown link repointed to a nonexistent name - caught. A repo- root path in this manifest reverted to its pre-move spelling - caught. doc- branch-count.js's path.join reverted to the pre-move segments - caught. Empty- root negative control via QUEUE_GATE_ROOT exits 1 rather than passing on an empty tree.

---

## Backfix 2 - folded into 15.0.9

`parcel: backfix2` &mdash; 2 items

Decided 2026-09-23 (maintainer) to ship inside 15.0.9 rather than after it;
bf2/backports is #8751, and bf2/ops and bf2/auth-hardening (with the subject-
edit fix folded in as its last commit) open next. Plan and flag rule:
docs/30-design/remedial/backfix-2-plan-2026-09-22.md. Units are grouped by the
reviewer they need and integrated on a scratch rc/backfix-2 branch pinned to
dev by SHA, evaluating between each merge.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `BF2-AUTH` | bf2/auth-hardening - bf/auth + bf/throttle + the client-ip.js backport behind TRUST_PROXY | `in-flight-upstream` | `bf2/auth-hardening` | major | 5 run |
| `BF2-OPS` | bf2/ops - BF-10 compose ulimits, FU-RESIDUALS 3 and 7, BF-63 renderer | `merged-upstream` | `bf2/ops` | patch | 2 run + 1 no-gate |

### `BF2-AUTH` &mdash; bf2/auth-hardening - bf/auth + bf/throttle + the client-ip.js backport behind TRUST_PROXY

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf2/auth-hardening` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/work/crm-bf2-auth` |
| semver | `major` |
| review | SECURITY - the reviewer P0-C already names; none assigned. |
| register | `BF-17`, `BF-30` |

**Blast radius.** Tip 29e6430e on origin/dev 74fc6619. lib/authorization/{index,delaylist, storage,endpoints}.js; lib/server/{client-ip,env,app,websocket}.js; lib/api/{index,status}.js; lib/api3/{index,security,alarmSocket, storageSocket}.js; package.json and lock (proxy-addr declared, forwarded-for kept); README and docs/proposals/trusted-proxy-migration.md. Against chore/nightscout-modernization b1bdaca0 it conflicts in 10 paths, two of them pre-existing (bootevent.js from dev, storage.js from bf/auth).

**What an operator sees.** Not released. Combines the two login-security fixes already described under P0-C and P0-J with a setting that lets you tell Nightscout which proxy in front of it to trust. If you change nothing, Nightscout behaves as it does today; the stronger protection against password guessing applies only once you name your trusted proxy.

**Why `major`.** Inherits P0-C's major (the BF-47 allow-list), unless the maintainer's BF-47 decision puts that behind a compatibility flag, which would make this minor (a new setting, today's behaviour by default).

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/auth bf2/auth-hardening && git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/throttle bf2/auth-hardening`
  - Contains both source branches by ancestry, not re-implementation.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf2/auth-hardening >/dev/null`
  - Merges into origin/dev with no conflict.
- `[static]` `git -C externals/cgm-remote-monitor-official cat-file -e bf2/auth-hardening:lib/server/client-ip.js`
  - The client-address module is present. Its default being today's behaviour is asserted by the branch's own tests, not here.
- `[unit]` `cd externals/work/crm-bf2-auth && n exec 20.20.0 npx mocha --timeout 10000 --exit tests/client-ip.test.js`
  - 48 cases, no database. Pins dev's client address, HTTPS detection and hostname with TRUST_PROXY unset (0, 1 and 2 hops, history dependence). Control, re-run 2026-09-22 - restoring 395f3207's client-ip.js fails exactly 7; flipping the unset default to trust nothing fails 23.
- `[integration]` `cd externals/work/crm-bf2-auth && TEST=authdelay npm run test-single`
  - 19 cases - default keying, the documented default gap, throttling under a configured TRUST_PROXY, and the boot message's claims. Flipping the unset default fails 5; bypassing TRUST_PROXY in authorization/index.js fails 4.

**Evidence.**

- `docs/30-design/remedial/backfix-2-plan-2026-09-22.md`
- `docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md`

**Notes.** 2026-09-23 - #8754's head is ef3404fd: 0ca46d92, 8211f8e2 and ef3404fd merge dev (up to ddd9b600) into 0a74ef4e. Measured: `git diff origin/dev ef3404fd` changes the same 21 files with the same added and removed lines as 0a74ef4e's own diff, so the PR's content is unchanged. The combined re-run on this head is RT-0's. 2026-09-23 - #8754's head is 0a74ef4e (pushed by the maintainer, description updated): the API v3 trust proxy line is dropped as inert, like v1's in 22953b77; suite 2481/0/3 on Node 20 and 22. Correction to 0a74ef4e's commit message (pushed, so not rewritten; a PR comment is drafted): lib/api3/security.js:34 DOES read app.get('trust proxy fn') for the v3 token throttle key. -1f measured the inherited fn === the parent's for unset, false, 10.0.0.0/8, 1 and true, with the legacy marker surviving and the resolved IP matching, so the trim is still inert in production. FOLLOW-UP - tests/fixtures/api3/instance.js has no parent trust proxy, so no test covers the v3 throttle key under the production default. 2026-09-23 - #8754 head is 22953b77 (pushed): the inert trust proxy line in lib/api/index.js is trimmed (maintainer decision), so that file is identical to dev; suite 2481/0/3 on Node 20 and 22, unchanged from 81623f9b; BACKPORT DIFFERENCE vs 06c83f2f in the commit message. Prepared, not pushed: 0a74ef4e on bf2/auth-hardening-trim- api3 trims the same inert line in lib/api3/index.js (54/54 answers identical, control 30/54 different; 2481/0/3); pushing it makes #8754 head 0a74ef4e. OPENED 2026-09-23 as nightscout/cgm-remote-monitor #8754 (head 7103f657, base dev) - subject-edit folded in as its last commit (maintainer, relayed 2026-09-23); withheld-style description. PUSHED 2026-09-23 - #8754's head is 81623f9b ("TRUST_PROXY accepts a hop count and true, with Express's meaning for each"), checks green; suite 2481/0/3; the withheld description covers hop counts and true. Express's subnet aliases (loopback, linklocal, uniquelocal) are refused on a separate path; accepting them is deferred to a later release (maintainer, 2026-09-23). chore/nightscout-modernization b1bdaca0's lib/server/client-ip.js still refuses hop counts and true, and needs the same change. DESTINATION 15.0.9 (plan section 1a, "backfix 2 scope", 2026-09-23). Evidence - the rc-c integration record, rc/15.0.9-additions-c b9c9828b, 2508/0/3 on every Node and MongoDB pair, break-its on the final tree. Three things for the maintainer from that record. (1) The auth-hardening line in lib/api/index.js (app.set('trust proxy', ...)) is inert - the v1 sub-app inherits trust proxy from lib/server/app.js - so removing it fails nothing, full suite included. (2) The record recommends folding bf2/subject-edit-keeps- fields (BFQ-47) into the auth-hardening PR as its last commit, and leaves the choice to the maintainer. (3) The record leaves the PR-body style (full or withheld) to the maintainer. The PR body as committed at b248bb73 (reports/phase0-pr-bodies/bf2-auth-hardening.md) records both as decided by the maintainer on 2026-09-23 - posted in full, and 7103f657 folded in as the final commit. rc-c contains the connector pin at 338deb7f (0.1.0-dev.1), now superseded by bf/connect-pin-0.1.0 adf5120c (0.1.0-dev.2), so the rc needs a re-merge before it is evidence for the pin. PREPARED 2026-09-22. Commits: merges of bf/auth and bf/throttle; cherry-pick -x of 06c83f2f and 395f3207 (hunks for files absent on dev dropped); 1114228d adapts two cherry-picked tests to bf/throttle's keysFor(); 8b975b41 is a PORT - with TRUST_PROXY unset the address comes from forwarded-for exactly as on dev, because 395f3207's default differs in four cases (BF-88); the trusted path is 395f3207's code unchanged. ONE flag, not two - the throttle keys on data.ip, which now comes from client-ip.js. Suite on Node 20.20.0 - dev 2386/0/3, branch 2462/0/3, +76 exactly. Semver stays major for BF-47; a compat flag for BF-47 (sketched in the PR body) would make it minor. Plan section 3's "PRs open after 15.0.9 is tagged" is superseded by the section 1a decision above. BF-30 is closed only when TRUST_PROXY names a boundary; with the default it remains open, and the branch must say so in its boot message and PR body.

### `BF2-OPS` &mdash; bf2/ops - BF-10 compose ulimits, FU-RESIDUALS 3 and 7, BF-63 renderer

| | |
|---|---|
| state (claimed) | `merged-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf2/ops` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/work/crm-bf2-ops` |
| semver | `patch` |
| review | maintainer |
| register | `BF-10`, `BF-63` |

**Blast radius.** docker-compose.yml, lib/plugins/index.js, lib/api/alexa/index.js, lib/server/booterror.js.

**What an operator sees.** Not released. Three small repairs: the bundled Docker setup stops the database crashing for lack of open files, an unrecognised Alexa request gets an answer instead of hanging, and the page that explains a start-up error stops failing for one kind of error.

**Why `patch`.** bug fixes and a shipped configuration file; no declared surface moves

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf2/ops >/dev/null`
  - Merges into origin/dev with no conflict.
- `[static]` `git -C externals/cgm-remote-monitor-official show bf2/ops:docker-compose.yml | grep -q nofile`
  - BF-10 - the compose file raises the open-file limit.
- **NO GATE** &mdash; Follow-ups 3 and 7 and BF-63 keep their existing gates on FU-RESIDUALS and RT-BOOTERROR, which read origin/dev and go green when this merges.

**Evidence.**

- `docs/30-design/remedial/backfix-2-plan-2026-09-22.md`
- `docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md`

**Notes.** MERGED 2026-09-23 into dev (now 4011193e); NOT RELEASED. #8753 as 3a38c6f2. CI and CodeQL green. OPENED 2026-09-23 as nightscout/cgm-remote-monitor #8753 (head e6a50e9a, base dev) - withheld-style description. DESTINATION 15.0.9 (plan section 1a, "backfix 2 scope", 2026-09-23). Evidence - the rc-c integration record, rc/15.0.9-additions-c b9c9828b, 2508/0/3 on every Node and MongoDB pair; this unit's step added +6 and its three break-its are red on the final tree. rc-c carries the superseded connector pin 338deb7f and needs a re- merge (see BF2-AUTH). PREPARED 2026-09-22 - tip e6a50e9a on origin/dev 74fc6619, four commits (03fba725 BF-10, e72ba30d follow-up 3, af8eee45 follow- up 7, e6a50e9a BF-63 renderer guard). Suite Node 20.20.0, mongo 7.0.43 - dev 2386/0/3, branch 2392/0/3, +6 exactly the new tests. Follow-up 4 stays on bf/auth (ce82f0cd) and is not repeated here.

---

*End of generated view. Source: `queue/work-queue.yaml`.*
