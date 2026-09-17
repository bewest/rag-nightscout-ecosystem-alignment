#!/bin/bash
SP=/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/17db8ba2-ae4b-4699-a1d7-3647f27a7741/scratchpad
cd $SP/crm-boot
SHA1=$(printf '%s' "${NS_HARNESS_SECRET:?set NS_HARNESS_SECRET}" | sha1sum | cut -d' ' -f1)
B=http://127.0.0.1:1380
# fresh db each cycle
docker exec nsharness-mongo mongosh --quiet --eval 'db.getSiblingDB("nsharness_dev").dropDatabase()' >/dev/null
rm -f $SP/server.log
T0=$(date +%s.%N)
./node_modules/.bin/env-cmd -f ./my.env node lib/server/server.js > $SP/server.log 2>&1 &
SRV=$!
for i in $(seq 1 600); do grep -q 'Listening on port' $SP/server.log 2>/dev/null && break; sleep 0.1; done
T1=$(date +%s.%N); echo "BOOT_TO_LISTENING_SECONDS=$(echo "$T1-$T0"|bc)"
# seed
curl -s -o /dev/null -w 'SEED_PROFILE_HTTP=%{http_code}\n' -H "api-secret: $SHA1" -H 'Content-Type: application/json' --data-binary @$SP/profile.json $B/api/v1/profile
curl -s -o /dev/null -w 'SEED_ENTRIES_HTTP=%{http_code}\n' -H "api-secret: $SHA1" -H 'Content-Type: application/json' --data-binary @$SP/entries.json $B/api/v1/entries
NOW=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)
curl -s -o /dev/null -w 'SEED_TREATMENT_HTTP=%{http_code}\n' -H "api-secret: $SHA1" -H 'Content-Type: application/json' -d "[{\"eventType\":\"Meal Bolus\",\"carbs\":45,\"insulin\":4.5,\"created_at\":\"$NOW\",\"enteredBy\":\"nsharness\"}]" $B/api/v1/treatments
TOK=$(curl -s -H "api-secret: $SHA1" -H 'Content-Type: application/json' -d '{"name":"harness","roles":["readable","careportal"]}' $B/api/v2/authorization/subjects >/dev/null; curl -s -H "api-secret: $SHA1" $B/api/v2/authorization/subjects | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["accessToken"])')
echo "TOKEN=$TOK"
T2=$(date +%s.%N); echo "SEED_TOTAL_SECONDS=$(echo "$T2-$T1"|bc)"
echo "########## GREEN CONTROL ##########"
node ./ns-client-gate.js "$B/?token=$TOK" 50; echo "GREEN_EXIT=$?"
T3=$(date +%s.%N); echo "GATE_SECONDS=$(echo "$T3-$T2"|bc)"
echo "########## RED CONTROL: wipe entries, chart must not draw ##########"
docker exec nsharness-mongo mongosh --quiet --eval 'db.getSiblingDB("nsharness_dev").entries.deleteMany({})' >/dev/null
node ./ns-client-gate.js "$B/?token=$TOK" 50; echo "RED_EXIT=$?"
kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
echo "DONE"
