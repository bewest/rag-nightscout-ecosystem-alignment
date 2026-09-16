// Repro 7c: the stale-session loop with an ASYNCHRONOUS fake request, so the
// synchronous stack overflow is not an artifact. Counts requests in 3 seconds
// of wall time from ONE poll tick.
const Module=require('module');
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
let n=0; const t0=Date.now();
function fakeRequest(req, then){
  n++;
  if (Date.now()-t0 > 3000) { return; }           // stop feeding the loop
  const kind=/Authenticate/.test(req.uri)?'auth':/LoginPublisher/.test(req.uri)?'login':'glucose';
  setImmediate(() => {
    if (kind==='auth') then(null,{statusCode:200},'ACCT');
    else if (kind==='login') then(null,{statusCode:200},'SESSION');
    else then(null,{statusCode:401},{Code:'SessionIdNotFound'});   // session rejected
  });
  return {};
}
Module._load=((o)=>function(r){ if(r==='request') return fakeRequest; return o.apply(this,arguments); })(Module._load);
console.log=()=>{}; console.error=()=>{};
const engine=require(CRM+'/node_modules/share2nightscout-bridge');
engine({ login:{accountName:'s',password:'s'}, fetch:{maxCount:1,minutes:10}, nightscout:{},
         maxFailures:3, firstFetchCount:1, callback:()=>{} });
setTimeout(()=>{ process.stdout.write(
  `ONE poll tick, session permanently rejected: ${n} vendor requests in 3 s of wall clock ` +
  `(~${Math.round(n/3)}/s), no backoff, no bound. maxFailures never reaches 3 because refresh_token() resets failures=0 on every successful login.\n`);
  process.exit(0); }, 3500);
