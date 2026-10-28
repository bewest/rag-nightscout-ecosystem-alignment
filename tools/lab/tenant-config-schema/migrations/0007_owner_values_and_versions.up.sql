-- 0007: owner values (D22 layer 3), the alarm-threshold side-table, and versions.
--
-- tenant_setting_value    -- one row per setting the owner has set. Accepted
--                            only within the governing policy row and the floor.
-- tenant_alarm_thresholds -- the owner's four glucose thresholds, typed columns,
--                            mg/dL only, all four or none (A.3, J11).
-- tenant_config_version   -- append-only: each change is a numbered version
--                            recording who, when, what kind, and the full
--                            owner-scope state after it. Rollback writes a new
--                            version whose state equals an older one.
--
-- The invariant the database holds: at commit, a tenant's owner-scope state
-- equals the state recorded in its newest version. A write that skips
-- versioning cannot commit.

CREATE TABLE tenant_setting_value (
  tenant_id         uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
  setting_key       text NOT NULL REFERENCES config_setting (key),
  value             jsonb NOT NULL,
  -- floor (data safety): permanent deletion needs both, recorded at the write
  confirmed_at      timestamptz,
  export_offered_at timestamptz,
  updated_at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, setting_key)
);

ALTER TABLE tenant_setting_value ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_setting_value FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_setting_value_tenant_isolation ON tenant_setting_value
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- NULL when an owner may store value v for setting k on tenant t now;
-- otherwise the reason, naming the operator rule behind it. Shared by the
-- write trigger and by cfg_rollback, which reports every blocked setting at once.
CREATE FUNCTION cfg_owner_value_error(p_tenant uuid, p_key text, p_value jsonb, p_confirmed boolean)
RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE s config_setting; pol record;
BEGIN
  SELECT * INTO s FROM config_setting WHERE key = p_key;
  IF NOT FOUND THEN RETURN format('policy: %s is not a hosted setting', p_key); END IF;
  IF NOT s.owner_settable THEN RETURN format('policy: %s is not set by the owner', s.key); END IF;
  IF NOT cfg_value_ok(s.value_type, s.enum_values, p_value) THEN
    RETURN format('policy: %s must be a %s', s.key, s.value_type);
  END IF;
  IF NOT cfg_satisfies(s.value_type, s.enum_values, s.floor, p_value) THEN
    RETURN format('floor: %s = %s breaks the project floor %s', s.key, p_value, s.floor);
  END IF;
  SELECT * INTO pol FROM cfg_policy_for(p_tenant, p_key);
  IF pol.mode = 'pinned' THEN
    RETURN format('policy: %s is pinned by the operator (%s rule: pinned to %s)', s.key, pol.source, COALESCE(pol.pin_value::text, 'the code default'));
  END IF;
  IF pol.mode = 'bounded' AND NOT cfg_satisfies(s.value_type, s.enum_values, pol.constraint_spec, p_value) THEN
    RETURN format('policy: %s = %s is outside the operator''s constraint (%s rule: bounded %s)', s.key, p_value, pol.source, pol.constraint_spec);
  END IF;
  IF s.needs_confirmation AND NOT p_confirmed THEN
    RETURN format('floor: %s deletes data permanently; it needs an explicit confirmation and an export offered first', s.key);
  END IF;
  RETURN NULL;
END $$;

CREATE FUNCTION cfg_owner_value_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE err text;
BEGIN
  err := cfg_owner_value_error(NEW.tenant_id, NEW.setting_key, NEW.value,
                               NEW.confirmed_at IS NOT NULL AND NEW.export_offered_at IS NOT NULL);
  IF err IS NOT NULL THEN
    RAISE EXCEPTION '%', err USING ERRCODE = CASE WHEN err LIKE '%not a hosted setting' THEN '23503' ELSE '23514' END;
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

CREATE TRIGGER tenant_setting_value_check BEFORE INSERT OR UPDATE ON tenant_setting_value
  FOR EACH ROW EXECUTE FUNCTION cfg_owner_value_check();

