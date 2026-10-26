#!/usr/bin/env bash
# boot-nocturne.sh — start the Nocturne API from a built tree (run.sh builds it).
#
# Usage: boot-nocturne.sh <nocturne tree> <port> <Development|Production> <pg port> <log> <pidfile>
#   Passwords for the nocturne_app / nocturne_migrator roles come from $NPAR_PG_APP_PW / $NPAR_PG_MIG_PW,
#   the instance key from $NPAR_INSTANCE_KEY (run.sh makes random ones per run).
# Binds 127.0.0.1. Requests to 127.0.0.1 carry no tenant subdomain, so Nocturne resolves them to
# its only tenant (TenantResolutionMiddleware, single-tenant apex).
set -euo pipefail
TREE=$1 PORT=$2 ENVNAME=$3 PGPORT=$4 LOG=$5 PIDF=$6
: "${NPAR_PG_APP_PW:?}" "${NPAR_PG_MIG_PW:?}" "${NPAR_INSTANCE_KEY:?}"
cd "$TREE/src/API/Nocturne.API"
setsid nohup env ASPNETCORE_ENVIRONMENT="$ENVNAME" ASPNETCORE_URLS="http://127.0.0.1:$PORT" DOTNET_gcServer=0 \
  "ConnectionStrings__nocturne-postgres=Host=127.0.0.1;Port=$PGPORT;Database=nocturne;Username=nocturne_app;Password=$NPAR_PG_APP_PW" \
  "ConnectionStrings__nocturne-postgres-migrator=Host=127.0.0.1;Port=$PGPORT;Database=nocturne;Username=nocturne_migrator;Password=$NPAR_PG_MIG_PW" \
  INSTANCE_KEY="$NPAR_INSTANCE_KEY" DemoService__Enabled=false \
  dotnet bin/Release/net10.0/Nocturne.API.dll > "$LOG" 2>&1 < /dev/null &
echo $! > "$PIDF"
