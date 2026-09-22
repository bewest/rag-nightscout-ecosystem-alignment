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
- Measured at: 2026-09-22
- Measured against cgm-remote-monitor-official: `74fc6619`
- Measured against nightscout-connect: `8e26786`
- Measured against main_repo_head: `1d97eda4`

One queue spans every programme on purpose, so that a tenancy task colliding with a release train is visible in one place. The `parcel` field does the separating.

## Totals

| | count |
|---|---|
| items | 89 |
| runnable gates | 151 |
| explicit `no-gate:` markers | 141 |

A `no-gate:` marker is not a gap in the bookkeeping; it is the bookkeeping. It records that nobody has yet built a way to measure the property, and it carries the reason. 141 of the 292 gate slots in this queue are in that state.

### Claimed state (NOT a measurement -- run `make queue-status`)

| state | n | ids |
|---|---|---|
| `not-started` | 32 | RT-VERSION, RT-4, BFQ-10, BFQ-21, BFQ-19, BFQ-22, BFQ-23, BFQ-25, BFQ-24, BFQ-26, BFQ-27, BFQ-18, BFQ-20, BFQ-CAP01, T30-SCHEMA-CRED, T30-SCHEMA-CONFIG, T30-ORY-PROOF, T30-WIRING, T43, T44, A7A-3, A7A-4, DOC-SEQUENCING, DOC-PLAN, DOC-REGISTER, DOC-MEMORY, DOC-LAYOUT, DOC-TESTSCRIPTS, BFQ-69, BFQ-MINIMED, BFQ-CAP02, FU-HYGIENE |
| `gate-not-met` | 15 | P0-C, P0-J, RT-REBASE, SEAM-REFRESH, DOC-EXPOSURE, BFQ-71, BFQ-41, BFQ-CONNECTOR, BFQ-46, BFQ-ENV, BFQ-67, RT-CONNECT-PIN-CUTS, RT-NODE-FLOOR-TESTED, RT-BOOTERROR, FU-RESIDUALS |
| `ready-to-push` | 4 | P0-C-REMEDIATE, T30-AUTH, DOC-VIEWS, DOC-LINKS |
| `blocked` | 12 | P0-PIN, P0-LOCK, RT-1, RT-2, RT-3, RT-5, T31-REM, T32-REM, T33-REM, A7A-GATE, BFQ-66, FU-LIMIT |
| `in-flight-upstream` | 1 | P0-F |
| `merged-upstream` | 13 | P0-A, P0-B, P0-D, P0-E, P0-G, P0-H, P0-I, P0-K, P0-T01, BFQ-04, BFQ-40, ADV-RETRO, ADV-ALARM |
| `needs-decision` | 9 | P0-TAG, RT-D3, RT-0, T30-RESEARCH, BFQ-72, BFQ-47, FU-PRBODIES, ADV-XSS-META, ADV-CONFIG |
| `unsettled` | 3 | BFQ-09, A7A-7, BFQ-52 |

### Reaches an operator on today's release

The register's `§1` vs `§1b` distinction, carried as `ships_to_operators_today`. Preserving it is the only thing that makes the register mean anything.

- **BFQ-09** BF-09 - socket dedup truthiness skips a falsy value
- **BFQ-10** BF-10 - mongod fatal-asserts at Docker's default nofile=1024
- **BFQ-04** BF-04 - the v1 operator allowlist - superseded by P0-K
- **BFQ-CAP01** CAP-01 - Nightscout cannot be served from a sub-path
- **BFQ-69** BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing
- **BFQ-71** BF-71 - any dateString key drops the default date window, and the window is not a control
- **BFQ-72** BF-72 - an unauthenticated $regex can spend minutes of database CPU
- **BFQ-40** BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion
- **BFQ-41** BF-41 - a reading dated ahead of the clock silences the stale-data alarm
- **BFQ-CONNECTOR** BF-42, BF-43 - master pins the leaking connector, with a violated axios override
- **BFQ-MINIMED** BF-44, BF-45, BF-85 - MiniMed ingestion divergences and the CareLink zero reading
- **BFQ-46** BF-46 - eleven API v3 variables bypass env.js, one family deletes data
- **BFQ-47** BF-47 - an ordinary subject edit destroys stored fields, on today's release
- **BFQ-ENV** BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies
- **BFQ-52** BF-52 - the age plugins can only ask for their urgent alarm in one window
- **BFQ-67** BF-67, BF-86 - alarm thresholds quietly changed, or quietly kept when they cannot work
- **ADV-RETRO** GHSA-gjhc - loadRetro serves devicestatus to any socket (BF-79)
- **ADV-ALARM** GHSA-8849 - /alarm broadcasts to the whole namespace (BF-75, BF-76)
- **ADV-XSS-META** GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74)
- **ADV-CONFIG** The readable-by-world warning, the careportal role, and the two settings behind both (BF-77, BF-78, BF-81)

---

## Phase 0 backfixes - ships to every existing operator

`parcel: phase0` &mdash; 20 items

Eight of the ten cgm-remote-monitor Phase 0 branches are merged into
origin/dev (PRs #8733 to #8743, 2026-09-17 to 2026-09-20); their items are
`merged-upstream`, meaning in dev and not released. Until RT-0 ships 15.0.9,
no operator carries any of them. Remaining on the cgm-remote-monitor side:
bf/auth (P0-C) and bf/throttle (P0-J), both behind origin/dev and trial-
merging clean. Remaining on the connector side: nightscout-connect's
official/dev (8e26786) has taken #71 (Glooko), #72 (CI) and #73 (LibreLinkUp
v4) and its package.json says 0.0.14, while the programme's local, unpushed
tag v0.0.14 (649a7de) is 11 ahead and 24 behind that and conflicts with it in
11 files (`git merge-tree --write-tree --name-only official/dev v0.0.14` in
externals/nightscout-connect, 2026-09-22). PR #68 (backoff and jitter, P0-F)
is open and in neither. P0-TAG is needs-decision on which 0.0.14 is the
release; P0-PIN and P0-LOCK are blocked behind it. None of these needs a
tenancy decision.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `P0-A` | bf/alarms - PR #8739, BF-28, BF-29, BF-31 | `merged-upstream` | `bf/alarms` | minor | 9 run + 3 no-gate |
| `P0-B` | bf/cache - PR #8740, T0.2 and T0.3 read-path cost | `merged-upstream` | `bf/cache` | patch | 6 run + 2 no-gate |
| `P0-C` | bf/auth - BF-17 plaintext token (BF-30 split out to P0-J) | `gate-not-met` | `bf/auth` | major | 4 run + 3 no-gate |
| `P0-J` | bf/throttle - BF-30, failed-auth throttling, compatibility default | `gate-not-met` | `bf/throttle` | patch | 5 run + 2 no-gate |
| `P0-C-REMEDIATE` | Operator remediation for tokens already stored in plaintext - text, not tooling | `ready-to-push` | `-` | n/a | 1 run + 2 no-gate |
| `P0-D` | bf/coercion - PR #8737, query filter typing (T0.5) and the $exists inversion | `merged-upstream` | `bf/coercion` | minor | 7 run + 1 no-gate |
| `P0-E` | bf/reads - PR #8738, six read-path fixes, independent of bf/coercion | `merged-upstream` | `bf/reads` | major | 10 run + 5 no-gate |
| `P0-F` | fix/connect-timer-jitter - PR #68, BF-34 backoff precedence and start jitter | `in-flight-upstream` | `fix/connect-timer-jitter` | minor | 3 run + 2 no-gate |
| `P0-G` | bf/food - PR #8735, BF-16 quick-pick filter, BF-35 bolus calculator chooser | `merged-upstream` | `bf/food` | minor | 6 run + 1 no-gate |
| `P0-H` | bf/merge - PR #8734, BF-36 client delta merge reads past the end | `merged-upstream` | `bf/merge` | patch | 5 run + 2 no-gate |
| `P0-I` | bf/parms - PR #8736, BF-37, BF-38, BF-39 | `merged-upstream` | `bf/parms` | patch | 6 run + 1 no-gate |
| `P0-K` | bf/operators - PR #8743, BF-04 extracted, BF-70 found | `merged-upstream` | `bf/operators` | minor | 7 run + 2 no-gate |
| `P0-TAG` | nightscout-connect release/v0.0.14 and tag - prepared, needs a human push | `needs-decision` | `release/v0.0.14` | minor | 6 run + 1 no-gate |
| `P0-PIN` | bf/connect-pin - move dev's connector pin to the v0.0.14 tarball | `blocked` | `bf/connect-pin` | patch | 3 run + 1 no-gate |
| `P0-LOCK` | Regenerate package-lock.json after the v0.0.14 tag is pushed | `blocked` | `bf/connect-pin` | n/a | 2 run |
| `P0-T01` | T0.1 - PR #8733, the two quadratic treatment scans | `merged-upstream` | `fix/quadratic-treatment-processing` | patch | 1 run + 1 no-gate |
| `FU-LIMIT` | Follow-up 2 - the limit rule is written twice, and that is the root cause | `blocked` | `-` | patch | 2 run + 1 no-gate |
| `FU-RESIDUALS` | Follow-ups 3, 4, 7 - three named residuals beside branches already prepared | `gate-not-met` | `-` | patch | 3 run + 1 no-gate |
| `FU-PRBODIES` | Five merged PR bodies have drifted from the files they were posted from | `needs-decision` | `-` | n/a | 1 run + 2 no-gate |
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
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/alarms | grep -q 5dcf783fdbb20188c378d79121dcbe860425eede`
  - the branch behind PR #8739 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
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
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/cache | grep -q 4f86bab1637e926502c9b02af008cbba4f424c28`
  - the branch behind PR #8740 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
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

