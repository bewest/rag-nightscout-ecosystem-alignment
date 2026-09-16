// Repro 6: a PERMANENTLY rejected session. Does connect ever get a new one?
const NC = process.env.NC_ROOT;
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const {interpret} = require(CRM+'/node_modules/xstate');
const builder = require(NC + '/lib/builder');
const dexcomshare = require(NC + '/lib/sources/dexcomshare');
const MIN=60*1000;
function VirtualClock () {
  let now = 0, seq = 0; const timers = new Map();
  return { now: () => now,
    setTimeout (fn, ms) { const id = ++seq; timers.set(id, {at: now + (ms||0), fn}); return id; },
    clearTimeout (id) { timers.delete(id); },
    async increment (ms) { const target = now + ms;
      for (;;) { let next=null; for (const [id,t] of timers) if (t.at<=target && (next===null || t.at<timers.get(next).at)) next=id;
        if (next===null) break; const t=timers.get(next); timers.delete(next); now=t.at; t.fn();
        await new Promise(r=>setImmediate(r)); await new Promise(r=>setImmediate(r)); } now=target; } };
}
(async () => {
  const counts={auth:0,login:0,glucose:0};
  const timeline=[];
  const clock=VirtualClock();
  const fakeAxios={create:()=>({post:(p)=>{
    const kind=/Authenticate/.test(p)?'auth':/LoginPublisher/.test(p)?'login':'glucose';
    counts[kind]++; timeline.push(`${(clock.now()/MIN).toFixed(1)}m ${kind}`);
    if (kind==='auth') return Promise.resolve({data:'ACCT'});
    if (kind==='login') return Promise.resolve({data:'SESSION-'+counts.login});
    if (counts.glucose<=2) return Promise.resolve({data:[{WT:`/Date(${Date.now()})/`,Trend:4,Value:100}]});
    const e=new Error('401'); e.response={status:401,data:{Code:'SessionIdNotFound'}}; return Promise.reject(e);
  }})};
  const persister=(b)=>Promise.resolve({entries:new Date(Date.now()-6*MIN)});
  persister.gap_for=()=>Promise.resolve({entries:new Date(Date.now()-6*MIN)});
  const log={debug(){},error(){},info(){},warn(){}};
  const make=builder({output:persister,logger:log});
  const impl=dexcomshare({shareAccountName:'s',sharePassword:'s'},fakeAxios,log);
  impl.generate_driver(make);
  const actor=interpret(make(),{clock}); actor.start(); actor.send({type:'START'});
  const marks=[60,180,360,720,1439,1441,1500];
  let last=0;
  for (const m of marks) { await clock.increment((m-last)*MIN); last=m;
    console.log(`t=${String(m).padStart(4)}m  auth=${counts.auth} login=${counts.login} glucose=${counts.glucose}`);
  }
  console.log('\nfirst 12 vendor calls:', timeline.slice(0,12).join(' | '));
  console.log('calls around the 24h session expiry:', timeline.filter(x=>parseFloat(x)>1420 && parseFloat(x)<1460).join(' | ') || '(none)');
  actor.stop();
})();
