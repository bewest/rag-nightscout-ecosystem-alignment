#!/bin/bash
# record-identity lab: what each write, read and delete path does with a
# client-sent _id and identifier (v1, API v3, socket), for entries, treatments,
# devicestatus, profile and food, against several cgm-remote-monitor refs side
# by side. Built for docs/10-domain/record-identity-reference.md.
#
#   tools/lab/record-identity/lab.sh up     archive each ref, start mongo and every build
#   tools/lab/record-identity/lab.sh run    run probes.js against every build, print a table
#   tools/lab/record-identity/lab.sh down   stop the builds, remove the container
#
# Builds are NAME=REF:PORT, space separated, in $RID_BUILDS, archived from
# $RID_REPO into $RID_STATE/b<NAME>. node_modules: set RID_NM_<NAME> to a
# directory installed from the same package-lock.json to symlink it, else
# `npm ci --ignore-scripts` runs. The API secret is generated into
# $RID_STATE/secret; nothing secret is kept here. Synthetic data only.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
RID_REPO=${RID_REPO:-$ROOT/externals/cgm-remote-monitor-official}
RID_BUILDS=${RID_BUILDS:-"1508=15.0.8:3983 dev=fade2299:3984"}
RID_STATE=${RID_STATE:-${TMPDIR:-/tmp}/record-identity}
RID_MONGO_PORT=${RID_MONGO_PORT:-27184}
RID_MONGO_IMAGE=${RID_MONGO_IMAGE:-mongo:7}
RID_NODE=${RID_NODE:-node}
CONTAINER=ridlab-mongo
export RID_STATE RID_MONGO_PORT

mkdir -p "$RID_STATE/out"
[ -s "$RID_STATE/secret" ] || { head -c 18 /dev/urandom | base64 | tr -d '/+=' > "$RID_STATE/secret"; chmod 600 "$RID_STATE/secret"; }
hash () { printf %s "$(cat "$RID_STATE/secret")" | sha1sum | cut -c1-40; }
listener () { ss -ltnpH "sport = :$1" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }

each_build () {
  for b in $RID_BUILDS; do
    local name=${b%%=*} rest=${b#*=}
    "$@" "$name" "${rest%:*}" "${rest##*:}"
  done
}

prepare () {
  local name=$1 ref=$2 dir=$RID_STATE/b$1 nm
  [ -d "$dir" ] || {
    mkdir -p "$dir"
    git -C "$RID_REPO" archive "$ref" | tar -x -C "$dir"
    git -C "$RID_REPO" rev-parse "$ref^{commit}" > "$dir/.lab-ref"
    nm=$(eval echo "\${RID_NM_$name:-}")
    if [ -n "$nm" ]; then
      cmp -s "$dir/package-lock.json" "$nm/../package-lock.json" || { echo "$name: RID_NM_$name is not from the same package-lock.json"; return 1; }
      ln -s "$nm" "$dir/node_modules"
    else
      (cd "$dir" && npm ci --ignore-scripts --no-audit --no-fund >/dev/null)
    fi
  }
}

start_build () {
  local name=$1 port=$3 dir=$RID_STATE/b$1
  "$RID_NODE" "$HERE/probes.js" --drop "$name" "$dir"
  ( cd "$dir" && env -i PATH="$PATH" HOME="$HOME" \
      MONGODB_URI="mongodb://127.0.0.1:$RID_MONGO_PORT/ridlab_$name" \
      API_SECRET="$(cat "$RID_STATE/secret")" PORT="$port" HOSTNAME=127.0.0.1 \
      INSECURE_USE_HTTP=true AUTH_DEFAULT_ROLES=readable DISPLAY_UNITS=mg/dl \
      ENABLE="careportal devicestatus food" \
      setsid nohup "$RID_NODE" lib/server/server.js </dev/null > "$RID_STATE/server-$name.log" 2>&1 & )
  for _ in $(seq 1 90); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/v1/status.json" -H "api-secret: $(hash)")" = 200 ] \
      && { echo "$name up ($(cut -c1-8 "$dir/.lab-ref"), :$port)"; return 0; }
    sleep 1
  done
  echo "$name did not come up"; tail -20 "$RID_STATE/server-$name.log"; return 1
}

stop_build () {
  local name=$1 port=$3 pid
  pid=$(listener "$port")
  if [ -n "$pid" ] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'lib/server/server.js'; then
    kill "$pid"; echo "$name stopped (pid $pid, :$port)"
  fi
}

run_build () {
  local name=$1 port=$3
  "$RID_NODE" "$HERE/probes.js" "$name" "$RID_STATE/b$name" "$port" > "$RID_STATE/out/$name.json"
}

case ${1:-} in
  up)
    docker inspect "$CONTAINER" >/dev/null 2>&1 || docker run -d --name "$CONTAINER" -p "127.0.0.1:$RID_MONGO_PORT:27017" "$RID_MONGO_IMAGE" >/dev/null
    for _ in $(seq 1 30); do docker exec "$CONTAINER" mongosh --quiet --eval 'db.version()' >/dev/null 2>&1 && break; sleep 1; done
    echo "mongod $(docker exec "$CONTAINER" mongosh --quiet --eval 'db.version()') ($CONTAINER, 127.0.0.1:$RID_MONGO_PORT)"
    each_build prepare
    each_build start_build ;;
  run)
    rm -f "$RID_STATE"/out/*.json
    each_build run_build
    "$RID_NODE" "$HERE/probes.js" --compare "$RID_STATE"/out/*.json ;;
  down)
    each_build stop_build
    docker rm -f "$CONTAINER" >/dev/null 2>&1 && echo "$CONTAINER removed" || true ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
