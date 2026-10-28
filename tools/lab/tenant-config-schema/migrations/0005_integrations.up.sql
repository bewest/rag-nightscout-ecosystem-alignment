-- 0005: integrations as typed records (D22, second round).
--
-- deployment_integration    -- the operator's part of a kind's credential, by
--                              reference (e.g. a push service's application
--                              token, shared by every tenant). Not tenant-scoped.
-- tenant_integration        -- one record per connector, webhook or push target:
--                              a kind, settings validated by the kind's schema,
--                              a REFERENCE to the owner's credential in the
--                              secrets component, and an enabled flag.
-- tenant_integration_status -- last success / last error. Split out so that a
--                              connector's polling writes do not make a
--                              configuration version.

CREATE TABLE deployment_integration (
  kind                text PRIMARY KEY REFERENCES integration_kind (kind),
  operator_secret_ref text CONSTRAINT deployment_integration_ref_format
                      CHECK (operator_secret_ref IS NULL OR cfg_is_secret_ref(operator_secret_ref)),
  -- What the tenant-owner listener may see: whether the operator's part exists,
  -- never its reference (0007 grants this column, not the reference).
  operator_configured boolean GENERATED ALWAYS AS (operator_secret_ref IS NOT NULL) STORED,
  updated_at          timestamptz NOT NULL DEFAULT now(),
  updated_by          text NOT NULL
);

CREATE TABLE tenant_integration (
  tenant_id        uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
  id               uuid NOT NULL,
  kind             text NOT NULL REFERENCES integration_kind (kind),
  label            text NOT NULL DEFAULT '' CHECK (length(label) <= 80),
  settings         jsonb NOT NULL DEFAULT '{}'::jsonb,
  owner_secret_ref text CONSTRAINT tenant_integration_ref_format
                   CHECK (owner_secret_ref IS NULL OR cfg_is_secret_ref(owner_secret_ref)),
  enabled          boolean NOT NULL DEFAULT true,
  updated_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id)
);

ALTER TABLE tenant_integration ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_integration FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_integration_tenant_isolation ON tenant_integration
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

CREATE TABLE tenant_integration_status (
  tenant_id       uuid NOT NULL,
  integration_id  uuid NOT NULL,
  last_success_at timestamptz,
  last_error_at   timestamptz,
  last_error      text CHECK (length(last_error) <= 1000),
  PRIMARY KEY (tenant_id, integration_id),
  FOREIGN KEY (tenant_id, integration_id) REFERENCES tenant_integration (tenant_id, id) ON DELETE CASCADE
);

