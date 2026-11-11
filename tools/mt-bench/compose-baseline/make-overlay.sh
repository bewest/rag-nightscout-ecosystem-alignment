#!/usr/bin/env bash
# Builds the bootstrap overlay: core's deploy/multitenant/{config.js,bootstrap.js} at the commit under
# test, plus the nightscout-deploy bench fixes (the diff between two deploy commits), nothing else.
#   make-overlay.sh <core-checkout> <core-commit> <deploy-checkout> <deploy-base> <deploy-head> <out-dir>
set -euo pipefail
core=$1 commit=$2 deploy=$3 from=$4 to=$5 out=$6
[ -e "$out" ] && { echo "exists: $out" >&2; exit 1; }
mkdir -p "$out"
for f in config.js bootstrap.js; do git -C "$core" show "$commit:deploy/multitenant/$f" > "$out/$f"; done
git -C "$deploy" diff "$from" "$to" -- bindings/compose/multitenant/config.js bindings/compose/multitenant/bootstrap.js \
  | patch --quiet --no-backup-if-mismatch -F3 -p4 -d "$out"
# Fuzz 3: next to fix 1 the deploy tree omits core's ownership_operator grant lines (its own delta).
# The bench run checks the result against the overlay it was measured with (PROVENANCE sha256).
{ echo "core $commit"; echo "deploy $from..$to"; sha256sum "$out"/config.js "$out"/bootstrap.js; } > "$out/PROVENANCE"
cat "$out/PROVENANCE"
