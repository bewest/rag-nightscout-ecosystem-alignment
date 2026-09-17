#!/bin/bash
# boot.sh <treedir> <port> <dbname> <logfile> [extra env assignments...]
TREE=$1; PORT=$2; DB=$3; LOG=$4; shift 4
cd "$TREE"
env MONGODB_URI="mongodb://127.0.0.1:27018/$DB" \
    API_SECRET="${NS_HARNESS_SECRET:?set NS_HARNESS_SECRET}" PORT=$PORT HOSTNAME=127.0.0.1 \
    INSECURE_USE_HTTP=true DISPLAY_UNITS=mg/dl AUTH_DEFAULT_ROLES=denied \
    AUTH_FAIL_DELAY=3000 NODE_ENV=production \
    ENABLE='careportal basal iob cob bwp cage sage iage rawbg' \
    "$@" node lib/server/server.js > "$LOG" 2>&1 &
echo $!
