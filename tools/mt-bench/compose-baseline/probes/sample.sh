#!/usr/bin/env bash
# Samples every 2 s until killed: per-container CPU/RSS (docker stats), host load, and PostgreSQL
# backend states/wait events and ungranted locks (superuser psql inside the postgres container).
#   sample.sh <project> <env-file> <compose.yaml> <compose.bench.yaml> <out-dir>
set -uo pipefail
project=$1 env=$2 f1=$3 f2=$4 out=$5
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
  sleep 2
done
