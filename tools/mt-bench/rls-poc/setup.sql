-- Mirrors Nocturne's pattern (verified in externals/nocturne):
--   NocturneDbContext.cs:14-64            (EF Core global query filter, app-layer)
--   Migrations/20260227034745_EnforceMultitenancy.cs:66-76  (FORCE ROW LEVEL SECURITY)
--   Interceptors/TenantConnectionInterceptor.cs             (sets app.current_tenant_id per connection)
-- Reimplemented here with knex/pg instead of EF Core, same primitive.

CREATE TABLE IF NOT EXISTS entries (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL,
  sgv integer NOT NULL,
  device text,
  date timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS entries_tenant_idx ON entries (tenant_id, date DESC);

-- A role the application actually connects as: NOT the table owner, no BYPASSRLS,
-- no SUPERUSER. This is the part that is easy to skip and that makes RLS toothless
-- if skipped — table owners bypass RLS by default in Postgres.
DROP ROLE IF EXISTS app_user;
CREATE ROLE app_user LOGIN PASSWORD 'poc' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT SELECT, INSERT, UPDATE, DELETE ON entries TO app_user;
GRANT USAGE, SELECT ON SEQUENCE entries_id_seq TO app_user;

ALTER TABLE entries ENABLE ROW LEVEL SECURITY;
-- FORCE is the load-bearing word: without it, the table owner (and anyone granted
-- BYPASSRLS) still sees every row even with RLS "enabled". Nocturne's migration
-- forces it explicitly for this reason.
ALTER TABLE entries FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON entries
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
-- Two guards, both load-bearing, matching Nocturne's migration exactly
-- (Migrations/20260227034745_EnforceMultitenancy.cs:66-76):
--   * second arg `true` to current_setting = "missing GUC returns NULL, not an error";
--   * NULLIF(..., '') extends that to an *empty-string* GUC, which set_config can
--     produce and which would otherwise raise on ::uuid.
-- NULL = anything is NULL in SQL (never true), so an unbound or empty tenant context
-- returns zero rows rather than throwing. That NULL-comparison behaviour, not the
-- POLICY syntax, is the actual fail-closed mechanism. Dropping the second argument
-- would instead throw on an unbound connection — also fail-closed, but noisier, and
-- a different failure mode than the one this PoC is written to demonstrate.
