#!/usr/bin/env bash
# fetch-trees.sh — download both hubs at the commits this lab was run at, as GitHub archives.
#
# Usage: tools/lab/hub-active-state/fetch-trees.sh <dir>
#   writes <dir>/crm-fade2299 and <dir>/nocturne-42275c812
#   CRM_NODE_MODULES=<path>  symlink that node_modules into the cgm-remote-monitor tree
#                            (it must come from the same package-lock.json); otherwise npm ci runs
# Override the commits with CRM_COMMIT / NOC_COMMIT.
set -euo pipefail
DIR=$(mkdir -p "$1" && cd "$1" && pwd)
CRM_COMMIT=${CRM_COMMIT:-fade229909e6f3a0b5459230bc7273fe85de4f32}
NOC_COMMIT=${NOC_COMMIT:-42275c812d9b942251a3309fea8066871940cfc2}

fetch () { # repo commit dest
  local tmp; tmp=$(mktemp -d)
  curl -sSfL "https://codeload.github.com/nightscout/$1/tar.gz/$2" | tar -xz -C "$tmp"
  rm -rf "$3"; mv "$tmp/$1-$2" "$3"; rmdir "$tmp"
}
fetch cgm-remote-monitor "$CRM_COMMIT" "$DIR/crm-${CRM_COMMIT:0:8}"
fetch nocturne "$NOC_COMMIT" "$DIR/nocturne-${NOC_COMMIT:0:9}"

if [ -n "${CRM_NODE_MODULES:-}" ]; then
  ln -s "$CRM_NODE_MODULES" "$DIR/crm-${CRM_COMMIT:0:8}/node_modules"
else
  (cd "$DIR/crm-${CRM_COMMIT:0:8}" && npm ci --ignore-scripts)
fi
echo "$DIR/crm-${CRM_COMMIT:0:8} $DIR/nocturne-${NOC_COMMIT:0:9}"
