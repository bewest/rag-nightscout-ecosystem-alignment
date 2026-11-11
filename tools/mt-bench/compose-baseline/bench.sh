#!/usr/bin/env bash
# MT-BENCH-BASELINE harness for the one-host multitenant Compose reference.
#
#   bench.sh deploy   <N>        prepare + bootstrap + up an N-tenant deployment
#   bench.sh run      <N> [label] host label, samplers, k6 workload, socket probe, oracle
#   bench.sh control  <N>        oracle break-it control (alter one row, expect red, restore)
#   bench.sh teardown <N>        compose down -v and remove that deployment's private state
#
# Environment (see README.md):
#   NS_BENCH_CORE     core checkout detached at the commit under test (built image must match)
#   NS_BENCH_OVERLAY  directory holding the N-tenant config.js/bootstrap.js for that commit
#   NS_BENCH_WORK     private, git-ignored working directory (state, credentials, raw output)
#   NS_BENCH_IMAGE    image tag built from NS_BENCH_CORE by deploy/multitenant/build.js
#   NS_BENCH_BASE_URL optional: skip deploy and drive an existing base URL (k6 + probe only)
#   BENCH_DURATION    k6 steady-state seconds (default 120)
#   BENCH_ACCEL       time compression of the 5-minute client cycle (default 60: one cycle per 5 s)
#   BENCH_HOT_FACTOR  hot tenant multiplier (default 10)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
: "${NS_BENCH_CORE:?core checkout}" "${NS_BENCH_WORK:?private work dir}"
NS_BENCH_IMAGE=${NS_BENCH_IMAGE:-nsbench-baseline:local}
K6_IMAGE=${K6_IMAGE:-grafana/k6:1.3.0}
BENCH_DURATION=${BENCH_DURATION:-120}
BENCH_ACCEL=${BENCH_ACCEL:-60}
BENCH_HOT_FACTOR=${BENCH_HOT_FACTOR:-10}
mt="$NS_BENCH_CORE/deploy/multitenant"

cmd=${1:?command}; N=${2:?tenant count}
port=$((18400 + N))
project="nsbench-n$N"
dir="$NS_BENCH_WORK/n$N"
compose() { docker compose -p "$project" --env-file "$dir/env" -f "$mt/compose.yaml" -f "$here/compose.bench.yaml" "$@"; }
# pg_stat_statements lives in the maintenance database only: created in the application database,
# its PUBLIC-executable functions make the lifetime window admission refuse (foreign_functions).
psql_super() { compose exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U postgres -d postgres "$@"; }

# Statement statistics for one phase: per-role totals, lifecycle operations (one INSERT per tenant
# operation-window lease: the evaluator's and realtime's per-tenant cycle count) and the top statements.
pgss_snapshot() {
  local out=$1 phase=$2
  psql_super -At -F $'\t' -c "SELECT r.rolname, sum(s.calls), round(sum(s.total_exec_time)::numeric,1) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid WHERE r.rolname LIKE 'nsdemo%' GROUP BY 1 ORDER BY 3 DESC" > "$out/pg-by-role-$phase.tsv"
  psql_super -At -F $'\t' -c "SELECT r.rolname, sum(s.calls) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid WHERE s.query LIKE 'INSERT INTO %tenant_lifecycle_operations%' GROUP BY 1 ORDER BY 1" > "$out/pg-ops-$phase.tsv"
  psql_super -At -F $'\t' -c "SELECT r.rolname, s.calls, round(s.total_exec_time::numeric,1), round(s.mean_exec_time::numeric,3), left(regexp_replace(s.query,'\s+',' ','g'),140) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid WHERE r.rolname LIKE 'nsdemo%' ORDER BY s.total_exec_time DESC LIMIT 40" > "$out/pg-statements-$phase.tsv"
  psql_super -c 'SELECT pg_stat_statements_reset()' >/dev/null
}

host_label() {
  local out=$1
  {
    echo "date_utc=$(date -u +%FT%TZ)"
    echo "cpu=$(lscpu | sed -n 's/^Model name:[[:space:]]*//p')"
    echo "cores=$(nproc)"
    echo "mem_total_kb=$(awk '/MemTotal/{print $2}' /proc/meminfo)"
    echo "disk=$(df -h /var/lib/docker 2>/dev/null | awk 'NR==2{print $1" size="$2" avail="$4" use="$5}')"
    echo "docker=$(docker version --format '{{.Server.Version}}')"
    echo "compose=$(docker compose version --short)"
    echo "kernel=$(uname -r)"
    echo "loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
    echo "containers_running=$(docker ps -q | wc -l)"
    echo "containers_other=$(docker ps --format '{{.Label "com.docker.compose.project"}}' | grep -vc "^$project\$" || true)"
  } > "$out"
}

