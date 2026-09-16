# cgm-remote-monitor 15.0.9 — contents

**Status: DRAFT for maintainer review. Contributor-facing; full technical depth intended.**
Nothing merged, pushed, tagged or published.

> Complements the generated changelog. The changelog is authoritative for *what merged*;
> this file records *what the release is made of, how each figure was measured, and what is
> unsettled*.

## ⚠ The number is not settled, and this directory's name is the planned number, not a decision

| | |
|---|---|
| Base | `origin/dev` = `a8888f0d` |
| `package.json` on `dev` today | `15.0.9` |
| Tag in the repository | **none.** `git tag -l` stops at `v15.0.8` |
| What the policy says | **`15.1.0` at minimum; `16.0.0` if three rows ship as written; preferred outcome is to split** |

`docs/30-design/semver-and-release-versioning-policy-2026-09-15.md` §8.1 and §8.2:

- **§8.1 — the `dev` candidate is already a MINOR** on two rows that have nothing to do with
  Phase 0: two new environment variables with a changed logging default (`DEBUG_LOGGING`,
  `CONNECT_DEBUG`), and a connector pin move that changes retry behaviour.
- **§8.2 — Phase 0 as one release is a MAJOR** on three rows: the Alexa/Google Home locale
  removal, the subject-storage allow-list, and `?count=` as written.
- **Its preferred option is option 4**: split, *and* narrow the two changes so they stop
  being major — `bf/auth` deletes only `DERIVED_SUBJECT_FIELDS` rather than allow-listing
  the whole document, and `?count=0` **clamps with a `Deprecation` header** instead of
  rejecting. Both majors disappear, the unbounded-download hole still shuts today, and
  nobody's sync silently dies. In both cases the major-ness is incidental to what the fix is
  for.

**One qualification the notes must carry** (policy §8.1): `15.0.9` has never been released —
no tag, no version-tagged image, because `.github/workflows/main.yml` tags `dev` builds
`dev_<sha>` / `latest_dev` and uses the `package.json` version only on `master`. **But the
running application reports its `package.json` version** (`lib/server/env.js:137` →
`lib/api/status.js:32`), so every `dev`-channel deployment already answers
`/api/v1/status` with `15.0.9` today. A renumber means some sites appear to go *backwards*;
the note must say `15.0.9` was never a release so a bug reporter who says "I was on 15.0.9"
is understood rather than contradicted.

**Independent of the number choice:** the five parcel branches must stop claiming `15.0.9`.
Fifteen refs report that string today.

## The nine branches

All measured today against `origin/dev` `a8888f0d`.

| Branch | Tip | Commits | Register | Semver (GT4/policy) |
|---|---|---|---|---|
| `bf/alarms` | `5dcf783f` | 3 | BF-28, BF-29, BF-31 | **major** (locale removal); minor for the URGENT fix, patch for the ENABLE warning |
| `bf/auth` | `64db1f35` | 2 | BF-17, BF-30 | **major** (storage allow-list); throttle + `notes` each minor |
| `bf/cache` | `4f86bab1` | 2 | BF-06, BF-07 (partly) | **patch** — identical bytes on the wire |
| `bf/coercion` | **`b7234753`** | **2** | BF-02, BF-03, BF-11, BF-32, BF-40, BF-68 | **minor** |
| `bf/reads` | **`2ecfeb53`** | **6** | BF-01, BF-05, BF-13, BF-14, BF-15, BF-33 | **major** as written, on one row (`?count=`) |
| `bf/food` | `73495331` | 1 | BF-16, **BF-35** | **minor** — a v1 response changes contents |
| `bf/merge` | `b06c6faf` | 1 | BF-36 | **patch** — client only |
| `bf/parms` | `eb0bc918` | 3 | BF-37, BF-38, BF-39 | **patch** ⚖ |
| `bf/connect-pin` | `0807eb1c` | 1 | delivers BF-34, BF-08, BF-42 | **minor** — one line, but it is the vehicle |

### ⚠ Three corrections to `maintainer-release-brief-2026-09-15.md` §5, measured today

That document is another agent's and is not edited here. Its §5 is stale in three ways and
a reviewer working from it will do the wrong thing:

1. **`bf/coercion` is `b7234753` and carries TWO commits (was `ab197bf8`, before that `88d1f8a4`); `bf/reads` is `2ecfeb53`, not `0d19bb31`.**
   Both were rewritten to strip hand-edited `CHANGELOG.md` content, by the maintainer's
   rule that the changelog is a generated release output. Backups exist as
   `bf/coercion.bak-changelog` and `bf/reads.bak-changelog`.
