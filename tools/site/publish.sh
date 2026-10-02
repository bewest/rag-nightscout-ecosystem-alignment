#!/usr/bin/env bash
# make site-publish: build the site locally and commit it to the gh-pages branch
# in a separate worktree. Nothing is pushed; the script prints the push command.
#
# By default the build is APPENDED: one new commit whose parent is the remote's
# current gh-pages (origin/gh-pages, fetched first), so the push is a plain
# fast-forward. If someone else publishes in between, that push is rejected
# instead of overwriting their build; re-run make site-publish.
#
# PURGE=1 instead makes the build the only commit of a fresh orphan branch,
# dropping every earlier build from the branch's history (for removing
# something that should never have been published). That needs a force-push,
# which the script prints with a lease on the gh-pages it fetched.
#
# Refuses unless: the working tree is clean; HEAD is on a remote branch
# (skipped with DRY_RUN=1); SITE_PSEUDONYM_KEY is set; make site-check passes.
# DRY_RUN=1 stages the files into the worktree but does not commit.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
WT="${SITE_PAGES_WORKTREE:-$(dirname "$REPO")/rag-alignment-gh-pages}"
BRANCH=gh-pages
DRY="${DRY_RUN:-}"
PURGE="${PURGE:-}"
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

# the worktree: created once
if [ ! -e "$WT/.git" ]; then
  git worktree add --detach "$WT" >/dev/null
fi

# the build to append to: the remote's gh-pages as it is now
git -C "$WT" fetch -q origin "$BRANCH" 2>/dev/null || true
BASE="$(git -C "$WT" rev-parse -q --verify "refs/remotes/origin/$BRANCH^{commit}" || true)"

# stage the build on an unborn branch, so the index holds exactly build/site
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
  echo "site-publish: DRY_RUN: nothing committed."
  exit 0
fi

TREE="$(git -C "$WT" write-tree)"
if [ -n "$PURGE" ] || [ -z "$BASE" ]; then
  NEW="$(git -C "$WT" commit-tree "$TREE" -m "$MSG")"
  HOW="one commit, no parent"
else
  if [ "$TREE" = "$(git -C "$WT" rev-parse "$BASE^{tree}")" ]; then
    git -C "$WT" checkout -q -f "$BRANCH" 2>/dev/null || git -C "$WT" checkout -q -f --detach "$BASE"
    echo "site-publish: the build is identical to origin/$BRANCH $(git -C "$WT" rev-parse --short "$BASE"); nothing to publish."
    exit 0
  fi
  NEW="$(git -C "$WT" commit-tree "$TREE" -p "$BASE" -m "$MSG")"
  HOW="on top of origin/$BRANCH $(git -C "$WT" rev-parse --short "$BASE")"
fi
git -C "$WT" checkout -q --detach "$NEW"
git -C "$WT" branch -q -f "$BRANCH" "$NEW"
git -C "$WT" checkout -q "$BRANCH"
echo "site-publish: committed $(git -C "$WT" rev-parse --short HEAD) on $BRANCH ($HOW)."
echo "site-publish: to publish, the maintainer runs:"
if [ -n "$PURGE" ] && [ -n "$BASE" ]; then
  echo "  git -C $WT push --force-with-lease=$BRANCH:$BASE origin $BRANCH:$BRANCH"
else
  echo "  git -C $WT push origin $BRANCH:$BRANCH"
fi
