'use strict';
// Bounded functional diagnostic only. It does not execute a capacity window.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const fail=code=>Object.assign(new Error(code),{code});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function run({directory,seconds,ioFactory,restart,deadlinePollMs=50,maxWarmProbes=512}){
  if(!Number.isSafeInteger(seconds)||seconds<1||seconds>180)throw fail('M7_DIAGNOSTIC_LIMIT_INVALID');
  if(!Number.isInteger(maxWarmProbes)||maxWarmProbes<1||maxWarmProbes>512)throw fail('M7_DIAGNOSTIC_WARM_PROBE_LIMIT_INVALID');
  const d=directory,m=JSON.parse(fs.readFileSync(path.join(d,'owner.json'))),tenants=JSON.parse(fs.readFileSync(path.join(d,'tenants.private.json')));
  if(m.profile!=='fresh-image-diagnostic'||tenants.length!==m.tenants||tenants.length<1||tenants.length>10||m.replicas>2)throw fail('M7_DIAGNOSTIC_PROFILE_REQUIRED');
  const out=path.join(d,'load'),marker=fs.readFileSync(path.join(out,'runid'),'utf8').trim();
  const deadline=Date.now()+seconds*1000,sockets=[],agents=[],checks={},metrics={},requests=new Set();let timer,criterionHttpRequests=0,physicalHttpRequests=0,warmProbeHttpRequests=0,stage='exchange-and-prime',terminalCode=null;
  const httpTrail={version:2,requests:[]},trailFile=path.join(out,'diagnostic-http.json');
  const safeCode=value=>typeof value==='string'&&/^[A-Z][A-Z0-9_]{0,63}$/.test(value)?value:null;
  const trailByteLimit=262144,trailRecordLimit=4*tenants.length+maxWarmProbes;
  const persistTrail=()=>{const bytes=JSON.stringify(httpTrail,null,2);if(Buffer.byteLength(bytes)>trailByteLimit)throw fail('M7_DIAGNOSTIC_TRAIL_BYTE_BOUND');fs.writeFileSync(trailFile,bytes,{mode:0o600});};
  const accounting=()=>({httpAccountingVersion:2,dataHttpRequests:criterionHttpRequests,criterionHttpRequests,physicalHttpRequests,warmProbeHttpRequests,trailRecords:httpTrail.requests.length,trailBytes:fs.statSync(trailFile).size});
  persistTrail();
  const io=ioFactory||require('socket.io-client').io;
  const restartFn=restart||require('./restart.cjs').restart;
  const lookup=(hostname,options,callback)=>options&&options.all?callback(null,[{address:'127.0.0.1',family:4}]):callback(null,'127.0.0.1',4);
  let shuttingDown=false;
  const agent=new http.Agent({keepAlive:true,lookup}),addRequest=agent.addRequest.bind(agent);
  // Socket.IO may enqueue its final polling close request after close() returns.
  // Agent.destroy() alone allows future requests to create fresh owned sockets.
  agent.addRequest=(request,options)=>{if(shuttingDown){queueMicrotask(()=>request.destroy(fail('M7_DIAGNOSTIC_STOPPED')));return;}return addRequest(request,options);};
  agents.push(agent);
  const awaitUntil=async(check,code)=>{while(Date.now()<deadline){if(check())return;await sleep(deadlinePollMs);}throw fail(code);};
  function request(tenant,route,body,context){
    if(!context||!Number.isInteger(context.tenantIndex)||context.tenantIndex<0||context.tenantIndex>=tenants.length||
       !['data-exchange','initial-status','data-write','recovery-status'].includes(context.stage)||
       !['exchange','status','entries-write'].includes(context.routeClass))return Promise.reject(fail('M7_DIAGNOSTIC_REQUEST_CONTEXT_INVALID'));
    if(httpTrail.requests.length>=trailRecordLimit)return Promise.reject(fail('M7_DIAGNOSTIC_REQUEST_BOUND'));
    if(Date.now()>=deadline)return Promise.reject(fail('M7_DIAGNOSTIC_DEADLINE'));
    physicalHttpRequests++;
    const record={request:physicalHttpRequests,classification:'pending',stage:context.stage,tenantIndex:context.tenantIndex,method:body===undefined?'GET':'POST',routeClass:context.routeClass,status:null,errorCode:null,failureCode:null};
    httpTrail.requests.push(record);persistTrail();
    return new Promise((resolve,reject)=>{
      const bytes=body===undefined?null:Buffer.from(JSON.stringify(body));
      const req=http.request({hostname:'127.0.0.1',port:m.port,path:route,method:bytes?'POST':'GET',headers:{Host:tenant.host,Accept:'application/json',...(bytes?{'content-type':'application/json','content-length':bytes.length}:{})},timeout:Math.min(10000,deadline-Date.now())},res=>{
        record.status=Number.isInteger(res.statusCode)?res.statusCode:null;try{persistTrail();}catch(error){req.destroy(error);return;}
        const chunks=[];let size=0;
        res.on('data',chunk=>{size+=chunk.length;if(size>1048576)req.destroy(fail('M7_DIAGNOSTIC_RESPONSE_TOO_LARGE'));else chunks.push(chunk);});
        res.on('end',()=>{try{const parsed=JSON.parse(Buffer.concat(chunks).toString());record.errorCode=parsed&&!Array.isArray(parsed)&&typeof parsed==='object'?safeCode(parsed.error):null;
          if(res.statusCode===200){criterionHttpRequests++;record.classification='criterion';}
          else if(context.routeClass==='status'&&body===undefined&&res.statusCode===503&&record.errorCode==='TENANT_WARMING'){warmProbeHttpRequests++;record.classification='warming-probe';}
          else record.classification='refused';
          persistTrail();resolve({status:res.statusCode,body:parsed});}catch(error){record.failureCode=safeCode(error.code)||'M7_DIAGNOSTIC_RESPONSE_INVALID';record.classification='failed';try{persistTrail();}catch{}reject(fail(record.failureCode));}});
        res.on('error',error=>{record.failureCode=safeCode(error.code)||'M7_DIAGNOSTIC_HTTP_ERROR';persistTrail();reject(error);});
      });
      requests.add(req);req.once('close',()=>requests.delete(req));
      req.on('timeout',()=>req.destroy(fail('M7_DIAGNOSTIC_HTTP_TIMEOUT')));req.on('error',error=>{record.failureCode=safeCode(error.code)||'M7_DIAGNOSTIC_HTTP_ERROR';persistTrail();reject(error);});req.end(bytes);
    });
  }
  async function statusRequest(tenant,tenantIndex,phase){
    for(;;){
      const response=await request(tenant,'/api/v1/status.json?token='+encodeURIComponent(tenant.token),undefined,{stage:phase,tenantIndex,routeClass:'status'});
      if(response.status!==503||response.body?.error!=='TENANT_WARMING')return response;
      if(warmProbeHttpRequests>=maxWarmProbes)throw fail('M7_DIAGNOSTIC_WARM_PROBE_LIMIT');
      if(Date.now()>=deadline)throw fail('M7_DIAGNOSTIC_DEADLINE');
      await sleep(Math.min(200,Math.max(0,deadline-Date.now())));
    }
  }
  const increment=key=>{metrics[key]??={count:0};metrics[key].count++;};
  try{return await Promise.race([(async()=>{
    for(const [tenantIndex,tenant] of tenants.entries()){
      const exchange=await request(tenant,'/api/v2/authorization/request/'+encodeURIComponent(tenant.token),undefined,{stage:'data-exchange',tenantIndex,routeClass:'exchange'});
      if(exchange.status!==200||typeof exchange.body.token!=='string')throw fail('M7_DIAGNOSTIC_DATA_EXCHANGE_REFUSED');
      const status=await statusRequest(tenant,tenantIndex,'initial-status');
      if(status.status!==200||!status.body||typeof status.body!=='object')throw fail('M7_DIAGNOSTIC_HTTP_REFUSED');
      const cell={tenant,frames:[],connected:false,connects:0,disconnects:[]};
      // The registered hostname belongs in the URL. XHR may overwrite Host
      // overrides when a127 URL is used, so no extraHeaders workaround exists.
      cell.socket=io('http://'+tenant.host+':'+m.port,{transports:['polling'],agent,reconnection:true,reconnectionDelay:200,reconnectionDelayMax:500,timeout:Math.min(10000,seconds*1000)});
      cell.socket.on('connect',()=>{cell.connects++;cell.connected=true;cell.socket.emit('authorize',{client:'web',token:exchange.body.token,history:1,status:true},()=>{});});
      cell.socket.on('disconnect',reason=>{cell.disconnects.push(reason);cell.connected=false;});
      cell.socket.on('dataUpdate',frame=>{cell.frames.push({at:Date.now(),mills:(frame?.sgvs||[]).map(row=>Number(row.mills))});});
      sockets.push(cell);
    }
    await awaitUntil(()=>sockets.every(row=>row.connected&&row.frames.length),'M7_DIAGNOSTIC_STOCK_PRIME_FAILED');checks.stockPrimed=true;checks.dataHttp=true;
    stage='write-and-current-frame';
    for(const [index,cell] of sockets.entries()){
      const date=Date.now()+index;cell.expectedDate=date;
      const row={type:'sgv',sgv:110+index,date,dateString:new Date(date).toISOString(),direction:'Flat',device:marker};
      const response=await request(cell.tenant,'/api/v1/entries?token='+encodeURIComponent(cell.tenant.token),[row],{stage:'data-write',tenantIndex:index,routeClass:'entries-write'});
      if(response.status!==200)throw fail('M7_DIAGNOSTIC_WRITE_REFUSED');
      increment('writes_ok');increment('writes_ok{tenant:'+cell.tenant.id+'}');increment('writes_ok{kind:entries}');
    }
    fs.writeFileSync(path.join(out,'client-acks.json'),JSON.stringify({kind:'bounded-diagnostic-acks',metrics}));
    fs.writeFileSync(path.join(out,'fanout.json'),JSON.stringify({probeWrites:{byTenant:{}}}));
    await awaitUntil(()=>sockets.every(row=>row.frames.some(frame=>frame.mills.includes(row.expectedDate))),'M7_DIAGNOSTIC_FRAME_MISSING');checks.currentFrames=true;
    const config=JSON.parse(fs.readFileSync(path.join(d,'frozen.compose.json')));
    const roles=Object.entries(config.services).filter(([,value])=>Array.isArray(value.command)&&value.command.at(-1)==='realtime').map(([name])=>name);
    if(!roles.length)throw fail('M7_DIAGNOSTIC_REALTIME_ROSTER_MISSING');
    stage='observed-restart-and-stock-recovery';
    const at=Date.now(),restarted=await restartFn({composeArgs:['compose','-p',m.project,'--env-file',path.join(d,'env'),'-f',path.join(d,'frozen.compose.json')],roles,at});
    checks.restartObserved=true;
    // No manual connect() after disconnect: this is stock unaided recovery.
    await awaitUntil(()=>sockets.every(row=>row.connected&&row.frames.some(frame=>frame.at>at&&frame.mills.includes(row.expectedDate))),'M7_DIAGNOSTIC_STOCK_RECOVERY_FAILED');checks.stockRecovered=true;
    for(const [tenantIndex,cell] of sockets.entries()){const status=await statusRequest(cell.tenant,tenantIndex,'recovery-status');if(status.status!==200)throw fail('M7_DIAGNOSTIC_POST_RECOVERY_HTTP_REFUSED');}
    checks.httpAfterRecovery=true;
    const observation={kind:'bounded-diagnostic-observations',checks,restart:restarted,acceptedWrites:metrics.writes_ok.count,...accounting(),tenants:tenants.length,trafficDeadlineSeconds:seconds,requestTrail:'diagnostic-http.json'};
    fs.writeFileSync(path.join(out,'diagnostic-observations.json'),JSON.stringify(observation,null,2));
    return observation;
  })(),new Promise((resolve,reject)=>{timer=setTimeout(()=>reject(fail('M7_DIAGNOSTIC_DEADLINE')),seconds*1000);})]);
  }catch(error){terminalCode=safeCode(error.code)||'M7_DIAGNOSTIC_CLIENT_REFUSED';throw error;}finally{if(!fs.existsSync(path.join(out,'diagnostic-observations.json')))fs.writeFileSync(path.join(out,'diagnostic-observations.json'),JSON.stringify({checks,stage,failureCode:terminalCode,requestTrail:'diagnostic-http.json',...accounting(),sockets:sockets.map(row=>({connects:row.connects,disconnects:row.disconnects,connected:row.connected,frames:row.frames.length,containsExpected:row.frames.some(frame=>frame.mills.includes(row.expectedDate))}))}));clearTimeout(timer);shuttingDown=true;for(const request of requests)request.destroy();for(const cell of sockets)cell.socket.close();for(const agent of agents)agent.destroy();}
}
module.exports={run};
if(require.main===module)run({directory:process.argv[2],seconds:Number(process.argv[3])}).then(()=>console.log('M7_DIAGNOSTIC_CLIENT_CRITERIA_PASS')).catch(error=>{console.error(/^M7_[A-Z_]+$/.test(error.code||'')?error.code:'M7_DIAGNOSTIC_CLIENT_REFUSED');process.exitCode=1;});
