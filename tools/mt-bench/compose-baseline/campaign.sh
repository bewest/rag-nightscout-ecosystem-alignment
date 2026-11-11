#!/usr/bin/env bash
# The published campaign: for each tenant count, deploy, run the real-cadence workload and the
# 10x-compressed workload, run the oracle control once, tear down. Usage: campaign.sh [N ...]
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
counts=${*:-1 10 50 200}
for n in $counts; do
  echo "== N=$n deploy $(date -u +%T) load $(cut -d' ' -f1 /proc/loadavg)"
  "$here/bench.sh" deploy "$n" > "$NS_BENCH_WORK/deploy-n$n.log" 2>&1 || { echo "deploy N=$n failed"; tail -5 "$NS_BENCH_WORK/deploy-n$n.log"; "$here/bench.sh" teardown "$n" >/dev/null 2>&1; continue; }
  cat "$NS_BENCH_WORK/n$n/deploy.json"
  BENCH_ACCEL=1 BENCH_DURATION=300 PROBE_INTERVAL_MS=5000 "$here/bench.sh" run "$n" real > "$NS_BENCH_WORK/run-n$n-real.log" 2>&1; tail -1 "$NS_BENCH_WORK/run-n$n-real.log"
  BENCH_ACCEL=10 BENCH_DURATION=120 PROBE_INTERVAL_MS=5000 "$here/bench.sh" run "$n" x10 > "$NS_BENCH_WORK/run-n$n-x10.log" 2>&1; tail -1 "$NS_BENCH_WORK/run-n$n-x10.log"
  if [ "$n" = 10 ]; then "$here/bench.sh" control "$n" > "$NS_BENCH_WORK/control-n$n.log" 2>&1; tail -1 "$NS_BENCH_WORK/control-n$n.log"; fi
  "$here/bench.sh" teardown "$n" > /dev/null 2>&1
  echo "== N=$n done $(date -u +%T)"
done
