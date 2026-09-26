#!/usr/bin/env bash
# ar_chain.sh - AR ("auth_request chain") topologies for the proxy-trust lab.
#
# WHAT IT ADDS
#   A self-contained add-on to lab.sh/run_matrix.sh (it edits neither) for the
#   multi-tenant hosted-platform shape where nginx picks the NEXT hop per request
#   from an auth_request subrequest, several times in series:
#
#     client -> L4 LB (PROXY protocol) -> GATEWAY  (auth_request: public name -> origin)
#                                       -> ROUTER   (auth_request: name -> tenant id)
#                                       -> TENANT ROUTER (auth_request: tenant -> host:port)
#                                       -> Nightscout
#
#   Topologies (all end at the same TENANT ROUTER, then Nightscout):
#     AR-PP3  L4+PP -> gateway(overwrite XFF from PP) -> router(append) -> tenant(append)
#     AR-PP2  L4+PP -> gateway(overwrite XFF from PP) -> tenant(append)
#     AR-L4   L4 no PP (TCP passthrough)              -> router(append) -> tenant(append)
#     AR-L4PP L4+PP -> router(real_ip from PP, append)                  -> tenant(append)
#   See README-ar-chain.md for the expected TRUST_PROXY per topology.
#
# USAGE (same env as lab.sh; run `./lab.sh up` first for network/mongo/clients)
#   ./ar_chain.sh up        # render + start the AR containers (target: Nightscout)
#   ./ar_chain.sh selftest  # NO Nightscout needed: swap NS for a header-echo
#                           # backend and assert routing + forwarded headers per hop
#   ./ar_chain.sh run       # O1 (+O2 with $PROXYLAB_PRIVATE_PROBES) per topology x setting
#   ./ar_chain.sh o2families  # O2 across every header family (private probes required)
#   ./ar_chain.sh status | down
#
# Disclosure: same rules as lab.sh. Tracked output says protected / not protected.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
: "${DEV_TREE:=/nonexistent-dev-tree}" "${PR_TREE:=/nonexistent-pr-tree}"  # selftest needs neither
export DEV_TREE PR_TREE
LAB_SOURCED=1 . "$HERE/lab.sh"

NETP=${GW%.*}
IP_AR_LBPP=$NETP.90     # L4 front, PROXY protocol on  -> gateway:8080
IP_AR_GW=$NETP.91       # gateway (consumes PP, overwrites XFF)
IP_AR_RT=$NETP.92       # router, plain listen
IP_AR_TR=$NETP.93       # tenant router (peer to Nightscout)
IP_AR_LBTCP=$NETP.94    # L4 front, no PROXY protocol -> router:80
IP_AR_LBPP2=$NETP.96    # L4 front, PROXY protocol on  -> router-pp:8080
IP_AR_RTPP=$NETP.97     # router consuming PP with real_ip
IP_AR_ECHO=$NETP.99     # selftest-only header echo (stands in for Nightscout)
AR_NAMES="arlbpp argw arrt artr arlbtcp arlbpp2 arrtpp arecho"

# topology -> "entry-ip|Host header|expected TRUST_PROXY hop count (none = unattainable)"
declare -A AR=(
  [AR-PP3]="$IP_AR_LBPP|guest.gw.test|3"
  [AR-PP2]="$IP_AR_LBPP|hosted.gw.test|2"
  [AR-L4]="$IP_AR_LBTCP|demo-guest.lab.test|none"
  [AR-L4PP]="$IP_AR_LBPP2|demo-guest.lab.test|2"
)
AR_TOPOS=(AR-PP3 AR-PP2 AR-L4 AR-L4PP)

