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
  "ALARMS:bf/alarms"
  "PARMS:bf/parms"
  "MERGE:bf/merge"
  "CACHE:bf/cache"
  "QUAD:fix/quadratic-treatment-processing"
  "PERFBASE:a8888f0d"
  "RC:rc/2026-09-dev-cycle"
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
probe "alarms" "#8739" node "$HERE/probes/alarms.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" \
  --candidate-worktree "$NSREVIEW_ROOT/states/ALARMS"
probe "merge" "#8734" node "$HERE/probes/merge.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" \
  --candidate-worktree "$NSREVIEW_ROOT/states/MERGE"
probe "quadratics" "#8733" node "$HERE/probes/quadratics-shape.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" \
  --candidate-worktree "$NSREVIEW_ROOT/states/QUAD"
# cache-shape RESEEDS AND RESTARTS both states it is given, in production mode.
# It therefore runs against PERFBASE, never BASE: pointing it at the shared
# control silently strips BASE of its adversarial fixtures and drops it out of
# development mode, and the next run then fails for reasons unrelated to any
# branch. That is not hypothetical — it happened on 2026-09-17.
probe "cache" "#8740" node "$HERE/probes/cache-shape.js" \
  --base-state PERFBASE --candidate-state CACHE --secret "$SEC"

# The integration branch carries every qualified unit. Running the SAME probes
# against it is what catches a later merge breaking an earlier fix - the whole
# point of evaluating between each merge rather than bisecting at the end.
echo
echo "== the integration branch (rc/2026-09-dev-cycle) =="
RC_URL="http://127.0.0.1:$(port RC)"
probe "rc:pair"        "RC" node "$HERE/probes/pair-reads-coercion.js" \
  --base "$BASE_URL" --candidate "$RC_URL" --secret "$SEC" --manifest "$RUN/RC.manifest.json"
probe "rc:food"        "RC" node "$HERE/probes/food.js" \
  --base "$BASE_URL" --candidate "$RC_URL" --secret "$SEC"
probe "rc:credentials" "RC" node "$HERE/probes/credentials.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" --candidate-worktree "$NSREVIEW_ROOT/states/RC"
probe "rc:alarms"      "RC" node "$HERE/probes/alarms.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" --candidate-worktree "$NSREVIEW_ROOT/states/RC"
probe "rc:merge"       "RC" node "$HERE/probes/merge.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" --candidate-worktree "$NSREVIEW_ROOT/states/RC"
probe "rc:quadratics"  "RC" node "$HERE/probes/quadratics-shape.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" --candidate-worktree "$NSREVIEW_ROOT/states/RC"

# Every probe must also be RED when its candidate is BASE. A probe that passes
# both ways measured nothing, and this loop is the only thing that notices.
# ---------------------------------------------------------------- client side
#
# Client probes require NODE_ENV=development. In production every state serves
# ONE shared bundle out of the common node_modules cache, so a branch's own
# instance serves dev's client code and a browser probe compares dev to dev.
# provenance.js is the BLOCKING pre-gate for exactly that, and it is run first.
echo
echo "== client-side (dev mode; bundles compile on first fetch) =="
export NSREVIEW_ENABLE='careportal basal iob cob bwp cage sage iage rawbg food boluscalc'
for s in BASE FOOD PARMS RC; do
  "$NSCTL" stop "$s" >/dev/null 2>&1
  "$NSCTL" start "$s" development >/dev/null 2>&1
  curl -s -o /dev/null -m 300 "http://127.0.0.1:$(port "$s")/devbundle/js/bundle.app.js" \
    && printf '  %-6s dev bundle ready\n' "$s"
done
BASE_DEV="http://127.0.0.1:$(port BASE)"
FOOD_DEV="http://127.0.0.1:$(port FOOD)"
PARMS_DEV="http://127.0.0.1:$(port PARMS)"
RC_DEV="http://127.0.0.1:$(port RC)"

if node "$HERE/probes/provenance.js" --base "$BASE_DEV" --candidate "$FOOD_DEV" \
     --unit bf/food >/dev/null 2>&1; then
  echo "  provenance: PASS — each instance serves its own client"
  probe "food-boluscalc" "#8735 BF-35" node "$HERE/probes/food-boluscalc-browser.js" \
    --base "$BASE_DEV" --candidate "$FOOD_DEV" --secret "$SEC"
  probe "parms" "#8736 BF-37" node "$HERE/probes/parms-browser.js" \
    --base "$BASE_DEV" --candidate "$PARMS_DEV" --secret "$SEC"
  probe "rc:boluscalc" "RC" node "$HERE/probes/food-boluscalc-browser.js" \
    --base "$BASE_DEV" --candidate "$RC_DEV" --secret "$SEC"
  probe "rc:parms" "RC" node "$HERE/probes/parms-browser.js" \
    --base "$BASE_DEV" --candidate "$RC_DEV" --secret "$SEC"
else
  echo "  provenance: FAIL — skipping browser probes, they would compare a build to itself"
  ROWS+=("$(printf '%-26s|%-18s|%-6s|%s' food-boluscalc '#8735 BF-35' SKIP 'provenance pre-gate failed')")
fi

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
red_control food-boluscalc node "$HERE/probes/food-boluscalc-browser.js" \
  --base "$BASE_DEV" --candidate "$BASE_DEV" --secret "$SEC"
red_control provenance node "$HERE/probes/provenance.js" \
  --base "$BASE_DEV" --candidate "$BASE_DEV" --unit bf/food
red_control alarms node "$HERE/probes/alarms.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" --candidate-worktree "$NSREVIEW_ROOT/states/BASE"
red_control merge node "$HERE/probes/merge.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" --candidate-worktree "$NSREVIEW_ROOT/states/BASE"
red_control parms node "$HERE/probes/parms-browser.js" \
  --base "$BASE_DEV" --candidate "$BASE_DEV" --secret "$SEC"
red_control quadratics node "$HERE/probes/quadratics-shape.js" \
  --base-worktree "$NSREVIEW_ROOT/states/BASE" --candidate-worktree "$NSREVIEW_ROOT/states/BASE"

echo
printf '%-26s %-18s %-6s %s\n' PROBE UNIT VERDICT SUMMARY
printf '%s\n' "$(printf '%.0s-' {1..108})"
for r in "${ROWS[@]}"; do IFS='|' read -r a b c d <<<"$r"; printf '%-26s %-18s %-6s %s\n' "$a" "$b" "$c" "$d"; done
echo
echo "logs: $RUN/probe-*.log"
[ $rc_bad -eq 0 ] || echo "WARNING: at least one probe is vacuous — its PASS above is not evidence."
