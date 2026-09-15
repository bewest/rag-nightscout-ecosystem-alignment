# Multitenancy execution plan: decisions, tasks, and the context each one needs

Date: 2026-09-14. Status: draft for maintainer discussion.
**This is the working document.** The evidence lives in {M}, {R} and {DB}; the component
design in {C}. This says what is decided, what is next, and carries enough context per task
that work can be picked up without re-reading the evidence chain.

| ref | document |
|---|---|
| **{M}** | [Nightscout multitenancy: evidence and options](nightscout-multitenancy-discussion-2026-09-09.md) |
| **{C}** | [Deployable components](nightscout-deployable-components-2026-09-14.md) |
| **{R}** | [What sets K](../60-research/multitenancy-k-and-residency-2026-09-14.md) |
| **{DB}** | [A real database in the loop](../60-research/exp-mt-026-database-in-the-loop-2026-09-14.md) |
| **{S}** | [T1.1 — the storage seam: interface and call-site classification](nightscout-storage-seam-interface-2026-09-14.md) |

---

## 1. Decisions

Settled. Each carries the evidence that settled it, so a later reader can tell a decision from
a preference.

| # | Decision | Basis |
|---|---|---|
| **D1** | **Bulk Nightscout-as-a-service hosting is the design target**; families, clinics and communities are configurations of the same system. **Self-hosted single-tenant stays first-class permanently**, on data-rights and mission grounds | maintainer, {M} §11 |
| **D2** | **Shared logical storage with a tenant discriminator** — *not* database-per-tenant. Database-per-tenant costs 47 WiredTiger files and ~3.7 MB of non-evictable `mongod` RSS **per tenant holding zero documents**, and fatal-asserts on file descriptors; the shared shape is 104 files total at 400 tenants, flat | {DB} §4, §7 |
| **D3** | **PostgreSQL + RLS for the multitenant service.** Index locality no longer separates the engines — the deciding property is that a forgotten filter returns **0 rows** under RLS and **every tenant's rows** under a discriminator | {DB} §7.1, §8.2 |
| **D4** | **MongoDB is permanent for the single-tenant target**, not a deprecated path. Existing self-hosters keep their databases | **maintainer, this session** |
| **D5** | **Four hosted entrypoints over one core** — `api` (stateless), `evaluator` (change-driven), `realtime` (fan-out), `vcpool` — plus `single` unchanged | {C} §2, {DB} §6 |
| **D6** | **Change feed = replication slot (spine) + `NOTIFY` (latency) + bounded aggregate poll (backstop)**, with `NOTIFY` emitted **by the slot reader, never by a trigger** | {DB} §8.5, §9.4 |
| **D7** | **The platform-admin plane gets its own entrypoint on its own network interface**, ORY-style, unauthenticated-by-network rather than credentialed | **maintainer, this session** — §2 |
| **D8** | **API v3's closed operator set is the query contract; v1 is bounded by corpus evidence** | **maintainer, this session** — §3 |
| **D9** | **Base the work on `chore/nightscout-modernization`**, not `dev` | **maintainer, this session** — §5 |
| **D10** | **Tenant `slug` is globally unique per deployment, and is a *host label*** — the resolver maps Host → slug by a configured rule, so both `foo.user-content.apex.org` and `foo-user-content.apex.org` name tenant `foo` | **maintainer, 2026-09-14 (second session)** — §2.5 |
| **D11** | **`devicestatus` gets almost no generated columns.** The body stays JSONB, and the real answer to its 182 nodes is *decomposition into normalised time series driven by registered controller descriptions*, not a wider column list | **maintainer, 2026-09-14 (second session)** — §2.6 |
| **D12** | **`rag-nightscout-ecosystem-alignment` carries the tooling, documentation and alignment exercises; `cgm-remote-monitor` stays pristine.** This repository is the quality-control system for that one | **maintainer, 2026-09-14 (second session)** — §2.7 |

## 2. D7 — the admin plane

### 2.1 Two privilege planes that get conflated

Nocturne separates these and the distinction is worth taking:

| plane | who | examples | where it lives |
|---|---|---|---|
| **tenant admin** | a person administering *their own* site | settings, subjects, roles, API secrets, their own export | **consumer interface**, authenticated, RLS-scoped — Nocturne's `Controllers/V4/TenantAdmin/*` |
| **platform admin** | the hoster | create/suspend/delete tenants, quota, provisioning, cross-tenant export | **separate entrypoint** — this decision |

**Only the platform plane moves.** Tenant admin is an ordinary authenticated consumer request
and must stay where RLS can bind it.

### 2.2 The ORY pattern, and why it is stronger than an admin role

ORY (Kratos, Hydra) exposes a **public API** and an **admin API** on different ports, and the
admin API carries **no authentication of its own** — it is secured by being unreachable.

That looks careless and is the opposite. An admin credential is a thing that can be phished,
committed to a repo, logged, or reused; **if no such credential exists, none of those failures
is possible.** The cost is a hard operational contract: *this port is never routed from the
internet*. That contract is auditable in one place (the listen address, the firewall) instead
of being a property of every authorization check.

**This is a deliberate departure from Nocturne**, which puts admin behind controllers with
authorization inside the same application (`PlatformAdminBootstrapService`,
`IsPlatformAdminToSubjects`). Nocturne's approach is defensible; ORY's gives a smaller blast
radius for a hoster running strangers' data, which is D1's target.

### 2.3 Design

```
bin/admin.js
  binds ADMIN_BIND (default 127.0.0.1), ADMIN_PORT (default 1338)
  no API_SECRET, no JWT, no shiro — authorization is network reachability
  REFUSES TO START if bound to a non-loopback address unless
    ADMIN_INSECURE_BIND_ACKNOWLEDGED=true is set explicitly
```

It is the **only** component that writes the `tenants` table, and — like the slot reader and
`ns-evaluator` ({DB} §8.6) — it is cross-tenant by construction and therefore **cannot be
protected by RLS**. It joins the small set of privileged components whose correctness is
enforced by code review rather than by the database, which is an argument for keeping it
minimal.