-- The A.3 safety table. Typed, NOT NULL columns: there is no JSON path to be
-- absent and so no NULL for a CHECK to pass on. Stored in mg/dL whatever the
-- display unit; the write boundary converts mmol and echoes the stored numbers.
-- Bounds 20..600 are A.2's (20 is below any real mg/dL threshold and above any
-- real mmol one); the exact bounds are for clinical review.
CREATE TABLE tenant_alarm_thresholds (
  tenant_id              uuid PRIMARY KEY REFERENCES tenants (id) ON DELETE CASCADE,
  bg_low_mgdl            integer NOT NULL,
  bg_target_bottom_mgdl  integer NOT NULL,
  bg_target_top_mgdl     integer NOT NULL,
  bg_high_mgdl           integer NOT NULL,
  -- what the person typed in; display only, never a conversion input here
  entered_units          text NOT NULL CHECK (entered_units IN ('mg/dl', 'mmol')),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT tenant_alarm_thresholds_plausible_mgdl CHECK (
        bg_low_mgdl           BETWEEN 20 AND 600
    AND bg_target_bottom_mgdl BETWEEN 20 AND 600
    AND bg_target_top_mgdl    BETWEEN 20 AND 600
    AND bg_high_mgdl          BETWEEN 20 AND 600),
  -- Refused, never rewritten: dev's verifyThresholds nudges a misordered value
  -- to a neighbour and logs it (BF-67). Here the write fails visibly.
  CONSTRAINT tenant_alarm_thresholds_ordered CHECK (
        bg_low_mgdl < bg_target_bottom_mgdl
    AND bg_target_bottom_mgdl < bg_target_top_mgdl
    AND bg_target_top_mgdl < bg_high_mgdl)
);

ALTER TABLE tenant_alarm_thresholds ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_alarm_thresholds FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_alarm_thresholds_tenant_isolation ON tenant_alarm_thresholds
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

CREATE TABLE tenant_config_version (
  tenant_id     uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
  version       integer NOT NULL CHECK (version >= 1),
  created_at    timestamptz NOT NULL DEFAULT now(),
  -- who: the plane and the identity provider's subject (D17 as amended: text,
  -- no foreign key). 'system' for bootstrap and imports.
  actor_plane   text NOT NULL CHECK (actor_plane IN ('owner', 'operator', 'system')),
  actor_subject text NOT NULL CHECK (length(actor_subject) BETWEEN 1 AND 255),
  -- the identity provider that issued actor_subject (as tenant_members, 0002);
  -- required for an owner, absent for system writes
  actor_provider text CHECK (actor_provider ~ '^[a-z][a-z0-9-]{0,31}$'),
  kind          text NOT NULL CHECK (kind IN ('change', 'rollback', 'bootstrap', 'import')),
  rollback_of   integer,
  reason        text CHECK (length(reason) <= 500),
  -- what: the owner-scope state after this version (cfg_current_state)
  state         jsonb NOT NULL,
  PRIMARY KEY (tenant_id, version),
  CONSTRAINT tenant_config_version_owner_has_provider CHECK (actor_plane <> 'owner' OR actor_provider IS NOT NULL),
  CONSTRAINT tenant_config_version_rollback_target CHECK ((kind = 'rollback') = (rollback_of IS NOT NULL)),
  CONSTRAINT tenant_config_version_rollback_earlier CHECK (rollback_of IS NULL OR rollback_of < version),
  FOREIGN KEY (tenant_id, rollback_of) REFERENCES tenant_config_version (tenant_id, version)
);

ALTER TABLE tenant_config_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_config_version FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_config_version_tenant_isolation ON tenant_config_version
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- Append-only. UPDATE never; DELETE only as the cascade of deleting the tenant.
CREATE FUNCTION cfg_version_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' AND NOT EXISTS (SELECT 1 FROM tenants WHERE id = OLD.tenant_id) THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'versions are append-only' USING ERRCODE = '42501';
END $$;
CREATE TRIGGER tenant_config_version_immutable BEFORE UPDATE OR DELETE ON tenant_config_version
  FOR EACH ROW EXECUTE FUNCTION cfg_version_immutable();

CREATE FUNCTION cfg_empty_state() RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
  SELECT '{"values": {}, "thresholds": null, "integrations": []}'::jsonb
$$;

