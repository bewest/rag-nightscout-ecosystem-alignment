-- 0008 down: remove every grant 0008 made.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ns_operator, ns_tenant_admin, ns_api;
REVOKE USAGE ON SCHEMA public FROM ns_operator, ns_tenant_admin, ns_api;
