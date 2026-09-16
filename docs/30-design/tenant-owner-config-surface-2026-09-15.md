# The tenant-owner configuration surface — T3.0's missing schema

**Status: DRAFT for maintainer review.** This is a design specification, not landed work.
It proposes DDL, a credential model and a change list against code that is already merged on
`seam/t1-2-storage-interface`. Nothing in it has been implemented, and the DDL in §A has **not**
been executed against a PostgreSQL server (see §G.1 — no credentialled server was reachable from
this session). Sections marked **DECISION** need the maintainer's yes before anyone writes code;
sections marked **CONSEQUENCE** follow mechanically from D13/D14/D15 and need no new decision.

**Audience: contributors.** It is fully technical throughout. The operator- and user-facing text
this work implies — what a tenant owner is told when their alarm thresholds are rejected, what a
self-hoster reads before deciding whether to move — is *not* in here and is named as separate work
in §E.4. Two paragraphs of it touch alarm behaviour (§A.3, §B.5); those are flagged because getting
them wrong means somebody's low-glucose alarm does not fire.

| | |
|---|---|
| Measured against | `externals/work/crm-seam` @ `81a1f6ce` (`seam/t1-2-storage-interface`), and `externals/work/crm-bf-auth` @ `64db1f35` for `lib/authorization/storage.js` |
| Repo head when written | `08753474` (re-verified and completed at this head; §0-§B were first drafted at `75c38a17` and every number in them has been re-measured since) |
| Decisions assumed | D1, D3, D4, D5, D7, D8, D10, D11, D12, **D13, D14, D15** |
| Amends | T3.1, T3.2, T3.3 (all `DONE-EXCEPT`), and `lib/authorization/index.js:169-173`, which predates this programme |
| Blocked by | nothing |
| Adversarially reviewed | 2026-09-15 at repo head `08753474`, against `crm-seam` @ `81a1f6ce` and `crm-bf-auth` @ `64db1f35`. Corrections are marked in place; see the index immediately below |

### Adversarial-review index (2026-09-15)

A second agent re-ran or re-read every claim this document's conclusions rest on. **What held:**
§0.2's `settingsFor` gap, all of §0.3(i)-(iii) including the JWT-with-no-tenant-claim finding
(re-executed, all six arms plus controls), §A.3's mmol/mg-dL control pair (re-executed, 56/81/180/252
against 3.1/4.5/10/14), every line citation in §C, §D and §F, §A.1's reading of `platform.sql`,
§B.5(i)'s two HSTS spellings (re-executed), §B.5(ii), §B.6, and the whole of §H.4 — the API v3
autoprune finding — which reproduces line for line. The union of **247** reproduces exactly.

**What did not, and where the correction is:**

| # | claim | where corrected |
|---|---|---|
| 1 | `{"s3prefixes":35}` published as measured output; the script returns **37**, and `s2` is 51 under a regex that matches the double quotes `env.js` actually uses | §B.1 table, §G.3 note |
| 2 | webhook's four reads are "at module scope … once, at require time" — they are inside the exported plugin factory | §B.2 gap 1, §H.1 |
| 3 | §B's grep gate cannot see `process.env['X']`, so it missed gap 3 — the largest gap and §H.4's defect — entirely | §B "done" block |
| 4 | §B.4's arithmetic double-counts `TREATMENTS_AUTH` and `CI`, undercounts `PUMP_*` by one, and leaves `MONGODB_COLLECTION` in no class. The surface is **277**, not 258 | §B.4 reconciliation note |
| 5 | twelve `ADMIN_*`/`FEED_*` variables read by the hosted entrypoints appear in no source, no gap and no total | §B.2 gap 5 (new) |
| 6 | `tenant_settings_no_proto`'s `?|` is top-level only; the code check recurses. The database is weaker than the comment claims | §A.2 reviewer note |
| 7 | `tenant_settings_thresholds_mgdl` accepts a **partial** mmol override, because a CHECK passes when its expression is NULL — so §A.3's backstop is not yet there | §A.2 reviewer note, §A.3 defence 1 |
| 8 | `verifyThresholds()` described as a check that "passes"; it is a **silent rewriter** of alarm thresholds | §A.3, §E.4 item 2b, §H.7 (new) |
| 9 | §E.1's bootstrap inserts cannot execute against §A.2's `FORCE` RLS with no tenant bound — **blocking** | §E.1 blocking note, J12 |
| 10 | "if it is lost, it is rotated" — rotation requires the lost credential, and §F.1 forbids the admin plane a recovery route | §E.1, §I.7, J13 |
| 11 | a migration with three one-way doors and no rollback | §E.2a (new) |
| 12 | two stale line citations inside the DDL comments (`storage.js:15,:218`; `api3/index.js:85`) | §A.2 |

Nothing in §A has been executed against PostgreSQL by either author — findings 6 and 7 are read off
PostgreSQL's documented semantics, not off a server, and §G.1 was already honest about that. They
are the first two things the §A harness must test.

---

## 0. The premise, and what is actually missing

The maintainer's correction of 2026-09-15 is the premise:

> Per-tenant settings, API secret and plugin configs MUST come from the database, administered by
> the tenant owner. Environment-sourced config is the single-tenant bootstrap only. This is WHY
> D5's entrypoints are separate — different bootstrapping, not just different process topology.

### 0.1 Three interfaces, not two

| # | interface | who | where | state |
|---|---|---|---|---|
| 1 | hosting-operator → cohort | the hoster | D7's admin plane, own process, own port, no credential, secured by unreachability | **built** (T3.2: `bin/admin.js`, `lib/admin/*`) |
| 2 | **tenant owner → that tenant's runtime config** | the person whose site it is | the consumer interface, under RLS | **this document. No schema, no task, no code.** |
| 3 | single-tenant Nightscout | a self-hoster | `process.env`, read by `lib/server/env.js` | **unchanged, permanently first-class (D1, D4)** |

Interface 3 acquires **no** database dependency for its configuration from this work. That is not a
courtesy; it is D1 and it is the reason §B classifies rather than migrates. `config()` keeps reading
`process.env` and keeps being the only thing the `single` entrypoint reads.

### 0.2 The gap is concrete and is one function argument wide

`lib/server/tenant-context.js` already has the hook. `createContextCache` accepts
`options.settingsFor`, documented at line 353 as `(tenant) => {settings, extendedSettings}`, and
`ctxFor` calls it at line 448 to supply `deriveEnv`'s overrides. But `fromEnv` (lines 495-504)
passes only `base`, `max` and `ttl`. `settingsFor` therefore falls through to its default at line
391 — `function none () { return undefined; }` — so `deriveSettings` receives no overrides and every
tenant is handed a private *copy of the deployment's environment-sourced settings*.

**That is exactly what D15 forbids**, and it is a four-line hole rather than an architectural one.
What is missing is the thing `settingsFor` would read from. This document specifies that thing.

### 0.3 Corrections to the premises this task was given

Three statements this task rests on do not survive measurement — two from the briefing, and one
that is in no document at all. All three make the task *larger*, not smaller.

**(i) D14 does not kill BF-25 as a class on its own.** It kills the JWT half. Measured on
`crm-seam`: a token signed with tenant A's key returns `null` from `enclave.verifyJWT` under tenant
B's key, so `tenantClaim` returns `null` and `credentialRefusal` refuses — the promised signature
failure. But BF-25's actual vector is an **opaque access token in the request body**, and an opaque
token has no signature to fail. `lib/authorization/index.js:192-194` resolves it against
`storage.doesAccessTokenExist`, which reads the **process-wide** `storage.subjects` array.
Per-tenant signing keys do not touch that path. Killing BF-25 as a class needs D14 *and* the subject
store moved under RLS (§C.4). Stating D14 alone as the structural fix would leave the larger half of
the vector open while the register entry reads closed.

**(ii) D13, taken literally, breaks access-token derivation — silently, not loudly.** Subject access
tokens are *derived from the deployment API secret*: `lib/authorization/storage.js:227` on `crm-bf-auth` calls
`env.enclave.getSubjectHash(subject._id.toString())` (the same call is `storage.js:211` on `crm-seam`,
which does not carry bf/auth), and `getSubjectHash` (`enclave.js:71-76`) hashes
`secrets[apiKeySHA1]` — the SHA-1 of `API_SECRET` — together with the id. Measured: with no API key
set, `getSubjectHash` throws `TypeError: The "data" argument must be of type string …`; with one
set it returns a hash (control). The throw is not reached, because the line above it guards the whole block
with `if (env.enclave.isApiKeySet())` (`storage.js:226` on `crm-bf-auth`, `:210` on `crm-seam`). So under D13 every subject loads with **no**
`accessToken`, `digest` or `accessTokenDigest` at all, and the first token lookup reaches
`subject.accessTokenDigest.indexOf(...)` on `undefined` (`storage.js:326` on `crm-bf-auth`, `:310`
on `crm-seam`).

D13 is therefore not "do not set `API_SECRET`". It is "**re-root the subject hash on the tenant's own
credential**", and that is T3.0 work nobody has written down. §C.3 specifies it.

**(iii) The deployment does not put a tenant claim in the tokens it mints, so under `multi` with
today's defaults it refuses its own.** This one is not a correction to the brief — it is not in any
document — and it is the finding with the shortest path to a visible failure.

`lib/authorization/index.js:289` is the only caller of `signJWT` in the tree
(`grep -rn signJWT lib/ bin/` returns that line and the definition, nothing else):

```js
const token = env.enclave.signJWT({ accessToken: subject.accessToken });
```

The payload has one field. `tenantClaim` (`tenant-middleware.js:139-151`) requires
`payload.tenant` to be a non-empty string and returns `null` otherwise; `credentialRefusal`
(`:181-192`) then returns `MSG_NO_CLAIM` because `requireTokenClaim` defaults to true
(`:208`). Executed against the real modules, with the exact payload line 289 mints and a control:

| token payload | `tenantClaim` | `credentialRefusal` |
|---|---|---|
| `{accessToken}` — what the deployment mints today | `null` | `"This credential does not name a Nightscout site."` |
| `{accessToken, tenant}` — control | the tenant id | `null` (proceeds) |

So the claim check and the minting path have never been run against each other end to end. T3.1's
tests supply hand-built tokens that carry a `tenant` field; nothing in the tree produces one. The
consequence under `TENANCY_MODE=multi` is not a leak — it is that **every authenticated request
using a Nightscout-issued JWT is refused**, which is the safe direction and is why it has not bitten
anyone: nothing runs `multi` yet. It still has to be fixed by the same task that introduces the
per-tenant key, because that task is the one that decides what goes in the payload. §D.1, and
proposed register entry §H.5.

---

## A. The data model

### A.1 What exists today, and what it does not carry

`lib/admin/platform.sql` (78 lines, read in full) holds exactly two tables. GT3's finding is
confirmed by reading it:

- `tenants` — `id`, `slug`, `display_name`, `is_active`, `created_at`, `last_reading_at`.
  **Deliberately not RLS-protected**, and the file explains why at lines 15-22: it is read to
  *decide* which tenant a request is, which happens before a tenant context exists.
- `tenant_members` — `id`, `tenant_id`, `subject_id uuid NOT NULL`, `permissions text[]`, `label`,
  `last_used_at`. RLS-protected with the same policy predicate as the emitted document tables.

There is **no** configuration, **no** secret, **no** signing key, and `subject_id` references
nothing. It cannot: `auth_subjects._id` is modelled as a `string`
(`specs/nsschema/auth_subjects.model.json`, root children), because it is a Mongo ObjectId hex on
one backend and arbitrary text on the other. A `uuid` column cannot carry a 24-character hex
ObjectId, so `subject_id` is not merely missing a `REFERENCES` clause — **its type is wrong for the
thing it names**. §D.2 says what to do about that.

### A.2 What is ADDED (four tables, no ALTER to `tenants`)

Nothing in `tenants` changes. Everything below is additive, which matters because `bin/admin.js` is
the only writer of `tenants` and its `ensureSchema` compares against `PLATFORM_DDL` read from this
same file (`platform-store.js:53`, `120-158`).

