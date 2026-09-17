#!/bin/bash
D=$1; P=$2; NE=${3:-production}
cd $D
T0=$(date +%s.%N)
CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:27017/nsharness_lens API_SECRET="${NS_HARNESS_SECRET:?set NS_HARNESS_SECRET}" HOSTNAME=localhost INSECURE_USE_HTTP=true PORT=$P NODE_ENV=$NE DISPLAY_UNITS=mg/dl node lib/server/server.js > /tmp/boot_$P.log 2>&1 &
PID=$!
while ! curl -sf -o /dev/null http://localhost:$P/api/v1/status.json 2>/dev/null; do
  kill -0 $PID 2>/dev/null || { echo "DIED"; cat /tmp/boot_$P.log|tail -5; exit 1; }
  sleep 0.05
done
T1=$(date +%s.%N)
echo "BOOT_TO_200 ${NE} $(echo "$T1 - $T0" | bc) s"
kill $PID 2>/dev/null; wait $PID 2>/dev/null
