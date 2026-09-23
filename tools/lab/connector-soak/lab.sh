#!/usr/bin/env bash
# lab.sh - Nightscout-to-Nightscout connector soak lab.
#
# A source Nightscout (S) with AUTH_DEFAULT_ROLES=denied, seeded with
# synthetic data and fed by a live writer; sink Nightscouts (K*) running
# nightscout-connect with CONNECT_SOURCE=nightscout, reaching S through a
# counting proxy. Every server has its own MongoDB. Counts are read from mongo.
#
# All state (secrets, ledger, samples, logs) lives under $CKSOAK_STATE, which
# must be outside any git tree. Secrets are generated here at runtime and are
# never printed. Containers and the network are named cksoak-*; `down`
# removes only the names this script creates.
#
# Usage (see the soak report for the full run order):
#   CKSOAK_STATE=/path lab.sh build <connector-version>   # e.g. 0.1.0-dev.2
#   lab.sh up-main <connector-version>      # S, proxy, K1 (token), K2 (secret), writer, sampler
#   lab.sh control <tag> <connector-version|shipped> <source-roles> <mode> [preseed-subject]
#       SINK_EXTRA_ENV adds one line to the sink env; NS_COMMIT selects the Nightscout image
#   lab.sh stats-loop                        # host loop: docker stats + VmRSS, every 60 s
#   lab.sh canary <container...>             # credential scan of container logs
#   lab.sh analyze <outdir> <ledger> <src:src-mongo> <name:sink:sink-mongo=firstFetchISO>...
#   lab.sh disturb <outdir> <source> <source-mongo> update-treatment|update-entry|delete|backdate
#   lab.sh mongo-eval <container> <db> <js>  # authoritative reads
#   lab.sh down                              # remove every cksoak-* container this script made
#
# Environment: NS_REPO (cgm-remote-monitor clone), NS_COMMIT (default 74fc6619),
# NODE_VER for lockfile regeneration (default 22.23.2, run with `n exec`).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
STATE=${CKSOAK_STATE:?set CKSOAK_STATE to a directory outside the repo}
NS_REPO=${NS_REPO:-$ROOT/externals/cgm-remote-monitor-official}
NS_COMMIT=${NS_COMMIT:-74fc6619}
NODE_VER=${NODE_VER:-22.23.2}
NET=cksoak-net
BASE=cksoak-ns:$NS_COMMIT
mkdir -p "$STATE"/{secrets,out,build,logs}
chmod 700 "$STATE/secrets"

secret () { # secret <name>: create once, never print
  local f="$STATE/secrets/$1"
  [ -s "$f" ] || { umask 077; openssl rand -hex 24 > "$f"; }
  echo "$f"
}

net () { docker network inspect $NET >/dev/null 2>&1 || docker network create $NET >/dev/null; }

build () {
  local v=$1 src="$STATE/build/ns-$NS_COMMIT"
  if ! docker image inspect "$BASE" >/dev/null 2>&1; then
    rm -rf "$src"; mkdir -p "$src"
    git -C "$NS_REPO" archive "$NS_COMMIT" | tar -x -C "$src"
    (cd "$src" && docker build -q -t "$BASE" .)
  fi
  local d="$STATE/build/ns-$NS_COMMIT-nc$v"
  rm -rf "$d"; cp -a "$src" "$d" 2>/dev/null || { mkdir -p "$d"; git -C "$NS_REPO" archive "$NS_COMMIT" | tar -x -C "$d"; }
  python3 - "$d/package.json" "$v" <<'EOF'
import json,sys
p=json.load(open(sys.argv[1])); p['dependencies']['nightscout-connect']=sys.argv[2]
open(sys.argv[1],'w').write(json.dumps(p,indent=2)+'\n')
EOF
  (cd "$d" && n exec "$NODE_VER" npm install --package-lock-only --ignore-scripts --no-audit --no-fund >/dev/null)
  local want got
  want=$(npm view "nightscout-connect@$v" dist.integrity)
  got=$(python3 -c "import json;print(json.load(open('$d/package-lock.json'))['packages']['node_modules/nightscout-connect']['integrity'])")
  [ "$want" = "$got" ] || { echo "lockfile integrity $got does not match npm $want" >&2; exit 1; }
  (cd "$d" && docker build -q -t "$BASE-nc$v" .)
  docker run --rm --entrypoint node "$BASE-nc$v" -p 'require("/opt/app/node_modules/nightscout-connect/package.json").version'
}

