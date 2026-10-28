-- 0004: operator policy (D22 layer 2), written on the operator plane (D7).
--
-- deployment_policy      -- one deployment policy: per setting, a default, a
--                           mode (open, bounded, pinned), a constraint, a pin.
-- tenant_policy_override -- operator overrides on individual tenants. An
--                           override row REPLACES the deployment row for that
--                           tenant and setting (whole-row; open question).
--
-- Every row is checked against the project floor in config_setting. The floor
-- check is in the database as well as in code because an operator writes these
-- rows, and a floor an operator's tool could skip is not a floor.

CREATE TABLE deployment_policy (
  setting_key     text PRIMARY KEY REFERENCES config_setting (key),
  mode            text NOT NULL CHECK (mode IN ('open', 'bounded', 'pinned')),
  default_value   jsonb,
  constraint_spec jsonb NOT NULL DEFAULT '{}'::jsonb,
  pin_value       jsonb,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  updated_by      text NOT NULL,
  CONSTRAINT deployment_policy_pin_iff_pinned CHECK ((mode = 'pinned') = (pin_value IS NOT NULL)),
  CONSTRAINT deployment_policy_bounded_has_constraint CHECK (mode <> 'bounded' OR constraint_spec <> '{}'::jsonb)
);

CREATE TABLE tenant_policy_override (
  tenant_id       uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
  setting_key     text NOT NULL REFERENCES config_setting (key),
  mode            text NOT NULL CHECK (mode IN ('open', 'bounded', 'pinned')),
  default_value   jsonb,
  constraint_spec jsonb NOT NULL DEFAULT '{}'::jsonb,
  pin_value       jsonb,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  updated_by      text NOT NULL,
  PRIMARY KEY (tenant_id, setting_key),
  CONSTRAINT tenant_policy_override_pin_iff_pinned CHECK ((mode = 'pinned') = (pin_value IS NOT NULL)),
  CONSTRAINT tenant_policy_override_bounded_has_constraint CHECK (mode <> 'bounded' OR constraint_spec <> '{}'::jsonb)
);

ALTER TABLE tenant_policy_override ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_policy_override FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_policy_override_tenant_isolation ON tenant_policy_override
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- Floor and well-formedness check for a policy row. Errors are 23514
-- (check_violation) with a message that starts with 'floor:' or 'policy:'.
CREATE FUNCTION cfg_policy_row_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s config_setting;
BEGIN
  SELECT * INTO s FROM config_setting WHERE key = NEW.setting_key;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'policy: % is not a hosted setting', NEW.setting_key USING ERRCODE = '23503';
  END IF;
  IF TG_TABLE_NAME = 'tenant_policy_override' AND s.scope <> 'tenant' THEN
    RAISE EXCEPTION 'policy: % is a deployment value and cannot be overridden per tenant', s.key
      USING ERRCODE = '23514';
  END IF;
  IF s.scope = 'deployment' AND NEW.mode <> 'pinned' THEN
    RAISE EXCEPTION 'policy: % is a deployment value and must be pinned', s.key USING ERRCODE = '23514';
  END IF;
  IF NOT cfg_constraint_ok(s.value_type, s.enum_values, NEW.constraint_spec) THEN
    RAISE EXCEPTION 'policy: malformed constraint for %', s.key USING ERRCODE = '23514';
  END IF;
  IF NOT cfg_within(s.value_type, s.enum_values, CASE WHEN NEW.mode = 'bounded' THEN NEW.constraint_spec ELSE s.floor END, s.floor) THEN
    RAISE EXCEPTION 'floor: the constraint for % offers values below the project floor', s.key
      USING ERRCODE = '23514';
  END IF;
  IF NEW.default_value IS NOT NULL THEN
    IF NOT cfg_value_ok(s.value_type, s.enum_values, NEW.default_value) THEN
      RAISE EXCEPTION 'policy: default for % is not a %', s.key, s.value_type USING ERRCODE = '23514';
    END IF;
    IF NOT cfg_satisfies(s.value_type, s.enum_values, s.floor, NEW.default_value) THEN
      RAISE EXCEPTION 'floor: default for % breaks the project floor', s.key USING ERRCODE = '23514';
    END IF;
    IF NEW.mode = 'bounded' AND NOT cfg_satisfies(s.value_type, s.enum_values, NEW.constraint_spec, NEW.default_value) THEN
      RAISE EXCEPTION 'policy: default for % is outside its own constraint', s.key USING ERRCODE = '23514';
    END IF;
  END IF;
  IF NEW.pin_value IS NOT NULL THEN
    IF NOT cfg_value_ok(s.value_type, s.enum_values, NEW.pin_value) THEN
      RAISE EXCEPTION 'policy: pin for % is not a %', s.key, s.value_type USING ERRCODE = '23514';
    END IF;
    IF NOT cfg_satisfies(s.value_type, s.enum_values, s.floor, NEW.pin_value) THEN
      RAISE EXCEPTION 'floor: pin for % breaks the project floor', s.key USING ERRCODE = '23514';
    END IF;
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

CREATE TRIGGER deployment_policy_check BEFORE INSERT OR UPDATE ON deployment_policy
  FOR EACH ROW EXECUTE FUNCTION cfg_policy_row_check();
CREATE TRIGGER tenant_policy_override_check BEFORE INSERT OR UPDATE ON tenant_policy_override
  FOR EACH ROW EXECUTE FUNCTION cfg_policy_row_check();

-- The policy row that governs (tenant, setting): override, else deployment,
-- else the catalogue's shipped default. Runs as the caller, so the override
-- lookup is under RLS and only ever sees the bound tenant's overrides.
CREATE FUNCTION cfg_policy_for(p_tenant uuid, p_key text,
  OUT mode text, OUT default_value jsonb, OUT constraint_spec jsonb, OUT pin_value jsonb, OUT source text)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  SELECT o.mode, o.default_value, o.constraint_spec, o.pin_value, 'override'
    INTO mode, default_value, constraint_spec, pin_value, source
    FROM tenant_policy_override o WHERE o.tenant_id = p_tenant AND o.setting_key = p_key;
  IF FOUND THEN RETURN; END IF;
  SELECT d.mode, d.default_value, d.constraint_spec, d.pin_value, 'deployment'
    INTO mode, default_value, constraint_spec, pin_value, source
    FROM deployment_policy d WHERE d.setting_key = p_key;
  IF FOUND THEN RETURN; END IF;
  SELECT c.default_mode, NULL::jsonb, c.default_constraint, NULL::jsonb, 'catalogue'
    INTO mode, default_value, constraint_spec, pin_value, source
    FROM config_setting c WHERE c.key = p_key;
END $$;
