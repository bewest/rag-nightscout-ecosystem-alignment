'use strict';
// Bounded, read-only authority transport check. No new benchmark workload.
const fs=require('node:fs'),http=require('node:http'),path=require('node:path');
async function run(tenants,base,io,{observeMs=5000}={}){
  if(tenants.length!==2||!base.hostname.match(/^(127\.0\.0\.1|localhost)$/))throw Error('K8S_ACCESS_SCOPE');
  const records=[],sockets=[],startedAt=Date.now(),deadline=startedAt+45000;
  const lookup=(host,opts,cb)=>opts?.all?cb(null,[{address:'127.0.0.1',family:4}]):cb(null,'127.0.0.1',4);
  const agent=new http.Agent({lookup});
  const get=(host,token,exchange=false)=>new Promise((resolve,reject)=>{
    const route=exchange?'/api/v2/authorization/request/'+encodeURIComponent(token):'/api/v1/entries/sgv.json?count=1&token='+encodeURIComponent(token);
    const req=http.get({hostname:base.hostname,port:base.port,path:route,headers:{Host:host},timeout:5000},res=>{
      let n=0;const chunks=[];res.on('data',c=>{n+=c.length;if(n>65536)req.destroy(Error('K8S_ACCESS_BODY_BOUND'));else chunks.push(c);});
      res.on('end',()=>{let value;try{value=JSON.parse(Buffer.concat(chunks));}catch{value=null;}
        resolve({status:res.statusCode,arrayBody:Array.isArray(value),error:typeof value?.error==='string'&&/^[A-Z_]{1,64}$/.test(value.error)?value.error:null,...(exchange?{jwt:value?.token}:{})});});
    });req.on('timeout',()=>req.destroy(Error('K8S_ACCESS_TIMEOUT')));req.on('error',reject);
  });
  try{
    for(let i=0;i<2;i++){
      const exchanged=await get(tenants[i].host,tenants[i].token,true);
      if(exchanged.status!==200||typeof exchanged.jwt!=='string'||!exchanged.jwt)throw Error('K8S_ACCESS_EXCHANGE_UNMEASURED');
      const foreign=await get(tenants[1-i].host,tenants[i].token);
      if(![401,403].includes(foreign.status)||foreign.arrayBody)throw Error('K8S_CROSS_TENANT_AUTHORITY');
      records.push({case:'cross-token-host',tenantIndex:i,...foreign});
      const invalid=await get(tenants[i].host,'synthetic-invalid-credential');
      if(![401,403].includes(invalid.status)||invalid.arrayBody)throw Error('K8S_INVALID_CREDENTIAL_ACCEPTED');
      records.push({case:'invalid-token',tenantIndex:i,...invalid});
      // A swapped credential on the stock Socket.IO authorization path must
      // produce no dataUpdate during a finite observed polling connection.
      let connected=false,frames=0,authorizeReply=false;
      const socket=io('http://'+tenants[1-i].host+':'+base.port,{transports:['polling'],agent,reconnection:false,timeout:5000});sockets.push(socket);
      socket.on('connect',()=>{connected=true;socket.emit('authorize',{client:'web',token:exchanged.jwt,history:1,status:true},()=>{authorizeReply=true;});});
      socket.on('dataUpdate',()=>frames++);
      const observationStarted=Date.now(),until=Math.min(deadline,Date.now()+observeMs);
      await new Promise(resolve=>setTimeout(resolve,Math.max(0,until-Date.now())));
      if(!connected)throw Error('K8S_SOCKET_REFUSAL_UNMEASURED');
      if(frames)throw Error('K8S_FOREIGN_SOCKET_FRAME');
      records.push({case:'cross-token-socket',tenantIndex:i,connected,authorizeReply,frames,observedMs:Date.now()-observationStarted});socket.close();
    }
    return {version:1,verdict:'PASS',crossTenantChecks:2,records,startedAt,endedAt:Date.now(),scope:'finite read refusal and no foreign frame; no network-policy enforcement claim',capacityAcceptance:'NOT_GRANTED'};
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
  const result = await run(selected, new URL(process.argv[3]),
    require(path.join(process.argv[4], 'node_modules/socket.io-client')).io);
  console.log(JSON.stringify({ ...result, tenantRosterSize: tenants.length, witnessTenants: selected.map(row => row.id) }));
}
module.exports = { run, witnesses };
if (require.main === module) main().catch(e => {
  console.error(/^K8S_[A-Z_]+$/.test(e.message) ? e.message : 'K8S_ACCESS_UNMEASURED');
  process.exitCode = 1;
});