mongo () { # mongo <name> <hostport>
  docker rm -f "$1" >/dev/null 2>&1 || true
  docker run -d --name "$1" --network $NET --ulimit nofile=64000:64000 \
    -p "127.0.0.1:$2:27017" --restart no mongo:7 --quiet >/dev/null
  until docker exec "$1" mongosh --quiet --eval 'db.adminCommand({ping:1}).ok' >/dev/null 2>&1; do sleep 1; done
}

ns_common () { # ns_common <envfile> <db-host> <db-name> <secretfile> <default-roles>
  { echo "MONGODB_URI=mongodb://$2:27017/$3"
    echo "API_SECRET=$(cat "$4")"
    echo "INSECURE_USE_HTTP=true"; echo "PORT=1337"; echo "TZ=UTC"; echo "DISPLAY_UNITS=mg/dl"
    echo "AUTH_DEFAULT_ROLES=$5"
    echo "ALARM_TYPES=simple"; echo "ALARM_HIGH=off"; echo "ALARM_LOW=off"; echo "ALARM_URGENT_HIGH=off"; echo "ALARM_URGENT_LOW=off"
    echo "ALARM_TIMEAGO_WARN=off"; echo "ALARM_TIMEAGO_URGENT=off"
  } > "$1"
  chmod 600 "$1"
}

wait_http () { # wait_http <hostport>
  for _ in $(seq 1 120); do curl -fsS -o /dev/null "http://127.0.0.1:$1/api/v1/status.json" 2>/dev/null && return 0
    curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$1/api/v1/status.json" 2>/dev/null | grep -q '^401$' && return 0; sleep 2; done
  echo "server on $1 did not come up" >&2; return 1
}

source_ns () { # source_ns <name> <hostport> <default-roles> <mongo-name> <image>
  local env="$STATE/secrets/$1.env"
  ns_common "$env" "$4" "${1//-/_}" "$(secret "$1")" "$3"
  echo "ENABLE=careportal basal iob cob" >> "$env"
  docker rm -f "$1" >/dev/null 2>&1 || true
  docker run -d --name "$1" --network $NET -p "127.0.0.1:$2:1337" --env-file "$env" \
    --log-opt max-size=200m --restart no "$5" >/dev/null
  wait_http "$2"
}

proxy () { # proxy <name> <upstream-container>
  docker rm -f "$1" >/dev/null 2>&1 || true
  docker run -d --name "$1" --network $NET -e UPSTREAM="http://$2:1337" -v "$HERE:/lab:ro" \
    --log-opt max-size=200m --restart no --entrypoint node "$BASE" /lab/proxy.js >/dev/null
}

sink_ns () { # sink_ns <name> <hostport> <image> <mode token|secret> <proxy> <source> <debug> <mongo-name>
  local name=$1 env="$STATE/secrets/$1.env" endpoint="http://$5:1337"
  ns_common "$env" "$8" "${1//-/_}" "$(secret "$1")" denied
  { echo "ENABLE=careportal basal iob cob connect"; echo "CONNECT_SOURCE=nightscout"; echo "CONNECT_DEBUG=$7"; } >> "$env"
  [ -z "${SINK_EXTRA_ENV:-}" ] || echo "$SINK_EXTRA_ENV" >> "$env"   # e.g. CONNECT_SOURCE_COLLECTIONS=...
  case $4 in
    token)  subject "$6" "$name-reader" readable
            echo "CONNECT_SOURCE_ENDPOINT=$endpoint/?token=$(cat "$STATE/secrets/$name-reader.token")" >> "$env" ;;
    secret) echo "CONNECT_SOURCE_ENDPOINT=$endpoint" >> "$env"
            echo "CONNECT_SOURCE_API_SECRET=$(cat "$STATE/secrets/$6")" >> "$env" ;;
    *) echo "mode must be token or secret" >&2; return 2 ;;
  esac
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --network $NET -p "127.0.0.1:$2:1337" --env-file "$env" \
    --log-opt max-size=200m --restart no "$3" >/dev/null
  wait_http "$2"
}

