#!/bin/bash
# object-id lab: replay client _id shapes against several Nightscout builds.
#
#   tools/lab/object-id/lab.sh up        start mongo and every build
#   tools/lab/object-id/lab.sh run       run probes.js against every build, then compare
#   tools/lab/object-id/lab.sh down      stop the builds and remove the mongo container
#
# Builds are NAME=worktree:port, space separated, in $OID_BUILDS. The default is
# 15.0.8, dev and PR #8758 as checked out in externals/work. Each build gets
# its own database (oidlab_<NAME>), dropped at the start of every run.
#
# The API secret is generated per lab into $OID_STATE/secret; nothing secret is
# kept in this directory. Synthetic data only: never point this at a real site.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
W=$ROOT/externals/work
OID_BUILDS=${OID_BUILDS:-"a=$W/crm-6a-replay-a:3971 b=$W/crm-6a-replay-b:3972 d=$W/crm-bf-object-id-crud:3973"}
OID_STATE=${OID_STATE:-${TMPDIR:-/tmp}/object-id-lab}
OID_MONGO_PORT=${OID_MONGO_PORT:-27181}
OID_MONGO_IMAGE=${OID_MONGO_IMAGE:-mongo:7}
OID_NODE=${OID_NODE:-22.23.2}
CONTAINER=oid-lab-mongo

mkdir -p "$OID_STATE/logs" "$OID_STATE/pids" "$OID_STATE/out"
[ -s "$OID_STATE/secret" ] || { head -c 18 /dev/urandom | base64 | tr -d '/+=' > "$OID_STATE/secret"; chmod 600 "$OID_STATE/secret"; }

hash () { printf %s "$(cat "$OID_STATE/secret")" | sha1sum | cut -c1-40; }

each_build () {
  for b in $OID_BUILDS; do
    local name=${b%%=*} rest=${b#*=}
    "$@" "$name" "${rest%:*}" "${rest##*:}"
  done
}

start_build () {
  local name=$1 dir=$2 port=$3
  ( cd "$dir" && env -i PATH="$PATH" HOME="$HOME" N_PREFIX="${N_PREFIX:-}" \
      MONGODB_URI="mongodb://127.0.0.1:$OID_MONGO_PORT/oidlab_$name" \
      API_SECRET="$(cat "$OID_STATE/secret")" PORT="$port" HOSTNAME=127.0.0.1 \
      INSECURE_USE_HTTP=true AUTH_DEFAULT_ROLES=readable DISPLAY_UNITS=mg/dl \
      ENABLE="careportal basal iob cob devicestatus profile" \
      setsid nohup n exec "$OID_NODE" node lib/server/server.js \
      </dev/null > "$OID_STATE/logs/server-$name.log" 2>&1 & )
  local h; h=$(hash)
  for _ in $(seq 1 90); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/v1/status.json" -H "api-secret: $h")" = 200 ] \
      && { listener "$port" > "$OID_STATE/pids/$name.pid"; echo "$name up ($(git -C "$dir" rev-parse --short HEAD), :$port, pid $(cat "$OID_STATE/pids/$name.pid"))"; return 0; }
    sleep 1
  done
  echo "$name did not come up"; tail -20 "$OID_STATE/logs/server-$name.log"; return 1
}

# `n exec` does not exec node in place, so $! is not the server. Record and
# stop the process that listens on the build's port, and only if it is a
# Nightscout server.
listener () { ss -ltnpH "sport = :$1" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }

stop_build () {
  local name=$1 port=$3 pid
  pid=$(listener "$port")
  if [ -n "$pid" ] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'lib/server/server.js'; then
    kill "$pid"; echo "$name stopped (pid $pid, :$port)"
  fi
  rm -f "$OID_STATE/pids/$name.pid"
}

drop_db () { OID_MONGO_PORT=$OID_MONGO_PORT n exec "$OID_NODE" node "$HERE/probes.js" --drop "$1" "$2"; }

run_build () {
  local name=$1 dir=$2 port=$3
  OID_STATE=$OID_STATE OID_MONGO_PORT=$OID_MONGO_PORT \
    n exec "$OID_NODE" node "$HERE/probes.js" "$name" "$dir" "$port" > "$OID_STATE/out/$name.json"
  echo "$name: $(git -C "$dir" rev-parse --short HEAD) -> $OID_STATE/out/$name.json"
}

case ${1:-} in
  up)
    docker ps --format '{{.Names}}' | grep -qx "$CONTAINER" || \
      docker run -d --rm --name "$CONTAINER" --ulimit nofile=64000:64000 \
        -p "127.0.0.1:$OID_MONGO_PORT:27017" "$OID_MONGO_IMAGE" >/dev/null
    for _ in $(seq 1 30); do docker exec "$CONTAINER" mongosh --quiet --eval 'db.runCommand({ping:1}).ok' 2>/dev/null | grep -q 1 && break; sleep 1; done
    each_build drop_db
    each_build start_build ;;
  run)
    each_build run_build
    n exec "$OID_NODE" node "$HERE/probes.js" --compare "$OID_STATE/out" ;;
  down)
    each_build stop_build
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true ;;
  *) sed -n '2,14p' "$0"; exit 2 ;;
esac
