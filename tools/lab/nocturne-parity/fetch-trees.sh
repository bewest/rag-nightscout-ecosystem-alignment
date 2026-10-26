#!/usr/bin/env bash
# fetch-trees.sh — clone both servers at the commits in PINS (git trees: run.sh checks HEAD and cleanliness).
#
# Usage: tools/lab/nocturne-parity/fetch-trees.sh <dir>
#   writes <dir>/crm-<sha8> (with node_modules from its own `npm ci`) and <dir>/nocturne-<sha9>
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/PINS"
DIR=$(mkdir -p "$1" && cd "$1" && pwd)
NODE=${NODE:-node}; NPM=${NPM:-npm}

fetch () { # repo ref commit dest
  if [ ! -d "$4/.git" ]; then git clone -q --filter=blob:none "https://github.com/nightscout/$1.git" "$4"; fi
  git -C "$4" fetch -q origin "$2"
  git -C "$4" checkout -q --detach "$3"
}
CRM="$DIR/crm-${CRM_COMMIT:0:8}"; NOC="$DIR/nocturne-${NOC_COMMIT:0:9}"
fetch cgm-remote-monitor "$CRM_REF" "$CRM_COMMIT" "$CRM"
fetch nocturne "$NOC_REF" "$NOC_COMMIT" "$NOC"
[ -d "$CRM/node_modules" ] || (cd "$CRM" && $NPM ci)
echo "$CRM $NOC"
