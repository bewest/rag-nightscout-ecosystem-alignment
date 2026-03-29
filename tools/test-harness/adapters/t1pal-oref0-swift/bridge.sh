#!/usr/bin/env bash
# T1Pal Swift Adapter Bridge
#
# Multi-algorithm adapter backed by T1PalAlgorithm from t1pal-mobile-apex.
# Supports: oref0, Loop, Loop-Tidepool, GlucOS, SimpleProportional
#
# Prerequisites:
#   cd tools/t1pal-adapter-cli && swift build

set -euo pipefail

ADAPTER_DIR="$(cd "$(dirname "$0")" && pwd)"
CLI="${ADAPTER_DIR}/../../../t1pal-adapter-cli/.build/debug/T1PalAdapterCLI"

if [ ! -f "$CLI" ]; then
  cat <<EOF
{
  "error": "T1PalAdapterCLI not found. Build with: cd tools/t1pal-adapter-cli && swift build",
  "name": "t1pal-swift",
  "status": "not-built"
}
EOF
  exit 1
fi

exec "$CLI"
