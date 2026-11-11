#!/usr/bin/env bash
# Recreate the api of a kept deployment (start.sh KEEP=1) with NS_TENANT_READINESS=<mode>
# and measure: time to listener open (container start -> "Listening for role api"),
# time to the first served request for three tenants (first, middle, last; 250 ms probe
# through nginx, which promotes the tenant in serve mode), the api RSS at listener open
# and, in serve mode, after the background warm drains.
#   recreate.sh <N> <label> <serve|all>    Env: CORE, WORK
set -uo pipefail
N=$1 label=$2 mode=$3
mt="$CORE/deploy/multitenant"; bench=/home/bewest/src/rag-nightscout-ecosystem-alignment/tools/mt-bench/compose-baseline
project="ns-pdb-$label"; dir="$WORK/$label"; port=$((19400 + N % 1000))
compose() { docker compose -p "$project" --env-file "$dir/env" -f "$mt/compose.yaml" -f "$bench/compose.bench.yaml" -f "$dir/override.yaml" "$@"; }
eval "$(sed -n '/^probe() {/,/^}/p' "$(dirname "$0")/restart.sh")"
compose up -d --no-build --pull never --no-deps --wait ui nginx >/dev/null 2>&1
[ -f "$dir/pick.private.json" ] || node -e '
  const t=require(process.argv[1]).tenants; const pick=[0, Math.floor(t.length/2), t.length-1].map(i=>({index:i,host:t[i].host,token:t[i].dataToken}));
  require("fs").writeFileSync(process.argv[2],JSON.stringify(pick),{mode:0o600});' "$dir/state/ops/tenants.json" "$dir/pick.private.json"
python3 - "$dir/override.yaml" "$mode" <<'PY'
import sys
p, mode = sys.argv[1], sys.argv[2]
lines = [l for l in open(p).read().split('\n') if 'NS_TENANT_READINESS' not in l]
out = []
for i, l in enumerate(lines):
    out.append(l)
    if l == '  api:':
        pass
    if l.startswith('    healthcheck') and out[-2] == '  api:':
        out.append('    environment: {NS_TENANT_READINESS: "%s"}' % mode)
open(p, 'w').write('\n'.join(out))
PY
echo "mode=$mode loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
# Stop the running api first, so every probe answer comes from the new container;
# times are measured from the new container's creation.
old=$(compose ps -q api 2>/dev/null); compose stop api >/dev/null 2>&1
t0=$(date +%s%3N)
compose up -d --no-deps --force-recreate --no-build --pull never api >/dev/null 2>&1 &
for i in 0 1 2; do probe $i "$t0" & done
api=""; until [ -n "$api" ] && [ "$api" != "$old" ]; do api=$(compose ps -q api 2>/dev/null); sleep 0.2; done
until docker logs "$api" 2>&1 | grep -q 'Listening for role api'; do sleep 0.2; done
docker stats --no-stream --format 'rss_at_listen={{.MemUsage}}' "$api"
if [ "$mode" = serve ]; then
  # Images before 86617644 do not log the drain: bounded wait, labelled.
  deadline=$(( $(date +%s) + ${DRAIN_WAIT_S:-900} )); drained=0
  until [ "$(date +%s)" -ge "$deadline" ]; do docker logs "$api" 2>&1 | grep -q 'Tenant warm drained' && { drained=1; break; }; sleep 0.5; done
  if [ $drained = 1 ]; then docker stats --no-stream --format 'rss_after_warm={{.MemUsage}}' "$api"
  else docker stats --no-stream --format "rss_after_${DRAIN_WAIT_S:-900}s_no_drain_line={{.MemUsage}}" "$api"; fi
fi
wait
started=$(docker inspect --format '{{.State.StartedAt}}' "$api")
listen=$(docker logs -t "$api" 2>&1 | grep 'Listening for role api' | head -1 | cut -d' ' -f1)
drained=$(docker logs -t "$api" 2>&1 | grep 'Tenant warm drained' | head -1)
node -e 'const [s,l]=process.argv.slice(1);console.log("listener_open_ms="+(Date.parse(l)-Date.parse(s)))' "$started" "$listen"
[ -n "$drained" ] && node -e 'const [s,line]=process.argv.slice(1);console.log("warm_drained_ms="+(Date.parse(line.split(" ")[0])-Date.parse(s))+" "+line.split(" ").slice(1).join(" "))' "$started" "$drained"
echo "readiness_alert_lines=$(docker logs "$api" 2>&1 | grep -c 'Tenant readiness alert')"
echo "enabling_feature_lines_before_listen=$(docker logs "$api" 2>&1 | sed '/Listening for role api/q' | grep -c 'enabling feature')"
docker exec "$api" printenv NS_TENANT_READINESS | sed 's/^/api NS_TENANT_READINESS=/'
