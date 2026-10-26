#!/usr/bin/env bash
# BF-164 lab (tools/lab/aaps-ws-delivery): boots two Nightscout servers from one worktree, as separate processes.
#   source (port 17317, db bf164src): a plain Nightscout the connector reads from.
#   target (port 17316, db bf164tgt): the site under test; nightscout-connect enabled with
#     CONNECT_SOURCE=nightscout pointed at the source, so connector writes are the real thing.
# Synthetic data only. Secrets below are lab-only throwaways, generated per run.
set -euo pipefail
WT=${1:?worktree}
OUT=${2:?outdir}
MONGO=${3:-mongodb://127.0.0.1:27316}
mkdir -p "$OUT"
SRC_SECRET=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
TGT_SECRET=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
printf '%s\n%s\n' "$SRC_SECRET" "$TGT_SECRET" > "$OUT/secrets"
chmod 600 "$OUT/secrets"
common=(NODE_ENV=production INSECURE_USE_HTTP=true HOSTNAME=127.0.0.1 DISPLAY_UNITS=mg/dl AUTH_DEFAULT_ROLES=denied AUTH_FAIL_DELAY=50)
cd "$WT"
env -i PATH="$PATH" HOME="$HOME" "${common[@]}" PORT=17317 MONGODB_URI="$MONGO/bf164src" API_SECRET="$SRC_SECRET" \
  ENABLE="careportal api" \
  setsid nohup node lib/server/server.js > "$OUT/source.log" 2>&1 < /dev/null &
echo $! > "$OUT/source.pid"
env -i PATH="$PATH" HOME="$HOME" "${common[@]}" PORT=17316 MONGODB_URI="$MONGO/bf164tgt" API_SECRET="$TGT_SECRET" \
  ENABLE="careportal api connect" CONNECT_SOURCE=nightscout CONNECT_SOURCE_ENDPOINT=http://127.0.0.1:17317 \
  CONNECT_SOURCE_API_SECRET="$SRC_SECRET" \
  setsid nohup node lib/server/server.js > "$OUT/target.log" 2>&1 < /dev/null &
echo $! > "$OUT/target.pid"
for p in 17317 17316; do
  for i in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:$p/api/v1/status.json" -H "api-secret: $(printf %s "$([ $p = 17317 ] && echo "$SRC_SECRET" || echo "$TGT_SECRET")" | sha1sum | cut -d' ' -f1)" > /dev/null; then echo "up $p"; break; fi
    sleep 1
  done
done
