#!/usr/bin/env bash
# lab.sh - A/B soak harness for Nightscout (cgm-remote-monitor) itself.
#
# Two arms, each its own Nightscout process and its own MongoDB container,
# get the same synthetic traffic at the same moment (traffic.js). A sampler
# records liveness, freshness, RSS and document counts; a preload inside each
# server records heap and event-loop delay. analyze.js turns a run directory
# into a verdict: PASS, FAIL (findings listed) or INVALID (liveness not shown).
#
#   lab.sh run [opts]           up, compressed traffic, analyze, down (foreground)
#   lab.sh soak --hours N [opts] up, real-time traffic in the background; prints PIDs
#   lab.sh up [opts]            start mongo + both arms only (prints the run dir)
#   lab.sh traffic <run> [opts] start sampler + traffic against a run that is up
#   lab.sh disturb <run> mongo-restart|mongo-outage|server-restart [a|b|both]   (OUTAGE_SEC, default 60)
#   lab.sh analyze <run>        print the verdict (and write <run>/analysis.json)
#   lab.sh status <run>         PIDs, containers, last sample
#   lab.sh stop <run>           stop traffic, sampler, proxies and servers, each by its recorded PID
#   lab.sh down <run>           remove the run's mongo containers (after analyze)
#
# Options (run/soak/up/traffic):
#   --aa                both arms run build A (A/A control: expect zero diffs)
#   --minutes M         real minutes of traffic (compressed; default 45)
#   --sim-hours H       simulated hours those minutes cover (default 72)
#   --hours N           real-time mode, N hours (soak)
#   --config denied|readable   AUTH_DEFAULT_ROLES (default denied)
#   --fault-drop RATE   silently drop RATE of devicestatus POSTs to the fault arm
#   --fault-leak KB     the fault arm's server retains KB of heap per request
#   --fault-arm a|b     which arm gets the fault (default b)
#
# Environment (defaults in brackets):
#   SOAK_STATE   state root outside any git tree [${TMPDIR:-/tmp}/rc-soak]
#   ARM_A_DIR    build A worktree [externals/work/crm-6a-soak-a = 15.0.8]
#   ARM_B_DIR    build B worktree [externals/work/crm-6a-soak-b = candidate]
#   NODE_VER     node for the servers, via `n exec` [22.23.2]
#   MONGO_IMAGE  [mongo:7.0.43]; mongo:4.4 works too (use another PFX and ports)
#   PFX          container name prefix [s6a-soak]
#   MONGO_PORT_A/B [27531/27532]  NS_PORT_A/B [17531/17532]  PROXY_PORT_A/B [17533/17534]
#   SAMPLE_SEC   sampler interval [10 compressed, 60 real-time]
#
# Secrets: API_SECRET is generated per run into <run>/secrets (mode 700) and
# never printed. Synthetic data only: never point this at a real site.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
STATE=${SOAK_STATE:-${TMPDIR:-/tmp}/rc-soak}
ARM_A_DIR=${ARM_A_DIR:-$ROOT/externals/work/crm-6a-soak-a}
ARM_B_DIR=${ARM_B_DIR:-$ROOT/externals/work/crm-6a-soak-b}
NODE_VER=${NODE_VER:-22.23.2}
MONGO_IMAGE=${MONGO_IMAGE:-mongo:7.0.43}
PFX=${PFX:-s6a-soak}
MONGO_PORT_A=${MONGO_PORT_A:-27531}; MONGO_PORT_B=${MONGO_PORT_B:-27532}
NS_PORT_A=${NS_PORT_A:-17531}; NS_PORT_B=${NS_PORT_B:-17532}
PROXY_PORT_A=${PROXY_PORT_A:-17533}; PROXY_PORT_B=${PROXY_PORT_B:-17534}
export N_PREFIX=${N_PREFIX:-$HOME/n}

die () { echo "lab.sh: $*" >&2; exit 1; }
nodex () { n exec "$NODE_VER" node "$@"; }
port_free () { ! ss -ltnH "sport = :$1" | grep -q .; }
listener () { ss -ltnpH "sport = :$1" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }
is_ours () { [ -n "${1:-}" ] && [ -r "/proc/$1/cmdline" ] && tr '\0' ' ' < "/proc/$1/cmdline" | grep -q "$2"; }

