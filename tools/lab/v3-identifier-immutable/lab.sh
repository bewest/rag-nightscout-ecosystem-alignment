#!/bin/bash
# v3-identifier-immutable lab: re-send a record with the same identifier and a
# different date, device or eventType, through API v3 (and v1 for contrast),
# against several cgm-remote-monitor refs side by side.
#
#   tools/lab/v3-identifier-immutable/lab.sh up     archive each ref, start mongo and every build
#   tools/lab/v3-identifier-immutable/lab.sh run    run probes.js against every build, print a table
#   tools/lab/v3-identifier-immutable/lab.sh down   stop the builds, remove the container
#
# Builds are NAME=REF:PORT, space separated, in $V3I_BUILDS, archived from
# $V3I_REPO into $V3I_STATE/b<NAME>. node_modules: set V3I_NM_<NAME> to a
# directory installed from the same package-lock.json to symlink it, else
# `npm ci --ignore-scripts` runs. The API secret is generated into
# $V3I_STATE/secret; nothing secret is kept here. Synthetic data only.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
V3I_REPO=${V3I_REPO:-$ROOT/externals/cgm-remote-monitor-official}
V3I_BUILDS=${V3I_BUILDS:-"1508=15.0.8:3981 dev=official/dev:3982"}
V3I_STATE=${V3I_STATE:-${TMPDIR:-/tmp}/v3-identifier-immutable}
V3I_MONGO_PORT=${V3I_MONGO_PORT:-27183}
V3I_MONGO_IMAGE=${V3I_MONGO_IMAGE:-mongo:7}
V3I_NODE=${V3I_NODE:-node}
CONTAINER=v3imm-mongo
export V3I_STATE V3I_MONGO_PORT

mkdir -p "$V3I_STATE/out"
[ -s "$V3I_STATE/secret" ] || { head -c 18 /dev/urandom | base64 | tr -d '/+=' > "$V3I_STATE/secret"; chmod 600 "$V3I_STATE/secret"; }
hash () { printf %s "$(cat "$V3I_STATE/secret")" | sha1sum | cut -c1-40; }
listener () { ss -ltnpH "sport = :$1" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }

each_build () {
  for b in $V3I_BUILDS; do
    local name=${b%%=*} rest=${b#*=}
    "$@" "$name" "${rest%:*}" "${rest##*:}"
  done
}

prepare () {
  local name=$1 ref=$2 dir=$V3I_STATE/b$1 nm
  [ -d "$dir" ] || {
    mkdir -p "$dir"
    git -C "$V3I_REPO" archive "$ref" | tar -x -C "$dir"
    git -C "$V3I_REPO" rev-parse "$ref^{commit}" > "$dir/.lab-ref"
    nm=$(eval echo "\${V3I_NM_$name:-}")
    if [ -n "$nm" ]; then
      cmp -s "$dir/package-lock.json" "$nm/../package-lock.json" || { echo "$name: V3I_NM_$name is not from the same package-lock.json"; return 1; }
      ln -s "$nm" "$dir/node_modules"
    else
      (cd "$dir" && npm ci --ignore-scripts --no-audit --no-fund >/dev/null)
    fi
  }
}

start_build () {
  local name=$1 port=$3 dir=$V3I_STATE/b$1
  "$V3I_NODE" "$HERE/probes.js" --drop "$name" "$dir"
  ( cd "$dir" && env -i PATH="$PATH" HOME="$HOME" \
      MONGODB_URI="mongodb://127.0.0.1:$V3I_MONGO_PORT/v3imm_$name" \
      API_SECRET="$(cat "$V3I_STATE/secret")" PORT="$port" HOSTNAME=127.0.0.1 \
      INSECURE_USE_HTTP=true AUTH_DEFAULT_ROLES=readable DISPLAY_UNITS=mg/dl \
      ENABLE="careportal devicestatus" \
      setsid nohup "$V3I_NODE" lib/server/server.js </dev/null > "$V3I_STATE/server-$name.log" 2>&1 & )
  for _ in $(seq 1 90); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/v1/status.json" -H "api-secret: $(hash)")" = 200 ] \
      && { echo "$name up ($(cut -c1-8 "$dir/.lab-ref"), :$port)"; return 0; }
    sleep 1
  done
  echo "$name did not come up"; tail -20 "$V3I_STATE/server-$name.log"; return 1
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
  "$V3I_NODE" "$HERE/probes.js" "$name" "$V3I_STATE/b$name" "$port" > "$V3I_STATE/out/$name.json"
}

case ${1:-} in
  up)
    docker inspect "$CONTAINER" >/dev/null 2>&1 || docker run -d --name "$CONTAINER" -p "127.0.0.1:$V3I_MONGO_PORT:27017" "$V3I_MONGO_IMAGE" >/dev/null
    for _ in $(seq 1 30); do docker exec "$CONTAINER" mongosh --quiet --eval 'db.version()' >/dev/null 2>&1 && break; sleep 1; done
    echo "mongod $(docker exec "$CONTAINER" mongosh --quiet --eval 'db.version()') ($CONTAINER, 127.0.0.1:$V3I_MONGO_PORT)"
    each_build prepare
    each_build start_build ;;
  run)
    rm -f "$V3I_STATE"/out/*.json
    each_build run_build
    "$V3I_NODE" "$HERE/probes.js" --compare "$V3I_STATE"/out/*.json ;;
  down)
    each_build stop_build
    docker rm -f "$CONTAINER" >/dev/null 2>&1 && echo "$CONTAINER removed" || true ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
