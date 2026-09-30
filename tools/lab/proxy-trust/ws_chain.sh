#!/usr/bin/env bash
# ws_chain.sh - WebSocket (socket.io) cells for the proxy-trust lab's AR chain.
#
# WHAT IT ADDS
#   ar_chain.sh measures the address Nightscout resolves for HTTP requests
#   behind the auth_request chain. Nightscout's socket server resolves the
#   address of socket.request (the handshake) through the same helper, and a
#   wrong-secret `authorize` event feeds the same failed-auth delay and the same
#   admin-notify. These cells check that the socket path agrees with HTTP, and
#   that the upgrade really happens through every hop.
#
#     W0  upgrade    the socket ends on the websocket transport and every HTTP
#                    hop on the path logged a 101 for it (non-vacuity for W1/W2)
#     W1  address    the IP recorded for a socket `authorize` with a wrong
#                    secret is the honest client, and equals the IP recorded for
#                    an HTTP request with a wrong secret from the same client
#     W2  adversarial  (private probes only) every header family in the
#                    socket handshake; tracked output says protected / not
#     W3  idle       (off by default) an idle socket through the chain with
#                    proxy_read/send_timeout set on every hop; the tradeoff
#                    between hop timeouts and the socket.io ping interval
#
#   Transports: "polling,websocket" (polling first, then upgrade: what the web
#   client does; socket.request is the first polling request) and "websocket"
#   (the upgrade request is the handshake).
#
# USAGE (same environment as lab.sh / ar_chain.sh)
#   ./ws_chain.sh selftest   # NO Nightscout: upgrade + forwarded headers per hop
#   ./ws_chain.sh run        # W0 + W1 per topology x setting x transport
#   PROXYLAB_PRIVATE_PROBES=… PROXYLAB_PRIVATE_RESULTS=… ./ws_chain.sh o2families   # W2
#   WS_IDLE=1 ./ws_chain.sh idle   # W3 (minutes; refuses without WS_IDLE=1)
#   ./ws_chain.sh status | down
#   Knobs: WS_SETTINGS, WS_TRANSPORTS, WS_TOPOS, WS_IDLE_TOPO, WS_IDLE_TIMEOUTS,
#          WS_IDLE_MS, WS_CLIENT_NM (socket.io-client; default $PR_TREE/node_modules)
#
# Disclosure: same rules as lab.sh. Tracked output says protected / not protected.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
AR_SOURCED=1 . "$HERE/ar_chain.sh"

IP_WS_CLIENT=$NETP.14
WS_CLIENT=$PFX-wsclient
IMG_NODE=${IMG_NODE:-node:22-alpine}
WS_TOPOS=(${WS_TOPOS:-${AR_TOPOS[*]}})
WS_TRANSPORTS=(${WS_TRANSPORTS:-polling,websocket websocket})
# HTTP hops on each path; each must log a 101 for the upgrade (L4 hops are streams)
declare -A WS_HOPS=( [AR-PP3]="argw arrt artr" [AR-PP2]="argw artr" [AR-L4]="arrt artr" [AR-L4PP]="arrtpp artr" )

# ---- client container -------------------------------------------------------
ws_client_up () {
  local nm=${WS_CLIENT_NM:-$PR_TREE/node_modules} src
  [ -d "$nm/socket.io-client" ] || nm=$STATE/run/ws-empty-nm   # selftest needs no tree
  mkdir -p "$STATE/run/ws-empty-nm"
  src=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/nm"}}{{.Source}}{{end}}{{end}}' "$WS_CLIENT" 2>/dev/null || true)
  if docker inspect -f '{{.State.Running}}' "$WS_CLIENT" 2>/dev/null | grep -q true && [ "$src" = "$nm" ]; then return 0; fi
  docker rm -f "$WS_CLIENT" >/dev/null 2>&1 || true
  docker run -d --name "$WS_CLIENT" --network "$NET" --ip "$IP_WS_CLIENT" \
    -v "$nm":/nm:ro -v "$HERE/tools":/probe:ro -e NODE_PATH=/nm \
    --entrypoint sh "$IMG_NODE" -c 'sleep infinity' >/dev/null
}

