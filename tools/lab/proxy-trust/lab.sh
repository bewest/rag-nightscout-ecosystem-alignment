#!/usr/bin/env bash
# lab.sh - TRUST_PROXY / client-address resolution lab for cgm-remote-monitor.
#
# WHAT IT MEASURES
#   How Nightscout resolves the client address (getRemoteIP / lib/server/client-ip.js)
#   and how the failed-authentication delay behaves, behind real proxy software
#   and real sockets, under each TRUST_PROXY setting. The observation channel is
#   the admin-notify a failed auth emits ("A device at IP address %1 attempted
#   authenticating ..."), read back through the adminnotifies API with the admin
#   secret. Every observation reboots Nightscout first, so notifies start empty
#   and the read is liveness-checked in the same run as the probe.
#
# TOPOLOGY
#   A docker bridge network (default 172.31.66.0/24). Nightscout runs ON THE HOST
#   bound to the network GATEWAY (172.31.66.1:3866) so containers reach it and
#   present distinct, fixed source addresses. Front ends and clients are
#   containers with fixed IPs. Mongo is our own mongo:7 container. All container
#   and network names are prefixed s66lab-.
#
# DISCLOSURE
#   The default-mode weakness is live on the shipping release, and this repo is
#   public. Honest-client cells always run. The ADVERSARIAL cells (O2/O3: a
#   caller supplying forwarding headers) run only when $PROXYLAB_PRIVATE_PROBES
#   points at the private probes file; without it they are skipped. Tracked
#   results say only "protected / not protected"; the header recipes live in the
#   private directory.
#
# USAGE
#   PROXYLAB_STATE=/path/outside/repo \
#   DEV_TREE=... PR_TREE=... DELAY_TREE=... \
#   ./lab.sh up            # network + mongo + all front-end containers
#   ./lab.sh status        # assert network/mongo/front-ends/gateway server
#   ./lab.sh run           # honest matrix -> results JSON + markdown
#   PROXYLAB_PRIVATE_PROBES=.../probes.json ./lab.sh run   # + adversarial cells
#   ./lab.sh down          # stop (do not remove) every s66lab-* container + host servers
#
# RULES BAKED IN
#   * Servers launched detached; the REAL node pid is recorded (echo $$ then exec).
#   * A reboot refuses to start if the gateway port is busy, and stop verifies the
#     port is released. A dead server answers negative probes like a fixed one, so
#     liveness is asserted next to every probe.
#   * down/stop only ever act on recorded pids or on the single listener bound to
#     OUR unique gateway address. Never pkill.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)

# ---- configuration -------------------------------------------------------
PFX=${LAB_PREFIX:-s66lab}
NET=$PFX-net
SUBNET=${LAB_SUBNET:-172.31.66.0/24}
GW=${LAB_GW:-172.31.66.1}
NSPORT=${LAB_NSPORT:-3866}
MONGO_HOSTPORT=${LAB_MONGO_PORT:-27366}
MONGO=127.0.0.1:$MONGO_HOSTPORT

# fixed container addresses
IP_MONGO=172.31.66.2
IP_CLIENT=172.31.66.10      # honest client / guesser "real IP"
IP_BYSTANDER=172.31.66.12   # bystander at a different real IP (O4a)
IP_F1=172.31.66.20          # nginx append
IP_F2=172.31.66.21          # nginx replace
IP_F3F=172.31.66.30         # two-hop front
IP_F3I=172.31.66.31         # two-hop inner (peer to NS)
IP_F4=172.31.66.40          # caddy
IP_F5=172.31.66.50          # traefik
IP_F6=172.31.66.60          # haproxy
IP_TLS=172.31.66.70         # TLS terminator
IP_LBF=172.31.66.80         # L-B front (stream, PROXY protocol) = DO LB emulation
IP_LB2=172.31.66.81         # L-B layer 2 (ingress-nginx emulation)
IP_LB3=172.31.66.82         # L-B layer 3 (last in-cluster hop)

# images (pin by tag; digests recorded in results)
IMG_NGINX=${IMG_NGINX:-nginx:1.27-alpine}
IMG_CADDY=${IMG_CADDY:-caddy:2.8}
IMG_TRAEFIK=${IMG_TRAEFIK:-traefik:v3.1}
IMG_HAPROXY=${IMG_HAPROXY:-haproxy:3.0}
IMG_CURL=${IMG_CURL:-curlimages/curl:8.11.1}
IMG_MONGO=${IMG_MONGO:-mongo:7}

