-- Schema PostgREST exposes as the REST API (its "db-schemas" setting).
CREATE SCHEMA IF NOT EXISTS api;

CREATE TABLE api.entries (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL,
  sgv integer NOT NULL,
  date timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON api.entries (tenant_id, date DESC);

-- web_anon: PostgREST's default "no JWT presented" role. No table grants at all —
-- an unauthenticated request gets a permission-denied, not zero-rows-by-accident.
DROP ROLE IF EXISTS web_anon;
CREATE ROLE web_anon NOLOGIN;

-- app_tenant: the role a *verified* JWT switches PostgREST into (via the JWT's own
-- "role" claim, PostgREST's built-in mechanism, no custom pre-request function
-- needed). RLS-restricted exactly like the knex rls-poc's app_user.
DROP ROLE IF EXISTS app_tenant;
CREATE ROLE app_tenant NOLOGIN NOBYPASSRLS;
GRANT web_anon, app_tenant TO CURRENT_USER; -- authenticator must be able to switch into both
GRANT USAGE ON SCHEMA api TO web_anon, app_tenant;
GRANT SELECT, INSERT ON api.entries TO app_tenant;
GRANT USAGE, SELECT ON SEQUENCE api.entries_id_seq TO app_tenant;

ALTER TABLE api.entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE api.entries FORCE ROW LEVEL SECURITY;

-- PostgREST puts the verified JWT's claims into the `request.jwt.claims` GUC as a
-- JSON string automatically — no pre-request function required for this simple case.
-- Same NULLIF/current_setting fail-closed shape as the knex rls-poc (§6.1).
CREATE POLICY tenant_isolation ON api.entries
  USING (
    tenant_id = NULLIF(
      (current_setting('request.jwt.claims', true)::json ->> 'tenant_id'), ''
    )::uuid
  );

-- authenticator: the single login role PostgREST connects as (its "db-uri" user).
-- Mirrors PostgREST's documented tutorial pattern, not a departure from it.
DROP ROLE IF EXISTS authenticator;
CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'poc';
GRANT web_anon TO authenticator;
GRANT app_tenant TO authenticator;
