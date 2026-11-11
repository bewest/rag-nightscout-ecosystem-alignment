# Tenant root (API_SECRET) admin tools parity on the owner-aware writer

*Contributor-facing measurement record, captured 2026-11-10. Not edited after capture. Queue item
`MT-ROOT-ADMIN-PARITY`. Lane `codex/root-admin-parity-20261110`; local, unpushed. Decisions
[`tenant-root-single-site-parity`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-root-single-site-parity)
and [`root-may-edit-owner-subjects`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#root-may-edit-owner-subjects);
amended paragraph in [owner authority](../../../docs/30-design/tenancy/owner-authority.md#management-authentication-and-lifetime-policy).*

## Anchors

| tree | ref | commit |
|---|---|---|
| lane head | `codex/root-admin-parity-20261110` (worktree `externals/work/crm-root-admin-parity-20261110`) | `cfae532c362cc125147843d965603af3293c1d94` |
| lane commit 1 (code, tests) | | `db93072e13979cc2c6041b8c1ac20322b53e8cd0` |
| lane commit 2 (deploy grants only) | | `cfae532c362cc125147843d965603af3293c1d94` |
| lane base = BF-229 fix | `codex/m6b-followups-20261110` | `65657a62a1e26dde9e245f9a7651d2593da0208a` |
| base of the base = draft #8898 head | `official/workspace/multitenant-20261102` | `b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| `official/dev` | | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` at writing | | `638e5909181db06d38a86dff8242ab13742257ca` |

At start: `make queue-status` showed `MT-ROOT-ADMIN-PARITY ... not-started 0/0 UNMEASURED`; the
base head was `65657a62` as briefed.

Instruments: PostgreSQL `postgres:16`, resolved and run as
`postgres@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97` (server
`16.15`); the suite fixture starts it by tag and removes its own container and volume. MongoDB for
the single-site tests: dedicated `mongo@sha256:9854f7139445d766a9523571d6f047530c45547460ffcf8259eb2bf4264632ca`
(server `7.0.43`), removed afterwards (127.0.0.1:27017 is 3.6.8 and was not used). Node `v22.23.4`.
After every run `docker ps -a` showed no container from this lane.

## What changed (reproduced unless marked)

| # | change | where |
|---|---|---|
| 1 | **One writer in multitenant mode.** The PostgreSQL subject store refuses construction without `ownerPolicy` (`TypeError: Owner policy requires an explicit catalogue`). The store is multi-only, so the earlier writer is not buildable at all. | `lib/subject-admin/postgres.js` |
| 2 | **Root plane on the owner-aware writer.** `plane:'root'`: authority is the current config row and owner policy row (both `FOR SHARE`); delegation is the operator ceiling; no owner actor row is read for authority or locked. Grants stay inside project catalogue ∩ ceiling. The BF-229 last-owner guard runs on both planes. Root-plane issuance (`withCredential`) refuses. Adds `list`/`listRoles` reads. | `lib/subject-admin/owner-policy.js`, `postgres.js`, `component.js` |
| 3 | **Admin tools routes on the DATA listener** for the resolved tenant's root secret only, selected by the optional preview `subjectAdmin {writerConnectionEnv, ownerPolicy:{catalogue}}`. Same paths, verbs and form/JSON payloads as `lib/authorization/endpoints.js` as called by `lib/admin_plugins/subjects.js` and `roles.js`. Mounted inside the tenant admission (operation window, tenant preparation). | `lib/server/tenant-app/root-admin.js`, `index.js`, `lib/server/serve/preview-api.js`, `preview-config.js` |
| 4 | `secrets.rootLegacyTokens`: the listed `accessToken` is derived only when the presented secret is that tenant's current root, in the same decrypt; equal to the shipping single-site `accessToken`. | `lib/secrets/component.js` |
| 5 | Deploy plan: a separate `nsdemo_root_writer` identity (separate commit). | `deploy/multitenant/config.js` |

Single-site files (`lib/authorization/`, `lib/admin_plugins/`, `lib/api/`) are unchanged (git diff
over the lane).

### Routes restored

| route | root on DATA listener |
|---|---|
| `GET /api/v2/authorization/subjects` | `[{_id,name,roles,notes,accessToken}]` |
| `POST /api/v2/authorization/subjects` | create (an `_id` in the body refuses 400) |
| `PUT /api/v2/authorization/subjects` | update by `_id`, any subject including an owner's; `accessToken` in the body is accepted and ignored |
| `DELETE /api/v2/authorization/subjects/:_id` | remove; last usable owner → 409 `SUBJECT_ADMIN_LAST_OWNER` |
| `GET /api/v2/authorization/roles` | `[{_id:name,name,permissions}]` |
| `POST /api/v2/authorization/roles` | create (`notes` accepted, not stored: no column) |
| `PUT /api/v2/authorization/roles`, `DELETE /api/v2/authorization/roles/:_id` | 501 `SUBJECT_ADMIN_UNSUPPORTED` (decision question Q1) |

Not restored (read-derived: the admin tools page does not call them): `GET /permissions`,
`/permissions/trie`, `/debug/check/:permission`. The admin page's data-cleaning tools call
`/api/v1/...` data routes, which root already has. Refusals use the shipping 401 envelope
`{status:401,message:'Unauthorized',description:'Invalid/Missing'}`.

## Acceptance (synthetic tenants A and B, real PostgreSQL)

`NS_OWNER_SUBJECT_POLICY_DOCKER_TEST=1 node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 60000 --require ./tests/hooks.js --exit tests/owner-subject-policy.integration.test.js`
at `cfae532c`: **33 passing, 0 failing** (base `65657a62`: 25; one case rewritten, eight added in
the nested describe "tenant root (API_SECRET) single-site admin tools parity").

| criterion | test case | result |
|---|---|---|
| A's root lists, creates, edits, deletes subjects and creates roles with the admin tools payloads (jQuery form encoding, `roles[]`, empty array omitted) | "lists, creates, edits and deletes subjects…" | pass; listed `accessToken` verifies as that subject; audit rows `root/tenant-api`, five operations; B has no audit rows |
| root stays inside catalogue and ceiling | "stays inside the project catalogue and operator ceiling" | pass; `outside` role and `['*']` role 403 with no effect; narrowed ceiling refuses `uploader` |
| A's root edits and deletes a co-owner's subject | "edits and deletes a co-owner's subject without touching ownership" | pass; owner actor rows byte-identical before/after |
| A's root removing A's last owner | "refuses removing the last usable owner (409) with no effect" | pass; 409 `SUBJECT_ADMIN_LAST_OWNER`, both tenants' rows unchanged |
| root revocation vs operator transfer (the M6b item-2 interleaving, on the root plane) | "race: a root revocation of the incoming owner serializes…" | pass; revoke `applied`, transfer `refused/OWNERSHIP_SUBJECT_UNKNOWN`, usable owners `['manager']` |
| root on owner and operator routes | "refuses root on owner and operator routes…" | pass; `/api/v1/tenant/settings` (GET, PUT, rollback), `/subject-policy` (GET, PUT) → 401 `CREDENTIAL_REFUSED`, no owner service called; operator policy and owner-plane `/credential` → 404 on DATA; owner listener subject route with `api-secret` → 401; role PUT/DELETE → 501 |
| B's root cannot affect A | "refuses another tenant's root…" | pass; B's root on A's host: GET, DELETE, PUT, POST subject, POST role → 401, A unchanged; subject token as `api-secret` → 401; B's root on B's host deletes B's twin only |
| legacy writer not buildable | "allows explicit owner revocation; the writer without an owner policy is not buildable…" and "holds distinct privilege shapes…" | pass; no/undefined/null `ownerPolicy` → `TypeError`; the earlier writer's grants → `SUBJECT_ADMIN_STORE_UNSAFE` on both planes; owner plane on the root identity and root plane on the owner identity → `SUBJECT_ADMIN_STORE_UNSAFE` |
| single-site admin tools unchanged | `tests/authsubjects.test.js`, `tests/api.security.test.js`, `tests/api-docs.contract.test.js` on mongo 7.0.43 | **42 passing, 0 failing** |

Other affected suites at the lane head:

| suite | result |
|---|---|
| `tests/subject-admin-postgres.integration.test.js` (converted from the earlier writer to the owner-aware writer: owner grants, policy `['*']`, actor `manager`) | 10 passing, 0 failing |
| `tests/subject-management-http.integration.test.js` (same conversion) | 13 passing, 0 failing |
| `tests/owner-preview.integration.test.js` (dedicated PostgreSQL by digest, database `owner_preview_test`) | 9 passing, 0 failing |
| focused unit set (20 files: root-admin, subject-admin, owner-*, tenant-legacy-credentials, tenant-app, secrets, preview-serving-status, preview-vault-token-file, legacy-credential-issuance*, serve-roles, serve-listeners, compose-deployment-protocol, tenant-rest-authority) | 198 passing, 0 failing |
| deploy tests (`compose-deployment-protocol`, `compose-ui`, `tenant-deployment-operations`, `deploy/multitenant/bootstrap.test.js`, `restore.test.js`) | 47 passing, 0 failing |
| `node scripts/test-tiers.js check` | `615 test files, 8 tiers: ok` |
| `npm run lint` | 0 errors, 49 warnings |
| native mutants in `tests/native/oidc-matrix/authority-races-controls.cjs` | all eight anchors still materialize against the changed sources (not executed: native campaigns out of scope) |

New unit file `tests/root-admin.test.js` (registered in `tests/tiers.json`, unit tier): router
binding and refusals without a database, preview `subjectAdmin` parsing (separate identity, same
database, valid catalogue), and the preview API boot composing the root-plane writer only when
selected.

## Break-it controls

Each control edited one source file, ran the suite, restored the file (`cmp`-identical to the
committed file afterwards). Logs in `externals/work/root-admin-parity-20261110-evidence/` (local).

| control | edit | result | symptom |
|---|---|---|---|
| C1: root through the legacy writer's removal | `postgres.js`: last-owner check skipped when `owner.plane === 'root'` (the earlier writer's `remove`) | 32 passing, 1 failing | "refuses removing the last usable owner (409)": `200 !== 409` |
| C2: root reaches an owner route | `tenant-app/index.js`: owner `protect('owner')` accepts a root session | 32 passing, 1 failing | "refuses root on owner and operator routes": `200 !== 401` |
| C3: tenant binding dropped on the restored routes | `root-admin.js`: secret verified against every bound tenant, actor kept on the resolved tenant | 32 passing, 1 failing | "refuses another tenant's root…": `200 !== 401`; body is A's subject list (without `accessToken`, because token derivation still checks A's root) |
| C4: token listing without the root check | `secrets/component.js`: root comparison removed in `rootLegacyTokens` | `tests/tenant-legacy-credentials.test.js` 8 passing, 1 failing | another tenant's secret received A's token map |

