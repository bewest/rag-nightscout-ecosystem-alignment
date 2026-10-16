#!/usr/bin/env bash
# Generate every variant for every input (base and mutated), render each to SVG, then measure.
#   ./lab.sh            render + measure into results/
#   ./lab.sh render     render only
# Tools come from .tools/ (see README for the install commands) and Graphviz on PATH.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
T="$HERE/.tools"
OUT="$HERE/results/build"
PY="${PYTHON:-python3}"
# A current Chrome: Mermaid 11.17 leaves every edge label unplaced in Chrome 131 (README, findings)
CHROME="${CHROME:-$(command -v google-chrome)}"

rm -rf "$OUT"
mkdir -p "$OUT"

render() {  # $1 = dir containing generated sources
  local d="$1" f t0 rc
  for f in "$d"/*; do
    local base="${f##*/}"
    local name="${base%.*}"
    local svg="$d/$name.svg" log="$d/$name.log"
    t0=$(date +%s%N)
    case "$base" in
      dot-*.dot)         dot -Tsvg "$f" -o "$svg" >"$log" 2>&1 ;;
      d2-dagre.d2|d2-grid.d2) "$T/bin/d2" --layout=dagre --pad 10 "$f" "$svg" >"$log" 2>&1 ;;
      d2-elk.d2)         "$T/bin/d2" --layout=elk --pad 10 "$f" "$svg" >"$log" 2>&1 ;;
      plantuml.puml)     java -Djava.awt.headless=true -jar "$T/plantuml/plantuml.jar" -tsvg -o "$d" "$f" >"$log" 2>&1 ;;
      *) continue ;;
    esac
    rc=$?
    echo "{\"variant\": \"$name\", \"rc\": $rc, \"ms\": $(( ($(date +%s%N) - t0) / 1000000 ))}" >> "$d/render.jsonl"
  done
  # Mermaid renders in the browser, as on the docs site (mermaid-render.js)
  NODE_PATH="$T/node/node_modules" node "$HERE/mermaid-render.js" "$CHROME" "$d"/mermaid-*.mmd > "$d/mermaid.log" 2>&1
}

for input in "$HERE"/inputs/*.yaml; do
  dia="$(basename "$input" .yaml)"
  for mode in base mutated; do
    d="$OUT/$dia/$mode"
    if [ "$mode" = mutated ]; then "$PY" "$HERE/gen.py" "$input" "$d" --mutate; else "$PY" "$HERE/gen.py" "$input" "$d"; fi
    render "$d"
  done
done

[ "${1:-}" = render ] && exit 0
NODE_PATH="$T/node/node_modules" node "$HERE/measure.js" "$OUT" "$CHROME" > "$HERE/results/metrics.json"
"$PY" "$HERE/report.py" "$HERE/results/metrics.json" > "$HERE/results/metrics.md"
cat "$HERE/results/metrics.md"
