"use strict";
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
module.exports=({directory,result,control})=>{
 const rows=JSON.parse(fs.readFileSync(path.join(directory,'actual-socket-epoch.json'))),find=kind=>rows.find(x=>x.kind===kind),clean=rows.at(-1);
 assert.equal(clean.kind,'cleanup');assert.deepEqual(clean.errors,[]);assert.equal(clean.operatorRestored,true);
 const main=find('main-reauthorization'),alarm=find('alarm-reauthorization'),operator=find('operator-tightening');
 const holds=rows.filter(x=>x.kind==='actual-authority-held'),released=rows.filter(x=>x.kind==='actual-authority-released');assert(holds.every(x=>x.read===true));assert.equal(holds.length,released.length);
 if(control){assert.equal(result.status,1);assert(/^ERR_ASSERTION$/m.test(fs.readFileSync(path.join(directory,'native.log'),'utf8')));
  if(control.oracle==='socket-epoch'){assert(holds.some(x=>x.namespace==='/'));assert(main&&main.deniedRead===false&&main.protectedEvents.length>0,'EPOCH_CONTROL_REQUIRES_ACTUAL_STALE_FRAME');}
  else{assert.equal(control.oracle,'config-epoch');assert.equal(holds.length,3);assert(operator&&operator.protectedEvents.length>0,'CONFIG_CONTROL_REQUIRES_ACTUAL_STALE_FRAME');}
  return;}
 assert.equal(result.status,0,'JOINED_EPOCH_CLI_STATUS');assert.equal(holds.length,3);assert.equal(holds.filter(x=>x.namespace==='/').length,2);assert.equal(holds.filter(x=>x.namespace==='/alarm').length,1);assert.equal(main.deniedRead,false);for(const row of [main,alarm,operator])assert.deepEqual(row.protectedEvents,[]);assert.deepEqual(alarm.handoff,{value:{accepted:true,receipt:null,clearedRequestIds:[]}});
};