**Endpoints (proposed, to be argued):** tenant create / list / get / suspend / activate /
delete; per-tenant export (D1's confirmed requirement, {M} §11 Q6); quota get/set; a health
endpoint reporting slot lag and `pg_notification_queue_usage()` — the two things {DB} §8.3 and
§9.4 say must be alerted on.

### 2.4 Schema

Adapted from Nocturne's `TenantEntity` / `TenantMemberEntity`, which are already in production
shape:

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

`tenants` is **not** RLS-protected — it is the map used to *resolve* a tenant, so it is read
before a tenant context exists. `tenant_members` is.

~~**Open, needs a decision before Task A5**~~ — **settled as D10, see §2.5.**

### 2.5 D10 — the tenant slug is a host label

**Globally unique per deployment.** A hoster coordinates names inside their own deployment;
two independent hosters may both have `alice`, because nothing joins their tables.

**The part that is not obvious, and that the schema must not foreclose:** the slug is a *label
inside a hostname*, and hosters will not agree on where the boundary falls.

| shape | example | slug |
|---|---|---|
| subdomain of a content domain | `foo.user-content.apex.org` | `foo` |
| prefixed label on one domain | `foo-user-content.apex.org` | `foo` |
| path prefix (fallback, {M} §5.2) | `apex.org/foo/api/v1/...` | `foo` |

So **tenant resolution is a configured rule, not a hardcoded "first DNS label"**, and T3.1 owns
it. The rule needs to be expressible per deployment — a pattern with one capture group is
sufficient for all three shapes above and is the recommended form.

**Two constraints this puts on the schema, neither of them expensive:**

1. `slug` stores **only the label**, never the full host. A deployment that moves from
   `foo.a.org` to `foo-a.org` must not rewrite its tenant rows.
2. The label charset is the intersection of what DNS allows and what is safe in a path segment:
   lowercase alphanumerics and `-`, not starting or ending with `-`. **Validate on write in
   `bin/admin.js`** (§2.3), because it is the only writer of `tenants`.

**Still deliberately deferred**: two hosters sharing one deployment and wanting the same slug.
D10 makes that a per-deployment uniqueness question, which is the tractable version of it.

### 2.6 D11 — devicestatus is a decomposition problem, not a column-selection problem

T2.1 was blocked on "which of devicestatus's 182 nodes get generated columns". **That question
is now retired rather than answered**, because it assumed the document shape is the thing being
stored.

**The direction instead:** `devicestatus` is decomposed into idiomatic, normalised time series,
and *what* it decomposes into is declared by a registered controller description rather than
hardcoded. The mechanism already exists in the proposal series
([controller descriptions](PROPOSAL-controller-descriptions-2026-09-11.md) §5):

```yaml
documents:
  - collection: devicestatus
    discriminator: {path: loop, test: is-object}   # structural, not the device string
    decomposesTo: [ApsSnapshot, PumpSnapshot, UploaderSnapshot]
```

A known catalogue ships with Nightscout; a controller may publish or correct its own; either
way the decomposition is **data, not code**, which is what keeps it from becoming a fifth
drift-prone list beside the OpenAPI spec, `indexedFields`, the nsschema model and the `walker`
(§3.4).

**What this decides for T2.1, concretely:**

- **Emit almost no generated columns for `devicestatus`.** Its `indexedFields` declares only
  `created_at`, `NSCLIENT_ID` and one compound; those, and nothing else. The remaining 179
  nodes stay in JSONB.
- **Do not widen the column list to anticipate decomposition.** The normalised series are
  separate relations with their own schemas; adding columns to the document table would be
  building half of a design that is going somewhere else.
- **T2.1 is unblocked and smaller.** It emits DDL for the document shape; the decomposition is
  its own task in its own phase.
- **One thing to carry, not to solve here:** the 56-of-166 dropped-path finding that motivates
  decomposition ({M}'s motivation (a)) is a *fidelity* problem, and fixing it in the
  multitenant backend only would leave single-tenant behind, which D4 forbids. **Decomposition
  must sit above the seam, like coercion does** (§3.4) — file it accordingly.

### 2.7 D12 — what each repository is for

| repository | role |
|---|---|
| **`rag-nightscout-ecosystem-alignment`** (this one) | tooling, documentation, evidence, experiments, alignment exercises. Verification harnesses live here (`tools/seam/`, `tools/qc/`, `tools/mt-bench/`), as do all findings |
| **`cgm-remote-monitor`** | **kept pristine, neat and tidy.** Shipping code and its tests, nothing else |

**This repository is the quality-control system for that one.** Practical consequences:

- A benchmark, a differential oracle, a census script or a one-off probe belongs **here**, even
  when it exercises code **there**. Harnesses `require()` the shipping module by path so the
  two cannot drift, rather than carrying a copy.
- A commit to `cgm-remote-monitor` should read as ordinary, reviewable upstream work — no
  scaffolding, no research artifacts, no vendored fixtures that exist only to support an
  experiment.
- Findings are written up **here** and referenced from there, not pasted into code comments.
- `node_modules` is never tracked in either. A manifest plus a lockfile is what makes a tool
  reproducible; the tree is noise in the diff.

## 3. D8 — the query surface

### 3.1 Your impression is right, and the reason inverts

| | operator surface | where |
|---|---|---|
| **API v3** | **closed — exactly 9**: `eq ne gt gte lt lte in nin re` | `lib/api3/generic/search/input.js:111` |
| **API v1** | **open — pass-through** | `lib/server/query.js:157` |

v1's `create()` builds the filter with `traverse` type-coercion and injects a date constraint,
then **returns it to the driver without an operator allowlist**. Whatever `find[x][$op]` a
client sends reaches Mongo. That is {M} §6.5's unmitigated ReDoS/full-scan finding stated as a
translation problem: **you cannot write a complete SQL translation of an open pass-through.**

So v3 is not "smaller because it is newer" — it is smaller **because someone wrote the list
down**. That makes it the contract to implement first.

### 3.2 Strategy

1. **Implement v3's nine operators natively.** Closed, enumerable, testable exhaustively.
2. **Bound v1 with evidence, not guesswork.** The corpus in this workspace can answer *which*
   operators clients actually send. Support that set; reject the rest with a documented 400.
   **This is simultaneously the §6.5 security fix** — the allowlist that does not exist today.
3. **Keep the shape backwards compatible.** Same URLs, same parameter encoding, same defaults
   (`ENTRIES_DEFAULT_COUNT`, the two-day `deltaAgo` in `query.js`). A client that works today
   and sends an operator in the evidence set must not notice.

### 3.3 Libraries — verified available, with what each is actually for

| package | version | use here |
|---|---|---|
| **`mingo`** | 7.2.4 | **The differential-test oracle.** Evaluates Mongo queries against in-memory objects, so a translation can be checked by running the same query both ways and asserting identical results — the technique PR #8733 used with 636 randomised fixtures. **This is the highest-value one.** |
| `sift` | 17.1.3 | Same category; a second oracle if a `mingo` disagreement needs adjudicating |
| `mongo-query-to-postgres-jsonb` | 0.2.19 | Mongo→Postgres JSONB translation. A candidate for the v1 long tail, **not** for the v3 nine — those are better written explicitly than pulled from a dependency |
| FerretDB | `ghcr.io/ferretdb/ferretdb` | Mongo wire protocol over Postgres. **Named and rejected for the multitenant target**: it connects as a single role and cannot do per-transaction RLS binding, which is D3's entire point. Possibly useful as a migration bridge or for single-tenant-on-Postgres; not on this path |

**Recommendation: write the nine operators by hand, and use `mingo` as the test oracle.** Nine
operators is less code than integrating and constraining a translation library, and the oracle
is where the leverage is.

### 3.4 Type coercion — and no, mongoose is not where to fix it

**The casting gap {M} §6.5 refers to is worse than "a gap", and it is three different bugs.**
v1 coerces query values through a **hand-maintained per-collection allowlist** (`walker`), not
from any schema:

| collection | `walker` | source |
|---|---|---|
| entries | 7 fields, all `parseInt` | `lib/server/entries.js:186` |
| treatments | `insulin carbs glucose` → `parseInt`; `notes eventType enteredBy` → regex | `lib/server/treatments.js:260` |
| profile | `{}` — empty | `lib/server/profile.js:97` |
| **devicestatus, activity, food** | **none at all** | — |

Run against `lib/server/query.js` directly:

```
treatments insulin $gte=1.5                  {"insulin":{"$gte":1}}      <- truncated
treatments carbs   $gte=7.5                  {"carbs":{"$gte":7}}        <- truncated
entries    sgv     $gte=120                  {"sgv":{"$gte":120}}        <- correct
entries    delta   $gte=1.5                  {"delta":{"$gte":"1.5"}}    <- still a string
devicestatus uploader.battery $lt=50         {"uploader.battery":{"$lt":"50"}}  <- still a string
```

1. **Over-coercion gives wrong answers.** `insulin` and `carbs` are `parseInt`, but
   `specs/nsschema/treatments.model.json` declares both as `number`. **A query for boluses
   ≥ 1.5 U returns boluses of 1.0 U.**
2. **Under-coercion gives silently empty answers.** Any field with no `walker` entry stays a
   string, and MongoDB orders BSON types before comparing values, so a numeric field never
   matches a string bound. `devicestatus` and `activity` have no coercion at all, so *every*
   numeric filter on them matches nothing and returns 200.
3. **The `walker` is a fourth drift-prone list** beside the OpenAPI spec, `indexedFields` and
   the nsschema model — exactly what {M} §7.6 warned about.

**Would mongoose fix it? It would fix (1) and (2), in the wrong place.**

- **Mongoose is MongoDB-only, and D4 makes two backends permanent.** Coercion inside mongoose
  is coercion in one of them; Postgres would need its own, which recreates the drift problem
  one level up instead of removing it.
- **Coercion belongs *above* the seam.** The job is "HTTP query string → typed value", which is
  backend-independent and must happen *before* the repository interface is called — otherwise
  that interface's contract is "accepts strings or numbers, the backend decides", which is not
  a contract.
- **The types are already derived.** `specs/nsschema/` distinguishes exactly the case that is
  broken — `treatments.insulin: ['null','number']` against `entries.noise: ['integer']` — and
  five emitters already consume those models.

> **So: a coercion-table emitter is the sixth emitter, feeding one table used by the query
> parser above the seam, for both backends.** Mongoose keeps the role {M} §7.6 actually scoped
> it to — write-path validation *inside the MongoDB adapter*, where cast errors and defaults
> earn their keep and being Mongo-only is fine.

**Compatibility note for whoever ships this:** fixing (2) is user-visible. Queries that
silently returned nothing will start returning rows. That is the point, and it belongs in
release notes rather than arriving as a surprise.

## 4. D4 — what "MongoDB stays" costs the seam

The seam must carry **two mature backends permanently**, not one plus a migration path. Three
consequences that change how Task A1 is written:

1. **The interface is the intersection, not Mongo's shape.** If it exposes driver semantics it
   is not a seam ({M} §2.5 is precisely this complaint about `mongo-storage.js`).
2. **Both backends stay in CI forever.** Every storage test runs twice.
3. **`specs/generated/mongoose/` is the single-tenant validation path** — {M} §7.6 already
   recommends mongoose *scoped to the MongoDB adapter only*, with schemas generated from
   `specs/` rather than hand-maintained. That recommendation is now load-bearing — **but see
   §3.4: mongoose is for write-path validation inside the adapter, not for query coercion**,
   which has to sit above the seam to serve both backends from one table.

## 5. D9 — base branch

| branch | tip | vs `dev` |
|---|---|---|
| `origin/dev` | `a8888f0d` | — |
| `origin/chore/nightscout-modernization` | `0a4109f6` | **495 commits, 573 files, +107,596 / −14,872** |

**Base on the modernization branch.** It already closes {M} §3.1's shared-alarm-state blocker
(commit `9e869662`), it carries the Playwright suite and the Node 22/24 floor, and rebasing 495
commits underneath this work later would be worse than starting on top of it.

**One caveat to carry, not to resolve here:** the release-readiness review found #8605 has
**zero human reviews across 1,909 production lines**, all by one author. That is a blocker for
*shipping* the modernization stack, and it is not a blocker for *developing* against it. Do not
let this plan be read as having reviewed it.

---

## 6. Tasks

Ordered by dependency. Each is sized to be picked up independently. **Every task states what
"done" means as a command that passes**, because "done" that cannot be checked is how a plan
rots.

Conventions for all tasks: branch from `origin/chore/nightscout-modernization`; `NODE_ENV=test`;
the suite is `npm run test:unit` (149 files, no database) and `npm run test:integration`
(10 files, needs a database at `mongodb://127.0.0.1:27017/testdb`, see `tests/ci.test.env`).

### Phase 0 — ships to every existing operator, no tenancy decision required

**T0.1 · Land PR #8733.** In flight. The two quadratic scans. Everything downstream assumes it.

**T0.2 · Fix `/api/v1/entries` untyped read.**
`lib/api/entries/index.js:459-500`. `?count=10` costs **0.83 ms** without `find[type]` and
**0.02 ms** with it — a 42× overcharge for a byte-identical response, because
`ctx.cache.getData('entries')` (`lib/server/cache.js:73-76`) deep-clones the whole 48-hour
array before anything is sliced. Slice first, then clone the slice; the documents handed out
are still clones, so the defensive property is preserved.
*Done*: `node --expose-gc tools/mt-bench/apitier.js read` shows the untyped branch within 2× of
the typed one at `count=10`; `npm run test:unit` and `test:integration` pass.
*Evidence*: {R} §12.2.

**T0.3 · Audit `cache.getData`'s five call sites.**
`lib/server/cache.js:81`, `lib/data/dataloader.js:195/332/489`, `lib/api/entries/index.js:490`.
`insertData` returns `getData()` — a JSON round-trip over the **whole** retained array, per
datatype, per cycle: **4.08 ms**, which is 65 % of the post-#8733 load cycle.
**Resolve `dataloader.js:203` first** — `if (!element.mills) element.mills = element.date`
writes to the element, so a shallow copy changes behaviour there. The measurement sizes the
prize; it does not license the patch.
*Done*: `node --expose-gc tools/mt-bench/apitier.js cycle` shows clone cost < 1 ms; full suite
passes; a test pins the mutation semantics either way.
*Evidence*: {R} §12.3.

**T0.5 · Schema-driven query type coercion.**
Emit a coercion table from `specs/nsschema/*.model.json` (sixth emitter, beside
`mongoose_emit.py` et al.) and drive `lib/server/query.js`'s walker from it instead of the
hand-maintained per-collection lists. Fixes three measured bugs (§3.4): `insulin`/`carbs`
truncated by `parseInt` despite being declared `number`; every numeric filter on
`devicestatus`, `activity`, `food` and `profile` silently matching nothing; and a fourth
drift-prone list. **Ships to single-tenant operators independently of everything else.**
*Done*: the §3.4 cases produce correctly-typed output; a test asserts the emitted table matches
the model for every collection; the full suite passes. **Release-note the behaviour change** —
queries that returned nothing will start returning rows.
*Depends on*: nothing. *Blocks*: nothing, but makes T2.3/T2.4 much easier because the typed
value is then backend-independent.

**T0.4 · Start and interval jitter in `nightscout-connect`.**
800 actors fire their first upstream request inside one second on every restart and deploy
(`run()` sends `START` with no jitter), and stay phase-locked on the same five-minute boundary
after. Independent of everything else here.
*Evidence*: {R} §6.2.

### Phase 1 — the seam (the real prerequisite)

**T1.1 · Define the repository interface. — DONE 2026-09-14**, see
[the seam interface document](nightscout-storage-seam-interface-2026-09-14.md) and
`reports/storage-seam/t1-1-call-site-classification.tsv`.

**Three corrections it produced, which change the tasks below:**

1. **The count is 85, not 68.** The grep in the original task text excluded `.find(` to dodge
   `Array.find`, which also dropped every `col.find(filter)` — the commonest read in the
   codebase. Scripts to re-derive it are committed beside the classification.
2. **The conversion is ~55 sites, not 85.** 15 are already interface consumers
   (`api3/generic/*`, `mongoCachedCollection`) and 14 are the interface and its Mongo adapter.
   **API v3 is three-quarters of a seam that already exists** — `MongoCollection` exposes a
   real interface with a real decorator over it. The task is to finish it and bring v1 to it,
   not to design one.
3. **There is a third write path.** `lib/server/websocket.js` implements full CRUD over
   Socket.IO (`dbAdd`/`dbUpdate`/`dbUpdateUnset`/`dbRemove`) with **its own dedup logic**,
   parallel to v1's and v3's. Every "v1 and v3" statement in {M}, {C} and this plan is
   incomplete. Convert it last; file dedup unification separately, as it is a behaviour change.

**Classification**: 39 `fits`, 27 `needs-escape-hatch`, 19 `must-change` — and the 19 are
**four root causes**, of which **9 sites are the single cause "`query_for` returns a Mongo
filter document"**.

**The recommendation that follows**: do the **filter AST** first, standalone, before converting
anything. Make v3's nine operators the seam's filter language; then T0.5's coercion table has
somewhere to apply, T2.3 is already done by construction, and **T2.4's allowlist falls out
structurally — an AST that cannot express an unlisted operator *is* the allowlist**, which is
{M} §6.5's security fix arriving for free.

~~**One gap to close before T1.2 starts**: the interface has no **transaction scope**~~ —
**closed 2026-09-14, after T1.2 rather than before it.** `store.withTenant` plus a
`requireTenant` assertion at the `MongoCollection` delegations; see {S} §9.1 for what was built
and why `SINGLE_TENANT` is a `Symbol`. The warning about retrofitting was right about the risk
and wrong about the cost: T1.2 left **one** choke point where there had been 68, so the retrofit
touched three files. The assertion is **inert until T3.1** — nothing selects multitenant mode
yet — and exists so T2.5 has the scope RLS requires.

**T1.2 · Convert the 19 files to the interface, MongoDB only. — SUBSTANTIALLY DONE 2026-09-14**
**Zero behaviour change.** No Postgres, no tenancy, no schema.
*Done*: all 159 test files pass unchanged; no file outside `lib/storage/` and the adapter
imports the `mongodb` driver.
*This is the highest-value task in the plan* — it is the prerequisite for everything in Phase 2
and it is checkable by a suite that already exists.

**Status.** Suite **2207 passing, 1 pending, 0 failing** (baseline 2150; the increase is new
tests only). **No existing test expectation was changed** — the single edit to an existing test
file is a test double gaining a `project()` method, because the projection now rides on the
cursor rather than `find()`'s second argument.

Converted: `activity` (4 sites), `treatments` (9), `food` + `devicestatus` (9), `profile` (7 of
8) + `entries` (4 of 4), `authorization/storage` (4), `aggregate` (1), `api/entries` count (1).

`websocket.js` is converted too — the last cluster, and the one where a filter and an update
document are assembled from fields arriving straight off a socket, so it is where "the query
object is the allowlist" had the least margin.

**One site remains**: `profile.list_query`. `GET /profiles/` accepts `$expr` today and a test
asserts it. Whether to represent or reject `$expr` is a **query-surface decision (D8/T2.4)**,
not a conversion detail — and T2.4's census found no client sends it, so this is now a decision
about a server capability rather than about breaking a known consumer.

**Four defects and gaps found by doing the conversion**, none of which the plan anticipated:

1. **`fromMongo` silently dropped a native `RegExp`.** `Object.keys(/x/i)` is `[]`, so the
   clause produced no nodes and vanished with no error. `lib/server/query.js`'s `parseRegEx`
   returns a native RegExp for the treatments `notes`/`eventType`/`enteredBy` filters, so
   `find[eventType]=/Bolus/i` returned **every** treatment rather than the boluses. A widened
   query is the worst available failure mode: it looks like a working answer. Fixed by giving
   the `re` node an `options` field — flags off the pattern, so they cost nothing against
   `RE_MAX_LEN` and the SQL adapter can use the operator PostgreSQL actually has (`~*`).
2. **The count endpoint's date bound** (`aggregate.js` calling `find_options(opts)` with one
   argument) — already recorded; the fix now routes count and list through the *same*
   `query_for`, so they bound identically by construction. It affected treatments and
   devicestatus too, not only entries.
3. **`acknowledged` was about to disappear from four delete response bodies.** Three modules
   independently re-synthesised `{acknowledged: true}` to compensate, which would misreport an
   unacknowledged write. The interface now passes the driver's value through.
4. **No non-upserting replace existed.** The socket path's profile dedup replaces in place and
   must not insert; every route the interface offered was an upsert, which would resurrect a
   profile deleted between the lookup and the write. Closed with `replaceFiltered`.

Three of the four surfaced because a converting agent **stopped and reported a mismatch instead
of reaching for the nearest working call**. That is worth carrying into Phase 2 as a working
rule, not just recording as a fact about this milestone.

**Method note.** The seam is verified by two differentials, both re-run on every change:
`tools/seam/roundtrip.js` (4000 generated `query.js`-shaped filters, mingo as oracle) and
`tools/seam/validate.js` (5000 randomised ASTs, mingo vs live PostgreSQL, reported per
operator). `roundtrip.js` reports zero mismatches; `validate.js` reports zero for nine of its
ten operators and the `re` defects T2.3 records below. Each was checked to be **non-vacuous** by
reverting the fix under test — the RegExp case gives 240 mismatches when removed, several
reading `0 vs 98` and `69 vs 333`; `nin`'s `IS NULL` guard gives 588 and `exists` on the
generated column gives 188, each charged to that operator alone. A differential that has never
failed is not yet evidence.

**T1.3 · Parametrise the storage-touching tests by backend. — DONE 2026-09-14**
*Done*: the storage-touching files run against a backend selected by env, with MongoDB as the
only implementation so far, and pass. **2207 passing, 1 pending, 0 failing** — identical to the
pre-merge figure, and no `lib/` file touched.

**The census found 21 files, not 10.** The estimate in this plan was off by more than a factor
of two. Two of the 21 are grep false positives: `tests/runtime-policy.test.js` matches only
because `'../storage/mongo-storage'` appears inside a spawned child's module blocklist, and
`tests/boot-sequence-integration.test.js` matches `ctx.store` only to assert it is `undefined`
after a *failed* boot. Neither was touched.

The remaining 19 split three ways, and the split is recorded in a comment above each suite
rather than in this document, because that is where someone editing the file will look:

| class | count | disposition |
|---|---:|---|
| backend-agnostic — touch storage only for fixtures | 7 | `describeForEachBackend` |
| MongoDB's own **by nature** — driver semantics, pooling, retry, URI grammar, AWS auth | 6 | `describeMongoOnly` |
| MongoDB's own **by mechanism** — intent is agnostic, proof is wire-command counting | 6 | held, see below |

The middle and last rows are not the same thing and the harness says so in two different
spellings. *By nature* is permanent: `mongo-uri-credentials` is about `mongodb+srv://` grammar
and there is no backend-agnostic statement hiding inside it. *By mechanism* is temporary: the
six `monitorCommands` suites assert something genuinely backend-independent — permission is
enforced before any I/O, no executable predicate reaches the database, the right collection was
read — but they prove it by counting `find`/`aggregate`/`delete` wire commands. Forcing them
through the harness today would mean weakening the assertion to something a second backend
could also satisfy. **They need a per-backend I/O observer first; that is a follow-up task, not
a skip.**

Two files E classified as blocked were **unblocked before the branch landed**:
`websocket.shape-handling` and `websocket.xss-purification` were held because
`lib/server/websocket.js` reached MongoDB directly, which stopped being true at `ef89bdb8`.
Both are now parametrised. Worth noting as a coordination cost of running conversions in
parallel: a classification is only as current as the tree it was taken against.

**The visibility contract is the deliverable, not the parametrisation.** A backend that cannot
run must produce *pending* tests, never absent ones. Two mechanisms, both demonstrated on the
merged tree:

1. **An unrecognised name is a hard error at require time.** `NS_TEST_BACKEND=postgre` exits 1
   with `Unknown NS_TEST_BACKEND "postgre"`. A typo can never quietly shrink the suite.
2. **A known-but-unavailable backend skips one for one.** The unavailable path uses
   `describe.skip`, which *still evaluates the suite body*, so every `it` is registered and then
   reported pending rather than never existing:

| run | passing | pending | **total** | failing |
|---|---:|---:|---:|---|
| default (`mongodb`) | 2207 | 1 | **2208** | 0 |
| `NS_TEST_BACKEND=postgres` | 2045 | 163 | **2208** | 0 |

Exactly 162 tests move columns; the total is conserved. This is the property that matters — it
is what stops a future PostgreSQL run from reaching "0 failing" by making tests disappear.

**Scope honesty.** Under `NS_TEST_BACKEND=postgres` the 2045 still-passing tests are the
*unconverted* suite running against MongoDB exactly as before. The harness covers the enumerated
storage-touching files; it does not make the whole suite backend-aware, and does not claim to.

**T2.0 · The storage backend lookup at boot. — DONE 2026-09-14**
`lib/server/bootevent.js` carried `//TODO assume mongo for now, when there are more storage
options add a lookup` over a hardcoded `require('../storage/mongo-storage')`. That TODO *was*
the backend selection: the interface had an implementation behind it and no way to choose one.

*Done*: `lib/server/storage-backends.js` selects by the **scheme already present in the
connection URI**, not by a new env var. A separate `NS_STORAGE_BACKEND` can disagree with the
URI it is supposed to describe, and the disagreement surfaces as a driver parse error rather
than as the configuration mistake it is — which is precisely today's behaviour, and the reason
the new boot test is non-vacuous: reverting the lookup makes it fail with `Unable to connect to
Mongo / MONGODB_URI seems invalid` for a `postgres://` URI, sending the operator to inspect a
database that was never contacted. It now reports `Unsupported storage backend`, names the
scheme asked for, and lists the schemes the build actually has.

A URI with **no** scheme, or no URI at all, still resolves to `mongodb`. That is the shape a
misconfigured deployment has today and `mongo-storage` already has a specific message for it; a
scheme error would replace a good message with a worse one.

The `require()` calls stay literal, inside thunks, and a test enforces that. `require(spec)`
over a variable would **retire `tests/runtime-policy.test.js` without failing it** — that test
intercepts `Module._load` and treats the literal `'../storage/mongo-storage'` as the sentinel
for "an application service was loaded before the Node version was checked". A check that
silently stops checking is worse than one that was never written. A second test asserts no
driver is pulled into the process until a backend is selected and asked for.

8 tests added; **2215 passing, 1 pending, 0 failing**.

**Two further items were blocked behind this and are now unblocked** — they are listed here
rather than separately because they share the change, and neither is done:

- `storageClear` in `tests/fixtures/api3/utils.js` calls `ctx.store.db.dropDatabase()` — the
  single most MongoDB-specific line in the shared fixtures, reached by ten further unconverted
  `api3.*` files. Routing it through the harness *before* this task would make those files fail
  loudly under a non-Mongo selection rather than skip, drowning out the pending arithmetic that
  is the whole point.
- **Per-run test isolation.** Every worktree in this phase shared one `testdb`, because the
  database name is buried in the path component of a connection URI in a single env var
  (`CUSTOMCONNSTR_mongo`) and there is no separate "which database" knob. Two agents running
  full suites concurrently would have destroyed each other's data, and
  `tests/lib/production-safety.js` would not have noticed: it guards *destructiveness* (entry
  count, "test" in the name) and has no concept of *collision*. The natural home for the fix is
  the harness — an adapter already owns `clearAll`, so it can own "derive an isolated namespace
  for this run" (a database for Mongo, a schema for Postgres). It cannot be done first: the
  store is built by `bootevent` from `env.storageURI` before any test code runs.

*Remaining for T2.0's dependants*: route `storageClear` through the harness, and give each run
its own namespace. Both are now possible; neither is done.

### Phase 2 — Postgres behind the seam

**T2.1 · Postgres DDL emitter. — DONE 2026-09-14**
A sixth emitter in `tools/nsschema/emit/` alongside `mongoose_emit.py`, `zod_emit.py`,
`jsonschema_emit.py`, `pyarrow_emit.py`, `fieldref_emit.py`. Input: `specs/nsschema/*.model.json`
(entries 31 fields, treatments 58, devicestatus 17 top-level / **182 nodes**, profile 14 / 72).
Output: `CREATE TABLE` with `tenant_id uuid` leading, JSONB for the document body, **generated
columns for the fields in `indexedFields`** (41 indexes, enumerated in {M} §6.7), each index
tenant-prefixed.
~~*Blocked on a decision*~~ — **unblocked by D11 (§2.6)**: emit `devicestatus`'s
`indexedFields` set only (`created_at`, `NSCLIENT_ID`, one compound) and leave the other 179
nodes in JSONB. The 182-node question is retired, not answered: decomposition into normalised
time series is declared by registered controller descriptions and is its own task, above the
seam.
*Done*: emitted DDL loads clean; `tools/mt-bench/pgfeed/pgfeed.js` RLS arm passes against the
generated schema instead of its hand-written one.

**T2.2 · The missing collection models. — DONE 2026-09-14**
`food`, `activity`, `settings` (~~mechanical~~), and **`auth_subjects` / `auth_roles`, which have
no evidence-derived model and must be read out of `lib/authorization/storage.js`**. Auth is not
optional for a running server.
*Done*: `specs/nsschema/` carries a model for all **ten** collections, and `provenance` is now on
every node of every model — `measured` · `declared` · `declared+measured` · `code` ·
`structural`. The absence of an `evidence` block could not distinguish "declared in a spec but
never observed" from "nobody ever censused this collection"; now an emitter can tell.

**`settings` was not mechanical, because `settings.census.json` is not a census of the `settings`
collection.** It is collected from each snapshot's `settings.json`, which is a capture of
`GET /api/v1/status.json` — its twelve fields are exactly the `info` object `lib/api/status.js`
builds. So `settings` has **no** census, and nothing in `cgm-remote-monitor` writes a document to
that collection at all. The real evidence is modelled under its own name as `status.model.json`;
the `settings` collection gets an honest code-derived open-bodied model that records the
collision, because a reader who finds `settings.census.json` on disk will otherwise conclude the
model is stale.

**Neither route this plan offered was taken, and the reason generalises.** An OpenAPI document is
an *assertion*; a census is a *measurement*. Merging an assertion through `model.py` into the
same directory under the same filename convention produces a file **indistinguishable from an
evidence-derived one** — which is the poisoning to avoid, arriving by the route that looked
safest. A wholly separate generator would have duplicated the IR. What landed is a separate
generator over a real parse of the literals the server declares its shapes in
(`tools/nsschema/jsread.py`, which refuses what it cannot parse rather than returning a plausible
empty result), sharing `model.Node` and `to_dict` so all 48 existing artifacts stayed
byte-identical.

**The drift check is proved, not asserted**: seven mutations of a copied tree (a field added, a
field renamed, an index dropped, a role added, a digest field renamed, two source anchors moved)
each exit 1; the unmodified control exits 0. Its `--cross-check` additionally shows
`externals/work/crm-seam` and `externals/cgm-remote-monitor-official` declare **identical** field
sets — independent confirmation that none of the seam work moved these anchors.

Three findings worth carrying: **BF-17** (a subject edit persists the API access token in
plaintext — see the register), **BF-16**'s second half (form encoding stringifies `position`, so
eleven or more quick picks sort lexicographically and come back in the wrong order **on the
shipping path**), and that `NSCLIENT_ID` is client-supplied, never generated or validated by the
server, and is the *sole* match key for websocket duplicate detection when present.