probe () { docker exec -e PROBE="$1" "$WS_CLIENT" node /probe/ws_probe.js 2>/dev/null; }
# jf <json> <field>: one field of a probe result (lists/objects as JSON)
jf () { python3 -c 'import json,sys
try: d=json.loads(sys.argv[1] or "{}")
except Exception: d={}
v=d.get(sys.argv[2],"")
print(json.dumps(v) if isinstance(v,(list,dict,bool)) else v)' "$1" "$2"; }
pjson () { # pjson mode entry host transports secret [headers-json] [extra-json]
  python3 -c 'import json,sys
m,e,h,t,s=sys.argv[1:6]; hd=json.loads(sys.argv[6]) if len(sys.argv)>6 and sys.argv[6] else {}
x=json.loads(sys.argv[7]) if len(sys.argv)>7 and sys.argv[7] else {}
d=dict(mode=m,entry=e,host=h,transports=[p for p in t.split(",") if p],secret=s,headers=hd); d.update(x)
print(json.dumps(d))' "$@"; }

now () { date -u +%Y-%m-%dT%H:%M:%S.%NZ; }
hops_101 () { # hops_101 <topology> <since> -> "ok" or "missing:<hop,...>"
  local c miss=""
  for c in ${WS_HOPS[$1]}; do
    docker logs --since "$2" "$PFX-$c" 2>&1 \
      | grep -qE '"GET /socket\.io/\?[^"]*transport=websocket[^"]* HTTP/1\.1" 101 ' || miss="$miss${miss:+,}$c"
  done
  [ -z "$miss" ] && echo ok || echo "missing:$miss"
}

# ---- selftest: upgrade through every hop without Nightscout -------------------
ws_selftest () {
  ar_up echo || return 1
  # swap the nginx echo for a node one that also answers upgrades
  docker rm -f "$PFX-arecho" >/dev/null 2>&1 || true
  docker run -d --name "$PFX-arecho" --network "$NET" --ip "$IP_AR_ECHO" \
    -v "$HERE/tools":/probe:ro "$IMG_NODE" node /probe/ws_echo.js >/dev/null
  ws_client_up; sleep 1
  local C=$IP_WS_CLIENT fails=0 t e h r since echo
  check () { if [ "$2" = "$3" ]; then printf 'PASS %-36s %s\n' "$1" "$2"
    else printf 'FAIL %-36s got=[%s] want=[%s]\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }
  field () { tr '|' '\n' <<<"$1" | sed -n "s/^$2=//p"; }
  declare -A HONEST=( [AR-PP3]="$C, $IP_AR_GW, $IP_AR_RT" [AR-PP2]="$C, $IP_AR_GW"
                      [AR-L4]="$IP_AR_LBTCP, $IP_AR_RT"   [AR-L4PP]="$C, $IP_AR_RTPP" )
  for t in "${AR_TOPOS[@]}"; do
    IFS='|' read -r e h _ <<<"${AR[$t]}"
    since=$(now)
    r=$(probe "$(pjson raw "$e" "$h" "" "")")
    echo=$(jf "$r" echo)
    check "$t upgrade status" "$(jf "$r" status)" 101
    check "$t upgrade reached backend" "$(field "$echo" upgrade)|$(field "$echo" connection)" "websocket|upgrade"
    check "$t peer" "$(field "$echo" peer)" "$IP_AR_TR"
    check "$t xff on upgrade (honest)" "$(field "$echo" xff)" "${HONEST[$t]}"
    check "$t host rewritten to tenant" "$(field "$echo" host | grep -oE '^tenant1\.backends')" "tenant1.backends"
    sleep 1
    check "$t 101 logged at every HTTP hop" "$(hops_101 "$t" "$since")" ok
  done
  # non-vacuity: a request without Upgrade is not upgraded and logs no 101
  IFS='|' read -r e h _ <<<"${AR[AR-PP2]}"
  since=$(now)
  r=$(docker exec "$WS_CLIENT" wget -qO- --header "Host: $h" "http://$e/socket.io/?EIO=4&transport=websocket" 2>/dev/null)
  check "control: plain GET reached backend" "$(field "$r" peer)" "$IP_AR_TR"
  check "control: plain GET not upgraded" "$(field "$r" upgrade)" ""
  sleep 1
  check "control: no 101 logged" "$(hops_101 AR-PP2 "$since")" "missing:argw,artr"
  echo "ws selftest: $fails failure(s)"; return $((fails > 0))
}

# ---- W0 + W1 ------------------------------------------------------------------
ws_expected () { local e h exp; IFS='|' read -r e h exp <<<"${AR[$1]}"; echo "$exp"; }

ws_cell () { # ws_cell <topology> <tree_dir> <tree_label> <tp> <transports> <jsonl>
  local topo=$1 tree=$2 tlabel=$3 tp=$4 tr=$5 out=$6 e h exp
  IFS='|' read -r e h exp <<<"${AR[$topo]}"
  local tag=wscell db="s66_ws_${topo//-/_}_${tlabel}_$(echo "$tp"|tr -c 'A-Za-z0-9' _)_${tr//,/_}"
  local id="$topo/$tlabel/$tp/$tr"
  stop_ns "$tag" >/dev/null 2>&1
  boot_ns "$tree" "$db" "$tp" "$tag" 400 true >/dev/null || { echo "SKIP $id (dead)"; return; }
  assert_alive || { echo "SKIP $id (not alive)"; return; }
  local since r transport upgraded auth err hops w0 ws_ip both match ok
  since=$(now)
  r=$(probe "$(pjson auth "$e" "$h" "$tr" "$(wrongsecret "ws-$id")")")
  transport=$(jf "$r" transport); upgraded=$(jf "$r" upgraded); auth=$(jf "$r" auth); err=$(jf "$r" error)
  sleep 1
  hops=$(hops_101 "$topo" "$since")
  # W0: websocket-only must be on websocket; polling-first must have upgraded
  w0=fail
  if [ -z "$err" ] && [ "$transport" = websocket ] && [ "$hops" = ok ]; then
    case "$tr" in websocket) w0=ok ;; *) [ "$upgraded" = true ] && w0=ok ;; esac
  fi
  assert_alive || { echo "SKIP $id (died during probe)"; return; }
  ws_ip=$(notify_ips)
  # same client, HTTP, different wrong secret: must resolve the same address
  probe "$(pjson http "$e" "$h" "" "$(wrongsecret "wshttp-$id")")" >/dev/null
  both=$(notify_ips)
  match=no; [ -n "$ws_ip" ] && [ "$both" = "$ws_ip" ] && match=yes
  ok=no; [ "$ws_ip" = "$IP_WS_CLIENT" ] && ok=yes
  [ -z "$ws_ip" ] && ws_ip="(no notify)"
  printf '%-7s %-4s tp=%-6s %-17s W0=%-4s ws_ip=%-15s correct=%-3s http_match=%-3s auth=%s%s\n' \
    "$topo" "$tlabel" "$tp" "$tr" "$w0" "$ws_ip" "$ok" "$match" "$auth" "${err:+ err=$err}"
  echo "{\"date\":\"$DATE\",\"topology\":\"$topo\",\"tree\":\"$tlabel\",\"tree_sha\":\"$([ "$tlabel" = dev ] && echo "$DEV_SHA" || echo "$PR_SHA")\",\"trust_proxy\":\"$tp\",\"expected_tp\":\"$exp\",\"transports\":\"$tr\",\"transport\":\"$transport\",\"upgraded\":\"$upgraded\",\"hops_101\":\"$hops\",\"w0\":\"$w0\",\"auth\":\"$auth\",\"error\":\"$err\",\"ws_resolved\":\"$ws_ip\",\"ws_correct\":\"$ok\",\"after_http\":\"$both\",\"http_match\":\"$match\",\"client_ip\":\"$IP_WS_CLIENT\"}" >> "$out"
  stop_ns "$tag" >/dev/null 2>&1
}

ws_prep () {
  [ -d "$PR_TREE/node_modules/socket.io-client" ] || { echo "set PR_TREE to a Nightscout tree with node_modules" >&2; return 1; }
  mongo_up && ar_up ns && ws_client_up || return 1
  OUT="$STATE/out"; mkdir -p "$OUT"; DATE=$(date +%F)
  DEV_SHA=$(git -C "$DEV_TREE" rev-parse --short HEAD 2>/dev/null || echo dev)
  PR_SHA=$(git -C "$PR_TREE" rev-parse --short HEAD 2>/dev/null || echo pr)
}

ws_run () {
  ws_prep || return 1
  local jsonl="$OUT/results-ws-$DATE.jsonl"; : > "$jsonl"
  local settings=(${WS_SETTINGS:-UNSET false 1 2 3 4 true}) t s x
  echo "=== WS chain W0/W1 ($DATE, dev=$DEV_SHA pr=$PR_SHA) ==="
  if [ -d "$DEV_TREE" ]; then
    for t in "${WS_TOPOS[@]}"; do for x in "${WS_TRANSPORTS[@]}"; do ws_cell "$t" "$DEV_TREE" dev UNSET "$x" "$jsonl"; done; done
  fi
  for t in "${WS_TOPOS[@]}"; do for s in "${settings[@]}"; do for x in "${WS_TRANSPORTS[@]}"; do
    ws_cell "$t" "$PR_TREE" pr "$s" "$x" "$jsonl"; done; done; done
  echo "results: $jsonl"
  python3 "$HERE/tools/ws_analyze.py" matrix "$jsonl" "$OUT/matrix-ws-$DATE.md" "$DATE" "$DEV_SHA" "$PR_SHA"
}

# ---- W2: every header family in the socket handshake (private probes) ---------
ws_o2families () {
  local priv=${PROXYLAB_PRIVATE_PROBES:?set PROXYLAB_PRIVATE_PROBES to the private probes file}
  local pres=${PROXYLAB_PRIVATE_RESULTS:?set PROXYLAB_PRIVATE_RESULTS to a gitignored directory}
  local tree=${O2_TREE:-$PR_TREE}
  ws_prep || return 1
  mkdir -p "$pres"
  local sha; sha=$(git -C "$tree" rev-parse --short HEAD)
  local jsonl="$pres/o2-families-ws-$DATE.jsonl" summary="$OUT/o2-families-ws-$DATE.md"; : > "$jsonl"
  local probes; mapfile -t probes < <(python3 - "$priv" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
for i, pr in enumerate(p["o2_single_header_probes"]):
    print(f'{i}\t{pr["header"]}\t{pr["value"]}\t{p["spoof_ip_alt"]}')
PY
)
  [ "${#probes[@]}" -gt 0 ] || { echo "no probes in $priv" >&2; return 2; }
  ws_attempt () { # ws_attempt <entry> <host> <transports> <header> <value> <label> -> moved|held|dead|vacuous
    local r hd; hd=$(python3 -c 'import json,sys;print(json.dumps({sys.argv[1]:sys.argv[2]}))' "$4" "$5")
    r=$(probe "$(pjson auth "$1" "$2" "$3" "$(wrongsecret "wso2f-$6")" "$hd")")
    case "$(jf "$r" error)" in unsendable-on-polling) echo vacuous; return ;; esac
    [ "$(jf "$r" transport)" = websocket ] || { echo vacuous; return; }
    assert_alive || { echo dead; return; }
    notify_ips | tr ',' '\n' | grep -qxF "$5" && echo moved || echo held
  }
  declare -A verdict; local t tp tr e h exp line idx hd v v2 first second key db tag=wso2f
  for t in "${WS_TOPOS[@]}"; do
    IFS='|' read -r e h exp <<<"${AR[$t]}"; [ "$exp" = none ] && exp=2
    for tp in UNSET "$exp"; do for tr in "${WS_TRANSPORTS[@]}"; do
      key="$t|$tp|$tr"; verdict[$key]=protected
      for line in "${probes[@]}"; do
        IFS=$'\t' read -r idx hd v v2 <<<"$line"
        db="s66_wso2f_${t//-/_}_$(echo "$tp"|tr -c 'A-Za-z0-9' _)_${tr//,/_}_$idx"
        stop_ns "$tag" >/dev/null 2>&1
        boot_ns "$tree" "$db" "$tp" "$tag" 400 true >/dev/null || { verdict[$key]=error; continue; }
        first=$(ws_attempt "$e" "$h" "$tr" "$hd" "$v" "$t-$tp-$tr-$idx-first")
        probe "$(pjson auth "$e" "$h" "$tr" "$(wrongsecret "wso2f-honest-$t-$tp-$tr-$idx")")" >/dev/null
        second=$(ws_attempt "$e" "$h" "$tr" "$hd" "$v2" "$t-$tp-$tr-$idx-second")
        stop_ns "$tag" >/dev/null 2>&1
        printf '%-7s tp=%-6s %-17s probe=%s first=%s second=%s\n' "$t" "$tp" "$tr" "$idx" "$first" "$second"
        echo "{\"date\":\"$DATE\",\"tree_sha\":\"$sha\",\"topology\":\"$t\",\"trust_proxy\":\"$tp\",\"transports\":\"$tr\",\"probe\":$idx,\"header\":\"$hd\",\"first\":\"$first\",\"second\":\"$second\"}" >> "$jsonl"
        case "$first$second" in
          *dead*) verdict[$key]=error ;;
          *moved*) [ "${verdict[$key]}" = error ] || verdict[$key]="not protected" ;;
          *vacuous*) case "${verdict[$key]}" in protected) verdict[$key]="protected (some probes unsendable)" ;; esac ;;
        esac
      done
    done; done
  done
  {
    echo "# O2 across all client-address header families, socket handshake, AR topologies ($DATE)"
    echo
    echo "Tree \`$sha\`. The probe header rides the socket.io handshake; the observation is the"
    echo "address recorded for a wrong-secret \`authorize\`. \"protected\" = no probe moved it."
    echo "\"unsendable\" = the polling transport cannot send that header, so that probe says"
    echo "nothing for that transport. Probe detail is private. AR-L4 uses 2, the closest setting."
    echo
    echo "| topology | TRUST_PROXY | transports | O2 |"
    echo "|---|---|---|---|"
    for t in "${WS_TOPOS[@]}"; do
      IFS='|' read -r e h exp <<<"${AR[$t]}"; [ "$exp" = none ] && exp=2
      for tp in UNSET "$exp"; do for tr in "${WS_TRANSPORTS[@]}"; do
        echo "| $t | $tp | \`$tr\` | ${verdict[$t|$tp|$tr]} |"; done; done
    done
  } > "$summary"
  echo "private: $jsonl"; echo "summary: $summary"
}

