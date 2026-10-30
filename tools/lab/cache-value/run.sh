#!/usr/bin/env bash
# run.sh - Part 2: all arms in parallel, real time, same traffic schedule.
#   run.sh <run-name> [hours]      (env: SCALE for a compressed smoke test only)
# Arms (name tree pool expect):
#   base-a        dev       default(5)  cache    } noise floor: base vs base
#   base-b        dev       default(5)  cache    }
#   cache-pool100 dev       100         cache
#   bypass-pool5  dev+bypass default(5) bypass
#   bypass-pool100 dev+bypass 100       bypass
# State (secrets, pids, server logs) lives in $CV_STATE, outside git; raw
# results (no secrets) are copied to results/<run-name>/.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NAME=$1; HOURS=${2:-3}; SCALE=${SCALE:-1}
WORK=/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work
DEV=$WORK/crm-cache-value; BYP=$WORK/crm-cache-value-bypass
STATE=${CV_STATE:?set CV_STATE to a directory outside any git tree}/$NAME
RES=$HERE/results/$NAME
mkdir -p "$STATE" "$RES"; chmod 700 "$STATE"
ARMS=("base-a $DEV - cache 0" "base-b $DEV - cache 1" "cache-pool100 $DEV 100 cache 2" "bypass-pool5 $BYP - bypass 3" "bypass-pool100 $BYP 100 bypass 4")

NOW=$(date +%s%3N)
{ echo "dev $(git -C "$DEV" rev-parse HEAD) diff: $(git -C "$DEV" diff --stat | tail -1)"
  echo "bypass $(git -C "$BYP" rev-parse HEAD) diff: $(git -C "$BYP" diff --stat | tail -1)"
  echo "node $(node --version)"; echo "hours $HOURS scale $SCALE seed-now $NOW"; } > "$RES/anchors.txt"

for a in "${ARMS[@]}"; do
  read -r arm tree pool expect i <<< "$a"
  mport=$((27810 + i)); port=$((17810 + i)); name=cv-p2-$NAME-$arm
  ver=$("$HERE/mongo.sh" up "$name" "$mport" mongo:8.0)
  echo "$arm mongo $ver container $name" >> "$RES/anchors.txt"
  "$HERE/mongo.sh" inspect "$name" > "$RES/docker-$arm.jsonl"
  uri=mongodb://127.0.0.1:$mport/cvp2
  echo "$arm seed $(CRM_DIR=$DEV node "$HERE/seed.js" "$uri" "$NOW")" >> "$RES/anchors.txt"
  ( umask 077; node -e "process.stdout.write(require('crypto').randomBytes(24).toString('hex'))" > "$STATE/secret-$arm" )
  ( umask 077
    { echo "MONGODB_URI='$uri'"; echo "API_SECRET='$(cat "$STATE/secret-$arm")'"; echo "PORT='$port'"; echo "HOSTNAME='127.0.0.1'"
      echo "INSECURE_USE_HTTP='true'"; echo "AUTH_DEFAULT_ROLES='denied'"; echo "DISPLAY_UNITS='mg/dl'"; echo "TZ='UTC'"
      echo "ENABLE='careportal basal iob cob devicestatus openaps pump'"
      echo "ALARM_HIGH='off'"; echo "ALARM_LOW='off'"; echo "ALARM_URGENT_HIGH='off'"; echo "ALARM_URGENT_LOW='off'"
      echo "ALARM_TIMEAGO_WARN='off'"; echo "ALARM_TIMEAGO_URGENT='off'"
      echo "HEARTBEAT='$((60 / SCALE))'"
      [ "$pool" != - ] && echo "MONGO_POOL_SIZE='$pool'"
      echo "NODE_OPTIONS='--require $HERE/preload.js'"; echo "CV_METRICS='$RES/metrics-$arm.jsonl'"
    } > "$STATE/env-$arm" )
  ( cd "$tree" && setsid nohup env -i PATH="$PATH" HOME="$HOME" bash -c "set -a; . '$STATE/env-$arm'; set +a; exec node lib/server/server.js" < /dev/null > "$STATE/server-$arm.log" 2>&1 & )
done

for a in "${ARMS[@]}"; do
  read -r arm tree pool expect i <<< "$a"; port=$((17810 + i))
  for _ in $(seq 1 120); do
    st=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/v1/status.json" -H "api-secret: $(printf %s "$(cat "$STATE/secret-$arm")" | sha1sum | cut -c1-40)" || true)
    [ "$st" = 200 ] && break; sleep 1
  done
  [ "$st" = 200 ] || { tail -20 "$STATE/server-$arm.log"; echo "arm $arm did not come up" >&2; exit 1; }
  ss -ltnpH "sport = :$port" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2 > "$STATE/server-$arm.pid"
  echo "$arm up pid $(cat "$STATE/server-$arm.pid") port $port tree $(basename "$tree") pool $pool"
done
sleep 20  # let the boot-time long loads finish before hour 0

pids=()
for a in "${ARMS[@]}"; do
  read -r arm tree pool expect i <<< "$a"
  CRM_DIR=$DEV BASE=http://127.0.0.1:$((17810 + i)) SECRET_FILE=$STATE/secret-$arm MONGODB_URI=mongodb://127.0.0.1:$((27810 + i))/cvp2 \
    METRICS=$RES/metrics-$arm.jsonl OUT=$RES/replay-$arm.jsonl ARM=$arm EXPECT=$expect HOURS=$HOURS SCALE=$SCALE \
    node "$HERE/replay.js" > "$RES/replay-$arm.log" 2>&1 &
  pids+=($!)
done
rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done

for a in "${ARMS[@]}"; do
  read -r arm tree pool expect i <<< "$a"; name=cv-p2-$NAME-$arm
  "$HERE/mongo.sh" inspect "$name" >> "$RES/docker-$arm.jsonl"
  pid=$(cat "$STATE/server-$arm.pid")
  if tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q lib/server/server.js; then kill "$pid"; fi
  grep -c -i "error" "$STATE/server-$arm.log" | sed "s/^/$arm server-log error lines: /" >> "$RES/anchors.txt" || true
done
echo "replay exit $rc" >> "$RES/anchors.txt"
exit $rc
