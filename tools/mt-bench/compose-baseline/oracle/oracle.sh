#!/usr/bin/env bash
# Independent stored-count oracle: counts this run's rows per tenant and domain directly in
# PostgreSQL (superuser psql inside the postgres container: no API, no RLS, no application code),
# then compares with what the clients were told was accepted (k6 summary, probe output).
#   oracle.sh <project> <env-file> <compose.yaml> <compose.bench.yaml> <run-dir>
set -euo pipefail
project=$1 env=$2 f1=$3 f2=$4 out=$5
runid=$(cat "$out/runid")
here=$(cd "$(dirname "$0")" && pwd)
docker compose -p "$project" --env-file "$env" -f "$f1" -f "$f2" exec -T postgres \
  psql -X -At -F $'\t' -v ON_ERROR_STOP=1 -U postgres -d nightscout_compose_test -v runid="$runid" > "$out/oracle-stored.tsv" <<'SQL'
SELECT tenant_id, 'entries', count(*) FROM nsdemo_entries.entries WHERE doc->>'device' = :'runid' GROUP BY 1
UNION ALL SELECT tenant_id, 'devicestatus', count(*) FROM nsdemo_devicestatus.devicestatus WHERE doc->>'device' = :'runid' GROUP BY 1
UNION ALL SELECT tenant_id, 'treatments', count(*) FROM nsdemo_treatments.treatments WHERE doc->>'enteredBy' = :'runid' GROUP BY 1
UNION ALL SELECT tenant_id, 'probe', count(*) FROM nsdemo_entries.entries WHERE doc->>'device' = :'runid' || '-probe' GROUP BY 1;
SQL
node "$here/compare.js" "$out"
