#!/usr/bin/env bash
# run.sh — run both hubs over records/cases.json and compare.
#
# Usage: tools/lab/hub-active-state/run.sh <cgm-remote-monitor tree> <nocturne tree> [outdir]
#   <cgm-remote-monitor tree>  a checkout or archive of the commit under test, with node_modules
#   <nocturne tree>            a checkout or archive of the commit under test (the harness is
#                              copied into <tree>/tests/Lab/HubActiveState and built there)
#   [outdir]                   default: results/ next to this script
# fetch-trees.sh downloads both trees at the commits RESULTS.md names.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
CRM=$(cd "$1" && pwd)
NOC=$(cd "$2" && pwd)
OUT=${3:-$HERE/results}
LOGS=${LOGS:-$(mktemp -d)}   # build and stderr logs carry local paths; kept out of results/
mkdir -p "$OUT"

# cases.json must be what make-records.js writes
node "$HERE/records/make-records.js" | cmp - "$HERE/records/cases.json"

node "$HERE/crm-probe.js" "$CRM" "$HERE/records/cases.json" > "$OUT/crm.json" 2> "$LOGS/crm.stderr.log"

LAB="$NOC/tests/Lab/HubActiveState"
mkdir -p "$LAB"
cp "$HERE/nocturne-harness/HubActiveState.csproj" "$HERE/nocturne-harness/Program.cs" "$LAB/"
dotnet build "$LAB/HubActiveState.csproj" -c Release -p:GenerateNSwagClient=false > "$LOGS/nocturne-build.log" 2>&1 \
  || { tail -n 30 "$LOGS/nocturne-build.log"; exit 2; }
DLL="$LAB/bin/Release/net10.0/HubActiveState.dll"
dotnet "$DLL" "$HERE/records/cases.json" > "$OUT/nocturne.json" 2> "$LOGS/nocturne.stderr.log"
dotnet "$DLL" "$HERE/records/cases.json" --mock-dedup > "$OUT/nocturne-mockdedup.json" 2>> "$LOGS/nocturne.stderr.log"

node "$HERE/compare.js" "$OUT/crm.json" "$OUT/nocturne.json" "$OUT/nocturne-mockdedup.json" > "$OUT/compare.md"
node "$HERE/compare.js" --selftest "$OUT/crm.json"
cat "$OUT/compare.md"
echo "logs: $LOGS" >&2
