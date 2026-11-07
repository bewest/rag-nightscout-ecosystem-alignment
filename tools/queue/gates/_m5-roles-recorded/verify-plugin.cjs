"use strict";
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
module.exports=({directory,result,control})=>{
 const row=JSON.parse(fs.readFileSync(path.join(directory,'actual-plugin-ack.json')));assert.deepEqual(row.cleanupErrors,[]);
 assert(row.physical.some(x=>x.doc._id===row.packet.data._id),'PLUGIN_CANONICAL_STORED_TREATMENT');assert.deepEqual(row.beforeOwner,[]);
 assert.deepEqual(row.windowBefore.map(x=>x.level).sort(),[1,2]);for(const x of row.windowBefore){assert.equal(x.group,'default');assert.equal(x.silenceTime,600000);assert(x.lastAckTime+x.silenceTime>row.ackStartedAt);}
 if(control){assert.equal(result.status,1);assert.equal(control.oracle,'plugin-owner-write');assert(!require('node:util').isDeepStrictEqual(row.immediately,row.beforeOwner),'PLUGIN_CONTROL_MUST_EXHIBIT_PHYSICAL_OWNER_WRITE');assert(/^ERR_ASSERTION$/m.test(fs.readFileSync(path.join(directory,'native.log'),'utf8')));return;}
 assert.equal(result.status,0,'JOINED_PLUGIN_CLI_STATUS');assert.equal(row.pluginAckIgnored,true);assert.equal(row.originalAbsoluteExpiryPreserved,true);assert.deepEqual(row.immediately,row.beforeOwner);assert.deepEqual(row.afterOwner,row.beforeOwner);
 const after=row.producerAfter[0].producer.alarms.filter(x=>x.group==='default'&&[1,2].includes(x.level));assert.deepEqual(after,row.windowBefore);
};