C1 is the reachable form of "root through the legacy writer": composing root on a writer without
an owner policy is now refused at construction (case 8 above), so the control removes the one
behaviour that writer lacked.

## Grant changes (commit 2, `deploy/multitenant/config.js`)

New identity `nsdemo_root_writer`, used by the api role through `NS_API_ROOT_WRITER_PG`; api config
gains `subjectAdmin {writerConnectionEnv:'NS_API_ROOT_WRITER_PG', ownerPolicy:{catalogue:['api:entries:read']}}`
(the owner catalogue). Derived from the SQL the root plane runs:

| table | grant | why |
|---|---|---|
| `tenant_authorization_subjects` | SELECT, INSERT, UPDATE, DELETE | list, create, update, `FOR UPDATE` lock, remove, guard's `FOR UPDATE OF s` |
| `legacy_credential_subjects` | SELECT, INSERT, UPDATE, DELETE | token prefix with the subject, metadata lock |
| `tenant_authorization_roles` | SELECT, INSERT, UPDATE(owner_fence) | list, create, `FOR SHARE` on proposed roles |
| `tenant_authorization_subject_roles` | SELECT, INSERT, DELETE | links |
| `tenant_subject_admin_audit` | INSERT | audit, no reads |
| `tenant_authorization_config`, `tenant_owner_policy` | SELECT, UPDATE(owner_fence) | `FOR SHARE` (serializes with operator ownership transfer) |
| `tenant_owner_actors` | SELECT only | the last-owner guard reads owner rows; root never locks or writes them |

