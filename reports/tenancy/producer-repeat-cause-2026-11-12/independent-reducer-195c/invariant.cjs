'use strict';
const assert=require('node:assert/strict');
const result=require('./result.json'),rows=result.cases[process.argv[2]];
assert(rows);assert.equal(rows[0].effects[0].origin,rows[2].effects[0].origin,'UNCHANGED_OUTPUT_MUST_WAIT_FOR_ORIGINAL_REPEAT_DEADLINE');
console.log('NO_EARLY_REPEAT_INVARIANT_GREEN '+process.argv[2]);
