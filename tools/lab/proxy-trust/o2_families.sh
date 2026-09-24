#!/usr/bin/env bash
# o2_families.sh - O2 across every client-address header family the
# compatibility path reads, not only one.
#
# For each topology x TRUST_PROXY setting (unset, and the topology's right
# setting) x probe in the PRIVATE probes file: boot Nightscout, send the probe
# through the front end as a failed authentication, then send it again with a
# second value. Both attempts are recorded.
#
# The probes (which headers, which values) live only in $PROXYLAB_PRIVATE_PROBES.
# Per-probe results go to $PROXYLAB_PRIVATE_RESULTS. The tracked summary says,
# per topology and setting, only "protected" (no probe moved the address on any
# attempt) or "not protected".
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
LAB_SOURCED=1 . "$HERE/lab.sh"

PRIV=${PROXYLAB_PRIVATE_PROBES:?set PROXYLAB_PRIVATE_PROBES to the private probes file}
PRES=${PROXYLAB_PRIVATE_RESULTS:?set PROXYLAB_PRIVATE_RESULTS to a gitignored directory}
TREE=${O2_TREE:-${DELAY_TREE:-$PR_TREE}}
OUT="$STATE/out"; mkdir -p "$OUT" "$PRES"
DATE=$(date +%F)
SHA=$(git -C "$TREE" rev-parse --short HEAD)
JSONL="$PRES/o2-families-$DATE.jsonl"; : > "$JSONL"
SUMMARY="$OUT/o2-families-$DATE.md"

declare -A ENTRY=(
  [F0]="$GW:$NSPORT" [F1]="$IP_F1" [F2]="$IP_F2" [F3]="$IP_F3F"
  [F4]="$IP_F4" [F5]="$IP_F5" [F6]="$IP_F6" [TLS]="$IP_TLS" [LB]="$IP_LBF"
)
# The setting each topology needs to resolve the real client (lab-measured).
declare -A RIGHT=( [F0]=false [F1]=1 [F2]=1 [F3]=2 [F4]=1 [F5]=1 [F6]=1 [TLS]=1 [LB]=2 )
TOPOS=${O2_TOPOS:-"F0 F1 F2 F3 F4 F5 F6 TLS LB"}

# probe list: index<TAB>header<TAB>value<TAB>second value, read from the private
# file only. The second attempt uses a different value, so an address recorded
# by the first attempt cannot be mistaken for the second.
mapfile -t PROBES < <(python3 - "$PRIV" <<'EOF'
import json, sys
p = json.load(open(sys.argv[1]))
alt = p["spoof_ip_alt"]
for i, pr in enumerate(p["o2_single_header_probes"]):
    print(f'{i}\t{pr["header"]}\t{pr["value"]}\t{alt}')
EOF
)
[ "${#PROBES[@]}" -gt 0 ] || { echo "no probes in $PRIV" >&2; exit 2; }

probe_once () { # probe_once <scheme> <feip> <header> <value> <label> -> "moved"|"held"|"dead"
  local sch=$1 feip=$2 h=$3 v=$4 label=$5
  client_get "$PFX-client" "$sch://$feip/api/v1/entries.json" \
     -H "$h: $v" -H "api-secret: $(wrongsecret "o2f-$label")" >/dev/null
  assert_alive || { echo dead; return; }
  # notify_ips is comma-joined and accumulates for the life of the process
  notify_ips | tr ',' '\n' | grep -qxF "$v" && echo moved || echo held
}

declare -A VERDICT
for topo in $TOPOS; do
  feip=${ENTRY[$topo]}; sch=http; [ "$topo" = TLS ] && sch=https
  for tp in UNSET "${RIGHT[$topo]}"; do
    key="$topo|$tp"; VERDICT[$key]=protected
    for line in "${PROBES[@]}"; do
      IFS=$'\t' read -r idx h v v2 <<<"$line"
      tag="o2f"; db="s66_o2f_${topo}_$(echo "$tp"|tr -c 'A-Za-z0-9' _)_$idx"
      stop_ns "$tag" >/dev/null 2>&1
      boot_ns "$TREE" "$db" "$tp" "$tag" 400 true >/dev/null || { VERDICT[$key]=error; continue; }
      first=$(probe_once "$sch" "$feip" "$h" "$v" "$topo-$tp-$idx-first")
      client_get "$PFX-client" "$sch://$feip/api/v1/entries.json" \
         -H "api-secret: $(wrongsecret "o2f-honest-$topo-$tp-$idx")" >/dev/null
      second=$(probe_once "$sch" "$feip" "$h" "$v2" "$topo-$tp-$idx-second")
      stop_ns "$tag" >/dev/null 2>&1
      printf '%-4s tp=%-6s probe=%s first=%s second=%s\n' "$topo" "$tp" "$idx" "$first" "$second"
      echo "{\"date\":\"$DATE\",\"tree_sha\":\"$SHA\",\"topology\":\"$topo\",\"trust_proxy\":\"$tp\",\"probe\":$idx,\"header\":\"$h\",\"first\":\"$first\",\"second\":\"$second\"}" >> "$JSONL"
      case "$first$second" in
        *dead*) VERDICT[$key]=error ;;
        *moved*) [ "${VERDICT[$key]}" = error ] || VERDICT[$key]="not protected" ;;
      esac
    done
  done
done

{
  echo "# O2 across all client-address header families ($DATE)"
  echo
  echo "Tree \`$SHA\`. \"protected\" = no probe in the private set moved the resolved"
  echo "address on any attempt. Probe detail is private."
  echo
  echo "| topology | TRUST_PROXY | O2 |"
  echo "|---|---|---|"
  for topo in $TOPOS; do for tp in UNSET "${RIGHT[$topo]}"; do
    echo "| $topo | $tp | ${VERDICT[$topo|$tp]} |"; done; done
} > "$SUMMARY"
echo "private: $JSONL"
echo "summary: $SUMMARY"
