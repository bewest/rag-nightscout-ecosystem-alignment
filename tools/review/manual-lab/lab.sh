#!/usr/bin/env bash
# Manual-check lab: one seeded Nightscout per scenario, for a person to verify in a browser.
# First used 2026-09-23 on the 15.0.9 combined rc ec70aab0; see
# docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md.
#   lab.sh up [name...]       reset + boot + seed (all when no name)
#   lab.sh fire <name> <step> trigger a step (e.g. alarm urgent)
#   lab.sh urls               print what to open (includes the lab's access tokens)
#   lab.sh down               stop every instance and remove the database container
# Env: LAB_RC (worktree under test, required), LAB_REF (a 15.0.8 worktree, for drag-1508),
#      LAB_STATE (logs, generated API secret, seed output; default ./manual-lab-state).
# Worktrees need `w2-instance.sh prep` first. Synthetic data only.
set -euo pipefail
LAB=$(cd "$(dirname "$0")" && pwd)
H=$LAB/../probes/w2-instance.sh
RC=${LAB_RC:?set LAB_RC to the worktree under test}
REF=${LAB_REF:-}
export W2_STATE=${LAB_STATE:-$PWD/manual-lab-state} W2_MONGO_CONTAINER=${LAB_MONGO_CONTAINER:-ns-lab-manual} W2_MONGO_PORT=${LAB_MONGO_PORT:-27094}
export LAB_SECRET_FILE=$W2_STATE/secret
NODE="n exec 22.22.0 node"

BASE="careportal+basal+iob+cob+bwp"
# name ; worktree ; port ; roles ; seed scenario ; extra env (space-separated VAR=val, '+' stands for a space in a value)
declare -A I=(
  [drag]="$RC;15201;denied;drag;"
  [drag-mmol]="$RC;15202;denied;drag;DISPLAY_UNITS=mmol"
  [drag-1508]="$REF;15203;denied;drag;"
  [alarm]="$RC;15211;denied;alarm;ALARM_TYPES=simple BG_LOW=55 BG_TARGET_BOTTOM=80"
  [alarm-prompt]="$RC;15212;denied;alarm;ALARM_TYPES=simple BG_LOW=55 BG_TARGET_BOTTOM=80 AUTHENTICATION_PROMPT_ON_LOAD=true"
  [noreading]="$RC;15221;readable;noreading;ENABLE=$BASE+pump PUMP_ENABLE_ALERTS=true PUMP_FIELDS=reservoir"
  [quickpick]="$RC;15231;denied;quickpick;ENABLE=$BASE+boluscalc+food SHOW_PLUGINS=careportal+boluscalc"
  [empty]="$RC;15241;readable;empty;"
  [cob]="$RC;15251;readable;cob;ENABLE=$BASE+openaps+loop+sage+cage DEVICESTATUS_ADVANCED=true SHOW_PLUGINS=openaps+loop+cob+iob+sage+cage"
)
ORDER=(drag drag-mmol drag-1508 alarm alarm-prompt noreading quickpick empty cob)

parse() {
  IFS=';' read -r wt port roles scen extra <<<"${I[$1]}"
  envs=()
  for kv in $extra; do envs+=("${kv//+/ }"); done
}

mongo_up() {
  docker inspect "$W2_MONGO_CONTAINER" >/dev/null 2>&1 || \
    docker run -d --name "$W2_MONGO_CONTAINER" --ulimit nofile=64000:64000 -p 127.0.0.1:$W2_MONGO_PORT:27017 mongo:7 >/dev/null
  for _ in $(seq 1 60); do docker exec "$W2_MONGO_CONTAINER" mongosh --quiet --eval 1 >/dev/null 2>&1 && return; sleep 0.5; done
}

up() {
  mongo_up
  local names=("$@"); [ ${#names[@]} -eq 0 ] && names=("${ORDER[@]}")
  for n in "${names[@]}"; do
    parse "$n"
    [ -z "$wt" ] && { echo "== $n skipped (LAB_REF unset)"; continue; }
    echo "== $n"
    $H reset "$n" "$wt" "$port" "lab_${n//-/_}" "$roles" "${envs[@]}" | sed 's/^/  /'
    $NODE "$LAB/seed.js" "http://127.0.0.1:$port" "$scen" | tee "$W2_STATE/$n.seed"
  done
}

fire() { parse "$1"; $NODE "$LAB/seed.js" "http://127.0.0.1:$port" "$scen" "$2"; }

urls() {
  for n in "${ORDER[@]}"; do
    parse "$n"; local tok
    tok=$(grep -m1 -oE 'token +[a-z0-9-]+' "$W2_STATE/$n.seed" 2>/dev/null | awk '{print $2}' || true)
    printf '%-13s http://127.0.0.1:%s/%s\n' "$n" "$port" "${tok:+?token=$tok}"
    grep -E 'token|status-only' "$W2_STATE/$n.seed" 2>/dev/null | sed 's/^/                /' || true
  done
}

down() { for n in "${ORDER[@]}"; do $H stop "$n" >/dev/null; done; docker rm -f "$W2_MONGO_CONTAINER" >/dev/null 2>&1 || true; echo down; }

cmd=${1:-}; shift || true
case "$cmd" in up) up "$@" ;; fire) fire "$@" ;; urls) urls ;; down) down ;; *) sed -n '2,6p' "$0"; exit 1 ;; esac
