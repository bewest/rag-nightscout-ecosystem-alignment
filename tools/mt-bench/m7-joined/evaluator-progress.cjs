'use strict';
// Executed in one exact owned evaluator container, never an application mount.
// The controller prefixes only bounded synthetic UUIDs and byte/query limits.
(async()=>{
  let bytes=0,queries=0;
  const deadline=Date.now()+15000;
  const watchdog=setTimeout(()=>process.exit(1),16000);
  try {
    const values=require('./deploy/multitenant/service-environment').read();
    // Read the same pure pool contract without loading evaluator execution/settings.
    const partition=require('./lib/pool-membership/config').fromEnvironment('evaluator',values);
    const keys=['NS_SERVE_INTERNAL_HOST','NS_SERVE_INTERNAL_PORT','NS_SERVE_INTERNAL_SOCKET','NS_SERVE_INTERNAL_SHUTDOWN_TIMEOUT_MS','XDG_RUNTIME_DIR'];
    const environment=Object.fromEntries(keys.filter(key=>Object.hasOwn(values,key)).map(key=>[key,values[key]]));
    const selfOrdinal=partition.partitioned?partition.ordinal:0;
    const selfMode=partition.partitioned?'partitioned':'standalone';
    const own=require('./lib/server/internal-api/listener-config').resolve(['evaluator'],environment);
    const client=require('./lib/server/internal-api/clients').evaluatorInspection(own.peer('evaluator',{maxBytes:1048576,timeoutMs:5000}));
    for(let offset=0;offset<M7_PROGRESS_IDS.length;offset+=128){
      if(Date.now()>=deadline||++queries>M7_PROGRESS_QUERY_BUDGET)throw Error('M7_EVALUATOR_PROGRESS_BUDGET');
      const selected=M7_PROGRESS_IDS.slice(offset,offset+128);
      const view=await client.inspectEvaluator({tenants:selected});
      const line=JSON.stringify({selected,view,selfOrdinal,selfMode,observedAt:Date.now()})+'\n';
      bytes+=Buffer.byteLength(line);
      if(bytes>M7_PROGRESS_BYTE_BUDGET)throw Error('M7_EVALUATOR_PROGRESS_BUDGET');
      if(!process.stdout.write(line))await new Promise((resolve,reject)=>{const done=()=>{process.stdout.removeListener('error',failed);resolve();};const failed=error=>{process.stdout.removeListener('drain',done);reject(error);};process.stdout.once('drain',done);process.stdout.once('error',failed);});
    }
  } finally {clearTimeout(watchdog);}
})().catch(()=>{process.stderr.write('M7_EVALUATOR_PROGRESS_UNAVAILABLE\n');process.exitCode=1;});
