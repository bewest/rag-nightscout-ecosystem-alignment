#!/usr/bin/env bash
# run.sh — boot both servers from the pinned commits, probe them, diff the documents, write results/.
#
# Usage:
#   tools/lab/nocturne-parity/run.sh <crm tree> <nocturne tree> [outdir]
#   tools/lab/nocturne-parity/run.sh --compare-only [outdir]
#       re-renders compare.md from the result files already in outdir; refuses if they were made
#       by another probe.js, ops.js or docdiff.js, or from other commits than PINS
#
#   <crm tree>       git checkout of cgm-remote-monitor at CRM_COMMIT (PINS), clean, with node_modules
#   <nocturne tree>  git checkout of Nocturne at NOC_COMMIT (PINS), clean; built here
#   [outdir]         default: results/ next to this script
# fetch-trees.sh makes both trees.
#
# Needs: docker, git, curl, openssl, sha256sum, the .NET 10 SDK, cargo (Nocturne's alert engine
# library is built from its crates/ tree), and Node.js 22 or later (NODE overrides the command,
# e.g. NODE="n exec 24 node"). Ports: CRM_PORT_DENIED, CRM_PORT_READABLE, NOC_PORT, MONGO_PORT,
# PG_PORT (defaults below; each is checked free). Containers npar-mongo-$$ and npar-pg-$$ are made
# here and removed on exit; servers are stopped by the PIDs this script recorded.
# Logs (they carry local paths) go to $LOGS, a temporary directory unless set.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
. "$HERE/PINS"
NODE=${NODE:-node}
sha () { sha256sum "$1" | cut -d' ' -f1; }
die () { echo "run.sh: $*" >&2; exit 3; }

if [ "${1:-}" = --compare-only ]; then
  OUT=${2:-$HERE/results}
  [ -f "$OUT/meta.json" ] || die "no $OUT/meta.json"
  for f in probe.js ops.js docdiff.js; do
    want=$(sha "$HERE/$f")
    got=$($NODE -e 'const m=require(process.argv[1]);console.log(m.sha256[process.argv[2]])' "$OUT/meta.json" "$f")
    [ "$want" = "$got" ] || die "stale results: $OUT was made by a different $f ($got, now $want); rerun run.sh"
  done
  for k in crm noc; do
    got=$($NODE -e 'console.log(require(process.argv[1])[process.argv[2]].commit)' "$OUT/meta.json" $k)
    want=$([ $k = crm ] && echo "$CRM_COMMIT" || echo "$NOC_COMMIT")
    [ "$want" = "$got" ] || die "stale results: $OUT is from $k $got, PINS says $want"
  done
  $NODE "$HERE/compare.js" "$OUT" > "$OUT/compare.md"
  $NODE "$HERE/compare.js" --selftest "$OUT"
  exit 0
fi

CRM=$(cd "$1" && pwd)
NOC=$(cd "$2" && pwd)
OUT=${3:-$HERE/results}
LOGS=${LOGS:-$(mktemp -d)}
mkdir -p "$OUT"

# ---------- inputs must be the pinned commits, clean ----------
for pair in "crm:$CRM:$CRM_COMMIT" "nocturne:$NOC:$NOC_COMMIT"; do
  IFS=: read -r name tree want <<< "$pair"
  got=$(git -C "$tree" rev-parse HEAD) || die "$name tree is not a git checkout"
  [ "$got" = "$want" ] || die "stale input: $name tree is at $got, PINS says $want"
  [ -z "$(git -C "$tree" status --porcelain --untracked-files=no)" ] || die "$name tree has local changes"
done
# the repo's copies of #8858's documents must be the ones in the crm tree
cmp -s "$REPO/specs/openapi/upstream/cgm-remote-monitor/api-v1.yaml" "$CRM/lib/server/swagger.yaml" || die "stale input: specs/openapi/upstream/cgm-remote-monitor/api-v1.yaml differs from the crm tree's lib/server/swagger.yaml"
cmp -s "$REPO/specs/openapi/upstream/cgm-remote-monitor/api-v3.yaml" "$CRM/lib/api3/swagger.yaml" || die "stale input: specs/openapi/upstream/cgm-remote-monitor/api-v3.yaml differs from the crm tree's lib/api3/swagger.yaml"
[ -d "$CRM/node_modules" ] || die "crm tree has no node_modules (npm ci in it)"

