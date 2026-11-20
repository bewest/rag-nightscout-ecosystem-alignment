SELECT json_build_object('identity', json_build_array((pg_control_system()).system_identifier::text,
  (pg_control_checkpoint()).timeline_id, current_database()), 'tenants',
  (SELECT coalesce(json_object_agg(l.tenant_id, json_build_array(l.generation::text, w.last_stamp::text)), '{}'::json)
     FROM "@lifecycle@".tenant_lifecycle_windows l JOIN "@clock@".tenant_write_clock w USING (tenant_id)
    WHERE l.phase = 'active'))::text;
