#!/usr/bin/env bash
#
# ablate.sh — the standing NEGATIVE CONTROL for a gate that runs a branch's own
# test files.
#
# It builds a THROWAWAY worktree of <branch>, puts the shipping code back to
# <base> while KEEPING the branch's tests, runs the named test files and exits
# with mocha's status. A gate whose control exits 0 here is a gate that passes
# on code that does not contain the fix — which is the whole failure this
# instrument exists to find.
#
#   ablate.sh <repo-dir> <branch> <base-rev> <donor-worktree> <test-name>...
#
# RULE 6: it only ever touches a worktree it created itself, under $TMPDIR, and
# removes it again. It never writes into <donor-worktree> — that is another
# session's working state, and it is read for `node_modules` and `my.test.env`
# only.
#
# THIS SCRIPT WAS ITSELF VACUOUS ONCE, AND THE BUG IS WORTH KEEPING IN MIND.
# The first version reverted with `git checkout <base> -- <files>`. When a
# branch ADDS a file, that path does not exist at <base>, git aborts the WHOLE
# checkout, and nothing at all is reverted — so the ablation reported a
# comfortable green having broken nothing. Files added by the branch are now
# deleted instead of restored, and the script refuses to continue if the
# working tree came out unchanged.
set -u

if [ "$#" -lt 5 ]; then
  echo "CONTROL-INVALID: usage: ablate.sh <repo-dir> <branch> <base-rev> <donor-worktree> <test>..." >&2
  exit 90
fi

REPO="$1"; BRANCH="$2"; BASE="$3"; DONOR="$4"; shift 4

# --files=a,b restricts the ablation to those paths. Use it when reverting
# everything only proves that a deleted module cannot be require()d: a
# MODULE_NOT_FOUND is a non-zero exit for the wrong reason, and a control that
# passes for the wrong reason is only half a control.
ONLY=""
case "${1:-}" in
  --files=*) ONLY="${1#--files=}"; shift;;
esac

fail_setup () { echo "CONTROL-INVALID: $*" >&2; exit 90; }

[ -d "$REPO" ]  || fail_setup "repo $REPO does not exist"
[ -d "$DONOR" ] || fail_setup "donor worktree $DONOR does not exist"
# Absolute, because the throwaway worktree lives under $TMPDIR and a relative
# node_modules symlink would dangle there.
REPO="$(cd "$REPO" && pwd)"
DONOR="$(cd "$DONOR" && pwd)"
[ -d "$DONOR/node_modules" ] || fail_setup "donor worktree $DONOR has no node_modules"

WT="$(mktemp -d "${TMPDIR:-/tmp}/queue-ablate-XXXXXX")"
cleanup () {
  git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1
  rm -rf "$WT"
  git -C "$REPO" worktree prune >/dev/null 2>&1
}
trap cleanup EXIT
rmdir "$WT"

git -C "$REPO" worktree add --detach "$WT" "$BRANCH" >/dev/null 2>&1 \
  || fail_setup "could not create a throwaway worktree of $BRANCH"

ln -s "$DONOR/node_modules" "$WT/node_modules"
[ -f "$DONOR/my.test.env" ] && cp "$DONOR/my.test.env" "$WT/my.test.env"

restored=0; deleted=0
while read -r file; do
  [ -z "$file" ] && continue
  case "$file" in test/*|tests/*) continue;; esac
  if [ -n "$ONLY" ]; then
    case ",$ONLY," in *",$file,"*) :;; *) continue;; esac
  fi
  if git -C "$WT" cat-file -e "$BASE:$file" 2>/dev/null; then
    git -C "$WT" checkout "$BASE" -- "$file" || fail_setup "could not restore $file to $BASE"
    restored=$((restored + 1))
  else
    rm -f "$WT/$file"; deleted=$((deleted + 1))
  fi
done < <(git -C "$WT" diff --name-only "$BASE".."$BRANCH")

echo "ablation: $BRANCH -> $BASE  ($restored file(s) restored, $deleted added file(s) removed)"
[ "$((restored + deleted))" -gt 0 ] || fail_setup "nothing was ablated${ONLY:+ (--files=$ONLY matched no changed path)}; the control would prove nothing"
[ "$(git -C "$WT" status --porcelain | wc -l)" -gt 0 ] \
  || fail_setup "the working tree is unchanged; the ablation broke NOTHING"

status=0
for test in "$@"; do
  if [ ! -f "$WT/tests/$test.test.js" ] && [ ! -f "$WT/test/$test.test.js" ]; then
    fail_setup "no test file for '$test' in the ablated worktree"
  fi
  # Capture first, print after. `( ... | tail )` would hand back tail's exit
  # status, which is always 0 — and a control that always reports 0 is exactly
  # the bug this whole instrument exists to find.
  if [ -f "$WT/my.test.env" ]; then
    out="$( cd "$WT" && ./node_modules/.bin/env-cmd -f ./my.test.env \
        ./node_modules/.bin/mocha --timeout 5000 --require ./tests/hooks.js --exit \
        "./tests/$test.test.js" 2>&1 )"
    rc=$?
  else
    out="$( cd "$WT" && node --test "test/$test.test.js" 2>&1 )"
    rc=$?
  fi
  echo "$out" | tail -12
  echo "ablated $BRANCH/$test -> exit $rc"
  [ "$rc" -ne 0 ] && status="$rc"
done
exit "$status"