**T2.3 · v3's nine operators in SQL, with `mingo` as oracle. — DONE 2026-09-14; the three `re`
defects are FIXED** in `lib/storage/filter.js` (`c1218d50` on `seam/t1-2-storage-interface`),
which cost one existing test expectation — the regex SQL spelling test asserted a match against
the generated column, and that *was* the first defect. See
[the `re` validation report](../60-research/seam-filter-re-operator-validation-2026-09-14.md).
`eq ne gt gte lt lte in nin re` from `lib/api3/generic/search/input.js:111`. Differential-test
each against `mingo` over randomised fixtures, following #8733's method.
*Done*: ≥500 randomised fixtures per operator, zero disagreements with `mingo`; `re` explicitly
bounded (pattern guard + timeout) since it is {M} §6.5's live exposure.

**Status.** `tools/seam/validate.js` is now per-operator (a focus operator round-robins so the
counts are built rather than hoped for, blame is isolated to a single node before it is counted,
and the run fails if any operator lands under 500). Over 5000 fixtures — **981 to 1052 per
operator** — the eight non-regex operators and `exists` report **zero** disagreements. `re`,
which was behind a `WITH_RE` flag and had never been measured by any published run, reports
**54 mismatches and 95 SQL errors**, in three distinct defects in `toSql`'s `re` branch: ARE's
newline modes are not Mongo's `m`/`s`, jsonb renders non-strings as text that a pattern then
matches, and `re` against a numeric generated column raises `operator does not exist` — a 500,
reachable by any client, on 1.9 % of generated fixtures. A fix is proposed and measured (0
mismatches, 0 errors) against a scratch copy; `externals/work/crm-seam/` was not modified.

