#!/usr/bin/env bash
export N_PREFIX=$HOME/n
for t in "$@"; do (cd /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/$t && n exec 22.23.2 npm ci --no-audit --no-fund > ${OUT:-/tmp/seam-propagation}/$t.npmci.log 2>&1; echo "$t npm ci exit=$?"); done