parse () { # sets AA MINUTES SIMH HOURS CONFIG FDROP FLEAK FARM
  AA=0 MINUTES=45 SIMH=72 HOURS= CONFIG=denied FDROP=0 FLEAK=0 FARM=b
  while [ $# -gt 0 ]; do case $1 in
    --aa) AA=1 ;; --minutes) MINUTES=$2; shift ;; --sim-hours) SIMH=$2; shift ;; --hours) HOURS=$2; shift ;;
    --config) CONFIG=$2; shift ;; --fault-drop) FDROP=$2; shift ;; --fault-leak) FLEAK=$2; shift ;; --fault-arm) FARM=$2; shift ;;
    *) die "unknown option $1" ;; esac; shift; done
  case $CONFIG in denied|readable) ;; *) die "--config denied|readable" ;; esac
}

arm_dir () { if [ "$1" = a ] || [ "$(cat "$RUN/aa")" = 1 ]; then echo "$ARM_A_DIR"; else echo "$ARM_B_DIR"; fi; }
arm_port () { [ "$1" = a ] && echo "$NS_PORT_A" || echo "$NS_PORT_B"; }
arm_mport () { [ "$1" = a ] && echo "$MONGO_PORT_A" || echo "$MONGO_PORT_B"; }
arm_pport () { [ "$1" = a ] && echo "$PROXY_PORT_A" || echo "$PROXY_PORT_B"; }
mongo_url () { echo "mongodb://127.0.0.1:$(arm_mport "$1")/rcsoak_test"; }

mongo_up () { # mongo_up <arm>
  local name=$PFX-mongo-$1 port; port=$(arm_mport "$1")
  docker inspect "$name" >/dev/null 2>&1 && die "container $name exists (stop the earlier run first)"
  docker run -d --name "$name" --ulimit nofile=64000:64000 -p "127.0.0.1:$port:27017" --restart no "$MONGO_IMAGE" --quiet >/dev/null
  [ "$(docker inspect -f '{{.State.Running}}' "$name")" = true ] || die "$name is not running"
  echo "$name" >> "$RUN/containers"
  mongo_wait "$1"
}
mongo_wait () {
  for _ in $(seq 1 60); do
    if nodex -e "const{MongoClient}=require('$ARM_A_DIR/node_modules/mongodb');MongoClient.connect('$(mongo_url "$1")',{serverSelectionTimeoutMS:1500}).then(async c=>{const v=(await c.db().admin().serverInfo()).version;console.log(v);await c.close()}).catch(()=>process.exit(1))" > "$RUN/mongo-version-$1" 2>/dev/null; then return 0; fi
    sleep 1
  done
  die "mongo for arm $1 did not answer"
}

server_env () { # server_env <arm>: env file (mode 600) the launcher sources
  local f=$RUN/secrets/env-$1
  umask 077
  { echo "MONGODB_URI='$(mongo_url "$1")'"
    echo "API_SECRET='$(cat "$RUN/secrets/api_secret")'"
    echo "PORT='$(arm_port "$1")'"; echo "HOSTNAME='127.0.0.1'"; echo "INSECURE_USE_HTTP='true'"
    echo "AUTH_DEFAULT_ROLES='$(cat "$RUN/config")'"; echo "DISPLAY_UNITS='mg/dl'"; echo "TZ='UTC'"
    echo "ENABLE='careportal basal iob cob devicestatus profile loop openaps pump override boluscalc'"
    echo "ALARM_TYPES='simple'"; echo "ALARM_HIGH='off'"; echo "ALARM_LOW='off'"; echo "ALARM_URGENT_HIGH='off'"; echo "ALARM_URGENT_LOW='off'"
    echo "ALARM_TIMEAGO_WARN='off'"; echo "ALARM_TIMEAGO_URGENT='off'"
    echo "NODE_OPTIONS='--require $HERE/preload.js'"; echo "SOAK_METRICS='$RUN/metrics-$1.jsonl'"; echo "SOAK_METRICS_SEC='${METRICS_SEC:-10}'"
    if [ "$(cat "$RUN/fault_arm")" = "$1" ] && [ "$(cat "$RUN/fault_leak")" != 0 ]; then echo "SOAK_FAULT_LEAK_KB='$(cat "$RUN/fault_leak")'"; fi
  } > "$f"
}

