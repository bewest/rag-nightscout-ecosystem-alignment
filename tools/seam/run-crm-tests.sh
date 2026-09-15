#!/bin/bash
# The modernization branch refuses Node < 24.20.0 and this host has 24.15.0, so the
# suite runs in node:24-bookworm (24.21.0). --network host is required, not
# convenience: tests/fixtures/http-assets/worker.js asserts the database is on
# loopback, so a bridged container IP fails three tests for the wrong reason.
cd /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-seam
docker run --rm --network host -v "$PWD":/app -w /app node:24-bookworm \
  npx env-cmd -f ./my.test.env npx mocha --timeout 15000 --require ./tests/hooks.js --exit --reporter min "$@"
