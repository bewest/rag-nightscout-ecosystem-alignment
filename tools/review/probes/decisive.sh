SP=/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/17db8ba2-ae4b-4699-a1d7-3647f27a7741/scratchpad
cd $SP/crm-boot
SHA1=$(printf '%s' "${NS_HARNESS_SECRET:?set NS_HARNESS_SECRET}" | sha1sum | cut -d' ' -f1); B=http://127.0.0.1:1380
docker exec nsharness-mongo mongosh --quiet --eval 'db.getSiblingDB("nsharness_dev").dropDatabase()' >/dev/null
rm -f $SP/server.log
T0=$(date +%s.%N)
./node_modules/.bin/env-cmd -f ./my.env node lib/server/server.js > $SP/server.log 2>&1 &
SRV=$!; for i in $(seq 1 600); do grep -q 'Listening on port' $SP/server.log && break; sleep 0.1; done
sleep 1.5
T1=$(date +%s.%N); echo "BOOT_USABLE_SECONDS=$(echo "$T1-$T0"|bc)"
curl -s -o /dev/null -H "api-secret: $SHA1" -H 'Content-Type: application/json' -d '{"name":"h","roles":["readable","careportal"]}' $B/api/v2/authorization/subjects
TOK=$(curl -s -H "api-secret: $SHA1" $B/api/v2/authorization/subjects | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["accessToken"])')
echo "TOKEN=$TOK"
# profile only, NO entries -> must be RED
curl -s -o /dev/null -H "api-secret: $SHA1" -H 'Content-Type: application/json' --data-binary @$SP/profile.json $B/api/v1/profile
echo "===== STATE A: empty entries (EXPECT RED) ====="
node ./ns-client-gate.js "$B/?token=$TOK" 50; echo "A_EXIT=$?"
echo "===== STATE B: 288 entries seeded (EXPECT GREEN) ====="
curl -s -o /dev/null -H "api-secret: $SHA1" -H 'Content-Type: application/json' --data-binary @$SP/entries.json $B/api/v1/entries
T2=$(date +%s.%N)
node ./ns-client-gate.js "$B/?token=$TOK" 50; echo "B_EXIT=$?"
T3=$(date +%s.%N); echo "GATE_WALL_SECONDS=$(echo "$T3-$T2"|bc)"
echo "===== STATE C: inject a client-side regression (EXPECT RED) ====="
cp lib/client/index.js $SP/index.js.bak
sed -i "s|^'use strict';|'use strict';\nthrow new Error('NSHARNESS injected client regression');|" lib/client/index.js
head -3 lib/client/index.js
sleep 12   # let webpack-dev-middleware rebuild
grep -oE 'webpack built [a-f0-9]+ in [0-9]+ ms' $SP/server.log | tail -2
node ./ns-client-gate.js "$B/?token=$TOK" 50; echo "C_EXIT=$?"
cp $SP/index.js.bak lib/client/index.js
kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
echo ALLDONE