# ---- W3: idle sockets vs hop timeouts (off by default) --------------------------
# Rewrites the rendered hop configs IN PLACE (same inode: they are file bind
# mounts) with proxy_read_timeout/proxy_send_timeout N on every proxied
# location, reloads, and restores the originals afterwards.
ws_set_timeouts () { # ws_set_timeouts <seconds|default>
  local R=$STATE/run/ar f c
  for f in tr gw rt rtpp; do
    [ -f "$R/$f.conf.orig" ] || cp "$R/$f.conf" "$R/$f.conf.orig"
    if [ "$1" = default ]; then cat "$R/$f.conf.orig" > "$R/$f.conf"
    else sed "s#proxy_http_version 1.1;#proxy_http_version 1.1; proxy_read_timeout ${1}s; proxy_send_timeout ${1}s;#" \
      "$R/$f.conf.orig" > "$R/$f.conf.new" && cat "$R/$f.conf.new" > "$R/$f.conf"; fi
  done
  for c in artr argw arrt arrtpp; do
    docker exec "$PFX-$c" nginx -t >/dev/null 2>&1 || { echo "FAIL $c config"; docker exec "$PFX-$c" nginx -t; return 1; }
    docker exec "$PFX-$c" nginx -s reload >/dev/null 2>&1
  done
  sleep 1
}

