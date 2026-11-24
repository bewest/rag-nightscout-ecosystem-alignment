'use strict';
// Bounded, read-only authority transport check. No new benchmark workload.
const fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const SOCKET_ERROR_CLASSES=new Set(['Error','TransportError','TypeError']);
const SOCKET_ERROR_CODES=new Set(['ECONNREFUSED','ECONNRESET','EHOSTUNREACH','ENETUNREACH','ENOTFOUND','EAI_AGAIN','ETIMEDOUT','EPIPE']);
function transportError(error){
  const description=error?.description;
  const status=[description,error?.context?.status,description?.status].find(value=>Number.isInteger(value)&&value>=100&&value<=599);
  const code=[error?.code,description?.code,error?.context?.code].find(value=>SOCKET_ERROR_CODES.has(value));
  const errorClass=[error?.type,error?.name].find(value=>SOCKET_ERROR_CLASSES.has(value));
  return {errorClass:errorClass??'Other',status:status??null,code:code??null};
}
async function warmWitnesses(tenants,open,until,connectMs){
  const observations=[];
  for(let tenantIndex=0;tenantIndex<tenants.length;tenantIndex++){
    const started=Date.now();
    let attempts=0,refused403=0,firstError=null,engineOpened=false,connected=false;
    while(Date.now()<until){
      firstError=null;
      const timeout=Math.max(1,Math.min(connectMs,until-Date.now()));
      const socket=open(tenants[tenantIndex].host,timeout);
      attempts++;
      try{
        connected=await new Promise(resolve=>{
          const timer=setTimeout(()=>resolve(false),timeout);
          const finish=value=>{clearTimeout(timer);resolve(value);};
          socket.io?.once('open',()=>{engineOpened=true;});
          socket.once('connect_error',error=>{firstError=transportError(error);finish(false);});
          socket.once('connect',()=>finish(true));
        });
      }finally{socket.close();}
      if(connected)break;
      // A refusal before the tenant is warm (403/503 or a transport error) is a
      // warm-up signal: record it and retry until the configured warm deadline.
      if(firstError?.status===403)refused403++;
      await new Promise(resolve=>setTimeout(resolve,Math.max(0,Math.min(500*2**Math.min(attempts-1,4),5000,until-Date.now()))));
    }
    const row={tenantIndex,attempts,refused403,elapsedMs:Date.now()-started};
    // Never PASS on missing evidence: a socket that did not warm inside the
    // deadline is UNMEASURED with its last typed status; the run continues.
    observations.push(connected?{...row,verdict:'CONNECTED'}:{...row,verdict:'UNMEASURED',stage:'warmup',firstError,engineOpened});
  }
  return observations;
}
// Loopback (the workstation's port-forward), or the edge Service's IPv4 ClusterIP when the controller runs in the
// cluster (edge_access.py; NS_CAMPAIGN_ATTACH_SCOPE=pod is set only in the controller Pod).
function scope(base,env=process.env){
  if(/^(127\.0\.0\.1|localhost)$/.test(base.hostname))return true;
  return env.NS_CAMPAIGN_ATTACH_SCOPE==='pod'&&/^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/.test(base.hostname);
}
async function run(tenants,base,io,{connectMs=5000,observeMs=5000,warmupMs=0,step=()=>{}}={}){
  // Per-step timings as they happen (round 2, 2026-11-24): {step, tenantIndex, phase start|end, at, ms, outcome}.
  const timed=async(name,tenantIndex,fn,outcome=v=>'ok')=>{const t0=Date.now();step({step:name,tenantIndex,phase:'start',at:t0});
    try{const v=await fn();step({step:name,tenantIndex,phase:'end',at:Date.now(),ms:Date.now()-t0,outcome:outcome(v)});return v;}
    catch(e){step({step:name,tenantIndex,phase:'end',at:Date.now(),ms:Date.now()-t0,outcome:/^K8S_[A-Z_]+$/.test(e?.message)?e.message:(e?.code||'error')});throw e;}};
  if(tenants.length!==2||!scope(base))throw Error('K8S_ACCESS_SCOPE');
  const records=[],sockets=[],startedAt=Date.now();
  if(!Number.isSafeInteger(warmupMs)||warmupMs<0||!Number.isSafeInteger(startedAt+warmupMs))throw Error('K8S_SOCKET_PREWARM_BUDGET');
  const address=base.hostname==='localhost'?'127.0.0.1':base.hostname;
  const lookup=(host,opts,cb)=>opts?.all?cb(null,[{address,family:4}]):cb(null,address,4);
  const agent=new http.Agent({lookup});
  const open=(host,timeout)=>io('http://'+host+':'+base.port,{transports:['polling'],agent,reconnection:false,timeout});
  const get=(host,token,exchange=false)=>new Promise((resolve,reject)=>{
    const route=exchange?'/api/v2/authorization/request/'+encodeURIComponent(token):'/api/v1/entries/sgv.json?count=1&token='+encodeURIComponent(token);
    const req=http.get({hostname:base.hostname,port:base.port,path:route,headers:{Host:host},timeout:5000},res=>{
      let n=0;const chunks=[];res.on('data',c=>{n+=c.length;if(n>65536)req.destroy(Error('K8S_ACCESS_BODY_BOUND'));else chunks.push(c);});
      res.on('end',()=>{let value;try{value=JSON.parse(Buffer.concat(chunks));}catch{value=null;}
        resolve({status:res.statusCode,arrayBody:Array.isArray(value),error:typeof value?.error==='string'&&/^[A-Z_]{1,64}$/.test(value.error)?value.error:null,...(exchange?{jwt:value?.token}:{})});});
    });req.on('timeout',()=>req.destroy(Error('K8S_ACCESS_TIMEOUT')));req.on('error',reject);
  });
  try{
    const warmup=warmupMs?await timed('warmup',null,()=>warmWitnesses(tenants,open,startedAt+warmupMs,connectMs),v=>v.every(r=>r.verdict==='CONNECTED')?'connected':'unmeasured'):null;
    const deadline=Date.now()+45000;
    for(let i=0;i<2;i++){
      const exchanged=await timed('exchange',i,()=>get(tenants[i].host,tenants[i].token,true),v=>'status-'+v.status);
      if(exchanged.status!==200||typeof exchanged.jwt!=='string'||!exchanged.jwt)throw Error('K8S_ACCESS_EXCHANGE_UNMEASURED');
      records.push({case:'own-token-exchange',tenantIndex:i,status:200});
      const foreign=await timed('cross-token-host',i,()=>get(tenants[1-i].host,tenants[i].token),v=>'status-'+v.status);
      if(![401,403].includes(foreign.status)||foreign.arrayBody)throw Error('K8S_CROSS_TENANT_AUTHORITY');
      records.push({case:'cross-token-host',tenantIndex:i,...foreign});
      const invalid=await timed('invalid-token',i,()=>get(tenants[i].host,'synthetic-invalid-credential'),v=>'status-'+v.status);
      if(![401,403].includes(invalid.status)||invalid.arrayBody)throw Error('K8S_INVALID_CREDENTIAL_ACCEPTED');
      records.push({case:'invalid-token',tenantIndex:i,...invalid});
      // A swapped credential on the stock Socket.IO authorization path must
      // produce no dataUpdate during a finite observed polling connection.
      const connectStarted=Date.now();
      let frames=0,authorizeReply=false,engineOpened=false,firstError=null,disconnect=null;
      const socket=open(tenants[1-i].host,connectMs);sockets.push(socket);
      socket.io?.once('open',()=>{engineOpened=true;});
      socket.once('disconnect',reason=>{disconnect={at:Date.now(),serverClosed:reason==='io server disconnect'};});
      socket.on('dataUpdate',()=>frames++);
      const connected=await timed('socket-connect',i,()=>new Promise(resolve=>{
        const timer=setTimeout(()=>resolve(false),Math.max(0,Math.min(connectMs,deadline-Date.now())));
        socket.once('connect_error',error=>{firstError=transportError(error);clearTimeout(timer);resolve(false);});
        socket.once('connect',()=>{clearTimeout(timer);resolve(true);});
      }),v=>v?'connected':(firstError?'connect-error-'+(firstError.status??firstError.code??firstError.errorClass):'connect-timeout'));
      // A socket that cannot be observed is a signal, not an isolation result:
      // record it UNMEASURED and continue. Frames and accepted credentials still fail.
      const unmeasured=stage=>{
        records.push({case:'cross-token-socket',tenantIndex:i,verdict:'UNMEASURED',stage,engineOpened,firstError,elapsedMs:Date.now()-connectStarted});
        socket.close();
      };
      if(!connected){unmeasured('connect');continue;}
      if(Date.now()+observeMs>deadline){unmeasured('observation-budget');continue;}
      socket.emit('authorize',{client:'web',token:exchanged.jwt,history:1,status:true},()=>{authorizeReply=true;});
      const observationStarted=Date.now();
      await timed('socket-observe',i,()=>new Promise(resolve=>setTimeout(resolve,observeMs)),()=>frames?'frames-'+frames:'no-frames');
      if(frames)throw Error('K8S_FOREIGN_SOCKET_FRAME');
      if(disconnect && (!disconnect.serverClosed || disconnect.at<observationStarted)){unmeasured('disconnect');continue;}
      records.push({case:'cross-token-socket',tenantIndex:i,connected,authorizeReply,frames,
        observedMs:(disconnect?.at??Date.now())-observationStarted,terminal:disconnect?'server-closed':'observation-complete',
        connectElapsedMs:observationStarted-connectStarted});socket.close();
    }
    const unmeasuredCases=records.filter(r=>r.verdict==='UNMEASURED').length+(warmup||[]).filter(r=>r.verdict==='UNMEASURED').length;
    return {version:1,verdict:unmeasuredCases?'UNMEASURED':'PASS',crossTenantChecks:2,unmeasuredCases,records,startedAt,endedAt:Date.now(),
      ...(warmup?{warmup:{budgetMs:warmupMs,observations:warmup}}:{}),
      scope:'finite read refusal and no foreign frame; no network-policy enforcement claim',capacityAcceptance:'NOT_GRANTED'};
  }finally{for(const s of sockets)s.close();agent.destroy();}
}
function witnesses(tenants) {
  if (!Array.isArray(tenants) || tenants.length < 2 || tenants[0]?.id === tenants.at(-1)?.id)
    throw Error('K8S_ACCESS_SCOPE');
  return [tenants[0], tenants.at(-1)];
}

async function main() {
  const tenants = JSON.parse(fs.readFileSync(process.argv[2]));
  const selected = witnesses(tenants);
  // K8S_ACCESS_STEPS: append each step synchronously, so a kill at the run's bound keeps every completed step.
  const stepsFile = process.env.K8S_ACCESS_STEPS;
  const step = stepsFile ? row => fs.appendFileSync(stepsFile, JSON.stringify(row) + '\n') : () => {};
  const result = await run(selected, new URL(process.argv[3]),
    require(path.join(process.argv[4], 'node_modules/socket.io-client')).io,
    {warmupMs:process.argv[5]===undefined?0:Number(process.argv[5])*1000, step});
  console.log(JSON.stringify({ ...result, tenantRosterSize: tenants.length, witnessTenants: selected.map(row => row.id) }));
}
module.exports = { run, scope, witnesses };
if (require.main === module) main().catch(e => {
  if (e.socketEvidence) console.log(JSON.stringify({socketEvidence:e.socketEvidence}));
  console.error(/^K8S_[A-Z_]+$/.test(e.message) ? e.message : 'K8S_ACCESS_UNMEASURED');
  process.exitCode = 1;
});