**Notes.** Sequencing letter C. GT3 found BF-17's created_at residual: the pick() at endpoints.js:44 is ['_id','name','accessToken','roles','notes'] - notes was added by the fix, created_at was not. Commit 56ed29d2 removes the leftover console.log('Loading',opts). That line was not introduced by this branch - it is on origin/dev at storage.js:84 - and it is taken here because it sits in a file this branch already rewrites and is the same defect class as the count- path filter leak fixed on bf/reads. FU-RESIDUALS follow-up 4 is carried BY THIS BRANCH and should not be fixed there a second time; it is `fixed` (on a branch), not merged, and FU-RESIDUALS' gate, which reads origin/dev, correctly still fails. Green gates here do not mean an operator is safe - tokens written in plaintext before the upgrade are untouched by it. The remediation is TEXT, not tooling (P0-C-REMEDIATE): no detector and no migration, rotation instructions carried by this branch's PR body and the 15.0.9 release notes, and a gate guarding what they say, including that renaming a subject is not a rotation because the matcher is name-independent. --- The 2026-09-21 merge-up (tip 404e714c, origin/dev 59430336 merged into ce82f0cd, on the maintainer's instruction). Exactly one file is touched by both sides, lib/authorization/storage.js, in different functions: dev's 06b133a7 (BF-01, from bf/reads) replaces the limit() helper on the READ path, while this branch narrows save() to a field allow-list and removes the console.log('Loading',opts) on that same read path. The merge changed 2 lines and removed 4 in lib/authorization/. merge-tree is not trusted alone here (the register's BF-04 detail records a merge-tree CLEAN result that hid a semantic collision), so it was measured: TEST=authsubjects 8 passing at ce82f0cd and 8 passing at 404e714c; tracking gate green; full suite 2319 passing, 3 pending, 0 failing at 404e714c against mongod 7.0.43 started with --ulimit nofile=64000:64000. That qualifier matters - at Docker's default descriptor limit mongod dies mid-suite (BF-10) and every downstream timeout looks like a regression. --- Current state (2026-09-22): behind origin/dev 74fc6619 by the three advisory merges; trial merge clean. The merge is not done here because a merge without re-running the full suite would trade a red gate for an unmeasured green one. While this branch is ready and unpushed it goes stale every time dev moves, and at gate-not-met it has no reviewer packet (emit_packets builds only for in-flight-upstream, ready-to-push and needs- decision). Pushing it is what stops that.

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

