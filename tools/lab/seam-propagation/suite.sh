#!/usr/bin/env bash
# suite.sh <worktree-name> <label>  -- runs the tree's own `npm test` on node 22.23.2 vs prop-mongo (27152)
set -u
W=/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work
OUT=${OUT:-/tmp/seam-propagation}/suite; mkdir -p $OUT
export N_PREFIX=$HOME/n
d=$W/$1; label=$2; v=${NODEV:-22.23.2}; port=27152; db=prop_${label//-/_}_test
log=$OUT/$label.log
cd "$d" || exit 9
ver=$(n exec $v node -e "const{MongoClient}=require('./node_modules/mongodb');MongoClient.connect('mongodb://127.0.0.1:$port/$db',{serverSelectionTimeoutMS:3000}).then(async c=>{const v=await c.db().command({buildInfo:1});await c.db().dropDatabase();console.log(v.version);await c.close()}).catch(e=>{console.error(e);process.exit(1)})")
sed "s#^CUSTOMCONNSTR_mongo=.*#CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:$port/$db#" tests/ci.test.env > my.test.env
{
  echo "label=$label tree=$(git rev-parse HEAD) treeid=$(git rev-parse HEAD^{tree}) dirty=$(git status --porcelain --untracked-files=no | wc -l)"
  echo "node=$(n exec $v node --version) mongo_read=$ver driver=$(n exec $v node -p "require('./node_modules/mongodb/package.json').version") db=$db start=$(date -u +%FT%TZ)"
} > $log
t0=$(date +%s)
NODE_ENV=test n exec $v npm test >> $log 2>&1
rc=$?
echo "exit=$rc end=$(date -u +%FT%TZ) elapsed_s=$(( $(date +%s) - t0 ))" >> $log
rm -f my.test.env
grep -E '^ +[0-9]+ (passing|failing|pending)' $log; tail -1 $log