Not granted: the access schema, `legacy_credential_config`, audit reads, the control schema (the
loop that gives every other role control-schema reads excludes `root_writer`). The api's serving
identity is not broadened. Measured on real PostgreSQL by applying the plan's SQL and building the
store (`deploy-grants.check.js`, log `deploy-grants.log`): root plane on `root_writer` builds; owner
plane on `owner_writer` builds; crossing them → `SUBJECT_ADMIN_STORE_UNSAFE`; the earlier writer →
`TypeError`; adding `UPDATE(owner_fence)` on actors → UNSAFE; removing `SELECT` on actors → UNSAFE;
restored → builds.

## Decision questions

**Q1. Role edit and delete (`PUT/DELETE /api/v2/authorization/roles`).** Answer 501 today. Mechanism:
the audit constraint admits only `update, remove, create, create-role, issue, owner-*`
(`lib/tenant-authorization/postgres-candidate.json` migration 0006), so an audited role update
needs a new migration; the writer has no `UPDATE(permissions)` or `DELETE` on roles; roles are keyed
by name and `tenant_authorization_subject_roles` has a foreign key to them, so deleting a held role
fails where a single site leaves dangling names, and a rename would rewrite links. Options: (a)
migration 0007 adding `update-role`/`remove-role`, grants on the root identity only, update inside
catalogue ∩ ceiling, delete refused while held, rename refused; (b) keep 501. Recommendation (a):
the admin tools' Save on an existing role is a PUT, so parity is incomplete without it; refusing a
held delete keeps current authority valid (a missing role makes the authority throw
`TENANT_AUTHORITY_INVALID` for every holder, read-derived from `lib/tenant-authorization/postgres.js`).
Unmeasured: migration numbering against peer lanes. Multitenant only.

