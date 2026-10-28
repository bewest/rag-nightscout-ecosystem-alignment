-- 0003: the catalogues the project ships with the code.
--
-- config_setting   -- one row per census setting name that hosted configuration
--                     may carry at all. A name that is NOT here cannot appear in
--                     any policy or owner row (foreign keys). That absence is how
--                     the "not offered" floors (API_SECRET, TREATMENTS_AUTH,
--                     IMPORT_CONFIG, TRUST_PROXY, BASE_URL, DEBUG_LOGGING,
--                     API3_SECURITY_ENABLE, API3_SETTINGS_STRICT_READ_ENABLED)
--                     reach the database. Class D (deployment-level) names are
--                     absent too: they are environment variables of the role
--                     that reads them.
-- integration_kind -- the driver catalogue: one row per integration kind, with
--                     the schema its settings must satisfy and the names of the
--                     credential parts it needs (names only, never values).
--
-- Only migrations write these tables. No application role is granted INSERT,
-- UPDATE or DELETE on them (0008), so an operator cannot widen a floor by
-- editing the catalogue.

-- Value grammar, shared by floors, operator constraints, defaults, pins and
-- owner values. Written as nested IFs on purpose: SQL does not promise the
-- order in which AND evaluates, so a type guard joined by AND to a cast can
-- still let the cast run first (the config-surface document's A.2 hole 2).
CREATE FUNCTION cfg_value_ok(p_type text, p_enum text[], v jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE n numeric;
BEGIN
  IF v IS NULL THEN RETURN false; END IF;
  IF p_type = 'boolean' THEN
    RETURN jsonb_typeof(v) = 'boolean';
  ELSIF p_type = 'integer' THEN
    IF jsonb_typeof(v) <> 'number' THEN RETURN false; END IF;
    n := (v #>> '{}')::numeric;
    RETURN n = trunc(n);
  ELSIF p_type IN ('enum', 'ordinal') THEN
    IF jsonb_typeof(v) <> 'string' THEN RETURN false; END IF;
    RETURN (v #>> '{}') = ANY (p_enum);
  ELSIF p_type = 'role_list' THEN
    IF jsonb_typeof(v) <> 'array' OR jsonb_array_length(v) = 0 THEN RETURN false; END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(v) e
                WHERE jsonb_typeof(e) <> 'string' OR NOT ((e #>> '{}') = ANY (p_enum))) THEN
      RETURN false;
    END IF;
    RETURN (SELECT count(DISTINCT e) FROM jsonb_array_elements(v) e) = jsonb_array_length(v);
  ELSIF p_type = 'host_list' THEN
    IF jsonb_typeof(v) <> 'array' THEN RETURN false; END IF;
    RETURN NOT EXISTS (
      SELECT 1 FROM jsonb_array_elements(v) e
       WHERE jsonb_typeof(e) <> 'string'
          OR (e #>> '{}') !~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$');
  END IF;
  RETURN false;
END $$;

-- Does value v (already known to be well typed) satisfy constraint c?
-- Constraint grammar: {} | {"allowed": [..]} | {"min": x} | {"max": x}, combinable.
CREATE FUNCTION cfg_satisfies(p_type text, p_enum text[], c jsonb, v jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE allowed text[];
BEGIN
  IF c IS NULL OR c = '{}'::jsonb THEN RETURN true; END IF;
  IF c ? 'allowed' THEN
    allowed := ARRAY(SELECT jsonb_array_elements_text(c -> 'allowed'));
    IF p_type IN ('role_list', 'host_list') THEN
      IF EXISTS (SELECT 1 FROM jsonb_array_elements_text(v) e WHERE NOT (e = ANY (allowed))) THEN
        RETURN false;
      END IF;
    ELSIF p_type IN ('enum', 'ordinal') THEN
      IF NOT ((v #>> '{}') = ANY (allowed)) THEN RETURN false; END IF;
    ELSE
      RETURN false;
    END IF;
  END IF;
  IF c ? 'min' THEN
    IF p_type = 'integer' THEN
      IF (v #>> '{}')::numeric < (c ->> 'min')::numeric THEN RETURN false; END IF;
    ELSIF p_type = 'ordinal' THEN
      IF array_position(p_enum, v #>> '{}') < array_position(p_enum, c ->> 'min') THEN RETURN false; END IF;
    ELSE
      RETURN false;
    END IF;
  END IF;
  IF c ? 'max' THEN
    IF p_type = 'integer' THEN
      IF (v #>> '{}')::numeric > (c ->> 'max')::numeric THEN RETURN false; END IF;
    ELSIF p_type = 'ordinal' THEN
      IF array_position(p_enum, v #>> '{}') > array_position(p_enum, c ->> 'max') THEN RETURN false; END IF;
    ELSE
      RETURN false;
    END IF;
  END IF;
  RETURN true;
END $$;

-- Is constraint c well formed for this type? (Keys known, values well typed.)
CREATE FUNCTION cfg_constraint_ok(p_type text, p_enum text[], c jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE k text;
BEGIN
  IF c IS NULL OR jsonb_typeof(c) <> 'object' THEN RETURN false; END IF;
  FOR k IN SELECT jsonb_object_keys(c) LOOP
    IF k NOT IN ('allowed', 'min', 'max') THEN RETURN false; END IF;
  END LOOP;
  IF c ? 'allowed' THEN
    IF p_type NOT IN ('enum', 'ordinal', 'role_list', 'host_list') THEN RETURN false; END IF;
    IF jsonb_typeof(c -> 'allowed') <> 'array' THEN RETURN false; END IF;
    IF p_type <> 'host_list' AND EXISTS (
         SELECT 1 FROM jsonb_array_elements(c -> 'allowed') e
          WHERE jsonb_typeof(e) <> 'string' OR NOT ((e #>> '{}') = ANY (p_enum))) THEN
      RETURN false;
    END IF;
  END IF;
  IF c ? 'min' OR c ? 'max' THEN
    IF p_type = 'integer' THEN
      IF c ? 'min' AND NOT cfg_value_ok('integer', NULL, c -> 'min') THEN RETURN false; END IF;
      IF c ? 'max' AND NOT cfg_value_ok('integer', NULL, c -> 'max') THEN RETURN false; END IF;
    ELSIF p_type = 'ordinal' THEN
      IF c ? 'min' AND NOT cfg_value_ok('ordinal', p_enum, c -> 'min') THEN RETURN false; END IF;
      IF c ? 'max' AND NOT cfg_value_ok('ordinal', p_enum, c -> 'max') THEN RETURN false; END IF;
    ELSE
      RETURN false;
    END IF;
  END IF;
  RETURN true;
END $$;

-- Does the inner constraint offer nothing the outer one (the floor) forbids?
-- Only keys the inner constraint states are compared: a key it leaves out adds
-- no restriction of its own, and owner values are checked against the floor
-- separately. Used so an operator cannot OFFER an owner a value below a floor
-- (census 3a row 1: "an allowed list within the floor's three").
CREATE FUNCTION cfg_within(p_type text, p_enum text[], inner_c jsonb, outer_c jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  IF outer_c IS NULL OR outer_c = '{}'::jsonb THEN RETURN true; END IF;
  IF inner_c ? 'allowed' AND outer_c ? 'allowed' THEN
    IF EXISTS (SELECT 1 FROM jsonb_array_elements_text(inner_c -> 'allowed') e
                WHERE NOT (e = ANY (ARRAY(SELECT jsonb_array_elements_text(outer_c -> 'allowed'))))) THEN
      RETURN false;
    END IF;
  END IF;
  IF inner_c ? 'min' AND outer_c ? 'min' THEN
    IF NOT cfg_satisfies(p_type, p_enum, jsonb_build_object('min', outer_c -> 'min'), inner_c -> 'min') THEN RETURN false; END IF;
  END IF;
  IF inner_c ? 'max' AND outer_c ? 'max' THEN
    IF NOT cfg_satisfies(p_type, p_enum, jsonb_build_object('max', outer_c -> 'max'), inner_c -> 'max') THEN RETURN false; END IF;
  END IF;
  RETURN true;
END $$;

CREATE TABLE config_setting (
  -- The census name (t30-census-dev-2026-10-27.md), or a namespaced policy key
  -- such as INTEGRATION_MAX:webhook.
  key                text PRIMARY KEY
                     CHECK (key ~ '^[A-Z][A-Z0-9_]*(:[a-z][a-z0-9-]*)?$'),
  -- Every row is a TENANT-FACING setting. Deployment-level (class D) values
  -- live in each role's environment, not here (maintainer, 2026-10-27).
  value_type         text NOT NULL
                     CHECK (value_type IN ('boolean', 'integer', 'enum', 'ordinal', 'role_list', 'host_list')),
  -- enum / role_list: the values the type admits. ordinal: in order, loosest first.
  enum_values        text[],
  owner_settable     boolean NOT NULL,
  -- Alarm thresholds and enables. Hidden from the owner until the execution
  -- plan's 7a gate passes (D22, census 3a row 10): see CHECK below.
  is_alarm           boolean NOT NULL DEFAULT false,
  -- Permanent deletion (API3_AUTOPRUNE_*): an owner value needs an explicit
  -- confirmation and a recorded export offer (floor, data and log safety).
  needs_confirmation boolean NOT NULL DEFAULT false,
  -- The PROJECT FLOOR, in the constraint grammar. Shipped by the project; no
  -- operator policy can loosen it.
  floor              jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- What applies when the operator has written no row for this setting. A
  -- lab choice, listed as an open question in the schema spec.
  default_mode       text NOT NULL DEFAULT 'pinned'
                     CHECK (default_mode IN ('open', 'bounded', 'pinned')),
  default_constraint jsonb NOT NULL DEFAULT '{}'::jsonb,
  census_row         integer CHECK (census_row BETWEEN 1 AND 12),
  note               text NOT NULL DEFAULT '',

  CONSTRAINT config_setting_enum_iff_enumerated
    CHECK ((value_type IN ('enum', 'ordinal', 'role_list')) = (enum_values IS NOT NULL)),
  -- FLOOR (alarm settings hidden until 7a's gate). A post-gate migration drops
  -- this CHECK; until then no alarm setting can be marked owner-settable.
  CONSTRAINT config_setting_alarms_hidden
    CHECK (NOT (is_alarm AND owner_settable)),
  -- FLOOR (no deployment secrets; secrets are never settings). A name that
  -- looks like a credential cannot enter the catalogue, so no policy or owner
  -- row can ever carry one. Credentials live in the secrets component and are
  -- referenced from integration records.
  CONSTRAINT config_setting_no_secret_names
    CHECK (key !~ '(SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE|APIKEY|_KEY$|_KEY_|_KEY:)'),
  CONSTRAINT config_setting_floor_ok
    CHECK (jsonb_typeof(floor) = 'object' AND cfg_constraint_ok(value_type, enum_values, floor)),
  CONSTRAINT config_setting_default_constraint_ok
    CHECK (cfg_constraint_ok(value_type, enum_values, default_constraint)
           AND cfg_within(value_type, enum_values, default_constraint, floor))
);

-- A credential reference: names a secret held by the secrets component
-- (`nightscout serve secrets`, D22). Never the secret. The format is a lab
-- placeholder (open question in the schema spec): backend name, then an opaque id.
CREATE FUNCTION cfg_is_secret_ref(t text) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT t ~ '^sref:v1:[a-z][a-z0-9-]{0,31}:[A-Za-z0-9_-]{22,64}$'
$$;

-- No settings field of any integration kind may be named like a credential:
-- credentials go in secret parts (names only), whose values live in the
-- secrets component.
CREATE FUNCTION cfg_schema_fields_not_secret(s jsonb) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_typeof(s) = 'object'
     AND jsonb_typeof(s -> 'fields') = 'object'
     AND NOT EXISTS (
       SELECT 1 FROM jsonb_object_keys(s -> 'fields') f
        WHERE f ~* '(pass|secret|token|credential|private|key|signing|cookie|session)')
$$;

CREATE TABLE integration_kind (
  kind                  text PRIMARY KEY CHECK (kind ~ '^[a-z][a-z0-9-]*$'),
  -- {"fields": {name: {"type": "string|integer|boolean|enum|url",
  --                     "required": bool, "enum": [...], "max": n,
  --                     "hosts": "driver|public"}}}; unknown fields are refused.
  settings_schema       jsonb NOT NULL
                        CONSTRAINT integration_kind_no_secret_fields CHECK (cfg_schema_fields_not_secret(settings_schema)),
  -- Hosts a url field marked "hosts":"driver" may name (network-safety floor).
  driver_hosts          text[] NOT NULL DEFAULT '{}',
  -- Names of credential parts. The owner's parts are referenced from the
  -- tenant's integration record; the operator's from deployment_integration.
  owner_secret_parts    text[] NOT NULL DEFAULT '{}',
  operator_secret_parts text[] NOT NULL DEFAULT '{}',
  census_names          text NOT NULL DEFAULT ''
);
