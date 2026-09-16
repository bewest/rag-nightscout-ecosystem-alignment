const Module=require('module');
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const MODE=process.argv[2], MINUTES=Number(process.argv[3]||60), IVAL=process.argv[4];
const calls=[];
function fakeRequest(req, then){
  const kind=/Authenticate/.test(req.uri)?'auth':/LoginPublisher/.test(req.uri)?'login':'glucose';
  calls.push(kind);
  let res={statusCode:200}, body=null;
  if (MODE==='authfail' && kind==='auth'){ res={statusCode:401}; body={Code:'SSO_AuthenticateAccountNotFound'}; }
  else if (kind==='auth') body='ACCT';
  else if (kind==='login') body='SESSION';
  else if (MODE==='badshape') body={Code:'MonitoringSessionNotActive'};
  else if (MODE==='sessionstale') { res={statusCode:401}; body={Code:'SessionIdNotFound'}; }
  else body=[{WT:`/Date(${Date.now()})/`,Trend:4,Value:100}];
  then(null,res,body);            // synchronous: deterministic accounting
  return {};
}
Module._load=((o)=>function(r){ if(r==='request') return fakeRequest; return o.apply(this,arguments); })(Module._load);
const timers=[]; const realDate=Date; let now=realDate.now();
global.setInterval=(fn,ms)=>{ timers.push({fn,ms,next:now+ms}); return timers.length; };
global.clearInterval=()=>{};
global.Date=class extends realDate { constructor(...a){ if(a.length===0) super(now); else super(...a);} static now(){return now;} };
console.log = () => {}; console.error = () => {};
const bridge=require(CRM+'/lib/plugins/bridge.js');
const entries=[];
const s={userName:'u',password:'p'}; if(IVAL!==undefined) s.interval = isNaN(Number(IVAL))?IVAL:Number(IVAL);
const b=bridge.create({extendedSettings:{bridge:s}}, null);
b.startEngine({create:(g,cb)=>{entries.push(...(g||[])); cb&&cb(null,g);}});
let thrown=0, firstThrow=null;
for(let i=0;i<MINUTES*60;i++){ now+=1000;
  for(const t of timers) if(now>=t.next){ t.next=now+t.ms; try{ t.fn(); }catch(e){ thrown++; firstThrow=firstThrow||String(e); } } }
const c={}; calls.forEach(k=>c[k]=(c[k]||0)+1);
process.stdout.write(`mode=${MODE.padEnd(13)} minutes=${String(MINUTES).padStart(4)} requests=${JSON.stringify(c).padEnd(46)} total=${String(calls.length).padStart(6)} entries=${String(entries.length).padStart(5)} uncaught=${thrown}${firstThrow?' :: '+firstThrow:''}\n`);
