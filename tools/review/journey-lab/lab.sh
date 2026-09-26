#!/usr/bin/env bash
# Journey lab: Nightscout sites set up the way a Loop, Trio or AndroidAPS user sets them up, for a
# person to walk the user journeys (docs/60-research/remedial/journey-map-15.0.9.md) by hand in a
# browser while this script plays the phone. Synthetic data only; not medical advice.
#
#   lab.sh prep                    npm ci in LAB_RC (and LAB_REF if set), once
#   lab.sh up [--ref] [name...]    fresh site(s): drop the database, boot, seed (report sites backfill)
#   lab.sh fire <name> <step> [args]   play one app action (lab.sh fire <name> help lists them)
#   lab.sh urls                    what to open, with the lab's tokens
#   lab.sh status <name>           what that site holds now
#   lab.sh apns                    every push "the phone" received (Loop remote commands)
#   lab.sh share [n]               the last n requests the connector made to the fake Dexcom Share server (cgm-* sites)
#   lab.sh live <name>|stop <name> keep that site's phone uploading every 5 minutes (a reading, device
#                                  status, doses), so pages don't go stale and alarm; `live stop <name>` ends it
#   lab.sh down                    stop everything and remove the database container
#
# Env: LAB_RC      worktree under test (required; the 15.0.9 candidate)
#      LAB_REF     a 15.0.8 worktree, for `up --ref <name>` (runs the same site on 15.0.8, port +50)
#      LAB_STATE   logs, generated API secret, per-site state (default ./journey-lab-state; keep it
#                  outside any git tree: it holds the secret and tokens)
#      LAB_TZ      the person's time zone for profiles and meal times (default: this machine's)
# Needs docker (mongo:7), n with node 22.22.0, curl, openssl.
set -euo pipefail
LAB=$(cd "$(dirname "$0")" && pwd)
H=$LAB/../probes/w2-instance.sh
RC=${LAB_RC:?set LAB_RC to the worktree under test}
REF=${LAB_REF:-}
export W2_STATE=${LAB_STATE:-$PWD/journey-lab-state} W2_MONGO_CONTAINER=${LAB_MONGO_CONTAINER:-ns-journey-lab} W2_MONGO_PORT=${LAB_MONGO_PORT:-27095}
export LAB_STATE=$W2_STATE LAB_SECRET_FILE=$W2_STATE/secret
export LAB_TZ=${LAB_TZ:-$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo UTC)}
NODE_VER=${W2_NODE:-22.22.0}
APNS_PORT=${LAB_APNS_PORT:-17601}
SHARE_PORT=${LAB_SHARE_PORT:-17602}
mkdir -p "$W2_STATE"

# Flag sets: what each app's setup guide asks for (Nightscout README plugin sections; release notes
# recommend AUTH_DEFAULT_ROLES=denied). '+' stands for a space inside a value.
COMMON="careportal+basal+iob+cob+bwp+boluscalc+pump+profile+sage+cage+iage+bage"
PUMP="PUMP_FIELDS=reservoir+battery+clock+status"
LOOP_FLAGS="ENABLE=$COMMON+loop+override SHOW_PLUGINS=careportal+boluscalc+loop+pump+override+iob+cob+sage+cage+iage+bage $PUMP"
OREF_FLAGS="ENABLE=$COMMON+openaps SHOW_PLUGINS=careportal+boluscalc+openaps+pump+iob+cob+sage+cage+iage+bage $PUMP"

# name ; kind ; variant ; port ; units ; backfill days at `up` (0 = empty site) ; flags
declare -A I=(
  [loop]="loop;;15301;mg/dl;0;$LOOP_FLAGS"
  [trio]="trio;;15302;mg/dl;0;$OREF_FLAGS"
  [aaps]="aaps;v3-34;15303;mmol;0;$OREF_FLAGS"
  [aaps-v1]="aaps;v1-34;15304;mg/dl;0;$OREF_FLAGS"
  [aaps40]="aaps;v3-40;15305;mg/dl;0;$OREF_FLAGS"
  [cp-loop]="loop;;15311;mg/dl;0;$LOOP_FLAGS"
  [cp-trio]="trio;;15312;mg/dl;0;$OREF_FLAGS"
  [cp-aaps]="aaps;v3-34;15313;mmol;0;$OREF_FLAGS"
  [rep-loop]="loop;;15321;mg/dl;14;$LOOP_FLAGS"
  [rep-trio]="trio;;15322;mg/dl;14;$OREF_FLAGS"
  [rep-aaps]="aaps;v3-34;15323;mmol;14;$OREF_FLAGS"
  [rep-90]="trio;;15324;mg/dl;90;$OREF_FLAGS"
  [cgm-loop]="loop;;15331;mg/dl;0;${LOOP_FLAGS/ENABLE=/ENABLE=connect+}"
  [cgm-trio]="trio;;15332;mg/dl;0;${OREF_FLAGS/ENABLE=/ENABLE=connect+}"
  [cgm-aaps]="aaps;v3-34;15333;mmol;0;${OREF_FLAGS/ENABLE=/ENABLE=connect+}"
)
ORDER=(loop trio aaps aaps-v1 aaps40 cp-loop cp-trio cp-aaps rep-loop rep-trio rep-aaps rep-90 cgm-loop cgm-trio cgm-aaps)

