#!/usr/bin/env bash
# Cache catch-up lab: every arm and scenario, realistic then heavy cache sizes.
#
#   tools/lab/cache-catchup/run.sh up      mongo:8.0.29 STANDALONE on 127.0.0.1:$CC_PORT (no replica set:
#                                          nothing here needs change streams, and the catch-up must work without one)
#   tools/lab/cache-catchup/run.sh all     results/realistic.{log,json}, results/heavy.{log,json}
#   tools/lab/cache-catchup/run.sh round2  results/round2/{realistic,heavy}.{log,json}: the resolve arm
#                                          (write scoped to the ids read) against dev, flush and ids
#   tools/lab/cache-catchup/run.sh round3  results/round3/{realistic,heavy}.{log,json}: API v3 writes of the
#                                          write-contract Q-A sketch (lab-v3.js, server-v3.js) against #8874
#   tools/lab/cache-catchup/run.sh down
#
# Trees (each needs its own `npm ci`):
#   CC_DEV    dev 991b0654, unmodified (control)
#   CC_PROTO  proto/cache-catchup (CACHE_CATCHUP=flush|ids|watermark; flush is dev's behaviour);
#             round 2: dev 305a6533 and proto/cache-resolve (adds CACHE_CATCHUP=resolve)
#   round 3: CC_PR #8874 7463e76d; CC_UNIFY proto/v3-unify (the break-it arm drops a name in its announce())
# The API secret is generated per run in lab.js and never written. Logs start and end with docker state.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
W=${CC_WORK:-/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work}
DEV=${CC_DEV:-$W/crm-cache-dev}
PROTO=${CC_PROTO:-$W/crm-cache-catchup}
PORT=${CC_PORT:-27621}
NAME=${CC_CONTAINER:-cache-lab-$PORT}
MONGO=mongodb://127.0.0.1:$PORT
OUT=$HERE/results
state () { docker inspect -f '{{.Name}} {{.State.Status}} started={{.State.StartedAt}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}' "$NAME"; }
ARMS="--arm dev=$DEV --arm flush=$PROTO:CACHE_CATCHUP=flush --arm ids=$PROTO:CACHE_CATCHUP=ids
  --arm wm5=$PROTO:CACHE_CATCHUP=watermark,CACHE_CATCHUP_OVERLAP_MS=5
  --arm wm1000=$PROTO:CACHE_CATCHUP=watermark,CACHE_CATCHUP_OVERLAP_MS=1000
  --arm idsbreak=$PROTO:CACHE_CATCHUP=ids,CACHE_CATCHUP_BREAK=drop-last"
case "${1:-}" in
  up) docker run -d --name "$NAME" --ulimit nofile=64000:64000 -p 127.0.0.1:$PORT:27017 mongo:8.0.29 >/dev/null; sleep 5; state ;;
  down) state; docker rm -f "$NAME" ;;
  all)
    mkdir -p "$OUT"
    node --version; docker exec "$NAME" mongosh --quiet --eval 'db.version()'
    for size in realistic heavy; do
      # no pipe: a crashed lab must not leave its output in a pipe's buffer
      { state; node "$HERE/lab.js" --mongo "$MONGO" --reps 10 --size $size --out "$OUT/$size.json" $ARMS 2>&1; echo "exit=$?"; state; } > "$OUT/$size.log" || true
    done ;;
  round2)
    ARMS2="--arm dev=$DEV --arm flush=$PROTO:CACHE_CATCHUP=flush --arm ids=$PROTO:CACHE_CATCHUP=ids
      --arm resolve=$PROTO:CACHE_CATCHUP=resolve --arm resolvebreak=$PROTO:CACHE_CATCHUP=resolve,CACHE_CATCHUP_BREAK=drop-last"
    mkdir -p "$OUT/round2"
    node --version; docker exec "$NAME" mongosh --quiet --eval 'db.version()'
    for size in realistic heavy; do
      { state; node "$HERE/lab.js" --mongo "$MONGO" --reps 10 --size $size --out "$OUT/round2/$size.json" $ARMS2 2>&1; echo "exit=$?"; state; } > "$OUT/round2/$size.log" || true
    done ;;
  round3)
    PR=${CC_PR:-$W/crm-v3-pr}; UNIFY=${CC_UNIFY:-$W/crm-v3-unify}
    ARMS3="--arm pr=$PR --arm unify=$UNIFY --arm unifybreak=$UNIFY:V3LAB_BREAK=drop-last"
    mkdir -p "$OUT/round3"
    node --version; docker exec "$NAME" mongosh --quiet --eval 'db.version()'
    for size in realistic heavy; do
      # no pipe (the servers inherit stderr, so an orphan would hold a pipe open); the
      # servers' per-request plugin notices are filtered out afterwards
      { state; node "$HERE/lab-v3.js" --mongo "$MONGO" --reps 10 --size $size --out "$OUT/round3/$size.json" $ARMS3 2>&1; echo "exit=$?"; state; } > "$OUT/round3/$size.raw" || true
      grep -v -e 'For the Basal plugin' -e '^SECURITY: failed-authentication' "$OUT/round3/$size.raw" > "$OUT/round3/$size.log" || true
      rm -f "$OUT/round3/$size.raw"
    done ;;
  *) sed -n 2,18p "$0"; exit 2 ;;
esac
