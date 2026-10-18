#!/usr/bin/env bash
#
# nsschema-weakened.sh <module.py> <old> <new> <test-file> — the NEGATIVE
# CONTROL for a tools/nsschema pytest gate. It copies tools/nsschema and
# specs/sync into a scratch root, replaces <old> with <new> once in
# tools/nsschema/<module.py> there (a rule the suite must notice), and runs
# the suite against the copy. It exits with pytest's status, which must be
# non-zero. Exits 90 CONTROL-INVALID when <old> is not found exactly once, so
# a control that no longer matches its code cannot pass for the wrong reason.
# Never writes outside its scratch directory.
set -u
MODULE="$1"; OLD="$2"; NEW="$3"; TEST="$4"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/nsschema-weakened-XXXXXX")"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/tools" "$T/specs"
cp -r "$ROOT/tools/nsschema" "$T/tools/" && cp -r "$ROOT/specs/sync" "$T/specs/"
# Cached bytecode is checked by modification time and size only, so a
# replacement of the same length made within the same second would run the
# unweakened code and pass for the wrong reason.
find "$T" -name __pycache__ -type d -prune -exec rm -rf {} +
export PYTHONDONTWRITEBYTECODE=1
python3 - "$T/tools/nsschema/$MODULE" "$OLD" "$NEW" <<'PY' || exit 90
import sys
path, old, new = sys.argv[1:]
text = open(path).read()
if text.count(old) != 1:
    print("CONTROL-INVALID: %r occurs %d times in %s" % (old, text.count(old), path))
    sys.exit(1)
open(path, "w").write(text.replace(old, new))
PY
cd "$T" && python3 -m pytest -q -p no:cacheprovider "tools/nsschema/$TEST" 2>&1 | tail -2
exit "${PIPESTATUS[0]}"
