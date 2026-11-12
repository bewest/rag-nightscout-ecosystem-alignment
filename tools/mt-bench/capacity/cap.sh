#!/usr/bin/env bash
# Quiet-host capacity campaign driver (2026-11-11) for the one-host multitenant Compose reference,
# nightscout-deploy's Compose tree overlaid on core. Synthetic data only.
#
#   cap.sh deploy   <label> <N>        prepare (source-checked) + bootstrap + start roles; startup timings
#   cap.sh idle     <label> <N> <s>    idle window: no clients; CPU, RSS, DB time, connections
#   cap.sh load     <label> <N> <s>    real cadence (k6) + sockets + probe writes, then a full restart
#   cap.sh oracle   <label> <N>        stored-count oracle for the load run
#   cap.sh control  <label> <N>        oracle break-it control (compose-baseline control.sh)
#   cap.sh teardown <label> <N>        down -v, remove private state (raw output kept)
#
# Environment:
#   CAP_CORE     core overlay tree (tools/compose-overlay.sh output), HEAD = the core commit under test
#   CAP_DEPLOY   nightscout-deploy checkout; CAP_DEPLOY_COMMIT the commit whose multitenant tree is overlaid
#   CAP_WORK     private run directory outside any checkout (state, credentials, raw output)
#   CAP_IMAGE    image built by build.sh (revision label = core HEAD)
#   CAP_EXTRA    optional extra Compose files, colon-separated (instrument mounts)
#   CAP_CONFIG_MAX_BYTES  optional role config bound (core 5517cb6c+: MULTITENANT_CONFIG_MAX_BYTES)
#   CAP_NO_K6=1 (load window without k6: sockets only), CAP_SOCKETS_PER=0 (no sockets: k6 only)
#   CAP_SOCKETS_PER (2), CAP_OPEN_MS (stagger between socket opens, 5), CAP_PROBE_MS (probe write period, 3000)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); base="$here/../compose-baseline"
: "${CAP_CORE:?}" "${CAP_DEPLOY:?}" "${CAP_DEPLOY_COMMIT:?}" "${CAP_WORK:?}" "${CAP_IMAGE:?}"
K6_IMAGE=${K6_IMAGE:-grafana/k6:1.3.0}
cmd=$1 label=$2 N=$3; shift 3
mt="$CAP_CORE/deploy/multitenant"
project="nscap-$label-n$N"; dir="$CAP_WORK/$label-n$N"
port=$(( 30000 + (N % 10000) + ( $(printf '%s' "$label" | cksum | cut -d' ' -f1) % 50 ) * 10 ))
[ -f "$dir/port" ] && port=$(cat "$dir/port")
files=(-f "$mt/compose.yaml" -f "$base/compose.bench.yaml")
IFS=: read -r -a extra <<< "${CAP_EXTRA:-}"; for f in "${extra[@]}"; do [ -n "$f" ] && files+=(-f "$f"); done
compose() { docker compose -p "$project" --env-file "$dir/env" "${files[@]}" "$@"; }
spec() { local s="$project|$dir/env"; for f in "${files[@]}"; do [ "$f" = -f ] || s="$s|$f"; done; echo "$s"; }
psql_super() { compose exec -T postgres psql -X -q -At -F $'\t' -v ON_ERROR_STOP=1 -U postgres -d postgres "$@"; }
psql_app() { compose exec -T postgres psql -X -q -At -F $'\t' -v ON_ERROR_STOP=1 -U postgres -d nightscout_compose_test "$@"; }
stamp() { echo "$(date -u +%FT%TZ) load=$(cut -d' ' -f1-3 /proc/loadavg) $*"; }
host_label() {
  {
    echo "date_utc=$(date -u +%FT%TZ)"; echo "uptime=$(uptime)"
    echo "loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"; echo "cores=$(nproc)"
    echo "mem_available_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo)"
    echo "containers_running=$(docker ps -q | wc -l)"
    echo "containers_other=$(docker ps --format '{{.Names}}' | grep -vc "^$project-" || true)"
    echo "containers_other_names=$(docker ps --format '{{.Names}}' | grep -v "^$project-" | sort | tr '\n' ' ')"
  } > "$1"
}
# cgroup counters for every role container: CPU µs, memory.current, anon (one JSON object).
cgroups() {
  local first=1; printf '{"at":%s' "$(date +%s%3N)"
  for svc in api realtime evaluator tenant-admin postgres nginx; do
    local id; id=$(compose ps -q "$svc" 2>/dev/null || true); [ -n "$id" ] || continue
    local cpu mem anon
    cpu=$(docker exec "$id" cat /sys/fs/cgroup/cpu.stat 2>/dev/null | awk '/^usage_usec/{print $2}')
    mem=$(docker exec "$id" cat /sys/fs/cgroup/memory.current 2>/dev/null)
    anon=$(docker exec "$id" cat /sys/fs/cgroup/memory.stat 2>/dev/null | awk '/^anon /{print $2}')
    printf ',"%s":{"cpuUsec":%s,"memoryCurrent":%s,"anon":%s}' "$svc" "${cpu:-null}" "${mem:-null}" "${anon:-null}"
  done
  echo '}'
}
pg_phase() { # $1 out prefix: per-role statement time, connections by identity
  psql_super -c "SELECT r.rolname, sum(s.calls), round(sum(s.total_exec_time)::numeric,1) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid WHERE r.rolname LIKE 'nsdemo%' GROUP BY 1 ORDER BY 3 DESC" > "$1-pg-by-role.tsv"
  psql_super -c "SELECT r.rolname, s.calls, round(s.total_exec_time::numeric,1), round(s.mean_exec_time::numeric,3), left(regexp_replace(s.query,'\s+',' ','g'),140) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid WHERE r.rolname LIKE 'nsdemo%' ORDER BY s.total_exec_time DESC LIMIT 25" > "$1-pg-top.tsv"
  psql_super -c "SELECT usename, state, count(*) FROM pg_stat_activity WHERE datname='nightscout_compose_test' GROUP BY 1,2 ORDER BY 1,2" > "$1-pg-conns.tsv"
}
pg_reset() { psql_super -c 'SELECT pg_stat_statements_reset()' >/dev/null; }
sampler_start() { "$base/probes/sample.sh" "$project" "$dir/env" "$mt/compose.yaml" "$base/compose.bench.yaml" "$1" & echo $! > "$1/.sampler"; }
sampler_stop() { kill "$(cat "$1/.sampler")" 2>/dev/null || true; rm -f "$1/.sampler"; }

