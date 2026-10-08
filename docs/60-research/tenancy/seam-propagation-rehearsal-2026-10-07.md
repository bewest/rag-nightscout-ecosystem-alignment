# Seam propagation rehearsal: the Phase 1 prefix by merge and by rebase

> **Snapshot — measured 2026-10-07 against `official/dev` `43289dde`, `official/chore/nightscout-modernization` `b1bdaca0` and `seam/t1-2-e` `a2690bd4`. Status: evidence for queue item `RT-PROPAGATION`, not the decision. Throwaway rehearsal: the two `prop/*` branches are local, unpushed, and are not the real refresh. Plan: [execution plan](../../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) §5, §5.1.**

*Audience: contributors and the maintainer deciding `RT-PROPAGATION`.*

Harness and raw results: [`tools/lab/seam-propagation/`](../../../tools/lab/seam-propagation/).
Every figure below is **measured** (a command was run) unless it is labelled **read**.

## 0. Setup

| item | value |
|---|---|
| shipping clone | `externals/cgm-remote-monitor-official`, remote `official`, fetched 2026-10-07T21:25Z |
| worktrees (created for this run) | `externals/work/crm-prop-{merge,rebase,base-mod,base-dev,seam-e,seam-s}` |
| branches (created for this run) | `prop/merge-prefix`, `prop/rebase-prefix` |
| Node | 22.23.2 for every suite (inside both `^22.23.2 \|\| ^24.20.0` and `>=20.x`); 20.20.0 additionally for dev and the rebased prefix |
| MongoDB | container `prop-mongo`, image `mongo:6.0.27`, server version read back as `6.0.27` before each suite (6.0 is in both branches' CI matrices) |
| driver | read from each tree's `node_modules/mongodb/package.json`: 7.6.0 on modernization-based trees, 5.9.2 on dev-based trees |
| suite command | each tree's own `npm test`, `tests/ci.test.env` with the connection string pointed at a per-run database (`tools/lab/seam-propagation/suite.sh`) |

### 0.1 Seam tips, before and after

Recorded at 2026-10-07T21:25:28Z with
`git for-each-ref --format='%(refname:short) %(objectname)' refs/heads/seam/`
([before](../../../tools/lab/seam-propagation/results/seam-tips-before.txt),
[after](../../../tools/lab/seam-propagation/results/seam-tips-after.txt)):

| branch | before | after |
|---|---|---|
| `seam/t1-2-a` | `256c6b58` | unchanged |
| `seam/t1-2-b` | `4ee593b1` | unchanged |
| `seam/t1-2-c` | `b5dc2cbb` | unchanged |
| `seam/t1-2-d` | `12ac8f51` | unchanged |
| `seam/t1-2-e` | `a2690bd4` | unchanged |
| `seam/t1-2-storage-interface` | `81a1f6ce` | unchanged |
| `seam/t2-4-allowlist` | `987e9657` | unchanged |
| `seam/t2-5-postgres-entries` | `aaab43d0` | unchanged |
| `seam/t3-h` … `seam/t3-l` (5) | `cd43f6d8`, `20644452`, `72565f82`, `98afe513`, `32872f61` | unchanged |
| `seam/t30-schema-cred` | `81a1f6ce` | **`65ce54b9`** |
| `seam/t4-m`, `t4-n`, `t4-o` | `8f7117f1`, `c8b456a7`, `01c5b6d8` | unchanged |

`seam/t30-schema-cred` moved during the run. This rehearsal did not move it: its reflog shows it
was created from `seam/t1-2-storage-interface` at 14:25:28 PDT (the same second as the "before"
record) and fast-forwarded by a commit, "T3.0: per-tenant credential storage in the platform
schema", at 14:41:21 PDT, in the `crm-t30-cred` worktree, which belongs to another session.
The other 16 tips are byte-identical.

### 0.2 Distances re-measured

`git rev-list --left-right --count A...B` and
`git merge-tree --write-tree --name-only --no-messages A B | tail -n +2 | grep -c .`:

| A | B | behind / ahead | conflicting paths |
|---|---|---|---|
| `official/dev` `43289dde` | modernization `b1bdaca0` | 246 / 498 | 27 |
| modernization | `seam/t1-2-e` `a2690bd4` | 68 / 16 | 8 |
| `official/dev` | `seam/t1-2-e` | 311 / 511 | 43 |
| modernization | `seam/t1-2-storage-interface` `81a1f6ce` | 68 / 50 | 19 |
| `official/dev` | `seam/t1-2-storage-interface` | 311 / 545 | 50 |
| `official/dev` | cuts 1–4 (`bce12ecc`, `b6e8c7cd`, `ebb690cf`, `b80aa147`) | 370 behind each | 12 / 19 / 22 / 36 |

All match the figures in the brief.

## 1. Merge path: `prop/merge-prefix`

```
git worktree add externals/work/crm-prop-merge -b prop/merge-prefix seam/t1-2-e
git -C externals/work/crm-prop-merge merge --no-ff official/chore/nightscout-modernization
```

Result: merge commit **`16222c97`**. 8 conflicting paths, 14 hunks, 21 lines in the result that
appear in neither parent (`git diff-tree --cc -p 16222c97 | grep -c '^++'`). Agent wall-clock
from `git merge` to commit: 21:27:22–21:29:17Z (1 min 55 s).

None of the four §4.1 write-rule modules (`object-id-forms`, `srv-dates`, `soft-deleted`,
`treatment-fallback-key`) exists on the modernization branch (`git cat-file -e
official/chore/nightscout-modernization:lib/server/<module>.js` fails for all four), so no
merge-path conflict involves one.

| path | hunks | upstream change met | kind | resolution | judgement? |
|---|---:|---|---|---|---|
| `lib/authorization/storage.js` | 1 | `06b133a7` (`?count=0` read rule: `count.applyCount` on a cursor) | upstream fix vs seam rewrite | drop the cursor `limit()` helper (no cursor on the seam); `limit: countParam.parseCount(opts && opts.count) \|\| undefined` | mechanical: `findFiltered` skips `.limit` for `undefined`, which is `applyCount`'s `null` case |
| `lib/server/activity.js` | 2 | `06b133a7` | same | same | mechanical |
| `lib/server/devicestatus.js` | 2 | `06b133a7` | same | same | mechanical |
| `lib/server/entries.js` | 2 | `06b133a7` | same | keep the seam's comment; same `limit` | mechanical |
| `lib/server/profile.js` | 1 | `06b133a7` | require lines | keep both | mechanical |
| `lib/server/treatments.js` | 1 | `06b133a7` | same | same | mechanical |
| `lib/server/food.js` | 1 | `73495331` (quick-pick: `hidden $nin [true,'true']`, numeric sort after fetch) | upstream fix vs seam rewrite | `cmp('nin', 'hidden', [true, 'true'])` through `findFiltered`, then `.sort(quickpick.byPosition)`; dropped the seam's query-side `position` sort | small: the AST has `nin`; kept the sort in JS because the upstream commit moved it there on purpose |
| `lib/server/aggregate.js` | 4 | BF-70 (`refusePipeline`), `3b588098` (no filter logging on the request path), `4772b983` (`api.query_for`) | upstream security and privacy fixes vs seam `count()` | seam's `storage.count()` body; upstream's `refusePipeline()` 400 and unconditional `api.query_for`; removed the seam's `console.log('$match query', query)` | **yes**: chose the seam's body and upstream's refusal; the `conf.pipeline` hook question in §1.1 follows from it |

### 1.1 Merge-path suite

| tree | tree id | passing | pending | failing |
|---|---|---:|---:|---:|
| modernization `b1bdaca0` (baseline) | `73228b6b` | 2426 | 1 | 0 |
| `seam/t1-2-e` `a2690bd4` (for reference) | `991f65f2` | 2213 | 1 | 0 |
| `prop/merge-prefix` `16222c97` | `b7234f6f` | 2476 | 1 | **4** |

The four failures are modernization tests that arrived with its dev merge `e3b22034`:

| test | cause | kind |
|---|---|---|
| `api-v1-count-pipeline` "still counts normally when no pipeline is named" | the test stubs the collection with `aggregate()` only; the seam calls `countDocuments()` | test pins the driver call shape |
| `api-v1-count-pipeline` "still answers the ordinary count over HTTP" | same stub, 500 | test pins the driver call shape |
| `api-v1-count-pipeline` "keeps the server-side conf.pipeline hook working" | BF-70 deliberately kept `conf.pipeline` as a server-side hook; the seam's `count()` runs no pipeline and throws | **design difference**, open |
| `api.count-parameter` "never asks the driver for limit(0)" | the spy replaces `ctx.store.collection` after the module is built; the seam memoizes its handle on first use, so the spy sees no call. `parseCount() \|\| undefined` cannot produce `limit(0)` | test pins per-call collection lookup |

The prefix's done criterion is an unchanged suite (§5.1). On the merge path it is not unchanged
until the three tests are re-expressed and the `conf.pipeline` question is decided. Neither was
done here.

## 2. Rebase path: `prop/rebase-prefix`

### 2.1 What "rebase onto dev" has to mean

A plain `git rebase --rebase-merges 43289dde` from `seam/t1-2-e` replays the modernization
branch's own commits as well, because the seam sits on top of them. The first stop was
modernization's dev merge `0a4109f6` with 37 conflicting paths. It was aborted. Re-parenting only
the seam's 16 commits needs the old base named:

```
git -C externals/work/crm-prop-rebase rebase --rebase-merges --onto 43289dde 0a4109f6
```

`--rebase-merges` keeps the prefix's three merge commits. None of them carries resolution content
(`git diff-tree --cc -p <merge>` is empty for `e82da8a2`, `fc8c5d40`, `73d69b46`), and all three
replayed without conflict.

**Difference from the plan:** §5.1 places the prefix "after `RT-3`" under a rebase. `RT-3` is
not built, so this rebase targets dev itself. §2.3 measures what the prefix needs from cuts 2–3.

### 2.2 Per-commit stops

Result before follow-up: `29c7c1fa`. 10 of the 13 non-merge commits changed (`git range-diff
0a4109f6..seam/t1-2-e 43289dde..29c7c1fa`: 10 `!`, 3 `=`). 14 stops' worth of content conflicts:
**58 hunks in 11 distinct lib files**, plus 9 modify/delete events on 8 test files. Agent
wall-clock from `--onto` to finish: 21:29:59–21:37:40Z (7 min 41 s), plus a follow-up commit
after the suite (§2.4). Full stop log:
[`rebase-stops.txt`](../../../tools/lab/seam-propagation/results/rebase-stops.txt).

| seam commit | path | hunks | dev change met | §4.1 rule? | resolution | judgement? |
|---|---|---:|---|---|---|---|
| `12a83d61` leaks | `api3/storage/mongoCollection/index.js` | 2 | #8758 `findEveryForm`/`updateEveryForm`/`deleteEveryForm` on `self.col` | object-id-forms | keep dev's methods, bound to the closure `col` | mechanical |
| `b0709c2c` escape hatches | `.../find.js` | 1 | context: modernization's `mongo-read-options` require | — | keep `toMongo` and the JS guard; drop `READ_OPTIONS` (not on dev) | mechanical. **Per-commit only:** `find.js` is not in the tip's 43 |
| | `.../modify.js` | 1 | dev's export list (#8758) | object-id-forms | union of exports | mechanical; **plus a silent hazard (H1)** |
| `3c8bd748` activity | `lib/server/activity.js` | 5 | #8758 stored `_id` form, stale string twins, both-forms delete; dev count rule | object-id-forms | `toStoredId` before `cmp('eq','_id')`; twins deleted through `store().deleteMany(fromMongo({_id:{$in:stale}}))` after `bulkUpsert`; `idFilter` remove through `fromMongo`; count rule: `isZeroCount` → `[]`, `parseCount` limit | **yes**: the twin delete leaves the ordered bulk write and becomes a second call; **plus silent hazard (H2)** |
| `256c6b58` food+devicestatus | `lib/server/devicestatus.js` | 5 | re-send identity (`withoutStoredIds`), `srv-dates`, `soft-deleted`, `stored_query_for` | three rules | re-send read through `findFiltered` with projection; `insertMany` through the seam with dev's `ordered:false` and its `writeErrors`/`11000` handling | **yes**: MongoDB's `writeErrors` shape now crosses the interface (§4 item 1 says it must not) |
| | `lib/server/food.js` | 10 | `object-id-forms`, `srv-dates`, `soft-deleted`, BF-35 | three rules | `srv-dates.carryForReplace` stays on the raw collection, AST filters rendered back with `toMongo`; `softDeleted.visible()` through `fromMongo` (×3); twins as activity | **yes**: srv-dates is driver-shaped and left outside the interface; **plus H2 ×2** |
| `4ee593b1` entries+profile | `lib/server/entries.js` | 4 | upsert with `$set`/`$setOnInsert{_id,srvCreated}`/`$unset{isValid}`; both-forms `getEntry` | three rules | **seam conversion of entries create dropped**: stays `api().bulkWrite` with dev's ops. Remove and `getEntry` through the seam | **yes**: `bulkUpsert` cannot express insert-only fields or unsets; an interface change belongs to `WRITE-CONTRACT` |
| | `lib/server/profile.js` | 6 (+1 auto-merged raw read) | stored-as-string set, `srv-dates`, soft-delete, twins | three rules | as food; the auto-merged `idsStoredAsString` read moved onto `findFiltered` | yes (as food) |
| `b5dc2cbb` auth+count | `lib/authorization/storage.js` | 7 | owned fields, usable name, `keepStoredFields` (`a8f75da5`, `1942920a`, `7103f657`), `idFilter` remove, `query_for` list | object-id-forms | keep dev's rules; `keepStoredFields` reads through the seam; list takes **dev's** `query_for` semantics | **yes**: modernization refuses any `find` on this list (`71c42c9a`, a cut-3 commit not on dev) while dev routes it through `query_for` (`f8b5138a`); dev's was kept |
| | `lib/server/aggregate.js` | 3 | BF-70 | — | as the merge path | yes (as §1) |
| | `tests/count-pipeline-boundary.test.js` | modify/delete | modernization-only file | — | removed; its 2 seam tests need the cut-5-only `lib/middleware/configure-request` | **yes**: test coverage dropped |
| `a7c6efbc` treatments | `lib/server/treatments.js` | 9 | BF-130 interleaved twin deletes, `srv-dates`, `treatment-fallback-key`, count rule | four rules | **seam conversion of the batch create dropped**: stays `api().bulkWrite`, because BF-130 places each `deleteMany` immediately after its `replaceOne` inside one ordered bulk write | **yes** |
| `1eba42df` reconcile | `aggregate.js` / `devicestatus.js` / `entries.js` | 2 / 1 / 2 | — | — | entries list onto `findFiltered` with dev's count rule; pass-through `deleteMany` result | mechanical; **plus silent hazard (H3)** |
| `a2690bd4` T1.3 | 8 test files | modify/delete ×8 | modernization-only files | — | removed; T1.3's backend tagging on them is dropped and must be redone when the cuts bring the files | **yes** |

Of the 11 lib files, 7 call a 15.0.9 write rule on dev: `activity`, `devicestatus`, `entries`,
`food`, `profile`, `treatments` and `lib/authorization/storage.js`.

### 2.3 Silent hazards: auto-merged lines that break the result

Git reported no conflict on these lines. Each was found by reading the merged file, then
reintroduced on the finished branch to see whether the suite catches it
(`tools/lab/seam-propagation/hazards.sh`):

| id | site | what the auto-merge produced | full suite with the hazard reintroduced on `b894ec76` |
|---|---|---|---|
| H1 | `api3/storage/mongoCollection/modify.js` | dev's removal of the `assert-no-query-javascript` require, while the seam's `deleteMany`/`count`/`bulkUpsert` still call it | **red**: 3300 passing / 218 failing (`ReferenceError: assertNoQueryJavascript is not defined`) |
| H2 | `lib/server/activity.js` (and `food.js` ×2) | `idForms.withStaleStringsRemoved(bulkOps, …)` pushing a driver-shaped `{deleteMany:…}` into the seam's `{filter, doc}` list | **red**: 3602 / 14; 9 extra failures in #8758's CRUD-by-id matrix |
| H3 | `lib/server/devicestatus.js` `remove()` | `fromMongo(query_for(opts))`, the soft-delete-visible filter, where dev uses `stored_query_for` | **not caught**: 3611 / 5, the same five as the clean branch |

H3 is a real behaviour difference. `tools/lab/seam-propagation/ds-remove-softdeleted.js` stores
one live and one `isValid: false` devicestatus, then calls `remove()` with a matching filter:
dev and the clean rebased branch delete both (`deletedCount: 2`); with H3 the soft-deleted record
survives (`deletedCount: 1`). The same one-line break on dev itself
(`api().deleteMany(query_for(opts))`) shows the same difference and leaves dev's suite green
(3564 / 0). So dev's suite does not pin which filter devicestatus `remove()` uses.

### 2.4 Rebase-path suite

The first suite on `29c7c1fa` was 3601 passing / 15 failing. Ten of the extra failures
(treatment POST/PUT 500s and two storage timeouts) had one cause, `TypeError: unsupported operator
'$not' on field 'syncIdentifier'`, 18 occurrences. `treatment-fallback-key` (#8780) matches an
empty identity with `{$in: [null, ''], $not: {$type: 'array'}}`, and the seam's filter AST has
neither `$not` nor `$type`, so `fromMongo` refuses every v1 treatment write that falls back to it.

Follow-up commit `b894ec76` (choice): treatments `upsertOne`/`findOneBy` stay on the raw
collection; also removed an unused `cmp` import the entries resolution left behind.

| tree | Node | tree id | passing | pending | failing |
|---|---|---|---:|---:|---:|
| dev `43289dde` (baseline) | 22.23.2 | `8c2e85b5` | 3564 | 4 | 0 |
| dev `43289dde` (baseline) | 20.20.0 | `8c2e85b5` | 3564 | 4 | 0 |
| `prop/rebase-prefix` before follow-up `29c7c1fa` | 22.23.2 | `85c56d56` | 3601 | 4 | 15 |
| `prop/rebase-prefix` `b894ec76` | 22.23.2 | `56dc072f` | 3611 | 4 | **5** |
| `prop/rebase-prefix` `b894ec76` | 20.20.0 | `56dc072f` | 3611 | 4 | **5** |

The five residual failures: the same three `api-v1-count-pipeline` tests as the merge path (dev
carries that file too), and two in `api.devicestatus.resend-guard`, whose spies replace
`ctx.store.collection` after the module has memoized its interface handle (the same kind as
merge-path failure 4). None is a driver or Node error. Lint (`npx eslint lib`): the same 5 errors
as dev, plus one warning in the seam's `lib/storage/filter.js`.

### 2.5 Driver 7 and Node 22/24: measured answer

**The prefix's own code runs on dev's MongoDB driver 5.9.2 and on Node 20.20.0 and 22.23.2.**
Every driver call the prefix adds (`bulkWrite`, `countDocuments`, `deleteMany`, `find`,
`insertMany`, `updateMany`, and cursor `limit`, `project`, `skip`, `sort`, `toArray`; from `git
diff 0a4109f6 seam/t1-2-e -- lib`) runs in the suites above with no driver or engine error.

What the prefix does take from the modernization branch is two **driver-neutral modules**, which
the rebase re-expressed in dev's idiom rather than carrying:

| module | first on | content | prefix use |
|---|---|---|---|
| `lib/storage/mongo-read-options.js` | cut 3 (`b8fd24c6`, "prepare MongoDB 7 migration with bounded read batches") | `Object.freeze({batchSize: 1000})` | `READ_OPTIONS` in 8 lib files; dropped (dev passes none) |
| `lib/utils/callback-tasks.js` | cut 2 (`26d0908a`) | bounded callback runner | `treatments.js` context only; dev's own mechanism kept |

Its tests also lean on cut-5-only `lib/middleware/configure-request` and on 8 modernization-only
test files (§2.2), which is the coverage the rebase dropped.

Not measured: the full chain (`seam/t1-2-storage-interface`, which adds the `pg` driver and
tenancy) on driver 5, and Node 24.

## 3. The `$exists` overlap in `lib/server/query.js`

Inputs: two entries, `has` (with `sgv`, `mbg`, `pump`, `noise`) and `lacks` (with `sgv` only),
run through each tree's own `lib/server/entries.js` `list()`. That is the raw driver on dev and
modernization, and `findFiltered(fromMongo(...))` on the seam trees
(`tools/lab/seam-propagation/exists-diff.js`). Cells are the matched documents; `-` is none.

| case | dev | mod | prefix `a2690bd4` | full chain `81a1f6ce` | merge `16222c97` | rebase `b894ec76` |
|---|---|---|---|---|---|---|
| `find[mbg][$exists]=true` | has | has | **lacks** | has | has | has |
| `find[mbg][$exists]=false` | lacks | lacks | lacks | lacks | lacks | lacks |
| `find[pump][$exists]=true` | has | has | has | has | has | has |
| `find[pump][$exists]=false` | lacks | lacks | **has** | lacks | lacks | lacks |
| `find[mbg][$exists]=` (empty) | has | has | lacks | **lacks** | **lacks** | **lacks** |
| `find[pump][$exists]=` (empty) | has | has | lacks | **lacks** | **lacks** | **lacks** |
| `find[mbg][$exists]=%20false%20` | has | has | lacks | **lacks** | has | has |
| `find[pump][$exists]=FALSE` | lacks | lacks | **has** | lacks | lacks | lacks |
| `find[mbg][$exists]=0` | lacks | lacks | lacks | lacks | lacks | lacks |
| `find[mbg][$exists]=no` | has | has | **lacks** | has | has | has |
| `find[mbg][$not][$exists]=false` | refused (BF-04 allowlist) | refused (allowlist) | refused by `fromMongo` | refused (allowlist) | refused (allowlist) | refused (allowlist) |
| `$or` of `mbg $exists false`, `noise $exists true` | has, lacks | has, lacks | has | has, lacks | has, lacks | has, lacks |
| `sgv $exists true` + `sgv $gte 50` | has, lacks | has, lacks | **-** | has, lacks | has, lacks | has, lacks |
| `sgv $gte 50` + `sgv $exists false` (other key order) | - | - | - | - | - | - |

(The rebase column was measured on `29c7c1fa`. `b894ec76` changes only treatments and an import
in entries.js, and does not touch the query path. The merge and rebase trees' `query.js`,
`query-coercion.js` and `query-coercion.json` are byte-identical to their bases: `git diff --stat
<base> <branch> -- <those>` is empty.)

**Answer.** Dev's schema-driven coercion covers the ordering the seam's handles. The seam
coerces before the walker and detaches `$exists` from it. Dev runs the walker first, with
`coercion.isValueLeaf()` keeping it off non-value operands, then normalizes. On every case where
the walker could touch `$exists` (typed `mbg`/`sgv`, nested `$or`, both key orders with `$gte`),
the two agree. They differ only on operand **spellings**: the seam's `existsArgument()` reads `''`
and whitespace-padded `' false '` as false. Dev's `readBooleanOperand()` deliberately leaves both
alone (its comment: guessing on `''` "would silently invert somebody's query"), and MongoDB then
reads them as true.

Non-vacuity, each on the identical setup with the unmodified run as its positive control
([`results/ctl-*.jsonl`](../../../tools/lab/seam-propagation/results/)):

| break | tree | rows that change | symptom reproduced |
|---|---|---|---|
| comment out `normalizeOperands(query)` | merge | 6, e.g. `mbg $exists=false` lacks → **has** | the older string defect: `$exists=false` returns documents having the field |
| walker converts every leaf (`if (true \|\| coercion.isValueLeaf(path))`) | merge | 4, e.g. `mbg $exists=true` has → **lacks** | the T1.2 walker regression e0564167 describes (`parseInt('true')` = NaN, then `!!NaN`) |
| comment out the seam's `coerceExistsArguments(params.find)` | full chain | 7, e.g. `pump $exists=false` lacks → **has** | the older string defect |

**Two consequences the plan does not state:**

1. **The prefix alone carries the `$exists` inversion.** `seam/t1-2-e` has neither fix:
   `coerceExistsArguments` arrives in `e0564167` (in `seam/t2-4-allowlist`, after the prefix), and
   its base `0a4109f6` predates dev's `normalizeOperands` (`b7234753`, 2026-09-16). `fromMongo`
   applies `!!value`, so `?find[mbg][$exists]=true` returns the entries without `mbg`. The
   prefix's suite is green (2213 / 0), so an unchanged suite does not catch it. Both refreshed
   branches inherit upstream's `normalizeOperands` and lose the inversion; the prefix shipped
   as-is would not.
2. **On both refreshed branches the empty operand flips relative to dev.** Dev passes `''` to
   MongoDB (matches documents having the field); the seam's `fromMongo` applies `!!''` (matches
   documents lacking it). Under either path, keeping dev's documented behaviour needs `fromMongo`
   to stop coercing a non-boolean `$exists` operand. Keeping the seam's needs a decision against
   dev's comment.

**BF-04.** Neither path's resolution touches `query.js`, so BF-04's `assertAllowedQueryOperators`
call is unchanged. Break-it on `tests/api-v1-operator-allowlist.test.js`, call commented out
(`tools/lab/seam-propagation/onetest.sh`):

| tree | intact | BF-04 call removed |
|---|---|---|
| modernization `b1bdaca0` | 79 / 0 | 65 / **14** (10 × "expected 400, got 200") |
| `prop/merge-prefix` | 79 / 0 | 65 / **14** (10 × "expected 400, got 200"; one direct call now fails as a `TypeError` from `fromMongo`, not as no rejection) |

The seam's own structural allowlist in `fromMongo` does not replace BF-04 on these paths. BF-04
remains the guard that gives a 400.

## 4. Full chain, classified only

`tools/lab/seam-propagation/classify.py <base> <seam>`; categories: add/add supersession from
BF-04 (upstream wins), §4.1 write rule (the base's version of the path calls one of the four rule
modules), manifest, test, docs, other lib. "Seam-own" means touched by a commit in `0a4109f6..tip`.
Data: [`results/full-vs-mod.json`](../../../tools/lab/seam-propagation/results/full-vs-mod.json),
[`full-vs-dev.json`](../../../tools/lab/seam-propagation/results/full-vs-dev.json),
[`e-vs-mod.json`](../../../tools/lab/seam-propagation/results/e-vs-mod.json),
[`e-vs-dev.json`](../../../tools/lab/seam-propagation/results/e-vs-dev.json).

| comparison | paths | BF-04 add/add | §4.1 write rule | other lib | test | manifest | docs | seam-own | modernization's own (seam does not touch) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full chain vs modernization | 19 | 3 | **0** | 14 | 2 | 0 | 0 | 19 | 0 |
| full chain vs dev | 50 | 3 | **11** | 20 | 11 | 3 | 2 | 29 | 21 |
| prefix vs modernization | 8 | 0 | 0 | 8 | 0 | 0 | 0 | 8 | 0 |
| prefix vs dev | 43 | 0 | **11** | 16 | 11 | 3 | 2 | 12 | 31 |

**The plan's nine.** §5.1 names nine of the 19 as files that "now call a 15.0.9 write rule":
`lib/api/entries/index.js`, `lib/authorization/storage.js`,
`lib/server/{activity,devicestatus,entries,food,profile,query,treatments}.js`. All nine are among
the 19. They call a rule **on dev**; on the modernization branch, the 19's merge target, none
does, because none of the four modules is there. Against dev the full chain has eleven: the nine
plus `lib/server/bootevent.js` (`srv-dates`) and `lib/server/websocket.js` (all four).

Full chain vs modernization, the 19: BF-04 add/add `lib/api/shared/query-error.js`,
`lib/server/query-operator-allowlist.js`, `tests/api-v1-operator-allowlist.test.js`; tests
`tests/mongo-query-javascript.http.test.js`, `tests/query-leaf-contract.test.js`; other lib
`lib/api/{activity,entries,profile}/index.js`, `lib/authorization/storage.js`,
`lib/server/{activity,aggregate,devicestatus,entries,food,profile,query,treatments}.js`,
`lib/server/swagger.{json,yaml}`.

Full chain vs dev adds: manifests `package.json`, `package-lock.json`, `azuredeploy.json`; docs
`README.md`, `docs/proposals/trusted-proxy-migration.md`; modify/delete
`lib/plugins/mmconnect.js` and five tests; and the api3/socket/auth/client files listed in the JSON.
21 of the 50 are modernization's own conflicts with dev (27 in total between those two branches),
which the seam inherits and does not cause.

## 5. The two paths side by side (prefix only)

| measure | merge into modernization | rebase onto dev (`--onto`) |
|---|---|---|
| tip-level conflicting paths before starting | 8 | 43 |
| paths actually met | 8 | 11 lib + 8 test (modify/delete); 1 not visible at the tip (`find.js`) |
| conflict hunks | 14 | 58, plus 9 modify/delete events |
| §4.1 write-rule files met | 0 (the rules are not on the base) | 7 |
| resolutions needing design judgement | 2 (`food.js` sort, `aggregate.js` body) | 11 (see the "judgement" column in §2.2) |
| seam conversions abandoned to keep a dev rule | 0 | 3 write sites (entries create, treatments batch create, treatments single upserts) |
| silent auto-merge hazards found | none found on reading the 8 files | 5 sites of 3 kinds; 1 kind not caught by the suite |
| test coverage dropped | 0 | the seam's edits to 8 modernization-only test files (T1.3 backend tagging on all 8; 2 count tests in one of them) |
| lines in the result present in neither parent | 21 | range-diff: 884 changed diff-of-diff lines (upper bound, includes context) |
| follow-up commits needed after the suite | 0 made; 3 tests to re-express + `conf.pipeline` open | 1 (`b894ec76`) |
| suite vs its baseline, same environment | 2476 / 4 vs 2426 / 0 | 3611 / 5 vs 3564 / 0 |
| residual failures, by kind | 3 test-pins-driver, 1 design (`conf.pipeline`) | 3 test-pins-driver (2 the same tests), 1 design (`conf.pipeline`), 2 test-pins-handle |
| agent wall-clock to a committed result | 1 min 55 s | 7 min 41 s + follow-up |
| driver / Node under test | 7.6.0 / 22.23.2 | 5.9.2 / 20.20.0 and 22.23.2 |
| what it leaves for later | the 15.0.9 write rules arrive when modernization next takes dev. `treatment-fallback-key`'s `$not`/`$type` (§2.4) will meet the seam's treatments `upsertOne` then, as it did here | the modernization branch's own 27 conflicts with dev, paid in `RT-3`/`RT-5`, plus re-tagging the 8 test files when they arrive |

Read across the two columns: the merge path is cheaper now because its base does not yet carry
15.0.9's write rules. The rebase path meets those rules now, which is the work §4.1 and
`WRITE-CONTRACT` describe. The wall-clock figures are one agent's and only show the ratio. A
human resolving the same hunks would take longer on both.

## 6. Mismatches with the plan (§5, §5.1)

1. **"Re-parent onto dev" must be `--onto`.** A plain rebase replays the modernization branch
   underneath (§2.1).
2. **"The Phase 1 prefix after `RT-3`"** is not required by the driver: the prefix runs on driver
   5.9.2 and Node 20/22. It uses two modules from cuts 2–3, both driver-neutral, which a rebase can
   drop or carry (§2.5).
3. **"Done criterion = an unchanged suite"** is green on `seam/t1-2-e` while that tip inverts
   `$exists` (§3). The fix is later in the chain (`e0564167`), not in the prefix.
4. **"Nine of the 19 are write-rule files"** is true of their dev versions; on the merge target
   none is (§4). On the rebase path the prefix itself met 7.
5. **Per-commit conflicts differ from the tip's.** As the plan warns: `find.js` and 8 test
   modify/deletes appeared only per commit, and 31 of the prefix's 43 tip conflicts with dev never
   appear on the `--onto` path.

## 7. Candidate defects (no ids allocated)

| # | where | reproduction | live on |
|---|---|---|---|
| C1 | `seam/t1-2-e` `a2690bd4` `lib/storage/filter.js` `fromMongo` + no coercion on its base | `node tools/lab/seam-propagation/exists-diff.js <tree> <db>`: `find[mbg][$exists]=true` → `lacks`; `find[pump][$exists]=false` → `has` | the prefix alone; not on dev, 15.0.8 or either `prop/*` branch |
| C2 | `fromMongo`'s `!!value` for `$exists`, on top of dev's `normalizeOperands` | same probe: `find[mbg][$exists]=` → `lacks` on both `prop/*` branches, `has` on dev | both refreshed branches; the full chain by design (`existsArgument('')` is false) |
| C3 | dev's suite does not pin devicestatus `remove()`'s filter | `node tools/lab/seam-propagation/ds-remove-softdeleted.js <dev tree> <db>` → `deletedCount 2`; with `stored_query_for` → `query_for`, `deletedCount 1` and the suite stays 3564 / 0 | dev `43289dde` (test gap, not a behaviour defect) |
| C4 | storage filter AST cannot express `treatment-fallback-key`'s empty-identity match | rebase suite on `29c7c1fa`: 18 × `unsupported operator '$not' on field 'syncIdentifier'` | any seam tree that takes dev's `treatment-fallback-key` (a `WRITE-CONTRACT` input, not a shipping defect) |

A read-derived candidate was raised and withdrawn during the run. At `a7c6efbc` the seam's
treatments `remove()` read `stat.deletedCount` from an interface that returned only `deleted`. The
prefix's own `1eba42df` makes `deleteMany` return both, so the tip is unaffected.

## 8. Reproduce

```
# distances and conflicts: §0.2 commands
# merge path: §1 commands; rebase path: §2.1 command, resolutions per results/rebase-stops.txt
docker run -d --name prop-mongo --ulimit nofile=64000:64000 -p 127.0.0.1:27152:27017 mongo:6.0.27
OUT=/tmp/seam-propagation tools/lab/seam-propagation/install.sh crm-prop-merge ...
OUT=/tmp/seam-propagation [NODEV=20.20.0] tools/lab/seam-propagation/suite.sh <worktree> <label>
node tools/lab/seam-propagation/exists-diff.js externals/work/<worktree> <db>
python3 tools/lab/seam-propagation/classify.py <base-ref> <seam-ref>
OUT=/tmp/seam-propagation tools/lab/seam-propagation/hazards.sh
```

Suite summaries: [`results/suite/`](../../../tools/lab/seam-propagation/results/suite/).
