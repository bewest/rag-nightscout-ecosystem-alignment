#!/usr/bin/env bash
# Recreate the api with NS_TENANT_READINESS=all (override.yaml) and time the first
# served request for the pick tenants, as restart.sh part (1).
set -uo pipefail
N=$1 label=$2
mt="$CORE/deploy/multitenant"; bench=/home/bewest/src/rag-nightscout-ecosystem-alignment/tools/mt-bench/compose-baseline
project="ns-pdb-$label"; dir="$WORK/$label"; port=$((19400 + N % 1000))
compose() { docker compose -p "$project" --env-file "$dir/env" -f "$mt/compose.yaml" -f "$bench/compose.bench.yaml" -f "$dir/override.yaml" "$@"; }
eval "$(sed -n '/^probe() {/,/^}/p' "$(dirname "$0")/restart.sh")"
t0=$(date +%s%3N)
compose up -d --no-deps --force-recreate --no-build --pull never api >/dev/null 2>&1 &
for i in 0 1 2; do probe $i "$t0" & done; wait
docker exec "$(compose ps -q api)" printenv NS_TENANT_READINESS | sed 's/^/api NS_TENANT_READINESS=/'
