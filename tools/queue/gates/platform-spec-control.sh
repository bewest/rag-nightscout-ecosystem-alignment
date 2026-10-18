#!/usr/bin/env bash
#
# platform-spec-control.sh <layer> <break> — the NEGATIVE CONTROL for
# platform-spec.js. It copies the gate's inputs into a scratch root, breaks ONE
# property there, and runs the gate against that root (QUEUE_GATE_ROOT). It
# exits with the gate's own status, which must be non-zero, and prints the
# gate's BAD line so the reason can be checked, not just the exit code.
#
#   narration  append an amendment note to the spec
#   case       rename one cited case so it no longer exists
#   count      change the stated case count
#   pointer    remove the spec link from the first source document
#
# Never writes outside its scratch directory.
set -u
LAYER="${1:-}"; BREAK="${2:-}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SPEC="docs/30-design/platform/spec/$LAYER.md"
[ -f "$ROOT/$SPEC" ] || { echo "CONTROL-INVALID: no $SPEC"; exit 90; }

T="$(mktemp -d "${TMPDIR:-/tmp}/platform-spec-control-XXXXXX")"
trap 'rm -rf "$T"' EXIT
for p in docs/30-design/platform docs/30-design/tenancy docs/60-research/tenancy specs/sync/conformance; do
  mkdir -p "$T/$(dirname "$p")" && cp -r "$ROOT/$p" "$T/$p"
done

case "$BREAK" in
  narration) printf '\n*(Withdrawn 2026-10-18: control.)*\n' >> "$T/$SPEC" ;;
  case)      c=$(grep -m1 -oE '^\| `[a-z0-9-]+/[a-z0-9-]+`' "$T/$SPEC" | tr -d '|` ')
             mv "$T/specs/sync/conformance/$c.yaml" "$T/specs/sync/conformance/$c.moved" ;;
  count)     sed -i -E 's/^([0-9]+) cases/999 cases/' "$T/$SPEC" ;;
  pointer)   src=$(node "$ROOT/tools/queue/gates/platform-spec.js" "$LAYER" --sources | head -1)
             sed -i "s#spec/$LAYER\.md#spec/REMOVED.md#g" "$T/$src" ;;
  *)         echo "CONTROL-INVALID: break must be narration|case|count|pointer"; exit 90 ;;
esac

out="$(QUEUE_GATE_ROOT="$T" node "$ROOT/tools/queue/gates/platform-spec.js" "$LAYER" 2>&1)"; rc=$?
echo "$out" | grep -E '^  BAD|checked'
exit $rc