ALTER TABLE tenant_integration_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_integration_status FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_integration_status_tenant_isolation ON tenant_integration_status
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- A url's host, if the url is https with no user-info; else NULL.
-- `https://user:pw@host/` does not match, so credentials in a url are refused.
CREATE FUNCTION cfg_https_host(u text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT (regexp_match(lower(u), '^https://([a-z0-9.-]+)(:[0-9]{1,5})?(/[^[:space:]]*)?$'))[1]
$$;

-- First-line network-safety floor for a url that must reach a public address.
-- A literal private, loopback, link-local or shared address, or a local-only
-- name, is refused. Names that RESOLVE to such addresses can only be caught at
-- send time (DNS); that check is the application's (schema spec, floors).
CREATE FUNCTION cfg_public_host_ok(h text) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE a inet;
BEGIN
  IF h IS NULL OR h = '' THEN RETURN false; END IF;
  IF h = 'localhost' OR h ~ '\.(localhost|local|internal|home\.arpa|lan)$' OR h !~ '\.' THEN RETURN false; END IF;
  IF h ~ '^[0-9.]+$' THEN
    BEGIN a := h::inet; EXCEPTION WHEN others THEN RETURN false; END;
    IF a << '0.0.0.0/8' OR a << '10.0.0.0/8' OR a << '100.64.0.0/10' OR a << '127.0.0.0/8'
       OR a << '169.254.0.0/16' OR a << '172.16.0.0/12' OR a << '192.168.0.0/16'
       OR a << '224.0.0.0/4' OR a << '240.0.0.0/4' THEN
      RETURN false;
    END IF;
  END IF;
  RETURN true;
END $$;

-- NULL when settings satisfy the kind's schema; otherwise the reason.
CREATE FUNCTION cfg_integration_settings_error(p_schema jsonb, p_driver_hosts text[], p_host_allow jsonb, s jsonb)
RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE f text; spec jsonb; v jsonb; h text; n numeric;
BEGIN
  IF jsonb_typeof(s) <> 'object' THEN RETURN 'settings must be an object'; END IF;
  FOR f IN SELECT jsonb_object_keys(s) LOOP
    IF NOT (p_schema -> 'fields') ? f THEN RETURN 'unknown field ' || f; END IF;
  END LOOP;
  FOR f, spec IN SELECT * FROM jsonb_each(p_schema -> 'fields') LOOP
    IF NOT s ? f THEN
      IF (spec ->> 'required') = 'true' THEN RETURN 'missing field ' || f; END IF;
      CONTINUE;
    END IF;
    v := s -> f;
    IF spec ->> 'type' = 'string' THEN
      IF jsonb_typeof(v) <> 'string' THEN RETURN f || ' must be a string'; END IF;
      IF spec ? 'max' AND length(v #>> '{}') > (spec ->> 'max')::int THEN RETURN f || ' is too long'; END IF;
    ELSIF spec ->> 'type' = 'boolean' THEN
      IF jsonb_typeof(v) <> 'boolean' THEN RETURN f || ' must be true or false'; END IF;
    ELSIF spec ->> 'type' = 'integer' THEN
      IF jsonb_typeof(v) <> 'number' THEN RETURN f || ' must be a whole number'; END IF;
      n := (v #>> '{}')::numeric;
      IF n <> trunc(n) THEN RETURN f || ' must be a whole number'; END IF;
    ELSIF spec ->> 'type' = 'enum' THEN
      IF jsonb_typeof(v) <> 'string' OR NOT (spec -> 'enum') ? (v #>> '{}') THEN
        RETURN f || ' must be one of ' || (spec -> 'enum')::text;
      END IF;
    ELSIF spec ->> 'type' = 'url' THEN
      IF jsonb_typeof(v) <> 'string' THEN RETURN f || ' must be a url'; END IF;
      h := cfg_https_host(v #>> '{}');
      IF h IS NULL THEN RETURN f || ' must be an https url with no user name or password'; END IF;
      IF spec ->> 'hosts' = 'driver' THEN
        IF NOT (h = ANY (p_driver_hosts)) THEN RETURN 'floor: ' || f || ' host ' || h || ' is not one the driver defines'; END IF;
      ELSIF spec ->> 'hosts' = 'public' THEN
        IF NOT cfg_public_host_ok(h) THEN RETURN 'floor: ' || f || ' host ' || h || ' is not a public address'; END IF;
        IF p_host_allow IS NOT NULL AND NOT p_host_allow ? h THEN
          RETURN 'policy: ' || f || ' host ' || h || ' is not on the operator''s allow-list';
        END IF;
      ELSE
        RETURN 'kind schema gives ' || f || ' no host rule';
      END IF;
    ELSE
      RETURN 'kind schema gives ' || f || ' an unknown type';
    END IF;
  END LOOP;
  RETURN NULL;
END $$;

CREATE FUNCTION cfg_integration_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE k integration_kind; pol record; maxv numeric; n integer; err text; allow jsonb; ready boolean;
BEGIN
  SELECT * INTO k FROM integration_kind WHERE kind = NEW.kind;
  IF TG_OP = 'UPDATE' AND NEW.kind <> OLD.kind THEN
    RAISE EXCEPTION 'integration: the kind of a record cannot change' USING ERRCODE = '23514';
  END IF;
  -- Enabled for this tenant, and within the count. Owner cannot set this key,
  -- so the effective value is pin, else default, else 0 (disabled).
  SELECT * INTO pol FROM cfg_policy_for(NEW.tenant_id, 'INTEGRATION_MAX:' || NEW.kind);
  maxv := COALESCE((pol.pin_value #>> '{}')::numeric, (pol.default_value #>> '{}')::numeric, 0);
  SELECT count(*) INTO n FROM tenant_integration
   WHERE tenant_id = NEW.tenant_id AND kind = NEW.kind AND id <> NEW.id;
  IF n + 1 > maxv THEN
    RAISE EXCEPTION 'policy: integration kind % allows % per tenant here', NEW.kind, maxv USING ERRCODE = '23514';
  END IF;
  SELECT * INTO pol FROM cfg_policy_for(NEW.tenant_id, 'INTEGRATION_HOSTS:' || NEW.kind);
  allow := COALESCE(pol.pin_value, pol.default_value);   -- NULL when the key is not in the catalogue
  err := cfg_integration_settings_error(k.settings_schema, k.driver_hosts, allow, NEW.settings);
  IF err IS NOT NULL THEN
    RAISE EXCEPTION 'integration: %', err USING ERRCODE = '23514';
  END IF;
  IF cardinality(k.owner_secret_parts) > 0 AND NEW.owner_secret_ref IS NULL THEN
    RAISE EXCEPTION 'integration: kind % needs a reference to the owner''s credential', NEW.kind USING ERRCODE = '23514';
  END IF;
  IF cardinality(k.owner_secret_parts) = 0 AND NEW.owner_secret_ref IS NOT NULL THEN
    RAISE EXCEPTION 'integration: kind % takes no owner credential', NEW.kind USING ERRCODE = '23514';
  END IF;
  IF cardinality(k.operator_secret_parts) > 0 THEN
    SELECT d.operator_configured INTO ready FROM deployment_integration d WHERE d.kind = NEW.kind;
    IF NOT COALESCE(ready, false) THEN
      RAISE EXCEPTION 'integration: the operator has not configured its part of kind %', NEW.kind USING ERRCODE = '23514';
    END IF;
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;

CREATE TRIGGER tenant_integration_check BEFORE INSERT OR UPDATE ON tenant_integration
  FOR EACH ROW EXECUTE FUNCTION cfg_integration_check();
