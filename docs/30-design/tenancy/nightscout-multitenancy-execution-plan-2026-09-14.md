# Multitenancy execution plan: decisions, tasks, and the context each one needs

*Contributor- and maintainer-facing.*

**Status: living document — the decision record.** Decisions D1–D17 are the maintainer's
(2026-09-14 to 2026-09-16) and are all **adopted**, except **D17 row 2** (Ory Kratos as one
cohort-wide human-identity pool), which is **held** pending queue item `T30-ORY-PROOF`. Each
decision carries the evidence that settled it. Task definitions follow in §6. **Item state lives
in [`queue/work-queue.yaml`](../../../queue/work-queue.yaml)** (rendered as
[`queue/QUEUE.md`](../../../queue/QUEUE.md), measured by `make queue-status`); defect facts live
in the [backfix register](../remedial/nightscout-backfix-register.md). Measured facts below name
their date and commit.

| ref | document |
|---|---|
| **{M}** | [Nightscout multitenancy: evidence and options](nightscout-multitenancy-discussion-2026-09-09.md) (snapshot) |
| **{C}** | [Deployable components](nightscout-deployable-components-2026-09-14.md) |
| **{S}** | [Storage seam interface](nightscout-storage-seam-interface-2026-09-14.md) |
| **{R}** | [What sets K](../../60-research/tenancy/multitenancy-k-and-residency-2026-09-14.md) |
| **{DB}** | [A real database in the loop](../../60-research/tenancy/exp-mt-026-database-in-the-loop-2026-09-14.md) |

---

## Where things stand

Measured 2026-09-24 against `cgm-remote-monitor` `official/dev` `153e5658` and
`nightscout-connect` `official/main` `4dde1ec`.