ar_up () { # ar_up [ns|echo]  -- which backend the tenant router points at
  local target=${1:-ns} F=$HERE/frontends R=$STATE/run/ar
  mkdir -p "$R"; net_up
  local gw=$GW port=$NSPORT
  if [ "$target" = echo ]; then
    gw=$IP_AR_ECHO; port=3866
    cat > "$R/echo.conf" <<'EOF'
server {
    listen 3866;
    default_type text/plain;
    return 200 "peer=$remote_addr|xff=$http_x_forwarded_for|xrip=$http_x_real_ip|proto=$http_x_forwarded_proto|host=$host\n";
}
EOF
    nginx_c "$PFX-arecho" "$IP_AR_ECHO" "$R/echo.conf"
  fi
  GW=$gw NSPORT=$port render "$F/ar-tenant-router.conf" "$R/tr.conf"
  render "$F/ar-gateway.conf" "$R/gw.conf" "TENANT_ROUTER_ADDR=$IP_AR_TR" "ROUTER_ADDR=$IP_AR_RT"
  render "$F/ar-router.conf"  "$R/rt.conf" "TENANT_ROUTER_ADDR=$IP_AR_TR" \
    "ROUTER_LISTEN=listen 80 default_server;" "ROUTER_REALIP="
  render "$F/ar-router.conf"  "$R/rtpp.conf" "TENANT_ROUTER_ADDR=$IP_AR_TR" \
    "ROUTER_LISTEN=listen 8080 proxy_protocol default_server;" \
    "ROUTER_REALIP=set_real_ip_from $IP_AR_LBPP2; real_ip_header proxy_protocol;"
  render "$F/ar-l4-stream.nginx.conf" "$R/lbpp.conf"  "PP_DIRECTIVE=proxy_protocol on;" "NEXT_ADDR=$IP_AR_GW:8080"
  render "$F/ar-l4-stream.nginx.conf" "$R/lbtcp.conf" "PP_DIRECTIVE="                   "NEXT_ADDR=$IP_AR_RT:80"
  render "$F/ar-l4-stream.nginx.conf" "$R/lbpp2.conf" "PP_DIRECTIVE=proxy_protocol on;" "NEXT_ADDR=$IP_AR_RTPP:8080"

  nginx_c "$PFX-artr"   "$IP_AR_TR"   "$R/tr.conf"
  nginx_c "$PFX-arrt"   "$IP_AR_RT"   "$R/rt.conf"
  nginx_c "$PFX-arrtpp" "$IP_AR_RTPP" "$R/rtpp.conf"
  nginx_c "$PFX-argw"   "$IP_AR_GW"   "$R/gw.conf"
  local n; for n in lbpp:$IP_AR_LBPP lbtcp:$IP_AR_LBTCP lbpp2:$IP_AR_LBPP2; do
    docker rm -f "$PFX-ar${n%%:*}" >/dev/null 2>&1 || true
    docker run -d --name "$PFX-ar${n%%:*}" --network "$NET" --ip "${n#*:}" \
      -v "$R/${n%%:*}.conf":/etc/nginx/nginx.conf:ro "$IMG_NGINX" >/dev/null
  done
  clients_up
  sleep 1
  for n in artr arrt arrtpp argw arlbpp arlbtcp arlbpp2; do
    docker inspect -f '{{.State.Running}}' "$PFX-$n" 2>/dev/null | grep -q true \
      || { echo "FAIL $PFX-$n not running:"; docker logs --tail 5 "$PFX-$n" 2>&1; return 1; }
  done
  echo "AR chain up (tenant router -> $target $gw:$port)"
}

ar_body () { # ar_body <entry> <host> [curl args...]
  local e=$1 h=$2; shift 2
  docker exec "$PFX-client" curl -s --max-time 10 -H "Host: $h" "$@" "http://$e/api/v1/entries.json"
}

