#!/usr/bin/env bash
# After start.sh <N> <label> with KEEP=1: restart the api and the evaluator of that
# deployment and measure (1) time to the first served request for chosen tenants,
# polling every 250 ms, and (2) per-tenant time to the first evaluator operation.
#   restart.sh <N> <label>     Env: CORE, WORK
set -uo pipefail
N=$1 label=$2
mt="$CORE/deploy/multitenant"; bench=/home/bewest/src/rag-nightscout-ecosystem-alignment/tools/mt-bench/compose-baseline
project="ns-pdb-$label"; dir="$WORK/$label"; port=$((19400 + N % 1000))
compose() { docker compose -p "$project" --env-file "$dir/env" -f "$mt/compose.yaml" -f "$bench/compose.bench.yaml" -f "$dir/override.yaml" "$@"; }
appsql() { compose exec -T postgres psql -X -At -F $'\t' -U postgres -d nightscout_compose_test "$@"; }
compose up -d --no-build --pull never --no-deps --wait ui nginx >/dev/null 2>&1 || { echo "nginx/ui did not start" >&2; exit 1; }
node -e '
  const t=require(process.argv[1]).tenants; const pick=[0, Math.floor(t.length/2), t.length-1].map(i=>({index:i,host:t[i].host,token:t[i].dataToken}));
  require("fs").writeFileSync(process.argv[2],JSON.stringify(pick),{mode:0o600});' "$dir/state/ops/tenants.json" "$dir/pick.private.json"
probe() { # tenant index from pick file -> one line: elapsed_ms, statuses seen
  node -e '
    const http=require("node:http"); const [file,port,which,t0]=process.argv.slice(1); const p=require(file)[which];
    const get=()=>new Promise(resolve=>{ const req=http.get({host:"127.0.0.1",port,path:"/api/v1/entries.json?count=1&token="+encodeURIComponent(p.token),headers:{host:p.host},timeout:5000},res=>{res.resume();res.on("end",()=>resolve([res.statusCode,res.headers["retry-after"]||""]));}); req.on("timeout",()=>req.destroy()); req.on("error",()=>resolve([0,""])); });
    (async()=>{ const seen={}; for(;;){ const at=Date.now(); const [status,ra]=await get(); const key=status+(ra?"/ra="+ra:"");
      seen[key]=(seen[key]||0)+1;
      if(status===200){ console.log(JSON.stringify({index:p.index,firstServedMs:at-Number(t0),statuses:seen})); return; }
      if(at-Number(t0)>900000){ console.log(JSON.stringify({index:p.index,firstServedMs:null,statuses:seen})); return; }
      await new Promise(r=>setTimeout(r,250)); } })();' "$dir/pick.private.json" "$port" "$1" "$2"
}
# (1) api restart
t0=$(date +%s%3N)
compose restart api >/dev/null 2>&1 &
sleep 0.5
for i in 0 1 2; do probe $i "$t0" & done; wait
compose logs --no-color --since 30m api 2>/dev/null | grep -c 'Tenant readiness alert' | sed 's/^/api_alert_lines=/'
compose logs --no-color --since 30m api 2>/dev/null | grep 'Tenant readiness alert' | awk '{print $(NF-1)}' | sort | uniq -c | sed 's/^/api_alert_codes /'
# (2) SUPERSEDED by eval-gap.js: joining pg_stat_activity drops operations owned by pooled
#     backends that have since closed (10 s idle timeout), so this undercounts.
# (2) evaluator restart: per-tenant time to the second operation of the new evaluator
# backends (the first is its startup warm in readiness 'all'; the second its first cycle)
t1=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ); e0=$(date +%s%3N)
compose restart evaluator >/dev/null 2>&1
deadline=$(( $(date +%s) + 1500 )); : > "$dir/eval-first.tsv"
while [ "$(date +%s)" -lt "$deadline" ]; do
  now=$(date +%s%3N)
  appsql -c "SELECT o.tenant_id FROM nsdemo_control.tenant_lifecycle_operations o JOIN pg_stat_activity a ON a.pid=o.owner_pid AND a.backend_start=o.owner_birth WHERE a.usename='nsdemo_lifetime_evaluator' AND o.owner_birth > '$t1' GROUP BY o.tenant_id HAVING count(*) >= 2" 2>/dev/null \
    | while read -r t; do grep -q "^$t" "$dir/eval-first.tsv" || printf '%s\t%s\n' "$t" "$((now - e0))" >> "$dir/eval-first.tsv"; done
  [ "$(wc -l < "$dir/eval-first.tsv")" -ge "$N" ] && break
  sleep 1
done
awk -F'\t' -v n="$N" '{print $2}' "$dir/eval-first.tsv" | sort -n | awk -v n="$N" '{a[NR]=$1} END {printf "evaluator_first_op: tenants_seen=%d of %d p50_ms=%s p95_ms=%s max_ms=%s\n", NR, n, a[int(NR*0.5)+0], a[int(NR*0.95)+0], a[NR]}'
compose logs --no-color --since 30m evaluator 2>/dev/null | grep -c 'Tenant readiness alert' | sed 's/^/evaluator_alert_lines=/'
