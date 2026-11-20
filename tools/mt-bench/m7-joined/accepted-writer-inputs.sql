-- All three synthetic writer keys, the clock and the durable output share one MVCC snapshot.
WITH source AS MATERIALIZED (SELECT @identity@ AS identity),
inputs AS (
  SELECT tenant_id, 'entries' AS domain, doc->>'device' AS marker, doc->>'date' AS key, doc->'srvModified' AS stamp
    FROM "@entries@".entries WHERE doc->>'device' IN ('@run@', '@run@-probe')
  UNION ALL
  SELECT tenant_id, 'devicestatus', doc->>'device', doc->>'created_at', doc->'srvModified'
    FROM "@devicestatus@".devicestatus WHERE doc->>'device' = '@run@'
  UNION ALL
  SELECT tenant_id, 'treatments', doc->>'enteredBy', doc->>'date', doc->'srvModified'
    FROM "@treatments@".treatments WHERE doc->>'enteredBy' = '@run@'
), active AS (
  SELECT tenant_id, json_agg(json_build_array(domain, marker, key, stamp)) AS inputs
    FROM inputs GROUP BY tenant_id
)
SELECT json_build_object(
  'tenant', a.tenant_id, 'inputs', a.inputs, 'identity', source.identity,
  'generation', l.generation, 'phase', l.phase, 'clock', w.last_stamp,
  'evaluated', o.checkpoint, 'observed', o.work_observed[1], 'completed', o.work_completed[1],
  'stateOK', o.work_version = 2 AND o.contract_digest = '@digest@' AND o.work_enabled
    AND o.projection->0->>'kind' = 'evaluator-work-v2'
    AND array_dims(o.work_observed) = '[1:6]' AND array_dims(o.work_completed) = '[1:6]'
    AND o.checkpoint BETWEEN 0 AND w.last_stamp,
  'outputAbsent', body.output = 'null'::jsonb AND o.output_revision = 0
    AND o.output_identity IS NULL AND o.output_digest IS NULL AND o.output_restore_generation IS NULL
    AND o.work_completed = array_fill(NULL::bigint, ARRAY[6]),
  'outputTenant', body.output->>'tenant',
  'outputOK', body.output->>'tenant' = a.tenant_id::text
    AND o.output_restore_generation = l.generation AND o.output_revision > 0
    AND o.output_identity ~ '^[a-f0-9]{64}$' AND o.output_digest ~ '^[a-f0-9]{64}$'
    AND body.output->'result'->>'progress' = 'level-window'
    AND body.output->'result'->>'generation' = l.generation::text
    AND jsonb_typeof(body.output->'result'->'properties') = 'object'
    AND jsonb_typeof(body.output->'frame') = 'object'
    AND body.output->>'inputCheckpoint' = body.output->'result'->>'checkpoint'
    AND CASE WHEN body.output->>'inputCheckpoint' ~ '^(0|[1-9][0-9]{0,18})$'
             THEN (body.output->>'inputCheckpoint')::numeric BETWEEN 0 AND o.checkpoint ELSE false END
)::text
-- Emit the database identity even when no run marker is visible yet.
FROM source LEFT JOIN active a ON true
LEFT JOIN "@lifecycle@".tenant_lifecycle_windows l USING (tenant_id)
LEFT JOIN "@clock@".tenant_write_clock w USING (tenant_id)
LEFT JOIN "@checkpoint@".tenant_consumer_checkpoint o ON o.tenant_id = a.tenant_id AND o.consumer = '@consumer@'
CROSS JOIN LATERAL (SELECT o.projection->0->'output' AS output) body;
