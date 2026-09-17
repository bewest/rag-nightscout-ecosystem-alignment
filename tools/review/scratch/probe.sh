SP=/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/17db8ba2-ae4b-4699-a1d7-3647f27a7741/scratchpad
cd $SP/crm-boot
SHA1=$(printf '%s' "${NS_HARNESS_SECRET:?set NS_HARNESS_SECRET}" | sha1sum | cut -d' ' -f1); B=http://127.0.0.1:1380
docker exec nsharness-mongo mongosh --quiet --eval 'db.getSiblingDB("nsharness_dev").dropDatabase()' >/dev/null
rm -f $SP/server.log
./node_modules/.bin/env-cmd -f ./my.env node lib/server/server.js > $SP/server.log 2>&1 &
SRV=$!; for i in $(seq 1 600); do grep -q 'Listening on port' $SP/server.log && break; sleep 0.1; done
curl -s -o /dev/null -H "api-secret: $SHA1" -H 'Content-Type: application/json' --data-binary @$SP/profile.json $B/api/v1/profile
curl -s -o /dev/null -H "api-secret: $SHA1" -H 'Content-Type: application/json' --data-binary @$SP/entries.json $B/api/v1/entries
curl -s -o /dev/null -H "api-secret: $SHA1" -H 'Content-Type: application/json' -d '{"name":"h","roles":["readable"]}' $B/api/v2/authorization/subjects
TOK=$(curl -s -H "api-secret: $SHA1" $B/api/v2/authorization/subjects | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["accessToken"])')
echo "### WITH 288 ENTRIES ###"; node ./probe2.js "$B/?token=$TOK"
echo "### AFTER deleteMany entries ###"
docker exec nsharness-mongo mongosh --quiet --eval 'db.getSiblingDB("nsharness_dev").entries.deleteMany({})' 
node ./probe2.js "$B/?token=$TOK"
kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
