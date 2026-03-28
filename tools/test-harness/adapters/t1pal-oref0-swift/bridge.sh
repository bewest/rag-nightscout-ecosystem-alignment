#!/usr/bin/env bash
# T1Pal oref0 Swift Adapter Bridge
#
# This script wraps the T1PalAlgorithm Swift package as a JSON-over-stdio adapter.
# It reads JSON from stdin, passes it to the Swift CLI tool, and writes JSON to stdout.
#
# Prerequisites:
#   1. Build T1PalAdapterCLI: cd $T1PAL_WORKSPACE && swift build
#   2. Ensure the binary is in PATH or set T1PAL_CLI_PATH
#
# The Swift CLI tool must:
#   - Accept JSON on stdin matching adapter-input.schema.json
#   - Output JSON on stdout matching adapter-output.schema.json
#   - Support modes: execute, validate-input, describe

set -euo pipefail

T1PAL_WORKSPACE="${T1PAL_WORKSPACE:-$(dirname "$0")/../../../../t1pal-mobile-workspace}"
T1PAL_CLI="${T1PAL_CLI_PATH:-$T1PAL_WORKSPACE/.build/debug/T1PalAdapterCLI}"

if [ ! -f "$T1PAL_CLI" ]; then
  # Return describe-mode response indicating the adapter isn't built yet
  cat <<EOF
{
  "error": "T1PalAdapterCLI not found at $T1PAL_CLI. Build with: cd $T1PAL_WORKSPACE && swift build --product T1PalAdapterCLI",
  "name": "t1pal-oref0-swift",
  "algorithm": "oref0",
  "status": "not-built"
}
EOF
  exit 1
fi

# Pass stdin through to the Swift CLI
exec "$T1PAL_CLI"
