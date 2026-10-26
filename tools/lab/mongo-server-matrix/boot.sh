#!/bin/bash
# MongoDB server matrix, boot cell: start one cgm-remote-monitor tree against one
# MongoDB server and report what an operator would see in the first WIN seconds.
#
#   tools/lab/mongo-server-matrix/boot.sh <tree-dir> <label> <mongo-port> <http-port> [window-s]
#
# Prints one CELL line (process alive or dead, first HTTP status and when, final
# status) plus the start of /api/v1/status.json, the page text at /, and the
# MongoDB-related log lines. The server log goes to $MM_OUT/boot-<label>.log.
# The API secret is generated per run; nothing secret lives in this directory.
# Synthetic data only: the server uses its own database, mmboot, on that port.
set -u
T=$1; L=$2; MP=$3; HP=$4; WIN=${5:-60}
OUT=${MM_OUT:-${TMPDIR:-/tmp}/mongo-server-matrix}; mkdir -p "$OUT"; LOG=$OUT/boot-$L.log
SECRET=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
cd "$T"
env -i PATH="$PATH" HOME="$HOME" CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:$MP/mmboot API_SECRET="$SECRET" \
  PORT=$HP HOSTNAME=127.0.0.1 INSECURE_USE_HTTP=true \
  setsid nohup node lib/server/server.js > "$LOG" 2>&1 < /dev/null &
PID=$!
t0=$(date +%s); first=""; c=000
while [ $(( $(date +%s) - t0 )) -lt "$WIN" ]; do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:$HP/api/v1/status.json)
  if [ "$c" != "000" ] && [ -z "$first" ]; then first="$c@$(( $(date +%s) - t0 ))s"; fi
  [ "$c" = "200" ] && break
  sleep 2
done
alive=$(kill -0 $PID 2>/dev/null && echo alive || echo dead)
st=$(curl -s --max-time 3 http://127.0.0.1:$HP/api/v1/status.json | head -c 300)
root=$(curl -s --max-time 3 http://127.0.0.1:$HP/ | sed 's/<[^>]*>/ /g' | tr -s ' \n' ' ' | head -c 400)
echo "CELL $L proc=$alive first_http=${first:-none} final_status_code=$c"
echo "  status.json: $st"
echo "  / text: $root"
echo "  log lines: $(wc -l < "$LOG"); mongo-ish lines:"
grep -iE 'mongo|wire|storage|error|retry|listening' "$LOG" | sort | uniq -c | sort -rn | head -8 | sed 's/^/    /'
kill -- -$PID 2>/dev/null; kill $PID 2>/dev/null; sleep 1
