#!/usr/bin/env bash
# nsctl.sh — lifecycle for concurrent Nightscout review instances.
#
# One scratch clone, one private node_modules, one worktree + database + port
# per state. Every instance carries a RUN ID; nsctl refuses to touch anything
# that does not carry its own.
#
# Four hazards this exists to handle, all measured 2026-09-17 (see
# docs/30-design/remedial/dev-cycle-review-harness-plan-2026-09-17.md §3):
#
#   1. Servers launched as plain background children DIE WITH THE INVOKING
#      SHELL. Everything starts under setsid with stdin from /dev/null.
#   2. `echo $!` after `( ... & )` records the SUBSHELL, not node. PIDs are
#      discovered by querying the bound port, never from $!.
#   3. A shared node_modules symlink target MUST ITSELF BE NAMED node_modules,
#      or Node resolves to the realpath, finds no node_modules to walk up into,
#      and dies with `Cannot find module 'jws'` while require.resolve still
#      succeeds. The private tree is therefore <root>/deps/node_modules.
#   4. Killing by PID is not enough when PID discovery is by port or cwd —
#      that reached sibling agents' servers. Every child is stamped with
#      NSREVIEW_RUN_ID and nothing without a matching stamp is ever killed.
#
# Usage:
#   nsctl.sh init                    create clone + private deps (slow, once)
#   nsctl.sh add   <state> <ref>     add a worktree for a committish
#   nsctl.sh start <state> [mode]    boot detached; mode=development|production
#   nsctl.sh reset <state> [mode]    stop, DROP the database, start — the only
#                                    safe way to re-seed (see cmd_reset)
#   nsctl.sh stop  <state>|--all
#   nsctl.sh status
#   nsctl.sh url   <state>
#   nsctl.sh exec  <state> -- <cmd>  run a command inside a state's worktree
#
# Env:
#   NSREVIEW_ROOT      scratch root (default: alongside this repo's scratchpad)
#   NS_HARNESS_SECRET  API secret for every instance; generated on init if unset
#   NSREVIEW_MONGO     mongo host:port (default 127.0.0.1:27099, container managed here)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SOURCE_REPO="$REPO_ROOT/externals/cgm-remote-monitor-official"

: "${NSREVIEW_ROOT:=${TMPDIR:-/tmp}/nsreview}"
: "${NSREVIEW_MONGO:=127.0.0.1:27099}"
MONGO_CONTAINER="nsreview-mongo"
PORT_BASE=14100

RUN="$NSREVIEW_ROOT/run"
STATES="$NSREVIEW_ROOT/states"
DEPS="$NSREVIEW_ROOT/deps/node_modules"   # hazard 3: the target is named node_modules
CLONE="$NSREVIEW_ROOT/repo"
RUNID_FILE="$NSREVIEW_ROOT/run-id"

log()  { printf '\033[0;36m[nsctl]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[0;31m[nsctl] %s\033[0m\n' "$*" >&2; exit 1; }

run_id() {
  [ -f "$RUNID_FILE" ] || die "not initialised — run: nsctl.sh init"
  cat "$RUNID_FILE"
}

# ---------------------------------------------------------------- port helpers

port_for() {  # deterministic per state name, then probed for availability
  local state="$1" h
  h=$(printf '%s' "$state" | cksum | cut -d' ' -f1)
  local p=$(( PORT_BASE + (h % 400) ))
  while ss -ltn "( sport = :$p )" 2>/dev/null | grep -q LISTEN; do p=$((p+1)); done
  echo "$p"
}

pid_on_port() {  # hazard 2: ask the kernel who holds the port
  ss -ltnp "( sport = :$1 )" 2>/dev/null \
    | grep -oP 'pid=\K[0-9]+' | head -1
}

# a pid is ours only if its environ carries our run id (hazard 4)
pid_is_ours() {
  local pid="$1" want; want="$(run_id)"
  [ -r "/proc/$pid/environ" ] || return 1
  tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null \
    | grep -qx "NSREVIEW_RUN_ID=$want"
}

# ---------------------------------------------------------------- mongo

mongo_up() {
  if docker ps --format '{{.Names}}' | grep -qx "$MONGO_CONTAINER"; then return 0; fi
  if docker ps -a --format '{{.Names}}' | grep -qx "$MONGO_CONTAINER"; then
    log "starting existing $MONGO_CONTAINER"; docker start "$MONGO_CONTAINER" >/dev/null;
  else
    log "creating $MONGO_CONTAINER on ${NSREVIEW_MONGO##*:}"
    # --ulimit nofile: BF-10, mongod fatal-asserts at Docker's default 1024
    docker run -d --name "$MONGO_CONTAINER" \
      -p "${NSREVIEW_MONGO##*:}:27017" \
      --ulimit nofile=64000:64000 \
      mongo:7 >/dev/null
  fi
  for _ in $(seq 1 40); do
    docker exec "$MONGO_CONTAINER" mongosh --quiet --eval 'db.runCommand({ping:1}).ok' 2>/dev/null | grep -q 1 && return 0
    sleep 0.5
  done
  die "mongo did not become ready"
}

