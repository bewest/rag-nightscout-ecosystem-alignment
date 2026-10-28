-- 0006 down. Destroys every tenant's owner values, thresholds and version history.
DROP TRIGGER tenant_integration_versioned ON tenant_integration;
DROP FUNCTION cfg_rollback(uuid, integer, text, text, text, jsonb);
DROP FUNCTION cfg_apply(uuid, jsonb, text, text, text, text, integer, jsonb);
DROP FUNCTION cfg_threshold_input_check(jsonb);
DROP TABLE tenant_config_version;
DROP TABLE tenant_alarm_thresholds;
DROP TABLE tenant_setting_value;
DROP FUNCTION cfg_assert_versioned();
DROP FUNCTION cfg_current_state(uuid);
DROP FUNCTION cfg_empty_state();
DROP FUNCTION cfg_version_immutable();
DROP FUNCTION cfg_owner_value_check();
