#!/usr/bin/env bash
# Disk: database size, per-schema size, and the run's stored bytes per domain (pg_column_size of doc).
set -euo pipefail
project=$1 env=$2 f1=$3 f2=$4 out=$5
runid=$(cat "$out/runid")
docker compose -p "$project" --env-file "$env" -f "$f1" -f "$f2" exec -T postgres \
  psql -X -At -F $'\t' -v ON_ERROR_STOP=1 -U postgres -d nightscout_compose_test -v runid="$runid" <<'SQL'
SELECT 'database_bytes', pg_database_size('nightscout_compose_test');
SELECT 'schema_bytes', n.nspname, sum(pg_total_relation_size(c.oid)) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname LIKE 'nsdemo_%' AND c.relkind IN ('r','m') GROUP BY 2 ORDER BY 3 DESC;
SELECT 'run_rows', 'entries', count(*), sum(pg_column_size(doc)) FROM nsdemo_entries.entries WHERE doc->>'device' = :'runid';
SELECT 'run_rows', 'devicestatus', count(*), sum(pg_column_size(doc)) FROM nsdemo_devicestatus.devicestatus WHERE doc->>'device' = :'runid';
SELECT 'run_rows', 'treatments', count(*), sum(pg_column_size(doc)) FROM nsdemo_treatments.treatments WHERE doc->>'enteredBy' = :'runid';
SELECT 'table_bytes', n.nspname || '.' || c.relname, pg_total_relation_size(c.oid), c.reltuples::bigint FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname IN ('nsdemo_entries','nsdemo_devicestatus','nsdemo_treatments') AND c.relkind='r';
SQL
