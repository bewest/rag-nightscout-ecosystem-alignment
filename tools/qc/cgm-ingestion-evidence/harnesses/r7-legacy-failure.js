// Repro 7: legacy bridge under (a) permanent auth failure and (b) a stale
// session / non-array body. Drives lib/plugins/bridge.js with a fake clock
// and a fake `request`. No network.
const Module=require('module');
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
let MODE='authfail';
const calls=[];
function fakeRequest(req, then){
  const kind=/Authenticate/.test(req.uri)?'auth':/LoginPublisher/.test(req.uri)?'login':'glucose';
  calls.push(kind);
  let res={statusCode:200}, body=null;
  if (MODE==='authfail' && kind==='auth'){ res={statusCode:401}; body={Code:'SSO_AuthenticateAccountNotFound'}; }
  else if (kind==='auth') body='ACCT';
  else if (kind==='login') body='SESSION';
  else if (MODE==='badshape') body={Code:'MonitoringSessionNotActive'};
  else body=[{WT:`/Date(${Date.now()})/`,Trend:4,Value:100}];
  process.nextTick(()=>then(null,res,body));
  return {};
}
const orig=Module._load;
Module._load=function(r){ if(r==='request') return fakeRequest; return orig.apply(this,arguments); };

// virtual timers for setInterval used by bridge.js
const timers=[]; let now=Date.now();
const realSetInterval=global.setInterval, realDate=Date;
global.setInterval=(fn,ms)=>{ timers.push({fn,ms,next:now+ms}); return timers.length; };
global.clearInterval=()=>{};
global.Date=class extends realDate { constructor(...a){ if(a.length===0) super(now); else super(...a);} static now(){return now;} };

const bridge=require(CRM+'/lib/plugins/bridge.js');
function drive(minutes, label, mode, settings){
  MODE=mode; calls.length=0; timers.length=0; now=realDate.now();
  const entries=[]; const ctx={create:(g,cb)=>{entries.push(...(g||[])); cb&&cb(null,g);}};
  const b=bridge.create({extendedSettings:{bridge:Object.assign({userName:'u',password:'p'},settings||{})}}, null);
  b.startEngine(ctx);
  const ticks=minutes*60;
  let thrown=0;
  for(let i=0;i<ticks;i++){
    now+=1000;
    for(const t of timers) if(now>=t.next){ t.next=now+t.ms; try{ t.fn(); }catch(e){ thrown++; } }
    // flush nextTick callbacks synchronously enough
  }
  return new Promise(r=>setTimeout(()=>{
    const c={}; calls.forEach(k=>c[k]=(c[k]||0)+1);
    console.log(`\n### LEGACY ${label} (${minutes} simulated minutes)`);
    console.log('   vendor requests:', JSON.stringify(c), ' total', calls.length);
    console.log('   entries handed to entries.create:', entries.length);
    console.log('   exceptions escaping the timer callback:', thrown);
    r();
  }, 300));
}
(async()=>{
  await drive(60,'permanent auth failure (wrong credentials)','authfail');
  await drive(60,'happy path — how many sessions per hour?','ok');
  await drive(5,'vendor returns an object instead of an array','badshape');
  await drive(10,'BRIDGE_INTERVAL set to a non-numeric string','ok',{interval:'abc'});
  process.exit(0);
})();
