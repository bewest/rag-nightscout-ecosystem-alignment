-- One activity snapshot, with at most 32 pg_blocking_pids calls per sample.
-- Export only synthetic role names, lock types, event names and opaque query IDs.
WITH activity AS MATERIALIZED (
  SELECT pid,
         CASE WHEN usename ~ '^(nsdemo_[a-z0-9_]+|postgres)$'
              THEN usename::text ELSE 'other' END AS role,
         coalesce(state, '') AS state,
         coalesce(wait_event_type, '') AS wait_type,
         coalesce(wait_event, '') AS event,
         coalesce(query_id::text, '-') AS queryid
  FROM pg_stat_activity
  WHERE datname = 'nightscout_compose_test' AND pid <> pg_backend_pid()
), waiters AS MATERIALIZED (
  SELECT * FROM activity WHERE wait_type = 'Lock' ORDER BY pid LIMIT 32
), blockers AS MATERIALIZED (
  SELECT pid, pg_blocking_pids(pid) AS blocking_pids FROM waiters
), waiting_locks AS MATERIALIZED (
  SELECT pid, min(locktype) AS locktype
  FROM pg_locks WHERE NOT granted AND pid IN (SELECT pid FROM waiters)
  GROUP BY pid
), observed AS (
  SELECT w.role, w.state, w.event, w.queryid, coalesce(l.locktype, '-') AS locktype,
         coalesce(b.roles, '-') AS roles
  FROM waiters w
  JOIN blockers USING (pid)
  LEFT JOIN waiting_locks l USING (pid)
  CROSS JOIN LATERAL (
    SELECT string_agg(DISTINCT coalesce(a.role, 'unresolved'),
                      ',' ORDER BY coalesce(a.role, 'unresolved')) AS roles
    FROM unnest(blockers.blocking_pids) AS p(pid) LEFT JOIN activity a USING (pid)
  ) b
)
SELECT 'activity', role, state, wait_type, event, count(*)::text, '', '', ''
FROM activity GROUP BY role, state, wait_type, event
UNION ALL
SELECT 'sample', count(*)::text, greatest(count(*) - 32, 0)::text, '', '', '', '', '', ''
FROM activity WHERE wait_type = 'Lock'
UNION ALL
SELECT 'wait', role, state, event, queryid, locktype, roles, count(*)::text, ''
FROM observed GROUP BY role, state, event, queryid, locktype, roles;