**One correction to the criterion itself.** `re` is the only operator whose meaning comes from a
regex *engine*, and mingo's is V8 while MongoDB's is PCRE2. A new deterministic three-arm probe
(`tools/qc/re-arms.js`, 21 constructs) finds three where **mongod differs from PostgreSQL and
mingo agrees with PostgreSQL** — the differential reports 100 % while the real backends return
different documents. So for `re`, "zero disagreements with `mingo`" does not imply "the backends
agree", and closing T2.3 needs the mongod arm as well. Same tool measures the bound: `RE_MAX_LEN`
is a length bound, not a work bound, and on the classic catastrophic patterns the backtracking
exposure is the **JavaScript** arm's — mongod 7 and PostgreSQL 16 are both flat.

**T2.4 · v1 operator census, then an allowlist. — CENSUS DONE 2026-09-14**
Derive the operators clients actually send from the corpus; support those, reject the rest with
a documented 400. **Ships as a security fix regardless of Postgres** — it is the allowlist that
does not exist today.
*Done*: census committed with counts per operator; allowlist enforced; the rejected set
documented in the API docs.

**Census result** (`tools/qc/v1_operator_census.py`, `reports/v1-query-census/`): 157 literal
`find[field][$op]` occurrences across **14 client projects**.

| operator | occurrences | projects | in the AST |
|---|---:|---:|---|
| `gte` | 55 | 13 | yes |
| `eq` | 36 | 10 | yes |
| `lte` | 32 | 10 | yes |
| `gt` | 22 | 5 | yes |
| `lt` | 5 | 3 | yes |
| `ne` | 4 | 3 | yes |
| `exists` | 3 | 2 | yes |