**Notes.** Why the split. The modernization branch (PR #8605) does not touch lib/authorization/delaylist.js - it is byte-identical to dev there - but it REPLACES THE IP DERIVATION THAT FEEDS IT, swapping the forwarded-for package for lib/server/client-ip.js driven by TRUST_PROXY, in exactly the call sites the peer-address plumbing also edited. The two were fixing one root cause with two different modules. Without peer-address.js the conflict with #8605 is one file, and that one belongs to BF-17 (P0-C). What the compatibility default costs, recorded because it was argued and decided: another release in which an attacker rotating X-Forwarded-For is not throttled. The usual price of turning it on - one failing client behind a shared proxy slowing others - is already paid for by the sleep-timing change in this same commit, because only failing requests wait. So the compatibility case is weaker here than for the allow- list on P0-C, and that was said at the time. The maintainer's instruction was compatibility defaults plus notification across this area. --- The 2026-09-21 merge-up (tip a0823c4f, origin/dev 59430336 merged into 435419ce, on the maintainer's instruction). Zero overlap, measured before merging: dev had no commit touching any of this branch's three files. Both properties the split exists to preserve hold after the merge - no conflict against chore/nightscout-modernization, and no peer-address plumbing. TEST=authdelay: 11 passing at 435419ce and at a0823c4f. Current state (2026-09-22): behind origin/dev 74fc6619 by the three advisory merges, so the freshness gate is red and the state is gate-not-met; the other three static gates pass. Not merged up, for the reason given under P0-C. `pr: []` is declared because the review text names #8605, which is RT-3's PR, not this item's; without the declaration the packet generator would infer the wrong PR from the prose.

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
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/coercion | grep -q b72347538ba29f965c531bdd47f81dc52d895a13`
  - the branch behind PR #8737 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
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
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/reads | grep -q 2ecfeb53ff1e6121ef5f76e1f08e97af1ca6c2fa`
  - the branch behind PR #8738 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
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
| state (claimed) | `in-flight-upstream` |
| repo | `nightscout-connect` |
| branch | `fix/connect-timer-jitter` |
| base | `b77e5bb` |
| worktree | `externals/work/nc-jitter` |
| semver | `minor` |
| review | maintainer - the sequencing document says land this one first if anything is landed first. Open as nightscout-connect PR #68, base dev. One approval there covers four PRs' worth of change; see notes. |
| register | `BF-08`, `BF-34` |

**Blast radius.** lib/backoff.js, lib/machines/cycle.js. 19 new tests, 135 pass / 0 fail, every part reverted in turn and caught.

**What an operator sees.** This changes the connector, the part of Nightscout that fetches readings from a CGM (continuous glucose monitor) vendor's online service. When that service is refusing requests, the connector used to retry roughly 586 times faster than it was configured to, and every account retried at the same instant. With this fix it waits the interval it was told to wait and spreads the retries out. Something that may seem backwards: after this fix a vendor outage can look like it recovers more slowly, because the connector no longer retries in a burst that could not have worked. Your data does not arrive any later than it would have; the burst was never getting through. The connector can also spread out its first contact with the vendor after a restart; both of these spreading settings default to 0, so nothing changes for anyone who does not set them. This is merged nowhere yet and reaches no one until a connector release is cut and Nightscout is updated to use it (P0-TAG, P0-PIN).

**Why `minor`.** GT4 argues for 0.1.0 rather than 0.0.14 and the argument is sound - option precedence reversed, a changed default (use_random_slot:false -> jitter:'equal'), a new throw on an unknown jitter mode, and duration_for became non-deterministic. Each is breaking for a caller. It costs nothing because ^0.0.13 matches only 0.0.13 and cgm-remote-monitor pins by tarball anyway. Unresolved disagreement: the prepared tag says 0.0.14.

**Gates.**

- `[unit]` _(cwd: `externals/work/nc-jitter`)_ `npm test`
  - 135 passing / 0 failing; the connector suite needs no database
- `[unit]` _(cwd: `externals/work/nc-jitter`)_ `node -e "const b=require('./lib/backoff.js'); try { b({jitter:'wild'}); process.exit(1); } catch(e) { process.exit(/unknown jitter mode/.test(e.message)?0:1); }"`
  - the new throw on an unknown jitter mode is the observable half of the precedence fix - if options were still being discarded, the bad mode would never be read and this would not throw
- **NO GATE** &mdash; Vendor rate limits are unmeasured (EXP-MT-051) and need real credentials, which rule 0 forbids here. T0.4 shipped CONNECT_START_JITTER_MS so the pool CAN be spread - but the window to set it is exactly the number that is unmeasured.
- `[network]` `git -C externals/nightscout-connect ls-remote --heads origin fix/connect-timer-jitter | grep -q c1cce2a2f9623e1164d85b1625a65d27e3116b51`
  - the branch behind nightscout-connect PR #68 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
- **NO GATE** &mdash; Review and merge state of PR #68 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven - the same marker P0-T01 carries.

**Evidence.**

- `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** Sequencing letter F. Merging this in the connector repository ships it to nobody - cgm-remote-monitor pins the connector by tarball. P0-TAG and P0-PIN are what deliver it. As of official/dev 8e26786 (2026-09-22) the backoff-and- jitter commit c1cce2a is NOT in connector dev (`git merge-base --is-ancestor c1cce2a official/dev` exits 1), so it is in neither candidate 0.0.14 that dev could release. PR target (maintainer, 2026-09-16): base `dev`, head `fix/connect-timer-jitter`, ONE PR carrying 11 commits. Measured at the time: `origin/dev` 6dfc4f0 was tree-identical to `origin/main` b394411 (main was only the merge commit of PR #26), and #64 and #67 both target `dev`, so `dev` is the release line for this batch. `git rev-list --count origin/dev..fix/connect-timer-jitter` = 11; 27 files, +1359/-309; trial merge into that `dev` clean. Connector dev has since moved to 8e26786 and this has not been re-trial-merged against it. What the one PR approves: only c1cce2a is this branch's work. Nine of the other ten commits belong to four other pull requests - #64 (open, -> dev), #65 (merged into `fix/dexcom-safe-logging`, NOT into dev or main), #66 (open, -> `fix/dexcom-safe-logging`), #67 (open, -> dev; its commit 234d47c is what cgm-remote-monitor dev pins today) - plus the integration merge b77e5bb (`origin/fix/modernization-debug-logging`, no PR). So one approval covers four PRs' worth of change. The maintainer chose this over stacking on `fix/modernization-debug-logging` (which would reduce the PR to the single commit c1cce2a) with the tradeoff on the table, and the PR body says so; its description of those nine commits is that they are not yet merged. Why c1cce2a is not rebased alone onto dev (measured 2026-09-16): `git cherry-pick c1cce2a` onto the then origin/dev conflicts in three files, one hunk each (README.md, index.js, lib/builder.js); lib/backoff.js and lib/machines/cycle.js auto-merge clean. The builder.js resolution would have to delete `logger: config.logger`, which comes from 234d47c - the commit genuinely assumes #67 is in place, as its own message says ("The precedence fix cannot ship alone"). The 135-test and per-part-ablation evidence was taken on the stacked base and would need re-taking.

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
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/food | grep -q 73495331e68c4cda3a63e8c047387bdf404b89b0`
  - the branch behind PR #8735 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
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
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/merge | grep -q b06c6faf882ebd84d627468c75dade0fe1fd01a1`
  - the branch behind PR #8734 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
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
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/parms | grep -q eb0bc918036a7802a0b88156e9722f45fd9107f3`
  - the branch behind PR #8736 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
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

### `P0-TAG` &mdash; nightscout-connect release/v0.0.14 and tag - prepared, needs a human push

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `nightscout-connect` |
| branch | `release/v0.0.14` |
| base | `v0.0.13@b394411` |
| worktree | `externals/nightscout-connect` |
| semver | `minor` |
| review | maintainer - pushing the tag is the deliberate human act; the connector repository has no release workflow, so the tag publishes nothing by itself |
| register | `BF-08`, `BF-34` |
| blocks on | `P0-F` |

**Blast radius.** Two candidate 0.0.14s exist. Measured 2026-09-22 against connector official/dev 8e26786: official/dev's package.json says 0.0.14 (bumped upstream in e231600), and the programme's local, unpushed annotated tag v0.0.14 points at release/v0.0.14 649a7de, whose package.json also says 0.0.14 - two different trees with one version. `git rev-list --left-right --count official/dev...release/v0.0.14` = 24 behind / 11 ahead. The 24 include LibreLinkUp v4 (PR #73), the Glooko work (#71), the connector regression-CI restore (#72) and the main->dev merge (#69). `git merge-tree --write-tree official/dev release/v0.0.14` conflicts in 11 files at 8e26786: .github/workflows/test.yml (added in both), index.js, lib/builder.js, lib/machines/{cycle,fetch,poller,session}.js, lib/outputs/internal.js, lib/sources/glooko/{convert,index}.js and lib/sources/librelinkup.js. Pushing the prepared tag would therefore mint a v0.0.14 that is not dev's 0.0.14, and the tarball P0-PIN pins would omit work upstream considers part of that version. That is a release-content decision, not a mechanical reconciliation. Three shapes, none obviously right: reconcile release/v0.0.14 onto dev and cut the tag from there; abandon the prepared branch and let upstream tag dev; or cut ours as 0.0.15 and leave 0.0.14 to dev. Nothing has been pushed; the remote's newest tag is v0.0.13. The prepared release itself: 11 commits, 29 files, +1362/-312, of which 887 lines are new test files; b394411 fast- forwards to 649a7de.

**What an operator sees.** A new version of the CGM connector, the part of Nightscout that fetches readings from a CGM vendor's online service. See P0-F for what changes in behaviour. Nothing reaches anyone until the connector version is decided, tagged, and a Nightscout release is updated to use it.

**Why `minor`.** see P0-F. GT4 argues the version should be 0.1.0; the prepared tag says 0.0.14, and upstream dev has independently declared 0.0.14. Unresolved.

**Gates.**

- `[static]` `git -C externals/nightscout-connect merge-base --is-ancestor v0.0.13 release/v0.0.14`
  - v0.0.13 fast-forwards to the release - no divergence to reconcile
- `[static]` `test "$(git -C externals/nightscout-connect cat-file -t v0.0.14)" = tag`
  - v0.0.14 is an ANNOTATED tag, not a lightweight one
- `[static]` `test "$(git -C externals/nightscout-connect rev-parse v0.0.14^{commit})" = "$(git -C externals/nightscout-connect rev-parse release/v0.0.14)"`
  - the tag points at the release branch tip
- `[static]` `test "$(git -C externals/nightscout-connect show release/v0.0.14:package.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')" = 0.0.14`
  - package.json version matches the tag
- `[network]` `git -C externals/nightscout-connect ls-remote --tags origin v0.0.14 | grep -q . && exit 1 || exit 0`
  - RULE 0. This gate PASSES only while the tag is NOT on origin. It is the machine-checkable form of "nothing has been pushed". Read-only.
- `[static]` `git -C externals/nightscout-connect merge-base --is-ancestor official/dev release/v0.0.14`
  - The release branch must contain everything on upstream dev, or the tag names a tree missing work upstream already considers released. RED: release/v0.0.14 is 24 commits behind official/dev 8e26786 (2026-09-22). The other five gates measure the prepared artefact against itself - tag type, tag target, version string, fast-forward from the previous tag; this is the one that measures it against the tree it would be pushed into.
- **NO GATE** &mdash; Whether all seven connector commits are the RIGHT content for a release is a release-content decision, not a mechanical bump, and it is the maintainer's. Nothing can gate it.

**Evidence.**

- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`

**Notes.** v0.0.14 is the FIRST ref carrying all seven connector commits - both the debug-logging narrowing that cgm-remote-monitor dev's pin (234d47c, connector PR #67, open) has and the three log-redaction fixes that cut 4's pin has. GT4 found the two mitigations split across the two release trains. That is why abandoning the branch outright is not obviously the right shape either: connector dev at 8e26786 does NOT carry c1cce2a, the backoff-and-jitter commit, because PR #68 is still open. Whatever is decided has to keep all seven.

### `P0-PIN` &mdash; bf/connect-pin - move dev's connector pin to the v0.0.14 tarball

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `bf/connect-pin` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-connect-pin` |
| semver | `patch` |
| review | maintainer |
| blocks on | `P0-TAG` |

**Blast radius.** 1 commit, 0807eb1c, one file, +1/-1 (package.json:140).

**What an operator sees.** Nightscout picks up the new connector (the part that fetches readings from a CGM vendor's online service). Three fixes that keep CGM vendor credentials and personal health data out of the log file come with it. The connector already in the next release (15.0.9) stops writing passwords, session tokens and readings to the log, with or without debug logging turned on. This item moves Nightscout onto a published connector version rather than an in-progress one, and adds the connector's other fixes (cleaner shutdown, retry timing). Not released; waits on the connector version decision (P0-TAG).

**Why `patch`.** a dependency pin move; the behaviour change is the connector's and is classified at P0-F.

**Gates.**

- `[static]` _(cwd: `externals/work/crm-bf-connect-pin`)_ `grep -q 'archive/refs/tags/v0.0.14.tar.gz' package.json`
  - package.json points at the v0.0.14 tag tarball
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/connect-pin`
  - bf/connect-pin has not fallen behind origin/dev. RED, and correctly: this branch is still waiting to be pushed, so being behind dev is a real defect in it (dev at 74fc6619 carries the Phase 0 merges this branch does not). The remedy is a `git merge dev`; the trial merge was measured conflict-free on 2026-09-21.
- `[static]` _(cwd: `externals/work/crm-bf-connect-pin`)_ `grep -q '234d47c85510a77f07b3be0d2c026dd0272715d6' package-lock.json`
  - DELIBERATELY INVERTED. This gate passes while the lockfile is STILL on the old SHA. The lock's integrity is a hash over a tarball GitHub does not generate until the tag is pushed; a hash invented locally would break `npm ci` for everyone. Leaving it stale makes `npm ci` fail LOUDLY as out-of-sync, which is the correct failure. When P0-LOCK is done this gate SHOULD go red - that is the handoff signal.
- **NO GATE** &mdash; Nothing can verify the tarball's integrity hash before the tag exists on GitHub. That is the whole reason P0-LOCK is a separate item.

**Evidence.**

- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`

**Notes.** This is the branch that closes the split GT4 found: neither dev's pin (234d47c) nor cut 4's pin carries both the logging narrowing and the redaction commits. Master pins connector tag v0.0.13. If P0-TAG is resolved as something other than the prepared v0.0.14 (for example upstream tags dev, or ours becomes 0.0.15), this branch's target tarball changes with it.

### `P0-LOCK` &mdash; Regenerate package-lock.json after the v0.0.14 tag is pushed

| | |
|---|---|
| state (claimed) | `blocked` |
| repo | `cgm-remote-monitor` |
| branch | `bf/connect-pin` |
| base | `bf/connect-pin@0807eb1c` |
| worktree | `externals/work/crm-bf-connect-pin` |
| semver | `n/a` |
| review | maintainer - same PR as P0-PIN |
| blocks on | `P0-PIN`, `P0-TAG` |

**Blast radius.** package-lock.json, two entries (lines 58 and 7894).

**What an operator sees.** Nothing you see. Until this is done, the install command `npm ci` fails with an out-of-sync error on this branch - which is intentional and correct, not a bug.

**Why `n/a`.** lockfile only

**Gates.**

- `[static]` _(cwd: `externals/work/crm-bf-connect-pin`)_ `grep -q 'archive/refs/tags/v0.0.14.tar.gz' package-lock.json`
  - the lockfile agrees with package.json. FAILS today, on purpose, and must not be made to pass locally - see P0-PIN's inverted gate.
- `[network]` _(cwd: `externals/work/crm-bf-connect-pin`)_ `npm ci --dry-run`
  - npm ci resolves; requires the pushed tag to exist on GitHub

**Evidence.**

- `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`

**Notes.** Deliberately undone and it must not be papered over. Regenerate with `npm install` once the tag is pushed, in the same PR.

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

- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bewest/wip/optimize-treatment-processing | grep -q dfe2753d`
  - the one Phase 0 branch that was pushed from outside the backfix worktrees. GT1 verified this live. Read-only.
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

**What an operator sees.** One of these three is visible to you. If an Amazon Alexa request arrives that Nightscout does not recognise, Nightscout answers nothing at all and the request hangs until Alexa gives up, rather than saying it did not understand. The other two are internal - a check that always answers "yes" but that nothing currently asks, and a leftover log line that prints request details to the server log.

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

**Notes.** Three small residuals the sequencing document named together, each one file and each measurable. Follow-up 4 (the console.log in lib/authorization/storage.js) is fixed on bf/auth as commit ce82f0cd and must not be fixed here as well - this is a cross-reference, not a second item. Its gate fails, correctly, because it reads origin/dev and P0-C has not merged; when P0-C merges it goes green on its own and only follow-ups 3 and 7 remain. Follow-up 7 sits beside the ctx.language.set(locale) line that bf/alarms (P0-A, merged) changed.

### `FU-PRBODIES` &mdash; Five merged PR bodies have drifted from the files they were posted from

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@74fc6619` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | MAINTAINER, and the decision is narrow: are merged pull request bodies worth correcting at all? For: a merged PR body is the durable public record of why a change was made, and four of these cite file paths that 404 for anybody who follows them. Against: few people read a merged PR body and the edit costs a push. If the answer is yes, #8739 must be handled differently from the other four. Its live body is ahead; the upstream text has to be reconciled INTO reports/phase0-pr-bodies/bf-alarms.md before anything is pushed, or that work is destroyed. A one-way `gh pr edit <pr> --body-file <local>` on #8739 would overwrite it and then report green. |
| ships to operators today | no (pre-release) |

**Blast radius.** No code. Five pull request bodies and up to five files under reports/phase0-pr-bodies/. Measured 2026-09-21 by tools/queue/gates/pr-body- parity.js over all eight pairs: #8738, #8740 and #8743 match; #8734, #8735, #8736, #8737 and #8739 differ. The drift runs in two directions. #8734, #8735, #8736 and #8737 differ only in documentation paths - the local files were updated when the docs tree moved into programme subdirectories, so the LIVE bodies still cite the pre-move spellings (the backfix register without its `remedial/` segment, the semver classification without `modernization/`), and those paths no longer resolve. The spellings are deliberately not written out here: doc-links.js gates this file, and a dead path quoted in a note is indistinguishable to it from a dead path being relied on. Word counts are identical each way. #8739 is the opposite: the live body is 1640 words to the file's 1537 and carries paragraphs the file does not have - the urgent- severity versus notification-delivery distinction, and a note about Alexa and Google Home locale handling - added upstream after posting.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation of changes already merged; no shipped behaviour

**Gates.**

- `[network]` `node tools/queue/gates/pr-body-parity.js`
  - All eight bodies match their files. Red with five failing as of 2026-09-21. Read-only - it fetches bodies and never edits one.
- **NO GATE** &mdash; Whether a body is TRUE is not measured by anything here, and parity with a wrong file is still parity. Figures in these bodies have been wrong before - bf/parms had two, bf/reads had four - and only re-running the claim catches that.
- **NO GATE** &mdash; Nothing gates the reconciliation of #8739. Merging upstream prose into a local file is an editorial act; a gate can say the two differ and cannot say the merge was faithful.

**Evidence.**

- `tools/queue/gates/pr-body-parity.js`
- `reports/phase0-pr-bodies/bf-alarms.md`

**Notes.** The parity gate belonged to eight Phase 0 items that are all merged-upstream, so its red reads as expected post-merge noise on rows nobody revisits; this item gives it an owner. No PR body was edited; five were read.

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

`parcel: release-train` &mdash; 12 items

The adopted order (maintainer, 2026-09-15): 15.0.9, then cut 1, then cut 2,
then cuts 3+5 combined, then a deprecation release, then cut 4. The premise of
"zero rebase work" was measured false (GT2); the rebase items here are what
that costs.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `RT-D3` | Answer the D3 question before 15.0.9 ships | `needs-decision` | `origin/dev` | minor | 2 run + 1 no-gate |
| `RT-VERSION` | Two artefacts claim version 15.0.9 with different Node floors | `not-started` | `-` | n/a | 1 run + 1 no-gate |
| `RT-REBASE` | Cuts 1-4 are 133 commits behind dev and now all five conflict | `gate-not-met` | `chore/retire-jsdom, chore/build-runtime-separation, chore/compose-mongodb6, chore/mime-exposure-review` | n/a | 6 run + 1 no-gate |
| `RT-0` | Release 15.0.9 | `needs-decision` | `origin/dev` | minor | 1 run + 2 no-gate |
| `RT-1` | Cut 1 - chore/retire-jsdom | `blocked` | `chore/retire-jsdom` | major | 2 run + 2 no-gate |
| `RT-2` | Cut 2 - chore/build-runtime-separation | `blocked` | `chore/build-runtime-separation` | minor | 1 run + 1 no-gate |
| `RT-3` | Cuts 3+5 combined - dependency release | `blocked` | `chore/nightscout-modernization` | major | 1 run + 2 no-gate |
| `RT-4` | Deprecation release - the MiniMed migration path that does not exist | `not-started` | `-` | minor | 1 run + 1 no-gate |
| `RT-5` | Cut 4 - chore/mime-exposure-review, the one to slow down on | `blocked` | `chore/mime-exposure-review` | major | 2 run + 2 no-gate |
| `RT-CONNECT-PIN-CUTS` | BF-65 - cuts 1-3 ship the leaking connector to upgraders first | `gate-not-met` | `chore/retire-jsdom, chore/build-runtime-separation, chore/compose-mongodb6` | patch | 1 run + 1 no-gate |
| `RT-NODE-FLOOR-TESTED` | BF-58, BF-59 - the enforced Node floor is not the Node anything exercises | `gate-not-met` | `chore/compose-mongodb6, chore/mime-exposure-review, chore/nightscout-modernization` | n/a | 2 run + 2 no-gate |
| `RT-BOOTERROR` | BF-63 - the page that reports a boot error crashes on cut 4's boot errors | `gate-not-met` | `-` | patch | 2 run + 1 no-gate |

### `RT-D3` &mdash; Answer the D3 question before 15.0.9 ships

| | |
|---|---|
| state (claimed) | `needs-decision` |
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

- `[unit]` _(cwd: `externals/cgm-remote-monitor-official`)_ `TEST=dependency-d3 npm run test-single`
  - 24 passing (GT2), driving the real renderer and chart against the D3 7 browser bundle. Non-vacuous: it catches reverting mouseover handlers to the D3-5 signature and catches breaking d3.pointer.
- `[static]` `node tools/queue/gates/d3-drag-clamp-covered.js`
  - The coverage gap. With BOTH treatment-drag clamps deleted (renderer.js:764 and 770-771) the suite stays at 24/24 - the handler runs 25 times with only x in {20,400}, all strictly inside 0..900, so the boundary is never reached (GT2). This gate re-runs that ablation and FAILS while the clamps are uncovered.
- **NO GATE** &mdash; lib/plugins/cob.js +49/-73 is filed under the D3 heading in release-readiness §2 and is NOT D3 work - it is 34e9b2da, "fix(cob): use the COB reported by the uploading system". It is more than twice the size of the entire D3 migration, it changes what a user reads when deciding about food and correction, and it has no line of its own in the 15.0.9 release decision. Nothing gates it because nobody has decided what it is.

**Evidence.**

- `docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`
- `docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md`

**Notes.** The clamps bound a user-initiated rewrite of a treatment's created_at emitted over the socket, and a treatment's timestamp is what IOB/COB key off. They are the exact lines the D3 6 migration rewrote and the least covered lines it touched.

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

**Notes.** Given the governance gap - 100 self-merged PRs, zero human reviews - the version number is the only warning an operator gets, and right now it does not distinguish these builds.

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

**Notes.** A rebase is prepared locally (2026-09-21, on the maintainer's instruction) in externals/work/crm-cuts: rt/cut1 77d6ffaf, rt/cut2 6106332e, rt/cut3 5bff9225, rt/cut4 8a692d88. NOT PUSHED. The published cut branches the gates measure are unchanged. Method: dev was propagated UP the stack (dev into cut 1, cut 1 into cut 2, and so on), so the prefix property is preserved and cut 1's resolutions are inherited. Measured: each cut is an ancestor of the next, each contains origin/dev, and all four trial-merge into dev cleanly. Propagation needed 7 conflict resolutions at cut 1, then 9 / 5 / 4, against the 14 / 16 / 18 each would have had against dev directly. Nine of the 25 conflicts were Phase 0 fixes the cuts predate, and taking the cut's side would have reintroduced each: BF-01 (?count=0 answering with the whole collection), BF-07 (cloning the retained window), BF-16 and BF-35 (the bolus calculator quick-pick filter and chooser), BF-36 (delta merge past the end), plus the BF-04 allowlist and BF-70 pipeline refusal. All seven verified present on cut 4 after the merges. The cut 5 tip carries only two thirds of BF-07, and these branches do not copy that: b1bdaca0 keeps getDataRef in lib/server/cache.js and both lib/data/dataloader.js callers but reverted lib/api/entries/index.js to getData - origin/dev has 7 occurrences under lib/, b1bdaca0 has 6, these branches have 7. Worth raising against e3b22034 upstream. The connector pin at cut 4 was a real fork: dev's 234d47c8 and cut 4's c962a13f are neither an ancestor of the other, so either side loses something. Resolved to b77e5bb7, which has both, is pushed to the connector remote, and is what the local tip pins. This makes P0-PIN and the v0.0.14 question more urgent. Test results on Node 24.20.0 against mongod 7.0.43 (the Node version matters - see RT-NODE- FLOOR-TESTED): cut 1 348 passing, cut 2 357, cut 3 324, cut 4 310, zero failures. Counts differ because later cuts remove suites (cut 4 retires the bridge and mmconnect tests). Cut 1's ported browser coverage was ablated: removing dev's 06372e1d takes it from 21 passing to 12 passing / 9 failing, so it measures the fix. Not done: the coverage of tests/pluginbase.modern.test.js and tests/profile-sinks.test.js, both deleted by cut 1's jsdom retirement, has not been audited against cut 1's Playwright replacements - 12 it() cases in the first and 6 in the second are unaccounted for. Only clock-client's was audited, because it had a named production fix behind it. Release-readiness §5's "each costs zero rebase work today" was false when written: the cut tips date to 2026-09-05/06 and dev's tip to 2026-09-09. "0 commits behind dev" was true of the stack tip only, because of one commit, 0a4109f6.

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

**Notes.** First on the adopted train. Every merged backfix in dev - the items in state merged-upstream - reaches operators only through this release; until it ships they are in code nobody runs. Merging dev publishes a Docker Hub image, which is not a release. dev pins nightscout-connect at 234d47c (unmerged connector branch fix/8714-opt-in-debug-logging, connector PR #67), where master pins tag v0.0.13 - see P0-PIN and P0-TAG.

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

**Notes.** From cut 1 onward docker-build and docker-build-pr carry needs: [test, browser-test], so a browser-test failure blocks image publication. On dev, docker-build has needs: test only.

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
| register | `BF-64` |
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

**Notes.** §5's commits column sums to 554 against a 495-commit stack (GT2). Counted as modernization work, cut 5 is 95, and 95 + 400 = 495.

### `RT-4` &mdash; Deprecation release - the MiniMed migration path that does not exist

| | |
|---|---|
| state (claimed) | `not-started` |
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

**Notes.** The adopted train puts this BEFORE cut 4 deliberately. GT4 found the real code work: the MiniMed shim has to be written, not just a warning added. Caveat on the population: the maintainer stated on 2026-09-21 that mmconnect (minimed- connect-to-nightscout) has been broken for some time (operational knowledge, not measured here) and that legacy Dexcom Share is intended to map to nightscout-connect. If mmconnect is not working today, the MiniMed half of this release warns about a path that is already failing; BF-44/BF-45 were graded assuming it is live and have not been re-graded.

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
  - Re-runs GT4's execution of both cut-4 shims in the order bootevent.js calls them, with four env shapes. FAILS while either shape produces a bootError. This is the gate that says whether an operator's site goes dark, and it must be green before this cut ships.
- **NO GATE** &mdash; "No real Dexcom account or live database has been used and no live migration is claimed" - the cut's own evidence document. No gate can substitute for a real migration, and nothing in this repository may use real credentials (rule 0).
- **NO GATE** &mdash; Cut 4 deletes bridgeUseLegacy and the log line naming it, so DEXCOM_BRIDGE_USE_LEGACY becomes accepted-and-ignored. Credentials are still migrated so ingestion continues; only the operator's expressed intent is discarded silently. Nothing checks for accepted-and-ignored settings.

**Evidence.**

- `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`
- `docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`

**Notes.** HELD BACK on the adopted train, behind a deprecation release. If the Connect migration misbehaves the symptom is a user's glucose data stops arriving - a data-availability failure for someone managing diabetes.

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

**Notes.** The gate's caller-count arm matches ES6 shorthand `err` as well as `err:` - dev's `bootErrors.push({desc: synopsis.join(' '), err})` has no colon and is not an err-less site. It reproduces the register exactly: 7/7/9 push sites, 0/0/2 err-less, on master/dev/cut 4.

---

## Open backfix-register entries

`parcel: register-open` &mdash; 30 items

The §1 / §1b distinction is preserved in `ships_to_operators_today`. That
distinction is the only thing that makes the register mean anything - widening
§1's criterion would destroy it.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
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
| `BFQ-69` | BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing | `not-started` | `-` | patch | 1 run + 1 no-gate |
| `BFQ-71` | BF-71 - any dateString key drops the default date window, and the window is not a control | `gate-not-met` | `-` | patch | 2 run + 2 no-gate |
| `BFQ-72` | BF-72 - an unauthenticated $regex can spend minutes of database CPU | `needs-decision` | `-` | minor | 1 run + 3 no-gate |
| `BFQ-40` | BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion | `merged-upstream` | `-` | minor | 1 run |
| `BFQ-41` | BF-41 - a reading dated ahead of the clock silences the stale-data alarm | `gate-not-met` | `-` | minor | 1 run + 1 no-gate |
| `BFQ-CONNECTOR` | BF-42, BF-43 - master pins the leaking connector, with a violated axios override | `gate-not-met` | `-` | patch | 1 run + 2 no-gate |
| `BFQ-MINIMED` | BF-44, BF-45, BF-85 - MiniMed ingestion divergences and the CareLink zero reading | `not-started` | `-` | minor | 0 run + 3 no-gate |
| `BFQ-46` | BF-46 - eleven API v3 variables bypass env.js, one family deletes data | `gate-not-met` | `-` | minor | 1 run + 1 no-gate |
| `BFQ-47` | BF-47 - an ordinary subject edit destroys stored fields, on today's release | `needs-decision` | `-` | major | 0 run + 2 no-gate |
| `BFQ-ENV` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies | `gate-not-met` | `-` | minor | 4 run + 2 no-gate |
| `BFQ-52` | BF-52 - the age plugins can only ask for their urgent alarm in one window | `unsettled` | `-` | patch | 0 run + 2 no-gate |
| `BFQ-67` | BF-67, BF-86 - alarm thresholds quietly changed, or quietly kept when they cannot work | `gate-not-met` | `-` | minor | 1 run + 1 no-gate |
| `ADV-RETRO` | GHSA-gjhc - loadRetro serves devicestatus to any socket (BF-79) | `merged-upstream` | `bf/ws-loadretro-auth` | patch | 2 run + 1 no-gate |
| `ADV-ALARM` | GHSA-8849 - /alarm broadcasts to the whole namespace (BF-75, BF-76) | `merged-upstream` | `bf/alarm-socket-scope` | minor | 2 run + 2 no-gate |
| `ADV-XSS-META` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) | `needs-decision` | `-` | n/a | 2 run + 1 no-gate |
| `ADV-CONFIG` | The readable-by-world warning, the careportal role, and the two settings behind both (BF-77, BF-78, BF-81) | `needs-decision` | `-` | patch | 2 run + 1 no-gate |

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

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`
- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** The register entry names the wrong fields. Measured over 277,690 treatments: ZERO zero-valued `insulin` (0 of 107,732) and ZERO zero-valued `carbs` (0 of 12,394). The field that actually carries falsy values is `absolute` - 67,521 of 153,315, 44% - the zero temp basal. `duration:0` adds 2,094. The entry also omits the ±2s window (maxtimediff). GT3's reading: a bug, not intent - the author built an explicit selected/fallback mechanism, so truthiness on `absolute` means the code treats a zero temp as "no value here", which is false in AID terms.

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
  - FAILS today. GT3 verified the mongo service carries no ulimits block on EITHER master (mongo:5.0.32) or dev (mongo:4.4), and grep for ulimit/nofile over the whole released tree returns nothing.
- **NO GATE** &mdash; REPRODUCED 2026-09-21: one branch's full suite (~2200 tests) against a plain `docker run -d mongo:7` with no ulimits killed the server. Startup warning `Soft rlimits for open file descriptors too low` (currentValue 1024, recommendedMinimum 64000), then during index creation `__posix_directory_sync` / `Too many open files` / error_code 24, then `Fatal assertion 23089 msgid 50853` at wiredtiger_util.cpp:772, then abort; container exit 14. Control: the same image with `--ulimit nofile=64000:64000` logs that warning ZERO times against TWO on the default. It is not a gate because reaching it takes a full suite against a deliberately under-provisioned mongod, and the side effect is a DEAD server - sibling worktrees sharing that mongod then fail their own suites with a `before all` timeout, which reads like a code regression. A gate whose failure mode breaks other items' gates does not belong in a shared runner. Evidence is in the register's BF-10 detail. The reproduction also shows it is not specific to the 4.4/5.0 images the shipped compose files pin - 7.0.43 does it too - and it does not need tenant scale: EXP-MT-040b reached it at 50 tenant databases; one ordinary test run is enough.

**Evidence.**

- `docs/60-research/remedial/gt3-register-truth-2026-09-15.md`

**Notes.** The register entry's "Not a code defect; it belongs in the operator documentation" does not hold: there is a one-block landing site in the file most self-hosters actually use. The fix is that file first, docs second.

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
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `patch` |
| review | maintainer, and whoever reviews P0-G. This item cannot be reviewed on its own - see blocks_on and the sequencing note. |
| ships to operators today | **yes** |
| register | `BF-69` |
| blocks on | `P0-G` |

**Blast radius.** lib/client/boluscalc.js - loadFoodQuickpicks has exactly one call site, at module construction. lib/client/index.js:239 creates an empty client.sbx, :323 constructs boluscalc against it, :596 replaces client.sbx once data arrives and :637 calls updateVisualisations, which does not rebuild the chooser. Client-side, so it needs a rebundle, not a restart.

**What an operator sees.** The Bolus Wizard (Nightscout's built-in bolus calculator) has a "quick pick" list of saved meals. That list is always empty, so saved quick picks cannot be used at all and foods have to be added one at a time from the food database instead. Nothing shows a wrong number; the feature simply does not work. This is not medical advice - if you rely on quick picks for meal dosing, raise it with your care team as well as checking your settings.

**Why `patch`.** Restores a documented feature that is inert. No API or configuration surface changes.

**Gates.**

- `[integration]` `NSREVIEW_ROOT=${NSREVIEW_ROOT:?} node tools/review/probes/quickpick-chooser-browser.js --base "$NSREVIEW_BASE_URL" --candidate "$NSREVIEW_CANDIDATE_URL" --secret "$NS_HARNESS_SECRET"`
  - Clicks the Bolus Wizard exactly as a user does and reads the chooser. It does not call loadFoodQuickpicks itself, which probes/food-boluscalc-browser.js does deliberately to reach BF-35; the difference between the two probes is this defect. Green only when the chooser is both populated and correct, because a build that repairs it without bf/food offers 8 entries and throws 5 times.
- **NO GATE** &mdash; Nothing can gate the sequencing constraint itself. A reviewer who merges this without P0-G gets a green chooser arm and a bolus calculator that loads the wrong food's carbs. blocks_on carries it; judgement enforces it.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/30-design/remedial/dev-cycle-review-harness-plan-2026-09-17.md`

**Notes.** Reproduced 2026-09-17 in a browser against the review harness, on a8888f0d and on rc/2026-09-dev-cycle: 8 food records present, chooser empty on both. The one-line candidate fix (call loadFoodQuickpicks from boluscalc.prepare, which toggleDrawer already runs on every open) was applied to a scratch worktree and verified. SEQUENCING, MEASURED: the same one-line change applied to a8888f0d without bf/food makes the chooser offer eight entries - every plain food plus the quick pick the user hid - and selecting them throws five times. BF-35's dose consequence is latent on 15.0.8 only because BF-69 hides it. Repairing the chooser first converts a latent high-severity defect into a live one in a bolus calculator. Ship with P0-G (merged to dev as #8735) or after it, never before.

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

**Notes.** Found 2026-09-21 while re-measuring the security advisory's third proof of concept, which the advisory frames as $regex data extraction. On the shipped `readable` default that is close to vacuous - entries, treatments and devicestatus are the three collections prep_storage admits, all three are already readable, and the API returns whole documents, so a regex oracle reveals nothing a plain read does not. What the same operator does do is cost the database, which the advisory does not describe. Sequencing with P0-K: #8743 merged on 2026-09-18 and did not narrow $regex, because the client census found real clients sending it. So this entry is not a regression from that branch and is not fixed by it. State is needs-decision rather than gate- not-met: a gate fails, but the blocking thing is not work. It is whether Nightscout's security contact process is invoked and in what order - the same question P0-K left open, still unanswered.

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

### `BFQ-41` &mdash; BF-41 - a reading dated ahead of the clock silences the stale-data alarm

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer, and it needs a decision before it needs code. The register prescribes no fix: a small forward skew is normal and a large one is not, and "clamp the timestamp" and "a reading ahead of the clock is itself an alarm condition" are different products. |
| ships to operators today | **yes** |
| register | `BF-41` |

**Blast radius.** lib/plugins/timeago.js - the :26 early return in checkNotifications and isStale at :97. The browser alarm decision at lib/client/index.js:918-919 reads the same status.

**What an operator sees.** Nightscout can warn you when no new glucose reading has arrived for a while - the "minutes ago" warning, which is switched on by default in the browser at 15 and 30 minutes. If a reading arrives stamped with a time in the FUTURE, that warning stops working, and it stays off. A future timestamp usually comes from a clock or timezone problem on the device or uploader sending the data - which is the same kind of fault most likely to have stopped your readings in the first place. So the warning can go quiet exactly when you need it. What you would see instead is the "minutes ago" pill reading "future", or stuck at "1m". If you rely on that warning to tell you your data has stopped, please make sure you have another way to notice, and talk to your care team about what you rely on Nightscout for. This is not medical advice.

**Why `minor`.** Whichever way the decision goes, it changes when an alarm that is on by default fires. That is a behaviour change on a safety-adjacent surface and it cannot arrive as a silent patch.

**Gates.**

- `[static]` `node tools/queue/gates/timeago-future-reading.js`
  - Executes the shipping timeago plugin. FAILS today - a reading 5 and 120 minutes ahead of the server clock both return checkStatus 'current', so neither alarm path fires. Three controls come out the other way through the same harness (2 min = current, 20 min = warn, 40 min = urgent), and the gate was proven to go green against an isolated copy carrying a future guard. This gate is BF-41's reproduction (provenance: reproduced).
- **NO GATE** &mdash; Nothing here exercises the push path end to end. checkNotifications returns early at :26 for the same reason, but it is opt-in (sbx.extendedSettings.enableAlerts) and driving it needs a booted notification stack. "The stale-data alarm is on by default and this turns it off" is true of the browser alarm and false of the push alarm; the gate measures the one that is on by default.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** BF-44 is a concrete, shipping way to produce a future-dated reading, which is why BFQ-MINIMED carries the same severity argument from the other end.

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
  - FAILS on origin/master for both arms - the v0.0.13 tag tarball (112 live console.* sites, 101 passing a non-literal argument, no debug guard anywhere) and an axios override of 1.16.0 against the connector's declared ^1.18.1. origin/dev is the control and passes both, which proves the gate reads the pins and not the command: dev's pin 234d47c deletes the leaking call sites (so "dev only makes the logging opt-in" is inaccurate). Note that 234d47c is on an unmerged connector branch (connector PR #67), not on a connector release.
- **NO GATE** &mdash; No live run and no vendor account. The census is a source census of a git archive extraction, and rule 0 forbids creating an account or contacting a vendor. It is non-vacuous in the way that matters - the same scanner returns 112/101 on the leaking tree, 22/20 on the redacted ones, and correctly reports cut 4's commented-out MiniMed block as 47 calls with zero dynamic arguments, so it distinguishes deletion from commenting-out.
- **NO GATE** &mdash; No runtime failure is claimed for the axios override, and no axios API was identified that the connector uses and 1.16.0 lacks. The defect is the silent constraint violation - `overrides` exists precisely to suppress the ERESOLVE that would report it - and nothing gates "a constraint was overridden into violation" in general.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/40-migration/connector-pin-consolidation-2026-09-15.md`

**Notes.** The fix is the same one-line pin move as P0-PIN, applied to master rather than dev, and it cannot be prepared until a connector 0.0.14 release exists. That is P0-TAG's open decision: connector official/dev (8e26786) now declares 0.0.14 in its own package.json, while the programme's local, unpushed v0.0.14 tag (649a7de) is 11 ahead / 24 behind it and conflicts in 11 files. RT- CONNECT-PIN-CUTS is the same change on cuts 1-3 and is filed separately because those are pre-release (§1b) and this is not.

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

**What an operator sees.** Two problems that affect people using a MiniMed pump with CareLink. First, the old built-in CareLink connection and the newer connector work out WHEN a reading happened in different ways, so the same reading can be filed at a different time by each. If it is filed in the future, the "no new data" warning stops working - see the separate item on that. Second, if you set up the new connector while the old CareLink connection is still switched on, BOTH run at once. For Dexcom the old one stands aside automatically; for MiniMed it does not. So any advice to "set up the new connection before removing the old one" is safe for Dexcom and NOT safe for MiniMed. The project maintainer reports that the old built-in CareLink connection has not been working for some time, which may mean fewer people are affected than this description suggests; that has not been measured. Third, when CareLink reports "no reading" for a moment, the connector saves it as a glucose value of 0, and while that is the newest value Nightscout's high and low alarms are not checked. Keep your pump's and CGM's own alarms switched on. Your glucose data continuing to arrive, at the right time, and your alarms being checked is what is at stake here. This is not medical advice; if you are changing how your data reaches Nightscout, plan it with your care team.

**Why `minor`.** BF-45's repair adds a stand-down guard to a boot stage, which changes what a deployment with both configurations does. BF-44's repair changes the timestamp a reading is stored with, which is a data-affecting change and cannot be a silent patch.

**Gates.**

- **NO GATE** &mdash; The divergence itself is reproduced and recorded in the register - both shipping implementations loaded side by side, three arms diverging by exactly the offset (UTC+2, UTC-7, UTC+5:30) and two controls agreeing (UTC+0, and UTC+2 with a zone-bearing lastConduitDateTime). It is not re-run as a queue gate because the arm/control roles invert with the server's own timezone: the magnitude is (pump offset minus server offset) whenever the payload carries no zone designator, so under TZ=Europe/Berlin the Berlin arm agrees and the UTC control diverges. A gate that did not pin TZ would report the opposite result on a differently configured machine, which is worse than no gate.
- **NO GATE** &mdash; What decides active versus latent cannot be measured from here - do real CareLink payloads omit lastConduitDateTime, and do sgs[].datetime, markers[].dateTime and sMedicalDeviceTime carry zone designators of their own? That needs a real CareLink account, which rule 0 forbids. Coverage is thin in exactly the way that hides it: lastConduitDateTime appears zero times in tests/fixtures/minimed-cutover.json and in tests/connect-minimed-cutover.test.js, and the one connector test that sets the field passes a Z-suffixed value, which makes the rewrite a no-op - that test is a control, not coverage.
- **NO GATE** &mdash; BF-45's double ingestion is read-derived from both function bodies in full on master and dev, not run as a live double ingestion. Medium alone, because the sysTime+type upsert absorbs duplicate writes; high in combination with BF-44, where the two paths compute different keys and nothing absorbs them. That combination is why these two are one item.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`
- `docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md`

**Notes.** Also recorded on BF-44 and not separately filed: pump.clock is not parsed at all, deviceStatusEntry assigns data['sMedicalDeviceTime'] verbatim, so a client doing new Date(pump.clock) can get Invalid Date. And the legacy transform throws RangeError on a Z-suffixed payload outside the MMCONNECT_SERVER=EU / GUARDIAN branch rather than producing a comparison value, so the reproduction arms hold only with MMCONNECT_SERVER=EU. GRADING CAVEAT: the grades assume the legacy mmconnect path (minimed-connect-to- nightscout) is live. The maintainer reported on 2026-09-21, as operational knowledge not measured here, that mmconnect has been broken for some time. If so, BF-45's double ingestion and BF-44's divergence are latent for most deployments. BF-44 and BF-45 have not been re-graded against that report, and nothing here can measure whether mmconnect works against the live CareLink service.

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
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-auth` |
| semver | `major` |
| review | maintainer, AND the security reviewer who takes P0-C, together - this is the one irreversible change in the Phase 0 batch and the question has to be answered BEFORE merge, not after |
| ships to operators today | **yes** |
| register | `BF-47` |
| blocks on | `P0-C` |

**Blast radius.** lib/authorization/endpoints.js:40 pick(), lib/admin_plugins/subjects.js PUT, lib/authorization/storage.js save() replaceOne with upsert. The same three files P0-C already touches.

**What an operator sees.** Editing a person or device entry (a "subject") through Nightscout's admin page already throws away fields that are not shown on that page - notes, the date it was created, and anything a third-party tool has stored there. It happens silently, there is no error, and it cannot be recovered by going back to an older version of Nightscout. This is how today's release (15.0.8) behaves.

**Why `major`.** The repair on bf/auth narrows the loss rather than introducing it, but it also introduces an allow-list, so a third-party tool can no longer preserve its own fields by sending them in its own PUT - which it can do today, because save() writes the caller's object as given. That is a capability removal on an HTTP surface.

**Gates.**

- **NO GATE** &mdash; Read-derived from source on origin/dev and on bf/auth; not reproduced against a deployment. A gate would need a database with a subject row carrying an extra field planted on it, an edit through the admin path, and an assertion that the field survived - with a control row that has no extra field so a green result is known to distinguish the two. Nobody has built it.
- **NO GATE** &mdash; The missing fact is not code, it is an inventory. No list exists of third-party tools that store extra fields on subjects or roles, and nothing in this repository can produce one. That inventory decides whether the narrower repair - delete only the derived accessToken/accessTokenDigest/digest and pass unknown fields through - is required or merely tidier.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** A verifier's review of bf/auth established that the field loss already happens on the current release, not only on the unmerged branch. Keeping the security goal of BF-17 - the derived token never reaches the database - does not require the allow-list.

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

### `BFQ-52` &mdash; BF-52 - the age plugins can only ask for their urgent alarm in one window

| | |
|---|---|
| state (claimed) | `unsettled` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-alarms` |
| semver | `patch` |
| review | maintainer - this needs a decision on intent before it needs code, exactly like BFQ-09 |
| ships to operators today | **yes** |
| register | `BF-52` |

**Blast radius.** lib/plugins/insulinage.js:92 and the same shape in cannulaage, sensorage and batteryage. One line each.

**What an operator sees.** Nightscout can remind you when an insulin reservoir, cannula, sensor or battery is overdue. The on-screen indicator turns red and stays red, which is correct. The optional PUSH reminder (a notification sent to your phone or other device) can only be requested in the single check where the age exactly equals the threshold you set - so if Nightscout restarts, or a check is skipped, or there is a gap in data at that moment, that reminder never arrives. It is not settled whether sending it once is the intended behaviour; repeating it every check would be its own problem. The push reminder is off unless you have switched it on. This is not medical advice.

**Why `patch`.** If it is a defect at all, the fix is a bug fix to an opt-in notification. The on-screen level is already continuous and does not change.

**Gates.**

- **NO GATE** &mdash; Read-derived, not reproduced. No run across a sequence of evaluations was made, and a sequence is the only thing that can show the notification is missed when a window is skipped - a single evaluation at the exact threshold sends it, which is what makes the defect invisible to a one-shot test. That run would settle the grade, and it is the instrument this item needs.
- **NO GATE** &mdash; Marked `unsettled` deliberately. One-shot may be the intent. What is not defensible is that :90 uses >= and :92 uses === without saying why, and no check anywhere asserts an intended relationship between the two.

**Evidence.**

- `docs/30-design/remedial/nightscout-backfix-register.md`

**Notes.** BF-28 masked this on insulinage for years - the level line was broken, so nobody reached the notification line. The three sibling plugins have shipped with the same shape unmasked. Any release note for BF-28 (merged to dev via #8739, arriving in 15.0.9) must get two things right - the push alarm is opt- in and off by default, and what does reach everyone is the on-screen pill, because the level is assigned outside the alerts guard.

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
| review | SECURITY. Fix shape: MAINTAINER DECISION 2026-09-21, SHAPE B - admit at connection time when the deployment's anonymous default role already permits reading, re-evaluate on subscribe, and gate delivery on api:*:read. The maintainer separately judged the shipped web client to be the only consumer of /alarm - the fact that would have argued for the strict shape - and chose B anyway, as insurance against that judgement being wrong. What was weighed: shape A required subscribed AND authorized. On the shipped `readable` default, receiving without subscribing is behaviour third-party clients have observed for five releases: the /alarm protocol is in no swagger file and nothing under docs/, so implementers had only the observed behaviour to go on. Measured, the marginal CONTENT disclosure on that default is zero - every field in all five payloads is already in treatments.json, entries.json or status.json, and notifyhash/key are sha1 over already-readable fields. So the strict version breaks non-subscribing clients for no confidentiality gain on the majority configuration, while B closes the `denied` bypass identically. Too tight and a follower app silently stops delivering hypo alarms; too loose and the bypass stays open. A second PR exists: the advisory's reporter opened one in GitHub's private advisory fork (nightscout/cgm-remote-monitor-ghsa-8849-qjp5-vrrj PR #1, based on v15.0.8) on 2026-09-18. Measured, it does NOT close the bypass: it gates on AUTHENTICATION_PROMPT_ON_LOAD rather than AUTH_DEFAULT_ROLES, so on a hardened instance with the prompt flag at its default a socket that never subscribes still receives everything; and even where it engages it never consults api:*:read, so a token granting only api:treatments:create hears every alarm while getting 401 on every REST read in the same run. A reviewer should read ghsa-8849-reporter-pr-evaluation-2026-09-21.md and decide how the two PRs are reconciled and how the reporter is credited. BF-76 is NOT part of the advisory. It was found while fixing BF-75 - the access-token branch of subscribe registered the ack handler with no permission check, so a valid token of any role could silence alarms on the instance, for a caller-chosen duration with no upper bound. Authorization is fixed; the unbounded silence duration is left open on purpose, because what a legitimately authorized client may ask for is a product decision. No automated test drives hashauth against a live socket. A human must load a `denied` instance, authenticate at the prompt, force an alarm and confirm it arrives. That is the one path the new cases do not cover. |
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

**Notes.** REPRODUCED, and every "fixed" cell is paired with a positive v15.0.7 control from the same run - four write paths across three refs, end-to-end over real HTTP and socket, with the document read back out of mongo, and v3 driven with a real JWT on all three refs. The fix is broader than either advisory claims: PUT /api/v1/treatments/, POST /api/v1/food and POST /api/v1/activity also had no purification at 15.0.7 and now do. The headline, which source-reading could not have answered: a payload a 15.0.7 server had ALREADY STORED does not fire on a patched server. At 15.0.7 the day-to-day report executed it in a real browser; at 15.0.8 and dev it renders as visible text. That is true only because the output-escaping half of the fix (da548d2a) landed alongside the purification half - had only the purifier shipped, the answer would be the opposite. Both advisories should say so. Residual sinks: none. 32 `.html(` sites on dev classified; a mechanical scan for unescaped free-text interpolation found 25 hits across 10 files at v15.0.7 and zero at v15.0.8 and dev. The internal report's sweep claim names 4 files; the shipped sweep covers 10. Sanitizer bounds: a string over the size budget is NOT passed through unsanitized - it throws RangeError and the write is REFUSED on all four paths, fail-closed. The POSSIBLE_HTML_MARKUP pre-filter is evadable, but none of the three evading forms executes at any sink on any ref, including v15.0.7 - the defence-in-depth argument the purifier's own header makes, now measured. BF-73 was filed because the XSS fix created its trigger: the new RangeError escapes uncaught to the error page. Independently reproduced against v15.0.8 - the 500 body named six absolute paths and the deployment's directory layout.

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

**Notes.** Found while building the configuration matrix that answers "were the right flags set when the five advisories were evaluated"; these two fell out of enumerating what AUTH_DEFAULT_ROLES actually gates. REPRODUCED on v15.0.8 AND dev 59430336, mongod 7.0, with both controls in the same run. BF-77: default -> notifyCount 1, title "Nightscout readable by world" (POSITIVE CONTROL, the notice does fire when it should); TREATMENTS_AUTH=off -> notifyCount 0 while anonymous read is 200 and anonymous POST /api/v1/treatments is 200 with the record stored; AUTH_DEFAULT_ROLES=denied -> notifyCount 0, correctly (NEGATIVE CONTROL, so absence in the middle row is attributable to the string compare and not to the notice being broken generally). These are documented configurations, not a bypass. BF-78, anonymous POST /api/v1/treatments: `readable careportal` 200 stored, `careportal` 401, `denied careportal` 401, `denied` 401. BF-81 was filed on the maintainer's instruction, 2026-09-21, as the shared root of the other two: the configuration surface carries two authorization-shaped settings with adjacent names - AUTH_DEFAULT_ROLES, which is the boundary, and AUTHENTICATION_PROMPT_ON_LOAD, which is a client prompt that grants nothing - and nothing documents the difference. Its strongest evidence is that the reporter of GHSA-8849 keyed their own security patch to the wrong one. It is prose in README.md and the swagger documents, there is no branch, and the wording is a maintainer's to write.

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
| `DOC-VIEWS` | A reviewer-facing surface over the queue: three overview pages and a packet per PR | `ready-to-push` | `main` | n/a | 2 run + 3 no-gate |
| `DOC-LINKS` | Every path the programme's documents and tooling cite must resolve | `ready-to-push` | `main` | n/a | 1 run + 2 no-gate |

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
- **NO GATE** &mdash; CI is not blind to this - main.yml runs test-ci, which is ./tests/*.test.js, all 159. The gap is in the local scripts only, so the fix is a convenience fix; it matters because agents and contributors read the local scripts as the suite. Nothing can gate "a human believed the wrong thing".

**Evidence.**

- `docs/60-research/remedial/gt1-branch-inventory-2026-09-15.md`

**Notes.** test:unit is not database-free: without MongoDB it fails 6 tests (verifyauth x4, API_SECRET x2) on pristine dev. Every gate in this manifest that invokes test:unit is therefore filed as `integration`.

### `DOC-VIEWS` &mdash; A reviewer-facing surface over the queue: three overview pages and a packet per PR

| | |
|---|---|
| state (claimed) | `ready-to-push` |
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

**Notes.** Built 2026-09-16 on the maintainer's instruction: a view of progress and a place where reviewers and teammates can collaborate. Hybrid generation for the overview pages, full generation for the packets, audience the maintainer plus reviewers being recruited. The pages are built around the reviewer-load table (generated in PROGRAMME-STATUS.md): most items route to the maintainer, and the SECURITY and SAFETY rows name a kind of reviewer with no individual attached.

### `DOC-LINKS` &mdash; Every path the programme's documents and tooling cite must resolve

| | |
|---|---|
| state (claimed) | `ready-to-push` |
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

**Notes.** Non-vacuity, run 2026-09-16: three ablations, one per detection pass, each confirmed to land before its result was read. A markdown link repointed to a nonexistent name - caught. A repo-root path in this manifest reverted to its pre-move spelling - caught. doc-branch-count.js's path.join reverted to the pre-move segments - caught. Empty-root negative control via QUEUE_GATE_ROOT exits 1 rather than passing on an empty tree.

---

*End of generated view. Source: `queue/work-queue.yaml`.*