**Q2. Root's grant bound.** Root is bounded by project catalogue ∩ operator ceiling (owner authority:
owners "cannot exceed operator/project bounds"). In the compose demo the catalogue is
`['api:entries:read']`, so root there can grant only that; on a single site `API_SECRET` can grant
`*`. Recommendation: keep the operator bound (root must not exceed operator authority) and have
deployments that want single-site behaviour set catalogue and ceiling to `['*']`. Multitenant only.

**Q3. Subjects with admin permissions.** On a single site any subject whose roles grant
`admin:api:subjects:*` (for example the default `admin` role, `*`) can use the admin tools
(`managementPermission` in `lib/authorization/endpoints.js`). The restored routes accept only the
root secret; owner authority states that data permissions including `*` confer no management
membership. Recommendation: keep root-only; record the difference for operators.

**Q4. Tenants without an owner policy row.** Root authority reads the policy row for catalogue
digest and ceiling; without it every root admin call is 403 (read-derived from `owner-policy.js`
`authority`). Operators must provision the policy row for root parity, as for owners.

No defect is proposed for a BF id: the M6b item-2 property (a writer blind to ownership) is now
closed by construction (case 8, C1) and measured on the root plane (race case).

## Unmeasured

- Preview API boot against real PostgreSQL and Vault with `subjectAdmin` (only the source-level
  boot composition test ran).
- Restore cohort census with the api role holding a `root_writer` backend (owned by the admin
  lifecycle fit lane; read-derived risk: the census refuses backends it cannot attribute).
- Native `tests/native/oidc-matrix` authority races against the changed owner policy.
- Browser run of the admin tools page against the DATA listener.
