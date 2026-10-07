#!/bin/bash
# Break-it controls for tools/qc/write-contract-matrix.js (queue WRITE-CONTRACT).
#
#   WC_ABLATE_WORKTREE=<detached crm worktree, node_modules present> \
#   WC_MONGO=mongodb://127.0.0.1:27151 tools/qc/write-contract-ablate.sh [NAME ...]
#
# For each ablation: run the matrix cells it names on the clean worktree (the
# positive control), remove one write rule from one place, run the same cells
# (the break), restore the file and run them again (the revert). The break must
# change exactly the cells listed under "expect", for the reason given; the
# revert must match the clean run. An ablation whose substitution changes no
# file stops with ABLATION-NO-OP instead of reporting a green break.
#
# Exit 0 when every break changed exactly its expected cells and every revert
# matched; 1 otherwise; 2 when the worktree is dirty before a run.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
H=$HERE/write-contract-matrix.js
W=${WC_ABLATE_WORKTREE:?set WC_ABLATE_WORKTREE to a detached cgm-remote-monitor worktree}
OUT=${WC_ABLATE_OUT:-${TMPDIR:-/tmp}/wc-ablate}
NODE=${WC_NODE:-22.23.2}
mkdir -p "$OUT"

# name | file | sed substitution | matrix arguments | expected changed cells (space separated, _ for spaces inside a cell key)
ABLATIONS=(
  "oid|lib/server/websocket.js|s/if (!idForms.isHexId(document._id)) return;/return;/|--paths ws --only treatments,food --forms resend-hex,resend-upper|treatments_ws_resend-hex treatments_ws_resend-upper food_ws_resend-hex food_ws_resend-upper"
  "srv|lib/server/websocket.js|s/if (servedByV3(data.collection)) srvDates.stampCreated(data.data);/;/|--paths ws --only food,entries --forms create|food_ws_create entries_ws_create"
  "soft|lib/server/treatments.js|s/return softDeleted.visible(stored_query_for(opts), opts);/return stored_query_for(opts);/|--only treatments --forms softdelete|treatments_v1_softdelete treatments_v3_softdelete treatments_ws_softdelete treatments_inproc_softdelete"
  "key|lib/server/treatments.js|s/return fallbackKey.fallbackQuery(obj, results.created_at, { withAmounts: true });/return Object.assign(fallbackKey.fallbackQuery(obj, results.created_at, { withAmounts: true }), { wcNever: { \$eq: true } });/|--only treatments --forms resend-identity|treatments_v1_resend-identity treatments_inproc_resend-identity"
  "derive|lib/api3/storage/mongoCachedCollection/index.js|s/const DERIVE_FOR_CACHE = { treatments: true, devicestatus: true };/const DERIVE_FOR_CACHE = {};/|--paths v3 --only treatments,devicestatus --forms create,update|treatments_v3_create treatments_v3_update devicestatus_v3_create devicestatus_v3_update"
  "wire|lib/api3/generic/create/insert.js|s/ctx.bus.emit('storage-socket-create', { colName: col.colName, doc });/;/|--paths v1,v3 --only treatments --forms create|treatments_v3_create"
)

run () { # tag name args...
  local tag=$1 name=$2; shift 2
  WC_WORKTREE=$W n exec "$NODE" node "$H" --no-cross "$@" --out "$OUT/$name-$tag.json" > "$OUT/$name-$tag.log" 2>&1
}

status=0
for a in "${ABLATIONS[@]}"; do
  IFS='|' read -r name file expr args expect <<< "$a"
  if [ $# -gt 0 ] && ! printf '%s\n' "$@" | grep -qx "$name"; then continue; fi
  git -C "$W" diff --quiet -- lib || { echo "$name: worktree dirty before the run"; exit 2; }
  # shellcheck disable=SC2086
  run clean "$name" $args
  sed -i "$expr" "$W/$file"
  if git -C "$W" diff --quiet -- lib; then echo "$name: ABLATION-NO-OP (the substitution changed nothing in $file)"; status=1; continue; fi
  echo "== $name: $(git -C "$W" diff -U0 -- lib | grep '^[-+][^-+]' | tr '\n' ' ')"
  # shellcheck disable=SC2086
  run broken "$name" $args
  git -C "$W" checkout -- lib
  # shellcheck disable=SC2086
  run revert "$name" $args
  changed=$(node "$H" --compare "$OUT/$name-clean.json" "$OUT/$name-broken.json" | grep -v '^  [AB] \|^differing' | sort | tr ' ' '_' | tr '\n' ' ')
  want=$(printf '%s\n' $expect | sort | tr '\n' ' ')
  node "$H" --compare "$OUT/$name-clean.json" "$OUT/$name-broken.json" | grep '^  [AB] \|^[a-z]' | sed 's/^/   /'
  if [ "$changed" = "$want" ]; then echo "   break: changed exactly the expected cells"; else echo "   break: MISMATCH, changed [$changed] expected [$want]"; status=1; fi
  if node "$H" --compare "$OUT/$name-clean.json" "$OUT/$name-revert.json" > /dev/null; then echo "   revert: matches the clean run"; else echo "   revert: DIFFERS from the clean run"; status=1; fi
done
exit $status
