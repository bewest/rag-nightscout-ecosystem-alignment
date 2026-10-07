#!/usr/bin/env bash
# run-all.sh - the whole T30-ORY-PROOF measurement on a FRESH stack, in order.
#   RUN=<results dir name>  (default: today's date)
#   KRATOS_IMAGE / HYDRA_IMAGE override the pinned images (compose.yaml defaults: v1.3.1 / v2.3.0)
#   SKIP_NRG=1 skips the nightscout-roles-gateway port measurement
# Leaves the stack UP for inspection; `./lab.sh down` removes it and its volumes.
set -uo pipefail
cd "$(dirname "$0")"
export RUN="${RUN:-$(date +%F)}"
[ -f .secrets.env ] || ./lab.sh secrets
./lab.sh down >/dev/null 2>&1
./lab.sh up >/dev/null 2>&1 || { echo "stack did not come up"; exit 2; }
rc=0
step() { echo; echo "=== $*"; "$@" || rc=1; }
kratos() { LAB_VARIANT="${1:-}" ./lab.sh recreate-kratos >/dev/null 2>&1 ; }
hydra()  { LAB_VARIANT="${1:-}" ./lab.sh recreate-hydra  >/dev/null 2>&1 ; }

step node probes/proof.js
VARIANT=host-only step node probes/cookies.js
kratos cookie-apex;          VARIANT=apex step node probes/cookies.js
kratos cookie-user-content;  VARIANT=user-content step node probes/cookies.js
kratos
step node probes/hydra.js
hydra hydra-opaque;          step node probes/hydra-pairwise.js
hydra
step node probes/return-to.js
VARIANT=default step node probes/recovery.js
kratos recovery-template;    VARIANT=recovery-template step node probes/recovery.js
kratos
[ -n "${SKIP_NRG:-}" ] || step ./probes/nrg-port.sh
step ./probes/ops.sh

echo; echo "=== summary results/$RUN"
for f in results/"$RUN"/*.json; do
  node -e "const d=require('./$f'); console.log((d.error ? 'ERROR    ' : d.failed ? 'MISMATCH ' : 'ok       ') + d.probe.padEnd(28) + (d.total-d.failed) + '/' + d.total + (d.error ? '  ERROR ' + d.error.split('\n')[0] : ''))"
done
exit $rc
