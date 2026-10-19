#!/usr/bin/env bash
# Run a command while holding this checkout's site build lock (build/.site.lock), so two
# sessions never build into the same build/ at once. A second caller waits up to
# SITE_LOCK_WAIT seconds (default 900), then fails with exit 75. A caller that already holds
# the lock (publish.sh) sets SITE_LOCK_HELD=1 and its children run without taking it again.
set -euo pipefail
if [ -n "${SITE_LOCK_HELD:-}" ]; then exec "$@"; fi
mkdir -p build
exec 9>build/.site.lock
if ! flock -w "${SITE_LOCK_WAIT:-900}" 9; then
  echo "site: another site build or publish in this checkout holds build/.site.lock (waited ${SITE_LOCK_WAIT:-900}s); run again when it finishes" >&2
  exit 75
fi
export SITE_LOCK_HELD=1
"$@"