- **Shipping release:** `cgm-remote-monitor` tag `15.0.8` (`official/master` `92d08342`).
  `official/dev` is `153e5658` (the merge of #8762) and declares `15.0.9`: 350 commits and 61
  first-parent merges ahead of master
  (`git -C externals/cgm-remote-monitor-official rev-list --count official/master..official/dev`,
  and the same with `--first-parent`). Nothing past 15.0.8 is released; the release is queue
  `RT-0` (release PR #8598, no approving review).
- **Phase 0, `cgm-remote-monitor` half: merged, not released.** T0.1 (#8733), T0.2/T0.3
  (`bf/cache`, #8740), T0.5 (`bf/coercion`, #8737) and T2.4's allowlist (#8743) are in `dev`,
  with the other Phase 0, advisory and 15.0.9 PRs listed in queue `RT-0`. **Every §1 register
  defect, including those merged, is still present for every operator on 15.0.8** until 15.0.9
  ships. `bf/auth` (BF-17) and `bf/throttle` (BF-30) ship inside #8754 (`bf2/auth-hardening`,
  queue `BF2-AUTH`), which is open. `dev` pins `nightscout-connect` exactly `0.1.0` from npm
  (#8762, queue `P0-PIN`); `master` pins the `v0.0.13` tag tarball.
- **Connector half: released.** Connector PR #68 (T0.4) is in `nightscout-connect` `0.1.0`,
  released 2026-09-24 (tag `v0.1.0` on connector `main` `4dde1ec`, npm `latest`; queue `P0-TAG`).
  It reaches Nightscout operators with 15.0.9.
- **Tenancy work (Phases 1–4) is local and unpushed.** The seam chain ends at
  `seam/t1-2-storage-interface` `81a1f6ce` (worktree `externals/work/crm-seam`), cut from
  `chore/nightscout-modernization` at `0a4109f6`. That base is now `b1bdaca0`; the seam is 68
  behind it and 50 ahead, with 19 conflicting paths on trial merge (§5, queue `SEAM-REFRESH`).
- **Open tenancy work:** T3.0 (configuration surface and credential root). `T30-SCHEMA-CRED` has
  no blockers and is claimable; `T30-SCHEMA-CONFIG` waits on `T30-RESEARCH` (config half) and
  `T30-ORY-PROOF` (identity half).
- **`TENANCY_MODE=multi` is developer-only**, and under it alarms and live updates are withheld
  (§2.10, §7a).

**Task status words** (tasks in §6 are built on the local seam chain unless stated otherwise;
none of Phases 1–4 is merged anywhere): **DONE** · **DONE-EXCEPT** (built; one named site is
superseded by a later decision) · **GATE NOT MET** (the change landed, the numeric target did
not; the reason is recorded). Register statuses use the DoD words `open` · `fixed` · `merged` ·
`released`.

### Rules for picking up work

1. **Confirm the head commit and that your task is still open.** Several sessions share this
   branch and it moves several times a day.
2. **Allocate a `BF-` id by reading the register's highest id at the moment you write it.**
3. **Never create, delete or repoint a worktree you did not create.**
4. **A "done" command must exercise the shipping module, not a copy.** Harnesses `require()` the
   module by path; `tools/mt-bench/apitier.js` builds the real module and throws rather than
   printing a number for code that is not there.
5. **Nothing is pushed, merged, tagged remotely or published by an agent.** Prepare branches,
   commits and tags locally, record what you did, and stop; a human pushes, reviews and releases.
6. **On `cgm-remote-monitor`, a push to `dev` or `master` publishes a Docker image** (`main.yml`
   job `docker-build`, gated on those two refs). Treat it as shipping. Other branches on `origin`
   run nothing on push; `chore/nightscout-modernization` runs full CI on PRs targeting it. On
   `nightscout-connect` every branch and tag is safe — its one workflow runs tests and
   `npm publish` is manual. Detail: [PR sequencing](../remedial/phase0-pr-sequencing-2026-09-15.md) §0.
7. **Where things go (D12).** Shipping fixes and their tests go in `cgm-remote-monitor` as clean
   reviewable commits — no scaffolding, no findings in code comments. Harnesses, measurements and
   findings go in this repository.
8. **A check is evidence only after it has been seen to fail.** Break the code under it and
   confirm it goes red for the right reason; a check can be vacuous because the corpus never
   exercises the property *or* because the code under test cannot distinguish the branches.

**Repository layout.** The pristine shipping checkout is `externals/cgm-remote-monitor-official`
(origin = `nightscout/cgm-remote-monitor`), and every `crm-*` worktree under `externals/work/`
belongs to it. `externals/cgm-remote-monitor` is a detached checkout at a 2014 commit on a
different fork and holds none of this programme's work.

---

## 0. The map — what is where, and which document decides what

**When this plan and the queue disagree about whether something is done, the queue wins** — its
state is measured by gates. **When they disagree about why something is being done, or what a
decision was, this plan wins.**

| document | what it is for | authoritative for |
|---|---|---|
| [`queue/README.md`](../../../queue/README.md), [`queue/QUEUE.md`](../../../queue/QUEUE.md), `queue/work-queue.yaml` | the live index of every work item, with a gate per item | **item state** |
| this plan | decisions, their evidence, and task definitions | **decisions**, and what a task means |
| [backfix register](../remedial/nightscout-backfix-register.md) | every defect found, with provenance | **defect facts and ids** |
| [roadmap](../../00-overview/ROADMAP.md) | the order of the work ahead, generated from the queue's blockers | nothing; it links to where each order is decided |
| [maintainer release brief](../remedial/maintainer-release-brief-2026-09-15.md) | the Phase 0 batch, branch by branch | what a maintainer needs to say yes or no |
| [PR sequencing](../remedial/phase0-pr-sequencing-2026-09-15.md) | how the Phase 0 branches land | branch mechanics |
| [semver and release versioning policy](../modernization/semver-and-release-versioning-policy-2026-09-15.md) | the surface ladder, the version procedure, the adopted release train | **what number a change gets; the train** |
| [15.0.9 contents](../../../releases/cgm-remote-monitor-15.0.9/contents.md) and [decisions](../../../releases/cgm-remote-monitor-15.0.9/decisions.md) | what the next release contains, leaves broken and was decided on; what it still waits on is in [ROADMAP §1](../../00-overview/ROADMAP.md) | the next release |
| [tenant-owner configuration surface](tenant-owner-config-surface-2026-09-15.md) | T3.0's research deliverable and proposed DDL | the per-tenant configuration surface |
| [operator upgrade path](../../40-migration/operator-upgrade-path-2026-09-15.md) | what each release means for someone running a site | operator-facing upgrade guidance |
| [legacy CGM ingestion → Connect](../../40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md) | the Dexcom and MiniMed retirement | the legacy-bridge migration, which is on cut 1 (queue `RT-1`) |
| [connector pin consolidation](../../40-migration/connector-pin-consolidation-2026-09-15.md) | the `nightscout-connect` pins across `dev` and the cuts | background to the pin decision; item state in `P0-PIN` and `RT-CONNECT-PIN-CUTS` |
| [MongoDB → PostgreSQL, hosted](../../40-migration/mongodb-to-postgres-hosted-2026-09-15.md) | what moving a tenant's data costs | the migration shape |

---

## 1. Decisions

Each carries the evidence that settled it, so a later reader can tell a decision from a
preference.

| # | Decision | Basis |
|---|---|---|
| **D1** | **Bulk Nightscout-as-a-service hosting is the design target**; families, clinics and communities are configurations of the same system. **Self-hosted single-tenant stays first-class permanently**, on data-rights and mission grounds | maintainer, 2026-09-14; {M} §11 |
| **D2** | **Shared logical storage with a tenant discriminator** — *not* database-per-tenant. Database-per-tenant costs 47 WiredTiger files and ~3.7 MB of non-evictable `mongod` RSS **per tenant holding zero documents**, and fatal-asserts on file descriptors; the shared shape is 104 files total at 400 tenants, flat | {DB} §4, §7 |
| **D3** | **PostgreSQL + RLS for the multitenant service.** Index locality no longer separates the engines — the deciding property is that a forgotten filter returns **0 rows** under RLS and **every tenant's rows** under a discriminator | {DB} §7.1, §8.2 |
| **D4** | **MongoDB is permanent for the single-tenant target**, not a deprecated path. Existing self-hosters keep their databases, so the storage seam carries two mature backends permanently (§4) | maintainer, 2026-09-14 |
| **D5** | **Four hosted entrypoints over one core** — `api` (stateless), `evaluator` (change-driven), `realtime` (fan-out), `vcpool` — plus `single` unchanged. The split is also a configuration-source split (D15) | {C} §2, {DB} §6 |
| **D6** | **Change feed = replication slot (spine) + `NOTIFY` (latency) + bounded aggregate poll (backstop)**, with `NOTIFY` emitted **by the slot reader, never by a trigger** | {DB} §8.5, §9.4; measured in T4.1 |
| **D7** | **The platform-admin plane gets its own entrypoint on its own network interface**, ORY-style, secured by unreachability rather than a credential. Tenant admin stays on the consumer interface under RLS. A deliberate departure from Nocturne | maintainer, 2026-09-14 — §2 |
| **D8** | **API v3's closed operator set is the query contract; v1 is bounded by corpus evidence.** `mingo` is the differential-test oracle | maintainer, 2026-09-14 — §3 |
| **D9** | **Base the work on `chore/nightscout-modernization`**, not `dev` | maintainer, 2026-09-14 — §5 |
| **D10** | **Tenant `slug` is globally unique per deployment, and is a *host label*** — the resolver maps Host → slug by a configured rule with one capture group, so both `foo.user-content.apex.org` and `foo-user-content.apex.org` name tenant `foo`. Store the label only | maintainer, 2026-09-14 — §2.5 |
| **D11** | **`devicestatus` gets almost no generated columns.** Only its `indexedFields`; the body stays JSONB. The answer to its 182 nodes is *decomposition into normalised time series driven by registered controller descriptions*, not a wider column list | maintainer, 2026-09-14 — §2.6 |
| **D12** | **`rag-nightscout-ecosystem-alignment` carries the tooling, documentation, evidence and QC; `cgm-remote-monitor` stays pristine** | maintainer, 2026-09-14 — §2.7 |
| **D13** | **In `TENANCY_MODE=multi` there is no deployment-wide secret on any interface.** `API_SECRET` is a *single-tenant* bootstrapping mechanism and does not exist in multi mode; each tenant holds its own root credential, stored with its configuration. The platform-admin plane remains credential-free (D7) | maintainer, 2026-09-15 — §2.8 |
| **D14** | **Per-tenant JWT signing key**, stored with tenant configuration. Tenant resolution runs before any credential is examined, so the correct key is known at verify time; cross-tenant token reuse becomes a *signature* failure rather than a claim-check failure | maintainer, 2026-09-15 — §2.8 |
| **D15** | **Configuration source diverges by entrypoint.** `single` reads the process environment; hosted entrypoints read per-tenant configuration from the database, administered by the tenant owner. Env-sourced configuration must not reach the multi path | maintainer, 2026-09-15 — §2.8 |
| **D16** | **Three listeners, three audiences** — consumer/data (`ns-api`, plus `single`), tenant-owner configuration (`ns-tenant-admin`), platform operator (`ns-admin`). **Prerequisite: tenant resolution and credential verification extract into one module before the third listener exists** | maintainer, 2026-09-16 — §2.9 |
| **D17** | **The auth plane splits by audience, not by build-versus-buy.** Adopted: devices and the data path keep a **native per-tenant credential permanently**; Hydra is **deferred**; D7 is **unchanged**. **Held, not adopted:** human identity via one cohort-wide Ory Kratos pool, hosted-only — conditional on `T30-ORY-PROOF`. D14 holds either way: Nightscout mints its own per-tenant token after authentication | maintainer, 2026-09-16 — §2.9 |

**Amendment carried with D13, true however D17 row 2 lands:** *credentials are per-tenant,
identity is per-cohort, authorization is per-tenant.* Isolation rests on the authorization layer
and RLS, not on the authentication layer (§2.9).

---

## 2. D7 — the admin plane, and the decisions that followed from it

### 2.1 Two privilege planes that get conflated

| plane | who | examples | where it lives |
|---|---|---|---|
| **tenant admin** | a person administering *their own* site | settings, subjects, roles, credentials, their own export | **consumer side**, authenticated, RLS-scoped — Nocturne's `Controllers/V4/TenantAdmin/*`; under D16 the `ns-tenant-admin` listener |
| **platform admin** | the hoster | create/suspend/delete tenants, provisioning, cross-tenant export | **separate entrypoint** (`bin/admin.js`, `ns-admin`) |

Only the platform plane moves off the consumer interface. Tenant admin is an authenticated,
per-tenant request and must stay where RLS can bind it.

### 2.2 The ORY pattern, and why it is stronger than an admin role

ORY (Kratos, Hydra) exposes a **public API** and an **admin API** on different ports, and the
admin API carries **no authentication of its own** — it is secured by being unreachable. An admin
credential can be phished, committed, logged or reused; **if no such credential exists, none of
those failures is possible.** The cost is an operational contract — *this port is never routed
from the internet* — auditable in one place (the listen address, the firewall) instead of in every
authorization check.

**This departs from Nocturne**, which puts admin behind controllers with authorization inside the
same application (`PlatformAdminBootstrapService`, `IsPlatformAdminToSubjects`). Nocturne's
approach is defensible; ORY's gives a smaller blast radius for a hoster running strangers' data,
which is D1's target.

### 2.3 Design

```
bin/admin.js
  binds ADMIN_BIND (default 127.0.0.1), ADMIN_PORT (default 1338)
  no API_SECRET, no JWT, no shiro — authorization is network reachability
  REFUSES TO START if bound to a non-loopback address unless
    ADMIN_INSECURE_BIND_ACKNOWLEDGED=true is set explicitly
```

It is the **only** component that writes the `tenants` table, and — like the slot reader and
`ns-evaluator` ({DB} §8.6) — it is cross-tenant by construction and **cannot be protected by
RLS**. Its correctness is enforced by code review rather than by the database, which argues for
keeping it minimal.

**Endpoints.** Built (T3.2): tenant create / list / get / suspend / activate / delete, and
**per-tenant export** (`lib/admin/platform-store.js:386` `exportTenant`, a streaming server-side
cursor in one repeatable-read transaction that emits the covered-table list before any row; D1's
requirement, {M} §11 Q6). **There is no import counterpart** (register CAP-02). Export sits on the
platform plane, so **a tenant cannot self-serve an export**; a user-facing promise that they can is
wrong until a tenant-admin route exists. Argued against and not built: quota get/set (nothing
enforces a quota — §6 T3.2). Health reports only what has a producer (slot lag and
`pg_notification_queue_usage()`, the two things {DB} §8.3 and §9.4 say must be alerted on, arrive
with Phase 4).

### 2.4 Schema

Adapted from Nocturne's `TenantEntity` / `TenantMemberEntity`:

```sql
CREATE TABLE tenants (
  id              uuid PRIMARY KEY,
  slug            text NOT NULL UNIQUE,      -- host label: slug.example.org
  display_name    text NOT NULL DEFAULT '',
  is_active       boolean NOT NULL DEFAULT true,   -- inactive => 403, not 404
  created_at      timestamptz NOT NULL DEFAULT now(),
  last_reading_at timestamptz                      -- signal-loss detection; ingest updates it
);

CREATE TABLE tenant_members (
  id            uuid PRIMARY KEY,
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  subject_id    uuid NOT NULL,
  permissions   text[],            -- shiro strings, as today's auth_subjects carries
  label         text,
  last_used_at  timestamptz,
  UNIQUE (tenant_id, subject_id)
);
```

`tenants` is **not** RLS-protected — it is the map used to *resolve* a tenant, read before a tenant
context exists. `tenant_members` is.

**As built in `lib/admin/platform.sql` (T3.2), which differs from the block above:** `slug` has a
`CHECK` (writes only); `tenant_members` has `ENABLE`/`FORCE ROW LEVEL SECURITY` and a policy;
`tenants.id` has no `DEFAULT`. **Owed (T3.0 / `T32-REM`):** `subject_id`'s type is wrong for the
subjects it names — `specs/nsschema/auth_subjects.model.json` records `auth_subjects._id` as
`types:["string"]`, and a 24-character hex ObjectId does not fit `uuid` — so the fix is an `ALTER`
on a shipped table, not an added `REFERENCES`. The table has no configuration, secret or signing
key (D13–D15).

### 2.5 D10 — the tenant slug is a host label

**Globally unique per deployment.** Two independent hosters may both have `alice`, because nothing
joins their tables.

The slug is a *label inside a hostname*, and hosters disagree on where the boundary falls:

| shape | example | slug |
|---|---|---|
| subdomain of a content domain | `foo.user-content.apex.org` | `foo` |
| prefixed label on one domain | `foo-user-content.apex.org` | `foo` |
| path prefix (fallback, {M} §5.2) | `apex.org/foo/api/v1/...` | `foo` |

So **tenant resolution is a configured rule, not a hardcoded "first DNS label"** — a pattern with
exactly one capture group, which covers all three shapes (T3.1).

Constraints on the schema:

1. `slug` stores **only the label**, never the full host. A deployment that moves from `foo.a.org`
   to `foo-a.org` must not rewrite its tenant rows.
2. The label charset is the intersection of DNS and a safe path segment: lowercase alphanumerics
   and `-`, not starting or ending with `-`. Validated on write in `bin/admin.js`, the only writer
   of `tenants`, and re-checked on read by the resolver.

**Deferred:** two hosters sharing one deployment and wanting the same slug — under D10 a
per-deployment uniqueness question.

### 2.6 D11 — devicestatus is a decomposition problem, not a column-selection problem

The question "which of devicestatus's 182 nodes get generated columns" is **retired rather than
answered**, because it assumed the document shape is the thing being stored.

**The direction:** `devicestatus` is decomposed into idiomatic, normalised time series, and *what*
it decomposes into is declared by a registered controller description rather than hardcoded
([controller descriptions](../platform/PROPOSAL-controller-descriptions-2026-09-11.md) §5):

```yaml
documents:
  - collection: devicestatus
    discriminator: {path: loop, test: is-object}   # structural, not the device string
    decomposesTo: [ApsSnapshot, PumpSnapshot, UploaderSnapshot]
```

A known catalogue ships with Nightscout; a controller may publish or correct its own. The
decomposition is **data, not code**, so it does not become another drift-prone list beside the
OpenAPI spec, `indexedFields`, the nsschema model and the `walker` (§3.4).

**What it decides for T2.1:**

- **Emit only `devicestatus`'s `indexedFields`** — `created_at`, `NSCLIENT_ID` and one compound.
  The remaining 179 nodes stay in JSONB.
- **Do not widen the column list to anticipate decomposition.** The normalised series are separate
  relations with their own schemas.
- **Decomposition must sit above the seam, like coercion** (§3.4). The 56-of-166 dropped-path
  finding that motivates it ({M} motivation (a)) is a fidelity problem; fixing it in the multitenant
  backend only would leave single-tenant behind, which D4 forbids.

### 2.7 D12 — what each repository is for

| repository | role |
|---|---|
| **`rag-nightscout-ecosystem-alignment`** | tooling, documentation, evidence, experiments, alignment exercises. Verification harnesses live here (`tools/seam/`, `tools/qc/`, `tools/mt-bench/`), as do all findings |
| **`cgm-remote-monitor`** | **kept pristine.** Shipping code and its tests, nothing else |

- A benchmark, differential oracle, census script or probe belongs **here**, even when it exercises
  code **there**; harnesses `require()` the shipping module by path so the two cannot drift.
- A commit to `cgm-remote-monitor` reads as ordinary upstream work — no scaffolding, no research
  artefacts, no fixtures that exist only to support an experiment.
- Findings are written up **here** and referenced from there, never pasted into code comments.
- `node_modules` is tracked in neither; a manifest plus a lockfile makes a tool reproducible.

### 2.8 D13, D14, D15 — the credential root, and where configuration comes from

**Why.** One deployment API secret, one signing key and tenant separation by inspecting a claim are
properties of *single-tenant* Nightscout, true only because there is one tenant to read the
environment for. In the hosted target, per-tenant settings, plugin credentials and secrets come
from the database, where a tenant owner administers them; the process environment is the
single-tenant bootstrap. That is also why D5's entrypoints are separate: different bootstrapping,
not only different process topology.

**What the built code assumes** (measured 2026-09-15 on `239f8c25`; re-resolved on `crm-seam`
`81a1f6ce`):

| site | assumption |
|---|---|
| `lib/authorization/index.js:169-173` | a matching `api_secret` grants shiro `['*']` (`authorizeAdminSecret` → `env.enclave.isApiKey` → the one secret armed from `process.env` at boot). **No tenant dimension on this path** |
| `lib/server/tenant-middleware.js:139-143` (`tenantClaim`) and the call at `:346` (`enclave: env.enclave`, resolved once at construction) | one install-wide key signs and verifies every tenant's tokens |
| `lib/server/enclave.js:29-30` | the JWT key is read from the **file** `node_modules/.cache/_ns_cache/randomString`, so it is per-*install*, survives `setAPISecret`'s scrub of `process.env.API_SECRET`, and appears in no environment census. Two deployments sharing an install directory share a signing key today |
| `lib/server/enclave.js:54` `setJWTKey` | exists and has **no caller** in `lib/` or `bin/` — dead code or T3.0's injection point |
| `lib/admin/platform.sql` | no settings, secret or plugin configuration; `tenant_members.subject_id` references nothing — the subjects it names are still process-wide, which is BF-25's cause |
| `lib/server/tenant-context.js` (T3.3) | builds the mechanism for per-tenant settings (`deriveEnv`, validated overrides) and takes the overrides as a parameter; nothing supplies them |

**D13 — no deployment secret in multi mode.** The `['*']` grant path becomes unreachable under
`TENANCY_MODE=multi`; `isApiKey` becomes tenant-scoped. Consistent with D7: the platform plane
already needs no credential. A tenant owner administers their site with their own credential,
which is what makes the tenant-admin surface something a tenant can hold. **D13 also reaches
subject access tokens:** `enclave.getSubjectHash` (`enclave.js:71-76`) hashes
`secrets[apiKeySHA1]`, so every subject's token derives from the deployment secret. Executed: with
no API key set it throws a `TypeError`, and the `isApiKeySet()` guard above the call site turns the
throw into silence — every subject loads with no digest, `accessToken` or `accessTokenDigest`, and
the first lookup dereferences `undefined`. So D13 means **re-rooting the subject hash on the
tenant's own credential**.

**D14 — per-tenant signing key.** T3.1 resolves Host → slug → tenant id *before* any credential is
examined, so the tenant is known when a JWT is verified; a token minted for tenant A fails the
signature for tenant B. **D14 closes the signed-JWT vector completely but not BF-25 on its own:**
BF-25's vector is an opaque token in the request **body**, which carries no signature. Closing the
class needs D14 **and** scoping the subject store under RLS. Needs key storage and a rotation
story, which land with the configuration schema. **BF-66**: every JWT is minted with the payload
`{accessToken}` and no `tenant` claim, so under `multi` with the default `requireTokenClaim` the
deployment's own tokens fail its own tenant check (fails safe). T3.0 chooses the payload, so T3.0
fixes it.

**D15 — configuration source diverges by entrypoint.** Saying so is what stops env-sourced
configuration leaking into the hosted path by default.

**Bootstrap and rotation — direction set, evidence owed.** The hosting operator mints a tenant's
initial credential through `bin/admin.js` on the unroutable port, and the tenant owner can rotate
on demand. An IdP binding on the tenant row is in scope as an alternative to a local secret (see
[trusted identity providers](../../10-domain/trusted-identity-providers.md)). The impact of
operator-assigned-then-rotated credentials, and what the alternatives cost, are unmeasured — the
first half of T3.0.

#### T3.0 · Configuration surface and credential root

Queue: `T30-RESEARCH`, `T30-SCHEMA-CRED`, `T30-SCHEMA-CONFIG`, `T30-WIRING`; amends T3.1, T3.2,
T3.3 (`T31-REM`, `T32-REM`, `T33-REM`). Specification:
[tenant-owner configuration surface](tenant-owner-config-surface-2026-09-15.md).

1. **Research** — delivered as the specification above. Findings it rests on:
   - **Nightscout's configuration variables have no common prefix.** There is no `SETTINGS_*`
     family: across `lib/server/env.js`, `lib/settings.js` and `README.md` the string `SETTINGS_`
     occurs once, inside `MONGO_SETTINGS_COLLECTION` (`env.js:215`). The measured union is **247
     names** from four sources; the specification's reconciliation puts the surface at **277**
     including names no regex can see.
   - **Three families are invisible to a `readENV` census**: the eleven API v3 names read straight
     from `process.env` (**BF-46**, one family of which deletes stored documents), `WEBHOOK_*`
     (**BF-48**), and the hosted entrypoints' `ADMIN_*` / `FEED_*`, read through injected readers.
     A census scoped to `lib/` describes the `single` entrypoint only.
   - **Dead names**: `SECURE_HSTS_HEADER_INCLUDESUBDOMAINS` has two spellings and the settings
     dictionary produces the one nothing reads, with four more dead keys (**BF-49**);
     `MONGODB_COLLECTION` is documented and read by nothing (**BF-50**). A tenant-admin UI generated
     from the settings dictionary would offer five settings that do nothing, one a security header.
2. **Schema** — add configuration and credential storage to `lib/admin/platform.sql`: the per-tenant
   root credential and signing key, device/uploader credential tables, and what `subject_id`
   references (`T30-SCHEMA-CRED`, claimable); the per-tenant settings table and human-identity
   columns (`T30-SCHEMA-CONFIG`). The specification's DDL **has never been parsed**, and two of its
   constraints are wrong on paper: a `?|` proto guard that tests top-level keys only while the code
   recurses, and a threshold `CHECK` that a partial override satisfies because SQL `NULL` is not
   `FALSE`. **Do not write human-identity DDL until `T30-ORY-PROOF` resolves.** The amendment must
   also touch `lib/admin/platform-store.js:45` (`PLATFORM_TABLES`, which drives `ensureSchema`'s
   completeness check) and `:51` (`NOT_TENANT_DATA`, or `exportTenant` streams every tenant's
   wrapped credentials).
3. **Wiring** (`T30-WIRING`, which also carries D16's extraction prerequisite) — supply T3.3's
   `deriveEnv` overrides from storage and make `isApiKey`/`verifyJWT` tenant-scoped:

| task | site that must change |
|---|---|
| **T3.1** | the call at `tenant-middleware.js:346` (`enclave: env.enclave`, resolved once at construction) and the file-sourced key at `enclave.js:30`. `tenantClaim` at `:139-143` is the reader, not the site |
| **T3.2** | `platform.sql` (`subject_id` type `ALTER`; configuration, secret, signing key) plus `platform-store.js:45` and `:51` |
| **T3.3** | the frozen list `PER_TENANT_ENV_KEYS` at `tenant-context.js:143`, the copy-loop guard at `:278` (`if (PER_TENANT_ENV_KEYS.includes(key)) continue;`), and the explicit assignments in `deriveEnv` at `:265-300`. (`:137` is the doc comment stating the rejected reasoning) |
| pre-programme | `lib/authorization/index.js:169-173`, from `if (data.api_secret && authorizeAdminSecret(...))` through `const result = { shiros: [admin] };` |

*Blocked by*: nothing for the credential half. *Register entries owned*: **BF-46**, **BF-48**,
**BF-49**, **BF-50**, **BF-66**, and BF-25's subject-store half. The measurements, tests and
isolation evidence of T3.1–T3.3 stand; only their credential assumptions are superseded.

### 2.9 D16, D17 — the auth plane

Research: [the auth plane: Ory Kratos/Hydra against building it ourselves](../../60-research/tenancy/auth-plane-ory-vs-inhouse-2026-09-16.md).
Queue: `T30-AUTH`, `T30-ORY-PROOF`.

#### D16 — three listeners

Adopted whole, including the prerequisite. The argument is asymmetry of regret: merging two
listeners later is a routing change; splitting one later means re-deriving which routes were ever
safe to expose against a codebase that by then depends on them sharing a process. Separation also
decouples the auth question from the data path — a separate listener can be fronted by Ory, by a
native credential, or by nothing but unreachability, without touching the consumer API.

**Three listeners for the whole deployment, not three per tenant.** Tenancy is multiplexed inside
each listener by Host → slug → id (D10) and bound by RLS. This axis is **audience**, orthogonal to
D5's **workload** axis. Nothing in either decision splits per tenant — D2 rejected
database-per-tenant on 47 WiredTiger files and 3.7 MB of RSS per empty tenant, and the auth
research rejects Kratos-per-tenant on the same grounds.

| listener | audience | authn | authz | tenancy |
|---|---|---|---|---|
| `ns-api` + `ns-realtime` (and `single`) | devices, clients, viewers | native per-tenant credential, tokens | shiro | Host → slug → id, RLS |
| `ns-tenant-admin` | the tenant owner | native today; D17 row 2 if it lands | owner role | Host → slug → id, RLS |
| `ns-admin` | the hoster | none, by D7 | none — reachability | cross-tenant by construction |

`ns-evaluator` and `ns-vcpool` accept no inbound connections — neither carries express ({C} §2) —
so they are D5 entrypoints, not D16 listeners.

**Open: is `ns-tenant-admin` its own process, or a second bound socket inside `ns-api`?** D16
decides the boundary (the tenant-owner surface does not share a listening socket with the data
path) and is silent on process topology. A second `listen()` in one process gets the routing
separation and the extraction prerequisite at no extra process; a separate process adds its own
failure domain, bind address and resource ceiling, which is what makes `ns-admin` worth a process
under D7. D7's argument does not transfer automatically, because `ns-tenant-admin` is credentialed
and RLS-scoped where `ns-admin` is neither. Decide before the third listener is built.

**The prerequisite.** `lib/server/tenant-resolver.js` and `tenant-middleware.js` are the one module
for the consumer path; the admin plane deliberately does not use them because it is cross-tenant.
The tenant-owner plane is the first surface that is **per-tenant and not the data path**, so it is
the first real consumer of that extraction, which must exist before the third listener does. It
lands on `T30-WIRING`.

#### D17 — by audience

| audience | decision | status |
|---|---|---|
| devices and uploaders | native per-tenant credential, **never Ory** | **ADOPTED.** Forced by D1 — an uploader cannot run an OAuth flow |
| tenant owners and caregivers | Ory Kratos, one cohort-wide pool, hosted-only | **HELD — direction of travel, not adopted.** Conditional on `T30-ORY-PROOF` |
| third-party apps | Hydra **deferred** | **ADOPTED.** Nothing needs delegated access today; deferring costs nothing |
| platform operator | D7 unchanged | **ADOPTED** |

**Why row 2 is held.** Every Ory claim behind it is read-derived — no Kratos or Hydra instance has
been started — and **a shared identity pool is effectively irreversible once identities exist.**
`T30-ORY-PROOF` (about a day): stand up Kratos 1.x and Hydra 2.x, register two tenants against one
pool, and confirm a session for tenant A cannot be exchanged for a Nightscout token on tenant B —
**with a control**: the same session against A's own host must succeed, or the test only proves
that everything fails.

**The bridge is `nsjwt`, and it is ours under every outcome.** Kratos says who the person is; a
policy says what they may do on this site; Nightscout mints a **per-tenant** token (D14) the data
path already understands. That is `externals/nightscout-roles-gateway`'s design (a working Kratos +
Hydra + Nightscout RBAC gateway, 31 migrations, 2022-era dependencies, one cohort-wide identity pool
plus one Hydra client per site, `joined_groups.subject` as the seam) and its unfinished half.
Letting Hydra issue the token instead would abandon D14 for the human path: OSS Hydra signs with
its own keys and has one issuer.

**What "lean on Ory" buys:** no password hashing, credential recovery, MFA enrolment, session
invalidation or OIDC federation handshake of our own. **What it does not buy:** multi-tenancy, the
authorization model, the token exchange, the device path, or freedom from maintaining the native
path. **Adopting Ory means the auth seam carries two backends permanently** — the same standing
cost D4 imposes on storage, counted as maintenance, not migration.

#### The amendment to D13

One cohort-wide identity pool makes the authentication plane shared infrastructure by
construction: one identity, one session, one login spanning every tenant — which is also the
feature, because a mobile app can log in once and *select* which Nightscout it may reach.

D13 is about **secrets** and stays true: each tenant holds its own root credential. D13 says
nothing about identity, and reading it as "nothing is cohort-wide" would rule out the only workable
topology. So:

> **Credentials are per-tenant. Identity is per-cohort. Authorization is per-tenant.**

**Isolation therefore rests on the authorization layer and on RLS, not on the authn layer.** The
failure mode to design against is a cross-tenant identity bug shipped on the assumption that the
authn plane was isolated. This holds whether or not row 2 lands.

#### Corroboration: Nocturne reached the same split with no Ory

Measured 2026-09-16 against `externals/nocturne@d9e14309` (read, after the decision — corroboration,
not basis):

| | measurement |
|---|---|
| `SubjectEntity` | `: IEntityTimestamped` — **not `ITenantScoped`**, so no RLS policy and no tenant query filter (`NocturneDbContext.cs:137`) |
| likewise | `PasskeyCredentialEntity`, `TotpCredentialEntity`, `SubjectOidcIdentityEntity`, `SubjectRoleEntity`, `RecoveryCodeEntity`, `RefreshTokenEntity`, `OidcProviderEntity` — **none tenant-scoped**, against **57 entities that are** |
| `ix_subjects_access_token_hash` | **UNIQUE, with no tenant column** |
| `TenantMemberEntity` | `TenantId` + `SubjectId`; unique on `(TenantId, SubjectId)` and `(TenantId, Username)` — **the seam** |
| per-tenant authorization | `TenantRoleEntity`, `TenantMemberRoleEntity`, unique on `(TenantId, Slug)` |
| federation | `Controllers/V4/TenantAdmin/OidcProviderAdminController.cs:25,27` is `[Route("api/v4/admin/oidc-providers")]` under `[Authorize(Roles = "platform_admin")]`, and `OidcProviderEntity` is not tenant-scoped — **configured once per deployment by the platform operator**, not per tenant |

Nocturne's identity plane is deployment-scoped, its authorization plane tenant-scoped, joined by a
membership table. It goes further than D13 allows (its access token is deployment-global). It has
no D7 — platform admin sits on the consumer API behind a `platform_admin` role — so on the admin
plane it is what D7 departs from. Agreement between two read designs is not evidence that either
is safe.

### 2.10 What "declared safe" means, and what suspension means

**The declared-safe gate is deliberately not written yet (maintainer, 2026-09-15).** Every tenancy
finding carries the qualifier *"high, within `TENANCY_MODE=multi`, which is not yet declared
safe."* The anchor that qualifier rests on is **reachability**, measurable today:

| mechanism | effect |
|---|---|
| `lib/server/env.js` `mode: readENV('TENANCY_MODE', 'single')` | opt-in; defaults off |
| `tenant-middleware.buildRegistry` | throws unless the storage URI names postgres |
| `lib/server/socket-tenancy.js` | refuses to boot on a path-only rule |
| `lib/server/socket-tenancy.js` | logs `WITHHOLDING` per surface when it does boot |

**`TENANCY_MODE=multi` is developer-only until declared otherwise, and that declaration is the
gate.** Nobody reaches it by upgrading — it takes a deliberate variable, a PostgreSQL deployment,
and ignoring a boot-time error saying alarms are off. `fromEnv()`'s boot message should name what
is outstanding rather than saying "not safe" generically.

**The checklist is deferred on purpose.** {M} §5.2's eight cross-cutting requirements are the basis,
extended by four found since (process-wide `authorization.storage.subjects`; the per-tenant
credential root, D13/D14; process-wide `language`/`levels`, BF-31; per-tenant `ddata`). Roughly 4
of 12 are met; items 4, 5 and 7 — per-tenant plugin instances, fairness/backpressure, quotas — have
not started, and acceptance criteria written for unstarted work get rewritten when it starts.
**Write the gate when 4/5/7 have owners.**

#### Suspension is two verbs

`is_active = false` is a **total blackout**: `tenant-middleware.js:233` answers 403 to every request
— reads, writes, the API and **CGM ingest** — and `tenant-registry.js:25` keeps no cache so it takes
effect immediately. `platform-store.js:321` requires suspension before deletion.

**Decided 2026-09-15:**

| verb | meaning |
|---|---|
| **suspend** | total blackout, as built. Abuse/ToS, and the pre-deletion state the delete gate requires |
| **pause** | **ingest continues; the UI and reads are blocked.** A billing lapse or an owner-requested pause never costs the person their data |

The delete gate requires **suspend**, not pause.

#### The socket gap is a display problem

`is_active` is checked at the Socket.IO handshake and never again. A suspended tenant answers 403 to
everything new while an already-open tab keeps its socket and shows a **live-looking chart that
will never update**.

**Decided: disconnect, and make the page say so — keep the last data visible and plainly marked
stale**, using Nightscout's existing staleness vocabulary (the clock and time-ago going red).
Blanking the screen does not help someone mid-decision; a display that silently looks current is
the failure to design against. A silent disconnect leaves the same frozen chart, so the disconnect
alone does not close this.

---

### 2.11 Deployment metadata: a recommendation, not a decision

Operator-supplied deployment metadata, such as a support contact, is not yet decided. The
recommendation: **two fields with different owners, never merged into one.**

- **A platform-level value is required**, and it must be servable with no tenant binding. A support
  contact is needed exactly when something is broken: an unknown slug, a suspended tenant, a
  database outage, the boot-error page. Those are the cases where a tenant record cannot be read.
- **A tenant-level value takes precedence when present.** Under `single` the one value comes from
  the environment, unchanged (D1). Under `multi`, D15 rules out env-sourced configuration, so the
  platform value is a deployment row and the tenant value is a tenant row.
- **Render both, labelled.** "Ask the person who set up your site" and "ask the company hosting it"
  are different actions, and someone whose glucose data has stopped arriving needs to know which is
  which.
- **A tenant-supplied contact is often a private person's contact details**, for example a parent
  who runs a site for a child. Treat it as tenant-controlled personal data: not on any
  unauthenticated endpoint by default, not in logs, and not in any export that crosses a tenant
  boundary. The platform contact is an organisational address and carries no such constraint.
- It is a low-risk first consumer of the per-tenant configuration table (`T30-SCHEMA-CONFIG`),
  because it is tenant-administrable but not a secret.

Wherever this metadata is rendered (a boot-error page, a suspended-tenant response, a push
notification), the text is user-facing. It must say plainly which party to contact and for what,
and it must not suggest that contacting anyone replaces the person's own care team when the
problem concerns their therapy rather than the software.

## 3. D8 — the query surface

### 3.1 v3 is closed, v1 is open

| | operator surface | where |
|---|---|---|
| **API v3** | **closed — exactly 9**: `eq ne gt gte lt lte in nin re` | `lib/api3/generic/search/input.js:111` |
| **API v1** | **open — pass-through** on `origin/master` (15.0.8) | `lib/server/query.js:157` |

On 15.0.8, v1's `create()` builds the filter with `traverse` type-coercion and injects a date
constraint, then returns it to the driver with no operator allowlist — {M} §6.5's ReDoS/full-scan
finding stated as a translation problem: **you cannot write a complete SQL translation of an open
pass-through.** v3 is smaller because someone wrote the list down, which makes it the contract to
implement first.

`origin/dev` now carries a v1 operator allowlist (BF-04, #8743, merged 2026-09-18, not released):
`$expr` and the pipeline parameter are refused, `$type` is allowed (so the seam's filter AST owes a
`$type` node, or v1 narrows by one operator when the seam lands). The unauthenticated `$regex` cost
defect, BF-72, is open on 15.0.8 and dev; see the register.

### 3.2 Strategy

1. **Implement v3's nine operators natively.** Closed, enumerable, testable exhaustively.
2. **Bound v1 with evidence.** The corpus census (T2.4) says which operators clients send; support
   that set and reject the rest with a documented 400. This is also the §6.5 security fix.
3. **Keep the shape backwards compatible.** Same URLs, parameter encoding and defaults
   (`ENTRIES_DEFAULT_COUNT`, the two-day `deltaAgo` in `query.js`). A client that sends an operator
   in the evidence set must not notice.

### 3.3 Libraries

| package | version | use here |
|---|---|---|
| **`mingo`** | 7.2.4 | **The differential-test oracle.** Evaluates Mongo queries against in-memory objects, so a translation is checked by running the same query both ways — the technique PR #8733 used with 636 randomised fixtures. **Limit:** mingo applies JavaScript truthiness, MongoDB does not (it reads `{$exists: NaN}` as true — T0.5), and its regex engine is V8 where MongoDB's is PCRE2 (T2.3) |
| `sift` | 17.1.3 | a second oracle if a `mingo` disagreement needs adjudicating |
| `mongo-query-to-postgres-jsonb` | 0.2.19 | candidate for the v1 long tail, **not** for the v3 nine |
| FerretDB | `ghcr.io/ferretdb/ferretdb` | **Rejected for the multitenant target**: connects as a single role and cannot do per-transaction RLS binding, which is D3's point. Possibly a migration bridge or single-tenant-on-Postgres option |

**Write the nine operators by hand, and use `mingo` as the oracle.**

### 3.4 Type coercion belongs above the seam, not in mongoose

On 15.0.8, v1 coerces query values through a **hand-maintained per-collection allowlist**
(`walker`), not from any schema:

| collection | `walker` | source |
|---|---|---|
| entries | 7 fields, all `parseInt` | `lib/server/entries.js:186` |
| treatments | `insulin carbs glucose` → `parseInt`; `notes eventType enteredBy` → regex | `lib/server/treatments.js:260` |
| profile | `{}` — empty | `lib/server/profile.js:97` |
| **devicestatus, activity, food** | **none** | — |

Run against `lib/server/query.js` (15.0.8 behaviour):

```
treatments insulin $gte=1.5                  {"insulin":{"$gte":1}}      <- truncated
treatments carbs   $gte=7.5                  {"carbs":{"$gte":7}}        <- truncated
entries    sgv     $gte=120                  {"sgv":{"$gte":120}}        <- correct
entries    delta   $gte=1.5                  {"delta":{"$gte":"1.5"}}    <- still a string
devicestatus uploader.battery $lt=50         {"uploader.battery":{"$lt":"50"}}  <- still a string
```

1. **Over-coercion gives wrong answers.** `insulin` and `carbs` are `parseInt` although
   `specs/nsschema/treatments.model.json` declares both `number`. **A query for boluses ≥ 1.5 U
   returns boluses of 1.0 U.**
2. **Under-coercion gives silently empty answers.** A field with no `walker` entry stays a string,
   and MongoDB orders BSON types before values, so a numeric field never matches a string bound;
   every numeric filter on `devicestatus` and `activity` matches nothing and returns 200.
3. **The `walker` is a fourth drift-prone list** beside the OpenAPI spec, `indexedFields` and the
   nsschema model ({M} §7.6).

T0.5 (`bf/coercion`, #8737, merged, not released) replaces the walker with a schema-derived table.

**Why not mongoose.** It would fix (1) and (2) in the wrong place: mongoose is MongoDB-only and D4
makes two backends permanent, so Postgres would need its own coercion and the drift problem moves up
a level. The job — "HTTP query string → typed value" — is backend-independent and must happen
*before* the repository interface is called; otherwise the interface's contract is "accepts strings
or numbers, the backend decides". `specs/nsschema/` already distinguishes the broken case
(`treatments.insulin: ['null','number']` against `entries.noise: ['integer']`), and five emitters
already consume those models.

> **A coercion-table emitter is the sixth emitter, feeding one table used by the query parser above
> the seam, for both backends.** Mongoose keeps the role {M} §7.6 scoped it to — write-path
> validation *inside the MongoDB adapter*.

**Compatibility:** fixing (2) is user-visible — queries that returned nothing start returning rows.
It belongs in release notes.

---

## 4. D4 — what "MongoDB stays" costs the seam

The seam carries **two mature backends permanently**, not one plus a migration path:

1. **The interface is the intersection, not Mongo's shape.** If it exposes driver semantics it is
   not a seam ({M} §2.5's complaint about `mongo-storage.js`).
2. **Both backends stay in CI permanently.** Every storage test runs twice.
3. **`specs/generated/mongoose/` is the single-tenant validation path** — mongoose scoped to the
   MongoDB adapter, schemas generated from `specs/` ({M} §7.6). It is for write-path validation, not
   query coercion (§3.4).

---

## 5. D9 — base branch

**Base the work on `chore/nightscout-modernization`.** At the decision (2026-09-14) it was
`0a4109f6`, 495 commits / 573 files / +107,596 −14,872 ahead of `origin/dev` `a8888f0d`. It closes
{M} §3.1's shared-alarm-state blocker (commit `9e869662`) and carries the Playwright suite and the
Node 22/24 floor; rebasing that many commits underneath this work later would be worse than
starting on top of it.

**Measured 2026-09-24:** `official/chore/nightscout-modernization` is `b1bdaca0`, 51 behind / 498
ahead of `official/dev` `153e5658` (`git rev-list --left-right --count official/dev...official/chore/nightscout-modernization`);
its last merge of `dev` is `e3b22034` (2026-09-21). The seam chain has not been refreshed onto it
(`SEAM-REFRESH`): `seam/t1-2-storage-interface` `81a1f6ce` is 68 behind / 50 ahead of `b1bdaca0`
with 19 conflicting paths (`git merge-tree --write-tree --name-only official/chore/nightscout-modernization seam/t1-2-storage-interface`)
— three of them add/add supersessions from BF-04's upstream allowlist, which wins; sixteen content
conflicts across the v1 API and server storage modules, cost unmeasured. Against `official/dev`
`153e5658` the seam is 116 behind / 545 ahead with 36 conflicting paths (the same two commands with
`official/dev`). **Open, recorded in `SEAM-REFRESH`:** whether the seam should refresh onto the
modernization branch or onto `dev`, now that `dev` carries the allowlist the seam duplicates. D9
stands until the maintainer decides otherwise.

**Caveat:** #8605 (the modernization integration PR) has zero human reviews across its production
lines, all by one author. That blocks *shipping* the stack, not *developing* against it. This plan
does not constitute a review of it.

**Refreshing the seam, when it is done.** The chain is 16 linear branches, which is the nearest
thing to an irreversible operation in this programme.

- Before starting, record every seam tip in a committed file:
  `git for-each-ref --format='%(refname:short) %(objectname)' refs/heads/seam/`. Rollback is
  `git reset --hard <recorded tip>` per branch. `ORIG_HEAD` does not survive a multi-branch rebase,
  and reflogs expire.
- Decide per-branch rebase or squash before starting. A squash discards the per-branch history that
  explains why each conflict was resolved the way it was. If squashing, tag the pre-squash tips
  first.
- `lib/server/query.js` carries two fixes for the same `$exists` operand defect: the seam's
  `coerceExistsArguments()` (`e0564167`) and `dev`'s schema-driven `lib/server/query-coercion`
  (#8737, BF-32). The schema-driven one covers more operators. Whether it covers the ordering the
  seam's version handles has **not been measured**, so measure it before dropping either. BF-04's
  operator allowlist sits in the same output path, so a careless resolution can re-open a security
  fix.
- The conflict count in `SEAM-REFRESH` is measured against the tip only. A per-branch rebase may
  meet conflicts the tip does not show.

---

## 6. Tasks

Ordered by dependency. **Every task states what "done" means as a command that passes.**

Conventions: branch from `origin/chore/nightscout-modernization` (D9); `NODE_ENV=test`.

**Suite conventions, measured on `origin/dev` `a8888f0d` (register BF-53):**

- `npm run test:unit` is a brace list resolving to **44** files; `npm run test:integration` to
  **89**. There are **159** `tests/*.test.js`; the union of the two scripts is **107**, leaving
  **52 run by neither** (queue `DOC-TESTSCRIPTS`).
- `npm run test:unit` is **not** database-free: with no `mongod` reachable it fails 6 tests
  (`verifyauth` ×4, `API_SECRET` ×2) on pristine `dev`.
- **A green `test:unit` is not evidence for a fix whose test is among the 52** — including
  `tests/boluscalc.quickpick.test.js` (BF-35), `tests/receiveddata.merge.test.js` (BF-36),
  `tests/browser-utils.queryparms.test.js` (BF-37) and `tests/dataloader.test.js`. **Use
  `npm test`**, the whole tree, which is what CI runs (`main.yml` → `test-ci` → `./tests/*.test.js`).
  `npm test -- tests/one.test.js` does **not** run one file: npm appends the argument to the
  script's own glob.
- Integration needs a database; each worktree names its own port in `my.test.env` (27030-27034,
  27018, 27117), so concurrent runs do not collide.

### Phase 0 — ships to every existing operator, no tenancy decision required

**T0.1 · The two quadratic treatment scans — PR #8733, merged 2026-09-17** (queue `P0-T01`). Not
released.

**T0.2 · `/api/v1/entries` untyped read — DONE; merged in `bf/cache`, PR #8740** (queue `P0-B`).
`lib/api/entries/index.js:459-500`. `?count=10` cost **0.83 ms** without `find[type]` and **0.02 ms**
with it — a 42× overcharge for a byte-identical response, because `ctx.cache.getData('entries')`
(`lib/server/cache.js:73-76`) deep-clones the whole 48-hour array before slicing. Fix: slice first,
then clone the slice (documents handed out are still clones). Measured **0.837 ms → 0.025 ms**, from
42.0× the typed read to 0.7×.
*Done*: `node --expose-gc tools/mt-bench/apitier.js read` shows the untyped branch within 2× of the
typed one at `count=10`; full suite passes. *Evidence*: {R} §12.2.

**T0.3 · `cache.getData`'s five call sites — GATE NOT MET; merged in `bf/cache`, PR #8740.**
`lib/server/cache.js:81`, `lib/data/dataloader.js:195/332/489`, `lib/api/entries/index.js:490`.
`insertData` returns `getData()` — a JSON round-trip over the whole retained array, per datatype,
per cycle: **4.08 ms**, 65 % of the post-#8733 load cycle. Result: the three cache calls went
**3.747 ms → 2.657 ms** against a target of < 1 ms. **98 % of the remainder is `devicestatus`**,
whose caller rewrites fields in place and whose result lives in `ddata` for the life of the process;
taking it needs proof that nothing in the plugin tier writes to a device-status document (a field
silently vanishing from every cached API read is the failure mode, and a grep is not that proof).
`dataloader.js:204`'s `mills` write was found dead (all three branches below it read `element.date`)
and removed, with a test that goes red if it returns.
*Done*: `node --expose-gc tools/mt-bench/apitier.js cycle` shows clone cost < 1 ms; full suite
passes; a test pins the mutation semantics.
**The gate cannot be re-run:** the 3.747 → 2.657 ms workload is recorded in no file here
(`tools/mt-bench/cycle-fix.js` measures `ddata`/`calcdelta`; the cache tests are correctness tests).
The queue records `P0-B` with an explicit no-gate marker. **Work owed: write the harness and
re-measure**, not a harness that reproduces the threshold. *Evidence*: {R} §12.3.

**T0.4 · Start and interval jitter in `nightscout-connect` — DONE on `fix/connect-timer-jitter`
`c1cce2a`; connector PR #68, merged into connector `dev` as `3f73288` on 2026-09-22** (queue `P0-F`;
the merged head `635cc9f` unifies this jitter with LibreLinkUp's own; suite 283 pass / 0 fail).
Released in `nightscout-connect` `0.1.0` (2026-09-24, queue `P0-TAG`), which `cgm-remote-monitor`
`dev` pins exactly (#8762, merged, not released). The measurements below were taken on `b77e5bb` (the commit `chore/nightscout-modernization` pins): 19
new tests, suite 135 pass / 0 fail, every part of the change reverted in turn and caught by at least
one test. Harness `tools/mt-bench/vcherd.js`
(EXP-MT-048b), local mock only — no vendor endpoint contacted, no credentials used.
- **The phase-lock is at start and on the unaligned interval.** All four vendor drivers already put
  an 18-second random window into the timestamp they align to: at 400 actors over 700 s, later cycles
  arrive as a band ~15 s wide peaking at **30 requests/s**; the first cycle is **400 in one second**.
  The unjittered moments are the **start** and the **unaligned interval** (taken when a source
  declines to align — when the vendor has nothing new and the pool is already stepping together).
  Both are now windows on the cycle machine: `CONNECT_START_JITTER_MS` and
  `CONNECT_INTERVAL_JITTER_MS`. At 400 actors, 60 s of start jitter takes the busiest second
  **400 → 15**.
- **Both windows default to `0`** — one connector is not a herd, and a self-hosted site would only
  delay its own first reading. So the jitter is a knob the **hosted vendor pool** sets, not a fix
  every operator receives (§7, EXP-MT-051).
- **Start jitter de-phases the first cycle only**: from cycle 2 alignment re-anchors every actor to
  the data's shared boundary, so the pool re-locks and the driver's 18-second window bounds the peak.
  Over 700 s at 400 actors the busiest second falls **400 → 34**, all of it the start. A flatter
  profile means widening the drivers' alignment window (four vendor files), which needs EXP-MT-051.
- **What it does ship to every operator: BF-34.** `lib/backoff.js` merged options as
  `{ ...config, ...defaults }`, so every caller value was discarded. All five sources ask for a
  2.5-minute retry interval (the `nightscout` source 10 s for its frame retry) and each got the
  256 ms default — **586× faster than configured**, with `use_random_slot` forced `false` so a pool
  that fails together retries in lockstep. With the upstream refusing authentication, 100 actors
  delivered the same 800 requests across **3 s** before and **67 s** after. The precedence fix ships
  with `max_interval_ms` and two cadence-relative ceilings, because `exponent_ceiling` caps the
  exponent, not the delay (uncapped, attempt 20 is five years); the six-interval cycle cap is a
  judgement, flagged as one in the code and the register.
*Lands on operators with* 15.0.9 (queue `RT-0`): `dev` pins `0.1.0` (queue `P0-PIN`), while
`master` (15.0.8) pins `v0.0.13`. **Release-note it**: a vendor outage will look slower to recover.
*Evidence*: {R} §6.2, register BF-08 and BF-34, `tools/mt-bench/results/exp-mt-048b-*.json`.

**T0.5 · Schema-driven query type coercion — DONE; merged in `bf/coercion`, PR #8737, 2026-09-18**
(queue `P0-D`). Not released.
Emit a coercion table from `specs/nsschema/*.model.json` (sixth emitter, beside `mongoose_emit.py`
et al.) and drive `lib/server/query.js`'s walker from it. **158 coercions over 5 collections replace
13 hand-written entries.** Fixes the §3.4 cases: BF-02 and BF-11; BF-03 for `devicestatus` and
`profile` (`food` never reaches `query.js`; `activity`'s model has no numeric field). BF-12 does not
reproduce (`entries.js` coerces `rssi`, which is in the model).
- **BF-32, found and fixed here:** a walker that coerced every leaf including operator operands
  turned `find[sgv][$regex]=^1` into `{$regex: NaN}`, a server error, and `find[sgv][$exists]=true`
  into `{$exists: NaN}` — which MongoDB reads as **true** (measured against seven `mongod`
  instances, 3.6.8 and 7.0.43: numeric truthiness is `value != 0`), so that case returned the right
  documents by accident. `mingo` applies JavaScript truthiness and disagrees — a recorded limit on
  the D8 oracle.
- **BF-40 fixed by the same PR:** `find[...][$exists]=false` returned documents that **have** the
  field on 15.0.8, on every field, because MongoDB reads the string `"false"` as truthy. #8737 reads
  `$exists` operands as booleans (`BOOLEAN_OPERANDS` / `readBooleanOperand` in
  `lib/server/query.js`).
- **The count path composes:** BF-01's fix (in `bf/reads`, #8738) delegates to each collection's
  `query_for`, which names its collection, so coercion reaches `query.js` on the count path.
  Measured at the level of the constructed filter with two control arms; no live-database assertion
  that a numeric filter on `count/devicestatus/where` returns rows exists yet.
- **Residual, measured inert:** `lib/authorization/storage.js`'s `queryOpts` is the last caller of
  `query.js` that names no collection, so it keeps the legacy `{date: parseInt, sgv: parseInt}`;
  auth documents carry neither field, and `noDateFilter:true` is honoured identically across twelve
  probe runs.
*Done*: the §3.4 cases produce correctly-typed output; a test asserts the emitted table matches the
model for every collection; the full suite passes. **Release-note the behaviour change** — queries
that returned nothing start returning rows.

### Phase 1 — the seam

**T1.1 · Define the repository interface — DONE 2026-09-14.** See {S} and
`reports/storage-seam/t1-1-call-site-classification.tsv` (scripts to re-derive it are committed
beside it).
- **85 storage call sites** (a grep excluding `.find(` to dodge `Array.find` also drops every
  `col.find(filter)`, the commonest read).
- **~55 need conversion**: 15 are already interface consumers (`api3/generic/*`,
  `mongoCachedCollection`) and 14 are the interface and its Mongo adapter. **API v3 is three-quarters
  of a seam that already exists** — `MongoCollection` is a real interface with a decorator over it.
- **A third write path:** `lib/server/websocket.js` implements CRUD over Socket.IO
  (`dbAdd`/`dbUpdate`/`dbUpdateUnset`/`dbRemove`) with **its own dedup logic**, parallel to v1's and
  v3's. Convert it last; dedup unification is a separate behaviour change.
- **Classification:** 39 `fits`, 27 `needs-escape-hatch`, 19 `must-change` — four root causes, 9
  sites being "`query_for` returns a Mongo filter document".
- **Do the filter AST first.** With v3's nine operators as the seam's filter language, T0.5's table
  has somewhere to apply, T2.3 is done by construction, and **T2.4's allowlist falls out
  structurally — an AST that cannot express an unlisted operator is the allowlist.**
- **Transaction scope:** `store.withTenant` plus a `requireTenant` assertion at the `MongoCollection`
  delegations ({S} §9.1; `SINGLE_TENANT` is a `Symbol`). Inert until T3.1; exists so T2.5 has the
  scope RLS requires.

**T1.2 · Convert the storage call sites to the interface, MongoDB only — DONE except one site.**
**Zero behaviour change.** *Done*: all test files pass unchanged; no file outside `lib/storage/` and
the adapter imports the `mongodb` driver. Suite **2207 passing, 1 pending, 0 failing** (baseline
2150; the increase is new tests). **No existing test expectation changed**; one test double gained a
`project()` method because projection now rides on the cursor.
Converted: `activity` (4), `treatments` (9), `food` + `devicestatus` (9), `profile` (7 of 8) +
`entries` (4 of 4), `authorization/storage` (4), `aggregate` (1), `api/entries` count (1), and
`websocket.js`. **Remaining:** `profile.list_query` — `GET /profiles/` accepted `$expr`, which is a
query-surface decision (D8/T2.4); #8743 now refuses `$expr` on dev, and T2.4's census found no client
sending it.
Defects found by the conversion:
1. **`fromMongo` silently dropped a native `RegExp`** (`Object.keys(/x/i)` is `[]`), so
   `find[eventType]=/Bolus/i` returned **every** treatment. Fixed with an `options` field on the `re`
   node — flags off the pattern, costing nothing against `RE_MAX_LEN`, and mapping to PostgreSQL's
   `~*`.
2. **The count endpoint's date bound** (`aggregate.js` calling `find_options(opts)` with one argument)
   — count and list now route through the same `query_for` and bound identically. Affected
   treatments and devicestatus too.
3. **`acknowledged` would have vanished from four delete responses**; three modules re-synthesised
   `{acknowledged: true}`, which would misreport an unacknowledged write. The interface passes the
   driver's value through.
4. **No non-upserting replace existed.** The socket path's profile dedup must not insert; an upsert
   would resurrect a profile deleted between lookup and write. Closed with `replaceFiltered`.
**Method:** two differentials re-run on every change — `tools/seam/roundtrip.js` (4000 generated
`query.js`-shaped filters, mingo as oracle; zero mismatches) and `tools/seam/validate.js` (5000
randomised ASTs, mingo vs live PostgreSQL, per operator; zero for nine of ten operators, `re` per
T2.3). Non-vacuity: removing the RegExp fix gives 240 mismatches (several reading `0 vs 98`,
`69 vs 333`); removing `nin`'s `IS NULL` guard gives 588; `exists` on the generated column gives 188,
each charged to that operator alone.

**T1.3 · Parametrise the storage-touching tests by backend — DONE 2026-09-14.**
*Done*: storage-touching files run against a backend selected by env and pass. **2207 passing,
1 pending, 0 failing**, no `lib/` file touched. Census: **21 files**, two of them grep false
positives (`tests/runtime-policy.test.js` names `'../storage/mongo-storage'` in a spawned child's
module blocklist; `tests/boot-sequence-integration.test.js` asserts `ctx.store` is `undefined` after
a failed boot). The other 19, with the class recorded in a comment above each suite:

| class | count | disposition |
|---|---:|---|
| backend-agnostic — storage only for fixtures | 7 | `describeForEachBackend` |
| MongoDB's own **by nature** — driver semantics, pooling, retry, URI grammar, AWS auth | 6 | `describeMongoOnly` (permanent) |
| MongoDB's own **by mechanism** — intent agnostic, proof by wire-command counting | 6 | held: needs a per-backend I/O observer (follow-up task) |

**The visibility contract is the deliverable.** A backend that cannot run produces *pending* tests,
never absent ones: an unrecognised name is a hard error at require time (`NS_TEST_BACKEND=postgre`
exits 1 with `Unknown NS_TEST_BACKEND "postgre"`), and a known-but-unavailable backend uses
`describe.skip`, which still registers every `it`.

| run | passing | pending | **total** | failing |
|---|---:|---:|---:|---|
| default (`mongodb`) | 2207 | 1 | **2208** | 0 |
| `NS_TEST_BACKEND=postgres` | 2045 | 163 | **2208** | 0 |

Under `postgres`, the 2045 passing are the unconverted suite against MongoDB as before; the harness
covers the enumerated storage-touching files only.

**T2.0 · Storage backend lookup at boot — DONE 2026-09-14.** `lib/server/bootevent.js` hardcoded
`require('../storage/mongo-storage')` under a `//TODO ... add a lookup`. `lib/server/storage-backends.js`
now selects by the **scheme in the connection URI**, not a new env var (a separate
`NS_STORAGE_BACKEND` could disagree with the URI and surface as a driver parse error). A
`postgres://` URI reports `Unsupported storage backend`, names the scheme and lists the schemes the
build has (reverting the lookup makes the boot test fail with `Unable to connect to Mongo /
MONGODB_URI seems invalid`). A URI with no scheme, or none, still resolves to `mongodb`, keeping
`mongo-storage`'s existing message. The `require()` calls stay literal inside thunks, enforced by a
test — `require(spec)` over a variable would silently retire `tests/runtime-policy.test.js`, which
treats the literal as its sentinel. A second test asserts no driver loads until a backend is selected.
8 tests added; **2215 passing, 1 pending, 0 failing**. `storageClear` routing and per-run namespaces
were completed in T2.5.

### Phase 2 — Postgres behind the seam

**T2.1 · Postgres DDL emitter — DONE 2026-09-14.** A sixth emitter in `tools/nsschema/emit/`
alongside `mongoose_emit.py`, `zod_emit.py`, `jsonschema_emit.py`, `pyarrow_emit.py`,
`fieldref_emit.py`. Input `specs/nsschema/*.model.json` (entries 31 fields, treatments 58,
devicestatus 17 top-level / 182 nodes, profile 14 / 72). Output: `CREATE TABLE` with `tenant_id uuid`
leading, JSONB body, generated columns for `indexedFields` (41 indexes, {M} §6.7), each index
tenant-prefixed; `devicestatus` per D11.
*Done*: emitted DDL loads clean; the `tools/mt-bench/pgfeed/pgfeed.js` RLS arm passes against the
generated schema.

**T2.1a · Two things T4.2 needs from the DDL emitter** (not expressible today):
1. **A global, non-tenant-leading index.** Every emitted index is tenant-leading — right for every
   tenant-facing query, wrong for the two components {DB} §8.6 says are never tenant-bound. T4.2's
   `describeBound()` reports the index's absence and reads the leading key from `pg_get_indexdef`
   (seven emitted indexes mention `date`; none bounds the poll).
2. **An insertion-ordered column on `entries`.** The bounded window predicate is over the
   **uploader's clock**. A slow device writes rows a bounded sweep cannot see (so `fullSweepEveryMs`
   is a detection latency); a fast one drags its tenant's watermark past real time, after which that
   tenant goes quiet until the clock catches up. Not fixable at the poll layer: clamping re-reports
   the same row forever, and dropping a reading is not something an alarm path may do. T4.2 counts it.

**T2.2 · The missing collection models — DONE 2026-09-14.** `specs/nsschema/` carries a model for all
**ten** collections, with `provenance` on every node (`measured` · `declared` · `declared+measured` ·
`code` · `structural`). `auth_subjects` / `auth_roles` are read out of `lib/authorization/storage.js`.
**`settings.census.json` is not a census of the `settings` collection**: it captures
`GET /api/v1/status.json` (its twelve fields are the `info` object `lib/api/status.js` builds). That
evidence is modelled as `status.model.json`; the `settings` collection, which nothing in
`cgm-remote-monitor` writes, gets a code-derived open-bodied model recording the collision. OpenAPI
assertions are not merged into the measured models (an assertion written under the census naming
convention would be indistinguishable from evidence); `tools/nsschema/jsread.py` parses the server's
literal shape declarations and refuses what it cannot parse, sharing `model.Node` and `to_dict` so
all 48 existing artefacts stayed byte-identical. **Drift check proved:** seven mutations of a copied
tree each exit 1; the unmodified control exits 0; `--cross-check` shows `externals/work/crm-seam` and
`externals/cgm-remote-monitor-official` declare identical field sets.
Findings: **BF-17** (a subject edit persists the API access token in plaintext); **BF-16**'s second
half (form encoding stringifies `position`, so eleven or more quick picks sort lexicographically on
the shipping path); `NSCLIENT_ID` is client-supplied, never generated or validated, and is the sole
match key for websocket duplicate detection when present.

**T2.3 · v3's nine operators in SQL, with `mingo` as oracle — DONE; the three `re` defects fixed** in
`lib/storage/filter.js` (`c1218d50` on `seam/t1-2-storage-interface`; one existing expectation
changed — the regex SQL spelling test asserted a match against the generated column, which was the
first defect). Report: [the `re` validation](../../60-research/tenancy/seam-filter-re-operator-validation-2026-09-14.md).
*Done*: ≥500 randomised fixtures per operator, zero disagreements with `mingo`; `re` bounded (pattern
guard + timeout).
`tools/seam/validate.js` is per-operator (a focus operator round-robins; blame is isolated to one node;
the run fails if any operator lands under 500). Over 5000 fixtures — 981 to 1052 per operator — the
eight non-regex operators and `exists` report zero disagreements. Before the fix `re` reported 54
mismatches and 95 SQL errors in three defects: ARE newline modes are not Mongo's `m`/`s`; jsonb renders
non-strings as text a pattern then matches; `re` against a numeric generated column raised
`operator does not exist` (a 500 on 1.9 % of fixtures).
**For `re`, mingo agreement does not imply backend agreement.** `tools/qc/re-arms.js` (21 constructs,
three arms) finds three where **mongod differs from PostgreSQL and mingo agrees with PostgreSQL**, so
closing T2.3 fully needs the mongod arm. `RE_MAX_LEN` is a length bound, not a work bound. On
`re-arms.js`'s catastrophic constructs and fixtures, mongod 7 and PostgreSQL 16 were flat and only the
JavaScript arm backtracked — **but that does not generalise**: BF-72 (reproduced 2026-09-21, `mongod
7.0.43`) shows mongod backtracking for minutes of CPU on nested-quantifier patterns evaluated against a
repetitive string field. A length bound protects neither backend; the PostgreSQL arm has not been
measured against BF-72's shape.

**T2.4 · v1 operator census, then an allowlist — CENSUS DONE 2026-09-14; the allowlist shipped
separately as BF-04, PR #8743, merged 2026-09-18** (queue `P0-K`). Not released.
*Done*: census committed with counts per operator; allowlist enforced; the rejected set documented.
Census (`tools/qc/v1_operator_census.py`, `reports/v1-query-census/`): 157 literal `find[field][$op]`
occurrences across **14 client projects**:

| operator | occurrences | projects | in the AST |
|---|---:|---:|---|
| `gte` | 55 | 13 | yes |
| `eq` | 36 | 10 | yes |
| `lte` | 32 | 10 | yes |
| `gt` | 22 | 5 | yes |
| `lt` | 5 | 3 | yes |
| `ne` | 4 | 3 | yes |
| `exists` | 3 | 2 | yes |

Plus `$or` (2) and `$and` (1), both from one project. **Every operator any client sends is expressible
in the filter AST**; 21 distinct fields appear, led by `created_at` (57), `date` (30) and `eventType`
(13). Nothing sends `$where`, `$expr`, `$elemMatch` or `$near`. **Limit:** this measures client
*source*, not what a deployment receives — a lower bound on the field set and a strong signal on the
operator set.

**T2.5 · `entries` end-to-end on Postgres + RLS — DONE 2026-09-15.** EXP-MT-037. Connect as a
**`NOSUPERUSER NOBYPASSRLS`** role — RLS is silently not enforced for superusers.
*Done*: an unbound connection returns **0** rows (and **4** on the same connection once bound);
`EXPLAIN` shows `Index Cond: (tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)`
on `entries_tenant_date`, over 12,000 rows across 3 tenants; `tests/entries-both-backends.test.js`,
16 HTTP tests over API v1 and v3 entries, passes **16/16 on MongoDB and 16/16 on PostgreSQL**.
Suite **2351 passing, 1 pending, 0 failing**; under `NS_TEST_BACKEND=postgres` **2172 passing, 180
pending, 0 failing** — total conserved at 2352.
- **"T1.3's suites pass on PostgreSQL" is not achievable at entries-only scope**: all seven boot
  through `bootevent`, which builds all six v1 modules and both auth collections. A suite now declares
  the collections it needs, and a backend lacking one skips it with the collection named.
- **`is_local` is asserted at the pool:** a connection handed back must carry no binding (otherwise a
  transaction-pooling pgbouncer serves one tenant's request on another's binding). A pool of one plus
  `store.pooledTenantBinding()` assert it; breaking `set_config(…, is_local => true)` to `false` fails
  it.
- **The `Index Cond` criterion is insensitive to `columnTypes`**, so the test also asserts the emitted
  predicate is `"date" >= $1`.
- `lib/server/aggregate.js` now passes the storage accessor, so `/count/:storage/where` works on
  PostgreSQL.
- **jsonb's cross-type sort order is not BSON's.** Every sort this path issues is on a single-typed
  field; the limit is documented at the code.
- `storageClear` routes through the harness adapter; per-run namespaces arrive as
  `STORAGE_NAMESPACE` (a schema on PostgreSQL, a database on MongoDB, with the configured database as
  a prefix). No stray databases, schemas or roles after a run. `tests/lib/production-safety.js` still
  reads the database name from the URI and is not namespace-aware.
- **Vendoring:** the emitted DDL is vendored into `lib/storage/postgres/generated/`, and
  `make schema-vendor-drift` compares the two byte for byte; a run that checked nothing says so.
*Not done*: every collection but `entries`; `insertMany`, `updateMany` and `replaceFiltered` throw by
name (`$unset` has no decided representation); no TLS, no pgbouncer in the suite, no write-throughput
or working-set measurement; `bulkUpsert` issues one statement per operation (one transaction).

**T2.6 · The remaining nine collections on PostgreSQL — DEFINED, UNSCHEDULED.** `treatments`,
`devicestatus`, `profile`, `food`, `activity`, `settings` and the `auth_*` collections, and so
full-server boot on PostgreSQL.
- **Three open register entries become live the day it starts:** **BF-19** (`ORDER BY` reads the
  generated column and orders differently from the document; client-reachable via v3 `?sort=`),
  **BF-21** (`bulkUpsert` ignores the caller's mode), **BF-22** (a dotted field stores two different
  documents). BF-19's and BF-21's prescribed fixes are read-derived and have never been run. Land them
  first.
- **Needs CAP-02**: no importer and no Mongo→PostgreSQL loader exists; the transform is unsettled
  ([hosted migration plan](../../40-migration/mongodb-to-postgres-hosted-2026-09-15.md) §4.3).
*Done*: not written, deliberately, until the work has an owner. *Blocked by*: BF-19/BF-21/BF-22.

### Phase 3 — tenancy

**T3.1 · Tenant resolution middleware — DONE-EXCEPT** (the install-wide signing key, superseded by
D14; remainder `T31-REM`; also owns **BF-66**). Host → slug → tenant id, path-prefix fallback, token
claim verified against the resolved tenant. {M} §5.2 item 1.
The rule is a **configured regular expression with exactly one capture group** (D10). Not configurable,
each for a reason in the code: **exactly one group** (with two, which capture is the slug is a guess at
the isolation boundary); **no flags** (`g` and `y` carry `lastIndex` across calls; hosts are lowercased
instead of allowing `i`); **the slug charset is re-checked on read** (a loose pattern such as
`^(.*)\.apex\.org$` is the realistic mistake).
Departures from {M} §5.2, all deliberate:
1. **The host comes from `req.headers.host`, not `req.hostname`.** `req.hostname` prefers
   `X-Forwarded-Host` whenever trust-proxy says yes, and `compileTrust('')`, Nightscout's default,
   always says yes — any client could choose its tenant with a header. Naming another header
   (`TENANT_HOST_HEADER`) refuses to start unless `TRUST_PROXY` is configured. (**BF-24**, open:
   `TRUST_PROXY=false` currently lets a non-`host` tenant header through unchecked.)
2. **A presented credential with no tenant claim is refused by default**, because
   `lib/authorization/storage.js` keeps subjects in one process-wide array. A knob, not a constant.
   Anonymous requests pass.
3. **The claim carries the tenant *id*, not the slug** — an id cannot be reassigned, and it is what RLS
   compares.
It **binds** (`tenantScope.withTenant`) rather than opening a transaction (`store.withTenant` would
hold a PostgreSQL transaction across response streaming). **Single-tenant is not a degraded mode**:
`fromEnv` returns `null` unless `TENANCY_MODE=multi`, and `setTenancyMode('multi')` is its last
action. 18 guards broken one at a time, each failing its test. (A header-source test is only
non-vacuous if the test app's `trust proxy` differs from express's default; otherwise both headers
agree and either answer passes.)
*Not done*: no end-to-end multi-tenant boot before T3.2's DDL existed; `fromEnv` warns at boot, and
the README states, that `multi` is not safe.

**T3.2 · `bin/admin.js` — DONE-EXCEPT** (no per-tenant configuration, secret or signing key;
`subject_id` type; remainder `T32-REM`, §2.4, §2.8). Per §2.3, including the refuse-to-start guard.
- **The guard refuses for the right reason:** refuse `0.0.0.0:P`, then bind `P` by hand (nothing was
  opened); bind the same address through `listen()` with the acknowledgement set and serve a request,
  one variable apart; a control squats a port and asserts `EADDRINUSE` is not the guard's error; an
  ordering test runs a broken `STORAGE_URI` on `0.0.0.0` (fails on bind) and on loopback (fails on the
  database).
- Classification uses `net.BlockList`; a **name is resolved and every resolved address must be
  loopback** (also catching `127.1`, which glibc accepts and `net.isIP` does not); an empty
  `ADMIN_BIND` is refused, because `listen(port, '')` binds everything.
- **Quota get/set — not built.** Nothing enforces a quota; an operator who can set a cap will believe
  it exists. It wants an enforcement point first.
- **Health reports only what has a producer.** Replication slots report `{status: "absent", reason: …}`
  naming Phase 4, never `lag_bytes: 0`; the test takes its expectation from an independent query
  against `pg_replication_slots`.
- **Delete refuses while any tenant-scoped rows exist**, because document tables carry `tenant_id` with
  no foreign key to `tenants` (deleting the row would orphan data). Four gates: slug echoed in the body,
  tenant already suspended, no rows left, state unchanged since read.
- **The admin store refuses to run as `SUPERUSER`/`BYPASSRLS`**: its per-tenant counts are computed by
  RLS, and that count decides whether a `DELETE` proceeds.
- **Grants between the two roles:** `bin/admin.js` creates and owns `tenants`; a hoster running the
  application as a different role got `permission denied` as a 503 on every request. The registry now
  turns `insufficient_privilege` and `undefined_table` into sentences naming the `GRANT` and the admin
  plane, and passes other errors through.
*Not done*: two-role deployments untested beyond the grant message; logical-slot lag has no producer
until Phase 4; the admin plane is PostgreSQL-only, with no export for single-tenant MongoDB;
**reserved labels** (`www`, `api`, `admin`) and `xn--` prefixes are flagged, not enforced.

**T3.3 · `ctxFor(tenantId)` — DONE-EXCEPT** (shares `env.enclave`, superseded by D13/D14; remainder
`T33-REM`). The `Map<tenantId, ctx>` substrate for the single-process path — a cache with a graceful
fallback; an evicted context rebuilds to something **deep-equal** to what was dropped.
- **Isolation is proved structurally:** tests crawl every object reachable from each context and assert
  the intersection is empty (a shallow copy separates every top-level field while sharing the alarm
  configuration). Per tenant: `settings`, `extendedSettings`, `err`, `notifies`. Shared deliberately,
  with a test: the enclave (to change under T3.0), the tenancy rule, the store, the scalar deployment
  config.
- **`config()` is not how a tenant gets an environment** — it reads the process environment. Per-tenant
  environments are derived from a built one.
- **Cache bound:** T3.1 refuses an unknown slug before a tenant id exists, so a Host header cannot
  allocate (measured through the build counter); T3.3 owns the heap — 10,000 registered tenants on
  legitimate traffic exceed {R}'s ceiling. `DERIVED_CONTEXT_KEYS` is four entries and a test fails if
  it grows, naming T3.4 (caching ack/snooze would let eviction un-snooze an alarm).
- Tests pin two failure modes that would ship silently: `ctx.env` is set by nothing, so a substrate that
  depended on it returned `null` in the real server while self-built test bases passed; an unset
  `TENANT_CONTEXT_MAX` arrives as `null`, and `parseInt` gave `NaN`.
- **`env` is one object per process** (`lib/server/env.js:13`); a second `config()` overwrote the first
  in place, and because `setAPISecret` deletes `API_SECRET` from `process.env` once read, it **disarmed
  the first context's enclave** — measured, fixed in T3.3.
- **The MongoDB connection is a process singleton** (`lib/storage/mongo-storage.js:7`, `:111`):
  measured, tenant B asking for its own namespace was handed tenant A's. `init()` now refuses a second
  target. This does not block `ctxFor`: under D3/D4 multi-tenant never uses MongoDB
  (`buildRegistry` throws unless the URI names postgres), and under PostgreSQL the store is
  deliberately shared, isolated by per-transaction `set_config`; a per-tenant store would be a
  per-tenant connection pool bypassing the binding RLS reads.
*Not done*: **`language` and `levels.translate` are process-wide** — `language.set('de')` on the shared
instance changes what every tenant reads (**BF-31**, fixed in `bf/alarms`, merged #8739, not
released; a live single-tenant defect too). `language.set` records a code only; the catalogue is read
once at boot, so `levels.translate` does not move and alarm text is not affected — what leaks is
`moment`'s global locale, which reaches the assistant's answers. Authorization subjects remain one
process-wide array; tenant settings have no source (T3.0); `ddata`/`cache`/`plugins`/`dataloader` are
absent, with the alarm-slice split as precondition. Shared-state audit:
[tenant shared state](../../60-research/tenancy/tenant-shared-state-audit-2026-09-15.md),
`tools/qc/tenant-shared-state.js` — of 70 files with module-level mutable state, six are
server-resident and written after load; the other 40 are browser files loaded once per page.

**T3.4 · Ack/snooze isolation — REGRESSION TEST DONE; the storage move is T4.4a (DONE).**
On the modernization branch `alarms` lives inside `init(env, ctx)` (`9e869662`, "Own notification
alarm state per service and clear it on teardown"); on `origin/dev` it is still module-scope at
`lib/notifications.js:15`. Measured with three separate processes, same level and group:

| process | alarms emitted | `lastAckTime` |
|---|---:|---|
| acknowledges, then evaluates | **0** | set |
| a sibling process | **1** | 0 |
| a restart of the acknowledging process | **1** | 0 |

An acknowledgement was invisible to a sibling and did not survive a restart. The four constraints
T4.4a was held to: PostgreSQL needs a real `(tenant, level, group)` table; the interface offers no
compare-and-set ({S} §9: no cross-operation atomicity promise on both backends, since many
self-hosters run a standalone `mongod`); the alarm path is synchronous end to end
(`bootevent.js:330-332`), and an alarm that does not fire is the worst outcome this software has; the
key is the tenant. Redis is rejected as the home: {M} §7.6 scopes keyv to ephemeral state and `single`
must never need Redis to keep a snooze.
**Deliverable:** `tests/notification-tenant-isolation.test.js`, three cases, one per route to somebody
else's alarm. Hoisting `alarms` to module scope fails three tests (*"a shared alarm map makes one
person's snooze silence a different person's hypo alarm"*); hoisting `requests` fails two, while the
pre-existing lifecycle test passes through that break.

**T3.5 · Tenant socket rooms and tenant-bound socket authorization — DONE 2026-09-15.**
`alarmSocket.js` emitted to the whole namespace with no room (five sites). Under single tenancy "every
socket on `/alarm`" and "every socket of the one person this deployment serves" are the same set, so
every single-tenant branch is left as it was. `/storage` is covered too.
**A handshake resolves by host only.** A Socket.IO handshake URL is the engine path (`/socket.io/`),
and that path is a client option, so honouring it would let a caller pick its tenant. **A
`TENANT_PATH_PATTERN`-only deployment refuses to start** (upheld by the maintainer, 2026-09-15):
refusing to boot beats HTTP working while alarms silently never arrive. Path-prefix deployments remain
possible when a reverse proxy derives the tenant from its own location match and asserts it in the
configured `TENANT_HOST_HEADER` (both polling and websocket upgrade requests carry headers), so the
tenant is asserted by the proxy rather than chosen by the caller. **Do not document that configuration
for operators until BF-24 is fixed** — BF-24 defeats exactly that guard.
T3.1's rejection rule is **one function** called by the HTTP middleware and both socket entry points. A
refusal on `subscribe` **disconnects**, because the socket already joined the tenant's alarm room.

> **Under `TENANCY_MODE=multi`, `/alarm`'s and `/`'s producers run outside any tenant scope, so their
> emissions are withheld rather than broadcast. Turning on `multi` today turns live updates and alarms
> off.** Failing closed is right; it is logged per surface, pinned by a named test, and stated in plain
> language in the README with a note to talk to a care team. Under `single`, nothing is withheld.

*Not done*: rooms fix who *hears* a result, not whose state it mutates (the ack path; see T4.4a). A
tenant suspended mid-session is not re-checked after the handshake (§2.10).

### Phase 4 — the feed

**T4.1 · Slot reader — DONE 2026-09-15.** Emits `NOTIFY` itself, never from a trigger ({DB} §9.4). 321
lines in `lib/feed/` plus `bin/feed.js` at 88 — small because its isolation is review-only ({DB} §8.6).
- **Durability:** reader stopped, 200 rows written across two tenants (the slot pinned 234.5 KB of
  WAL), reader returned → **200/200 delivered**, coalesced into 2 notifications, **0 on re-consume**.
  Peek → notify → advance: the slot is not acknowledged until the batch's notifications commit.
- **Decoupling**, a consumer wedged idle-in-transaction, 200 inserts per arm:

| | writes | per-insert p50 | notification queue |
|---|---|---|---|
| **NOTIFY from the reader** | 200 in 79 ms | 0.228 ms | 0.000000% → **0.000000%** |
| `AFTER INSERT` trigger | 200 in 187 ms | 0.677 ms | 0.000000% → **0.019073%** |

  The same writes rolled back moved the gauge not at all. *Not reproduced*: the queue filling (PG 16
  has no `max_notify_queue_pages`); the coupling is measured, the blocking cited from §9.4.
- **Payload** (a deviation from {DB} §9.3, for review): no document and no row identifier, ~127 bytes.
  A consumer told only "tenant T changed" reads under its own tenant binding, so **RLS re-verifies the
  routing decision this privileged component made**, and a misrouting bug leaks nothing across the
  queue. The WAL carries no document for a DELETE anyway. Cost: one indexed read per notification,
  ~6 ms/s per consumer at 33 changes/s; nothing on the alarm path, which is the slot.
- **Slot lifecycle:** created idempotently; dropped only by `bin/feed.js --drop-slot`, never on
  shutdown. Abandoned, it pins WAL at ~3.25 GB/day at 33 rows/s until the disk fills and **ingest
  dies**; `max_slot_wal_keep_size` caps it by invalidating the slot instead (T4.2 covers a broken
  feed). Dropping a slot needs the `REPLICATION` attribute; as the application role it fails silently
  and leaks one slot per run until `max_replication_slots` is exhausted.
*Not done*: the durable hand-off into `ns-evaluator` (T4.4) — **the end-to-end alarm path is not yet
durable past the slot.**

**T4.2 · Bounded aggregate poll — DONE 2026-09-15.** The backstop when the slot reader is dropped,
wedged, partitioned or not deployed.
**As specified in {DB} §8.4 the sweep is O(registered tenants)** — a nested loop with one index descent
per watermark row, ~1.4 µs each; that run varied neither axis. Reproduced with its own query and index
configuration:

| registered tenants | 100 | 400 | 1600 | 3200 |
|---|---:|---:|---:|---:|
| sweep p50, writing set held at 100 | 0.696 ms | 0.979 ms | 2.909 ms | 5.236 ms |

At 10,000 it would be ~15 ms. **With a global index no emitted schema contains** (T2.1a), the same
corpora are flat (0.806 / 0.731 / 0.761 / 0.865 ms across 32×), and the bound is **rows written since
the last sweep**: ~0.57 ms fixed plus ~0.8 µs per row.
- **The window anchors to the last successful sweep**, from a durable row, never a constant (a poller
  down an hour resuming on a ten-minute window would skip fifty minutes). Past `maxLookbackMs` it
  escalates to a full sweep; a missing heartbeat does the same, closing {DB} §8.5's cold-start case.
- **The sweep reports and never acknowledges.** The consumer advances the watermark with the value the
  sweep observed, under `GREATEST()` — a crash re-reports, and a late acknowledgement cannot move a
  watermark backwards.
- **The observable is an age, not an error**; `tenants_seen` beside `tenants_reported` separates
  "nothing was due" from "I can see nothing".
- The rows-touched assertion reads rows *examined* (`Actual Rows` is post-filter, so a sequential scan
  reported ten).
*Not done*: no entrypoint and no wiring — the handler contract is T4.4's. Only `entries` is swept.

**T4.3 · `ns-realtime`** (queue `T43`, not started) — `LISTEN` per served tenant, on a direct
connection **not through pgbouncer** ({DB} §10.3: transaction-mode pooling accepts `LISTEN` and
silently delivers nothing).

**T4.4 · `ns-evaluator`** (queue `T44`, not started) — the per-tenant evaluation loop. Ack state is
durable (T4.4a), and the conditional upsert serialises concurrent acks in the database, so hash
partitioning is no longer needed for the guard's correctness. **Build it with no resident `ddata`**
(§7b: 32.7 KB and 1.94 ms per tenant per evaluation against 852 KB and 27.5 ms for all of `ddata`,
emitting the identical alarm). The slice is transient — materialise, evaluate, discard — and every
field is "newest *n* of a type within a time bound". The loop must not get wrong:
`treatmentnotify.js:64-75` snoozes every URGENT for 10 min after any treatment; `profiles` can withhold
one via `boluswizardpreview.highSnoozedByIOB`; only the **newest** `devicestatus` is needed. Open:
whether a batching or replaying evaluator may own its clock (§7a item 7).

**T4.4a · Durable ack/snooze state — DONE 2026-09-15.** `lib/storage/ack-store.js` +
`lib/storage/postgres/alarm-ack.sql` (hand-authored, outside `postgres/generated/`, because here the
row is the record).
- **The conditional upsert** replaces the compare-and-set {S} §9 declines to promise:
  `ON CONFLICT … DO UPDATE … WHERE standing.ack_time + standing.silence_ms <= EXCLUDED.ack_time`, with
  `rowCount` as the branch — `ack`'s own guard exactly. **Eight concurrent calls apply one and refuse
  seven**; without the `WHERE`, all eight apply. `tenant_id` comes from `current_setting` (what RLS
  reads), not from a caller: an unbound write hits `NOT NULL`, a misbound one `WITH CHECK`.
- **The synchronous alarm path is unchanged** (no `async`/`await` in `lib/notifications.js`). The
  table is read at an awaited boot step before the `data-loaded` handler (restart survival) and by a
  fire-and-forget refresh after `data-processed` (a sibling's ack). Cost: **a sibling's ack lands one
  cycle late, so an alarm may fire once more than it had to**; holding an alarm while storage answers
  is never an option.
- `requireTenant` throws synchronously, so it is caught inside `recordAck` (otherwise it abandons the
  rest of `process()`, other groups' alarms included). The write is **detached** from the caller's
  transaction, which has already committed and released a connection that may now be bound to another
  tenant.

| arm | T3.4 | T4.4a |
|---|---:|---:|
| acknowledges, then evaluates | 0 | **0** |
| a sibling process | 1 | **0** |
| a restart of the acknowledging process | 1 | **0** |
| *control*: sibling with the durable read removed | — | **1** |
| *control*: a different tenant's sibling | — | **1** |

- Six assertions in `tests/admin-tenants.test.js` changed: T3.2's `tenantScopedTables` discovers
  tables by `tenant_id` column, and `alarm_ack` is tenant-scoped with no FK to `tenants`, so the delete
  gate applies to it. **Open for T3.2's owner:** the export manifest now carries ack rows.
- **MongoDB keeps the in-memory path**, so a self-hoster's behaviour is unchanged; restart survival
  would be worth having there too and is not delivered.
- Under `multi` the server's own cycle runs unbound, so the first ack logs a named marker.

---

## 7. What is still unmeasured, and which task it lands on

| gap | lands on | why it matters |
|---|---|---|
| **No TLS or auth in any database measurement** | T2.5/T2.6 | Both add CPU to the per-operation term the cost model rests on; `ns-api` has the least headroom (110 ms/s of 300) |
| **Write performance** | T2.6 | Write *correctness* is measured ([write path](../../60-research/tenancy/seam-write-path-2026-09-15.md): 23 agree, 4 differ, 0 vacuous — BF-21, BF-22, BF-23); no write-performance figures |
| **Working set past cache size** | T2.6 | {DB} §7's 400-tenant run is where cache pressure starts |
| pgbouncer + `set_config(is_local)` | — | **Measured**: [pgbouncer and the D3 binding](../../60-research/tenancy/pgbouncer-tenant-binding-2026-09-15.md) — isolation holds in session and transaction pooling, proven on a shared backend pid |
| **Active fraction (15 %)** is an assumption | — | Drives options A and B far harder than C; a real hoster's figure would sharpen the model |
| **Vendor rate limits** (EXP-MT-051) | — | Needs real credentials; the 9,700-account figure is a ceiling. `CONNECT_START_JITTER_MS` exists (T0.4), but the window to set it is exactly this unmeasured number |
| **Reconnect storms, `UNLISTEN` churn** | T4.3 | The interesting realtime case |
| **Per-tenant plugin-registry memory** | `T33-REM` | Decides between the two fixes for the `language` half of the `ctx` hazard (§7a) |
| **No standing gate that the two backends agree on `bulkUpsert` mode** | `BFQ-21` | Today they agree only because `entries`, the one collection with a PostgreSQL schema, asks for the mode PostgreSQL hard-codes (register BF-21). The gate needed: parse every `bulkUpsert` call through its closing parenthesis (a line `grep` misses options on the continuation line). Fail if a collection with a PostgreSQL schema asks for a mode the adapter does not implement, or if any call passes no options. Break-it: flip `entries.js:168` to `replace` and see it fail |
| **Whether per-tenant alarm thresholds are tenant-overridable or hoster-pinned** | `T30-RESEARCH`, maintainer | `T44` cannot build a per-tenant evaluation loop without the answer. A hoster pinning thresholds limits what a tenant can be alerted about, so this is a safety policy question, not an engineering one |

## 7a. What stands between here and alarms being ON under `multi`

**The most safety-relevant section of this plan.** Under `TENANCY_MODE=multi` the alarm and
live-update producers run outside any tenant scope, so their emissions are withheld (T3.5). Turning
multi on today turns alarms off. Failing closed is right; staying closed indefinitely is not.
Queue: `A7A-GATE` and the items below.

| # | what | status |
|---|---|---|
| 1 | **Durable ack/snooze keyed by tenant** — without it every snooze fails open and the alarm re-fires forever | **DONE** — T4.4a, with two control arms |
| 2 | **A per-tenant evaluation loop** inside `withTenant`, so an emission has a room | **not started** (T4.4); sized by §7b |
| 3 | **A per-tenant error boundary** — `serverInit`/`initRequests`/`process` are unguarded, so in a plain loop one tenant throwing means every later tenant is never evaluated | **not started** (`A7A-3`) |
| 4 | **A health signal for a silent per-tenant outage** — the per-plugin `try/catch` turns bad data into an alarm outage nobody is told about | **not started** (`A7A-4`) |
| 5 | **BF-31** — one assistant request re-points `moment`'s global locale for the whole process | **not a gate item.** A shared-state defect, not an alarm-text one: `language.set` records a code only and the catalogue is read once at boot, so `levels.translate` does not move. Fixed in `bf/alarms`, merged #8739, not released |
| 6 | **BF-29** — an unknown `ENABLE` entry silently disabled an alarm plugin | **partial, not credit.** It now warns and names the plugin it thinks was meant (six file-name mismatches); merged #8739, not released. This removes the silence; it does not make per-tenant arming trustworthy |
| 7 | **The clock question** — snooze is measured in data time, ack in wall time; `sbx.time` is hardcoded `Date.now()` and `lastEntry` drops entries ahead of it. The same clock has a single-tenant safety consequence today: once the wall clock passes a future-dated reading's timestamp, `lastEntry` returns it as current, so an uploader clock running ahead delays the stale-data alarm by about the size of the skew (register **BF-95**, open; **BF-44** is one shipping source of forward skew). A reading still ahead of the clock does not silence the alarm, because `lastEntry` skips it (**BF-41**, closed 2026-09-23 as not reproducing) | **open** (`A7A-7`); T4.4a chose wall time for ack |

**Score: 1 of the 5 gate items (1–4, 7) complete.** `bin/` holds only `admin.js` and `feed.js` — there
is no `ns-evaluator` and no `ns-realtime` entrypoint, so two of D5's four hosted entrypoints do not
exist. Items 5 and 6, with BF-28 (`insulinage`'s urgent alarm could never fire), are single-tenant
register fixes that are also prerequisites for trusting alarm text and arming per tenant; none is credit
toward turning alarms on. See [BF-28/29/31 alarm delivery](../../60-research/remedial/bf28-29-31-alarm-delivery-2026-09-15.md).

### The `ctx` hazard is three mechanisms, not one

Measured 2026-09-15 on `crm-seam` `81a1f6ce`:

| object | what it is | so the problem is… | and the fix is… |
|---|---|---|---|
| **`ctx.language`** | `lib/language.js` is `module.exports = init` — a **factory** | **capture**: a second call makes a second object; a plugin holding the first never sees it | re-point plugins at the per-evaluation object |
| **`ctx.levels`** | `lib/levels.js:52` is `module.exports = levels`, an **object literal** — a require-cache **singleton** | **not capture**: there is no second object | make it stateless or give it per-tenant state |
| **`ctx.moment`** | `moment-timezone`, no factory | **not capture**, as `levels` | — |

**`levels` is unshareable because of one mutation:** `lib/server/bootevent.js:212` does
`ctx.levels.translate = ctx.language.translate` (browser twin at `lib/client/index.js:241`). Running
boot per tenant means **the last tenant to boot sets level names process-wide**. Only two files require
`levels` directly (`bootevent.js:211`, `lib/client/index.js:12`); every other consumer goes through
`ctx.levels` / `sbx.levels`. `lib/sandbox.js:55-57` already re-points `sbx.levels`, `sbx.language` and
`sbx.translate` from `ctx` on every `serverInit`, so a plugin reading `sbx.*` is per-evaluation.
Census over `lib/plugins/*.js`: 22 files touch these objects, 21 capture at init, `ar2.js` is mixed,
and `treatmentnotify.js` is 0-capture / 9-`sbx` — the one already doing it right, and one of the three
able to withhold an alarm (§7b).

**Two ways to fix the `language` half.** A captured `translate` is not frozen: it reads its
language instance's catalogue at call time. Only *which instance* it reads is fixed at init. So:

1. **A per-tenant plugin registry.** `lib/plugins/index.js` is a factory
   (`require('../plugins')(ctx)`), so one registry per tenant gives each tenant's plugins a closure
   over that tenant's own language instance. No plugin source file changes. Its cost is per-tenant
   registry memory, which is **unmeasured**: §7b measured the per-evaluation slice, and that
   figure does not bound registry residency. Measure it before choosing (`T33-REM`).
2. **Move the 21 capturing plugins to `sbx.*` reads.** This is the fallback if the registry is too
   expensive.

For `levels`, the smaller fix is to make it **stateless** (`toDisplay(level, translate)`), rather
than turn it into a factory. A function with no stored state cannot be re-pointed wrongly, and a
factory still admits the boot-time mutation. For `moment`, do not attempt a per-tenant instance:
`moment-timezone` has no factory, so a tenant's locale has to be passed at each call.

> **Safety caveat.** `lib/levels.js` and `lib/client/index.js` are single-tenant shipping code — the
> alarm-level rendering path every self-hoster runs. A multitenancy-motivated refactor that changes
> **what an alarm level is called** on an existing deployment is a real risk, especially for
> non-English operators. **Any such change needs a single-tenant non-regression arm with
> `TENANCY_MODE` unset, in at least one non-English locale.**

**Item 7's plumbing is small:** `lib/sandbox.js:45` `serverInit(env, ctx)` hardcodes
`sbx.time = Date.now()` at `:50`, while `:85` `clientInit(ctx, time, data)` takes `time` as a parameter
(`:91`). The work is to give `serverInit` that parameter. **Data-time versus wall-time for snooze** is a
policy question and remains undecided.

**Nothing here may be marked done by inference.** Alarms go back on when a test shows tenant A's alarm
reaching A and not B, through the real producer path, with a snooze that survives a restart and a
process change.

## 7b. The per-tenant evaluator is cheap, and the split is by depth

Measured 2026-09-15 by two independent methods — bottom-up from `checkNotifications` and top-down from
a two-tenant spike. Reports: [alarm-critical slice](../../60-research/tenancy/alarm-critical-slice-2026-09-15.md),
[ns-evaluator spike](../../60-research/tenancy/ns-evaluator-spike-2026-09-15.md).

**32.7 KB and 1.94 ms per tenant per evaluation.** Whole `ddata` on a realistic fixture (576 SGVs, 600
treatments, 576 devicestatus, 1 profile) is **852.1 KB**, and one evaluation of `bootevent.js:327-333`
costs **27.5 ms p50**. Reduced to a window taken from the alarm code's own constants, the same
evaluation costs **1.94 ms p50 / 2.14 ms p95** over **33,475 bytes** and **emits the identical alarm**
— 26× less memory, 14× less CPU; at a 30 % event-loop budget ~155 evaluations/s/process.

**{R} §12.5's field split is the wrong axis.** By knockout, **9 of 19 fields are alarm-critical and
carry 92.4 % of the bytes**; one field (`cals`, 98 B) is display-only. The real split is by **depth**:
newest *n* of each type within a time bound. {R} §12.5's size estimate (50.6 KB) holds within 1.5×.
Consequence: the slice is transient and made of a handful of indexed queries (`dataloader.js:360,:416`
already issue two as `count: 1`); **`ns-evaluator` needs no resident `ddata`**, which strengthens {R}
§12.6's option C and takes residency tiering off the alarm critical path.

**Three dependencies that can withhold an alarm:**

- `treatmentnotify.js:64-75` snoozes all URGENT alarms for 10 min after any treatment: same 48 mg/dl
  reading — a treatment 25 min ago gives an `ar2` URGENT low; 4 min ago gives nothing.
- `profiles`, via `boluswizardpreview.highSnoozedByIOB` — knock out the profile and the snooze vanishes,
  so the high fires.
- `devicestatus` (478 KB), because `iob.js` prefers device-reported IOB — but only its newest document
  is needed.

The top-down spike reported a field split with raw `treatments` as display-only; that is wrong
(`treatmentnotify` withholds on treatments) and the spike's corpus armed 6 of 17 alarm producers. The
bottom-up result is the one to use.

**{R} §2's "the plugin tier is small and flat — 0.61 ms p50" does not hold for the full alarm set:** it
is **27.5 ms**, ~74 % `cob.setProperties` and 12 % `openaps.setProperties`; `checkNotifications` itself
is ~1 %. Unmeasured: whether `cob.setProperties` is quadratic in treatments.

**Measurement hazards found:** `settings.enable` matches `plugin.name` (`bwp`, `cage`, `iage`, `sage`,
`bage`), not the file name, and nothing warned about an unknown entry, so alarm plugins measured inert
(BF-29). `slice(-0)` returns the whole array, so a depth probe starting at 0 reported a tail of 0 for
every field until the result was checked.

## 8. How to read a number from this programme

Successive passes each found a term the previous one missed — the load cycle measured 0.03 ms, then
9.5, 6.27 and 8.77 ms as the fixture defect, `cache.insertData` and the database were found. Two of the
most decision-relevant findings arrived as side effects: the file-descriptor `fassert()` at 50 tenant
databases, and `LISTEN` silently returning nothing through pgbouncer. Every figure carries a scope limit
in its source document. **The ordering of options has been stable across every pass; the absolute
numbers have not. Quote the ordering.**
