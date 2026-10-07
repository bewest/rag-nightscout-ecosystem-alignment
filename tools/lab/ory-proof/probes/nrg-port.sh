#!/usr/bin/env bash
# probes/nrg-port.sh - prepare a RUNNABLE COPY of nightscout-roles-gateway (never the externals
# checkout itself) and run probes/nrg-port.js against this lab's Kratos 1.x / Hydra 2.x.
#   NRG_SRC defaults to the alignment repo's externals/nightscout-roles-gateway.
# The copy lives in nrg-run/ (gitignored). NRG runs in node:22 because restify 11.1.0 pulls
# spdy -> http-deceiver, which calls process.binding('http_parser') - gone in Node 24.
set -euo pipefail
cd "$(dirname "$0")/.."
# externals/ is gitignored, so from a worktree look in the main checkout (the common git dir's parent)
NRG_SRC="${NRG_SRC:-$(cd "$(git rev-parse --git-common-dir)/.." && pwd)/externals/nightscout-roles-gateway}"
NODE_IMAGE="node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392"
rm -rf nrg-run && mkdir nrg-run
git -C "$NRG_SRC" archive HEAD | tar -x -C nrg-run
git -C "$NRG_SRC" rev-parse --short HEAD > nrg-run/.nrg-commit
# npm 11 refuses the lockfile's peer graph (knex-utils@5.5.0 wants knex ^0.95.4, NRG pins knex ^2.0.0)
(cd nrg-run && npm ci --no-audit --no-fund --legacy-peer-deps >/dev/null 2>&1) || { echo "npm ci failed"; exit 2; }
source .secrets.env
umask 077
printf 'KNEX_CONNECT=postgres://lab:%s@127.0.0.1:54353/nrg\nBACKEND_ENV=production\n' "$PG_PASSWORD" > nrg-run/.lab.env
# a fresh database each run, so the migration count below is measured, not inherited
docker compose --env-file .secrets.env exec -T postgres psql -q -U lab -d lab -c 'DROP DATABASE IF EXISTS nrg' -c 'CREATE DATABASE nrg'
docker run --rm --network host --env-file nrg-run/.lab.env -v "$PWD/nrg-run:/app" -w /app "$NODE_IMAGE" \
  ./node_modules/.bin/knex migrate:latest --env production 2>&1 | tail -1
NODE_IMAGE="$NODE_IMAGE" node probes/nrg-port.js