subject () { # subject <source> <subject-name> <roles|none>
  docker run --rm --network $NET -v "$HERE:/lab:ro" -v "$STATE/secrets:/secrets" --entrypoint node "$BASE" \
    /lab/subject.js "http://$1:1337" "/secrets/$1" "$2" "$3" "/secrets/$2.token"
}

subjects () { # subjects <source>
  docker run --rm --network $NET -v "$HERE:/lab:ro" -v "$STATE/secrets:/secrets:ro" --entrypoint node "$BASE" \
    /lab/subject.js "http://$1:1337" "/secrets/$1" --list
}

writer () { # writer <name> <source> <ledger>
  docker rm -f "$1" >/dev/null 2>&1 || true
  docker run -d --name "$1" --network $NET -v "$HERE:/lab:ro" -v "$STATE:/state" \
    -e TARGET="http://$2:1337" -e SECRET_FILE="/state/secrets/$2" -e LEDGER="/state/out/$3" \
    --log-opt max-size=50m --restart no --entrypoint node "$BASE" /lab/writer.js >/dev/null
}

sampler () { # sampler <name> <outdir> <target specs...>  spec: name:container:mongo-container
  local n=$1 o=$2; shift 2; local specs=()
  for s in "$@"; do IFS=: read -r t c m <<<"$s"
    specs+=("$t=mongodb://$m:27017/${c//-/_}|http://$c:1337|/state/secrets/$c"); done
  mkdir -p "$STATE/out/$o"
  docker rm -f "$n" >/dev/null 2>&1 || true
  docker run -d --name "$n" --network $NET -v "$HERE:/lab:ro" -v "$STATE:/state" \
    -e NODE_PATH=/opt/app/node_modules -e OUT="/state/out/$o" -e TARGETS="$(IFS=,; echo "${specs[*]}")" \
    -e INTERVAL_SEC="${INTERVAL_SEC:-60}" --log-opt max-size=50m --restart no --entrypoint node "$BASE" /lab/sampler.js >/dev/null
}

up_main () { # up_main <connector-version>
  local img="$BASE-nc$1"
  net
  mongo cksoak-mongo-s 27471; mongo cksoak-mongo-k1 27472; mongo cksoak-mongo-k2 27473
  source_ns cksoak-s 3471 denied cksoak-mongo-s "$BASE"
  writer cksoak-writer cksoak-s ledger.jsonl
  until grep -q '"kind":"live"\|seeded' <(docker logs cksoak-writer 2>&1); do sleep 2; done
  proxy cksoak-proxy cksoak-s
  sink_ns cksoak-k1 3472 "$img" token  cksoak-proxy cksoak-s false cksoak-mongo-k1
  sink_ns cksoak-k2 3473 "$img" secret cksoak-proxy cksoak-s true  cksoak-mongo-k2
  add_k3 "$1"
}

add_k3 () { # K3: as K1 but without profiles, the configuration that avoids the profile write failure
  mongo cksoak-mongo-k3 27474
  SINK_EXTRA_ENV=CONNECT_SOURCE_COLLECTIONS=entries,treatments,devicestatus \
    sink_ns cksoak-k3 3474 "$BASE-nc$1" token cksoak-proxy cksoak-s false cksoak-mongo-k3
  sampler cksoak-sampler main s:cksoak-s:cksoak-mongo-s k1:cksoak-k1:cksoak-mongo-k1 k2:cksoak-k2:cksoak-mongo-k2 k3:cksoak-k3:cksoak-mongo-k3
}

control () { # control <tag> <connector-version> <source-roles> <token|secret> [preseed-subject-version]
  # A self-contained pair: its own source (seeded by its own writer), proxy and sink.
  local tag=$1 v=$2 roles=$3 mode=$4 pre=${5:-}
  local s=cksoak-c$tag-s k=cksoak-c$tag-k p=cksoak-c$tag-proxy w=cksoak-c$tag-writer
  # "shipped" = the NS_COMMIT image with whatever connector its own package.json pins.
  local kimg="$BASE-nc$v"; [ "$v" = shipped ] && kimg="$BASE"
  net
  mongo "$s-mongo" 0; mongo "$k-mongo" 0
  source_ns "$s" "${CPORT_S:?}" "$roles" "$s-mongo" "$BASE"
  writer "$w" "$s" "ledger-c$tag.jsonl"
  until grep -q 'seeded' <(docker logs "$w" 2>&1); do sleep 2; done
  proxy "$p" "$s"
  if [ -n "$pre" ]; then
    # Leave behind the subject an earlier connector created, then upgrade.
    sink_ns "$k" "${CPORT_K:?}" "$BASE-nc$pre" "$mode" "$p" "$s" true "$k-mongo"
    until subjects "$s" | grep -q nightscout-connect-reader; do sleep 3; done
    docker rm -f "$k" >/dev/null
  fi
  sink_ns "$k" "${CPORT_K:?}" "$kimg" "$mode" "$p" "$s" true "$k-mongo"
  sampler "cksoak-c$tag-sampler" "c$tag" "s:$s:$s-mongo" "k:$k:$k-mongo"
}

