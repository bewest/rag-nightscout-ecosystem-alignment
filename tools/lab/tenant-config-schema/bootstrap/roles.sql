-- Run once per cluster by a database administrator (the harness does it as
-- the container's superuser). Passwords are set by the harness per run from
-- random values held in memory, never in this file.
--
-- cfg_owner owns the schema and runs migrations. It is NOT a superuser and
-- cannot bypass RLS, so FORCE ROW LEVEL SECURITY applies to it too.
-- The three application roles own nothing.
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['cfg_owner', 'ns_operator', 'ns_tenant_admin', 'ns_api'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE', r);
    END IF;
  END LOOP;
END $$;
