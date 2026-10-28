#!/usr/bin/env bash
# Control for write-rule-copies.js (WC-STEP-PATCH).
# Exports lib/ and bin/ at a ref into a temporary directory and runs the gate twice on that same copy:
#   positive: the copy as exported must pass;
#   negative: the copy with one planted call to the BF-194 helper in lib/server/food.js must fail,
#             and the failure must name only that (rule, file) pair.
# A red negative proves the gate sees a new copy only when the positive on the identical copy is green.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=${1:-$HERE/../../../externals/cgm-remote-monitor-official}
REF=${2:-official/dev}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git -C "$REPO" archive "$REF" lib bin | tar -x -C "$TMP"

node "$HERE/write-rule-copies.js" --tree "$TMP" > "$TMP/positive.log" 2>&1 || { echo "CONTROL BROKEN: the unplanted copy fails"; cat "$TMP/positive.log"; exit 1; }

cat >> "$TMP/lib/server/food.js" <<'EOF'
var plantedUnits = require('../treatmentTargetUnits');
function plantedCopy (doc) { return plantedUnits.normalizeTargetUnits(doc); }
EOF
if node "$HERE/write-rule-copies.js" --tree "$TMP" > "$TMP/negative.log" 2>&1; then
  echo "CONTROL FAILED: the planted copy was not seen"; cat "$TMP/negative.log"; exit 1
fi
named=$(grep -cE '^  (NEW|GREW) ' "$TMP/negative.log" || true)
if [ "$named" != 1 ] || ! grep -q 'NEW   target-units in lib/server/food.js' "$TMP/negative.log"; then
  echo "CONTROL FAILED: the failure does not name exactly the planted pair"; cat "$TMP/negative.log"; exit 1
fi
echo "control OK: unplanted copy passes, planted copy fails naming only target-units in lib/server/food.js"