CREATE FUNCTION cfg_current_state(p_tenant uuid) RETURNS jsonb LANGUAGE sql STABLE AS $$
  SELECT jsonb_build_object(
    'values', COALESCE((SELECT jsonb_object_agg(v.setting_key, v.value)
                          FROM tenant_setting_value v WHERE v.tenant_id = p_tenant), '{}'::jsonb),
    'thresholds', (SELECT jsonb_build_object(
                     'bgLow', t.bg_low_mgdl, 'bgTargetBottom', t.bg_target_bottom_mgdl,
                     'bgTargetTop', t.bg_target_top_mgdl, 'bgHigh', t.bg_high_mgdl,
                     'enteredUnits', t.entered_units)
                     FROM tenant_alarm_thresholds t WHERE t.tenant_id = p_tenant),
    'integrations', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                     'id', i.id, 'kind', i.kind, 'label', i.label, 'settings', i.settings,
                     'secretRef', i.owner_secret_ref, 'enabled', i.enabled) ORDER BY i.id)
                     FROM tenant_integration i WHERE i.tenant_id = p_tenant), '[]'::jsonb))
$$;

-- At commit: the tenant's state must equal its newest version's state.
CREATE FUNCTION cfg_assert_versioned() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE t uuid; head jsonb;
BEGIN
  IF TG_OP = 'DELETE' THEN t := OLD.tenant_id; ELSE t := NEW.tenant_id; END IF;
  IF NOT EXISTS (SELECT 1 FROM tenants WHERE id = t) THEN RETURN NULL; END IF;   -- tenant deleted
  SELECT v.state INTO head FROM tenant_config_version v
   WHERE v.tenant_id = t ORDER BY v.version DESC LIMIT 1;
  IF head IS NULL THEN head := cfg_empty_state(); END IF;
  IF head IS DISTINCT FROM cfg_current_state(t) THEN
    RAISE EXCEPTION 'version: configuration of tenant % changed without a version (use cfg_apply)', t
      USING ERRCODE = '23514';
  END IF;
  RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER tenant_setting_value_versioned
  AFTER INSERT OR UPDATE OR DELETE ON tenant_setting_value
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cfg_assert_versioned();
CREATE CONSTRAINT TRIGGER tenant_alarm_thresholds_versioned
  AFTER INSERT OR UPDATE OR DELETE ON tenant_alarm_thresholds
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cfg_assert_versioned();
CREATE CONSTRAINT TRIGGER tenant_integration_versioned
  AFTER INSERT OR UPDATE OR DELETE ON tenant_integration
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cfg_assert_versioned();
CREATE CONSTRAINT TRIGGER tenant_config_version_matches_state
  AFTER INSERT ON tenant_config_version
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cfg_assert_versioned();