Plus `$or` (2) and `$and` (1), both from one project. **Every operator any client sends is
already expressible in the filter AST**, and 21 distinct fields appear, led by `created_at`
(57), `date` (30) and `eventType` (13). Nothing in the corpus sends `$where`, `$expr`,
`$elemMatch` or `$near` — which is the evidence that rejecting them is a security fix and not a
compatibility break.

**Read the limit with the number.** This measures what client *source* contains, not what a
deployment receives: a filter built by string concatenation at runtime, or typed into a
browser, is invisible to it. It is a **lower bound on the field set and a strong signal on the
operator set**, because the operator is almost always a literal even when the field and value
are not. Same method and same caveat as `reports/schema-census/attribution.json`.

This directly settles the `$expr` question T1.2 deferred: no client sends it, so the remaining
`profile.list_query` site is a decision about a server capability with a test, not about
breaking a known consumer.

**T2.5 · `entries` end-to-end on Postgres + RLS. — DONE 2026-09-15**

Every prerequisite is now in place, which is worth stating because they were added in four
different milestones and it is not obvious from any one of them: the **backend lookup** (T2.0),
the **transaction scope** RLS binding needs (§9.1 — `set_config(…, is_local => true)` is
transaction-local), the **DDL and its `columnTypes` manifest** (T2.1), the **filter adapter
validated against a live mongod** (T2.3 + §8.6.2, 3000/3000 cross-type), and the
**backend-selectable test harness** (T1.3). The two items left open behind T2.0 — routing
`storageClear` through the harness, and per-run namespace isolation — fall to this task, because
it is the first one that actually needs them.
EXP-MT-037. Connect as a role that is **`NOSUPERUSER NOBYPASSRLS`** — {DB} §8.1 nearly
published two false findings because the test ran as superuser, and RLS is silently not
enforced for superusers.
*Done*: ~~T1.3's parametrised tests pass against both backends~~ — **this criterion cannot be
met at this scope, and the reason is worth keeping**; an unbound connection returns **0** rows
(and **4** on the same connection once bound); `EXPLAIN` shows
`Index Cond: (tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)`
on `entries_tenant_date`, over 12,000 rows across 3 tenants.

