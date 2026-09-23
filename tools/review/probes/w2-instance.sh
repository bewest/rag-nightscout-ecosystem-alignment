#!/usr/bin/env bash
# w2-instance.sh — one Nightscout per worktree, each with ITS OWN node_modules,
# for the RT-D3 drag and alarm-delivery browser probes (2026-09-22).
#
# Why not nsctl.sh: nsctl links every state to ONE shared node_modules. For a
# D3 5.16 (15.0.8) vs D3 7.9 (dev) comparison that is fatal — `d3` resolves
# from node_modules, so both states would draw with the same D3. Each worktree
# here gets its own `npm ci --ignore-scripts` instead.
#
# Usage:
#   w2-instance.sh prep  <worktree>                       npm ci + dev-mode cache dirs
#   w2-instance.sh boot  <name> <worktree> <port> <db> <denied|readable> [VAR=val ...]
#   w2-instance.sh stop  <name>
#   w2-instance.sh reset <name> <worktree> <port> <db> <roles> [VAR=val ...]   stop, DROP db, boot
#
# Env: W2_STATE (dir for logs + the generated API secret; default ./w2-state),
#      W2_MONGO_CONTAINER (default ns-w2-mongo, published on 127.0.0.1:27082),
#      W2_NODE (default 22.22.0; engines >=20, CI matrix 20/22/24).
# The secret is generated into $W2_STATE/secret (mode 600) and never printed.
set -euo pipefail
: "${W2_STATE:=$PWD/w2-state}"; : "${W2_MONGO_CONTAINER:=ns-w2-mongo}"; : "${W2_NODE:=22.22.0}"
export N_PREFIX="${N_PREFIX:-$HOME/n}"
mkdir -p "$W2_STATE"
[ -f "$W2_STATE/secret" ] || { head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$W2_STATE/secret"; chmod 600 "$W2_STATE/secret"; }
sha1() { printf '%s' "$(cat "$W2_STATE/secret")" | sha1sum | cut -d' ' -f1; }

prep() {
  local wt=$1
  ( cd "$wt" && n exec "$W2_NODE" npm ci --ignore-scripts --no-audit --no-fund )
  # dev mode serves bundles from memory, but app.js still resolves this dir
  mkdir -p "$wt/node_modules/.cache/_ns_cache/public"
  ( cd "$wt" && node bin/generateRandomString.js > node_modules/.cache/_ns_cache/randomString )
}

boot() {
  local name=$1 wt=$2 port=$3 db=$4 roles=$5; shift 5
  local log="$W2_STATE/$name.log"; : > "$log"
  # NODE_ENV=development is required: production bundles live inside
  # node_modules and a browser probe would not be measuring the worktree.
  env -i PATH="$PATH" HOME="$HOME" N_PREFIX="$N_PREFIX" TZ=UTC W2_RUN="ns-w2-$name" \
    MONGODB_URI="mongodb://127.0.0.1:27082/$db" API_SECRET="$(cat "$W2_STATE/secret")" \
    PORT="$port" HOSTNAME=127.0.0.1 INSECURE_USE_HTTP=true NODE_ENV=development \
    DISPLAY_UNITS=mg/dl AUTH_DEFAULT_ROLES="$roles" TIME_FORMAT=24 \
    ENABLE="${ENABLE:-careportal basal iob cob bwp boluscalc}" \
    SHOW_PLUGINS="${SHOW_PLUGINS:-careportal iob cob}" \
    "$@" \
    bash -c "cd '$wt' && exec setsid nohup '$N_PREFIX/bin/n' exec '$W2_NODE' node lib/server/server.js >>'$log' 2>&1 </dev/null" &
  disown
  for i in $(seq 1 240); do
    curl -sf -m 2 -H "api-secret: $(sha1)" "http://127.0.0.1:$port/api/v1/status.json" >/dev/null && { echo "$name up :$port"; return 0; }
    sleep 0.5
  done
  echo "$name FAILED to start"; tail -20 "$log"; return 1
}

stop() {  # only processes stamped with this instance's W2_RUN are touched
  local want="W2_RUN=ns-w2-$1" p pid
  for p in /proc/[0-9]*; do pid=${p#/proc/}
    { tr '\0' '\n' < "$p/environ"; } 2>/dev/null | grep -qx "$want" && kill "$pid" 2>/dev/null && echo "stopped $pid"
  done; true
}

reset() {  # never drop a database under a live server: the cache survives it
  local name=$1 port=$3 db=$4
  stop "$name"
  for _ in $(seq 1 40); do ss -ltn "( sport = :$port )" | grep -q LISTEN || break; sleep 0.25; done
  docker exec "$W2_MONGO_CONTAINER" mongosh --quiet "$db" --eval 'db.dropDatabase().ok' >/dev/null
  boot "$@"
}

cmd=${1:-}; shift || true
case "$cmd" in
  prep|boot|stop|reset) "$cmd" "$@" ;;
  *) sed -n '2,21p' "$0" | sed 's/^# \?//'; exit 1 ;;
esac
