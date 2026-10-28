-- 0007: what each role may touch. The roles are created outside migrations
-- (bootstrap/roles.sql, run once by a database administrator), like the seam's
-- platform.sql operational note: a migration that could create or widen roles
-- would let the schema grant itself access.
--
--   ns_operator     -- the operator plane (D7): tenants, deployment policy,
--                      per-tenant overrides, the operator's integration parts.
--   ns_tenant_admin -- the tenant-owner listener (D16): owner values, versions,
--                      integrations; reads its policy; never writes policy.
--   ns_api          -- consumer, evaluator, connector roles (D5/D21): read the
--                      configuration they merge; write integration status only.
-- None of the three owns a table. Ownership stays with the migration role.

GRANT USAGE ON SCHEMA public TO ns_operator, ns_tenant_admin, ns_api;

GRANT SELECT ON tenants TO ns_operator, ns_tenant_admin, ns_api;
GRANT INSERT, UPDATE, DELETE ON tenants TO ns_operator;
GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_members TO ns_tenant_admin;
GRANT SELECT ON tenant_members TO ns_api;

-- Catalogues: read-only to everyone. Floors cannot be edited at run time.
GRANT SELECT ON config_setting, integration_kind TO ns_operator, ns_tenant_admin, ns_api;

-- Deployment policy: the operator writes; everyone reads.
GRANT SELECT, INSERT, UPDATE, DELETE ON deployment_policy TO ns_operator;
GRANT SELECT ON deployment_policy TO ns_tenant_admin, ns_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON deployment_integration TO ns_operator;
GRANT SELECT ON deployment_integration TO ns_api;
-- The owner may see whether the operator's part exists, not its reference.
GRANT SELECT (kind, operator_configured) ON deployment_integration TO ns_tenant_admin;

-- Per-tenant overrides: the operator writes under a tenant binding.
GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_policy_override TO ns_operator;
GRANT SELECT ON tenant_policy_override TO ns_tenant_admin, ns_api;

-- Owner-scope configuration: written by the tenant-owner listener only.
GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_setting_value TO ns_tenant_admin;
GRANT SELECT ON tenant_setting_value TO ns_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_integration TO ns_tenant_admin;
GRANT SELECT ON tenant_integration TO ns_api;
GRANT SELECT ON tenant_integration_status TO ns_tenant_admin;
GRANT SELECT, INSERT, UPDATE ON tenant_integration_status TO ns_api;
-- Versions: insert and read; never update or delete (also refused by trigger).
GRANT SELECT, INSERT ON tenant_config_version TO ns_tenant_admin;
GRANT SELECT ON tenant_config_version TO ns_api;

-- FLOOR (alarm settings hidden until the 7a gate): the owner's listener may
-- read the threshold table and may NOT write it. The post-gate migration is a
-- one-line GRANT, so turning alarms on for owners is a reviewed, versioned
-- schema change rather than a runtime switch.
GRANT SELECT ON tenant_alarm_thresholds TO ns_tenant_admin, ns_api;
