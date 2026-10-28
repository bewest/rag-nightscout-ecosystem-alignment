-- 0007 down: remove every grant 0007 made.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ns_operator, ns_tenant_admin, ns_api;
REVOKE USAGE ON SCHEMA public FROM ns_operator, ns_tenant_admin, ns_api;
