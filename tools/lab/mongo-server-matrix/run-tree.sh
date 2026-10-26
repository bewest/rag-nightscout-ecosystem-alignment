#!/bin/bash
# Run itest-docker.sh for one tree against each server container mm-mongo-<suffix>.
#   tools/lab/mongo-server-matrix/run-tree.sh <tree> <label-prefix> 36 40 42 44 50 60 70 80
T=$1; P=$2; shift 2; HERE=$(cd "$(dirname "$0")" && pwd)
for v in "$@"; do "$HERE/itest-docker.sh" "$T" "$P-$v" "mm-mongo-$v"; done
