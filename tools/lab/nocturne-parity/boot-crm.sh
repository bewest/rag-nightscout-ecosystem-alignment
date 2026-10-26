#!/usr/bin/env bash
# boot-crm.sh — start one cgm-remote-monitor server (from the audit's boot.sh for #8858).
#
# Usage: boot-crm.sh <crm tree> <port> <AUTH_DEFAULT_ROLES> <mongo uri> <log> <pidfile>
#   API_SECRET comes from $NPAR_CRM_SECRET (run.sh makes a random one per run).
# Binds 127.0.0.1. Node comes from $NODE_CMD (default `node`; run.sh uses `n exec 24 node`).
set -euo pipefail
TREE=$1 PORT=$2 ROLES=$3 MONGO=$4 LOG=$5 PIDF=$6
: "${NPAR_CRM_SECRET:?NPAR_CRM_SECRET must be set}"
cd "$TREE"
setsid nohup env -i PATH="$PATH" HOME="$HOME" N_PREFIX="${N_PREFIX:-}" \
  CUSTOMCONNSTR_mongo="$MONGO" API_SECRET="$NPAR_CRM_SECRET" HOSTNAME=127.0.0.1 PORT="$PORT" \
  INSECURE_USE_HTTP=true NODE_ENV=production AUTH_DEFAULT_ROLES="$ROLES" \
  ENABLE="careportal boluscalc food bwp cage sage iage iob cob basal ar2 rawbg pushover bgi pump openaps loop alexa googlehome cors" \
  ${NODE_CMD:-node} lib/server/server.js > "$LOG" 2>&1 < /dev/null &
echo $! > "$PIDF"
