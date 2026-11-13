'use strict';
// TEST ONLY. Exact archived common helper; emits constructed envelopes, not CLI evidence.
const path=require('node:path'),crypto=require('node:crypto');
const root=process.argv[2];if(!root||!path.isAbsolute(root))throw Error('FIXED_ARCHIVE_REQUIRED');
const B=require(path.join(root,'connection-budget')),C=require(path.join(root,'control-recovery'));
const source={coreCommit:'d0036890d0623ae79f14bfa71e7226c0fa122a29',deployCommit:'d831c372b39ac19aff4271ecc5e2b1639d176448'};
const principal={role:'synthetic_operator',roleOid:'31',database:'synthetic',databaseOid:'16384'};
const plan={version:2,kind:'controlled-connection-budget-plan',source,workerDatabase:{database:'synthetic',databaseOid:'16384'},lifecycleOperator:{version:2},
 resource:{systemIdentifier:'synthetic',postmasterStartedAt:'synthetic-epoch',pgResourceId:'synthetic-pg',serverMaximum:20,reserved:{superuser:3,other:0},allowances:{controlRecovery:2,observers:2}},
 slots:[{processInstanceId:'api',declaredMaximum:4,maximumOutstandingGenerations:2,capabilities:{'synthetic-capability':{kind:'pool',poolMax:4,maxInstances:1}}}],
 controlRecovery:{version:1,classes:Object.fromEntries(C.CLASSES.map(c=>[c,{principal:{...principal,...(c==='restore-commissioner'?{role:'synthetic_ddl',roleOid:'32'}:{})}}]))}};
plan.sha256=B.hash(plan);
const expected={kind:'m7-tagged-admission-observation-v1',source,imageId:'sha256:'+'1'.repeat(64),project:'synthetic-project',workingDirectory:'/tmp/synthetic',planSha256:plan.sha256};
const original={cid:'2'.repeat(64),startedAt:'synthetic-birth',project:expected.project,workingDirectory:expected.workingDirectory,service:'api',imageId:expected.imageId,source};
const worker={incarnation:'a'.repeat(32),nonce:'b'.repeat(32),tags:['nscb:'+'a'.repeat(32)+':'+crypto.createHash('sha256').update('synthetic-capability').digest('hex').slice(0,16)],container:original,state:'ISSUED',retired:false};
function fixture(name){const ledger=C.ledger(plan);ledger.slots.api.push(structuredClone(worker));
 const add=(c,state,stopped)=>{const r=C.allocate(plan,ledger,{class:c,intentSha256:'f'.repeat(64)});if(state!=='ISSUED'){C.bound(plan,ledger,r,{...original,cid:r.incarnation.repeat(2),service:c},Object.fromEntries(['source','project','workingDirectory','imageId'].map(k=>[k,expected[k]])));}
  if(state==='UNKNOWN'){C.uncertain(plan,ledger,r);if(stopped)C.stopped(plan,ledger,r,{container:r.container,resourceEpoch:ledger.resourceEpoch,noFutureDispatch:true});}return r;};
 if(name==='pair'){add('lifecycle-operator','UNKNOWN',true);add('realtime-recovery','BOUND');}
 else if(name==='two-unknown'){add('lifecycle-operator','UNKNOWN',true);add('realtime-recovery','UNKNOWN',true);}
 else if(name==='setup-terminal'){add('restore-commissioner','UNKNOWN',true);}
 else add(name,'ISSUED');
 C.validate(plan,ledger);
 const tags=C.known(plan,ledger).map(applicationName=>({applicationName,count:0}));const resource={systemIdentifier:'synthetic',postmasterStartedAt:'synthetic-epoch',pgResourceId:'synthetic-pg',serverMaximum:20,superuserReserved:3,otherReserved:0,unmanagedClients:0};
 const controlProcesses=ledger.controlLeases.filter(r=>r.state!=='CLOSED').map(r=>({processInstanceId:r.class,incarnation:r.incarnation,container:r.container?{...r.container,running:false,operatorIncarnation:r.incarnation}:null,inspection:r.container?'STOPPED':'UNBOUND',...(r.container?{inspectedCid:r.container.cid}:{})}));
 return {expected,plan,ledger,processes:[{processInstanceId:'api',incarnation:worker.incarnation,container:{...original,running:true},inspection:'RUNNING',inspectedCid:original.cid}],controlProcesses,census:{resource,tags,occupancy:C.occupancy(plan,ledger,tags)}};}
let n=1;const saved=crypto.randomBytes;crypto.randomBytes=size=>Buffer.alloc(size,n++);try{process.stdout.write(JSON.stringify(Object.fromEntries([...C.CLASSES,'pair','two-unknown','setup-terminal'].map(name=>[name,fixture(name)]))));}finally{crypto.randomBytes=saved;}