CRM_PORT_DENIED=${CRM_PORT_DENIED:-17461} CRM_PORT_READABLE=${CRM_PORT_READABLE:-17462}
NOC_PORT=${NOC_PORT:-17470} MONGO_PORT=${MONGO_PORT:-27460} PG_PORT=${PG_PORT:-25460}
for p in $CRM_PORT_DENIED $CRM_PORT_READABLE $NOC_PORT $MONGO_PORT $PG_PORT; do
  ss -ltnH "sport = :$p" | grep -q . && die "port $p is in use"
done

# ---------- cleanup: only what this run made ----------
PIDS=() CONTAINERS=()
cleanup () {
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  for c in "${CONTAINERS[@]}"; do docker rm -f "$c" > /dev/null 2>&1 || true; done
}
trap cleanup EXIT
running () { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = true ] || die "container $1 is not running"; }
wait_http () { # url want-status pid
  for _ in $(seq 1 120); do
    kill -0 "$3" 2>/dev/null || die "server pid $3 exited (see $LOGS)"
    [ "$(curl -s -o /dev/null -w '%{http_code}' "$1")" = "$2" ] && return 0
    sleep 2
  done
  die "$1 did not answer $2"
}
stop_pid () { kill "$1"; for _ in $(seq 1 30); do kill -0 "$1" 2>/dev/null || return 0; sleep 1; done; die "pid $1 did not stop"; }

# ---------- per-run secrets (never written to results) ----------
export NPAR_CRM_SECRET; NPAR_CRM_SECRET=$(openssl rand -hex 16)
export NPAR_PG_APP_PW NPAR_PG_MIG_PW NPAR_INSTANCE_KEY
NPAR_PG_APP_PW=$(openssl rand -hex 16); NPAR_PG_MIG_PW=$(openssl rand -hex 16); NPAR_INSTANCE_KEY=$(openssl rand -hex 32)
PG_SUPER_PW=$(openssl rand -hex 16); PG_WEB_PW=$(openssl rand -hex 16)
TOKFILE="$LOGS/noc-token"

# ---------- databases ----------
MONGO=npar-mongo-$$ PG=npar-pg-$$
docker run -d --name "$MONGO" --ulimit nofile=64000 -p "127.0.0.1:$MONGO_PORT:27017" mongo:7 > /dev/null; CONTAINERS+=("$MONGO")
docker run -d --name "$PG" -p "127.0.0.1:$PG_PORT:5432" -e POSTGRES_USER=npar_super -e POSTGRES_PASSWORD="$PG_SUPER_PW" -e POSTGRES_DB=nocturne \
  -e NOCTURNE_MIGRATOR_PASSWORD="$NPAR_PG_MIG_PW" -e NOCTURNE_APP_PASSWORD="$NPAR_PG_APP_PW" -e NOCTURNE_WEB_PASSWORD="$PG_WEB_PW" \
  -v "$NOC/docs/postgres/container-init/00-init.sh:/docker-entrypoint-initdb.d/00-init.sh:ro" postgres:17.6 -c max_connections=130 > /dev/null
CONTAINERS+=("$PG")

# ---------- Nocturne build (the alert engine library from source, as image builds do) ----------
(cd "$NOC/crates" && cargo build --release -p nocturne-alerts-ffi) > "$LOGS/cargo.log" 2>&1 || { tail -n 20 "$LOGS/cargo.log"; die "cargo build failed"; }
dotnet build "$NOC/src/API/Nocturne.API/Nocturne.API.csproj" -c Release -p:GenerateNSwagClient=false -p:NocturneAlertsFromSource=true \
  > "$LOGS/nocturne-build.log" 2>&1 || { tail -n 30 "$LOGS/nocturne-build.log"; die "Nocturne build failed"; }

