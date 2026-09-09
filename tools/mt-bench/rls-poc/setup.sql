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
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
-- second arg `true` to current_setting = "missing GUC returns NULL, not an error" —
-- NULL = anything is NULL in SQL (never true), so an unset tenant context returns
-- zero rows rather than throwing. This is the actual fail-closed mechanism.
