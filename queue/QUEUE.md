<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit.py   (make queue)
  Staleness check:  python3 tools/queue/emit.py --check

  Every edit to this file will be destroyed by the next `make queue`. Edit the
  YAML instead. The reason this file is generated at all is that a
  hand-maintained `state` column is an ASSERTION, and this programme has been
  bitten repeatedly by assertions that read like measurements.

  Even here, `state` is only a CLAIM about what the gates will say. The
  measurement is `make queue-status`, which runs them.
  ============================================================================
-->

# Work queue

Generated from `queue/work-queue.yaml` by `tools/queue/emit.py`. **Do not hand-edit.**

- Manifest schema version: `1`
- Measured at: 2026-09-15
- Measured against cgm-remote-monitor-official: `a8888f0d`
- Measured against main_repo_head: `75c38a17`

One queue spans every programme on purpose, so that a tenancy task colliding with a release train is visible in one place. The `parcel` field does the separating.

## Totals

| | count |
|---|---|
| items | 74 |
| runnable gates | 116 |
| explicit `no-gate:` markers | 107 |

A `no-gate:` marker is not a gap in the bookkeeping; it is the bookkeeping. It records that nobody has yet built a way to measure the property, and it carries the reason. 107 of the 223 gate slots in this queue are in that state, which is the honest shape of the programme today.

### Claimed state (NOT a measurement -- run `make queue-status`)

| state | n | ids |
|---|---|---|
| `not-started` | 34 | RT-VERSION, RT-4, BFQ-10, BFQ-04, BFQ-21, BFQ-19, BFQ-22, BFQ-23, BFQ-25, BFQ-24, BFQ-26, BFQ-27, BFQ-18, BFQ-20, BFQ-CAP01, T30-RESEARCH, T30-SCHEMA, T30-WIRING, T43, T44, A7A-3, A7A-4, SEAM-REFRESH, DOC-SEQUENCING, DOC-PLAN, DOC-REGISTER, DOC-EXPOSURE, DOC-MEMORY, DOC-LAYOUT, DOC-TESTSCRIPTS, BFQ-40, BFQ-MINIMED, BFQ-CAP02, FU-HYGIENE |
| `gate-not-met` | 11 | P0-B, RT-REBASE, BFQ-41, BFQ-CONNECTOR, BFQ-46, BFQ-ENV, BFQ-67, RT-CONNECT-PIN-CUTS, RT-NODE-FLOOR-TESTED, RT-BOOTERROR, FU-RESIDUALS |
| `ready-to-push` | 3 | P0-C, P0-C-REMEDIATE, P0-TAG |
| `blocked` | 12 | P0-PIN, P0-LOCK, RT-1, RT-2, RT-3, RT-5, T31-REM, T32-REM, T33-REM, A7A-GATE, BFQ-66, FU-LIMIT |
| `in-flight-upstream` | 8 | P0-A, P0-D, P0-E, P0-F, P0-G, P0-H, P0-I, P0-T01 |
| `needs-decision` | 3 | RT-D3, RT-0, BFQ-47 |
| `unsettled` | 3 | BFQ-09, A7A-7, BFQ-52 |

### Reaches an operator on today's release

The register's `§1` vs `§1b` distinction, carried as `ships_to_operators_today`. Preserving it is the only thing that makes the register mean anything.

- **BFQ-09** BF-09 - socket dedup truthiness skips a falsy value
- **BFQ-10** BF-10 - mongod fatal-asserts at Docker's default nofile=1024
- **BFQ-04** BF-04 - extract the v1 operator allowlist out of the seam
- **BFQ-CAP01** CAP-01 - Nightscout cannot be served from a sub-path
- **BFQ-40** BF-40 - $exists is not read as a boolean, before OR after bf/coercion
- **BFQ-41** BF-41 - a reading dated ahead of the clock silences the stale-data alarm
- **BFQ-CONNECTOR** BF-42, BF-43 - master pins the leaking connector, with a violated axios override
- **BFQ-MINIMED** BF-44, BF-45 - the two MiniMed ingestion divergences
- **BFQ-46** BF-46 - eleven API v3 variables bypass env.js, one family deletes data
- **BFQ-47** BF-47 - an ordinary subject edit destroys stored fields, on today's release
- **BFQ-ENV** BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies
- **BFQ-52** BF-52 - the age plugins can only ask for their urgent alarm in one window
- **BFQ-67** BF-67 - an alarm threshold is quietly changed and only the server log says so

---

## Phase 0 backfixes - ships to every existing operator

`parcel: phase0` &mdash; 17 items

Ten branches prepared locally against origin/dev a8888f0d, plus the connector
tag and the lockfile that deliberately was not regenerated. No tenancy
decision is required by any of them.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `P0-A` | bf/alarms - PR #8739, BF-28, BF-29, BF-31 | `in-flight-upstream` | `bf/alarms` | major | 9 run + 3 no-gate |
| `P0-B` | bf/cache - T0.2 and T0.3 read-path cost | `gate-not-met` | `bf/cache` | patch | 4 run + 1 no-gate |
| `P0-C` | bf/auth - BF-17 plaintext token, BF-30 throttle key | `ready-to-push` | `bf/auth` | major | 5 run + 2 no-gate |
| `P0-C-REMEDIATE` | Operator remediation for tokens already stored in plaintext - text, not tooling | `ready-to-push` | `-` | n/a | 1 run + 2 no-gate |
| `P0-D` | bf/coercion - PR #8737, query filter typing (T0.5) and the $exists inversion | `in-flight-upstream` | `bf/coercion` | minor | 7 run + 1 no-gate |
| `P0-E` | bf/reads - PR #8738, six read-path fixes, independent of bf/coercion | `in-flight-upstream` | `bf/reads` | major | 10 run + 5 no-gate |
| `P0-F` | fix/connect-timer-jitter - PR #68, BF-34 backoff precedence and start jitter | `in-flight-upstream` | `fix/connect-timer-jitter` | minor | 3 run + 2 no-gate |
| `P0-G` | bf/food - PR #8735, BF-16 quick-pick filter, BF-35 bolus calculator chooser | `in-flight-upstream` | `bf/food` | minor | 6 run + 1 no-gate |
| `P0-H` | bf/merge - PR #8734, BF-36 client delta merge reads past the end | `in-flight-upstream` | `bf/merge` | patch | 5 run + 2 no-gate |
| `P0-I` | bf/parms - PR #8736, BF-37, BF-38, BF-39 | `in-flight-upstream` | `bf/parms` | patch | 6 run + 1 no-gate |
| `P0-TAG` | nightscout-connect release/v0.0.14 and tag - prepared, needs a human push | `ready-to-push` | `release/v0.0.14` | minor | 5 run + 1 no-gate |
| `P0-PIN` | bf/connect-pin - move dev's connector pin to the v0.0.14 tarball | `blocked` | `bf/connect-pin` | patch | 3 run + 1 no-gate |
| `P0-LOCK` | Regenerate package-lock.json after the v0.0.14 tag is pushed | `blocked` | `bf/connect-pin` | n/a | 2 run |
| `P0-T01` | T0.1 - PR #8733, the two quadratic treatment scans | `in-flight-upstream` | `fix/quadratic-treatment-processing` | patch | 1 run + 1 no-gate |
| `FU-LIMIT` | Follow-up 2 - the limit rule is written twice, and that is the root cause | `blocked` | `-` | patch | 2 run + 1 no-gate |
| `FU-RESIDUALS` | Follow-ups 3, 4, 7 - three named residuals beside branches already prepared | `gate-not-met` | `-` | patch | 3 run + 1 no-gate |
| `FU-HYGIENE` | Follow-ups 9, 10 - the two audits that have no instrument | `not-started` | `-` | n/a | 0 run + 2 no-gate |

### `P0-A` &mdash; bf/alarms - PR #8739, BF-28, BF-29, BF-31

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/alarms` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-alarms` |
| semver | `major` |
| review | maintainer, plus one reviewer who has never merged their own PR in this stack (the governance finding - 100 self-merged PRs, zero human reviews). OPENED 2026-09-16 as PR #8739, base dev. THIS ONE NEEDS AN EXPLICIT YES, not only a review: it starts an alarm that has never fired in any deployment, with no grace period, and it removes per-request locale from two HTTP endpoints with no replacement. Dropping 5dcf783f leaves a clean minor, which is the option to offer if Phase 0 should land as 15.1.0. |
| register | `BF-28`, `BF-29`, `BF-31` |

**Blast radius.** 3 commits. lib/plugins/insulinage.js, lib/plugins/index.js, lib/api/googlehome/index.js, lib/api/alexa/index.js. Zero file overlap with any other Phase 0 branch.

**What an operator sees.** Three alarm fixes. The "insulin reservoir change overdue" reminder could never appear at all and now can. If you list a plugin by its file name in ENABLE - for example "cannulaage" instead of "cage" - Nightscout used to switch it off without telling you, and now says so and names the plugin it thinks you meant. These do not change when any alarm fires, only whether it can. This is not medical advice; if an alarm you rely on has been silent, talk it through with your care team as well as checking your settings.

**Why `major`.** GT4: the third commit REMOVES per-request locale handling from POST /api/v1/alexa and POST /api/v1/googlehome. A request carrying request.locale used to be answered in that language and now is answered in the server's configured language. The removal is correct - ctx.language.set and moment.locale are process-global, so one request re-languaged every later request - but it is a capability removal on an HTTP endpoint with no replacement in the same changeset.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/alarms`
  - bf/alarms has not fallen behind origin/dev
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/alarms >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[unit]` _(cwd: `externals/work/crm-bf-alarms`)_ `TEST=insulinage npm run test-single`
  - BF-28, measured. 5 passing, and E3 ABLATED it - with lib/plugins/insulinage.js put back to origin/dev the same file gives 3 passing / 2 failing. Database-free: re-run with the mongo URL pointed at a dead port, still 5 passing.
- `[unit]` _(cwd: `externals/work/crm-bf-alarms`)_ `TEST=plugins npm run test-single`
  - BF-29, measured. 13 passing, and E3 ABLATED it - with lib/plugins/index.js put back to origin/dev the same file gives 5 passing / 8 failing. Database-free.
- `[integration]` _(cwd: `externals/work/crm-bf-alarms`)_ `TEST=api.alexa npm run test-single`
  - BF-31, the branch's own test for the locale removal. 4 passing, MEASURED 2026-09-16 - the previous text here said it CANNOT BE RUN IN THIS ENVIRONMENT because nothing listened on port 27034. That was a fact about the machine and it was fixed by starting a mongod on 27034, not by changing the branch. ABLATED: lib/api/alexa/index.js restored to origin/dev gives 3 passing / 1 failing.
- `[integration]` _(cwd: `externals/work/crm-bf-alarms`)_ `TEST=api.googlehome npm run test-single`
  - BF-31's sibling. 2 passing, MEASURED 2026-09-16 on the same mongod. ABLATED: lib/api/googlehome/index.js restored to origin/dev gives 1 passing / 1 failing.
- **NO GATE** &mdash; THE GATE THAT WAS HERE - `npm run test:unit` - ASSERTED LESS THAN IT LOOKED LIKE. It resolves to a 44-file brace list, it needs MongoDB (verifyauth x4 and API_SECRET x2 fail without it even on pristine dev), and tests/api.alexa.test.js and tests/api.googlehome.test.js - two of the four files this branch adds - are in NEITHER local script, so it never ran half the branch's own evidence. CI's `test-ci` runs all 159 files and does cover them; a gate that mirrors the local script is weaker than CI, not equal to it.
- `[static]` `test -f externals/work/crm-bf-alarms/node_modules/.cache/_ns_cache/public/js/bundle.app.js`
  - GT1 found this worktree is the only one missing the client bundle, and that absence produced a seventh test failure that looked like a defect. `npm run bundle` in that worktree fixes it.
- **NO GATE** &mdash; Nothing exercises the ENABLE warning through a booted plugin registry. GT4 had to hand-reconstruct the plugin-name list to test it, and a reconstructed registry is not the registry. Needs a boot-level test.
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/alarms | grep -q 5dcf783fdbb20188c378d79121dcbe860425eede`
  - the branch behind PR #8739 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
- **NO GATE** &mdash; Review and merge state of PR #8739 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8739`
  - the live body of PR #8739 still matches the file it was posted from. Bodies drift in one direction - a correction gets written into the file first - and the only previous record that one was owed was a sentence in a notes: field, which is what let #8738 stay wrong in public for a day. It does NOT measure whether the body is TRUE: parity with a wrong file is still parity, and every figure in these bodies has been wrong at least once. NON-VACUITY, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/60-research/bf28-29-31-alarm-delivery-2026-09-15.md`
- `docs/30-design/phase0-pr-sequencing-2026-09-15.md`
- `docs/30-design/nightscout-backfix-register.md`

**Notes.** THE TWO INTEGRATION GATES ARE NOW MEASURED, 2026-09-16, AND THE CAVEAT IS THE SAME SHAPE AS THE BUNDLE GATE'S. api.alexa and api.googlehome had never been run anywhere in this programme - the branch's own evidence for BF-31, the commit that grades it major, was unexecuted. Nothing was listening on port 27034, which crm-bf-alarms' my.test.env names. A mongod was started on 27034 with a scratch dbpath and both gates went green (4 and 2 passing), each ablated against origin/dev (3/1 and 1/1 failing). THAT MONGOD IS NOT PERSISTENT: its dbpath is under this session's scratchpad and it dies with the machine. Anyone who sees these two gates red should check for a listener on 27034 before reading it as a regression - green here is a property of the branch AND of a running database, and only the first half travels. --- Sequencing letter A. §7a items 5 and 6 are these commits; neither may be read as making alarms safe to turn on under TENANCY_MODE=multi. STATE CORRECTED 2026-09-15 from ready-to-push to gate-not-met, by the manifest's own definition: a declared gate fails. The failing gate is the client-bundle check, and what it catches is a LOCAL worktree artifact, not a defect in the branch - crm-bf-alarms is the only worktree missing node_modules/.cache/_ns_cache/public/js/bundle.app.js, and that absence is what produced the seventh test failure GT1 had to rule out by hand. `npm run bundle` in that worktree clears it. The branch CONTENT is ready; this entry is not a doubt about the three commits. It was not fixed here because crm-bf- alarms belongs to another session and rule 5 forbids writing into a worktree this session did not create. RESOLVED 2026-09-16 on the maintainer's instruction: `npm run bundle` was run in crm-bf-alarms (webpack exit 0, 1.76 MB artifact), the gate passes, and the state is back to ready-to-push with all 5 runnable gates green. No commit was needed and the worktree is still clean - the artifact is build output under node_modules, not tracked content. CAVEAT ON WHAT THIS GATE MEASURES: it tests for a LOCAL build product, so it goes red again in any fresh worktree or after `npm ci`, and green here is NOT a property of the branch. Anyone who sees it red elsewhere should run `npm run bundle` before reading it as a regression.

### `P0-B` &mdash; bf/cache - T0.2 and T0.3 read-path cost

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `bf/cache` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-cache` |
| semver | `patch` |
| review | maintainer |
| register | `BF-06`, `BF-07` |

**Blast radius.** 2 commits at 4f86bab1, 6 files, +385/-8. lib/server/cache.js, lib/data/dataloader.js, lib/api/entries/index.js, plus three test files. NOTE the dataloader path - this entry said lib/server/dataloader.js, which does not exist; the file is lib/data/dataloader.js.

**What an operator sees.** Pages that read recent glucose values get faster. Nothing you see changes value or meaning.

**Why `patch`.** performance only; no declared surface moves.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/cache`
  - bf/cache has not fallen behind origin/dev
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/cache >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[integration]` `node tools/queue/gates/t02-read-ratio.js`
  - T0.2's stated gate, RUN LIVE, AND IT IS MET - an untyped /api/v1/entries read must come within 2x of a typed one at count=10, and it is 0.7x. It is carried beside the T0.3 gate on purpose: that one is red and this one is green, and an item showing only the failure would misrepresent this branch as much as one showing only the win. NON-VACUITY IS STRUCTURAL: the harness reads lib/api/entries/index.js out of the worktree and names the shape it found - clone-then-slice on dev, slice-then-clone on the branch. Measured 2026-09-16: dev FAILS at 42.3x, the branch PASSES at 0.7x, so it distinguishes them. SKIPS when the worktree has no node_modules.
- `[integration]` `node tools/queue/gates/t03-cycle-clone-budget.js`
  - T0.3's stated gate, RUN LIVE, AND IT IS RED ON PURPOSE - the budget is under 1 ms and the three cycle calls are 2.66. THE MARKER THAT WAS HERE SAID THIS COULD NOT BE RE-RUN, because "the workload that produced those two figures is not recorded anywhere in this repository". That was FALSE when it was written: docs/60-research/t02-t03-cache-clone-2026-09-15.md §2 names the harness (tools/mt-bench/apitier.js, arm `cycle`) and the fixture - 576 entries, 600 treatments of which 361 survive retention, 576 device statuses with 72-point prediction arrays, DEVICESTATUS_DAYS=2 - and §10 gives the command. The cost of the wrong marker was that queue-status printed CLAIM UNBACKED on this item: the state said gate-not-met while every runnable gate passed and the failing property hid behind a marker nobody could run. RE-MEASURED 2026-09-16 on Node v24.15.0: branch 2.656 ms against a recorded 2.657, origin/dev 3.929 against a recorded 3.747 - ordinary variance on a timing bench, same direction and magnitude. NON-VACUITY IS STRUCTURAL: the harness reads the live call sites out of the worktree and prints them (dev entries=insertData, branch entries=insertDataRef) and throws on a tree it cannot recognise, so it cannot report the branch's number for dev's code. Reproduced anyway - --budget 5 passes, proving it can go green. SKIPS when the worktree has no node_modules.
- **NO GATE** &mdash; The 98% of the remaining cost is devicestatus, whose caller rewrites fields in place. Taking it needs proof that nothing in the plugin tier writes to a device-status document. A grep is not that proof when the failure mode is a field silently vanishing from every API read served out of the cache. There is no test that would catch it.

**Evidence.**

- `docs/60-research/t02-t03-cache-clone-2026-09-15.md`
- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`
- `tools/mt-bench/apitier.js`

