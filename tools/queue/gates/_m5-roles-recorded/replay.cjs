'use strict';
// Reuse frozen native physical verifiers in owned scratch only. No source
// checkout, application boot, connection, build or provider is invoked.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{execFileSync}=require('node:child_process');
const {ensure,sha,canonical}=require('./schema.cjs');
const objects=new Map();
function readObject(repo,head,file){
 ensure(/^[a-f0-9]{40}$/.test(head)&&!path.isAbsolute(file)&&!file.split('/').includes('..'),'ROLE_OBJECT_PATH');
 const key=JSON.stringify([path.resolve(repo),head,file]);
 if(!objects.has(key))objects.set(key,execFileSync('git',['-C',repo,'show',head+':'+file],{maxBuffer:64*1024*1024}));
 // Only immutable committed objects are cached, never current worktree/capture.
 return Buffer.from(objects.get(key));
}
function source(plan,repo,directory){
 ensure(execFileSync('git',['-C',repo,'rev-parse',plan.head+'^{tree}'],{encoding:'utf8'}).trim()===plan.tree,'ROLE_SOURCE_TREE');
 for(const [file,hash]of Object.entries(plan.causalFiles)){
  ensure(!path.isAbsolute(file)&&!file.split('/').includes('..'),'ROLE_SOURCE_PATH');
  const bytes=readObject(repo,plan.head,file);ensure(sha(bytes)===hash,'ROLE_SOURCE_HASH '+file);
  if(plan.oracleFiles.includes(file)){const target=path.join(directory,file);fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,bytes);}
 }
 ensure(sha(readObject(repo,plan.head,'package-lock.json'))===plan.lockSha256,'ROLE_SOURCE_LOCK');
}
function restoreOrigins(value){
 if(Array.isArray(value))return value.map(restoreOrigins);
 if(value&&typeof value==='object'){
  if(Object.keys(value).sort().join(',')==='host,port,scheme'){
   ensure(value.scheme==='http'&&['one.example.test','two.example.test'].includes(value.host)&&Number.isSafeInteger(value.port)&&value.port>0&&value.port<65536,'ROLE_ORIGIN');return 'http://'+value.host+':'+value.port;
  }
  return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,restoreOrigins(v)]));
 }return value;
}
function replay(phase,plan,{repo,deps,originalDirectory,configuration}){
 const scratch=fs.mkdtempSync(path.join(os.tmpdir(),'m5-role-recorded-'));
 try{
  for(const [file,hash]of Object.entries(plan.adapterHashes))ensure(sha(fs.readFileSync(path.join(__dirname,file)))===hash,'ROLE_ADAPTER_HASH '+file);
  source(plan,repo,scratch);
  ensure(typeof deps==='string'&&path.isAbsolute(deps)&&fs.existsSync(path.join(deps,'mongodb/package.json')),'NO-INSTRUMENT: explicit existing mongodb dependencies required');
  ensure(sha(fs.readFileSync(path.join(deps,'../package-lock.json')))===plan.lockSha256,'NO-INSTRUMENT: read-only dependency lock mismatch');
  ensure(JSON.parse(fs.readFileSync(path.join(deps,'mongodb/package.json'))).version===plan.mongodbVersion,'NO-INSTRUMENT: mongodb version mismatch');
  fs.symlinkSync(deps,path.join(scratch,'node_modules'),'dir');
  const control=phase.kind==='control'?plan.controls.find(c=>c.id===phase.id):undefined;
  const verifier=control?.verifier||plan.phaseVerifiers[phase.phase];ensure(plan.adapterHashes[verifier],'ROLE_REVIEWED_VERIFIER');
  const directory=path.join(scratch,'observations');fs.mkdirSync(directory);
  if(originalDirectory){
   for(const file of plan.requiredRaw[phase.phase])fs.copyFileSync(path.join(originalDirectory,file),path.join(directory,file));
   if(control){ensure(/^ERR_ASSERTION$/m.test(fs.readFileSync(path.join(originalDirectory,'native.log'),'utf8')),'ROLE_ORIGINAL_ASSERTION_WITNESS');fs.writeFileSync(path.join(directory,'native.log'),'ERR_ASSERTION\n');}
  }else{
   for(const [file,value]of Object.entries(phase.observations)){ensure(plan.requiredRaw[phase.phase].includes(file),'ROLE_RAW_SELECTION');fs.writeFileSync(path.join(directory,file),JSON.stringify(restoreOrigins(value)));}
   if(control){ensure(phase.assertionWitness==='ERR_ASSERTION','ROLE_ASSERTION_WITNESS');fs.writeFileSync(path.join(directory,'native.log'),'ERR_ASSERTION\n');}
  }
  return require('./phase-verdict.cjs')({directory,result:phase.process,configuration:configuration||restoreOrigins(phase.configuration),control,requiredRaw:plan.requiredRaw[phase.phase],sourceDir:scratch,sourceFiles:plan.causalFiles,verify:require(path.join(__dirname,verifier))});
 }finally{fs.rmSync(scratch,{recursive:true,force:true});}
}
module.exports={replay,source,restoreOrigins,readObject};
