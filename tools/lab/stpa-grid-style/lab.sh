#!/usr/bin/env bash
# Render every candidate for every input, measure, report, and draw the contact sheets.
#   ./lab.sh            everything
#   ./lab.sh render     render only
# Node packages come from .tools/node (README has the install commands); Graphviz and Chrome from PATH.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
CHROME="${CHROME:-$(command -v google-chrome)}"
export NODE_PATH="$HERE/.tools/node/node_modules"
cd "$HERE"
"$PY" lab.py
"$PY" gridstpa.py -o results/demo inputs-demo/*.yaml
[ "${1:-}" = render ] && exit 0
node measure.js results/build "$CHROME" > results/metrics.json
"$PY" report.py results/metrics.json > results/metrics.md
node sheet.js results/build "$CHROME" results/sheets
node sheet.js results/build "$CHROME" results/sheets dot-spline grid
head -30 results/metrics.md
