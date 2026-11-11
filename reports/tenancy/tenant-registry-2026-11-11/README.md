# Tenant registry and provisioning: design and lane record (MT-TENANT-REGISTRY)

*Contributor-facing lane record, 2026-11-11. Living until the lane hands off. Decisions implemented:
[tenant-registry](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-registry),
[provisioning-split](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#provisioning-split) (as refined
on alignment `3b841112c`). Patterns reused:
[change-stamp-definer-function](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#change-stamp-definer-function),
[admission-epoch-everywhere](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#admission-epoch-everywhere),
[readiness-serve-then-warm](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#readiness-serve-then-warm),
[pool-primitive-shared](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#pool-primitive-shared).*

## Anchors

| tree | commit |
|---|---|
| base: batch join accepted head (`codex/batch-join-20261111`) | `0392acf9` |
| lane branch `workspace/tenant-registry-20261111`, worktree `externals/work/crm-tenant-registry-20261111` | see [Slices](#slices) |
| nightscout-deploy (read only) | `9de244d` |
| alignment `main` at design time | `3b841112c` |

Base note: the local branch `workspace/multitenant-20261102` is at `0afdb87f`, an ancestor of `0392acf9`; the accepted
batch head `0392acf9` has not been fast-forwarded into it. The lane branches from `0392acf9`, as the peer lane
`workspace/capacity-fixes-20261111` does.

## Design

### What exists at 0392acf9 (read-derived)

- `lib/server/serve/preview-config.js:128-148` builds the resolver, one Vault Transit provider per tenant
  (`encryptionKey`, `signingKey`, `signingVersion`, `tokenEnv | tokenFile`), the client environment and the access-token
  trust keys from `config.tenants` and `config.accessTokens.keys`.
- The api uses the static set in `tenant-startup` cells, `human-session/runtime` (`tenants`), root-admin
  authentication (`tenants`), `secrets.providerFor`, `preview-domains` (`config.environments`), and the operation window's
  static lock map (`operation-cohort-config` `locks`; `operation-window.js:28`).
- Realtime, evaluator, tenant-admin, admin (ownership), the operation config (`locks`), the socket admission file and the
  UI config each carry their own tenant list.
- Per-tenant provisioning today lives in the Compose bootstrap (`nightscout-deploy bindings/compose/multitenant/bootstrap.js:91-149`)
  and the core fixture (`tests/fixtures/realtime-preview/bootstrap.js`), mixed with lab priming.
- Vault key names are index-based: `tenant-<i>-data`, `tenant-<i>-signing`, `tenant-<i>-access`, `tenant-<i>-management`,
  one ACL policy `<prefix>_tenant_<i>` per tenant; the Vault Agent policy is the union of those policies
  (`vault-agent-bootstrap.js:63-72`), so it grows with N and changes with every tenant.

### Catalogue, namespace and migration number

A new operational catalogue `lib/tenant-registry/postgres-candidate.json`, migration **`0001_tenant_registry`**, in its own
namespace (deployment layout kind `registry`). It is added to the census `OPERATIONAL` list
(`lib/tenant-operations/catalogues.js:22`) with its digest pinned: it is deployment configuration, never part of a tenant
artifact, export, erase or restore.

| object | columns | access |
|---|---|---|
| `tenant_registry` | `tenant_id uuid PK` (not the metadata tenant), `state text CHECK (state IN ('active','removed'))`, `signing_version integer >= 1`, `revision bigint`, `created_at`, `updated_at` | FORCE RLS on `app.current_tenant_id`; SELECT granted to serving identities, so a role reads its own tenant's row only under that tenant's binding |
| `tenant_registry_hosts` | `host text PK` (lower-case, validated like `tenant-resolution`), `tenant_id uuid FK`, `kind text CHECK (kind IN ('alias','internal'))` | no RLS, **no grant to any login role**; read only by the definer function |
| `tenant_registry_keys` | `(tenant_id, purpose IN ('access','management'), kid)` PK, `public_key text` (Ed25519, base64, public material) | FORCE RLS; SELECT to api (access) and tenant-admin (management) |
| `tenant_registry_clock` | singleton `revision bigint` | no RLS, no grant; read only by the revision function |

`state` holds existence only (`active`, `removed`). Pause and suspend stay in `tenant_activity`, their one home
(decision activity-row-always-provisioned), read afresh per request as today.

### Definer functions, signatures and grants

Shaped exactly as `tenant_change_stamps` (`lib/change-stamps/postgres.js`): `SECURITY DEFINER`, `plpgsql`, owned by the
NOLOGIN catalogue owner, `SET search_path = <registry ns>, pg_catalog`, `SET app.current_tenant_id = ''` so a binding
never leaks to the caller, `REVOKE ALL ... FROM PUBLIC`, `EXECUTE` granted only to the serving identities that resolve hosts
(api, tenant-admin, realtime), named in the census operational inventory.

```sql
tenant_registry_lookup(host text, kind text) RETURNS TABLE (tenant_id uuid, state text)
tenant_registry_revision() RETURNS bigint
```

- `lookup` reads one `tenant_registry_hosts` row by exact `(host, kind)`, binds that tenant with
  `set_config('app.current_tenant_id', ..., true)` and returns that tenant's `(tenant_id, state)`. Zero or one row. No
  other column, no list, no prefix match.
- `revision` returns the singleton counter. Every provisioning transaction (and any later alias, state or signing-version
  change) increments it in the same transaction.
- Every call also returns the function's catalogue version (`pg_proc.xmin` plus owner attributes); an unadmitted version
  runs the full attribute check (definer, language, result type, body, owner without LOGIN/SUPERUSER/BYPASSRLS, no PUBLIC
  EXECUTE, pinned config) before any row is used, the change-stamp and admission-epoch rule. Refusal code
  `TENANT_REGISTRY_FUNCTION_UNSAFE`.

### Lookup, bounded cache and refresh rule

`lib/tenant-registry/reader.js` is a resolver with the same `resolve(req)` contract and refusal codes as
`lib/tenant-resolution` (every call site already `await`s it), plus `entry(tenant)` for per-tenant attributes.

- **First request**: the host is validated with the existing `hostname()` rules (`TENANT_HOST_INVALID` as today), then
  looked up through `tenant_registry_lookup`. Per-tenant attributes (`signing_version`, public keys) are read once under
  that tenant's RLS binding and cached with the entry.
- **Bound**: an LRU of at most `maxTenants` positive entries (operator-set, default 10,000, maximum 100,000) and a separate
  negative cache of at most 1,024 unknown hosts. Concurrent misses for one host share one lookup.
- **Refresh (stage 1, aggregate poll)**: one `tenant_registry_revision()` statement per `refreshMs` (default 2,000 ms,
  bounds 250–60,000) per process, independent of tenant count. When the revision moves, the negative cache is cleared and
  every positive entry is marked stale; a stale entry is revalidated (one lookup) on its next use. No LISTEN/NOTIFY.
- **New tenant**: served without a restart within `refreshMs` plus one lookup.
- Unmeasured: revalidation after a change touches each cached host once on next use (about N lookups spread over traffic at
  N cached tenants). A changed-since function would remove that but returns tenant ids across tenants; left for stage 2 with
  NOTIFY.

### Unknown host

Same refusal as today: `TENANT_HOST_UNKNOWN` (and `TENANT_PROXY_UNTRUSTED`, `TENANT_SELECTOR_CONFLICT` in
canonical-internal mode with the same rules). The negative cache only bounds the database cost of repeated unknown hosts.

### Removed or suspended tenant and cached entries

- `removed`: provisioning's removal path deletes the host rows and sets `state='removed'` in one transaction with a revision
  bump. Within one refresh interval every entry is stale; its next request re-looks up, finds no host, and refuses with
  `TENANT_HOST_UNKNOWN`. A cached `entry(tenant)` for a removed tenant answers `TENANT_REMOVED`.
- Suspended or paused: unchanged. `tenant_activity` is read per request by the serving gate; the cache never holds it.
- The registry never re-points a host to another tenant in place: an alias change is remove-then-add, both with revision
  bumps, so a stale cached host can only refuse, never serve the wrong tenant beyond one refresh interval. (Re-pointing is
  not offered by this lane.)

### Admission epochs and the restore fence with a cached tenant

- The cache only supplies which tenant a host names and its Vault/key attributes. Every data transaction still acquires the
  operation window's shared advisory lock and reads the window row and catalogue epoch inside the transaction
  (`operation-window.js` `assertClient`), so a restore or maintenance window refuses requests whatever the cache holds.
- The window's static `locks` map gives way to a **lock-key rule** (below) for registry tenants; the in-transaction check
  `row.lock_key !== held.key` (`operation-window.js:128`) remains the fence, so a lock key that differs from the window row
  refuses `LIFECYCLE_WINDOW_BINDING_CHANGED`.
- A restore increments the window generation; existing `invalidateTenant` paths reset startup cells as today. Registry rows
  are operational and are not restored, so restore cannot change a tenant's hosts.
- The registry functions carry their own version admission (above); registry tables are not added to the window's
  catalogue epoch.

### Fixed rules: Vault key names and lock keys

- Vault Transit key names: **`tenant-<purpose>-<tenant uuid>`**, purpose in `data`, `signing`, `access`, `management`
  (for example `tenant-data-0b5c...`). Purpose first so that one role-level ACL can use prefix globs
  (`path "<mount>/decrypt/tenant-data-*"`); the index form `tenant-<i>-<purpose>` is not accepted in registry mode.
- Vault credential: one role-level source (`vault.tokenFile`, the Vault Agent sink, or `vault.tokenEnv`); no per-tenant
  token reference exists to store. `signing_version` is per-tenant state in `tenant_registry` (it changes on rotation),
  not a Vault reference.
- Operation-window lock key: derived, `1 + (first 62 bits of sha256('nightscout-tenant-lock-v1:' + uuid))`, written once
  into `tenant_lifecycle_windows.lock_key` at provisioning (its existing home, `UNIQUE`); a collision refuses provisioning
  with `TENANT_PROVISION_LOCK_COLLISION`.

### Provisioning: library, admin operation, batch form

`lib/tenant-registry/provision.js` is the implementation; the admin role exposes it on the operator plane as
`tenant-provisioning` (new contract in `lib/server/internal-api/contracts/`). No caller writes provisioning rows with its own
database credentials.

Steps for one tenant, idempotency key **the tenant id**:

1. Validate the spec (id, hosts, optional canonical internal host). If the id exists in the registry with the same hosts:
   outcome `existing`, nothing written. Same id with different hosts, or a host bound to another tenant: `refused`
   (`TENANT_PROVISION_CONFLICT`), nothing written.
2. Vault: for each purpose, read the key; create it if absent (`aes256-gcm96` for data and signing, `ed25519` for access and
   management, non-exportable); an existing key of the wrong type refuses. Read the access and management public keys.
3. Root secret record: if no `root` record exists for the tenant, generate and encrypt one through the secrets component; an
   existing record is reused.
4. One PostgreSQL transaction on the provisioning identity, all or nothing: `tenant_registry`, `tenant_registry_hosts`,
   `tenant_registry_keys`, the clock bump; `legacy_credential_config` (`root`), `tenant_authorization_config`
   (`anonymous_roles = {denied}`), `tenant_owner_policy` (deployment catalogue), `access_tenants`, `access_keys`
   (`key1`/data, `management1`/management), `tenant_write_clock`, one `tenant_consumer_checkpoint` per configured consumer
   (consumer id and contract digest are deployment configuration of the operation), `tenant_lifecycle_windows`
   (derived lock key, `active`, generation 1), and the activity row and audit (`tenant-activity/provisioning.js`, in the
   same transaction as the window row).

The **commit point is the registry row**, written in step 4. A tenant without a registry row is not served. Failure before or
inside step 4 leaves no registry row and rolls back every row of step 4; Vault keys and the root secret record from steps 2–3
remain and are adopted by a re-run, which then produces the same state as a clean run. Nothing that serves a tenant exists
before step 4 commits.

Not provisioning (lab priming, stays in the bench and lab harness): subjects, roles, subject roles, owner actors, access
credentials and sessions, management tokens, and synthetic entries. Restore authority (`tenant_lifecycle_restore_authority`)
stays a separate operator step.

**Batch form** (`provisionTenants`): at most 100 tenants per call (contract `maxItems`, and the admin listener's `maxBytes`);
each tenant runs the single-tenant steps independently (one transaction per tenant, bounded concurrency 4); the response has
one result per tenant in request order: `{ id, ref, outcome: 'created' | 'existing' | 'refused', code? }`. A retried batch
returns `existing` for tenants already committed, so retry after any failure is safe. Duplicate ids or hosts inside one
batch refuse the whole batch before any work.

**Credential hook for priming**: each seed row may carry `ref`, an opaque lab label echoed in every result. On `created`
only, and only when the request sets `issueRootSecret: true`, the result carries the tenant's root secret once; the CLI
writes it to a `--secrets-out` file (mode 0600) keyed by `ref` and id. The harness reads that file to prime each tenant
through its normal data API. A re-run returns `existing` without a secret; the harness keeps its file. The provisioning
CLI and the admin API load no data.

### The CLI: one thin client

`nightscout admin provision`, a top-level client command beside `healthcheck` (which is also a client of a role's listener);
`nightscout multitenant <roles>` stays the serving command.

```text
nightscout admin provision --id <uuid> --host <host> [--host <host>...] [--internal-host <host>] [--ref <label>]
nightscout admin provision --seed <file.json|file.csv> [--batch 100] [--secrets-out <file>]
  admin listener: --socket <path> | --url http://<private address>  (default from ADMIN_HOSTNAME/ADMIN_PORT)
```

Seed schema, one for both formats:

| field | JSON | CSV column | rule |
|---|---|---|---|
| `id` | string | `id` | canonical lower-case UUID, required |
| `hosts` | array of strings | `hosts`, `;`-separated | at least one in direct-alias mode |
| `internalHost` | string | `internal_host` | canonical-internal mode only |
| `ref` | string | `ref` | optional, `^[A-Za-z0-9_.-]{1,64}$` |

JSON is `{ "version": 1, "tenants": [ ... ] }`; CSV has a header row naming exactly those columns. The CLI sends bounded
batches, prints one line per tenant (`ref id outcome [code]`), exits 0 only when every tenant is `created` or `existing`,
and is safe to re-run. It has no database or Vault credentials.

### Roles in registry mode, and refusing a tenant list

A role selects the registry with a `registry` block (connection env of its serving identity, namespace, `maxTenants`,
`refreshMs`). A config that carries `registry` and `tenants` (or per-tenant `accessTokens.keys`) is refused at load with
`registry configuration refuses a tenants list`. Order of conversion:

1. **api** (this lane, first): resolver, Vault providers by rule, access-token keys from `tenant_registry_keys`, client
   environment from `tenantSettings` (required in registry mode), startup cells created on first lookup, operation window
   lock by rule.
2. tenant-admin and admin ownership (lookup and management keys).
3. realtime and evaluator need the set of tenants without a request; they are open items (an enumeration path through
   the change-stamp or a registry function, sized for 10k), not in this lane's first delivery.

## Slices

| slice | commit | what it does | focused tests |
|---|---|---|---|
| S1 | `a2ffddb2` | Catalogue `lib/tenant-registry/postgres-candidate.json` (`0001_tenant_registry`), three definer functions (lookup, revision, paged enumeration of active ids, added per the coordinator's redirect), statement-level revision trigger, reader with version admission (`postgres.js`), fixed rules (`rules.js`), census `OPERATIONAL` pin | `tests/tenant-registry.integration.test.js` |
| S2 | `abaa2fad` | Registry resolver: first-request lookup, bounded LRU + negative cache, one revision poll per interval, fail closed past the staleness bound (`resolver.js`) | `tests/tenant-registry-resolver.test.js` |
| S3 | `f2f0e63c` | Provisioning library (`provision.js`, `vault-keys.js`); lifecycle migration `0008_tenant_lifecycle_window_provisioning` (window INSERT policy) and window readiness expecting it | `tests/tenant-registry-provision.integration.test.js` |
| S4 | `75e65b8e` | Admin REST resource (`rest.js`, `openapi.json`), admin config `provisioning` section, `nightscout admin provision` client (`lib/cli/commands/admin.js`) | `tests/admin-provisioning.integration.test.js`, `tests/admin-provisioning-cli.test.js` |
| S5 | `4c0b2c98` | api in registry mode: `registry` + one role-level Vault credential in place of `tenants`; `registry-tenants.js` materializes binding, provider (key names by rule, signing version from the registry), environment and access keys on first resolved request; startup cells on first use; operation config may name `registry` in place of `locks` (lock key by rule); restore cohort treats the registry as its tenant set; refuses a tenant list or `accessTokens.keys` beside `registry`; refuses socket forwarding and OIDC in registry mode | `tests/api-registry.integration.test.js`, `tests/registry-config.test.js` |
| S6 | `b5d00a1b` | tenant-admin (`registry` in place of `tenants` and `management.keys`; owner credential providers by rule) and admin ownership (`registry` in place of `tenants`; acts for active registry tenants) | `tests/registry-config.test.js` (unit); existing owner/admin suites |
| S7 | `3dcd4731` | Evaluator stage 1 (option a): `registry` in place of `tenants` (tenant settings store required); `registry-tenant-set.js` enumerates active ids at start, removal reads as not configured within the refresh bound, tenants added after start counted as `waiting` (alert `TENANT_REGISTRY_EXPANSION_RESTART {waiting}`, health `registry`, evaluator-inspection contract optional `registry` object); pool slice over the enumeration; empty registry refuses start (`TENANT_REGISTRY_EMPTY`) | `tests/registry-tenant-set.integration.test.js`, `tests/registry-config.test.js` |
| S8 | `f5c4c0c3` | Provisioning isolation: `/v1/tenants` (one, batch, read, description) answers as an unknown route on the api, tenant-admin and realtime public listeners and every `serve.internal` listener; realtime public routes factored into `publicApp`; docs: operator REST API section in `docs/internal-service-api.md`, admin listener in `docs/internal-service-topology.md`, `docs/tenant-registry.md` (catalogue, definer functions, cache, fixed names, provisioning), `nightscout admin provision` in the README | `tests/provisioning-private.test.js`, `AR_PROVISIONING_PRIVATE`, `PROVISIONING_PRIVATE` in `tests/owner-preview.integration.test.js` |

Branch head `f5c4c0c393fa1717a05b64fc5efa2d25cc3d15e4`, 8 commits on `0392acf9` (55 files changed, 3162 insertions(+), 76 deletions(-), from `git diff --shortstat`). Not pushed.

Design changes after the note, from the coordinator: provisioning is a REST resource on the admin listener
(decision operator-rest-api), not an RPC contract; the evaluator and realtime are in this lane, so the catalogue
carries the enumeration function; live addition of tenants to a running evaluator or realtime is its own lane
(MT-TENANT-LIVE-ADD, decision tenant-live-add) and this lane builds stage 1 (restart picks them up). The CLI is
`nightscout admin provision` (a top-level client command beside `healthcheck`; `nightscout multitenant` stays the
serving command). A configuration without `registry` still loads its static tenant list: the refusal applies once a
configuration selects the registry (see Open). Finding during S3 (reproduced): `tenant_lifecycle_windows` had no INSERT policy under FORCE
RLS, so only a superuser or BYPASSRLS identity could provision a window row (the Compose bootstrap runs as the
database superuser). Migration 0008 adds `FOR INSERT WITH CHECK (bound tenant AND phase = 'active' AND generation = 1
AND claim_id IS NULL AND artifact_digest IS NULL)`; `operation-window-readiness.js` `policiesFor` expects it.

## Gates and controls

All runs on a disposable `postgres:16` container (PostgreSQL 16.15) and dev-mode Vault containers started by the
lab fixture, on 2026-11-11, before any quiet window. Counts are mocha's. Every control was put back and the suite
re-run green.

| gate | test (focused count) | control | symptom when broken |
|---|---|---|---|
| The definer function returns only the host mapping; tenant A's context sees no B rows | `tests/tenant-registry.integration.test.js` (12 passing): `TR_DEFINER_NARROW`, `TR_ISOLATION`, `TR_GRANTS`, `TR_ALTERED_REFUSED` x4, `TR_BODY_REPLACED` | widened the catalogue's lookup to also return `host` (all hosts aggregated), reader admitting the new shape | `TR_DEFINER_NARROW` red: result fields `['tenant_id','state','host']` instead of `['tenant_id','state']`; 11 others green |
| Cache refresh: a new tenant is served after the next poll | `tests/tenant-registry-resolver.test.js` (9 passing) | poll never moves the revision after the first read | `RR_NEW_TENANT` red (`TENANT_HOST_UNKNOWN`), `RR_REMOVED` red (missing rejection), `RR_REVISION_LISTENERS` red |
| A tenant provisioned while the api runs is served without a restart, within the refresh bound | `tests/api-registry.integration.test.js` (3 passing); served after 376 ms at `refreshMs` 500 (one run) | same refresh break | `AR_NEW_TENANT` red: last status 404, expected 403 (anonymous refusal of a served tenant); `AR_REMOVED` red: 403 instead of 404 |
| A config carrying `tenants` is refused | `tests/registry-config.test.js` (7 passing): api, tenant-admin, admin ownership, evaluator, `accessTokens.keys`, `management.keys` | admitted `tenants` beside `registry` in the api loader | `RC_TENANTS_REFUSED` red: missing expected exception |
| Provisioning twice gives the same state; an injected failure leaves no partial tenant and a re-run converges | `tests/tenant-registry-provision.integration.test.js` (14 passing; failure injected at each of 9 steps) | on failure, `COMMIT` instead of `ROLLBACK` | the 7 in-transaction injection points red with leftover rows (for example `{ 'registry.tenant_registry': 1 }`); the 2 pre-transaction points (vault, database) stay green, as designed. A first control (no `BEGIN`) was rejected as imprecise: it broke every test because the tenant binding is transaction-local |
| The root secret never reaches CLI stdout or stderr | `tests/admin-provisioning.integration.test.js` (5 passing), `AP_CLI_NO_SECRET_LEAK` in both seed formats | the CLI also writes each secret to stderr | `AP_CLI_SEED_CSV` and `AP_CLI_SEED_JSON` red with `AP_CLI_NO_SECRET_LEAK: a root secret reached the terminal` |
| `/v1/tenants` is reachable only on the admin listener | api: `AR_PROVISIONING_PRIVATE` (`tests/api-registry.integration.test.js`, 4 passing); tenant-admin: `PROVISIONING_PRIVATE` (`tests/owner-preview.integration.test.js`, 10 passing); realtime and every internal contract: `tests/provisioning-private.test.js` (2 passing) | mounted the provisioning REST handler (with a stub library) on each public listener in turn: api, tenant-admin, realtime | each red: `POST /v1/tenants` answered `201` where an unknown route answers `404` |
| Evaluator stage 1: removal within the bound, waiting count, alert with the count | `tests/registry-tenant-set.integration.test.js` (2 passing) | none run (UNMEASURED as a control) | |

Other focused suites run green on the branch: `tests/admin-provisioning-cli.test.js` (4), census
`tests/tenant-deployment-operations.test.js` (28), unit sets for cohort, operation window, startup, root-admin,
admin role, owner, evaluator, realtime (182 + 116 + 72 passing in three runs).

Multitenant corpus suites touching resolution, admission and restore, re-run after S5/S6/S7 changes (opt-in flags as
in `scripts/test-multitenant.js`): `multitenant-preview-process` 16, `tenant-runtime-vault` 7, `owner-preview` 9,
`admin-lifecycle-fit` 6, `admin-role-ownership` 11, `operation-window-epoch` 47, `tenant-ownership-postgres` 9,
`tenant-key-retention` 6, `tenant-activity` 8, `evaluator-consumers` 13 passing. Not run: `tenant-rest-context`
(needs MongoDB 4.4+; the local mongod is 3.6). `realtime-browser-diagnostics.test.js` times out at mocha's default
2000 ms on this branch and identically on the base worktree at `0392acf9` (not a change of this lane).

Not measured end to end: the evaluator role booted in registry mode (config, boot path and tenant set are tested
separately; no evaluator lab run in registry mode); tenant-admin and admin ownership in registry mode beyond unit
tests; the full suite and the joined-browser corpus.

### Restart cost to pick up one new tenant (stage 1)

`RS_RESTART_COST`, one run each, machine not quiet: the registry part of a restart (enumerate active ids through the
paged definer plus build each tenant's evaluator entry) took 18 ms at 101 tenants, 62 ms at 1,001 and 142 ms at
3,001, one enumeration each. The rest of an evaluator restart (readiness, warm, first evaluation of every tenant) is
the existing serve-then-warm cost and is not re-measured here; the 2026-11-10 measurement put a bounded warm at
1,000 tenants at 421 s for the evaluator (`reports/tenancy/perf-db-2026-11-10/README.md`).

## Deploy changes required (nightscout-deploy)

Read at nightscout-deploy `9de244d`; nothing edited there.

1. **Schema and identities.** Add the `registry` namespace and catalogue (`lib/tenant-registry/postgres-candidate.json`).
   The bootstrap's owner loop refuses functions with arguments (`bootstrap.js` `BOOTSTRAP_UNREVIEWED_FUNCTION_SIGNATURE`):
   the registry has `tenant_registry_lookup(text, text)` and `tenant_registry_tenants(uuid, integer)` (and the change-stamp
   function already has `uuid[]`), so the loop must alter owners by `oid::regprocedure`. Run
   `require('lib/tenant-registry/postgres').grants({ namespace, resolvers: [api, owner_reader, ...], enumerators: [evaluator, realtime], readers: [api, owner_reader] })`.
   Re-run the lifecycle catalogue to `0008`.
2. **Provisioning identity.** A new `provisioner` login role (NOSUPERUSER NOBYPASSRLS) with
   `provisionerGrants({ namespaces, role, checkpoints })` from `lib/tenant-registry/provision.js`; the admin role gets a
   `provisioning` section (connection env, the seven namespaces, checkpoint consumers with their contract digests, Vault).
3. **Vault.** Key names `tenant-<purpose>-<uuid>`. A provisioning policy: `create, read, update` on
   `<mount>/keys/tenant-*`, `update` on `<mount>/encrypt/tenant-data-*`. One serving policy per role with prefix globs
   (`decrypt/tenant-data-*`, `hmac|verify/tenant-signing-*`, `sign/tenant-access-*`) replacing the per-tenant policies
   and the Agent's union of them (`vault-agent-bootstrap.js:63-72`); one token source per role (`vault.tokenFile`).
4. **Role configs without a tenant list.** api, tenant-admin, admin ownership and evaluator take `registry`
   (`{ namespace, maxTenants?, refreshMs? }`); api and evaluator require `tenantSettings`; api `accessTokens` and
   tenant-admin `management` drop `keys`; the operation config takes `registry: { namespace }` in place of `locks`.
5. **Bootstrap split.** Per-tenant provisioning leaves the bootstrap: tenants are created by
   `nightscout admin provision --seed <file>` against the admin listener (one schema, JSON or CSV). Lab priming
   (subjects, roles, owner actors, access credentials and sessions, management tokens, synthetic entries) moves to the
   harness and uses each tenant's root secret from `--secrets-out` (0600) through the tenant's data API.
6. **Order at start.** Provision before starting the evaluator (an empty registry refuses its start); restart the
   evaluator to pick up tenants provisioned later (health `registry.waiting`).
7. Until the gaps below close, a Compose deployment that uses socket forwarding (legacy realtime) or OIDC stays on the
   static tenant list.

## Open

Gaps to close before registry mode becomes the default:

- **Realtime and api socket forwarding.** Not converted. Realtime's warm calls the api's private `authorizeSocket`
  (`preview-realtime.js:77-80`), and the api's private API resolves hosts from the static alias list and the socket
  admission file (`realtime/private-api.js:36-39,92`), which registry mode refuses. Realtime registry mode needs the
  admission object (`realtime/admission.js`: `resolve`, `resolveHost`, `allows`, `enabled`, `ids`, `aliases`) served
  from the registry (lookup for host, active for allows/enabled) on both the api and realtime, and the warm call
  without a tenant-to-host reverse lookup.
- **OIDC origins** (`OIDC_TENANT_ORIGINS`, one per configured tenant, `human-session/runtime.js:55-58`): refused in
  registry mode.
- **Static mode still loads.** A configuration without `registry` keeps its tenant list. Removing static mode (the
  decision's end state) also needs the fixtures (`tests/fixtures/realtime-preview/bootstrap*.js`, `deploy/multitenant/`)
  and nightscout-deploy moved to provisioning.
- **Tenant removal** has no operator operation yet (tests remove by SQL); deletion ceremony integration is open.
- **Settings at provisioning.** Provisioning writes no `tenant_settings` row; tenants start on operator-policy defaults.
- **Peer lane.** A trial merge of `workspace/capacity-fixes-20261111` (`5517cb6c`) conflicts in the five loaders this lane
  also changes (`admin-config.js`, `evaluator-config.js`, `operation-cohort-config.js`, `owner-preview-config.js`,
  `preview-config.js`); resolve at the join.
- Unmeasured: first-request lookup latency and cache churn at 10k; revalidation cost after each registry change (each
  cached host re-looked up once on next use); the evaluator role end to end in registry mode.

### For MT-TENANT-LIVE-ADD: fixed-set assumptions, read at `3dcd4731`

| where | assumption |
|---|---|
| `lib/server/serve/evaluator-runtime.js:82-86` | refuses an empty or changing `tenants` array at construction |
| `lib/server/serve/evaluator-runtime.js:98` | `states` Map built once from `tenants`; no add path |
| `lib/server/serve/evaluator-runtime.js:432` | health lists `states` only |
| `lib/server/serve/evaluator-runtime.js:478` | background boot iterates the start set |
| `lib/server/serve/evaluator-consumers.js:29-32,46` | `coordinate` refuses an empty set; `states` built once |
| `lib/server/serve/evaluator-consumers.js:137-140` | run, retry and backstop sweeps over the start `tenants` |
| `lib/server/serve/evaluator-consumers.js:206,231` | `prepare` takes `config.tenants` keys once and settles startup over them |
| `lib/server/serve/evaluator-pool.js:16-17,35,41,71` | gate built over the start tenant list; slice changes recomputed over that list only |
| `lib/server/serve/evaluator-preview.js:54,66,88,107,118` | gate, startup cells, runtime, pool wake and inspection over `config.tenants` |
| `lib/server/serve/evaluator-readiness.js:56` | readiness checks each start tenant |
| `lib/server/serve/tenant-startup.js:61-73` | cells from the start set; `accept` (added in S5) creates cells on first use and is the model for adding |
| `lib/server/serve/registry-tenant-set.js:29-51` | stage 1: `tenants` fixed at start, added ids only counted (`waiting`) |
| `lib/server/realtime/runtime.js:16,23,89,93,105` | refuses empty set; cells built once; detection and due selection over the start set |
| `lib/server/realtime/config.js:36-48` | `REALTIME_RESTART_REQUIRED` when the tenant set grows |
| `lib/server/realtime/admission.js:22-26` | `SOCKET_ADMISSION_EXPANSION_RESTART` when the admission file grows |
| `lib/server/serve/preview-realtime.js:71,78,94` | startup cells, warm host from admission aliases, runtime over `config.tenants` |
| `lib/server/realtime/protocol.js:343-347` | recheck over primed socket states (already dynamic per socket) |
