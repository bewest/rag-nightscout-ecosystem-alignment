# GT1 — branch, worktree and commit inventory

> **Snapshot — inventory as of 2026-09-15, measured against `origin/dev a8888f0d` (main repo HEAD `9fc55eaa`→`8c379476`). Status: point-in-time; branch, push and test states have since changed — most `bf/*` branches are now merged to dev (unreleased); `bf/auth` and `fix/connect-timer-jitter` remain fixed-on-branch. Contributor-facing. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md), [work queue](../../../queue/work-queue.yaml).**

**Measured 2026-09-15, 17:05–17:55 local, by running git against the checkouts.** Nothing in this
document was taken from another document without re-measuring it. Main repo HEAD when this started
was `9fc55eaa`; it moved to `8c379476` during the run (another session committed). Every SHA below
was read from `git`, not from prose.

Audience: contributor-facing. Nothing here is operator- or user-facing.

---

## 0. Measured facts that differ from the working assumptions

| # | assumed | measured |
|---|---|---|
| **C1** | the `crm-*` worktrees belong to `externals/cgm-remote-monitor` | **They belong to `externals/cgm-remote-monitor-official`.** `git -C externals/cgm-remote-monitor worktree list` returns **one** entry — itself. Every `crm-*` worktree's `.git` file points at `externals/cgm-remote-monitor-official/.git/worktrees/…` |
| **C2** | `externals/cgm-remote-monitor` is "shipping code … detached HEAD `6893781f`" | `6893781f` is a **2014** commit — *"Merge pull request #207 from nightscout/release/0.5.0"*. Its `origin` is `bewest/cgm-remote-monitor-1`, a different fork. It holds **none** of this programme's work. The shipping-code checkout is `externals/cgm-remote-monitor-official` (`origin` = `nightscout/cgm-remote-monitor`, `origin/dev` = `a8888f0d`) |
| **C3** | 13 worktrees, `crm-bf-food` appears in no list | **16 `crm-*`/`nc-*` worktrees now.** `crm-bf-merge`, `crm-bf-parms` and `crm-base-verify` are also absent from the brief. `crm-base-verify` was created *during* this run |
| **C4** | "seven Phase 0 branches", five elsewhere | **Ten**, across two repos: nine lettered **A–I** in `phase0-pr-sequencing-…md` (rewritten at 17:06, after the brief was written) plus `bf/connect-pin`. The document still says "five" in its title, "seven" at line 28, "all six" at line 91 and "all seven" at lines 153/235 — four mutually inconsistent counts |
| **C5** | register has 34 entries, highest BF-34 | **38 entries, highest BF-38.** BF-35/36/37/38 were added today |
| **C6** | "only THREE open entries affect an operator on today's release — BF-16, BF-09, BF-10" | BF-16 is now **fixed** on `bf/food`, and fixing it turned up **BF-35**, a *high*-severity client defect that puts the wrong carb count into the bolus calculation. The count and the membership have both moved |
| **C7** | `test:unit` is "149 files, no database"; `test:integration` is "10 files" | `test:unit` is a brace list resolving to **44 files**; `test:integration` to **89**. `tests/*.test.js` is **159**. **52 files match neither list.** And `test:unit` **does** need MongoDB — `verifyauth` (4) and `security`/`API_SECRET` (2) fail without it |
| **C8** | "worktrees share one MongoDB instance and concurrent integration runs destroy each other" | **Already solved, by someone.** Each worktree's `my.test.env` names its **own port** (27030–27034, 27018, 27117), and where a port is shared the **database name differs** (`27033/testdb`, `27033/bffood_test`, `27033/bfmerge_test`, `27033/bfparms_test`). The collision risk the brief warns about does not exist as described |
| **C9** | "nothing has been pushed" | **True for all 9 `bf/*` branches, all 16 `seam/*` branches, `fix/connect-timer-jitter`, `release/v0.0.14` and tag `v0.0.14`** — verified by live `ls-remote`, not by stale tracking refs. **One exception:** `fix/quadratic-treatment-processing` `dfe2753d` **is on `origin`** as `bewest/wip/optimize-treatment-processing` (this is T0.1 / PR #8733, expected) |

---

## 1. Repositories

| path | role | HEAD | clean? |
|---|---|---|---|
| `externals/cgm-remote-monitor-official` | **the real cgm-remote-monitor.** `origin` = `nightscout/cgm-remote-monitor`, `official` = same over SSH, `bewest` = `bewest/cgm-remote-monitor` fork | detached `a8888f0d` (= `origin/dev`) | yes |
| `externals/cgm-remote-monitor` | **a 2014-era unrelated fork.** `origin` = `bewest/cgm-remote-monitor-1`. Not used by any Phase 0 work | detached `6893781f` (2014-11-06) | yes |
| `externals/nightscout-connect` | `origin` = `nightscout/nightscout-connect`. **No fork remote configured** | `649a7de` on **`release/v0.0.14`** | yes |
| `/home/bewest/src/rag-nightscout-ecosystem-alignment` | this repo (D12) | `8c379476` on `main` | **no** — see §6 |

Reference points: `origin/dev` = **`a8888f0d`**, `origin/master` = `92d08342`,
`origin/chore/nightscout-modernization` = **`0a4109f6`**. Connect: `origin/main` = `b394411`
(= tag `v0.0.13`), `origin/dev` = `6dfc4f0`, `origin/fix/modernization-debug-logging` = `b77e5bb`.

---

## 2. Worktree inventory

All 16 are **clean** (`git status --porcelain` empty in every one). Ahead/behind is against the
merge-base with the branch's base, which for every `bf/*` branch is `origin/dev` `a8888f0d` with
**0 behind** — the whole Phase 0 set is rebased current.

| worktree | branch / detached | head | base | ahead | pushed? | node_modules |
|---|---|---|---|---|---|---|
| `crm-bf-alarms` | `bf/alarms` | `5dcf783f` | `origin/dev` | 3 | no | own (255M, **no client bundle**) |
| `crm-bf-auth` | `bf/auth` | `64db1f35` | `origin/dev` | 2 | no | own (267M) |
| `crm-bf-cache` | `bf/cache` | `4f86bab1` | `origin/dev` | 2 | no | own (267M) |
| `crm-bf-coercion` | `bf/coercion` | `88d1f8a4` | `origin/dev` | 1 | no | own (267M) |
| `crm-bf-connect-pin` | `bf/connect-pin` | `0807eb1c` | `origin/dev` | 1 | no | **none**, and no `my.test.env` |
| `crm-bf-food` | `bf/food` | `73495331` | `origin/dev` | 1 | no | symlink → `crm-bf-reads` |
| `crm-bf-merge` | `bf/merge` | `b06c6faf` | `origin/dev` | 1 | no | symlink → `crm-bf-reads` |
| `crm-bf-parms` | `bf/parms` | `c9a7a21c` | `origin/dev` | 2 | no | symlink → `crm-bf-reads` |
| `crm-bf-reads` | `bf/reads` | `824380a0` | `origin/dev` | 7 | no | own (267M) |
| `crm-base-verify` | **detached** `a8888f0d` | `a8888f0d` | — | 0 | n/a | — |
| `crm-pool` | **detached** `239f8c25` | `239f8c25` | mid-`seam` chain | — | no | symlink |
| `crm-quadratics` | `fix/quadratic-treatment-processing` | `dfe2753d` | `origin/dev` | 1 | **YES** — `origin/bewest/wip/optimize-treatment-processing` and `official/…` | symlink |
| `crm-seam` | `seam/t1-2-storage-interface` | `81a1f6ce` | `origin/chore/nightscout-modernization` | 50 | no | own (273M) |
| `crm-tenant` | **detached** `239f8c25` | `239f8c25` | mid-`seam` chain | — | no | symlink |
| `crm-write` | **detached** `239f8c25` | `239f8c25` | mid-`seam` chain | — | no | symlink |
| `nc-jitter` | `fix/connect-timer-jitter` | `c1cce2a` | `origin/fix/modernization-debug-logging` `b77e5bb` | 1 | no | — |

Three notes a later agent needs:

- **`crm-pool`, `crm-tenant` and `crm-write` are all detached at the same commit, `239f8c25`**
  (*"Close the seam between the tenant reader and its writer"*), which is a **mid-chain** commit
  of `seam/t1-2-storage-interface`, not a tip. They carry no branch and no work of their own.
  They look finished-with. **Do not remove them** (rule 5) — flag them for their owner.
- **`crm-seam`'s admin directory is named `ns-seam-t12`**, not `crm-seam`. The worktree was moved
  and git keeps the original name. Anything matching admin-dir names to paths will miss it.
- **`crm-base-verify` did not exist at 17:00 and existed at 17:50.** Another session is working now.

---

## 3. The Phase 0 branch set, resolved

Ten branches. The `bf/*` set is **flat, not a stack**: every one is based directly on
`origin/dev` `a8888f0d`, 0 behind.

| # | branch | repo | commits (oldest → newest) | carries |
|---|---|---|---|---|
| **A** | `bf/alarms` | crm | `8714093b` insulinage urgent alarm could never fire<br>`99e46a52` ENABLE entry naming a file is silently ignored<br>`5dcf783f` one assistant request re-languages the process | BF-28, BF-29, BF-31 |
| **B** | `bf/cache` | crm | `ddcdb1a8` untyped `/api/v1/entries` read clones 48 h of CGM<br>`4f86bab1` two of three load-cycle reads copy the retained window | **T0.2** (BF-06), **T0.3** (BF-07, gate not met) |
| **C** | `bf/auth` | crm | `a26ba416` caller rotating `X-Forwarded-For` is never throttled<br>`64db1f35` editing a subject wrote its access token in plaintext | BF-30, **BF-17** (security) |
| **D** | `bf/coercion` | crm | `88d1f8a4` query filters compared numbers against text | **T0.5**: BF-02, BF-11, BF-03 (devicestatus+profile), BF-32 |
| **E** | `bf/reads` | crm | `4a398d47` count/:storage/where counted nothing<br>`c8fb536b` every count request printed its filter to stdout<br>`399dc283` v3 paging lost/repeated docs on a full sort tie<br>`ba70f1fc` v3 dotted `?fields=` returned `{}` with 200<br>`1640b64b` `?count=0` returned the whole collection<br>`ea50cf52` v3 `?limit=0x10` removed the bound<br>`824380a0` release notes | BF-01, BF-05, BF-13, BF-15, BF-14, BF-33 |
| **F** | `fix/connect-timer-jitter` | **connect** | `c1cce2a` every retry interval was 256 ms, first cycle had no jitter | **T0.4**, **BF-34** |
| **F′** | `bf/connect-pin` | crm | `0807eb1c` pin the connector to v0.0.14 | the pin move; **package.json only** |
| **G** | `bf/food` | crm | `73495331` the quick-pick chooser named one meal and loaded another | **BF-16**, **BF-35** (high) |
| **H** | `bf/merge` | crm | `b06c6faf` a delta that removed one treatment and missed on the next stopped the page | **BF-36** |
| **I** | `bf/parms` | crm | `522c6ffb` a bare flag in the URL stopped the page loading<br>`c9a7a21c` `%1` ate `%10`: substitution ran in prefix order | **BF-37**, **BF-38** |

The sequencing document's own trial-merge result stands: the only conflicting pair is
**`bf/coercion` + `bf/reads`**, and only on `CHANGELOG.md`.

### The `seam/*` chain (Phases 1–4), for completeness

16 local branches, none pushed, all based on `origin/chore/nightscout-modernization` `0a4109f6`,
all **0 behind**. Verified linear: **every one of the other 15 is an ancestor of
`seam/t1-2-storage-interface`**, which at `81a1f6ce` is 50 commits ahead and is the accumulated
tip despite its `t1-2` name (its subject is *"T4.4a: durable ack/snooze state…"*). Checkpoints, in
chain order: `t1-2-a` `256c6b58` (6) · `t1-2-b` `4ee593b1` (6) · `t1-2-c` `b5dc2cbb` (6) ·
`t1-2-d` `12ac8f51` (16) · `t1-2-e` `a2690bd4` (16) · `t2-4-allowlist` `987e9657` (22) ·
`t2-5-postgres-entries` `aaab43d0` (31) · `t3-h` `cd43f6d8` (33) · `t3-i` `20644452` (33) ·
`t3-j` `72565f82` (33) · `t3-k` `98afe513` (41) · `t3-l` `32872f61` (41) · `t4-m` `8f7117f1` (45) ·
`t4-n` `c8b456a7` (45) · `t4-o` `01c5b6d8` (45) · `t1-2-storage-interface` `81a1f6ce` (50).

---

## 4. What is actually pushed

Checked **live** with `git ls-remote` against both remotes, because the local tracking refs can be
a day stale (the sequencing document records exactly that trap).

| ref | on `origin` | on `bewest` fork | note |
|---|---|---|---|
| all 9 `bf/*` | **no** | **no** | `ls-remote --heads … refs/heads/bf/` returns nothing on either |
| all 16 `seam/*` | **no** | **no** | same |
| `fix/quadratic-treatment-processing` `dfe2753d` | **YES**, as `bewest/wip/optimize-treatment-processing` | — | T0.1 / PR #8733, in flight upstream. Not ours to land |
| connect `fix/connect-timer-jitter` | **no** | (no fork remote) | |
| connect `release/v0.0.14` | **no** | — | |
| connect tag `v0.0.14` | **no** | — | `origin` tags stop at `v0.0.13` = `b394411` |

`bewest` carries 7 heads, none of them ours. Rule 0 holds: **nothing from this programme has left
this machine.**

---

## 5. The connect release state — every claim confirmed

| claim | measured |
|---|---|
| `release/v0.0.14` exists at `649a7de` | **yes** — and it is the checked-out branch of `externals/nightscout-connect` |
| annotated tag `v0.0.14` exists locally | **yes** — `git cat-file -t v0.0.14` → `tag`; tagged by the maintainer; points at `649a7de` |
| tag is pushed | **no** — `ls-remote --tags origin` has `v0.0.12` `1e63c53` and `v0.0.13` `b394411`, nothing beyond |
| `v0.0.13` (`b394411`, `origin/main`) fast-forwards | **yes** — `merge-base --is-ancestor b394411 release/v0.0.14` succeeds. 11 commits, no merge to reconcile |
| `package.json` says `0.0.14` | **yes** |
| `package-lock.json` in `crm-bf-connect-pin` deliberately not updated | **confirmed, and correct.** `package.json:140` → `…/archive/refs/tags/v0.0.14.tar.gz`; `package-lock.json:58` and `:7894` still → `…/archive/234d47c85510a77f07b3be0d2c026dd0272715d6.tar.gz`. `0807eb1c` touches **one file, +1/−1**, and its message states the reason. `npm ci` will fail loudly as out-of-sync until the tag is pushed and `npm install` regenerates the lock in the same PR |

The 11 commits `b394411..649a7de` include the three log-redaction fixes the `dev` pin omits
(`9fa2c3c`, `5349d47`, `77e2396`), plus `8406edf`, `51b6e6e`, `234d47c`, `b77e5bb`, `c1cce2a`
(BF-34 + start jitter) and the `649a7de` version bump. `release/v0.0.14` differs from `c1cce2a` by
`package.json` and `package-lock.json` only.

---

## 6. Test state per branch — measured

**Command run: `npm run test:unit` only.** No integration run was started, per the brief.
Node v24.15.0. Each worktree used **its own** `my.test.env` and therefore its own MongoDB port.

### Baseline, measured not assumed

`origin/dev` `a8888f0d` in a throwaway worktree, MongoDB deliberately **unreachable**:
**355 passing, 6 failing** (total 361). The 6 are `API_SECRET` ×2 and `verifyauth` ×4 — all
25 000 ms connection timeouts. This matches the T0.5 evidence document's "361 on the base commit"
once the failures are counted back in.

### Results

| branch | mongod port | live? | result | verdict |
|---|---|---|---|---|
| `bf/alarms` | 27034 | **no** | **346 passing, 7 failing** | environment ×2 — see below |
| `bf/auth` | 27031 | yes | **361 passing, 0 failing** | **green** |
| `bf/cache` | 27033/`testdb` | yes | **371 passing, 0 failing** | **green** (matches its evidence doc exactly) |
| `bf/coercion` | 27030 | **no** | **368 passing, 6 failing** | **green** — the 6 are the identical baseline mongo failures; 374 total = the doc's claimed 374 |
| `bf/reads` | 27032 | yes | **361 passing, 0 failing** | **green** |
| `bf/food` | 27033/`bffood_test` | yes | **361 passing, 0 failing** | **green** |
| `bf/merge` | 27033/`bfmerge_test` | yes | **361 passing, 0 failing** | **green** |
| `bf/parms` | 27033/`bfparms_test` | yes | **362 passing, 0 failing** | **green** |
| `bf/connect-pin` | — | — | **not runnable** — no `node_modules`, no `my.test.env` | its diff is `package.json`, +1/−1 |

Live ports at measurement: 27017, 27018, 27019, 27023, 27031, 27032, 27033. **27030 and 27034 were
not listening**, which is the whole of the `bf/coercion` and most of the `bf/alarms` shortfall.

**The two `bf/alarms` causes, separated:**

1. Six failures are the baseline mongo-down set. The three failing files (`careportal`,
   `security`, `verifyauth`) are **byte-identical** (`cmp`) to `bf/reads`'s copies, and
   `git diff --name-only origin/dev bf/alarms` touches none of them or the code they exercise.
2. The seventh is **a missing build artifact, not a defect**:
   `Error: benv-shim.require: file not found: …/node_modules/.cache/_ns_cache/public/js/bundle.app.js`
   in `careportal`'s `before all`. `crm-bf-alarms` is the **only** worktree whose `node_modules`
   lacks that bundle (`crm-bf-auth`, `-cache`, `-coercion`, `-reads`, `crm-seam` all have it).
   Fix: `npm run bundle` in `crm-bf-alarms`. This also explains the ~9 missing passes.

### Non-vacuity (rule 2) — the unit suite was broken to prove it catches

Each branch's changed unit-list test file was copied onto **pristine `origin/dev` code** and run:

| test file | from | on `dev` code |
|---|---|---|
| `tests/insulinage.test.js` | `bf/alarms` | **2 failing** (3 passing) |
| `tests/plugins.test.js` | `bf/alarms` | **8 failing** (5 passing) |
| `tests/data.cache-clone.test.js` | `bf/cache` | **8 failing** (2 passing) |
| `tests/query.test.js` | `bf/coercion` | **cannot even load** — `Cannot find module '../lib/server/query-coercion'` |
| `tests/language.test.js` | `bf/parms` | **1 failing** (16 passing) |

Every one distinguishes fixed from unfixed. The suite is not vacuous for the fixes it covers.

### But the unit suite does not cover most of this work — a real gap

On `dev`: **159** `tests/*.test.js`; `test:unit` resolves to **44**, `test:integration` to **89**,
union **107**. **52 files match neither script.** Among them are four that matter here:

| test file | branch | covered by `test:unit`? | by `test:integration`? |
|---|---|---|---|
| `tests/boluscalc.quickpick.test.js` | `bf/food` — **BF-35, high** | no | **no** |
| `tests/receiveddata.merge.test.js` | `bf/merge` — BF-36 | no | **no** |
| `tests/browser-utils.queryparms.test.js` | `bf/parms` — BF-37 | no | **no** |
| `tests/dataloader.test.js` | `bf/cache` — the dead `mills` write | no | **no** |

CI is **not** blind to them: `.github/workflows/main.yml` runs `npm run-script test-ci`, which is
`mocha … ./tests/*.test.js` — all 159. The gap is in the **local** scripts. An agent told "run
`test:unit`, and `test:integration` needs a database" will never execute BF-35's test at all, and
the `361 passing` on `bf/food` is therefore **not** evidence that BF-35's fix works.
Use `npm test` (whole tree) for a branch's own evidence.

### Integration — claimed by each branch's evidence document, **not re-run here**

| branch | document claim |
|---|---|
| `bf/reads` | full suite **2063 passing, 3 pending, 0 failing** |
| `bf/cache` | `test:integration` **756 passing, 3 pending**; `npm test` **2040 passing, 0 failing** |
| `bf/coercion` | `test:integration` **754 passing, 3 pending, 0 failing** |
| `bf/auth` | full suite **2047 passing / 3 pending / 0 failing**, MongoDB 7 on port 27031 |
| `bf/alarms` | integration selection (`api`, `api.alexa`, `api.googlehome`, `notifications`) green; unit selection **332 passing / 21 failing**, all 21 asserted pre-existing |
| `bf/food`, `bf/merge`, `bf/parms`, `bf/connect-pin` | no integration figure located |

`bf/alarms`'s document reports 21 failures where I measured 7. Different environment (it counted
`purifier` ×13, which is outside the `test:unit` brace list). Neither figure is a defect claim.