**Notes.** READ THE CLAIM UNBACKED WARNING ON THIS ITEM CAREFULLY - IT MEANS SOMETHING DIFFERENT NOW. Both performance targets are gated as of 2026-09-16, but both gates run a benchmark, so they are kind: integration and `make queue-status` SKIPS them unless you pass INTEGRATION=1. In a default run every gate that executes passes and the runner therefore still prints CLAIM UNBACKED. With INTEGRATION=1 the item is 3/4 and the red gate is the T0.3 budget, which is the honest picture: T0.2 met, T0.3 not. Run `make queue-status ID=P0-B INTEGRATION=1` before drawing any conclusion from this row. --- Sequencing letter B. T0.2 passed its gate (0.837 -> 0.025 ms, asserted identical over HTTP). T0.3 did not. A dead `mills` write at dataloader.js:203 was found and removed with a test that goes red if it returns.

### `P0-C` &mdash; bf/auth - BF-17 plaintext token, BF-30 throttle key

| | |
|---|---|
| state (claimed) | `ready-to-push` |
| repo | `cgm-remote-monitor` |
| branch | `bf/auth` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-auth` |
| semver | `major` |
| review | SECURITY - a human security reviewer first, before any other Phase 0 branch. This is the one the sequencing document singles out. |
| register | `BF-17`, `BF-30` |

**Blast radius.** 2 commits. lib/authorization/endpoints.js, storage.js, delaylist.js, index.js, lib/admin_plugins/subjects.js.

**What an operator sees.** Two security fixes. Editing a subject through the admin page used to write that subject's API access token into the database in readable form, which turned read access to your database into API access; it no longer does. IMPORTANT: tokens already written that way are still in your database - fixing the code does not remove them. Brute-force slowdown on failed logins was keyed on a value the caller could choose, so it never engaged; it now is. Existing access tokens keep working - they are re-derived on every load and are not invalidated by this change.

**Why `major`.** GT4: beyond the two fixes, the branch narrows lib/authorization/storage.js to write only an allow-list of fields (name, roles, notes, created_at), so any field a third-party admin tool has stored is dropped on the next edit with NO error. It also adds `notes` to the GET /api/v1/subjects response. The throttle change alone would be minor - the sleep moved to the failure path, so no request that authenticates is delayed by another client's failures behind a shared proxy.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/auth`
  - bf/auth has not fallen behind origin/dev
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/auth >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[static]` _(cwd: `externals/work/crm-bf-auth`)_ `grep -nE "console\\.log\\('Loading',[[:space:]]*opts\\)" lib/authorization/storage.js && exit 1 || exit 0`
  - BF-05's unfixed sibling, a TRACKING gate: it is meant to FAIL while the residual is present, and the describe it replaces said so in as many words. IT DID NOT FAIL. The pattern was `console.log('Loading', opts)` with a space after the comma; the code at storage.js:113 has NO space, so the grep never matched, the `|| exit 0` arm fired, and P0-C reported 3/3 PASS on a property that is false. The pattern is now whitespace-tolerant and this gate is red, which is the honest reading. DO NOT loosen the pattern again. SETTLED 2026-09-16: of the two ways to green this gate offered, the maintainer chose the first - the one-line removal was taken onto bf/auth as commit 56ed29d2, and the gate is green because the residual is gone, not because the pattern was weakened. The gate stays as a regression guard.
- `[integration]` _(cwd: `externals/work/crm-bf-auth`)_ `TEST=authdelay npm run test-single`
  - BF-30, the branch's OWN test, which `npm run test:unit` never ran - tests/authdelay.test.js matches neither local brace list and is one of the 52 files only CI's `test-ci` reaches. 11 passing with MongoDB up on 27031. E3 ABLATED it: with the seven changed lib files put back to origin/dev and lib/server/peer-address.js removed, 2 passing / 9 failing. Needs the database (6 passing / 1 failing against a dead port), so it is integration and honestly so.
- `[integration]` _(cwd: `externals/work/crm-bf-auth`)_ `TEST=authsubjects npm run test-single`
  - BF-17, same story: not in either local script, 8 passing with MongoDB, and 1 passing / 7 failing under the same ablation.
- **NO GATE** &mdash; `npm run test:unit` was here and was recorded as "361 passing / 0 failing at GT1's measurement". That number is not evidence for this branch: the 44-file brace list contains NEITHER of the two test files bf/auth adds, so the suite could pass in full with every one of these fixes reverted.
- **NO GATE** &mdash; Nothing here checks that the plaintext tokens ALREADY written into existing databases get cleaned up, and nothing will: the code fix does not remove them, there is no migration, and as of 2026-09-16 there deliberately is no detector script either. What DOES exist is measured next door - P0-C-REMEDIATE's gate checks that this branch's PR body and the release notes tell an operator the truth about it, including that a rename is not a rotation. Read that item before signing this one off; this marker is the honest half of the pair.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** Sequencing letter C. GT3 also found BF-17's created_at residual: the pick() at endpoints.js:44 is ['_id','name','accessToken','roles','notes'] - notes was added by the fix, created_at was not. RESOLVED 2026-09-16: commit 56ed29d2 removes the leftover console.log('Loading',opts), the last failing gate, and all 3 runnable gates now pass. That line was NOT introduced by this branch - it is on origin/dev at storage.js:84 - and it was taken here rather than left to FU-RESIDUALS because it sits in a file this branch already rewrites and is the same defect class as the count-path filter leak fixed on bf/reads: a per- request debug print of request-derived values. FU-RESIDUALS follow-up 4 is carried BY THIS BRANCH and should not be fixed there a second time - but it is NOT yet closed on dev, and FU-RESIDUALS' gate correctly still fails, because that gate reads origin/dev and the repair only exists on bf/auth until this merges. Same convention as the register's `fixed`: repaired on a branch, not merged. THE REAL RISK ON THIS ITEM, RESTATED 2026-09-16: both no-gate markers still stand and green gates here still do not mean an operator is safe - tokens written in plaintext before the upgrade are untouched by it. What changed is that the remediation is no longer unwritten. P0-C-REMEDIATE is settled as TEXT, not tooling: no detector and no migration, the rotation instructions carried by this branch's PR body and the 15.0.9 release notes, and a gate guarding what they say. That review found the instructions were WRONG - they listed renaming a subject as a rotation, which it is not, because the matcher is name-independent. Corrected. So the sentence a reviewer needs when this PR goes up is not "remediation is missing" but "remediation is a note, the note was wrong once, and here is the gate that says it is right now".

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

**What an operator sees.** If you have ever edited a subject through the admin page, a readable copy of that subject's API access token is sitting in your database. Upgrading does not remove it - it clears for a subject only when you next save that subject through the admin page, and clearing the copy does not retire the token. There are exactly TWO ways to retire an exposed token: delete and recreate the subject, or change API_SECRET. RENAMING THE SUBJECT IS NOT ONE OF THEM, even though the token's appearance changes. Anyone who has had read access to your database since the first edit could have used that token.

**Why `n/a`.** not a code change to the shipped surface

**Gates.**

- `[static]` `node tools/queue/gates/bf17-remediation-note.js`
  - 17 checks. The deliverable here is PROSE, and prose was exactly what went wrong: the 15.0.9 release notes listed "rename the user" as one of three ways to change an exposed token, and so did report 2.3, which they were written from. A rename is cosmetic - checkToken keeps the LAST dash-segment of the presented token and matches it against subject.digest, which is getSubjectHash(subject._id); the name reaches only the abbrev at the front, which is never read back. An operator who renamed and stopped would believe a leaked credential was retired while it still authenticated. The gate pins the CODE property on origin/dev AND the bf/auth worktree, so the prose cannot drift from it in either direction, then checks each of the four documents for what must be said and for the retracted sentences. NON-VACUITY, reproduced 2026-09-16 before the gate was committed: restoring the rename row to the release notes -> 1 failing; restoring the PR body's "discarded when Nightscout next loads it" -> 2 failing; restoring the rename option to report 2.3 -> 1 failing; empty QUEUE_GATE_ROOT -> 17 failing.
- **NO GATE** &mdash; NO DETECTOR SCRIPT, BY DECISION (maintainer, 2026-09-16). The earlier marker here asked for a script reporting how many subject rows carry a non-derived accessToken. It was not written and will not be. The reasoning, recorded so it is not rediscovered as a gap: a count is not remediation - remediation is rotation, and rotation is an operator decision no script can take. The per-operator form of the same question is one query, and it is already written out in the PR body ("look in your auth_subjects collection for any document with an accessToken, accessTokenDigest or digest field"). A fleet-wide count has no consumer. THE RESIDUAL THIS LEAVES, STATED PLAINLY: an operator who never re-saves a previously-edited subject keeps a plaintext row indefinitely and nothing prompts them. The release notes now say so in as many words.
- **NO GATE** &mdash; NOTHING MEASURES WHETHER AN OPERATOR ACTS. This item ships words. No gate in this repository can show that a single exposed token was rotated, and none should claim to.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`
- `docs/60-research/bf17-bf30-auth-defects-2026-09-15.md`
- `releases/cgm-remote-monitor-15.0.9/release-notes.md`
- `reports/phase0-pr-bodies/bf-auth.md`

**Notes.** SETTLED 2026-09-16. This item was not-started for as long as it existed, on the strength of one sentence in the register's BF-17 row - "existing rows still hold tokens, see the report" - which nothing acted on. It is now closed as TEXT rather than tooling: the maintainer decided against a detector script and against a migration, on the ground that the notes carry the operator's actual decision and a script does not. WHAT THE REVIEW TURNED UP WHILE CLOSING IT, and the reason the item was not simply deleted: the notes were WRONG. Two operator documents told people that renaming a subject retires its token. It does not - measured at lib/authorization/storage.js:326 on bf/auth and :288 on origin/dev, the matcher is name-independent - and a third document, the report those notes were written from, is where the error came from. A fourth claim, that the upgrade discards the stored copy on load, was also wrong: reload() deletes the derived fields from the IN-MEMORY record only, and the row clears when the subject is next saved through the admin path. All four are corrected and the gate above is the regression guard. THE LESSON IS THE ITEM'S REAL OUTPUT: "the deliverable is a note" is not a reason to leave it ungated. The note was the defect.

### `P0-D` &mdash; bf/coercion - PR #8737, query filter typing (T0.5) and the $exists inversion

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/coercion` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-coercion` |
| semver | `minor` |
| review | maintainer. OPENED 2026-09-16 as PR #8737, base dev. The old text here said "lands first of the stack so the query path settles"; there is no stack, and the branch merges clean against dev and against all eight others. Three things a reviewer cannot get from the diff: the classification is minor and rests on no request that worked ceasing to work; `tests/query.operands.test.js` matches neither local brace list, so a green `npm run test:unit` is evidence for the typing fix and none for BF-40; and the composition with bf/reads is a property of the PAIR, not of either diff, and is deliberately in neither PR. |
| register | `BF-02`, `BF-03`, `BF-11`, `BF-32`, `BF-40`, `BF-68` |

**Blast radius.** 2 commits at b7234753, the largest change in the set. lib/server/query.js plus a generated coercion table over 5 collections; 158 coercions replace 13 hand- written entries.

**What an operator sees.** Searches through the API that filter on a number used to compare that number against text, so many of them quietly matched nothing and still answered "OK". They now compare correctly. If you have a saved search, a script or a third-party app that was returning nothing, it may start returning results - that is the fix working, not a new problem. SEPARATELY, and this is the one most likely to have been acted on: asking the API for records that do NOT have a field - $exists=false - returned exactly the records that DO have it, with a success code and nothing to say the answer was inverted. Any report, dashboard or script filtering on $exists=false was answering the opposite question, and a count from one was counting the wrong group. Re-run anything built on one; the set it returns now is the complement of what it returned before. $exists=true was correct before and is correct after.

**Why `minor`.** GT4 measured the change in answers: find[duration][$gte]=30 goes from {"$gte":"30"} (matched nothing) to {"$gte":30}; find[insulin][$gte]=1.5 from {"$gte":1} to {"$gte":1.5}; find[sgv][$exists]=true from {"$exists":NaN} (which returned the documents that LACK the field) to {"$exists":"true"}. No request that worked stops working.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/coercion`
  - bf/coercion has not fallen behind origin/dev
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/coercion >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[unit]` _(cwd: `externals/work/crm-bf-coercion`)_ `TEST=query.operands npm run test-single`
  - BF-40's own test, 12 cases, on the second commit. In NEITHER local brace list (GT1), so a green `npm run test:unit` is not evidence for it. Ablated three ways with each break confirmed to land: removing the call fails 6, mapping "" to false fails exactly the test pinning that decision, adding $regex to the reader map fails exactly the $regex test.
- `[unit]` _(cwd: `externals/work/crm-bf-coercion`)_ `TEST=query npm run test-single`
  - 29 passing, database-free (measured against a dead mongo port). E3 RE-ABLATED it properly: GT1's control was "the file cannot even LOAD against pristine dev", which is a module-resolution failure, not a behavioural one. Reverting ONLY lib/server/query.js and keeping the new table gives 24 passing / 4 failing on assertions ("expected '1.5' to be 1.5"), which is the control that means something.
- `[static]` `T=$(mktemp -d) && trap 'rm -rf "$T"' EXIT && python3 -m tools.nsschema.emit.coercion_emit --bundle "$T/emitted.json" >/dev/null && diff -q "$T/emitted.json" externals/work/crm-bf-coercion/lib/server/query-coercion.json`
  - House style is "emit, then check the emission", and THE GATE THAT WAS HERE DID NOT CHECK IT. `coercion_emit --drift` ends in `return 0` unconditionally: E3 ran it and it exited 0 while printing "DRIFT vs the shipping walkers: 157 disagreements". It also compares against a HARDCODED transcription of origin/dev's walkers, so it says nothing about bf/coercion at all and would have exited 0 with the branch deleted. What is gateable is the emission itself: the table vendored into the branch must be byte-identical to what the emitter produces today, or the branch is shipping a stale generated file.
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/coercion | grep -q b72347538ba29f965c531bdd47f81dc52d895a13`
  - the branch behind PR #8737 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
- **NO GATE** &mdash; Review and merge state of PR #8737 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8737`
  - the live body of PR #8737 still matches the file it was posted from. Bodies drift in one direction - a correction gets written into the file first - and the only previous record that one was owed was a sentence in a notes: field, which is what let #8738 stay wrong in public for a day. It does NOT measure whether the body is TRUE: parity with a wrong file is still parity, and every figure in these bodies has been wrong at least once. NON-VACUITY, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `tools/nsschema/emit/coercion_emit.py`
- `docs/30-design/nightscout-backfix-register.md`

**Notes.** Sequencing letter D. BF-03 is closed for devicestatus and profile only - `food` reaches query.js at no point and `activity`'s model has no numeric field, so those two halves were misfiled rather than fixed.

### `P0-E` &mdash; bf/reads - PR #8738, six read-path fixes, independent of bf/coercion

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/reads` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-reads` |
| semver | `major` |
| review | maintainer. OPENED 2026-09-16 as PR #8738, base dev. NOT after P0-D - the stack is dissolved and the two branches merge cleanly with each other. Three things a reviewer cannot get from the diff: it is graded major on one commit only (06b133a7, the ?count= tightening, which is app.use'd ahead of every v1 router and so covers writes); none of the five test files is in `npm run test:unit`, so a green run there is evidence for none of the six fixes; and ?count=0 answered TWO different ways on dev depending on whether the runtime cache could serve the request - see notes. maintainer. NOT after P0-D - the stack is dissolved and the two branches merge cleanly with each other. |
| register | `BF-01`, `BF-05`, `BF-13`, `BF-14`, `BF-15`, `BF-33` |

**Blast radius.** 6 commits at 2ecfeb53, all its own, based directly on origin/dev. lib/server/aggregate.js, entries.js and four siblings, lib/api3/generic/search/input.js, lib/api3/shared/fieldsProjector.js, lib/api3/generic/collection.js, lib/server/count.js, lib/api/index.js.

**What an operator sees.** Six fixes to how the API answers read requests. Counting entries that matched a filter returned nothing at all; paging through results could skip or repeat records; asking for a nested field returned an empty answer; and three different ways of asking for "no limit" returned the entire collection instead. CHANGE YOU MAY NOTICE: six spellings of ?count= that used to be accepted now return an error instead of a surprising answer - count=0, count=0x10, count=2.5, count=-3, count=1e2 and count=abc. If a script of yours uses one of those, it will now fail loudly instead of quietly returning the wrong number of records.

