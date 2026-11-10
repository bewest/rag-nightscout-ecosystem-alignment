# M6b follow-ups: last-owner revocation, legacy subject writers, export-file expiry

*Contributor-facing measurement record, captured 2026-11-10. Not edited after capture. Lane
`codex/m6b-followups-20261110`; local, unpushed. Source of the three items: the M6b join
coordinator handoff, step 6 (read-derived, not reproduced).*

## Anchors

| tree | ref | commit |
|---|---|---|
| lane head | `codex/m6b-followups-20261110` (worktree `externals/work/crm-m6b-followups-20261110`) | `65657a62a1e26dde9e245f9a7651d2593da0208a` |
| lane base = draft #8898 head | `official/workspace/multitenant-20261102` (fetched at start) | `b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| `official/dev` | fetched at start | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` at writing | | `de6b6c06d578981c24f068ed66282b46b21b71f0` |

Containers: PostgreSQL `postgres:16` (the suite fixture names the tag; it resolved to
`postgres@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97`, server
`16.15`), one owned container per suite run, removed by the fixture (verified: no
`ns-owner-policy-test-*` container left). Unit tier: dedicated
`mongo@sha256:9854f7139445d766a9523571d6f047530c45547460ffcf8259eb2bf4264632ca`
(`--ulimit nofile=1048576:1048576`, no tmpfs), removed afterwards. Node `v22.23.4`.