server_start () { # server_start <arm>
  local dir port; dir=$(arm_dir "$1"); port=$(arm_port "$1")
  port_free "$port" || die "port $port is in use"
  server_env "$1"
  ( cd "$dir" && setsid nohup env -i PATH="$PATH" HOME="$HOME" N_PREFIX="$N_PREFIX" bash -c "set -a; . '$RUN/secrets/env-$1'; set +a; exec n exec '$NODE_VER' node lib/server/server.js" \
      < /dev/null >> "$RUN/server-$1.log" 2>&1 & )
  for _ in $(seq 1 120); do
    local st; st=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/v1/status.json" -H "api-secret: $(hash)" || true)
    if [ "$st" = 200 ]; then
      listener "$port" > "$RUN/pid-server-$1"
      is_ours "$(cat "$RUN/pid-server-$1")" lib/server/server.js || die "listener on $port is not a Nightscout server"
      echo "arm $1: $(git -C "$dir" rev-parse --short=8 HEAD) :$port pid $(cat "$RUN/pid-server-$1")"
      return 0
    fi
    sleep 1
  done
  tail -20 "$RUN/server-$1.log"; die "arm $1 did not come up"
}
server_stop () {
  local pid; pid=$(cat "$RUN/pid-server-$1" 2>/dev/null || true)
  if is_ours "$pid" lib/server/server.js; then kill "$pid"; for _ in $(seq 1 30); do [ -d "/proc/$pid" ] || break; sleep 0.5; done; echo "arm $1 server stopped (pid $pid)"; fi
}
hash () { printf %s "$(cat "$RUN/secrets/api_secret")" | sha1sum | cut -c1-40; }

proxy_start () { # proxy_start <arm> <rate>
  local p; p=$(arm_pport "$1"); port_free "$p" || die "port $p is in use"
  UPSTREAM="http://127.0.0.1:$(arm_port "$1")" PORT=$p DROP_RATE=$2 setsid nohup n exec "$NODE_VER" node "$HERE/proxy.js" < /dev/null > "$RUN/proxy-$1.log" 2>&1 &
  for _ in $(seq 1 30); do [ -n "$(listener "$p")" ] && break; sleep 0.5; done
  listener "$p" > "$RUN/pid-proxy-$1"
}

up () {
  parse "$@"
  local id; id=$(date -u +%Y%m%dT%H%M%SZ)-ab
  [ "$AA" = 1 ] && id=${id%-ab}-aa; [ "$FDROP" = 0 ] || id=$id-drop; [ "$FLEAK" = 0 ] || id=$id-leak; [ -z "$HOURS" ] || id=$id-${HOURS}h
  RUN=$STATE/runs/$id; mkdir -p "$RUN/secrets"; chmod 700 "$RUN/secrets"
  ( umask 077; openssl rand -hex 24 > "$RUN/secrets/api_secret" )
  echo "$AA" > "$RUN/aa"; echo "$CONFIG" > "$RUN/config"; echo "$FARM" > "$RUN/fault_arm"; echo "$FLEAK" > "$RUN/fault_leak"; echo "$FDROP" > "$RUN/fault_drop"
  : > "$RUN/containers"
  for p in "$MONGO_PORT_A" "$MONGO_PORT_B" "$NS_PORT_A" "$NS_PORT_B"; do port_free "$p" || die "port $p is in use"; done
  [ -d "$ARM_A_DIR/node_modules" ] && [ -d "$ARM_B_DIR/node_modules" ] || die "npm ci both worktrees first"
  mongo_up a; mongo_up b
  server_start a; server_start b
  local ha hb; ha=$(git -C "$(arm_dir a)" rev-parse HEAD); hb=$(git -C "$(arm_dir b)" rev-parse HEAD)
  local ta tb; ta=$(git -C "$(arm_dir a)" rev-parse 'HEAD^{tree}'); tb=$(git -C "$(arm_dir b)" rev-parse 'HEAD^{tree}')
  local dirty_a dirty_b; dirty_a=$(git -C "$(arm_dir a)" status --porcelain --untracked-files=no | wc -l); dirty_b=$(git -C "$(arm_dir b)" status --porcelain --untracked-files=no | wc -l)
  cat > "$RUN/run.json" <<EOF
{"id":"$id","aa":$AA,"config":"$CONFIG","node":"$(nodex -v)","mongo_image":"$MONGO_IMAGE",
 "mongo_version":{"a":"$(cat "$RUN/mongo-version-a")","b":"$(cat "$RUN/mongo-version-b")"},
 "arms":{"a":{"dir":"$(arm_dir a)","head":"$ha","tree":"$ta","dirty_tracked_files":$dirty_a,"version":"$(nodex -p "require('$(arm_dir a)/package.json').version")"},
         "b":{"dir":"$(arm_dir b)","head":"$hb","tree":"$tb","dirty_tracked_files":$dirty_b,"version":"$(nodex -p "require('$(arm_dir b)/package.json').version")"}},
 "mongo_url":{"a":"$(mongo_url a)","b":"$(mongo_url b)"},"ports":{"a":$NS_PORT_A,"b":$NS_PORT_B},
 "fault":{"arm":"$FARM","drop_devicestatus":$FDROP,"leak_kb":$FLEAK}}
EOF
  if [ "$FDROP" != 0 ]; then
    proxy_start a "$([ "$FARM" = a ] && echo "$FDROP" || echo 0)"; proxy_start b "$([ "$FARM" = b ] && echo "$FDROP" || echo 0)"
    echo "http://127.0.0.1:$PROXY_PORT_A" > "$RUN/http-a"; echo "http://127.0.0.1:$PROXY_PORT_B" > "$RUN/http-b"
  else
    echo "http://127.0.0.1:$NS_PORT_A" > "$RUN/http-a"; echo "http://127.0.0.1:$NS_PORT_B" > "$RUN/http-b"
  fi
  ln -sfn "$RUN" "$STATE/current"
  echo "run: $RUN"
}

