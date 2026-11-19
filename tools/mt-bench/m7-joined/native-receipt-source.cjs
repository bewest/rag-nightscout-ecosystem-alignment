'use strict';
// Run inside the already selected application image. Read configuration and call
// its shipping factories only; never open a database, mutate state or inspect rows.
const fs=require('node:fs'),path=require('node:path'),{createHash}=require('node:crypto');
const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
const hash=x=>createHash('sha256').update(canonical(x)).digest('hex');
const fail=()=>{throw Error('M7_COMPLETION_RECEIPT_SOURCE');};
function capture(root,{evaluator:e,realtime:r,operation,checkpoints}){
 if(!e?.pgstream?.generation&&!e?.pgstream?.recovery)return null;
 const namespace=e.postgres?.namespaces?.checkpoint,consumer=e.consumer;
 if(!operation||operation.intakeProfile!==undefined||!Array.isArray(checkpoints))fail();
 const selection=operation.nativeSelection===undefined?null:require(path.join(root,'lib/tenant-lifecycle/native-selection')).create(operation.nativeSelection);
 const contractDigest=selection?.contractDigest||require(path.join(root,'lib/pgstream/checkpoint')).create({typed:true,connection:{},namespace,consumer,maxBytes:1}).digest;
 const plans=checkpoints.filter(row=>row.namespace===namespace&&row.consumer===consumer+'-completed');
 if(plans.length!==1||plans[0].digest!==contractDigest)fail();
 if(selection){const b=selection.binding;if(b.namespace!==namespace||b.consumer!==consumer||b.lifecycleNamespace!==e.trustedWorker?.activity||b.lifecycleNamespace!==operation.namespace||b.generation!==e.pgstream.generation||b.source.slot!==e.pgstream.slot)fail();}
 return {kind:'native-receipt-contract-v1',contractDigest,evaluatorConfigSha256:hash(e),realtimeConfigSha256:hash(r),selection:selection?{binding:selection.binding,selectionDigest:selection.selectionDigest}:null};
}
function captureFiles(root,state){const read=file=>JSON.parse(fs.readFileSync(path.join(state,file))),evaluator=read('evaluator/config.json'),realtime=read('realtime/config.json');if(!evaluator?.pgstream?.generation&&!evaluator?.pgstream?.recovery)return null;return capture(root,{evaluator,realtime,operation:read('evaluator/operation.json'),checkpoints:read('admin/config.json').provisioning.checkpoints});}
module.exports={capture,captureFiles};