```sql
-- =====================================================================
-- T3.0 · the tenant-owner configuration surface.
--
-- Interface 2 of three (see the design document). The hoster's plane is
-- bin/admin.js on an unrouted port (D7); the self-hoster's plane is the
-- process environment and is not affected by anything in this file (D1,
-- D15). What follows is what the TENANT OWNER administers, on the
-- consumer interface, under RLS.
--
-- WHY THESE ARE PLATFORM TABLES AND NOT A DOCUMENT COLLECTION. The tree
-- already has an api3 `settings` collection (registered in the
-- enabledCollections list at lib/api3/index.js:71 -- an earlier draft of
-- this comment cited :85, which is inside the dev-only /test route)
-- and it is the wrong home: specs/nsschema/settings.model.json records
-- that "nothing in cgm-remote-monitor writes a document here at all" and
-- that it is an open body with no server-side schema. Configuration is
-- read during CONTEXT BUILD, before any document API is on the stack, and
-- it is the one row in the system whose contents decide when an alarm
-- fires. It gets constraints, and a collection whose contract is "open
-- body" cannot carry them.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. tenant_settings -- the site, as its owner configures it.
-- ---------------------------------------------------------------------
CREATE TABLE tenant_settings (
  tenant_id  uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,

  -- camelCase OVERRIDE names: exactly the shape tenant-context.js's
  -- deriveSettings() already takes as `options.settings`, including a
  -- nested `thresholds` object. NOT the environment spelling. The env
  -- spelling is a transport, and storing it would oblige this table to
  -- know about envNameOverrides (UNITS -> DISPLAY_UNITS, env.js:246-248)
  -- for as long as the table exists.
  settings   jsonb NOT NULL DEFAULT '{}'::jsonb,

  -- Per-plugin, non-secret. The shape deriveEnv() takes as
  -- `options.extendedSettings`: {"pushover": {"apiToken": ...}} with the
  -- inner keys camelCased exactly as findExtendedSettings() produces them
  -- (env.js:356-387). Secrets do NOT live here -- see tenant_secret.
  extended   jsonb NOT NULL DEFAULT '{}'::jsonb,

  -- The tenant's DISPLAY unit. Display only: thresholds below are always
  -- stored in mg/dL, whatever this says. See the constraint and the
  -- design document's A.3 for why that is not a preference.
  units      text NOT NULL DEFAULT 'mg/dl'
             CHECK (units IN ('mg/dl', 'mmol')),

  -- settings.js resolves ENABLE/DISABLE/DEFAULT_FEATURES/ALARM_TYPES into
  -- a final `enable` array by a procedure deriveSettings() does NOT re-run
  -- (tenant-context.js:236-241 says so). So the RESOLVED list is stored,
  -- not the operator's ENABLE string, and the resolution happens once at
  -- write time where a person can be shown what it produced.
  enabled_plugins text[] NOT NULL DEFAULT '{}',

  updated_at timestamptz NOT NULL DEFAULT now(),
  -- Which tenant member last wrote this. Nullable because the first row
  -- is written by the bootstrap (E.1), before any member exists.
  updated_by uuid REFERENCES tenant_members(id) ON DELETE SET NULL,

  -- ALARM SAFETY, AT THE STORAGE BOUNDARY.
  --
  -- The deployment path converts mmol thresholds to mg/dL
  -- (settings.js:290-296, gated on `bgHigh < 50`). deriveSettings() does
  -- NOT: its own comment at tenant-context.js:236-241 says overrides "are
  -- NOT re-run through settings.js's mmol conversion". Measured on
  -- crm-seam: deriveSettings(base, {units:'mmol', thresholds:{bgHigh:14,
  -- bgTargetTop:10, bgTargetBottom:4.5, bgLow:3.1}}) stores those numbers
  -- verbatim and verifyThresholds() does not object, because 3.1 < 4.5 <
  -- 10 < 14 is a valid ORDER. The control -- the same four numbers through
  -- the deployment path -- yields 56/81/180/252. An urgent-low threshold
  -- of 3.1 mg/dL can never fire.
  --
  -- The ordering check alone cannot catch that, so the RANGE check is the
  -- load-bearing half. A plausible mmol set is 3-15; a plausible mg/dL set
  -- is 50-400. 20 is below any real mg/dL threshold and above any real
  -- mmol one.
  -- REVIEWER NOTE (adversarial review, 2026-09-15). THIS CONSTRAINT DOES
  -- NOT YET DO WHAT A.3 SAYS IT DOES, and A.3 is the safety section.
  -- Two holes, neither executable here because no PostgreSQL was reachable
  -- (G.1), both decidable from PostgreSQL's documented semantics:
  --
  --  (1) A CHECK is SATISFIED when the expression is TRUE *or NULL*. A
  --      PARTIAL thresholds override -- which applyOverrides explicitly
  --      supports and tenant-context.js:193-196 exists to support ("a
  --      tenant that sets bgLow must not thereby drop bgHigh") -- leaves
  --      the absent paths as SQL NULL, so the AND chain evaluates to NULL
  --      and the row is ACCEPTED. `{"thresholds":{"bgHigh":14}}`, an mmol
  --      urgent-high on its own, is stored. That is exactly the case A.3
  --      is the backstop for, and the backstop is not there.
  --  (2) PostgreSQL does not guarantee AND/OR evaluation order, so the
  --      `jsonb_typeof(...) = 'number'` guards cannot be relied on to run
  --      before the `::numeric` casts. A thresholds object holding a
  --      STRING can raise `invalid input syntax for type numeric` instead
  --      of a clean constraint violation -- an error the write boundary
  --      has to translate, not one it can report as "we refused this".
  --
  -- The fix is a per-key form: require all four together (`? 'bgLow' AND
  -- ? 'bgTargetBottom' AND ...`) so a partial override is refused outright
  -- and normalised at the write boundary instead, and do the numeric work
  -- inside an IMMUTABLE function rather than a bare AND chain. That is a
  -- DECISION, because refusing partial overrides is a behaviour choice
  -- and not a syntax fix: see the new row J11.
  CONSTRAINT tenant_settings_thresholds_mgdl CHECK (
    settings #> '{thresholds}' IS NULL
    OR (
          jsonb_typeof(settings #> '{thresholds,bgLow}')           = 'number'
      AND jsonb_typeof(settings #> '{thresholds,bgTargetBottom}')  = 'number'
      AND jsonb_typeof(settings #> '{thresholds,bgTargetTop}')     = 'number'
      AND jsonb_typeof(settings #> '{thresholds,bgHigh}')          = 'number'
      AND (settings #>> '{thresholds,bgLow}')::numeric >= 20
      AND (settings #>> '{thresholds,bgHigh}')::numeric <= 600
      AND (settings #>> '{thresholds,bgLow}')::numeric
        < (settings #>> '{thresholds,bgTargetBottom}')::numeric
      AND (settings #>> '{thresholds,bgTargetBottom}')::numeric
        < (settings #>> '{thresholds,bgTargetTop}')::numeric
      AND (settings #>> '{thresholds,bgTargetTop}')::numeric
        < (settings #>> '{thresholds,bgHigh}')::numeric
    )),

  -- `__proto__`, `constructor` and `prototype` are refused in code
  -- (tenant-context.js:149) because settings overrides are tenant-
  -- controlled data. A second spelling of a refusal is a second thing
  -- that can drift, so the database refuses them too -- the same argument
  -- platform.sql already makes for the `slug` CHECK at lines 30-35.
  -- REVIEWER NOTE (adversarial review, 2026-09-15): AS WRITTEN THIS IS
  -- WEAKER THAN THE CODE IT CLAIMS TO MIRROR, and the comment above
  -- overstates it. `jsonb ?| text[]` tests TOP-LEVEL keys only.
  -- applyOverrides (tenant-context.js:173-198) RECURSES and refuses a
  -- forbidden key at every depth, so `{"thresholds": {"__proto__": 1}}`
  -- passes this constraint and is refused by the code. That is drift in
  -- the direction the comment says it prevents. Either replace this with
  -- a recursive key test (a jsonb_path_exists over `$.**.__proto__` and
  -- its two siblings, or a small IMMUTABLE function) or delete the claim
  -- that the database and the code hold the same line. Do NOT land it in
  -- this form with the comment above unchanged.
  CONSTRAINT tenant_settings_no_proto CHECK (
    NOT (settings  ?| ARRAY['__proto__','constructor','prototype']) AND
    NOT (extended  ?| ARRAY['__proto__','constructor','prototype'])),

  CONSTRAINT tenant_settings_are_objects CHECK (
    jsonb_typeof(settings) = 'object' AND jsonb_typeof(extended) = 'object')
);

ALTER TABLE tenant_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_settings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_settings_tenant_isolation ON tenant_settings
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);


-- ---------------------------------------------------------------------
-- 2. tenant_secret -- credentials the tenant holds, and the ones the
--    deployment holds ON BEHALF OF the tenant.
--
-- SEPARATE FROM tenant_settings ON PURPOSE, for three reasons that are
-- each independently sufficient:
--   (a) admin-plane export. platform-store.js:186-197 discovers tenant-
--       scoped tables by looking for a `tenant_id` column and subtracting
--       a one-element deny list, NOT_TENANT_DATA = {'tenant_members'}.
--       Anything else with a tenant_id is streamed verbatim by
--       exportTenant(). A secret must not be in that stream by default.
--   (b) a settings read happens on every context build (cache miss); a
--       secret read happens at boot and at rotation. Different lifetimes.
--   (c) column-level grants. A future read-only reporting role can be
--       given tenant_settings and not this.
-- ---------------------------------------------------------------------
CREATE TABLE tenant_secret (
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

  -- 'root'        -- the tenant's own API secret, D13's replacement for
  --                  the deployment API_SECRET. Grants this tenant's
  --                  root shiro, scoped to this tenant, and NOTHING else.
  -- 'jwt'         -- D14's per-tenant JWT signing key.
  -- 'subject-salt'-- the value getSubjectHash() is re-rooted on (C.3).
  -- 'plugin:<n>'  -- one row per plugin holding third-party credentials
  --                  (Pushover, Maker, Dexcom Share, LibreLinkUp, ...).
  kind        text NOT NULL
              CHECK (kind = 'root' OR kind = 'jwt' OR kind = 'subject-salt'
                     OR kind ~ '^plugin:[a-z0-9]([a-z0-9-]*[a-z0-9])?$'),

  -- Monotonic. Rotation ADDS a version; it does not overwrite one, because
  -- BF-17's lesson is that a credential already issued keeps working until
  -- something deliberately stops it, and you cannot deliberately stop what
  -- you have overwritten and can no longer name. See E.3.
  version     integer NOT NULL DEFAULT 1 CHECK (version >= 1),

  -- 'active'   -- mint and verify with this
  -- 'retiring' -- verify with this, do not mint. The overlap window.
  -- 'revoked'  -- neither. Kept so an audit can say when it stopped.
  state       text NOT NULL DEFAULT 'active'
              CHECK (state IN ('active','retiring','revoked')),

  -- Ciphertext. Never a plaintext credential, never a reversible encoding
  -- of one. What wraps it is the hoster's key-encryption key -- see the
  -- design document's C.5, which is a DECISION and not settled here.
  material    bytea NOT NULL,
  -- Names the KEK that wrapped `material`, so a KEK rotation can find the
  -- rows it still has to rewrap. An identifier, not a key.
  key_ref     text NOT NULL,

  created_at  timestamptz NOT NULL DEFAULT now(),
  -- When a 'retiring' row stops verifying. NULL for 'active'.
  expires_at  timestamptz,
  -- Set when state becomes 'revoked'. Answers "was this still live on the
  -- day in question", which is the only question an incident ever asks.
  revoked_at  timestamptz,

  PRIMARY KEY (tenant_id, kind, version),

  CONSTRAINT tenant_secret_revoked_has_time CHECK (
    (state = 'revoked') = (revoked_at IS NOT NULL)),
  CONSTRAINT tenant_secret_retiring_has_expiry CHECK (
    state <> 'retiring' OR expires_at IS NOT NULL)
);

-- At most one ACTIVE secret of each kind per tenant. A partial unique
-- index rather than a trigger: two concurrent rotations racing is exactly
-- the case a trigger's read-then-write loses and an index does not.
CREATE UNIQUE INDEX tenant_secret_one_active
  ON tenant_secret (tenant_id, kind)
  WHERE state = 'active';

ALTER TABLE tenant_secret ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_secret FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_secret_tenant_isolation ON tenant_secret
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);


-- ---------------------------------------------------------------------
-- 3. tenant_subject -- the tenant's own subjects and roles.
--
-- This is what makes BF-25 a CLASS kill rather than an instance kill.
-- Today lib/authorization/storage.js keeps storage.subjects as ONE
-- process-wide array loaded at boot (storage.js:18 declares it, :209
-- replaces it wholesale on every reload; an earlier draft of this comment
-- cited :15 and :218, which are `var storage = { }` and a closing brace),
-- so an opaque
-- access token resolves to its subject no matter which tenant's host it
-- arrived on -- and an opaque token carries no signature for D14's
-- per-tenant key to fail. Scoping the SUBJECT STORE is the other half.
--
-- The field list is bf/auth's allow-list (storage.js:50-51,
-- SUBJECT_FIELDS / ROLE_FIELDS) and deliberately excludes accessToken,
-- accessTokenDigest and digest: bf/auth establishes that those three are
-- DERIVED on every load and must not be stored.
-- ---------------------------------------------------------------------
CREATE TABLE tenant_subject (
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  -- TEXT, not uuid. auth_subjects._id is a string on both backends
  -- (specs/nsschema/auth_subjects.model.json), and a tenant imported from
  -- a self-hosted MongoDB brings 24-hex ObjectIds with it.
  subject_id  text NOT NULL,
  name        text NOT NULL,
  roles       text[] NOT NULL DEFAULT '{}',
  notes       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, subject_id),
  -- Scoped, not global: two tenants imported from two deployments can
  -- legitimately carry the same subject name. Same argument the emitted
  -- entries table makes for PRIMARY KEY (tenant_id, "_id").
  UNIQUE (tenant_id, name)
);

CREATE TABLE tenant_role (
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name        text NOT NULL,
  permissions text[] NOT NULL DEFAULT '{}',
  notes       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, name)
);

ALTER TABLE tenant_subject ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_subject FORCE ROW LEVEL SECURITY;
ALTER TABLE tenant_role    ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_role    FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_subject_tenant_isolation ON tenant_subject
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

CREATE POLICY tenant_role_tenant_isolation ON tenant_role
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
```

### A.2b What is ALTERED

Exactly one thing, and it is in code rather than DDL:

```js
// lib/admin/platform-store.js:51 -- today
const NOT_TENANT_DATA = new Set([ 'tenant_members' ]);
// required by this change
const NOT_TENANT_DATA = new Set([ 'tenant_members', 'tenant_secret' ]);
```

`tenantScopedTables()` (`platform-store.js:186-197`) selects every relation in the schema carrying a
`tenant_id` attribute and subtracts that set. It feeds both `tenantDataCounts` — used to show a
hoster what a deletion will destroy — and `exportTenant`. Adding `tenant_secret` without adding it
to the deny list means **a tenant export writes that tenant's wrapped root credential, signing key
and every plugin credential into the export stream**. `tenant_settings`, `tenant_subject` and
`tenant_role` should *stay* in the export: a tenant's configuration and role list are part of what
"give me my site" means, and excluding them would make the export useless for migration. That split
is the point of putting secrets in their own table.

`tenant_members.subject_id` is discussed in §D.2; the recommendation there is to change its type,
which is an ALTER, and it is a **DECISION** because it touches a shipped table.

### A.3 The one thing in §A that is about safety rather than tidiness

`tenant_settings_thresholds_mgdl` is not a validation nicety. Measured on `crm-seam`, with a
control:

| path | input | stored `thresholds` |
|---|---|---|
| deployment (`eachSettingAsEnv`) | `UNITS=mmol BG_HIGH=14 BG_TARGET_TOP=10 BG_TARGET_BOTTOM=4.5 BG_LOW=3.1` | `{bgHigh:252, bgTargetTop:180, bgTargetBottom:81, bgLow:56}` |
| per-tenant (`deriveSettings`) | `{units:'mmol', thresholds:{bgHigh:14, bgTargetTop:10, bgTargetBottom:4.5, bgLow:3.1}}` | `{bgHigh:14, bgTargetTop:10, bgTargetBottom:4.5, bgLow:3.1}` |

Both rows above were re-executed during adversarial review on `crm-seam` @ `81a1f6ce` and both
reproduce exactly.

`verifyThresholds()` runs in the second case (tenant-context.js:242) and passes, because the numbers
are correctly *ordered*. The result is a site whose urgent-low alarm is set at 3.1 mg/dL and whose
urgent-high is at 14 mg/dL — for a person with diabetes, an alarm configuration that can never fire
in either direction, arrived at by entering exactly the numbers their clinic uses. Nothing in the
process says so.

**And `verifyThresholds` is not an inert check — it is a SILENT REWRITER, which this section
originally did not say.** Read at `settings.js:302-324`: when the ordering invariant fails it does
not throw and does not refuse. It *mutates* the offending threshold to a neighbour ±1 and emits a
`console.warn` — `bgHigh` becomes `bgTargetTop + 1`, `bgLow` becomes `bgTargetBottom - 1`, and so
on. So the failure mode for a partial mmol override such as `{"thresholds":{"bgHigh":14}}` is not
"rejected" and not "stored as 14". It is: the person's urgent-high, which they meant as 14 mmol/L
(≈252 mg/dL), is silently replaced with `bgTargetTop + 1` = **181 mg/dL**, their site runs, the
alarm fires at a number they never chose, and the only trace is a line in a server log nobody is
reading. That is the silent-failure shape this programme cares about, and it is why the write
boundary must echo back the stored numbers (defence 2 below) rather than trusting either the
constraint or `verifyThresholds` to have preserved them.

