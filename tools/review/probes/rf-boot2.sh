#!/bin/bash
TREE=$1; PORT=$2; DB=$3; LOG=$4; SEC=$5; shift 5
cd "$TREE"
env MONGODB_URI="mongodb://127.0.0.1:27018/$DB" API_SECRET="$SEC" PORT=$PORT HOSTNAME=127.0.0.1 \
    INSECURE_USE_HTTP=true AUTH_DEFAULT_ROLES=denied NODE_ENV=production \
    "$@" node lib/server/server.js > "$LOG" 2>&1 &
echo $!
