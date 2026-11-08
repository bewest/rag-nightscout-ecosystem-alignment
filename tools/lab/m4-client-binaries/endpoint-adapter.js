'use strict';
// Endpoint semantics live ONLY in the pinned verbatim Python helper. This is
// a fixed inert JSON caller; the finite parent must pin this Python executable.
const assert=require('node:assert/strict'),path=require('node:path'),cp=require('node:child_process');
const PYTHON='/usr/bin/python3.12';
function call (operation, value) {
  const input=JSON.stringify({operation,...value});assert(Buffer.byteLength(input)<=32*1024*1024,'M4_ENDPOINT_INPUT_BOUND');
  const result=cp.spawnSync(PYTHON,['-I','-B',path.join(__dirname,'endpoint-adapter.py')],
    {input,encoding:'utf8',timeout:8000,maxBuffer:32*1024*1024,env:{PATH:'/usr/bin:/bin',LANG:'C.UTF-8'}});
  assert(!result.error && result.status===0,'M4_ENDPOINT_PROFILE_REFUSED');return JSON.parse(result.stdout);
}
module.exports=Object.freeze({PYTHON,PROFILE:'network-endpoint-stable-v1',
  baselineSnapshot:rawBatches=>call('baseline-snapshot',{rawBatches}),
  compareBaseline:(before,after)=>call('compare-baseline',{before,after}),
  networkSnapshot:rows=>call('network-snapshot',{rows}),
  compareEndpoints:(before,after)=>call('compare-endpoints',{before,after}),
  configurationFingerprint:(Config,HostConfig)=>call('configuration',{Config,HostConfig})});