Three defences, and all three are wanted:

1. **The constraint above**, so the row cannot be written at all. A rejected write is a visible
   failure; a stored 3.1 is not. **As drafted the constraint only achieves this when all four
   threshold keys are present in the same write** — see the reviewer note beside it in §A.2. A
   partial override slips through on SQL NULL semantics. That is unfinished work, not a detail.
2. **Normalise at the write boundary**, in whatever serves the tenant-admin PUT: convert to mg/dL
   using `units` before storing, the same way `settings.js:290-296` does, and echo back what was
   stored so the person can see 56 and not 3.1. The constraint is the backstop for the day the
   normalisation is skipped.
3. **Surface `verifyThresholds`'s rewrites instead of logging them.** Any threshold it changes must
   come back to the tenant owner as a visible message naming the old and the new value, because the
   thing it silently changes is when an alarm fires. Today the only evidence is `console.warn`.
   Proposed register entry §H.7.

The `< 50` heuristic settings.js uses is *not* reproduced in the constraint. It is a heuristic about
unlabelled data; this table has a `units` column and can be explicit.

**Done, §A:**

```
node tools/qc/tenant-config-arm.js schema --root externals/work/crm-seam
```
New harness (§G.2). It must: apply `platform.sql` into a throwaway schema; assert the four tables
exist with RLS **enabled and forced**; assert the threshold constraint rejects
`{"thresholds":{"bgLow":3.1,"bgTargetBottom":4.5,"bgTargetTop":10,"bgHigh":14}}` and accepts
`{"thresholds":{"bgLow":56,"bgTargetBottom":81,"bgTargetTop":180,"bgHigh":252}}`; assert
`tenant_secret_one_active` rejects a second active row of the same kind; and — the non-vacuity
pairing this project requires — re-run each assertion against a deliberately weakened copy of
`platform.sql` with the constraint removed, and require it to go red.

```
node -e "const s=require('./lib/admin/platform-store'); \
  process.exit(s.NOT_TENANT_DATA.has('tenant_secret') ? 0 : 1)"
```
`NOT_TENANT_DATA` must be exported for this to be checkable; it is module-private today. Exporting
it is part of the change.

---

## B. The mapping from today's environment variables

This section is the spec's real substance. An incomplete enumeration is a spec that silently drops
an operator's setting, so the method comes before the answer.

### B.1 Coverage method, stated so it can be attacked

**First, a correction to the task this section discharges.** The plan's T3.0 step 1 asks for
"every `SETTINGS_*` variable". **There is no such family.** Measured across `lib/server/env.js`,
`lib/settings.js` and `README.md`, the string `SETTINGS_` occurs exactly once, at `env.js:215`, as
part of `MONGO_SETTINGS_COLLECTION` — a storage variable, per-deployment, unrelated. An agent
enumerating `SETTINGS_*` literally would find one name and conclude the surface was trivial.
Nightscout's configuration variables have **no common prefix**: they are named after what they
configure (`BG_HIGH`, `CUSTOM_TITLE`) or after the plugin that reads them (`PUSHOVER_API_TOKEN`),
and the only closed enumeration is the one below.


The surface was derived **from the code**, not from the README, and then the README was used only as
a *fourth* source to catch names the code reads indirectly. Four sources:

| # | source | how it was enumerated | count |
|---|---|---|---|
| 1 | the settings layer | ran `lib/settings.js`'s own `eachSettingAsEnv` with a recording accessor, so the list is whatever `nameFromKey(…, 'env')` actually produces, including `thresholds` and the `enable`/`disable`/`alarmTypes` triple | **70** |
| 2 | `lib/server/env.js` | regex over literal string arguments to `readENV`/`readENVTruthy`/`readENVRaw`/`readEnvFile`, plus `shadowEnv['X']` and `process.env.X` reads inside that file | **43** |
| 3 | plugin extended settings | `findExtendedSettings` (`env.js:356-387`) scans `process.env` for `<ENABLED_PLUGIN>_*`, so the closed set is the **prefix** set, not the variable set. Counted as `lib/plugins/*.js` basenames | **37 prefixes** |
| 4 | `README.md` | regex for `[A-Z][A-Z0-9]*(_[A-Z0-9]+)+`, to catch variables sources 1-3 cannot see | **208** |

Union of sources 1, 2 and 4: **247 distinct names**, measured by running the script in §G.3
against `externals/work/crm-seam` (`81a1f6ce`). Source 3 contributes prefixes rather than names and
is not in that union. Source 2's count is sensitive to how the regex is written and the union is
not: every name source 2 finds is also produced by source 1 or matched in the README, so widening
or narrowing that regex moves 51 but leaves 247 alone. That insensitivity is the only reason the
union is quotable at all, and it was re-measured rather than asserted — see the verification note
in §G.3, where the published `s2` and `s3prefixes` figures were corrected and the union was
confirmed under both the narrow and the widened regex.

**247 is not the whole surface.** §B.2 gap 3 adds ten API v3 names none of the four sources can
see; gap 1 adds four `WEBHOOK_*`; gap 2 adds three `AWS_*`; gap 5 adds twelve `ADMIN_*`/`FEED_*`;
and `CI` is in no source's output. The measured total is **277**, not the **258** first published
here — that figure double-counted `CI` and omitted `WEBHOOK_*` and gap 5 entirely. The arithmetic
is in the reconciliation note at the head of §B.4.

