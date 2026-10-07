#!/usr/bin/env bash
# probes/ops.sh - operational cost observations for the running stack: images, idle memory,
# migrations and tables per database. Usage: RUN=<dir> probes/ops.sh   (stack must be up and idle)
set -euo pipefail
cd "$(dirname "$0")/.."
RUN="${RUN:-$(date +%F)}"; mkdir -p "results/$RUN"
DC=(docker compose --env-file .secrets.env -f compose.yaml)
psql() { "${DC[@]}" exec -T postgres psql -U lab -At "$@"; }
{
  echo "## images (pinned)"
  for s in kratos hydra postgres mailpit; do
    img=$(docker inspect -f '{{.Config.Image}}' "ory-proof-$s-1")
    printf '%s\t%s\t%s MB\n' "$s" "$img" "$(docker image inspect -f '{{.Size}}' "$img" | awk '{printf "%.1f", $1/1e6}')"
  done
  echo "## versions"
  docker exec ory-proof-kratos-1 kratos version | tr -s '\t' ' '
  docker exec ory-proof-hydra-1 hydra version | tr -s ' '
  echo "## idle memory and CPU (docker stats --no-stream, ${IDLE_SECONDS:-30} s after last request)"
  sleep "${IDLE_SECONDS:-30}"
  docker stats --no-stream --format '{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' ory-proof-kratos-1 ory-proof-hydra-1 ory-proof-postgres-1 ory-proof-mailpit-1
  echo "## one-shot migration containers: wall time on this (fresh) stack"
  for c in kratos-migrate hydra-migrate; do
    docker inspect -f '{{.State.StartedAt}} {{.State.FinishedAt}} {{.State.ExitCode}}' "ory-proof-$c-1" |
      node -e "const [a,b,e]=require('fs').readFileSync(0,'utf8').trim().split(' '); console.log('$c', ((Date.parse(b)-Date.parse(a))/1000).toFixed(2)+' s', 'exit='+e)"
  done
  echo "## migrations applied and tables per database"
  for db in kratos hydra nsjwt nrg; do
    t=$(psql -d "$db" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
    m=$(psql -d "$db" -c "SELECT count(*) FROM schema_migration" 2>/dev/null || psql -d "$db" -c "SELECT count(*) FROM knex_migrations" 2>/dev/null || echo n/a)
    s=$(psql -d "$db" -c "SELECT pg_size_pretty(pg_database_size('$db'))")
    printf '%s\ttables=%s\tmigrations=%s\tsize=%s\n' "$db" "$t" "$m" "$s"
  done
  echo "## identities and sessions held by the pool after the probes"
  printf 'identities=%s sessions=%s hydra_clients=%s\n' \
    "$(psql -d kratos -c 'SELECT count(*) FROM identities')" "$(psql -d kratos -c 'SELECT count(*) FROM sessions')" "$(psql -d hydra -c 'SELECT count(*) FROM hydra_client')"
} | tee "results/$RUN/ops.txt"