case "$cmd" in
  deploy)
    [ -e "$dir" ] && { echo "exists: $dir" >&2; exit 1; }
    mkdir -p "$dir"; chmod 700 "$dir"; echo "$port" > "$dir/port"
    [ -e "$mt/.env" ] && { echo "$mt/.env exists" >&2; exit 1; }
    host_label "$dir/host-deploy.txt"
    if [ -f "$mt/.overlay.json" ]; then
      # Overlay made by nightscout-deploy tools/compose-overlay.sh (or by hand, same marker): prepare.js
      # checks core HEAD for every other input and deploy/multitenant against the marker's deploy commit.
      [ "$(node -p 'require(process.argv[1]).deployCommit' "$mt/.overlay.json")" = "$CAP_DEPLOY_COMMIT" ] || { echo "overlay marker is not CAP_DEPLOY_COMMIT" >&2; exit 1; }
      (cd "$mt" && node prepare.js --state "$dir/state" --port "$port") > "$dir/prepare.txt"
      echo "source $(git -C "$CAP_CORE" rev-parse HEAD) deploy $CAP_DEPLOY_COMMIT" >> "$dir/prepare.txt"
    else
      node "$here/prepare-overlay.js" "$CAP_CORE" "$CAP_DEPLOY" "$CAP_DEPLOY_COMMIT" --state "$dir/state" --port "$port" > "$dir/prepare.txt"
    fi
    mv "$mt/.env" "$dir/env"
    printf 'NS_DEMO_IMAGE=%s\nNS_DEMO_TENANTS=%s\nNS_BENCH_OVERLAY=%s\n' "$CAP_IMAGE" "$N" "$CAP_WORK/overlay" >> "$dir/env"
    # Role config bound (core MULTITENANT_CONFIG_MAX_BYTES through the deploy tree's NS_BOOTSTRAP_CONFIG_MAX_BYTES).
    [ -n "${CAP_CONFIG_MAX_BYTES:-}" ] && printf 'NS_BOOTSTRAP_CONFIG_MAX_BYTES=%s\n' "$CAP_CONFIG_MAX_BYTES" >> "$dir/env"
    # Realtime socket cap per tenant (deploy d1c7aca+: maxSockets = max(100, N x this); deploy default 2).
    # CAP_SOCKET_CAP_PER, or the file $CAP_WORK/socket-cap-per (read at each deploy, so a running campaign picks it up).
    : "${CAP_SOCKET_CAP_PER:=$(cat "$CAP_WORK/socket-cap-per" 2>/dev/null || true)}"
    [ -n "${CAP_SOCKET_CAP_PER:-}" ] && printf 'NS_DEMO_SOCKETS_PER_TENANT=%s\n' "$CAP_SOCKET_CAP_PER" >> "$dir/env"
    rev=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$CAP_IMAGE")
    [ "$rev" = "$(git -C "$CAP_CORE" rev-parse HEAD)" ] || { echo "image revision $rev does not match core HEAD" >&2; exit 1; }
    drev=$(docker image inspect --format '{{index .Config.Labels "org.nightscout.deploy.revision"}}' "$CAP_IMAGE")
    [ "$drev" = "$CAP_DEPLOY_COMMIT" ] || { echo "image deploy revision $drev does not match CAP_DEPLOY_COMMIT" >&2; exit 1; }
    t0=$(date +%s.%N)
    compose up -d --wait postgres vault >/dev/null 2>&1
    psql_super -c 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements' >/dev/null
    compose --profile ops run --rm bootstrap > "$dir/bootstrap.log" 2>&1 || { echo "bootstrap failed" >&2; tail -3 "$dir/bootstrap.log" >&2; exit 1; }
    t1=$(date +%s.%N)
    node -e 'const t=require(process.argv[1]).tenants.map(({id,host,dataToken})=>({id,host,token:dataToken}));require("fs").writeFileSync(process.argv[2],JSON.stringify(t),{mode:0o600});' \
      "$dir/state/ops/tenants.json" "$dir/tenants.private.json"
    compose up -d --no-deps --wait ui nginx > "$dir/edge-up.log" 2>&1 || {
      echo "ui/nginx start failed" >&2; tail -3 "$dir/edge-up.log" >&2
      for s in ui nginx; do echo "$s: $(compose logs --no-color "$s" 2>&1 | tail -2 | tr '\n' ' ')" >&2; done; exit 1; }
    pg_reset
    echo "$(cgroups)" > "$dir/startup-cgroups-before.json"
    node "$here/startup.js" --compose "$(spec)" --base "http://127.0.0.1:$port" --tenants "$dir/tenants.private.json" \
      --start api,realtime,evaluator,tenant-admin --timeout 1200 --out "$dir/startup.json"
    echo "$(cgroups)" > "$dir/startup-cgroups-after.json"
    pg_phase "$dir/startup"
    maxsock=$(node -p 'require(process.argv[1]).maxSockets' "$dir/state/realtime/config.json" 2>/dev/null || echo null)
    printf '{"tenants":%s,"port":%s,"image":"%s","bootstrapSeconds":%.1f,"realtimeMaxSockets":%s,"socketCapPerTenant":"%s","configMaxBytes":"%s"}\n' "$N" "$port" "$CAP_IMAGE" "$(echo "$t1 - $t0" | bc)" "$maxsock" "${CAP_SOCKET_CAP_PER:-default 2}" "${CAP_CONFIG_MAX_BYTES:-default}" > "$dir/deploy.json"
    cat "$dir/deploy.json"; node -e 'const s=require(process.argv[1]);console.log(JSON.stringify(s.summary))' "$dir/startup.json"
    ;;
  idle)
    secs=$1; out="$dir/idle"; mkdir -p "$out"; host_label "$out/host-before.txt"
    sampler_start "$out"; pg_reset; cgroups > "$out/cgroups-before.json"
    sleep "$secs"
    cgroups > "$out/cgroups-after.json"; pg_phase "$out/idle"; sampler_stop "$out"; host_label "$out/host-after.txt"
    echo "idle $secs s done"
    ;;
  load)
    secs=$1; out="$dir/load"; mkdir -p "$out"; host_label "$out/host-before.txt"
    runid="cap-$label-n$N-$(date +%s)"; echo "$runid" > "$out/runid"
    sampler_start "$out"; pg_reset; cgroups > "$out/cgroups-before.json"
    # Socket probe: opens the sockets, then runs the window with probe writes, then the full restart.
    NODE_PATH="${CAP_NODE_PATH:?core node_modules}" node "$here/probe.js" --base "http://127.0.0.1:$port" --tenants "$dir/tenants.private.json" \
      --compose "$(spec)" --runid "$runid" --per "${CAP_SOCKETS_PER:-2}" --open "${CAP_OPEN_MS:-5}" --window "$secs" \
      --probeEvery "${CAP_PROBE_MS:-3000}" --restart 1 --evalTimeout "${CAP_EVAL_TIMEOUT:-900}" --out "$out/probe.json" \
      --signal "$out/.window" > "$out/probe.log" 2>&1 &
    probe=$!
    # k6 starts when the probe's sockets are primed (the probe touches .window), and runs the window.
    for i in $(seq 1 1200); do [ -f "$out/.window" ] && break; kill -0 $probe 2>/dev/null || break; sleep 1; done
    stamp "window start" >> "$out/phases.txt"
    # Load generators on the same host (background for the record): k6 container and probe process CPU every 5 s.
    ( echo -e "t\tk6_cpu_pct\tk6_mem\tprobe_cpu_pct\tprobe_rss_kb" > "$out/loadgen.tsv"
      while kill -0 $probe 2>/dev/null; do
        k=$(docker stats --no-stream --format '{{.CPUPerc}}\t{{.MemUsage}}' "$project-k6" 2>/dev/null || true)
        p=$(ps -o %cpu=,rss= -p $probe 2>/dev/null | awk '{print $1"\t"$2}')
        echo -e "$(date +%s.%N)\t${k:-\t}\t${p:-\t}" >> "$out/loadgen.tsv"; sleep 5; done ) &
    lg=$!
    if [ "${CAP_NO_K6:-}" = 1 ]; then echo "k6 not run (CAP_NO_K6=1): sockets-only window of $secs s" > "$out/k6.log"; sleep "$secs"; else
    docker run --rm --name "$project-k6" --network host -u "$(id -u):$(id -g)" -v "$here/k6:/scripts:ro" -v "$out:/out" -v "$dir/tenants.private.json:/tenants.private.json:ro" \
      -e BASE_URL="http://127.0.0.1:$port" -e TENANTS_FILE=/tenants.private.json -e RUN_ID="$runid" -e RUN_START="$(( $(date +%s) * 1000 - 86400000 ))" \
      -e DURATION="$secs" -e ACCEL=1 -e HOT_FACTOR=1 \
      "$K6_IMAGE" run --quiet --summary-export /out/k6-summary.json /scripts/workload.js > "$out/k6.log" 2>&1 || echo "k6 exit $?" >> "$out/k6.log"
    fi
    stamp "window end" >> "$out/phases.txt"
    cgroups > "$out/cgroups-after.json"; pg_phase "$out/load"
    pg_reset; touch "$out/.restart"
    wait $probe || echo "probe exit $?" >> "$out/probe.log"
    kill $lg 2>/dev/null || true
    stamp "restart phase end" >> "$out/phases.txt"
    pg_phase "$out/restart"; sampler_stop "$out"
    for s in api realtime evaluator tenant-admin; do compose logs --no-color --timestamps "$s" > "$out/$s.log" 2>&1 || true; done
    # Realtime's /health after the restart phase (the only role with an HTTP /health); the other roles'
    # alert codes come from their logs (summarize.js) and the api/realtime DIAG instruments.
    compose exec -T realtime node -e 'fetch("http://127.0.0.1:1339/health").then(async r=>{const h=await r.json();const c={};for(const a of h.alerts||[]){const k=a.code+(a.cause?":"+a.cause:"");c[k]=(c[k]||0)+1;}delete h.alerts;delete h.tenants;console.log(JSON.stringify({status:r.status,alertCauses:c,...h}));}).catch(e=>console.log(JSON.stringify({error:String(e.message)})))' > "$out/realtime-health-after.json" 2>&1 || true
    node "$here/startup.js" --fromLogs "$out" --compose "$(spec)" --since "$(cat "$out/.restart-at" 2>/dev/null || echo 0)" --out "$out/restart-startup.json" || true
    host_label "$out/host-after.txt"
    echo "load $secs s + restart done"
    ;;
  oracle)
    out="$dir/load"
    "$base/oracle/oracle.sh" "$project" "$dir/env" "$mt/compose.yaml" "$base/compose.bench.yaml" "$out" > "$out/oracle.txt" || true
    tail -1 "$out/oracle.txt"
    ;;
  control)
    "$base/oracle/control.sh" "$project" "$dir/env" "$mt/compose.yaml" "$base/compose.bench.yaml" "$dir/load" | tee "$dir/load/oracle-control.txt" | tail -4
    ;;
  teardown)
    [ -f "$dir/env" ] && compose --profile ops down -v --remove-orphans >/dev/null 2>&1
    rm -rf "$dir/state" "$dir/tenants.private.json"
    ;;
  *) echo "unknown $cmd" >&2; exit 64 ;;
esac