2. **The stack is dissolved.** `git merge-base --is-ancestor bf/coercion bf/reads` now
   **fails**. `bf/reads` was un-stacked and rebased directly onto `origin/dev`, and is **6
   commits, not 8**. The brief's "open `bf/reads` against base `bf/coercion` and retarget
   it" instruction, and its "merging `bf/reads` merges `bf/coercion` with it" warning, are
   both **obsolete**. The plan is **nine independent PRs onto `dev`**.
3. **No branch touches `CHANGELOG.md` any more**, so the file-level reasoning in that
   document's branch-G note is moot as well as already-struck.

### The §3b concern survives, for a different reason, and is not a merge hazard

`bf/coercion` gives `lib/server/query.js` a new `collection:` option; `bf/reads` fixes
`lib/server/aggregate.js`, which **calls** `query.js` and passes no options. So after both
land, the count path still gets the legacy default walker. **That is a real follow-up and
is deliberately in neither PR.** There is no end-to-end assertion that a numeric filter on
`count/devicestatus/where` returns rows on the merged tree; **that test does not exist and
is the one test worth adding.**

## The five operator-visible behaviour changes, with their evidence

These are what the release notes exist for. Everything else is "a thing that was broken now
works".

### 1. insulinage's URGENT alarm starts firing — `bf/alarms`, S7

**Read on `bf/alarms:lib/plugins/insulinage.js`. Not executed against a running site.**

```js
if (insulinInfo.age >= prefs.urgent) {          // was compared against a field never filled in
  sendNotification = insulinInfo.age === prefs.urgent;
  message = translate('Insulin reservoir change overdue!');
  sound = 'persistent';
  insulinInfo.level = levels.URGENT;            // <- OUTSIDE the enableAlerts guard
} ...
if (prefs.enableAlerts && sendNotification && insulinInfo.minFractions <= 20) { ... }
```

Three facts the note must carry, and the second is the one most drafts get wrong:

- **Default `IAGE_ENABLE_ALERTS` is `false`** — `enableAlerts: sbx.extendedSettings.enableAlerts || false`
  (`getPrefs`, line 20). So the **notification** reaches only operators who turned alerts on.
- **The LEVEL is assigned outside that guard**, so the **urgent-red IAGE pill reaches
  everyone**, including operators who have alerts off. A note that says only "a new alarm is
  coming" is wrong for most readers; a note that says only "a pill turns red" is wrong for
  the rest. **Both audiences need a sentence.**
- **The notification fires in ONE evaluation window** — `age === prefs.urgent` **and**
  `minFractions <= 20` — and does not repeat. This matches `cannulaage`, `sensorage` and
  `batteryage`, so it is consistent rather than wrong. **"Do not describe it as repeating"
  is a hard requirement**: someone who expects it to nag will rely on something that will
  not happen.

**Policy §3.3 attaches three unwaivable obligations to any S7 change**: say what arrives,
when, at what level, with what sound, and how to turn it off; name the **default** that
decides whether it fires; and **do not simplify the algorithm**. *"Your reservoir alarm now
works"* is the named example of an inadequate note.

**This branch needs a maintainer's explicit yes in writing.** An alarm that has never fired
starting to fire is the one change here that reaches someone at 3 a.m., and the audience is
not the operator — it is whoever holds the phone.

### 2. `?count=` restrictions — `bf/reads`, S1

Measured by executing the branch's `lib/server/count.js` against an exact transcription of
the old `if (opts && opts.count) return this.limit(parseInt(opts.count))`:

| `?count=` | old | new |
|---|---|---|
| `0` | `limit(0)` → **the whole collection** (MongoDB: unbounded) | **400** |
| `0x10` | `limit(16)` | **400** |
| `2.5` | `limit(2)` | **400** |
| `-3` | `limit(-3)` | **400** |
| `1e2` | `limit(1)` | **400** |
| `abc` | `limit(NaN)` | **400** |
| `9007199254740993` | `limit(9007199254740992)` | **400** |
| `1`, `10`, `" 5 "`, absent, empty | unchanged | unchanged |

**Scope is wider than "the read path".** `validateCount` is `app.use`'d on the whole v1 app
**before every router** (`lib/api/index.js:51`), so it covers **writes**:
`POST /api/v1/treatments?count=0` now returns 400. Enumerated line by line from
`lib/api/index.js`: **15 mount points covered** — `/entries*`, `/echo/*`, `/times/*`,
`/slice/*`, `/count/*`, `/treatments*`, `/profile*`, `/devicestatus*`, `/notifications*`,
`/activity*`, `/food*`, `/status*`, `/alexa*`, `/googlehome*`, plus the `verifyauth` and
`adminnotifiesapi` routers at `/` — and **one not covered**: `/experiments`, mounted at
line 38, *before* the validator.

