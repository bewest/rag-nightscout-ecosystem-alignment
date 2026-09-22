#!/usr/bin/env bash
#
# bf17-rename-row-control.sh — the SHARP negative control for
# tools/queue/gates/bf17-remediation-note.js.
#
# The weak form (empty-root-control.sh) would only show that gate reads files.
# This one restores THE ACTUAL DEFECT and checks the gate refuses to pass: it
# copies the four documents the gate reads into a throwaway tree, puts the
# "Rename the user" row back into the 15.0.9 release-notes rotation table, and
# puts the PR body's retracted "discarded when Nightscout next loads it"
# sentence back. Those are the two mistakes that were really in these documents
# on 2026-09-16, restored verbatim rather than paraphrased.
#
# `externals/` is SYMLINKED, not copied — the gate also reads
# lib/authorization/storage.js out of the official checkout and the bf/auth
# worktree to pin the code property its prose depends on, and rule 5 forbids a
# control from touching either. Reading through a symlink writes nothing.
#
# IT EXITS WITH THE GATE'S OWN STATUS, per the control convention: a control IS
# the gate applied to a known-negative and must exit NON-ZERO. CONTROL-INVALID
# means the setup itself failed, which is not the same as the gate passing.
set -u

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
GATE="$ROOT/tools/queue/gates/bf17-remediation-note.js"
[ -f "$GATE" ] || { echo "CONTROL-INVALID: no such gate: $GATE"; exit 90; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/queue-bf17-control-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

ln -s "$ROOT/externals" "$WORK/externals" || {
  echo "CONTROL-INVALID: could not link externals/"; exit 90; }

NOTES="releases/cgm-remote-monitor-15.0.9/release-notes.md"
PRBODY="reports/phase0-pr-bodies/bf-auth.md"
for f in "$NOTES" "$PRBODY" \
         "docs/60-research/remedial/bf17-bf30-auth-defects-2026-09-15.md" \
         "docs/30-design/remedial/nightscout-backfix-register.md"; do
  [ -f "$ROOT/$f" ] || { echo "CONTROL-INVALID: missing input $f"; exit 90; }
  mkdir -p "$WORK/$(dirname "$f")"
  cp "$ROOT/$f" "$WORK/$f" || { echo "CONTROL-INVALID: copy failed: $f"; exit 90; }
done

python3 - "$WORK/$NOTES" "$WORK/$PRBODY" <<'PY' || { echo "CONTROL-INVALID: could not reintroduce the defect"; exit 90; }
import io, sys

notes_path, prbody_path = sys.argv[1], sys.argv[2]

notes = io.open(notes_path, encoding='utf-8').read()
anchor = "| **Delete the user and create a new one**"
row = ("| **Rename the user** (in the admin screen) | That one user's token "
       "changes. Everything using the old token stops working until you give it "
       "the new one. |\n")
if notes.count(anchor) != 1:
    sys.exit("anchor row not found in the release notes")
io.open(notes_path, 'w', encoding='utf-8').write(notes.replace(anchor, row + anchor))

pr = io.open(prbody_path, encoding='utf-8').read()
old = "previous edit left behind is dropped from the in-memory record on every load"
if pr.count(old) != 1:
    sys.exit("in-memory sentence not found in the PR body")
pr = pr.replace(old, "previous edit left behind is discarded when Nightscout next loads it")
pr = pr.replace("**The stored row itself is not rewritten by the upgrade.**", "")
io.open(prbody_path, 'w', encoding='utf-8').write(pr)
PY

out="$(QUEUE_GATE_ROOT="$WORK" node "$GATE" 2>&1)"
rc=$?
echo "$out" | grep -E '^  BAD |checked, ' || true
echo "gate exited $rc against a tree with the rename row and the 'discarded on load' sentence restored"
[ "$rc" -eq 0 ] && echo "the gate passed with the defect present"
exit "$rc"
