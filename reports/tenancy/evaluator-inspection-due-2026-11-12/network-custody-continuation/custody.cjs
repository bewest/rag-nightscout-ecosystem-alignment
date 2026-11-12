'use strict';
// Test-owned custody guard. No Docker, startup or resource calls are implicit.
const assert=require('node:assert/strict');
function canonical(value){
 if(Array.isArray(value))return value.map(canonical).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
 if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])]));
 return value;
}
function normalized(rows,expected){
 assert.equal(rows.length,expected.count,'CUSTODY_CONTAINER_COUNT');const ids=new Set();
 for(const row of rows){assert(/^[0-9a-f]{64}$/.test(row.id),'CUSTODY_FULL_CONTAINER_ID');assert(!ids.has(row.id),'CUSTODY_DUPLICATE_CONTAINER_ID');ids.add(row.id);assert.equal(row.running,false,'CUSTODY_CONTAINER_MUST_STAY_STOPPED');assert.equal(row.status,'exited','CUSTODY_CONTAINER_MUST_STAY_EXITED');assert.equal(row.labels['com.docker.compose.project'],expected.project,'CUSTODY_PROJECT');assert.equal(row.labels['com.docker.compose.project.working_dir'],expected.workingDir,'CUSTODY_WORKDIR');}
 // Network dictionaries are keyed by network name; aliases/DNS lists and mount
 // descriptors are order-insensitive multisets. Duplicates remain significant.
 return canonical(rows);
}
function verify(record,expected){
 const before=normalized(record.beforeContainers,expected),after=normalized(record.afterContainers,expected);
 assert.deepEqual(after,before,'CUSTODY_SEMANTIC_MISMATCH');return{verified:true,containers:before.length,comparison:'all keys; order-insensitive nested arrays/multisets'};
}
async function guarded(record,expected,startup){
 let result;try{result=verify(record,expected);}
 catch(error){error.custodyStartup='NOT_RUN';error.nextAction='NOT_RUN';throw error;}
 return{...result,startup:await startup()};
}
if(require.main===module){const fs=require('node:fs');const [file,project,workingDir,count,...extra]=process.argv.slice(2);assert(!extra.length&&file&&project&&workingDir&&Number.isInteger(Number(count)),'CUSTODY_ARGUMENTS');console.log(JSON.stringify(verify(JSON.parse(fs.readFileSync(file)),{project,workingDir,count:Number(count)})));}
module.exports={canonical,verify,guarded};
