#!/usr/bin/env bash
# Realtime perf lane RT driver over the one-host Compose reference (compose-baseline harness pieces).
#   run.sh overlay  <label> <core-worktree> <commit>         N-tenant bootstrap overlay, maxSockets raised
#   run.sh deploy   <label> <core-worktree> <image> <N>      prepare + bootstrap + up (project ns-prt-<label>-n<N>)
#   run.sh measure  <label> <core-worktree> <N> <name> [measure.js args...]
#   run.sh teardown <label> <core-worktree> <N>
# Environment: NS_PRT_WORK (private, outside any checkout), NS_DEPLOY (nightscout-deploy checkout),
#   NS_PRT_EXTRA_COMPOSE (optional extra Compose file, e.g. a diagnostic mount; used by deploy and measure).
# Containers are named ns-prt-*; teardown removes them and their volumes.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); bench="$here/../compose-baseline"
: "${NS_PRT_WORK:?private work dir}"
cmd=$1 label=$2 core=$3; shift 3
mt="$core/deploy/multitenant"
overlay="$NS_PRT_WORK/overlay-${label%2}"
case "$cmd" in
  overlay)
    commit=$1
    "$bench/make-overlay.sh" "$core" "$commit" "${NS_DEPLOY:?nightscout-deploy}" 085d88a 4e5a1051 "$overlay" >/dev/null
    # 20 sockets per tenant at 50 tenants exceeds the reference's 100-socket ceiling.
    sed -i 's/maxSockets:100\b/maxSockets:25000/' "$overlay/config.js"
    grep -c 'maxSockets:25000' "$overlay/config.js"
    ;;
  deploy)
    image=$1 N=$2
    case "$label" in base) port=$((20000 + N));; int) port=$((24000 + N));; *) port=$((22000 + N));; esac
    project="ns-prt-$label-n$N"; dir="$NS_PRT_WORK/$label-n$N"
    [ -e "$dir" ] && { echo "exists: $dir" >&2; exit 1; }
    mkdir -p "$dir"; [ -e "$mt/.env" ] && { echo "$mt/.env exists" >&2; exit 1; }
    (cd "$mt" && node prepare.js --state "$dir/state" --port "$port" >/dev/null)
    mv "$mt/.env" "$dir/env"
    printf 'NS_DEMO_IMAGE=%s\nNS_DEMO_TENANTS=%s\nNS_BENCH_OVERLAY=%s\n' "$image" "$N" "$overlay" >> "$dir/env"
    compose() { docker compose -p "$project" --env-file "$dir/env" -f "$mt/compose.yaml" -f "$bench/compose.bench.yaml" ${NS_PRT_EXTRA_COMPOSE:+-f "$NS_PRT_EXTRA_COMPOSE"} "$@"; }
    t0=$(date +%s.%N)
    compose up -d --wait postgres vault >/dev/null 2>&1
    compose --profile ops run --rm bootstrap >/dev/null
    t1=$(date +%s.%N)
    compose up -d --no-build --pull never --wait --wait-timeout 900 api realtime evaluator tenant-admin ui nginx >/dev/null 2>&1 || echo "up: not all healthy" >&2
    t2=$(date +%s.%N)
    compose exec -T postgres psql -X -q -U postgres -d postgres -c 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements' >/dev/null
    node -e 'const t=require(process.argv[1]).tenants.map(({id,host,dataToken})=>({id,host,token:dataToken}));require("fs").writeFileSync(process.argv[2],JSON.stringify(t),{mode:0o600});' \
      "$dir/state/ops/tenants.json" "$dir/tenants.private.json"
    printf '{"label":"%s","tenants":%s,"port":%s,"image":"%s","bootstrapSeconds":%.1f,"startSeconds":%.1f}\n' "$label" "$N" "$port" "$image" \
      "$(echo "$t1 - $t0" | bc)" "$(echo "$t2 - $t1" | bc)" | tee "$dir/deploy.json"
    compose ps --format '{{.Service}} {{.State}} {{.Health}}'
    ;;
  measure)
    N=$1 name=$2; shift 2
    project="ns-prt-$label-n$N"; dir="$NS_PRT_WORK/$label-n$N"
    port=$(node -e 'console.log(require(process.argv[1]).port)' "$dir/deploy.json")
    NODE_PATH="$core/node_modules" node "$here/measure.js" --base "http://127.0.0.1:$port" --tenants "$dir/tenants.private.json" \
      --compose "$project|$dir/env|$mt/compose.yaml|$bench/compose.bench.yaml${NS_PRT_EXTRA_COMPOSE:+|$NS_PRT_EXTRA_COMPOSE}" --out "$dir/$name.json" "$@"
    ;;
  teardown)
    N=$1; project="ns-prt-$label-n$N"; dir="$NS_PRT_WORK/$label-n$N"
    [ -f "$dir/env" ] && docker compose -p "$project" --env-file "$dir/env" -f "$mt/compose.yaml" -f "$bench/compose.bench.yaml" --profile ops down -v --remove-orphans >/dev/null 2>&1
    rm -rf "$dir/state" "$dir/tenants.private.json"
    ;;
  *) echo "unknown $cmd" >&2; exit 64 ;;
esac