STATE=${PROXYLAB_STATE:?set PROXYLAB_STATE to a directory OUTSIDE any git tree}
mkdir -p "$STATE"/{secrets,logs,pids,run,out}; chmod 700 "$STATE/secrets"

DEV_TREE=${DEV_TREE:?set DEV_TREE to a dev (f1591069) worktree}
PR_TREE=${PR_TREE:?set PR_TREE to the bf2/auth-hardening worktree}
DELAY_TREE=${DELAY_TREE:-}   # optional: bf2/auth-delay-dev-order (f6f361b1)

secret () { local f="$STATE/secrets/$1"; [ -s "$f" ] || { umask 077; openssl rand -hex 20 > "$f"; }; cat "$f"; }
API=$(secret api)
SHA1=$(printf %s "$API" | sha1sum | cut -d' ' -f1)

# ---- docker helpers ------------------------------------------------------
net_up () { docker network inspect "$NET" >/dev/null 2>&1 || \
  docker network create --subnet="$SUBNET" --gateway="$GW" "$NET" >/dev/null; }

mongo_up () {
  docker inspect -f '{{.State.Running}}' "$PFX-mongo" 2>/dev/null | grep -q true && return 0
  docker rm -f "$PFX-mongo" >/dev/null 2>&1 || true
  docker run -d --name "$PFX-mongo" --network "$NET" --ip "$IP_MONGO" \
    --ulimit nofile=64000:64000 -p "127.0.0.1:$MONGO_HOSTPORT:27017" "$IMG_MONGO" --quiet >/dev/null
  local i; for i in $(seq 1 30); do
    docker exec "$PFX-mongo" mongosh --quiet --eval 'db.adminCommand({ping:1}).ok' 2>/dev/null | grep -q 1 && return 0
    sleep 1; done
  echo "mongo did not come up" >&2; return 1
}

# render a front-end config: subst NS_ADDR and any extra KEY=VALUE pairs
render () { # render <src> <dst> [KEY=VAL ...]
  local src=$1 dst=$2; shift 2
  local expr="s#NS_ADDR#$GW:$NSPORT#g"
  local kv; for kv in "$@"; do expr="$expr; s#${kv%%=*}#${kv#*=}#g"; done
  sed "$expr" "$src" > "$dst"
}

nginx_c () { # nginx_c <name> <ip> <rendered-conf> [extra docker args...]
  local name=$1 ip=$2 conf=$3; shift 3
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --network "$NET" --ip "$ip" \
    -v "$conf":/etc/nginx/conf.d/default.conf:ro "$@" "$IMG_NGINX" >/dev/null
}