case "$cmd" in
  deploy)
    [ -e "$dir" ] && { echo "exists: $dir (teardown first)" >&2; exit 1; }
    mkdir -p "$dir"
    [ -e "$mt/.env" ] && { echo "core checkout already has deploy/multitenant/.env; move it aside" >&2; exit 1; }
    (cd "$mt" && node prepare.js --state "$dir/state" --port "$port")
    mv "$mt/.env" "$dir/env"
    printf 'NS_DEMO_IMAGE=%s\nNS_DEMO_TENANTS=%s\nNS_BENCH_OVERLAY=%s\n' "$NS_BENCH_IMAGE" "$N" "${NS_BENCH_OVERLAY:?overlay dir}" >> "$dir/env"
    rev=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$NS_BENCH_IMAGE")
    [ "$rev" = "$(git -C "$NS_BENCH_CORE" rev-parse HEAD)" ] || { echo "image revision $rev does not match core HEAD" >&2; exit 1; }
    t0=$(date +%s.%N)
    compose up -d --wait postgres vault
    compose --profile ops run --rm bootstrap
    t1=$(date +%s.%N)
    compose up -d --no-build --pull never --wait --wait-timeout 600 api realtime evaluator tenant-admin ui nginx
    t2=$(date +%s.%N)
    printf '{"tenants":%s,"port":%s,"bootstrapSeconds":%.1f,"startSeconds":%.1f}\n' "$N" "$port" \
      "$(echo "$t1 - $t0" | bc)" "$(echo "$t2 - $t1" | bc)" > "$dir/deploy.json"
    cat "$dir/deploy.json"
    ;;
  run)
    label=${3:-run}
    out="$dir/$label"; mkdir -p "$out"
    base=${NS_BENCH_BASE_URL:-http://127.0.0.1:$port}
    host_label "$out/host-before.txt"
    # Tenants file for the workload: hosts and data tokens (private; never leaves $NS_BENCH_WORK).
    node -e '
      const t=require(process.argv[1]).tenants.map(({id,host,dataToken})=>({id,host,token:dataToken}));
      require("fs").writeFileSync(process.argv[2],JSON.stringify(t),{mode:0o600});' \
      "$dir/state/ops/tenants.json" "$out/tenants.private.json"
    runid="bench-$(date +%s)"; echo "$runid" > "$out/runid"
    printf '{"duration":%s,"accel":%s,"hotFactor":%s,"k6Image":"%s","socketsHot":%s,"socketsCold":%s,"probeIntervalMs":%s,"baseUrl":"%s"}\n' \
      "$BENCH_DURATION" "$BENCH_ACCEL" "$BENCH_HOT_FACTOR" "$K6_IMAGE" "${SOCKETS_HOT:-20}" "${SOCKETS_COLD:-40}" "${PROBE_INTERVAL_MS:-2000}" "$base" > "$out/bench.json"
    compose ps --format json > "$out/compose-ps.json"
    for svc in postgres vault api realtime evaluator tenant-admin ui nginx; do
      echo "$svc $(docker inspect --format '{{.Image}}' "$(compose ps -q "$svc")")"
    done > "$out/image-ids.txt"
    psql_super -c 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements' -c 'SELECT pg_stat_statements_reset()' >/dev/null
    "$here/oracle/disk.sh" "$project" "$dir/env" "$mt/compose.yaml" "$here/compose.bench.yaml" "$out" > "$out/disk-before.txt"
    "$here/probes/sample.sh" "$project" "$dir/env" "$mt/compose.yaml" "$here/compose.bench.yaml" "$out" &
    sampler=$!
    trap 'kill $sampler 2>/dev/null || true' EXIT
    # Idle window: background polling cost of N configured tenants with no client load.
    echo "idle_start=$(date +%s.%N)" > "$out/phases.txt"; sleep 30; echo "idle_end=$(date +%s.%N)" >> "$out/phases.txt"
    pgss_snapshot "$out" idle
    # Socket probe runs alongside k6 and measures write-to-dataUpdate fanout, then a realtime restart.
    NODE_PATH="$NS_BENCH_CORE/node_modules" node "$here/probes/fanout.js" --base "$base" --tenants "$out/tenants.private.json" --runid "$runid" \
      --duration "$BENCH_DURATION" --out "$out/fanout.json" --compose "$project|$dir/env|$mt/compose.yaml|$here/compose.bench.yaml" \
      > "$out/fanout.log" 2>&1 &
    probe=$!
    echo "load_start=$(date +%s.%N)" >> "$out/phases.txt"
    docker run --rm --network host -u "$(id -u):$(id -g)" -v "$here/k6:/scripts:ro" -v "$out:/out" \
      -e BASE_URL="$base" -e TENANTS_FILE=/out/tenants.private.json -e RUN_ID="$runid" -e RUN_START="$(( $(date +%s) * 1000 - 86400000 ))" \
      -e DURATION="$BENCH_DURATION" -e ACCEL="$BENCH_ACCEL" -e HOT_FACTOR="$BENCH_HOT_FACTOR" \
      "$K6_IMAGE" run --quiet --summary-export /out/k6-summary.json /scripts/workload.js > "$out/k6.log" 2>&1 || echo "k6 exit $?" >> "$out/k6.log"
    echo "load_end=$(date +%s.%N)" >> "$out/phases.txt"
    pgss_snapshot "$out" load
    wait $probe || echo "probe exit $?" >> "$out/fanout.log"
    echo "reconnect_end=$(date +%s.%N)" >> "$out/phases.txt"
    kill $sampler 2>/dev/null || true; wait $sampler 2>/dev/null || true; trap - EXIT
    pgss_snapshot "$out" reconnect
    "$here/oracle/oracle.sh" "$project" "$dir/env" "$mt/compose.yaml" "$here/compose.bench.yaml" "$out" > "$out/oracle.txt" || true
    "$here/oracle/disk.sh" "$project" "$dir/env" "$mt/compose.yaml" "$here/compose.bench.yaml" "$out" > "$out/disk.txt" || true
    host_label "$out/host-after.txt"
    rm -f "$out/tenants.private.json"
    node "$here/summarize.js" "$out" "$N" > "$out/summary.json"
    cat "$out/oracle.txt"
    ;;
  control)
    out=$(dirname "$(ls -t "$dir"/*/runid | head -1)")   # the most recent run (not state/)
    "$here/oracle/control.sh" "$project" "$dir/env" "$mt/compose.yaml" "$here/compose.bench.yaml" "$out"
    ;;
  teardown)
    [ -f "$dir/env" ] && compose --profile ops down -v --remove-orphans
    rm -rf "$dir/state"
    ;;
  *) echo "unknown command $cmd" >&2; exit 64 ;;
esac
