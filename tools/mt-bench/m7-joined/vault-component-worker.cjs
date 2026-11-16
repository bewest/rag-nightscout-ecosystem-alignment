'use strict';
// Single finite component case, actual six-purpose client plus root encryption.
const fs=require('node:fs'),path=require('node:path'),{AsyncLocalStorage}=require('node:async_hooks');
const task=new AsyncLocalStorage(),realFetch=globalThis.fetch;
const codes=new Set(['ECONNREFUSED','ECONNRESET','EPIPE','ETIMEDOUT','ENOTFOUND','EAI_AGAIN','UND_ERR_CONNECT_TIMEOUT','UND_ERR_HEADERS_TIMEOUT','UND_ERR_BODY_TIMEOUT','UND_ERR_SOCKET']);
const own=(o,k)=>{try{return o&&Object.getOwnPropertyDescriptor(o,k)?.value;}catch{return undefined;}};
// Transit has no fetch injection; observe its existing fetch without reading/copying bodies.
globalThis.fetch=async(...args)=>{
 const ctx=task.getStore();if(!ctx||ctx.phase!=='root-encrypt')return realFetch(...args);
 const started=performance.now(),signal=args[1]?.signal;ctx.root={started,signal,phase:'transport'};
 try{const response=await realFetch(...args);ctx.root.phase='response';
  if(Number.isInteger(response.status)&&response.status>=100&&response.status<=599)ctx.root.status=response.status;
  return response;
 }catch(e){const errno=[own(e,'code'),own(own(e,'cause'),'code')].find(x=>codes.has(x));if(errno)ctx.root.errno=errno;throw e;}
};
function rootDiagnostic(ctx,timeoutMs,code){
 const r=ctx.root;if(!r)return undefined;
 const timeout=r.signal?.aborted===true&&r.signal.reason?.name==='TimeoutError';
 return Object.freeze({operation:'encrypt',phase:r.phase,timeout,deadlineMs:timeoutMs,elapsedMs:Math.min(3600000,Math.max(0,Math.round(performance.now()-r.started))),
  failureClass:timeout?'own-timeout':code==='SECRETS_PROVIDER_REFUSED'||r.errno==='ECONNREFUSED'?'refused':r.errno==='ECONNRESET'||r.errno==='UND_ERR_SOCKET'?'reset':r.errno==='ENOTFOUND'||r.errno==='EAI_AGAIN'?'DNS':'other',
  ...(r.status===undefined?{}:{status:r.status}),...(r.errno?{errno:r.errno}:{})});
}
(async()=>{
 const c=JSON.parse(fs.readFileSync(0,'utf8'));
 if(c.runtimeReceiptPath)fs.writeFileSync(c.runtimeReceiptPath,JSON.stringify({version:process.version,pid:process.pid,heapLimit:require('node:v8').getHeapStatistics().heap_size_limit,memory:process.memoryUsage()})+'\n',{mode:0o600});
 const {createVaultKeys,diagnosticFor}=require(path.join(c.source,'lib/tenant-registry/vault-keys'));
 const rules=require(path.join(c.source,'lib/tenant-registry/rules'));
 const {createVaultTransit}=require(path.join(c.source,'lib/secrets/vault-transit'));
 const options={address:c.address,mount:'transit',getToken:async()=>c.token,timeoutMs:10000,allowInsecureLoopback:true};
 const goal=c.targetSets??10000;if(!Number.isSafeInteger(goal)||goal<1||goal>10000)throw Error('TARGET');
 const checkpointEvery=Math.min(100,Math.max(1,Math.floor(goal/4)));
 const keys=createVaultKeys(options);let next=1,done=0,failed=false,target=Math.min(6000,goal);
 const start=performance.now();
 const emit=x=>fs.writeSync(1,JSON.stringify({...x,at:x.at??new Date().toISOString(),elapsedMs:performance.now()-start})+'\n');
 function recordFirst(record){if(!c.firstFailurePath)return;let fd;try{fd=fs.openSync(c.firstFailurePath,'wx',0o600);fs.writeSync(fd,JSON.stringify(record)+'\n');fs.fsyncSync(fd);}catch(e){if(e.code!=='EEXIST')throw e;}finally{if(fd!==undefined)fs.closeSync(fd);}}
 async function tenant(i,ctx){
  const id='40000000-0000-4000-8000-'+i.toString(16).padStart(12,'0');
  for(const [purpose,type] of Object.entries(rules.PURPOSES)){ctx.purpose=purpose;await keys.ensure(rules.vaultKey(id,purpose),type);ctx.completedPurposes++;}
  ctx.phase='root-encrypt';delete ctx.purpose;
  const transit=createVaultTransit({...options,encryptionKey:rules.vaultKey(id,'data'),signingKey:rules.vaultKey(id,'signing'),signingVersion:1});
  await transit.encrypt(Buffer.from(JSON.stringify({tenant:id,id:'root',data:Buffer.alloc(48,97).toString('base64')})));
 }
 async function worker(){while(!failed){const i=next++;if(i>target)return;if(Date.now()>=c.stopWorkAtMs){failed=true;emit({status:'DEADLINE',completed:done});return;}
  const ctx={phase:'ensure',completedPurposes:0};try{await task.run(ctx,()=>tenant(i,ctx));done++;if(done%checkpointEvery===0)emit({status:'CHECKPOINT',completed:done});}
  catch(e){failed=true;const known=['TENANT_PROVISION_VAULT_UNAVAILABLE','TENANT_PROVISION_VAULT_REFUSED','TENANT_PROVISION_VAULT_KEY_MISMATCH','SECRETS_PROVIDER_UNAVAILABLE','SECRETS_PROVIDER_REFUSED','SECRETS_PROVIDER_RESPONSE'];
   const code=known.includes(e.code)?e.code:'OTHER',diagnostic=ctx.phase==='ensure'?diagnosticFor(e):rootDiagnostic(ctx,options.timeoutMs,code);
   const record={status:'REFUSED',completed:done,code,phase:ctx.phase,completedPurposes:ctx.completedPurposes,...(ctx.purpose?{purpose:ctx.purpose}:{}),...(diagnostic?{diagnostic}:{}),at:new Date().toISOString(),elapsedMs:performance.now()-start};
   recordFirst(record);emit(record);
  }
 }}
 await Promise.all(Array.from({length:4},worker));
 if(!failed&&done===6000&&goal>6000&&c.allow10000){const remaining=c.stopWorkAtMs-Date.now(),predicted=(performance.now()-start)*(goal-6000)/6000;const proceed=remaining>predicted*1.25+120000;emit({status:'PREFIX_6000',completed:done,continue10000:proceed,remainingMs:remaining,predictedAdditionalMs:predicted});if(proceed){target=goal;next=6001;await Promise.all(Array.from({length:4},worker));}}
 emit({status:done===target?'COMPLETE':'PARTIAL',completed:done,target});process.exitCode=done===target?0:1;
})().catch(()=>{fs.writeSync(1,JSON.stringify({status:'FAILED',code:'LOCAL_DISCRIMINATOR_FAILED'})+'\n');process.exitCode=1;});