frontends_up () {
  local F=$HERE/frontends R=$STATE/run
  mkdir -p "$R"/{f1,f2,f3f,f3i,f4,f5,f6,tls,lbf,lb2,lb2bad,lb3}
  render "$F/f1-nginx-append.conf"  "$R/f1/default.conf"
  render "$F/f2-nginx-replace.conf" "$R/f2/default.conf"
  render "$F/f3-inner-append.conf"  "$R/f3i/default.conf"
  render "$F/f3-front-append.conf"  "$R/f3f/default.conf" "F3_INNER=$IP_F3I"
  render "$F/f4-Caddyfile"          "$R/f4/Caddyfile"
  render "$F/f6-haproxy.cfg"        "$R/f6/haproxy.cfg"
  render "$F/f5-traefik-dynamic.yml" "$R/f5/dynamic.yml"
  cp     "$F/f5-traefik.yml"        "$R/f5/traefik.yml"
  render "$F/tls-nginx.conf"        "$R/tls/default.conf"
  # L-B chain
  render "$F/lb-l3-append.conf"     "$R/lb3/default.conf"
  render "$F/lb-l2-ingress.conf"    "$R/lb2/default.conf" "LB_FRONT_IP=$IP_LBF" "LB3_ADDR=$IP_LB3"
  render "$F/lb-l2-misconfig-noproxyproto.conf" "$R/lb2bad/default.conf" "LB3_ADDR=$IP_LB3"
  render "$F/lb-front-stream.nginx.conf" "$R/lbf/nginx.conf" "LB2_ADDR=$IP_LB2:8080"

  nginx_c "$PFX-f1" "$IP_F1" "$R/f1/default.conf"
  nginx_c "$PFX-f2" "$IP_F2" "$R/f2/default.conf"
  nginx_c "$PFX-f3inner" "$IP_F3I" "$R/f3i/default.conf"
  nginx_c "$PFX-f3front" "$IP_F3F" "$R/f3f/default.conf"

  docker rm -f "$PFX-f4" >/dev/null 2>&1 || true
  docker run -d --name "$PFX-f4" --network "$NET" --ip "$IP_F4" \
    -v "$R/f4/Caddyfile":/etc/caddy/Caddyfile:ro "$IMG_CADDY" >/dev/null

  docker rm -f "$PFX-f5" >/dev/null 2>&1 || true
  docker run -d --name "$PFX-f5" --network "$NET" --ip "$IP_F5" \
    -v "$R/f5/traefik.yml":/etc/traefik/traefik.yml:ro \
    -v "$R/f5/dynamic.yml":/etc/traefik/dynamic.yml:ro "$IMG_TRAEFIK" >/dev/null

  docker rm -f "$PFX-f6" >/dev/null 2>&1 || true
  docker run -d --name "$PFX-f6" --network "$NET" --ip "$IP_F6" \
    -v "$R/f6/haproxy.cfg":/usr/local/etc/haproxy/haproxy.cfg:ro "$IMG_HAPROXY" >/dev/null

  # TLS terminator: self-signed cert
  if [ ! -s "$R/tls/lab.crt" ]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 3 \
      -keyout "$R/tls/lab.key" -out "$R/tls/lab.crt" -subj "/CN=s66lab.test" >/dev/null 2>&1
  fi
  docker rm -f "$PFX-tls" >/dev/null 2>&1 || true
  docker run -d --name "$PFX-tls" --network "$NET" --ip "$IP_TLS" \
    -v "$R/tls/default.conf":/etc/nginx/conf.d/default.conf:ro \
    -v "$R/tls/lab.crt":/etc/nginx/certs/lab.crt:ro \
    -v "$R/tls/lab.key":/etc/nginx/certs/lab.key:ro "$IMG_NGINX" >/dev/null

  # L-B chain: l3 (inner), l2 (ingress, PROXY protocol), front (stream, PROXY protocol)
  nginx_c "$PFX-lb3" "$IP_LB3" "$R/lb3/default.conf"
  nginx_c "$PFX-lb2" "$IP_LB2" "$R/lb2/default.conf"
  docker rm -f "$PFX-lbfront" >/dev/null 2>&1 || true
  docker run -d --name "$PFX-lbfront" --network "$NET" --ip "$IP_LBF" \
    -v "$R/lbf/nginx.conf":/etc/nginx/nginx.conf:ro "$IMG_NGINX" >/dev/null

  clients_up
  echo "front ends + clients up"
}

# ---- Nightscout host server lifecycle ------------------------------------
port_pid () { ss -ltnp 2>/dev/null | awk -v a="$GW:$NSPORT" '$4==a{print $NF}' | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2; }
port_busy () { ss -ltn 2>/dev/null | grep -q "$GW:$NSPORT"; }
assert_alive () { local c; c=$(curl -s -o /dev/null -w '%{http_code}' "http://$GW:$NSPORT/api/v1/status.json" 2>/dev/null||true); [ -n "$c" ] && [ "$c" != "000" ]; }

boot_ns () { # boot_ns <treedir> <db> <TRUST_PROXY|UNSET> <tag> [afd=400] [insec=true]
  local tree=$1 db=$2 tp=$3 tag=$4 afd=${5:-400} insec=${6:-true}
  local pidf="$STATE/pids/ns-$tag.pid" log="$STATE/logs/ns-$tag.log"
  if port_busy; then echo "REFUSE boot ns-$tag: gateway busy (pid $(port_pid))" >&2; return 2; fi
  local env_tp=""; [ "$tp" != "UNSET" ] && env_tp="$tp"
  ( cd "$tree" && \
    NIGHTSCOUT_HOSTNAME=$GW PORT=$NSPORT MONGODB_URI="mongodb://$MONGO/$db" API_SECRET="$API" \
    INSECURE_USE_HTTP=$insec AUTH_DEFAULT_ROLES=denied AUTH_FAIL_DELAY=$afd TZ=UTC NODE_ENV=production \
    TRUST_PROXY="$env_tp" \
    setsid nohup bash -c 'echo $$ > "'"$pidf"'"; exec node lib/server/server.js' > "$log" 2>&1 < /dev/null & )
  local i code
  for i in $(seq 1 45); do
    grep -q EADDRINUSE "$log" 2>/dev/null && { echo "DEAD ns-$tag EADDRINUSE" >&2; return 1; }
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://$GW:$NSPORT/api/v1/status.json" 2>/dev/null||true)
    if [ -n "$code" ] && [ "$code" != "000" ]; then
      local rp lp; rp=$(cat "$pidf" 2>/dev/null); lp=$(port_pid)
      echo "ALIVE ns-$tag http=$code pid=$rp listener=$lp tp=[$tp] db=$db afd=$afd insec=$insec"
      [ "$rp" = "$lp" ] || echo "  WARN recorded pid != listener" >&2
      return 0
    fi; sleep 1
  done
  echo "DEAD ns-$tag (timeout)" >&2; tail -6 "$log" >&2; return 1
}

