#!/usr/bin/env bash
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
export OVERLAY=/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/bench-20261110/overlay-4e5a1051 WORK=/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/perf-db-20261110 IDLE_S=10
bench=/home/bewest/src/rag-nightscout-ecosystem-alignment/tools/mt-bench/compose-baseline
for run in "before-20261110 540d3998 100" "20261110 86617644 100" "20261110 86617644 1000" "before-20261110 540d3998 1000"; do
  set -- $run
  export CORE=/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-perf-db-$1 IMAGE=ns-pdb-perf:$2; N=$3; label=d-$2-n$N
  echo "=== $label $(date +%T)"
  KEEP=1 "$here/start.sh" $N $label 2>&1 | grep '^{'
  case $2 in 540d3998) export DRAIN_WAIT_S=$(( N / 4 + 30 ));; *) export DRAIN_WAIT_S=900;; esac
  for mode in serve all serve; do "$here/recreate.sh" $N $label $mode 2>&1; done
  dir=$WORK/$label
  docker compose -p ns-pdb-$label --env-file $dir/env -f $CORE/deploy/multitenant/compose.yaml -f $bench/compose.bench.yaml -f $dir/override.yaml --profile ops down -v --remove-orphans >/dev/null 2>&1
  rm -rf $dir/state $dir/pick.private.json
done
echo "=== done $(date +%T)"