# ---- selftest: header chain without Nightscout ----------------------------
ar_selftest () {
  ar_up echo || return 1
  local C=$IP_CLIENT fails=0
  check () { # check <label> <got> <want>
    if [ "$2" = "$3" ]; then printf 'PASS %-34s %s\n' "$1" "$2"
    else printf 'FAIL %-34s got=[%s] want=[%s]\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }
  field () { tr '|' '\n' <<<"$1" | sed -n "s/^$2=//p"; }
  local t e h b
  # expected XFF at the last hop for an honest client (no caller-supplied headers;
  # adversarial checks belong to `run`/`o2families` with the private probes)
  declare -A HONEST=( [AR-PP3]="$C, $IP_AR_GW, $IP_AR_RT" [AR-PP2]="$C, $IP_AR_GW"
                      [AR-L4]="$IP_AR_LBTCP, $IP_AR_RT"   [AR-L4PP]="$C, $IP_AR_RTPP" )
  for t in "${AR_TOPOS[@]}"; do
    IFS='|' read -r e h _ <<<"${AR[$t]}"
    b=$(ar_body "$e" "$h")
    check "$t peer" "$(field "$b" peer)" "$IP_AR_TR"
    check "$t xff (honest)" "$(field "$b" xff)" "${HONEST[$t]}"
    check "$t host rewritten to tenant" "$(field "$b" host | grep -oE '^tenant1\.backends' )" "tenant1.backends"
    check "$t proto" "$(field "$b" proto)" "http"
  done
  # non-vacuity: the gateway's authorizer really gates, unknown names don't route
  check "gateway denies unknown view" \
    "$(docker exec "$PFX-client" curl -s -o /dev/null -w '%{http_code}' -H 'Host: nosuch.gw.test' "http://$IP_AR_LBPP/")" 401
  check "gateway 421 for foreign host" \
    "$(docker exec "$PFX-client" curl -s -o /dev/null -w '%{http_code}' -H 'Host: example.org' "http://$IP_AR_LBPP/")" 421
  echo "selftest: $fails failure(s)"; return $((fails > 0))
}

# ---- Nightscout cells (mirrors run_matrix.sh cell(), plus Host + expected) --
ar_cell () { # ar_cell <topology> <tree_dir> <tree_label> <tp> <jsonl>
  local topo=$1 tree=$2 tlabel=$3 tp=$4 out=$5 e h exp
  IFS='|' read -r e h exp <<<"${AR[$topo]}"
  local tag=cell db="s66_${topo//-/_}_${tlabel}_$(echo "$tp"|tr -c 'A-Za-z0-9' _)"
  stop_ns "$tag" >/dev/null 2>&1
  boot_ns "$tree" "$db" "$tp" "$tag" 400 true >/dev/null || { echo "SKIP $topo/$tlabel/$tp (dead)"; return; }
  assert_alive || { echo "SKIP $topo/$tlabel/$tp (not alive)"; return; }
  local code; code=$(client_get "$PFX-client" "http://$e/api/v1/entries.json" -H "Host: $h" \
     -H "api-secret: $(wrongsecret "o1-$topo-$tlabel-$tp")")
  # the chain must deliver the request to Nightscout (no hop-level 421/5xx/timeout)
  case "$code" in 000|421|5??) false ;; esac || { echo "SKIP $topo/$tlabel/$tp (chain returned $code)"; stop_ns "$tag" >/dev/null 2>&1; return; }
  local o1; o1=$(notify_ips)
  local o2=skipped spoofseen=n/a
  if [ -n "$PRIV" ]; then
    client_get "$PFX-client" "http://$e/api/v1/entries.json" -H "Host: $h" \
       -H "$SPOOF_H: $SPOOF" -H "api-secret: $(wrongsecret "o2-$topo-$tlabel-$tp")" >/dev/null
    if notify_ips | tr ',' '\n' | grep -qxF "$SPOOF"; then o2=not-protected; spoofseen=yes; else o2=protected; spoofseen=no; fi
  fi
  local ok=no; [ "$o1" = "$IP_CLIENT" ] && ok=yes
  printf '%-7s %-4s tp=%-6s O1=%-15s correct=%-3s O2=%-13s (expected tp=%s)\n' "$topo" "$tlabel" "$tp" "$o1" "$ok" "$o2" "$exp"
  echo "{\"date\":\"$DATE\",\"topology\":\"$topo\",\"tree\":\"$tlabel\",\"tree_sha\":\"$([ "$tlabel" = dev ] && echo "$DEV_SHA" || echo "$PR_SHA")\",\"trust_proxy\":\"$tp\",\"expected_tp\":\"$exp\",\"o1_resolved\":\"$o1\",\"o1_correct\":\"$ok\",\"o2\":\"$o2\",\"spoof_seen\":\"$spoofseen\",\"client_ip\":\"$IP_CLIENT\"}" >> "$out"
  stop_ns "$tag" >/dev/null 2>&1
}