---

## 7. Concurrent activity — what not to clobber

`git status` in the main repo: **one** modified file.

| file | state | last touched | read |
|---|---|---|---|
| `tools/qc/pgbouncer-tenant-binding.js` | **uncommitted, +600/−156** | **12:09**, ~5 h ago | Last commit touching it is `c884a472` (11:10). It has sat untouched for five hours, so it is **stranded**, not live. Its owning session appears to have moved on. Do not commit it blind; ask before touching |

Files modified in the last three hours (all committed):

| file | mtime | by |
|---|---|---|
| `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md` | **17:06** | `8c379476` — added branches G/H/I |
| `docs/30-design/remedial/nightscout-backfix-register.md` | **17:04** | `9fc55eaa` — BF-35…BF-38 |
| `docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md` | 16:42 | `4382d8f8` |
| `docs/60-research/tenancy/multitenancy-k-and-residency-2026-09-14.md` | 15:19 | |
| `tools/mt-bench/vcherd.js` + `tools/mt-bench/results/exp-mt-048b-*.json` | 14:50–15:18 | T0.4 |
| `tools/nsschema/emit/coercion_emit.py`, `specs/jsonschema/generated/**` | 14:45 | T0.5 |

**The two hot documents are `phase0-pr-sequencing-2026-09-15.md` and
`nightscout-backfix-register.md`** — both written to within the last hour, both by other sessions.
Re-read either immediately before editing. The sequencing document currently contradicts itself on
the branch count in four places (C4); a later agent should sweep it (rule 6).

`crm-base-verify` appeared under `externals/work/` during this run, detached at `a8888f0d`. At
least one session is active in the shipping checkout right now.

### Worktree hygiene, for its owners — nothing was removed

- `crm-pool`, `crm-tenant`, `crm-write`: three worktrees, one commit (`239f8c25`), no branches.
- `crm-seam`: admin directory is `ns-seam-t12`.
- `crm-bf-alarms`: needs `npm run bundle` before its `careportal` tests can pass.
- `crm-bf-connect-pin`: no `node_modules`, no `my.test.env` — cannot run any suite as it stands.
- Nothing is prunable; `git worktree prune -n -v` is silent.
