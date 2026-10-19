#!/usr/bin/env bash
#
# id-conventions-control.sh — the NEGATIVE CONTROL for id-conventions.js.
# Copies the conventions page to a scratch root, deletes the "device status /
# Loop" row there, and runs the gate against that root (QUEUE_GATE_ROOT). Exits
# with the gate's status, which must be non-zero, and prints its BAD line.
# Never writes outside its scratch directory.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
REL=docs/30-design/platform/identifier-conventions.md
[ -f "$ROOT/$REL" ] || { echo "CONTROL-INVALID: no $REL"; exit 90; }
T="$(mktemp -d "${TMPDIR:-/tmp}/id-conventions-control-XXXXXX")"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/$(dirname "$REL")"
grep -v '^| device status | Loop ' "$ROOT/$REL" > "$T/$REL"
cmp -s "$ROOT/$REL" "$T/$REL" && { echo "CONTROL-INVALID: no device status / Loop row to delete"; exit 90; }
QUEUE_GATE_ROOT="$T" node "$ROOT/tools/queue/gates/id-conventions.js" > "$T/out" 2>&1
rc=$?
grep -E 'BAD|failing' "$T/out"
exit $rc