ar_run () {
  [ -d "$PR_TREE" ] || { echo "set PR_TREE to the bf2/auth-hardening worktree" >&2; return 1; }
  mongo_up && ar_up ns || return 1
  PRIV=${PROXYLAB_PRIVATE_PROBES:-}
  OUT="$STATE/out"; FULL="${PROXYLAB_PRIVATE_RESULTS:-$OUT}"; mkdir -p "$OUT" "$FULL"
  DATE=$(date +%F)
  DEV_SHA=$(git -C "$DEV_TREE" rev-parse --short HEAD 2>/dev/null || echo dev)
  PR_SHA=$(git -C "$PR_TREE" rev-parse --short HEAD 2>/dev/null || echo pr)
  # O2 (single chain injection) comes ONLY from the private probes file
  SPOOF_H=""; SPOOF=""
  if [ -n "$PRIV" ]; then
    SPOOF_H=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["o2_chain_injection"]["header"])' "$PRIV") || return 2
    SPOOF=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["o2_chain_injection"]["value"])' "$PRIV") || return 2
  fi
  local jsonl="$FULL/results-ar-$DATE.jsonl"; : > "$jsonl"
  local settings=(${AR_SETTINGS:-UNSET false 1 2 3 4 true}) t s
  echo "=== AR chain matrix ($DATE, pr=$PR_SHA, probes=$([ -n "$PRIV" ] && echo ON || echo OFF)) ==="
  # unset on the dev tree = what a shipping release does today, per topology
  if [ -d "$DEV_TREE" ]; then for t in "${AR_TOPOS[@]}"; do ar_cell "$t" "$DEV_TREE" dev UNSET "$jsonl"; done; fi
  for t in "${AR_TOPOS[@]}"; do for s in "${settings[@]}"; do ar_cell "$t" "$PR_TREE" pr "$s" "$jsonl"; done; done
  echo "results (full): $jsonl"
  python3 "$HERE/tools/analyze.py" "$jsonl" "$OUT/matrix-ar-$DATE.md" "$DATE" "$DEV_SHA" "$PR_SHA"
}

