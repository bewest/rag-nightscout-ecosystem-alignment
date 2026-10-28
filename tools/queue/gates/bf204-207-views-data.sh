#!/bin/sh
# bf204-207-views-data.sh — BFQ-204..207 (BF-204 ddata/at frame, BF-205
# same-mills order, BF-206 untimestamped device IOB, BF-207 sage burst).
#
# Runs one of the fix branch's test files twice, each time in a tree extracted
# with git archive (the checkout's working tree is not kept at any ref):
#   1. the fix ref as it is: the file must pass;
#   2. the same tree with lib/ replaced by the control ref's lib/: the file must
#      fail, and on an AssertionError, not a timeout or a thrown error.
# The gate is met only when both hold, so a test that cannot see its defect, or
# that fails for the wrong reason, is reported rather than counted.
#
# node_modules come from a tree installed at the fix ref (NODE_MODULES_FROM,
# default the fix branch's worktree). The official clone's own node_modules is
# older: under it dev's Express 5 routes answer 404, which reads as a failure of
# the test. The gate refuses to run when the installed express is not the one
# the fix ref's package-lock.json names.
#
#   usage: bf204-207-views-data.sh <test file> [fix ref] [control ref]
#   e.g.   bf204-207-views-data.sh tests/data.ddata-at.test.js
test_file="$1"
fix_ref="${2:-bf/16.0.0-views-data}"
control_ref="${3:-db3b9e4e}"
crm=externals/cgm-remote-monitor-official
modules="${NODE_MODULES_FROM:-externals/work/crm-bf-views}/node_modules"
[ -n "$test_file" ] || { echo "usage: $0 <test file> [fix ref] [control ref]"; exit 2; }
[ -d "$modules" ] || { echo "UNMEASURED: no node_modules at $modules (set NODE_MODULES_FROM to a tree installed at $fix_ref)"; exit 2; }
want=$(git -C "$crm" show "$fix_ref:package-lock.json" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>console.log(JSON.parse(s).packages["node_modules/express"].version))')
have=$(node -p "require('$PWD/$modules/express/package.json').version")
[ "$want" = "$have" ] || { echo "UNMEASURED: $modules has express $have, $fix_ref locks $want"; exit 2; }

run_in () {
  # $1 tree; prints mocha's output, returns its exit status
  ( cd "$1" && NODE_ENV=test ./node_modules/.bin/mocha --timeout 15000 --require ./tests/hooks.js --exit "$test_file" 2>&1 )
}

fix=$(mktemp -d) && control=$(mktemp -d) || exit 2
trap 'rm -rf "$fix" "$control"' EXIT
git -C "$crm" archive "$fix_ref" | tar -x -C "$fix" || exit 2
git -C "$crm" archive "$fix_ref" | tar -x -C "$control" || exit 2
rm -rf "$control/lib"
git -C "$crm" archive "$control_ref" lib | tar -x -C "$control" || exit 2
ln -s "$PWD/$modules" "$fix/node_modules"
ln -s "$PWD/$modules" "$control/node_modules"

out=$(run_in "$fix"); fix_rc=$?
echo "$out" | grep -E '^\s+[0-9]+ (passing|failing|pending)' | sed "s|^|  $fix_ref: |"
out_c=$(run_in "$control"); control_rc=$?
echo "$out_c" | grep -E '^\s+[0-9]+ (passing|failing|pending)' | sed "s|^|  lib at $control_ref: |"

if [ "$fix_rc" -ne 0 ]; then
  echo "NOT MET: $test_file fails on $fix_ref"
  echo "$out" | tail -30
  exit 1
fi
if [ "$control_rc" -eq 0 ]; then
  echo "NOT MET: $test_file passes with lib/ at $control_ref, so it cannot see the defect"
  exit 1
fi
if ! echo "$out_c" | grep -q 'AssertionError' || echo "$out_c" | grep -q 'Timeout of'; then
  echo "NOT MET: the control fails, but not only on assertions (a timeout or a thrown error)"
  echo "$out_c" | grep -E 'Error' | head -10
  exit 1
fi
echo "met: $test_file passes on $fix_ref and fails on assertions with lib/ at $control_ref"
