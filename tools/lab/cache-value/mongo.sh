#!/usr/bin/env bash
# mongo.sh - this lab's MongoDB containers (ports 27800-27820 only).
#   mongo.sh up <name> <port> [image]   start (no --rm, nofile 64000), wait, print server version
#   mongo.sh inspect <name>             one JSON line: state, restart count, container id, image
#   mongo.sh down <name>                stop and remove
set -euo pipefail
cmd=$1; name=$2
case $cmd in
  up)
    port=$3; image=${4:-mongo:8.0}
    [ "$port" -ge 27800 ] && [ "$port" -le 27820 ] || { echo "port must be 27800-27820" >&2; exit 2; }
    docker run -d --name "$name" --ulimit nofile=64000:64000 -p "127.0.0.1:$port:27017" --restart no "$image" --quiet >/dev/null
    for _ in $(seq 1 60); do
      v=$(docker exec "$name" mongosh --quiet --eval 'db.version()' 2>/dev/null || true)
      [ -n "$v" ] && { echo "$v"; exit 0; }
      sleep 1
    done
    echo "mongo $name did not answer" >&2; exit 1 ;;
  inspect)
    docker inspect -f '{"name":"{{.Name}}","id":"{{.Id}}","image":"{{.Config.Image}}","status":"{{.State.Status}}","running":{{.State.Running}},"restartCount":{{.RestartCount}},"oomKilled":{{.State.OOMKilled}},"startedAt":"{{.State.StartedAt}}","at":"'"$(date -u +%FT%TZ)"'"}' "$name" ;;
  down)
    docker rm -f "$name" >/dev/null ;;
  *) echo "usage: mongo.sh up|inspect|down <name> ..." >&2; exit 2 ;;
esac
