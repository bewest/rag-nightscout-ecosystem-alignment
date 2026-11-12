'use strict';
// Test-only actual child process: real stock SDK/HTTP, instrumented platform
// restart over private IPC to the owned HTTP/Socket.IO server fixture.
const {run}=require('./diagnostic.cjs');
if(typeof process.send!=='function')throw Error('M7_FIXTURE_IPC_REQUIRED');
run({directory:process.argv[2],seconds:Number(process.argv[3]),restart:()=>new Promise((resolve,reject)=>{
  process.once('message',value=>value?.kind==='fixture-restarted'?resolve(value.result):reject(Error('M7_FIXTURE_PROTOCOL')));
  process.send({kind:'fixture-restart'});
})}).then(()=>console.log('M7_DIAGNOSTIC_CLIENT_CRITERIA_PASS')).catch(error=>{console.error(/^M7_[A-Z_]+$/.test(error.code||'')?error.code:'M7_DIAGNOSTIC_CLIENT_REFUSED');process.exitCode=1;}).finally(()=>process.disconnect());
