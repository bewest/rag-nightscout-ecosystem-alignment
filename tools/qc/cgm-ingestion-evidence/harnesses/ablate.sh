#!/usr/bin/env bash
# Ablation harness v2: THROWAWAY worktree of <branch>; revert shipping code to
# <base> (restoring files that exist on base, DELETING files the branch added);
# keep the branch's tests; run <tests>. Expect FAILURE.
# v1 was itself vacuous: `git checkout base -- <file-not-on-base>` aborts the
# whole checkout, so nothing was reverted and the ablation reported green.
set -u
SP=/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad
REPO="$1"; BRANCH="$2"; BASE="$3"; DONOR="$4"; shift 4
WT="$SP/ab-$(echo "$BRANCH" | tr '/' '-')"
git -C "$REPO" worktree remove --force "$WT" 2>/dev/null; rm -rf "$WT"
git -C "$REPO" worktree add --detach "$WT" "$BRANCH" >/dev/null 2>&1 || { echo "ABLATE-SETUP-FAIL"; exit 99; }
ln -s "$DONOR/node_modules" "$WT/node_modules"
cp "$DONOR/my.test.env" "$WT/my.test.env" 2>/dev/null
restored=(); deleted=()
while read -r f; do
  [ -z "$f" ] && continue
  case "$f" in tests/*) continue;; esac
  if git -C "$WT" cat-file -e "$BASE:$f" 2>/dev/null; then
    git -C "$WT" checkout "$BASE" -- "$f" || { echo "ABLATE-SETUP-FAIL restore $f"; exit 98; }
    restored+=("$f")
  else
    rm -f "$WT/$f"; deleted+=("$f")
  fi
done < <(git -C "$WT" diff --name-only "$BASE"..HEAD)
echo "ABLATION SCOPE: restored[${#restored[@]}]=${restored[*]:-none}"
echo "                deleted[${#deleted[@]}]=${deleted[*]:-none}"
# PROVE the ablation actually changed the tree.
if [ "$(git -C "$WT" status --porcelain | wc -l)" -eq 0 ]; then
  echo "ABLATE-SETUP-FAIL: working tree unchanged; the ablation broke NOTHING"; exit 97
fi
for T in "$@"; do
  OUT=$(cd "$WT" && timeout 300 ./node_modules/.bin/env-cmd -f ./my.test.env ./node_modules/.bin/mocha --timeout 5000 --require ./tests/hooks.js --exit "./tests/$T.test.js" 2>&1)
  RC=$?
  echo "ABLATION $BRANCH/$T -> exit $RC  [$(echo "$OUT" | grep -E '^\s+[0-9]+ (passing|failing)' | tr -s ' \n' ' ')]"
done
git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1; rm -rf "$WT"