ws_idle () {
  [ "${WS_IDLE:-}" = 1 ] || { echo "W3 is off by default (minutes per cell); run with WS_IDLE=1" >&2; return 1; }
  ws_prep || return 1
  local topo=${WS_IDLE_TOPO:-AR-PP2} ms=${WS_IDLE_MS:-90000} e h exp
  local timeouts=(${WS_IDLE_TIMEOUTS:-20 30 default}) transports=(${WS_IDLE_TRANSPORTS:-websocket polling})
  IFS='|' read -r e h exp <<<"${AR[$topo]}"; [ "$exp" = none ] && exp=2
  local jsonl="$OUT/results-ws-idle-$DATE.jsonl"; : > "$jsonl"
  local tag=wsidle to x r
  echo "=== WS idle W3 ($DATE, $topo, tp=$exp, idle ${ms}ms, pr=$PR_SHA) ==="
  stop_ns "$tag" >/dev/null 2>&1
  boot_ns "$PR_TREE" "s66_wsidle" "$exp" "$tag" 400 true >/dev/null || { echo "DEAD"; return 1; }
  for to in "${timeouts[@]}"; do
    ws_set_timeouts "$to" || break
    for x in "${transports[@]}"; do
      r=$(probe "$(pjson idle "$e" "$h" "$x" "" "" "{\"idleMs\":$ms}")")
      assert_alive || { echo "Nightscout died during idle cell"; break 2; }
      printf 'timeout=%-8s %-10s transport=%-9s disconnects=%-3s reasons=%s connected_at_end=%s%s\n' "$to" "$x" \
        "$(jf "$r" transport)" "$(jf "$r" disconnects)" "$(jf "$r" reasons)" "$(jf "$r" connectedAtEnd)" \
        "$(e=$(jf "$r" error); [ -n "$e" ] && echo " err=$e")"
      python3 -c 'import json,sys;d=json.loads(sys.argv[1] or "{}");d.update(date=sys.argv[2],tree_sha=sys.argv[3],topology=sys.argv[4],trust_proxy=sys.argv[5],hop_timeout=sys.argv[6],requested=sys.argv[7]);print(json.dumps(d))' \
        "$r" "$DATE" "$PR_SHA" "$topo" "$exp" "$to" "$x" >> "$jsonl"
    done
  done
  ws_set_timeouts default
  stop_ns "$tag" >/dev/null 2>&1
  echo "results: $jsonl"
  python3 "$HERE/tools/ws_analyze.py" idle "$jsonl" "$OUT/ws-idle-$DATE.md" "$DATE" "$PR_SHA" "$PR_SHA"
}

case "${1:-}" in
  selftest)   ws_selftest ;;
  run)        ws_run ;;
  o2families) ws_o2families ;;
  idle)       ws_idle ;;
  status)     for c in $AR_NAMES wsclient; do printf '  %-8s %s\n' "$c" "$(docker inspect -f '{{.State.Running}}' "$PFX-$c" 2>/dev/null||echo -)"; done ;;
  down)       docker stop "$WS_CLIENT" >/dev/null 2>&1 || true; "$HERE/ar_chain.sh" down ;;
  *)          sed -n '2,37p' "$0"; exit 1 ;;
esac
