'use strict';
// Preload only in a disposable test process, before contracts are frozen.
const path=require('node:path');
require(path.resolve(process.env.M7_CORE,'lib/server/internal-api/contracts/evaluator-inspection.json')).version=1;
