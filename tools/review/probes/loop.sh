SP=/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/17db8ba2-ae4b-4699-a1d7-3647f27a7741/scratchpad
cd $SP/crm-boot
SHA1=$(printf '%s' "${NS_HARNESS_SECRET:?set NS_HARNESS_SECRET}" | sha1sum | cut -d' ' -f1); B=http://127.0.0.1:1380
run_one () {
  REF="$1"; DB="nsharness_$(echo $REF | tr '/-' '__')"
  LT0=$(date +%s.%N)
  git checkout --quiet --detach "$REF" 2>/dev/null
  LT1=$(date +%s.%N)
  sed -i "s|/nsharness[a-z_0-9]*|/$DB|" my.env
  docker exec nsharness-mongo mongosh --quiet --eval "db.getSiblingDB('$DB').dropDatabase()" >/dev/null
  rm -f $SP/server.log
  ./node_modules/.bin/env-cmd -f ./my.env node lib/server/server.js > $SP/server.log 2>&1 &
  SRV=$!
  for i in $(seq 1 600); do grep -q 'Listening on port' $SP/server.log && break; sleep 0.1; done
  sleep 1.5
  LT2=$(date +%s.%N)
  curl -s -o /dev/null -H "api-secret: $SHA1" -H 'Content-Type: application/json' -d '{"name":"h","roles":["readable","careportal"]}' $B/api/v2/authorization/subjects
  TOK=$(curl -s -H "api-secret: $SHA1" $B/api/v2/authorization/subjects | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["accessToken"])' 2>/dev/null)
  curl -s -o /dev/null -H "api-secret: $SHA1" -H 'Content-Type: application/json' --data-binary @$SP/profile.json $B/api/v1/profile
  curl -s -o /dev/null -H "api-secret: $SHA1" -H 'Content-Type: application/json' --data-binary @$SP/entries.json $B/api/v1/entries
  LT3=$(date +%s.%N)
  G=$(node ./ns-client-gate.js "$B/?token=$TOK" 50); RC=$?
  LT4=$(date +%s.%N)
  kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
  printf "%-42s checkout=%.2fs boot=%.2fs seed=%.2fs gate=%.2fs TOTAL=%.2fs gate_rc=%d\n" \
    "$REF" $(echo "$LT1-$LT0"|bc) $(echo "$LT2-$LT1"|bc) $(echo "$LT3-$LT2"|bc) $(echo "$LT4-$LT3"|bc) $(echo "$LT4-$LT0"|bc) $RC
  echo "      $G"
}
for r in a8888f0d bf/parms bf/cache bf/reads $(cat $SP/stack.sha); do run_one "$r"; done
git checkout --quiet --detach a8888f0d
