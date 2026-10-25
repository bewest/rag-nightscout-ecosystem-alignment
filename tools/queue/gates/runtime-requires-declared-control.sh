#!/usr/bin/env bash
# runtime-requires-declared-control.sh — the negative control for
# runtime-requires-declared.js (BF-176). Three known-negative states, and the
# gate must refuse ALL of them:
#
#   1. the released tag v15.0.9 (immutable): axios is only a devDependency and
#      lodash is undeclared;
#   1b. dev at eb72a1d3 (a commit id, so it cannot go stale when the fix
#      merges): 16.0.0 with cut 1 (#8828) merged, the same two findings, and
#      the tree where the IMPORT_CONFIG boot crash is measured;
#   2. a scratch copy of <ref> (default bf/axios-runtime-dependency, where the
#      gate passes) with one extra require('webpack-hot-middleware') appended
#      to the end of lib/server/app.js, OUTSIDE the NODE_ENV === 'development'
#      block. This proves the allowlist is bounded by the guard, not by the
#      package name.
#
# Exit status, for tools/queue/vacuity.py: NON-ZERO when the gate refused all
# three (the gate works); ZERO when the gate passed on any negative (vacuous), or
# when the mutation could not be made (printed as CONTROL-ERROR, and zero on
# purpose so it can never read as a working gate).
#
# Reads the object database with git archive into a temporary directory; never
# touches a worktree.

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${QUEUE_GATE_ROOT:-$(cd "$HERE/../../.." && pwd)}"
CRM="$ROOT/externals/cgm-remote-monitor-official"
REF="${1:-bf/axios-runtime-dependency}"
GATE="$HERE/runtime-requires-declared.js"

echo "control 1: RUNTIME_REQUIRES_REF=v15.0.9"
if RUNTIME_REQUIRES_REF=v15.0.9 node "$GATE"; then
  echo "control 1 PASSED: the gate accepts v15.0.9 (vacuous)"
  exit 0
fi

echo "control 1b: RUNTIME_REQUIRES_REF=eb72a1d3 (dev, 16.0.0 with cut 1 merged)"
if ! git -C "$CRM" cat-file -e eb72a1d3^{commit} 2>/dev/null; then
  echo "CONTROL-ERROR: eb72a1d3 is not in $CRM (git fetch official)"
  exit 0
fi
if RUNTIME_REQUIRES_REF=eb72a1d3 node "$GATE"; then
  echo "control 1b PASSED: the gate accepts dev eb72a1d3 (vacuous)"
  exit 0
fi

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
if ! git -C "$CRM" archive "$REF" package.json server.js bin lib | tar -x -C "$SCRATCH"; then
  echo "CONTROL-ERROR: could not archive $REF"
  exit 0
fi
APP="$SCRATCH/lib/server/app.js"
before="$(grep -c "require(\"webpack-hot-middleware\")\|require('webpack-hot-middleware')" "$APP")"
printf "\nconst strayHotMiddleware = require('webpack-hot-middleware');\n" >> "$APP"
after="$(grep -c "require(\"webpack-hot-middleware\")\|require('webpack-hot-middleware')" "$APP")"
if [ "$after" -ne $((before + 1)) ]; then
  echo "CONTROL-ERROR: the stray require was not added ($before -> $after)"
  exit 0
fi

echo "control 2: $REF with require('webpack-hot-middleware') appended outside the guard"
if RUNTIME_REQUIRES_TREE="$SCRATCH" node "$GATE"; then
  echo "control 2 PASSED: the gate accepts a require outside the development guard (vacuous)"
  exit 0
fi
echo "all three negatives refused"
exit 1
