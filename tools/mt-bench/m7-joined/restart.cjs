'use strict';
// Instrument-owned restart observer. A failed/skipped restart must never look
// like measured recovery of a still-running old process. No product authority.
const {execFile}=require('node:child_process');
const fail=code=>Object.assign(new Error(code),{code});
const execute=args=>new Promise((resolve,reject)=>execFile('docker',args,{encoding:'utf8',timeout:120000,maxBuffer:1048576},(error,stdout)=>error?reject(fail('M7_RESTART_COMMAND_FAILED')):resolve(stdout.trim())));
async function restart({composeArgs,roles,at=Date.now(),run=execute}){
  if(!Array.isArray(composeArgs)||composeArgs[0]!=='compose'||!Array.isArray(roles)||!roles.length||roles.length>64||roles.some(role=>!/^[a-z0-9][a-z0-9_-]*$/.test(role))||!Number.isSafeInteger(at))throw fail('M7_RESTART_INPUT_INVALID');
  await run([...composeArgs,'restart',...roles]);
  const starts={};
  for(const role of roles){
    const id=await run([...composeArgs,'ps','-q',role]);
    if(!/^[0-9a-f]{12,64}$/.test(id))throw fail('M7_RESTART_CONTAINER_MISSING');
    let state;try{state=JSON.parse(await run(['inspect','--format','{{json .State}}',id]));}catch{throw fail('M7_RESTART_STATE_UNAVAILABLE');}
    const started=Date.parse(state.StartedAt);
    if(state.Running!==true||!Number.isFinite(started)||started<at)throw fail('M7_RESTART_NOT_OBSERVED');
    starts[role]={startedAt:state.StartedAt,pid:state.Pid};
  }
  return {commandMs:Date.now()-at,starts};
}
module.exports={restart,execute};
