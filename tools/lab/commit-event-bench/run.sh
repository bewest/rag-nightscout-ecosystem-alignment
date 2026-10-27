#!/usr/bin/env bash
# commit-event bench: every axis, in order, against one lab mongod.
#
#   tools/lab/commit-event-bench/run.sh up        mongo:8.0.29 single-node replica set on 127.0.0.1:$CEB_PORT
#   tools/lab/commit-event-bench/run.sh all       axes a-d plus their controls, results/ + logs
#   tools/lab/commit-event-bench/run.sh down      remove the container
#
# Trees (each needs its own `npm ci`; never share node_modules):
#   CEB_BASE   base tree (dev 9668b179)
#   CEB_NOOP   base + one comment line (no-op control)
#   CEB_PROTO  option 1 prototype
# The API secret is generated per run into the environment; nothing secret is written.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
W=${CEB_WORK:-/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work}
BASE=${CEB_BASE:-$W/crm-devent-base}
NOOP=${CEB_NOOP:-$W/crm-devent-noop}
PROTO=${CEB_PROTO:-$W/crm-devent-proto}
PORT=${CEB_PORT:-27601}
NAME=${CEB_CONTAINER:-devent-mongo-$PORT}
MONGO=mongodb://127.0.0.1:$PORT
OUT=$HERE/results
state () { docker inspect -f '{{.Name}} {{.State.Status}} started={{.State.StartedAt}} restarts={{.RestartCount}}' "$NAME"; }
filter () { grep -v 'SECURITY: failed-authentication\|For the Basal plugin' || true; }

case "${1:-}" in
  up)
    docker run -d --name "$NAME" --ulimit nofile=64000:64000 -p 127.0.0.1:$PORT:27017 mongo:8.0.29 --replSet rs0 >/dev/null
    sleep 5
    docker exec "$NAME" mongosh --quiet --eval 'rs.initiate({_id:"rs0",members:[{_id:0,host:"127.0.0.1:27017"}]}).ok'
    sleep 3; docker exec "$NAME" mongosh --quiet --eval 'db.version()' ;;
  down) docker rm -f "$NAME" ;;
  all)
    mkdir -p "$OUT"
    node --version
    docker exec "$NAME" mongosh --quiet --eval 'db.version()'
    run () { local name=$1; shift; { state; node "$@" 2>&1 | filter; state; } > "$OUT/$name.log"; }
    run inventory-base   "$HERE/inventory.js" "$BASE" "$MONGO"
    run inventory-proto  "$HERE/inventory.js" "$PROTO" "$MONGO"
    run latency   "$HERE/bench.js" --mongo "$MONGO" --n 200 --nbulk 200 --out "$OUT/latency.json" \
      --arm base=$BASE:count --arm base2=$BASE:count --arm noop=$NOOP:count --arm proto=$PROTO:count --arm proto0=$PROTO:none
    run payload   "$HERE/payload.js" --mongo "$MONGO" --reps 20 --out "$OUT/payload.json" --arm base=$BASE --arm proto=$PROTO
    run changefeed "$HERE/changefeed.js" --mongo "$MONGO" --reps 5 --out "$OUT/changefeed.json" --arm base=$BASE --arm proto=$PROTO
    run concurrent "$HERE/concurrent.js" --mongo "$MONGO" --levels 1,2,4 --seconds 20 --rounds 2 --out "$OUT/concurrent.json" --arm base=$BASE --arm proto=$PROTO
    run concurrent-pruner "$HERE/concurrent.js" --mongo "$MONGO" --levels 1,4 --seconds 20 --rounds 2 --pruner --out "$OUT/concurrent-pruner.json" --arm base=$BASE --arm proto=$PROTO
    run concurrent-break "$HERE/concurrent.js" --mongo "$MONGO" --levels 2 --seconds 10 --rounds 1 --break swap-writer --out "$OUT/concurrent-break.json" --arm proto=$PROTO
    ;;
  *) sed -n 2,14p "$0"; exit 2 ;;
esac