**Suite: 2351 passing, 1 pending, 0 failing. Under `NS_TEST_BACKEND=postgres`: 2172 passing, 180
pending, 0 failing. Total conserved at 2352 both ways.** Lint back to baseline.

#### The scope conflict, reported rather than worked around

**"`entries` only" and "T1.3's parametrised suites pass on PostgreSQL" are mutually exclusive.**
All seven of those suites boot through `bootevent`, which constructs a storage collection for all
six v1 modules *and* both authorization collections, and five of them assert on `treatments`,
`profile`, `food`, `activity` or auth. **Zero of the seven can run against an entries-only
backend** — including `api3.renderer`, which is otherwise entries-only.

The resolution keeps the visibility contract instead of bending it: a suite now declares the
collections it needs, and a backend that lacks one skips it **with the collection named**. Still
pending, never absent. The question the criterion was actually asking is answered by a new suite
that can answer it — `tests/entries-both-backends.test.js`, 16 HTTP tests over API v1 and API v3
entries, **16/16 on MongoDB, 16/16 on PostgreSQL, 32 passing in one `mongodb,postgres` run**.

#### The `is_local` check was vacuous, and this one was the *implementation's* fault

§8.6.1 recorded a differential that could not fail because the **corpus** never exercised the
property. This is the other way it happens. Breaking `set_config(…, is_local => true)` to
`false` produced **0 failures** — because the adapter binds every operation anyway, so nothing
distinguished a transaction-local binding from a session-local one. The entire argument for
`is_local`, which is the reason the interface needed a transaction scope at all (§9), was
unmeasured.

It *is* measurable, and the thing to measure is not the query: **a connection handed back to the
pool must carry no binding.** Otherwise a future unbound path — or a transaction-pooling
pgbouncer, which is how this deployment is expected to scale — serves one tenant's request on
another tenant's binding. A pool of one plus `store.pooledTenantBinding()` (a *question*, not a
query hatch) now assert it, and the break fails it.

**Generalise both:** a check is vacuous when *nothing in the run distinguishes the two branches*,
and that can be a property of the corpus **or** of the code under test. Only breaking it tells
you which.

#### Three more findings

- **The `Index Cond` criterion is insensitive to `columnTypes`.** The policy predicate alone
  gives a tenant bound on any index, so that criterion would pass with the manifest thrown away.
  What `columnTypes` actually decides is whether `date` reaches the typed column, so the test
  asserts the emitted predicate is `"date" >= $1` as well.
- **`lib/server/aggregate.js` still took a raw driver collection.** T1.2 moved the count path
  onto `count()` and left its *argument* behind, so `/count/:storage/where` worked on MongoDB
  only. Fixed; all three v1 modules now pass their storage accessor.
- **jsonb's cross-type sort ordering is not BSON's.** Both sort types before values and they
  disagree on the order of the types. Every sort this path issues is on a field that is one type
  in practice (`date`, `srvModified`, `identifier`, `created_at`), so it does not bite — but the
  adapter cannot enforce that, and the limit is documented at the code rather than assumed away.

#### The two items behind T2.0, both closed

`storageClear` routes through the harness adapter — MongoDB drops the database, PostgreSQL
truncates the run's tables. Per-run namespaces arrive as `STORAGE_NAMESPACE`: a schema on
PostgreSQL, a database on MongoDB, with the configured database kept as a prefix so
`production-safety`'s "looks like a test database" check still sees what it saw. Verified: no
stray databases, schemas or roles after a run.

