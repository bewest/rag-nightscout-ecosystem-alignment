'use strict';
// Uses the actual paired entrypoint/load-env/service-environment/core modules.
// Only CLI execution is stopped at its public main boundary, before SUT boot.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),Module=require('node:module'),{execFileSync}=require('node:child_process');
async function child(root,mode){
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'clinical-startup-')),helper=path.join(__dirname,'clinical-intake-timeline.cjs');
 const targets=path.join(directory,'targets.json'),environment=path.join(directory,'env.json');
 fs.writeFileSync(targets,JSON.stringify({ids:['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222']}));
 fs.writeFileSync(environment,JSON.stringify({NS_M7_DIAGNOSTICS:'1',NS_M7_DIAGNOSTICS_INTERVAL_MS:'1000'}),{mode:0o600});
 process.env.NS_M7_DIAGNOSTICS='0';delete process.env.NS_M7_CLINICAL_TIMELINE;delete process.env.NS_CONNECTION_BUDGET_FILE;delete process.env.NS_CONNECTION_BUDGET_PLAN_FILE;delete process.env.NS_CONNECTION_BUDGET_CLAIM_DIR;process.env.NS_ENV_FILE=environment;
 let exports;
 if(mode==='eager'||mode==='exports'||mode==='raw'){
  const source=fs.readFileSync(helper,'utf8'),marker='// CANONICAL_LOAD_BOUNDARY: no app require occurs before the entrypoint.';assert.equal(source.split(marker).length,2);
  const broken=new Module(helper,module);broken.filename=helper;broken.paths=module.paths;const changed=mode==='raw'?source.replace('raw:rawFile?{file:rawFile}:null','raw:null'):mode==='eager'?source.replace(marker,'require(files.runtime);'):source.replace('Object.defineProperties(wrapped,Object.getOwnPropertyDescriptors(original));','const descriptors=Object.getOwnPropertyDescriptors(original);delete descriptors.canonical;Object.defineProperties(wrapped,descriptors);');assert.notEqual(changed,source);broken._compile(changed,helper);exports=broken.exports;
 }else exports=require(helper);
 const realLoad=Module._load,entrypoint=path.join(root,'deploy/multitenant/entrypoint.js'),cli=require.resolve(path.join(root,'lib/cli')),diagnostic=path.join(root,'lib/diagnostics/m7.js');
 const originals=new Map();let mainCalled=false,environmentAtDiagnostic=null,armed;
 Module._load=function(request,parent,isMain){
  const file=Module._resolveFilename(request,parent,isMain);
  if(file===cli)return {main(args){assert.deepEqual(args,['multitenant','evaluator']);mainCalled=true;assert.equal(process.env.NS_M7_DIAGNOSTICS,'1');
   // Actual canonical caller imports the same modules; no evaluator instance.
   require(path.join(root,'lib/server/serve/evaluator-preview.js'));
   require(path.join(root,'lib/pgstream/receiver.js'));require(path.join(root,'lib/pgstream/activity-scheduler.js'));return 'STOP_BEFORE_BOOT';}};
  if(file===diagnostic&&environmentAtDiagnostic===null)environmentAtDiagnostic=process.env.NS_M7_DIAGNOSTICS;
  const value=Reflect.apply(realLoad,this,arguments);if(armed&&Object.values(armed.files).includes(file)&&!originals.has(file))originals.set(file,value);return value;
 };
 try{
  armed=exports.arm({root,targetsFile:targets,traceFile:path.join(directory,'trace.jsonl'),statusFile:path.join(directory,'status.json'),rawFile:path.join(directory,'raw.jsonl'),rawStatusFile:path.join(directory,'raw-status.json')});
  const earlyCore=Object.keys(require.cache).filter(file=>file.startsWith(root+'/lib/'));const earlyTargets=Object.values(armed.files).filter(file=>require.cache[file]);
  process.argv=[process.execPath,entrypoint,'evaluator'];require(entrypoint);
  assert(mainCalled,'ACTUAL_ENTRYPOINT_MAIN_BOUNDARY_REQUIRED');const diag=require(diagnostic);
  const runtime=require(armed.files.runtime),receiver=require(armed.files.receiver),scheduler=require(armed.files.scheduler),pg=require(armed.files.pg);
  for(const [kind,value]of Object.entries({runtime,receiver,scheduler,pg})){const file=armed.files[kind];assert.equal(value,require(file),'REPEATED_EXPORT_IDENTITY');assert.equal(value,require.cache[file].exports,'CACHE_EXPORT_IDENTITY');}
  const create=receiver.create,start=scheduler.start,connect=pg.Pool.prototype.connect,query=pg.Client.prototype.query;
  require(armed.files.receiver);require(armed.files.scheduler);require(armed.files.pg);require(armed.files.runtime);
  assert.equal(receiver.create,create);assert.equal(scheduler.start,start);assert.equal(pg.Pool.prototype.connect,connect);assert.equal(pg.Client.prototype.query,query);
  const original=originals.get(armed.files.runtime);assert(original);for(const key of Reflect.ownKeys(original))assert.deepEqual(Object.getOwnPropertyDescriptor(runtime,key),Object.getOwnPropertyDescriptor(original,key),'RUNTIME_STATIC_DESCRIPTOR_'+String(key));
  const result={rawArmed:armed.tap.rawStatus()!==null&&fs.existsSync(path.join(directory,'raw.jsonl')),earlyCore:earlyCore.length,earlyTargets:earlyTargets.length,environmentAtDiagnostic,diagnosticsEnabled:diag.enabled,canonicalEntrypoint:true,stableCacheExports:true,stableRepeatedHooks:true,canonicalStaticExport:typeof runtime.canonical==='function'};
  diag.close();await armed.tap.seal();return result;
 }finally{if(require.cache[diagnostic])require.cache[diagnostic].exports.close();if(armed)armed.restore();Module._load=realLoad;}
}
(async()=>{
 if(process.argv[2]==='--child'){const result=await child(path.resolve(process.argv[3]),process.argv[4]);process.stdout.write(JSON.stringify(result)+'\n');return;}
 const root=path.resolve(process.argv[2]),run=mode=>JSON.parse(execFileSync(process.execPath,['--max-old-space-size=128',__filename,'--child',root,mode],{encoding:'utf8',timeout:7000,stdio:'pipe'}));
 const criterion=value=>{assert.equal(value.rawArmed,true,'CANONICAL_RAW_ARM_REQUIRED');assert.equal(value.earlyCore,0,'PRELOAD_MUST_NOT_INITIALIZE_CORE');assert.equal(value.earlyTargets,0,'PRELOAD_MUST_NOT_INITIALIZE_TARGET_MODULES');assert.equal(value.environmentAtDiagnostic,'1','CANONICAL_PRIVATE_ENV_BEFORE_DIAGNOSTICS');assert.equal(value.diagnosticsEnabled,true);assert.equal(value.canonicalStaticExport,true);};
 const original=run('restored');criterion(original);assert.throws(()=>criterion(run('raw')),{code:'ERR_ASSERTION'},'RAW_ARM_ABLATION_MUST_FAIL');assert.throws(()=>run('exports'),error=>error.status===1&&String(error.stderr).includes('RUNTIME_STATIC_DESCRIPTOR_canonical'),'STATIC_EXPORT_ABLATION_MUST_FAIL');const broken=run('eager');assert.throws(()=>criterion(broken),{code:'ERR_ASSERTION'});const restored=run('restored');criterion(restored);
 console.log(JSON.stringify({status:'PASS',scope:'actual paired entrypoint and private environment reader; CLI stops before SUT boot',original,staticExportAblation:'RED_EXPECTED',eagerControl:broken,restored,actors:'no application services or database connections'}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
