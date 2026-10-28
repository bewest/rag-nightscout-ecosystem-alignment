#!/usr/bin/env bash
# Start-form matrix: the same docker run forms against two images; compare boot, PID 1, stop.
set -u
NET=nslab-net; SECRET=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
docker network create $NET >/dev/null 2>&1
docker rm -f nslab-mongo >/dev/null 2>&1
docker run -d --name nslab-mongo --network $NET mongo:8.0 >/dev/null
sleep 6
ENVS=(-e MONGODB_URI=mongodb://nslab-mongo:27017/nslab -e API_SECRET=$SECRET -e INSECURE_USE_HTTP=true -e DISPLAY_UNITS=mg/dl -e PORT=1337)
forms=("default|" "node|node lib/server/server.js" "npm|npm start" "shc|sh -c node\ lib/server/server.js" "nssingle|nightscout single")
for img in dev pr8865; do
  for f in "${forms[@]}"; do
    name=${f%%|*}; cmd=${f#*|}; c=nslab-$img-$name
    docker rm -f $c >/dev/null 2>&1
    if [ -z "$cmd" ]; then docker run -d --name $c --network $NET "${ENVS[@]}" nslab:$img >/dev/null
    elif [ $name = shc ]; then docker run -d --name $c --network $NET "${ENVS[@]}" nslab:$img sh -c 'node lib/server/server.js' >/dev/null
    else docker run -d --name $c --network $NET "${ENVS[@]}" nslab:$img $cmd >/dev/null; fi
    t0=$(date +%s.%N); code=000
    running=true
    for i in $(seq 1 120); do
      if [ "$(docker inspect -f '{{.State.Running}}' $c)" != true ]; then running=false; break; fi
      code=$(docker exec $c wget -q -S -O /dev/null http://127.0.0.1:1337/api/v1/status.json 2>&1 | awk '/HTTP\//{print $2; exit}')
      [ "$code" = 200 ] && break; sleep 0.5
    done
    if [ $running = false ]; then
      echo "$img|$name|exited before serving|exit=$(docker inspect $c --format '{{.State.ExitCode}}')|$(docker logs $c 2>&1 | grep -m1 -E 'Error|error' | cut -c1-80)"
      docker rm -f $c >/dev/null; continue
    fi
    up=$(echo "$(date +%s.%N) - $t0" | bc)
    pid1=$(docker exec $c cat /proc/1/cmdline | tr '\0' ' ')
    nnode=$(docker exec $c sh -c 'ls /proc | grep -E "^[0-9]+$" | while read p; do tr "\0" " " < /proc/$p/cmdline; echo; done 2>/dev/null | grep -c "^node \|^npm "')
    hc=""; [ $img = pr8865 ] && hc=$(docker exec $c nightscout healthcheck >/dev/null 2>&1; echo "healthcheck_exit=$?")
    s0=$(date +%s.%N); docker stop -t 10 $c >/dev/null; st=$(echo "$(date +%s.%N) - $s0" | bc)
    ex=$(docker inspect $c --format '{{.State.ExitCode}}')
    echo "$img|$name|status=$code|up=${up:0:5}s|pid1=$pid1|node_or_npm_procs=$nnode|stop=${st:0:5}s|exit=$ex|$hc"
    docker logs $c > /tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/50546576-09fa-4321-aeff-597d94ca7f3a/scratchpad/imglab/log-$img-$name.txt 2>&1
    docker rm -f $c >/dev/null
  done
  # non-server forms
  echo "$img|env-keys|$(docker run --rm nslab:$img env | cut -d= -f1 | sort | tr '\n' ' ')"
  echo "$img|node-version|$(docker run --rm nslab:$img node --version)"
done
docker rm -f nslab-mongo >/dev/null; docker network rm $NET >/dev/null