# ---------- cgm-remote-monitor: two servers, AUTH_DEFAULT_ROLES denied and readable ----------
running "$MONGO"
NODE_CMD="$NODE" "$HERE/boot-crm.sh" "$CRM" "$CRM_PORT_DENIED" denied "mongodb://127.0.0.1:$MONGO_PORT/npar_denied" "$LOGS/crm-denied.log" "$LOGS/crm-denied.pid"
PIDS+=("$(cat "$LOGS/crm-denied.pid")")
NODE_CMD="$NODE" "$HERE/boot-crm.sh" "$CRM" "$CRM_PORT_READABLE" readable "mongodb://127.0.0.1:$MONGO_PORT/npar_readable" "$LOGS/crm-readable.log" "$LOGS/crm-readable.pid"
PIDS+=("$(cat "$LOGS/crm-readable.pid")")
wait_http "http://127.0.0.1:$CRM_PORT_DENIED/api/versions" 200 "$(cat "$LOGS/crm-denied.pid")"
wait_http "http://127.0.0.1:$CRM_PORT_READABLE/api/versions" 200 "$(cat "$LOGS/crm-readable.pid")"
running "$MONGO"
NPAR_SECRET="$NPAR_CRM_SECRET" $NODE "$HERE/probe.js" "http://127.0.0.1:$CRM_PORT_DENIED" crm-denied > "$OUT/probe-crm-denied.jsonl" 2> "$LOGS/probe-crm-denied.err" || { cat "$LOGS/probe-crm-denied.err"; die "crm denied probe failed"; }
running "$MONGO"
NPAR_SECRET="$NPAR_CRM_SECRET" $NODE "$HERE/probe.js" "http://127.0.0.1:$CRM_PORT_READABLE" crm-readable > "$OUT/probe-crm-readable.jsonl" 2> "$LOGS/probe-crm-readable.err" || { cat "$LOGS/probe-crm-readable.err"; die "crm readable probe failed"; }

# ---------- Nocturne: set up in Development, measure in Production ----------
running "$PG"
for _ in $(seq 1 60); do docker exec "$PG" pg_isready -h 127.0.0.1 -q && break; sleep 2; done
"$HERE/boot-nocturne.sh" "$NOC" "$NOC_PORT" Development "$PG_PORT" "$LOGS/noc-dev.log" "$LOGS/noc-dev.pid"
DEVPID=$(cat "$LOGS/noc-dev.pid"); PIDS+=("$DEVPID")
wait_http "http://127.0.0.1:$NOC_PORT/api/versions" 503 "$DEVPID"   # 503 setup_required: no tenant yet
$NODE "$HERE/setup-nocturne.js" tenant "http://127.0.0.1:$NOC_PORT" "$TOKFILE" > "$LOGS/noc-setup.json"
stop_pid "$DEVPID"
"$HERE/boot-nocturne.sh" "$NOC" "$NOC_PORT" Production "$PG_PORT" "$LOGS/noc-prod.log" "$LOGS/noc-prod.pid"
PRODPID=$(cat "$LOGS/noc-prod.pid"); PIDS+=("$PRODPID")
wait_http "http://127.0.0.1:$NOC_PORT/api/versions" 200 "$PRODPID"
# the runtime document for the v1-v3 surface; its `servers` entry names this run's port, so it is set to "/"
curl -sf "http://127.0.0.1:$NOC_PORT/openapi/nightscout.json" | $NODE -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const d=JSON.parse(s);d.servers=[{url:"/"}];process.stdout.write(JSON.stringify(d,null,1)+"\n")})' > "$OUT/nocturne-nightscout-openapi.json"
running "$PG"
NPAR_SECRET="$(cat "$TOKFILE")" $NODE "$HERE/probe.js" "http://127.0.0.1:$NOC_PORT" noc-public-none > "$OUT/probe-noc-public-none.jsonl" 2> "$LOGS/probe-noc-none.err" || { cat "$LOGS/probe-noc-none.err"; die "Nocturne probe failed"; }
$NODE "$HERE/setup-nocturne.js" public-read "http://127.0.0.1:$NOC_PORT" "$TOKFILE" > "$OUT/nocturne-public-read-setup.json"
running "$PG"
NPAR_SECRET="$(cat "$TOKFILE")" $NODE "$HERE/probe.js" "http://127.0.0.1:$NOC_PORT" noc-public-read > "$OUT/probe-noc-public-read.jsonl" 2> "$LOGS/probe-noc-read.err" || { cat "$LOGS/probe-noc-read.err"; die "Nocturne probe failed"; }