# ---------------------------------------------------------------- init

cmd_init() {
  mkdir -p "$NSREVIEW_ROOT" "$RUN" "$STATES" "$(dirname "$DEPS")"
  if [ ! -f "$RUNID_FILE" ]; then
    printf 'nsreview-%s-%s' "$(date +%Y%m%d-%H%M%S)" "$$" > "$RUNID_FILE"
    log "run id $(cat "$RUNID_FILE")"
  fi
  if [ -z "${NS_HARNESS_SECRET:-}" ]; then
    if [ ! -f "$NSREVIEW_ROOT/secret" ]; then
      head -c 18 /dev/urandom | base64 | tr -d '/+=' > "$NSREVIEW_ROOT/secret"
      chmod 600 "$NSREVIEW_ROOT/secret"
    fi
    log "using generated secret at \$NSREVIEW_ROOT/secret (not committed)"
  fi

  [ -d "$SOURCE_REPO/.git" ] || die "no source repo at $SOURCE_REPO"
  if [ ! -d "$CLONE/.git" ]; then
    log "cloning (local, shared objects) …"
    git clone --shared --no-checkout "$SOURCE_REPO" "$CLONE" >/dev/null 2>&1
    # the source's own origin/dev is 810 commits stale; pin by SHA only
    git -C "$CLONE" fetch --quiet "$SOURCE_REPO" '+refs/heads/*:refs/heads/*' 2>/dev/null || true
  fi

  if [ ! -d "$DEPS" ]; then
    local donor
    donor="$(ls -d "$REPO_ROOT"/externals/work/crm-*/node_modules 2>/dev/null | head -1)"
    [ -n "$donor" ] || die "no donor node_modules found to seed private deps"
    log "copying private node_modules from $(dirname "$donor") (~267M, once) …"
    cp -a "$(readlink -f "$donor")" "$DEPS"
  fi
  log "init complete: $NSREVIEW_ROOT"
}

secret() {
  if [ -n "${NS_HARNESS_SECRET:-}" ]; then printf '%s' "$NS_HARNESS_SECRET";
  else cat "$NSREVIEW_ROOT/secret"; fi
}

# ---------------------------------------------------------------- states

cmd_add() {
  local state="${1:?state}" ref="${2:?committish}"
  local wt="$STATES/$state"
  [ -d "$wt" ] && { log "$state already exists"; return 0; }
  git -C "$CLONE" rev-parse --verify "$ref^{commit}" >/dev/null 2>&1 \
    || die "unknown committish: $ref"
  git -C "$CLONE" worktree add --detach "$wt" "$ref" >/dev/null 2>&1
  ln -sfn "$DEPS" "$wt/node_modules"          # hazard 3
  echo "$ref" > "$RUN/$state.ref"
  log "added $state at $(git -C "$wt" rev-parse --short HEAD) ($ref)"
}

write_env() {
  local state="$1" port="$2" mode="$3"
  # Values are QUOTED: this file is `source`d, and ENABLE contains spaces.
  cat > "$RUN/$state.env" <<EOF
MONGODB_URI='mongodb://$NSREVIEW_MONGO/nsreview_$state'
API_SECRET='$(secret)'
PORT='$port'
HOSTNAME='127.0.0.1'
INSECURE_USE_HTTP='true'
NODE_ENV='$mode'
DISPLAY_UNITS='mg/dl'
AUTH_DEFAULT_ROLES='denied'
ENABLE='${NSREVIEW_ENABLE:-careportal basal iob cob bwp cage sage iage rawbg}'
SHOW_PLUGINS='${NSREVIEW_SHOW_PLUGINS:-careportal basal iob cob bwp cage sage iage boluscalc}'
TIME_FORMAT='24'
EOF
}

cmd_start() {
  local state="${1:?state}" mode="${2:-development}"
  local wt="$STATES/$state"
  [ -d "$wt" ] || die "no such state: $state (nsctl.sh add $state <ref>)"
  mongo_up

  if [ -f "$RUN/$state.port" ]; then
    local old; old="$(cat "$RUN/$state.port")"
    local p; p="$(pid_on_port "$old" || true)"
    if [ -n "$p" ] && pid_is_ours "$p"; then log "$state already running on $old (pid $p)"; return 0; fi
  fi

  local port; port="$(port_for "$state")"
  write_env "$state" "$port" "$mode"
  echo "$port" > "$RUN/$state.port"
  : > "$RUN/$state.log"

  # hazard 1: setsid + </dev/null so it outlives this shell.
  # stderr and stdout BOTH captured — the bf/throttle SECURITY line is a
  # console.warn and never appears on stdout.
  ( set -a; . "$RUN/$state.env"; set +a
    export NSREVIEW_RUN_ID="$(run_id)" NSREVIEW_STATE="$state"
    cd "$wt"
    setsid node lib/server/server.js >>"$RUN/$state.log" 2>&1 </dev/null &
  )

  local sec; sec="$(secret)"
  for i in $(seq 1 120); do
    if curl -sf -m 2 -H "api-secret: $(printf '%s' "$sec" | sha1sum | cut -d' ' -f1)" \
         "http://127.0.0.1:$port/api/v1/status.json" >/dev/null 2>&1; then
      local pid; pid="$(pid_on_port "$port" || true)"
      echo "${pid:-0}" > "$RUN/$state.pid"
      log "$state up on :$port (pid ${pid:-?}, $mode) after ${i}00ms"
      return 0
    fi
    sleep 0.1
  done
  log "FAILED to start $state — last log lines:"; tail -20 "$RUN/$state.log" >&2
  return 1
}

