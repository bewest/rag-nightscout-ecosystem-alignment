'use strict';
const assert=require('node:assert/strict'),root=process.env.M7_PRODUCER_CORE;
const scope=require(root+'/lib/storage/tenant-scope'),f=require(root+'/tests/fixtures/tenant-notifications')();
const producer=require(root+'/lib/tenant-notifications/producer'),notifier=require(root+'/lib/tenant-notifications/component');
let at=Date.UTC(2026,10,12,12),effects=0;const mode=scope.getTenancyMode();scope.setTenancyMode('multi');
const notice={kind:'notify',level:2,title:'Synthetic',message:'Synthetic stale guard',plugin:{name:'synthetic'},group:'default'};
let source={identity:'config',eligible:true,contentDigest:'a'.repeat(64),runtimeId:'first',outputRevision:1,inputCheckpoint:1,result:{now:at,requested:[notice]}};
const p=producer({store:f.store,reader:{read:async()=>[]},current:()=>source,currentConfig:async()=>({tenant:f.A,identity:'config'}),isCurrent:async()=>true,consumer:'realtime-test',now:()=>at,maxRows:10,maxBytes:65536,maxPayloadBytes:10000});
const n=notifier({store:f.store,adapter:{id:'realtime-test',send(_req,cb){effects++;cb(null,{accepted:true});}},selectCycle:p.select,isCurrent:async()=>true,allows:async()=>true,mayAttempt:async({notification})=>notification.clear===true||source.eligible===true,requireIntentOrigin:true,now:()=>at,normalPolicy:'realtime-cycle',maxRows:10,maxPayloadBytes:10000,maxInflight:1,attemptTimeoutMs:1000,retryDelayMs:1});
(async()=>{try{
 await p.select(f.A);const id=f.snapshot().requests[0].request_id;source={...source,eligible:false};at+=1000;
 await p.select(f.A);await n.retry(f.A);assert.equal(effects,0,'UNAVAILABLE_MODEL_MUST_NOT_DISPATCH_PENDING_NORMAL');
 source={...source,eligible:true,runtimeId:'new-owner'};at+=3438;await p.select(f.A);await n.retry(f.A);
 assert.equal(effects,1);assert.equal(f.snapshot().requests.length,1);assert.equal(f.snapshot().requests[0].request_id,id);
 console.log(JSON.stringify({scope:'actual producer/component plus recording SQL store; not native PG',pendingNormalUnavailableDispatches:0,recoveredDispatches:1,sameDurableRequest:true}));
 }finally{await n.close();p.close();scope.setTenancyMode(mode);}})().catch(e=>{console.error(e.stack);process.exitCode=1;});
