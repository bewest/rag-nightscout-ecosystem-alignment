'use strict';
// Run source-only AFTER the existing profile generator has admitted the exact
// clean source and overlay. This exports the real operation-to-service join.
const path=require('node:path'),fs=require('node:fs'),crypto=require('node:crypto');
function derive(input){
 const report=require('../native-admission/profile.cjs').generate(input),base=path.join(input.sourceRoot,'deploy/multitenant'),before={...process.env};
 try{
  Object.assign(process.env,report.selectedEnvironment);
  const docs=require(path.join(base,'connection-budget-profile')).sourceDocuments();
  const slots=report.descriptors.map(x=>x.processInstanceId),operations=Object.entries(docs.operations).map(([service,operation])=>({service,participantId:operation.participantId,roles:report.descriptors.find(x=>x.processInstanceId===service)?.roles}));
  if(slots.length!==11||operations.length!==7||new Set(operations.map(x=>x.service)).size!==7||new Set(operations.map(x=>x.participantId)).size!==7||operations.some(x=>!slots.includes(x.service)||!Array.isArray(x.roles)))throw Error('NATIVE_CLINICAL_OPERATION_ROSTER');
  const expected=new Set(operations.map(x=>x.participantId));
  for(const operation of Object.values(docs.operations))if(operation.participants.length!==7||operation.participants.some(x=>!expected.has(x.id)))throw Error('NATIVE_CLINICAL_OPERATION_ROSTER');
  const state=path.join(path.dirname(input.sourceRoot),'state'),F=require(path.join(base,'connection-budget-files')),config=F.read(path.join(state,'connection-budget/controller-config.json'));
  if(JSON.stringify(config.source)!==JSON.stringify(report.source)||config.workingDirectory!==base)throw Error('NATIVE_CLINICAL_PREPARED_SOURCE');
  const yaml=require('js-yaml'),definitions={};
  for(const file of config.composeFiles){if(file!==path.join(base,'compose.yaml')&&!(path.dirname(file)===state&&/^compose[.a-z-]+[.]yaml$/.test(path.basename(file))))throw Error('NATIVE_CLINICAL_COMPOSE_PATH');if(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==config.fileDigests[file])throw Error('NATIVE_CLINICAL_COMPOSE_CHANGED');for(const[name,value]of Object.entries(yaml.load(fs.readFileSync(file,'utf8')).services||{}))definitions[name]={...definitions[name],...value};}
  function health(service,seen=new Set()){if(seen.has(service))throw Error('NATIVE_CLINICAL_HEALTH_CYCLE');seen.add(service);const row=definitions[service];if(!row)throw Error('NATIVE_CLINICAL_HEALTH_SOURCE');return row.healthcheck?.test||row.extends&&health(row.extends.service,seen)||null;}
  const healthTests=Object.fromEntries(slots.map(slot=>[slot,health(slot)]));for(const[slot,test]of Object.entries(healthTests))if(slot!=='feed-reader'&&(!Array.isArray(test)||test[0]!=='CMD'))throw Error('NATIVE_CLINICAL_HEALTH_CONTRACT');
  const realtimeWorkers=Object.fromEntries(operations.filter(x=>x.roles.includes('realtime')).map(x=>[docs.environments[x.service].REALTIME_WORKER_ID,x.service]));if(Object.keys(realtimeWorkers).length!==2)throw Error('NATIVE_CLINICAL_REALTIME_JOIN');
  const cold=require(path.join(input.sourceRoot,'lib/server/serve/cold-start-admission')).create({activeLimit:1,pendingLimit:9,minDelayMs:25,maxDelayMs:75}).health();
  const rpc=JSON.parse(fs.readFileSync(path.join(input.sourceRoot,'lib/server/internal-api/contracts/evaluator-inspection.json'),'utf8')),selectors=rpc.operations.inspectEvaluator.request.properties.diagnostics?.enum||[];const diagnostics={clinicalResults:selectors.includes('clinical-result-v1')?'clinical-result-v1':null,changeFeed:selectors.includes('change-feed-v1')?'change-feed-v1':null};
  return {diagnostics,realtimeWorkers,coldObserved:cold.observed?{version:cold.observed.version,fields:Object.keys(cold.observed)}:null,feedHeartbeatTimeoutMs:docs.configs.evaluator.changeFeed?.heartbeatTimeoutMs??null,healthTests,adminPort:Number(docs.admin.environment.ADMIN_PORT),kind:'native-clinical-source-topology',source:report.source,slots,operations,tenantIds:require(path.join(base,'config')).tenantIds(),cold:report.profile.slots.map(x=>({service:x.processInstanceId,...x.cold})),health:{feedReader:'SOURCE_LIVENESS_AND_DOWNSTREAM_DELIVERY_ONLY',socketEdge:'SOURCE_SHIPPED_1343_HEALTHZ',others:'SOURCE_SHIPPED_CMD_HEALTHCHECK'},authorization:'MODEL_ONLY_NOT_LAUNCH_AUTHORIZATION'};
 }finally{for(const k of Object.keys(process.env))if(!Object.hasOwn(before,k))delete process.env[k];Object.assign(process.env,before);}
}
module.exports={derive};

if(require.main===module){try{const [file,out]=process.argv.slice(2);if(!path.isAbsolute(file)||!path.isAbsolute(out))throw Error();const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);let raw;try{const st=fs.fstatSync(fd);if(!st.isFile()||st.mode&0o077||st.size>65536)throw Error();raw=fs.readFileSync(fd);}finally{fs.closeSync(fd);}const result=derive(JSON.parse(raw));fs.writeFileSync(out,JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});process.stdout.write('SOURCE_TOPOLOGY_ONLY_NOT_LAUNCH_AUTHORIZATION\n');}catch{process.stderr.write('NATIVE_CLINICAL_SOURCE_TOPOLOGY_REFUSED\n');process.exitCode=1;}}