stop_ns () { # stop_ns <tag>
  local tag=${1:-}; [ -n "$tag" ] || return 0
  local pidf="$STATE/pids/ns-$tag.pid"; local pid; pid=$(cat "$pidf" 2>/dev/null||true)
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  local i; for i in $(seq 1 10); do port_busy || { rm -f "$pidf"; return 0; }; sleep 1; done
  local p; p=$(port_pid); [ -n "$p" ] && { kill "$p" 2>/dev/null; sleep 2; kill -9 "$p" 2>/dev/null; }
  port_busy && echo "WARN gateway still busy after stop ns-$tag" >&2
  rm -f "$pidf"
}

# ---- observation ---------------------------------------------------------
notify_ips () { # distinct resolved IPs currently recorded
  curl -s -H "api-secret: $SHA1" "http://$GW:$NSPORT/api/v1/adminnotifies" \
    | python3 "$HERE/tools/notify_ips.py"
}
wrongsecret () { printf %s "$1" | sha1sum | cut -d' ' -f1; }
# Requests come from PERSISTENT client containers via `docker exec`. A fixed
# --ip with --rm cannot be reused back-to-back (the endpoint frees lazily and
# the next run blocks), so we never churn container IPs during a sweep.
client_get () { # client_get <container> <url> [curl args...]
  local c=$1 url=$2; shift 2
  docker exec "$c" curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "$@" "$url"
}
clients_up () {
  local n ip
  for n in "$PFX-client:$IP_CLIENT" "$PFX-bystander:$IP_BYSTANDER"; do
    ip=${n#*:}; n=${n%:*}
    docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null | grep -q true && continue
    docker rm -f "$n" >/dev/null 2>&1 || true
    docker run -d --name "$n" --network "$NET" --ip "$ip" --entrypoint sh "$IMG_CURL" -c 'sleep infinity' >/dev/null
  done
}

# ---- commands ------------------------------------------------------------
# When sourced by run_matrix.sh (LAB_SOURCED=1) we only export functions/config.
if [ "${LAB_SOURCED:-}" = 1 ]; then return 0 2>/dev/null || true; fi

case "${1:-}" in
  up)         net_up; mongo_up; frontends_up ;;
  frontends)  frontends_up ;;
  status)
    echo "network: $(docker network inspect "$NET" -f '{{.Name}} {{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null||echo MISSING)"
    echo "mongo:   running=$(docker inspect -f '{{.State.Running}}' "$PFX-mongo" 2>/dev/null||echo NO)"
    for c in f1 f2 f3front f3inner f4 f5 f6 tls lbfront lb2 lb3 client bystander; do
      printf '  %-8s %s\n' "$c" "$(docker inspect -f '{{.State.Running}}' "$PFX-$c" 2>/dev/null||echo -)"; done
    echo "gateway server alive: $(assert_alive && echo yes || echo no)"
    ;;
  run)        "$HERE/run_matrix.sh" ;;
  down)
    for t in "$STATE"/pids/ns-*.pid; do [ -e "$t" ] || continue; stop_ns "$(basename "$t" .pid | sed 's/^ns-//')"; done
    for c in f1 f2 f3front f3inner f4 f5 f6 tls lbfront lb2 lb3 client bystander mongo; do
      docker stop "$PFX-$c" >/dev/null 2>&1 || true; done
    echo "stopped (not removed) all $PFX-* containers and recorded host servers"
    ;;
  *) sed -n '2,60p' "$0"; exit 1 ;;
esac
