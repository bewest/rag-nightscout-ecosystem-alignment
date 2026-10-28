-- 0004: catalogue rows for the settings the lab exercises.
--
-- Covers every policy row census 3a leaves (rows 1, 6, 9, 10), the integration
-- rows (4, 11), and two open owner settings. Class D names (TRUST_PROXY,
-- API_V3_DATA_WARNINGS, the API_V1_COUNT_* switches, ...) are absent: they live in each
-- role's environment (maintainer, 2026-10-27). Names
-- the census marks "not offered" under multi are DELIBERATELY ABSENT (rows 2,
-- 3, 5, 7, 8, 12 and TREATMENTS_AUTH, BASE_URL): absence is the floor.
-- A full release would generate this file from the census (J7).
-- Role names and defaults are dev's (lib/authorization/storage.js:239-245,
-- lib/settings.js, lib/server/env.js:121-132).

INSERT INTO config_setting
  (key, value_type, enum_values, owner_settable, is_alarm, needs_confirmation,
   floor, default_mode, default_constraint, census_row, note)
VALUES
  -- row 1: no anonymous writes
  ('AUTH_DEFAULT_ROLES', 'role_list',
   ARRAY['denied', 'readable', 'status-only', 'careportal', 'devicestatus-upload', 'activity', 'admin'],
   true, false, false,
   '{"allowed": ["denied", "readable", "status-only"]}', 'bounded',
   '{"allowed": ["denied", "readable", "status-only"]}', 1,
   'floor: default roles only from denied, readable, status-only'),
  -- row 6: data safety
  ('WRITE_VALIDATION', 'ordinal', ARRAY['off', 'log', 'reject'],
   true, false, false, '{"min": "log"}', 'bounded', '{"min": "log"}', 6,
   'floor: at least log; owner may tighten'),
  -- row 9: permanent deletion. Off unless the operator writes a policy.
  ('API3_AUTOPRUNE_DEVICESTATUS', 'integer', NULL, true, false, true, '{"min": 1}', 'pinned', '{}', 9, 'days'),
  ('API3_AUTOPRUNE_ENTRIES', 'integer', NULL, true, false, true, '{"min": 1}', 'pinned', '{}', 9, 'days'),
  ('API3_AUTOPRUNE_FOOD', 'integer', NULL, true, false, true, '{"min": 1}', 'pinned', '{}', 9, 'days'),
  ('API3_AUTOPRUNE_PROFILE', 'integer', NULL, true, false, true, '{"min": 1}', 'pinned', '{}', 9, 'days'),
  ('API3_AUTOPRUNE_SETTINGS', 'integer', NULL, true, false, true, '{"min": 1}', 'pinned', '{}', 9, 'days'),
  ('API3_AUTOPRUNE_TREATMENTS', 'integer', NULL, true, false, true, '{"min": 1}', 'pinned', '{}', 9, 'days'),
  -- row 10: alarm thresholds (operator defaults, mg/dL) and enables. Hidden
  -- from the owner; the owner's own thresholds live in tenant_alarm_thresholds.
  ('BG_HIGH', 'integer', NULL, false, true, false, '{"min": 20, "max": 600}', 'pinned', '{}', 10, 'mg/dL'),
  ('BG_TARGET_TOP', 'integer', NULL, false, true, false, '{"min": 20, "max": 600}', 'pinned', '{}', 10, 'mg/dL'),
  ('BG_TARGET_BOTTOM', 'integer', NULL, false, true, false, '{"min": 20, "max": 600}', 'pinned', '{}', 10, 'mg/dL'),
  ('BG_LOW', 'integer', NULL, false, true, false, '{"min": 20, "max": 600}', 'pinned', '{}', 10, 'mg/dL'),
  ('ALARM_URGENT_HIGH', 'boolean', NULL, false, true, false, '{}', 'pinned', '{}', 10, ''),
  ('ALARM_HIGH', 'boolean', NULL, false, true, false, '{}', 'pinned', '{}', 10, ''),
  ('ALARM_LOW', 'boolean', NULL, false, true, false, '{}', 'pinned', '{}', 10, ''),
  ('ALARM_URGENT_LOW', 'boolean', NULL, false, true, false, '{}', 'pinned', '{}', 10, ''),
  -- rows 4 and 11: which integration kinds are enabled, and how many per tenant
  -- (0 = disabled). Operator-only.
  ('INTEGRATION_MAX:push-relay', 'integer', NULL, false, false, false, '{"min": 0}', 'pinned', '{}', 11, 'per tenant'),
  ('INTEGRATION_MAX:app-push', 'integer', NULL, false, false, false, '{"min": 0}', 'pinned', '{}', 11, 'per tenant'),
  ('INTEGRATION_MAX:webhook', 'integer', NULL, false, false, false, '{"min": 0}', 'pinned', '{}', 4, 'per tenant'),
  ('INTEGRATION_MAX:cgm-connector', 'integer', NULL, false, false, false, '{"min": 0}', 'pinned', '{}', 4, 'per tenant'),
  -- row 4: the operator's optional webhook host allow-list
  ('INTEGRATION_HOSTS:webhook', 'host_list', NULL, false, false, false, '{}', 'pinned', '{}', 4, 'optional'),
  -- ordinary owner settings (class T)
  ('SHOW_SECONDS', 'boolean', NULL, true, false, false, '{}', 'open', '{}', NULL, 'display only'),
  ('DISPLAY_UNITS', 'enum', ARRAY['mg/dl', 'mmol'], true, false, false, '{}', 'open', '{}', NULL, 'display only; thresholds stay mg/dL');

-- Driver catalogue. Kind names are generic; hosts are synthetic (.test, RFC 2606).
INSERT INTO integration_kind (kind, settings_schema, driver_hosts, owner_secret_parts, operator_secret_parts, census_names)
VALUES
  ('push-relay',
   '{"fields": {"priority": {"type": "enum", "enum": ["normal", "high", "emergency"], "required": true},
                "sound":    {"type": "string", "max": 40}}}',
   '{}', ARRAY['userKey', 'alarmKey'], ARRAY['applicationToken'], 'PUSHOVER_*'),
  ('app-push',
   '{"fields": {"bundleId":    {"type": "string", "required": true, "max": 155},
                "environment": {"type": "enum", "enum": ["production", "development"], "required": true}}}',
   '{}', ARRAY['apnsKey', 'apnsKeyId', 'teamId'], '{}', 'LOOP_APNS_*, LOOP_DEVELOPER_TEAM_ID'),
  ('webhook',
   '{"fields": {"url":    {"type": "url", "hosts": "public", "required": true},
                "events": {"type": "enum", "enum": ["alarm", "treatment", "all"], "required": true}}}',
   '{}', ARRAY['signingSecret'], '{}', 'WEBHOOK_*'),
  ('cgm-connector',
   '{"fields": {"region":   {"type": "enum", "enum": ["us", "ous"], "required": true},
                "endpoint": {"type": "url", "hosts": "driver"}}}',
   ARRAY['share1.cgm-driver.test', 'share2.cgm-driver.test'], ARRAY['login'], '{}', 'CONNECT_*, BRIDGE_*');
