-- 0005 down. Destroys every tenant's integration records (references only).
DROP TABLE tenant_integration_status;
DROP TABLE tenant_integration;
DROP TABLE deployment_integration;
DROP FUNCTION cfg_integration_check();
DROP FUNCTION cfg_integration_settings_error(jsonb, text[], jsonb, jsonb);
DROP FUNCTION cfg_public_host_ok(text);
DROP FUNCTION cfg_https_host(text);
