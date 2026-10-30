#!/usr/bin/env bash
# commit-event bench: every axis, in order, against one lab mongod.
#
#   tools/lab/commit-event-bench/run.sh up        mongo:8.0.29 single-node replica set on 127.0.0.1:$CEB_PORT
#   tools/lab/commit-event-bench/run.sh all       round 1: axes a-d, base vs pre-read, results/
#   tools/lab/commit-event-bench/run.sh round2    round 2: base, base2, noop, pre, post, results/round2/
#   tools/lab/commit-event-bench/run.sh round3    round 3: since-watermark arm, results/round3/
#   tools/lab/commit-event-bench/run.sh down      remove the container
#
# Trees (each needs its own `npm ci`; never share node_modules):
#   CEB_BASE   base tree (dev 9668b179)
#   CEB_NOOP   base + one comment line (no-op control)
#   CEB_PROTO  option 1 prototype, pre-read variant (8a396715)
#   CEB_POST   option 1 prototype, post-write variant (proto/d-event-post-write)
#   CEB_SINCE  since-watermark variant (proto/d-event-since-watermark), round 3
#   CEB_SINCE_<arm>=late,overlap=N  that arm's since-watermark knobs (round 3)
# The API secret is generated per run into the environment; nothing secret is written.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
W=${CEB_WORK:-/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work}
BASE=${CEB_BASE:-$W/crm-devent-base}
NOOP=${CEB_NOOP:-$W/crm-devent-noop}
PROTO=${CEB_PROTO:-$W/crm-devent-proto}
POST=${CEB_POST:-$W/crm-devent-post}
SINCE=${CEB_SINCE:-$W/crm-devent-since}
CAPPED=${CEB_CAPPED:-$W/crm-devent-capped}
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
  round2)
    R=$OUT/round2; mkdir -p "$R"
    node --version
    docker exec "$NAME" mongosh --quiet --eval 'db.version()'
    run () { local name=$1; shift; { state; node "$@" 2>&1 | filter; state; } > "$R/$name.log"; }
    run inventory-post "$HERE/inventory.js" "$POST" "$MONGO"
    run latency   "$HERE/bench.js" --mongo "$MONGO" --n 200 --nbulk 100 --nbig 10 --out "$R/latency.json" \
      --arm base=$BASE:count --arm base2=$BASE:count --arm noop=$NOOP:count --arm pre=$PROTO:count --arm post=$POST:count
    run payload   "$HERE/payload.js" --mongo "$MONGO" --reps 20 --out "$R/payload.json" --arm base=$BASE --arm pre=$PROTO --arm post=$POST
    run misname   "$HERE/misname.js" --mongo "$MONGO" --reps 5 --out "$R/misname.json" --arm pre=$PROTO --arm post=$POST
    run misname-break "$HERE/misname.js" --mongo "$MONGO" --reps 5 --break counts-from-records --out "$R/misname-break.json" --arm pre=$PROTO --arm post=$POST
    run changefeed "$HERE/changefeed.js" --mongo "$MONGO" --reps 5 --out "$R/changefeed.json" --arm base=$BASE --arm pre=$PROTO --arm post=$POST
    A5="--arm base=$BASE --arm base2=$BASE --arm noop=$NOOP --arm pre=$PROTO --arm post=$POST"
    run concurrent "$HERE/concurrent.js" --mongo "$MONGO" --levels 1,2,4 --seconds 20 --rounds 2 --out "$R/concurrent.json" $A5
    run concurrent-pruner "$HERE/concurrent.js" --mongo "$MONGO" --levels 1,4 --seconds 20 --rounds 2 --pruner --out "$R/concurrent-pruner.json" $A5
    run concurrent-break "$HERE/concurrent.js" --mongo "$MONGO" --levels 2 --seconds 10 --rounds 1 --break swap-writer --out "$R/concurrent-break.json" --arm post=$POST
    ;;
  round3)
    # since: overlap 5 (the arm); since0: overlap 0; late0/late5: the watermark
    # one write late (the call's last stamp), overlap 0 and 5 (break-it controls)
    export CEB_SINCE_since0=overlap=0 CEB_SINCE_late0=late,overlap=0 CEB_SINCE_late5=late,overlap=5
    R=$OUT/round3; mkdir -p "$R"
    node --version
    docker exec "$NAME" mongosh --quiet --eval 'db.version()'
    run () { local name=$1; shift; { state; node "$@" 2>&1 | filter; state; } > "$R/$name.log"; }
    run inventory-since "$HERE/inventory.js" "$SINCE" "$MONGO"
    run reads     "$HERE/reads.js" --mongo "$MONGO" --reps 10 --out "$R/reads.json" \
      --arm base=$BASE --arm pre=$PROTO --arm post=$POST --arm capped=$CAPPED --arm since=$SINCE
    run misname   "$HERE/misname.js" --mongo "$MONGO" --reps 5 --out "$R/misname.json" \
      --arm pre=$PROTO --arm post=$POST --arm since=$SINCE --arm since0=$SINCE --arm late0=$SINCE --arm late5=$SINCE
    run misname-break "$HERE/misname.js" --mongo "$MONGO" --reps 5 --break counts-from-records --out "$R/misname-break.json" --arm since=$SINCE
    run changefeed "$HERE/changefeed.js" --mongo "$MONGO" --reps 5 --out "$R/changefeed.json" \
      --arm base=$BASE --arm pre=$PROTO --arm post=$POST --arm since=$SINCE --arm since0=$SINCE --arm late0=$SINCE --arm late5=$SINCE
    ;&
  round3b)
    # the steps after the change feed: the first round-3 run crashed in a
    # combined singles+backfill latency run (see the README), so these ran again
    export CEB_SINCE_since0=overlap=0 CEB_SINCE_late0=late,overlap=0 CEB_SINCE_late5=late,overlap=5
    R=$OUT/round3; mkdir -p "$R"
    run () { local name=$1; shift; { state; node "$@" 2>&1 | filter; state; } > "$R/$name.log"; }
    SINGLES=$(node -e "console.log(Object.keys(require('$HERE/lib').SHAPES).join(','))")
    BULKS=$(node -e "console.log(Object.keys(require('$HERE/lib').BULK).join(','))")
    run latency-singles "$HERE/bench.js" --mongo "$MONGO" --n 200 --only "$SINGLES" --out "$R/latency-singles.json" \
      --arm base=$BASE:count --arm base2=$BASE:count --arm noop=$NOOP:count --arm pre=$PROTO:count --arm post=$POST:count --arm since=$SINCE:count
    run latency-bulk "$HERE/bench.js" --mongo "$MONGO" --nbulk 50 --nbig 8 --only "$BULKS" --out "$R/latency-bulk.json" \
      --arm base=$BASE:count --arm base2=$BASE:count --arm pre=$PROTO:count --arm post=$POST:count --arm since=$SINCE:count
    run payload   "$HERE/payload.js" --mongo "$MONGO" --reps 20 --out "$R/payload.json" --arm base=$BASE --arm pre=$PROTO --arm post=$POST --arm since=$SINCE
    A5="--arm base=$BASE --arm base2=$BASE --arm pre=$PROTO --arm post=$POST --arm since=$SINCE"
    run concurrent "$HERE/concurrent.js" --mongo "$MONGO" --levels 1,2,4 --seconds 20 --rounds 2 --out "$R/concurrent.json" $A5
    run concurrent-pruner "$HERE/concurrent.js" --mongo "$MONGO" --levels 1,4 --seconds 20 --rounds 2 --pruner --out "$R/concurrent-pruner.json" $A5
    run concurrent-break "$HERE/concurrent.js" --mongo "$MONGO" --levels 2 --seconds 10 --rounds 1 --break swap-writer --out "$R/concurrent-break.json" --arm since=$SINCE
    # identity reads counted in each arm's process (readtap.js); the profiler-only
    # reads run at the start of round3 lost the bulk calls' reads
    run reads     "$HERE/reads.js" --mongo "$MONGO" --reps 10 --out "$R/reads.json" \
      --arm base=$BASE --arm pre=$PROTO --arm post=$POST --arm capped=$CAPPED --arm since=$SINCE
    ;;
  *) sed -n 2,16p "$0"; exit 2 ;;
esac