**Why `major`.** GT4: six previously-accepted ?count= spellings now return 400, not two, and the validator is app.use'd on the WHOLE v1 app before every router - so it covers /treatments, /profile, /devicestatus, /notifications, /activity, /food, /status, /alexa, /googlehome, and WRITES as well as reads. A POST /api/v1/treatments?count=0 now returns 400 where it previously succeeded. The branch CHANGELOG lists read routes only.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/reads`
  - bf/reads has not fallen behind origin/dev. THIS REPLACES an is-ancestor check on bf/coercion. The two-deep stack existed only to resolve a CHANGELOG collision; the CHANGELOG edits were stripped by the maintainer's instruction and bf/reads was re-cut directly onto dev, so the old gate now measures a fact that is deliberately false.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/reads >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[static]` `node tools/queue/gates/bf-reads-read-contract.js`
  - THE GATE THAT WAS HERE was `git log --format=%H bf/reads | grep -q .`, which asserts the branch has at least one commit. The E3 audit ran it against origin/dev, origin/master and bf/alarms and it passed for all three. This replaces it with the database-free half of the branch's behaviour, driven through the four pure modules the six fixes live in: parseCount/hasCount/applyCount, the dotted-?fields= projector, the _id tiebreak in the v3 sort chain, and the count path's use of query_for with nothing printed. 8 assertions. Its own negative control is built in - `--rev origin/dev` runs the identical assertions against dev materialised from the object database and gives 4 failing.
- `[integration]` _(cwd: `externals/work/crm-bf-reads`)_ `TEST=api.count-parameter npm run test-single`
  - BF-13/BF-33, 13 passing. CORRECTION TO THE E3 BRIEF, which said this runs "in 2 seconds with no database": it needs MongoDB. Pointed at a dead port it goes to 0 passing / 1 failing, timing out in the before-all hook. It is fast only because a mongod happens to be listening on crm-bf-reads' port 27032.
- `[integration]` _(cwd: `externals/work/crm-bf-reads`)_ `TEST=api.count-where npm run test-single`
  - BF-01, 5 passing. Needs MongoDB.
- `[integration]` _(cwd: `externals/work/crm-bf-reads`)_ `TEST=api3.fields npm run test-single`
  - BF-15, 6 passing. Needs MongoDB (5 of 6 survive without it).
- `[integration]` _(cwd: `externals/work/crm-bf-reads`)_ `TEST=api3.limit npm run test-single`
  - BF-33, 8 passing. Needs MongoDB.
- `[integration]` _(cwd: `externals/work/crm-bf-reads`)_ `TEST=api3.paging npm run test-single`
  - BF-14, 3 passing. Needs MongoDB.
- **NO GATE** &mdash; THE `npm run test:unit` GATE WAS REMOVED, not downgraded. It was recorded as "361 passing / 0 failing at GT1's measurement", but not one of the five test files this branch adds is in the 44-file brace list - all five are api*/api3* and match test:integration's glob - so the suite could have passed in full with every fix reverted.
- **NO GATE** &mdash; The ordering constraint inside the branch (BF-05's commit must follow BF-01's) is not machine-checked. After the CHANGELOG strip and the re-cut onto dev the two commits are 3b588098 and 4772b983, so any gate quoting an earlier SHA is stale by construction. A real gate would assert the relative order of the two by subject line, and nobody has written it.
- **NO GATE** &mdash; The CHANGELOG on this branch lists read routes only, while the ?count= validator covers writes too. Nothing checks a release note against the code it describes.
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/reads | grep -q 2ecfeb53ff1e6121ef5f76e1f08e97af1ca6c2fa`
  - the branch behind PR #8738 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
- **NO GATE** &mdash; Review and merge state of PR #8738 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- **NO GATE** &mdash; THE TWO-PATH BEHAVIOUR OF ?count=0 IS MEASURED BUT NOT ASSERTED. tools/probes/count0-two-paths.js reproduces it - 0 rows from the cache and all 24 from the database on dev, 400 on both after this branch, with two controls that stay sane on each tree - but it PRINTS rather than exits non-zero, so it is a probe and not a gate. Making it one means deciding what the contract IS, and that is the reviewer's call on #8738, not this queue's. It also needs two worktrees and a mongod.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8738`
  - the live body of PR #8738 still matches the file it was posted from. Bodies drift in one direction - a correction gets written into the file first - and the only previous record that one was owed was a sentence in a notes: field, which is what let #8738 stay wrong in public for a day. It does NOT measure whether the body is TRUE: parity with a wrong file is still parity, and every figure in these bodies has been wrong at least once. NON-VACUITY, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/30-design/phase0-pr-sequencing-2026-09-15.md`
- `docs/60-research/gt4-semver-classification-2026-09-15.md`
- `docs/60-research/e3-gate-vacuity-audit-2026-09-15.md`

**Notes.** THE CORRECTION IS PUSHED. #8738's body carried the wrong account of ?count=0 for a day - it said the whole collection, which is true only past the runtime cache; the plain spelling returns 0 rows and is correct. Edited 2026-09-16 and the parity gate above is green. The state question this raised is settled and worth keeping: while the gate was red this item reported FAIL and the state stayed in-flight-upstream, because the manifest's gate-not-met rule was written for a red gate meaning a DEFECT IN THE CODE, and here the branch was fine and the PROSE was stale. Those are different questions and the state model does not separate them. --- MEASURED 2026-09-16, AFTER THE PR WAS POSTED, and the PR body is wrong about it: `?count=0` answered TWO different ways on dev depending on the path. With no `find`, the runtime cache served it and returned 0 rows - which is what the client asked for and is CORRECT. With a `find` that forces the read past the cache to the database, `.limit(0)` means unbounded and it returned all 24 of 24. Both measured against dev a8888f0d with 24 stored entries, controls sane (count=5 -> 5 rows, no count -> 10, the default). The read-defects report has the 24-row half and says it forced past the cache; nobody wrote down the other half, so the PR body states the unbounded answer as if it were the only one. A reviewer who tests plain `?count=0` on their own instance sees `[]` and concludes the premise is wrong. Correction prepared in the body file, NOT yet pushed to #8738. --- Sequencing letter E. THE SHA HISTORY, because three documents quote different ones: GT1 measured 824380a0 (7 commits, on dev); this queue first recorded 0d19bb31 (8 commits, on bf/coercion, after a rebase); the CHANGELOG-only commit was then dropped and the branch re-cut directly onto origin/dev, and it is now 2ecfeb53, 6 commits. `git range-diff` showed all six content-identical to their pre-strip selves. THE STACK IS DISSOLVED, so blocks_on is empty. The §3b concern survives and is NOT a merge hazard: bf/coercion gives query.js a new `collection:` option and bf/reads fixes aggregate.js, which calls query.js through api.query_for and passes no options - so the count path still gets the legacy default walker after both land. Deliberately in neither PR.

### `P0-F` &mdash; fix/connect-timer-jitter - PR #68, BF-34 backoff precedence and start jitter

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `nightscout-connect` |
| branch | `fix/connect-timer-jitter` |
| base | `b77e5bb` |
| worktree | `externals/work/nc-jitter` |
| semver | `minor` |
| review | maintainer - the sequencing document says land this one first if anything is landed first. OPENED 2026-09-16 as nightscout-connect PR #68, base dev. One approval there covers four PRs' worth of change; see notes. |
| register | `BF-08`, `BF-34` |

**Blast radius.** lib/backoff.js, lib/machines/cycle.js. 19 new tests, 135 pass / 0 fail, every part reverted in turn and caught.

**What an operator sees.** When a CGM vendor's service is refusing requests, Nightscout's connector used to retry roughly 586 times faster than it was configured to, and every account retried at the same instant. It now waits the interval it was told to wait and spreads the retries out. COUNTER-INTUITIVE: after this fix a vendor outage will look like it recovers MORE SLOWLY, because the connector has stopped retrying in a burst that could not have worked. Your data is not arriving any later than it would have; the burst was never getting through. Also, on restart the connector no longer reaches the vendor all at once - both jitter windows default to 0, so nothing changes for anyone who does not set them.

**Why `minor`.** GT4 argues for 0.1.0 rather than 0.0.14 and the argument is sound - option precedence reversed, a changed default (use_random_slot:false -> jitter:'equal'), a new throw on an unknown jitter mode, and duration_for became non-deterministic. Each is breaking for a caller. It costs nothing because ^0.0.13 matches only 0.0.13 and cgm-remote-monitor pins by tarball anyway. RECORDED AS A DISAGREEMENT, not resolved - the tag as cut says 0.0.14.

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

- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** Sequencing letter F. Merging this in the connector repository ships it to NOBODY - cgm-remote-monitor pins by tarball. P0-TAG and P0-PIN are what deliver it. PR TARGET SETTLED 2026-09-16 (maintainer): base `dev`, head `fix/connect-timer-jitter`, ONE PR carrying 11 commits. The earlier sequencing text said base `origin/main`; that was a merge-base measurement mistaken for a PR target. Measured: `origin/dev` 6dfc4f0 is TREE-IDENTICAL to `origin/main` b394411 (`git diff origin/dev origin/main` empty - main is only the merge commit of PR #26), and #64 and #67 both target `dev`, so `dev` is the release line for this batch. `git rev-list --count origin/dev..fix/connect-timer- jitter` = 11; 27 files, +1359/-309; trial merge into `dev` CLEAN. WHAT THAT ONE PR APPROVES, STATED SO IT IS NOT DISCOVERED LATER: only c1cce2a is this branch's work. Nine of the other ten commits belong to four other pull requests - #64 (OPEN, -> dev), #65 (merged into `fix/dexcom-safe-logging`, NOT into dev or main), #66 (OPEN, -> `fix/dexcom-safe-logging`), #67 (OPEN, -> dev) - plus the integration merge b77e5bb (`origin/fix/modernization-debug- logging`, no PR). So one approval covers four PRs' worth of change. The maintainer chose this over stacking on `fix/modernization-debug-logging` (which would reduce the PR to the single commit c1cce2a) with the tradeoff on the table. It is written into the PR body rather than left implicit. WHY NOT REBASE c1cce2a ALONE ONTO dev - measured, not assumed: `git cherry-pick c1cce2a` onto origin/dev CONFLICTS in three files, one hunk each (README.md, index.js, lib/builder.js); lib/backoff.js and lib/machines/cycle.js auto-merge clean. The builder.js resolution would have to DELETE `logger: config.logger`, which comes from 234d47c - i.e. the commit genuinely assumes #67 is in place, exactly as its own message says ("The precedence fix cannot ship alone"). The 135-test and per-part-ablation evidence was taken on the stacked base and would need re-taking. PR BODY CORRECTED 2026-09-16 before publication: reports/phase0-pr-bodies/fix-connect-timer-jitter.md called those nine commits "already-merged". They are not. Third draft of that block; the first two both understated what the branch carries.

### `P0-G` &mdash; bf/food - PR #8735, BF-16 quick-pick filter, BF-35 bolus calculator chooser

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/food` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-food` |
| semver | `minor` |
| review | maintainer - the sequencing document calls this the one to read first, and BF-35 is why. OPENED 2026-09-16 as PR #8735, base dev. Still wants a reviewer who has not self-merged in this stack (the governance finding), and an explicit yes on the /api/v1/food/quickpicks filter change. |
| register | `BF-16`, `BF-35` |

**Blast radius.** 1 commit. lib/client/boluscalc.js, lib/food/food.js, lib/food/quickpick.js (new), lib/server/food.js, 2 new test files.

**What an operator sees.** IMPORTANT. In the bolus calculator, choosing a quick pick could load a DIFFERENT record's food, so the carbohydrate number that went into the insulin calculation came from a record you did not choose, and nothing on screen said so. Picking the last entry in the list could throw an error, and plain foods that are not quick picks appeared in the chooser. This is fixed. Separately, quick picks saved by a JSON client, or saved before the "hidden" setting existed, were missing from the quick-pick list and now appear. If you have used the bolus calculator's quick picks, the amount it suggested may not have matched the food you selected. The calculator is a suggestion tool, not a dosing instruction - please raise this with your care team if you think a past suggestion was wrong. This is not medical advice.

**Why `minor`.** GT4: it changes an HTTP API v1 response. /api/v1/food/quickpicks goes from filtering on the literal string {hidden:'false'} to {hidden:{$nin:[true,'true']}}, so quick picks written by any JSON client, and any record saved before the field existed, start appearing. Position ordering moves from lexicographic (in-query) to numeric (in-process). Records appear that did not; none disappears.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/food`
  - bf/food has not fallen behind origin/dev
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/food >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[unit]` _(cwd: `externals/work/crm-bf-food`)_ `TEST=boluscalc.quickpick npm run test-single`
  - BF-35's own test, 11 cases. THIS IS THE GATE GT1 WARNED ABOUT: the file is in NEITHER the test:unit nor the test:integration brace list, so a green `npm run test:unit` on this branch is not evidence that BF-35's fix works. Named explicitly here for that reason.
- `[integration]` _(cwd: `externals/work/crm-bf-food`)_ `TEST=api.food.quickpicks npm run test-single`
  - BF-16 over the real HTTP path; needs MongoDB
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/food | grep -q 73495331e68c4cda3a63e8c047387bdf404b89b0`
  - the branch behind PR #8735 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
- **NO GATE** &mdash; Review and merge state of PR #8735 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8735`
  - the live body of PR #8735 still matches the file it was posted from. Bodies drift in one direction - a correction gets written into the file first - and the only previous record that one was owed was a sentence in a notes: field, which is what let #8738 stay wrong in public for a day. It does NOT measure whether the body is TRUE: parity with a wrong file is still parity, and every figure in these bodies has been wrong at least once. NON-VACUITY, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/30-design/phase0-pr-sequencing-2026-09-15.md`

**Notes.** Sequencing letter G. BF-35 is a regression from 3457de5b (2017) and was found while fixing BF-16 - which is the argument for landing BF-16 even though BF-16 itself has no in-tree consumer. PREREQUISITE DISCHARGED 2026-09-16. This item carried a blocker - the SOURCE_ASSERTIONS in tools/nsschema/code_model.py pin text bf/food deletes, so `make schema-code-drift` would fail the day the branch reached a checked tree. It is handled, and NOT the way BF-16 prescribed. The register said "replace the anchors when the branch lands"; replacing them now would fail the check against both SOURCE_ROOTS, which still carry the pre-fix text because bf/food has not merged. Instead each anchor now accepts EXACTLY the pre-fix and post-fix spelling and nothing else, and lib/food/quickpick.js isTrue went into a new SOURCE_ASSERTIONS_IF_PRESENT tuple that arms when the file appears. Measured: schema-code-drift exits 0 against crm-seam, cgm-remote-monitor-official AND crm-bf-food; crm-bf-food failed on exactly these two anchors beforehand. Ablated three ways with each break confirmed to land first - filter narrowed to `{ hidden: false }` FAILS, restoreBoolValue rewritten to Boolean() FAILS, quickpick.isTrue renamed FAILS, all three restored exits 0. STILL OWED AT MERGE, not now: delete the pre-fix arm of each anchor and promote the quickpick.js entry, or a revert passes silently.

### `P0-H` &mdash; bf/merge - PR #8734, BF-36 client delta merge reads past the end

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/merge` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-merge` |
| semver | `patch` |
| review | maintainer. OPENED 2026-09-16 as PR #8734, base dev. |
| register | `BF-36` |

**Blast radius.** 1 commit. lib/client/receiveddata.js, one new test file.

**What an operator sees.** A treatment being removed at the same time as another update arrived could make the page stop updating until you reloaded it. The clock that tells you how old the reading is runs on its own timer, so it would still have gone stale and warned you - the reading shown was never wrong, it just stopped advancing.

**Why `patch`.** availability fix in client code; no declared surface moves

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/merge`
  - bf/merge has not fallen behind origin/dev
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/merge >/dev/null`
  - trial-merge into origin/dev is conflict-free
- `[unit]` _(cwd: `externals/work/crm-bf-merge`)_ `TEST=receiveddata.merge npm run test-single`
  - in NEITHER local brace list - GT1's finding. Named here so the gate actually runs the file that proves the fix.
- **NO GATE** &mdash; `dataUpdate` still has no try/catch, so the NEXT throw from anywhere in the merge path has the same effect. This branch fixes one throw, not the missing boundary. No test asserts the boundary exists because it does not.
- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/merge | grep -q b06c6faf882ebd84d627468c75dade0fe1fd01a1`
  - the branch behind PR #8734 is on the remote at the exact tip this item was measured against. Read-only. Verified 2026-09-16.
- **NO GATE** &mdash; Review and merge state of PR #8734 is upstream's, and cannot be gated from here without a GitHub API call. Tracked, not driven.
- `[network]` `node tools/queue/gates/pr-body-parity.js --only 8734`
  - the live body of PR #8734 still matches the file it was posted from. Bodies drift in one direction - a correction gets written into the file first - and the only previous record that one was owed was a sentence in a notes: field, which is what let #8738 stay wrong in public for a day. It does NOT measure whether the body is TRUE: parity with a wrong file is still parity, and every figure in these bodies has been wrong at least once. NON-VACUITY, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** Sequencing letter H.

### `P0-I` &mdash; bf/parms - PR #8736, BF-37, BF-38, BF-39

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `bf/parms` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-parms` |
| semver | `patch` |
| review | maintainer. OPENED 2026-09-16 as PR #8736, base dev. Worth stating in the review request: classification is patch with one judgement call (the underscore decoding, see semver_reason); the BF-37 test is invisible to `npm run test:unit`, so a green run there is evidence for BF-38 and none for BF-37; and BF-39 breaks nothing live today - both token spellings return 200 - which the body says outright rather than implying a break. |
| register | `BF-37`, `BF-38`, `BF-39` |

**Blast radius.** 3 commits at eb0bc918. lib/client/browser-utils.js, lib/language.js.

**What an operator sees.** A web address with a bare option in it - anything ending in "?", or containing "&&", or a setting with no value such as "?debug" - stopped the page loading entirely, leaving only the loading message. That is fixed. Two smaller fixes go with it: a translation containing ten or more substitutions came out with a stray digit, and an access token belonging to a subject whose name contains an underscore was being corrupted in the address bar (the server was accepting it anyway, so nothing was broken for you).

**Why `patch`.** all three are bug fixes with no declared-surface movement. BF-38 is latent - no shipped catalogue uses more than %3.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/parms`
  - bf/parms has not fallen behind origin/dev
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
  - the live body of PR #8736 still matches the file it was posted from. Bodies drift in one direction - a correction gets written into the file first - and the only previous record that one was owed was a sentence in a notes: field, which is what let #8738 stay wrong in public for a day. It does NOT measure whether the body is TRUE: parity with a wrong file is still parity, and every figure in these bodies has been wrong at least once. NON-VACUITY, reproduced 2026-09-16: one altered file gives 1 failing, an empty body dir gives 6 failing. SKIPS with exit 0 when gh is unauthenticated.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** Sequencing letter I. CORRECTION: the sequencing document at line 165 lists the commits as 522c6ffb, eb0bc918, c9a7a21c mapped to BF-37, BF-39, BF-38. Re- measured, the branch order is 522c6ffb (BF-37), c9a7a21c (BF-38), eb0bc918 (BF-39). GT3 found the same.

### `P0-TAG` &mdash; nightscout-connect release/v0.0.14 and tag - prepared, needs a human push

| | |
|---|---|
| state (claimed) | `ready-to-push` |
| repo | `nightscout-connect` |
| branch | `release/v0.0.14` |
| base | `v0.0.13@b394411` |
| worktree | `externals/nightscout-connect` |
| semver | `minor` |
| review | maintainer - pushing the tag is the deliberate human act; the connector repository has no release workflow, so the tag publishes nothing by itself |
| register | `BF-08`, `BF-34` |
| blocks on | `P0-F` |

**Blast radius.** 11 commits, 29 files, +1362/-312, of which 887 lines are new test files. b394411 FAST-FORWARDS to 649a7de.

**What an operator sees.** A new version of the CGM connector. See P0-F for what changes in behaviour.

**Why `minor`.** see P0-F. GT4 argues the version should be 0.1.0; the tag as cut says 0.0.14. UNRESOLVED and deliberately left visible.

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
- **NO GATE** &mdash; Whether all seven connector commits are the RIGHT content for a release is a release-content decision, not a mechanical bump, and it is the maintainer's. Nothing can gate it.

**Evidence.**

- `docs/30-design/phase0-pr-sequencing-2026-09-15.md`

**Notes.** v0.0.14 is the FIRST ref carrying all seven connector commits - both the debug-logging narrowing that dev's pin has and the three log-redaction fixes that cut 4's pin has. GT4 found the two mitigations split across the two release trains.

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

**What an operator sees.** Nightscout picks up the new connector. Three fixes that keep CGM vendor credentials and patient data out of the log file come with it. Those fixes matter most exactly when you turn debug logging on to diagnose a problem - today's release narrows WHEN the leak happens but does not stop it happening then.

**Why `patch`.** a dependency pin move; the behaviour change is the connector's and is classified at P0-F.

**Gates.**

- `[static]` _(cwd: `externals/work/crm-bf-connect-pin`)_ `grep -q 'archive/refs/tags/v0.0.14.tar.gz' package.json`
  - package.json points at the v0.0.14 tag tarball
- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/connect-pin`
  - bf/connect-pin has not fallen behind origin/dev
- `[static]` _(cwd: `externals/work/crm-bf-connect-pin`)_ `grep -q '234d47c85510a77f07b3be0d2c026dd0272715d6' package-lock.json`
  - DELIBERATELY INVERTED. This gate passes while the lockfile is STILL on the old SHA. The lock's integrity is a hash over a tarball GitHub does not generate until the tag is pushed; a hash invented locally would break `npm ci` for everyone. Leaving it stale makes `npm ci` fail LOUDLY as out-of-sync, which is the correct failure. When P0-LOCK is done this gate SHOULD go red - that is the handoff signal.
- **NO GATE** &mdash; Nothing can verify the tarball's integrity hash before the tag exists on GitHub. That is the whole reason P0-LOCK is a separate item.

**Evidence.**

- `docs/30-design/phase0-pr-sequencing-2026-09-15.md`

**Notes.** This is the branch that closes the split GT4 found: neither dev's pin nor cut 4's pin carries both the logging narrowing and the redaction commits.

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

**What an operator sees.** Nothing you see. Until this is done, `npm ci` fails with an out-of-sync error - which is intentional and correct, not a bug.

**Why `n/a`.** lockfile only

**Gates.**

- `[static]` _(cwd: `externals/work/crm-bf-connect-pin`)_ `grep -q 'archive/refs/tags/v0.0.14.tar.gz' package-lock.json`
  - the lockfile agrees with package.json. FAILS today, on purpose, and must not be made to pass locally - see P0-PIN's inverted gate.
- `[network]` _(cwd: `externals/work/crm-bf-connect-pin`)_ `npm ci --dry-run`
  - npm ci resolves; requires the pushed tag to exist on GitHub

**Evidence.**

- `docs/30-design/phase0-pr-sequencing-2026-09-15.md`

**Notes.** DELIBERATELY UNDONE and it must not be papered over. Regenerate with `npm install` once the tag is pushed, in the same PR.

### `P0-T01` &mdash; T0.1 - PR #8733, the two quadratic treatment scans

| | |
|---|---|
| state (claimed) | `in-flight-upstream` |
| repo | `cgm-remote-monitor` |
| branch | `fix/quadratic-treatment-processing` |
| base | `origin/dev` |
| worktree | `externals/work/crm-quadratics` |
| semver | `patch` |
| review | upstream reviewers on PR #8733 - not ours to land |

**Blast radius.** dfe2753d. Pushed as bewest/wip/optimize-treatment-processing.

**What an operator sees.** Sites with a lot of treatment records load faster. Nothing you see changes value or meaning.

**Why `patch`.** performance only

**Gates.**

- `[network]` `git -C externals/cgm-remote-monitor-official ls-remote --heads origin bewest/wip/optimize-treatment-processing | grep -q dfe2753d`
  - the one Phase 0 branch that IS legitimately pushed. GT1 verified this live. Read-only.
- **NO GATE** &mdash; PR merge state is upstream's and cannot be gated from here without a GitHub API call. This item is tracked, not driven.

**Evidence.**

- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** The plan says "everything downstream assumes it". It is the only Phase 0 item not prepared locally, and the only one already on a remote.

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
  - CONTROL, and it PASSES - and it carries a correction. The sequencing document says the rule is written twice, in lib/server/count.js and v3's parseLimit. THAT FILE DOES NOT EXIST ON origin/dev; bf/reads creates it. So the duplication does not exist yet and this follow-up is created by P0-E landing.
- `[static]` `git -C externals/cgm-remote-monitor-official cat-file -e bf/reads:lib/server/count.js 2>/dev/null && git -C externals/cgm-remote-monitor-official show bf/reads:lib/api3/generic/collection.js | grep -q "self.parseLimit" && exit 1 || exit 0`
  - FAILS on bf/reads, where both readings of the rule are present. Paired with the control above, a red here is the duplication and not the command - the identical command run against origin/dev exits 0.
- **NO GATE** &mdash; Nothing asserts that the two implementations AGREE while they both exist. A differential test - the same limit value through both paths, including 0, a negative, a non-numeric and a value above the maximum - is what would make the duplication safe until it is removed, and it does not exist. Two readings of one rule is the root cause of this whole family, so leaving it duplicated is a debt with a name.

**Evidence.**

- `docs/30-design/phase0-pr-sequencing-2026-09-15.md`

**Notes.** Follow-up #1 in the same list is struck through as RESOLVED by the combination - BF-01 delegates to each collection's query_for, which already names its collection, so coercion's option reaches query.js on the count path. What remains there is an end-to-end test asserting it, which does not exist, and it is not this item.

### `FU-RESIDUALS` &mdash; Follow-ups 3, 4, 7 - three named residuals beside branches already prepared

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `patch` |
| review | maintainer. Follow-up 7 should land WITH bf/alarms, which already changes the line beside it; the other two are independent. |

**Blast radius.** Three one-line changes in three files - lib/plugins/index.js:152, lib/authorization/storage.js:113, lib/api/alexa/index.js switch.

**What an operator sees.** One of these three is visible to you. If an Amazon Alexa request arrives that Nightscout does not recognise, Nightscout answers nothing at all and the request hangs until Alexa gives up, rather than saying it did not understand. The other two are internal - a check that always answers "yes" but that nothing currently asks, and a leftover log line that prints request details to the server log.

**Why `patch`.** Three bug fixes. None moves a declared surface. The alexa change adds a response where there is currently none, which is a repair of a hang rather than a new capability.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official show origin/dev:lib/plugins/index.js | grep -q "return (p !== null)" && exit 1 || exit 0`
  - Follow-up 3. FAILS today - plugins.isPluginEnabled compares find()'s result with !== null, and find() returns UNDEFINED when it misses, so the function always returns true. No caller today, which is why it has no register id, but it is what the next instrument will reach for.
- `[static]` `git -C externals/cgm-remote-monitor-official show origin/dev:lib/authorization/storage.js | grep -qE "console\\.log\\('Loading',[[:space:]]*opts\\)" && exit 1 || exit 0`
  - Follow-up 4. FAILS today. BF-05's unfixed sibling - the same shape, a different file. THE PATTERN IS THE STORY OF THIS GATE. The shipping source is console.log('Loading',opts) with NO SPACE after the comma. The register (L1005), the sequencing document and P0-C's gate all quote it WITH a space, and the first draft of this gate copied that quotation - so it searched for a string that is not in the file, matched nothing, and PASSED while the defect was present. A vacuous green, caught by running it. The same defect was found concurrently in P0-C's copy of the gate by another session and fixed there; this is the same space-tolerant pattern, so the two cannot diverge again. :84 AND :113 ARE BOTH RIGHT - storage.js:84 on origin/dev, :113 on bf/auth. The sequencing document's "measured, it is :113, not :84" is true of bf/auth and false of dev; neither number names its ref. This gate measures origin/dev, which is where the fix has to land.
- `[static]` `bash -c 's=$(git -C externals/cgm-remote-monitor-official show origin/dev:lib/api/alexa/index.js); echo "$s" | grep -q "switch (req.body.request.type)" || exit 1; echo "$s" | grep -q "default:"'`
  - Follow-up 7. FAILS today. The switch on request.type has no default, so an unrecognised type calls neither res.json nor next() and the request hangs until the client times out. The first clause is the control - it asserts the switch is still there, so a red result cannot come from the file having been restructured. Measured: 0 occurrences of "default:" in the file. googlehome has no switch at all, so this is alexa-only.
- **NO GATE** &mdash; Reachability of follow-up 7 is not measured. It needs an Alexa request type outside SessionEndedRequest, LaunchRequest and IntentRequest, and nothing here enumerates what Amazon can send.

**Evidence.**

- `docs/30-design/phase0-pr-sequencing-2026-09-15.md`

**Notes.** BATCHED as three small residuals the sequencing document named together, each one file and each measurable. UPDATE 2026-09-16: follow-up 4 (the console.log at lib/authorization/storage.js) is now REPAIRED ON bf/auth as commit 56ed29d2 and must not be fixed here as well - this is a cross-reference, not a second item. Its gate below still fails, correctly, because the gate reads origin/dev and P0-C has not merged. When P0-C merges, that gate goes green on its own and only follow-ups 3 and 7 remain. SEPARABLE, and the destinations differ - follow-up 7 sits beside the ctx.language.set(locale) line bf/alarms already changes and should land with P0-A; follow-up 4 sits in the file P0-C already touches. Split them back if either branch is reopened.

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

- **NO GATE** &mdash; Follow-up 9 - audit the suppressions OUTSIDE lib/: detect-non-literal-fs-filename, detect-possible-timing-attacks, no-cond-assign. There is no instrument because the audit IS the work: object-injection's 34 suppressed lines yielded five real defects (BF-35, BF-36, BF-37, BF-38 and BF-39 - the register's own tally of four is stale), and the same reasoning applies to each remaining category. What could be gated afterwards is a rule that no NEW suppression is added without an entry, and that rule does not exist.
- **NO GATE** &mdash; Follow-up 10 - jsdom test hygiene has no enforcement. A suite that sets global.window or global.document must restore them in afterEach or it breaks browser-settings.test.js later in the same run. hashauth.modern.test.js does the restore; nothing requires it, and the failure lands in a DIFFERENT file from the one that caused it, which is the shape that costs the most review time. The instrument is a harness-level check, and cut 1 retires jsdom entirely, so it should be decided against the release train rather than built twice.

**Evidence.**

- `docs/30-design/phase0-pr-sequencing-2026-09-15.md`

**Notes.** Both are honestly UNMEASURED and say so. They are in the queue because the sequencing document listed them and no queue had them, and because the first is how five of this batch's defects were found - the trivial lint rule was the best signal in the programme.

---

## Modernization release train

`parcel: release-train` &mdash; 12 items

The adopted order (maintainer, 2026-09-15): 15.0.9, then cut 1, then cut 2,
then cuts 3+5 combined, then a deprecation release, then cut 4. GT2 measured
the premise of "zero rebase work" false; the rebase items here are what that
costs.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `RT-D3` | Answer the D3 question before 15.0.9 ships | `needs-decision` | `origin/dev` | minor | 2 run + 1 no-gate |
| `RT-VERSION` | Two artefacts claim version 15.0.9 with different Node floors | `not-started` | `-` | n/a | 1 run + 1 no-gate |
| `RT-REBASE` | Cuts 1-4 are 59 commits behind dev and each conflicts | `gate-not-met` | `chore/retire-jsdom, chore/build-runtime-separation, chore/compose-mongodb6, chore/mime-exposure-review` | n/a | 5 run + 1 no-gate |
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

**Blast radius.** GT2 re-measured: commit 48075a18 touches THREE production files - lib/client/renderer.js +25/-25, lib/client/chart.js +2/-2, lib/report_plugins/daytoday.js +3/-3. 30 lines, not the five files the release-readiness document lists.

**What an operator sees.** The charts on the main page were rebuilt on a new version of the drawing library. What is being checked is whether dragging a treatment on the chart still behaves - because dragging one changes the time that treatment is recorded at, and insulin-on-board and carbs-on-board are calculated from that time.

**Why `minor`.** GT4: D3 5.16 -> 7.9 by itself moves NO declared surface, so it forces neither minor nor major. 15.0.9 is a minor for reasons independent of D3 - lib/server/env.js gains DEBUG_LOGGING and CONNECT_DEBUG, debug logging flips to off by default, and a new lib/api2/loop-notification-errors.js appears.

**Gates.**

- `[unit]` _(cwd: `externals/cgm-remote-monitor-official`)_ `TEST=dependency-d3 npm run test-single`
  - GT2 ran this: 24 passing, driving the REAL renderer and chart against the D3 7 browser bundle. Non-vacuous - it catches reverting mouseover handlers to the D3-5 signature and catches breaking d3.pointer.
- `[static]` `node tools/queue/gates/d3-drag-clamp-covered.js`
  - THE GAP. GT2 deleted BOTH treatment-drag clamps at renderer.js:764 and 770-771 and the suite stayed at 24/24 - the handler runs 25 times with only x in {20,400}, all strictly inside 0..900, so the boundary is never reached. This gate re-runs that ablation and FAILS while the clamps are uncovered.
- **NO GATE** &mdash; lib/plugins/cob.js +49/-73 is filed under the D3 heading in release-readiness §2 and is NOT D3 work - it is 34e9b2da, "fix(cob): use the COB reported by the uploading system". It is more than twice the size of the entire D3 migration, it changes what a user reads when deciding about food and correction, and it has no line of its own in the 15.0.9 release decision. Nothing gates it because nobody has decided what it is.

**Evidence.**

- `docs/60-research/gt2-cut-remeasure-2026-09-15.md`
- `docs/30-design/cgm-remote-monitor-release-readiness-2026-09-14.md`

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
  - FAILS while origin/dev and any cut tip carry the same package.json version string. GT4's sharpest finding, expressed as a measurement.
- **NO GATE** &mdash; Both cut-4 migration shims emit error text saying "retired in Nightscout 15.0.9", but on the ADOPTED train 15.0.9 is the bug-fix release and retires nothing. Nothing checks error strings against the release they name.

**Evidence.**

- `docs/60-research/gt4-semver-classification-2026-09-15.md`

**Notes.** Given the governance gap - 100 self-merged PRs, zero human reviews - the version number is the only warning an operator gets, and right now it is missing.

### `RT-REBASE` &mdash; Cuts 1-4 are 59 commits behind dev and each conflicts

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `chore/retire-jsdom, chore/build-runtime-separation, chore/compose-mongodb6, chore/mime-exposure-review` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `n/a` |
| review | maintainer - this changes the cost of the adopted train |
| register | `BF-55`, `BF-56` |

**Blast radius.** Each cut conflicts with dev in 4-5 files under merge-tree: lib/server/bootevent.js, package.json, package-lock.json, tests/clock- client.test.js (modify/delete) for cut 1; cuts 2-4 add README.md. The 59 missing commits total 63 files, +2011/-95.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** rebase mechanics, not a release

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/retire-jsdom >/dev/null`
  - cut 1 trial-merges into dev cleanly - FAILS today (GT2)
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/build-runtime-separation >/dev/null`
  - cut 2 trial-merges into dev cleanly - FAILS today
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/compose-mongodb6 >/dev/null`
  - cut 3 trial-merges into dev cleanly - FAILS today
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/mime-exposure-review >/dev/null`
  - cut 4 trial-merges into dev cleanly - FAILS today
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/nightscout-modernization >/dev/null`
  - cut 5 trial-merges cleanly - PASSES, and it is the only one that does. The control arm: this gate proves the four failures above are not the command being wrong.
- **NO GATE** &mdash; The sharpest cost is one NON-mechanical conflict and no command can resolve it. dev's 06372e1d adds 56 lines to tests/clock-client.test.js covering the low-and-falling clock concern; cut 1 DELETES that file as part of jsdom retirement, and cut 1's Playwright replacement has ZERO references to concern or falling (positive control: 3 hits on dev). Resolving the conflict the obvious way keeps the production fix and loses its only test, on a screen people read at a glance.

**Evidence.**

- `docs/60-research/gt2-cut-remeasure-2026-09-15.md`

**Notes.** CORRECTS release-readiness §5's "each costs zero rebase work today", which was false WHEN WRITTEN - the cut tips date to 2026-09-05/06 and dev's tip to 2026-09-09. The stack's "0 commits behind dev" is true of the TIP only, and only because of one commit, 0a4109f6.

### `RT-0` &mdash; Release 15.0.9

| | |
|---|---|
| state (claimed) | `needs-decision` |
| repo | `cgm-remote-monitor` |
| branch | `origin/dev` |
| base | `origin/master` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer, and at least one human reviewer who is not the author - release PR #8598 and integration PR #8605 each carry ZERO human reviews |
| blocks on | `RT-D3`, `RT-VERSION` |

**Blast radius.** dev vs master. Includes four user-visible bug fixes plus i18n.

**What an operator sees.** A bug-fix release. Fixes for unnamed profiles, embedded profile switch schedules, treatments query failures, and a clock display that now shows concern for a low and falling reading. Debug logging becomes opt-in, so your logs get quieter unless you turn it on.

**Why `minor`.** GT4: cannot be a patch, for reasons INDEPENDENT of D3. lib/server/env.js gains DEBUG_LOGGING and CONNECT_DEBUG, debug logging flips to off by default (removing log lines an operator relies on when diagnosing), and a new API file lib/api2/loop-notification-errors.js appears.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/master origin/dev`
  - dev descends from master with no divergence to reconcile
- **NO GATE** &mdash; CI state at dev's tip is not re-verified here. The only evidence is release-readiness §3's record of 21 green checks on PR #8605 as of 2026-09-14, evaluated against the INTEGRATION branch as base, not against dev. Re-running it needs the full matrix (three Mongo versions, replica sets) and, for the browser half, three browser engines.
- **NO GATE** &mdash; RT-D3's drag-clamp gap is unresolved and this release ships the D3 7 charts. The decision to ship anyway is the maintainer's; recording it as a no-gate keeps it from reading as covered.

**Evidence.**

- `docs/30-design/cgm-remote-monitor-release-readiness-2026-09-14.md`
- `docs/60-research/gt4-semver-classification-2026-09-15.md`

**Notes.** First on the adopted train. Phase 0's branches target dev, so landing them changes what 15.0.9 contains - that collision is why there is one queue.

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

**Blast radius.** 99 commits. GT2 re-measured the incremental production diff as 11 files +68/-54, NOT the 21 files +91/-123 the §5 table publishes - row 1 was measured on a different basis from rows 2-5 and also counts dev's own 59 commits as deletions. Total 106 files, not 163.

**What an operator sees.** A maintenance release. THE ONE THING TO CHECK BEFORE UPGRADING: it will refuse to start on older versions of Node. You need Node 22.23.2 or newer, or 24.20.0 or newer. Node 20 no longer works, and neither do Node 21, 23, or 25 and above - the requirement is two specific ranges, not a minimum. If Nightscout stops starting after this upgrade, that is why.

**Why `major`.** GT4: the ENFORCED floor today is Node >=16 in bootevent.js, not the >=20 that `engines` declares - engines is not enforced on dev or master. Cut 1 introduces runtime-policy.js, which reads engines.node and calls process.exit(1). So the enforced floor jumps SIX majors, the declared range becomes a whitelist excluding Node 21/23/25+ and 22.0-22.23.1, and the check becomes a hard exit. Cut 1 also drops MongoDB 4.4 from CI in the same branch.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/retire-jsdom >/dev/null`
  - trial-merges into dev cleanly - FAILS today, see RT-REBASE
- `[static]` `node tools/queue/gates/node-floor-consistency.js`
  - "Trivially revertible - the engines field plus a boot check" is mechanically true and operationally misleading. Six other files state the floor independently (.nvmrc, bin/setup.sh, azuredeploy.json, README.md, CONTRIBUTING.md, docs/meta/architecture-overview.md). This gate checks they agree; a one-field revert would leave them stale.
- **NO GATE** &mdash; Dockerfile is node:22-alpine on both dev and cut 1, while cut 1's engines requires ^22.23.2 - a floating major tag against a patch floor. Nothing checks a Dockerfile base tag against an engines range.
- **NO GATE** &mdash; The clock-client concern/falling coverage is lost in the conflict resolution (RT-REBASE). Porting it to the Playwright suite is real work nobody has scheduled, and release-readiness §2 Option 1's "one CI run plus a cherry-pick of tests/browser/" undercosts it - cut 1 also deletes tests/dependency-d3.test.js, tests/fixtures/d3.js, tests/fixtures/d3-chart.js and tests/client.renderer.test.js, and its browser suite requires a playwright-core fixture and a module builder that dev does not have.

**Evidence.**

- `docs/60-research/gt2-cut-remeasure-2026-09-15.md`
- `docs/60-research/gt4-semver-classification-2026-09-15.md`

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
  - trial-merges into dev cleanly - FAILS today, see RT-REBASE
- **NO GATE** &mdash; The minor classification rests on no plugin ever being run against it. A plugin corpus does not exist here. Until one does, "minor" is a judgement and the queue says so rather than letting the field imply a measurement.

**Evidence.**

- `docs/60-research/gt2-cut-remeasure-2026-09-15.md`

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

**Blast radius.** Cut 3: 63 commits, prod 23 files +294/-54 (MongoDB driver 7, jQuery UI). Cut 5: 154 commits as §5 states, but GT2 measured that 95 are modernization work and 59 are dev's, pulled in by the tip merge 0a4109f6. Prod 36 files +397/-131 (Express 5, Helmet, EJS, Axios, Mocha 12, Swagger).

**What an operator sees.** A dependency upgrade release. The database driver, the web framework and several libraries move to new major versions. You should see no difference in what Nightscout does. The bundled Docker setup moves from MongoDB 5.0 to 6.0; MongoDB 5.0, 6.0, 7.0 and 8.0 are all still tested, so no database version you are running today stops being supported.

**Why `major`.** Cut 3 alone is minor - GT4 verified the CI matrix runs 5.0.32, 6.0.27, 7.0.40 and 8.0.29, so NO tested server is lost; only the bundled docker-compose default moves. Cut 5 is classified major on dependency major bumps (Express 4->5, Helmet 4->8) and a 36-file production diff, NOT on a measured contract break. Combined, the release is major.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/nightscout-modernization >/dev/null`
  - cut 5 trial-merges into dev cleanly. PASSES today - it is the only cut that does, because its tip 0a4109f6 is the one commit in the whole 495-commit stack that contains origin/dev.
- **NO GATE** &mdash; Express 4->5 and Helmet 4->8 are classified major on dependency version numbers and diff size, not on any measured contract break. Nobody has run a contract test against the route surface.
- **NO GATE** &mdash; Combining cuts 3 and 5 skips cut 4 in the middle of a LINEAR stack. Cut 5 is a descendant of cut 4, so "3+5 without 4" is not a prefix and the parcel-as-prefix property the whole plan rests on does not hold for this step. Nobody has measured what that costs.

**Evidence.**

- `docs/60-research/gt2-cut-remeasure-2026-09-15.md`
- `docs/60-research/gt4-semver-classification-2026-09-15.md`

**Notes.** GT2's arithmetic correction: §5's commits column sums to 554 against a 495-commit stack. Stated as modernization work cut 5 is 95, and 95 + 400 = 495.

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

- `docs/60-research/gt4-semver-classification-2026-09-15.md`

**Notes.** The adopted train puts this BEFORE cut 4 deliberately. GT4 found the real code work: the MiniMed shim has to be written, not just a warning added.

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

**Blast radius.** 79 commits, prod 66 files +324/-511. DELETES TWO CGM INGESTION PATHS (legacy Dexcom and MiniMed), trusted proxies, DOMPurify, Moment/tz.

**What an operator sees.** READ THIS BEFORE UPGRADING. This release removes the built-in Dexcom Share and MiniMed CareLink connections. If you have not moved to the nightscout-connect connector, your glucose data stops arriving. If you use MiniMed CareLink and have not set a country, Nightscout will not start at all - not just the CGM part, the whole site, showing an error page instead. The same happens if you currently use Dexcom Share AND MiniMed CareLink together, which works today and does not after this release. If your data stops arriving you may not have a glucose reading when you expect one; please make sure you have another way to check your glucose before upgrading, and talk to your care team about what you rely on Nightscout for. This is not medical advice.

**Why `major`.** GT4 EXECUTED the shims. An MMCONNECT operator with no CONNECT_COUNTRY_CODE gets {migrated:false,error:...}; bootevent.js pushes it to ctx.bootErrors; app.js:202 then installs app.get('*', bootErrorView) and returns, and server.js:61 returns before websocket setup. The WHOLE deployment serves the boot-error page - no API, no sockets, no charts. Separately, running BRIDGE_* and MMCONNECT_* together - two independent boot stages today - gets the same total outage, because there is now one CONNECT_SOURCE and the second source has nowhere to go. That is a capability removal (concurrent multi-source CGM ingestion) absent from every summary of the cut.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev origin/chore/mime-exposure-review >/dev/null`
  - trial-merges into dev cleanly - FAILS today, see RT-REBASE
- `[static]` `node tools/queue/gates/cut4-total-outage.js`
  - Re-runs GT4's execution of both cut-4 shims in the order bootevent.js calls them, with four env shapes. FAILS while either shape produces a bootError. This is the gate that says whether an operator's site goes dark, and it must be green before this cut ships.
- **NO GATE** &mdash; "No real Dexcom account or live database has been used and no live migration is claimed" - the cut's own evidence document. No gate can substitute for a real migration, and nothing in this repository may use real credentials (rule 0).
- **NO GATE** &mdash; Cut 4 deletes bridgeUseLegacy and the log line naming it, so DEXCOM_BRIDGE_USE_LEGACY becomes accepted-and-ignored. Credentials are still migrated so ingestion continues; only the operator's expressed intent is discarded silently. Nothing checks for accepted-and-ignored settings.

**Evidence.**

- `docs/60-research/gt4-semver-classification-2026-09-15.md`
- `docs/60-research/gt2-cut-remeasure-2026-09-15.md`

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

**What an operator sees.** The first two releases on the planned upgrade path are presented as low-risk maintenance releases. As the branches stand, upgrading to either of them leaves you on the same connector version that writes your CGM credentials and glucose readings into the log. It is a one-line change on each branch to move them to the fixed version, and it should happen before those releases are cut.

**Why `patch`.** a dependency pin moves to a newer patch of the same package

**Gates.**

- `[static]` `node tools/queue/gates/connector-pin-exposure.js --refs origin/chore/retire-jsdom,origin/chore/build-runtime-separation,origin/chore/compose-mongodb6,origin/dev`
  - FAILS on all three cut tips, which pin the v0.0.13 TAG tarball, and PASSES on origin/dev as the control. The gate also refuses to report when every ref agrees, because a run that distinguished nothing is not a result.
- **NO GATE** &mdash; The pins are MEASURED; the ordering is QUOTED from release-readiness §5 and was not re-derived. So "ships the leaking connector to upgraders FIRST" is an inference from combining the two, and nothing gates a claim about the order of releases. It is cheap to remove either way - all three pin the v0.0.13 tag, so moving them is the same one-line change as dev's, with no incomparability to reason about.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** Filed separately from BFQ-CONNECTOR, not batched with it, because the §1/§1b line runs between them - master ships to operators today, cut tips do not - and that line is the only thing that makes the register's sections mean anything. The work is identical and they should be done together.

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

**Blast radius.** Dockerfile (builder and runtime FROM lines) and the .github/workflows test-job matrix, on the cut tips. No production source.

**What an operator sees.** From the first maintenance release onward Nightscout refuses to start on Node older than 22.23.2 or 24.20.0, and exits immediately with a message. The container image it ships is built on a floating "node 22" tag, so a cached or mirrored older layer produces a container that starts, prints that message and stops. That looks like a crash and is not data loss. The release notes should name the message so you recognise it.

**Why `n/a`.** CI and image configuration. It changes no declared surface. The Node floor itself is classified on RT-1 and this item does not restate it.

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official show origin/chore/retire-jsdom:.github/workflows/main.yml | grep -q "'22.23.2'" && git -C externals/cgm-remote-monitor-official show origin/chore/retire-jsdom:.github/workflows/main.yml | grep -q "'24.20.0'"`
  - CONTROL, and it PASSES - cut 1's test matrix is ['22.23.2','22','24.20.0','24'], so the two floor versions the runtime policy refuses to start below are exercised. A green here is what makes the red below a fact about cut 3 rather than about the grep.
- `[static]` `git -C externals/cgm-remote-monitor-official show origin/chore/compose-mongodb6:.github/workflows/main.yml | grep -q "'22.23.2'" && git -C externals/cgm-remote-monitor-official show origin/chore/compose-mongodb6:.github/workflows/main.yml | grep -q "'24.20.0'"`
  - BF-59. FAILS - from cut 3 onward the matrix is ['22','24'] and the two exact versions the software refuses to start below are exercised by no test job. engines is byte-identical across all five cuts, so this is LOST COVERAGE rather than a changed requirement.
- **NO GATE** &mdash; BF-58 is not reproducible against a current image and no image was built - rule 0 forbids pulling one. node:22-alpine tracks the latest 22.x and satisfies the floor today; the exposure is cached, mirrored or explicitly pinned older 22.x layers. Nothing checks a Dockerfile base tag against an engines range, and that is the missing instrument.
- **NO GATE** &mdash; PARTIAL MITIGATION ALREADY IN CI, recorded so the residual is not overstated - from cut 1 the docker-build-pr job builds the image and runs runtime-policy against it plus a start-up smoke test. The gap is narrower: the docker-build job that PUBLISHES to Docker Hub on master/dev has no such step and builds with no-cache, so it re-resolves node:22-alpine at publish time without re-validating.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** BATCHED because both are one question - is the floor the software enforces the floor anything actually runs? - and because fixing one without the other leaves the question open. RT-1 carries BF-58 as a no-gate already; this item is the work, that is the measurement.

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

**What an operator sees.** When Nightscout cannot start it shows a page explaining why. For one shape of start-up error that page itself fails, so instead of the sentence telling you what to fix you get nothing at all. The error shape that triggers it is the one a MiniMed CareLink user hits on the release that removes the built-in connection - the message that would tell them to set their country. Losing that message is what makes this worth fixing before that release, not after.

**Why `patch`.** A crash fix in an error renderer. No declared surface moves. The call-site half on cut 4 is part of that cut's own classification.

**Gates.**

- `[static]` `node tools/queue/gates/booterror-shape-coverage.js --ref origin/chore/mime-exposure-review`
  - FAILS on the two err-less shapes and reports that cut 4's bootevent.js has 2 of 9 push sites producing them. Three control shapes - the Mongo string, the ENV array and a real Error - RENDER through the identical expression, so the failure is the input shape and not the harness. The gate also refuses to run if the map expression is no longer present verbatim in the shipping file.
- `[static]` `node tools/queue/gates/booterror-shape-coverage.js --ref origin/dev`
  - THE §1b CONTROL, and it also fails - on origin/dev the renderer throws on the same two shapes while 0 of 7 push sites produce them. That is the register's filing decision as a measurement: the weakness is in SHIPPING code today and is awaiting a caller, and the caller arrives with cut 4. Correcting an earlier draft of the finding, git diff origin/dev origin/chore/mime-exposure-review -- lib/server/booterror.js is EMPTY; a reviewer sent to that diff would have dismissed it.
- **NO GATE** &mdash; Nothing renders the actual error.html template. The gate exercises the map that builds each error line, which is where the TypeError is thrown, but a full render needs EJS, express and a views path. The fix must be BOTH halves - pass err at both call sites AND make the renderer defensive - with a regression test asserting a desc-only boot error renders as HTML. Fixing only the call sites leaves the next caller to rediscover it.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** A gate-construction error is recorded here because it is the failure this queue exists to catch. The first draft of the caller-count arm tested only /\berr\s*:/ and reported dev's `bootErrors.push({desc: synopsis.join(' '), err})` - ES6 shorthand, no colon - as an err-less site, which would have "refuted" a register claim that is in fact correct. Caught by reading the site the gate named. The arm now matches the shorthand and reproduces the register exactly - 7/7/9 sites, 0/0/2 err-less on master/dev/cut 4.

---

## Open backfix-register entries

`parcel: register-open` &mdash; 23 items

The §1 / §1b distinction is preserved in `ships_to_operators_today`. That
distinction is the only thing that makes the register mean anything - widening
§1's criterion would destroy it.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `BFQ-09` | BF-09 - socket dedup truthiness skips a falsy value | `unsettled` | `-` | patch | 1 run + 2 no-gate |
| `BFQ-10` | BF-10 - mongod fatal-asserts at Docker's default nofile=1024 | `not-started` | `-` | patch | 1 run + 1 no-gate |
| `BFQ-04` | BF-04 - extract the v1 operator allowlist out of the seam | `not-started` | `-` | minor | 0 run + 2 no-gate |
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
| `BFQ-40` | BF-40 - $exists is not read as a boolean, before OR after bf/coercion | `not-started` | `-` | minor | 0 run + 2 no-gate |
| `BFQ-41` | BF-41 - a reading dated ahead of the clock silences the stale-data alarm | `gate-not-met` | `-` | minor | 1 run + 1 no-gate |
| `BFQ-CONNECTOR` | BF-42, BF-43 - master pins the leaking connector, with a violated axios override | `gate-not-met` | `-` | patch | 1 run + 2 no-gate |
| `BFQ-MINIMED` | BF-44, BF-45 - the two MiniMed ingestion divergences | `not-started` | `-` | minor | 0 run + 3 no-gate |
| `BFQ-46` | BF-46 - eleven API v3 variables bypass env.js, one family deletes data | `gate-not-met` | `-` | minor | 1 run + 1 no-gate |
| `BFQ-47` | BF-47 - an ordinary subject edit destroys stored fields, on today's release | `needs-decision` | `-` | major | 0 run + 2 no-gate |
| `BFQ-ENV` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies | `gate-not-met` | `-` | minor | 4 run + 2 no-gate |
| `BFQ-52` | BF-52 - the age plugins can only ask for their urgent alarm in one window | `unsettled` | `-` | patch | 0 run + 2 no-gate |
| `BFQ-67` | BF-67 - an alarm threshold is quietly changed and only the server log says so | `gate-not-met` | `-` | minor | 1 run + 1 no-gate |

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

- `docs/60-research/gt3-register-truth-2026-09-15.md`
- `docs/30-design/nightscout-backfix-register.md`

**Notes.** CORRECTS THE REGISTER ENTRY. BF-09 names the wrong fields. Measured over 277,690 treatments: ZERO zero-valued `insulin` (0 of 107,732) and ZERO zero- valued `carbs` (0 of 12,394). The field that actually carries falsy values is `absolute` - 67,521 of 153,315, 44% - the zero temp basal. `duration:0` adds 2,094. The entry also omits the ±2s window (maxtimediff). GT3's reading: a bug, not intent - the author built an explicit selected/fallback mechanism, so truthiness on `absolute` means the code treats a zero temp as "no value here", which is false in AID terms.

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
- **NO GATE** &mdash; Nothing reproduces the fatal assert. It needs a container started under nofile=1024 with enough load to reach the limit, and a control started with the ulimit raised - otherwise a green docker-compose is not evidence the setting does anything.

**Evidence.**

- `docs/60-research/gt3-register-truth-2026-09-15.md`

**Notes.** CORRECTS THE REGISTER ENTRY. BF-10 says "Not a code defect; it belongs in the operator documentation." Wrong. There is a one-block code landing site in the file most self-hosters actually use. The fix is that file first, docs second.

### `BFQ-04` &mdash; BF-04 - extract the v1 operator allowlist out of the seam

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-seam` |
| semver | `minor` |
| review | SECURITY - ReDoS / full-scan exposure |
| ships to operators today | **yes** |
| register | `BF-04` |

**Blast radius.** lib/server/query.js:157 - API v1 filter pass-through reaches the driver with no operator allowlist.

**What an operator sees.** The version 1 API passes search operators straight through to the database with no list of which ones are allowed. A request can be crafted that makes the database scan everything, or that takes a very long time to evaluate. Requires API access.

**Why `minor`.** an allowlist narrows an open pass-through, so some requests that worked will start being refused. Which ones is exactly what the corpus census (T2.4) exists to bound.

**Gates.**

- **NO GATE** &mdash; Nothing exists to gate. The fix lives inside the seam branch as a side effect and has never been extracted. Its OWN register entry says the extraction "should not have to wait for the seam to land", and that extraction has never been done.
- **NO GATE** &mdash; T2.4's v1 operator census is DONE but the allowlist derived from it has no test against the corpus, so nobody can say which shipping clients a given allowlist would break.

**Evidence.**

- `docs/60-research/gt3-register-truth-2026-09-15.md`

**Notes.** GT3'S THIRD OPERATOR-FACING ENTRY, and the one nobody counts. BF-04 is HIGH severity, ships to every current operator, and appears in no open list because its status is `fixed-in-seam`. It is invisible in exactly the way the register exists to prevent.

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

- `docs/60-research/seam-write-path-2026-09-15.md`

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

- `docs/30-design/nightscout-backfix-register.md`

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

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** NOTE ON THE ID. The execution plan at L351 and L1189 uses "BF-22" for the process-wide language/levels leak, which was RENUMBERED to BF-31. BF-22 today means this defect. One document uses one id for two things (GT3).

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

- `docs/30-design/nightscout-backfix-register.md`

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

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** D14 KILLS THIS BUG CLASS STRUCTURALLY. Per-tenant JWT signing keys mean tenant resolution runs BEFORE any credential is examined, so cross-tenant token reuse becomes a SIGNATURE failure rather than a claim-check failure. That is why this blocks on T3.0's wiring rather than getting a patch.

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

- `docs/30-design/nightscout-backfix-register.md`

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

- `docs/30-design/nightscout-backfix-register.md`

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

- `docs/60-research/gt3-register-truth-2026-09-15.md`

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

- `docs/30-design/nightscout-backfix-register.md`

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

- `docs/30-design/nightscout-backfix-register.md`

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

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** The only capability entry in the register. BFQ-26 (BF-26) is the one part of it that is a defect rather than an absence.

### `BFQ-40` &mdash; BF-40 - $exists is not read as a boolean, before OR after bf/coercion

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/work/crm-bf-coercion` |
| semver | `minor` |
| review | maintainer, and whoever reviews P0-D, because this decides a sentence in that branch's operator-facing text |
| ships to operators today | **yes** |
| register | `BF-40` |

**Blast radius.** The $exists special case in the query walker - lib/server/query.js walk_prop on dev, lib/server/query-coercion.js:90 on bf/coercion - plus a regression test, which does not exist: tests/query.test.js:138 covers $exists=true only.

**What an operator sees.** If you or a tool you use asks Nightscout for records that do NOT have a particular field - for example entries with no "sgv" value - you get back exactly the records that DO have it. The opposite of what was asked, with no error. This is wrong today on every field, and it stays wrong after the query type-conversion fix unless this is fixed too. Asking for records that DO have a field works correctly.

**Why `minor`.** It changes what a documented v1 endpoint returns for a documented query parameter, in the direction of correctness, which is the same class as BF-02 and BF-03 and needs the same release note.

**Gates.**

- **NO GATE** &mdash; The measurement is a live one and it needs MongoDB. The register's claim was established against SEVEN mongod instances (3.6.8 and 7.0.43) with identical results, precisely because a JavaScript-side oracle gets it wrong: mingo applies JavaScript truthiness, MongoDB applies `value != 0`, and that difference is the whole entry. A gate that reproduced it against mingo would agree with BF-32 and be wrong. The instrument this needs is an integration gate with a real server, and none of the existing harnesses provides one.
- **NO GATE** &mdash; The prescribed fix - route the operand through a boolean reader that understands "false", "0" and "" - is UNVERIFIED. Nobody has run it. Two fixes this register prescribed were wrong when somebody finally ran them, so it is recorded as unrun rather than gated as if settled.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** COSTS P0-D SOMETHING BEFORE IT IS PROPOSED. bf/coercion's operator-facing text says find[sgv][$exists]=true "became $exists: NaN, which MongoDB reads as false, so the query returned exactly the records you did not ask for". That sentence is false - $exists=true is answered correctly before and after - and it tells operators to distrust queries that were right. What the coercion genuinely broke and the fix genuinely repairs is $regex, a much smaller blast radius than the one claimed.

### `BFQ-41` &mdash; BF-41 - a reading dated ahead of the clock silences the stale-data alarm

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer, and it needs a DECISION before it needs code. The register deliberately prescribes no fix: a small forward skew is normal and a large one is not, and "clamp the timestamp" and "a reading ahead of the clock is itself an alarm condition" are different products. |
| ships to operators today | **yes** |
| register | `BF-41` |

**Blast radius.** lib/plugins/timeago.js - the :26 early return in checkNotifications and isStale at :97. The browser alarm decision at lib/client/index.js:918-919 reads the same status.

**What an operator sees.** Nightscout can warn you when no new glucose reading has arrived for a while - the "minutes ago" warning, which is switched on by default in the browser at 15 and 30 minutes. If a reading arrives stamped with a time in the FUTURE, that warning stops working, and it stays off. A future timestamp usually comes from a clock or timezone problem on the device or uploader sending the data - which is the same kind of fault most likely to have stopped your readings in the first place. So the warning can go quiet exactly when you need it. What you would see instead is the "minutes ago" pill reading "future", or stuck at "1m". If you rely on that warning to tell you your data has stopped, please make sure you have another way to notice, and talk to your care team about what you rely on Nightscout for. This is not medical advice.

**Why `minor`.** Whichever way the decision goes, it changes when an alarm that is on by default fires. That is a behaviour change on a safety-adjacent surface and it cannot arrive as a silent patch.

**Gates.**

- `[static]` `node tools/queue/gates/timeago-future-reading.js`
  - Executes the SHIPPING timeago plugin. FAILS today - a reading 5 and 120 minutes ahead of the server clock both return checkStatus 'current', so neither alarm path fires. Three controls come out the other way through the same harness (2 min = current, 20 min = warn, 40 min = urgent), and the gate was proven to go green against an isolated copy carrying a future guard. This gate is also what upgrades BF-41's provenance from read-derived to REPRODUCED.
- **NO GATE** &mdash; Nothing here exercises the PUSH path end to end. checkNotifications returns early at :26 for the same reason, but it is opt-in (sbx.extendedSettings.enableAlerts) and driving it needs a booted notification stack. The claim "the stale-data alarm is on by default and this turns it off" is true of the BROWSER alarm and false of the push alarm; the gate measures the one that is on by default.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

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

**Blast radius.** Two lines of origin/master's package.json - the nightscout-connect dependency URL and overrides['nightscout-connect'].axios - plus the lockfile that follows them. No cgm-remote-monitor source changes.

**What an operator sees.** The connector version that today's release installs writes your CGM service's username and password, its session tokens, and your glucose readings into Nightscout's log. It does this every time Nightscout starts, for every data source, before it contacts anything, and there is no setting that turns it off. Anyone who can read your logs - which on many hosting platforms is more people than you might expect - can read those credentials. If you have been running this, treat the password for your CGM account as exposed and change it, and change it anywhere else you have used it. This is a fix to which version is installed; it does not change how your data is collected.

**Why `patch`.** A dependency pin moves to a newer patch of the same package. No declared surface of cgm-remote-monitor moves. It nonetheless needs a security note, which is a different obligation from a version number.

**Gates.**

- `[static]` `node tools/queue/gates/connector-pin-exposure.js --refs origin/master,origin/dev`
  - FAILS on origin/master for both arms - the v0.0.13 tag tarball (112 live console.* sites, 101 passing a non-literal argument, no debug guard anywhere) and an axios override of 1.16.0 against the connector's declared ^1.18.1. origin/dev is the CONTROL and passes both, which is what proves the gate is reading the pins and not the command: dev's 234d47c8 DELETES the leaking call sites, so redaction does not improve monotonically with release order and the widely repeated "dev only makes the logging opt-in" is inverted.
- **NO GATE** &mdash; No live run and no vendor account. The census is a source census of a git archive extraction, and rule 0 forbids creating an account or contacting a vendor. It is non-vacuous in the way that matters - the same scanner returns 112/101 on the leaking tree, 22/20 on the redacted ones, and correctly reports cut 4's commented-out MiniMed block as 47 calls with ZERO dynamic arguments, so it distinguishes deletion from commenting-out.
- **NO GATE** &mdash; No runtime failure is claimed for the axios override and no axios API was identified that the connector uses and 1.16.0 lacks. The defect is the silent constraint violation - `overrides` exists precisely to suppress the ERESOLVE that would report it - and nothing gates "a constraint was overridden into violation" in general.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`
- `docs/40-migration/connector-pin-consolidation-2026-09-15.md`

**Notes.** The fix is the same one-line pin move as P0-PIN, applied to master rather than dev, and it cannot be prepared until the v0.0.14 tag is pushed - a human decision, rule 0. RT-CONNECT-PIN-CUTS is the same change on cuts 1-3 and is filed separately because those are pre-release (§1b) and this is not.

### `BFQ-MINIMED` &mdash; BF-44, BF-45 - the two MiniMed ingestion divergences

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
| register | `BF-44`, `BF-45` |

**Blast radius.** BF-44 - nightscout-connect's CareLink source reassign_zone, against the retired minimed-connect-to-nightscout transform.js:41-85. BF-45 - setupMMConnect in lib/server/bootevent.js, which references Connect nowhere while setupBridge stands down for it.

**What an operator sees.** Two problems that affect people using a MiniMed pump with CareLink. First, the old built-in CareLink connection and the newer connector work out WHEN a reading happened in different ways, so the same reading can be filed at a different time by each. If it is filed in the future, the "no new data" warning stops working - see the separate item on that. Second, if you set up the new connector while the old CareLink connection is still switched on, BOTH run at once. For Dexcom the old one stands aside automatically; for MiniMed it does not. So any advice to "set up the new connection before removing the old one" is safe for Dexcom and NOT safe for MiniMed. Your glucose data continuing to arrive, and at the right time, is what is at stake here. This is not medical advice; if you are changing how your data reaches Nightscout, plan it with your care team.

**Why `minor`.** BF-45's repair adds a stand-down guard to a boot stage, which changes what a deployment with both configurations does. BF-44's repair changes the timestamp a reading is stored with, which is a data-affecting change and cannot be a silent patch.

**Gates.**

- **NO GATE** &mdash; The divergence itself IS reproduced and recorded in the register - both shipping implementations loaded side by side, three arms diverging by exactly the offset (UTC+2, UTC-7, UTC+5:30) and two controls agreeing (UTC+0, and UTC+2 with a zone-bearing lastConduitDateTime). It is not re-run as a queue gate because the arm/control roles INVERT with the server's own timezone: the magnitude is (pump offset minus SERVER offset) whenever the payload carries no zone designator, so under TZ=Europe/Berlin the Berlin arm agrees and the UTC control diverges. A gate that did not pin TZ would report the opposite result on a differently configured machine, which is worse than no gate.
- **NO GATE** &mdash; What decides ACTIVE versus LATENT cannot be measured from here at all - do real CareLink payloads omit lastConduitDateTime, and do sgs[].datetime, markers[].dateTime and sMedicalDeviceTime carry zone designators of their own? That needs a real CareLink account, which rule 0 forbids. Coverage is thin in exactly the way that hides it: lastConduitDateTime appears ZERO times in tests/fixtures/minimed-cutover.json and in tests/connect-minimed-cutover.test.js, and the one connector test that sets the field passes a Z-suffixed value, which makes the rewrite a no-op - that test is a control, not coverage.
- **NO GATE** &mdash; BF-45's double ingestion is derived from reading both function bodies in full on master and dev, not run as a live double-ingestion. Medium alone, because the sysTime+type upsert absorbs duplicate writes; HIGH in combination with BF-44, where the two paths compute different keys and nothing absorbs them. That combination is the reason these two are one item.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`
- `docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md`

**Notes.** Also recorded on BF-44 and not separately filed - pump.clock is not parsed at all, deviceStatusEntry assigns data['sMedicalDeviceTime'] verbatim, so a client doing new Date(pump.clock) can get Invalid Date. And the legacy transform THROWS RangeError on a Z-suffixed payload outside the MMCONNECT_SERVER=EU / GUARDIAN branch rather than producing a comparison value, so the reproduction arms hold only with MMCONNECT_SERVER=EU.

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

**What an operator sees.** Nightscout's newer API reads eleven settings straight from the environment, and none of them is written down anywhere - not in the README and not in the settings list. Six of them, one per kind of record, DELETE your stored history older than a number of days you give. Entries. That is your glucose history. The deletion cannot be undone, and Nightscout does not check whether it worked, so a failure is not reported either. If you run Nightscout on a hosting platform where someone else sets environment variables for you, this is worth checking. Nothing here changes unless one of these is set.

**Why `minor`.** Routing them through env.js makes eleven names part of the documented configuration surface for the first time. Nothing that works today stops working; a surface appears.

**Gates.**

- `[static]` `node tools/queue/gates/config-surface-census.js --arm api3`
  - FAILS today on both arms. Ten API3_* names (four flags plus API3_AUTOPRUNE_ for six collections) are absent from README.md and from lib/server/env.js, and the autoprune path calls storage.deleteManyOr WITHOUT awaiting the result. Controls come out the other way through the identical lookup - MONGO_CONNECTION and DISPLAY_UNITS are found in both files - so "not found" means absent rather than a broken grep, and the call sites are confirmed present before their names are reported on.
- **NO GATE** &mdash; THE DELETION PATH WAS READ, NOT EXECUTED. Nobody has run API3_AUTOPRUNE_ENTRIES against a database and watched rows go. Doing so needs MongoDB and a corpus that can be destroyed, and the honest version of that instrument is a rehearsal harness with a restore, not a gate.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** Kept OUT of BFQ-ENV deliberately, although the critic proposed batching the env-var family. The other three are a documentation and plumbing residue; this one irreversibly deletes a person's glucose history through a name nobody can look up, with the result unawaited. A reviewer should not have to find it inside a batch whose other members are a README typo and a dead settings key.

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

**What an operator sees.** Editing a person or device entry through Nightscout's admin page already throws away fields that are not shown on that page - notes, the date it was created, and anything a third-party tool has stored there. It happens silently, there is no error, and it cannot be recovered by going back to an older version of Nightscout. This is how today's release behaves.

**Why `major`.** The repair on bf/auth narrows the loss rather than introducing it, but it also introduces an allow-list, so a third-party tool can no longer preserve its own fields by sending them in its own PUT - which it CAN do today, because save() writes the caller's object as given. That is a capability removal on an HTTP surface.

**Gates.**

- **NO GATE** &mdash; DERIVED FROM SOURCE on origin/dev and on bf/auth. Not reproduced against a deployment. A gate would need a database with a subject row carrying an extra field planted on it, an edit through the admin path, and an assertion that the field survived - with a control row that has no extra field so a green result is known to distinguish the two. Nobody has built it.
- **NO GATE** &mdash; THE MISSING FACT IS NOT CODE, IT IS AN INVENTORY. No list exists of third-party tools that store extra fields on subjects or roles, and nothing in this repository can produce one. That inventory is what decides whether the narrower repair - delete only the derived accessToken/accessTokenDigest/digest and pass unknown fields through - is required or merely tidier.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** This entry exists because a verifier REFUTED the framing of a finding about bf/auth, and the refutation moved the defect from an unmerged branch onto the current release. Keeping the security goal of BF-17 - the derived token never reaches the database - does not require the allow-list.

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
  - BF-49. EXECUTES lib/settings.js and records the env names its own nameFromKey asks for, rather than grepping for a spelling - the defect IS that two spellings exist, so a gate hardcoding one could not detect a third. FAILS on SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS. The control is inside the same family: 4 of the 5 generated security names ARE read by env.js, so the miss is a divergence and not a broken compare.
- `[static]` `node tools/queue/gates/config-surface-census.js --arm readme`
  - BF-50. FAILS while README.md documents MONGODB_COLLECTION and none of the five configuration and storage modules reads it. Control - the same files DO contain ENTRIES_COLLECTION.
- `[static]` `node tools/queue/gates/config-surface-census.js --arm azure`
  - BF-51. FAILS while azuredeploy.json declares a WEBSITE_NODE_DEFAULT_VERSION parameter and references it via parameters(...) zero times. Control - parameters('mongoConnection') occurs once, so a zero is a fact about that knob and not about the regex.
- **NO GATE** &mdash; BF-51 is NOT reproduced against a live Azure deployment - there is no Azure environment on this machine and rule 0 forbids creating one. Why deployments work today is an open question attached to the entry rather than a finding: the platform presumably ignores the literal 8.11.1 as unavailable and falls back.
- **NO GATE** &mdash; Nothing checks that a key in the settings dictionary has a consumer. BF-49's five dead keys were found by grep over lib/, views/ and static/, and the general check - every settings key is read somewhere - is the instrument that would have caught all five at once. It does not exist, and D7/D13 tenant-admin work will generate a UI from that dictionary.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** BATCHED because it is one piece of work with one runnable gate in four arms - make the configuration surface tell the truth - and because a reviewer reading any one of them alone would ask about the other three. Split it back by arm if the documentation half lands separately from the plumbing half. BF-46 was deliberately NOT batched here; see that item.

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

**What an operator sees.** Nightscout can remind you when an insulin reservoir, cannula, sensor or battery is overdue. The on-screen indicator turns red and stays red, which is correct. The optional PUSH reminder can only be requested in the single check where the age exactly equals the threshold you set - so if Nightscout restarts, or a check is skipped, or there is a gap in data at that moment, that reminder never arrives. It is not settled whether sending it once is the intended behaviour; repeating it every check would be its own problem. The push reminder is off unless you have switched it on. This is not medical advice.

**Why `patch`.** If it is a defect at all, the fix is a bug fix to an opt-in notification. The on-screen level is already continuous and does not change.

**Gates.**

- **NO GATE** &mdash; READ, NOT REPRODUCED. No run across a SEQUENCE of evaluations was made, and a sequence is the only thing that can show the notification is missed when a window is skipped - a single evaluation at the exact threshold sends it, which is what makes the defect invisible to a one-shot test. That run is what would settle the grade, and it is the instrument this item needs.
- **NO GATE** &mdash; Marked `unsettled` deliberately. One-shot may be the intent. What is not defensible is that :90 uses >= and :92 uses === without saying why, and no check anywhere asserts an intended relationship between the two.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** BF-28 MASKED this on insulinage for years - the level line was broken, so nobody reached the notification line. The three sibling plugins have shipped with the same shape unmasked. Any release note for BF-28 must also get two things right - the push alarm is opt-in and off by default, and what DOES reach everyone is the on-screen pill, because the level is assigned outside the alerts guard.

### `BFQ-67` &mdash; BF-67 - an alarm threshold is quietly changed and only the server log says so

| | |
|---|---|
| state (claimed) | `gate-not-met` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `origin/dev@a8888f0d` |
| worktree | `externals/cgm-remote-monitor-official` |
| semver | `minor` |
| review | maintainer, and it is a DECISION with a safety dimension before it is code. Refusing a contradictory threshold set, correcting it and announcing it, and unit-checking the input are three different products. |
| ships to operators today | **yes** |
| register | `BF-67` |

**Blast radius.** lib/settings.js verifyThresholds(), four branches. Unconditional at settings load on every deployment.

**What an operator sees.** Nightscout checks that your four glucose thresholds are in a sensible order. If they are not, it does not tell you and ask - it changes one of them by one unit and carries on, and the only record is a line in the server log, which on many hosting setups you will never see. The case this actually reaches is a units mix-up. If you think in mmol/L and set your high alarm to 14, Nightscout is reading mg/dL unless you have told it otherwise, 14 is below the target range, and it is stored as 181 mg/dL. You believe you have set a high alarm and you have set a different one. The same happens if you ask for a low alarm at 90 while the target range still starts at 80 - it is stored as 79. If you have set thresholds and the alarms do not behave as you expect, check what Nightscout actually stored, and please discuss your alarm settings with your care team. This is not medical advice.

**Why `minor`.** Every option changes what a deployment with contradictory thresholds does at boot - refuse, announce, or convert. Alarm thresholds are what alarms fire on, so this cannot arrive as a silent patch under any of the three.

**Gates.**

- `[static]` `node tools/queue/gates/threshold-silent-rewrite.js`
  - EXECUTES the shipping settings layer. FAILS today on both arms - BG_HIGH=14 with UNITS at the mg/dL default is stored as 181, and BG_LOW=90 against the shipped bgTargetBottom of 80 is stored as 79, each with two console.warn lines and no other surface. Four controls come out the other way through the same harness, and the gate was proven to go green against an isolated copy with the two rewrite sites removed. This gate upgrades BF-67 from read-derived to REPRODUCED.
- **NO GATE** &mdash; Nothing checks that a corrected setting is SURFACED. The gate proves the value changes; the defect is that the only evidence is stdout. Grep over lib/client/ and views/ finds no surface that reports the rewrite, and building one is the fix, not the measurement.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`
- `docs/60-research/e4-queue-register-reconciliation-2026-09-15.md`

**Notes.** CORRECTS BF-67, measured while building the gate. The entry says "The same applies at the bottom - a BG_LOW of 3.9 becomes bgTargetBottom - 1 = 79". IT DOES NOT. The low check is `bgLow >= bgTargetBottom`, so a value far BELOW the band passes through untouched and BG_LOW=3.9 is stored as 3.9. The low-side rewrite is real from the other direction (BG_LOW=90 -> 79). The refuted half leaves a DIFFERENT and worse residue that no entry owns - a low alarm set to 3.9 mg/dL can never fire, and is stored with no warning of any kind. Also relevant to T3.0: the per-tenant configuration spec proposes a CHECK constraint as a backstop for this, and it is not one - a partial override leaves absent paths SQL NULL, the AND chain evaluates to NULL rather than FALSE, and PostgreSQL accepts the row.

---

## Multitenancy programme

`parcel: tenancy` &mdash; 15 items

T3.0 and the DONE-EXCEPT remainders it amends, T4.3, T4.4, the four open §7a
alarm-readiness items, and the seam branch refresh.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `T30-RESEARCH` | T3.0 part 1 - enumerate the per-tenant configuration surface | `not-started` | `-` | n/a | 1 run + 1 no-gate |
| `T30-SCHEMA` | T3.0 part 2 - configuration and credential storage in platform.sql | `not-started` | `-` | n/a | 1 run + 1 no-gate |
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
| `SEAM-REFRESH` | Refresh the seam chain onto a moved modernization branch | `not-started` | `seam/t1-2-storage-interface` | n/a | 2 run + 1 no-gate |
| `BFQ-66` | BF-66 - the deployment's own tokens fail its own tenant check | `blocked` | `crm-seam` | n/a | 0 run + 2 no-gate |
| `BFQ-CAP02` | CAP-02 - no importer, and no Mongo to PostgreSQL loader | `not-started` | `crm-seam` | n/a | 0 run + 2 no-gate |

### `T30-RESEARCH` &mdash; T3.0 part 1 - enumerate the per-tenant configuration surface

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |

**Blast radius.** A docs/60-research/ report. Every SETTINGS_* variable, every plugin credential, which are secrets and which are not, what a tenant may override versus what the hoster pins.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** research deliverable

**Gates.**

- `[static]` `test -f docs/60-research/tenant-config-surface-2026-09-15.md`
  - the deliverable exists. FAILS today. A file-existence gate is weak on purpose - it is honest about being a presence check, where a "state: done" field would have been an assertion.
- **NO GATE** &mdash; Nothing checks that the enumeration is COMPLETE. The only non-vacuous form is a differential: enumerate from the report, enumerate from lib/server/env.js by parsing, and require the two sets to agree - with a planted extra variable as the control. That harness does not exist.

**Evidence.**

- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** T3.0 is the largest correction owed in the programme. It does NOT block T3.3 - T3.3 landed first. It AMENDS T3.1, T3.2 and T3.3, which are all marked DONE- EXCEPT.

### `T30-SCHEMA` &mdash; T3.0 part 2 - configuration and credential storage in platform.sql

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `-` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | SECURITY - this is where D13's per-tenant credential root and D14's per-tenant signing key live |
| blocks on | `T30-RESEARCH` |

**Blast radius.** lib/admin/platform.sql. GT3 measured it as holding exactly two tables - tenants (L23) and tenant_members (L49) - with subject_id uuid NOT NULL at L52 and NO foreign key, no settings table, no secrets table and no signing-key column.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release schema

**Gates.**

- `[static]` `node tools/queue/gates/platform-sql-surface.js`
  - FAILS while platform.sql carries no signing-key column, no configuration table and no referent for tenant_members.subject_id. Re-runs GT3's grep as a machine check rather than a claim.
- **NO GATE** &mdash; D13 forbids any deployment-wide secret under TENANCY_MODE=multi on any interface. Nothing checks for one. A gate would have to enumerate every place a secret can enter and assert none is deployment-wide under multi - which is the T30-RESEARCH deliverable, so this is blocked on it in substance as well as in order.

**Evidence.**

- `docs/60-research/gt3-register-truth-2026-09-15.md`

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
| blocks on | `T30-SCHEMA` |

**Blast radius.** lib/server/tenant-context.js, lib/server/tenant-middleware.js, lib/authorization/index.js.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; The task is not started, so there is nothing to run. The gate it will need is the D14 property stated as a test: tenant A's token presented against tenant B's host fails as a SIGNATURE failure, not a claim check - with a control where the same token against A's own host succeeds, so the failure is known to come from the key and not from everything failing.

**Evidence.**

- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`

**Notes.** CORRECTS THE PLAN'S AMENDMENT TABLE. It cites tenant-context.js:137 as T3.3's site. GT3 measured L137 as the COMMENT stating the rejected reasoning; the mechanism is PER_TENANT_ENV_KEYS at L143 and the copy loop at L278 (`if (PER_TENANT_ENV_KEYS.includes(key)) continue;`). A spec naming only L137 changes a comment. Also enclave.js's key read is at line 30, not 29, and tenant-middleware.js's tenantClaim opens at L139 with verifyJWT at L144 - so the cited 139-143 stops one line short.

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

- **NO GATE** &mdash; Blocked on T30-SCHEMA - there is no per-tenant key to verify against until the column exists. Recorded now so that T3.1's DONE-EXCEPT does not read as DONE to an agent that only loads that section.

**Evidence.**

- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`

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
| blocks on | `T30-SCHEMA` |

**Blast radius.** lib/admin/platform.sql; tenant_members.subject_id references nothing.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; Same as T30-SCHEMA, which is the work. This row exists so T3.2's DONE-EXCEPT has a visible remainder rather than living only in a parenthesis in the plan.

**Evidence.**

- `docs/60-research/gt3-register-truth-2026-09-15.md`

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

**Blast radius.** lib/server/tenant-context.js - PER_TENANT_ENV_KEYS at L143 and the copy loop at L278, NOT L137 as the plan says. Plus the process-wide `language` instance at lib/server/server.js:34 and the one authorization subjects array.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; The enclave half is blocked on T30-WIRING. The language half is PARTLY discharged - BF-31 is fixed on bf/alarms (P0-A) - but `language` and `levels.translate` are still one process-wide instance, and authorization subjects remain one process-wide array. Neither has a test that would notice a second tenant.
- **NO GATE** &mdash; Tenant settings have no SOURCE. Overrides are an input to the substrate, not something read from storage. That is T30-SCHEMA's deliverable and until it exists there is nothing to gate.

**Evidence.**

- `docs/60-research/tenant-shared-state-audit-2026-09-15.md`

**Notes.** CORRECTS THE PLAN. T3.3's "not done" paragraph at L1189 still carries the claim BF-31's measurement REFUTED - "that is how alarm text reaches a push notification". It does not: the catalogue is read once at boot and never reloaded. The same paragraph uses the pre-renumbering id BF-22, which today means a different defect. A HAZARD THIS ROW CARRIES: plugins capture ctx.moment, ctx.language and ctx.levels at plugin INIT, not per call, so a per-tenant ctx cannot re-point any of them for an already-initialised plugin. That needs settling BEFORE a per-tenant ctx is designed.

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
  - the entrypoint exists. FAILS today - GT3 measured bin/ as holding only admin.js and feed.js.
- **NO GATE** &mdash; The DESIGN constraint cannot be gated by existence: the connection must NOT go through pgbouncer, because transaction-mode pooling accepts LISTEN and silently delivers nothing ({DB} §10.3). "Accepts and silently delivers nothing" is precisely the shape a naive test passes. The gate has to assert a delivered notification on a direct connection AND assert non-delivery through the pooler as its control.
- **NO GATE** &mdash; Reconnect storms and UNLISTEN churn are the interesting realtime case and are not covered anywhere (plan §7).

**Evidence.**

- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`

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
  - the entrypoint exists. FAILS today.
- **NO GATE** &mdash; §7b names three things the loop must not get wrong, none of which an existence check touches: `treatments` can WITHHOLD an alarm (treatmentnotify.js:64-75 snoozes every URGENT for 10 min after any treatment), `profiles` can withhold one via boluswizardpreview.highSnoozedByIOB, and only the NEWEST devicestatus document is needed despite it being the largest field. A loop that drops a withholding path fires alarms that should not fire.
- **NO GATE** &mdash; Residency tiering is NOT a prerequisite - §7b settled that - so an evaluator built around a resident per-tenant ddata would be building the expensive version of a cheap problem. Nothing prevents someone doing that; it is a design note with no gate.

**Evidence.**

- `docs/60-research/ns-evaluator-spike-2026-09-15.md`
- `docs/60-research/alarm-critical-slice-2026-09-15.md`

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

- **NO GATE** &mdash; Not started. The gate is stateable now and worth writing down: three tenants, the middle one throwing, and the THIRD tenant's alarm still arrives. Without the boundary, in a plain loop one tenant throwing means every LATER tenant is never evaluated - and the control that makes the test non-vacuous is a run with no thrower where all three arrive, because a test where nobody's alarm arrives also "passes" a badly written assertion.

**Evidence.**

- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`

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

- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`

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

- **NO GATE** &mdash; Unsettled by design, not by neglect. T4.4a chose wall time for ack; the rest is open. A batching or replaying evaluator cannot own its clock today, and until someone decides whether it may, there is nothing to test. Recorded as unsettled rather than not-started so nobody starts building against an undecided semantics.

**Evidence.**

- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`

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

**What an operator sees.** On a hosted multi-tenant Nightscout, alarms are switched off on purpose until this is finished. Nothing on a self-hosted single-tenant Nightscout is affected. Do not rely on a hosted deployment for alarms until this says otherwise, and talk to your care team about what you rely on alarms for.

**Why `n/a`.** pre-release

**Gates.**

- **NO GATE** &mdash; THE PLAN'S OWN WORDING, and it is the gate: "Alarms go back on when a test shows tenant A's alarm reaching A and not B, through the real producer path, with a snooze that survives a restart and a process change - not when the last row above is edited." That test does not exist. It is recorded as a no-gate rather than a to-do because a to-do that gets ticked is exactly the failure this sentence forbids.
- **NO GATE** &mdash; GT3 RE-DERIVED §7a's tally: it reads 3-of-7 done and the honest count is 1. Item 1 (durable ack/snooze) is genuinely done with two control arms. Item 6 says of itself that it "does not make per-tenant arming trustworthy". Item 5 (BF-31) was discharged by being found MISFILED - its own row text says it is a shared-state item, not an alarm-text one. So: 1 complete, 1 partial, 1 misfiled, 4 open.

**Evidence.**

- `docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md`
- `docs/60-research/gt3-register-truth-2026-09-15.md`

### `SEAM-REFRESH` &mdash; Refresh the seam chain onto a moved modernization branch

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `cgm-remote-monitor` |
| branch | `seam/t1-2-storage-interface` |
| base | `origin/chore/nightscout-modernization@0a4109f6` |
| worktree | `externals/work/crm-seam` |
| semver | `n/a` |
| review | maintainer |

**Blast radius.** 16 seam branches. GT1 measured the chain as LINEAR - all 15 others are ancestors of seam/t1-2-storage-interface (81a1f6ce), which is 50 commits ahead of 0a4109f6 and 0 behind.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** pre-release rebase mechanics

**Gates.**

- `[static]` `git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/chore/nightscout-modernization seam/t1-2-storage-interface`
  - the seam tip has not fallen behind its base. PASSES today. It goes red the moment the modernization branch moves - which is what RT-3 does.
- `[static]` `git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/chore/nightscout-modernization seam/t1-2-storage-interface >/dev/null`
  - the seam trial-merges into its base cleanly
- **NO GATE** &mdash; The release train moves the modernization branch under the seam. Nobody has measured what the seam's 50 commits cost to rebase after RT-3, and RT-REBASE shows the programme's track record on "costs zero rebase work today" claims.

**Evidence.**

- `docs/60-research/gt1-branch-inventory-2026-09-15.md`

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

- **NO GATE** &mdash; The REPRODUCTION exists and is recorded in the register - both modules executed on crm-seam 81a1f6ce with the exact minted payload, tenantClaim returning null and credentialRefusal returning "This credential does not name a Nightscout site", with a control token carrying a tenant field proceeding. It is not re-run as a queue gate because it would pin this item to one seam commit, and SEAM-REFRESH exists precisely because that branch has to move. Re-point the gate after the refresh, not before.
- **NO GATE** &mdash; IT FAILS SAFE - refusing rather than admitting - which is why it went unnoticed and why the severity is medium. Nothing gates "fails safe rather than open", and treating a safe failure as equivalent to an unsafe one is how a real refusal gets downgraded.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`

**Notes.** THE FIX BELONGS TO T3.0 AND SHOULD NOT BE TAKEN SEPARATELY. The task that introduces the per-tenant signing key (D14) is the task that chooses the payload; fixing this first would mean choosing the tenant claim twice. Filed as its own item rather than folded into T30-WIRING so the reproduced defect keeps an id a reviewer can find.

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
| blocks on | `T30-SCHEMA` |

**Blast radius.** One loader, plus whatever decides the BSON to jsonb transform. The outbound half already exists - exportTenant is a streaming server-side cursor in one repeatable-read transaction that declares its covered-table list before any row.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** a capability that does not exist yet; no surface moves

**Gates.**

- **NO GATE** &mdash; There is nothing to measure: the thing is absent. The first gate is the loader's own round-trip test - export a known corpus, load it, and assert the loaded rows equal the exported ones - with a control that plants a value the transform is known to mangle so a green result is known to distinguish. That test cannot exist before the loader does.
- **NO GATE** &mdash; THE TRANSFORM ITSELF IS UNSETTLED, which is the part that would make a naive loader silently lossy. scalarizeDoc turns Long, Decimal128, Binary, Int32 and Timestamp into jsonb OBJECTS, which the generated columns then read as SQL NULL with no error. Measured and recorded in the hosted migration plan §4.3; nothing gates it because no loader calls it yet.

**Evidence.**

- `docs/30-design/nightscout-backfix-register.md`
- `docs/40-migration/mongodb-to-postgres-hosted-2026-09-15.md`

**Notes.** §1c, so it is neither §1 nor §1b. ships_to_operators_today is false because an operator on today's release sees nothing - the capability is needed by hosted- tenant onboarding, which does not exist yet. Filed because the execution plan lists per-tenant EXPORT under "Endpoints (proposed, to be argued)" when it is implemented, and says nothing about import, so the asymmetry is invisible to a reader of either document. Prior art for the rehearsal shape, and NOT the missing piece - tools/rehearse-database-upgrade.py:76.

---

## Document-truth sweeps

`parcel: docs-truth` &mdash; 7 items

Rule 6 work. Agents read SECTIONS, not documents, so a fact stated twice and
differently is a live hazard, not untidiness. GT1/GT3/GT4 enumerated these.

| id | title | state | branch | semver | gates |
|---|---|---|---|---|---|
| `DOC-SEQUENCING` | phase0-pr-sequencing contradicts itself on the branch count | `not-started` | `main` | n/a | 1 run + 1 no-gate |
| `DOC-PLAN` | The execution plan's tallies and line references are stale | `not-started` | `main` | n/a | 0 run + 1 no-gate |
| `DOC-REGISTER` | The register's own header undercounts, and BF-27 has no detail section | `not-started` | `main` | n/a | 1 run + 4 no-gate |
| `DOC-EXPOSURE` | Say in the register that `fixed` does not mean an operator is safe | `not-started` | `main` | n/a | 1 run + 1 no-gate |
| `DOC-MEMORY` | The two memory files disagree with each other, and one cites a file that does not exist | `not-started` | `main` | n/a | 2 run + 1 no-gate |
| `DOC-LAYOUT` | The repository-layout preamble names the wrong shipping checkout | `not-started` | `main` | n/a | 1 run + 1 no-gate |
| `DOC-TESTSCRIPTS` | 52 test files match neither local test script | `not-started` | `origin/dev` | n/a | 1 run + 1 no-gate |

### `DOC-SEQUENCING` &mdash; phase0-pr-sequencing contradicts itself on the branch count

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@75c38a17` |
| worktree | `.` |
| semver | `n/a` |
| review | whoever edits it next - and it is HOT, edited by other sessions within the hour. Re-read immediately before editing. |

**Blast radius.** docs/30-design/phase0-pr-sequencing-2026-09-15.md.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation

**Gates.**

- `[static]` `node tools/queue/gates/doc-branch-count.js`
  - FAILS while the document states more than one branch count. GT1 and GT3 both found it: "five branches" in the title and at L3, "the seven Phase 0 branches", "all six other branches", "all seven" twice - and its own tables list A-I, which is nine, plus the unlettered bf/connect-pin, which is ten.
- **NO GATE** &mdash; The trial-merge matrix at L71-79 covers only 6 pairs among bf/reads, bf/coercion, bf/cache, bf/auth and bf/alarms. It PREDATES bf/food, bf/merge, bf/parms and bf/connect-pin, whose rows claim "clean against all six" / "all seven" in prose. The matrix was never extended to support those claims. Extending it is work, not a sweep.

**Evidence.**

- `docs/60-research/gt1-branch-inventory-2026-09-15.md`
- `docs/60-research/gt3-register-truth-2026-09-15.md`

**Notes.** Also at L388: it says master pins nightscout-connect as "^0.0.12", a semver range from npm. GT4 measured master as pinning the v0.0.13 TAG TARBALL. There is no npm-range pin anywhere in the tree. The ^0.2.12 on master is share2nightscout-bridge, a different package. And L165 lists bf/parms' commits in the wrong order.

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

**Blast radius.** docs/30-design/nightscout-multitenancy-execution-plan-2026-09-14.md at L7, L8, L351, L1189, and the T3.0 amendment table.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation

**Gates.**

- **NO GATE** &mdash; A prose tally cannot be gated without a machine-readable source for the number. THIS QUEUE is that source for the items it covers, so the honest fix is to make the plan cite queue/QUEUE.md rather than restate counts. Until it does, no gate.

**Evidence.**

- `docs/60-research/gt3-register-truth-2026-09-15.md`

**Notes.** GT3's list. L7 says "Phase 0 is done and is not the blocker any more", contradicted by its own L529 (T0.1 "In flight") and L541 (T0.3 "GATE NOT MET"). L8's tallies: "13 register entries closed" (actual 26 closed or partly), "3 new defects found" (actual 8, BF-32..BF-39), "4 register entries corrected as wrong" (at least 7). L351 and L1189 use "BF-22" for what is now BF-31. L1189 still carries the claim BF-31's measurement refuted. The T3.0 amendment table cites tenant-context.js:137, which is a comment.

### `DOC-REGISTER` &mdash; The register's own header undercounts, and BF-27 has no detail section

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@75c38a17` |
| worktree | `.` |
| semver | `n/a` |
| review | whoever edits it next - HOT, edited within the hour |

**Blast radius.** docs/30-design/nightscout-backfix-register.md at L26 and L41-53.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** documentation

**Gates.**

- `[static]` `node tools/queue/gates/register-rows-vs-details.js`
  - Every table row id has a detail section and vice versa. FAILS today: BF-27 has a row at L124 and NO detail section - the only id in the file without one. GT3 found this by programmatic set difference, and it resolves the earlier suspicion of "a stale detail heading or a second table": no such thing exists.
- **NO GATE** &mdash; The header's "Five entries have now had a claim fail on contact" is at least seven - the §1 table itself flags two the header omits, BF-08 and BF-30. The same undercount is copied into plan L8 and sequencing L526. Counting "claims that failed on contact" needs a marked field per entry, which the register does not have. Adding one is the real fix.
- **NO GATE** &mdash; The suppression-audit tally at L48-53 is stale. BF-39 is a THIRD defect from the no-useless-escape category, on BF-37's own site. Correct: five defects, 40 of 45, row = 2 sites / 3 defects. L41's "from BF-35, BF-36, BF-37 and BF-38. All four" should be five.
- **NO GATE** &mdash; Three entries contradict themselves on PROVENANCE - the one property the header says must be marked. BF-17, BF-30 and BF-31 each carry a prepended "reproduced against a running instance" block while their original bodies still read "*Not reproduced against a live instance.*"
- **NO GATE** &mdash; Two line references no longer resolve: BF-05's unfixed sibling console.log('Loading', opts) is at lib/authorization/storage.js:113, not :84; BF-09's block is websocket.js:538-566, not 535-568 (the seam interface document carries the same stale range).

**Evidence.**

- `docs/60-research/gt3-register-truth-2026-09-15.md`

**Notes.** BF-14's detail section contradicts ITSELF, which is what made a naive grep read it as open: L587 re-grades it to high and retracts "it returns no wrong data", then L594-600 restates that exact sentence in the present tense.

### `DOC-EXPOSURE` &mdash; Say in the register that `fixed` does not mean an operator is safe

| | |
|---|---|
| state (claimed) | `not-started` |
| repo | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@75c38a17` |
| worktree | `.` |
| semver | `n/a` |
| review | maintainer - this is the correction that changes how the whole register reads |

**Blast radius.** The register's status legend and every document that quotes "only three open entries affect an operator on today's release" - the plan, the sequencing document and memory/multitenancy-target-decision.md.

**What an operator sees.** A defect marked "fixed" in the project's register is fixed on a branch that has not been released. If you are running today's Nightscout, it is still there.

**Why `n/a`.** documentation

**Gates.**

- `[static]` `node tools/queue/gates/register-exposure-legend.js`
  - Parses the STATUS COLUMN of §1/§1b/§1c and reports how many defects are actually live for an operator today, then checks whether the legend SAYS so. REPLACED a `grep -q 'landed'` gate that passed vacuously - its only three hits were the legend line and two unrelated prose uses of the word. That gate was labelled "deliberately weak" in this manifest, but a PASS that means nothing renders identically to a PASS that means something, so it was laundering an assertion inside the very tool built to stop that. Now FAILS, correctly, on both counts.
- **NO GATE** &mdash; THE CORRECTION ITSELF cannot be gated: no entry anywhere has status `landed`, so the open/fixed column tracks WORK DONE, not operator exposure - and no document says so. A reader taking "3 open" as "3 defects still shipping" mis-sizes the release train by an order of magnitude. On today's release all 26 §1 defects are present for every self-hoster.

**Evidence.**

- `docs/60-research/gt3-register-truth-2026-09-15.md`

**Notes.** GT3 calls this its biggest correction and it is the reason this queue carries `ships_to_operators_today` as a field rather than inferring exposure from `state`.

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
  - memory/release-train-and-work-queue.md declares queue/work-queue.yaml the source of truth and queue/QUEUE.md generated from it. THE GATE THAT WAS HERE - `test -f queue/work-queue.yaml` - was vacuous BY CONSTRUCTION and not merely in practice: status.py loads the manifest before it runs a single gate, so if that file were missing the runner would abort and this gate could never be OBSERVED failing. A gate that cannot be seen to fail is not a measurement. `emit.py --check` asserts the stronger and actually-checkable half of the memory's claim: the generated view is not stale with respect to the source of truth.
- `[static]` `grep -q '^queue-status:' Makefile`
  - the same memory names `make queue-status` as the gate runner. GT3 measured no such target. Same reading as above.
- **NO GATE** &mdash; The two memory files still contradict each other on Phase 0's state - multitenancy-target-decision.md:67-68 says 0 of 5 with 29 open entries and tenancy work STOPPED, release-train-and-work-queue.md:13-14 says both halves are discharged. Reconciling them is an edit a human must make; no command can decide which is right.

**Evidence.**

- `docs/60-research/gt3-register-truth-2026-09-15.md`

**Notes.** memory/release-train-and-work-queue.md also declares queue/QUEUE.md generated, which this queue now makes true.

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
  - FAILS if externals/cgm-remote-monitor is presented as this programme's shipping checkout. GT1 measured it at 6893781f, a 2026-era brief pointing at a 2014-11-06 commit ("Merge pull request #207 from nightscout/release/0.5.0") on a DIFFERENT fork (origin = bewest/cgm-remote-monitor-1). It holds none of this programme's work. The real one is externals/cgm-remote-monitor-official.
- **NO GATE** &mdash; Briefs are composed outside this repository, so no gate here reaches them. The only durable fix is to correct the source the briefs are generated from, which is not a file in this tree.

**Evidence.**

- `docs/60-research/gt1-branch-inventory-2026-09-15.md`

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

**Blast radius.** package.json test:unit and test:integration brace lists. 159 files in tests/*.test.js; test:unit resolves to 44, test:integration to 89, union 107, leaving 52 matched by neither.

**What an operator sees.** _Nothing. No operator-visible change._

**Why `n/a`.** developer tooling

**Gates.**

- `[static]` `node tools/queue/gates/test-script-coverage.js`
  - FAILS while any tests/*.test.js matches neither brace list. This is GT1's finding turned into a standing measurement - the four files that are the evidence for the BF-35/36/37 batch are among the 52, so an agent told "run test:unit" would never execute BF-35's test and bf/food's clean 361-passing run is not evidence that BF-35's fix works.
- **NO GATE** &mdash; CI is NOT blind to this - main.yml runs test-ci, which is ./tests/*.test.js, all 159. The gap is in the LOCAL scripts only. So the fix is a convenience fix, and the reason it matters is that agents and contributors read the local scripts as the suite. Nothing can gate "a human believed the wrong thing".

**Evidence.**

- `docs/60-research/gt1-branch-inventory-2026-09-15.md`

**Notes.** Also: test:unit is NOT database-free. Without MongoDB it fails 6 tests (verifyauth x4, API_SECRET x2) on pristine dev. Every gate in this manifest that invokes test:unit is therefore filed as `integration`.

---

*End of generated view. Source: `queue/work-queue.yaml`.*
