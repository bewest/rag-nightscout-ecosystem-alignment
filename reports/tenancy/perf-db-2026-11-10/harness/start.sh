#!/usr/bin/env bash
# Startup at N tenants on the one-host Compose reference, then an idle window.
#   start.sh <N> <label> [startup-concurrency]
# Env: CORE (worktree), IMAGE, OVERLAY, WORK (private run dir), IDLE_S (default 60)
set -uo pipefail
N=$1 label=$2 conc=${3:-}
here=$(cd "$(dirname "$0")" && pwd)
mt="$CORE/deploy/multitenant"; bench=/home/bewest/src/rag-nightscout-ecosystem-alignment/tools/mt-bench/compose-baseline
project="ns-pdb-$label"; dir="$WORK/$label"; IDLE_S=${IDLE_S:-60}
mkdir -p "$dir"
port=$((19400 + N % 1000))
(cd "$mt" && node prepare.js --state "$dir/state" --port "$port" >/dev/null) || exit 1
mv "$mt/.env" "$dir/env"
printf 'NS_DEMO_IMAGE=%s\nNS_DEMO_TENANTS=%s\nNS_BENCH_OVERLAY=%s\n' "$IMAGE" "$N" "$OVERLAY" >> "$dir/env"
# Healthchecks get room to measure the real time to ready; optional startup concurrency.
{
  echo "services:"
  for s in api realtime evaluator; do
    echo "  $s:"
    echo "    healthcheck: {interval: 1s, timeout: 2s, retries: 3, start_period: 1200s, start_interval: 1s}"
    [ -n "$conc" ] && echo "    environment: {NS_TENANT_STARTUP_CONCURRENCY: \"$conc\"}"
  done
} > "$dir/override.yaml"
compose() { docker compose -p "$project" --env-file "$dir/env" -f "$mt/compose.yaml" -f "$bench/compose.bench.yaml" -f "$dir/override.yaml" "$@"; }
psql_super() { compose exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U postgres -d postgres "$@"; }
out="$dir/result.json"
echo "loadavg_before=$(cut -d' ' -f1-3 /proc/loadavg)" > "$dir/host.txt"
compose up -d --wait postgres vault >/dev/null 2>&1 || { echo '{"error":"postgres/vault"}' > "$out"; exit 1; }
psql_super -c 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements' >/dev/null
compose --profile ops run --rm bootstrap > "$dir/bootstrap.log" 2>&1 || { echo '{"error":"bootstrap"}' > "$out"; exit 1; }
psql_super -c 'SELECT pg_stat_statements_reset()' >/dev/null
t0=$(date +%s.%N)
compose up -d --no-build --pull never api realtime evaluator tenant-admin >/dev/null 2>&1
declare -A ready
deadline=$(( $(date +%s) + 1200 )); status=timeout
while [ "$(date +%s)" -lt "$deadline" ]; do
  all=1
  for s in api realtime evaluator tenant-admin; do
    [ -n "${ready[$s]:-}" ] && continue
    cid=$(compose ps -a -q "$s"); st=$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}} {{.State.ExitCode}}' "$cid" 2>/dev/null)
    case "$st" in
      "running healthy"*) ready[$s]=$(echo "$(date +%s.%N) - $t0" | bc) ;;
      exited*) ready[$s]="exit:${st##* }"; status=failed ;;
      *) all=0 ;;
    esac
  done
  [ "$status" = failed ] && break
  [ "$all" = 1 ] && { status=ok; break; }
  sleep 0.5
done
echo "loadavg_ready=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$dir/host.txt"
for s in api realtime evaluator tenant-admin; do compose logs --no-color "$s" 2>/dev/null | tail -40 > "$dir/$s.log"; done
psql_super -At -F $'\t' -c "SELECT r.rolname, sum(s.calls), round(sum(s.total_exec_time)::numeric,1) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid WHERE r.rolname LIKE 'nsdemo%' GROUP BY 1 ORDER BY 3 DESC" > "$dir/pg-startup.tsv"
idle=""
if [ "$status" = ok ]; then
  psql_super -c 'SELECT pg_stat_statements_reset()' >/dev/null
  i0=$(date +%s.%N); sleep "$IDLE_S"
  psql_super -At -F $'\t' -c "SELECT r.rolname, sum(s.calls), round(sum(s.total_exec_time)::numeric,1) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid WHERE r.rolname LIKE 'nsdemo%' GROUP BY 1 ORDER BY 3 DESC" > "$dir/pg-idle.tsv"
  psql_super -At -F $'\t' -c "SELECT r.rolname, s.calls, round(s.total_exec_time::numeric,1), left(regexp_replace(s.query,'\s+',' ','g'),110) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid WHERE r.rolname LIKE 'nsdemo%' ORDER BY s.total_exec_time DESC LIMIT 15" > "$dir/pg-idle-top.tsv"
  i1=$(date +%s.%N); idle=$(echo "$i1 - $i0" | bc)
  compose exec -T postgres psql -X -At -F $'\t' -U postgres -d nightscout_compose_test -c "SELECT usename, state, count(*) FROM pg_stat_activity WHERE datname=current_database() GROUP BY 1,2 ORDER BY 1,2" > "$dir/pg-conns.tsv"
  docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' $(compose ps -q) > "$dir/docker-stats.tsv"
  docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' $(compose ps -q) > "$dir/docker-stats-2.tsv"
fi
echo "loadavg_after=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$dir/host.txt"
{
  printf '{"tenants":%s,"label":"%s","concurrency":"%s","status":"%s","idle_s":"%s"' "$N" "$label" "${conc:-default}" "$status" "$idle"
  for s in api realtime evaluator tenant-admin; do printf ',"%s":"%s"' "$s" "${ready[$s]:-not-ready}"; done
  echo '}'
} > "$out"
cat "$out"
[ "${KEEP:-0}" = 1 ] || { compose --profile ops down -v --remove-orphans >/dev/null 2>&1; rm -rf "$dir/state"; }
