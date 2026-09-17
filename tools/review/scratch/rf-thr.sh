#!/bin/bash
SHA1=$(printf '%s' "${NS_HARNESS_SECRET:?set NS_HARNESS_SECRET}" | sha1sum | cut -d' ' -f1)
P=$1; MODE=$2
U=http://127.0.0.1:$P
echo "== port $P mode=$MODE =="
for i in 1 2 3; do
  if [ "$MODE" = token ]; then
    t=$(curl -s -o /dev/null -w '%{time_total} %{http_code}' "$U/api/v1/entries.json?token=badtoken$i")
  else
    t=$(curl -s -o /dev/null -w '%{time_total} %{http_code}' -H "api-secret: deadbeefdeadbeefdeadbeef0000000$i" "$U/api/v1/entries.json")
  fi
  echo "  bad-cred attempt $i: $t"
done
t=$(curl -s -o /dev/null -w '%{time_total} %{http_code}' "$U/api/v1/entries.json")
echo "  ANON after 3 bad: $t"
t=$(curl -s -o /dev/null -w '%{time_total} %{http_code}' -H "api-secret: $SHA1" "$U/api/v1/entries.json")
echo "  GOOD-secret after: $t"
