#!/usr/bin/env bash
SP=${OUT:-/tmp/seam-propagation}
R=/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-prop-rebase

cd $R
# H1: the require dev dropped from modify.js, as git auto-merged it
sed -i "s#^const assertNoQueryJavascript = require('../../../storage/assert-no-query-javascript');#// H1#" lib/api3/storage/mongoCollection/modify.js
git diff --stat > $SP/h1.diff; $(dirname "$0")/suite.sh crm-prop-rebase hazard-h1; git checkout -- lib/api3/storage/mongoCollection/modify.js
# H2: activity create pushes a driver-shaped deleteMany op into the seam's op list, as auto-merged
sed -i "s#^    var stale = idForms.staleStringForms(submitted);#    var stale = []; idForms.withStaleStringsRemoved(bulkOps, submitted);#" lib/server/activity.js
git diff --stat > $SP/h2.diff; $(dirname "$0")/suite.sh crm-prop-rebase hazard-h2; git checkout -- lib/server/activity.js
# H3: devicestatus remove with the soft-delete-visible filter, as auto-merged
sed -i "s#var stat = await store().deleteMany(fromMongo(stored_query_for(opts)));#var stat = await store().deleteMany(fromMongo(query_for(opts)));#" lib/server/devicestatus.js
git diff --stat > $SP/h3.diff; $(dirname "$0")/suite.sh crm-prop-rebase hazard-h3; git checkout -- lib/server/devicestatus.js
git status --short --untracked-files=no > $SP/h-final-status.txt
echo BATCH5-DONE
