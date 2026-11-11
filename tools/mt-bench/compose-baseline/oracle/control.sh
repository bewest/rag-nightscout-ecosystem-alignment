#!/usr/bin/env bash
# Break-it control for the oracle: alter one stored row of the last run so it no longer carries the
# run marker, expect ORACLE RED, restore the row, expect ORACLE GREEN again.
#   control.sh <project> <env-file> <compose.yaml> <compose.bench.yaml> <run-dir>
set -uo pipefail
project=$1 env=$2 f1=$3 f2=$4 out=$5
here=$(cd "$(dirname "$0")" && pwd)
runid=$(cat "$out/runid")
psql_() { docker compose -p "$project" --env-file "$env" -f "$f1" -f "$f2" exec -T postgres psql -X -At -v ON_ERROR_STOP=1 -U postgres -d nightscout_compose_test -v runid="$runid" "$@"; }
before=$("$here/oracle.sh" "$@" | tail -1); echo "baseline: $before"
# The tenant insertion-ordinal trigger requires the row's tenant binding even for a superuser UPDATE
# (lib/tenant-lifecycle/tenant-insertion-sql.js:46-47), so each change binds it in its transaction.
victim=$(psql_ <<'SQL'
BEGIN;
SELECT set_config('app.current_tenant_id', (SELECT tenant_id::text FROM nsdemo_entries.entries WHERE doc->>'device' = :'runid' LIMIT 1), true) \gset ignored_
UPDATE nsdemo_entries.entries SET doc = jsonb_set(doc, '{device}', to_jsonb(:'runid' || '-tampered'))
 WHERE ctid = (SELECT ctid FROM nsdemo_entries.entries WHERE doc->>'device' = :'runid' AND tenant_id = current_setting('app.current_tenant_id')::uuid LIMIT 1)
 RETURNING tenant_id || ' ' || _id;
COMMIT;
SQL
)
echo "altered: $victim"
broken=$("$here/oracle.sh" "$@" | tail -1); echo "broken:   $broken"
psql_ >/dev/null <<'SQL'
BEGIN;
SELECT set_config('app.current_tenant_id', (SELECT tenant_id::text FROM nsdemo_entries.entries WHERE doc->>'device' = :'runid' || '-tampered' LIMIT 1), true) \gset ignored_
UPDATE nsdemo_entries.entries SET doc = jsonb_set(doc, '{device}', to_jsonb((:'runid')::text)) WHERE doc->>'device' = :'runid' || '-tampered';
COMMIT;
SQL
restored=$("$here/oracle.sh" "$@" | tail -1); echo "restored: $restored"
case "$before|$broken|$restored" in *GREEN*'|'*RED*'|'*GREEN*) echo "CONTROL PASS"; exit 0;; *) echo "CONTROL FAIL"; exit 1;; esac
