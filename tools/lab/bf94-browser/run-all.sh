#!/usr/bin/env bash
# run every scenario, with and without history, against one tree. Usage: run-all.sh <label> <tree> <port> <outdir>
set -u
L=$1; D=$2; P=$3; O=$4
: "${NODE_PATH:?set NODE_PATH to a node_modules directory that has playwright}"; export NODE_PATH
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$O/shots"
for h in 0 1; do for s in ${SCENARIOS:-loop-new trio-reupload-new aaps-v3 cancel-trio cancel-aaps-v3 cancel-oref}; do
  node "$HERE/probe.js" --dir "$D" --label "$L" --scenario $s --hist $h --mongo mongodb://127.0.0.1:27941 --port "$P" \
    --out "$O/$L-$s-h$h.json" --shots "$O/shots" --watch ${WATCH:-75} || echo "{\"label\":\"$L\",\"sc\":\"$s\",\"hist\":$h,\"verdict\":\"COULD-NOT-RUN\"}"
done; done
