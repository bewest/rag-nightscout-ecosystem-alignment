'use strict';
// Finite accepted-input discriminator. Synthetic data only.
// CRM_ROOT=<clean source> OUT=<overflow artifacts/run> MODE=plain HOURS=24 K=80
// node --expose-gc --max-old-space-size=512 accepted-input-profile.cjs
// EXPECTED_HEAD explicitly selects another immutable experimental checkpoint.
//
// Reuses actual evaluator, views, projection reads and runtime digest. Replay
// returns already-accepted bounded input; the SQL sentinel rejects every query.
// This excludes intake, replay/database cost, scheduler/pool waits, authority
// checks, durable completion SQL, transport and HTTP. Those remain UNMEASURED.
// Due-only means direct evaluateTime calls without new input, with clinical time
// advancing one second per cycle; it does not measure a running due scheduler.
// Statistics are an independent synthetic whole-history value, never window size.
//
// Modes: plain (no stage/sampling profiler), stages (inclusive nested wall timers
// and total JSON text bytes, NOT physical copies), cpu (V8 samples), heap (V8
// sampled allocations incl collected objects; NOT exact total allocated bytes),
// control (frame independence, freshness, restoration, input correction), typed
// (private exports of unchanged typed-checkpoint content/envelope functions).
// TRACE=1 records full per-cycle result hashes for semantic comparison; do not
// compare its timing with a run without TRACE. BREAK=reuse-output compiles an
// in-memory semantic mutation; control must reject it at FRAME_ALIAS.
// All modes include per-cycle memory snapshots and ordinary GC observation.
// Peaks are sampled, retained heap follows explicit GC, event-loop delay includes
// deliberate setImmediate yields. These are process-local observations on a
// shared host, with a V8 heap bound and finite cycles, not a fleet forecast.
// Preserve the measured harness alongside output before adding instruments.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const cp = require('node:child_process'), crypto = require('node:crypto'), inspector = require('node:inspector');
const { PerformanceObserver, monitorEventLoopDelay } = require('node:perf_hooks');
const root = fs.realpathSync(process.env.CRM_ROOT || '');
const expectedHead=process.env.EXPECTED_HEAD || 'c1173eab7c4fea1270eb585aff5961142849d048';
const head = cp.execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], {encoding:'utf8'}).trim();
assert.equal(head, expectedHead, 'SOURCE_BOUNDARY');
assert.equal(cp.execFileSync('git', ['-C', root, 'status', '--porcelain', '--untracked-files=no'], {encoding:'utf8'}), '', 'SOURCE_DIRTY');
const out = process.env.OUT, mode = process.env.MODE || 'plain', hours = +(process.env.HOURS || 24), K = +(process.env.K || 80);
assert.equal(typeof global.gc,'function','Run node with --expose-gc');
assert(out && ['plain','stages','cpu','heap','control','typed'].includes(mode));
assert([24,48].includes(hours) && Number.isSafeInteger(K) && K>0 && K<=200);
fs.mkdirSync(out, {recursive:true});
const req = p => require(path.join(root,p));
console.log=console.info=console.warn=()=>{};
const stages = {}; let counting = false, json = {}, captures={kept:0,refused:0,copied:0};
const working=req('lib/data/working-set');
const keep=working.keep,copy=working.copy;
working.keep=function(...a){const r=keep(...a);if(counting)captures[r===null?'refused':'kept']++;return r;};
working.copy=function(...a){if(counting)captures.copied++;return copy(...a);};
function timed(name, fn) { return function(...args) { if(!counting)return fn.apply(this,args);const t=process.hrtime.bigint();try{return fn.apply(this,args);}finally{const s=stages[name] ||= {calls:0,ms:0};s.calls++;s.ms+=Number(process.hrtime.bigint()-t)/1e6;} }; }
if(mode==='stages') {
  for(const [file,names] of [['lib/storage/postgres-identity',['encodeDocument','decodeDocument']],['lib/storage/postgres-projection-read',['prepare']],['lib/data/json-copy',['deepFreeze']],['lib/data/working-set',['keep','copy']]]) {
    const m=req(file);for(const name of names)m[name]=timed(name,m[name]);
  }
  const file=require.resolve(path.join(root,'lib/data/views')), factory=req('lib/data/views');
  require.cache[file].exports=function(...args){const v=factory(...args);v.evaluateCycle=timed('engine',v.evaluateCycle);const materialise=v.materialise;v.materialise=function(...a){if(!counting)return materialise.apply(this,a);const t=process.hrtime.bigint(), cb=a.pop();a.push(function(...b){const s=stages.materialise ||= {calls:0,ms:0};s.calls++;s.ms+=Number(process.hrtime.bigint()-t)/1e6;return cb(...b);});return materialise.apply(this,a);};return v;};
  const stringify=JSON.stringify, parse=JSON.parse;
  JSON.stringify=function(...a){const r=stringify(...a);if(counting){json.stringifyCalls=(json.stringifyCalls||0)+1;json.stringifyBytes=(json.stringifyBytes||0)+Buffer.byteLength(r||'');}return r;};
  JSON.parse=function(...a){if(counting){json.parseCalls=(json.parseCalls||0)+1;json.parseBytes=(json.parseBytes||0)+Buffer.byteLength(a[0]);}return parse(...a);};
}
if(process.env.BREAK === 'reuse-output') {
 const Module=require('node:module'), file=path.join(root,'lib/data/tenant-projection-evaluator.js');
 const source=fs.readFileSync(file,'utf8'), needle='    binding();\n    if (running)';
 assert.equal(source.split(needle).length,2,'MUTATION_LANDED_ONCE');
 const mutant=new Module(file,module);mutant.filename=file;mutant.paths=Module._nodeModulePaths(path.dirname(file));
 mutant._compile(source.replace(needle,'    if (!acquire && kept) return kept;\n'+needle),file);require.cache[file]=mutant;
}
const evaluator=req('lib/data/tenant-projection-evaluator'), runtime=req('lib/server/serve/evaluator-runtime');
const clock=req('tests/lib/views-replay/clock'), scope=req('lib/storage/tenant-scope');
let typed;
if(mode==='typed') {
 const Module=require('node:module'), file=path.join(root,'lib/pgstream/typed-checkpoint.js');
 const instrument=new Module(file,module);instrument.filename=file;instrument.paths=Module._nodeModulePaths(path.dirname(file));
 instrument._compile(fs.readFileSync(file,'utf8')+'\nmodule.exports.profileOnly={contentOf,bodyOf};',file);
 typed=instrument.exports.profileOnly;
}