**The exposure is latent, not observed, and the census is the evidence.**
`docs/60-research/seam-limit-and-projection-2026-09-14.md` §2 (from
`tools/qc/v1_count_census.py`): **274 `count=` occurrences across 10 client projects — 236
literal, 25 computed at request time, 11 prose, 2 other. No client sends a literal
`count=0`.** The observed literals are `1, 2, 3, 5, 10, 20, 24, 50, 100, 288, 500, 1000,
1500, 10000, 100000, 9999999`. The exposure is the **9.1 % computed** arm, where nothing
bounds the value away from zero; `oref0`, the closed loop, has four such sites. **The census
reads client source, not request logs, because there are no request logs.**

**A maintainer who weighs the census more heavily than the argument can reasonably reject
the split and ship all six rejections today.** Policy §10 item 1 names this as the most
overrulable call in the document. Both positions are on file; neither is decided.

### 3. Filters that matched nothing start matching — `bf/coercion`, S1

**158 schema-driven coercions** over five collections (`devicestatus` 99, `treatments` 29,
`entries` 20, `profile` 10, `activity` 0 — counted from `lib/server/query-coercion.json`).
Measured by executing both versions of `query.js` on the same inputs:

| query | before | after |
|---|---|---|
| `treatments?find[duration][$gte]=30` | `{"$gte":"30"}` — matched nothing | `{"$gte":30}` |
| `treatments?find[insulin][$gte]=1.5` | `{"$gte":1}` — rounded down | `{"$gte":1.5}` |

The three regular-expression walker entries on `treatments` (`notes`, `eventType`,
`enteredBy`) are deliberately kept — they are search affordances, not type claims.

> **The sentence that must survive verbatim into the operator note** (policy §3.1, §5.6):
> *"earlier results may have under- or over-reported delivered therapy."* The version number
> is bookkeeping; that sentence is the actual warning.

**BF-32's stated impact does not survive contact with a real MongoDB, and the wrong version
of it currently ships to operators.** Measured against two live `mongod` servers (3.6.8 and
7.0.43, driver 5.9.2): MongoDB's truthiness for a BSON double is `value != 0`, and
`NaN != 0` is **true**, so `{$exists: NaN}` was read as `{$exists: true}` and returned the
documents that **have** the field — the right answer, reached by accident. Consequences:

1. **There is no `$exists=false` inversion.** Both spellings produced `{$exists: NaN}` on
   `dev`; both return "has the field" before and after. Settled: **no**.
2. **`bf/reads`' `CHANGELOG.md` said** *"which MongoDB reads as false, so the query returned
   exactly the records you did not ask for"*. **That is wrong and it was operator-facing
   text.** It is gone with the changelog strip — **and it must not come back through the
   generated changelog**, which is generated from commit messages. **Check the commit
   messages at reconciliation time.**
3. **What BF-32 still fixes, and this part holds:** the other non-value operators on the ten
   numeric walker-covered fields were run through `parseInt`. `find[sgv][$type]=number`
   reached the driver as `NaN` on `dev` and as `"number"` on the branch;
   `find[sgv][$regex]=^1` as `NaN` and as `"^1"`.
4. **A separate pre-existing defect is exposed and is not fixed by this batch:**
   `find[<any field>][$exists]=false` has never meant "lacks the field" anywhere in API v1,
   on `master`, on `dev`, or after this branch. **It belongs in the release notes' known
   issues** and is carried there. Proposed for the register with **no id allocated**.
5. **`mingo` is not a faithful oracle for non-boolean `$exists` operands.** Under decision
   D8 that matters for the seam's differential tests.

### 4. Alexa / Google Home per-request locale removed — `bf/alarms` `5dcf783f`, S1

`POST /api/v1/alexa` and `POST /api/v1/googlehome` stop honouring `request.locale` and
answer in the server's configured language. **The removal is correct** — `ctx.language` and
`moment.locale()` are process-global, so the old code re-languaged **every later request in
the process** — and correctness is not the question. It is a **capability removal on an HTTP
endpoint with no replacement**, which is why the branch classifies major.

### 5. Subject/role storage becomes an allow-list — `bf/auth`, S4

```js
var SUBJECT_FIELDS = ['name', 'roles', 'notes', 'created_at'];
var ROLE_FIELDS    = ['name', 'permissions', 'notes', 'created_at'];
function save (collection, fields) { var doc = ownedFields(obj, fields);
  await collection.replaceOne({_id: doc._id}, doc, {upsert: true}); }
```

