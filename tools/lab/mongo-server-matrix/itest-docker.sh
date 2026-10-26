#!/bin/bash
# MongoDB server matrix, integration cell: run one tree's integration tier against
# one MongoDB container, inside node:22, sharing that container's network namespace
# (mongod at 127.0.0.1:27017 and port 1337 private to the cell), so several cells
# can run at once without sharing a port or a database.
#
#   tools/lab/mongo-server-matrix/itest-docker.sh <tree> <label> <mongo-container> [test files...]
#
# MM_GITDIR: the clone's .git directory, mounted read-only (the tier runner reads
#   git for test:affected; default externals/cgm-remote-monitor-official/.git).
# MM_NODE: a host node binary mounted as /usr/local/bin/node (default: the image's).
# The env file is the tree's own tests/ci.test.env with only the connection string
# changed. Output: $MM_OUT/itest-<label>.log, ending in "EXIT <status>".
set -u
T=$1; L=$2; C=$3; shift 3
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../.." && pwd)
OUT=${MM_OUT:-${TMPDIR:-/tmp}/mongo-server-matrix}; mkdir -p "$OUT"
G=${MM_GITDIR:-$ROOT/externals/cgm-remote-monitor-official/.git}
E=$OUT/env-$L.env
sed -e "s#^CUSTOMCONNSTR_mongo=.*#CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:27017/testdb#" "$T/tests/ci.test.env" > "$E"
echo "# $L $(date -u +%FT%TZ) container $C files: $*" > "$OUT/itest-$L.log"
NODE_MOUNT=(); [ -n "${MM_NODE:-}" ] && NODE_MOUNT=(-v "$MM_NODE:/usr/local/bin/node:ro")
docker run --rm --name "mmrun-$L" --network "container:$C" -u "$(id -u):$(id -g)" -e HOME=/tmp -e TEST_ENV_FILE="$E" \
  -v "$T:$T" -v "$G:$G:ro" -v "$OUT:$OUT" "${NODE_MOUNT[@]}" -w "$T" node:22 \
  timeout 2400 node scripts/test-tiers.js run integration "$@" >> "$OUT/itest-$L.log" 2>&1
echo "EXIT $?" >> "$OUT/itest-$L.log"
