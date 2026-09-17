#!/usr/bin/env bash
# run.sh — bring up every review state, seed them identically, run every probe,
# and print one verdict table.
#
# Idempotent. Re-running resets each state's database and re-seeds, because
# seeding under a live server leaves the in-memory cache populated and poisons
# every read-path measurement (see nsctl.sh cmd_reset).
#
# Usage:  tools/review/run.sh [state ...]     (default: all known states)

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${NSREVIEW_ROOT:?set NSREVIEW_ROOT}"
NSCTL="$HERE/nsctl.sh"
RUN="$NSREVIEW_ROOT/run"

# state:committish — BASE first, it is every probe's control.
STATES=(
  "BASE:a8888f0d"
  "PAIR:rc/2026-09-dev-cycle"
  "COERCION:bf/coercion"
  "READS:bf/reads"
  "FOOD:bf/food"
  "P8741:pr8741"
)

secret() { "$NSCTL" secret; }
port()   { cat "$RUN/$1.port"; }

echo "== bringing up states =="
for sc in "${STATES[@]}"; do
  s="${sc%%:*}"; ref="${sc##*:}"
  "$NSCTL" add "$s" "$ref" >/dev/null 2>&1
  "$NSCTL" reset "$s" production >/dev/null 2>&1 \
    && printf '  %-10s up   ' "$s" || { printf '  %-10s FAILED TO START\n' "$s"; continue; }
  node "$HERE/seed.js" --url "http://127.0.0.1:$(port "$s")" --secret "$(secret)" \
    --mongo-db "nsreview_$s" --out "$RUN/$s.manifest.json" >/dev/null 2>&1 \
    && echo "seeded" || echo "SEED FAILED"
done

BASE_URL="http://127.0.0.1:$(port BASE)"
SEC="$(secret)"
declare -a ROWS

probe() {  # probe <label> <unit> <command...>
  local label="$1" unit="$2"; shift 2
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  local line; line="$(printf '%s' "$out" | tail -1)"
  ROWS+=("$(printf '%-26s|%-18s|%-6s|%s' "$label" "$unit" \
    "$([ $rc -eq 0 ] && echo PASS || echo FAIL)" "$line")")
  printf '%s\n' "$out" > "$RUN/probe-$label.log"
}

echo
echo "== probes =="
probe "pair"        "#8737+#8738" node "$HERE/probes/pair-reads-coercion.js" \
  --base "$BASE_URL" --candidate "http://127.0.0.1:$(port PAIR)" --secret "$SEC" \
  --manifest "$RUN/PAIR.manifest.json"
probe "pair-half-reads"    "#8738 alone" node "$HERE/probes/pair-reads-coercion.js" \
  --base "$BASE_URL" --candidate "http://127.0.0.1:$(port READS)" --secret "$SEC" \
  --manifest "$RUN/READS.manifest.json"
probe "pair-half-coercion" "#8737 alone" node "$HERE/probes/pair-reads-coercion.js" \
  --base "$BASE_URL" --candidate "http://127.0.0.1:$(port COERCION)" --secret "$SEC" \
  --manifest "$RUN/COERCION.manifest.json"
probe "food"        "#8735" node "$HERE/probes/food.js" \
  --base "$BASE_URL" --candidate "http://127.0.0.1:$(port FOOD)" --secret "$SEC" \
  --manifest "$RUN/FOOD.manifest.json"
probe "credentials" "#8741" node "$HERE/probes/credentials.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" \
  --candidate-worktree "$NSREVIEW_ROOT/states/P8741"

# Every probe must also be RED when its candidate is BASE. A probe that passes
# both ways measured nothing, and this loop is the only thing that notices.
echo
echo "== red controls (candidate = BASE; every one MUST fail) =="
rc_bad=0
red_control() {  # red_control <label> <command...>
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  $label: *** PASSED AGAINST BASE — probe is vacuous, its PASS is not evidence ***"
    rc_bad=1
  else
    echo "  $label: correctly red"
  fi
}
red_control pair node "$HERE/probes/pair-reads-coercion.js" \
  --base "$BASE_URL" --candidate "$BASE_URL" --secret "$SEC"
red_control food node "$HERE/probes/food.js" \
  --base "$BASE_URL" --candidate "$BASE_URL" --secret "$SEC"
red_control credentials node "$HERE/probes/credentials.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" \
  --candidate-worktree "$NSREVIEW_ROOT/states/BASE"

echo
printf '%-26s %-18s %-6s %s\n' PROBE UNIT VERDICT SUMMARY
printf '%s\n' "$(printf '%.0s-' {1..108})"
for r in "${ROWS[@]}"; do IFS='|' read -r a b c d <<<"$r"; printf '%-26s %-18s %-6s %s\n' "$a" "$b" "$c" "$d"; done
echo
echo "logs: $RUN/probe-*.log"
[ $rc_bad -eq 0 ] || echo "WARNING: at least one probe is vacuous — its PASS above is not evidence."