parse() { # parse <name> [ref]  -> kind variant port units days envs[] wt
  local base=${1%-1508}
  [ -n "${I[$base]:-}" ] || { echo "no site $1 (sites: ${ORDER[*]})"; exit 2; }
  IFS=';' read -r kind variant port units days flags <<<"${I[$base]}"
  wt=$RC
  if [ "$1" != "$base" ]; then wt=${REF:?LAB_REF is not set}; port=$((port + 50)); fi
  envs=("DISPLAY_UNITS=$units" "NODE_OPTIONS=--require $LAB/preload.js")
  for kv in $flags; do envs+=("${kv//+/ }"); done
  if [[ "$flags" == *connect* ]]; then # CGM first: the real nightscout-connect Dexcom driver, pointed at fake-share.js
    envs+=("CONNECT_SOURCE=dexcomshare" "CONNECT_SHARE_ACCOUNT_NAME=${1%-1508}" "CONNECT_SHARE_PASSWORD=lab-synthetic-not-a-secret"
           "CONNECT_SHARE_SERVER=localhost:$SHARE_PORT" "NODE_EXTRA_CA_CERTS=$W2_STATE/share.crt")
  fi
  if [ "$kind" = loop ]; then
    envs+=("LOOP_APNS_KEY=$(cat "$W2_STATE/apns_key.pem")" "LOOP_APNS_KEY_ID=LABKEYID01" "LOOP_DEVELOPER_TEAM_ID=LABTEAM001"
           "LOOP_PUSH_SERVER_ENVIRONMENT=development" "LAB_APNS_PORT=$APNS_PORT")
  fi
}
jenv() { # environment for journey.js
  local cgm=; [[ "$flags" == *connect* ]] && cgm=connect
  env LAB_CGM="$cgm" LAB_URL="http://127.0.0.1:$port" LAB_KIND="$kind" LAB_VARIANT="$variant" LAB_UNITS="$units" LAB_MODULES="$wt/node_modules" \
    N_PREFIX="${N_PREFIX:-$HOME/n}" n exec "$NODE_VER" node "$LAB/journey.js" "$@"
}

mongo_up() {
  docker inspect "$W2_MONGO_CONTAINER" >/dev/null 2>&1 || \
    docker run -d --name "$W2_MONGO_CONTAINER" --ulimit nofile=64000:64000 -p 127.0.0.1:$W2_MONGO_PORT:27017 mongo:7 >/dev/null
  for _ in $(seq 1 60); do docker exec "$W2_MONGO_CONTAINER" mongosh --quiet --eval 1 >/dev/null 2>&1 && return; sleep 0.5; done
}
apns_up() {
  [ -f "$W2_STATE/apns_key.pem" ] || ( umask 077; openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt > "$W2_STATE/apns_key.pem" )
  local p; p=$(cat "$W2_STATE/pid-apns" 2>/dev/null || true)
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then return; fi
  PORT=$APNS_PORT TREE="$RC" OUT="$W2_STATE/apns.jsonl" PIDFILE="$W2_STATE/pid-apns" \
    setsid nohup n exec "$NODE_VER" node "$LAB/apns-log.js" </dev/null >"$W2_STATE/apns.log" 2>&1 &
  sleep 1
}

share_up() {
  [ -f "$W2_STATE/share.crt" ] || ( umask 077; openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 30 \
      -subj /CN=localhost -addext subjectAltName=DNS:localhost,IP:127.0.0.1 -keyout "$W2_STATE/share.key" -out "$W2_STATE/share.crt" 2>/dev/null )
  local p; p=$(cat "$W2_STATE/pid-share" 2>/dev/null || true)
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then return; fi
  PORT=$SHARE_PORT CERT="$W2_STATE/share.crt" KEY="$W2_STATE/share.key" OUT="$W2_STATE/share.jsonl" PIDFILE="$W2_STATE/pid-share" LAB_TZ="$LAB_TZ" \
    setsid nohup n exec "$NODE_VER" node "$LAB/fake-share.js" </dev/null >"$W2_STATE/share.log" 2>&1 &
  sleep 1
}