# ---- O2 across every header family the compatibility path reads ----------
# Mirrors o2_families.sh for the AR topologies (which need a Host header to
# route). Probes come only from $PROXYLAB_PRIVATE_PROBES; per-probe detail goes
# to $PROXYLAB_PRIVATE_RESULTS; the tracked summary says protected / not protected.
ar_o2families () {
  local priv=${PROXYLAB_PRIVATE_PROBES:?set PROXYLAB_PRIVATE_PROBES to the private probes file}
  local pres=${PROXYLAB_PRIVATE_RESULTS:?set PROXYLAB_PRIVATE_RESULTS to a gitignored directory}
  local tree=${O2_TREE:-$PR_TREE}
  [ -d "$tree" ] || { echo "set PR_TREE (or O2_TREE)" >&2; return 1; }
  mongo_up && ar_up ns || return 1
  local out="$STATE/out" date sha; mkdir -p "$out" "$pres"; date=$(date +%F)
  sha=$(git -C "$tree" rev-parse --short HEAD)
  local jsonl="$pres/o2-families-ar-$date.jsonl" summary="$out/o2-families-ar-$date.md"; : > "$jsonl"
  local probes; mapfile -t probes < <(python3 - "$priv" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
alt = p["spoof_ip_alt"]
for i, pr in enumerate(p["o2_single_header_probes"]):
    print(f'{i}\t{pr["header"]}\t{pr["value"]}\t{alt}')
PY
)
  [ "${#probes[@]}" -gt 0 ] || { echo "no probes in $priv" >&2; return 2; }
  probe_once () { # probe_once <entry> <host> <header> <value> <label>
    client_get "$PFX-client" "http://$1/api/v1/entries.json" -H "Host: $2" \
       -H "$3: $4" -H "api-secret: $(wrongsecret "o2f-$5")" >/dev/null
    assert_alive || { echo dead; return; }
    notify_ips | tr ',' '\n' | grep -qxF "$4" && echo moved || echo held
  }
  declare -A verdict; local t tp e h exp line idx hd v v2 first second key db tag=o2f
  for t in "${AR_TOPOS[@]}"; do
    IFS='|' read -r e h exp <<<"${AR[$t]}"
    [ "$exp" = none ] && exp=2   # AR-L4 has no correct setting; 2 is the closest
    for tp in UNSET "$exp"; do
      key="$t|$tp"; verdict[$key]=protected
      for line in "${probes[@]}"; do
        IFS=$'\t' read -r idx hd v v2 <<<"$line"
        db="s66_o2f_${t//-/_}_$(echo "$tp"|tr -c 'A-Za-z0-9' _)_$idx"
        stop_ns "$tag" >/dev/null 2>&1
        boot_ns "$tree" "$db" "$tp" "$tag" 400 true >/dev/null || { verdict[$key]=error; continue; }
        first=$(probe_once "$e" "$h" "$hd" "$v" "$t-$tp-$idx-first")
        client_get "$PFX-client" "http://$e/api/v1/entries.json" -H "Host: $h" \
           -H "api-secret: $(wrongsecret "o2f-honest-$t-$tp-$idx")" >/dev/null
        second=$(probe_once "$e" "$h" "$hd" "$v2" "$t-$tp-$idx-second")
        stop_ns "$tag" >/dev/null 2>&1
        printf '%-7s tp=%-6s probe=%s first=%s second=%s\n' "$t" "$tp" "$idx" "$first" "$second"
        echo "{\"date\":\"$date\",\"tree_sha\":\"$sha\",\"topology\":\"$t\",\"trust_proxy\":\"$tp\",\"probe\":$idx,\"header\":\"$hd\",\"first\":\"$first\",\"second\":\"$second\"}" >> "$jsonl"
        case "$first$second" in
          *dead*) verdict[$key]=error ;;
          *moved*) [ "${verdict[$key]}" = error ] || verdict[$key]="not protected" ;;
        esac
      done
    done
  done
  {
    echo "# O2 across all client-address header families, AR topologies ($date)"
    echo
    echo "Tree \`$sha\`. \"protected\" = no probe in the private set moved the resolved"
    echo "address on any attempt. Probe detail is private. AR-L4 has no setting that"
    echo "resolves the real client; its second row uses 2, the closest."
    echo
    echo "| topology | TRUST_PROXY | O2 |"
    echo "|---|---|---|"
    for t in "${AR_TOPOS[@]}"; do
      IFS='|' read -r e h exp <<<"${AR[$t]}"; [ "$exp" = none ] && exp=2
      for tp in UNSET "$exp"; do echo "| $t | $tp | ${verdict[$t|$tp]} |"; done
    done
  } > "$summary"
  echo "private: $jsonl"; echo "summary: $summary"
}

case "${1:-}" in
  up)       ar_up ns ;;
  selftest) ar_selftest ;;
  run)      ar_run ;;
  o2families) ar_o2families ;;
  status)   for c in $AR_NAMES; do printf '  %-8s %s\n' "$c" "$(docker inspect -f '{{.State.Running}}' "$PFX-$c" 2>/dev/null||echo -)"; done ;;
  down)     for c in $AR_NAMES; do docker stop "$PFX-$c" >/dev/null 2>&1 || true; done; echo "stopped AR containers" ;;
  *)        sed -n '2,32p' "$0"; exit 1 ;;
esac
