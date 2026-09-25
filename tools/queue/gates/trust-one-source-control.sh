#!/usr/bin/env bash
#
# trust-one-source-control.sh — the SHARP negative control for the
# RT-TRUST-ONE-SOURCE unit gate (TEST=client-ip npm run test-single in
# externals/work/crm-trust-one-source).
#
# ablate.sh cannot serve here. It puts lib/api3/security.js back to e549e1a6,
# and that file calls clientIP.getClientIP, which rt/trust-one-source no
# longer exports: the tests then fail with a TypeError, non-zero for the wrong
# reason. This restores THE DEFECT instead, on the branch's own code: API v3
# authentication keys the failed-login delay from something other than the
# env's TRUST_PROXY (here clientIPFor(undefined), the compatibility default).
#
#   trust-one-source-control.sh [branch]      (default rt/trust-one-source)
#
# RULE 6: it builds and removes its own worktree under $TMPDIR and only reads
# node_modules from externals/work/crm-trust-one-source.
#
# IT EXITS WITH MOCHA'S STATUS, per the control convention, and must exit
# NON-ZERO. CONTROL-INVALID (exit 90) means the setup failed, the edit did not
# apply, or the tests failed for a reason other than an assertion.
set -u

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
REPO="$ROOT/externals/cgm-remote-monitor-official"
DONOR="$ROOT/externals/work/crm-trust-one-source"
BRANCH="${1:-rt/trust-one-source}"
FILE="lib/api3/security.js"
FROM='clientIP.clientIPFor(env)(req)'
TO='clientIP.clientIPFor(undefined)(req)'

invalid () { echo "CONTROL-INVALID: $*"; exit 90; }

[ -d "$DONOR/node_modules" ] || invalid "no node_modules in $DONOR"

WT="$(mktemp -d "${TMPDIR:-/tmp}/queue-trust-one-source-XXXXXX")"
cleanup () {
  git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1
  rm -rf "$WT"
  git -C "$REPO" worktree prune >/dev/null 2>&1
}
trap cleanup EXIT
rmdir "$WT"

git -C "$REPO" worktree add --detach "$WT" "$BRANCH" >/dev/null 2>&1 \
  || invalid "could not create a throwaway worktree of $BRANCH"
ln -s "$DONOR/node_modules" "$WT/node_modules"

grep -qF "$FROM" "$WT/$FILE" || invalid "$FILE on $BRANCH no longer contains $FROM"
sed -i "s/clientIP\.clientIPFor(env)(req)/clientIP.clientIPFor(undefined)(req)/" "$WT/$FILE"
grep -qF "$TO" "$WT/$FILE" || invalid "the edit to $FILE did not apply"

out="$( cd "$WT" && ./node_modules/.bin/mocha --timeout 5000 --exit tests/client-ip.test.js 2>&1 )"
rc=$?
echo "$out" | grep -E "passing|failing|^  [0-9]+\) "
echo "mutated $BRANCH/$FILE -> exit $rc"
if [ "$rc" -ne 0 ]; then
  echo "$out" | grep -q "AssertionError" || invalid "tests failed without an AssertionError"
  echo "$out" | grep -qE "TypeError|ReferenceError|Cannot find module" \
    && invalid "tests failed with a load or type error, not the restored defect"
fi
exit "$rc"
