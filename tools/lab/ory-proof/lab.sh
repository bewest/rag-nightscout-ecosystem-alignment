#!/usr/bin/env bash
# T30-ORY-PROOF lab control. Usage: ./lab.sh secrets|up|down|ps|logs <svc>|recreate-kratos
set -euo pipefail
cd "$(dirname "$0")"
# LAB_VARIANT=cookie-apex|cookie-user-content|recovery-template|hydra-opaque overlays variants/<name>.yaml
DC=(docker compose --env-file .secrets.env -f compose.yaml)
[ -n "${LAB_VARIANT:-}" ] && DC+=(-f "variants/${LAB_VARIANT}.yaml")
# containers carry no healthcheck, so poll the services' own readiness endpoints from the host
ready() {
  for i in $(seq 1 120); do
    if curl -sf 127.0.0.1:44433/health/ready >/dev/null && curl -sf 127.0.0.1:44434/health/ready >/dev/null \
      && curl -sf 127.0.0.1:44444/health/ready >/dev/null && curl -sf 127.0.0.1:44445/health/ready >/dev/null; then return 0; fi
    sleep 0.5
  done
  echo "kratos/hydra not ready" >&2; return 1
}
gen() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
case "${1:-}" in
  secrets)
    [ -f .secrets.env ] && { echo ".secrets.env exists"; exit 0; }
    umask 077
    { echo "PG_PASSWORD=$(gen)"
      echo "KRATOS_SECRET_COOKIE=$(gen)"
      echo "KRATOS_SECRET_CIPHER=$(gen | head -c 32)"
      echo "KRATOS_SECRET_DEFAULT=$(gen)"
      echo "HYDRA_SECRET_SYSTEM=$(gen)"
      echo "HYDRA_PAIRWISE_SALT=$(gen)"; } > .secrets.env
    echo "wrote .secrets.env (gitignored)";;
  up)      "${DC[@]}" up -d --wait kratos hydra mailpit && ready ;;
  recreate-kratos) "${DC[@]}" up -d --wait --force-recreate --no-deps kratos && ready ;;
  recreate-hydra) "${DC[@]}" up -d --wait --force-recreate --no-deps hydra && ready ;;
  down)    "${DC[@]}" down -v ;;
  ps)      "${DC[@]}" ps ;;
  logs)    "${DC[@]}" logs "${2:-kratos}" ;;
  *) echo "usage: $0 secrets|up|down|ps|logs <svc>|recreate-kratos|recreate-hydra"; exit 2;;
esac
