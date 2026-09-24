#!/usr/bin/env bash
# run_matrix.sh - drive the proxy-trust matrix and emit results.
#
# Honest-client cells (O1, O5) always run. Adversarial cells (O2 spoof, O3
# guesser, O4 throttle-scope) run only when $PROXYLAB_PRIVATE_PROBES points at
# the private probes file. Full results (with any spoof addresses) are written
# under the private results dir when available; a SANITISED markdown table
# (protected / not protected only) is written to the tracked out dir.
#
# Reuses all config + boot/stop/observe helpers from lab.sh.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
LAB_SOURCED=1 . "$HERE/lab.sh"

PRIV=${PROXYLAB_PRIVATE_PROBES:-}
OUT="$STATE/out"; mkdir -p "$OUT"
FULL="${PROXYLAB_PRIVATE_RESULTS:-$OUT}"; mkdir -p "$FULL"
DATE=$(date +%F)
DEV_SHA=$(git -C "$DEV_TREE" rev-parse --short HEAD 2>/dev/null || echo dev)
PR_SHA=$(git -C "$PR_TREE" rev-parse --short HEAD 2>/dev/null || echo pr)
# The adversarial probe (header and value) comes only from the private file.
SPOOF_H=""; SPOOF=""
if [ -n "$PRIV" ]; then
  SPOOF_H=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["o2_chain_injection"]["header"])' "$PRIV") || exit 2
  SPOOF=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["o2_chain_injection"]["value"])' "$PRIV") || exit 2
fi

JSONL="$FULL/results-$DATE.jsonl"; : > "$JSONL"

# topology -> client entry IP (the front end the client connects to)
declare -A ENTRY=(
  [F0]="$GW:$NSPORT" [F1]="$IP_F1" [F2]="$IP_F2" [F3]="$IP_F3F"
  [F4]="$IP_F4" [F5]="$IP_F5" [F6]="$IP_F6" [TLS]="$IP_TLS" [LB]="$IP_LBF"
)
# topology -> scheme
scheme_for () { [ "$1" = TLS ] && echo https || echo http; }

emit () { # emit <json object as key=val pairs already formatted> -> jsonl
  echo "$1" >> "$JSONL"; }

# One cell: reboot, assert liveness, honest O1, optional adversarial O2.
cell () { # cell <topology> <tree_dir> <tree_label> <tp>
  local topo=$1 tree=$2 tlabel=$3 tp=$4
  local feip=${ENTRY[$topo]} sch; sch=$(scheme_for "$topo")
  local tag="cell" db="s66_${topo}_${tlabel}_$(echo "$tp"|tr -c 'A-Za-z0-9' _)"
  stop_ns "$tag" >/dev/null 2>&1
  local boot; boot=$(boot_ns "$tree" "$db" "$tp" "$tag" 400 true) || { echo "SKIP $topo/$tlabel/$tp (dead)"; return; }
  assert_alive || { echo "SKIP $topo/$tlabel/$tp (not alive)"; return; }

  # O1 honest: client at IP_CLIENT, WRONG secret, NO forwarding header
  client_get "$PFX-client" "$sch://$feip/api/v1/entries.json" \
     -H "api-secret: $(wrongsecret "o1-$topo-$tlabel-$tp")" >/dev/null
  local o1; o1=$(notify_ips)

  local o2="skipped" spoofseen="n/a"
  if [ -n "$PRIV" ]; then
    # O2 adversarial: client supplies a spoof forwarding header (recipe in $PRIV)
    client_get "$PFX-client" "$sch://$feip/api/v1/entries.json" \
       -H "$SPOOF_H: $SPOOF" \
       -H "api-secret: $(wrongsecret "o2-$topo-$tlabel-$tp")" >/dev/null
    local all; all=$(notify_ips)
    if echo "$all" | tr ',' '\n' | grep -qxF "$SPOOF"; then o2="not-protected"; spoofseen="yes"; else o2="protected"; spoofseen="no"; fi
  fi

  printf '%-4s %-6s tp=%-9s O1=%-15s O2=%s\n' "$topo" "$tlabel" "$tp" "$o1" "$o2"
  emit "{\"date\":\"$DATE\",\"topology\":\"$topo\",\"tree\":\"$tlabel\",\"tree_sha\":\"$([ "$tlabel" = dev ] && echo "$DEV_SHA" || echo "$PR_SHA")\",\"trust_proxy\":\"$tp\",\"o1_resolved\":\"$o1\",\"o2\":\"$o2\",\"spoof_seen\":\"$spoofseen\",\"client_ip\":\"$IP_CLIENT\"}"
  stop_ns "$tag" >/dev/null 2>&1
}

SETTINGS=(UNSET false 1 2 10.9.9.9 true)

echo "=== honest + adversarial matrix ($DATE, dev=$DEV_SHA pr=$PR_SHA, probes=$([ -n "$PRIV" ] && echo ON || echo OFF)) ==="
# unset on BOTH trees (the no-breaking-change-by-default evidence)
cell F1 "$DEV_TREE" dev UNSET
cell F1 "$PR_TREE"  pr  UNSET
# PR across all settings, key topologies
for topo in F0 F1 F2 F3 F4 F5 F6 LB; do
  for s in "${SETTINGS[@]}"; do cell "$topo" "$PR_TREE" pr "$s"; done
done

echo "results (full): $JSONL"
python3 "$HERE/tools/analyze.py" "$JSONL" "$OUT/matrix-$DATE.md" "$DATE" "$DEV_SHA" "$PR_SHA"
echo "sanitised markdown: $OUT/matrix-$DATE.md"