up() {
  local names=() ref=0
  for a in "$@"; do [ "$a" = --ref ] && ref=1 || names+=("$a"); done
  [ ${#names[@]} -eq 0 ] && names=("${ORDER[@]}")
  mongo_up; apns_up; share_up
  for n in "${names[@]}"; do
    [ $ref = 1 ] && n="$n-1508"
    parse "$n"
    echo "== $n  ($kind${variant:+ $variant}, $units, :$port${days:+, backfill ${days} d})"
    rm -f "$W2_STATE/$n.json"
    $H reset "$n" "$wt" "$port" "journey_${n//-/_}" denied "${envs[@]}" | sed 's/^/  /'
    if [ "$days" != 0 ]; then
      jenv "$n" connect >/dev/null 2>&1 || true
      jenv "$n" onboard
      jenv "$n" backfill $((days * 24)) || { echo "  !! backfill failed for $n"; exit 1; }
      jenv "$n" share
    fi
  done
}

fire() { local n=$1; shift; parse "$n"; jenv "$n" "$@"; }

urls() {
  echo "Every site is AUTH_DEFAULT_ROLES=denied. Log in with the API secret: it is in $W2_STATE/secret (not printed here)."
  for n in "${ORDER[@]}" $(cd "$W2_STATE" && ls *-1508.json 2>/dev/null | sed 's/\.json$//'); do
    parse "$n"
    printf '%-10s http://127.0.0.1:%s/   (%s%s, %s)\n' "$n" "$port" "$kind" "${variant:+ $variant}" "$units"
    [ -f "$W2_STATE/$n.json" ] && node -e '
      const s=require(process.argv[1]); for (const [k,v] of Object.entries(s.tokens||{})) if (k!=="app") console.log("           "+k.padEnd(15)+" ?token="+v);' "$W2_STATE/$n.json"
  done
}

live() {
  if [ "$1" = stop ]; then local p; p=$(cat "$W2_STATE/pid-live-$2" 2>/dev/null || true); [ -n "$p" ] && { pkill -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; }; rm -f "$W2_STATE/pid-live-$2"; echo "live $2 stopped"; return; fi
  local n=$1; parse "$n"
  [ -f "$W2_STATE/pid-live-$n" ] && kill -0 "$(cat "$W2_STATE/pid-live-$n")" 2>/dev/null && { echo "live $n already running"; return; }
  ( trap 'exit 0' TERM; while true; do jenv "$n" tick >>"$W2_STATE/live-$n.log" 2>&1; sleep 300; done ) </dev/null >/dev/null 2>&1 &
  echo $! > "$W2_STATE/pid-live-$n"; disown; echo "live $n: a phone cycle every 5 min (log $W2_STATE/live-$n.log)"
}

share() { [ -f "$W2_STATE/share.jsonl" ] && tail -n "${1:-20}" "$W2_STATE/share.jsonl" || echo "no Share requests yet"; }
apns() { [ -f "$W2_STATE/apns.jsonl" ] && tail -n "${1:-20}" "$W2_STATE/apns.jsonl" || echo "no pushes yet"; }

down() {
  for f in "$W2_STATE"/pid-live-*; do [ -f "$f" ] && { pkill -P "$(cat "$f")" 2>/dev/null; kill "$(cat "$f")" 2>/dev/null; rm -f "$f"; }; done
  for n in "${ORDER[@]}"; do $H stop "$n" >/dev/null; $H stop "$n-1508" >/dev/null; done
  local p; for f in pid-apns pid-share; do p=$(cat "$W2_STATE/$f" 2>/dev/null || true); [ -n "$p" ] && kill "$p" 2>/dev/null || true; done
  docker rm -f "$W2_MONGO_CONTAINER" >/dev/null 2>&1 || true; echo down
}

prep() { $H prep "$RC"; [ -n "$REF" ] && $H prep "$REF"; true; }

cmd=${1:-}; shift || true
case "$cmd" in
  prep) prep ;; up) up "$@" ;; fire) fire "$@" ;; urls) urls ;; status) fire "$1" status ;; apns) apns "$@" ;; share) share "$@" ;; live) live "$@" ;; down) down ;;
  *) sed -n '2,21p' "$0" | sed 's/^# \?//'; exit 1 ;;
esac