**`tests/lib/production-safety.js` is not namespace-aware** — it still reads the database name
out of the URI. Harmless today, wrong under `STORAGE_NAMESPACE`, and left alone rather than
half-changed.

#### Vendoring, and the check that makes it safe

The server cannot depend on this repository at runtime, so the emitted DDL is **vendored** into
`lib/storage/postgres/generated/` — and that copy is what creates tables on a deployment. Two
files in two repositories with nothing relating them is a schema that drifts silently, so
`make schema-vendor-drift` compares them byte for byte. A checkout that vendors nothing is not a
failure; a run that checked *nothing* says so rather than exiting 0, which is how a drift check
quietly stops being one.

#### Not done, and named

Every collection but `entries`, and therefore full-server boot on PostgreSQL. `insertMany`,
`updateMany` and `replaceFiltered` throw by name (`$unset` has no decided representation —
removing a jsonb key and setting it to null are different documents). No TLS, no pgbouncer, no
write-throughput or working-set measurement, all of which §7 lands here. `bulkUpsert` issues one
statement per operation — a performance gap, not a correctness one, and the whole batch is still
one transaction, which is more than the MongoDB path promises.

### Phase 3 — tenancy

**T3.1 · Tenant resolution middleware. — DONE 2026-09-15**
Host → slug → tenant id, path prefix fallback, token claim verified against the resolved tenant
(reject on mismatch). {M} §5.2 item 1.

The rule is a **configured regular expression with exactly one capture group**, per D10. Three
things are deliberately *not* configurable, each for a reason that lives in the code:

- **Exactly one group, not "at least one"** — with two, which capture is the slug is a guess made
  at the isolation boundary.
- **No flags.** `g` and `y` carry `lastIndex` across calls, so a shared regex would resolve a
  request by what the *previous* request did. Hosts are lowercased instead of allowing `i`.
- **The slug charset is re-checked on read**, even though `bin/admin.js` owns it on write,
  because the capture comes out of a Host header and a loose pattern (`^(.*)\.apex\.org$`) is
  the realistic mistake.

**Three departures from the letter of §5.2, all deliberate:**

1. **The host comes from `req.headers.host`, not `req.hostname`.** `req.hostname` prefers
   `X-Forwarded-Host` whenever the trust-proxy function says yes — and `compileTrust('')`,
   Nightscout's **default**, returns a function that always says yes. Under `req.hostname` any
   client could choose its own tenant with a header. Naming another header refuses to start
   unless `TRUST_PROXY` is configured.
2. **A presented credential with no tenant claim is refused by default.** §5.2 specifies only the
   mismatch, but `lib/authorization/storage.js` keeps subjects as **one process-wide array loaded
   at boot**, so a token resolves to its subject regardless of which tenant's host it arrived on
   and nothing underneath would catch an unclaimed one. A knob, not a constant, so T3.3 can
   revisit. Anonymous requests still pass.
3. **The claim carries the tenant *id*, not the slug** — a slug can be reassigned, an id cannot,
   and the id is what RLS compares, so there is no second mapping to drift.

It **binds** rather than opening a transaction (`tenantScope.withTenant`, not
`store.withTenant`, which would hold a PostgreSQL transaction open across response streaming).
That also composes with both backends, which a resolver that *selected a store* would not.

**Single-tenant is not a degraded mode**: `fromEnv` returns `null` unless `TENANCY_MODE=multi`,
so nothing mounts at all, and `setTenancyMode('multi')` is the **last** thing it does — a refused
configuration cannot leave a single-tenant process asserting a binding nothing sets.

**18 guards broken one at a time. Three changed nothing, and all three were the tests' fault
rather than the code's** — the corpus cause of vacuity, found by going looking for it. One of
them existed because the test app used express's *default* `trust proxy`, so the two headers
agreed and either answer passed.

*Not done*: never booted a real multi-tenant server end to end, because there is no `tenants`
table until T3.2's DDL runs. `fromEnv` warns loudly at boot, and the README says it, that `multi`
is **not safe yet** — settings, plugins, notification state and socket rooms are still
process-wide. This is the **first** of §5.2's eight cross-cutting requirements, not tenancy.

**T3.2 · `bin/admin.js` — DONE 2026-09-15**, per §2, including the refuse-to-start guard on a
non-loopback bind.

**The guard's proof is that it refuses for the *right* reason.** Refuse `0.0.0.0:P`, then bind
`P` successfully by hand — showing nothing was opened and closed and that the port was never
busy; then bind the *same* address and port through `listen()` with the acknowledgement set and
serve a real request on it, one environment variable apart. A control squats a port and asserts
`EADDRINUSE` is **not** the guard's error code, so the two failures are distinguishable. An
ordering test runs the same broken `STORAGE_URI` twice — once on `0.0.0.0` (fails on the bind),
once on loopback (fails on the database) — because without it the guard would also pass if it
ran last.

Classification uses `net.BlockList` rather than a hand-rolled IPv6 parser; a **name is resolved
and every resolved address must be loopback** (`localhost` is loopback because of a file this
process does not read, and that also catches `127.1`, which glibc accepts and `net.isIP` does
not); and an empty `ADMIN_BIND` is refused rather than folded into the default, because
`listen(port, '')` binds everything.

**Two parts of §2.3's proposal are argued against rather than implemented, and both arguments
are the same shape:**

- **Quota get/set — left out.** §2.4 has no quota column and **nothing in the system enforces a
  quota**. Shipping it widens a schema a sibling reads as a contract in order to store a number
  nobody reads — and *an operator who can set a cap will believe the cap exists*. It wants an
  enforcement point first.
- **Health reports only what has a producer.** Replication slots come back as
  `{status: "absent", reason: …}` naming Phase 4, never `lag_bytes: 0`. Same failure mode as the
  fabricated quota, one layer up.

**Delete is too dangerous in the shape proposed**: the document tables carry `tenant_id` with
**no foreign key** back to `tenants`, so deleting the tenant row *orphans* the rows rather than
removing them — unreachable, unexportable, still on disk. Delete therefore **refuses while any
tenant-scoped rows exist**, behind four gates (slug echoed in the body, tenant already suspended,
no rows left, state unchanged since read).

**Schema departures from §2.4**, for anyone reading that as a contract: `slug` gains a `CHECK`
(writes only — no reader is affected); `tenant_members` gains the `ENABLE`/`FORCE ROW LEVEL
SECURITY` and policy that §2.4's *prose* requires but its SQL block omits; `tenants.id` has no
`DEFAULT`, so a reader should not expect `gen_random_uuid()`.

**The admin store refuses to run as `SUPERUSER`/`BYPASSRLS`** — for a different reason than
`postgres-storage.js` does. Its per-tenant counts are computed *by* RLS, and that count is what
decides whether a `DELETE` proceeds; as a bypassing role the number would be every tenant's rows.

**B13 was a vacuous check of the agent's own, of the *code* variety** (§T2.5): the health test
read the endpoint's own `status` and asserted the detail only inside the `absent` branch, so a
break reporting `ok` steered it down the branch that asserts nothing — and the paired test
`skip()`ped on the same condition, **which looks exactly like a pass**. Fixed by taking the
expectation from an independent query against `pg_replication_slots`.

*Not done*: two-role deployments are untested; logical-slot lag arithmetic has no producer until
Phase 4; the admin plane is **PostgreSQL-only by construction**, with no export for a
single-tenant MongoDB deployment. **Reserved labels** (`www`, `api`, `admin`) and `xn--` prefixes
are flagged and not enforced — which labels collide is a fact about a hoster's DNS, not about
Nightscout, and a homograph policy is one this plan does not contain.

