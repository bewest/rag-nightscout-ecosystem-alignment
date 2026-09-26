#!/bin/bash
# prcheck.sh <worktree> : merge official/dev into the worktree's branch if needed,
# run the full suite on a freshly dropped database (Node 22, MongoDB 7), and show
# what a push would send. Never pushes.
set -euo pipefail
WT=${1:?usage: prcheck.sh <worktree>}
HERE=${PRCHECK_OUT:-/tmp/prcheck}; mkdir -p "$HERE"
# One run at a time: every run shares one database and port.
exec 9>"$HERE/.lock"
flock -n 9 || { echo "== another prcheck run is in progress; waiting for it"; flock 9; }
NODE22=$HOME/n/n/versions/node/22.23.2/bin
cd "$WT"
B=$(git branch --show-current)
[ -n "$B" ] || { echo "detached HEAD in $WT"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "uncommitted changes in $WT"; git status --short; exit 1; }

git fetch -q official
DEV=$(git rev-parse --short official/dev)
if git merge-base --is-ancestor official/dev HEAD; then
  echo "== $B already contains official/dev $DEV"
  MERGED=0
else
  echo "== merging official/dev $DEV into $B"
  git merge --no-edit official/dev || { echo "MERGE CONFLICT: resolve in $WT, commit, then re-run"; exit 1; }
  MERGED=1
fi

if [ "$MERGED" = 1 ] && ! git diff --quiet ORIG_HEAD HEAD -- package.json package-lock.json; then
  echo "== package files changed: npm ci"
  PATH=$NODE22:$PATH npm ci >"$HERE/prcheck-npm.log" 2>&1
fi

if ! docker ps --format '{{.Names}}' | grep -qx prcheck-mongo7; then
  docker rm -f prcheck-mongo7 >/dev/null 2>&1 || true
  docker run -d --name prcheck-mongo7 --ulimit nofile=64000:64000 -p 127.0.0.1:27990:27017 mongo:7.0.43 >/dev/null
  sleep 5
fi
docker exec prcheck-mongo7 mongosh --quiet --eval 'db.getSiblingDB("prcheck_testdb").dropDatabase()' >/dev/null
echo "== mongod $(docker exec prcheck-mongo7 mongosh --quiet --eval 'db.version()'), node $($NODE22/node --version)"

ENVF="$HERE/prcheck.env"
sed -e 's#^CUSTOMCONNSTR_mongo=.*#CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:27990/prcheck_testdb#' \
    -e 's#^PORT=.*#PORT=17990#' my.test.env > "$ENVF"
LOG="$HERE/prcheck-$(echo "$B" | tr / -).log"
echo "== full suite (log: $LOG)"
set +e
PATH=$NODE22:$PATH npx env-cmd -f "$ENVF" mocha --timeout 5000 --require ./tests/hooks.js --exit ./tests/*.test.js >"$LOG" 2>&1
RC=$?
set -e
grep -E '^\s+[0-9]+ (passing|failing|pending)' "$LOG" | sed 's/^ */   /'
[ "$RC" = 0 ] || { echo "SUITE FAILED (exit $RC): see $LOG; do not push"; exit 1; }

echo "== the push would send $(git rev-list --count official/dev..HEAD) commit(s) on official/dev $DEV:"
git log --format='   %h %an: %s' official/dev..HEAD
git ls-remote --exit-code --heads official "$B" >/dev/null && echo "   (official/$B already exists)" || echo "   (official/$B does not exist yet)"
echo "OK"
