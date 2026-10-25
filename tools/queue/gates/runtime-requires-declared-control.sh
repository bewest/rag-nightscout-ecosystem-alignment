#!/usr/bin/env bash
# runtime-requires-declared-control.sh — the negative control for
# runtime-requires-declared.js (BF-176). Four known-negative states, and the
# gate must refuse ALL of them:
#
#   1. the released tag v15.0.9 (immutable): axios is only a devDependency and
#      lodash is undeclared;
#   1b. dev at eb72a1d3 (a commit id, so it cannot go stale when the fix
#      merges): 16.0.0 with cut 1 (#8828) merged, the same two findings, and
#      the tree where the IMPORT_CONFIG boot crash is measured;
#   2. a scratch copy of <ref> (default official/dev, where the gate passes
#      since #8834 merged as 93f152bd) with one extra
#      require('webpack-hot-middleware') appended to the end of
#      lib/server/app.js, OUTSIDE the NODE_ENV === 'development' block;
#   3. a fresh scratch copy of <ref> with one extra require('webpack') appended
#      the same way. webpack joined the allowlist on 2026-10-25 because cut 2
#      (#8837) makes it a devDependency required inside the guard; this case
#      proves that entry is bounded by the guard too, on dev (webpack under
#      dependencies) as on cut 2 (devDependencies).
#
# Before each mutation the gate is run on the unmutated scratch copy and must
# PASS there, so a refusal of the mutated copy is caused by the stray require
# and not by something else in <ref>.
#
# Exit status, for tools/queue/vacuity.py: NON-ZERO when the gate refused all
# four (the gate works); ZERO when the gate passed on any negative (vacuous), or
# when a scratch copy could not be made or the gate already fails on <ref>
# unmutated (printed as CONTROL-ERROR, and zero on purpose so it can never read
# as a working gate).
#
# Reads the object database with git archive into a temporary directory; never
# touches a worktree.

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${QUEUE_GATE_ROOT:-$(cd "$HERE/../../.." && pwd)}"
CRM="$ROOT/externals/cgm-remote-monitor-official"
REF="${1:-official/dev}"
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

stray() {
  # $1 case number, $2 package id
  local dir="$SCRATCH/$1"
  mkdir -p "$dir"
  if ! git -C "$CRM" archive "$REF" package.json server.js bin lib | tar -x -C "$dir"; then
    echo "CONTROL-ERROR: could not archive $REF"
    exit 0
  fi
  if ! RUNTIME_REQUIRES_TREE="$dir" node "$GATE" >/dev/null; then
    echo "CONTROL-ERROR: the gate already fails on $REF unmutated; the stray-require case would be red for another reason"
    exit 0
  fi
  local app="$dir/lib/server/app.js"
  local pat="require(\"$2\")\\|require('$2')"
  local before after
  before="$(grep -c "$pat" "$app")"
  printf "\nconst strayRequire%s = require('%s');\n" "$1" "$2" >> "$app"
  after="$(grep -c "$pat" "$app")"
  if [ "$after" -ne $((before + 1)) ]; then
    echo "CONTROL-ERROR: the stray require of $2 was not added ($before -> $after)"
    exit 0
  fi
  echo "control $1: $REF with require('$2') appended outside the guard"
  if RUNTIME_REQUIRES_TREE="$dir" node "$GATE"; then
    echo "control $1 PASSED: the gate accepts a require of $2 outside the development guard (vacuous)"
    exit 0
  fi
}

stray 2 webpack-hot-middleware
stray 3 webpack
echo "all four negatives refused"
exit 1
