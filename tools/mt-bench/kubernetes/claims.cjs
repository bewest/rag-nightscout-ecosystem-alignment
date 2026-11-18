'use strict';
// Re-run the existing durable clinical/frame oracle over captured raw SQL rows.
const fs=require('node:fs'),o=require(process.argv[2]);
const fail=code=>{throw Error(code);};
function assess(v){
  const ids=v.tenants.map(t=>t.id),rows=v.probe?.completedOutput?.witnesses;
  if(!Array.isArray(rows)||!rows.length)fail('K8S_CLINICAL_UNMEASURED');
  const counts=new Map(ids.map((id,i)=>[id,Math.floor(v.clients/ids.length)+(i<v.clients%ids.length?1:0)]));
  const byId=new Map(),results=[];
  for(const witness of rows){
    if(!counts.has(witness.tenant)||!witness.rawRow||!Array.isArray(witness.clientObservations))fail('K8S_CLINICAL_UNMEASURED');
    const result=o.assess(witness.rawRow,witness,witness.clientObservations,counts.get(witness.tenant),v.completion);
    if(!result.ready)fail(result.code);
    const previous=byId.get(result.storedId);if(previous&&previous!==witness.tenant)fail('K8S_STORED_ID_TENANT_COLLISION');
    byId.set(result.storedId,witness.tenant);results.push(result);
  }
  const frames=v.probe.kubernetesFrames;
  if(!frames||frames.overflow!==false||!Array.isArray(frames.rows))fail('K8S_ISOLATION_UNMEASURED');
  for(const frame of frames.rows){
    if(!counts.has(frame.tenant)||!Array.isArray(frame.ids))fail('K8S_ISOLATION_UNMEASURED');
    if(frame.ids.some(id=>byId.has(id)&&byId.get(id)!==frame.tenant))fail('K8S_CROSS_TENANT_FRAME');
  }
  return {verdict:'PASS',witnesses:results.length,witnessTenants:new Set(results.map(r=>r.tenant)).size,
    clientFrameCoverage:{plannedStockViewers:v.clients,witnessesWithViewers:results.filter(r=>r.clients>0).length,witnessesWithoutViewers:results.filter(r=>r.clients===0).length,scope:'client frames required only for the declared viewers; unviewed tenants retain stored and selected clinical checks'},
    clinicalScope:'existing selected BG-now bucket mean/last plus durable typed output and exact stored row/client frame',
    isolationScope:'no other witnessed synthetic tenant stored ID in retained stock-client frames; access refusal separate',
    allClinicalProperties:'UNMEASURED',capacityAcceptance:'NOT_GRANTED'};
}
module.exports={assess};
if(require.main===module){try{console.log(JSON.stringify(assess(JSON.parse(fs.readFileSync(0,'utf8')))));}
catch(e){console.error(/^(M7|K8S)_[A-Z_]+$/.test(e.message)?e.message:'K8S_SEMANTIC_ERROR');process.exitCode=1;}}