**Why source 3 cannot be closed, and what that means for the schema.** `findExtendedSettings`
iterates `process.env` and accepts *any* key beginning with an enabled plugin's name and an
underscore. The README says so explicitly (line 816: "setting `MYPLUGIN_EXAMPLE_VALUE=1234` would
make `extendedSettings.exampleValue` available"). There is no list of legal extended settings
anywhere in the tree, and a third-party plugin invents its own. **Consequence:** `tenant_settings.
extended` must be an open `jsonb` keyed by plugin name. It cannot be a column set, and any schema
that enumerates extended settings will drop a plugin's configuration the first time someone adds
one. This is the same reasoning D11 applies to `devicestatus`.

### B.2 What the method does **not** cover, stated plainly

The four sources above all look at either the settings layer or `lib/server/env.js`. Anything that
reads `process.env` directly is invisible to all four. Measured, by grepping every
`process.env.X` and `process.env['X']` in `lib/` and subtracting `lib/server/env.js` and `NODE_ENV`:

```
lib/plugins/webhook.js:36-39                  WEBHOOK_PROTOCOL HOST PORT PATH
lib/storage/mongo-client-configuration.js:38-40   AWS_ACCESS_KEY_ID SECRET_ACCESS_KEY SESSION_TOKEN
lib/api3/index.js:26-29                       setENVTruthy(varName) -- a GENERIC reader
lib/api3/index.js:70                          CI
```

Three gaps, of which the third was missed by the first pass over this material and is the largest.

1. **Four webhook variables bypass the whole config system.** `lib/plugins/webhook.js:36-39` reads
   `WEBHOOK_PROTOCOL`, `WEBHOOK_HOST`, `WEBHOOK_PORT` and `WEBHOOK_PATH` from `process.env`. They are
   not in `env.js`, and `grep -c WEBHOOK_ README.md` returns 0. Although `findExtendedSettings`
   *would* collect them into `extendedSettings.webhook` when `webhook` is in `settings.enable`, the
   plugin never reads `extendedSettings` — it reads `process.env` directly. Under
   `TENANCY_MODE=multi` every tenant's webhook plugin posts to the same host, and no amount of
   per-tenant configuration changes that until the read site changes. Proposed register entry §H.1.

   > **CORRECTION (adversarial review).** The first version of this paragraph said the four reads
   > happen "at module scope … once, at require time". Measured: lines 36-39 sit INSIDE
   > `module.exports = function webhookPlugin() { … }`, so they run when the factory is invoked —
   > `require('./webhook')(ctx)` at `lib/plugins/index.js:71` and `:106` — not at require time. The
   > conclusion is unaffected, because the read is of `process.env` and not of `ctx`/`env`, so a
   > per-tenant value still cannot reach it. But the stated mechanism was wrong, and it matters for
   > the fix: converting this plugin is an ordinary `ctx.extendedSettings` change at an ordinary
   > call site, not the module-load rewrite the original wording implied.

2. **Three AWS variables are read in the storage layer** (`mongo-client-configuration.js:38-40`).
   Per-deployment by nature — they authenticate the process to its database, not a tenant to a
   vendor. Listed for completeness; **not** a gap.

3. **Ten API v3 variables (plus `CI`, already classified) are read through a generic `process.env`
   reader, are absent from the README, and one family of them deletes data.** `lib/api3/index.js:24-38` defines
   `setENVTruthy(varName, default)`, which reads `process.env[varName]` (and three Azure/lowercase
   spellings) directly. Measured call sites:

   | name | site | default | what it decides |
   |---|---|---|---|
   | `API3_SECURITY_ENABLE` | `index.js:73` | `true` (`lib/api3/const.json:3`) | whether API v3 enforces authorization **at all** |
   | `API3_DEDUP_FALLBACK_ENABLED` | `index.js:74` | `true` | v3 deduplication fallback |
   | `API3_CREATED_AT_FALLBACK_ENABLED` | `index.js:75` | `true` | v3 `created_at` fallback |
   | `API3_MAX_LIMIT` | `index.js:76` | `1000` | v3 page ceiling |
   | `API3_AUTOPRUNE_<COLLECTION>` | `generic/collection.js:32` | unset | **days of history to keep, then DELETE the rest** |

   Six collections are registered (`lib/api3/index.js`: `devicestatus`, `entries`, `food`,
   `profile`, `settings`, `treatments`), so the autoprune family is six names:
   `API3_AUTOPRUNE_DEVICESTATUS`, `_ENTRIES`, `_FOOD`, `_PROFILE`, `_SETTINGS`, `_TREATMENTS`.
   4 + 6 = **10** API v3 names the census could not see. `CI` at `index.js:70` is an eleventh
   direct read, but it is already carried in class **X** below and must not be added twice — the
   version first published here counted it in both places.

   Measured: `grep -c 'API3_' README.md` returns **0**, and `grep -c 'API3_'` returns 0 for both
   `lib/server/env.js` and `lib/settings.js`. So none of these appears in the 247, and none is
   documented anywhere an operator would look.

   **Why this one is not a tidy-up.** `collection.js:129-152` builds
   `deleteBefore = now - autoPruneDays * 24h` and calls `storage.deleteManyOr(...)` without waiting
   for the result. Retention of a person's glucose history is the most per-tenant setting in the
   system — it is the one a tenant owner is most likely to be told about by a clinician, and the one
   whose wrong value is unrecoverable. Under `TENANCY_MODE=multi` as the code stands, one
   deployment-wide environment variable prunes **every** tenant's data on one schedule and no tenant
   owner can see it, let alone set it. Classified **T** (per-tenant) by the §B.3 rule and **not yet
   reachable as T by any mechanism**. Proposed register entry §H.4.

4. **Anything a third-party plugin reads.** Out of scope by construction; gaps 1 and 3 are the shape
   of the problem.

5. **Twelve variables belonging to the hosted entrypoints themselves, found by adversarial review
   and missing from the census, the gap list and the totals.** The grep above was scoped to `lib/`,
   and the census's four sources all look at the `single` entrypoint's configuration path. The
   hosted entrypoints D5 and D7 already ship have their own, read through injected/generic readers
   that no regex over `readENV` can see:

   | site | names |
   |---|---|
   | `lib/admin/index.js:22, 37, 48-50` (`readEnv(source, name)` over `opts.env \|\| process.env`) | `ADMIN_STORAGE_URI` `ADMIN_STORAGE_NAMESPACE` `ADMIN_POOL_SIZE` |
   | `lib/admin/bind-guard.js:102, 144, 156` | `ADMIN_INSECURE_BIND_ACKNOWLEDGED` `ADMIN_BIND` `ADMIN_PORT` |
   | `bin/feed.js:64-65, 93-105` (`readEnv(name, fallback)` over `process.env`) | `FEED_STORAGE_URI` `FEED_STORAGE_NAMESPACE` `FEED_SLOT_NAME` `FEED_BATCH_SIZE` `FEED_POLL_INTERVAL_MS` `FEED_STATUS_INTERVAL_MS` |

   All twelve are **D** (per-deployment) by the §B.3 rule and none of them is a D15 violation —
   they configure a process, not a site. They are recorded because this section's whole claim is
   that the enumeration is closed, and it was not: it enumerated the `single` entrypoint's surface
   and called it Nightscout's. The census sources and the grep gate must both be widened to `bin/`
   and to injected-`env` readers before §B can be quoted as complete. Not a defect in the shipping
   code; a defect in this document's coverage.

A complete classification must therefore be paired with a **grep gate** that fails when a new
direct environment read appears outside `lib/server/env.js`. That gate is the second "done" command
at the end of §B, and it **fails today** — which is the correct state for a gate whose job is to
hold a line that has not yet been drawn. Its first published form matched `process.env.X` only and
therefore could not see `process.env['X']`, i.e. it missed gap 3 entirely; it has been corrected
there.

### B.3 The classification rules

| class | meaning | where it is read under `TENANCY_MODE=multi` |
|---|---|---|
| **T** | per-tenant, non-secret | `tenant_settings.settings` / `.extended`, via `settingsFor` |
| **TS** | per-tenant **secret** | `tenant_secret`, `kind='plugin:<n>'`, merged into `extendedSettings` at context build |
| **D** | per-deployment | `process.env`, as today. Identical for every tenant. |
| **B** | **bootstrap-only** (D15) | the `single` entrypoint only. Must not be read on any hosted entrypoint. |
| **X** | not Nightscout configuration | ignored (host platform, CI, doc artefacts) |

The rule that decides most of it: **if changing this value changes what one person's site shows,
alarms about, or connects to, it is T or TS. If changing it changes how the process listens, stores
or is deployed, it is D.**

### B.4 The census

Counts are measured by the script in §G.3 against `crm-seam` @ `81a1f6ce`.

> **RECONCILIATION, CORRECTED (adversarial review, 2026-09-15).** The arithmetic first published
> here — "the five classes sum to 245; the two names the rule could not decide bring it to the
> measured union of 247" — does not hold, and the group counts were not in fact reproduced from the
> script. The union of 247 IS confirmed. What it decomposes into was re-measured by expanding every
> abbreviated group (`BAGE_*`, `PUMP_*`, …) against the union and differencing:
>
> * `PUMP_*` is **13** names in the union, not 12 (`PUMP_WARN_BATT_QUIET_NIGHT` is the thirteenth),
>   so **T is 161**, not 160.
> * `TREATMENTS_AUTH` is counted inside T *and* added again as one of the two §B.6 names. It cannot
>   be both.
> * `CI` sits in the X list, but `CI` can never be in the union: source 4's regex requires an
>   underscore and no other source produces it. It was also counted a second time among §B.2 gap
>   3's "eleven", which is now stated as ten API v3 names plus `CI` counted once.
> * `MONGODB_COLLECTION` is in the union and is classified in **no** class list, despite §B.5(ii)
>   saying it is X. It is the one name in the 247 with no class; it has been added to X below.
>
> Reconciled and re-measured, with `MONGODB_COLLECTION` now added to X: the union of **247** is
> exactly T 161 + TS 28 + D 48 + B 2 + X 8 = **247** classified names, **less** `CI` (classified but
> not in the union, because no source emits it) = 246 present in the union, **plus**
> `DEXCOM_BRIDGE_USE_LEGACY` — which is in the union, is §B.6's second name and is in no class list
> — = **247**. The three AWS names listed parenthetically under D are likewise classified but not in
> the union: they are read directly (§B.2 gap 2) and no source sees them. Reproduced by expanding
> every abbreviated group against the union in a script and taking the set difference both ways;
> the difference is empty in both directions once those two exceptions are accounted for.
>
> The real surface is therefore **not 258**. Counting distinct names:
> 247 (union) + 3 (AWS, §B.2 gap 2) + 1 (`CI`, in no source's output) + 10 (§B.2 gap 3's API v3
> names) + 4 (§B.2 gap 1's `WEBHOOK_*`, which the published 258 omitted altogether)
> + 12 (§B.2 gap 5's `ADMIN_*`/`FEED_*`) = **277**, of which 8 are class **X** and are not
> Nightscout configuration at all. Every term in that sum was measured by set difference against
> the union; none of it should be quoted without re-running the script, which is the point of §B's
> gate.

Where a group is given a count, that count is a hand-expansion of the abbreviated list against the
union and **not** an output of the script — the script emits set sizes, not per-group tallies. Do
not read a group count as measured until the §B harness exists.

#### T — per-tenant, non-secret (161)

*Site identity and display (19)* — `CUSTOM_TITLE` `THEME` `DISPLAY_UNITS` `UNITS` `LANGUAGE`
`TIME_FORMAT` `NIGHT_MODE` `EDIT_MODE` `SCALE_Y` `FOCUS_HOURS` `DAY_START` `DAY_END` `SHOW_RAWBG`
`SHOW_PLUGINS` `SHOW_FORECAST` `SHOW_CLOCK_DELTA` `SHOW_CLOCK_LAST_TIME` `DE_NORMALIZE_DATES`
`BASE_URL`

*Alarms and thresholds (21)* — `BG_HIGH` `BG_LOW` `BG_TARGET_TOP` `BG_TARGET_BOTTOM` `ALARM_TYPES`
`ALARM_HIGH` `ALARM_HIGH_MINS` `ALARM_LOW` `ALARM_LOW_MINS` `ALARM_URGENT_HIGH`
`ALARM_URGENT_HIGH_MINS` `ALARM_URGENT_LOW` `ALARM_URGENT_LOW_MINS` `ALARM_URGENT_MINS`
`ALARM_WARN_MINS` `ALARM_TIMEAGO_WARN` `ALARM_TIMEAGO_WARN_MINS` `ALARM_TIMEAGO_URGENT`
`ALARM_TIMEAGO_URGENT_MINS` `ALARM_PUMP_BATTERY_LOW` `HEARTBEAT`

*Feature selection and access policy (6)* — `ENABLE` `DISABLE` `AUTH_DEFAULT_ROLES`
`AUTH_FAIL_DELAY` `AUTHENTICATION_PROMPT_ON_LOAD` `ADMIN_NOTIFIES_ENABLED` — plus `TREATMENTS_AUTH`,
classified by hand (§B.6)

*Frames (16)* — `FRAME_URL_1`…`FRAME_URL_8`, `FRAME_NAME_1`…`FRAME_NAME_8`

*Plugin configuration, non-secret (97)* — every `<PLUGIN>_*` that is not a credential:
`AR2_CONE_FACTOR` · `BAGE_*` (5) · `BASAL_RENDER` · `BOLUS_RENDER_*` (3) · `BWP_*` (4) · `CAGE_*`
(5) · `DBSIZE_*` (5) · `DEVICESTATUS_ADVANCED` `DEVICESTATUS_DAYS` · `ERRORCODES_*` (3) · `IAGE_*`
(4) · `LOOP_ENABLE_ALERTS` `LOOP_PUSH_SERVER_ENVIRONMENT` `LOOP_URGENT` `LOOP_WARN` · `OPENAPS_*`
(11) · `PROFILE_HISTORY` `PROFILE_MULTIPLE` · `PUMP_*` (13) · `SAGE_*` (4) · `TIMEAGO_ENABLE_ALERTS`
· `TREATMENTNOTIFY_*` (2) · `UPBAT_*` (3) · `XDRIPJS_*` (3) · `CORS_ALLOW_ORIGIN` ·
ingestion endpoints and regions: `BRIDGE_SERVER` `MMCONNECT_SERVER` `CONNECT_SOURCE`
`CONNECT_SOURCE_ENDPOINT` `CONNECT_SOURCE_COLLECTIONS` `CONNECT_SOURCE_MAX_COUNT`
`CONNECT_COUNTRY_CODE` `CONNECT_SHARE_REGION` `CONNECT_SHARE_SERVER` `CONNECT_CARELINK_REGION`
`CONNECT_CARELINK_SERVER` `CONNECT_LINK_UP_REGION` `CONNECT_LINK_UP_SERVER`
`CONNECT_LINK_UP_PRODUCT` `CONNECT_LINK_UP_VERSION` `CONNECT_GLOOKO_SERVER` `CONNECT_GLOOKO_ENV`
`CONNECT_GLOOKO_AUTH_MODE` `CONNECT_GLOOKO_WEB_ORIGIN` `CONNECT_GLOOKO_TIMEZONE_OFFSET`
`CONNECT_GLOOKO_USE_V3_GRAPH`

#### TS — per-tenant **secret** (28)

`PUSHOVER_API_TOKEN` `PUSHOVER_USER_KEY` `PUSHOVER_ALARM_KEY` `PUSHOVER_ANNOUNCEMENT_KEY` ·
`MAKER_KEY` `MAKER_ANNOUNCEMENT_KEY` · `LOOP_APNS_KEY` `LOOP_APNS_KEY_ID`
`LOOP_DEVELOPER_TEAM_ID` · `BRIDGE_USER_NAME` `BRIDGE_PASSWORD` · `MMCONNECT_USER_NAME`
`MMCONNECT_PASSWORD` · `CONNECT_SHARE_ACCOUNT_NAME` `CONNECT_SHARE_PASSWORD` ·
`CONNECT_CARELINK_USERNAME` `CONNECT_CARELINK_PASSWORD` `CONNECT_CARELINK_PATIENT_USERNAME` ·
`CONNECT_LINK_UP_USERNAME` `CONNECT_LINK_UP_PASSWORD` `CONNECT_LINK_UP_PATIENT_ID` ·
`CONNECT_GLOOKO_EMAIL` `CONNECT_GLOOKO_PASSWORD` `CONNECT_GLOOKO_SERIAL_NUMBER`
`CONNECT_GLOOKO_DEVICE_ID` · `CONNECT_SOURCE_API_SECRET` · `OBSCURED` `OBSCURE_DEVICE_PROVENANCE`

Three notes on this list, because two of them are judgement calls:

- **Usernames, patient ids and serial numbers are in TS, not T.** They are not passwords, but a
  `CONNECT_LINK_UP_PATIENT_ID` identifies a person to a device vendor and a
  `CONNECT_GLOOKO_SERIAL_NUMBER` identifies their pump. Under the Foundation's own handling rule
  these are identifiers in health-data context; they belong in the table that is excluded from
  export and never returned by a GET. Cost of being wrong in this direction: a tenant owner has to
  re-enter a username. Cost of being wrong the other way: an identifier leaks in an export.
- `OBSCURED` and `OBSCURE_DEVICE_PROVENANCE` are already in `settings.js`'s own `secureSettings`
  list (`settings.js:77-85`), which `filteredSettings()` strips before settings reach a client. They
  are TS for the same reason the code already treats them as secure, even though neither is a
  credential.
- `settings.js:77-85` also lists `apnsKey`, `apnsKeyId`, `developerTeamId`, `userName` and
  `password` — the camelCase forms of five of the names above. That is the existing code agreeing
  with this classification, and it is the strongest evidence in this section that the T/TS split is
  not invented here.

#### D — per-deployment (48)

*Listener and transport (13)* — `PORT` `SSL_KEY` `SSL_CERT` `SSL_CA` `INSECURE_USE_HTTP`
`SECURE_HSTS_HEADER` `SECURE_HSTS_HEADER_INCLUDESUBDOMAINS` `SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS`
`SECURE_HSTS_HEADER_PRELOAD` `SECURE_CSP` `SECURE_CSP_REPORT_ONLY`
`ALLOW_UNRESTRICTED_FRAME_EMBEDDING` `TRUST_PROXY`

*Storage (20)* — `STORAGE_URI` `STORAGE_NAMESPACE` `MONGO` `MONGO_CONNECTION` `MONGODB_URI`
`MONGOLAB_URI` `MONGO_POOL_SIZE` `MONGO_MIN_POOL_SIZE` `MONGO_MAX_IDLE_TIME_MS` `MONGO_POOL_DEBUG`
`ENTRIES_COLLECTION` `MONGO_COLLECTION` `MONGO_TREATMENTS_COLLECTION` `MONGO_PROFILE_COLLECTION`
`MONGO_SETTINGS_COLLECTION` `MONGO_DEVICESTATUS_COLLECTION` `MONGO_FOOD_COLLECTION`
`MONGO_ACTIVITY_COLLECTION` `MONGO_AUTHENTICATION_COLLECTIONS_PREFIX` `PREDICTIONS_MAX_SIZE`
(+ `AWS_ACCESS_KEY_ID` `AWS_SECRET_ACCESS_KEY` `AWS_SESSION_TOKEN`, read directly)

*Tenancy (7)* — `TENANCY_MODE` `TENANT_HOST_PATTERN` `TENANT_PATH_PATTERN` `TENANT_HOST_HEADER`
`TENANT_REQUIRE_TOKEN_CLAIM` `TENANT_CONTEXT_MAX` `TENANT_CONTEXT_TTL_MS`

*Process (8)* — `NIGHTSCOUT_STATIC_FILES` `NIGHTSCOUT_HOSTNAME` `HOSTNAME` `DEBUG_MINIFY`
`DEBUG_LOGGING` `CONNECT_DEBUG` `UUID_HANDLING` `IMPORT_CONFIG`

**`TRUST_PROXY` is the one D entry that is security-critical per tenant and still correctly D.** It
describes the physical deployment — who is in front of this process — and a tenant cannot be
allowed to assert it, because BF-24 shows what happens when the forwarded-host guard can be
defeated: the client picks its own tenant. `TENANT_HOST_HEADER` is D for the same reason.

**`IMPORT_CONFIG` deserves a second look and did not get one here.** It is a documented mechanism
for importing configuration wholesale. If it can import *settings*, then under multi it is a
deployment-wide variable that writes per-tenant state, which would be a D15 violation with a D
classification. Filed as open question §I.3.

#### B — bootstrap-only (2)

`API_SECRET` `API_SECRET_FILE`

These are the D15 entries and there are exactly two of them. `bin/server.js` running as `single`
reads them; the four hosted entrypoints (D5: api / evaluator / realtime / vcpool) must not. §C says
what enforces that.

#### X — not Nightscout configuration (8)

`NODE_ENV` `CI` `WEBSITE_NODE_DEFAULT_VERSION` `SCM_COMMAND_IDLE_TIMEOUT` (Azure platform) ·
`MYPLUGIN_EXAMPLE_VALUE` (README's worked example) · `OPTIONAL_API_SECRET` (a placeholder inside
README's `CONNECT_SOURCE_API_SECRET=<OPTIONAL_API_SECRET>` example, not a variable) ·
`DEFAULT_FEATURES` (produced by `nameFromKey` from `settings.DEFAULT_FEATURES`, which is a constant
at `settings.js:182`, not something read from the environment) · **`MONGODB_COLLECTION`** (added by
adversarial review: documented at `README.md:240` and read by nothing — §B.5(ii), §H.3. It was in
the union of 247 and in none of the five class lists, which is the hole the reconciliation note at
the head of §B.4 closes.)

Note that `CI` is in this list but is **not** in the union of 247 — source 4's regex requires an
underscore, and no other source emits it. It is counted once, here, and not again among §B.2 gap
3's names.

#### The ten the census could not see (§B.2 gap 3), plus `CI`

`CI` is listed in the table below for context only; it is counted once, in class **X** above.

Classified here for completeness; none of them is reachable through `settingsFor` today.

| name | class | why |
|---|---|---|
| `API3_AUTOPRUNE_DEVICESTATUS` `_ENTRIES` `_FOOD` `_PROFILE` `_SETTINGS` `_TREATMENTS` | **T** | data retention for one person's history |
| `API3_MAX_LIMIT` | **D** | a resource bound on the process, identical for everyone |
| `API3_SECURITY_ENABLE` | **D** | turns v3 authorization off deployment-wide. A tenant must not be able to set it — see §F.2 — and under `multi` it arguably should not be settable at all |
| `API3_DEDUP_FALLBACK_ENABLED` `API3_CREATED_AT_FALLBACK_ENABLED` | **D** | ingest-compatibility behaviour of the v3 writer; changing it per tenant would make two tenants' stored documents differ in shape for no reason a tenant could describe |
| `CI` | **X** | test harness |

`WEBHOOK_PROTOCOL` `WEBHOOK_HOST` `WEBHOOK_PORT` `WEBHOOK_PATH` are **T** — where *this* site's
webhook posts — and are likewise unreachable (§B.2 gap 1).

### B.5 Two names this census found that are defects rather than classifications

**(i) `SECURE_HSTS_HEADER_INCLUDESUBDOMAINS` has two spellings and only one works.** Measured, both
directions:

```
SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS=true  ->  env.secureHstsHeaderIncludeSubdomains = false
                                                settings.secureHstsHeaderIncludeSubdomains = true
SECURE_HSTS_HEADER_INCLUDESUBDOMAINS=true   ->  env.secureHstsHeaderIncludeSubdomains = true
                                                settings.secureHstsHeaderIncludeSubdomains = false
```

`lib/server/app.js:144` reads `env.secureHstsHeaderIncludeSubdomains`. Grep finds **no** consumer of
`settings.secureHstsHeaderIncludeSubdomains` anywhere in `lib/`, `views/` or `static/`. So the
underscore spelling — which is what `settings.js`'s own `nameFromKey` produces from the camelCase
key, and therefore the spelling a reader of the settings dictionary would expect — is accepted,
stored, and has no effect. The same dead duplication exists without a spelling divergence for
`insecureUseHttp` (`settings.js:46`), `secureHstsHeader` (`:47`), `secureHstsHeaderPreload` (`:49`)
and `secureCsp` (`:50`) — all four are defined in the settings dictionary and every consumer in
`lib/`, `views/` and `static/` reads the `env.*` form instead. Together with
`secureHstsHeaderIncludeSubdomains` that is the five below; the first version of this paragraph
named only four of them and left `secureHstsHeaderPreload` unstated. Verified by grepping each key
across `lib/`, `views/` and `static/`. Proposed register entry §H.2.

*Why it matters to this spec rather than only to the register:* five keys in `settings.js`'s
dictionary are dead. If `tenant_settings.settings` is populated from that dictionary — which is the
obvious implementation, since `deriveSettings` validates overrides against exactly those keys
(`tenant-context.js:178-182`) — then a tenant owner will be offered five settings that do nothing,
one of them a security header.

**(ii) `MONGODB_COLLECTION` is documented and read by nothing.** README line 240 documents
``MONGODB_COLLECTION`` (`entries`) as "The Mongo collection where CGM entries are stored." Grep over
`lib/` and `bin/` finds no reader; the code reads `ENTRIES_COLLECTION` or `MONGO_COLLECTION`
(`env.js:211`). An operator following the README gets the default and no error. Proposed register
entry §H.3. Classified **X**, because it is not a variable — but it is documented as one. (When
this section was first written it said "classified X above" while the X list did not contain it;
adversarial review found it was the one name in the union of 247 carrying no class at all, and it
has been added to X.)

### B.6 The two the rule could not classify

The script leaves two names at `?`; both were settled by hand and both are **T**.

- **`TREATMENTS_AUTH`** — `env.js:262-265`: when falsy, appends ` careportal` to
  `settings.authDefaultRoles`. It decides whether an unauthenticated caller may write treatments to
  *this site*. Per-tenant, unambiguously. It is not in the settings dictionary, so it will need a
  hand-written mapping into `tenant_settings.settings.authDefaultRoles` rather than falling out of
  the generic path.
- **`DEXCOM_BRIDGE_USE_LEGACY`** — documented, and **absent from `crm-seam`**: grep for the name and
  for `bridgeUseLegacy` over `lib/` returns nothing. This independently confirms GT4's finding that
  cut 4 deletes it and it becomes accepted-and-ignored. T in principle, dead in the modernization
  stack. No schema work.

**Done, §B:**

```
node tools/qc/env-classification-arm.js --root externals/work/crm-seam --spec docs/30-design/tenant-owner-config-surface-2026-09-15.md
```
New harness (§G.2). It re-derives all four sources at run time and diffs the union against the
census above, failing on any name present in one and not the other. This is the gate that stops the
spec silently dropping a setting: the enumeration is checked against the code rather than trusted.
Non-vacuity: add a variable to `lib/settings.js` and the gate must go red without the spec being
edited.

```
! grep -rnE "process\.env(\.[A-Z]|\[)" externals/work/crm-seam/lib/ externals/work/crm-seam/bin/ \
  | grep -vE "lib/server/env\.js|NODE_ENV"
```
Fails today, and it must: it finds `lib/plugins/webhook.js:36-39` (gap 1),
`lib/storage/mongo-client-configuration.js:38-40` (gap 2, an allow-list candidate),
`lib/api3/index.js:26-29` and `:70` (gap 3) and `bin/feed.js:65` (gap 5). It passes only once each
read site is converted or explicitly allow-listed.

> **CORRECTION (adversarial review).** The first published form of this gate was
> `grep -rnE "process\.env\.[A-Z]" …/lib/`. Run verbatim it returns exactly seven lines —
> `webhook.js:36-39` and `mongo-client-configuration.js:38-40` — and **nothing from
> `lib/api3/index.js`**, because that file reads `process.env['CUSTOMCONNSTR_' + varName]`,
> `process.env[varName]` and `process.env['CI']` in bracket notation. The gate therefore could not
> see gap 3, which this section calls the largest gap and §H.4 calls the sharpest defect found. A
> new `process.env['ANYTHING']` would have passed it silently. The pattern above adds the bracket
> alternative and `bin/`; both were verified by running it.

---

## C. The credential model

D13 and D14 are the whole of this section's authority. Nothing here is a new decision except where
it says **DECISION**.

### C.1 The rule, and the one line that breaks it

> **D13.** No deployment-wide secret under `TENANCY_MODE=multi`, on any interface. `API_SECRET` is a
> single-tenant bootstrapping mechanism only. Each tenant holds its own root credential, stored with
> its config.

The site is `lib/authorization/index.js:169-173`, read in full:

```js
if (data.api_secret && authorizeAdminSecret(data.api_secret)) {
  requestSucceeded(data.ip);
  var admin = shiroTrie.new();
  admin.add(['*']);
  const result = { shiros: [admin] };
```

`admin.add(['*'])` is every permission on everything. There is no tenant in the expression, no
tenant in `data` (`resolveWithRequest`, `:106-110`, builds `{api_secret, token, ip}`), and no tenant
in the shiro. Under `multi`, one string matching `authorizeAdminSecret` is root on **every tenant's
data at once** — the tenant scope is applied by `withTenant` at the storage layer, but the shiro
that decides *whether the request may act* has already said yes to everything, on a secret that
belongs to the deployment rather than to anybody's site.

This predates the programme. The plan already names it under T3.0; this document's contribution is
to say what replaces it.

### C.2 What replaces it — **CONSEQUENCE** of D13

Three changes, in the order they must be made.

**(a) The deployment secret is refused, not ignored, on a hosted entrypoint.** `env.js:132-146`
reads `API_SECRET`/`API_SECRET_FILE` and calls `env.enclave.setApiKey`. Under `multi` that call must
not happen, and a deployment that sets `API_SECRET` while running a hosted entrypoint must **fail to
boot** with the reason. Ignoring it is worse than refusing it: the operator believes a secret is in
force and it is not, which is exactly the failure mode `fromEnv` already refuses to have (its own
comment: "a substrate that is present but inert is still a thing that can be wrong").

The check belongs at the entrypoint, not in `env.js`, because D15's whole point is that the four
hosted entrypoints and `single` bootstrap differently. `single` keeps reading `API_SECRET` and keeps
behaving exactly as it does today. This is D1: single-tenant is not a degraded mode and does not
acquire a database dependency for its configuration.

**(b) `authorizeAdminSecret` becomes tenant-scoped.** Under `multi` the comparison is against the
tenant's own `tenant_secret` row (`kind='root'`, `state IN ('active','retiring')`), and the shiro it
grants is the tenant's root shiro — still `['*']` in shiro terms, because a tenant owner *is* root
on their own site, but reached only after `withTenant` has bound the request, so `['*']` cannot
address a row the policy does not return. Under `single` it is `enclave.isApiKey` unchanged.

The tenant is known at this point. `tenantClaim` and the whole of `tenant-middleware` run **above**
the authorization layer, and tenant resolution is by *address* — `req.headers.host` through the
configured rule — never by anything the credential says. That ordering is T3.1's and it is what
makes (b) expressible at all.

**(c) Comparison is constant-time, and it is not today.** `enclave.isApiKey` (`enclave.js:50-52`)
is `keyValue.toLowerCase() == secrets[apiKeySHA1] || keyValue == secrets[apiKeySHA512]` — `==` on
strings, which short-circuits on the first differing byte. Single-tenant has lived with that because
there is one secret and an attacker who can time it can usually also just try passwords. With one
row per tenant in a shared table the shape changes, and `crypto.timingSafeEqual` on equal-length
digests costs nothing. Marked **DECISION** only because it is a behaviour change to a shipped
function, not because the direction is in doubt.

### C.3 Re-rooting the subject hash — **CONSEQUENCE** of D13, and the part that is easy to miss

§0.3(ii) established the mechanism. Restated as a requirement:

`enclave.getSubjectHash(id)` (`enclave.js:71-76`) is
`sha1(secrets[apiKeySHA1] || id)`. It is what every subject's `accessToken` is derived from
(`storage.js:227` on `crm-bf-auth`, `:211` on `crm-seam`), and `accessToken` is the bearer
credential an uploader or a follower actually holds. Remove the deployment API secret and the
derivation has no root; measured, `getSubjectHash` with no API key set throws
`TypeError: The "data" argument must be of type string or an instance of Buffer, TypedArray, or
DataView`, and the `isApiKeySet()` guard above it converts that throw into **silence** — every
subject loads with no `digest`, no `accessToken` and no `accessTokenDigest`, and the first lookup
dereferences `undefined`.

So D13 requires a new root, and `tenant_secret.kind='subject-salt'` is it:

```
subject.digest = sha1( tenantSubjectSalt(tenantId) || subject._id )
```

**This is not the root credential and must not be.** Two separate values, because rotating the
tenant's API secret must not silently invalidate every uploader token on the site — that is BF-17's
lesson pointed at a different credential, and §E.3 makes it explicit. A tenant owner who rotates
their root credential keeps their uploaders running; a tenant owner who rotates the subject salt is
told, in as many words, that every device will need its token re-entered.

**DECISION required:** whether `subject-salt` rotation is even offered in the first release, or
whether the only supported response to a suspected token compromise is deleting and recreating the
subject (which changes `_id`, and therefore the token, for that one subject alone). The second is
smaller, safer and probably right; the first is what an operator will ask for. Recommending the
second.

### C.4 Per-tenant signing keys, and how they kill BF-25 **as a class**

> **D14.** Per-tenant JWT signing key. Tenant resolution runs before any credential is examined, so
> the right key is known at verify time; cross-tenant token reuse becomes a signature failure, not a
> claim-check failure.

BF-25 stated as a class: *a credential presented by a client must not be able to authorise an action
against a tenant other than the one the **address** resolved to.* Today there are two distinct ways
it can, and D14 closes one of them completely and the other not at all. Both were executed against
the real `lib/server/tenant-middleware.js` on `crm-seam`; the harness and its controls are §G.4.

**Vector 1 — signed JWT.** Closed by D14, structurally.

| # | arrangement | `tenantClaim` | refusal | what stopped it |
|---|---|---|---|---|
| 2 | **one install-wide key**; tenant A's token replayed at B | `A` | `MSG_WRONG_TENANT` | the **comparison** in `sameTenant` |
| 3 | **per-tenant keys** (D14); A's token verified with B's key | `null` | `MSG_NO_CLAIM` | the **signature** |
| 3c | control: A's token, A's key, at A | `A` | `null` — proceeds | — |
| 4 | **forged claim**: payload `{tenant: B}` signed with A's key, verified at B | `null` | `MSG_NO_CLAIM` | the **signature** |
| 4c | the same forgery under one install-wide key | `B` | `null` — **proceeds** | nothing |

Row 4 against row 4c is the whole argument for D14 and it is stronger than "defence in depth". Under
one install-wide key, the `tenant` claim is *self-asserted data inside a token the deployment
itself will vouch for*. Anything that can get a payload signed — a bug at the minting site, a
future endpoint that mints a token from client-supplied fields, a replayed token whose claim is
stale because a slug moved — produces a token that verifies cleanly and whose claim the comparison
must then be relied on to catch. Under D14 that token does not verify at all. The tenant binding
stops being a field that is checked and becomes a property of the key that checked it, and a class
of bug is removed rather than a case of it.

**Vector 2 — opaque access token in the request body.** *Not* closed by D14, because an opaque token
has no signature to fail. This is the half the brief's framing understates and it is the half that
is actually BF-25.

Measured, both sites read in full:

- `tenant-middleware.js:104-129`, `presentedCredential(req)`, consults `req.headers.authorization`,
  `req.query.token`, `req.query.secret` and `req.headers['api-secret']`. It does **not** consult
  `req.body`, and its own comment says so and says why: the middleware mounts above the body
  parsers, so a body token is not visible yet.
- `lib/authorization/index.js:72-92` (`apiSecretFromRequest`) and `:41-47` **do** consult `req.body`:
  `req.body.secret`, `req.body[0].secret`, `req.body.token`, `req.body[0].token`.

Executed:

```
presentedCredential({headers:{}, query:{}, body:{secret:'...'}})  ->  {present:false, jwt:null}
credentialRefusal(..., tenantB, that)                             ->  null        (PASSES)

control: the same credential in the query string
presentedCredential({headers:{}, query:{secret:'...'}, body:{}})  ->  {present:true, jwt:null}
credentialRefusal(..., tenantB, that)                             ->  "This credential does not
                                                                       name a Nightscout site."
```

A request carrying its credential **only in the body** is invisible to the check, passes through as
anonymous, and is then resolved by the authorization layer against `storage.subjects` — one
process-wide array loaded once at boot (`storage.js:18`, `:209`), containing every subject of every
tenant, searched with no tenant dimension (`checkToken`, `:301-312`). Tenant A's access token in the
body of a request addressed to tenant B resolves to A's subject and grants A's roles, and
`withTenant` has bound B.

**Therefore: killing BF-25 as a class requires D14 *and* `tenant_subject` (§A.2 table 3).** The two
together give a closed argument:

1. Tenant resolution is by address and happens first (T3.1). ✔ built
2. A signed credential that verifies at all was signed by *this* tenant's key (D14). ← T3.0
3. An opaque credential resolves only against *this* tenant's subjects (`tenant_subject` under RLS,
   `withTenant` already bound). ← T3.0
4. Therefore no credential of any shape can authorise against a tenant it does not belong to, and
   the `requireTokenClaim` knob stops being load-bearing.

Step 3 is what lets `TENANT_REQUIRE_TOKEN_CLAIM` finally become a constant rather than a knob —
`tenant-middleware.js`'s header already says it stays a knob *"now waiting on whichever task scopes
the subject store"*. That task is this one.

### C.5 What wraps the stored material — **DECISION**

`tenant_secret.material` is `bytea` and the DDL says "ciphertext". What encrypts it is not settled
here and should not be settled by this document alone. Three options, ordered by how much they ask
of a hoster:

| option | key lives | hoster cost | what a database dump yields |
|---|---|---|---|
| 1. KEK in the process environment (`TENANT_SECRET_KEK`) | env of the hosted entrypoints | none beyond setting a variable | nothing, unless the env leaks too |
| 2. KEK from a file, like the existing JWT key (`enclave.js:22-28` reads `node_modules/.cache/_ns_cache/randomString`) | disk | none; matches an existing pattern | nothing, unless the disk leaks too |
| 3. External KMS | a vendor | real | nothing |

A deployment-wide KEK is **not** a D13 violation: D13 forbids a deployment-wide *credential that
authorises requests*, and a KEK authorises nothing — presenting it to the API does not
authenticate anybody. Saying that out loud because the distinction will otherwise be re-litigated.
Recommending option 1 for the first release, with `key_ref` in the schema so option 3 can arrive
without a migration. **The maintainer must say yes**, and should also say whether a hoster is
required to be *unable* to read a tenant's plugin credentials — if yes, none of these three suffice
and the answer is client-side encryption with the tenant's own passphrase, which breaks server-side
polling of Dexcom Share and is therefore probably not wanted.

### C.6 What does **not** change

`single` is untouched. `API_SECRET` still boots it, `enclave` still holds one key, subject hashes
are still rooted on the deployment secret, and `lib/admin/platform.sql` is not read because there is
no PostgreSQL. A self-hoster upgrading to a release containing all of T3.0 should see **no
difference whatsoever**, and §G.1's first command is the check for that.

**Done, §C:**

```
node tools/qc/tenant-credential-arm.js --root externals/work/crm-seam
```
New harness (§G.4). It must run all five rows of the §C.4 table plus the two body-vector rows and
their controls, and it must **fail** if row 3, 4 or the body row starts passing the request. The
non-vacuity pairing: point the harness at a build where the per-tenant key lookup returns the
install-wide key, and rows 3 and 4 must go green — i.e. the harness must be able to tell the two
designs apart, which is the only thing that makes rows 3 and 4 evidence for D14 rather than
decoration.

```
! grep -n "admin.add(\['\*'\])" externals/work/crm-seam/lib/authorization/index.js
```
Fails today, by design: it is the §C.1 site, and it is the one-line check that D13 has landed.

---

## D. What T3.0 amends

The plan's T3.0 table names one site per task. Each is correct and each is smaller than the change
it stands for. This section is the concrete list.

### D.1 T3.1 — `tenantClaim` verifies with one install-wide key

The plan cites `tenant-middleware.js:139-143`. Measured, `tenantClaim` opens at **139** and the
`verifyJWT` call is at **143**, so the citation is right — but it names the *reader* and the change
is bigger at both ends.

| # | site | change | kind |
|---|---|---|---|
| 1 | `tenant-middleware.js:139` | `tenantClaim(enclave, jwt)` → the enclave is selected per tenant. The signature already takes an enclave, so this is a change at the **call** site, not here | CONSEQUENCE |
| 2 | `tenant-middleware.js:346` | `enclave: env.enclave` — the deployment's, resolved once at middleware construction. Becomes a per-request lookup keyed on the tenant the address resolved to | CONSEQUENCE |
| 3 | `enclave.js:30` | `secrets[jwtKey] = readKey('randomString')` — the signing key is read from `node_modules/.cache/_ns_cache/randomString` at construction. **Install-wide and file-sourced**, not env-sourced, which the plan does not say. Under `multi` the key comes from `tenant_secret` `kind='jwt'` | CONSEQUENCE |
| 4 | `lib/authorization/index.js:289` | the minted payload gains `tenant`. **Without this nothing works at all** — §0.3(iii) | CONSEQUENCE |
| 5 | `enclave.js:54-56` | `setJWTKey` exists and **has no caller** (`grep -rn setJWTKey lib/ bin/` returns only the definition). Either it becomes the per-tenant injection point or it is dead code that should go | DECISION |
| 6 | `tenant-middleware.js:208` | `requireTokenClaim` may become a constant `true` once §C.4 step 3 lands. Until then it stays a knob | DECISION |

Note on row 3: because the key is a *file* rather than an environment variable, it is not in §B's
census and never could have been. It is also why two Nightscout deployments sharing a filesystem
today already share a signing key, which is a single-tenant curiosity and a multi-tenant defect.

### D.2 T3.2 — `platform.sql` carries no configuration, and `subject_id` references nothing

The plan's citation is exact. `platform.sql` is 78 lines, two tables, and I read every line.

| # | site | change | kind |
|---|---|---|---|
| 1 | `platform.sql` | add `tenant_settings`, `tenant_secret`, `tenant_subject`, `tenant_role` (§A.2). Purely additive; `tenants` is not touched | CONSEQUENCE |
| 2 | `platform-store.js:45` | `PLATFORM_TABLES = ['tenants','tenant_members']` drives `ensureSchema`'s completeness check at `:138-146`, which throws when *some but not all* expected tables are present. Adding tables to the DDL **without** adding them here means a fresh database creates six tables and an existing two-table database silently passes as complete | CONSEQUENCE |
| 3 | `platform-store.js:51` | `NOT_TENANT_DATA` gains `tenant_secret`, or `exportTenant` streams wrapped credentials (§A.2b). Also must be exported to be checkable | CONSEQUENCE |
| 4 | `tenant_members.subject_id uuid` | **the type is wrong, not just the missing FK.** `specs/nsschema/auth_subjects.model.json` records `_id` as `types: ["string"]`, because it is a Mongo ObjectId hex on one backend and arbitrary text on the other. A 24-character hex ObjectId does not fit a `uuid` column. Recommend `ALTER TABLE tenant_members ALTER COLUMN subject_id TYPE text`, then `REFERENCES tenant_subject(tenant_id, subject_id)` as a composite FK | **DECISION** — it alters a shipped table |
| 5 | `lib/admin/app.js` | the admin plane has eight routes (`/health`, list/create/get/suspend/activate/delete tenant, export) and **no** configuration or credential route. It must not grow one: §F | CONSEQUENCE |

On row 4: `ensureSchema` runs the DDL only when **zero** platform tables exist, so there is no
migration machinery here at all. Whether T3.0 introduces one, or whether the platform schema is
still young enough to be dropped and recreated, is §I.1.

### D.3 T3.3 — `ctxFor(tenantId)` shares `env.enclave`

The plan cites `tenant-context.js:137`. **That line is a comment.** GT3 found this and it is
confirmed: line 137 is `` * `env.enclave` is shared, and that is the deliberate one. `` — prose
inside the doc block for `PER_TENANT_ENV_KEYS`. The mechanism is two other lines.

| # | site | what is there | change | kind |
|---|---|---|---|---|
| 1 | `tenant-context.js:143` | `PER_TENANT_ENV_KEYS = Object.freeze(['settings','extendedSettings','err','notifies'])` | add `'enclave'` | CONSEQUENCE |
| 2 | `tenant-context.js:278` | `if (PER_TENANT_ENV_KEYS.includes(key)) continue;` — the copy loop that shares everything **not** in that list by reference | no edit needed; it follows row 1 | CONSEQUENCE |
| 3 | `tenant-context.js:265-300` | `deriveEnv` assigns `derived.settings` and `derived.extendedSettings` explicitly after the loop | gains `derived.enclave = enclaveFor(tenant)` | CONSEQUENCE |
| 4 | `tenant-context.js:131-142` | the doc comment stating the rejected reasoning — *"of which there is exactly one … minting a second would mean tokens that verify for one tenant and not another for reasons unrelated to tenancy"* | rewrite. D14's answer is that verifying for one tenant and not another **is** the reason, and is the point | CONSEQUENCE |
| 5 | `tenant-context.js:495-504` | `fromEnv` passes `{base, max, ttl}` and **not** `settingsFor`, so `createContextCache` falls through to `function none()` at `:391` and every tenant receives a copy of the deployment's env-sourced settings — the D15 violation, four lines wide | CONSEQUENCE |

Row 4 is not bookkeeping. Rule 6 applies inside source files too: an agent that reads lines 131-142
and not this document will conclude that per-tenant enclaves were considered and rejected.

Row 5 is the single most important line in this section, because it is the one that makes D15 true
rather than aspirational. `settingsFor` is already documented at `:353` as
`(tenant) => {settings, extendedSettings}` and already called at `:448`. The function that reads
`tenant_settings` and returns exactly that shape is the entirety of the wiring work.

### D.4 The site older than the programme

`lib/authorization/index.js:169-173` — §C.1. The plan names it; §C.2 replaces it. It is listed
separately here because it belongs to no T3.x task and will be missed if it is only ever mentioned
in prose.

**Done, §D:**

```
node tools/qc/t30-amendment-gate.js --root externals/work/crm-seam
```
New harness (§G.2). One assertion per row above, each written as *the state after the change*, so
the gate is red until T3.0 lands and green afterwards. It is a checklist with an exit code, and the
non-vacuity argument is the ordinary one: it is red today, on the tree as it stands, and each row
was written by reading the line it names.

---

## E. Bootstrap and migration

### E.1 Creating the first tenant — **CONSEQUENCE** of D7 plus §A

The hoster's plane already creates tenants: `POST /tenants` on `lib/admin/app.js:138`, on an
unrouted port, with no credential (D7). It writes a row in `tenants` and nothing else. After T3.0 it
must also, in the same transaction:

1. insert `tenant_settings` with `settings = '{}'`, `extended = '{}'`, `units` from the request or
   the default, `enabled_plugins` = the resolved `DEFAULT_FEATURES` list;
2. generate and insert `tenant_secret` rows for `kind IN ('root','jwt','subject-salt')`, version 1,
   state `active`, from `crypto.randomBytes`;
3. return the **root credential in plaintext, exactly once, in the creation response.**

Point 3 is the only moment the plaintext exists outside the tenant owner's hands, and it must be the
only one: there is no "show me my secret again" endpoint, because the row is ciphertext and because
an endpoint that reveals a credential is an endpoint that can be made to reveal it to the wrong
person.

**If it is lost, it cannot be rotated by the tenant owner, and the first draft of this paragraph
said it could.** §E.3's rotation is an authenticated tenant-owner action: it needs the credential
that has just been lost. The recovery path is therefore the *hoster's* plane (interface 1) issuing
a new `root` secret for that tenant, which means `bin/admin.js` grows a
`POST /tenants/:slug/credential` route — and §D.2 row 5 and §F.1 both say the admin plane must
**not** grow a credential route. Those two requirements are in direct conflict and the conflict is
unresolved here. It has to be resolved before release, because "I lost my Nightscout password"
is not an edge case; it is the most common support request any hosted service receives. Filed as
open question §I.7 and decision J13.

The tenant owner then reaches their own configuration on the **consumer** interface, authenticating
with that root credential, under RLS. The hoster's plane never gains a configuration endpoint — §F.

> **BLOCKING CONTRADICTION found by adversarial review, 2026-09-15 — §E.1 as written cannot
> execute against §A.2's DDL.** All four new tables carry `FORCE ROW LEVEL SECURITY` and
> `WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)`.
> The admin plane writes `tenants` through the UNBOUND `query()` helper
> (`createTenant`, `platform-store.js:230-262`), with no `app.current_tenant_id` set. With no
> binding the predicate is `tenant_id = NULL`, which is NULL and not TRUE, so the `WITH CHECK`
> is not satisfied and the `tenant_settings` and `tenant_secret` inserts are **refused**. The
> escape hatches are both closed on purpose: `asTenant` (`platform-store.js:92-109`) is the only
> binding helper and its own doc comment says it is "used here only to ASK questions under RLS …
> never to write", and `assertNotBypassingRls` (`:160-172`) refuses to serve as a `SUPERUSER` or
> `BYPASSRLS` role at all. §F.2's reassurance that "a forgotten binding produces a broken feature,
> not a leak" is precisely the mechanism that breaks this.
>
> There are three ways out and the document does not choose between them, so this is a **DECISION**
> (new row J12):
>
> 1. let `createTenant` bind the id it has just generated and write inside `asTenant`, amending
>    that helper's contract and its comment (rule 6 applies — the comment is load-bearing);
> 2. give the four new tables a second policy admitting the admin role by name, which reintroduces
>    a cross-tenant write path on the consumer tables and needs its own argument;
> 3. move bootstrap rows out of the hoster's plane entirely and have the tenant owner's first
>    authenticated request create them, which needs a credential before there is a row to hold one.
>
> Until one is chosen, §E.1's "in the same transaction" is aspiration. The §E harness
> (`tenant-bootstrap-arm.js`) is the thing that would have caught this on the first run, which is
> the argument for writing it before the DDL is landed rather than after.

**One ordering hazard.** `ensureSchema` (`platform-store.js:120-158`) is the only DDL path and it
runs the whole `PLATFORM_DDL` in one transaction only when **zero** platform tables are present. A
deployment that already has `tenants` and `tenant_members` will not get the four new tables from it,
and will not be told. See §D.2 row 2 and §I.1.

### E.2 A self-hoster who chooses to move — **DECISION**, and the constraint on it is D1

**Nobody is ever required to do this.** D1 makes single-tenant permanently first-class. This is a
path offered to someone who wants it, and the honest framing is that it is a *migration into a
hosted service*, with everything that implies about who then holds their data.

The mechanical part is small, because §B is exactly the mapping:

1. read the self-hoster's `process.env` (or their `.env`);
2. run it through `lib/settings.js`'s `eachSettingAsEnv` and `findExtendedSettings` — the same code
   the deployment path runs, so the result is by construction what their site is doing today;
3. split the result by §B's classification: **T** → `tenant_settings.settings`/`.extended`,
   **TS** → `tenant_secret` rows with `kind='plugin:<n>'`, **D** and **B** → *discarded, with a
   report naming every one*;
4. copy documents with the existing `exportTenant`/import path.

Step 3's report is the load-bearing half and is the thing a naive importer will skip. Discarding
`PORT` is obvious. Discarding `TRUST_PROXY` is not, and discarding `API3_AUTOPRUNE_ENTRIES`
(§B.2 gap 3) would silently change how long their history is kept. **The importer must refuse to
run rather than drop a name it cannot classify** — a variable it has never seen is more likely to be
a third-party plugin's credential than noise.

Three things this migration cannot carry, and all three must be told to the person in advance:

- **Every access token changes.** Subject tokens are derived from the subject hash (§C.3), whose
  root changes from the deployment API secret to the tenant's `subject-salt`. Every uploader, every
  follower app, every xDrip connection is re-paired. This is not a bug and it is not avoidable; it is
  what "your credentials are no longer rooted in a secret someone else holds" means.
- **`API_SECRET` stops existing.** D13. Anything the person has configured with their API secret
  rather than a token uses the tenant root credential instead.
- **Alarm thresholds are re-validated on the way in.** If their stored thresholds are in mmol
  (§A.3), the constraint rejects them and the importer must convert and *show them the converted
  numbers*. A migration that silently normalised someone's alarm settings would be worse than one
  that refused.

#### E.2a The one-way doors, and the rollback — added by adversarial review

The first version of §E.2 named three costs and no rollback. A migration plan without a findable
rollback is incomplete, and this one moves a person's glucose data and their alarm configuration,
so it is stated here rather than at the end.

**One-way doors, in the order a person meets them.** A one-way door is a step that cannot be undone
by reversing it:

| # | step | why it is one-way |
|---|---|---|
| 1 | subject tokens are re-rooted on the tenant's `subject-salt` (§C.3) | the old tokens are derivations of a secret the person no longer holds. Going back means re-pairing every device a second time, not restoring anything |
| 2 | the deployment `API_SECRET` is dropped (D13) | nothing on the hosted side can reconstruct it; the self-hosted instance must still have it |
| 3 | mmol thresholds are converted to mg/dL on the way in (§A.3) | the conversion rounds (`Math.round`, `settings.js:290-296`), so the round trip back to mmol is not the number the person typed |
| 4 | **D** and **B** variables are discarded with a report (§E.2 step 3) | nothing stores them on the hosted side, so there is no copy to bring home |

**The rollback, and it is deliberately unglamorous.** Because every door above is one-way, rollback
is not "undo the migration": it is *keep the source running until you are sure*. Concretely, and
this is what the importer's documentation must tell a person to do **before** step 1:

1. **Do not decommission the self-hosted instance.** Leave it running, or at minimum keep its
   database and its `.env` (which holds `API_SECRET`), for at least one full cycle of whatever the
   person depends on — CGM ingestion, follower apps, alarms, reports.
2. **Take an export from the hosted tenant on day one** (`GET /tenants/:slug/export`, `app.js:194`)
   and confirm it opens. An export you have never opened is not a backup.
3. **Rolling back = pointing DNS and devices back at the self-hosted instance**, re-entering its
   original tokens (which still work, because nothing changed there), and then importing any
   documents written while the hosted tenant was live. That last step is the only part that needs
   new code, and it is the *same* import path in the other direction.
4. **Delete the hosted tenant only after the rollback window closes.** `DELETE /tenants/:slug`
   cascades, and `tenantDataCounts` exists precisely so a hoster sees what a deletion destroys
   before it happens.

**The check that tells you it is going wrong, not just how to fix it.** The failure mode of a CGM
migration is silent: readings simply stop arriving and nothing announces it. `tenants.last_reading_at`
(`platform.sql:44-46`) already exists for signal-loss detection. Migration is not complete until
that column is advancing on the hosted tenant, and the importer must say so in those words rather
than reporting success when the last row is copied.

**DECISION:** whether this importer is in scope for the first hosted release at all. It is a
substantial piece of work whose failure mode touches someone's alarm configuration, and the hosted
service is viable without it — a new tenant can configure their site from scratch. Recommending it
be a second release, and that the *export* half (getting your data back out) ship first, because
that is the one that affects whether someone is willing to move in the first place.

### E.3 Rotation — **CONSEQUENCE**, and BF-17's lesson is the reason it is a section

> **BF-17's lesson, stated for this document:** a code fix does not invalidate credentials that were
> already written. BF-17 was a plaintext access token persisted into subject documents; the fix
> stopped it being written and did **nothing** to the tokens already on disk, which continued to
> work and continued to be served by `GET /subjects` to anyone with the admin UI. Rotation is a
> separate operator action. **A spec that omits the rotation path is incomplete**, and one that
> assumes a deploy performs the rotation is worse than incomplete, because it will be believed.

This is why `tenant_secret` is versioned rather than overwritten, and why `state` has three values
instead of a boolean. The rotation procedure, for each `kind`:

| step | root credential | jwt key | subject-salt |
|---|---|---|---|
| 1 | insert version *n+1*, `state='active'` | same | same |
| 2 | update version *n* to `state='retiring'`, `expires_at = now() + overlap` | same | **no overlap is possible** |
| 3 | verification accepts `active` ∪ `retiring`; minting uses `active` only | same | — |
| 4 | at `expires_at`, `state='revoked'`, `revoked_at=now()` | same | — |
| overlap | hours to days — long enough for the person to update their uploaders | ≤ the JWT lifetime (`8h`, `enclave.js:59`), because no token outlives it | none |
| what breaks | nothing, during the overlap | nothing, during the overlap | **every subject token at once** |

`tenant_secret_one_active` (a partial unique index, not a trigger — two concurrent rotations racing
is exactly what a read-then-write trigger loses) enforces that step 1 and step 2 cannot both leave
two `active` rows.

The subject-salt column of that table is the one to read twice. There is no overlap window, because
a subject's `accessToken` is a *derivation* rather than a stored value: change the salt and every
subject's token changes in the same instant, and the old ones resolve to nothing. That is why §C.3
recommends not offering subject-salt rotation at all in the first release and handling a compromised
subject by deleting and recreating that one subject.

**What the tenant owner must be told, at the moment they press the button** — and this is the
operator-facing text §E.4 owes:

- rotating the **root credential**: your old secret keeps working until *(date)*, then stops.
  Anything you configured with it needs the new one before then.
- rotating the **signing key**: anyone currently signed in is signed out within 8 hours.
- rotating the **subject salt**: *every device that sends or reads your glucose data stops working
  immediately and must be re-paired, one at a time.* Do not do this unless you have been told to.

### E.4 The operator-facing text this implies, which is not in this document

This is a contributor-facing spec and the audience rule is not a formality. Everything above is
written for someone reading the source. The tenant owner is a person managing their own or a family
member's diabetes, and at least four things must exist in plain language before any of this is
usable:

1. what each rotation does, in the three sentences above;
2. what happens to alarms when thresholds are rejected — including that **alarms do not fire while
   settings are invalid**, and that "not medical advice, check with your care team about what your
   thresholds should be";
2b. **what happens when a threshold is not rejected but quietly changed.** `verifyThresholds`
   rewrites an out-of-order threshold and only writes a line to the server log (§A.3). The person
   must be shown the number that was stored, next to the number they entered, every time they are
   different — and told, in plain words, that the site will alarm at the stored one. "Your low
   alarm was saved as 70 mg/dL, not the 3.9 you entered" is the whole message. This is not medical
   advice and it is not a recommendation about what any threshold should be; decide those with
   your care team.
2c. **how to tell, without being told, that data has stopped arriving.** Every failure in this
   document's ingestion and migration paths is silent — readings stop, nothing announces it. The
   person needs one sentence naming what to look at (the time of the most recent reading on their
   own site) and what "too old" means for them, and they need it before they need it.
3. what moving to a hosted tenant costs (§E.2's three bullets), written before anyone is asked to
   choose;
4. that under `TENANCY_MODE=multi` **alarms are off by design** (T3.5 withholds emissions outside
   tenant scope) — which a person relying on a low alarm must be told in the strongest terms the
   project is willing to use, not discovered.

Item 4 is not this document's decision to revisit and is recorded here only so it is not lost
between the two audiences. Filed as §I.5.

**Done, §E:**

```
node tools/qc/tenant-bootstrap-arm.js --root externals/work/crm-seam
```
New harness (§G.2). Creates a tenant through the admin plane, asserts the three `tenant_secret` rows
and the `tenant_settings` row exist, asserts the plaintext root appears in the creation response and
in **no** subsequent response, then rotates the root credential and asserts: the old credential
authenticates during the overlap, does not after `expires_at`, and the new one authenticates
throughout. Non-vacuity: delete the `retiring` branch from the verification path and the
"old credential during overlap" assertion must go red.

```
node tools/qc/env-import-arm.js --env tests/fixtures/selfhost.env --report -
```
The §E.2 importer's gate: every name in the fixture is classified, and an **unclassified name is a
non-zero exit**, not a warning.

---

## F. The authorization boundary

### F.1 The line

| | tenant owner (interface 2) | platform admin (interface 1) |
|---|---|---|
| where | the consumer interface, under RLS | `bin/admin.js`, its own process, its own port |
| credential | the tenant's own root credential (§C.2b) | none — secured by unreachability (D7) |
| may | read and write everything belonging to their tenant: settings, plugin config, thresholds, their own subjects and roles, rotate their own credentials, export their own data | create, list, suspend, activate, delete a tenant; export any tenant |
| may **not** | see that any other tenant exists; create or delete a tenant; change their own `slug`, `is_active` or `id`; read `pg_catalog`; set `app.current_tenant_id`; enumerate the deployment's configuration | — (it is the deployment's own plane; its protection is that it is not routed) |

Two specific refusals worth naming because they will be asked for:

- **A tenant owner cannot change their own `slug`.** `slug` is a host label (D10) and the hoster's
  DNS points at it. A tenant that could rename itself could take a name a different tenant's DNS
  still resolves to. Slug changes are interface 1.
- **A tenant owner cannot un-suspend themselves.** `is_active` is the hoster's switch, and a
  suspended tenant answering 403 rather than 404 (`platform.sql:39-41`) is deliberate.

### F.2 How the line is enforced — **CONSEQUENCE** of D3

Not by convention, and not by a check in a route handler. Three layers, of which only the third is
code that can be forgotten.

**(1) RLS, on the four new tables.** Each carries

```sql
USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
```

character-for-character the predicate `tenant_members` and the emitted document tables already carry
— deliberately, because a second spelling is a second thing that can drift. `WITH CHECK` is what
stops a tenant owner *writing* a row for another tenant, and it is the half people omit.

`FORCE ROW LEVEL SECURITY` matters as much as `ENABLE`: without `FORCE`, the table owner bypasses
the policy, and the owner is whichever role ran `ensureSchema`. `crm-seam` already refuses to serve
as a superuser or a `BYPASSRLS` role (`platform-store.js:160-172`, `assertNotBypassingRls`), which is
the same argument made once already.

**(2) `tenants` is not reachable from a tenant context.** It carries no `tenant_id` column and no
policy, and the operational note at `platform.sql:71-78` says the application role needs an explicit
`GRANT SELECT ON tenants` and nothing more. So "may not create or delete a tenant" is enforced by
the absence of `INSERT`/`DELETE` privilege, which is not something a route handler can get wrong.
`slug` and `is_active` are refused by the same absence — they live in a table the consumer role can
only read.

**(3) `app.current_tenant_id` is set by `withTenant` and by nothing else.** `tenant-scope.js` sets it
through `set_config(..., is_local => true)` so it dies with the transaction rather than riding back
into the pool. The one thing code can get wrong here is running a tenant-owner write **outside**
`withTenant`, where `current_setting` returns empty, `NULLIF` gives `NULL`, and `tenant_id = NULL` is
`NULL` — so the policy returns **no rows** and the write fails. That is the right failure direction
and it is worth stating: a forgotten binding produces a broken feature, not a leak.

**What is *not* enforced by the database and therefore needs a test.** `enabled_plugins`,
`settings` and `extended` are opaque to RLS — the policy protects *which row* you touch, not *what
you put in it*. A tenant owner writing `{"trustProxy": "0.0.0.0/0"}` into `tenant_settings.settings`
must not have it reach `deriveEnv`. Today `deriveSettings` validates override keys against the
deployment settings object (`tenant-context.js:210-247`), which means **any key the deployment has
is overridable** — and `settings.js` has no `trustProxy`, so that example is refused by accident
rather than on purpose. The reliable form is an explicit allow-list of overridable setting keys,
derived from §B's class **T**, checked at the write boundary and again in `deriveSettings`.

**DECISION:** whether that allow-list is generated from the §B census at build time (it can be — the
census is a script, not a table) or hand-maintained. Generated is better and couples the spec to the
code, which is the point of §G.3's gate.

**Done, §F:**

```
node tools/qc/tenant-rls-arm.js --root externals/work/crm-seam
```
New harness (§G.2). Against a live PostgreSQL: bind tenant A, attempt to read and to write every one
of the four new tables for tenant B, and require **zero rows** and a policy violation respectively;
attempt the same with no binding and require zero rows; attempt an `INSERT` into `tenants` as the
consumer role and require a privilege error. Non-vacuity, and this project has learned to demand it:
re-run with `FORCE ROW LEVEL SECURITY` dropped from one table and require the cross-tenant read on
that table to **succeed** — if it still returns zero rows, the harness is not measuring the policy
and every green result above it is worthless.

```
node tools/qc/settings-allowlist-arm.js --root externals/work/crm-seam
```
Asserts that a `tenant_settings.settings` containing a **D**-class key is refused at the write
boundary and, if it somehow reaches `deriveSettings`, does not appear in the derived env.

---

## G. The harnesses, and what was and was not run

### G.1 What could not be measured, stated before the claims that depend on it

**No PostgreSQL server was available to this session.** Every piece of DDL in §A is therefore
*written* and not *executed*: it has not been parsed by PostgreSQL, the constraints have not been
shown to reject the values §A.3 says they reject, and the RLS policies have not been shown to
isolate anything. The syntax follows `platform.sql`, which does run, and the `jsonb` operators used
(`#>`, `#>>`, `?|`, `jsonb_typeof`) are ordinary — but *"it looks right"* is precisely the evidence
this project does not accept. §A's and §F's "done" commands exist because of this, and the first
person to run them should expect to find at least one syntax error.

Everything in §0.3, §B, §C.4 and §D was measured by reading or executing the code named, on
`externals/work/crm-seam` at `81a1f6ce` (and `crm-bf-auth` at `64db1f35` where §0.3(ii) says so).
The execution transcripts are reproducible from the snippets in each section.

The one check that protects D1 and that anybody can run today:

```
cd externals/work/crm-seam && npm test
```
T3.0 must not change a single-tenant result. If `single`'s behaviour moves, the change is wrong
however good the multi-tenant story is.

### G.2 New harnesses this document asks for

| harness | section | what it decides |
|---|---|---|
| `tools/qc/tenant-config-arm.js` | §A | the DDL applies; the threshold and no-proto constraints bite; one active secret per kind |
| `tools/qc/env-classification-arm.js` | §B | the census still matches the code |
| `tools/qc/tenant-credential-arm.js` | §C | D14 closes the JWT vector; `tenant_subject` closes the body vector |
| `tools/qc/t30-amendment-gate.js` | §D | every row of §D has landed |
| `tools/qc/tenant-bootstrap-arm.js`, `env-import-arm.js` | §E | creation, one-time plaintext, rotation overlap; no unclassified variable survives an import |
| `tools/qc/tenant-rls-arm.js`, `settings-allowlist-arm.js` | §F | the boundary is the database's, not a handler's |

House style applies: emit, then check the emission; and every harness carries a control arm that
must go red when the thing under test is broken.

### G.3 The census script

Reproduced here so §B is checkable without the harness. Run from a cgm-remote-monitor tree.

```js
const fs = require('fs'), path = require('path');
const ROOT = process.argv[2] || process.cwd();
const R = p => fs.readFileSync(path.join(ROOT, p), 'utf8');

// 1. the settings layer's own env spelling
const settings = require(path.resolve(ROOT, 'lib/settings.js'))();
const s1 = new Set();
settings.eachSettingAsEnv(name => { s1.add(name); return undefined; });

// 2. literal arguments to the readENV family, inside env.js
const envSrc = R('lib/server/env.js'); const s2 = new Set();
for (const m of envSrc.matchAll(/readENV(?:Truthy|Raw)?\s*\(\s*['"]([A-Z0-9_]+)['"]/g)) s2.add(m[1]);
for (const m of envSrc.matchAll(/readEnvFile\s*\(\s*['"]([A-Z0-9_]+)['"]/g))            s2.add(m[1]);
for (const m of envSrc.matchAll(/(?:shadowEnv|process\.env)\s*\[\s*['"]([A-Z0-9_]+)['"]\s*\]/g)) s2.add(m[1]);
for (const m of envSrc.matchAll(/process\.env\.([A-Z][A-Z0-9_]+)/g))              s2.add(m[1]);

// 3. plugin PREFIXES -- findExtendedSettings accepts any <PLUGIN>_* key
const s3 = new Set(fs.readdirSync(path.join(ROOT, 'lib/plugins'))
  .filter(f => f.endsWith('.js')).map(f => f.replace(/\.js$/, '').toUpperCase()));

// 4. README, to catch what 1-3 cannot see
const s4 = new Set();
for (const m of R('README.md').matchAll(/\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b/g)) s4.add(m[1]);

console.log(JSON.stringify({ s1: s1.size, s2: s2.size, s3prefixes: s3.size,
                             s4: s4.size, union: new Set([...s1,...s2,...s4]).size }));
```

Measured output on `crm-seam` @ `81a1f6ce`:
`{"s1":70,"s2":51,"s3prefixes":37,"s4":208,"union":247}`.

> **VERIFICATION NOTE (adversarial review, 2026-09-15).** The script above was re-run verbatim on
> `crm-seam` @ `81a1f6ce`. Two of the five numbers first published here did not reproduce and have
> been corrected in place:
>
> * `s3prefixes` was published as **35**; the script returns **37**, which is
>   `ls lib/plugins/*.js | wc -l`. 35 looks like a hand-adjustment excluding `index.js` and
>   `pluginbase.js`, but the script as printed does not make it, so the transcript and the script
>   disagreed. The prefix set is not part of the union, so nothing downstream moves.
> * `s2` was published as **43**. The regex in the version first published matched
>   single-quoted literals only, and `lib/server/env.js` writes most of this family with DOUBLE
>   quotes (`env.js:114`, `readENVTruthy("SECURE_HSTS_HEADER_INCLUDESUBDOMAINS", false)`). The
>   quote class has been widened above; the count is **51**.
>
> `s1`, `s4` and the **union of 247** all reproduce exactly, and the union is unchanged by the
> widened regex — that insensitivity was re-measured rather than assumed.

### G.4 The credential harness's arms, as executed

The §C.4 tables were produced by requiring `lib/server/tenant-middleware.js` directly and calling
`presentedCredential`, `tenantClaim` and `credentialRefusal` with stub enclaves wrapping
`jsonwebtoken` under two, then one, signing key. `jsonwebtoken` is the module `enclave.js` itself
uses (`enclave.js:5`), so the signature semantics are the shipping ones and not a model of them.
Every arm has a control in the same table, and the body-vector arm's control (the same credential
moved to the query string) is what distinguishes *"the check passes it"* from *"the check never saw
it"*.

---

## H. Proposed register entries

Per the project's rule, **no ids are allocated here.** Each is stated as the register would state it,
for a later agent to number.

**H.1 — `lib/plugins/webhook.js:36-39` reads four variables straight from `process.env`.**
`WEBHOOK_PROTOCOL`, `WEBHOOK_HOST`, `WEBHOOK_PORT`, `WEBHOOK_PATH` bypass `lib/server/env.js`, the
settings layer and `extendedSettings`. The reads are inside the exported plugin factory and run
when `require('./webhook')(ctx)` is called (`lib/plugins/index.js:71`, `:106`) — **not** at module
scope and not at require time, as an earlier draft of this entry said. Undocumented
(`grep -c WEBHOOK_ README.md` = 0). Single-tenant impact: an operator cannot configure the plugin
through any documented mechanism and it is not listed with the others. Multi-tenant impact: every
tenant's webhook posts to the same host and no per-tenant configuration can change it.
*Severity: low today, medium under `multi`. §1b pre-release for the multi half; the undocumented
half ships to operators now.*

**H.2 — `SECURE_HSTS_HEADER_INCLUDESUBDOMAINS` has two spellings and the documented one is the only
one that works.** `lib/settings.js:48` defines `secureHstsHeaderIncludeSubdomains`, so
`nameFromKey(..., 'env')` produces `SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS`, which the settings layer
accepts and stores. `lib/server/env.js:114` reads `SECURE_HSTS_HEADER_INCLUDESUBDOMAINS` (no
underscore) and `lib/server/app.js:144` reads `env.secureHstsHeaderIncludeSubdomains`. Grep finds
**no** consumer of `settings.secureHstsHeaderIncludeSubdomains` in `lib/`, `views/` or `static/`.
The README (line 399) documents the working spelling, so an operator following the README is fine
and an operator reading the settings dictionary is not. The same dead duplication without a spelling
divergence exists for `insecureUseHttp`, `secureHstsHeader`, `secureHstsHeaderPreload` and
`secureCsp` — four, not three, which with the HSTS key makes the five named below. *Severity: low. Ships
to operators today. Matters to T3.0 because a tenant-admin UI generated from the settings dictionary
would offer five settings that do nothing, one of them a security header.*

**H.3 — `MONGODB_COLLECTION` is documented and read by nothing.** `README.md:240` documents it as
"The Mongo collection where CGM entries are stored", default `entries`. Grep over `lib/` and `bin/`
finds no reader; the code reads `ENTRIES_COLLECTION` or `MONGO_COLLECTION` (`env.js:211`). An
operator who sets it gets the default and no error. *Severity: low. Ships to operators today.
Documentation defect with no code landing site — the fix is to correct the README.*

**H.4 — ten API v3 variables bypass the configuration system entirely, are undocumented, and one
family of them deletes data.** `lib/api3/index.js:24-38`'s `setENVTruthy` reads `process.env[varName]`
directly. Call sites: `API3_SECURITY_ENABLE`, `API3_DEDUP_FALLBACK_ENABLED`,
`API3_CREATED_AT_FALLBACK_ENABLED`, `API3_MAX_LIMIT` (`index.js:73-76`) and
`API3_AUTOPRUNE_<COLLECTION>` for six registered collections (`generic/collection.js:32`).
`grep -c API3_ README.md` = 0; `grep -c API3_` in `lib/server/env.js` and `lib/settings.js` = 0 each.
`collection.js:129-152` uses the autoprune value to compute `deleteBefore` and calls
`storage.deleteManyOr` without awaiting the result. Single-tenant impact: an undocumented
environment variable silently and irreversibly deletes a person's glucose history, and
`API3_SECURITY_ENABLE=false` disables v3 authorization with nothing in the README to say so.
Multi-tenant impact: retention is the most per-tenant setting in the system and is set
deployment-wide, invisibly, for everyone. *Severity: **high**. Ships to operators today. This is the
sharpest thing this task found.*

**H.5 — the deployment mints JWTs with no tenant claim, so under `TENANCY_MODE=multi` the tenant
check refuses every token the deployment issues.** `lib/authorization/index.js:289` is the only
caller of `signJWT` and its payload is `{ accessToken }`. `tenantClaim`
(`tenant-middleware.js:139-151`) requires `payload.tenant`; `credentialRefusal` (`:181-192`) returns
`MSG_NO_CLAIM` because `requireTokenClaim` defaults true (`:208`). Reproduced by executing both
modules with the exact payload line 289 mints; the control (the same token with a `tenant` field)
proceeds. The claim check and the minting path have never been exercised against each other.
*Severity: medium. **§1b pre-release** — it affects the tenancy branches only, no operator runs
`multi`. Fails safe (refuses rather than admits), which is why it has gone unnoticed. Must be fixed
by the task that introduces the per-tenant key, because that task chooses the payload.*

**H.7 — `verifyThresholds()` silently rewrites a person's alarm thresholds and only logs it.**
`lib/settings.js:302-324`. When the invariant `bgLow < bgTargetBottom < bgTargetTop < bgHigh` fails,
the function does not refuse the configuration: it mutates the offending value to a neighbour ±1
(`thresholds.bgHigh = thresholds.bgTargetTop + 1`, and three siblings) and emits `console.warn`.
An operator who sets `BG_HIGH` below `BG_TARGET_TOP` — for example by entering mmol/L numbers on a
site whose other thresholds are mg/dL — gets a running site whose urgent-high alarm fires at a
number they never chose, with no indication anywhere a person looks. Verified by reading
`settings.js:302-324` on `crm-seam` and by the §A.3 control pair (deployment path 56/81/180/252 vs
override path 3.1/4.5/10/14). Single-tenant impact: ships to every operator today. Multi-tenant
impact: it is the last thing standing between a tenant-owner form and an alarm that does not fire,
and it fails quietly. *Severity: medium, and it is a SILENT failure on an alarm path, which this
project grades above its severity. Ships to operators today. The fix is to return what was changed
to whoever wrote it, not to change the repair behaviour — repairing is the safe direction; not
saying so is not.*

**H.6 — `enclave.setJWTKey` has no caller.** `enclave.js:54-56`; `grep -rn setJWTKey lib/ bin/`
returns the definition and nothing else. The signing key is set once at construction from a file
(`enclave.js:30`, `node_modules/.cache/_ns_cache/randomString`). Either dead code or T3.0's
injection point. *Severity: low. §1b pre-release. Listed so it is decided rather than left.*

---

## I. Open questions

**I.1 — There is no migration machinery for the platform schema, and adding four tables needs one.
Who settles it: the maintainer, with T3.2's author.** `ensureSchema` (`platform-store.js:120-158`)
runs the whole DDL only when zero platform tables exist and throws when *some but not all* are
present. Adding tables to `platform.sql` without touching `PLATFORM_TABLES` means an existing
two-table database passes the completeness check and silently lacks the new tables; adding them to
`PLATFORM_TABLES` means it throws and tells the operator to repair it by hand. Neither is a
migration. Whether T3.0 introduces one, or whether the platform schema is young enough that "drop
and recreate" is the honest answer, is not this document's call — it depends on whether any
deployment anywhere has a `tenants` table, which I cannot determine from this machine.

**I.2 — Does `subject_id` become `text` (an ALTER on a shipped table), or does `tenant_members`
reference `tenant_subject` by a surrogate key? Who settles it: T3.2's author.** §D.2 row 4 recommends
the ALTER. The counter-argument is that `tenant_members` is the *platform's* record of who may act
in a tenant and `tenant_subject` is the *tenant's* own subject list, and conflating them may be
wrong — a hoster's support engineer granted access to a tenant is a member without being a subject.
If they are genuinely different things, `subject_id` should be renamed rather than retyped.

**I.3 — `IMPORT_CONFIG` was classified **D** without being read. Who settles it: whoever owns §B's
gate.** It is a documented mechanism for importing configuration wholesale. If it can import
*settings*, then under `multi` it is a deployment-wide variable that writes per-tenant state, which
would be a D15 violation wearing a **D** classification. I ran out of task before opening it. The
§B gate will not catch this, because it checks that names are classified and not that they are
classified correctly.

**I.4 — What wraps `tenant_secret.material`, and may the hoster read a tenant's plugin credentials?
Who settles it: the maintainer.** §C.5. The second half is a policy question about what the
Foundation is promising a tenant, not an engineering one, and the engineering follows from it: if
the answer is "no", server-side Dexcom Share polling becomes impossible and the hosted product
changes shape.

**I.5 — Alarms are off under `TENANCY_MODE=multi` by design (T3.5). What is a tenant owner told, and
when? Who settles it: the maintainer, with whoever writes user-facing text.** This document does not
revisit the decision. But a tenant-owner configuration surface that presents an alarm-threshold
form on a deployment where alarms do not fire is a surface that misleads someone about whether
they will be woken up. Either the form says so at the top, in plain language, or the thresholds are
not offered until T3.5 arms. Recorded here because it falls exactly between this task and that one.

**I.7 — A tenant owner who loses their root credential has no recovery path that §F.1 permits.
Who settles it: the maintainer.** §E.1 issues the plaintext once and offers no re-display; §E.3's
rotation needs the credential being replaced. The only remaining actor is the hoster's plane, and
§D.2 row 5 and §F.1 both forbid it growing a credential route. One of those three has to give.
Note that the answer decides something about the product, not only the code: if the hoster can
reissue a tenant's root credential, the hoster can impersonate a tenant, which is the same question
§I.4's second half asks about plugin credentials.

**I.6 — Is the §B classification correct, or merely complete? Who settles it: review.** §G.3's gate
proves every name is classified and that the list matches the code. It cannot prove a name is in the
right class. The judgement calls most worth attacking are: usernames, patient ids and serial numbers
placed in **TS** rather than **T**; `TRUST_PROXY` and `TENANT_HOST_HEADER` held in **D** (§B.4's
note); and `API3_SECURITY_ENABLE` in **D**, where an argument exists that under `multi` it should not
be settable by anyone.

---

## J. Decision index

Everything the maintainer must say yes or no to before code is written, in one place.

| # | decision | section | recommendation |
|---|---|---|---|
| J1 | `tenant_members.subject_id` type change on a shipped table | §D.2 r4, §I.2 | `text`, or rename if it is a different concept |
| J2 | constant-time credential comparison replacing `==` in `enclave.isApiKey` | §C.2c | yes |
| J3 | offer subject-salt rotation at all in release 1 | §C.3 | **no** — delete-and-recreate the subject instead |
| J4 | what wraps `tenant_secret.material` | §C.5, §I.4 | env-sourced KEK, `key_ref` kept so KMS can arrive later |
| J5 | may the hoster read a tenant's plugin credentials | §C.5, §I.4 | policy question; engineering follows |
| J6 | is the self-host → hosted importer in scope for release 1 | §E.2 | **no** — ship export first |
| J7 | overridable-settings allow-list: generated from the §B census, or hand-maintained | §F.2 | generated |
| J8 | `requireTokenClaim` becomes a constant once `tenant_subject` lands | §D.1 r6 | yes, but not before |
| J9 | `enclave.setJWTKey` — injection point or delete | §D.1 r5, §H.6 | injection point |
| J10 | platform-schema migration strategy | §I.1 | needs the maintainer's knowledge of deployed state |
| J11 | `tenant_settings_thresholds_mgdl`: refuse partial threshold overrides outright (all four keys or none), or extend the constraint to hold per key | §A.2 reviewer note, §A.3 | refuse partial writes; normalise and echo at the write boundary |
| J12 | how the hoster's plane writes bootstrap rows into `FORCE`-RLS tables: bind in `asTenant`, add an admin policy, or move bootstrap to the tenant's first request | §E.1 blocking note | bind in `asTenant` and amend that helper's contract and comment together |
| J13 | who reissues a tenant root credential that has been lost, given §F.1 forbids the admin plane a credential route | §E.1, §I.7 | must be answered before release; it is a product question first |
| J14 | widen §B's census sources and grep gate to `bin/` and to injected-`env` readers before the census is quoted as closed | §B.2 gap 5 | yes — the enumeration is currently the `single` entrypoint's, not the deployment's |

Everything else in this document is marked **CONSEQUENCE** and follows from D13, D14 and D15 without
a new decision. If any of those three is reopened, §C and §D are the sections that fall.