The intended behaviour comes from [owner authority](../../../docs/30-design/tenancy/owner-authority.md#owner-permissions-and-ceilings):
"last-owner removal must not orphan the tenant", and "last-owner protection, current authority
and audit remain required for the operator path"; and from the 16.0.0 decision
[`owner-may-revoke-subjects`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-may-revoke-subjects).
A usable owner is an active `tenant_owner_actors` row with `can_update` whose principal is an
existing subject of the tenant (`lib/tenant-ownership/README.md`).

## Verdicts

| # | item | verdict | test |
|---|---|---|---|
| 1 | owner-plane `remove()` can delete the last owner's subject | **reproduced**, fixed on the lane (one commit) | `tests/owner-subject-policy.integration.test.js`: "refuses revoking the last usable owner subject (409) …", "race: two owners revoking each other concurrently …" |
| 2 | legacy subject writers (no `ownerPolicy`) do not serialize with ownership changes | **reproduced at the store level**; not reachable through the shipped composition (measured); **decision question**, no fix written | scratch reproduction (below), uncommitted |
| 3 | export-file expiry is not automated | **unsettled: decision question**. The fact is stated by the module itself; whether and how the file must expire is not stated anywhere | none |

## Item 1: last-owner revocation (reproduced, fixed)

**Mechanism (b70ad83f).** `lib/subject-admin/postgres.js` `remove()` with an owner policy
checks the acting owner's current authority (`authorizePermissions(…, [])`) and then deletes the
target's role links, credential metadata and subject. It never reads `tenant_owner_actors` for the
target. Deleting the subject of the only usable owner leaves the tenant with an owner actor row
that no longer counts (no subject), that is, no usable owner, until an operator recovery. Two
owners revoking each other at the same time each lock only their own target subject, so both
commit (write skew) with the same result.

**Fix (lane commit).** In owner mode, after current authority and before the target lock,
`remove()` selects the subjects of every usable owner with `FOR UPDATE OF s` in `subject_id`
order, and refuses `SUBJECT_ADMIN_LAST_OWNER` when the target is the only one. The sorted lock
serializes concurrent revocations without a deadlock; the second one re-reads after the first
commits and is refused. HTTP maps the code to 409. Revoking a co-owner, or one's own subject,
while another usable owner remains is unchanged (decision `owner-may-revoke-subjects`). Legacy
mode (no owner policy) is unchanged; see item 2. Files: `lib/subject-admin/postgres.js`,
`lib/server/subject-management-app.js`, `tests/owner-subject-policy.integration.test.js`
(three cases), `tests/owner-subject-store-source.test.js` (the synthetic connection models the
new owner query).

**Before the fix** (tests added, source at `b70ad83f`;
`NS_OWNER_SUBJECT_POLICY_DOCKER_TEST=1 node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 60000 --require ./tests/hooks.js --exit tests/owner-subject-policy.integration.test.js`):
**23 passing, 2 failing**.

- "refuses revoking the last usable owner subject (409) …": `{}; persistent effects changed: true` / `200 !== 409`: the HTTP revocation of the only usable owner's subject succeeded.
- "race: two owners revoking each other …": outcomes `['applied', 'applied']`, expected `['SUBJECT_ADMIN_LAST_OWNER', 'applied']`: both concurrent revocations committed.

The race is a real interleaving, not a sequence: a holder connection takes
`LOCK TABLE … tenant_subject_admin_audit IN SHARE MODE`; the test waits until
`pg_stat_activity` shows 2 `nightscout-subject-admin` sessions with `wait_event_type='Lock'`
(both inside their transactions, deletes done, waiting at the audit insert) before releasing it.

**After the fix:** same command, **25 passing, 0 failing**.

**Break-it controls** (each restored, `cmp`-identical to the fixed file afterwards):

| ablation | result | meaning |
|---|---|---|
| A1: the `SUBJECT_ADMIN_LAST_OWNER` check removed | 23 passing, 2 failing: the same two cases, same symptoms as before the fix | the check is what refuses |
| A2: the check kept, `FOR UPDATE OF s` removed | 24 passing, 1 failing: the race case, outcomes `applied, applied` | the sorted lock is what makes the check hold under concurrency |
| A3: owner-policy `tenant_owner_policy … FOR SHARE` removed | 23 passing, 2 failing (the existing policy-narrowing cases); **the new transfer race stayed green** | green for a stated reason: the acting owner's `tenant_owner_actors` row `FOR SHARE` still blocks the transfer's `FOR UPDATE` on actor rows (second layer) |
| A4: both the policy and the actor-row `FOR SHARE` removed | 20 passing, 5 failing, including "race: an owner revocation of the incoming owner serializes with an operator transfer": transfer `outcome: 'applied', code: null` instead of `refused / OWNERSHIP_SUBJECT_UNKNOWN` | the third case can see the defect it guards |

The third new case ("race: an owner revocation of the incoming owner serializes with an operator
transfer to it") measures an item the ownership lane listed as UNMEASURED ("ownership change vs.
an in-flight owner-plane mutation holding the policy row"): with the owner revocation of the
transfer target held at its audit insert, the operator transfer waits on a lock, then reads the
committed revocation and refuses `OWNERSHIP_SUBJECT_UNKNOWN`; the tenant keeps its owner. It
passed on `b70ad83f` too: it is a serialization measurement, not a reproduction.

## Item 2: legacy subject writers (reproduced at the store level; decision question)

**Mechanism.** `createPostgresSubjectAdmin` composed without `ownerPolicy` ("legacy" writer)
keeps its pre-owner privilege shape: no SELECT on `tenant_owner_actors` or
`tenant_owner_policy` (measured: `has_table_privilege('legacy_writer', …, 'SELECT')` false for
both). Its `remove()` locks only the target subject and credential metadata rows. The operator
ownership store takes the policy row `FOR UPDATE` and reads subjects without a row lock. Nothing
the two share is locked by both, and the legacy writer cannot see which subjects are owners.

**Reproduction** (scratch file, not committed:
`externals/work/m6b-followups-20261110-evidence/legacy-writer-ownership.repro.js` (local,
git-ignored, with the run logs), run with `CRM_TREE=<lane worktree>` from the lane worktree from the lane worktree with the suite fixture; real
PostgreSQL; synthetic tenant and identifiers), 1 passing, 2 failing:

- Sequential: a legacy `remove()` of the only owner's subject returns `true` and leaves usable
  owners `[]`. No concurrency is needed; the legacy writer is blind to ownership.
- Concurrent: legacy `remove(TARGET)` held at its audit insert (delete done, uncommitted) while
  an operator `transfer(manager → TARGET)` runs, plans against the still-visible TARGET subject,
  writes the actor rows and waits at its own audit insert. Both sessions observed waiting at once
  (`pg_stat_activity`: one `nightscout-ownership-ops`, one `nightscout-subject-admin`, both on
  `INSERT INTO "owner_policy_test".tenant_s…`). Released: `revoke=applied transfer=applied:null
  owners_reported=[TARGET] usable_after=[]`. The transfer reported an owner whose subject no
  longer exists.
- Control: the same interleaving through the owner-policy store: `revoke=applied
  transfer=refused:OWNERSHIP_SUBJECT_UNKNOWN usable_after=["manager"]` (passes).

**Reachability (measured).** The only shipped composer of the store is
`lib/server/serve/owner-preview.js`, which passes `config.ownerPolicy`; the owner-preview
configuration parser requires it: the same configuration parsed with `ownerPolicy` and refused
without it (`invalid explicit headless owner preview configuration`). No other `lib/`, `bin/` or
`deploy/` file composes the store (grep, read-derived). So on `b70ad83f` the defect is reachable
only by a composition that does not exist yet; it is a property of the module, which still
accepts no `ownerPolicy` in multi mode.

**Why no fix was written.** The legacy writer cannot evaluate the owner invariant without
reading owner rows, and the existing suite asserts that legacy remove keeps working ("allows
explicit owner revocation and preserves legacy/default update/remove behavior"). Every fix changes
either that tested behaviour or a database identity's privilege shape. The decision question is
below.

## Item 3: export-file expiry (unsettled, decision question)

**What is stated.** Decision [`tenant-deletion-key-retention`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-deletion-key-retention)
keeps the Transit keys and the export artifact for 30 days, then an operator destroys the keys,
which cryptographically erases the artifact's secrets. `lib/tenant-lifecycle/README.md` says
"Expiry of the export artifact file itself is not automated by this module", and the
key-retention lane's operator note tells operators to delete the file themselves because glucose
and treatment records in it are not encrypted by those keys.

**What the code does (read-derived).** `saveTenantArtifact` writes
`<directory>/tenant-artifact-<digest>/artifact.json` (0600). The only removal in
`lib/tenant-lifecycle` is the staging directory on a failed save
(`filesystem-artifact.js:48`). In the shipped tree only `tools/lab/tenant-whole-c/core.js` calls
`saveTenantArtifact`; the ceremony verifies an artifact through a directory the operator
configures. No code removes the artifact at or after the window, at destroy, or on a timer.

**Why unsettled.** No document states whether the artifact file must be removed at the end of
the window, by whom, or whether it is the operator's backup to keep. Measuring "the file is still
there after destroy" would only confirm the stated behaviour; it is not a defect until the
intended behaviour is decided.

## Decision questions

### D-A. Legacy subject writers in multitenant mode (item 2)

- **Mechanism:** `lib/subject-admin/postgres.js:20-28` accepts `ownerPolicy` undefined in multi
  mode; `remove()` (`:181-194` at `b70ad83f`) then deletes any subject without reading
  `tenant_owner_actors`, whose rows that identity cannot read.
- **Options:**
  1. Refuse legacy `remove()` in multi mode (as legacy `create()` already refuses
     `SUBJECT_ADMIN_FORBIDDEN`). Smallest change; changes the asserted "preserve legacy remove"
     behaviour of a writer no shipped runtime composes.
  2. Require `ownerPolicy` for every multi-mode store (delete the legacy branch). Removes the
     unguarded path entirely; the legacy-mode suites (`subject-admin-postgres`,
     `subject-management-http`, part of `owner-subject-policy`) move to the owner writer shape.
  3. Keep the legacy writer and give its identity SELECT on owner actors plus
     `UPDATE(owner_fence)` on the policy row, then apply the item 1 guard and take the policy row
     `FOR SHARE`. Keeps the API, but the legacy identity grows to the owner writer's shape (a
     deployment-grant change; `deploy/multitenant/config.js` was out of this lane's scope).
- **Users/operators:** nothing changes for operators today (no composition); the choice decides
  whether a future multitenant composition can orphan a tenant through a subject revocation.
- **Single/multi:** multitenant only. Single-tenant MongoDB subject administration is a different
  store and is not affected.
- **Recommendation (if asked):** option 2 for long-term direction and maintenance (one guarded
  writer, one privilege shape, nothing to keep in step), with option 1 as the interim if the
  legacy suites are to be migrated later. Unmeasured: whether any lab or native harness outside
  `lib/` composes a legacy multi-mode writer (`tests/native/oidc-matrix` was not run).

### D-B. Export artifact file at the end of the retention window (item 3)

- **Mechanism:** see item 3; `destroyRetainedKeys` (`lib/tenant-lifecycle/key-retention.js`)
  erases secrets cryptographically and leaves the artifact file, whose clinical records stay
  readable.
- **Options:** (a) the operator's destroy step also removes the artifact it knows by digest from
  the configured artifact directory, audited in the same record, after the keys are confirmed
  absent; (b) a separate scheduled sweep of expired artifacts; (c) keep it an operator
  responsibility and document it in the deletion runbook (today's behaviour).
- **Trade-off:** (a) ties removal to an explicit, already window-gated operator action and adds no
  timer; it cannot reach copies outside the directory. (b) removes files without an operator
  present, but adds a time-driven writer to the lifecycle domain. (c) adds nothing, but leaves
  plaintext clinical data on disk past the window unless the operator acts.
- **Single/multi:** multitenant lifecycle only.
- **Recommendation (if asked):** (a), for reliability (one audited step) and maintenance (no new
  scheduler); unmeasured: how operators store artifacts in practice (only the lab harness saves
  them today).

## Proposed register entry (the coordinator allocates the id)

| field | proposal |
|---|---|
| title | Owner revocation can delete the last usable owner's subject, leaving a multitenant site with no owner |
| mechanism | Owner-plane `remove()` in `lib/subject-admin/postgres.js` checked the actor's authority but not whether the target was the last usable owner; two owners revoking each other concurrently each locked only their own target and both committed. |
| basis | reproduced (two failing cases at `b70ad83f`, passing on the lane head; four ablations) |
| status | fixed (lane `codex/m6b-followups-20261110` `65657a62a1e26dde9e245f9a7651d2593da0208a`), preview-only, never released |
| exposure | draft #8898 owner preview (multitenant); single-tenant unaffected |
| operator note | Revoking the last owner of a site is now refused with 409; add another owner first (operator-assisted ownership) and then revoke. |

Item 2 is not proposed as an entry until D-A is answered; if the answer is option 1 or 2 it is
a design change, not a defect in a released path.

## Runs

| run | result |
|---|---|
| owner-subject-policy suite, tests added, source `b70ad83f` | 23 passing, 2 failing |
| same, fix applied | 25 passing, 0 failing |
| ablations A1–A4 | as in the table above |
| unit files naming subject admin (7 files, `--fail-zero`) | 74 passing, 1 failing before the synthetic connection modelled the owner query; 75 passing after |
| `node scripts/test-multitenant.js --only owner-subject-policy --only subject-admin-postgres --only subject-management-http --only tenant-ownership-postgres` (record `ffa8f4008f8a`, 2026-11-10T22:50:48Z–22:51:08Z) | 55 passing, 0 pending, 0 failing; no containers left |
| unit tier `node scripts/test-tiers.js run unit` (after `npm run bundle`) | 3106 passing, 0 failing, exit 0 (started 2026-11-10T22:51:00Z, with the fix, before the commit; same tree as the commit) |
| `npm run lint` | 0 errors, 49 warnings, none in touched files |
| `node scripts/test-tiers.js check` | `614 test files, 8 tiers: ok` (no new test file) |
| item 2 scratch reproduction | 1 passing, 2 failing (as above) |

## UNMEASURED

- Full, browser and corpus campaigns, prcheck and CI on the lane head (the coordinator's joined
  candidate).
- `tests/native/oidc-matrix` (authority races, owner extension) against the new remove guard.
- The guard through the human-session management path end to end (the HTTP case uses the suite's
  synthetic management authentication).
- Interaction of the guard with `update()` and `withCredential()` under load: neither changes
  owner status; their lock order (target subject only) is reasoned compatible, not raced.
- Item 3: no run.
