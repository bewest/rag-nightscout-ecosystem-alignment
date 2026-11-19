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
# Only a source-pinned discovery actor opts into the paired blocker snapshot.
owner=${M7_SAMPLE_OWNER:-}
if [[ -n "$owner" ]]; then
  [[ "$owner" =~ ^[0-9a-f]{32}$ ]] || exit 64
  blocker_sql=$(normalize "$(dirname -- "$helper")/pg-blockers.sql") || exit 66
  printf 't\towner\tkind\tfields...\n' > "$out/pg-blockers.tsv"
fi
pg=$(docker compose -p "$project" --env-file "$env" -f "$f1" -f "$f2" ps -q postgres)
echo -e "t\tcontainer\tcpu_pct\tmem" > "$out/docker-stats.tsv"
echo -e "t\tload1\tload5\tload15" > "$out/host-load.tsv"
echo -e "t\trole\tstate\twait_event_type\twait_event\tn" > "$out/pg-activity.tsv"
echo -e "t\tungranted_locks\tbackends" > "$out/pg-locks.tsv"
# The runner writes the full ID at create time, before starting the load actor.
# A driver that exits between ticks can have a terminal receipt with no sample.
sample_driver_memory() {
  local cid started values
  [[ -r "$out/k6-container.cid" ]] || return 0
  cid=$(cat "$out/k6-container.cid") || return 0
  [[ "$cid" =~ ^[0-9a-f]{64}$ ]] || return 0
  started=$(timeout 3 docker container inspect --format '{{if .State.Running}}{{.State.StartedAt}}{{end}}' "$cid" 2>/dev/null) || return 0
  [[ -n "$started" ]] || return 0
  values=$(timeout 3 docker exec "$cid" cat /sys/fs/cgroup/{memory.peak,memory.max,memory.swap.max} 2>/dev/null) || return 0
  [[ "$values" =~ ^[0-9]+$'\n'(max|[0-9]+)$'\n'(max|[0-9]+)$ ]] || return 0
  [[ "$started" == "$(timeout 3 docker container inspect --format '{{.State.StartedAt}}' "$cid" 2>/dev/null)" ]] || return 0
  printf '%s\t%s\t%s\t%s\n' "$(date +%s.%N)" "$cid" "$started" "${values//$'\n'/$'\t'}" >> "$out/k6-memory.tsv"
}
driver_memory=${M7_SAMPLE_DRIVER_MEMORY:-}
if [[ "$driver_memory" == 1 ]]; then
  printf 't\tcontainerId\tstartedAt\tmemoryPeakBytes\tmemoryMax\tmemorySwapMax\n' > "$out/k6-memory.tsv"
fi
while :; do
  t=$(date +%s.%N)
  if [[ "$driver_memory" == 1 ]]; then sample_driver_memory; fi
  ids=$(docker ps -q --filter "label=com.docker.compose.project=$project")
  if [[ -n "$ids" ]]; then
    docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' $ids \
      | sed "s/^/$t\t/" >> "$out/docker-stats.tsv"
  fi
  echo -e "$t\t$(cut -d' ' -f1-3 /proc/loadavg | tr ' ' '\t')" >> "$out/host-load.tsv"
  if [[ -n "$owner" ]]; then
    # Buffer the bounded response so a failed query cannot publish a valid tick.
    if rows=$(docker exec -i "$pg" psql -X -qAt -F $'\t' -v ON_ERROR_STOP=1 -U postgres -d postgres \
          -c 'SET statement_timeout = 750' -f - < "$blocker_sql" 2>/dev/null); then
      awk -F '\t' -v OFS='\t' -v t="$t" -v owner="$owner" -v out="$out" '
        $1 == "activity" {print t,$2,$3,$4,$5,$6 >> (out "/pg-activity.tsv")}
        $1 == "sample" {print t,owner,$1,$2,$3 >> (out "/pg-blockers.tsv")}
        $1 == "wait" {print t,owner,$1,$2,$3,$4,$5,$6,$7,$8 >> (out "/pg-blockers.tsv")}
      ' <<< "$rows"
    fi
  else
    docker exec "$pg" psql -X -At -F $'\t' -U postgres -d postgres -c "SELECT usename, state, coalesce(wait_event_type,''), coalesce(wait_event,''), count(*) FROM pg_stat_activity WHERE datname='nightscout_compose_test' GROUP BY 1,2,3,4" 2>/dev/null \
      | sed "s/^/$t\t/" >> "$out/pg-activity.tsv"
  fi
  docker exec "$pg" psql -X -At -F $'\t' -U postgres -d postgres -c "SELECT (SELECT count(*) FROM pg_locks WHERE NOT granted), (SELECT count(*) FROM pg_stat_activity WHERE datname='nightscout_compose_test')" 2>/dev/null \
    | sed "s/^/$t\t/" >> "$out/pg-locks.tsv"
  sleep "$interval"
done
