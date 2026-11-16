'use strict';
// Finite host-probe event writes. No request, listener, polling or timer here.
const fs=require('node:fs'),path=require('node:path');
function create({directory,ids,maxRows=32,io=fs}){
 if(!Array.isArray(ids)||ids.length!==2||new Set(ids).size!==2||ids.some(id=>typeof id!=='string'||!/^[0-9a-f-]{36}$/.test(id)))throw Error('M7_CLINICAL_TIMELINE_IDS');
 const targets=new Set(ids);let rows=0,pending=0,written=0,dropped=0,failed=null;
 const status=()=>({rows,pending,written,dropped,failed,qualification:pending||dropped||failed?'UNMEASURED':'COMPLETE'});
 return Object.freeze({status,record(phase,tenant,value){
  if(!targets.has(tenant))return;
  if(!['writer-ack','first-matching-frame'].includes(phase))throw Error('M7_CLINICAL_TIMELINE_PHASE');
  if(rows>=maxRows){dropped++;return;}
  const number=++rows,record={phase,tenant,at:Date.now(),monoMs:performance.now(),date:value.date,sent:value.sent,...(phase==='writer-ack'?{acked:value.acked}:{received:value.received})};
  const text=JSON.stringify(record)+'\n';pending++;
  try{io.writeFile(path.join(directory,'clinical-client-'+number+'.json'),text,{flag:'wx',mode:0o600},error=>{pending--;if(error)failed=/^[A-Z0-9_]{1,64}$/.test(error.code||'')?error.code:'WRITE_REFUSED';else written++;});}catch(error){pending--;failed='WRITE_REFUSED';}
 },seal(){io.writeFileSync(path.join(directory,'clinical-client-status.json'),JSON.stringify(status())+'\n',{flag:'wx',mode:0o600});return status();}});
}
module.exports={create};