traffic () { # traffic <run> [opts]
  RUN=$(readlink -f "$1"); shift; parse "$@"
  local mode=() si=${SAMPLE_SEC:-10}
  if [ -n "$HOURS" ]; then mode=(REALTIME=1 HOURS="$HOURS"); si=${SAMPLE_SEC:-60}; else mode=(DURATION_MIN="$MINUTES" SIM_HOURS="$SIMH"); fi
  local arms_t="a=$(cat "$RUN/http-a")|http://127.0.0.1:$NS_PORT_A|$RUN/secrets/api_secret,b=$(cat "$RUN/http-b")|http://127.0.0.1:$NS_PORT_B|$RUN/secrets/api_secret"
  local arms_s="a=http://127.0.0.1:$NS_PORT_A|$(mongo_url a)|$RUN/secrets/api_secret|$RUN/pid-server-a,b=http://127.0.0.1:$NS_PORT_B|$(mongo_url b)|$RUN/secrets/api_secret|$RUN/pid-server-b"
  rm -f "$RUN/pid-traffic" "$RUN/pid-sampler"
  env RUN="$RUN" ARMS="$arms_s" MODULES="$ARM_A_DIR/node_modules" INTERVAL_SEC="$si" \
    setsid nohup n exec "$NODE_VER" node "$HERE/sampler.js" < /dev/null > "$RUN/sampler.log" 2>&1 &
  env RUN="$RUN" ARMS="$arms_t" MODULES="$ARM_A_DIR/node_modules" "${mode[@]}" \
    setsid nohup n exec "$NODE_VER" node "$HERE/traffic.js" < /dev/null > "$RUN/traffic.out" 2>&1 &
  for _ in $(seq 1 30); do [ -s "$RUN/pid-traffic" ] && [ -s "$RUN/pid-sampler" ] && break; sleep 0.5; done  # each writes its own PID
  is_ours "$(cat "$RUN/pid-traffic")" traffic.js || { cat "$RUN/traffic.out"; die "traffic did not start"; }
  echo "traffic pid $(cat "$RUN/pid-traffic"), sampler pid $(cat "$RUN/pid-sampler")"
}

wait_traffic () {
  local pid; pid=$(cat "$RUN/pid-traffic")
  while is_ours "$pid" traffic.js; do sleep 5; done
  [ -s "$RUN/done.json" ] || { tail -5 "$RUN/traffic.log" 2>/dev/null; echo "traffic exited without done.json" >&2; }
}

