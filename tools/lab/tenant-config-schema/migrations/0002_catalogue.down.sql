-- 0002 down.
DROP TABLE integration_kind;
DROP TABLE config_setting;
DROP FUNCTION cfg_schema_fields_not_secret(jsonb);
DROP FUNCTION cfg_is_secret_ref(text);
DROP FUNCTION cfg_within(text, text[], jsonb, jsonb);
DROP FUNCTION cfg_constraint_ok(text, text[], jsonb);
DROP FUNCTION cfg_satisfies(text, text[], jsonb, jsonb);
DROP FUNCTION cfg_value_ok(text, text[], jsonb);
