'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
module.exports=({directory,result})=>{
 const rows=JSON.parse(fs.readFileSync(path.join(directory,'joined-recovery-observations.json')));
 assert.equal(result.status,0,'JOINED_RECOVERY_CLI_STATUS');
 for(const transport of ['polling','websocket']){const row=rows.find(x=>x.transport===transport);assert(row?.admitted===true&&row.delta===false&&Array.isArray(row.sgvs),'JOINED_INITIAL_RAW_FRAME');}
 assert(rows.some(x=>x.quietRemoval&&x.clockUnchanged&&x.fullAbsence),'JOINED_ABSENCE_PHYSICAL');assert(rows.some(x=>x.tightened&&x.noProtectedDelivery),'JOINED_CURRENT_AUTHORITY_RAW');assert.deepEqual(rows.at(-1).cleanupErrors,[]);
 const denied=JSON.parse(fs.readFileSync(path.join(directory,'realtime-reader-denials.json')));assert.deepEqual(denied.map(x=>x.logical),['entries','treatments','devicestatus','profile','food','activity']);assert(denied.every(x=>x.refusal==='42501'),'JOINED_RESTRICTED_READER_PHYSICAL');
};
