#!/usr/bin/env bash
# probes/nrg-suite.sh - NRG's own mocha suite with its Kratos/Hydra tests skipped (it needs only
# Postgres), run twice in node:22: as shipped, and without site_registration.test.js, whose
# `after` hook rolls the schema back under every later test file. Needs nrg-run/ from
# probes/nrg-port.sh. Writes results/$RUN/nrg-suite.txt (counts and failing titles only).
set -uo pipefail
cd "$(dirname "$0")/.."
RUN="${RUN:-$(date +%F)}"; mkdir -p "results/$RUN" results/raw
NODE_IMAGE="node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392"
source .secrets.env
DB="postgres://lab:${PG_PASSWORD}@127.0.0.1:54353/nrg"
suite() {
  local label="$1"; shift
  docker compose --env-file .secrets.env exec -T postgres psql -q -U lab -d lab -c 'DROP DATABASE IF EXISTS nrg' -c 'CREATE DATABASE nrg'
  docker run --rm --network host -e DATABASE_URL="$DB" -e SKIP_HYDRA_TESTS=1 -e SKIP_KRATOS_TESTS=1 \
    -v "$PWD/nrg-run:/app" -w /app "$NODE_IMAGE" ./node_modules/.bin/mocha --recursive test "$@" > "results/raw/nrg-suite-$label.log" 2>&1
  echo "## $label ($*)"
  grep -av '^{' "results/raw/nrg-suite-$label.log" | grep -aE '^\s+[0-9]+ (passing|failing|pending)'
  echo "first failure messages (deduplicated):"
  grep -av '^{' "results/raw/nrg-suite-$label.log" | grep -aoE 'relation "[a-z_]+" does not exist|AssertionError: [^\n]{0,60}' | sort | uniq -c | sort -rn | head -5 || true
}
{ echo "NRG $(cat nrg-run/.nrg-commit) suite, SKIP_HYDRA_TESTS=1 SKIP_KRATOS_TESTS=1, node:22"
  suite as-shipped
  suite without-site-registration --ignore test/integration/site_registration.test.js
} | tee "results/$RUN/nrg-suite.txt"
