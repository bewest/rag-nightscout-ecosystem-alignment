-- Single MVCC snapshot. Only tenants with this run's synthetic mutations enter
-- the receipt and output joins. The immutable input key is also emitted at ACK.
WITH inputs AS MATERIALIZED (
  SELECT tenant_id, 'entries' AS domain, doc->>'device' AS marker, doc->>'date' AS key
    FROM nsdemo_entries.entries WHERE doc->>'device' IN ('@run@', '@run@-probe')
  UNION ALL
  SELECT tenant_id, 'devicestatus', doc->>'device', doc->>'created_at'
    FROM nsdemo_devicestatus.devicestatus WHERE doc->>'device' = '@run@'
  UNION ALL
  SELECT tenant_id, 'treatments', doc->>'enteredBy', doc->>'date'
    FROM nsdemo_treatments.treatments WHERE doc->>'enteredBy' = '@run@'
), active AS (
  SELECT tenant_id, json_agg(json_build_array(domain, marker, key)) AS inputs
    FROM inputs GROUP BY tenant_id
)
SELECT json_build_object(
  'tenant', a.tenant_id, 'inputs', a.inputs,
  'events', COALESCE(events.keys, '[]'::json),
  'latest', CASE WHEN (i.projection->0->'stream'->>'accepted_position')::pg_lsn >
                           (i.projection->0->'stream'->>'snapshot_position')::pg_lsn
                   AND i.projection->1->>'last' = i.projection->0->'stream'->>'accepted_position'
                   AND (i.projection->1->'events'->-1->>'sequence')::bigint = (i.projection->1->>'head')::bigint
                   THEN events.latest END,
  'snapshotPosition', i.projection->0->'stream'->>'snapshot_position',
  'outputAbsent', o.tenant_id IS NULL,
  'tailBase', i.projection->1->'base', 'tailHead', i.projection->1->'head',
  'inputFloor', i.checkpoint, 'generation', l.generation,
  'identity', i.projection->0->'stream'->'source_identity',
  'sourceOK', l.phase IN ('active','suspended') AND i.projection->0->>'kind' = 'clinical-stream-v2'
    AND i.projection->1->>'kind' = 'storage-events-v1'
    AND i.projection->0->>'floor' = i.checkpoint::text
    AND i.projection->0->'stream'->>'generation' = '@generation@:' || l.generation::text
    AND i.projection->0->'stream'->'source_identity' = jsonb_build_object(
      'system_id', (pg_control_system()).system_identifier::text,
      'timeline', (pg_control_checkpoint()).timeline_id, 'database', current_database(), 'slot', '@slot@'),
  'stateOK', o.work_version = 2 AND o.contract_digest = '@digest@'
    AND o.projection->0->>'kind' = 'evaluator-work-v2' AND o.work_enabled
    AND o.checkpoint BETWEEN 0 AND i.checkpoint
    AND (o.work_completed[6] IS NULL OR (o.work_completed[6] BETWEEN 0 AND o.checkpoint
      AND o.work_observed[6] BETWEEN o.work_completed[6] AND i.checkpoint)),
  'completed', o.work_completed[6],
  'revision', o.output_revision,
  'outputTenant', o.projection->0->'output'->>'tenant',
  'outputOK', o.output_restore_generation = l.generation AND o.output_revision > 0
    AND o.output_identity ~ '^[a-f0-9]{64}$' AND o.output_digest ~ '^[a-f0-9]{64}$'
    AND jsonb_typeof(o.projection->0->'output'->'result'->'properties') = 'object'
    AND jsonb_typeof(o.projection->0->'output'->'frame') = 'object'
    AND (o.projection->0->'output'->>'inputCheckpoint')::bigint BETWEEN 0 AND o.checkpoint
    AND o.projection->0->'output'->>'inputCheckpoint' = o.projection->0->'output'->'result'->>'checkpoint'
)::text
FROM active a
LEFT JOIN "@checkpoint@".tenant_consumer_checkpoint i
  ON i.tenant_id = a.tenant_id AND i.consumer = '@consumer@'
LEFT JOIN "@checkpoint@".tenant_consumer_checkpoint o
  ON o.tenant_id = a.tenant_id AND o.consumer = '@consumer@-completed'
LEFT JOIN "@lifecycle@".tenant_lifecycle_windows l ON l.tenant_id = a.tenant_id
LEFT JOIN LATERAL (
  SELECT json_agg(json_build_array(e->>'domain', COALESCE(doc->>'device',doc->>'enteredBy'),
       CASE WHEN e->>'domain' = 'devicestatus' THEN doc->>'created_at' ELSE doc->>'date' END)) AS keys,
    (jsonb_agg(jsonb_build_array(e->>'domain', COALESCE(doc->>'device',doc->>'enteredBy'),
       CASE WHEN e->>'domain' = 'devicestatus' THEN doc->>'created_at' ELSE doc->>'date' END))
       FILTER (WHERE (e->>'sequence')::bigint = (i.projection->1->>'head')::bigint))->0 AS latest
  FROM jsonb_array_elements(i.projection->1->'events') e
  CROSS JOIN LATERAL (SELECT e->'value'->'doc' AS doc) v
  WHERE e->>'event' IN ('create','update') AND
    (doc->>'device' IN ('@run@','@run@-probe') OR doc->>'enteredBy' = '@run@')
) events ON true;
