'use strict';
// One cached private inspection in one exact-owned role container. No tenant selector.
(async()=>{
  const watchdog=setTimeout(()=>process.exit(1),6000);
  try{
    const values=require('./deploy/multitenant/service-environment').read();
    const keys=['NS_SERVE_INTERNAL_HOST','NS_SERVE_INTERNAL_PORT','NS_SERVE_INTERNAL_SOCKET','NS_SERVE_INTERNAL_SHUTDOWN_TIMEOUT_MS','XDG_RUNTIME_DIR'];
    const environment=Object.fromEntries(keys.filter(key=>Object.hasOwn(values,key)).map(key=>[key,values[key]]));
    const own=require('./lib/server/internal-api/listener-config').resolve(['realtime'],environment);
    const client=require('./lib/server/internal-api/clients').realtimeInspection(own.peer('realtime',{maxBytes:65536,timeoutMs:5000}));
    const view=await client.inspectRealtime({});
    const output=JSON.stringify({kind:view.kind,processIncarnation:view.processIncarnation,phase:view.phase,ownerAvailable:view.ownerAvailable,stats:view.stats});
    if(Buffer.byteLength(output)>8192)throw Error('M7_REALTIME_COST_BOUND');
    process.stdout.write(output+'\n');
  }finally{clearTimeout(watchdog);}
})().catch(error=>{const code=/^[A-Z][A-Z0-9_]{0,95}$/.test(error?.code||'')?' '+error.code:'';process.stderr.write('M7_REALTIME_COST_UNAVAILABLE'+code+'\n');process.exitCode=1;});