const at=Date.UTC(2026,10,16,12), MIN=60000, tenant='eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
const rows=[];
for(let i=hours*12;i>0;i--){const t=at-i*5*MIN-2000;
 rows.push({domain:'entries',ordinal:rows.length+1,document:{_id:'synthetic-sgv-'+i,type:'sgv',sgv:123,date:t,dateString:new Date(t).toISOString(),direction:'Flat'}});
 rows.push({domain:'devicestatus',ordinal:rows.length+1,document:{_id:'synthetic-status-'+i,created_at:new Date(t).toISOString(),device:'synthetic-loop',uploader:{battery:60},pump:{clock:new Date(t).toISOString(),reservoir:100,battery:{percent:80}},loop:{timestamp:new Date(t).toISOString(),iob:{timestamp:new Date(t).toISOString(),iob:0.5},cob:{cob:0},predicted:{startDate:new Date(t).toISOString(),values:[120,121,122]}}}});
}
rows.push({domain:'profile',ordinal:rows.length+1,document:{_id:'synthetic-profile',defaultProfile:'Default',startDate:new Date(at-3*86400000).toISOString(),created_at:new Date(at-3*86400000).toISOString(),mills:at-3*86400000,units:'mg/dl',store:{Default:{dia:3,carbratio:[{time:'00:00',value:10}],sens:[{time:'00:00',value:50}],basal:[{time:'00:00',value:1}],target_low:[{time:'00:00',value:100}],target_high:[{time:'00:00',value:120}],timezone:'UTC',units:'mg/dl'}}}});
let stamp=1, reconciles=0, statsCalls=0, queryCalls=0;
const authoritativeStats={dataSize:90000000,indexSize:undefined};
const env=req('lib/server/tenant-app/environment')({settings:{enable:['bgnow','delta','direction','timeago','simplealarms','treatmentnotify','pump','loop','upbat','iob','cob','basal','profile','devicestatus']}});
const language=req('lib/language')();language.set('en');
const replay={stream:true,async reconcile(){reconciles++;return {checkpoint:stamp,progress:'synthetic-accepted-input',signature:{stamp,deleted:0},rows,stats:authoritativeStats};}};
function create(){return evaluator({tenant,replay,connection:{async query(){queryCalls++;throw Error('UNEXPECTED_SQL');}},env,language,dbstats:async()=>{statsCalls++;return authoritativeStats;},maxRows:5000,maxBytes:16*1024*1024,includeFrame:true});}
const session=new inspector.Session();const post=(m,p={})=>new Promise((resolve,reject)=>session.post(m,p,(e,r)=>e?reject(e):resolve(r)));
const gc=[];const observer=new PerformanceObserver(list=>{for(const e of list.getEntries())gc.push({duration:e.duration,kind:e.detail.kind});});observer.observe({entryTypes:['gc']});
const delay=monitorEventLoopDelay({resolution:1});
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const sourceFiles=['lib/data/tenant-projection-evaluator.js','lib/data/views/index.js','lib/storage/postgres-projection-read.js','lib/storage/projection-memory-read.js','lib/server/serve/evaluator-runtime.js','lib/storage/postgres-tenant-stats.js','lib/data/working-set.js','lib/data/json-copy.js','lib/storage/clinical-stream-state.js','lib/pgstream/typed-checkpoint.js','lib/pgstream/activity-scheduler.js'];
(async()=>{scope.setTenancyMode('multi');clock.install();clock.pin(at);session.connect();
 const result={head,node:process.version,mode,hours,K,rows:rows.length,inputBytes:Buffer.byteLength(JSON.stringify(rows)),stats:authoritativeStats,sourceFiles:Object.fromEntries(sourceFiles.map(f=>[f,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex')])),resource:{sharedHost:true,cpuAffinity:fs.readFileSync('/proc/self/status','utf8').match(/^Cpus_allowed_list:.*$/m)?.[0],limits:'process --max-old-space-size=512; finite K; no role quota; shared host'},cases:[]};
 const v=create();await v.evaluate({at});
 if(mode==='control'){
  const initial=await v.evaluateTime({at});assert.equal(initial.properties.bgnow.mean,123);
  const original=hash(initial.frame);const next=await v.evaluateTime({at});next.frame.sgvs[0].mgdl=-1;assert.equal(hash(initial.frame),original,'FRAME_ALIAS');
  const aged=await v.evaluateTime({at:at+3*86400000});assert.equal(aged.properties.bgnow.mean,undefined,'DUE_FRESHNESS');
  assert.equal((await v.evaluateTime({at})).properties.bgnow.mean,123,'RESTORE_TIME');
  rows[rows.length-3].document.sgv=124;stamp++;assert.equal((await v.evaluate({at})).properties.bgnow.mean,124,'INPUT_CORRECTION');
  const changed=await v.evaluateTime({at});assert.notEqual(runtime.contentDigest(initial),runtime.contentDigest(changed),'CONTENT_CHANGED');
  result.controls='PASS';v.close();clock.uninstall();observer.disconnect();session.disconnect();fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));return;
 }
 for(const kind of ['due-only','unchanged-input','new-input']){
  clock.pin(at);for(let i=0;i<12;i++)await v.evaluateTime({at});global.gc();await new Promise(setImmediate);
  for(const k of Object.keys(stages))delete stages[k];json={};captures={kept:0,refused:0,copied:0};gc.length=0;delay.reset();delay.enable();
  if(mode==='cpu'){await post('Profiler.enable');await post('Profiler.setSamplingInterval',{interval:100});await post('Profiler.start');}
  if(mode==='heap'){await post('HeapProfiler.enable');await post('HeapProfiler.startSampling',{samplingInterval:16384,includeObjectsCollectedByMajorGC:true,includeObjectsCollectedByMinorGC:true});}
  const before=process.memoryUsage(),cpu=process.cpuUsage(),t=process.hrtime.bigint(),calls={reconciles,statsCalls,queryCalls};let peak=before.heapUsed,peakRss=before.rss,last,frameBytes,digestMs=0,outputMs=0,typedDigestMs=0,typedEncodingMs=0,typedBytes=null;
  const semanticTrace=[];counting=true;
  for(let i=0;i<K;i++){
   if(kind==='new-input'){stamp++;rows[rows.length-3].document.sgv=123+(i%2);}
   const instant=at+i*1000;clock.pin(instant);
   last=await (kind==='due-only'?v.evaluateTime({at:instant}):v.evaluate({at:instant}));
   const d=process.hrtime.bigint();runtime.contentDigest(last);digestMs+=Number(process.hrtime.bigint()-d)/1e6;
   const o=process.hrtime.bigint();frameBytes=Buffer.byteLength(JSON.stringify(last));outputMs+=Number(process.hrtime.bigint()-o)/1e6;
   if(typed){
    const saved={...last};delete saved.encodedRows;delete saved.frame;
    const envelope={tenant,identity:'a'.repeat(64),restoreGeneration:null,outputRevision:1,contentDigest:null,inputCheckpoint:last.checkpoint,checkpoint:last.checkpoint,trigger:last.trigger,result:saved,rows:last.encodedRows??last.rows,frame:last.frame};
    const dt=process.hrtime.bigint();typed.contentOf(envelope);typedDigestMs+=Number(process.hrtime.bigint()-dt)/1e6;
    const et=process.hrtime.bigint();typedBytes=Buffer.byteLength(JSON.stringify([{kind:'evaluator-work-v2',output:typed.bodyOf(envelope)}]));typedEncodingMs+=Number(process.hrtime.bigint()-et)/1e6;
   }
   if(process.env.TRACE==='1')semanticTrace.push(hash(last));
   const m=process.memoryUsage();peak=Math.max(peak,m.heapUsed);peakRss=Math.max(peakRss,m.rss);
   if(i%8===0)await new Promise(setImmediate);
  }
  counting=false;const elapsed=Number(process.hrtime.bigint()-t)/1e6,used=process.cpuUsage(cpu);
  if(mode==='cpu'){const {profile}=await post('Profiler.stop');fs.writeFileSync(path.join(out,kind+'.cpuprofile'),JSON.stringify(profile));}
  if(mode==='heap'){const {profile}=await post('HeapProfiler.stopSampling');fs.writeFileSync(path.join(out,kind+'.heapprofile'),JSON.stringify(profile));}
  await new Promise(setImmediate);delay.disable();const duringGC=[...gc];const end=process.memoryUsage();global.gc();await new Promise(setImmediate);const retained=process.memoryUsage();
  assert.equal(last.properties.bgnow.mean,kind==='new-input'?123+((K-1)%2):123,'CLINICAL_ORACLE');
  result.cases.push({kind,wallMs:elapsed,cpuMs:(used.user+used.system)/1000,before,end,retained,observedPeakHeap:peak,observedPeakRss:peakRss,processMaxRssKiB:process.resourceUsage().maxRSS,gc:duringGC,eventLoopDelayMs:{mean:delay.mean/1e6,max:delay.max/1e6},calls:{reconciles:reconciles-calls.reconciles,statsCalls:statsCalls-calls.statsCalls,queryCalls:queryCalls-calls.queryCalls},stages:JSON.parse(JSON.stringify(stages)),json:{...json},captures:{...captures},digestMs,completedOutputEncodingMs:outputMs,typedDigestMs,typedEncodingMs,typedBytes,completedOutputBytes:frameBytes,clinicalMean:last.properties.bgnow.mean,frameHash:hash(last.frame),...(process.env.TRACE==='1'?{semanticTrace}:{})});
  // Restore synthetic correction before the next mode; no external input is touched.
  rows[rows.length-3].document.sgv=123;stamp++;clock.pin(at);await v.evaluate({at});
 }
 v.close();clock.uninstall();observer.disconnect();session.disconnect();fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));
})().catch(e=>{process.stderr.write(e.stack+'\n');process.exitCode=1;});
