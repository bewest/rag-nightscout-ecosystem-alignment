#!/bin/sh
# One container, three mongod processes, one replica set (rs0), for the MIG-VV lab.
# Run with --network host so each member's address (127.0.0.1:<port>) is the same
# from inside the container and from the host. Binds 127.0.0.1 only.
#   env MONGO_ROOT_PW  root password (from the operator's scratch directory; never in git)
#   /run/lab/keyfile   replica-set keyfile, mounted read-only (from scratch; never in git)
#   args: three ports
set -e
P1=$1; P2=$2; P3=$3
SHELL_BIN=$(command -v mongosh || command -v mongo)
install -m 400 /run/lab/keyfile /tmp/keyfile
for p in $P1 $P2 $P3; do
  mkdir -p /data/rs/$p
  mongod --replSet rs0 --bind_ip 127.0.0.1 --port $p --dbpath /data/rs/$p \
    --keyFile /tmp/keyfile --fork --logpath /data/rs/$p.log
done
# The localhost exception allows creating the first user over 127.0.0.1.
$SHELL_BIN --quiet --port $P1 --eval "rs.initiate({_id: 'rs0', members: [
  {_id: 0, host: '127.0.0.1:$P1', priority: 2}, {_id: 1, host: '127.0.0.1:$P2'}, {_id: 2, host: '127.0.0.1:$P3'}]})"
i=0; until $SHELL_BIN --quiet --port $P1 --eval "db.hello().isWritablePrimary" | grep -q true; do i=$((i+1)); [ $i -gt 60 ] && exit 1; sleep 1; done
$SHELL_BIN --quiet --port $P1 admin --eval "db.createUser({user: 'labroot', pwd: '$MONGO_ROOT_PW', roles: ['root']})" >/dev/null
echo READY
exec tail -F /data/rs/$P1.log /data/rs/$P2.log /data/rs/$P3.log >/dev/null