**Scoped correctly — most of the data loss is pre-existing, not introduced here**, and a
reviewer needs the difference:

- **Already true on `dev`.** `save()` is already `replaceOne` on the caller's object, and
  `endpoints.js:40` returns only `pick(subject, ['_id','name','accessToken','roles'])`. The
  stock admin UI `PUT`s back exactly that. **So on today's release, editing a subject in the
  admin UI already destroys `notes`, `created_at` and any third-party field.** `bf/auth` in
  fact *reduces* one case of this, by adding `notes` to the `GET` response and the
  allow-list.
- **What the branch newly removes** is a third-party tool's ability to *keep* its own fields
  by sending them in its own `PUT`. `ownedFields()` strips anything outside the allow-list
  regardless of what the caller sent.

**This is the one change in the batch a code revert cannot fully undo.** The honest question
for the community is narrower than "do you run third-party tooling": *does any third-party
tool write extra fields to subjects or roles through `/api/v2/authorization/`, and does it
depend on them surviving?* **Not reproduced against a real deployment; no third-party tool
was inspected.**

## BF-17 remediation — the fact the PR body and the notes both need

**Read on `bf/auth:lib/authorization/storage.js:214-235`. Not executed.**

```js
DERIVED_SUBJECT_FIELDS.forEach(function (field) { delete subject[field]; });
if (env.enclave.isApiKeySet()) {
  subject.digest = env.enclave.getSubjectHash(subject._id.toString());
  var abbrev = subject.name.toLowerCase().replace(/[\W]/g, '').substring(0, 10);
  subject.accessToken = abbrev + '-' + subject.digest.substring(0, 16);
  subject.accessTokenDigest = storage.getSHA1(subject.accessToken);
}
```

**The token is a deterministic function of `subject._id`, `subject.name` and the enclave key
(`API_SECRET`).** `reload()` recomputes all three derived fields on every load. Therefore:

> **A code fix cannot invalidate a token that already exists.** The fix stops new plaintext
> tokens being *written*; it changes nothing about tokens already written. **Rotation is the
> operator's action, and there are exactly three levers:**
>
> | Lever | Blast radius |
> |---|---|
> | Change the subject's **name** | that one subject's token |
> | **Delete and recreate** the subject (new `_id`) | that one subject's token |
> | Rotate **`API_SECRET`** | **every token on the site, at once** |

The branch also deletes any stored value under a derived name *before* deriving it, so a row
written before these fields were kept out of the collection cannot supply one. **The PR must
carry this remediation note** — a reader who sees "plaintext token fixed" and assumes the
exposure is closed will not rotate, and the exposure is not closed.

## Test evidence, per branch, with the suite that was actually run

**Read `docs/60-research/e3-gate-vacuity-audit-2026-09-15.md` before treating any green tick
as complete.**

| Branch | Suite | Result |
|---|---|---|
| `bf/auth` | `npm test` (full `./tests/*.test.js`, 161 files) on its own `mongod` :27031 | **2047 pass, 3 pending, 0 fail** |
| `bf/cache` | `npm test` (160 files), `mongod` :27033 | **2040 pass, 3 pending, 0 fail** |
| `bf/food` | `npm test` (161 files) — **run twice, two agents, same figures** | **2042 pass, 3 pending, 0 fail** |
| `bf/merge` | `npm test` (160 files) — run twice | **2040 pass, 3 pending, 0 fail** |
| `bf/parms` | `npm test` (160 files) — run twice | **2035 pass, 3 pending, 0 fail** |
| `bf/reads` (+`bf/coercion` as then-merged) | `npm test` (164 files) — run twice, two agents | **2076 pass, 3 pending, 0 fail** |
| `bf/alarms` | `npm run test:unit` only | 346 pass / **7 fail**, all attributed to the environment. **The full suite has still not been run on this branch.** |
| `bf/coercion` alone | `npm run test:unit` | 368 pass / 6 fail, environmental (`mongod` :27030 not listening) |
| `bf/connect-pin` | **none** — no `node_modules`, no `my.test.env` in that worktree | it is one line; **do not read a green tick that does not exist** |

**Four measurement facts that contradict figures in circulation:**

1. **`npm run test:unit` is a brace list of 44 files, not 149**, and it **does need
   MongoDB** — without it, 6 tests fail (`verifyauth` ×4, `API_SECRET` ×2) even on pristine
   `dev`. `npm run test:integration` is 89 files, not 10.
