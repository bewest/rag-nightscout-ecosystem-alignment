#!/bin/bash
# lane.sh PORT OUTDIR WORKTREE_PREFIX HARNESS COMMIT... : run the write-contract matrix on each
# commit's worktree (WORKTREE_PREFIX<commit>, `npm ci` done) in turn, against the MongoDB container
# compat-m7-PORT listening on 127.0.0.1:PORT. Writes OUTDIR/<commit>.json and .log, and appends
# "<commit> exit <code>" to OUTDIR/lane-PORT.done. Stops (exit 3) if the container is not running.
# Node is chosen with `n` (NODE_VERSION, default 22.23.4, the version of the 2026-10-31 measurement).
# HARNESS is tools/qc/write-contract-matrix.js, with tools/qc/compat/v15.0.9-harness-guard.diff
# applied when any tree predates lib/server/storage-reads (v15.0.9); see tools/qc/compat/README.md.
set -u
port=$1; out=$2; prefix=$3; harness=$4; shift 4
node_v=${NODE_VERSION:-22.23.4}
mkdir -p "$out"
for c in "$@"; do
  if [ "$(docker inspect -f '{{.State.Running}}' compat-m7-$port)" != true ]; then echo "container $port not running before $c" >> "$out/lane-$port.err"; exit 3; fi
  WC_WORKTREE=$prefix$c WC_MONGO=mongodb://127.0.0.1:$port n exec "$node_v" node "$harness" ${MATRIX_ARGS:-} --out "$out/$c.json" > "$out/$c.log" 2>&1
  echo "$c exit $?" >> "$out/lane-$port.done"
done
