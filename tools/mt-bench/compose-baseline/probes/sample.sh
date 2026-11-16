#!/usr/bin/env bash
# Samples at the supplied interval (default 2 s) until killed: per-container CPU/RSS (docker stats), host load, and PostgreSQL
# backend states/wait events and ungranted locks (superuser psql inside the postgres container).
#   sample.sh <project> <env-file> <compose.yaml> <compose.bench.yaml> <out-dir>
set -uo pipefail
project=$1 env=$2 f1=$3 f2=$4 out=$5 interval=${6:-2}
[[ "$interval" =~ ^[1-9][0-9]*$ ]] && (( interval <= 60 )) || exit 64
# Resolve caller-relative paths before moving to an accessible Compose context.
normalize() { realpath -e -- "$1"; }
helper=$(normalize "$(dirname -- "${BASH_SOURCE[0]}")/../../m7-joined/host_io.py") || { echo 'NO-INSTRUMENT: host IO helper path' >&2; exit 66; }
env=$(normalize "$env") && f1=$(normalize "$f1") && f2=$(normalize "$f2") && out=$(normalize "$out") || { echo 'NO-INSTRUMENT: sampler path normalization failed' >&2; exit 66; }
[[ -f "$env" && -f "$f1" && -f "$f2" && -d "$out" ]] || { echo 'NO-INSTRUMENT: sampler input type' >&2; exit 66; }
cd -- "$(dirname -- "$f1")" || { echo 'NO-INSTRUMENT: Compose working directory unavailable' >&2; exit 66; }
# A failed helper must leave an explicit missing-instrument receipt, never silence.
printf '%s\n' '{"schema":"host-io-v1","status":"NO-INSTRUMENT","reason":"helper has not initialized; inspect host-io.stderr"}' > "$out/host-io-metadata.json"
python3 "$helper" "$out" "$interval" 2> "$out/host-io.stderr" &
io_pid=$!
cleanup() { kill "$io_pid" 2>/dev/null || true; wait "$io_pid" 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 0' TERM INT
pg=$(docker compose -p "$project" --env-file "$env" -f "$f1" -f "$f2" ps -q postgres)
echo -e "t\tcontainer\tcpu_pct\tmem" > "$out/docker-stats.tsv"
echo -e "t\tload1\tload5\tload15" > "$out/host-load.tsv"
echo -e "t\trole\tstate\twait_event_type\twait_event\tn" > "$out/pg-activity.tsv"
echo -e "t\tungranted_locks\tbackends" > "$out/pg-locks.tsv"
while :; do
  t=$(date +%s.%N)
  docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' $(docker ps -q --filter "label=com.docker.compose.project=$project") \
    | sed "s/^/$t\t/" >> "$out/docker-stats.tsv"
  echo -e "$t\t$(cut -d' ' -f1-3 /proc/loadavg | tr ' ' '\t')" >> "$out/host-load.tsv"
  docker exec "$pg" psql -X -At -F $'\t' -U postgres -d postgres -c "SELECT usename, state, coalesce(wait_event_type,''), coalesce(wait_event,''), count(*) FROM pg_stat_activity WHERE datname='nightscout_compose_test' GROUP BY 1,2,3,4" 2>/dev/null \
    | sed "s/^/$t\t/" >> "$out/pg-activity.tsv"
  docker exec "$pg" psql -X -At -F $'\t' -U postgres -d postgres -c "SELECT (SELECT count(*) FROM pg_locks WHERE NOT granted), (SELECT count(*) FROM pg_stat_activity WHERE datname='nightscout_compose_test')" 2>/dev/null \
    | sed "s/^/$t\t/" >> "$out/pg-locks.tsv"
  sleep "$interval"
done
