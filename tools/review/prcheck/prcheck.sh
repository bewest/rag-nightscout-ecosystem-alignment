#!/bin/bash
# prcheck.sh <worktree> : the last step before pushing a fix branch. Fetch
# official, merge official/dev into the worktree's branch if other PRs have
# landed, and show what a push would send. Fast: it runs no tests. Test the
# branch before calling it ready; if this merge brings in files the branch also
# changes, it says so, and those tests are worth re-running. Never pushes.
set -euo pipefail
WT=${1:?usage: prcheck.sh <worktree>}
cd "$WT"
B=$(git branch --show-current)
[ -n "$B" ] || { echo "detached HEAD in $WT"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "uncommitted changes in $WT"; git status --short; exit 1; }

git fetch -q official
DEV=$(git rev-parse --short official/dev)
if git merge-base --is-ancestor official/dev HEAD; then
  echo "== $B already contains official/dev $DEV"
else
  BASE=$(git merge-base HEAD official/dev)
  echo "== merging official/dev $DEV into $B ($(git rev-list --count HEAD..official/dev) new commit(s) on dev)"
  git merge --no-edit official/dev || { echo "MERGE CONFLICT: resolve in $WT, commit, then re-run"; exit 1; }
  OVERLAP=$(comm -12 <(git diff --name-only "$BASE" ORIG_HEAD | sort) <(git diff --name-only "$BASE" official/dev | sort))
  if [ -n "$OVERLAP" ]; then
    echo "== dev also changed files this branch changes; re-run their tests before pushing:"
    echo "$OVERLAP" | sed 's/^/   /'
  fi
  git diff --quiet ORIG_HEAD HEAD -- package.json package-lock.json \
    || echo "== package files changed on dev: run npm ci before testing"
fi

echo "== the push would send $(git rev-list --count official/dev..HEAD) commit(s) on official/dev $DEV:"
git log --format='   %h %an: %s' official/dev..HEAD
STAT=$(git diff --shortstat official/dev HEAD)
[ -n "$STAT" ] && echo "  $STAT"
git ls-remote --exit-code --heads official "$B" >/dev/null && echo "   (official/$B already exists)" || echo "   (official/$B does not exist yet)"
echo "OK"
