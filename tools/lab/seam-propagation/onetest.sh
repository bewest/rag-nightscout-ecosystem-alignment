#!/usr/bin/env bash
# onetest.sh <worktree> <label> <test files...> : run named test files with the tree's mocha on prop-mongo
W=/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work; d=$W/$1; label=$2; shift 2
export N_PREFIX=$HOME/n; cd $d
sed "s#^CUSTOMCONNSTR_mongo=.*#CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:27152/prop_one_${label//-/_}#" tests/ci.test.env > my.test.env
NODE_ENV=test n exec 22.23.2 node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js --timeout 5000 --require ./tests/hooks.js --exit "$@" > ${OUT:-/tmp/seam-propagation}/one-$label.log 2>&1
rm -f my.test.env
grep -E '^ +[0-9]+ (passing|failing|pending)' ${OUT:-/tmp/seam-propagation}/one-$label.log
