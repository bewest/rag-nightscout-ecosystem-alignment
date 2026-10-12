#!/usr/bin/env bash
# run-variants.sh - the five Kratos cookie-scope shapes on a FRESH stack, in one run:
#   host-only, apex, content-domain (probes/cookies.js, as in the 2026-10-07 proof),
#   E  apex + hardened edge          (probes/cookie-edge.js,    LAB_MODE=edge)
#   H2 host-only + our own hand-off  (probes/cookie-handoff.js, LAB_MODE=handoff)
# plus probes/proof.js as a regression check of the nsjwt stand-in after the variant hooks.
#   RUN=<results dir name>  (default: <date>-cookie-variants)
#   KRATOS_IMAGE / HYDRA_IMAGE as in run-all.sh; the 2026-10-12 run used v26.2.0 (see the doc)
# Writes results/$RUN/*.json and results/$RUN/summary.txt; leaves the stack UP (`./lab.sh down`).
set -uo pipefail
cd "$(dirname "$0")"
export RUN="${RUN:-$(date +%F)-cookie-variants}"
[ -f .secrets.env ] || ./lab.sh secrets
./lab.sh down >/dev/null 2>&1
./lab.sh up >/dev/null 2>&1 || { echo "stack did not come up"; exit 2; }
rc=0
step() { echo; echo "=== $*"; "$@" || rc=1; }
kratos() { LAB_VARIANT="${1:-}" ./lab.sh recreate-kratos >/dev/null 2>&1 ; }

step node probes/proof.js
VARIANT=host-only step node probes/cookies.js
step node probes/cookie-handoff.js
kratos cookie-apex;          VARIANT=apex step node probes/cookies.js
step node probes/cookie-edge.js
kratos cookie-user-content;  VARIANT=user-content step node probes/cookies.js
kratos

mkdir -p results/"$RUN"
{
  echo "run $RUN  $(date -u +%FT%TZ)"
  docker inspect ory-proof-kratos-1 ory-proof-hydra-1 --format 'image {{.Name}} {{.Config.Image}}'
  echo "chrome $(${CHROME:-/usr/bin/google-chrome} --version)  node $(node --version)"
  for f in results/"$RUN"/*.json; do
    node -e "const d=require('./$f'); console.log((d.error ? 'ERROR    ' : d.failed ? 'MISMATCH ' : 'ok       ') + d.probe.padEnd(28) + (d.total-d.failed) + '/' + d.total + (d.error ? '  ERROR ' + d.error.split('\n')[0] : '')); for (const c of d.checks.filter(c=>!c.pass)) console.log('         not as predicted: ' + c.id)"
  done
} | tee results/"$RUN"/summary.txt
exit $rc
