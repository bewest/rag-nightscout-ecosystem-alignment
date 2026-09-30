#!/usr/bin/env bash
# make site-publish: build the site locally and stage it as ONE commit on an
# orphan gh-pages branch in a separate worktree. Nothing is pushed; the script
# prints the force-push command for the maintainer.
#
# Refuses unless: the working tree is clean; HEAD is on a remote branch
# (skipped with DRY_RUN=1); SITE_PSEUDONYM_KEY is set; make site-check passes.
# DRY_RUN=1 stages the files into the worktree but does not commit.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
WT="${SITE_PAGES_WORKTREE:-$(dirname "$REPO")/rag-alignment-gh-pages}"
BRANCH=gh-pages
DRY="${DRY_RUN:-}"
cd "$REPO"

fail() { echo "site-publish: REFUSED: $*" >&2; exit 1; }

[ -z "$(git status --porcelain)" ] || fail "the working tree is not clean (git status --porcelain is not empty)"
if [ -z "$DRY" ]; then
  [ -n "$(git branch -r --contains HEAD)" ] || fail "HEAD $(git rev-parse --short HEAD) is not on any remote branch; push it first (or use DRY_RUN=1)"
fi
[ -n "${SITE_PSEUDONYM_KEY:-}" ] || fail "SITE_PSEUDONYM_KEY is not set"

make --no-print-directory site-check || fail "make site-check failed"

SRC_SHA="$(git rev-parse HEAD)"
BUILT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
MSG="Site build of rag-nightscout-ecosystem-alignment ${SRC_SHA} (built ${BUILT})"

# the worktree: created once, on an orphan branch
if [ ! -e "$WT/.git" ]; then
  git worktree add --detach "$WT" >/dev/null
  git -C "$WT" checkout -q --orphan "$BRANCH"
  git -C "$WT" rm -rfq --cached . 2>/dev/null || true
fi
# every publish is a fresh orphan with exactly one commit
git -C "$WT" checkout -q --orphan "${BRANCH}-next"
git -C "$WT" rm -rfq --cached . 2>/dev/null || true
find "$WT" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
rsync -a --delete --exclude .git "$REPO/build/site/" "$WT/"
touch "$WT/.nojekyll"
git -C "$WT" add -A .
FILES="$(git -C "$WT" ls-files | wc -l)"
BYTES="$(du -sb --exclude=.git "$WT" | cut -f1)"

echo "site-publish: staged ${FILES} files, $((BYTES / 1000000)) MB, into $WT"
echo "site-publish: commit message: $MSG"
if [ -n "$DRY" ]; then
  git -C "$WT" checkout -q --orphan "$BRANCH" 2>/dev/null || true
  echo "site-publish: DRY_RUN: nothing committed."
  exit 0
fi
git -C "$WT" commit -q -m "$MSG"
if git -C "$WT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git -C "$WT" branch -q -D "$BRANCH"
fi
git -C "$WT" branch -q -m "$BRANCH"
echo "site-publish: committed $(git -C "$WT" rev-parse --short HEAD) on $BRANCH (one commit, no parent)."
echo "site-publish: to publish, the maintainer runs:"
echo "  git -C $WT push --force origin $BRANCH:$BRANCH"