# ---------- document diff, meta, table ----------
$NODE "$HERE/docdiff.js" "$CRM/node_modules/js-yaml" "$CRM/lib/server/swagger.yaml" "$CRM/lib/api3/swagger.yaml" "$OUT/nocturne-nightscout-openapi.json" > "$OUT/docdiff.json"
cat > "$OUT/meta.json" <<EOF
{
 "crm": {"commit": "$CRM_COMMIT", "what": "pull request #8858 head: dev c08cbe03 plus accurate API documents; NODE_ENV=production, API_SECRET set, two servers: AUTH_DEFAULT_ROLES=denied and =readable, MongoDB 7"},
 "noc": {"commit": "$NOC_COMMIT", "what": "main 2026-10-26; Release build, alert library from crates/; set up in Development, measured in ASPNETCORE_ENVIRONMENT=Production, PostgreSQL 17.6, one tenant at the apex"},
 "probeSha256": "$(sha "$HERE/probe.js")",
 "sha256": {"probe.js": "$(sha "$HERE/probe.js")", "ops.js": "$(sha "$HERE/ops.js")", "docdiff.js": "$(sha "$HERE/docdiff.js")"},
 "node": "$($NODE --version)", "dotnet": "$(dotnet --version)"
}
EOF
$NODE "$HERE/compare.js" "$OUT" > "$OUT/compare.md"
$NODE "$HERE/compare.js" --selftest "$OUT"

# ---------- non-vacuity: one altered Nocturne status changes compare.md for that probe only ----------
ALT=$(mktemp -d); cp "$OUT"/*.json "$OUT"/*.jsonl "$ALT/"
VICTIM=$($NODE -e '
const fs=require("fs");const L=f=>fs.readFileSync(f,"utf8").trim().split("\n").map(JSON.parse);
const c=L(process.argv[1]),n=L(process.argv[2]);
const v=n.find(r=>r.id==="v3.version"&&r.status===200&&c.find(x=>x.id===r.id&&x.status===200));
if(!v){process.exit(4)} v.status=299; fs.writeFileSync(process.argv[2],n.map(r=>JSON.stringify(r)).join("\n")+"\n"); console.log(v.id)' "$ALT/probe-crm-denied.jsonl" "$ALT/probe-noc-public-none.jsonl")
$NODE "$HERE/compare.js" "$ALT" > "$ALT/compare.md"
CHANGED=$(diff "$OUT/compare.md" "$ALT/compare.md" | grep '^>' || true)
echo "$CHANGED" > "$LOGS/nonvacuity.diff"
[ -n "$CHANGED" ] || die "non-vacuity: altering $VICTIM did not change compare.md"
# every changed line is the victim's probe row, its operation row, or a count line
if echo "$CHANGED" | grep -v -e "\`$VICTIM\`" -e '`GET /api/v3/version`' -e '^> Probes, ' > /dev/null; then die "non-vacuity: altering $VICTIM changed other lines (see $LOGS/nonvacuity.diff)"; fi
echo "non-vacuity ok: altering $VICTIM's status changed $(echo "$CHANGED" | wc -l) line(s) of compare.md, all for that probe" >&2
rm -rf "$ALT"
rm -f "$TOKFILE"
echo "results: $OUT; logs: $LOGS" >&2