stop_run () { # stop <run>: traffic, sampler, proxies, servers, by recorded PID; containers stay for analyze
  RUN=$(readlink -f "$1")
  local p
  for f in traffic sampler; do p=$(cat "$RUN/pid-$f" 2>/dev/null || true); if is_ours "$p" "$f.js"; then kill "$p"; echo "$f stopped (pid $p)"; fi; done
  p=$(cat "$RUN/pid-traffic" 2>/dev/null || true); for _ in $(seq 1 60); do is_ours "$p" traffic.js || break; sleep 1; done
  for a in a b; do p=$(cat "$RUN/pid-proxy-$a" 2>/dev/null || true); if is_ours "$p" proxy.js; then kill "$p"; echo "proxy $a stopped (pid $p)"; fi; done
  server_stop a; server_stop b
}
down_run () { # down <run>: remove the containers this run created
  RUN=$(readlink -f "$1")
  while read -r c; do [ -n "$c" ] && docker rm -f "$c" >/dev/null 2>&1 && echo "removed container $c"; done < "$RUN/containers"
  : > "$RUN/containers"
}

disturb () { # disturb <run> <action> [a|b|both]
  RUN=$(readlink -f "$1"); local action=$2 which=${3:-both} arms t0
  [ "$which" = both ] && arms="a b" || arms=$which
  t0=$(date -u +%FT%T.%3NZ)
  case $action in
    mongo-restart) for a in $arms; do docker restart "$PFX-mongo-$a" >/dev/null & done; wait; for a in $arms; do mongo_wait "$a"; done ;;
    mongo-outage) # the database is gone for OUTAGE_SEC (default 60) seconds, then comes back
      for a in $arms; do docker stop "$PFX-mongo-$a" >/dev/null & done; wait; sleep "${OUTAGE_SEC:-60}"
      for a in $arms; do docker start "$PFX-mongo-$a" >/dev/null; done; for a in $arms; do mongo_wait "$a"; done ;;
    server-restart) for a in $arms; do server_stop "$a"; done; for a in $arms; do server_start "$a"; done ;;
    *) die "disturb mongo-restart|mongo-outage|server-restart [a|b|both]" ;;
  esac
  echo "{\"action\":\"$action\",\"arms\":\"$which\",\"start\":\"$t0\",\"end\":\"$(date -u +%FT%T.%3NZ)\"}" >> "$RUN/disturb.jsonl"
  echo "disturb $action ($which): $t0 .. $(date -u +%FT%TZ)"
}

analyze () { RUN=$(readlink -f "$1"); local rc=0; RUN="$RUN" nodex "$HERE/analyze.js" > "$RUN/analysis.txt" || rc=$?; cat "$RUN/analysis.txt"; return "$rc"; }

status () {
  RUN=$(readlink -f "$1")
  for f in traffic sampler; do local p; p=$(cat "$RUN/pid-$f" 2>/dev/null || true); echo "$f pid ${p:-none} $(is_ours "$p" "$f.js" && echo running || echo stopped)"; done
  for a in a b; do local p; p=$(cat "$RUN/pid-server-$a" 2>/dev/null || true); echo "server $a pid ${p:-none} $(is_ours "$p" lib/server/server.js && echo running || echo stopped)"; done
  while read -r c; do [ -n "$c" ] && echo "container $c running=$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null || echo gone)"; done < "$RUN/containers"
  [ -s "$RUN/state.json" ] && cat "$RUN/state.json" && echo
}

cmd=${1:-help}; shift || true
case $cmd in
  up) up "$@" ;;
  traffic) traffic "$@" ;;
  run) up "$@"; traffic "$RUN" "$@"; wait_traffic; sleep 2; stop_run "$RUN"; rc=0; analyze "$RUN" || rc=$?
       [ "${KEEP:-0}" = 1 ] || down_run "$RUN"
       exit "$rc" ;;
  soak) parse "$@"; [ -n "$HOURS" ] || die "soak needs --hours N"; up "$@"; traffic "$RUN" "$@"
        echo "soak running for $HOURS h. Afterwards (or to stop early): $0 stop $RUN; $0 analyze $RUN; $0 down $RUN" ;;
  disturb) disturb "$@" ;;
  analyze) analyze "$@" ;;
  status) status "$@" ;;
  stop) stop_run "$@" ;;
  down) down_run "$@" ;;
  *) sed -n '2,40p' "$0" ;;
esac