**The seam between T3.1 and T3.2, closed after the merge.** Both were correct and the gap opened
anyway: `bin/admin.js` creates `tenants` and the role running it **owns** the table, while the
resolver assumes it can read it. A hoster running the application as a different role — the
careful shape, since the admin role is the one that can delete tenants — got `permission denied
for table tenants` as a **503 on every request**, with the fix sitting in a `platform.sql`
comment. The registry now turns `insufficient_privilege` and `undefined_table` into sentences
naming the `GRANT` and the admin plane respectively, and passes everything else through, because
a connection failure is not a configuration mistake.

**T3.3 · `ctxFor(tenantId)`** — the `Map<tenantId, ctx>` substrate, for the single-process
path. Note {C}'s finding that this is a *cache* with a graceful fallback, not the source of
truth.

**Two blockers, named before the task starts** — measured 2026-09-15, see
[the shared-state audit](../60-research/tenant-shared-state-audit-2026-09-15.md) and
`tools/qc/tenant-shared-state.js`. Of 70 files carrying module-level mutable state, only **six**
are server-resident *and* written after load; the other 40 are browser files loaded once per
page, by one person, for one site. Two of the six were confirmed by **running** them:

1. **`env` is one object for the whole process.** `lib/server/env.js:13` declares
   `const env = {…}` at module scope and `config()` returns *that* object. So §5.2 item 3 is not
   "audit every read of `env.settings`" — **there is only one `env` to read**, and a second
   `config()` overwrites the first's values in place. Two contexts cannot hold different
   settings.
2. **The MongoDB connection is a process singleton keyed by nothing.**
   `lib/storage/mongo-storage.js:7` holds one `client`/`db`, `:111` short-circuits on them, and
   T2.5's `STORAGE_NAMESPACE` is resolved once at first connect. Measured: tenant B asks for its
   own namespace and **is handed tenant A's**, while the server logs `Reusing MongoDB connection
   handler`. Latent today (`bootevent` calls `init()` once) and **not** latent under
   `ctxFor(tenantId)`, which is exactly the thing that calls it twice.

The PostgreSQL backend does not have this shape — its isolation is a per-transaction
`set_config` on a pooled connection, so two tenants sharing one pool is the *designed* case
rather than an accident. That contrast is D4 restated as a code property: two deployment targets
over one shared core, and this is one of the places the core is not yet shared.

**T3.4 · Ack/snooze state into storage. — REGRESSION TEST DONE 2026-09-15; the storage move is
DEFERRED to T4.4, with reasons.**

~~replacing `lib/notifications.js:15`'s module-scope map~~ — **the premise was stale on this
branch and the agent checked rather than assumed.** `alarms` was moved inside `init(env, ctx)`
by `9e869662` ("Own notification alarm state per service and clear it on teardown", 2026-09-06)
on the modernization branch. Still accurate for `origin/dev`; not for here.

**What actually remains, established by running it** — three separate `node` processes, same
level and group:

| process | alarms emitted | `lastAckTime` |
|---|---:|---|
| acknowledges, then evaluates | **0** | set |
| a sibling process | **1** | 0 |
| a restart of the acknowledging process | **1** | 0 |

So an acknowledgement is invisible to a sibling and does not survive a restart.

**The storage move is declined here, for four reasons rather than a shrug:**

1. **PostgreSQL has nowhere to put it** — the emitted DDL is one table, `entries`. A
   `(tenant, level, group)` row is schema work, not this task.
2. **The interface has no compare-and-set and declines to promise one.** `ack`'s guard is a
   read-modify-write; `updateOne` takes an *identifier*, not a predicate; and {S} §9 states
   outright that the interface does not promise atomicity across operations on both backends,
   because plenty of self-hosters run a standalone `mongod`. **T4.4 already hash-partitions the
   evaluator "for per-tenant ordering of ack state"** — the design knows this needs serialisation
   it cannot get here.
3. **The alarm path is synchronous end to end** (`bootevent.js:330-332` calls
   `initRequests`/`checkNotifications`/`process` inline in a bus listener). Storage-backed state
   makes it async and reorders the one path where **an alarm that does not fire is the worst
   outcome this software has**, with no corpus exercising the new ordering.
4. **There is no tenant to key by yet.** Under T3.3 the ctx *is* the tenant, so a redundant
   tenant key in `getAlarm` would imply the map is safe to share — the opposite of the property
   being pinned.

**Redis was read and rejected as the home, on this programme's own terms**: {M} §7.6 scopes keyv
to *ephemeral* tenant-keyed state and classifies ack/snooze as the durable part — and `ns-single`
is "the existing server, unchanged", so a self-hoster should never have to stand up Redis to keep
a snooze.

*Recommendation carried to T4.4*: do the move where the async path, the tenant id and a real
table all exist at once, and specify the write as a **single conditional upsert**
(`INSERT … ON CONFLICT … WHERE`) rather than read-then-write, so `ack`'s "already snoozed" guard
survives concurrency.

**The durable deliverable is the test**, which is what this task was really for: nothing recorded
*why* the state is per-instance, so a refactor could hoist it back with green CI.
`tests/notification-tenant-isolation.test.js` — three cases, one per route to somebody else's
alarm, with failure messages that explain the tenancy reason rather than the mechanics.
Verified independently: hoisting `alarms` back to module scope fails three tests, reading *"a
shared alarm map makes one person's snooze silence a different person's hypo alarm"*. Hoisting
`requests` fails two — **and the pre-existing lifecycle test passes through the whole of that
second break**, which is what makes the new file worth having rather than duplicative.

**T3.5 · Tenant socket rooms** and tenant-bound socket authorization, including
`lib/api3/alarmSocket.js`, which currently emits to the **whole namespace with no room at all**
— a worse leak than `DataReceivers`.

### Phase 4 — the feed

**T4.1 · Slot reader** — the spine. Emits `NOTIFY` itself; **never a trigger** ({DB} §9.4: a
trigger puts `NOTIFY` inside the ingest transaction, and a wedged realtime process would
eventually stop CGM uploads).
**T4.2 · Bounded aggregate poll** — the backstop, ~1.02 ms per sweep ({DB} §8.4).
**T4.3 · `ns-realtime`** — `LISTEN` per served tenant, direct connection **not through
pgbouncer** ({DB} §10.3: transaction-mode pooling accepts `LISTEN` and silently delivers
nothing).
**T4.4 · `ns-evaluator`** — hash-partitioned by tenant for per-tenant ordering of ack state.

---

## 7. What is still unmeasured, and which task it lands on

| gap | lands on | why it matters |
|---|---|---|
| **No TLS or auth in any database measurement** | T2.5 | Both add CPU to the per-operation term the whole cost model rests on; `ns-api` has the least headroom (110 ms/s of 300) |
| **Writes never measured** — every arm is a read | T2.5 | Ingest is what uploaders actually generate |
| **Working set past cache size** | T2.5 | {DB} §7's 400-tenant run is where cache pressure *starts* |
| **pgbouncer + `set_config(is_local)`** | T2.5 | {M} §6.7 says the pooler may be required; its interaction with transaction-scoped binding is untested |
| **Active fraction (15 %)** is an assumption | — | Drives A and B far harder than C; a real hoster's figure would sharpen the cost model |
| **Vendor rate limits** (EXP-MT-051) | T0.4 | Needs real credentials; the 9,700-account machinery figure is a ceiling the real answer sits well below |
| **Reconnect storms, `UNLISTEN` churn** | T4.3 | The interesting realtime case, and not covered |

## 8. How to read a number from this programme

Four passes each found a term the previous one missed — the load cycle went 0.03 ms → 9.5 → 6.27
→ 8.77 as the fixture defect, then `cache.insertData`, then the database were found. **Assume
the next pass finds another one.** Two of the most decision-relevant findings arrived as
accidents rather than as the thing being measured: the file-descriptor `fassert()` at 50 tenant
databases, and `LISTEN` silently returning nothing through pgbouncer.

Every figure here carries a scope limit in its source document's §L. **The ordering of options
has been stable across every pass; the absolute numbers have not.** Quote the ordering.