2. **`tests/*.test.js` is 159 files; 52 match neither local script**, including
   `tests/boluscalc.quickpick.test.js` (BF-35), `tests/receiveddata.merge.test.js` (BF-36)
   and `tests/browser-utils.queryparms.test.js` (BF-37). **CI is not blind to this** —
   `main.yml` runs `test-ci` = `./tests/*.test.js`, all 159. **The gap is in the local npm
   scripts only.** A green `test:unit` on `bf/food` is **not** evidence for BF-35.
3. **Worktree `mongod` isolation is only partly built.** `crm-bf-food`, `crm-bf-merge` and
   `crm-bf-parms` all name port **27033**; `crm-bf-coercion` (27030) and `crm-bf-alarms`
   (27034) have **no listener**; `crm-bf-connect-pin` has no `my.test.env` at all. The
   consequence is concrete: `bf/alarms`' two API test files cannot be run on this machine.
4. **The 2076 decomposition is inherited, not measured.** 2028 (base) + 35 + 13 = 2076: the
   **2076 is measured; the base 2028 is quoted** and no full-tree run of pristine
   `origin/dev` was ever made. If the additivity matters to a review, run `npm test` in a
   worktree at `a8888f0d`.

*Operational note:* the suite refuses to start if its test database holds more than 100
entries ("Production safety check activated"). An interrupted run leaves the database dirty
and the next run halts. Let a run finish, or raise `TEST_SAFETY_MAX_ENTRIES` for that
invocation only.

## Non-vacuity (house rule 2)

- `bf/coercion`: `tests/query.test.js` from the branch **cannot load** against pristine `dev`
  (`Cannot find module '../lib/server/query-coercion'`), so it distinguishes fixed from
  unfixed.
- `bf/cache`: the dead write at `lib/data/dataloader.js:204` is pinned by a test that fails
  if the write returns.
- `bf/food`: a drift tripwire fires when this lands and **it is not a breakage** —
  `tools/nsschema/code_model.py`'s `SOURCE_ASSERTIONS` deliberately pins the quoted `'false'`
  in `lib/server/food.js` so that fixing it *forces* the food model to be revisited.
  `make schema-code-drift` will fail the day this reaches the tooling repo's checkouts. What
  to replace the anchors with is written into BF-16.
- The queue's gate controls are audited in `docs/60-research/e3-gate-vacuity-audit-2026-09-15.md`:
  95 gate commands, all with declared negative controls; full run **91 non-vacuous, 4 exempt,
  0 vacuous, 0 uncontrolled**.

## Sequencing

1. **Nine independent PRs onto `dev`.** No stack. All nine merge cleanly against `dev` and
   against each other.
2. **`bf/alarms` and `bf/auth` each need a maintainer's explicit written yes.**
3. **`bf/connect-pin` is gated on the connector tag being pushed first**, because its
   `package-lock.json` cannot be regenerated until the tarball exists. See
   `releases/nightscout-connect-v0.0.14/contents.md`.
4. **Never push a branch onto `dev` or `master`** — a push to either triggers a Docker Hub
   image push and is a publication event.
5. **If pushing to a fork:** `.github/workflows/close-accidental-sync-prs.yml` runs on
   `pull_request_target: [opened]` and can auto-close a fork PR whose title matches
   `/\b(sync|merge|update|pull|new)\b/i`. **Title the PRs accordingly.**
6. `CHANGELOG.md` is generated at release time. **No branch hand-edits it, and none does.**

## What a reviewer must verify before this is relied on

1. **Run the full suite on `bf/alarms`.** It is the only branch without one, and it is the
   branch that starts an alarm. Needs the worktree's own `mongod` on 27034 started and
   `npm run bundle` run there.
2. **Decide the number**, and whether to split (policy §8.2 option 4). It changes what the
   notes say about `?count=0`.
3. **Decide `?count=0`: reject, or clamp with a `Deprecation` header.** The census evidence
   and the counter-argument are both above; neither is decided.
4. **Confirm the insulinage notification's once-only behaviour is intended**, not an
   oversight — the release-note wording depends on it.
5. **Answer, for the community:** does any third-party tool store its own fields on subjects
   or roles through `/api/v2/authorization/`?
6. **Check the generated changelog for BF-32's refuted sentence** before publishing.
7. Add the missing end-to-end assertion that a numeric filter on `count/devicestatus/where`
   returns rows on the merged `bf/coercion` + `bf/reads` tree. Until it exists, the §3b
   reasoning is reasoning, not measurement.
8. Delete the safety ref `bf/reads-prerebase` and the two `.bak-changelog` refs after the
   PRs merge.

---

*Draft, 2026-09-15. Prepared locally. Nothing merged, pushed, tagged or published. Requires
maintainer review before release.*
