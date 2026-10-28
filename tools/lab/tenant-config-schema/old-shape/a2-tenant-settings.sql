-- The OLD shape: tenant_settings exactly as drafted in
-- docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md §A.2 (extracted
-- verbatim by the lab, comments included). Applied on top of 0001 only, to measure
-- the §A.3 NULL-passing CHECK hazard. Not a migration.

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
  -- REVIEWER NOTE (2026-09-15, OPEN). THIS CONSTRAINT DOES NOT YET DO
  -- WHAT A.3 NEEDS, and A.3 is the safety section. Two holes, read-derived
  -- from PostgreSQL's documented semantics (not executed -- G.1):
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
  -- and not a syntax fix: see row J11.
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
  -- REVIEWER NOTE (2026-09-15, OPEN; read-derived): AS WRITTEN THIS IS
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

-- Lab addition so the owner role can write it (the draft has no grants).
GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_settings TO ns_tenant_admin;
GRANT SELECT ON tenants TO ns_tenant_admin;
