#!/usr/bin/env bash
# Quiet-host capacity campaign: each argument is <label>:<N>[:control], run in order.
# Per run: wait for a quiet host (1-minute load below CAP_QUIET, default 3, at most CAP_QUIET_WAIT s),
# deploy (startup), idle CAP_IDLE_S, real cadence CAP_LOAD_S with sockets and probe writes, the full
# restart (4 roles; then the edge, labelled), oracle, summary, teardown. `idleonly` stops after the
# idle window. `control` mounts the
# unbounded per-socket warm (realtime design control). The oracle break-it control runs on the first run.
#   campaign.sh r1:1000 r2:1000 ... ; env as cap.sh (source CAP_WORK/env.sh)
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
: "${CAP_WORK:?}"
QUIET=${CAP_QUIET:-3}; QUIET_WAIT=${CAP_QUIET_WAIT:-1800}
IDLE_S=${CAP_IDLE_S:-600}; LOAD_S=${CAP_LOAD_S:-900}
log() { echo "$(date -u +%FT%TZ) load=$(cut -d' ' -f1-3 /proc/loadavg) containers=$(docker ps -q | wc -l) $*" | tee -a "$CAP_WORK/campaign.log"; }
controlled=0
for spec in "$@"; do
  IFS=: read -r label N mode <<< "$spec"
  extra="$CAP_WORK/compose.stats.yaml"; [ "$mode" = control ] && extra="$extra:$CAP_WORK/compose.control-unbounded.yaml"
  # CAP_EXTRA_ADD: further Compose files for a labelled one-variable variant (e.g. an api pool size).
  [ -n "${CAP_EXTRA_ADD:-}" ] && extra="$extra:$CAP_EXTRA_ADD"
  waited=0
  until awk -v q="$QUIET" '{exit !($1 < q)}' /proc/loadavg || [ $waited -ge "$QUIET_WAIT" ]; do sleep 15; waited=$((waited+15)); done
  if awk -v q="$QUIET" '{exit !($1 < q)}' /proc/loadavg; then log "$label n$N quiet after ${waited}s"; else log "$label n$N NOT QUIET after ${waited}s; starting anyway"; fi
  dir="$CAP_WORK/$label-n$N"
  echo "waited_s=$waited quiet_threshold=$QUIET" > "$CAP_WORK/.quiet-$label-$N"
  { uptime; docker ps --format '{{.Names}}' | sort; } > "$CAP_WORK/.pre-$label-$N"
  export CAP_EXTRA="$extra"
  log "$label n$N deploy ($mode) config_max_bytes=${CAP_CONFIG_MAX_BYTES:-default} image=${CAP_IMAGE:-} socket_cap_per=${CAP_SOCKET_CAP_PER:-$(cat "$CAP_WORK/socket-cap-per" 2>/dev/null || echo default)} sockets_per=${CAP_SOCKETS_PER:-2} k6=$([ "${CAP_NO_K6:-}" = 1 ] && echo off || echo on) extra_add=${CAP_EXTRA_ADD:-none}"
  if ! "$here/cap.sh" deploy "$label" "$N" > "$CAP_WORK/$label-n$N.deploy.log" 2>&1; then
    log "$label n$N DEPLOY FAILED: $(tail -2 "$CAP_WORK/$label-n$N.deploy.log" | tr '\n' ' ')"
    "$here/cap.sh" teardown "$label" "$N" >/dev/null 2>&1; continue
  fi
  mv "$CAP_WORK/.quiet-$label-$N" "$dir/quiet.txt" 2>/dev/null; mv "$CAP_WORK/.pre-$label-$N" "$dir/host-pre-deploy.txt" 2>/dev/null
  log "$label n$N startup $(tail -1 "$CAP_WORK/$label-n$N.deploy.log" | cut -c1-300)"
  "$here/cap.sh" idle "$label" "$N" "$IDLE_S" >> "$CAP_WORK/$label-n$N.deploy.log" 2>&1; log "$label n$N idle done"
  if [ "$mode" = idleonly ]; then
    node "$here/summarize.js" "$dir" "$N" >> "$CAP_WORK/$label-n$N.deploy.log" 2>&1
    "$here/cap.sh" teardown "$label" "$N" >/dev/null 2>&1; log "$label n$N teardown (idle only)"; continue
  fi
  CAP_RESTART_EDGE=1 STOCK_MS=${STOCK_MS:-300000} RECOVERY_MS=${RECOVERY_MS:-120000} CAP_EVAL_TIMEOUT=${CAP_EVAL_TIMEOUT:-900} \
    "$here/cap.sh" load "$label" "$N" "$LOAD_S" >> "$CAP_WORK/$label-n$N.deploy.log" 2>&1
  log "$label n$N load+restart done: $(grep -E 'window|sockets|evalGap' "$dir/load/probe.log" | cut -c25-260 | tr '\n' ' ')"
  log "$label n$N oracle $("$here/cap.sh" oracle "$label" "$N" 2>&1 | tail -1)"
  if [ $controlled = 0 ] && [ "$mode" != control ]; then log "$label n$N oracle control $("$here/cap.sh" control "$label" "$N" 2>&1 | tail -1)"; controlled=1; fi
  node "$here/summarize.js" "$dir" "$N" >> "$CAP_WORK/$label-n$N.deploy.log" 2>&1
  for s in api realtime evaluator tenant-admin; do docker ps -a --filter "label=com.docker.compose.project=nscap-$label-n$N" --filter "label=com.docker.compose.service=$s" --format "$s {{.Status}}"; done > "$dir/final-state.txt"
  log "$label n$N final $(tr '\n' ';' < "$dir/final-state.txt")"
  "$here/cap.sh" teardown "$label" "$N" >/dev/null 2>&1; log "$label n$N teardown"
done
log "campaign done: $*"