stats_loop () { # host-side: one JSON line per container per minute
  while :; do
    local t; t=$(date -u +%FT%TZ)
    for c in $(docker ps --format '{{.Names}}' | grep '^cksoak-' | grep -v mongo | sort); do
      local rss fds; rss=$(docker exec "$c" sh -c 'grep VmRSS /proc/1/status' 2>/dev/null | awk '{print $2}' || true)
      fds=$(docker exec "$c" sh -c 'ls /proc/1/fd | wc -l' 2>/dev/null | tr -d ' ' || true)
      docker stats --no-stream --format "{\"t\":\"$t\",\"name\":\"{{.Name}}\",\"cpu\":\"{{.CPUPerc}}\",\"mem\":\"{{.MemUsage}}\",\"rss_kb\":\"${rss:-}\",\"fds\":\"${fds:-}\"}" "$c" 2>/dev/null || true
    done >> "$STATE/out/stats.jsonl"
    sleep 60
  done
}

canary () { # canary <container...>: counts only, never the matched text
  python3 "$HERE/canary.py" "$STATE" "$@"
}

analyze () { # analyze <outdir> <ledger> <src-container:src-mongo> <name:container:mongo=firstFetchISO>...
  local o=$1 l=$2 sc=${3%%:*} sm=${3#*:}; shift 3; local specs=()
  for x in "$@"; do local f=${x#*=} left=${x%%=*}; IFS=: read -r n c m <<<"$left"
    specs+=("$n=mongodb://$m:27017/${c//-/_}=$f"); done
  docker run --rm --network $NET -v "$HERE:/lab:ro" -v "$STATE:/state" -e NODE_PATH=/opt/app/node_modules \
    -e SOURCE="mongodb://$sm:27017/${sc//-/_}" -e SINKS="$(IFS=,; echo "${specs[*]}")" \
    -e LEDGER="/state/out/$l" -e SEEN_DIR="/state/out/$o" -e EXCLUDE="/state/out/$o/exclude.txt" \
    --entrypoint node "$BASE" /lab/analyze.js
}

disturb () { # disturb <outdir> <source> <source-mongo> <action>
  docker run --rm --network $NET -v "$HERE:/lab:ro" -v "$STATE:/state" -e NODE_PATH=/opt/app/node_modules \
    -e TARGET="http://$2:1337" -e SECRET_FILE="/state/secrets/$2" -e MONGO="mongodb://$3:27017/${2//-/_}" \
    -e OUT="/state/out/$1" --entrypoint node "$BASE" /lab/disturb.js "$4"
}

mongo_eval () { docker exec "$1" mongosh --quiet "$2" --eval "$3"; }

down () {
  for c in $(docker ps -a --format '{{.Names}}' | grep '^cksoak-'); do docker rm -f "$c" >/dev/null; done
  docker network rm $NET >/dev/null 2>&1 || true
}

cmd=${1:-help}; shift || true
case $cmd in
  build) build "$@" ;;
  up-main) up_main "$@" ;;
  add-k3) add_k3 "$@" ;;
  sampler) sampler "$@" ;;
  control) control "$@" ;;
  subject) subject "$@" ;;
  subjects) subjects "$@" ;;
  stats-loop) stats_loop ;;
  canary) canary "$@" ;;
  mongo-eval) mongo_eval "$@" ;;
  analyze) analyze "$@" ;;
  disturb) disturb "$@" ;;
  down) down ;;
  *) sed -n '2,25p' "$0" ;;
esac