cmd_stop() {
  local state="$1"
  local pf="$RUN/$state.port"
  [ -f "$pf" ] || { log "$state not running"; return 0; }
  local port pid; port="$(cat "$pf")"; pid="$(pid_on_port "$port" || true)"
  if [ -z "$pid" ]; then log "$state: nothing on :$port"; rm -f "$pf"; return 0; fi
  if ! pid_is_ours "$pid"; then          # hazard 4
    log "REFUSING to kill pid $pid on :$port — not stamped with $(run_id)"
    return 1
  fi
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  rm -f "$pf" "$RUN/$state.pid"
  log "$state stopped (pid $pid)"
}

cmd_stop_all() {
  for pf in "$RUN"/*.port; do [ -e "$pf" ] || continue
    cmd_stop "$(basename "$pf" .port)" || true
  done
}

# reset — the ONLY safe way to re-seed.
#
# MEASURED 2026-09-17: dropping a state's database while its server is running
# leaves the in-memory runtime cache populated. BASE then answered
# /api/v1/entries.json?count=-3 with 1145 distinct sgv documents while mongo
# held 582 — the first seed's documents were still being served from cache and
# merged with the second's. Every read-path measurement taken in that state was
# invalid, and nothing in the HTTP response said so.
#
# So: stop, drop, start. Never drop under a live server.
cmd_reset() {
  local state="${1:?state}" mode="${2:-production}"
  cmd_stop "$state" || true
  mongo_up
  docker exec "$MONGO_CONTAINER" mongosh --quiet "nsreview_$state" \
    --eval 'db.dropDatabase()' >/dev/null
  log "$state database dropped"
  cmd_start "$state" "$mode"
}

cmd_status() {
  printf '%-22s %-6s %-8s %-9s %-12s %s\n' STATE PORT PID MODE HEAD REF
  for rf in "$RUN"/*.ref; do [ -e "$rf" ] || continue
    local state port pid mode head ref
    state="$(basename "$rf" .ref)"; ref="$(cat "$rf")"
    port="$( [ -f "$RUN/$state.port" ] && cat "$RUN/$state.port" || echo - )"
    pid="-"; mode="-"
    [ "$port" != "-" ] && { pid="$(pid_on_port "$port" || echo -)"; }
    [ -f "$RUN/$state.env" ] && mode="$(sed -n "s/^NODE_ENV=.\(.*\)./\1/p" "$RUN/$state.env")"
    head="$(git -C "$STATES/$state" rev-parse --short HEAD 2>/dev/null || echo -)"
    [ -n "$pid" ] && [ "$pid" != "-" ] && pid_is_ours "$pid" || pid="${pid:--}"
    printf '%-22s %-6s %-8s %-9s %-12s %s\n' "$state" "$port" "$pid" "$mode" "$head" "$ref"
  done
}

cmd_url() {
  local state="${1:?state}"
  [ -f "$RUN/$state.port" ] || die "$state not running"
  echo "http://127.0.0.1:$(cat "$RUN/$state.port")"
}

cmd_exec() {
  local state="${1:?state}"; shift
  [ "${1:-}" = "--" ] && shift
  ( cd "$STATES/$state" && NSREVIEW_RUN_ID="$(run_id)" "$@" )
}

case "${1:-}" in
  init)   shift; cmd_init "$@" ;;
  add)    shift; cmd_add "$@" ;;
  start)  shift; cmd_start "$@" ;;
  reset)  shift; cmd_reset "$@" ;;
  stop)   shift; [ "${1:-}" = "--all" ] && cmd_stop_all || cmd_stop "$@" ;;
  status) shift; cmd_status "$@" ;;
  url)    shift; cmd_url "$@" ;;
  exec)   shift; cmd_exec "$@" ;;
  secret) shift
          if [ "${1:-}" = "--sha1" ]; then printf '%s' "$(secret)" | sha1sum | cut -d' ' -f1
          else printf '%s\n' "$(secret)"; fi ;;
  *) sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 1 ;;
esac