-- Threshold input: all four keys, whole mg/dL numbers, nothing else. Partial
-- input is refused here (J11's recommendation) before the NOT NULL backstop.
CREATE FUNCTION cfg_threshold_input_check(th jsonb) RETURNS void LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE k text; n numeric;
BEGIN
  IF jsonb_typeof(th) <> 'object' THEN
    RAISE EXCEPTION 'thresholds: must be an object' USING ERRCODE = '23514';
  END IF;
  FOR k IN SELECT jsonb_object_keys(th) LOOP
    IF k NOT IN ('bgLow', 'bgTargetBottom', 'bgTargetTop', 'bgHigh', 'enteredUnits') THEN
      RAISE EXCEPTION 'thresholds: unknown key %', k USING ERRCODE = '23514';
    END IF;
  END LOOP;
  FOREACH k IN ARRAY ARRAY['bgLow', 'bgTargetBottom', 'bgTargetTop', 'bgHigh'] LOOP
    IF NOT th ? k THEN
      RAISE EXCEPTION 'thresholds: all four are written together; % is missing', k USING ERRCODE = '23514';
    END IF;
    IF jsonb_typeof(th -> k) <> 'number' THEN
      RAISE EXCEPTION 'thresholds: % must be a number', k USING ERRCODE = '23514';
    END IF;
    n := (th ->> k)::numeric;
    IF n <> trunc(n) THEN
      RAISE EXCEPTION 'thresholds: % = % is not a whole mg/dL value; convert mmol/L at the write boundary', k, n
        USING ERRCODE = '23514';
    END IF;
  END LOOP;
END $$;

-- The one write path for owner-scope configuration. Runs as the caller
-- (SECURITY INVOKER), so RLS and table grants apply to everything it does.
-- p_changes: {"values": {KEY: value | null}, "thresholds": {...} | null,
--             "integrations": {"upsert": [...], "delete": [ids]}}
-- p_confirmations: {KEY: {"exportOfferedAt": timestamptz}} for keys that need one.
CREATE FUNCTION cfg_apply(p_tenant uuid, p_changes jsonb, p_actor_plane text, p_actor_subject text,
                          p_reason text DEFAULT NULL, p_kind text DEFAULT 'change',
                          p_rollback_of integer DEFAULT NULL, p_confirmations jsonb DEFAULT '{}'::jsonb,
                          p_actor_provider text DEFAULT NULL)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE k text; v jsonb; th jsonb; it jsonb; next_version integer;
BEGIN
  IF p_tenant IS DISTINCT FROM NULLIF(current_setting('app.current_tenant_id', true), '')::uuid THEN
    RAISE EXCEPTION 'cfg_apply: % is not the bound tenant', p_tenant USING ERRCODE = '42501';
  END IF;
  -- One writer per tenant at a time, so version numbers are allocated in order.
  PERFORM pg_advisory_xact_lock(hashtextextended('nightscout.config:' || p_tenant::text, 0));

  FOR k, v IN SELECT * FROM jsonb_each(COALESCE(p_changes -> 'values', '{}'::jsonb)) LOOP
    IF v = 'null'::jsonb THEN
      DELETE FROM tenant_setting_value WHERE tenant_id = p_tenant AND setting_key = k;
    ELSE
      INSERT INTO tenant_setting_value (tenant_id, setting_key, value, confirmed_at, export_offered_at)
      VALUES (p_tenant, k, v,
              CASE WHEN p_confirmations ? k THEN now() END,
              (p_confirmations -> k ->> 'exportOfferedAt')::timestamptz)
      ON CONFLICT (tenant_id, setting_key) DO UPDATE
        SET value = EXCLUDED.value, confirmed_at = EXCLUDED.confirmed_at,
            export_offered_at = EXCLUDED.export_offered_at;
    END IF;
  END LOOP;

  IF p_changes ? 'thresholds' THEN
    th := p_changes -> 'thresholds';
    IF th = 'null'::jsonb THEN
      DELETE FROM tenant_alarm_thresholds WHERE tenant_id = p_tenant;
    ELSE
      PERFORM cfg_threshold_input_check(th);
      INSERT INTO tenant_alarm_thresholds (tenant_id, bg_low_mgdl, bg_target_bottom_mgdl,
                                           bg_target_top_mgdl, bg_high_mgdl, entered_units)
      VALUES (p_tenant, (th ->> 'bgLow')::integer, (th ->> 'bgTargetBottom')::integer,
              (th ->> 'bgTargetTop')::integer, (th ->> 'bgHigh')::integer,
              COALESCE(th ->> 'enteredUnits', 'mg/dl'))
      ON CONFLICT (tenant_id) DO UPDATE
        SET bg_low_mgdl = EXCLUDED.bg_low_mgdl, bg_target_bottom_mgdl = EXCLUDED.bg_target_bottom_mgdl,
            bg_target_top_mgdl = EXCLUDED.bg_target_top_mgdl, bg_high_mgdl = EXCLUDED.bg_high_mgdl,
            entered_units = EXCLUDED.entered_units, updated_at = now();
    END IF;
  END IF;

  FOR it IN SELECT * FROM jsonb_array_elements(COALESCE(p_changes -> 'integrations' -> 'upsert', '[]'::jsonb)) LOOP
    INSERT INTO tenant_integration (tenant_id, id, kind, label, settings, owner_secret_ref, enabled)
    VALUES (p_tenant, (it ->> 'id')::uuid, it ->> 'kind', COALESCE(it ->> 'label', ''),
            COALESCE(it -> 'settings', '{}'::jsonb), it ->> 'secretRef',
            COALESCE((it ->> 'enabled')::boolean, true))
    ON CONFLICT (tenant_id, id) DO UPDATE
      SET kind = EXCLUDED.kind, label = EXCLUDED.label, settings = EXCLUDED.settings,
          owner_secret_ref = EXCLUDED.owner_secret_ref, enabled = EXCLUDED.enabled;
  END LOOP;
  FOR k IN SELECT jsonb_array_elements_text(COALESCE(p_changes -> 'integrations' -> 'delete', '[]'::jsonb)) LOOP
    DELETE FROM tenant_integration WHERE tenant_id = p_tenant AND id = k::uuid;
  END LOOP;

  SELECT COALESCE(max(version), 0) + 1 INTO next_version
    FROM tenant_config_version WHERE tenant_id = p_tenant;
  INSERT INTO tenant_config_version (tenant_id, version, actor_plane, actor_subject, actor_provider, kind, rollback_of, reason, state)
  VALUES (p_tenant, next_version, p_actor_plane, p_actor_subject, p_actor_provider, p_kind, p_rollback_of, p_reason,
          cfg_current_state(p_tenant));
  RETURN next_version;
END $$;

-- Roll back to version p_target: write, as a NEW version, the changes that make
-- the current state equal p_target's state. Every row passes the same checks a
-- fresh write does, against the CURRENT policy and floors.
-- DECIDED (maintainer, 2026-10-27, schema spec Q3): when the operator has since
-- pinned or narrowed a setting that version used, the rollback is refused WHOLE,
-- naming each blocked setting and the operator rule behind it. Nothing changes
-- and no version is written. Permanent-deletion settings need a fresh
-- confirmation; an old one is not carried forward.
CREATE FUNCTION cfg_rollback(p_tenant uuid, p_target integer, p_actor_plane text, p_actor_subject text,
                             p_reason text DEFAULT NULL, p_confirmations jsonb DEFAULT '{}'::jsonb,
                             p_actor_provider text DEFAULT NULL)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE target jsonb; cur jsonb; vals jsonb; changes jsonb; ups jsonb; dels jsonb; blocked text[];
BEGIN
  SELECT state INTO target FROM tenant_config_version WHERE tenant_id = p_tenant AND version = p_target;
  IF target IS NULL THEN
    RAISE EXCEPTION 'rollback: tenant has no version %', p_target USING ERRCODE = '22023';
  END IF;
  cur := cfg_current_state(p_tenant);
  SELECT COALESCE(jsonb_object_agg(k, COALESCE(target -> 'values' -> k, 'null'::jsonb)), '{}'::jsonb) INTO vals
    FROM (SELECT jsonb_object_keys(target -> 'values') AS k
          UNION SELECT jsonb_object_keys(cur -> 'values')) keys
   WHERE (target -> 'values' -> k) IS DISTINCT FROM (cur -> 'values' -> k);
  -- every blocked setting, not just the first
  SELECT array_agg(e ORDER BY e) INTO blocked FROM (
    SELECT cfg_owner_value_error(p_tenant, key, value, p_confirmations ? key) AS e
      FROM jsonb_each(vals) WHERE value <> 'null'::jsonb) x
   WHERE e IS NOT NULL;
  IF blocked IS NOT NULL THEN
    RAISE EXCEPTION 'rollback to version % refused; % setting(s) blocked: %', p_target, cardinality(blocked),
      array_to_string(blocked, '; ') USING ERRCODE = '23514';
  END IF;
  changes := jsonb_build_object('values', vals);
  IF (target -> 'thresholds') IS DISTINCT FROM (cur -> 'thresholds') THEN
    changes := changes || jsonb_build_object('thresholds', target -> 'thresholds');
  END IF;
  SELECT COALESCE(jsonb_agg(t), '[]'::jsonb) INTO ups
    FROM jsonb_array_elements(target -> 'integrations') t
   WHERE NOT EXISTS (SELECT 1 FROM jsonb_array_elements(cur -> 'integrations') c WHERE c = t);
  SELECT COALESCE(jsonb_agg(c ->> 'id'), '[]'::jsonb) INTO dels
    FROM jsonb_array_elements(cur -> 'integrations') c
   WHERE NOT EXISTS (SELECT 1 FROM jsonb_array_elements(target -> 'integrations') t WHERE t ->> 'id' = c ->> 'id');
  changes := changes || jsonb_build_object('integrations', jsonb_build_object('upsert', ups, 'delete', dels));
  RETURN cfg_apply(p_tenant, changes, p_actor_plane, p_actor_subject, p_reason, 'rollback', p_target, p_confirmations, p_actor_provider);
END $$;
